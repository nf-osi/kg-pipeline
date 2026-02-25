#!/usr/bin/env python3
"""Aggregate scored runs and publish them to a docs branch for GH Pages."""
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None  # type: ignore[assignment]


@dataclass
class RunSummary:
    name: str
    model: str | None
    solver: str | None
    overall_score: float | None
    overall_cost: float | None
    summary_path: Path
    started_at: str | None = None
    completed_at: str | None = None
    total_samples: int | None = None
    git_commit: str | None = None
    task_name: str | None = None
    score_stderr: float | None = None
    min_sample_time: float | None = None
    max_sample_time: float | None = None
    avg_sample_time: float | None = None
    difficulty_scores: dict[str, float] = field(default_factory=dict)
    category_scores: dict[str, float] = field(default_factory=dict)
    frustration_scores: dict[str, float] = field(default_factory=dict)
    frustration_samples: list[dict] = field(default_factory=list)
    level_samples: list[dict] = field(default_factory=list)
    complexity_samples: list[dict] = field(default_factory=list)
    task_stats: dict[str, dict] = field(default_factory=dict)


QuestionMeta = dict[str, dict[str, str]]  # id -> {level, complexity, user_frustration}


def load_question_metadata(yaml_path: Path) -> QuestionMeta:
    """Load question difficulty metadata from eval_tools.yaml."""
    if yaml is None:
        print("PyYAML not installed; skipping difficulty breakdown", file=sys.stderr)
        return {}
    if not yaml_path.exists():
        return {}
    try:
        data = yaml.safe_load(yaml_path.read_text())
    except Exception as exc:
        print(f"Warning: failed to parse {yaml_path}: {exc}", file=sys.stderr)
        return {}
    meta: QuestionMeta = {}
    for component in data.get("components", []):
        for q in component.get("questions", []):
            qid = q.get("id")
            if qid:
                meta[qid] = {
                    "level": q.get("level", ""),
                    "complexity": q.get("complexity", ""),
                    "user_frustration": q.get("user_frustration", ""),
                }
    return meta


def _compute_sample_breakdowns(
    summaries_data: list[dict],
    question_meta: QuestionMeta,
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, float],
    list[dict],
    list[dict],
    list[dict],
]:
    """Compute mean recall grouped by difficulty, category, and frustration."""
    diff_groups: dict[str, list[float]] = {}
    cat_groups: dict[str, list[float]] = {}
    frust_groups: dict[str, list[float]] = {}
    frust_samples: list[dict] = []
    level_samples: list[dict] = []
    complexity_samples: list[dict] = []
    for sample in summaries_data:
        sid = sample.get("id", "")
        scores = sample.get("scores", {})
        # Find the first scorer's value
        score_val = None
        for scorer in scores.values():
            if isinstance(scorer, dict) and "value" in scorer:
                score_val = scorer["value"]
                break
        if score_val is None:
            continue
        # Difficulty + frustration breakdown (from eval_tools.yaml metadata)
        meta = question_meta.get(sid)
        if meta:
            level = meta.get("level", "")
            complexity = meta.get("complexity", "")
            frustration = meta.get("user_frustration", "")
            if level:
                diff_groups.setdefault(f"level/{level}", []).append(score_val)
                level_samples.append(
                    {"id": sid, "level": level, "score": score_val}
                )
            if complexity:
                diff_groups.setdefault(f"complexity/{complexity}", []).append(score_val)
                complexity_samples.append(
                    {"id": sid, "complexity": complexity, "score": score_val}
                )
            if frustration:
                frust_groups.setdefault(f"frustration/{frustration}", []).append(
                    score_val
                )
                frust_samples.append(
                    {"id": sid, "frustration": frustration, "score": score_val}
                )
        # Category breakdown (from per-sample metadata)
        category = (sample.get("metadata") or {}).get("category", "")
        if category:
            cat_groups.setdefault(f"category/{category}", []).append(score_val)
    difficulty_scores = {k: sum(v) / len(v) for k, v in diff_groups.items() if v}
    category_scores = {k: sum(v) / len(v) for k, v in cat_groups.items() if v}
    frustration_scores = {k: sum(v) / len(v) for k, v in frust_groups.items() if v}
    return (
        difficulty_scores,
        category_scores,
        frustration_scores,
        frust_samples,
        level_samples,
        complexity_samples,
    )


