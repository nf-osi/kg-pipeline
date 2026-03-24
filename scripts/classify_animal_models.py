#!/usr/bin/env python3
"""Classify animal models by mapping species to subclass IRIs.

Reads the animal models CSV and the SSSOM lookup, then adds an
animalModelClass column with a resolved class IRI.
Runs after prepare_portal_tables.py and before RML mapping.

Usage:
    python scripts/classify_animal_models.py
    python scripts/classify_animal_models.py --check-only
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.classify_datatypes import build_label_to_iri

DEFAULT_INPUT = Path("data/csv/animal_models.csv")
DEFAULT_OUTPUT = Path("data/csv/animal_models_harmonized.csv")
DEFAULT_LOOKUP = Path("mappings/sssom/animal_model_species_lookup.sssom.tsv")


def classify_species(species: str, lookup: dict[str, str]) -> str:
    """Resolve a species label to an animal-model subclass IRI."""
    if not species:
        return ""
    iri = lookup.get(species.lower())
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
        help=f"Input animal_models CSV (default: {DEFAULT_INPUT})",
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
    print(f"Loaded {len(lookup)} species-to-IRI entries from {args.lookup}")

    rows: list[dict[str, str]] = []
    class_counts: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()

    with open(args.input, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            species = row.get("species", "").strip()
            animal_model_class = classify_species(species, lookup)

            if species and not animal_model_class:
                unmapped[species] += 1

            if animal_model_class:
                class_counts[animal_model_class] += 1
            else:
                class_counts["(unclassified)"] += 1

            row["animalModelClass"] = animal_model_class
            rows.append(row)

    print(f"\nClassification results ({len(rows)} animal models):")
    for cls, count in class_counts.most_common():
        print(f"  {cls:60s}: {count}")

    if unmapped:
        print(f"\nUnmapped species values ({len(unmapped)} unique):")
        for term, count in unmapped.most_common():
            print(f"  {count:3d}x  {term}")

    if args.check_only:
        return 0

    out_fieldnames = list(fieldnames) + ["animalModelClass"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote harmonized CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
