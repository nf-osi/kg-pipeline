"""Tests for CSV-side transforms and derived columns in prepare_portal_tables.py.

These cover logic that runs before RML and so is not exercised by the
mapping tests (which read fixture CSVs with derived columns already filled in).
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from prepare_portal_tables import (
    apply_derived_columns,
    format_doi,
    format_orcid,
    format_synapse_id,
)


class TestInvestigatorSynapseUserOrcid:
    """The synapseUserOrcid derived column drives nf:SynapseUser typing."""

    def _derive(self, rows):
        df = pd.DataFrame(rows)
        return apply_derived_columns("investigators", df, {})

    def test_populated_only_when_both_ids_present(self):
        out = self._derive([
            {"orcid": "0000-0001-1111-1111", "investigatorSynapseId": "3334263"},
            {"orcid": "0000-0002-2222-2222", "investigatorSynapseId": ""},
        ])
        assert out.loc[0, "synapseUserOrcid"] == "0000-0001-1111-1111"
        assert out.loc[1, "synapseUserOrcid"] == ""

    def test_blank_orcid_yields_blank(self):
        """No ORCID means nothing to type, even with a Synapse profile."""
        out = self._derive([{"orcid": "", "investigatorSynapseId": "3334263"}])
        assert out.loc[0, "synapseUserOrcid"] == ""

    def test_whitespace_only_profile_treated_as_absent(self):
        out = self._derive([{"orcid": "0000-0001-1111-1111", "investigatorSynapseId": "   "}])
        assert out.loc[0, "synapseUserOrcid"] == ""

    def test_missing_profile_column_does_not_raise(self):
        """Defensive: a source missing the column entirely should still process."""
        out = self._derive([{"orcid": "0000-0001-1111-1111"}])
        assert out.loc[0, "synapseUserOrcid"] == ""

    def test_existing_column_is_not_recomputed(self):
        """Re-processing from cache must not clobber an already-derived column."""
        df = pd.DataFrame([{
            "orcid": "0000-0001-1111-1111",
            "investigatorSynapseId": "3334263",
            "synapseUserOrcid": "preserved",
        }])
        out = apply_derived_columns("investigators", df, {})
        assert out.loc[0, "synapseUserOrcid"] == "preserved"


class TestPeopleOrcidPartition:
    """The people source mixes Synapse accounts with publication-derived people
    who have an ORCID but no ownerID. synapseUserOrcid / nonSynapseOrcid split
    the ORCID between them so each row yields exactly one person node, and so
    that account-less people are never typed nf:SynapseUser."""

    def _derive(self, rows):
        return apply_derived_columns("people", pd.DataFrame(rows), {})

    def test_account_holder_gets_synapse_user_orcid_only(self):
        out = self._derive([
            {"ownerID": "3324237", "orcid": "0000-0001-1111-1111", "onProject": ""},
        ]).reset_index(drop=True)
        assert out.loc[0, "synapseUserOrcid"] == "0000-0001-1111-1111"
        assert out.loc[0, "nonSynapseOrcid"] == ""

    def test_account_less_person_gets_non_synapse_orcid_only(self):
        out = self._derive([
            {"ownerID": "", "orcid": "0000-0002-2222-2222", "onProject": ""},
        ]).reset_index(drop=True)
        assert out.loc[0, "synapseUserOrcid"] == ""
        assert out.loc[0, "nonSynapseOrcid"] == "0000-0002-2222-2222"

    def test_columns_are_mutually_exclusive(self):
        out = self._derive([
            {"ownerID": "3324237", "orcid": "0000-0001-1111-1111", "onProject": ""},
            {"ownerID": None, "orcid": "0000-0002-2222-2222", "onProject": ""},
            {"ownerID": "3399999", "orcid": "", "onProject": "syn1"},
        ])
        both = out[(out["synapseUserOrcid"] != "") & (out["nonSynapseOrcid"] != "")]
        assert both.empty, f"A row must not populate both columns: {both}"

    def test_orcid_claimed_by_an_account_row_never_mints_a_second_person(self):
        """The registry holds some researchers twice -- once as a Synapse
        account, once publication-derived. Judging rows independently would give
        that person both a Profile-keyed and an ORCID-keyed biolink:Person node,
        double-counting them and typing one ORCID as a Synapse user and an
        account-less person at once."""
        out = self._derive([
            {"ownerID": "3572182", "orcid": "0009-0005-7564-346X", "onProject": "syn1"},
            {"ownerID": "", "orcid": "0009-0005-7564-346X", "onProject": ""},
        ]).reset_index(drop=True)
        assert out.loc[0, "synapseUserOrcid"] == "0009-0005-7564-346X"
        assert out.loc[1, "nonSynapseOrcid"] == "", \
            "duplicate publication-derived row must not become a second person"

    def test_claim_matching_ignores_orcid_prefix_formatting(self):
        """The source writes ORCIDs as 'orcid:<id>'; the two rows for one person
        must still be recognised as the same ORCID."""
        out = self._derive([
            {"ownerID": "3572182", "orcid": "orcid:0009-0005-7564-346X", "onProject": ""},
            {"ownerID": "", "orcid": "0009-0005-7564-346X", "onProject": ""},
        ]).reset_index(drop=True)
        assert out.loc[1, "nonSynapseOrcid"] == ""

    def test_unclaimed_orcid_still_mints_a_person(self):
        """The de-duplication must not swallow genuinely account-less people."""
        out = self._derive([
            {"ownerID": "3572182", "orcid": "0000-0001-1111-1111", "onProject": ""},
            {"ownerID": "", "orcid": "0000-0002-2222-2222", "onProject": ""},
        ]).reset_index(drop=True)
        assert out.loc[1, "nonSynapseOrcid"] == "0000-0002-2222-2222"

    def test_missing_owner_id_is_null_not_nan_string(self):
        """A NaN ownerID must not stringify into the Profile IRI template."""
        out = self._derive([
            {"ownerID": float("nan"), "orcid": "0000-0002-2222-2222", "onProject": ""},
        ]).reset_index(drop=True)
        assert out.loc[0, "nonSynapseOrcid"] == "0000-0002-2222-2222"
        assert out.loc[0, "synapseUserOrcid"] == ""

    def test_row_without_orcid_or_project_is_dropped(self):
        out = self._derive([
            {"ownerID": "3324237", "orcid": "", "onProject": ""},
            {"ownerID": "3399999", "orcid": "", "onProject": "syn1"},
        ])
        assert list(out["ownerID"]) == ["3399999"]

    def test_existing_columns_are_not_recomputed(self):
        """Re-processing from cache must not clobber already-derived columns."""
        df = pd.DataFrame([{
            "ownerID": "3324237",
            "orcid": "0000-0001-1111-1111",
            "onProject": "",
            "synapseUserOrcid": "preserved",
            "nonSynapseOrcid": "",
        }])
        out = apply_derived_columns("people", df, {}).reset_index(drop=True)
        assert out.loc[0, "synapseUserOrcid"] == "preserved"


class TestPublicationAuthorOrcidExplode:
    """(doi, orcid) pairs are exploded out of the people table's per-person
    `publications` DOI list, because an RML subject map cannot be multi-valued."""

    def _derive(self, rows):
        out = apply_derived_columns("publication_author_orcids", pd.DataFrame(rows), {})
        return out.reset_index(drop=True)

    def test_list_is_exploded_to_one_row_per_pair(self):
        out = self._derive([
            {"orcid": "0000-0001-1111-1111", "publications": ["10.1/a", "10.1/b"]},
        ])
        assert list(out["doi"]) == ["10.1/a", "10.1/b"]
        assert set(out["orcid"]) == {"0000-0001-1111-1111"}

    def test_tuple_from_synapse_list_column_is_handled(self):
        """normalize_fetched_df turns list cells into tuples before this runs."""
        out = self._derive([
            {"orcid": "0000-0001-1111-1111", "publications": ("10.1/a", "10.1/b")},
        ])
        assert list(out["doi"]) == ["10.1/a", "10.1/b"]

    def test_repr_string_from_cached_csv_is_handled(self):
        """--from-cache re-reads the raw CSV, where the list is a repr string."""
        out = self._derive([
            {"orcid": "0000-0001-1111-1111", "publications": "['10.1/a', '10.1/b']"},
        ])
        assert list(out["doi"]) == ["10.1/a", "10.1/b"]

    def test_person_without_orcid_contributes_no_pair(self):
        out = self._derive([
            {"orcid": "", "publications": ["10.1/a"]},
            {"orcid": "0000-0001-1111-1111", "publications": ["10.1/b"]},
        ])
        assert list(out["doi"]) == ["10.1/b"]

    def test_person_without_publications_contributes_no_pair(self):
        out = self._derive([
            {"orcid": "0000-0001-1111-1111", "publications": []},
            {"orcid": "0000-0002-2222-2222", "publications": ["10.1/b"]},
        ])
        assert list(out["doi"]) == ["10.1/b"]

    def test_duplicate_pairs_are_collapsed(self):
        """The same DOI can repeat within a list and across duplicate profiles."""
        out = self._derive([
            {"orcid": "0000-0001-1111-1111", "publications": ["10.1/a", "10.1/a"]},
            {"orcid": "0000-0001-1111-1111", "publications": ["10.1/a"]},
        ])
        assert len(out) == 1

    def test_same_doi_keeps_distinct_authors(self):
        """Co-authorship: one paper legitimately maps to many ORCIDs."""
        out = self._derive([
            {"orcid": "0000-0001-1111-1111", "publications": ["10.1/a"]},
            {"orcid": "0000-0002-2222-2222", "publications": ["10.1/a"]},
        ])
        assert len(out) == 2
        assert set(out["orcid"]) == {"0000-0001-1111-1111", "0000-0002-2222-2222"}

    def test_already_exploded_frame_is_left_alone(self):
        """--from-cache path: the raw CSV may already hold (doi, orcid) rows."""
        df = pd.DataFrame([{"doi": "10.1/a", "orcid": "0000-0001-1111-1111"}])
        out = apply_derived_columns("publication_author_orcids", df, {})
        assert list(out["doi"]) == ["10.1/a"]


class TestFormatSynapseId:
    def test_strips_materialized_view_prefix(self):
        assert format_synapse_id("syn:syn2343195") == "syn2343195"

    def test_reintegerizes_float_user_id(self):
        """A USERID column with any null becomes float64 in pandas, so the id
        arrives as '3324237.0' and would be baked into a dead Profile IRI."""
        assert format_synapse_id(3324237.0) == "3324237"
        assert format_synapse_id("3324237.0") == "3324237"

    def test_leaves_non_integral_looking_values_alone(self):
        assert format_synapse_id("syn123") == "syn123"
        assert format_synapse_id("3324237") == "3324237"

    def test_empty(self):
        assert format_synapse_id(None) == ""


class TestFormatOrcid:
    def test_strips_orcid_prefix(self):
        assert format_orcid("orcid:0000-0002-3127-5045") == "0000-0002-3127-5045"

    def test_passes_through_bare_id(self):
        assert format_orcid("0000-0002-3127-5045") == "0000-0002-3127-5045"

    def test_empty(self):
        assert format_orcid(None) == ""


class TestFormatDoi:
    """DOIs go straight into IRI templates, so IRI-unsafe chars must be encoded
    while path separators and sub-delims common in real DOIs are preserved."""

    @pytest.mark.parametrize("prefix", [
        "https://www.doi.org/", "https://doi.org/", "http://doi.org/",
    ])
    def test_strips_url_prefixes(self, prefix):
        assert format_doi(f"{prefix}10.1038/test001") == "10.1038/test001"

    def test_preserves_slash_and_subdelims(self):
        # Parentheses and semicolons are legal in IRIs and common in older DOIs
        assert format_doi("10.1016/0006-291x(85)91841-8") == "10.1016/0006-291x(85)91841-8"

    def test_encodes_square_brackets(self):
        # BioOne-style DOI; '[' and ']' are not legal unescaped in a Turtle IRIREF
        assert format_doi("10.1667/0033-7587(2000)153[0062:forimi]2.0.co;2") == \
            "10.1667/0033-7587(2000)153%5B0062:forimi%5D2.0.co;2"

    def test_encodes_angle_brackets(self):
        assert format_doi("10.1002/1097-0142(19910201)67:3<619::aid-cncr2820670317>3.0.co;2-y") == \
            "10.1002/1097-0142(19910201)67:3%3C619::aid-cncr2820670317%3E3.0.co;2-y"

    def test_does_not_double_encode(self):
        """Source data sometimes already contains percent-encoded DOIs."""
        already = "10.1002/1097-0215(200002)9999:9999%3C::AID-IJC1049%3E3.0.CO;2-C"
        assert format_doi(already) == already.lower().replace("%3c", "%3C").replace("%3e", "%3E")

    def test_lowercases_for_case_insensitive_matching(self):
        """DOIs are case-insensitive, and DOI IRIs are the cross-source join
        key, so capitalisation must not create two nodes for one paper."""
        assert format_doi("10.1158/1078-0432.CCR-22-2854") == "10.1158/1078-0432.ccr-22-2854"
        assert format_doi("https://doi.org/10.1158/1078-0432.ccr-22-2854") == \
            "10.1158/1078-0432.ccr-22-2854"

    def test_raw_and_preencoded_forms_converge(self):
        """A DOI supplied raw and the same DOI supplied already percent-encoded
        must normalise identically -- otherwise lowercasing would leave escape
        sequences in different cases and reintroduce the split it prevents."""
        raw = "10.1002/1097-0142(19910201)67:3<619::AID-CNCR>3.0.CO;2-Y"
        enc = "10.1002/1097-0142(19910201)67:3%3C619::aid-cncr%3E3.0.co;2-y"
        assert format_doi(raw) == format_doi(enc)

    def test_empty(self):
        assert format_doi(None) == ""


# Run with: pytest test/test_prepare_portal_tables.py -v
