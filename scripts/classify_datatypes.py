#!/usr/bin/env python3
"""Classify dataType values by mapping labels to IRIs via SSSOM lookup.

Reads a CSV and adds a dataTypeIRI column with resolved IRIs from the
SSSOM mapping in data_lookup.sssom.tsv. Runs after prepare_portal_tables.py
and before RML mapping.

Usage:
    python scripts/classify_datatypes.py --input data/csv/studies.csv --output data/csv/studies_harmonized.csv
    python scripts/classify_datatypes.py --check-only --input data/csv/studies.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

DEFAULT_INPUT = Path("data/csv/studies.csv")
DEFAULT_OUTPUT = Path("data/csv/studies_harmonized.csv")
DEFAULT_LOOKUP = Path("mappings/sssom/data_lookup.sssom.tsv")


def _expand_curie(curie: str, curie_map: dict[str, str]) -> str:
    """Expand a CURIE like 'nf:foo' to a full IRI using curie_map."""
    if ":" not in curie:
        return curie
    prefix, local = curie.split(":", 1)
    base = curie_map.get(prefix)
    if base is None:
        return curie
    return base + local


def build_label_to_iri(lookup_file: Path) -> dict[str, str]:
    """Build a case-insensitive label-to-IRI lookup from SSSOM TSV.

    Parses the metadata block for curie_map, then reads data rows.
    Returns dict keyed by subject_label.lower() -> expanded IRI.
    """
    curie_map: dict[str, str] = {}

    with open(lookup_file, "r", encoding="utf-8") as f:
        # Parse metadata block (lines starting with #)
        data_lines: list[str] = []
        in_curie_map = False
        for line in f:
            if line.startswith("#"):
                content = line[1:]
                if content.startswith("curie_map:"):
                    in_curie_map = True
                    continue
                if in_curie_map:
                    # YAML-style indented entries like "  nf: http://..."
                    stripped = content.strip()
                    if stripped and ":" in stripped:
                        # Check if it's still an indented curie_map entry
                        if content.startswith("  ") or content.startswith("\t"):
                            key, val = stripped.split(":", 1)
                            curie_map[key.strip()] = val.strip()
                            continue
                    in_curie_map = False
                # Other metadata lines - skip
                continue
            data_lines.append(line)

    # Parse TSV data rows
    lookup: dict[str, str] = {}
    reader = csv.DictReader(data_lines, delimiter="\t")
    for row in reader:
        label = row.get("subject_label", "").strip()
        object_id = row.get("object_id", "").strip()
        if label and object_id:
            iri = _expand_curie(object_id, curie_map)
            lookup[label.lower()] = iri

    return lookup


def classify_datatype(data_type: str, lookup: dict[str, str]) -> str:
    """Resolve a pipe-delimited dataType to pipe-delimited IRIs."""
    if not data_type:
        return ""

    seen: list[str] = []
    seen_set: set[str] = set()
    for part in data_type.split("|"):
        part = part.strip()
        iri = lookup.get(part.lower())
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
        help=f"Input CSV (default: {DEFAULT_INPUT})",
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
    print(f"Loaded {len(lookup)} label-to-IRI entries from {args.lookup}")

    rows: list[dict[str, str]] = []
    class_counts: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()

    with open(args.input, "r") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            data_type = row.get("dataType", "").strip()
            data_type_iri = classify_datatype(data_type, lookup)

            if data_type and not data_type_iri:
                for part in data_type.split("|"):
                    part = part.strip()
                    if part and part.lower() not in lookup:
                        unmapped[part] += 1

            if data_type_iri:
                for iri in data_type_iri.split("|"):
                    class_counts[iri] += 1
            else:
                class_counts["(unclassified)"] += 1

            row["dataTypeIRI"] = data_type_iri
            rows.append(row)

    print(f"\nClassification results ({len(rows)} rows):")
    for cls, count in class_counts.most_common():
        print(f"  {cls:60s}: {count}")

    if unmapped:
        print(f"\nUnmapped dataType values ({len(unmapped)} unique):")
        for term, count in unmapped.most_common():
            print(f"  {count:3d}x  {term}")

    if args.check_only:
        return 0

    out_fieldnames = list(fieldnames) + ["dataTypeIRI"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote harmonized CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
