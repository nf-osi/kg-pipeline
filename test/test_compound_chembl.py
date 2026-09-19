"""Tests for the portal compound string -> ChEMBL crosswalk.

Weighted towards the cases where a wrong answer looks right: an ambiguous label
resolving to a different drug, a systematic name shredded by the multi-value
delimiter, and a multi-line portal value corrupting the file it is written to.
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.map_compound_chembl import (
    DERIVED_METHODS,
    LabelIndex,
    build_rows,
    candidate_tokens,
    classify,
    flatten,
    looks_shredded,
    read_manual_rows,
    resolve_component,
    split_components,
    write_mapping,
)

#: label, folded, kind, source, chembl, name, drug_type, ambiguous
LABEL_ROWS = [
    ("OLAPARIB", "olaparib", "preferred_name", "OT", "CHEMBL521686", "OLAPARIB", "Small molecule", "yes"),
    ("Olaparib", "olaparib", "synonym", "ChEMBL", "CHEMBL4650351", "PARPI", "Small molecule", "yes"),
    ("TRAMETINIB", "trametinib", "preferred_name", "OT", "CHEMBL2103875", "TRAMETINIB", "Small molecule", "no"),
    ("TNO155", "tno155", "synonym", "ChEMBL", "CHEMBL4650521", "BATOPROTAFIB", "Small molecule", "no"),
    ("RIBOCICLIB", "ribociclib", "preferred_name", "OT", "CHEMBL3545110", "RIBOCICLIB", "Small molecule", "no"),
    ("CUDC-907", "cudc-907", "synonym", "ChEMBL", "CHEMBL3622533", "FIMEPINOSTAT", "Small molecule", "no"),
    ("DMSO", "dmso", "synonym", "ChEMBL", "CHEMBL504", "DIMETHYL SULFOXIDE", "Small molecule", "no"),
    ("Tivantinib", "tivantinib", "preferred_name", "OT", "CHEMBL1946170", "TIVANTINIB", "Small molecule", "no"),
    # Two molecules whose PREFERRED names are the same string: genuinely ambiguous.
    ("XL-184", "xl-184", "preferred_name", "OT", "CHEMBL2105717", "CABOZANTINIB", "Small molecule", "yes"),
    ("XL-184", "xl-184", "preferred_name", "OT", "CHEMBL2103868", "CABOZANTINIB S-MALATE", "Small molecule", "yes"),
    # Present so a fragment of a longer name CAN match -- without these the
    # partial-split tests would pass for the wrong reason.
    ("ACRIDINE", "acridine", "preferred_name", "OT", "CHEMBL15380", "ACRIDINE", "Small molecule", "no"),
    ("SALINOMYCIN", "salinomycin", "preferred_name", "OT", "CHEMBL508208", "SALINOMYCIN", "Small molecule", "no"),
]


@pytest.fixture
def index(tmp_path):
    path = tmp_path / "chembl_labels.tsv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        handle.write("# ChEMBL molecule label index, Open Targets Platform 26.06\n")
        handle.write("label\tlabel_folded\tkind\tsource\tchembl_id\tmolecule_name"
                     "\tdrug_type\tambiguous\n")
        for row in LABEL_ROWS:
            handle.write("\t".join(row) + "\n")
    return LabelIndex.load(path)


def resolved(component, index):
    return resolve_component(component, index)


class TestAmbiguityIsRefusedNotGuessed:
    def test_preferred_name_beats_another_molecules_synonym(self, index):
        """The measured failure: taking the first candidate resolves Olaparib to
        PARPI -- a different drug that looks plausible in a table."""
        result = resolved("Olaparib", index)
        assert result.hit["chembl"] == "CHEMBL521686"
        assert result.hit["kind"] == "preferred_name"
        assert result.method == "exact"

    def test_tie_at_the_best_kind_resolves_to_nothing(self, index):
        result = resolved("XL-184", index)
        assert result.hit is None
        assert result.method == "ambiguous"
        assert {c["chembl"] for c in result.candidates} == {
            "CHEMBL2105717", "CHEMBL2103868"}

    def test_ambiguous_notes_name_the_candidates_for_a_curator(self, index):
        result = resolved("XL-184", index)
        assert "CABOZANTINIB" in result.note and "curator" in result.note

    def test_unmatched_string_is_kept_not_dropped(self, index):
        result = resolved("SHP099", index)
        assert result.hit is None and result.method == "unmatched"


class TestParsing:
    def test_combination_separators(self):
        assert split_components("Olaparib;Trabectedin") == ["Olaparib", "Trabectedin"]
        assert split_components("tno155 plus ribociclib") == ["tno155", "ribociclib"]
        assert split_components("AZD6244 + Imatinib") == ["AZD6244", "Imatinib"]

    def test_plus_inside_a_chemical_name_is_not_a_separator(self):
        """`(+)-` denotes stereochemistry. Splitting on a bare `+` destroys it."""
        assert split_components("(+)-Camptothecin") == ["(+)-Camptothecin"]
        assert split_components("(S)-(+)-Ketamine") == ["(S)-(+)-Ketamine"]

    def test_both_sides_of_an_equals_are_tried(self, index):
        """The portal uses `=` in opposite directions."""
        assert resolved("212= trametinib", index).hit["chembl"] == "CHEMBL2103875"
        assert "trametinib" in candidate_tokens("212= trametinib")

    def test_leading_dose_is_stripped(self, index):
        for raw in ("100 nM CUDC-907", "100nM CUDC-907", "0.5 uM CUDC-907"):
            assert resolved(raw, index).hit["chembl"] == "CHEMBL3622533", raw

    def test_trailing_parenthetical_is_tried_both_ways(self, index):
        """`Bosutinib (SKI-606)` resolves on the stem, `ARQ 197 (Tivantinib)` on the
        parenthetical, and nothing in the string says which."""
        assert resolved("CUDC-907 (fimepinostat)", index).hit["chembl"] == "CHEMBL3622533"
        assert resolved("ARQ 197 (Tivantinib)", index).hit["chembl"] == "CHEMBL1946170"

    def test_punctuation_insensitive_retry(self, index):
        result = resolved("CUDC907", index)
        assert result.hit["chembl"] == "CHEMBL3622533"
        assert result.method == "parsed"

    def test_unaltered_match_is_preferred_over_a_parsed_one(self, index):
        assert resolved("trametinib", index).method == "exact"

    def test_fragments_are_not_looked_up(self, index):
        """Splitting `10|20uM Ataluren` leaves a bare `10`; ChEMBL synonym lists
        contain bare numbers, so a fragment can match and waste a curator's time."""
        for fragment in ("10", "2", "N", "ab"):
            assert not LabelIndex.worth_looking_up(fragment), fragment
        assert LabelIndex.worth_looking_up("DMSO")


