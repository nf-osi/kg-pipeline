"""Minting VRS identities for curated model mutations: parsing, coordinates, triples."""

import sys
from pathlib import Path

import pytest
from rdflib import Graph, Namespace, URIRef

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.materialize_model_mutation_vrs import build_graph
from scripts import mint_model_mutation_vrs as resolver
from scripts.mint_model_mutation_vrs import (
    normalize_hgvs,
    parse_expression,
    refseq_contig,
    spdi_to_vcf,
)

NF = Namespace("http://nf-osi.github.com/terms#")


class FakeReference:
    """A reference over one short sequence, addressed 0-based half-open."""

    def __init__(self, contig: str, offset: int, sequence: str):
        self.contig, self.offset, self.sequence = contig, offset, sequence

    def fetch(self, contig: str, start: int, end: int) -> str:
        assert contig == self.contig
        return self.sequence[start - self.offset : end - self.offset]


# --------------------------------------------------------------------- parsing

@pytest.mark.parametrize(
    "value, accession, hgvs_c, hgvs_p",
    [
        ("NM_000267.3(NF1):c.910C>T (p.Arg304Ter)", "NM_000267.3", "c.910C>T", "p.Arg304Ter"),
        # Splice variants are curated without a protein half.
        ("NM_000546.6(TP53):c.96+1G>A", "NM_000546.6", "c.96+1G>A", None),
        ("NM_000267.3:c.1756_1759del", "NM_000267.3", "c.1756_1759del", None),
    ],
)
def test_parse_expression(value, accession, hgvs_c, hgvs_p):
    match = parse_expression(value)
    assert match["accession"] == accession
    assert match["hgvs_c"] == hgvs_c
    assert match["hgvs_p"] == hgvs_p


def test_parse_expression_takes_the_first_of_a_pipe_separated_cell():
    value = ("NM_001042492.3(NF1):c.5488C>T (p.Arg1830Cys)"
             "|NM_000267.3:c.5425C>T:NP_000258.1:p.Arg1809Cys")
    match = parse_expression(value)
    assert match["accession"] == "NM_001042492.3"
    assert match["hgvs_c"] == "c.5488C>T"


def test_parse_expression_rejects_free_text():
    assert parse_expression("Ex16-35del") is None
    assert parse_expression("") is None


def test_normalize_hgvs_drops_the_gene_parenthetical():
    """ClinVar's preferred name carries `(NF1)`; the curated expression may not."""
    assert (normalize_hgvs("NM_001042492.3:c.6704+1G>T")
            in normalize_hgvs("NM_001042492.3(NF1):c.6704+1G>T"))


# ------------------------------------------------------------------ accessions

@pytest.mark.parametrize(
    "accession, contig",
    [("NC_000001.11", "chr1"), ("NC_000017.11", "chr17"),
     ("NC_000023.11", "chrX"), ("NC_000024.10", "chrY")],
)
def test_refseq_contig(accession, contig):
    assert refseq_contig(accession) == contig


def test_refseq_contig_rejects_a_transcript():
    """A transcript SPDI must never be mistaken for a genomic one."""
    with pytest.raises(ValueError):
        refseq_contig("NM_000267.3")


# ----------------------------------------------------------------- SPDI -> VCF

def test_substitution_needs_no_anchor():
    reference = FakeReference("chr17", 31200440, "AACGT")
    assert spdi_to_vcf("NC_000017.11:31200442:C:T", reference) == ("chr17", 31200443, "C", "T")


def test_deletion_takes_the_preceding_base_from_the_reference():
    """SPDI drops the anchor base; VCF requires it, and it comes from hg38, not
    from re-using a character out of the SPDI string."""
    reference = FakeReference("chr2", 188990325, "TGAC")
    assert spdi_to_vcf("NC_000002.12:188990327:A:", reference) == (
        "chr2", 188990327, "GA", "G",
    )


def test_insertion_takes_the_preceding_base_too():
    reference = FakeReference("chr17", 31226465, "TGC")
    assert spdi_to_vcf("NC_000017.11:31226467::C", reference) == (
        "chr17", 31226467, "G", "GC",
    )


def test_delins_keeps_both_sides_verbatim():
    reference = FakeReference("chr17", 31200440, "AACGT")
    assert spdi_to_vcf("NC_000017.11:31200441:AC:TT", reference) == (
        "chr17", 31200442, "AC", "TT",
    )


def test_a_reference_mismatch_is_an_error_not_a_silent_shift():
    reference = FakeReference("chr17", 31200440, "AAGGT")
    with pytest.raises(ValueError, match="reference has"):
        spdi_to_vcf("NC_000017.11:31200442:C:T", reference)


# ------------------------------------------------------------------- triples

