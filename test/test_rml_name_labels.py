"""Regression tests for replicated name and rdfs:label values.

Person nodes (biolink:Person, nf:Investigator) use foaf:name; every other
entity type uses nf:name. Each case carries its own name predicate so the
mirror-to-rdfs:label invariant is checked against the right one.
"""

import pytest
from rdflib import Namespace
from rdflib.namespace import RDFS

FOAF = Namespace("http://xmlns.com/foaf/0.1/")


CASES = [
    (
        "files.rml.ttl",
        {"data/csv/files_harmonized.csv": "test/files.csv"},
        "nf:File",
        "nf:name",
    ),
    (
        "resources.rml.ttl",
        {"data/csv/resources.csv": "test/resources.csv"},
        "nf:Tool",
        "nf:name",
    ),
    (
        "studies.rml.ttl",
        {"data/csv/studies_harmonized.csv": "test/studies.csv"},
        "biolink:Study",
        "nf:name",
    ),
    (
        "funders.rml.ttl",
        {"data/csv/funders.csv": "test/funders.csv"},
        "nf:Funder",
        "nf:name",
    ),
    (
        "investigators.rml.ttl",
        {"data/csv/investigators.csv": "test/investigators.csv"},
        "nf:Investigator",
        "foaf:name",
    ),
    (
        "datasets.rml.ttl",
        {"data/csv/datasets.csv": "test/datasets.csv"},
        "biolink:Dataset",
        "nf:name",
    ),
    (
        "initiatives.rml.ttl",
        {"data/csv/initiatives.csv": "test/initiatives.csv"},
        "nf:Initiative",
        "nf:name",
    ),
    (
        "biobanks.rml.ttl",
        {"data/csv/biobanks.csv": "test/biobanks.csv"},
        "nf:Biobank",
        "nf:name",
    ),
    (
        "people.rml.ttl",
        {"data/csv/people.csv": "test/people.csv"},
        "biolink:Person",
        "foaf:name",
    ),
]


@pytest.mark.parametrize(("mapping_file", "csv_replacements", "rdf_type", "name_pred"), CASES)
def test_name_is_replicated_to_rdfs_label(
    rml_runner,
    namespaces,
    mapping_file,
    csv_replacements,
    rdf_type,
    name_pred,
):
    """Every name emitted by these core mappings should also exist as rdfs:label."""
    graph = rml_runner(mapping_file=mapping_file, csv_replacements=csv_replacements)

    query = f"""
    SELECT ?entity ?name ?label
    WHERE {{
        ?entity a {rdf_type} ;
                {name_pred} ?name ;
                rdfs:label ?label .
    }}
    """
    rows = list(
        graph.query(
            query,
            initNs={"nf": namespaces["nf"], "biolink": namespaces["biolink"],
                    "foaf": FOAF, "rdfs": RDFS},
        )
    )

    assert rows, f"No {rdf_type} entities with both {name_pred} and rdfs:label found in {mapping_file}"
    for row in rows:
        assert str(row.name) == str(row.label), (
            f"Expected {name_pred} and rdfs:label to match for {row.entity} in {mapping_file}, "
            f"got {row.name!r} vs {row.label!r}"
        )


@pytest.mark.parametrize(("mapping_file", "csv_replacements", "rdf_type", "name_pred"), CASES)
def test_no_name_without_rdfs_label(
    rml_runner,
    namespaces,
    mapping_file,
    csv_replacements,
    rdf_type,
    name_pred,
):
    """No subject should emit a name from these mappings without the mirrored rdfs:label."""
    graph = rml_runner(mapping_file=mapping_file, csv_replacements=csv_replacements)

    query = f"""
    SELECT ?entity ?name
    WHERE {{
        ?entity a {rdf_type} ;
                {name_pred} ?name .
        FILTER NOT EXISTS {{ ?entity rdfs:label ?label }}
    }}
    """
    rows = list(
        graph.query(
            query,
            initNs={"nf": namespaces["nf"], "biolink": namespaces["biolink"],
                    "foaf": FOAF, "rdfs": RDFS},
        )
    )

    assert not rows, f"Found {name_pred} without rdfs:label in {mapping_file}: {rows}"
