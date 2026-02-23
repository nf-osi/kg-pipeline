#!/usr/bin/env python3
"""Prepare eval data and run astabench NF_RAG across models.

1. Discovers *_ground*.yaml files under evaluation/<dataset>/ and merges
   them into astabench/astabench/evals/nf_rag/eval_data.yaml.
2. Runs ``inspect eval`` for each model in parallel.

Required models (need ANTHROPIC_API_KEY):
    anthropic/claude-sonnet-4-5, anthropic/claude-haiku-4-5

With --full, additionally runs (need GOOGLE_API_KEY and OPENAI_API_KEY):
    google/gemini-2.5-pro, openai/gpt-5.2

With --google / --openai, runs only the specified non-Anthropic
model(s) instead of Anthropic models. Can be combined.

Usage:
    python scripts/astabench.py
    python scripts/astabench.py --dataset main --full
    python scripts/astabench.py --google
    python scripts/astabench.py --openai --google
    python scripts/astabench.py --full --epochs 3
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = REPO_ROOT / "evaluation"
OUTPUT_PATH = (
    REPO_ROOT / "astabench" / "astabench" / "evals" / "nf_rag" / "eval_data.yaml"
)

ANTHROPIC_MODELS = [
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-haiku-4-5",
]

GOOGLE_MODELS = ["google/gemini-2.5-pro"]
OPENAI_MODELS = ["openai/gpt-5.2"]


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def prepare_data(dataset: str) -> int:
    """Merge ground-truth YAML files into eval_data.yaml."""
    dataset_dir = EVAL_DIR / dataset
    if not dataset_dir.is_dir():
        print(f"Error: dataset directory not found: {dataset_dir}", file=sys.stderr)
        return 1

    ground_files = sorted(dataset_dir.glob("*_ground*.yaml"))
    if not ground_files:
        print(f"Error: no *_ground*.yaml files found in {dataset_dir}", file=sys.stderr)
        return 1

    merged: dict = {}
    for path in ground_files:
        with open(path) as f:
            data = yaml.safe_load(f)
        entries = data.get("ground_truth", {})
        merged.update(entries)
        print(f"  {path.name}: {len(entries)} entries")

    output = {"ground_truth": merged}
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"Wrote {len(merged)} entries to {OUTPUT_PATH}")
    return 0


# ---------------------------------------------------------------------------
# Eval execution
# ---------------------------------------------------------------------------

def run_eval(model: str, extra_args: list[str]) -> tuple[str, int]:
    """Run inspect eval for a single model. Returns (model, returncode)."""
    cmd = [
        "inspect", "eval", "astabench/nf_rag",
        "--solver", "basic_agent",
        "--model", model,
        *extra_args,
    ]
    print(f"[{model}] Starting: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT / "astabench"))
    return model, result.returncode


# ---------------------------------------------------------------------------
# Key validation
# ---------------------------------------------------------------------------

def check_keys(full: bool, google: bool, openai: bool) -> list[str]:
    """Check for required API keys. Returns list of error messages."""
    errors = []
    need_anthropic = not (google or openai)
    if (need_anthropic or full) and not os.environ.get("ANTHROPIC_API_KEY"):
        errors.append("ANTHROPIC_API_KEY is not set (required for Anthropic models)")
    if (full or google) and not os.environ.get("GOOGLE_API_KEY"):
        errors.append("GOOGLE_API_KEY is not set (required for Gemini)")
    if (full or openai) and not os.environ.get("OPENAI_API_KEY"):
        errors.append("OPENAI_API_KEY is not set (required for OpenAI)")
    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dataset",
        default="main",
        help="Subdirectory under evaluation/ to read from (default: main)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run non-Anthropic models (Gemini, OpenAI)",
    )
    parser.add_argument(
        "--google",
        action="store_true",
        help="Run only Google Gemini (no Anthropic models)",
    )
    parser.add_argument(
        "--openai",
        action="store_true",
        help="Run only OpenAI (no Anthropic models)",
    )
    parser.add_argument(
        "inspect_args",
        nargs="*",
        help="Extra arguments forwarded to inspect eval (e.g. --epochs 3)",
    )
    args = parser.parse_args(argv)

    # Load .env if present (does not override existing env vars)
    load_dotenv(REPO_ROOT / ".env")

    # Validate flag combinations
    if args.full and (args.google or args.openai):
        parser.error("--full cannot be combined with --google/--openai")

    # Validate API keys
    errors = check_keys(args.full, args.google, args.openai)
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        return 1

    # Step 1: prepare data
    print("=== Preparing eval data ===")
    rc = prepare_data(args.dataset)
    if rc != 0:
        return rc

    # Step 2: run evals
    if args.google or args.openai:
        models = []
        if args.google:
            models.extend(GOOGLE_MODELS)
        if args.openai:
            models.extend(OPENAI_MODELS)
    else:
        models = list(ANTHROPIC_MODELS)
        if args.full:
            models.extend(GOOGLE_MODELS + OPENAI_MODELS)

    print(f"\n=== Running evals for {len(models)} models ===")
    failed = []
    with ProcessPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(run_eval, model, args.inspect_args): model
            for model in models
        }
        for future in as_completed(futures):
            model, rc = future.result()
            status = "OK" if rc == 0 else f"FAILED (exit {rc})"
            print(f"[{model}] {status}")
            if rc != 0:
                failed.append(model)

    if failed:
        print(f"\n{len(failed)} model(s) failed: {', '.join(failed)}", file=sys.stderr)
        return 1

    print("\nAll evals completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
