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
    task_version: str | None = None
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


QuestionMeta = dict[str, dict[str, str]]  # id -> {level, complexity, user_frustration}


def load_question_metadata(yaml_path: Path) -> QuestionMeta:
    """Load question difficulty metadata from dataset_attributes.yaml."""
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
        # Difficulty + frustration breakdown (from dataset_attributes.yaml metadata)
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


def _load_flat_eval_runs(
    log_root: Path,
    question_meta: QuestionMeta,
) -> list[RunSummary]:
    """Load nf_rag results from flat .eval archive files.

    Current inspect_ai versions write a single .eval archive per run instead
    of the directory-per-run layout (summary_stats.json/scores.json/header.json)
    that the loop below expects, so runs produced by plain `inspect eval`
    (e.g. via scripts/astabench.py or scripts/quick_eval.py) land here.
    """
    from inspect_ai.log import read_eval_log

    runs: list[RunSummary] = []
    for eval_file in sorted(log_root.glob("*.eval")):
        try:
            log = read_eval_log(str(eval_file))
        except Exception as exc:
            print(f"Skipping {eval_file}: failed to read ({exc})", file=sys.stderr)
            continue

        if log.eval.task != "astabench/nf_rag":
            continue  # nf_rag_pubs and other tasks belong in load_pubs_runs, not here

        model = log.eval.model
        task_version = (
            str(log.eval.task_version) if log.eval.task_version is not None else None
        )
        git_commit = log.eval.revision.commit if log.eval.revision else None

        started_at = getattr(log.stats, "started_at", None) if log.stats else None
        completed_at = getattr(log.stats, "completed_at", None) if log.stats else None

        overall_score = None
        score_stderr = None
        if log.results and log.results.scores:
            metrics = log.results.scores[0].metrics
            if "f1" in metrics:
                overall_score = metrics["f1"].value
            elif "accuracy" in metrics:
                overall_score = metrics["accuracy"].value
            if "stderr" in metrics:
                score_stderr = metrics["stderr"].value

        input_tokens = output_tokens = cache_write_tokens = None
        cache_read_tokens = total_tokens = None
        cost = None
        if log.stats and log.stats.model_usage:
            usage = log.stats.model_usage.get(model)
            if usage:
                input_tokens = usage.input_tokens or 0
                output_tokens = usage.output_tokens or 0
                cache_write_tokens = usage.input_tokens_cache_write or 0
                cache_read_tokens = usage.input_tokens_cache_read or 0
                total_tokens = usage.total_tokens or 0
                cost = _compute_cost(model, usage)

        min_sample_time = max_sample_time = avg_sample_time = None
        summaries_data: list[dict] = []
        if log.samples:
            times = [s.total_time for s in log.samples if s.total_time is not None]
            if times:
                min_sample_time = min(times)
                max_sample_time = max(times)
                avg_sample_time = sum(times) / len(times)
            for s in log.samples:
                summaries_data.append(
                    {
                        "id": s.id,
                        "scores": {
                            name: {"value": sc.value}
                            for name, sc in (s.scores or {}).items()
                        },
                        "metadata": s.metadata or {},
                    }
                )

        (
            difficulty_scores,
            category_scores,
            frustration_scores,
            frustration_samples,
            level_samples,
            complexity_samples,
        ) = _compute_sample_breakdowns(summaries_data, question_meta)

        runs.append(
            RunSummary(
                name=eval_file.stem,
                model=model,
                solver=log.eval.solver,
                overall_score=overall_score,
                overall_cost=cost,
                summary_path=eval_file,
                started_at=started_at,
                completed_at=completed_at,
                total_samples=len(log.samples) if log.samples else 0,
                git_commit=git_commit,
                task_name=log.eval.task,
                task_version=task_version,
                score_stderr=score_stderr,
                min_sample_time=min_sample_time,
                max_sample_time=max_sample_time,
                avg_sample_time=avg_sample_time,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_write_tokens=cache_write_tokens,
                cache_read_tokens=cache_read_tokens,
                total_tokens=total_tokens,
                difficulty_scores=difficulty_scores,
                category_scores=category_scores,
                frustration_scores=frustration_scores,
                frustration_samples=frustration_samples,
                level_samples=level_samples,
                complexity_samples=complexity_samples,
                task_stats={},
            )
        )
    return runs


