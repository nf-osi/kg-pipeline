#!/usr/bin/env python3
"""Classify observations by mapping observationType terms to observation classes.

Reads the processed observations CSV (with pipe-delimited observationType) and the
SSSOM observation type mapping, then adds an observationClass column. Runs after
prepare_portal_tables.py and before RML mapping.

Usage:
    python scripts/classify_observations.py
    python scripts/classify_observations.py --observations data/csv/observations.csv
    python scripts/classify_observations.py --check-only
"""

from __future__ import annotations

import argparse
import csv
import sys
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.classify_datatypes import build_label_to_iri

DEFAULT_OBSERVATIONS = Path("data/csv/observations.csv")
DEFAULT_MAPPING = Path("mappings/sssom/observation_type_mapping.sssom.tsv")
DEFAULT_OUTPUT = Path("data/csv/observation_harmonized.csv")

NF_NS = "http://nf-osi.github.com/terms#"

# Stable display order for observation classes
CLASS_ORDER = [
    f"{NF_NS}PhenotypeObservation",
    f"{NF_NS}AssayObservation",
    f"{NF_NS}DerivationObservation",
    f"{NF_NS}MethodObservation",
    f"{NF_NS}IssueObservation",
    f"{NF_NS}UsageObservation",
    f"{NF_NS}ContributedObservation",
]


def classify_observation(obs_type: str, lookup: dict[str, str]) -> str:
    """Resolve a pipe-delimited observationType to pipe-delimited observationClass IRIs.

    An observation can belong to multiple classes simultaneously since
    observationType terms are not mutually exclusive.  Returns the unique
    classes in a stable order, pipe-delimited to match the existing
    multi-value convention.
    """
    if not obs_type:
        return ""

    terms = [t.strip() for t in obs_type.split("|")]
    classes = set()
    for term in terms:
        iri = lookup.get(term.lower())
        if iri:
            classes.add(iri)

    if not classes:
        return ""

    return "|".join(c for c in CLASS_ORDER if c in classes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--observations",
        type=Path,
        default=DEFAULT_OBSERVATIONS,
        help=f"Processed observations CSV (default: {DEFAULT_OBSERVATIONS})",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=DEFAULT_MAPPING,
        help=f"SSSOM observation type mapping (default: {DEFAULT_MAPPING})",
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
        help="Report unmapped terms without writing output",
    )
    args = parser.parse_args(argv)

    if not args.observations.exists():
        print(f"Error: observations file not found: {args.observations}", file=sys.stderr)
        return 1
    if not args.mapping.exists():
        print(f"Error: mapping file not found: {args.mapping}", file=sys.stderr)
        return 1

    lookup = build_label_to_iri(args.mapping)
    print(f"Loaded {len(lookup)} mapping entries from {args.mapping}", flush=True)

    # Read observations
    rows = []
    unmapped = Counter()
    class_counts = Counter()
    ids_generated = 0

    with open(args.observations, "r") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            # Mint a UUID for rows missing an observationId
            if not row.get("observationId", "").strip():
                row["observationId"] = str(uuid.uuid4())
                ids_generated += 1

            obs_type = row.get("observationType", "")
            obs_class = classify_observation(obs_type, lookup)

            if obs_type and not obs_class:
                for term in obs_type.split("|"):
                    term = term.strip()
                    if term and not lookup.get(term.lower()):
                        unmapped[term] += 1

            if obs_class:
                for c in obs_class.split("|"):
                    class_counts[c] += 1
            else:
                class_counts["(unclassified)"] += 1
            row["observationClass"] = obs_class
            rows.append(row)

    # Report
    if ids_generated:
        print(f"Generated {ids_generated} observationId UUIDs for rows missing IDs")
    print(f"\nClassification results ({len(rows)} observations):")
    for cls, count in class_counts.most_common():
        print(f"  {cls:60s}: {count}")

    if unmapped:
        print(f"\nUnmapped terms ({len(unmapped)} unique):")
        for term, count in unmapped.most_common(20):
            print(f"  {count:3d}x  {term}")
        if len(unmapped) > 20:
            print(f"  ... and {len(unmapped) - 20} more")

    if args.check_only:
        return 1 if unmapped else 0

    # Write harmonized CSV
    out_fieldnames = list(fieldnames) + ["observationClass"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote harmonized CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
