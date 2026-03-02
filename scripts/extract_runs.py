#!/usr/bin/env python3
"""Extract run data from astabench logs and append to evaluation/runs.json."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
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


def run_to_dict(run: RunSummary) -> dict:
    """Serialize RunSummary to JSON dict."""
    return {
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
        "min_sample_time": run.min_sample_time,
        "max_sample_time": run.max_sample_time,
        "avg_sample_time": run.avg_sample_time,
        "difficulty_scores": run.difficulty_scores,
        "category_scores": run.category_scores,
        "frustration_scores": run.frustration_scores,
        "frustration_samples": run.frustration_samples,
        "level_samples": run.level_samples,
        "complexity_samples": run.complexity_samples,
        "task_stats": run.task_stats,
    }


def append_runs(json_path: Path, new_runs: list[RunSummary]) -> None:
    """Load existing JSON, dedup by run name, append new, sort by started_at, write back."""
    existing_runs = []
    if json_path.exists():
        try:
            existing_runs = json.loads(json_path.read_text())
        except json.JSONDecodeError:
            print(f"Warning: failed to parse {json_path}, starting fresh", file=sys.stderr)

    # Create a map of existing runs by name
    run_map = {r["run"]: r for r in existing_runs}

    # Add/update with new runs
    for run in new_runs:
        run_map[run.name] = run_to_dict(run)

    # Convert back to list and sort by started_at (newest first)
    all_runs = list(run_map.values())
    all_runs.sort(key=lambda r: r.get("started_at") or "", reverse=True)

    # Write back
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(all_runs, indent=2) + "\n")
    print(f"✓ Wrote {len(all_runs)} runs to {json_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("astabench/logs"),
        help="Directory containing run logs",
    )
    parser.add_argument(
        "--eval-metadata",
        type=Path,
        default=Path("evaluation/main/eval_tools.yaml"),
        help="Path to eval_tools.yaml for difficulty metadata",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/runs.json"),
        help="Output JSON file path",
    )
    args = parser.parse_args()

    if not args.log_dir.exists():
        raise SystemExit(f"Log directory {args.log_dir} does not exist")

    question_meta = load_question_metadata(args.eval_metadata)
    runs = load_runs(args.log_dir, question_meta)

    if not runs:
        raise SystemExit("No scored runs found in logs directory")

    print(f"Found {len(runs)} runs in {args.log_dir}")
    append_runs(args.output, runs)


if __name__ == "__main__":
    main()
