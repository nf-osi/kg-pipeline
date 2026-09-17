"""Tests for the cBioPortal sample -> portal specimen crosswalk.

The crosswalk is a checked-in artifact that gets regenerated, so the behaviours worth
pinning are the ones a rerun could silently destroy: hand-authored corrections must
survive, and a barcode that does not resolve must be recorded as unmatched rather than
dropped or guessed at.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.map_cbioportal_samples import (
    build_rows,
    load_crosswalk,
    load_existing,
    strip_last_segment,
    write_crosswalk,
)

STUDY = "nst_nfosi_ntap"
SCHW = "schw_ctf_synodos_2025"
NFIB = "nfib_ctf_biobank_2025"
LGG = "lgg_ctf_synodos_2025"


def test_strip_last_segment_is_the_join_rule():
    # Verbatim barcodes match nothing (0/80); dropping the last segment matches 71/80.
    assert strip_last_segment("JH-2-001-8A1B1-A") == "JH-2-001-8A1B1"
    # Three real barcodes end in something other than -A, which is why the rule is
    # "minus the last segment" rather than "minus a trailing -A".
    assert strip_last_segment("JH-2-111-GAF53-A1011") == "JH-2-111-GAF53"
    assert strip_last_segment("NOSEGMENTS") == "NOSEGMENTS"


def test_resolved_row_carries_the_specimens_own_individual():
    rows = build_rows(
        STUDY,
        ["JH-2-001-8A1B1-A"],
        specimens={"JH-2-001-8A1B1"},
        specimen_individuals={"JH-2-001-8A1B1": {"JH-2-001"}},
        existing={},
    )
    assert rows[0]["specimen_id"] == "JH-2-001-8A1B1"
    # From the specimen's own fromIndividual link, not parsed out of the barcode.
    assert rows[0]["individual_id"] == "JH-2-001"
    assert rows[0]["method"] == "strip_last_segment"


def test_ambiguous_individual_is_left_blank_not_guessed():
    rows = build_rows(
        STUDY,
        ["JH-2-001-8A1B1-A"],
        specimens={"JH-2-001-8A1B1"},
        specimen_individuals={"JH-2-001-8A1B1": {"JH-2-001", "JH-2-999"}},
        existing={},
    )
    assert rows[0]["individual_id"] == ""
    assert "2 individuals" in rows[0]["notes"]


def test_unresolved_barcode_is_recorded_not_dropped():
    rows = build_rows(STUDY, ["JH-2-054-241HF-A"], specimens=set(),
                      specimen_individuals={}, existing={})
    assert len(rows) == 1, "an unmatched barcode must stay visible in the crosswalk"
    assert rows[0]["method"] == "unmatched"
    assert rows[0]["specimen_id"] == ""
    assert "set method=manual" in rows[0]["notes"]


def test_manual_rows_survive_regeneration(tmp_path):
    # The whole point of a checked-in crosswalk: a human fix is not undone by a rerun.
    path = tmp_path / "crosswalk.tsv"
    write_crosswalk(path, [{
        "study_id": STUDY, "tumor_sample_barcode": "JH-2-054-241HF-A",
        "specimen_id": "HAND-FIXED", "individual_id": "JH-2-054",
        "method": "manual", "notes": "confirmed with the submitter",
    }])

    rows = build_rows(STUDY, ["JH-2-054-241HF-A"], specimens=set(),
                      specimen_individuals={}, existing=load_existing(path))
    assert rows[0]["specimen_id"] == "HAND-FIXED"
    assert rows[0]["method"] == "manual"
    assert rows[0]["notes"] == "confirmed with the submitter"


def test_derived_rows_are_recomputed_on_regeneration(tmp_path):
    # The flip side: a stale derived row must NOT be preserved, or a crosswalk generated
    # before the portal gained a specimen would pin the old "unmatched" verdict forever.
    path = tmp_path / "crosswalk.tsv"
    write_crosswalk(path, [{
        "study_id": STUDY, "tumor_sample_barcode": "JH-2-001-8A1B1-A",
        "specimen_id": "", "individual_id": "", "method": "unmatched", "notes": "stale",
    }])

    rows = build_rows(STUDY, ["JH-2-001-8A1B1-A"], specimens={"JH-2-001-8A1B1"},
                      specimen_individuals={"JH-2-001-8A1B1": {"JH-2-001"}},
                      existing=load_existing(path))
    assert rows[0]["specimen_id"] == "JH-2-001-8A1B1"
    assert rows[0]["method"] == "strip_last_segment"


def test_load_crosswalk_hides_unresolved_rows_from_consumers(tmp_path):
    path = tmp_path / "crosswalk.tsv"
    write_crosswalk(path, [
        {"study_id": STUDY, "tumor_sample_barcode": "A-1", "specimen_id": "A",
         "individual_id": "P1", "method": "strip_last_segment", "notes": ""},
        {"study_id": STUDY, "tumor_sample_barcode": "B-1", "specimen_id": "",
         "individual_id": "", "method": "unmatched", "notes": ""},
        {"study_id": "other_study", "tumor_sample_barcode": "C-1", "specimen_id": "C",
         "individual_id": "P3", "method": "manual", "notes": ""},
    ])
    resolved = load_crosswalk(path, study_id=STUDY)
    assert set(resolved) == {"A-1"}, "unmatched and other-study rows must not leak"


def test_checked_in_crosswalk_is_readable_and_covers_every_study():
    # Guards the artifact itself: a malformed commit would break the RDF step later.
    # One file holds every study, so this also catches a regeneration that dropped one.
    path = Path(__file__).parent.parent / "mappings" / "cbioportal_sample_specimen.tsv"
    rows = load_existing(path)
    assert rows, "the checked-in crosswalk should not be empty"
    assert {study for study, _ in rows} == {STUDY, SCHW, NFIB, LGG}

    # nst is the only study needing a derived rule, and the only one with gaps.
    assert len([1 for study, _ in rows if study == STUDY]) == 80
    assert len(load_crosswalk(path, study_id=STUDY)) == 71

    # The three CTF/Synodos barcodes ARE portal specimen ids: no rule, no gaps.
    for study, expected in ((SCHW, 40), (NFIB, 38), (LGG, 21)):
        assert len([1 for s, _ in rows if s == study]) == expected, study
        assert len(load_crosswalk(path, study_id=study)) == expected, study
        methods = {r["method"] for (s, _), r in rows.items() if s == study}
        assert methods == {"verbatim"}, f"{study}: {methods}"


def test_verbatim_barcode_resolves_without_a_rule():
    """A barcode that already IS a specimenID must not be mangled by strip_last_segment."""
    rows = build_rows(
        SCHW,
        ["swn_patient_10_tumor_108"],
        {"swn_patient_10_tumor_108"},
        {"swn_patient_10_tumor_108": {"swn_patient_10"}},
        {},
    )
    assert rows[0]["specimen_id"] == "swn_patient_10_tumor_108"
    assert rows[0]["individual_id"] == "swn_patient_10"
    assert rows[0]["method"] == "verbatim"


def test_verbatim_is_tried_before_stripping():
    """Both rules could hit; the un-derived one must win, or the id loses a segment."""
    # 'A-B' is a specimen, and so is its stripped form 'A'. Verbatim is the truth.
    rows = build_rows(SCHW, ["A-B"], {"A-B", "A"}, {"A-B": {"i1"}, "A": {"i2"}}, {})
    assert (rows[0]["specimen_id"], rows[0]["method"]) == ("A-B", "verbatim")


def test_regenerating_one_study_keeps_another_studys_rows(tmp_path):
    """One file, many studies: rebuilding study B must not delete study A."""
    path = tmp_path / "crosswalk.tsv"
    write_crosswalk(path, [
        {"study_id": STUDY, "tumor_sample_barcode": "JH-2-001-8A1B1-A",
         "specimen_id": "JH-2-001-8A1B1", "individual_id": "JH-2-001",
         "method": "strip_last_segment", "notes": ""},
        {"study_id": STUDY, "tumor_sample_barcode": "JH-2-054-241HF",
         "specimen_id": "HAND-FIXED", "individual_id": "JH-2-054",
         "method": "manual", "notes": "curated"},
    ])
    before = load_existing(path)

    # Simulate main(): build study B, carry every other study across.
    rows = build_rows(SCHW, ["swn_patient_1_tumor_8"], {"swn_patient_1_tumor_8"},
                      {"swn_patient_1_tumor_8": {"swn_patient_1"}}, before)
    carried = [r for (study, _), r in before.items() if study != SCHW]
    write_crosswalk(path, carried + rows)

    after = load_existing(path)
    assert {study for study, _ in after} == {STUDY, SCHW}
    assert len(after) == 3
    # The hand-authored row in particular must survive untouched.
    assert after[(STUDY, "JH-2-054-241HF")]["specimen_id"] == "HAND-FIXED"
    assert after[(STUDY, "JH-2-054-241HF")]["method"] == "manual"
