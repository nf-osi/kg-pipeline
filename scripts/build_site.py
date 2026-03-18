#!/usr/bin/env python3
"""Generate HTML dashboard from evaluation/runs.json."""
from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None  # type: ignore[assignment]


@dataclass
class RunSummary:
    """Reconstructed from JSON for compatibility with existing chart functions."""
    name: str
    model: str | None
    solver: str | None
    overall_score: float | None
    overall_cost: float | None
    started_at: str | None = None
    completed_at: str | None = None
    total_samples: int | None = None
    git_commit: str | None = None
    task_name: str | None = None
    score_stderr: float | None = None
    min_sample_time: float | None = None
    max_sample_time: float | None = None
    avg_sample_time: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_write_tokens: int | None = None
    cache_read_tokens: int | None = None
    total_tokens: int | None = None
    difficulty_scores: dict[str, float] = field(default_factory=dict)
    category_scores: dict[str, float] = field(default_factory=dict)
    frustration_scores: dict[str, float] = field(default_factory=dict)
    frustration_samples: list[dict] = field(default_factory=list)
    level_samples: list[dict] = field(default_factory=list)
    complexity_samples: list[dict] = field(default_factory=list)
    task_stats: dict[str, dict] = field(default_factory=dict)


QuestionMeta = dict[str, dict[str, str]]


def load_question_metadata(yaml_path: Path) -> QuestionMeta:
    """Load question difficulty metadata from eval_tools.yaml."""
    if yaml is None:
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


