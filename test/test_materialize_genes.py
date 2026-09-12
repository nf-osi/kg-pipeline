"""Tests for the biolink:Gene layer.

The behaviours pinned here are the ones that stop a gene node from being silently wrong:
Ensembl (not symbol, not HGNC) is the key, HGNC is the symbol authority but only when it
cross-checks, and a symbol borrowed from a neighbouring locus must not end up labelling
two genes.
"""

import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF, RDFS, SKOS, XSD

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.materialize_genes import gene_iri, hgnc_iri, load_hgnc, materialize_genes

NF = Namespace("http://nf-osi.github.com/terms#")
BIOLINK = Namespace("https://w3id.org/biolink/vocab/")

MAF_COLUMNS = ["Hugo_Symbol", "Entrez_Gene_Id", "Gene", "HGNC_ID"]

HGNC_COLUMNS = ["hgnc_id", "symbol", "name", "status", "ensembl_gene_id"]


def write_maf(path: Path, rows: list[dict]) -> Path:
    lines = ["#banner: ignored", "\t".join(MAF_COLUMNS)]
    lines += ["\t".join(str(r.get(c, "")) for c in MAF_COLUMNS) for r in rows]
    path.write_text("\n".join(lines) + "\n")
    return path


def write_hgnc(path: Path, rows: list[dict]) -> Path:
    lines = ["\t".join(HGNC_COLUMNS)]
    lines += ["\t".join(str(r.get(c, "")) for c in HGNC_COLUMNS) for r in rows]
    path.write_text("\n".join(lines) + "\n")
    return path


def build(tmp_path: Path, maf_rows: list[dict], hgnc_rows: list[dict] | None = None):
    maf = write_maf(tmp_path / "maf.txt", maf_rows)
    hgnc = write_hgnc(tmp_path / "hgnc.txt", hgnc_rows) if hgnc_rows is not None else None
    out = tmp_path / "genes.ttl"
    index = materialize_genes(maf, out, hgnc)
    graph = Graph()
    graph.parse(out, format="turtle")
    return graph, index


NF1_MAF = {"Hugo_Symbol": "NF1", "Entrez_Gene_Id": "4763",
           "Gene": "ENSG00000196712", "HGNC_ID": "HGNC:7765"}
NF1_HGNC = {"hgnc_id": "HGNC:7765", "symbol": "NF1", "name": "neurofibromin 1",
            "status": "Approved", "ensembl_gene_id": "ENSG00000196712"}


def test_gene_node_is_biolink_and_keyed_on_ensembl(tmp_path):
    graph, index = build(tmp_path, [NF1_MAF], [NF1_HGNC])
    node = gene_iri("ENSG00000196712")

    # biolink:Gene directly -- nf:Gene means a PubTator text mention.
    assert (node, RDF.type, BIOLINK.Gene) in graph
    assert (node, RDF.type, NF.Gene) not in graph
    assert str(node) == "https://identifiers.org/ensembl:ENSG00000196712"

    assert (node, NF.geneSymbol, Literal("NF1", datatype=XSD.string)) in graph
    assert (node, NF.geneName, Literal("neurofibromin 1", datatype=XSD.string)) in graph
    assert (node, NF.hgncId, Literal("HGNC:7765", datatype=XSD.string)) in graph
    assert (node, NF.entrezGeneId, Literal("4763", datatype=XSD.string)) in graph
    assert (node, RDFS.label, Literal("NF1")) in graph
    # The HGNC equivalence lets HGNC-keyed data join without a lookup table.
    assert (node, SKOS.exactMatch, hgnc_iri("HGNC:7765")) in graph
    assert index.resolution["verified_by_hgnc"] == 1


def test_hgnc_corrects_a_symbol_borrowed_from_a_neighbouring_locus(tmp_path):
    # Real case: VEP reported NF1's symbol against EVI2A, which sits inside the NF1
    # locus. Left alone, "NF1" would label two gene nodes and split every gene-level
    # count across them.
    evi2a_maf = {"Hugo_Symbol": "NF1", "Entrez_Gene_Id": "2123",
                 "Gene": "ENSG00000126860", "HGNC_ID": "HGNC:3499"}
    evi2a_hgnc = {"hgnc_id": "HGNC:3499", "symbol": "EVI2A",
                  "name": "ecotropic viral integration site 2A",
                  "status": "Approved", "ensembl_gene_id": "ENSG00000126860"}
    graph, index = build(tmp_path, [NF1_MAF, evi2a_maf], [NF1_HGNC, evi2a_hgnc])

    assert (gene_iri("ENSG00000196712"), NF.geneSymbol,
            Literal("NF1", datatype=XSD.string)) in graph
    assert (gene_iri("ENSG00000126860"), NF.geneSymbol,
            Literal("EVI2A", datatype=XSD.string)) in graph
    # ...and crucially, NF1 now labels exactly one gene.
    assert len(set(graph.subjects(NF.geneSymbol, Literal("NF1", datatype=XSD.string)))) == 1
    assert index.resolution["symbol_corrected"] == 1


