#!/usr/bin/env python3
"""Generate RDF diffs (added/removed triples) between the previous Synapse archive and current build.

Reads archive location from data_sources.yaml, downloads the archived version,
and compares against the current local RDF files.

Usage:
    python scripts/diff_rdf.py [--rdf-dir DIR] [--output-dir DIR] [--profile PROFILE]

Examples:
    python scripts/diff_rdf.py
    python scripts/diff_rdf.py --output-dir data/diff/
    python scripts/diff_rdf.py --profile evaluation
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

import synapseclient
import yaml
from pyoxigraph import Store, RdfFormat, serialize, DefaultGraph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_SOURCES = Path("data_sources.yaml")
DEFAULT_RDF_DIR = Path("data/rdf")
DEFAULT_SCHEMA_DIR = Path("schema")
DEFAULT_OUTPUT_DIR = Path("data/diff")

TTL_PREFIXES = {
    "nf": "http://nf-osi.github.com/terms#",
    "syn": "https://www.synapse.org/Synapse:",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "edam": "http://edamontology.org/",
}


def load_current(rdf_dir: Path, schema_dir: Path) -> Store:
    """Load current data and schema TTL files into a single store."""
    store = Store()
    data_files = sorted(f for f in rdf_dir.glob("*.ttl") if not f.name.endswith("_raw.ttl"))
    schema_files = sorted(schema_dir.glob("*.ttl"))
    all_files = data_files + schema_files
    if not all_files:
        raise FileNotFoundError(f"No TTL files found in {rdf_dir} or {schema_dir}")
    for ttl_file in all_files:
        logger.info("  Loading %s", ttl_file)
        with open(ttl_file, "rb") as f:
            store.bulk_load(f, RdfFormat.TURTLE)
    logger.info("Loaded %d triples from %d files (%d data, %d schema)",
                len(store), len(all_files), len(data_files), len(schema_files))
    return store


def write_diff_ttl(quads: set, output_path: Path) -> int:
    """Write a set of quads to a Turtle file. Returns triple count."""
    store = Store()
    for quad in quads:
        store.add(quad)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    triples = (quad.triple for quad in store.quads_for_pattern(None, None, None, DefaultGraph()))
    serialize(triples, output=str(output_path), format=RdfFormat.TURTLE, prefixes=TTL_PREFIXES)
    return len(store)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--rdf-dir",
        type=Path,
        default=DEFAULT_RDF_DIR,
        help=f"Directory containing current data TTL files (default: {DEFAULT_RDF_DIR})",
    )
    parser.add_argument(
        "--schema-dir",
        type=Path,
        default=DEFAULT_SCHEMA_DIR,
        help=f"Directory containing current schema TTL files (default: {DEFAULT_SCHEMA_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to write added.ttl and removed.ttl (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--profile",
        default="release",
        help="Profile in data_sources.yaml to use (default: release)",
    )
    parser.add_argument(
        "--previous",
        type=Path,
        help="Local path to previous archive TTL (skips Synapse fetch, useful for testing)",
    )
    args = parser.parse_args(argv)

    with open(DATA_SOURCES) as f:
        sources = yaml.safe_load(f)

    profile = sources["profiles"].get(args.profile)
    if not profile:
        logger.error("Profile '%s' not found in %s", args.profile, DATA_SOURCES)
        return 1

    rdf_archive = profile.get("rdf_archive", {})
    archive_id = rdf_archive.get("archive_id")
    archive_version = rdf_archive.get("archive_version")

    if args.previous:
        logger.info("Using local previous archive: %s", args.previous)
        prev_store = Store()
        with open(args.previous, "rb") as f:
            prev_store.bulk_load(f, RdfFormat.TURTLE)
        logger.info("Previous archive: %d triples", len(prev_store))
    else:
        if not archive_id:
            logger.info("No previous RDF archive found in data_sources.yaml — skipping diff")
            return 0

        logger.info(
            "Fetching previous archive %s version %s from Synapse",
            archive_id, archive_version,
        )
        syn = synapseclient.Synapse()
        syn.login(silent=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            entity = syn.get(archive_id, version=archive_version, downloadLocation=tmpdir)
            prev_path = Path(entity.path)
            logger.info("Downloaded previous archive: %s", prev_path)
            prev_store = Store()
            with open(prev_path, "rb") as f:
                prev_store.bulk_load(f, RdfFormat.TURTLE)
            logger.info("Previous archive: %d triples", len(prev_store))

    logger.info("Loading current RDF from %s and %s", args.rdf_dir, args.schema_dir)
    curr_store = load_current(args.rdf_dir, args.schema_dir)

    prev_quads = set(prev_store)
    curr_quads = set(curr_store)
    added = curr_quads - prev_quads
    removed = prev_quads - curr_quads

    added_path = args.output_dir / "added.ttl"
    removed_path = args.output_dir / "removed.ttl"

    n_added = write_diff_ttl(added, added_path)
    n_removed = write_diff_ttl(removed, removed_path)

    logger.info("Diff complete: +%d added, -%d removed", n_added, n_removed)
    logger.info("  added.ttl   -> %s", added_path)
    logger.info("  removed.ttl -> %s", removed_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