class TestShreddedNames:
    @pytest.mark.parametrize("raw", [
        "11H-Benzo[a]carbazole-1|4-dione|7|11-dimethyl-",       # unbalanced [
        "1|2|4-Dithiazol-3-amine|5-[(2-furanyl)methylimino]-",  # bare-digit part
        "11H-Indolo[3|2-c]quinolin-9-amine|3-chloro-N|N-diethyl-",
    ])
    def test_delimiter_cutting_through_one_name_is_detected(self, raw):
        assert looks_shredded(raw)

    @pytest.mark.parametrize("raw", [
        "100 nM CUDC-907|100 nM Panobinostat",
        "Olaparib;Trabectedin",
        "Trametinib",
    ])
    def test_a_real_list_is_not_flagged(self, raw):
        assert not looks_shredded(raw)

    def test_a_comma_spelled_systematic_name_is_not_shredded(self, index):
        """Detection is pipe-only on purpose. Once the ingest stopped comma-splitting,
        the same string spelled with commas is simply the correct value, and flagging
        it would report a fixed problem as still broken."""
        assert not looks_shredded("11H-Benzo[a]carbazole-1,4-dione, 7,11-dimethyl-")
        assert looks_shredded("11H-Benzo[a]carbazole-1|4-dione|7|11-dimethyl-")

    def test_shredded_value_is_classified_as_corrupted_not_unknown(self, index):
        raw = "11H-Benzo[a]carbazole-1|4-dione|7|11-dimethyl-"
        value_class, note = classify(raw, [resolved(raw, index)], arms=1)
        assert value_class == "shredded_name"
        assert "comma" in note