def test_hgnc_is_rejected_when_its_ensembl_id_disagrees(tmp_path):
    # The cross-check is the whole point: if HGNC says this HGNC id belongs to a
    # different locus, one of the two sources is wrong, so neither symbol is trusted
    # over the other and the MAF's stands -- counted as unverified.
    hgnc = dict(NF1_HGNC, ensembl_gene_id="ENSG00000999999")
    graph, index = build(tmp_path, [NF1_MAF], [hgnc])
    node = gene_iri("ENSG00000196712")
    assert (node, NF.geneSymbol, Literal("NF1", datatype=XSD.string)) in graph
    assert not list(graph.objects(node, NF.geneName))
    assert index.resolution["unverified_maf_symbol"] == 1
    assert index.resolution["verified_by_hgnc"] == 0


def test_withdrawn_hgnc_entries_are_ignored(tmp_path):
    # Adopting a withdrawn symbol would reintroduce the ambiguity HGNC exists to remove.
    hgnc = dict(NF1_HGNC, status="Entry Withdrawn", symbol="NF1-OLD")
    graph, index = build(tmp_path, [NF1_MAF], [hgnc])
    node = gene_iri("ENSG00000196712")
    assert (node, NF.geneSymbol, Literal("NF1", datatype=XSD.string)) in graph
    assert index.resolution["unverified_maf_symbol"] == 1


def test_dominant_maf_symbol_wins_without_hgnc(tmp_path):
    # Offline path: no HGNC lookup, so the most frequent MAF symbol is used and the
    # minority one is dropped rather than asserted on the same node.
    rows = [
        {"Hugo_Symbol": "SLC4A7", "Gene": "ENSG00000033867", "HGNC_ID": "HGNC:11033",
         "Entrez_Gene_Id": "9497"},
        {"Hugo_Symbol": "SLC4A7", "Gene": "ENSG00000033867", "HGNC_ID": "HGNC:11033",
         "Entrez_Gene_Id": "9497"},
        {"Hugo_Symbol": "UBA52P4", "Gene": "ENSG00000033867", "HGNC_ID": "HGNC:11033",
         "Entrez_Gene_Id": "100271030"},
    ]
    graph, index = build(tmp_path, rows)
    node = gene_iri("ENSG00000033867")
    symbols = {str(o) for o in graph.objects(node, NF.geneSymbol)}
    assert symbols == {"SLC4A7"}, "a minority symbol must not label the dominant gene"
    # Entrez is restricted the same way, or the pseudogene's id lands on SLC4A7.
    assert {str(o) for o in graph.objects(node, NF.entrezGeneId)} == {"9497"}
    assert index.discarded_symbols == 1
    assert index.resolution["no_hgnc_lookup"] == 1


def test_one_node_per_ensembl_not_per_row(tmp_path):
    graph, index = build(tmp_path, [NF1_MAF, NF1_MAF, NF1_MAF], [NF1_HGNC])
    assert len(set(graph.subjects(RDF.type, BIOLINK.Gene))) == 1
    assert len(index.genes) == 1
    assert index.rows == 3


def test_maf_placeholders_produce_no_gene(tmp_path):
    rows = [
        {"Hugo_Symbol": "Unknown", "Gene": "", "HGNC_ID": "", "Entrez_Gene_Id": "0"},
        {"Hugo_Symbol": "RRN3P2", "Gene": "", "HGNC_ID": "", "Entrez_Gene_Id": "0"},
    ]
    graph, index = build(tmp_path, rows, [])
    assert len(set(graph.subjects(RDF.type, BIOLINK.Gene))) == 0
    assert index.rows_without_ensembl == 2
    # A symbol with no Ensembl id is reported, not silently dropped.
    assert index.orphan_symbols["RRN3P2"] == 1
    assert "Unknown" not in index.orphan_symbols


def test_gene_with_no_hgnc_id_still_gets_a_node(tmp_path):
    rows = [{"Hugo_Symbol": "LYRM4-AS1", "Gene": "ENSG00000012345",
             "HGNC_ID": "", "Entrez_Gene_Id": "0"}]
    graph, index = build(tmp_path, rows, [NF1_HGNC])
    node = gene_iri("ENSG00000012345")
    assert (node, RDF.type, BIOLINK.Gene) in graph
    assert (node, NF.geneSymbol, Literal("LYRM4-AS1", datatype=XSD.string)) in graph
    assert not list(graph.objects(node, NF.hgncId))
    assert index.resolution["unverified_maf_symbol"] == 1


def test_hgnc_iri_strips_the_curie_prefix(tmp_path):
    assert str(hgnc_iri("HGNC:7765")) == "https://identifiers.org/hgnc:7765"
    assert str(hgnc_iri("7765")) == "https://identifiers.org/hgnc:7765"


def test_load_hgnc_keeps_only_approved(tmp_path):
    path = write_hgnc(tmp_path / "h.txt", [
        NF1_HGNC,
        {"hgnc_id": "HGNC:1", "symbol": "OLD", "name": "old", "status": "Entry Withdrawn",
         "ensembl_gene_id": "ENSG1"},
    ])
    hgnc = load_hgnc(path)
    assert set(hgnc) == {"HGNC:7765"}


def test_missing_required_column_is_a_hard_error(tmp_path):
    path = tmp_path / "bad.txt"
    path.write_text("Hugo_Symbol\tHGNC_ID\nNF1\tHGNC:7765\n")
    try:
        materialize_genes(path, tmp_path / "out.ttl")
    except SystemExit as exc:
        assert "Gene" in str(exc)
    else:
        raise AssertionError("a MAF with no Gene column must fail, not yield no genes")
