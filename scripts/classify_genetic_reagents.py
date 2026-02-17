#!/usr/bin/env python3
"""Classify genetic reagents by mapping vectorType to subclass IRIs.

Reads the genetic reagents CSV and the SSSOM lookup, then adds a
reagentClass column with resolved class IRIs. Runs after
prepare_portal_tables.py and before RML mapping.

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.classify_datatypes import build_label_to_iri

DEFAULT_INPUT = Path("data/csv/genetic_reagents.csv")
DEFAULT_OUTPUT = Path("data/csv/genetic_reagents_harmonized.csv")
DEFAULT_LOOKUP = Path("mappings/sssom/reagent_type_lookup.sssom.tsv")


def classify_vector_type(vector_type: str, lookup: dict[str, str]) -> str:
    """Resolve a pipe-delimited vectorType to pipe-delimited class IRIs."""
    if not vector_type:
        return ""

    iris = []
    for part in vector_type.split("|"):
        part = part.strip()
        iri = lookup.get(part.lower())
        if iri:
            iris.append(iri)
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
    print(f"Loaded {len(lookup)} reagent-type-to-IRI entries from {args.lookup}")

    rows = []
    class_counts: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()

    with open(args.input, "r") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            vector_type = row.get("vectorType", "").strip()
            vector_class = classify_vector_type(vector_type, lookup)

            if vector_type and not vector_class:
                for part in vector_type.split("|"):
                    part = part.strip()
                    if part and not lookup.get(part.lower()):
                        unmapped[part] += 1

            if vector_class:
                for c in vector_class.split("|"):
                    class_counts[c] += 1
            else:
                class_counts["(unclassified)"] += 1

            row["reagentClass"] = vector_class
            rows.append(row)

    print(f"Classification results ({len(rows)} genetic reagents):")
    for cls, count in class_counts.most_common():
        print(f"  {cls:60s}: {count}")

    if unmapped:
        print(f"\nUnmapped vectorType values ({len(unmapped)} unique):")
        for term, count in unmapped.most_common():
            print(f"  {count:3d}x  {term}")

    if args.check_only:
        return 0

    out_fieldnames = list(fieldnames) + ["reagentClass"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote harmonized CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
