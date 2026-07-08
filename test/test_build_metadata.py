import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_metadata import (
    build_metadata_quads,
    write_metadata_ttl,
    KG_BUILD,
    PROV_WAS_DERIVED_FROM,
    RDF_TYPE,
    SYNAPSE_TABLE_CLASS_BASE,
)


def test_build_metadata_quads_includes_build_version_and_datetime():
    profile = {"version": "KG v0.2", "tables": {}}
    build_time = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)

    quads = build_metadata_quads(profile, build_time)

    subjects_predicates = {(q.subject, q.predicate) for q in quads}
    assert (KG_BUILD, PROV_WAS_DERIVED_FROM) not in subjects_predicates

    version_quad = next(q for q in quads if q.predicate.value.endswith("hasVersion"))
    assert version_quad.object.value == "KG v0.2"

    time_quad = next(q for q in quads if q.predicate.value.endswith("generatedAtTime"))
    assert time_quad.object.value == build_time.isoformat()


def test_build_metadata_quads_links_versioned_source_tables():
    profile = {
        "version": "KG v0.2",
        "tables": {
            "mutations": {"synapse_id": "syn26486835", "concrete_type": "TableEntity", "source_version": 4},
            "studies": {
                "synapse_id": "syn52694652",
                "concrete_type": "MaterializedView",
                "source_version": None,
                "source_version_note": "MaterializedView is not versionable",
            },
        },
    }
    build_time = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)

    quads = build_metadata_quads(profile, build_time)

    derived_from = {q.object.value for q in quads if q.predicate == PROV_WAS_DERIVED_FROM}
    assert "https://www.synapse.org/Synapse:syn26486835" in derived_from
    assert "https://www.synapse.org/Synapse:syn52694652" in derived_from

    mutations_version = next(
        q.object.value
        for q in quads
        if q.subject.value == "https://www.synapse.org/Synapse:syn26486835"
        and q.predicate.value.endswith("hasVersion")
    )
    assert mutations_version == "4"

    studies_comment = next(
        q.object.value
        for q in quads
        if q.subject.value == "https://www.synapse.org/Synapse:syn52694652"
        and q.predicate.value.endswith("comment")
    )
    assert studies_comment == "MaterializedView is not versionable"

    mutations_type = next(
        q.object.value
        for q in quads
        if q.subject.value == "https://www.synapse.org/Synapse:syn26486835" and q.predicate == RDF_TYPE
    )
    assert mutations_type == SYNAPSE_TABLE_CLASS_BASE + "TableEntity.html"

    studies_type = next(
        q.object.value
        for q in quads
        if q.subject.value == "https://www.synapse.org/Synapse:syn52694652" and q.predicate == RDF_TYPE
    )
    assert studies_type == SYNAPSE_TABLE_CLASS_BASE + "MaterializedView.html"


def test_write_metadata_ttl_writes_parseable_turtle(tmp_path):
    data_sources_path = tmp_path / "data_sources.yaml"
    data_sources_path.write_text(yaml.dump({
        "profiles": {
            "release": {
                "version": "KG v0.2",
                "tables": {
                    "mutations": {"synapse_id": "syn26486835", "source_version": 4},
                },
            },
        },
    }))
    output_path = tmp_path / "build_metadata.ttl"

    write_metadata_ttl(data_sources_path, "release", output_path)

    assert output_path.exists()
    ttl = output_path.read_text()
    assert "syn26486835" in ttl
    assert "hasVersion" in ttl
