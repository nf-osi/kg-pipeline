#!/usr/bin/env python3
"""Fetch raw Synapse tables, archive them, and update data_sources.yaml.

This script queries each table in the chosen profile via ``SELECT * FROM
<synapse_id>``, saves the raw CSVs to data/raw/, creates a tar.gz archive,
uploads it to a Synapse folder, and updates data_sources.yaml with the
archive metadata.

Prerequisites:
    Set SYNAPSE_AUTH_TOKEN environment variable:
        export SYNAPSE_AUTH_TOKEN='your-synapse-token'

Usage:
    python scripts/create_archive.py --profile release --comment "KG v0.1 release"
    python scripts/create_archive.py --profile eval --comment "Evaluation snapshot"
    python scripts/create_archive.py --profile release --comment "Bug fix" --tables studies files
    python scripts/create_archive.py --profile release --comment "Test" --dry-run

Output:
    Saves raw CSVs to data/raw/
    Creates a file like: csv-release-20250210.tar.gz
    Uploads to Synapse folder (default: syn73695288)
    Updates data_sources.yaml with archive metadata
"""

from __future__ import annotations

import argparse
import os
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import synapseclient
from synapseclient import File
import yaml


def load_version_config(config_path: Path) -> Dict[str, Any]:
    """Load the data_sources.yaml configuration file.

    Args:
        config_path: Path to data_sources.yaml

    Returns:
        Parsed YAML configuration as a dictionary
    """
    with config_path.open("r") as f:
        return yaml.safe_load(f)


