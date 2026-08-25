import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.check_source_versions import (
    apply_updates,
    compute_updates,
    render_summary_markdown,
    resolve_versionable_targets,
)


def _config():
    return {
        "profiles": {
            "release": {
                "tables": {
                    "mutations": {
                        "synapse_id": "syn26486835",
                        "concrete_type": "TableEntity",
                        "source_version": 4,
                    },
                    "people": {
                        "synapse_id": "syn23564971",
                        "concrete_type": "TableEntity",
                        "source_version": 10,
                    },
                    "publication_author_orcids": {
                        "synapse_id": "syn23564971",
                        "concrete_type": "TableEntity",
                        "source_version": 10,
                    },
                    "studies": {
                        "synapse_id": "syn52694652",
                        "concrete_type": "MaterializedView",
                        "source_version": None,
                    },
                },
            },
            "evaluation": {
                "tables": {
                    "mutations": {
                        "synapse_id": "syn26486835",
                        "concrete_type": "TableEntity",
                        "source_version": 4,
                    },
                },
            },
        },
    }


def test_resolve_versionable_targets_skips_materialized_views():
    targets = resolve_versionable_targets(_config(), ["release"])
    assert "syn52694652" not in targets
    assert set(targets) == {"syn26486835", "syn23564971"}


def test_resolve_versionable_targets_groups_shared_synapse_id():
    targets = resolve_versionable_targets(_config(), ["release"])
    people_target = targets["syn23564971"]
    assert set(people_target["pins"]) == {
        ("release", "people"),
        ("release", "publication_author_orcids"),
    }
    assert people_target["current_versions"] == {10}


def test_resolve_versionable_targets_unknown_profile_raises():
    try:
        resolve_versionable_targets(_config(), ["nonexistent"])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_compute_updates_flags_newer_snapshot():
    targets = resolve_versionable_targets(_config(), ["release"])
    latest_versions = {
        "syn26486835": {"versionNumber": 5, "versionLabel": "2026-08-01", "versionComment": "Scheduled snapshot"},
        "syn23564971": {"versionNumber": 10, "versionLabel": "v10", "versionComment": None},
    }

    updates = compute_updates(targets, latest_versions)

    assert len(updates) == 1
    update = updates[0]
    assert update["synapse_id"] == "syn26486835"
    assert update["old_versions"] == [4]
    assert update["new_version"] == 5


def test_compute_updates_skips_already_current():
    targets = resolve_versionable_targets(_config(), ["release"])
    latest_versions = {
        "syn26486835": {"versionNumber": 4, "versionLabel": None, "versionComment": None},
        "syn23564971": {"versionNumber": 10, "versionLabel": None, "versionComment": None},
    }

    assert compute_updates(targets, latest_versions) == []


def test_compute_updates_skips_never_snapshotted():
    targets = resolve_versionable_targets(_config(), ["release"])
    latest_versions = {"syn26486835": None, "syn23564971": None}

    assert compute_updates(targets, latest_versions) == []


def test_compute_updates_does_not_downgrade():
    targets = resolve_versionable_targets(_config(), ["release"])
    latest_versions = {
        "syn26486835": {"versionNumber": 2, "versionLabel": None, "versionComment": None},
        "syn23564971": {"versionNumber": 10, "versionLabel": None, "versionComment": None},
    }

    assert compute_updates(targets, latest_versions) == []


def test_apply_updates_updates_all_pinned_table_names():
    config = _config()
    updates = [
        {
            "synapse_id": "syn23564971",
            "pins": [("release", "people"), ("release", "publication_author_orcids")],
            "old_versions": [10],
            "new_version": 11,
            "label": None,
            "comment": None,
            "modified_on": None,
        }
    ]

    apply_updates(config, updates)

    tables = config["profiles"]["release"]["tables"]
    assert tables["people"]["source_version"] == 11
    assert tables["publication_author_orcids"]["source_version"] == 11
    assert tables["mutations"]["source_version"] == 4  # untouched


def test_render_summary_markdown_reports_no_changes():
    summary = render_summary_markdown([])
    assert "No pinned" in summary


def test_render_summary_markdown_lists_each_update():
    updates = [
        {
            "synapse_id": "syn26486835",
            "pins": [("release", "mutations")],
            "old_versions": [4],
            "new_version": 5,
            "label": "2026-08-01",
            "comment": "Scheduled snapshot",
            "modified_on": "2026-08-01T00:00:00.000Z",
        }
    ]

    summary = render_summary_markdown(updates)

    assert "syn26486835" in summary
    assert "mutations" in summary
    assert "4" in summary
    assert "5" in summary
    assert "Scheduled snapshot" in summary
