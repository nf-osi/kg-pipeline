"""Tests for the cBioPortal MAF fetcher.

The behaviour worth pinning here is reproducibility of the *source*. cBioPortal
reprocesses studies in place, so a ref that is not a commit does not identify the bytes:
the same URL served a 114-column MAF and, later, a 57-column rewrite with the gene
identifier columns removed. These tests fail if a study is ever repointed at something
mutable, or if the acceptance check that catches such a rewrite is weakened.

Nothing here touches the network.
"""

import hashlib
import io
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.fetch_cbioportal_maf import (
    REQUIRED_COLUMNS,
    STUDIES,
    accept_candidate,
    count_rows,
    maf_header,
)

from scripts import fetch_cbioportal_maf as fetcher

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


@pytest.fixture
def pinned_maf(tmp_path, monkeypatch):
    source = replace(STUDIES["nst_nfosi_ntap"], min_rows=1)
    monkeypatch.setitem(STUDIES, source.study_id, source)
    path = write_maf(tmp_path / "m.txt", sorted(REQUIRED_COLUMNS))
    content = path.read_bytes()
    pointer = Mock(return_value=(hashlib.sha256(content).hexdigest(), len(content)))
    url = Mock(return_value="https://example.org/maf")
    request = Mock(side_effect=lambda _: io.BytesIO(content))
    monkeypatch.setattr(fetcher, "read_lfs_pointer", pointer)
    monkeypatch.setattr(fetcher, "resolve_lfs_download", url)
    monkeypatch.setattr(fetcher, "_request", request)
    return source, path, content, pointer, url, request


def test_matching_cache_is_verified_without_downloading(pinned_maf):
    source, path, content, pointer, url, request = pinned_maf
    assert fetcher.fetch_maf(source.study_id, path) == path
    pointer.assert_called_once_with(source)
    url.assert_not_called()
    request.assert_not_called()
    assert path.read_bytes() == content


def test_repin_replaces_acceptable_same_size_cache(pinned_maf, monkeypatch):
    source, path, content, pointer, url, request = pinned_maf
    # A changed annotation passes the column/row checks and has the same byte size.
    path.write_bytes(content.replace(b"x", b"y"))
    assert accept_candidate(path, source) == ""
    repinned = replace(source, ref="a" * 40)
    monkeypatch.setitem(STUDIES, source.study_id, repinned)

    fetcher.fetch_maf(source.study_id, path)

    pointer.assert_called_once_with(repinned)
    request.assert_called_once()
    assert path.read_bytes() == content


def test_force_downloads_even_a_matching_cache(pinned_maf):
    source, path, content, pointer, url, request = pinned_maf
    fetcher.fetch_maf(source.study_id, path, force=True)
    request.assert_called_once()
    assert path.read_bytes() == content


@pytest.mark.parametrize("corruption", ["same_size", "truncated"])
def test_bad_download_preserves_previous_cache(pinned_maf, corruption):
    source, path, content, pointer, url, request = pinned_maf
    bad = content.replace(b"x", b"y") if corruption == "same_size" else content[:-1]
    request.side_effect = lambda _: io.BytesIO(bad)

    with pytest.raises(SystemExit, match="SHA-256|short read"):
        fetcher.fetch_maf(source.study_id, path, force=True)

    assert path.read_bytes() == content
    assert list(path.parent.iterdir()) == [path]
