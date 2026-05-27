"""Regression tests for replicated nf:name and rdfs:label values."""

import pytest
from rdflib.namespace import RDFS


CASES = [
    (
        "files.rml.ttl",
        {"data/csv/files_harmonized.csv": "test/files.csv"},
        "nf:File",
    ),
    (
        "resources.rml.ttl",
        {"data/csv/resources.csv": "test/resources.csv"},
        "nf:Tool",
    ),
    (
        "studies.rml.ttl",
        {"data/csv/studies_harmonized.csv": "test/studies.csv"},
        "biolink:Study",
    ),
    (
        "funders.rml.ttl",
        {"data/csv/funders.csv": "test/funders.csv"},
        "nf:Funder",
    ),
    (
        "investigators.rml.ttl",
        {"data/csv/investigators.csv": "test/investigators.csv"},
        "nf:Investigator",
    ),
    (
        "datasets.rml.ttl",
        {"data/csv/datasets.csv": "test/datasets.csv"},
        "biolink:Dataset",
    ),
    (
        "initiatives.rml.ttl",
        {"data/csv/initiatives.csv": "test/initiatives.csv"},
        "nf:Initiative",
    ),
    (
        "biobanks.rml.ttl",
        {"data/csv/biobanks.csv": "test/biobanks.csv"},
        "nf:Biobank",
    ),
]


@pytest.mark.parametrize(("mapping_file", "csv_replacements", "rdf_type"), CASES)
def test_name_is_replicated_to_rdfs_label(
    rml_runner,
    namespaces,
    mapping_file,
    csv_replacements,
    rdf_type,
):
    """Every nf:name emitted by these core mappings should also exist as rdfs:label."""
    graph = rml_runner(mapping_file=mapping_file, csv_replacements=csv_replacements)

    query = f"""
    SELECT ?entity ?name ?label
    WHERE {{
        ?entity a {rdf_type} ;
                nf:name ?name ;
                rdfs:label ?label .
    }}
    """
    rows = list(
        graph.query(
            query,
            initNs={"nf": namespaces["nf"], "biolink": namespaces["biolink"], "rdfs": RDFS},
        )
    )

    assert rows, f"No {rdf_type} entities with both nf:name and rdfs:label found in {mapping_file}"
    for row in rows:
        assert str(row.name) == str(row.label), (
            f"Expected nf:name and rdfs:label to match for {row.entity} in {mapping_file}, "
            f"got {row.name!r} vs {row.label!r}"
        )


@pytest.mark.parametrize(("mapping_file", "csv_replacements", "rdf_type"), CASES)
def test_no_name_without_rdfs_label(
    rml_runner,
    namespaces,
    mapping_file,
    csv_replacements,
    rdf_type,
):
    """No subject should emit nf:name from these mappings without the mirrored rdfs:label."""
    graph = rml_runner(mapping_file=mapping_file, csv_replacements=csv_replacements)

    query = f"""
    SELECT ?entity ?name
    WHERE {{
        ?entity a {rdf_type} ;
                nf:name ?name .
        FILTER NOT EXISTS {{ ?entity rdfs:label ?label }}
    }}
    """
    rows = list(
        graph.query(
            query,
            initNs={"nf": namespaces["nf"], "biolink": namespaces["biolink"], "rdfs": RDFS},
        )
    )

    assert not rows, f"Found nf:name without rdfs:label in {mapping_file}: {rows}"
