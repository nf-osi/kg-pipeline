"""Canned query parameterization -- in particular that a numeric threshold cannot
carry SPARQL into the query the way a quoted string literal safely can."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.query_sparql import CANNED_QUERIES, build_canned_query

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
