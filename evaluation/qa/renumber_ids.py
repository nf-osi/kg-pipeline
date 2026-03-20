#!/usr/bin/env python3
"""Renumber question IDs within each qa_PMC*.yaml file.

Assigns sequential zero-padded IDs (PMC{pmcid}-01, -02, ...) based on
the order questions appear in each file. Useful after removing or
reordering questions during review.

Usage:
    # Dry run (default) — show what would change
    python evaluation/qa/renumber_ids.py

    # Apply changes
    python evaluation/qa/renumber_ids.py --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def renumber_file(path: Path, write: bool) -> int:
    """Renumber IDs in a single QA file. Returns count of changes."""
    with open(path) as f:
        data = yaml.safe_load(f)

    if isinstance(data, dict):
        questions = data.get("questions", [])
    elif isinstance(data, list):
        questions = data
        data = None
    else:
        print(f"  Skipping {path.name}: unexpected format", file=sys.stderr)
        return 0

    if not questions:
        return 0

    pmcid = questions[0].get("pmcid", "")
    changes = 0

    for i, q in enumerate(questions):
        new_id = f"{pmcid}-{i + 1:02d}"
        old_id = q.get("id", "")
        if old_id != new_id:
            print(f"  {old_id} -> {new_id}")
            q["id"] = new_id
            changes += 1

    if changes and write:
        with open(path, "w") as f:
            if data is not None:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            else:
                yaml.dump(questions, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return changes


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply changes (default is dry run)",
    )
    args = parser.parse_args()

    qa_dir = Path(__file__).parent
    qa_files = sorted(qa_dir.glob("qa_PMC*.yaml"))

    if not qa_files:
        print("No qa_PMC*.yaml files found", file=sys.stderr)
        return 1

    mode = "WRITING" if args.write else "DRY RUN"
    print(f"[{mode}] Checking {len(qa_files)} files\n")

    total_changes = 0
    for path in qa_files:
        changes = renumber_file(path, args.write)
        if changes:
            total_changes += changes
        else:
            print(f"  {path.name}: OK")

    print(f"\n{total_changes} ID(s) {'updated' if args.write else 'would change'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