def row(mutation_id, vrs_id, evidence="both_agree"):
    return {"mutation_id": mutation_id, "vrs_id": vrs_id, "evidence": evidence}


def test_only_resolved_rows_become_triples():
    graph = build_graph([row("m1", "ga4gh:VA.aaa"), row("m2", "", "unresolved")])
    subject = URIRef("http://nf-osi.github.com/terms#mutation/m1")
    assert (subject, NF.mutationVrsId, None) in graph
    assert len(graph) == 1


def test_two_mutations_may_share_one_digest():
    """p.Arg1947Ter (NM_000267.3) and p.Arg1968Ter (NM_001042492.3) are one allele."""
    graph = build_graph([row("m1", "ga4gh:VA.same"), row("m2", "ga4gh:VA.same")])
    assert len(graph) == 2
    assert len(set(graph.objects(None, NF.mutationVrsId))) == 1


def test_the_digest_is_a_literal_not_a_node_reference():
    """Emitting an edge to ga4gh:VA.<digest> would mint allele nodes for the 36
    curated alleles no patient carries, and `?v a biolink:SequenceVariant` would
    stop meaning "observed in a specimen"."""
    graph = build_graph([row("m1", "ga4gh:VA.aaa")])
    ((_, _, obj),) = list(graph)
    assert not isinstance(obj, URIRef)
    assert str(obj) == "ga4gh:VA.aaa"


def test_mutation_iri_matches_the_rml_subject_template():
    graph = build_graph([row("c9b33ec8-8862-4b18-b0ea-37ab8284ef53", "ga4gh:VA.aaa")])
    ((subject, _, _),) = list(graph)
    assert str(subject) == (
        "http://nf-osi.github.com/terms#mutation/c9b33ec8-8862-4b18-b0ea-37ab8284ef53"
    )


@pytest.mark.parametrize(
    "searched,name,aliases,vs_spdi,evidence",
    [
        # A newer transcript alone cannot confirm the original intronic expression.
        ("NM_000546.6:c.96+1G>A", "NM_000546.6(TP53):c.96+1G>A", [], None,
         "clinvar_unconfirmed"),
        # A prefix of a longer expression is not an exact HGVS match.
        ("NM_000546.5:c.96+1G>A", "NM_000546.5(TP53):c.96+1G>AT", [], None,
         "clinvar_unconfirmed"),
        ("NM_000546.5:c.96+1G>A", "other", ["NM_000546.5:c.96+1G>AT"], None,
         "clinvar_unconfirmed"),
        # Gene/protein annotations do not change the transcript HGVS identity.
        ("NM_000546.5:c.96+1G>A", "NM_000546.5(TP53):c.96+1G>A (p.?)", [], None,
         "clinvar_only"),
        # A bumped search is safe if an alias still confirms the original version.
        ("NM_000546.6:c.96+1G>A", "NM_000546.6(TP53):c.96+1G>A",
         ["NM_000546.5:c.96+1G>A"], None, "clinvar_only"),
        # Independent projection of the original version also confirms identity.
        ("NM_000546.6:c.96+1G>A", "NM_000546.6(TP53):c.96+1G>A", [],
         "NC_000017.11:100:C:T", "both_agree"),
        ("NM_000546.6:c.96+1G>A", "NM_000546.6(TP53):c.96+1G>A", [],
         "NC_000017.11:200:C:T", "disagree"),
    ],
)
def test_resolution_requires_original_expression_or_coordinate_agreement(
    monkeypatch, searched, name, aliases, vs_spdi, evidence
):
    curated_hgvs = "NM_000546.5:c.96+1G>A"

    def project(hgvs, throttle):
        assert hgvs == curated_hgvs
        return vs_spdi

    def lookup(hgvs, throttle):
        assert hgvs == curated_hgvs
        return {"searched": searched, "name": name, "aliases": aliases,
                "spdi": "NC_000017.11:100:C:T", "vcv": "VCV_TEST",
                "chromosome": "17", "start": "101"}

    monkeypatch.setattr(resolver, "variation_services_spdi", project)
    monkeypatch.setattr(resolver, "clinvar_record", lookup)
    (resolved,) = resolver.resolve_all(
        [{"mutationId": "m1", "affectedGeneSymbol": "TP53",
          "humanClinVarMutation": "NM_000546.5(TP53):c.96+1G>A"}],
        FakeReference("chr17", 100, "C"), resolver.Throttle(0),
    )
    assert resolved["evidence"] == evidence
    if evidence in {"both_agree", "clinvar_only"}:
        assert resolved["genomic_spdi"] == "NC_000017.11:100:C:T"
        assert resolved["reference_bases"] == "C"
        assert resolved["alternate_bases"] == "T"
    else:
        assert resolved["genomic_spdi"] == ""
        assert resolved["reference_bases"] == ""
        assert resolved["vrs_id"] == ""
