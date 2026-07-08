#!/usr/bin/env python3
"""Build graph-level VoID/PROV metadata describing a KG build.

Emits a small TTL file with the build datetime (serving as the graph build
version) and the source tables used, as recorded in data_sources.yaml,
including each source table's version and its Synapse entity type (e.g.
https://rest-docs.synapse.org/rest/org/sagebionetworks/repo/model/table/TableEntity.html).
Intended to run as part of the RDF generation pipeline, alongside the other
data/rdf/*.ttl files, so the metadata is included whenever the graph is merged
(e.g. by scripts/archive_rdf.py).

Usage:
    python scripts/build_metadata.py [--data-sources FILE] [--profile PROFILE] [--output FILE]

Examples:
    python scripts/build_metadata.py
    python scripts/build_metadata.py --profile evaluation --output data/rdf/build_metadata.ttl
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pyoxigraph import Store, RdfFormat, serialize, DefaultGraph, NamedNode, Literal, Quad

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_SOURCES = Path("data_sources.yaml")
DEFAULT_OUTPUT = Path("data/rdf/build_metadata.ttl")

TTL_PREFIXES = {
    "nf": "http://nf-osi.github.com/terms#",
    "syn": "https://www.synapse.org/Synapse:",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "dcterms": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
    "void": "http://rdfs.org/ns/void#",
}

SYNAPSE_TABLE_CLASS_BASE = "https://rest-docs.synapse.org/rest/org/sagebionetworks/repo/model/table/"

RDF_TYPE = NamedNode(TTL_PREFIXES["rdf"] + "type")
RDFS_LABEL = NamedNode(TTL_PREFIXES["rdfs"] + "label")
RDFS_COMMENT = NamedNode(TTL_PREFIXES["rdfs"] + "comment")
DCTERMS_HAS_VERSION = NamedNode(TTL_PREFIXES["dcterms"] + "hasVersion")
PROV_GENERATED_AT_TIME = NamedNode(TTL_PREFIXES["prov"] + "generatedAtTime")
PROV_WAS_DERIVED_FROM = NamedNode(TTL_PREFIXES["prov"] + "wasDerivedFrom")
VOID_DATASET = NamedNode(TTL_PREFIXES["void"] + "Dataset")
XSD_DATETIME = NamedNode(TTL_PREFIXES["xsd"] + "dateTime")
KG_BUILD = NamedNode(TTL_PREFIXES["nf"] + "KGBuild")


def build_metadata_quads(profile: dict, build_time: datetime) -> list[Quad]:
    """Build graph-level VoID/PROV metadata describing this build: build datetime
    (serving as the graph build version) and the source table versions used,
    as recorded in data_sources.yaml.
    """
    quads = [
        Quad(KG_BUILD, RDF_TYPE, VOID_DATASET),
        Quad(KG_BUILD, RDFS_LABEL, Literal("NF-OSI Knowledge Graph")),
        Quad(KG_BUILD, DCTERMS_HAS_VERSION, Literal(profile.get("version", ""))),
        Quad(KG_BUILD, PROV_GENERATED_AT_TIME, Literal(build_time.isoformat(), datatype=XSD_DATETIME)),
    ]
    for table_name, table in profile.get("tables", {}).items():
        synapse_id = table.get("synapse_id")
        if not synapse_id:
            continue
        source_node = NamedNode(TTL_PREFIXES["syn"] + synapse_id)
        quads.append(Quad(KG_BUILD, PROV_WAS_DERIVED_FROM, source_node))
        quads.append(Quad(source_node, RDFS_LABEL, Literal(table_name)))
        concrete_type = table.get("concrete_type")
        if concrete_type:
            quads.append(Quad(source_node, RDF_TYPE, NamedNode(SYNAPSE_TABLE_CLASS_BASE + concrete_type + ".html")))
        source_version = table.get("source_version")
        if source_version is not None:
            quads.append(Quad(source_node, DCTERMS_HAS_VERSION, Literal(str(source_version))))
        elif table.get("source_version_note"):
            quads.append(Quad(source_node, RDFS_COMMENT, Literal(table["source_version_note"])))
    return quads


def write_metadata_ttl(data_sources_path: Path, profile_name: str, output_path: Path) -> Path:
    """Load the given profile from data_sources.yaml and write build metadata TTL."""
    with open(data_sources_path) as f:
        sources = yaml.safe_load(f)

    profile = sources["profiles"].get(profile_name)
    if not profile:
        raise KeyError(f"Profile '{profile_name}' not found in {data_sources_path}")

    build_time = datetime.now(timezone.utc)
    quads = build_metadata_quads(profile, build_time)

    store = Store()
    for quad in quads:
        store.add(quad)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    triples = (quad.triple for quad in store.quads_for_pattern(None, None, None, DefaultGraph()))
    serialize(triples, output=str(output_path), format=RdfFormat.TURTLE, prefixes=TTL_PREFIXES)
    logger.info("Wrote build metadata: %s (%d triples)", output_path, len(store))
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-sources",
        type=Path,
        default=DATA_SOURCES,
        help=f"Path to data_sources.yaml (default: {DATA_SOURCES})",
    )
    parser.add_argument(
        "--profile",
        default="release",
        help="Profile in data_sources.yaml to describe (default: release)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output TTL path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args(argv)

    write_metadata_ttl(args.data_sources, args.profile, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
