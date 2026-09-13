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


def test_checked_in_crosswalk_is_readable_and_covers_the_study():
    # Guards the artifact itself: a malformed commit would break the RDF step later.
    path = Path(__file__).parent.parent / "mappings" / "cbioportal_sample_specimen.tsv"
    rows = load_existing(path)
    assert rows, "the checked-in crosswalk should not be empty"
    assert {study for study, _ in rows} == {STUDY}
    resolved = load_crosswalk(path, study_id=STUDY)
    assert len(resolved) == 71, f"expected 71 resolved barcodes, found {len(resolved)}"
    assert len(rows) == 80
