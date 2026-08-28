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
    build_legacy_id_crosswalk,
    format_doi,
    format_orcid,
    format_synapse_id,
    translate_legacy_resource_ids,
)


class TestPeopleOrcidPartition:
    """The people source mixes Synapse accounts with publication-derived people
    who have an ORCID but no ownerID. nonSynapseOrcid keys the person node for
    the latter; account-holders are keyed by Profile IRI instead, so each row
    yields exactly one biolink:Person."""

    def _derive(self, rows):
        return apply_derived_columns("people", pd.DataFrame(rows), {})

    def test_account_holder_gets_no_orcid_keyed_node(self):
        out = self._derive([
            {"ownerID": "3324237", "orcid": "0000-0001-1111-1111", "onProject": ""},
        ]).reset_index(drop=True)
        assert out.loc[0, "nonSynapseOrcid"] == ""

    def test_account_less_person_is_keyed_by_orcid(self):
        out = self._derive([
            {"ownerID": "", "orcid": "0000-0002-2222-2222", "onProject": ""},
        ]).reset_index(drop=True)
        assert out.loc[0, "nonSynapseOrcid"] == "0000-0002-2222-2222"

    def test_no_synapse_user_orcid_column_is_produced(self):
        """It existed only to give `rdf:type nf:SynapseUser` something to
        null-propagate on. nf:hasSynapseProfile has a templated object, so the
        raw columns suffice -- see people.rml.ttl."""
        out = self._derive([
            {"ownerID": "3324237", "orcid": "0000-0001-1111-1111", "onProject": ""},
        ])
        assert "synapseUserOrcid" not in out.columns

    def test_orcid_claimed_by_an_account_row_never_mints_a_second_person(self):
        """The registry holds some researchers twice -- once as a Synapse
        account, once publication-derived. Judging rows independently would give
        that person both a Profile-keyed and an ORCID-keyed biolink:Person node,
        double-counting them."""
        out = self._derive([
            {"ownerID": "3572182", "orcid": "0009-0005-7564-346X", "onProject": "syn1"},
            {"ownerID": "", "orcid": "0009-0005-7564-346X", "onProject": ""},
        ]).reset_index(drop=True)
        assert out.loc[0, "nonSynapseOrcid"] == ""
        assert out.loc[1, "nonSynapseOrcid"] == "", \
            "duplicate publication-derived row must not become a second person"

    def test_disjoint_identifier_duplicate_is_not_caught(self):
        """KNOWN LIMIT, documented in apply_derived_columns: an account row with
        no ORCID plus a publication-derived row with one cannot be linked from
        this table alone, so both survive. This was Margaret Wallace, fixed
        upstream at source_version 10 rather than in code."""
        out = self._derive([
            {"ownerID": "3334263", "orcid": "", "onProject": "syn1"},
            {"ownerID": "", "orcid": "0000-0002-5202-8895", "onProject": ""},
        ]).reset_index(drop=True)
        assert out.loc[1, "nonSynapseOrcid"] == "0000-0002-5202-8895"

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

    def test_row_without_orcid_or_project_is_dropped(self):
        out = self._derive([
            {"ownerID": "3324237", "orcid": "", "onProject": ""},
            {"ownerID": "3399999", "orcid": "", "onProject": "syn1"},
        ])
        assert list(out["ownerID"]) == ["3399999"]

    def test_existing_column_is_not_recomputed(self):
        """Re-processing from cache must not clobber an already-derived column."""
        df = pd.DataFrame([{
            "ownerID": "",
            "orcid": "0000-0001-1111-1111",
            "onProject": "",
            "nonSynapseOrcid": "preserved",
        }])
        out = apply_derived_columns("people", df, {}).reset_index(drop=True)
        assert out.loc[0, "nonSynapseOrcid"] == "preserved"


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


class TestLegacyResourceIdTranslation:
    """Workaround for an upstream bug: syn26486834 renamed its
    animalModelId/cellLineId columns to `resourceId` without migrating the
    values. See docs/upstream-mutation-resourceid-bug.md.

    Delete this class together with the workaround once upstream is fixed.
    """

    @staticmethod
    def _crosswalk_frame():
        return pd.DataFrame([
            {"resourceId": "res-1", "cellLineId": "cl-1", "animalModelId": ""},
            {"resourceId": "res-2", "cellLineId": "", "animalModelId": "am-2"},
            {"resourceId": "res-3", "cellLineId": "", "animalModelId": ""},
        ])

    def test_crosswalk_maps_every_legacy_id(self):
        crosswalk = build_legacy_id_crosswalk(self._crosswalk_frame())
        assert crosswalk == {"cl-1": "res-1", "am-2": "res-2"}

    def test_crosswalk_skips_rows_without_legacy_ids(self):
        """res-3 has no legacy id, so it contributes no entry -- and must not
        map an empty string to itself, which would translate blank cells."""
        crosswalk = build_legacy_id_crosswalk(self._crosswalk_frame())
        assert "" not in crosswalk
        assert "res-3" not in crosswalk

    def test_translates_legacy_values(self):
        df = pd.DataFrame({"mutationId": ["m1", "m2"], "resourceId": ["cl-1", "am-2"]})
        out, translated, untouched = translate_legacy_resource_ids(
            df, {"cl-1": "res-1", "am-2": "res-2"})
        assert list(out["resourceId"]) == ["res-1", "res-2"]
        assert (translated, untouched) == (2, 0)

    def test_leaves_real_resource_ids_alone(self):
        """A value already absent from the crosswalk is either a genuine
        resourceId or unresolvable; either way it must pass through unchanged."""
        df = pd.DataFrame({"mutationId": ["m1"], "resourceId": ["res-9"]})
        out, translated, untouched = translate_legacy_resource_ids(df, {"cl-1": "res-1"})
        assert list(out["resourceId"]) == ["res-9"]
        assert (translated, untouched) == (0, 1)

    def test_blank_values_are_not_counted(self):
        df = pd.DataFrame({"mutationId": ["m1"], "resourceId": [""]})
        out, translated, untouched = translate_legacy_resource_ids(df, {"cl-1": "res-1"})
        assert (translated, untouched) == (0, 0)

    def test_does_not_mutate_input_frame(self):
        df = pd.DataFrame({"mutationId": ["m1"], "resourceId": ["cl-1"]})
        translate_legacy_resource_ids(df, {"cl-1": "res-1"})
        assert list(df["resourceId"]) == ["cl-1"]

    def test_missing_column_is_a_noop(self):
        df = pd.DataFrame({"mutationId": ["m1"]})
        out, translated, untouched = translate_legacy_resource_ids(df, {"cl-1": "res-1"})
        assert (translated, untouched) == (0, 0)
        assert list(out.columns) == ["mutationId"]

    def test_apply_derived_columns_uses_injected_crosswalk(self):
        """apply_derived_columns must accept a crosswalk via processed_tables so
        it never reaches out to Synapse during tests."""
        df = pd.DataFrame({"mutationId": ["m1"], "resourceId": ["cl-1"]})
        out = apply_derived_columns(
            "mutation_model", df,
            {"_legacy_resource_crosswalk": {"cl-1": "res-1"}},
        )
        assert list(out["resourceId"]) == ["res-1"]


# Run with: pytest test/test_prepare_portal_tables.py -v
