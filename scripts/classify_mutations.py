#!/usr/bin/env python3
"""Classify mutations by mapping mutationType terms to mutation subclass IRIs.

Reads the mutations CSV (with pipe-delimited mutationType) and the
SSSOM lookup, then adds a mutationTypeClass column with resolved class IRIs.
Runs after prepare_portal_tables.py and before RML mapping.

Usage:
    python scripts/classify_mutations.py
    python scripts/classify_mutations.py --input data/csv/mutations.csv
    python scripts/classify_mutations.py --check-only
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.classify_datatypes import build_label_to_iri

DEFAULT_INPUT = Path("data/csv/mutations.csv")
DEFAULT_OUTPUT = Path("data/csv/mutations_harmonized.csv")
DEFAULT_LOOKUP = Path("mappings/sssom/mutation_type_lookup.sssom.tsv")


def classify_mutation_type(mutation_type: str, lookup: dict[str, str]) -> str:
    """Resolve a pipe-delimited mutationType to pipe-delimited class IRIs."""
    if not mutation_type:
        return ""

    seen: list[str] = []
    seen_set: set[str] = set()
    for term in mutation_type.split("|"):
        term = term.strip()
        iri = lookup.get(term.lower())
        if iri and iri not in seen_set:
            seen.append(iri)
            seen_set.add(iri)

    return "|".join(seen)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Mutations CSV (default: {DEFAULT_INPUT})",
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
    print(f"Loaded {len(lookup)} mutation-type-to-IRI entries from {args.lookup}")

    rows = []
    class_counts: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()

    with open(args.input, "r") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            mutation_type = row.get("mutationType", "").strip()
            mutation_class = classify_mutation_type(mutation_type, lookup)

            if mutation_type and not mutation_class:
                for term in mutation_type.split("|"):
                    term = term.strip()
                    if term and not lookup.get(term.lower()):
                        unmapped[term] += 1

            if mutation_class:
                for c in mutation_class.split("|"):
                    class_counts[c] += 1
            else:
                class_counts["(unclassified)"] += 1

            row["mutationTypeClass"] = mutation_class
            rows.append(row)

    print(f"Classification results ({len(rows)} mutations):")
    for cls, count in class_counts.most_common():
        print(f"  {cls:60s}: {count}")

    if unmapped:
        print(f"\nUnmapped mutationType values ({len(unmapped)} unique):")
        for term, count in unmapped.most_common():
            print(f"  {count:3d}x  {term}")

    if args.check_only:
        return 0

    out_fieldnames = list(fieldnames) + ["mutationTypeClass"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote harmonized CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
