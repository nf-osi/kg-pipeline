#!/usr/bin/env python3
"""Classify cell lines by mapping cellLineCategory to subclass IRIs.

Reads the cell_lines CSV and the SSSOM lookup, then adds a
cellLineCategoryIRI column with resolved class IRIs.
Runs after prepare_portal_tables.py and before RML mapping.

Usage:
    python scripts/classify_cell_lines.py
    python scripts/classify_cell_lines.py --input data/csv/cell_lines.csv
    python scripts/classify_cell_lines.py --check-only
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.classify_datatypes import build_label_to_iri

DEFAULT_INPUT = Path("data/csv/cell_lines.csv")
DEFAULT_OUTPUT = Path("data/csv/cell_lines_harmonized.csv")
DEFAULT_LOOKUP = Path("mappings/sssom/cell_line_category_lookup.sssom.tsv")


def classify_category(category: str, lookup: dict[str, str]) -> str:
    """Resolve a cellLineCategory label to a class IRI."""
    if not category:
        return ""
    iri = lookup.get(category.lower())
    return iri or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input cell_lines CSV (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output harmonized CSV (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--lookup",
        type=Path,
        default=DEFAULT_LOOKUP,
        help=f"SSSOM lookup TSV (default: {DEFAULT_LOOKUP})",
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
    if not args.lookup.exists():
        print(f"Error: lookup file not found: {args.lookup}", file=sys.stderr)
        return 1

    lookup = build_label_to_iri(args.lookup)
    print(f"Loaded {len(lookup)} category-to-IRI entries from {args.lookup}")

    rows: list[dict[str, str]] = []
    class_counts: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()

    with open(args.input, "r") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            category = row.get("cellLineCategory", "").strip()
            category_iri = classify_category(category, lookup)

            if category and not category_iri:
                unmapped[category] += 1

            if category_iri:
                class_counts[category_iri] += 1
            else:
                class_counts["(unclassified)"] += 1

            row["cellLineCategoryIRI"] = category_iri
            rows.append(row)

    print(f"\nClassification results ({len(rows)} cell lines):")
    for cls, count in class_counts.most_common():
        print(f"  {cls:60s}: {count}")

    if unmapped:
        print(f"\nUnmapped cellLineCategory values ({len(unmapped)} unique):")
        for term, count in unmapped.most_common():
            print(f"  {count:3d}x  {term}")

    if args.check_only:
        return 0

    out_fieldnames = list(fieldnames) + ["cellLineCategoryIRI"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote harmonized CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