def load_runs(
    log_root: Path,
    question_meta: QuestionMeta,
) -> list[RunSummary]:
    from inspect_ai.log import read_eval_log

    runs: list[RunSummary] = list(_load_flat_eval_runs(log_root, question_meta))
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
        task_version = None
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
                task_version = str(eval_info.get("task_version", "")) if eval_info.get("task_version") is not None else None
                revision = eval_info.get("revision", {})
                git_commit = revision.get("commit")
            except json.JSONDecodeError:
                pass  # header.json is optional enrichment

        # Try to compute cost and extract token counts from .eval file
        cost = overall.get("cost")  # fallback to inspect_ai's calculation
        input_tokens = None
        output_tokens = None
        cache_write_tokens = None
        cache_read_tokens = None
        total_tokens = None
        eval_files = list(run_dir.glob("*.eval"))
        if eval_files:
            try:
                log = read_eval_log(str(eval_files[0]))
                if log.stats and log.stats.model_usage:
                    model = (eval_spec or {}).get("model")
                    if model and model in log.stats.model_usage:
                        usage = log.stats.model_usage[model]
                        input_tokens = usage.input_tokens or 0
                        output_tokens = usage.output_tokens or 0
                        cache_write_tokens = usage.input_tokens_cache_write or 0
                        cache_read_tokens = usage.input_tokens_cache_read or 0
                        total_tokens = usage.total_tokens or 0
                        computed_cost = _compute_cost(model, usage)
                        if computed_cost is not None:
                            cost = computed_cost
            except Exception:
                pass  # keep fallback cost

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
                overall_cost=cost,
                summary_path=summary_file,
                started_at=started_at,
                completed_at=completed_at,
                total_samples=total_samples,
                git_commit=git_commit,
                task_name=task_name,
                task_version=task_version,
                score_stderr=overall.get("score_stderr"),
                min_sample_time=min_sample_time,
                max_sample_time=max_sample_time,
                avg_sample_time=avg_sample_time,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_write_tokens=cache_write_tokens,
                cache_read_tokens=cache_read_tokens,
                total_tokens=total_tokens,
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


# The 6 PUB questions were added to the ground truth in #75 without bumping the
# dataset version, so runs that executed the 46-question set still report
# task_version v1.2 from their eval log. That set is what the changelog calls
# v1.3, and correcting the label here means it survives re-extraction rather
# than needing a hand-edit of runs.json each time.
#
# The marker is category/PUB, which the harness derives from per-sample metadata
# in the log. It is therefore independent of dataset_attributes.yaml, and works
# whether or not the PUB attributes are present. A sample count would not do:
# most of these are targeted development runs covering one or two questions.
#
# Runs that predate PUB keep their label -- the May 2026 ST-only development run
# is genuinely v1.2.
_MISLABELLED_VERSION = "v1.2"
_CORRECTED_VERSION = "v1.3"
_CORRECTED_VERSION_MARKER = "category/PUB"


def corrected_task_version(run: RunSummary) -> str | None:
    """The dataset version a run actually executed, not the one it reported."""
    if run.task_version != _MISLABELLED_VERSION:
        return run.task_version
    if _CORRECTED_VERSION_MARKER in (run.category_scores or {}):
        return _CORRECTED_VERSION
    return run.task_version