class TestArmSplitting:
    def test_comma_is_an_arm_separator(self, index):
        """What the portal records after the ingest stopped comma-splitting."""
        rows = build_rows({("trametinib,ribociclib", "compoundName"): 3}, {}, index)
        assert {r["chembl_id"] for r in rows} == {"CHEMBL2103875", "CHEMBL3545110"}
        assert {r["arm"] for r in rows} == {"1", "2"}

    def test_both_vintages_of_the_export_give_the_same_answer(self, index):
        """A pre-fix export spells the same list with pipes. Reading either without
        a flag is why both characters are arm separators."""
        def ids(raw):
            return {r["chembl_id"] for r in build_rows({(raw, "compoundName"): 1}, {}, index)}
        assert ids("trametinib,ribociclib") == ids("trametinib|ribociclib")

    def test_a_partly_resolving_split_is_refused(self, index):
        """`Acridine, 9-phenoxy-` is ONE compound. Accepting a split because some arm
        resolves returns ACRIDINE -- a real molecule, and the wrong one. This is the
        case that makes the rule all-arms rather than any-arm."""
        rows = build_rows({("Acridine, 9-phenoxy-", "compoundName"): 1}, {}, index)
        assert len(rows) == 1, "must stay whole"
        assert rows[0]["component"] == "Acridine, 9-phenoxy-"
        assert rows[0]["chembl_id"] == "", "must not resolve to the fragment's match"

    def test_a_salt_is_not_two_compounds(self, index):
        rows = build_rows({("SALINOMYCIN, SODIUM", "compoundName"): 1}, {}, index)
        assert len(rows) == 1 and rows[0]["chembl_id"] == ""

    def test_pipe_split_is_kept_when_it_resolves(self, index):
        rows = build_rows({("trametinib|ribociclib", "compoundName"): 3},
                          {("trametinib|ribociclib", "compoundName"): 3}, index)
        assert {r["chembl_id"] for r in rows} == {"CHEMBL2103875", "CHEMBL3545110"}
        assert {r["arm"] for r in rows} == {"1", "2"}
        # Separate arms, so neither is a combination.
        assert all(not r["combination_key"] for r in rows)

    def test_pipe_split_is_discarded_when_it_resolves_nothing(self, index):
        raw = "11H-Benzo[a]carbazole-1|4-dione|7|11-dimethyl-"
        rows = build_rows({(raw, "compoundName"): 1}, {}, index)
        assert len(rows) == 1, "the shredded name must stay whole"
        assert rows[0]["component"] == raw
        assert rows[0]["value_class"] == "shredded_name"

    def test_combination_key_is_per_arm(self, index):
        raw = "trametinib;ribociclib|tno155"
        rows = build_rows({(raw, "compoundName"): 1}, {}, index)
        arm_one = {r["combination_key"] for r in rows if r["arm"] == "1"}
        arm_two = {r["combination_key"] for r in rows if r["arm"] == "2"}
        assert arm_one == {"CHEMBL2103875+CHEMBL3545110"}
        assert arm_two == {""}, "a single-drug arm is not a combination"

    def test_order_variants_share_a_combination_key(self, index):
        """`Ribociclib;Trametinib` and `Trametinib;Ribociclib` are one experiment."""
        keys = set()
        for raw in ("trametinib;ribociclib", "ribociclib;trametinib"):
            rows = build_rows({(raw, "compoundName"): 1}, {}, index)
            keys |= {r["combination_key"] for r in rows}
        assert keys == {"CHEMBL2103875+CHEMBL3545110"}


