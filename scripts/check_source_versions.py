#!/usr/bin/env python3
"""Check pinned source table versions against the latest stable Synapse snapshot.

`data_sources.yaml` pins each `TableEntity`/`EntityView` source to a specific
snapshot version so builds stay reproducible (see
docs/kg-pipeline-architecture.md). Portal data managers create new snapshots
independently of this pipeline (e.g. on their own schedule); this script
detects when a newer snapshot exists upstream and updates the pin.

Only committed snapshots are considered -- `GET /entity/{id}/version` lists
snapshot history only, never the mutable "in progress" head, so its highest
`versionNumber` is always the latest STABLE version, never a draft.

`MaterializedView` sources are skipped; they don't support snapshot
versioning (see NON_VERSIONABLE_TYPES).

Prerequisites:
    - A working Synapse login (for example via SYNAPSE_AUTH_TOKEN)
    - Network access to Synapse

Usage:
    python scripts/check_source_versions.py [--config data_sources.yaml] [--profiles release] [--dry-run]

Examples:
    python scripts/check_source_versions.py --dry-run
    python scripts/check_source_versions.py --summary-out /tmp/summary.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

import synapseclient
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_CONFIG = Path("data_sources.yaml")
VERSIONABLE_TYPES = {"EntityView", "TableEntity"}
NON_VERSIONABLE_TYPES = {"MaterializedView"}


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def save_config(path: Path, config: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.dump(config, handle, default_flow_style=False, sort_keys=False, allow_unicode=True)


def resolve_versionable_targets(
    config: dict[str, Any], profiles: list[str]
) -> dict[str, dict[str, Any]]:
    """Map each unique versionable synapse_id to its concrete_type and the
    (profile, table_name) pairs pinned to it, so sources shared across
    profiles/table names (e.g. `people` and `publication_author_orcids`) stay
    in lockstep."""
    known_profiles = config.get("profiles", {})
    targets: dict[str, dict[str, Any]] = {}

    for profile in profiles:
        if profile not in known_profiles:
            raise ValueError(f"Unknown profile: {profile}")
        for table_name, table_info in known_profiles[profile].get("tables", {}).items():
            concrete_type = table_info.get("concrete_type")
            if concrete_type not in VERSIONABLE_TYPES:
                continue
            synapse_id = table_info["synapse_id"]
            entry = targets.setdefault(
                synapse_id,
                {"concrete_type": concrete_type, "pins": [], "current_versions": set()},
            )
            entry["pins"].append((profile, table_name))
            entry["current_versions"].add(table_info.get("source_version"))

    return targets


def fetch_latest_stable_version(syn: synapseclient.Synapse, synapse_id: str) -> dict[str, Any] | None:
    """Return the latest committed snapshot for a Table/View, or None if it
    has never been snapshotted. Only inspects the version list -- never the
    live entity bundle -- so an in-progress draft can never be returned."""
    response = syn.restGET(f"/entity/{synapse_id}/version?offset=0&limit=1")
    results = response.get("results", [])
    if not results:
        return None
    return results[0]


def compute_updates(
    targets: dict[str, dict[str, Any]],
    latest_versions: dict[str, dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Compare each target's pinned version(s) against the latest stable
    snapshot and return the ones that need to move forward. Pure function --
    no Synapse or filesystem access -- so it's testable without mocking a
    client."""
    updates = []
    for synapse_id, target in sorted(targets.items()):
        latest = latest_versions.get(synapse_id)
        if latest is None:
            logger.warning("%s has never been snapshotted; skipping", synapse_id)
            continue

        new_version = latest["versionNumber"]
        current_versions = target["current_versions"]
        if current_versions == {new_version}:
            continue  # already pinned to the latest stable snapshot

        if any(v is not None and v > new_version for v in current_versions):
            logger.warning(
                "%s: pinned version(s) %s are ahead of latest stable snapshot %s; leaving as-is",
                synapse_id, sorted(current_versions), new_version,
            )
            continue

        updates.append(
            {
                "synapse_id": synapse_id,
                "pins": target["pins"],
                "old_versions": sorted(v for v in current_versions if v is not None),
                "new_version": new_version,
                "label": latest.get("versionLabel"),
                "comment": latest.get("versionComment"),
                "modified_on": latest.get("modifiedOn"),
            }
        )
    return updates


def apply_updates(config: dict[str, Any], updates: list[dict[str, Any]]) -> None:
    profiles = config.get("profiles", {})
    for update in updates:
        for profile, table_name in update["pins"]:
            profiles[profile]["tables"][table_name]["source_version"] = update["new_version"]


def render_summary_markdown(updates: list[dict[str, Any]]) -> str:
    if not updates:
        return "No pinned source table versions are behind the latest stable Synapse snapshot.\n"

    lines = [
        "Newer stable Synapse snapshots are available for the following pinned source tables:",
        "",
        "| Synapse ID | Tables | Old version(s) | New version | Snapshot label | Snapshot comment |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for update in updates:
        table_names = ", ".join(sorted({name for _, name in update["pins"]}))
        old_versions = ", ".join(str(v) for v in update["old_versions"]) or "none"
        lines.append(
            f"| {update['synapse_id']} | {table_names} | {old_versions} | "
            f"{update['new_version']} | {update['label'] or ''} | {update['comment'] or ''} |"
        )
    lines.append("")
    lines.append(
        "Review the change against upstream before merging -- this only repins to the "
        "latest committed snapshot, it does not trigger a rebuild."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to data_sources.yaml")
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["release"],
        help="Profiles to check (default: release; the evaluation profile is a frozen benchmark and should not be auto-updated)",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=None,
        help="Write a Markdown summary of any changes (e.g. for a PR body) to this path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without modifying data_sources.yaml",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    targets = resolve_versionable_targets(config, args.profiles)

    syn = synapseclient.Synapse()
    syn.login(silent=True)

    latest_versions = {}
    for synapse_id in targets:
        try:
            latest_versions[synapse_id] = fetch_latest_stable_version(syn, synapse_id)
        except Exception as e:
            logger.error("Failed to fetch latest version for %s: %s", synapse_id, e)
            latest_versions[synapse_id] = None

    updates = compute_updates(targets, latest_versions)
    summary = render_summary_markdown(updates)
    print(summary)

    if args.summary_out:
        args.summary_out.write_text(summary)

    if not updates:
        return 0

    if args.dry_run:
        print("Dry run: data_sources.yaml not modified.")
        return 0

    apply_updates(config, updates)
    save_config(args.config, config)
    print(f"Updated {args.config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
