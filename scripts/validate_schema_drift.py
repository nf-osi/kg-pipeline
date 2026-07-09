#!/usr/bin/env python3
"""Check that every rdf:type used in the built RDF is declared as an owl:Class in the ontology.

Loads schema/ontology.ttl and data/rdf/*.ttl into a single in-memory store and
finds any nf:-namespace rdf:type value with no corresponding `a owl:Class`
declaration -- typically a typo'd class IRI or a new class introduced in an
RML mapping / SSSOM lookup without a matching ontology update.

See examples/consistency-checks.md#6-schema-drift for background and the
worked example that motivated this check.

Usage:
    python scripts/validate_schema_drift.py [--rdf-dir DIR] [--schema-dir DIR]

Exit code is 1 if any undeclared class is found, 0 otherwise.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pyoxigraph import Store, RdfFormat

DEFAULT_RDF_DIR = Path("data/rdf")
DEFAULT_SCHEMA_DIR = Path("schema")

NF_NS = "http://nf-osi.github.com/terms#"

QUERY = f"""
PREFIX owl: <http://www.w3.org/2002/07/owl#>
SELECT ?type (COUNT(?s) AS ?n) WHERE {{
  ?s a ?type .
  FILTER(STRSTARTS(STR(?type), "{NF_NS}"))
  FILTER NOT EXISTS {{ ?type a owl:Class }}
}}
GROUP BY ?type ORDER BY DESC(?n)
"""


def load_store(rdf_dir: Path, schema_dir: Path) -> Store:
    """Load data and schema TTL files into a single in-memory store."""
    store = Store()
    data_files = sorted(f for f in rdf_dir.glob("*.ttl") if not f.name.endswith("_raw.ttl"))
    schema_files = sorted(schema_dir.glob("*.ttl"))
    all_files = data_files + schema_files
    if not all_files:
        raise FileNotFoundError(f"No TTL files found in {rdf_dir} or {schema_dir}")
    for ttl_file in all_files:
        with open(ttl_file, "rb") as f:
            store.bulk_load(f, RdfFormat.TURTLE)
    return store


def find_undeclared_classes(store: Store) -> list[tuple[str, int]]:
    """Return (type_iri, instance_count) for every nf: rdf:type with no owl:Class declaration."""
    results = []
    for row in store.query(QUERY):
        results.append((str(row["type"]), int(row["n"].value)))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--rdf-dir",
        type=Path,
        default=DEFAULT_RDF_DIR,
        help=f"Directory containing data TTL files (default: {DEFAULT_RDF_DIR})",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=DEFAULT_SCHEMA_DIR,
        help=f"Directory containing ontology TTL files (default: {DEFAULT_SCHEMA_DIR})",
    )
    args = parser.parse_args(argv)

    print("Checking for rdf:type values not declared as owl:Class in the ontology...")
    store = load_store(args.rdf_dir, args.schema_dir)
    undeclared = find_undeclared_classes(store)

    if undeclared:
        print(f"::error::Found {len(undeclared)} undeclared class(es) used as rdf:type:")
        for type_iri, count in undeclared:
            print(f"::error::  {type_iri} ({count} instances)")
        print(
            "::error::Add an owl:Class declaration to schema/ontology.ttl, "
            "or fix the typo in the RML mapping / SSSOM lookup that introduced this type."
        )
        return 1

    print("No undeclared classes found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