class TestDemoFlagging:
    def test_demo_rows_sort_first_and_are_marked(self, index):
        counts = {("trametinib", "compoundName"): 2, ("ribociclib", "compoundName"): 99}
        demo = {("trametinib", "compoundName"): 2}
        rows = build_rows(counts, demo, index)
        assert rows[0]["raw_value"] == "trametinib", "demo rows lead regardless of count"
        assert rows[0]["in_demo"] == "yes" and rows[0]["demo_files"] == "2"
        assert rows[-1]["in_demo"] == "no" and rows[-1]["demo_files"] == "0"


class TestFileIntegrity:
    def test_flatten_removes_embedded_newlines(self):
        """One portal experimentalCondition is a four-line genotype note. Written
        unflattened it splits one record across four lines."""
        assert flatten("a\nb\tc\r\nd") == "a b c d"

    def test_written_file_is_one_record_per_line(self, index, tmp_path):
        raw = "#1212: Genotype GFAP-Cre\n#1213: Genotype GFAP-Cre\tHigh-fat diet"
        rows = build_rows({(raw, "experimentalCondition"): 4}, {}, index)
        out = tmp_path / "compound_chembl.tsv"
        write_mapping(out, rows, [], index, "test", {
            "strings": 1, "files_with_value": 4, "resolved_strings": 0,
            "partial": 0, "unresolved_strings": 1, "demo_strings": 0,
            "demo_files_with_value": 0, "demo_resolved": 0})
        data = [l for l in out.read_text(encoding="utf-8").splitlines()
                if not l.startswith("#")]
        with open(out, newline="", encoding="utf-8") as handle:
            records = list(csv.DictReader(
                (l for l in handle if not l.startswith("#")), delimiter="\t"))
        assert len(data) - 1 == len(records) == len(rows)

    def test_debris_is_not_preserved_as_a_manual_row(self, index, tmp_path):
        """The bug this guards: fragments of a split record read back with a blank
        method, get treated as hand edits, and are appended on every later run."""
        out = tmp_path / "compound_chembl.tsv"
        rows = build_rows({("trametinib", "compoundName"): 1}, {}, index)
        write_mapping(out, rows, [], index, "test", {
            "strings": 1, "files_with_value": 1, "resolved_strings": 1, "partial": 0,
            "unresolved_strings": 0, "demo_strings": 0, "demo_files_with_value": 0,
            "demo_resolved": 0})
        with open(out, "a", encoding="utf-8") as handle:
            handle.write("no\t0\tdebris\t\t\t\t\t\t\t\t\t\t\n")
        assert read_manual_rows(out) == []

    def test_a_real_hand_edit_is_preserved(self, index, tmp_path):
        out = tmp_path / "compound_chembl.tsv"
        write_mapping(out, [], [], index, "test", {
            "strings": 0, "files_with_value": 0, "resolved_strings": 0, "partial": 0,
            "unresolved_strings": 0, "demo_strings": 0, "demo_files_with_value": 0,
            "demo_resolved": 0})
        with open(out, "a", encoding="utf-8") as handle:
            handle.write("yes\t1\tSHP099\tcompoundName\t2\tcompound\t1\tSHP099"
                         "\tCHEMBL999\tSHP099\t\tmanual\t\thand-curated\n")
        manual = read_manual_rows(out)
        assert len(manual) == 1
        assert manual[0]["chembl_id"] == "CHEMBL999"
        assert manual[0]["method"] == "manual"
        assert "manual" not in DERIVED_METHODS
