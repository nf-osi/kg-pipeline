#!/usr/bin/env python3
"""Classify mutations by mapping mutationType terms to mutation subclass IRIs.

Reads the mutations CSV (with pipe-delimited mutationType) and adds a
mutationTypeClass column with resolved class IRIs. Runs after
prepare_portal_tables.py and before RML mapping.

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

DEFAULT_INPUT = Path("data/csv/mutations.csv")
DEFAULT_OUTPUT = Path("data/csv/mutations_harmonized.csv")

NF_NS = "http://nf-osi.github.com/terms#"

MUTATION_TYPE_TO_CLASS: dict[str, str] = {
    "Single point mutation": "SinglePointMutation",
    "Intragenic deletion": "IntragenicDeletion",
    "Insertion": "Insertion",
    "Insertion of gene trap vector": "Insertion",
    "Exogenous DNA expression": "ExogenousDNAExpression",
    "Homozygous deletion": "HomozygousDeletion",
    "Intergenic deletion": "IntergenicDeletion",
    "Loss of heterozygosity (deletion)": "LossOfHeterozygosityByDeletion",
    "Loss of heterozygosity (mitotic recombination)": "LossOfHeterozygosityByMitoticRecombination",
    "Loss of heterozygosity (unspecified mechanism)": "LossOfHeterozygosityUnspecified",
    "Viral insertion": "ViralInsertion",
    "Stable knockdown": "StableKnockdown",
    "Nucleotide substitutions": "NucleotideSubstitutions",
    "Microdeletion": "Microdeletion",
    "Duplication": "Duplication",
    "Not Specified": "UnspecifiedMutation",
}


def classify_mutation_type(mutation_type: str) -> str:
    """Resolve a pipe-delimited mutationType to pipe-delimited class IRIs."""
    if not mutation_type:
        return ""

    # Stable order: deduplicate while preserving first-seen order
    seen = []
    seen_set = set()
    for term in mutation_type.split("|"):
        term = term.strip()
        cls = MUTATION_TYPE_TO_CLASS.get(term)
        if cls and cls not in seen_set:
            seen.append(cls)
            seen_set.add(cls)

    return "|".join(f"{NF_NS}{c}" for c in seen)


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
            mutation_type = row.get("mutationType", "").strip()
            mutation_class = classify_mutation_type(mutation_type)

            if mutation_type and not mutation_class:
                for term in mutation_type.split("|"):
                    term = term.strip()
                    if term and term not in MUTATION_TYPE_TO_CLASS:
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
        print(f"  {cls:30s}: {count}")

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