def _duration_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
        return (e - s).total_seconds()
    except (ValueError, TypeError):
        return None


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return ""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def load_runs(
    log_root: Path,
    question_meta: QuestionMeta,
) -> list[RunSummary]:
    runs: list[RunSummary] = []
    for run_dir in sorted(log_root.iterdir()):
        if not run_dir.is_dir():
            continue
        summary_file = run_dir / "summary_stats.json"
        scores_file = run_dir / "scores.json"
        if not summary_file.exists() or not scores_file.exists():
            continue
        try:
            summary_data = json.loads(summary_file.read_text())
            overall = summary_data.get("stats", {}).get("overall", {})
            scores = json.loads(scores_file.read_text())
            eval_spec = (
                scores.get("results", [{}])[0].get("eval_spec")
                if scores.get("results")
                else None
            )
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            print(f"Skipping {run_dir}: failed to parse JSON ({exc})", file=sys.stderr)
            continue

        # Extract per-task/tag breakdown from summary_stats.json
        task_stats: dict[str, dict] = {}
        for key, val in summary_data.get("stats", {}).items():
            if key.startswith("task/") or key.startswith("tag/"):
                task_stats[key] = val

        # Read header.json for extra metadata
        started_at = None
        completed_at = None
        total_samples = None
        git_commit = None
        task_name = None
        header_file = run_dir / "header.json"
        if header_file.exists():
            try:
                header = json.loads(header_file.read_text())
                stats = header.get("stats", {})
                started_at = stats.get("started_at")
                completed_at = stats.get("completed_at")
                results = header.get("results", {})
                total_samples = results.get("total_samples")
                eval_info = header.get("eval", {})
                task_name = eval_info.get("task")
                revision = eval_info.get("revision", {})
                git_commit = revision.get("commit")
            except json.JSONDecodeError:
                pass  # header.json is optional enrichment

        # Read summaries.json for per-sample timing and difficulty breakdown
        min_sample_time = None
        max_sample_time = None
        avg_sample_time = None
        difficulty_scores: dict[str, float] = {}
        category_scores: dict[str, float] = {}
        frustration_scores: dict[str, float] = {}
        frustration_samples: list[dict] = []
        level_samples: list[dict] = []
        complexity_samples: list[dict] = []
        summaries_file = run_dir / "summaries.json"
        if summaries_file.exists():
            try:
                samples = json.loads(summaries_file.read_text())
                times = [s["total_time"] for s in samples if "total_time" in s]
                if times:
                    min_sample_time = min(times)
                    max_sample_time = max(times)
                    avg_sample_time = sum(times) / len(times)
                (
                    difficulty_scores,
                    category_scores,
                    frustration_scores,
                    frustration_samples,
                    level_samples,
                    complexity_samples,
                ) = _compute_sample_breakdowns(samples, question_meta)
            except (json.JSONDecodeError, TypeError):
                pass

        runs.append(
            RunSummary(
                name=run_dir.name,
                model=(eval_spec or {}).get("model"),
                solver=(eval_spec or {}).get("solver"),
                overall_score=overall.get("score"),
                overall_cost=overall.get("cost"),
                summary_path=summary_file,
                started_at=started_at,
                completed_at=completed_at,
                total_samples=total_samples,
                git_commit=git_commit,
                task_name=task_name,
                score_stderr=overall.get("score_stderr"),
                min_sample_time=min_sample_time,
                max_sample_time=max_sample_time,
                avg_sample_time=avg_sample_time,
                difficulty_scores=difficulty_scores,
                category_scores=category_scores,
                frustration_scores=frustration_scores,
                frustration_samples=frustration_samples,
                level_samples=level_samples,
                complexity_samples=complexity_samples,
                task_stats=task_stats,
            )
        )
    return runs


def _format_cost(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:.2f}"


def _format_date(iso_ts: str | None) -> str:
    if iso_ts is None:
        return ""
    try:
        dt = datetime.fromisoformat(iso_ts)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return html.escape(iso_ts)


def _format_score_with_stderr(score: float | None, stderr: float | None) -> str:
    if score is None:
        return "N/A"
    s = f"{score:.4f}"
    if stderr is not None:
        s += f" &plusmn; {stderr:.4f}"
    return s


def _format_score(value: float | None) -> str:
    return f"{value:.4f}" if value is not None else ""


def _esc(value: str | None) -> str:
    return html.escape(value) if value else ""


# Ordered keys for difficulty columns
DIFFICULTY_KEYS = [
    "level/baseline",
    "level/advanced",
    "complexity/0-hop",
    "complexity/1-hop",
    "complexity/2-hop",
]

DIFFICULTY_LABELS = {
    "level/baseline": "Baseline",
    "level/advanced": "Advanced",
    "complexity/0-hop": "0-hop",
    "complexity/1-hop": "1-hop",
    "complexity/2-hop": "2-hop",
}

LEVEL_KEYS = ["level/baseline", "level/advanced"]
LEVEL_LABELS = {k: DIFFICULTY_LABELS[k] for k in LEVEL_KEYS}

