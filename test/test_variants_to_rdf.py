"""Tests for the somatic variant layer RDF projection (nf-osi/kg-pipeline#95).

The invariants pinned here are the ones that make the layer worth having:

* the two-layer split holds -- nothing sample-specific lands on the shared allele node,
  which is what lets one allele seen in several samples stay one node;
* MAF's multi-term `Consequence` cell becomes several SO links, not one;
* rows that cannot be resolved (no VRS identity, or a barcode with no portal specimen)
  are KEPT and counted rather than dropped;
* the specimen join goes through the reviewed crosswalk, so a coverage regression is
  visible instead of silently shrinking the layer.
"""

import json
import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF, XSD

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.materialize_specimens import individual_iri, specimen_iri
from scripts.variants_to_rdf import so_iri, variant_iri, variants_to_rdf

NF = Namespace("http://nf-osi.github.com/terms#")
BIOLINK = Namespace("https://w3id.org/biolink/vocab/")
OBO = Namespace("http://purl.obolibrary.org/obo/")

REPO = Path(__file__).parent.parent
CONSEQUENCE_LOOKUP = REPO / "mappings" / "sssom" / "variant_consequence.sssom.tsv"
CLASSIFICATION_LOOKUP = REPO / "mappings" / "sssom" / "variant_classification.sssom.tsv"

VRS_ID = "ga4gh:VA.0AePZIWZUNsUlQTamyLrjm2HWUw2opLt"

ALLELE = {
    "id": VRS_ID,
    "type": "Allele",
    "location": {
        "type": "SequenceLocation",
        "start": 44908821,
        "end": 44908822,
        "sequenceReference": {
            "type": "SequenceReference",
            "refgetAccession": "SQ.IIB53T8CNeJJdUqzn9V_JnRtQadwWCbl",
        },
    },
    "state": {"type": "LiteralSequenceExpression", "sequence": "T"},
}


def observation(barcode: str, **overrides) -> dict:
    record = {
        "type": "VariantObservation",
        "variant": VRS_ID,
        "biosample": barcode,
        "tumorSampleBarcode": barcode,
        "matchedNormalSampleBarcode": f"{barcode}-N",
        "mutationStatus": "Somatic",
        "assemblyId": "GRCh38",
        "referenceName": "19",
        "sourceContig": "19",
        "sourcePos": 44908822,
        "affectedGeneSymbol": "APOE",
        "affectedGene": "ENSG00000130203",
        "hgncId": "HGNC:613",
        "variantClassification": "Missense_Mutation",
        "variantType": "SNP",
        "aminoacidChange": "p.C130R",
        "molecularConsequence": ["missense_variant"],
        "dbsnpId": ["rs7412"],
        "tumorDepth": 60,
        "tumorAltCount": 20,
        "variantAlleleFrequency": 20 / 60,
    }
    record.update(overrides)
    return record


