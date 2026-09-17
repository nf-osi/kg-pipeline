"""Tests for the cBioPortal MAF fetcher.

The behaviour worth pinning here is reproducibility of the *source*. cBioPortal
reprocesses studies in place, so a ref that is not a commit does not identify the bytes:
the same URL served a 114-column MAF and, later, a 57-column rewrite with the gene
identifier columns removed. These tests fail if a study is ever repointed at something
mutable, or if the acceptance check that catches such a rewrite is weakened.

Nothing here touches the network.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.fetch_cbioportal_maf import (
    REQUIRED_COLUMNS,
    STUDIES,
    accept_candidate,
    count_rows,
    maf_header,
)

FULL_SHA = 40


def write_maf(path: Path, columns: list[str], rows: int = 1, banner: bool = True) -> Path:
    lines = ["#comment: ignored"] if banner else []
    lines.append("\t".join(columns))
    lines += ["\t".join("x" for _ in columns)] * rows
    path.write_text("\n".join(lines) + "\n")
    return path


def test_every_study_pins_a_commit_not_a_branch():
    """A branch ref does not identify bytes -- cBioPortal rewrites studies in place."""
    for study_id, source in STUDIES.items():
        assert source.repo == "cBioPortal/datahub", f"{study_id} is off the canonical repo"
        assert len(source.ref) == FULL_SHA, f"{study_id}: ref {source.ref!r} is not a SHA"
        assert all(c in "0123456789abcdef" for c in source.ref), study_id


def test_study_ids_match_their_keys_and_paths():
    for study_id, source in STUDIES.items():
        assert source.study_id == study_id
        assert source.path == f"public/{study_id}/data_mutations.txt"


def test_header_skips_the_banner_lines(tmp_path):
    maf = write_maf(tmp_path / "m.txt", ["Hugo_Symbol", "Gene"])
    assert maf_header(maf) == ["Hugo_Symbol", "Gene"]


def test_row_count_excludes_banner_and_header(tmp_path):
    maf = write_maf(tmp_path / "m.txt", ["Hugo_Symbol"], rows=5)
    assert count_rows(maf) == 5


def test_missing_gene_columns_are_rejected(tmp_path):
    """The genome-nexus rewrite drops Gene and HGNC_ID -- that must not pass."""
    genome_nexus = ["Hugo_Symbol", "Entrez_Gene_Id", "Tumor_Sample_Barcode", "SYMBOL"]
    maf = write_maf(tmp_path / "m.txt", genome_nexus, rows=50_000)
    source = STUDIES["schw_ctf_synodos_2025"]
    reason = accept_candidate(maf, source)
    assert "HGNC_ID" in reason and "Gene" in reason


def test_a_filtered_rerelease_is_rejected_on_row_count(tmp_path):
    """Every column present, but a fraction of the data: the nst tarball's failure."""
    maf = write_maf(tmp_path / "m.txt", sorted(REQUIRED_COLUMNS), rows=955)
    source = STUDIES["nst_nfosi_ntap"]
    assert source.min_rows > 955
    assert "fewer than" in accept_candidate(maf, source)


def test_a_good_maf_is_accepted(tmp_path):
    maf = write_maf(tmp_path / "m.txt", sorted(REQUIRED_COLUMNS), rows=50_000)
    assert accept_candidate(maf, STUDIES["schw_ctf_synodos_2025"]) == ""
