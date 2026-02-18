#!/usr/bin/env python3
"""Combine ground-truth files into eval_data.yaml for astabench.

Discovers all *_ground*.yaml files under evaluation/<dataset>/, merges
their ground_truth sections, and writes a single eval_data.yaml to
astabench/astabench/evals/nf_rag/.

Usage:
    python scripts/build_eval_data.py              # defaults to "main"
    python scripts/build_eval_data.py --dataset main
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = REPO_ROOT / "evaluation"
OUTPUT_PATH = (
    REPO_ROOT / "astabench" / "astabench" / "evals" / "nf_rag" / "eval_data.yaml"
)


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
    args = parser.parse_args(argv)

    dataset_dir = EVAL_DIR / args.dataset
    if not dataset_dir.is_dir():
        parser.error(f"Dataset directory not found: {dataset_dir}")

    ground_files = sorted(dataset_dir.glob("*_ground*.yaml"))
    if not ground_files:
        parser.error(f"No *_ground*.yaml files found in {dataset_dir}")

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


if __name__ == "__main__":
    raise SystemExit(main())
