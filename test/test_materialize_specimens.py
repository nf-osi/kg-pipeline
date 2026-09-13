"""Tests for the specimen/individual layer materialized from the files table.

The behaviours pinned here are the three source-data quirks that would otherwise
corrupt the layer silently: pipe-delimited multi-value id cells, NA placeholder
spellings, and the same string being used as both a specimen and an individual id.
"""

import csv
import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.materialize_specimens import (
    individual_iri,
    materialize_specimens,
    specimen_iri,
    split_ids,
)

NF = Namespace("http://nf-osi.github.com/terms#")
BIOLINK = Namespace("https://w3id.org/biolink/vocab/")
SYN = "https://www.synapse.org/Synapse:"

FIELDS = ["id", "specimenID", "individualID"]


def write_files_csv(path: Path, rows: list[dict]) -> Path:
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build(tmp_path: Path, rows: list[dict]) -> tuple[Graph, object]:
    files_csv = write_files_csv(tmp_path / "files_harmonized.csv", rows)
    output = tmp_path / "specimens.ttl"
    index = materialize_specimens(files_csv, output)
    graph = Graph()
    graph.parse(output, format="turtle")
    return graph, index


def test_split_ids_handles_multivalue_and_na():
    # The portal packs several ids into one cell, separated by `|`.
    assert split_ids("N10|N5") == ["N10", "N5"]
    # NA spellings are placeholders, not identifiers -- same list the files RML uses.
    assert split_ids("na") == []
    assert split_ids("N5|NA|n/a|None|UNKNOWN|nan") == ["N5"]
    # Whitespace trimmed, duplicates collapsed, order preserved.
    assert split_ids(" N5 | N5 |N3") == ["N5", "N3"]
    assert split_ids("") == []
    assert split_ids(None) == []


def test_nodes_and_edges_for_a_simple_row(tmp_path):
    graph, index = build(tmp_path, [
        {"id": "syn1", "specimenID": "SPEC-1", "individualID": "IND-1"},
    ])
    specimen = specimen_iri("SPEC-1")
    individual = individual_iri("IND-1")

    assert (specimen, RDF.type, NF.Specimen) in graph
    assert (individual, RDF.type, NF.Individual) in graph
    assert (specimen, NF.fromIndividual, individual) in graph
    assert (individual, NF.hasSpecimen, specimen) in graph
    # File links go both ways so either direction resolves in one hop.
    assert (Namespace(SYN)["syn1"], NF.fromSpecimen, specimen) in graph
    assert (specimen, NF.hasFile, Namespace(SYN)["syn1"]) in graph
    # ...and the file->individual edge is asserted directly, not only via the specimen.
    assert (Namespace(SYN)["syn1"], NF.fromIndividual, individual) in graph
    assert index.rows == 1


def test_multivalue_cell_becomes_several_specimens(tmp_path):
    # Without splitting, this row would invent one specimen named "N10|N5".
    graph, index = build(tmp_path, [
        {"id": "syn1", "specimenID": "N10|N5", "individualID": "IND-1"},
    ])
    assert index.specimens == {"N10", "N5"}
    assert specimen_iri("N10|N5") not in set(graph.subjects(RDF.type, NF.Specimen))
    for sid in ("N10", "N5"):
        assert (specimen_iri(sid), NF.fromIndividual, individual_iri("IND-1")) in graph


def test_na_placeholders_produce_no_nodes(tmp_path):
    graph, index = build(tmp_path, [
        {"id": "syn1", "specimenID": "unknown", "individualID": "NA"},
        {"id": "syn2", "specimenID": "", "individualID": ""},
    ])
    assert index.specimens == set()
    assert index.individuals == set()
    assert len(graph) == 0
    assert index.rows_with_neither == 2


def test_same_string_as_specimen_and_individual_stays_distinct(tmp_path):
    # 2,188 real portal ids are used as both, so a shared IRI stem would merge a
    # specimen with an unrelated individual.
    graph, _ = build(tmp_path, [
        {"id": "syn1", "specimenID": "X1", "individualID": "X1"},
    ])
    assert specimen_iri("X1") != individual_iri("X1")
    assert (specimen_iri("X1"), RDF.type, NF.Specimen) in graph
    assert (individual_iri("X1"), RDF.type, NF.Individual) in graph
    assert (specimen_iri("X1"), RDF.type, NF.Individual) not in graph


def test_iri_unsafe_identifiers_are_percent_encoded(tmp_path):
    # A `#` is the dangerous one: the nf: namespace is itself a fragment, so an
    # unescaped `#` would truncate the IRI and silently merge nodes.
    graph, _ = build(tmp_path, [
        {"id": "syn1", "specimenID": "NCH1.5 biorep #2", "individualID": "cre- veh 52"},
    ])
    specimen = specimen_iri("NCH1.5 biorep #2")
    assert "%23" in str(specimen) and " " not in str(specimen)
    assert (specimen, RDF.type, NF.Specimen) in graph
    # The literal keeps the original, unescaped text so it is still searchable.
    assert (specimen, NF.specimenID, Literal("NCH1.5 biorep #2", datatype=None)) in graph or \
        any(str(o) == "NCH1.5 biorep #2" for o in graph.objects(specimen, NF.specimenID))


def test_specimen_shared_across_files_collects_all_of_them(tmp_path):
    graph, index = build(tmp_path, [
        {"id": "syn1", "specimenID": "SPEC-1", "individualID": "IND-1"},
        {"id": "syn2", "specimenID": "SPEC-1", "individualID": "IND-1"},
    ])
    specimen = specimen_iri("SPEC-1")
    files = set(graph.objects(specimen, NF.hasFile))
    assert len(files) == 2
    assert len(index.specimens) == 1


def test_specimen_with_no_individual_is_reported(tmp_path):
    _, index = build(tmp_path, [
        {"id": "syn1", "specimenID": "SPEC-1", "individualID": ""},
    ])
    assert index.orphan_specimens == {"SPEC-1"}


def test_missing_required_column_is_a_hard_error(tmp_path):
    path = tmp_path / "bad.csv"
    with open(path, "w", newline="") as handle:
        handle.write("id,specimenID\nsyn1,SPEC-1\n")
    try:
        materialize_specimens(path, tmp_path / "out.ttl")
    except SystemExit as exc:
        assert "individualID" in str(exc)
    else:
        raise AssertionError("a missing id column must fail loudly, not yield an empty graph")


def test_nodes_carry_both_the_nf_and_biolink_types(tmp_path):
    # The QLever index does no OWL reasoning, so rdfs:subClassOf in the ontology is not
    # enough: without the second type, a cross-portal `?s a biolink:MaterialSample`
    # query matches nothing.
    graph, _ = build(tmp_path, [{"id": "syn1", "specimenID": "S1", "individualID": "P1"}])

    specimen = specimen_iri("S1")
    assert (specimen, RDF.type, NF.Specimen) in graph
    assert (specimen, RDF.type, BIOLINK.MaterialSample) in graph

    individual = individual_iri("P1")
    assert (individual, RDF.type, NF.Individual) in graph
    assert (individual, RDF.type, BIOLINK.IndividualOrganism) in graph
    # NOT biolink:Case -- that class is a human organism in a patient role, and many
    # portal individualIDs name mice or zebrafish.
    assert (individual, RDF.type, BIOLINK.Case) not in graph
