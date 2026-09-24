"""Canned query parameterization -- in particular that a numeric threshold cannot
carry SPARQL into the query the way a quoted string literal safely can."""

import re
import sys
from pathlib import Path

import pytest
from pyoxigraph import RdfFormat, Store

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.query_sparql import CANNED_QUERIES, DEFAULT_PREFIXES, build_canned_query

MODEL_COVERAGE = [
    "variant-model-match",
    "variant-model-gap",
    "variant-model-gap-genes",
    "model-without-patient-allele",
]


@pytest.mark.parametrize("name", MODEL_COVERAGE)
def test_model_coverage_queries_are_registered(name):
    assert name in CANNED_QUERIES
    assert CANNED_QUERIES[name]["help"]


#: A leftover `{placeholder}`. SPARQL is full of bare `{`, but never `{identifier}`.
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


@pytest.mark.parametrize("name", sorted(CANNED_QUERIES))
def test_every_canned_query_builds_with_its_defaults(name):
    """Catches a parameter added to a query's text but not to binds/numeric_binds --
    which otherwise fails only when someone runs it against a live endpoint."""
    spec = CANNED_QUERIES[name]
    class_name = "Study" if spec.get("needs_class_name") else None
    query, _ = build_canned_query(name, class_name, {})
    assert not PLACEHOLDER.search(query), PLACEHOLDER.search(query).group()


def test_numeric_bind_accepts_a_whole_number():
    query, _ = build_canned_query("variant-model-gap", None, {"minSpecimens": "7"})
    assert "COUNT(DISTINCT ?specimen) >= 7" in query


@pytest.mark.parametrize("value", ["0) || (1=1", "3; DROP", "-1", "2.5", "", "seven"])
def test_numeric_bind_rejects_anything_that_is_not_a_whole_number(value):
    """A numeric parameter lands outside a string literal, where quote-escaping buys
    nothing -- so the value itself has to be constrained."""
    with pytest.raises(ValueError, match="whole number"):
        build_canned_query("variant-model-gap", None, {"minSpecimens": value})


def test_string_bind_still_escapes_quotes():
    query, _ = build_canned_query("variant-model-match", None, {"gene": 'N"F1'})
    assert r'"N\"F1"' in query


def test_unknown_parameter_names_the_ones_that_exist():
    with pytest.raises(ValueError, match="limit, minSpecimens"):
        build_canned_query("variant-model-gap", None, {"nope": "1"})


def test_a_query_can_take_both_kinds_of_parameter():
    query, _ = build_canned_query(
        "variant-model-gap-genes", None, {"minSpecimens": "5", "limit": "3"}
    )
    assert "COUNT(DISTINCT ?specimen) >= 5" in query
    assert "LIMIT 3" in query


PREFIXES = "\n".join(f"PREFIX {key}: <{iri}>" for key, iri in DEFAULT_PREFIXES.items())


@pytest.fixture(params=["direct", "mutation_set"])
def coverage_graph(request):
    store = Store()
    link = ("nf:r nf:hasMutation nf:m ." if request.param == "direct" else
            "nf:r nf:hasNf1MutationSet nf:set . nf:set nf:hasMutation nf:m .")
    store.load(input=PREFIXES + "\n" + link + '''
        nf:g a biolink:Gene; nf:geneSymbol "NF1" .
        nf:m a nf:Mutation; nf:affectedGeneSymbol "NF1";
            nf:proteinVariation "p.A1T" .
        nf:r a nf:CellLine; nf:name "model" .
        nf:v nf:vrsId "ga4gh:VA.one" .
        nf:o1 a nf:VariantObservation; nf:affectedGene nf:g; nf:hgvsP "p.A1T";
            nf:observesVariant nf:v; nf:hasConsequence obo:SO_0001583;
            nf:fromSpecimen nf:s1; nf:fromVariantDataset nf:d .
    ''', format=RdfFormat.TURTLE)
    return store


def coverage_query(store, name, **binds):
    query, _ = build_canned_query(name, None, binds)
    result = store.query(PREFIXES + "\n" + query)
    return [{variable.value: value.value for variable, value in zip(result.variables, row)
             if value is not None} for row in result]


def add_observation(store, *, variant="v", protein="p.A2T"):
    store.load(input=PREFIXES + f'''
        nf:o2 a nf:VariantObservation; nf:affectedGene nf:g; nf:hgvsP "{protein}";
            nf:observesVariant nf:{variant}; nf:hasConsequence obo:SO_0001583;
            nf:fromSpecimen nf:s2; nf:fromVariantDataset nf:d2 .
    ''', format=RdfFormat.TURTLE)


def test_protein_match_excludes_whole_allele_despite_other_transcript(coverage_graph):
    add_observation(coverage_graph)
    matches = coverage_query(coverage_graph, "variant-model-match")
    assert {(r["vrsId"], r["tier"]) for r in matches} == {
        ("ga4gh:VA.one", "2 protein string")
    }
    assert coverage_query(coverage_graph, "variant-model-gap", minSpecimens="1") == []


def test_tier_one_does_not_hide_other_alleles_matching_protein(coverage_graph):
    coverage_graph.load(input=PREFIXES + '''
        nf:m nf:mutationVrsId "ga4gh:VA.one" .
        nf:v2 nf:vrsId "ga4gh:VA.two" .
    ''', format=RdfFormat.TURTLE)
    add_observation(coverage_graph, variant="v2", protein="p.A1T")
    matches = coverage_query(coverage_graph, "variant-model-match")
    assert len(matches) == 2
    assert {(r["vrsId"], r["tier"]) for r in matches} == {
        ("ga4gh:VA.one", "1 allele identity"),
        ("ga4gh:VA.two", "2 protein string"),
    }
    assert coverage_query(coverage_graph, "variant-model-gap", minSpecimens="1") == []


def test_uncovered_allele_keeps_all_specimens_and_annotations(coverage_graph):
    # The same protein string in another gene must not count as coverage.
    coverage_graph.update(PREFIXES + '''
        DELETE DATA { nf:m nf:affectedGeneSymbol "NF1" };
        INSERT DATA { nf:m nf:affectedGeneSymbol "TP53" }
    ''')
    add_observation(coverage_graph)
    assert coverage_query(coverage_graph, "variant-model-match") == []
    (gap,) = coverage_query(coverage_graph, "variant-model-gap", minSpecimens="2")
    assert gap["vrsId"] == "ga4gh:VA.one"
    assert gap["specimens"] == "2"
    assert gap["cohorts"] == "2"
    assert set(gap["changes"].split("/")) == {"p.A1T", "p.A2T"}
    assert coverage_query(coverage_graph, "variant-model-gap", minSpecimens="3") == []