def save_version_config(config_path: Path, config: Dict[str, Any]) -> None:
    """Save the updated configuration back to data_sources.yaml.

    Args:
        config_path: Path to data_sources.yaml
        config: Updated configuration dictionary
    """
    with config_path.open("w") as f:
        yaml.dump(
            config,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def fetch_raw_tables(
    syn: synapseclient.Synapse,
    tables: Dict[str, Dict[str, Any]],
    raw_dir: Path,
) -> Dict[str, int]:
    """Query each Synapse table and save the raw CSV to *raw_dir*.

    Args:
        syn: Authenticated Synapse client
        tables: ``{name: {synapse_id: ..., ...}}`` from the profile config
        raw_dir: Directory to write raw CSVs into

    Returns:
        ``{table_name: row_count}``
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    table_counts: Dict[str, int] = {}

    for table_name, table_info in tables.items():
        synapse_id = table_info["synapse_id"]
        print(f"  Fetching {table_name} ({synapse_id})...", end=" ", flush=True)
        result = syn.tableQuery(f"SELECT * FROM {synapse_id}")
        df = result.asDataFrame()
        row_count = len(df)
        csv_path = raw_dir / f"{table_name}.csv"
        df.to_csv(csv_path, index=False)
        table_counts[table_name] = row_count
        print(f"{row_count} rows", flush=True)

    return table_counts


def count_raw_tables(
    tables: Dict[str, Dict[str, Any]],
    raw_dir: Path,
) -> Dict[str, int]:
    """Count rows in existing raw CSVs without fetching from Synapse.

    Raises:
        FileNotFoundError: If any expected CSV is missing from *raw_dir*.
    """
    missing = [n for n in tables if not (raw_dir / f"{n}.csv").exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing CSVs in {raw_dir}: {', '.join(missing)}"
        )

    table_counts: Dict[str, int] = {}
    for table_name in tables:
        csv_path = raw_dir / f"{table_name}.csv"
        with csv_path.open() as f:
            row_count = sum(1 for _ in f) - 1  # exclude header
        table_counts[table_name] = row_count
        print(f"  {table_name}.csv: {row_count} rows", flush=True)
    return table_counts


def create_csv_archive(
    tables: Dict[str, Dict[str, Any]],
    profile: str,
    raw_dir: Path,
) -> Path:
    """Create a compressed archive from raw CSVs in *raw_dir*.

    Args:
        tables: Dictionary of table configurations
        profile: Profile name for naming the archive
        raw_dir: Directory containing the raw CSV files

    Returns:
        Path to the created tar.gz archive
    """
    date = datetime.now().strftime("%Y%m%d")
    archive_name = f"csv-{profile}-{date}.tar.gz"
    archive_path = Path(tempfile.gettempdir()) / archive_name

    print(f"\nCreating archive {archive_name}...", flush=True)
    with tarfile.open(archive_path, "w:gz") as tar:
        for table_name in tables.keys():
            csv_path = raw_dir / f"{table_name}.csv"
            tar.add(csv_path, arcname=csv_path.name)

    print(f"  Archive created: {archive_path}", flush=True)
    return archive_path


def upload_archive_to_synapse(
    syn: synapseclient.Synapse,
    archive_path: Path,
    folder_id: str,
    comment: str,
    profile: str,
) -> tuple[str, int]:
    """Upload archive to Synapse folder.

    Args:
        syn: Authenticated Synapse client
        archive_path: Path to the tar.gz archive
        folder_id: Synapse ID of the destination folder
        comment: Version comment
        profile: Profile name for annotations

    Returns:
        Tuple of (synapse_id, version_number)
    """
    print(f"Uploading to Synapse folder {folder_id}...", flush=True)

    # Create File entity with annotations
    file_entity = File(
        path=str(archive_path),
        parent=folder_id,
        description=f"Table snapshot archive for {profile} profile",
        annotations={
            "profile": profile,
            "comment": comment,
            "contentType": "application/gzip",
        }
    )

    # Upload (will create new version if file with same name exists)
    uploaded = syn.store(file_entity, forceVersion=True)

    print(f"  ✓ Uploaded: {uploaded.id}.{uploaded.versionNumber}", flush=True)

    return uploaded.id, uploaded.versionNumber


def version_profile_tables(
    syn: synapseclient.Synapse,
    config: Dict[str, Any],
    profile: str,
    comment: str,
    archive_folder_id: str,
    table_subset: Optional[List[str]] = None,
    raw_dir: Path = Path("data/raw"),
    from_cache: bool = False,
) -> tuple[str, int, Dict[str, int]]:
    """Fetch raw tables from Synapse (or use cached CSVs), archive, and upload.

    Args:
        syn: Authenticated Synapse client
        config: Configuration dictionary from data_sources.yaml
        profile: Profile name ('release' or 'evaluation')
        comment: Version comment for the archive
        archive_folder_id: Synapse folder ID to upload archive to
        table_subset: Optional list of specific table names to include
        raw_dir: Directory to save raw CSVs (default: data/raw)
        from_cache: If True, skip fetching and use existing CSVs in raw_dir

    Returns:
        Tuple of (archive_synapse_id, archive_version, table_row_counts)
    """
    if profile not in config["profiles"]:
        raise ValueError(f"Profile '{profile}' not found in configuration")

    profile_config = config["profiles"][profile]
    tables = profile_config["tables"]

    # Filter to subset if provided
    if table_subset:
        tables = {k: v for k, v in tables.items() if k in table_subset}
        if not tables:
            raise ValueError(f"None of the specified tables found in profile '{profile}'")

    try:
        if from_cache:
            print(f"Using cached CSVs from {raw_dir}...\n", flush=True)
            table_counts = count_raw_tables(tables, raw_dir)
        else:
            print(f"Fetching {len(tables)} tables from Synapse...\n", flush=True)
            table_counts = fetch_raw_tables(syn, tables, raw_dir)

        # Create archive from raw CSVs
        archive_path = create_csv_archive(tables, profile, raw_dir)

        # Upload to Synapse
        archive_id, archive_version = upload_archive_to_synapse(
            syn, archive_path, archive_folder_id, comment, profile
        )

        # Clean up archive file
        archive_path.unlink()

        return archive_id, archive_version, table_counts

    except Exception as e:
        print(f"  ✗ Failed: {e}", file=sys.stderr, flush=True)
        raise


def update_config_versions(
    config: Dict[str, Any],
    profile: str,
    archive_id: str,
    archive_version: int,
    comment: str,
) -> Dict[str, Any]:
    """Update the configuration with CSV archive metadata.

    Args:
        config: Configuration dictionary from data_sources.yaml
        profile: Profile name that was versioned
        archive_id: Synapse ID of the uploaded archive
        archive_version: Version number of the archive
        comment: Version comment

    Returns:
        Updated configuration dictionary
    """
    profile_config = config["profiles"][profile]

    # Ensure csv_archive section exists
    if "csv_archive" not in profile_config:
        profile_config["csv_archive"] = {}

    # Update CSV archive metadata
    profile_config["csv_archive"]["archive_id"] = archive_id
    profile_config["csv_archive"]["archive_version"] = archive_version
    profile_config["csv_archive"]["last_snapshot_comment"] = comment
    profile_config["csv_archive"]["last_snapshot_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return config


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--profile",
        required=True,
        choices=["release", "evaluation", "eval"],
        help="Versioning profile to use (release, evaluation, or eval)",
    )
    parser.add_argument(
        "--comment",
        required=True,
        help="Version comment describing this snapshot",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        help="Optional subset of table names to include (defaults to all tables in profile)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("data_sources.yaml"),
        help="Path to data_sources.yaml (default: data_sources.yaml)",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory to save raw CSVs (default: data/raw)",
    )
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Archive and upload existing CSVs in --raw-dir instead of fetching from Synapse",
    )
    parser.add_argument(
        "--archive-folder",
        type=str,
        default="syn73695288",
        help="Synapse folder ID to upload archives to (default: syn73695288)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without creating archive or updating the config",
    )
    args = parser.parse_args(argv)

    # Map profile aliases
    if args.profile == "eval":
        args.profile = "evaluation"

    # Load configuration
    if not args.config.exists():
        parser.error(f"Configuration file not found: {args.config}")

    config = load_version_config(args.config)

    # Validate profile exists
    if args.profile not in config.get("profiles", {}):
        parser.error(f"Profile '{args.profile}' not found in {args.config}")

    # Get tables for the profile
    tables = config["profiles"][args.profile]["tables"]
    table_subset = args.tables if args.tables else None

    if table_subset:
        # Validate table names
        invalid_tables = set(table_subset) - set(tables.keys())
        if invalid_tables:
            parser.error(
                f"Tables not found in profile '{args.profile}': {', '.join(invalid_tables)}"
            )

    # Show what will be versioned
    print(f"Profile: {args.profile}")
    print(f"Comment: {args.comment}")
    print(f"Archive folder: {args.archive_folder}")
    if table_subset:
        print(f"Tables: {', '.join(table_subset)}")
        tables_to_version = {k: v for k, v in tables.items() if k in table_subset}
    else:
        print(f"Tables: all ({len(tables)} tables)")
        tables_to_version = tables

    print()
    for table_name, table_info in tables_to_version.items():
        print(f"  {table_name}: {table_info['synapse_id']}")
    print()

    if args.dry_run:
        print("DRY RUN: No changes will be made.")
        return 0

    # Authenticate with Synapse
    print("Authenticating with Synapse...", flush=True)
    auth_token = os.getenv("SYNAPSE_AUTH_TOKEN")
    if not auth_token:
        print("ERROR: SYNAPSE_AUTH_TOKEN environment variable not set", file=sys.stderr)
        print("Please set SYNAPSE_AUTH_TOKEN before running this script:", file=sys.stderr)
        print("  export SYNAPSE_AUTH_TOKEN='your-token-here'", file=sys.stderr)
        return 1

    syn = synapseclient.Synapse()
    syn.login(authToken=auth_token, silent=True)
    print("Authenticated successfully.\n", flush=True)

    # Fetch (or use cached), archive, and upload
    try:
        archive_id, archive_version, table_counts = version_profile_tables(
            syn, config, args.profile, args.comment, args.archive_folder,
            table_subset, args.raw_dir, args.from_cache,
        )
    except Exception as e:
        print(f"\nError creating archive: {e}", file=sys.stderr)
        return 1

    # Update configuration file
    print(f"\nUpdating {args.config}...", flush=True)
    updated_config = update_config_versions(
        config, args.profile, archive_id, archive_version, args.comment
    )
    save_version_config(args.config, updated_config)
    print("Configuration updated successfully.", flush=True)

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Profile: {args.profile}")
    print(f"Tables archived: {len(table_counts)}")
    print(f"Comment: {args.comment}")
    print(f"\nArchive: {archive_id}.{archive_version}")
    print(f"Location: {args.archive_folder}")
    print("\nTable row counts:")
    for table_name, count in table_counts.items():
        print(f"  {table_name}: {count:,} rows")
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
