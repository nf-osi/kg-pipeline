#!/usr/bin/env python3
"""Quick eval for one or more nf_rag or nf_rag_pubs questions.

Prepares eval data, runs inspect eval on the specified questions,
and prints a summary with per-question scores.

Usage:
    python scripts/quick_eval.py ST-001
    python scripts/quick_eval.py ST-001 ST-002 CR-004
    python scripts/quick_eval.py --category ST
    python scripts/quick_eval.py --category ST,CL --model anthropic/claude-haiku-4-5
    python scripts/quick_eval.py --pubs PMC9221468-01
    python scripts/quick_eval.py ST-001 -- --epochs 3 -S message_limit=100
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"


def prepare_data(pubs: bool) -> int:
    """Run data prep (reuse logic from astabench.py)."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from astabench import prepare_data as _prepare_main
    from astabench import prepare_pubs_data as _prepare_pubs
    return _prepare_pubs() if pubs else _prepare_main("main")


def load_questions(pubs: bool) -> dict[str, str]:
    """Load question ID -> question text from eval_data.yaml."""
    if pubs:
        path = REPO_ROOT / "astabench" / "astabench" / "evals" / "nf_rag_pubs" / "eval_data.yaml"
    else:
        path = REPO_ROOT / "astabench" / "astabench" / "evals" / "nf_rag" / "eval_data.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return {
        qid: entry.get("question", entry.get("user_query", ""))
        for qid, entry in data.get("ground_truth", {}).items()
    }


def run_eval(
    task: str,
    question_ids: list[str] | None,
    categories: list[str] | None,
    model: str,
    extra_args: list[str],
) -> tuple[int, Path | None]:
    """Run inspect eval filtered to the given questions or categories."""
    cmd = [
        "inspect", "eval", f"astabench/{task}",
        "--solver", "basic_agent",
        "--model", model,
    ]
    if question_ids:
        cmd += ["-T", f"task_filter={','.join(question_ids)}"]
    if categories:
        cmd += ["-T", f"task_category={','.join(categories)}"]
    cmd += extra_args

    print(f"\n{'=' * 60}")
    print(f"Running: {' '.join(cmd)}")
    print(f"{'=' * 60}\n")

    result = subprocess.run(cmd, cwd=str(REPO_ROOT / "astabench"))

    if result.returncode != 0:
        return result.returncode, None

    # Find latest log
    log_dir = REPO_ROOT / "astabench" / "logs"
    logs = sorted(log_dir.glob("*.eval"), key=lambda p: p.stat().st_mtime)
    return 0, logs[-1] if logs else None


def print_results(log_path: Path, questions: dict[str, str], pubs: bool) -> None:
    """Parse and display per-sample results from the log."""
    result = subprocess.run(
        ["inspect", "log", "dump", str(log_path)],
        capture_output=True, text=True,
        cwd=str(REPO_ROOT / "astabench"),
    )
    if result.returncode != 0:
        print(f"Could not read log: {result.stderr}")
        return

    data = json.loads(result.stdout)

    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}\n")

    scorer_key = "score_answer" if pubs else "score_nf_retrieval"

    for sample in data.get("samples", []):
        qid = sample.get("id", "?")
        question_text = questions.get(qid, "")
        score_data = sample.get("scores", {}).get(scorer_key, {})
        explanation = score_data.get("explanation", "")
        answer = score_data.get("answer", "")
        value = score_data.get("value", "?")
        metadata = score_data.get("metadata", {})

        print(f"  {qid}: {question_text[:72]}")
        print(f"    score:     {value}")
        if not pubs:
            print(f"    recall:    {metadata.get('recall', '?')}")
            print(f"    precision: {metadata.get('precision', '?')}")
            print(f"    f1:        {metadata.get('f1', '?')}")
        print(f"    predicted: {answer}")
        print(f"    detail:    {explanation}")

        # Show attribution score for pubs
        if pubs:
            attr_data = sample.get("scores", {}).get("score_attribution", {})
            if attr_data:
                print(f"    citation_f1: {attr_data.get('value', '?')}")

        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "questions",
        nargs="*",
        help="Question IDs to evaluate (e.g. ST-001 CL-003)",
    )
    parser.add_argument(
        "--category", "-c",
        help="Comma-separated category prefixes (e.g. ST,CL)",
    )
    parser.add_argument(
        "--pubs",
        action="store_true",
        help="Run nf_rag_pubs instead of nf_rag",
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"Model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "inspect_args",
        nargs=argparse.REMAINDER,
        help="Extra args for inspect eval after -- (e.g. -- --epochs 3)",
    )
    args = parser.parse_args(argv)

    if not args.questions and not args.category:
        parser.error("provide question IDs and/or --category")

    # Strip leading '--' from remainder args
    extra = args.inspect_args
    if extra and extra[0] == "--":
        extra = extra[1:]

    load_dotenv(REPO_ROOT / ".env")

    # Prepare data
    print("Preparing eval data...")
    rc = prepare_data(args.pubs)
    if rc != 0:
        print("Data prep failed", file=sys.stderr)
        return rc

    # Load question texts for display
    questions = load_questions(args.pubs)

    # Parse categories
    categories = [c.strip() for c in args.category.split(",")] if args.category else None

    # Run eval
    task = "nf_rag_pubs" if args.pubs else "nf_rag"
    rc, log_path = run_eval(
        task, args.questions or None, categories, args.model, extra,
    )
    if rc != 0:
        print(f"\nEval failed (exit {rc})", file=sys.stderr)
        return rc

    # Print results
    if log_path:
        print_results(log_path, questions, args.pubs)
    else:
        print("No log file found")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
