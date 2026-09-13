"""Tests for the variant-layer gate in the embedding edgelist loader.

The somatic variant layer is reversible only because three separate globs miss
`data/rdf/variants/`. This pins the edgelist one: non-recursive by default, opt-in by
flag. If `load_rdf` ever picks the subdirectory up implicitly, ~24k variant nodes enter
every embedding silently.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rdf_to_edgelist import VARIANT_SUBDIR, load_rdf

NF = "http://nf-osi.github.com/terms#"

CORE = f"""<{NF}specimen/S1> <{NF}fromIndividual> <{NF}individual/P1> .
"""

VARIANTS = f"""<{NF}variantObservation/o1> <{NF}fromSpecimen> <{NF}specimen/S1> .
<{NF}variantObservation/o2> <{NF}fromSpecimen> <{NF}specimen/S1> .
"""


@pytest.fixture
def rdf_dir(tmp_path: Path) -> Path:
    (tmp_path / "core.ttl").write_text(CORE)
    (tmp_path / VARIANT_SUBDIR).mkdir()
    (tmp_path / VARIANT_SUBDIR / "study.ttl").write_text(VARIANTS)
    return tmp_path


def test_variant_subdirectory_is_excluded_by_default(rdf_dir):
    assert len(load_rdf(rdf_dir)) == 1


def test_include_variants_folds_the_subdirectory_in(rdf_dir):
    assert len(load_rdf(rdf_dir, include_variants=True)) == 3


def test_include_variants_warns_rather_than_fails_when_empty(tmp_path, caplog):
    # The layer is opt-in at ingest too, so asking for it before generating it is a
    # plausible mistake and must not look like a successful variant-aware run.
    (tmp_path / "core.ttl").write_text(CORE)
    with caplog.at_level("WARNING"):
        assert len(load_rdf(tmp_path, include_variants=True)) == 1
    assert "holds no .ttl files" in caplog.text


def test_empty_rdf_dir_still_exits(tmp_path):
    with pytest.raises(SystemExit):
        load_rdf(tmp_path)