COMPLEXITY_KEYS = ["complexity/0-hop", "complexity/1-hop", "complexity/2-hop"]
COMPLEXITY_LABELS = {k: DIFFICULTY_LABELS[k] for k in COMPLEXITY_KEYS}

CATEGORY_KEYS = [
    "category/MUT",
    "category/AM",
    "category/CL",
    "category/AB",
    "category/GR",
    "category/PI",
    "category/CR",
]

CATEGORY_LABELS = {
    "category/MUT": "Mutation",
    "category/AM": "Animal Model",
    "category/CL": "Cell Line",
    "category/AB": "Antibody",
    "category/GR": "Genetic Reagent",
    "category/PI": "Investigator",
    "category/CR": "Cross-Resource",
}

FRUSTRATION_KEYS = [
    "frustration/low",
    "frustration/moderate",
    "frustration/high",
    "frustration/very_high",
]

FRUSTRATION_LABELS = {
    "frustration/low": "Low",
    "frustration/moderate": "Moderate",
    "frustration/high": "High",
    "frustration/very_high": "Very High",
}


def render_table(
    runs: list[RunSummary], has_difficulty: bool, has_categories: bool
) -> str:
    difficulty_cols = ""
    if has_difficulty:
        difficulty_cols = "".join(
            f"<th>{DIFFICULTY_LABELS[k]}</th>" for k in DIFFICULTY_KEYS
        )
    category_cols = ""
    if has_categories:
        category_cols = "".join(
            f"<th>{CATEGORY_LABELS[k]}</th>" for k in CATEGORY_KEYS
        )

    def _difficulty_cells(run: RunSummary) -> str:
        if not has_difficulty:
            return ""
        return "".join(
            f"<td>{_format_score(run.difficulty_scores.get(k))}</td>"
            for k in DIFFICULTY_KEYS
        )

    def _category_cells(run: RunSummary) -> str:
        if not has_categories:
            return ""
        return "".join(
            f"<td>{_format_score(run.category_scores.get(k))}</td>"
            for k in CATEGORY_KEYS
        )

    rows = "\n".join(
        (
            f"<tr><td>{_esc(run.task_name)}</td>"
            f"<td>{_esc(run.model)}</td>"
            f"<td>{_esc(run.solver)}</td>"
            f"<td>{run.total_samples if run.total_samples is not None else ''}</td>"
            f"<td>{_format_score_with_stderr(run.overall_score, run.score_stderr)}</td>"
            + _difficulty_cells(run)
            + _category_cells(run)
            + f"<td>{_format_cost(run.overall_cost)}</td>"
            f"<td>{_format_date(run.started_at)}</td>"
            f"<td>{_format_duration(_duration_seconds(run.started_at, run.completed_at))}</td>"
            f"<td>{_format_duration(run.avg_sample_time)}</td>"
            f"<td>{_format_duration(run.min_sample_time)}</td>"
            f"<td>{_format_duration(run.max_sample_time)}</td>"
            f"<td><code>{_esc(run.git_commit)}</code></td></tr>"
        )
        for run in runs
    )
    return f"""
<table id="runs-table">
  <thead>
    <tr>
      <th>Task</th>
      <th>Model</th>
      <th>Solver</th>
      <th>Samples</th>
      <th>Recall</th>
      {difficulty_cols}
      {category_cols}
      <th>Total Cost (USD)</th>
      <th>Date</th>
      <th>Total Time</th>
      <th>Avg Time / Sample</th>
      <th>Shortest Sample</th>
      <th>Longest Sample</th>
      <th>Commit</th>
    </tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>
"""


def _build_chart_data(runs: list[RunSummary]) -> tuple[str, str]:
    cost_points = []
    time_points = []
    for run in runs:
        if run.overall_score is None:
            continue
        label = _esc(run.model or run.name)
        if run.overall_cost is not None:
            cost_points.append(
                {"x": run.overall_cost, "y": run.overall_score, "label": label}
            )
        total_secs = _duration_seconds(run.started_at, run.completed_at)
        if total_secs is not None:
            time_points.append(
                {"x": total_secs / 60, "y": run.overall_score, "label": label}
            )
    return json.dumps(cost_points), json.dumps(time_points)


