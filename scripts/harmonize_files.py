#!/usr/bin/env python3
"""Link file modelSystemName values to AnimalModel/CellLine entity IRIs,
classify dataType values to IRIs, and classify genotype values to class IRIs.

Reads the files CSV and resources CSV, builds a name-to-IRI lookup from
resourceName and synonyms, then adds a modelSystemId column with resolved IRIs.
Also maps dataType labels to IRIs using data_lookup.sssom.tsv and genotype
labels to class IRIs using nf1/nf2_genotype_lookup.sssom.tsv.
Runs after prepare_portal_tables.py and before RML mapping.

Usage:
    python scripts/harmonize_files.py
    python scripts/harmonize_files.py --files data/csv/files.csv --resources data/csv/resources.csv
    python scripts/harmonize_files.py --check-only
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.classify_datatypes import build_label_to_iri, classify_datatype

DEFAULT_FILES = Path("data/csv/files.csv")
DEFAULT_RESOURCES = Path("data/csv/resources.csv")
DEFAULT_OUTPUT = Path("data/csv/files_harmonized.csv")
DEFAULT_LOOKUP = Path("mappings/sssom/data_lookup.sssom.tsv")
DEFAULT_NF1_LOOKUP = Path("mappings/sssom/nf1_genotype_lookup.sssom.tsv")
DEFAULT_NF2_LOOKUP = Path("mappings/sssom/nf2_genotype_lookup.sssom.tsv")

NF_NS = "http://nf-osi.github.com/terms#"


def build_lookup(resources_path: Path) -> dict[str, str]:
    """Build a case-insensitive name-to-IRI lookup from resources.csv.

    Maps resourceName (and each pipe-delimited synonym) to the corresponding
    animalModel or cellLine IRI. If a resource has both animalModelId and
    cellLineId, animalModelId takes precedence.
    """
    lookup: dict[str, str] = {}
    with open(resources_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            animal_model_id = row.get("animalModelId", "").strip()
            cell_line_id = row.get("cellLineId", "").strip()

            if animal_model_id:
                iri = f"{NF_NS}animalModel/{animal_model_id}"
            elif cell_line_id:
                iri = f"{NF_NS}cellLine/{cell_line_id}"
            else:
                continue

            name = row.get("resourceName", "").strip()
            if name:
                lookup[name.lower()] = iri

            synonyms = row.get("synonyms", "").strip()
            if synonyms:
                for syn in synonyms.split("|"):
                    syn = syn.strip()
                    if syn:
                        lookup[syn.lower()] = iri

    return lookup


def classify_genotype(genotype: str, lookup: dict[str, str]) -> str:
    """Resolve a pipe-delimited genotype string to pipe-delimited class IRIs.

    Each individual genotype label (e.g. "+/-") is looked up case-sensitively
    first, then case-insensitively. Returns unique IRIs, pipe-delimited.
    """
    if not genotype:
        return ""

    seen: list[str] = []
    seen_set: set[str] = set()
    for part in genotype.split("|"):
        part = part.strip()
        # Try exact match first (genotype labels are case-sensitive, e.g. "WT" vs "wt")
        iri = lookup.get(part) or lookup.get(part.lower())
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
        "--files",
        type=Path,
        default=DEFAULT_FILES,
        help=f"Input files CSV (default: {DEFAULT_FILES})",
    )
    parser.add_argument(
        "--resources",
        type=Path,
        default=DEFAULT_RESOURCES,
        help=f"Resources CSV (default: {DEFAULT_RESOURCES})",
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
        help=f"SSSOM lookup TSV for dataType (default: {DEFAULT_LOOKUP})",
    )
    parser.add_argument(
        "--nf1-lookup",
        type=Path,
        default=DEFAULT_NF1_LOOKUP,
        help=f"SSSOM lookup TSV for NF1 genotype (default: {DEFAULT_NF1_LOOKUP})",
    )
    parser.add_argument(
        "--nf2-lookup",
        type=Path,
        default=DEFAULT_NF2_LOOKUP,
        help=f"SSSOM lookup TSV for NF2 genotype (default: {DEFAULT_NF2_LOOKUP})",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Report match stats without writing output",
    )
    args = parser.parse_args(argv)

    if not args.files.exists():
        print(f"Error: files CSV not found: {args.files}", file=sys.stderr)
        return 1
    if not args.resources.exists():
        print(f"Error: resources CSV not found: {args.resources}", file=sys.stderr)
        return 1
    if not args.lookup.exists():
        print(f"Error: lookup file not found: {args.lookup}", file=sys.stderr)
        return 1

    lookup = build_lookup(args.resources)
    print(f"Loaded {len(lookup)} name-to-IRI entries from resources", flush=True)

    datatype_lookup = build_label_to_iri(args.lookup)
    print(f"Loaded {len(datatype_lookup)} dataType label-to-IRI entries from {args.lookup}", flush=True)

    nf1_lookup = build_label_to_iri(args.nf1_lookup) if args.nf1_lookup.exists() else {}
    nf2_lookup = build_label_to_iri(args.nf2_lookup) if args.nf2_lookup.exists() else {}
    print(f"Loaded {len(nf1_lookup)} NF1 genotype entries, {len(nf2_lookup)} NF2 genotype entries", flush=True)

    rows = []
    matched = 0
    unmatched_names: Counter[str] = Counter()
    empty_count = 0
    dt_class_counts: Counter[str] = Counter()
    dt_unmapped: Counter[str] = Counter()
    nf1_counts: Counter[str] = Counter()
    nf1_unmapped: Counter[str] = Counter()
    nf2_counts: Counter[str] = Counter()
    nf2_unmapped: Counter[str] = Counter()

    with open(args.files, "r") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            model_name = row.get("modelSystemName", "").strip()
            if not model_name:
                row["modelSystemId"] = ""
                empty_count += 1
            else:
                parts = [p.strip() for p in model_name.split(",")]
                iris = []
                has_unmatched = False
                for part in parts:
                    iri = lookup.get(part.lower(), "")
                    if iri:
                        iris.append(iri)
                    elif part:
                        unmatched_names[part] += 1
                        has_unmatched = True
                row["modelSystemId"] = "|".join(iris)
                if iris:
                    matched += 1

            # Classify dataType
            data_type = row.get("dataType", "").strip()
            data_type_iri = classify_datatype(data_type, datatype_lookup)
            if data_type and not data_type_iri:
                for part in data_type.split("|"):
                    part = part.strip()
                    if part and part.lower() not in datatype_lookup:
                        dt_unmapped[part] += 1
            if data_type_iri:
                for iri in data_type_iri.split("|"):
                    dt_class_counts[iri] += 1
            else:
                dt_class_counts["(unclassified)"] += 1
            row["dataTypeIRI"] = data_type_iri

            # Classify NF1 genotype
            nf1_raw = row.get("nf1Genotype", "").strip()
            nf1_iri = classify_genotype(nf1_raw, nf1_lookup)
            if nf1_raw and not nf1_iri:
                for part in nf1_raw.split("|"):
                    part = part.strip()
                    if part and not nf1_lookup.get(part) and not nf1_lookup.get(part.lower()):
                        nf1_unmapped[part] += 1
            if nf1_iri:
                for iri in nf1_iri.split("|"):
                    nf1_counts[iri] += 1
            row["nf1GenotypeIRI"] = nf1_iri

            # Classify NF2 genotype
            nf2_raw = row.get("nf2Genotype", "").strip()
            nf2_iri = classify_genotype(nf2_raw, nf2_lookup)
            if nf2_raw and not nf2_iri:
                for part in nf2_raw.split("|"):
                    part = part.strip()
                    if part and not nf2_lookup.get(part) and not nf2_lookup.get(part.lower()):
                        nf2_unmapped[part] += 1
            if nf2_iri:
                for iri in nf2_iri.split("|"):
                    nf2_counts[iri] += 1
            row["nf2GenotypeIRI"] = nf2_iri

            rows.append(row)

    total = len(rows)
    unmatched_total = sum(unmatched_names.values())
    print(f"\nModel system match results ({total} file rows):")
    print(f"  Matched:    {matched}")
    print(f"  Unmatched:  {unmatched_total}")
    print(f"  Empty:      {empty_count}")

    if unmatched_names:
        print(f"\nUnmatched modelSystemName values ({len(unmatched_names)} unique):")
        for name, count in unmatched_names.most_common(20):
            print(f"  {count:3d}x  {name}")
        if len(unmatched_names) > 20:
            print(f"  ... and {len(unmatched_names) - 20} more")

    print(f"\nDataType classification results ({total} file rows):")
    for cls, count in dt_class_counts.most_common():
        print(f"  {cls:60s}: {count}")
    if dt_unmapped:
        print(f"\nUnmapped dataType values ({len(dt_unmapped)} unique):")
        for term, count in dt_unmapped.most_common():
            print(f"  {count:3d}x  {term}")

    print(f"\nNF1 genotype classification ({total} file rows):")
    for cls, count in nf1_counts.most_common():
        print(f"  {cls:60s}: {count}")
    if nf1_unmapped:
        print(f"\nUnmapped NF1 genotype values ({len(nf1_unmapped)} unique):")
        for term, count in nf1_unmapped.most_common():
            print(f"  {count:3d}x  {term}")

    print(f"\nNF2 genotype classification ({total} file rows):")
    for cls, count in nf2_counts.most_common():
        print(f"  {cls:60s}: {count}")
    if nf2_unmapped:
        print(f"\nUnmapped NF2 genotype values ({len(nf2_unmapped)} unique):")
        for term, count in nf2_unmapped.most_common():
            print(f"  {count:3d}x  {term}")

    if args.check_only:
        return 0

    out_fieldnames = list(fieldnames) + ["modelSystemId", "dataTypeIRI", "nf1GenotypeIRI", "nf2GenotypeIRI"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote harmonized CSV -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