def run_to_dict(run: RunSummary) -> dict:
    """Serialize RunSummary to JSON dict."""
    return {
        "run": run.name,
        "model": run.model,
        "solver": run.solver,
        "score": run.overall_score,
        "cost": run.overall_cost,
        "task_name": run.task_name,
        "task_version": corrected_task_version(run),
        "total_samples": run.total_samples,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "git_commit": run.git_commit,
        "score_stderr": run.score_stderr,
        "min_sample_time": run.min_sample_time,
        "max_sample_time": run.max_sample_time,
        "avg_sample_time": run.avg_sample_time,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cache_write_tokens": run.cache_write_tokens,
        "cache_read_tokens": run.cache_read_tokens,
        "total_tokens": run.total_tokens,
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


_COST_OVERRIDES_PATH = (
    Path(__file__).resolve().parent.parent
    / "astabench" / "astabench" / "config" / "litellm_cost_overrides.json"
)

_cost_overrides_cache: dict | None = None


def _load_cost_overrides() -> dict:
    """Load litellm cost overrides, cached after first call."""
    global _cost_overrides_cache
    if _cost_overrides_cache is None:
        if _COST_OVERRIDES_PATH.exists():
            _cost_overrides_cache = json.loads(_COST_OVERRIDES_PATH.read_text())
        else:
            _cost_overrides_cache = {}
    return _cost_overrides_cache


def _resolve_pricing(model: str) -> dict | None:
    """Look up per-token pricing from litellm cost overrides.

    Strips the provider prefix (e.g. 'anthropic/claude-sonnet-4-5' -> 'claude-sonnet-4-5')
    and tries exact match, then a prefix match for versioned model IDs.
    """
    overrides = _load_cost_overrides()
    if not overrides:
        return None
    # Strip provider prefix
    bare = model.split("/", 1)[-1] if "/" in model else model
    # Try exact match first, then prefix match (e.g. 'gpt-5.4' matches 'gpt-5.4')
    for key in overrides:
        if key == bare or key.startswith(bare):
            return overrides[key]
    return None


def _compute_cost(model: str, usage) -> float | None:
    """Compute USD cost from ModelUsage and litellm cost overrides."""
    pricing = _resolve_pricing(model)
    if pricing is None or usage is None:
        return None
    cost = 0.0
    cost += (usage.input_tokens or 0) * pricing.get("input_cost_per_token", 0)
    cost += (usage.input_tokens_cache_write or 0) * pricing.get("cache_creation_input_token_cost", 0)
    cost += (usage.input_tokens_cache_read or 0) * pricing.get("cache_read_input_token_cost", 0)
    cost += (usage.output_tokens or 0) * pricing.get("output_cost_per_token", 0)
    return round(cost, 2)


def load_pubs_runs(log_dir: Path) -> list[dict]:
    """Load nf_rag_pubs results from .eval files using inspect_ai."""
    from inspect_ai.log import read_eval_log

    eval_files = sorted(log_dir.glob("*nf-rag-pubs*.eval"))
    if not eval_files:
        return []

    runs = []
    for eval_file in eval_files:
        log = read_eval_log(str(eval_file))
        model = log.eval.model
        task_args = log.eval.task_args or {}
        style = task_args.get("question_style", "precise")
        n_samples = len(log.samples) if log.samples else 0
        status = log.status

        # Extract task_version
        task_version = None
        if hasattr(log.eval, "task_version") and log.eval.task_version is not None:
            task_version = str(log.eval.task_version)

        entry: dict = {
            "log_file": eval_file.name,
            "model": model,
            "question_style": style,
            "status": status,
            "samples": n_samples,
            "total_samples": 130,
            "task_version": task_version,
        }

        # Extract timestamps
        if hasattr(log.eval, "created") and log.eval.created:
            entry["started_at"] = log.eval.created
        if hasattr(log, "stats") and log.stats:
            started = getattr(log.stats, "started_at", None)
            completed = getattr(log.stats, "completed_at", None)
            if started:
                entry["started_at"] = started
            if completed:
                entry["completed_at"] = completed

        # Extract cost from model usage
        if log.stats and log.stats.model_usage:
            usage = log.stats.model_usage.get(model)
            if usage:
                entry["input_tokens"] = usage.input_tokens or 0
                entry["output_tokens"] = usage.output_tokens or 0
                entry["input_tokens_cache_write"] = usage.input_tokens_cache_write or 0
                entry["input_tokens_cache_read"] = usage.input_tokens_cache_read or 0
                entry["total_tokens"] = usage.total_tokens or 0
                cost = _compute_cost(model, usage)
                if cost is not None:
                    entry["cost"] = cost

        # Extract per-sample timing
        if log.samples:
            times = [s.total_time for s in log.samples if s.total_time is not None]
            if times:
                entry["min_sample_time"] = round(min(times), 1)
                entry["max_sample_time"] = round(max(times), 1)
                entry["avg_sample_time"] = round(sum(times) / len(times), 1)

        # Extract aggregate metrics from completed runs
        if log.results and log.results.scores:
            for scorer in log.results.scores:
                if scorer.name == "score_answer":
                    entry["accuracy"] = round(scorer.metrics["accuracy"].value, 4)
                    entry["accuracy_stderr"] = round(scorer.metrics["stderr"].value, 4)
                elif scorer.name == "score_attribution":
                    # Current metric name is citation_f1; older evals used passage_f1
                    f1_key = "citation_f1" if "citation_f1" in scorer.metrics else "passage_f1"
                    entry["citation_f1"] = round(scorer.metrics[f1_key].value, 4)
                    entry["citation_f1_stderr"] = round(scorer.metrics["stderr"].value, 4)

        # Per-sample breakdown by difficulty, question_type, paper
        diff_acc: dict[str, list[float]] = {}
        diff_f1: dict[str, list[float]] = {}
        qtype_acc: dict[str, list[float]] = {}
        qtype_f1: dict[str, list[float]] = {}
        paper_acc: dict[str, list[float]] = {}
        paper_f1: dict[str, list[float]] = {}
        per_sample: list[dict] = []

        if log.samples:
            for s in log.samples:
                sid = s.id or ""
                meta = s.metadata or {}
                difficulty = meta.get("difficulty", "unknown")
                qtype = meta.get("question_type", "unknown")
                paper = meta.get("category", sid.rsplit("-", 1)[0])

                sample_acc = 0.0
                sample_f1 = 0.0
                if "score_answer" in s.scores:
                    sc = s.scores["score_answer"]
                    correct = (sc.metadata or {}).get("answer_correct", False)
                    sample_acc = 1.0 if correct else 0.0
                if "score_attribution" in s.scores:
                    sc = s.scores["score_attribution"]
                    sample_f1 = (sc.metadata or {}).get("f1", 0.0)

                diff_acc.setdefault(difficulty, []).append(sample_acc)
                diff_f1.setdefault(difficulty, []).append(sample_f1)
                qtype_acc.setdefault(qtype, []).append(sample_acc)
                qtype_f1.setdefault(qtype, []).append(sample_f1)
                paper_acc.setdefault(paper, []).append(sample_acc)
                paper_f1.setdefault(paper, []).append(sample_f1)

                per_sample.append({
                    "id": sid,
                    "accuracy": sample_acc,
                    "f1": round(sample_f1, 4),
                    "difficulty": difficulty,
                    "question_type": qtype,
                    "paper": paper,
                })

        # For incomplete runs without aggregate metrics, compute from samples
        if "accuracy" not in entry and per_sample:
            vals = [s["accuracy"] for s in per_sample]
            entry["accuracy"] = round(sum(vals) / len(vals), 4)
        if "citation_f1" not in entry and per_sample:
            vals = [s["f1"] for s in per_sample]
            entry["citation_f1"] = round(sum(vals) / len(vals), 4)

        def _mean(vals: list[float]) -> float:
            return round(sum(vals) / len(vals), 4) if vals else 0.0

        entry["difficulty_accuracy"] = {k: _mean(v) for k, v in diff_acc.items()}
        entry["difficulty_f1"] = {k: _mean(v) for k, v in diff_f1.items()}
        entry["question_type_accuracy"] = {k: _mean(v) for k, v in qtype_acc.items()}
        entry["question_type_f1"] = {k: _mean(v) for k, v in qtype_f1.items()}
        entry["paper_accuracy"] = {k: _mean(v) for k, v in paper_acc.items()}
        entry["paper_f1"] = {k: _mean(v) for k, v in paper_f1.items()}
        entry["per_sample"] = per_sample

        runs.append(entry)
        print(f"  {eval_file.name}: {model} ({style}) — {n_samples} samples, status={status}")

    return runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pubs",
        action="store_true",
        help="Extract nf_rag_pubs results from .eval files",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("astabench/logs"),
        help="Directory containing run logs",
    )
    parser.add_argument(
        "--eval-metadata",
        type=Path,
        default=Path("evaluation/main/dataset_attributes.yaml"),
        help="Path to dataset_attributes.yaml for difficulty metadata",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON file path",
    )
    args = parser.parse_args()

    if not args.log_dir.exists():
        raise SystemExit(f"Log directory {args.log_dir} does not exist")

    if args.pubs:
        output = args.output or Path("evaluation/pubs_runs.json")
        runs = load_pubs_runs(args.log_dir)
        if not runs:
            raise SystemExit("No nf_rag_pubs .eval files found in logs directory")
        print(f"Found {len(runs)} pubs runs in {args.log_dir}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(runs, indent=2) + "\n")
        print(f"✓ Wrote {len(runs)} runs to {output}")
    else:
        output = args.output or Path("evaluation/runs.json")
        question_meta = load_question_metadata(args.eval_metadata)
        runs = load_runs(args.log_dir, question_meta)
        if not runs:
            raise SystemExit("No scored runs found in logs directory")
        print(f"Found {len(runs)} runs in {args.log_dir}")
        append_runs(output, runs)


if __name__ == "__main__":
    main()