def write_ndjson(path: Path, records: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


CROSSWALK_HEADER = (
    "# test crosswalk\n"
    "study_id\ttumor_sample_barcode\tspecimen_id\tindividual_id\tmethod\tnotes\n"
)


def write_crosswalk(path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    body = "".join(
        f"nf_test\t{barcode}\t{specimen}\t{individual}\t{method}\t\n"
        for barcode, specimen, individual, method in rows
    )
    path.write_text(CROSSWALK_HEADER + body)
    return path


def build(tmp_path: Path, alleles: list[dict], observations: list[dict],
          crosswalk: list[tuple[str, str, str, str]]):
    out = tmp_path / "variants.ttl"
    builder = variants_to_rdf(
        alleles=write_ndjson(tmp_path / "alleles.ndjson", alleles),
        observations=write_ndjson(tmp_path / "obs.ndjson", observations),
        output_ttl=out,
        study_id="nf_test",
        crosswalk_path=write_crosswalk(tmp_path / "cw.tsv", crosswalk),
        consequence_lookup=CONSEQUENCE_LOOKUP,
        classification_lookup=CLASSIFICATION_LOOKUP,
    )
    graph = Graph()
    graph.parse(out, format="turtle")
    return graph, builder


def test_variant_node_carries_only_context_free_facts(tmp_path):
    graph, _ = build(tmp_path, [ALLELE], [observation("S1")],
                     [("S1", "SPEC-1", "IND-1", "strip_last_segment")])
    variant = variant_iri(VRS_ID)

    assert (variant, RDF.type, BIOLINK.SequenceVariant) in graph
    assert (variant, NF.vrsId, Literal(VRS_ID, datatype=XSD.string)) in graph
    assert (variant, NF.variantStart, Literal(44908821)) in graph
    assert (variant, NF.variantEnd, Literal(44908822)) in graph
    assert (variant, NF.variantState, Literal("T", datatype=XSD.string)) in graph

    # The whole point of the split: no sample, specimen, gene or depth on the allele.
    leaked = {
        NF.tumorSampleBarcode, NF.fromSpecimen, NF.fromIndividual, NF.affectedGeneSymbol,
        NF.tumorAltCount, NF.aminoacidChange, NF.variantClassification, NF.hasConsequence,
    }
    assert not (set(graph.predicates(variant, None)) & leaked)


def test_one_allele_two_samples_stays_one_variant_node(tmp_path):
    graph, builder = build(
        tmp_path, [ALLELE], [observation("S1"), observation("S2")],
        [("S1", "SPEC-1", "IND-1", "strip_last_segment"),
         ("S2", "SPEC-2", "IND-2", "strip_last_segment")],
    )
    assert len(set(graph.subjects(RDF.type, BIOLINK.SequenceVariant))) == 1
    assert len(set(graph.subjects(RDF.type, NF.VariantObservation))) == 2
    assert builder.counts["observations"] == 2
    # Both specimens reach the shared allele.
    for spec in ("SPEC-1", "SPEC-2"):
        obs = list(graph.objects(specimen_iri(spec), NF.hasVariantObservation))
        assert len(obs) == 1
        assert (obs[0], NF.observesVariant, variant_iri(VRS_ID)) in graph


def test_observation_links_to_specimen_and_individual(tmp_path):
    graph, builder = build(tmp_path, [ALLELE], [observation("S1")],
                           [("S1", "SPEC-1", "IND-1", "strip_last_segment")])
    obs = next(iter(graph.subjects(RDF.type, NF.VariantObservation)))
    assert (obs, NF.fromSpecimen, specimen_iri("SPEC-1")) in graph
    assert (obs, NF.fromIndividual, individual_iri("IND-1")) in graph
    assert (specimen_iri("SPEC-1"), NF.hasVariantObservation, obs) in graph
    assert builder.counts["observations_with_specimen"] == 1
    assert builder.counts["observations_with_individual"] == 1


def test_multi_term_consequence_becomes_several_so_links(tmp_path):
    # 1,950 real rows carry more than one SO term in the single Consequence cell.
    record = observation("S1", molecularConsequence=[
        "splice_region_variant", "splice_polypyrimidine_tract_variant", "intron_variant",
    ])
    graph, builder = build(tmp_path, [ALLELE], [record],
                           [("S1", "SPEC-1", "IND-1", "strip_last_segment")])
    obs = next(iter(graph.subjects(RDF.type, NF.VariantObservation)))
    assert set(graph.objects(obs, NF.hasConsequence)) == {
        so_iri("SO:0001630"), so_iri("SO:0002169"), so_iri("SO:0001627"),
    }
    assert not builder.unmapped_consequences


def test_classification_is_the_fallback_when_consequence_is_absent(tmp_path):
    # In nst_nfosi_ntap this is exactly the 16 IGR rows.
    record = observation("S1", molecularConsequence=[], variantClassification="IGR")
    graph, builder = build(tmp_path, [ALLELE], [record],
                           [("S1", "SPEC-1", "IND-1", "strip_last_segment")])
    obs = next(iter(graph.subjects(RDF.type, NF.VariantObservation)))
    assert set(graph.objects(obs, NF.hasConsequence)) == {so_iri("SO:0001628")}
    assert builder.counts["consequence_from_classification"] == 1


def test_unmapped_consequence_is_reported_not_swallowed(tmp_path):
    record = observation("S1", molecularConsequence=["not_a_real_so_term"])
    _, builder = build(tmp_path, [ALLELE], [record],
                       [("S1", "SPEC-1", "IND-1", "strip_last_segment")])
    assert builder.unmapped_consequences["not_a_real_so_term"] == 1


def test_unresolved_barcode_keeps_the_observation(tmp_path):
    graph, builder = build(tmp_path, [ALLELE], [observation("S-ORPHAN")], [])
    obs = next(iter(graph.subjects(RDF.type, NF.VariantObservation)))
    # Kept and traceable, just unattached -- an orphan beats a silent drop.
    assert (obs, NF.tumorSampleBarcode, Literal("S-ORPHAN", datatype=XSD.string)) in graph
    assert (obs, NF.observesVariant, variant_iri(VRS_ID)) in graph
    assert not list(graph.objects(obs, NF.fromSpecimen))
    assert builder.counts["observations_without_specimen"] == 1
    assert builder.counts["observations_with_specimen"] == 0


def test_unnormalized_variant_is_kept_and_flagged(tmp_path):
    unnormalized = {
        "type": "UnnormalizedVariant",
        "id": "nf:variant/GRCh37:9:1000:C:T",
        "unnormalized": True,
        "assemblyId": "GRCh37",
        "sourceContig": "9",
        "sourcePos": 1000,
        "referenceBases": "C",
        "alternateBases": "T",
        "reason": "MAF NCBI_Build 'GRCh37' != seqmap assembly 'GRCh38'",
    }
    graph, builder = build(tmp_path, [ALLELE, unnormalized], [observation("S1")],
                           [("S1", "SPEC-1", "IND-1", "strip_last_segment")])
    node = variant_iri("nf:variant/GRCh37:9:1000:C:T")
    assert (node, RDF.type, BIOLINK.SequenceVariant) in graph
    assert (node, NF.unnormalizedVariant, Literal(True)) in graph
    # It must NOT claim a VRS id -- that is the whole distinction.
    assert not list(graph.objects(node, NF.vrsId))
    assert builder.counts["variants_unnormalized"] == 1
    assert builder.counts["variants"] == 1


def test_not_fully_justified_indel_is_flagged(tmp_path):
    allele = dict(ALLELE, fullyJustified=False)
    graph, builder = build(tmp_path, [allele], [observation("S1")],
                           [("S1", "SPEC-1", "IND-1", "strip_last_segment")])
    assert (variant_iri(VRS_ID), NF.fullyJustified, Literal(False)) in graph
    assert builder.counts["variants_not_fully_justified"] == 1


def test_fully_justified_variants_carry_no_flag(tmp_path):
    # Absent rather than true, so the predicate's presence alone counts the bad ones.
    graph, builder = build(tmp_path, [ALLELE], [observation("S1")],
                           [("S1", "SPEC-1", "IND-1", "strip_last_segment")])
    assert not list(graph.objects(variant_iri(VRS_ID), NF.fullyJustified))
    assert builder.counts["variants_not_fully_justified"] == 0


def test_manual_crosswalk_rows_are_honoured(tmp_path):
    # A hand-authored row must win, since it exists precisely to fix what the rule
    # could not derive.
    graph, builder = build(tmp_path, [ALLELE], [observation("WEIRD-BARCODE")],
                           [("WEIRD-BARCODE", "SPEC-9", "IND-9", "manual")])
    obs = next(iter(graph.subjects(RDF.type, NF.VariantObservation)))
    assert (obs, NF.fromSpecimen, specimen_iri("SPEC-9")) in graph
    assert builder.counts["observations_with_specimen"] == 1


def test_observation_iri_is_stable_across_runs(tmp_path):
    crosswalk = [("S1", "SPEC-1", "IND-1", "strip_last_segment")]
    runs = []
    for name in ("a", "b"):
        run_dir = tmp_path / name
        run_dir.mkdir()
        graph, _ = build(run_dir, [ALLELE], [observation("S1")], crosswalk)
        runs.append(set(graph.subjects(RDF.type, NF.VariantObservation)))
    assert runs[0] == runs[1], (
        "observation IRIs must be deterministic, or every rebuild churns the whole layer"
    )


def test_dataset_provenance_node_is_emitted(tmp_path):
    graph, _ = build(tmp_path, [ALLELE], [observation("S1")],
                     [("S1", "SPEC-1", "IND-1", "strip_last_segment")])
    obs = next(iter(graph.subjects(RDF.type, NF.VariantObservation)))
    dataset = NF["variantDataset/nf_test"]
    assert (obs, NF.fromVariantDataset, dataset) in graph
