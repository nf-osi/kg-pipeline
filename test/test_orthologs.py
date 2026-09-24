"""Ortholog crosswalk: classification, keying, and what it refuses to assert."""

import csv
import io
import sys
from pathlib import Path

import pytest
from rdflib import Graph, Namespace
from rdflib.namespace import RDF

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.fetch_orthologs import EXCLUDED, build_rows, curated_symbols, render
from scripts.materialize_orthologs import build_graph, read_orthologs

NF = Namespace("http://nf-osi.github.com/terms#")
BIOLINK = Namespace("https://w3id.org/biolink/vocab/")


def pair(human_id, human_symbol, model_id, model_symbol, species, match="10", of="10"):
    return {
        "Gene1ID": human_id, "Gene1Symbol": human_symbol,
        "Gene2ID": model_id, "Gene2Symbol": model_symbol,
        "Gene2SpeciesName": species,
        "AlgorithmsMatch": match, "OutOfAlgorithms": of,
        "IsBestScore": "Yes", "IsBestRevScore": "Yes",
    }


PAIRS = [
    pair("HGNC:7765", "NF1", "MGI:97306", "Nf1", "Mus musculus"),
    pair("HGNC:7765", "NF1", "RGD:3168", "Nf1", "Rattus norvegicus"),
    pair("HGNC:7765", "NF1", "ZFIN:ZDB-GENE-030131-4907", "nf1a", "Danio rerio", "5"),
    pair("HGNC:1787", "CDKN2A", "MGI:104738", "Cdkn2a", "Mus musculus", "1"),
]


def by_symbol(rows):
    out = {}
    for row in rows:
        out.setdefault(row["curated_symbol"], []).append(row)
    return out


def test_human_symbols_get_an_hgnc_iri_and_need_no_crosswalk():
    rows = by_symbol(build_rows(PAIRS, {"NF1": 78}, {}))
    (row,) = rows["NF1"]
    assert row["status"] == "human"
    assert row["human_iri"] == "https://identifiers.org/hgnc:7765"
    assert row["model_gene_id"] == ""


def test_species_disambiguates_a_symbol_shared_by_two_organisms():
    """`Nf1` is mouse MGI:97306 and rat RGD:3168; the models say which."""
    rows = by_symbol(build_rows(PAIRS, {"Nf1": 13}, {"Nf1": {"Mus musculus"}}))
    (row,) = rows["Nf1"]
    assert row["status"] == "ortholog"
    assert row["model_gene_id"] == "MGI:97306"
    assert row["human_iri"] == "https://identifiers.org/hgnc:7765"


def test_ambiguous_species_is_unresolved_rather_than_guessed():
    rows = by_symbol(
        build_rows(PAIRS, {"Nf1": 13}, {"Nf1": {"Mus musculus", "Rattus norvegicus"}})
    )
    (row,) = rows["Nf1"]
    assert row["status"] == "unresolved"
    assert row["model_gene_id"] == ""


def test_a_symbol_with_no_animal_model_link_is_unresolved():
    rows = by_symbol(build_rows(PAIRS, {"nf1a": 1}, {}))
    assert rows["nf1a"][0]["status"] == "unresolved"


def test_constructs_are_excluded_with_a_stated_reason():
    counts = {symbol: 1 for symbol in EXCLUDED}
    rows = by_symbol(build_rows(PAIRS, counts, {}))
    for symbol, reason in EXCLUDED.items():
        (row,) = rows[symbol]
        assert row["status"] == "excluded"
        assert reason in row["notes"]
        assert row["model_gene_id"] == ""


def test_exclusion_beats_a_matching_human_symbol():
    """GFAP is a real HGNC symbol, but in mutations.csv it names a Cre driver."""
    pairs = PAIRS + [pair("HGNC:4235", "GFAP", "MGI:95697", "Gfap", "Mus musculus")]
    rows = by_symbol(build_rows(pairs, {"GFAP": 1}, {"GFAP": {"Mus musculus"}}))
    assert rows["GFAP"][0]["status"] == "excluded"


def test_weak_support_is_carried_not_dropped():
    rows = by_symbol(build_rows(PAIRS, {"Cdkn2a": 1}, {"Cdkn2a": {"Mus musculus"}}))
    (row,) = rows["Cdkn2a"]
    assert row["status"] == "ortholog"
    assert row["support"] == "1/10"


def test_rendered_tsv_round_trips_through_the_materializer(tmp_path):
    rows = build_rows(
        PAIRS,
        {"Nf1": 13, "NF1": 78, "Cre": 1},
        {"Nf1": {"Mus musculus"}},
    )
    path = tmp_path / "orthologs.tsv"
    path.write_text(render(rows), encoding="utf-8")
    assert read_orthologs(path) == [
        {k: v for k, v in row.items()} for row in rows
    ]


def test_only_ortholog_rows_become_triples(tmp_path):
    rows = build_rows(
        PAIRS,
        {"Nf1": 13, "NF1": 78, "Cre": 1},
        {"Nf1": {"Mus musculus"}},
    )
    graph = build_graph(rows)
    mouse = "https://identifiers.org/MGI:97306"
    human = "https://identifiers.org/hgnc:7765"
    from rdflib import URIRef

    assert (URIRef(human), NF.hasOrtholog, URIRef(mouse)) in graph
    assert (URIRef(mouse), NF.orthologOf, URIRef(human)) in graph
    # The human side is only ever an object here: the gene node itself is the variant
    # layer's, and this file must not start redefining it.
    assert (URIRef(human), RDF.type, None) not in graph


def test_model_genes_are_not_typed_biolink_gene(tmp_path):
    """The whole point of nf:ModelOrganismGene: `?s a biolink:Gene` must stay human.

    QLever does no OWL reasoning, so the subclass axiom in the ontology documents the
    semantics while leaving every existing gene count untouched. If this ever emits
    biolink:Gene too, variant-gene-summary and variant-layer-summary start counting
    mouse genes.
    """
    rows = build_rows(PAIRS, {"Nf1": 13}, {"Nf1": {"Mus musculus"}})
    graph = build_graph(rows)
    assert (None, RDF.type, BIOLINK.Gene) not in graph
    assert (None, RDF.type, NF.ModelOrganismGene) in graph


def test_identifiers_org_prefix_case_is_preserved():
    """`https://identifiers.org/mgi:97306` 404s; the MGI prefix must stay upper-case."""
    rows = build_rows(PAIRS, {"Nf1": 13}, {"Nf1": {"Mus musculus"}})
    graph = build_graph(rows)
    subjects = {str(s) for s in graph.subjects(RDF.type, NF.ModelOrganismGene)}
    assert subjects == {"https://identifiers.org/MGI:97306"}


def test_curated_symbols_reads_species_off_the_animal_models(tmp_path):
    mutations = tmp_path / "mutations.csv"
    mutations.write_text(
        "mutationId,affectedGeneSymbol\nm1,Nf1\nm2,Nf1\nm3,NF1\n", encoding="utf-8"
    )
    links = tmp_path / "mutation_model.csv"
    links.write_text("mutationId,resourceId\nm1,r1\nm3,r2\n", encoding="utf-8")
    animals = tmp_path / "animal_models.csv"
    animals.write_text("resourceId,species\nr1,Mus musculus\n", encoding="utf-8")

    counts, species = curated_symbols(mutations, links, animals)
    assert counts == {"Nf1": 2, "NF1": 1}
    # r2 is not an animal model, so NF1 gets no species and stays uninferred.
    assert species == {"Nf1": {"Mus musculus"}}