def load_runs_from_json(json_path: Path) -> list[RunSummary]:
    """Load runs from JSON and reconstruct RunSummary objects."""
    data = json.loads(json_path.read_text())
    runs = []
    for r in data:
        runs.append(
            RunSummary(
                name=r.get("run", ""),
                model=r.get("model"),
                solver=r.get("solver"),
                overall_score=r.get("score"),
                overall_cost=r.get("cost"),
                started_at=r.get("started_at"),
                completed_at=r.get("completed_at"),
                total_samples=r.get("total_samples"),
                git_commit=r.get("git_commit"),
                task_name=r.get("task_name"),
                score_stderr=r.get("score_stderr"),
                min_sample_time=r.get("min_sample_time"),
                max_sample_time=r.get("max_sample_time"),
                avg_sample_time=r.get("avg_sample_time"),
                input_tokens=r.get("input_tokens"),
                output_tokens=r.get("output_tokens"),
                cache_write_tokens=r.get("cache_write_tokens"),
                cache_read_tokens=r.get("cache_read_tokens"),
                total_tokens=r.get("total_tokens"),
                difficulty_scores=r.get("difficulty_scores", {}),
                category_scores=r.get("category_scores", {}),
                frustration_scores=r.get("frustration_scores", {}),
                frustration_samples=r.get("frustration_samples", []),
                level_samples=r.get("level_samples", []),
                complexity_samples=r.get("complexity_samples", []),
                task_stats=r.get("task_stats", {}),
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
    # Find best recall for bolding
    best_recall = max((r.overall_score for r in runs if r.overall_score is not None), default=None)

    # Find best values for each difficulty/complexity column
    best_difficulty = {}
    if has_difficulty:
        for key in DIFFICULTY_KEYS:
            best_difficulty[key] = max(
                (r.difficulty_scores.get(key) for r in runs if r.difficulty_scores.get(key) is not None),
                default=None
            )

    # Find best values for each category column
    best_category = {}
    if has_categories:
        for key in CATEGORY_KEYS:
            best_category[key] = max(
                (r.category_scores.get(key) for r in runs if r.category_scores.get(key) is not None),
                default=None
            )

    difficulty_cols = ""
    if has_difficulty:
        difficulty_cols = "".join(
            f"<th class='perf'>{DIFFICULTY_LABELS[k]}</th>" for k in DIFFICULTY_KEYS
        )
    category_cols = ""
    if has_categories:
        category_cols = "".join(
            f"<th class='category'>{CATEGORY_LABELS[k]}</th>" for k in CATEGORY_KEYS
        )

    def _difficulty_cells(run: RunSummary) -> str:
        if not has_difficulty:
            return ""
        cells = []
        for k in DIFFICULTY_KEYS:
            score = run.difficulty_scores.get(k)
            score_str = _format_score(score)
            if score is not None and score == best_difficulty.get(k):
                score_str = f"<strong>{score_str}</strong>"
            cells.append(f"<td>{score_str}</td>")
        return "".join(cells)

    def _category_cells(run: RunSummary) -> str:
        if not has_categories:
            return ""
        cells = []
        for k in CATEGORY_KEYS:
            score = run.category_scores.get(k)
            score_str = _format_score(score)
            if score is not None and score == best_category.get(k):
                score_str = f"<strong>{score_str}</strong>"
            cells.append(f"<td>{score_str}</td>")
        return "".join(cells)

    def _recall_cell(run: RunSummary) -> str:
        recall_str = _format_score_with_stderr(run.overall_score, run.score_stderr)
        if run.overall_score is not None and run.overall_score == best_recall:
            recall_str = f"<strong>{recall_str}</strong>"
        return recall_str

    rows = "\n".join(
        (
            f"<tr><td>{_esc(run.task_name)}</td>"
            f"<td>{_esc(run.model)}</td>"
            f"<td>{run.total_samples if run.total_samples is not None else ''}</td>"
            f"<td>{_recall_cell(run)}</td>"
            + _difficulty_cells(run)
            + _category_cells(run)
            + f"<td>{_format_cost(run.overall_cost)}</td>"
            + (f"<td class='token-col'>{run.input_tokens:,}</td>" if run.input_tokens is not None else "<td class='token-col'></td>")
            + (f"<td class='token-col'>{run.output_tokens:,}</td>" if run.output_tokens is not None else "<td class='token-col'></td>")
            + (f"<td class='token-col'>{run.cache_write_tokens:,}</td>" if run.cache_write_tokens is not None else "<td class='token-col'></td>")
            + (f"<td class='token-col'>{run.cache_read_tokens:,}</td>" if run.cache_read_tokens is not None else "<td class='token-col'></td>")
            + (f"<td class='token-col'>{run.total_tokens:,}</td>" if run.total_tokens is not None else "<td class='token-col'></td>")
            + f"<td>{_format_date(run.started_at)}</td>"
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
      <th class="info">Task</th>
      <th class="info">Model</th>
      <th class="info">Samples</th>
      <th class="recall">Recall</th>
      {difficulty_cols}
      {category_cols}
      <th class="cost">Total Cost (USD)</th>
      <th class="token-col cost">Input Tokens</th>
      <th class="token-col cost">Output Tokens</th>
      <th class="token-col cost">Cache Write</th>
      <th class="token-col cost">Cache Read</th>
      <th class="token-col cost">Total Tokens</th>
      <th class="time">Date</th>
      <th class="time">Total Time</th>
      <th class="time">Avg Time / Sample</th>
      <th class="time">Shortest Sample</th>
      <th class="time">Longest Sample</th>
      <th class="meta">Commit</th>
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
        # Get all models that achieved the top score (handle ties)
        top_models = [m for m, score in model_scores.items() if score == top_score]
        top_models_str = ", ".join(sorted(top_models))
        meta = question_meta.get(qid, {})
        rows.append(
            {
                "qid": qid,
                "frustration": FRUSTRATION_LABELS.get(
                    f"frustration/{frust}", frust
                ),
                "best_recall": top_score,
                "best_model": top_models_str,
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

  // Token toggle
  var tokenCols = document.querySelectorAll(".token-col");
  var tokenVisible = false;
  tokenCols.forEach(function(el) { el.style.display = "none"; });
  document.getElementById("token-toggle").addEventListener("click", function() {
    tokenVisible = !tokenVisible;
    tokenCols.forEach(function(el) { el.style.display = tokenVisible ? "" : "none"; });
    this.textContent = tokenVisible ? "Hide Token Details" : "Show Token Details";
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
      <details style="font-size:0.85rem; margin-bottom:0.5rem; max-width:900px; text-align:left;">
        <summary style="cursor:pointer; color:#555;">What is user frustration?</summary>
        <p style="margin:0.4rem 0;">User frustration estimates how difficult a query is to answer with the current portal&rsquo;s faceted search and text search.</p>
        <ul style="margin:0.3rem 0; padding-left:1.3rem;">
          <li><strong>Low</strong> &ndash; Answerable with minimal effort via facets or text search</li>
          <li><strong>Moderate</strong> &ndash; Requires knowing the right approach, extra steps, or domain knowledge</li>
          <li><strong>High</strong> &ndash; Incomplete/misleading results, painful workarounds, or only one weak path</li>
          <li><strong>Very High</strong> &ndash; Cannot be answered at all, or requires expert-level workarounds that most users would never find</li>
        </ul>
      </details>
      <canvas id="frustration-slope" width="900" height="420"></canvas>
    </figure>"""

    html_content = f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>NF Research Tools Discovery Evaluation</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
    th {{ cursor: pointer; font-weight: 600; }}
    /* Column group colors for better readability */
    th.info {{ background: #e3f2fd; }}     /* Run info: soft blue */
    th.recall {{ background: #c8e6c9; }}   /* Overall recall: emphasized green */
    th.perf {{ background: #e8f5e9; }}     /* Difficulty breakdown: soft green */
    th.category {{ background: #e0f2f1; }} /* Category breakdown: soft teal */
    th.cost {{ background: #fff3e0; }}     /* Cost: soft amber */
    th.time {{ background: #f3e5f5; }}     /* Timing: soft purple */
    th.meta {{ background: #f5f5f5; }}     /* Metadata: light gray */
    .charts {{ display: flex; flex-wrap: wrap; gap: 2rem; justify-content: center; }}
    .charts figure {{ margin: 0; text-align: center; }}
    .charts figcaption {{ font-weight: bold; margin-bottom: 0.5rem; }}
    canvas {{ border: 1px solid #eee; }}
    #token-toggle {{ margin-bottom: 1rem; padding: 0.5rem 1rem; cursor: pointer; }}
  </style>
</head>
<body>
  <h1>NF Research Tools Discovery Evaluation</h1>
  <p>Generated {generated} &mdash; Structured SPARQL queries against the Synapse portal knowledge graph</p>
  <button id="token-toggle">Show Token Details</button>
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
    (destination / "main.html").write_text(html_content)


def write_pubs_site(pubs_data: list[dict], destination: Path) -> None:
    """Generate HTML dashboard for nf_rag_pubs evaluation results."""
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "pubs_runs.json").write_text(json.dumps(pubs_data, indent=2))

    # Find best values for bolding
    best_acc = max((r.get("accuracy") for r in pubs_data if r.get("status") == "success"), default=None)
    best_f1 = max((r.get("citation_f1") or r.get("passage_f1") for r in pubs_data if r.get("status") == "success"), default=None)

    # Build summary table rows
    rows = []
    for run in pubs_data:
        model = _esc(run.get("model", ""))
        style = _esc(run.get("question_style", ""))
        status = run.get("status", "")
        samples = run.get("samples", 0)
        total = run.get("total_samples", 130)
        acc = run.get("accuracy")
        acc_se = run.get("accuracy_stderr")
        # Current key is citation_f1; older extracts used passage_f1
        f1 = run.get("citation_f1") or run.get("passage_f1")
        f1_se = run.get("citation_f1_stderr") or run.get("passage_f1_stderr")
        started = _format_date(run.get("started_at"))
        total_secs = _duration_seconds(run.get("started_at"), run.get("completed_at"))
        cost = run.get("cost")
        input_tok = run.get("input_tokens", 0)
        output_tok = run.get("output_tokens", 0)
        cache_write_tok = run.get("input_tokens_cache_write", 0)
        cache_read_tok = run.get("input_tokens_cache_read", 0)
        total_tok = run.get("total_tokens", 0)
        avg_t = run.get("avg_sample_time")
        min_t = run.get("min_sample_time")
        max_t = run.get("max_sample_time")
        samples_str = f"{samples}/{total}" if status != "success" else str(samples)
        status_badge = status if status == "success" else f"<em>{status}</em>"

        # Bold best values
        acc_str = _format_score_with_stderr(acc, acc_se)
        f1_str = _format_score_with_stderr(f1, f1_se)
        if acc is not None and acc == best_acc:
            acc_str = f"<strong>{acc_str}</strong>"
        if f1 is not None and f1 == best_f1:
            f1_str = f"<strong>{f1_str}</strong>"

        rows.append(
            f"<tr><td>{model}</td><td>{style}</td><td>{samples_str}</td>"
            f"<td>{acc_str}</td>"
            f"<td>{f1_str}</td>"
            f"<td>{_format_cost(cost)}</td>"
            f"<td class='token-col'>{input_tok:,}</td>"
            f"<td class='token-col'>{output_tok:,}</td>"
            f"<td class='token-col'>{cache_write_tok:,}</td>"
            f"<td class='token-col'>{cache_read_tok:,}</td>"
            f"<td class='token-col'>{total_tok:,}</td>"
            f"<td>{_format_duration(total_secs)}</td>"
            f"<td>{_format_duration(avg_t)}</td>"
            f"<td>{_format_duration(min_t)}</td>"
            f"<td>{_format_duration(max_t)}</td>"
            f"<td>{started}</td></tr>"
        )
    rows_html = "\n".join(rows)

    # Build chart data: difficulty breakdown (slope charts, user_query only)
    difficulty_keys = ["easy", "medium", "hard"]
    difficulty_labels = ["Easy", "Medium", "Hard"]
    diff_acc_slope = []
    diff_f1_slope = []
    for run in pubs_data:
        if run.get("status") != "success":
            continue
        if run.get("question_style") != "user_query":
            continue
        label = _esc(run.get('model', ''))
        da = run.get("difficulty_accuracy", {})
        df = run.get("difficulty_f1", {})
        for i, k in enumerate(difficulty_keys):
            if da.get(k) is not None:
                diff_acc_slope.append({"x": i, "y": da[k], "label": label})
            if df.get(k) is not None:
                diff_f1_slope.append({"x": i, "y": df[k], "label": label})

    # Build chart data: question type breakdown (user_query only)
    qtype_keys = sorted({
        k for run in pubs_data
        for k in run.get("question_type_accuracy", {})
    })
    qtype_acc_chart = []
    qtype_f1_chart = []
    for run in pubs_data:
        if run.get("status") != "success":
            continue
        if run.get("question_style") != "user_query":
            continue
        label = _esc(run.get('model', ''))
        qa = run.get("question_type_accuracy", {})
        qf = run.get("question_type_f1", {})
        qa_entry = {"label": label}
        qf_entry = {"label": label}
        for k in qtype_keys:
            qa_entry[k.title()] = qa.get(k)
            qf_entry[k.title()] = qf.get(k)
        qtype_acc_chart.append(qa_entry)
        qtype_f1_chart.append(qf_entry)

    # Build scatter plot data: cost and time vs accuracy and citation_f1 (user_query only)
    cost_acc_data = []
    cost_f1_data = []
    time_acc_data = []
    time_f1_data = []
    for run in pubs_data:
        if run.get("status") != "success":
            continue
        if run.get("question_style") != "user_query":
            continue
        label = _esc(run.get('model', ''))
        acc = run.get("accuracy")
        f1 = run.get("citation_f1") or run.get("passage_f1")
        cost = run.get("cost")
        total_secs = _duration_seconds(run.get("started_at"), run.get("completed_at"))

        if cost is not None and acc is not None:
            cost_acc_data.append({"x": cost, "y": acc, "label": label})
        if cost is not None and f1 is not None:
            cost_f1_data.append({"x": cost, "y": f1, "label": label})
        if total_secs is not None and acc is not None:
            time_acc_data.append({"x": total_secs / 60, "y": acc, "label": label})
        if total_secs is not None and f1 is not None:
            time_f1_data.append({"x": total_secs / 60, "y": f1, "label": label})

    diff_labels_json = json.dumps([k.title() for k in difficulty_keys])
    qtype_labels_json = json.dumps([k.title() for k in qtype_keys])
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>NF Publication RAG Evaluation</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
    th {{ font-weight: 600; cursor: pointer; }}
    /* Column group colors for better readability */
    th.info {{ background: #e3f2fd; }}     /* Run info: soft blue */
    th.metrics {{ background: #c8e6c9; }}  /* Accuracy, F1: emphasized green */
    th.cost {{ background: #fff3e0; }}     /* Cost: soft amber */
    th.time {{ background: #f3e5f5; }}     /* Timing: soft purple */
    th.meta {{ background: #f5f5f5; }}     /* Metadata: light gray */
    .charts {{ display: flex; flex-wrap: wrap; gap: 2rem; justify-content: center; }}
    .charts figure {{ margin: 0; text-align: center; }}
    .charts figcaption {{ font-weight: bold; margin-bottom: 0.5rem; }}
    canvas {{ border: 1px solid #eee; }}
    em {{ color: #e65100; }}
    #token-toggle {{ margin-bottom: 1rem; padding: 0.5rem 1rem; cursor: pointer; }}
  </style>
</head>
<body>
  <h1>NF Publication RAG Evaluation</h1>
  <p>Generated {generated} &mdash; 130 questions across 14 papers</p>

  <h2>Summary</h2>
  <p><strong>Accuracy</strong> measures whether the agent selected the correct answer from the multiple-choice options.
  <strong>Citation F1</strong> measures how well the agent cited the correct supporting passages (PMID + passage index tuples) &mdash;
  precision is the fraction of cited passages that are relevant, and recall is the fraction of expected passages that were cited.</p>
  <p><strong>Note:</strong> Charts below show results for the <em>user_query</em> question style only.
  Performance is similar for both <em>precise</em> and <em>user_query</em> styles, but <em>user_query</em> better reflects realistic user interactions with natural phrasing and ambiguity.</p>
  <button id="token-toggle">Show Token Details</button>
  <table id="runs-table">
    <thead>
      <tr>
        <th class="info">Model</th>
        <th class="info">Question Style</th>
        <th class="info">Samples</th>
        <th class="metrics">Accuracy</th>
        <th class="metrics">Citation F1</th>
        <th class="cost">Total Cost (USD)</th>
        <th class='token-col cost'>Input Tokens</th>
        <th class='token-col cost'>Output Tokens</th>
        <th class='token-col cost'>Cache Write</th>
        <th class='token-col cost'>Cache Read</th>
        <th class='token-col cost'>Total Tokens</th>
        <th class="time">Total Time</th>
        <th class="time">Avg / Sample</th>
        <th class="time">Shortest</th>
        <th class="time">Longest</th>
        <th class="meta">Date</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>

  <div class="charts">
    <figure>
      <figcaption>Cost vs Accuracy</figcaption>
      <canvas id="cost-acc-chart" width="720" height="420"></canvas>
    </figure>
    <figure>
      <figcaption>Time vs Accuracy</figcaption>
      <canvas id="time-acc-chart" width="720" height="420"></canvas>
    </figure>
    <figure>
      <figcaption>Cost vs Citation F1</figcaption>
      <canvas id="cost-f1-chart" width="720" height="420"></canvas>
    </figure>
    <figure>
      <figcaption>Time vs Citation F1</figcaption>
      <canvas id="time-f1-chart" width="720" height="420"></canvas>
    </figure>
    <figure>
      <figcaption>Accuracy by Difficulty</figcaption>
      <canvas id="diff-acc-slope" width="900" height="420"></canvas>
    </figure>
    <figure>
      <figcaption>Citation F1 by Difficulty</figcaption>
      <canvas id="diff-f1-slope" width="900" height="420"></canvas>
    </figure>
    <figure>
      <figcaption>Accuracy by Question Type</figcaption>
      <canvas id="qtype-acc-chart" width="900" height="420"></canvas>
    </figure>
    <figure>
      <figcaption>Citation F1 by Question Type</figcaption>
      <canvas id="qtype-f1-chart" width="900" height="420"></canvas>
    </figure>
  </div>

  <p>Raw data: <a href="pubs_runs.json">pubs_runs.json</a></p>

<script>
function drawScatter(canvasId, data, xLabel, yLabel, xFmt) {{
  if (!data.length) return;
  var canvas = document.getElementById(canvasId);
  var ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  var W = canvas.width, H = canvas.height;
  var pad = {{top: 30, right: 30, bottom: 50, left: 60}};
  var pW = W - pad.left - pad.right;
  var pH = H - pad.top - pad.bottom;

  var maxX = Math.max.apply(null, data.map(function(d) {{ return d.x; }})) * 1.15;
  var minY = Math.max(0, Math.min.apply(null, data.map(function(d) {{ return d.y; }})) - 0.05);
  var maxY = Math.min(1, Math.max.apply(null, data.map(function(d) {{ return d.y; }})) + 0.05);
  var rangeY = maxY - minY;

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
    var yVal = minY + (rangeY / 5) * j;
    var y = H - pad.bottom - ((yVal - minY) / rangeY) * pH;
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
  ctx.fillText(yLabel, 0, 0);
  ctx.restore();

  var colors = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7"];
  var modelColors = {{}};
  var ci = 0;
  data.forEach(function(d) {{
    if (!modelColors[d.label]) modelColors[d.label] = colors[ci++ % colors.length];
  }});

  data.forEach(function(d) {{
    var x = pad.left + (d.x / maxX) * pW;
    var y = H - pad.bottom - ((d.y - minY) / rangeY) * pH;
    ctx.fillStyle = modelColors[d.label];
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, 2 * Math.PI);
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = "#333";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(d.label, x, y - 10);
  }});
}}

function drawSlope(canvasId, data, categories, yLabel) {{
  if (!data.length) return;
  var canvas = document.getElementById(canvasId);
  var ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  var W = canvas.width, H = canvas.height;
  var pad = {{top: 30, right: 30, bottom: 50, left: 60}};
  var pW = W - pad.left - pad.right;
  var pH = H - pad.top - pad.bottom;
  var nCat = categories.length;

  // Dynamic y-axis range
  var minY = Math.max(0, Math.min.apply(null, data.map(function(d) {{ return d.y; }})) - 0.05);
  var maxY = Math.min(1, Math.max.apply(null, data.map(function(d) {{ return d.y; }})) + 0.05);
  var rangeY = maxY - minY;

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
    var yVal = minY + (rangeY / 5) * j;
    var y = H - pad.bottom - ((yVal - minY) / rangeY) * pH;
    ctx.fillText(yVal.toFixed(2), pad.left - 8, y + 4);
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
  ctx.fillText(yLabel, 0, 0);
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
      var y = H - pad.bottom - ((val - minY) / rangeY) * pH;
      if (!started) {{ ctx.moveTo(x, y); started = true; }}
      else ctx.lineTo(x, y);
    }});
    ctx.stroke();
    // dots with value labels
    avgs.forEach(function(val, ci) {{
      if (val == null) return;
      var x = xPositions[ci];
      var y = H - pad.bottom - ((val - minY) / rangeY) * pH;
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

function drawGroupedBar(canvasId, data, groups, yLabel) {{
  if (!data.length) return;
  var canvas = document.getElementById(canvasId);
  var ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  var W = canvas.width, H = canvas.height;
  var pad = {{top: 30, right: 20, bottom: 100, left: 60}};
  var pW = W - pad.left - pad.right;
  var pH = H - pad.top - pad.bottom;

  var n = data.length;
  var g = groups.length;
  var groupWidth = pW / n;
  var barWidth = (groupWidth * 0.8) / g;
  var gap = groupWidth * 0.2;

  var colors = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1","#ff9da7"];

  ctx.strokeStyle = "#999";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, H - pad.bottom);
  ctx.lineTo(W - pad.right, H - pad.bottom);
  ctx.stroke();

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

  ctx.fillStyle = "#333";
  ctx.font = "14px sans-serif";
  ctx.save();
  ctx.translate(15, H / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.fillText(yLabel, 0, 0);
  ctx.restore();

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
      ctx.fillStyle = "#333";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(val.toFixed(2), bx + barWidth / 2, by - 4);
    }});
    ctx.fillStyle = "#333";
    ctx.font = "11px sans-serif";
    ctx.save();
    ctx.translate(x0 + (g * barWidth) / 2, H - pad.bottom + 12);
    ctx.rotate(-Math.PI / 6);
    ctx.textAlign = "right";
    ctx.fillText(entry.label, 0, 0);
    ctx.restore();
  }});

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

document.addEventListener("DOMContentLoaded", function() {{
  var diffLabels = {json.dumps(difficulty_labels)};
  var qtypeLabels = {qtype_labels_json};
  drawScatter("cost-acc-chart", {json.dumps(cost_acc_data)}, "Total Cost (USD)", "Accuracy", function(v) {{ return "$" + v.toFixed(2); }});
  drawScatter("time-acc-chart", {json.dumps(time_acc_data)}, "Total Time (minutes)", "Accuracy", function(v) {{ return v.toFixed(1) + "m"; }});
  drawScatter("cost-f1-chart", {json.dumps(cost_f1_data)}, "Total Cost (USD)", "Citation F1", function(v) {{ return "$" + v.toFixed(2); }});
  drawScatter("time-f1-chart", {json.dumps(time_f1_data)}, "Total Time (minutes)", "Citation F1", function(v) {{ return v.toFixed(1) + "m"; }});
  drawSlope("diff-acc-slope", {json.dumps(diff_acc_slope)}, diffLabels, "Accuracy");
  drawSlope("diff-f1-slope", {json.dumps(diff_f1_slope)}, diffLabels, "Citation F1");
  drawGroupedBar("qtype-acc-chart", {json.dumps(qtype_acc_chart)}, qtypeLabels, "Accuracy");
  drawGroupedBar("qtype-f1-chart", {json.dumps(qtype_f1_chart)}, qtypeLabels, "Citation F1");

  // Token toggle
  var tokenCols = document.querySelectorAll(".token-col");
  var tokenVisible = false;
  tokenCols.forEach(function(el) {{ el.style.display = "none"; }});
  document.getElementById("token-toggle").addEventListener("click", function() {{
    tokenVisible = !tokenVisible;
    tokenCols.forEach(function(el) {{ el.style.display = tokenVisible ? "" : "none"; }});
    this.textContent = tokenVisible ? "Hide Token Details" : "Show Token Details";
  }});
}});
</script>
</body>
</html>
"""
    (destination / "pubs.html").write_text(html_content)


def write_home_page(destination: Path) -> None:
    """Generate home page linking to both dashboards."""
    destination.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>NF Knowledge Graph Evaluation</title>
  <style>
    body {{
      font-family: sans-serif;
      max-width: 900px;
      margin: 3rem auto;
      padding: 0 2rem;
      line-height: 1.6;
    }}
    h1 {{ color: #1976d2; margin-bottom: 0.5rem; }}
    .subtitle {{ color: #666; margin-top: 0; }}
    .dashboards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
      gap: 2rem;
      margin-top: 2rem;
    }}
    .card {{
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 2rem;
      background: #f9f9f9;
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    .card:hover {{
      transform: translateY(-4px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }}
    .card h2 {{ margin-top: 0; color: #1976d2; }}
    .card p {{ color: #555; margin: 1rem 0; }}
    .card a {{
      display: inline-block;
      padding: 0.75rem 1.5rem;
      background: #1976d2;
      color: white;
      text-decoration: none;
      border-radius: 4px;
      font-weight: 600;
      margin-top: 1rem;
    }}
    .card a:hover {{
      background: #1565c0;
    }}
    footer {{ margin-top: 3rem; padding-top: 2rem; border-top: 1px solid #ddd; color: #666; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>NF Knowledge Graph Evaluation</h1>
  <p class="subtitle">Model performance benchmarks for neurofibromatosis research tools</p>

  <div class="dashboards">
    <div class="card">
      <h2>Research Tools Discovery</h2>
      <p>Structured SPARQL queries against the Synapse portal knowledge graph. Evaluates recall for discovering datasets, publications, tools, and cross-resource linkages.</p>
      <p><strong>Task:</strong> <code>nf_rag</code><br>
      <strong>Metrics:</strong> Recall by difficulty, complexity, and resource category</p>
      <a href="main.html">View Dashboard →</a>
    </div>

    <div class="card">
      <h2>Publication QA</h2>
      <p>Question answering over full-text biomedical literature using SPARQL+Text retrieval. Evaluates accuracy and citation attribution across diverse question types.</p>
      <p><strong>Task:</strong> <code>nf_rag_pubs</code><br>
      <strong>Metrics:</strong> Accuracy, Citation F1</p>
      <a href="pubs.html">View Dashboard →</a>
    </div>
  </div>

  <footer>
    Generated {generated} &mdash;
    <a href="https://github.com/nf-osi/kg-pipeline">kg-pipeline</a> |
    <a href="https://github.com/nf-osi/asta-bench">asta-bench</a>
  </footer>
</body>
</html>
"""
    (destination / "index.html").write_text(html_content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "runs_json",
        type=Path,
        help="Path to runs.json file",
    )
    parser.add_argument(
        "--pubs",
        action="store_true",
        help="Generate pubs evaluation dashboard (input is pubs_runs.json)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("_site"),
        help="Output directory for generated site",
    )
    parser.add_argument(
        "--eval-metadata",
        type=Path,
        default=Path("evaluation/main/eval_tools.yaml"),
        help="Path to eval_tools.yaml for question metadata (for sweet spot table)",
    )
    args = parser.parse_args()

    if not args.runs_json.exists():
        raise SystemExit(f"Input file {args.runs_json} does not exist")

    if args.pubs:
        pubs_data = json.loads(args.runs_json.read_text())
        if not pubs_data:
            raise SystemExit("No runs found in JSON file")
        write_pubs_site(pubs_data, args.out)
        print(f"✓ Pubs dashboard generated at {args.out}/pubs.html")
    else:
        runs = load_runs_from_json(args.runs_json)
        if not runs:
            raise SystemExit("No runs found in JSON file")
        question_meta = load_question_metadata(args.eval_metadata)
        write_site(runs, args.out, question_meta)
        write_home_page(args.out)
        print(f"✓ Site generated at {args.out}/main.html")
        print(f"✓ Home page generated at {args.out}/index.html")


if __name__ == "__main__":
    main()