def _build_bar_chart_data(
    runs: list[RunSummary],
    keys: list[str],
    labels: dict[str, str],
    score_attr: str,
) -> str:
    """Build model-averaged grouped bar chart data."""
    model_scores: dict[str, list[dict[str, float | None]]] = {}
    for run in runs:
        scores: dict[str, float] = getattr(run, score_attr)
        if not scores:
            continue
        label = _esc(run.model or run.name)
        entry: dict[str, float | None] = {}
        for key in keys:
            entry[labels[key]] = scores.get(key)
        model_scores.setdefault(label, []).append(entry)
    entries = []
    for label, score_list in model_scores.items():
        entry_out: dict[str, object] = {"label": label}
        for key in keys:
            gl = labels[key]
            vals = [s[gl] for s in score_list if s.get(gl) is not None]
            entry_out[gl] = sum(vals) / len(vals) if vals else None
        entries.append(entry_out)
    return json.dumps(entries)


_LEVEL_X = {"baseline": 0, "advanced": 1}
_COMPLEXITY_X = {"0-hop": 0, "1-hop": 1, "2-hop": 2}
_FRUSTRATION_X = {"low": 0, "moderate": 1, "high": 2, "very_high": 3}


def _build_slope_data(
    runs: list[RunSummary],
    samples_attr: str,
    key_field: str,
    x_map: dict[str, int],
) -> str:
    """Build per-question scatter points for a slope chart."""
    points = []
    for run in runs:
        label = _esc(run.model or run.name)
        for s in getattr(run, samples_attr):
            x = x_map.get(s[key_field])
            if x is not None:
                points.append(
                    {"x": x, "y": s["score"], "label": label, "qid": s["id"]}
                )
    return json.dumps(points)


def _build_sweet_spot_table(
    runs: list[RunSummary],
    question_meta: QuestionMeta,
    recall_threshold: float = 0.95,
) -> str:
    """Build an HTML table of high/very_high frustration questions with best recall >= threshold."""
    # Collect best recall per (question, model)
    best: dict[str, dict[str, float]] = {}  # qid -> {model -> best_score}
    frust_map: dict[str, str] = {}  # qid -> frustration level
    for run in runs:
        model = _esc(run.model or run.name)
        for s in run.frustration_samples:
            qid = s["id"]
            frust_map[qid] = s["frustration"]
            best.setdefault(qid, {})
            if s["score"] > best[qid].get(model, -1):
                best[qid][model] = s["score"]
    # Filter: high/very_high frustration AND best recall across any model >= threshold
    rows = []
    for qid, model_scores in best.items():
        frust = frust_map.get(qid, "")
        if frust not in ("high", "very_high"):
            continue
        top_score = max(model_scores.values())
        if top_score < recall_threshold:
            continue
        top_model = max(model_scores, key=lambda m: model_scores[m])
        meta = question_meta.get(qid, {})
        rows.append(
            {
                "qid": qid,
                "frustration": FRUSTRATION_LABELS.get(
                    f"frustration/{frust}", frust
                ),
                "best_recall": top_score,
                "best_model": top_model,
                "complexity": meta.get("complexity", ""),
            }
        )
    if not rows:
        return ""
    rows.sort(key=lambda r: (-r["best_recall"], r["qid"]))
    row_html = "\n".join(
        f"<tr><td>{r['qid']}</td><td>{r['frustration']}</td>"
        f"<td>{r['complexity']}</td>"
        f"<td>{r['best_recall']:.2f}</td>"
        f"<td>{r['best_model']}</td></tr>"
        for r in rows
    )
    return f"""
<h2>High-Impact Questions</h2>
<p><small>Questions with high or very high user frustration where best recall &ge; {recall_threshold:.0%} &mdash;
queries the current portal struggles with but the KG pipeline handles well.</small></p>
<table id="sweet-spot-table">
  <thead>
    <tr>
      <th>Question</th>
      <th>User Frustration</th>
      <th>Complexity</th>
      <th>Best Recall</th>
      <th>Best Model</th>
    </tr>
  </thead>
  <tbody>
    {row_html}
  </tbody>
</table>
"""


