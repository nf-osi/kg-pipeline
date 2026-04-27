#!/usr/bin/env python3
"""Archive current RDF build to Synapse and update data_sources.yaml.

Merges all TTL files from data/rdf/ into a single kg_rdf.ttl and uploads
to the configured Synapse folder. Creates a new Synapse file entity on first
run; subsequent runs upload a new version of the same entity.

Updates data_sources.yaml with the new archive_id, archive_version, and
last_snapshot_date after a successful upload.

Usage:
    python scripts/archive_rdf.py [--rdf-dir DIR] [--profile PROFILE] [--comment TEXT]

Examples:
    python scripts/archive_rdf.py
    python scripts/archive_rdf.py --comment "Build v1.2.0"
    python scripts/archive_rdf.py --profile evaluation
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import synapseclient
from synapseclient import File
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
ARCHIVE_FILENAME = "kg_rdf.ttl"

TTL_PREFIXES = {
    "nf": "http://nf-osi.github.com/terms#",
    "syn": "https://www.synapse.org/Synapse:",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "edam": "http://edamontology.org/",
}


def merge_rdf_dir(rdf_dir: Path) -> Store:
    """Merge all non-raw TTL files from a directory into a single store."""
    store = Store()
    ttl_files = sorted(f for f in rdf_dir.glob("*.ttl") if not f.name.endswith("_raw.ttl"))
    if not ttl_files:
        raise FileNotFoundError(f"No TTL files found in {rdf_dir}")
    for ttl_file in ttl_files:
        logger.info("  Loading %s", ttl_file)
        with open(ttl_file, "rb") as f:
            store.bulk_load(f, RdfFormat.TURTLE)
    logger.info("Merged %d triples from %d files", len(store), len(ttl_files))
    return store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--rdf-dir",
        type=Path,
        default=DEFAULT_RDF_DIR,
        help=f"Directory containing TTL files to archive (default: {DEFAULT_RDF_DIR})",
    )
    parser.add_argument(
        "--profile",
        default="release",
        help="Profile in data_sources.yaml to update (default: release)",
    )
    parser.add_argument(
        "--comment",
        default="",
        help="Snapshot comment recorded in data_sources.yaml",
    )
    args = parser.parse_args(argv)

    with open(DATA_SOURCES) as f:
        sources = yaml.safe_load(f)

    profile = sources["profiles"].get(args.profile)
    if not profile:
        logger.error("Profile '%s' not found in %s", args.profile, DATA_SOURCES)
        return 1

    rdf_archive = profile.get("rdf_archive", {})
    folder_id = rdf_archive.get("folder_id")
    archive_id = rdf_archive.get("archive_id")

    if not folder_id:
        logger.error("rdf_archive.folder_id not set in data_sources.yaml for profile '%s'", args.profile)
        return 1

    logger.info("Merging RDF from %s", args.rdf_dir)
    store = merge_rdf_dir(args.rdf_dir)

    with tempfile.TemporaryDirectory() as tmpdir:
        merged_path = Path(tmpdir) / ARCHIVE_FILENAME
        triples = (quad.triple for quad in store.quads_for_pattern(None, None, None, DefaultGraph()))
        serialize(triples, output=str(merged_path), format=RdfFormat.TURTLE, prefixes=TTL_PREFIXES)
        logger.info("Wrote merged archive: %s (%d triples)", merged_path, len(store))

        syn = synapseclient.Synapse()
        syn.login(silent=True)

        if archive_id:
            logger.info("Uploading new version of %s to Synapse", archive_id)
            entity = File(path=str(merged_path), id=archive_id)
        else:
            logger.info("Creating new Synapse file in folder %s", folder_id)
            entity = File(path=str(merged_path), parent=folder_id, name=ARCHIVE_FILENAME)

        stored = syn.store(entity)
        new_id = stored.id
        new_version = stored.versionNumber
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        logger.info("Uploaded: %s version %s", new_id, new_version)

    # Update data_sources.yaml
    rdf_archive["archive_id"] = new_id
    rdf_archive["archive_version"] = new_version
    rdf_archive["last_snapshot_date"] = now
    rdf_archive["last_snapshot_comment"] = args.comment or None

    with open(DATA_SOURCES, "w") as f:
        yaml.dump(sources, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logger.info("Updated %s: archive_id=%s, archive_version=%s", DATA_SOURCES, new_id, new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
