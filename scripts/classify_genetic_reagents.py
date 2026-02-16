#!/usr/bin/env python3
"""Classify genetic reagents by mapping vectorType to subclass IRIs.

Reads the genetic reagents CSV and adds a vectorTypeClass column with resolved
class IRIs. Runs after prepare_portal_tables.py and before RML mapping.

Usage:
    python scripts/classify_genetic_reagents.py
    python scripts/classify_genetic_reagents.py --check-only
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

DEFAULT_INPUT = Path("data/csv/genetic_reagents.csv")
DEFAULT_OUTPUT = Path("data/csv/genetic_reagents_harmonized.csv")

NF_NS = "http://nf-osi.github.com/terms#"

VECTOR_TYPE_TO_CLASS: dict[str, str] = {
    "Bacterial Expression": "BacterialExpressionVector",
    "CRISPR": "CRISPRReagent",
    "Gateway Entry Clone": "GatewayEntryClone",
    "Lentiviral": "LentiviralVector",
    "Mammalian Expression": "MammalianExpressionVector",
    "Mouse Targeting": "MouseTargetingVector",
    "RNAi": "RNAiReagent",
    "Transfer Vector": "TransferVector",
    "Transposon Vector": "TransposonVector",
    "Yeast Expression": "YeastExpressionVector",
}


def classify_vector_type(vector_type: str) -> str:
    """Resolve a pipe-delimited vectorType to pipe-delimited class IRIs."""
    if not vector_type:
        return ""

    parts = [p.strip() for p in vector_type.split("|")]
    iris = []
    for part in parts:
        cls = VECTOR_TYPE_TO_CLASS.get(part)
        if cls:
            iris.append(f"{NF_NS}{cls}")
    return "|".join(iris)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Genetic reagents CSV (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output harmonized CSV (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Report stats without writing output",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Error: input file not found: {args.input}", file=sys.stderr)
        return 1

    rows = []
    class_counts: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()

    with open(args.input, "r") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            vector_type = row.get("vectorType", "").strip()
            vector_class = classify_vector_type(vector_type)

            if vector_type and not vector_class:
                for part in vector_type.split("|"):
                    part = part.strip()
                    if part and part not in VECTOR_TYPE_TO_CLASS:
                        unmapped[part] += 1

            if vector_class:
                for c in vector_class.split("|"):
                    class_counts[c] += 1
            else:
                class_counts["(unclassified)"] += 1

            row["vectorTypeClass"] = vector_class
            rows.append(row)

    print(f"Classification results ({len(rows)} genetic reagents):")
    for cls, count in class_counts.most_common():
        print(f"  {cls:30s}: {count}")

    if unmapped:
        print(f"\nUnmapped vectorType values ({len(unmapped)} unique):")
        for term, count in unmapped.most_common():
            print(f"  {count:3d}x  {term}")

    if args.check_only:
        return 0

    out_fieldnames = list(fieldnames) + ["vectorTypeClass"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote harmonized CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