def write_site(
    runs: list[RunSummary], destination: Path, question_meta: QuestionMeta
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    has_difficulty = any(run.difficulty_scores for run in runs)
    has_categories = any(run.category_scores for run in runs)
    has_frustration = any(run.frustration_scores for run in runs)
    data = [
        {
            "run": run.name,
            "model": run.model,
            "solver": run.solver,
            "score": run.overall_score,
            "cost": run.overall_cost,
            "task_name": run.task_name,
            "total_samples": run.total_samples,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "git_commit": run.git_commit,
            "score_stderr": run.score_stderr,
            "difficulty_scores": run.difficulty_scores,
            "category_scores": run.category_scores,
            "frustration_scores": run.frustration_scores,
            "task_stats": run.task_stats,
        }
        for run in runs
    ]
    (destination / "runs.json").write_text(json.dumps(data, indent=2))
    table_html = render_table(runs, has_difficulty, has_categories)
    cost_chart_data, time_chart_data = _build_chart_data(runs)
    level_chart_data = _build_bar_chart_data(
        runs, LEVEL_KEYS, LEVEL_LABELS, "difficulty_scores"
    )
    complexity_slope_data = _build_slope_data(
        runs, "complexity_samples", "complexity", _COMPLEXITY_X
    )
    category_chart_data = _build_bar_chart_data(
        runs, CATEGORY_KEYS, CATEGORY_LABELS, "category_scores"
    )
    frustration_scatter_data = _build_slope_data(
        runs, "frustration_samples", "frustration", _FRUSTRATION_X
    )
    sweet_spot_html = _build_sweet_spot_table(runs, question_meta)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sort_script = """
<script>
document.addEventListener("DOMContentLoaded", function() {
  var table = document.getElementById("runs-table");
  var headers = table.querySelectorAll("th");
  var sortOrder = {};
  headers.forEach(function(th, index) {
    th.style.cursor = "pointer";
    th.addEventListener("click", function() {
      var asc = sortOrder[index] = !sortOrder[index];
      var tbody = table.querySelector("tbody");
      var rows = Array.from(tbody.querySelectorAll("tr"));
      rows.sort(function(a, b) {
        var aText = a.children[index].textContent;
        var bText = b.children[index].textContent;
        var aVal = parseFloat(aText.replace(/[$,]/g, ""));
        var bVal = parseFloat(bText.replace(/[$,]/g, ""));
        if (!isNaN(aVal) && !isNaN(bVal)) return asc ? aVal - bVal : bVal - aVal;
        return asc ? aText.localeCompare(bText) : bText.localeCompare(aText);
      });
      rows.forEach(function(r) { tbody.appendChild(r); });
    });
  });
});
</script>
"""
    level_labels_json = json.dumps([LEVEL_LABELS[k] for k in LEVEL_KEYS])
    complexity_labels_json = json.dumps(
        [COMPLEXITY_LABELS[k] for k in COMPLEXITY_KEYS]
    )
    cat_labels_json = json.dumps([CATEGORY_LABELS[k] for k in CATEGORY_KEYS])
    chart_script = f"""
<script>
function drawScatter(canvasId, data, xLabel, xFmt) {{
  if (!data.length) return;
  var canvas = document.getElementById(canvasId);
  var ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  var W = canvas.width, H = canvas.height;
  var pad = {{top: 30, right: 30, bottom: 50, left: 60}};
  var pW = W - pad.left - pad.right;
  var pH = H - pad.top - pad.bottom;

  var maxX = Math.max.apply(null, data.map(function(d) {{ return d.x; }})) * 1.15;
  var maxY = Math.min(1, Math.max.apply(null, data.map(function(d) {{ return d.y; }})) * 1.25);

  ctx.strokeStyle = "#999";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, H - pad.bottom);
  ctx.lineTo(W - pad.right, H - pad.bottom);
  ctx.stroke();

  ctx.fillStyle = "#666";
  ctx.font = "12px sans-serif";
  ctx.textAlign = "center";
  for (var i = 0; i <= 5; i++) {{
    var xVal = (maxX / 5) * i;
    var x = pad.left + (xVal / maxX) * pW;
    ctx.fillText(xFmt(xVal), x, H - pad.bottom + 18);
    ctx.strokeStyle = "#eee";
    ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, H - pad.bottom); ctx.stroke();
  }}
  ctx.textAlign = "right";
  for (var j = 0; j <= 5; j++) {{
    var yVal = (maxY / 5) * j;
    var y = H - pad.bottom - (yVal / maxY) * pH;
    ctx.fillText(yVal.toFixed(2), pad.left - 8, y + 4);
    ctx.strokeStyle = "#eee";
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
  }}

  ctx.fillStyle = "#333";
  ctx.font = "14px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(xLabel, W / 2, H - 5);
  ctx.save();
  ctx.translate(15, H / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText("Recall", 0, 0);
  ctx.restore();

  var colors = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7"];
  var modelColors = {{}};
  var ci = 0;
  data.forEach(function(d) {{
    if (!modelColors[d.label]) modelColors[d.label] = colors[ci++ % colors.length];
  }});

  data.forEach(function(d) {{
    var x = pad.left + (d.x / maxX) * pW;
    var y = H - pad.bottom - (d.y / maxY) * pH;
    ctx.fillStyle = modelColors[d.label];
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, 2 * Math.PI);
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = "#333";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(d.label, x + 9, y + 4);
  }});
}}

function drawGroupedBar(canvasId, data, groups) {{
  if (!data.length) return;
  var canvas = document.getElementById(canvasId);
  var ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  var W = canvas.width, H = canvas.height;
  var pad = {{top: 30, right: 20, bottom: 80, left: 60}};
  var pW = W - pad.left - pad.right;
  var pH = H - pad.top - pad.bottom;

  var n = data.length;
  var g = groups.length;
  var groupWidth = pW / n;
  var barWidth = (groupWidth * 0.8) / g;
  var gap = groupWidth * 0.2;

  var colors = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7"];

  // y-axis
  ctx.strokeStyle = "#999";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, H - pad.bottom);
  ctx.lineTo(W - pad.right, H - pad.bottom);
  ctx.stroke();

  // y grid + labels
  ctx.fillStyle = "#666";
  ctx.font = "12px sans-serif";
  ctx.textAlign = "right";
  for (var j = 0; j <= 5; j++) {{
    var yVal = j * 0.2;
    var y = H - pad.bottom - (yVal) * pH;
    ctx.fillText(yVal.toFixed(1), pad.left - 8, y + 4);
    ctx.strokeStyle = "#eee";
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
  }}

  // y-axis label
  ctx.fillStyle = "#333";
  ctx.font = "14px sans-serif";
  ctx.save();
  ctx.translate(15, H / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillText("Recall", 0, 0);
  ctx.restore();

  // bars
  data.forEach(function(entry, i) {{
    var x0 = pad.left + i * groupWidth + gap / 2;
    groups.forEach(function(gName, gi) {{
      var val = entry[gName];
      if (val == null) return;
      var bx = x0 + gi * barWidth;
      var bh = val * pH;
      var by = H - pad.bottom - bh;
      ctx.fillStyle = colors[gi % colors.length];
      ctx.fillRect(bx, by, barWidth - 1, bh);
      // value label
      ctx.fillStyle = "#333";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(val.toFixed(2), bx + barWidth / 2, by - 4);
    }});
    // model label
    ctx.fillStyle = "#333";
    ctx.font = "11px sans-serif";
    ctx.save();
    ctx.translate(x0 + (g * barWidth) / 2, H - pad.bottom + 12);
    ctx.rotate(-Math.PI / 6);
    ctx.textAlign = "right";
    ctx.fillText(entry.label, 0, 0);
    ctx.restore();
  }});

  // legend
  var lx = W - pad.right - 10;
  var ly = pad.top + 5;
  groups.forEach(function(gName, gi) {{
    ctx.fillStyle = "#333";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(gName, lx - 16, ly + gi * 18 + 11);
    ctx.fillStyle = colors[gi % colors.length];
    ctx.fillRect(lx - 12, ly + gi * 18, 12, 12);
  }});
}}

function drawSlope(canvasId, data, categories) {{
  if (!data.length) return;
  var canvas = document.getElementById(canvasId);
  var ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  var W = canvas.width, H = canvas.height;
  var pad = {{top: 30, right: 30, bottom: 50, left: 60}};
  var pW = W - pad.left - pad.right;
  var pH = H - pad.top - pad.bottom;
  var nCat = categories.length;

  // axes
  ctx.strokeStyle = "#999";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, H - pad.bottom);
  ctx.lineTo(W - pad.right, H - pad.bottom);
  ctx.stroke();

  // y grid
  ctx.fillStyle = "#666";
  ctx.font = "12px sans-serif";
  ctx.textAlign = "right";
  for (var j = 0; j <= 5; j++) {{
    var yVal = j * 0.2;
    var y = H - pad.bottom - yVal * pH;
    ctx.fillText(yVal.toFixed(1), pad.left - 8, y + 4);
    ctx.strokeStyle = "#eee";
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
  }}

  // y-axis label
  ctx.fillStyle = "#333";
  ctx.font = "14px sans-serif";
  ctx.save();
  ctx.translate(15, H / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillText("Recall", 0, 0);
  ctx.restore();

  // x positions for each category
  var xPositions = [];
  ctx.fillStyle = "#333";
  ctx.font = "12px sans-serif";
  ctx.textAlign = "center";
  categories.forEach(function(cat, ci) {{
    var x = pad.left + (ci / (nCat - 1)) * pW;
    xPositions.push(x);
    ctx.fillText(cat, x, H - pad.bottom + 20);
  }});

  // model colors
  var colors = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7"];
  var modelColors = {{}};
  var ci = 0;
  data.forEach(function(d) {{
    if (!modelColors[d.label]) modelColors[d.label] = colors[ci++ % colors.length];
  }});

  // average by model per category
  var modelList = Object.keys(modelColors);
  var modelAvgs = {{}};
  modelList.forEach(function(m) {{
    var avgs = [];
    for (var c = 0; c < nCat; c++) {{
      var vals = [];
      data.forEach(function(d) {{
        if (d.label === m && d.x === c) vals.push(d.y);
      }});
      avgs.push(vals.length ? vals.reduce(function(a, b) {{ return a + b; }}, 0) / vals.length : null);
    }}
    modelAvgs[m] = avgs;
  }});

  // draw lines and dots
  modelList.forEach(function(m) {{
    var avgs = modelAvgs[m];
    var color = modelColors[m];
    // line segments
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    var started = false;
    avgs.forEach(function(val, ci) {{
      if (val == null) return;
      var x = xPositions[ci];
      var y = H - pad.bottom - val * pH;
      if (!started) {{ ctx.moveTo(x, y); started = true; }}
      else ctx.lineTo(x, y);
    }});
    ctx.stroke();
    // dots with value labels
    avgs.forEach(function(val, ci) {{
      if (val == null) return;
      var x = xPositions[ci];
      var y = H - pad.bottom - val * pH;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, 2 * Math.PI);
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.fillStyle = "#333";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(val.toFixed(2), x, y - 10);
    }});
  }});

  // legend
  var lx = W - pad.right - 10;
  var ly = pad.top + 5;
  modelList.forEach(function(m, mi) {{
    ctx.strokeStyle = modelColors[m];
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(lx - 30, ly + mi * 20 + 6);
    ctx.lineTo(lx - 14, ly + mi * 20 + 6);
    ctx.stroke();
    ctx.fillStyle = modelColors[m];
    ctx.beginPath();
    ctx.arc(lx - 22, ly + mi * 20 + 6, 3, 0, 2 * Math.PI);
    ctx.fill();
    ctx.fillStyle = "#333";
    ctx.font = "12px sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(m, lx - 34, ly + mi * 20 + 11);
  }});
}}

// Store chart data globally for model-filter redraw
var _costData = {cost_chart_data};
var _timeData = {time_chart_data};
var _levelData = {level_chart_data};
var _complexityData = {complexity_slope_data};
var _catData = {category_chart_data};
var _frustScatterData = {frustration_scatter_data};
var _frustCats = ["Low", "Moderate", "High", "Very High"];
var _levelLabels = {level_labels_json};
var _complexityLabels = {complexity_labels_json};
var _catLabels = {cat_labels_json};

function _redrawCharts(modelFilter) {{
  function match(label) {{ return !modelFilter || label === modelFilter; }}
  drawScatter("cost-recall-chart", _costData.filter(function(d) {{ return match(d.label); }}),
    "Total Cost (USD)", function(v) {{ return "$" + v.toFixed(2); }});
  drawScatter("time-recall-chart", _timeData.filter(function(d) {{ return match(d.label); }}),
    "Total Time (minutes)", function(v) {{ return v.toFixed(1) + "m"; }});
  drawGroupedBar("level-chart",
    _levelData.filter(function(d) {{ return match(d.label); }}), _levelLabels);
  drawSlope("complexity-chart",
    _complexityData.filter(function(d) {{ return match(d.label); }}), _complexityLabels);
  drawGroupedBar("category-chart",
    _catData.filter(function(d) {{ return match(d.label); }}), _catLabels);
  drawSlope("frustration-slope",
    _frustScatterData.filter(function(d) {{ return match(d.label); }}), _frustCats);
}}

document.addEventListener("DOMContentLoaded", function() {{
  _redrawCharts(null);

  // Model filter dropdown
  var table = document.getElementById("runs-table");
  var rows = Array.from(table.querySelectorAll("tbody tr"));
  var models = [];
  rows.forEach(function(r) {{
    var m = r.children[1].textContent;
    if (m && models.indexOf(m) === -1) models.push(m);
  }});
  if (models.length > 1) {{
    var sel = document.createElement("select");
    sel.id = "model-filter";
    sel.style.marginBottom = "1rem";
    sel.style.padding = "0.3rem";
    sel.style.fontSize = "14px";
    var all = document.createElement("option");
    all.value = "";
    all.textContent = "All Models";
    sel.appendChild(all);
    models.sort().forEach(function(m) {{
      var opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      sel.appendChild(opt);
    }});
    table.parentNode.insertBefore(sel, table);
    sel.addEventListener("change", function() {{
      var v = sel.value;
      rows.forEach(function(r) {{
        r.style.display = (!v || r.children[1].textContent === v) ? "" : "none";
      }});
      _redrawCharts(v || null);
    }});
  }}
}});
</script>
"""
    level_section = ""
    complexity_section = ""
    if has_difficulty:
        level_section = """
    <figure>
      <figcaption>Recall by Level</figcaption>
      <canvas id="level-chart" width="900" height="420"></canvas>
    </figure>"""
        complexity_section = """
    <figure>
      <figcaption>Recall by Complexity</figcaption>
      <canvas id="complexity-chart" width="900" height="420"></canvas>
    </figure>"""
    category_section = ""
    if has_categories:
        category_section = """
    <figure>
      <figcaption>Recall by Category</figcaption>
      <canvas id="category-chart" width="900" height="420"></canvas>
    </figure>"""
    frustration_section = ""
    if has_frustration:
        frustration_section = """
    <figure>
      <figcaption>Recall Degradation by User Frustration</figcaption>
      <canvas id="frustration-slope" width="900" height="420"></canvas>
    </figure>"""

    html_content = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>AstaBench Run Summary</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
    th {{ background: #f2f2f2; cursor: pointer; }}
    .charts {{ display: flex; flex-wrap: wrap; gap: 2rem; justify-content: center; }}
    .charts figure {{ margin: 0; text-align: center; }}
    .charts figcaption {{ font-weight: bold; margin-bottom: 0.5rem; }}
    canvas {{ border: 1px solid #eee; }}
  </style>
</head>
<body>
  <h1>AstaBench Runs</h1>
  <p>Generated {generated}</p>
  {table_html}
  <p><small>Runs with different commit hashes may reflect prompt or task changes that affect performance.</small></p>
  <div class="charts">
    <figure>
      <figcaption>Cost vs Recall</figcaption>
      <canvas id="cost-recall-chart" width="720" height="420"></canvas>
    </figure>
    <figure>
      <figcaption>Total Time vs Recall</figcaption>
      <canvas id="time-recall-chart" width="720" height="420"></canvas>
    </figure>
    {level_section}
    {complexity_section}
    {category_section}
    {frustration_section}
  </div>
  {sweet_spot_html}
  <p>Raw data: <a href=\"runs.json\">runs.json</a></p>
  {sort_script}
  {chart_script}
</body>
</html>
"""
    (destination / "index.html").write_text(html_content)


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, text=True, capture_output=True)


def ensure_clean_worktree() -> None:
    status = run_git("git", "status", "--porcelain")
    if status.stdout.strip():
        raise SystemExit("Working tree must be clean before running publish_docs.py")


def update_docs_branch(
    site_dir: Path,
    doc_branch: str,
    push: bool,
    commit_message: str,
) -> None:
    worktree_path = Path(tempfile.mkdtemp(prefix="docs-worktree-"))
    try:
        subprocess.run(
            ["git", "worktree", "add", "-B", doc_branch, str(worktree_path)],
            check=True,
        )
        # wipe existing contents except .git
        for item in worktree_path.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        # copy new site
        for item in site_dir.iterdir():
            dest = worktree_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        subprocess.run(["git", "-C", str(worktree_path), "add", "."], check=True)
        status = subprocess.run(
            ["git", "-C", str(worktree_path), "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        )
        if status.stdout.strip():
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(worktree_path),
                    "commit",
                    "-m",
                    commit_message,
                ],
                check=True,
            )
            if push:
                subprocess.run(
                    ["git", "-C", str(worktree_path), "push", "origin", doc_branch],
                    check=True,
                )
        else:
            print("Docs branch already up to date; no commit created.")
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, default=Path("astabench/logs"))
    parser.add_argument(
        "--eval-metadata",
        type=Path,
        default=Path("evaluation/main/eval_tools.yaml"),
        help="Path to eval_tools.yaml for difficulty metadata",
    )
    parser.add_argument("--doc-branch", default="docs")
    parser.add_argument("--commit-message", default="Update docs")
    parser.add_argument("--push", action="store_true")
    parser.add_argument(
        "--preview",
        type=Path,
        nargs="?",
        const=Path("preview"),
        default=None,
        help="Write site to a local directory for preview (default: preview/)",
    )
    args = parser.parse_args()

    if not args.log_dir.exists():
        raise SystemExit(f"Log directory {args.log_dir} does not exist")

    question_meta = load_question_metadata(args.eval_metadata)
    runs = load_runs(args.log_dir, question_meta)
    if not runs:
        raise SystemExit("No scored runs found in logs directory")

    if args.preview is not None:
        args.preview.mkdir(parents=True, exist_ok=True)
        write_site(runs, args.preview, question_meta)
        print(f"Preview site written to {args.preview}/")
        return

    ensure_clean_worktree()
    site_dir = Path(tempfile.mkdtemp(prefix="docs-site-"))
    try:
        write_site(runs, site_dir, question_meta)
        update_docs_branch(site_dir, args.doc_branch, args.push, args.commit_message)
    finally:
        shutil.rmtree(site_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
