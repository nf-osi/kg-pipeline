#!/usr/bin/env python3
"""Check that named source collections agree between data_sources.yaml and the built RDF.

A source collection (e.g. nf:ToolsCentralPublications) is declared once by a
table's ``collection_name`` in data_sources.yaml, from which
scripts/build_metadata.py generates the void:Dataset node. Individual entities
are attached to it by a hardcoded ``prov:wasDerivedFrom`` constant in that
table's RML mapping, because RML cannot read the YAML.

That split means the two can drift: a mapping can point entities at a
collection IRI that nothing defines, leaving dangling provenance. This check
fails the build when that happens.

Usage:
    python scripts/validate_collections.py [--rdf-dir DIR] [--data-sources FILE]

Exit code is 1 if any referenced collection is undeclared or unbuilt.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from pyoxigraph import Store, RdfFormat

DEFAULT_RDF_DIR = Path("data/rdf")
DEFAULT_DATA_SOURCES = Path("data_sources.yaml")

NF_NS = "http://nf-osi.github.com/terms#"
PROV_WAS_DERIVED_FROM = "http://www.w3.org/ns/prov#wasDerivedFrom"
VOID_DATASET = "http://rdfs.org/ns/void#Dataset"

# Collection IRIs referenced by entities in the built RDF.
REFERENCED_QUERY = f"""
SELECT DISTINCT ?collection WHERE {{
  ?s <{PROV_WAS_DERIVED_FROM}> ?collection .
  FILTER(STRSTARTS(STR(?collection), "{NF_NS}"))
}}
"""

# Collection IRIs actually built as void:Dataset nodes.
BUILT_QUERY = f"""
SELECT DISTINCT ?collection WHERE {{
  ?collection a <{VOID_DATASET}> .
  FILTER(STRSTARTS(STR(?collection), "{NF_NS}"))
}}
"""


def declared_collections(data_sources: Path) -> set[str]:
    """Collection IRIs declared by any profile's tables in data_sources.yaml."""
    with open(data_sources) as f:
        config = yaml.safe_load(f)
    names = set()
    for profile in config.get("profiles", {}).values():
        for table in profile.get("tables", {}).values():
            name = table.get("collection_name")
            if name:
                names.add(NF_NS + name)
    return names


def load_store(rdf_dir: Path) -> Store:
    store = Store()
    for ttl in sorted(rdf_dir.glob("*.ttl")):
        with open(ttl, "rb") as f:
            store.bulk_load(f, RdfFormat.TURTLE)
    return store


def _query_iris(store: Store, query: str) -> set[str]:
    return {str(row["collection"].value) for row in store.query(query)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rdf-dir", type=Path, default=DEFAULT_RDF_DIR)
    parser.add_argument("--data-sources", type=Path, default=DEFAULT_DATA_SOURCES)
    args = parser.parse_args(argv)

    declared = declared_collections(args.data_sources)
    store = load_store(args.rdf_dir)
    referenced = _query_iris(store, REFERENCED_QUERY)
    built = _query_iris(store, BUILT_QUERY)

    errors = []
    for iri in sorted(referenced - declared):
        errors.append(
            f"{iri} is referenced by prov:wasDerivedFrom in the RDF but is not "
            f"declared as a collection in {args.data_sources}. Add "
            f"`collection_name:` to the source table, or fix the constant in "
            f"that table's RML mapping."
        )
    for iri in sorted(referenced - built):
        if iri in declared:
            errors.append(
                f"{iri} is declared in {args.data_sources} and referenced by "
                f"entities, but no void:Dataset node was built for it. Is "
                f"build_metadata.py running, and is the table in the profile "
                f"being built?"
            )

    if errors:
        print("Source collection check FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    if referenced:
        print(f"Source collections OK: {len(referenced)} referenced, all declared and built")
        for iri in sorted(referenced):
            print(f"  {iri.replace(NF_NS, 'nf:')}")
    else:
        print("Source collections OK: none referenced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
