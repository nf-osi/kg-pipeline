"""Tests for CSV-side transforms and derived columns in prepare_portal_tables.py.

These cover logic that runs before RML and so is not exercised by the
mapping tests (which read fixture CSVs with derived columns already filled in).
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from prepare_portal_tables import apply_derived_columns, format_doi, format_orcid


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
