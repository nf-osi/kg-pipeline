"""Tests for the compoundChemblID -> ChEMBL IRI step in harmonize_files.py.

The resolution itself happens upstream, in map-compound-chembl in nf-osi/jobs, and
arrives as a CURIE (`chembl:CHEMBL504`). All this repo does is append it to the
identifiers.org base, so what is worth testing is the part that can silently produce a
wrong answer: minting an IRI for something that is not a CURIE.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.harmonize_files import chembl_iris

CH = "https://identifiers.org/chembl:"


class TestChemblIris:
    def test_a_single_curie_becomes_one_iri(self):
        assert chembl_iris("chembl:CHEMBL504") == ([CH + "CHEMBL504"], [])

    def test_a_combination_arm_becomes_one_iri_per_drug(self):
        """Pipe-joined because a file can carry several molecules: a combination arm
        is several drugs, and the two source fields resolve independently."""
        iris, malformed = chembl_iris("chembl:CHEMBL2103875|chembl:CHEMBL3545110")
        assert iris == [CH + "CHEMBL2103875", CH + "CHEMBL3545110"]
        assert malformed == []

    def test_the_authority_matches_the_rest_of_the_graph(self):
        """identifiers.org, the same spelling materialize_orthologs.py uses for HGNC
        and MGI, so every external identifier in this graph is one kind of IRI."""
        (iri,), _ = chembl_iris("chembl:CHEMBL504")
        assert iri == "https://identifiers.org/chembl:CHEMBL504"

    def test_the_curie_is_appended_not_reformatted(self):
        """The annotation is already a CURIE, so the IRI is the base plus the value
        verbatim. Rebuilding it from parts is what would let the prefix's case drift."""
        value = "chembl:CHEMBL504"
        (iri,), _ = chembl_iris(value)
        assert iri == "https://identifiers.org/" + value

    @pytest.mark.parametrize("raw", ["", "   ", "|", " | "])
    def test_no_value_produces_no_iri(self, raw):
        """An empty column is the expected state until the annotation exists on
        portal files, and it must produce no triple rather than an empty IRI."""
        assert chembl_iris(raw) == ([], [])

    def test_whitespace_around_a_curie_is_tolerated(self):
        assert chembl_iris(" chembl:CHEMBL504 | chembl:CHEMBL521686 ") == (
            [CH + "CHEMBL504", CH + "CHEMBL521686"], [])

    @pytest.mark.parametrize("raw", [
        "CHEMBL504",                  # bare accession, missing the prefix
        "CHEMBL:CHEMBL504",           # prefix case is not what identifiers.org serves
        "chembl:chembl504",
        "chembl:CHEMB504",            # typo
        "chembl:CHEMBL",              # no digits
        "chembl:CHEMBL504a",          # trailing junk
        "chembl:chembl:CHEMBL504",    # double-prefixed
        "https://identifiers.org/chembl:CHEMBL504",   # already an IRI
        "Trametinib",                 # a label that was never resolved
        "chembl:CHEMBL504,chembl:CHEMBL1",  # comma, not the portal's separator
    ])
    def test_a_non_curie_is_reported_not_turned_into_an_iri(self, raw):
        """The failure this guards is silent: appending anything at all yields an IRI
        that looks resolvable, and a wrong molecule IRI is a wrong drug rather than a
        near miss."""
        iris, malformed = chembl_iris(raw)
        assert iris == []
        assert malformed == [raw]

    def test_one_bad_value_does_not_discard_the_good_ones(self):
        """A file whose annotation is half wrong still has the molecules it got
        right; dropping the row would lose them to fix one typo."""
        iris, malformed = chembl_iris(
            "chembl:CHEMBL504|chembl:CHEMB504|chembl:CHEMBL521686")
        assert iris == [CH + "CHEMBL504", CH + "CHEMBL521686"]
        assert malformed == ["chembl:CHEMB504"]
