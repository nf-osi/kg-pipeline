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


# ---------------------------------------------------------------------------
# Named source collections (generated from the `collection:` block in
# data_sources.yaml; entities point at them with prov:wasDerivedFrom)
# ---------------------------------------------------------------------------

BUILD_TIME = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)

COLLECTION_PROFILE = {
    "version": "KG v0.3",
    "tables": {
        "publications": {
            "synapse_id": "syn26486839",
            "concrete_type": "TableEntity",
            "source_version": 9,
            "collection_name": "ToolsCentralPublications",
            "collection_label": "NF Research Tools Central publications",
            "collection_comment": "Partial view: tool-associated publications only.",
        },
        "mutations": {"synapse_id": "syn26486835", "concrete_type": "TableEntity", "source_version": 4},
    },
}

NF = "http://nf-osi.github.com/terms#"
VOID_DATASET_IRI = "http://rdfs.org/ns/void#Dataset"


def _quads_for(quads, subject_iri):
    return {(q.predicate.value, q.object.value) for q in quads if q.subject.value == subject_iri}


def test_collection_node_built_from_yaml():
    """A table declaring `collection:` yields a void:Dataset node carrying its
    label, comment, link to the build, and link to the source Synapse table."""
    quads = build_metadata_quads(COLLECTION_PROFILE, BUILD_TIME)
    facts = _quads_for(quads, NF + "ToolsCentralPublications")

    assert (RDF_TYPE.value, VOID_DATASET_IRI) in facts
    assert (PROV_WAS_DERIVED_FROM.value, "https://www.synapse.org/Synapse:syn26486839") in facts
    assert ("http://purl.org/dc/terms/isPartOf", KG_BUILD.value) in facts
    assert ("http://www.w3.org/2000/01/rdf-schema#label",
            "NF Research Tools Central publications") in facts
    comments = [o for p, o in facts if p.endswith("rdfs-schema#comment") or p.endswith("#comment")]
    assert any("Partial view" in c for c in comments)


def test_table_without_collection_emits_no_collection_node():
    """Only tables that opt in get a collection; the rest are unaffected."""
    quads = build_metadata_quads(COLLECTION_PROFILE, BUILD_TIME)
    collection_subjects = {
        q.subject.value for q in quads
        if q.predicate == RDF_TYPE and q.object.value == VOID_DATASET_IRI
    }
    # nf:KGBuild is itself a void:Dataset; the publications collection is the
    # only table-level one, and mutations (no `collection:` block) adds none.
    assert collection_subjects == {KG_BUILD.value, NF + "ToolsCentralPublications"}


def test_collection_name_only_is_sufficient():
    """label/comment are optional -- a bare name still produces a usable node."""
    profile = {
        "version": "v",
        "tables": {"t": {"synapse_id": "syn1", "collection_name": "BareCollection"}},
    }
    facts = _quads_for(build_metadata_quads(profile, BUILD_TIME), NF + "BareCollection")
    assert (RDF_TYPE.value, VOID_DATASET_IRI) in facts
    assert (PROV_WAS_DERIVED_FROM.value, "https://www.synapse.org/Synapse:syn1") in facts


def test_source_version_stays_on_the_table_not_the_collection():
    """The version describes the Synapse table, so it is asserted there; the
    collection reaches it in one hop via prov:wasDerivedFrom."""
    quads = build_metadata_quads(COLLECTION_PROFILE, BUILD_TIME)
    table_facts = _quads_for(quads, "https://www.synapse.org/Synapse:syn26486839")
    collection_facts = _quads_for(quads, NF + "ToolsCentralPublications")

    assert ("http://purl.org/dc/terms/hasVersion", "9") in table_facts
    assert not any(p.endswith("hasVersion") for p, _ in collection_facts)
