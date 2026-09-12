"""Project vrsify's NDJSON streams into the somatic variant RDF layer.

Part of the variant layer PoC (nf-osi/kg-pipeline#95). See `docs/variant-layer.md`.

`vrsify` (`~/sage/nf/vrsify`) reads a cBioPortal MAF and emits two NDJSON streams --
context-free GA4GH VRS alleles, and one observation per tumour sample. It deliberately
emits JSON only; turning that into RDF is this repo's job, and this is that step.

## The two-layer split, and why it is load-bearing

    biolink:SequenceVariant   <- one node per allele, shared by every sample carrying it
        ^ nf:observesVariant
    nf:VariantObservation     <- one node per (sample, allele)
        v nf:fromSpecimen        v nf:affectsGene
    nf:Specimen              biolink:Gene   <- both in the core graph

`nf:affectsGene` hangs off the observation, not the variant, because the gene
association comes from the transcript the caller picked -- it is annotation, not
identity. The same allele annotated against a different transcript could name a
different gene.

Nothing sample-specific may touch the variant node. That is what lets the same allele
seen in two studies -- or later in ClinVar or gnomAD -- collapse to one node, which is
the entire reason for computing VRS identifiers instead of using chrom:pos:ref:alt.
In `nst_nfosi_ntap` this collapse is real but modest: 23,741 rows over 23,181 distinct
alleles, so ~560 observations are recurrences of an allele already seen.

## Output location is the feature switch

Output goes to `data/rdf/variants/`, NOT `data/rdf/`. Both the QLever index
(`data/rdf/*.ttl` in the Dockerfile) and the embedding edgelist
(`rdf_to_edgelist.py`, same glob) are non-recursive, so this layer is excluded from
both by default and has to be opted into explicitly. That satisfies two of the issue's
requirements -- reversible ingest, and keep variants out of the embeddings -- with a
directory choice rather than a flag threaded through two pipelines.

## Nothing is dropped

Rows vrsify could not give a VRS identity (contig missing from the seqmap, assembly
disagreeing with the source, non-nucleotide alleles) arrive as `UnnormalizedVariant`
records and become variant nodes flagged `nf:unnormalizedVariant true`, keyed on
`assembly:chrom:pos:ref:alt`. Observations whose barcode did not resolve to a portal
specimen are still emitted, carrying `nf:tumorSampleBarcode` alone. Both counts are
reported, and `--require-specimen-coverage` can make a regression in the crosswalk fail
the build rather than quietly shrink the layer.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

sys.path.insert(0, str(Path(__file__).resolve().parent))

from map_cbioportal_samples import load_crosswalk  # noqa: E402
from materialize_genes import gene_iri  # noqa: E402
from materialize_specimens import individual_iri, specimen_iri  # noqa: E402

NF = Namespace("http://nf-osi.github.com/terms#")
BIOLINK = Namespace("https://w3id.org/biolink/vocab/")
OBO = Namespace("http://purl.obolibrary.org/obo/")
VOID = Namespace("http://rdfs.org/ns/void#")

CBIOPORTAL_STUDY_URL = "https://www.cbioportal.org/study/summary?id={study_id}"


def load_sssom(path: Path) -> dict[str, tuple[str, str]]:
    """Read an SSSOM lookup as ``{subject_label: (object_id, predicate_id)}``."""
    with open(path, newline="") as handle:
        rows = [line for line in handle if not line.startswith("#")]
    out: dict[str, tuple[str, str]] = {}
    for row in csv.DictReader(rows, delimiter="\t"):
        label = (row.get("subject_label") or "").strip()
        target = (row.get("object_id") or "").strip()
        if label and target:
            out[label] = (target, (row.get("predicate_id") or "").strip())
    return out


def so_iri(curie: str) -> URIRef:
    """`SO:0001583` -> the OBO IRI, matching how obo: terms appear elsewhere."""
    return OBO[curie.replace(":", "_")]


def variant_iri(record_id: str) -> URIRef:
    """IRI for a variant node, from vrsify's id for it.

    Normalized alleles arrive as `ga4gh:VA.<digest>`; the digest becomes the local name
    so the node is keyed by VRS identity and collapses across sources. Unnormalized rows
    arrive as `nf:variant/<assembly>:<chrom>:<pos>:<ref>:<alt>`, whose local part is
    percent-encoded because it contains colons and may contain `-`/`*`.

    A resolvable `ga4gh:` namespace does not exist, so rather than mint an IRI that
    404s, the node lives under nf: and carries the canonical CURIE in nf:vrsId.
    """
    if record_id.startswith("ga4gh:"):
        return NF[f"variant/{quote(record_id.split(':', 1)[1], safe='.')}"]
    if record_id.startswith("nf:variant/"):
        return NF[f"variant/{quote(record_id[len('nf:variant/'):], safe='')}"]
    return NF[f"variant/{quote(record_id, safe='')}"]


def observation_iri(study_id: str, barcode: str, variant_node: URIRef) -> URIRef:
    """Deterministic IRI for one (study, tumour sample, allele) observation."""
    local = str(variant_node).rsplit("/", 1)[-1]
    return NF[f"variantObservation/{study_id}/{quote(barcode, safe='')}/{local}"]


def add_variant(graph: Graph, record: dict) -> URIRef:
    """Emit one variant node. Returns its IRI."""
    node = variant_iri(record.get("id", ""))
    graph.add((node, RDF.type, BIOLINK.SequenceVariant))

    if record.get("type") == "UnnormalizedVariant":
        graph.add((node, NF.unnormalizedVariant, Literal(True)))
        # Keep the coordinates that make the row identifiable even without VRS identity.
        if record.get("assemblyId"):
            graph.add((node, NF.assemblyId, Literal(record["assemblyId"], datatype=XSD.string)))
        if record.get("sourceContig"):
            graph.add((node, NF.sourceContig, Literal(record["sourceContig"], datatype=XSD.string)))
        if record.get("sourcePos") is not None:
            graph.add((node, NF.sourcePos, Literal(int(record["sourcePos"]))))
        if record.get("reason"):
            graph.add((node, RDFS.comment, Literal(record["reason"])))
        return node

    graph.add((node, NF.vrsId, Literal(record["id"], datatype=XSD.string)))
    location = record.get("location") or {}
    sequence_reference = location.get("sequenceReference") or {}
    if sequence_reference.get("refgetAccession"):
        graph.add(
            (node, NF.refgetAccession,
             Literal(sequence_reference["refgetAccession"], datatype=XSD.string))
        )
    if location.get("start") is not None:
        graph.add((node, NF.variantStart, Literal(int(location["start"]))))
    if location.get("end") is not None:
        graph.add((node, NF.variantEnd, Literal(int(location["end"]))))
    state = record.get("state") or {}
    if "sequence" in state:
        graph.add((node, NF.variantState, Literal(state["sequence"], datatype=XSD.string)))
    # Present only when false: an indel whose id was computed without a reference and so
    # will not match vrs-python/ClinVar. Substitutions never carry it.
    if record.get("fullyJustified") is False:
        graph.add((node, NF.fullyJustified, Literal(False)))
    return node


#: Straight literal copies from the observation JSON, with their RDF datatypes.
STRING_FIELDS = [
    ("tumorSampleBarcode", NF.tumorSampleBarcode),
    ("matchedNormalSampleBarcode", NF.matchedNormalSampleBarcode),
    ("mutationStatus", NF.mutationStatus),
    ("assemblyId", NF.assemblyId),
    ("referenceName", NF.referenceName),
    ("sourceContig", NF.sourceContig),
    ("variantClassification", NF.variantClassification),
    ("variantType", NF.variantType),
    ("variantImpact", NF.variantImpact),
    ("affectedGeneSymbol", NF.affectedGeneSymbol),
    ("affectedGene", NF.ensemblGeneId),
    ("entrezGeneId", NF.entrezGeneId),
    ("hgncId", NF.hgncId),
    ("transcriptId", NF.transcriptId),
    ("aminoacidChange", NF.aminoacidChange),
    ("hgvsC", NF.hgvsC),
    ("hgvsP", NF.hgvsP),
    ("proteinPosition", NF.proteinPosition),
    ("exonNumber", NF.exonNumber),
]
INTEGER_FIELDS = [
    ("sourcePos", NF.sourcePos),
    ("tumorDepth", NF.tumorDepth),
    ("tumorRefCount", NF.tumorRefCount),
    ("tumorAltCount", NF.tumorAltCount),
    ("normalDepth", NF.normalDepth),
    ("normalRefCount", NF.normalRefCount),
    ("normalAltCount", NF.normalAltCount),
]
DOUBLE_FIELDS = [
    ("variantAlleleFrequency", NF.variantAlleleFrequency),
    ("gnomadAlleleFrequency", NF.gnomadAlleleFrequency),
]


class VariantRdfBuilder:
    def __init__(
        self,
        study_id: str,
        crosswalk: dict[str, dict],
        consequences: dict[str, tuple[str, str]],
        classifications: dict[str, tuple[str, str]],
        source_url: str = "",
    ) -> None:
        self.study_id = study_id
        self.crosswalk = crosswalk
        self.consequences = consequences
        self.classifications = classifications
        self.source_url = source_url
        self.graph = Graph()
        for prefix, ns in (("nf", NF), ("biolink", BIOLINK), ("obo", OBO), ("void", VOID)):
            self.graph.bind(prefix, ns)
        self.dataset = NF[f"variantDataset/{study_id}"]
        self.counts: Counter = Counter()
        self.unmapped_consequences: Counter = Counter()

        self.graph.add((self.dataset, RDF.type, VOID.Dataset))
        self.graph.add((self.dataset, RDFS.label, Literal(f"cBioPortal study {study_id}")))
        self.graph.add(
            (self.dataset, VOID.dataDump,
             URIRef(CBIOPORTAL_STUDY_URL.format(study_id=study_id)))
        )
        if source_url:
            self.graph.add((self.dataset, RDFS.comment, Literal(source_url)))

    # -- variants -------------------------------------------------------------

    def add_variants(self, alleles_ndjson: Path) -> None:
        for record in read_ndjson(alleles_ndjson):
            add_variant(self.graph, record)
            if record.get("type") == "UnnormalizedVariant":
                self.counts["variants_unnormalized"] += 1
            else:
                self.counts["variants"] += 1
                if record.get("fullyJustified") is False:
                    self.counts["variants_not_fully_justified"] += 1

    # -- observations ---------------------------------------------------------

    def resolve_consequences(self, record: dict) -> list[URIRef]:
        """SO terms for an observation.

        Prefers the MAF `Consequence` list (already SO term names); falls back to
        `Variant_Classification` only when `Consequence` is absent, which in
        nst_nfosi_ntap is exactly the 16 IGR rows.
        """
        terms = record.get("molecularConsequence") or []
        if isinstance(terms, str):
            terms = [terms]
        iris: list[URIRef] = []
        for term in terms:
            mapping = self.consequences.get(term)
            if mapping:
                iris.append(so_iri(mapping[0]))
            else:
                self.unmapped_consequences[term] += 1
        if iris:
            return iris

        classification = record.get("variantClassification")
        mapping = self.classifications.get(classification) if classification else None
        if mapping:
            self.counts["consequence_from_classification"] += 1
            return [so_iri(mapping[0])]
        if classification:
            self.unmapped_consequences[f"Variant_Classification={classification}"] += 1
        return []

    def add_observation(self, record: dict) -> None:
        barcode = record.get("tumorSampleBarcode") or record.get("biosample") or ""
        variant_node = variant_iri(record.get("variant", ""))
        node = observation_iri(self.study_id, barcode, variant_node)

        self.graph.add((node, RDF.type, NF.VariantObservation))
        self.graph.add((node, NF.observesVariant, variant_node))
        self.graph.add((node, NF.fromVariantDataset, self.dataset))
        self.counts["observations"] += 1

        for key, predicate in STRING_FIELDS:
            value = record.get(key)
            if value not in (None, ""):
                self.graph.add((node, predicate, Literal(str(value), datatype=XSD.string)))
        for key, predicate in INTEGER_FIELDS:
            if record.get(key) is not None:
                self.graph.add((node, predicate, Literal(int(record[key]))))
        for key, predicate in DOUBLE_FIELDS:
            if record.get(key) is not None:
                self.graph.add((node, predicate, Literal(float(record[key]))))
        for dbsnp in record.get("dbsnpId") or []:
            self.graph.add((node, NF.dbsnpId, Literal(dbsnp, datatype=XSD.string)))

        for consequence in self.resolve_consequences(record):
            self.graph.add((node, NF.hasConsequence, consequence))

        # Link to the core gene layer. Keyed on the Ensembl gene id, which is the only
        # MAF gene column that is internally consistent (see materialize_genes.py).
        ensembl = record.get("affectedGene")
        if ensembl:
            self.graph.add((node, NF.affectsGene, gene_iri(ensembl)))
            self.counts["observations_with_gene"] += 1
        else:
            self.counts["observations_without_gene"] += 1

        # Join to the core specimen layer via the reviewed crosswalk.
        mapping = self.crosswalk.get(barcode)
        if mapping and mapping.get("specimen_id"):
            specimen = specimen_iri(mapping["specimen_id"])
            self.graph.add((node, NF.fromSpecimen, specimen))
            self.graph.add((specimen, NF.hasVariantObservation, node))
            self.counts["observations_with_specimen"] += 1
            if mapping.get("individual_id"):
                self.graph.add((node, NF.fromIndividual, individual_iri(mapping["individual_id"])))
                self.counts["observations_with_individual"] += 1
        else:
            # Kept, but unattached: better an orphan observation than a silent drop.
            self.counts["observations_without_specimen"] += 1

    def add_observations(self, observations_ndjson: Path) -> None:
        for record in read_ndjson(observations_ndjson):
            self.add_observation(record)


def read_ndjson(path: Path):
    with open(path) as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{number}: invalid JSON: {exc}") from exc


def variants_to_rdf(
    alleles: Path,
    observations: Path,
    output_ttl: Path,
    study_id: str,
    crosswalk_path: Path,
    consequence_lookup: Path,
    classification_lookup: Path,
    source_url: str = "",
) -> VariantRdfBuilder:
    builder = VariantRdfBuilder(
        study_id=study_id,
        crosswalk=load_crosswalk(crosswalk_path, study_id),
        consequences=load_sssom(consequence_lookup),
        classifications=load_sssom(classification_lookup),
        source_url=source_url,
    )
    builder.add_variants(alleles)
    builder.add_observations(observations)
    output_ttl.parent.mkdir(parents=True, exist_ok=True)
    builder.graph.serialize(destination=output_ttl, format="turtle")
    return builder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--alleles", type=Path, required=True, help="vrsify alleles NDJSON")
    parser.add_argument("--observations", type=Path, required=True, help="vrsify observations NDJSON")
    parser.add_argument("--study-id", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output Turtle (default data/rdf/variants/<study-id>.ttl, matching what "
             "the Dagster asset writes). Deliberately a SUBdirectory of data/rdf, so "
             "the core index and the embedding edgelist -- which both glob "
             "data/rdf/*.ttl non-recursively -- exclude it.",
    )
    parser.add_argument(
        "--crosswalk",
        type=Path,
        default=Path("mappings/cbioportal_sample_specimen.tsv"),
        help="Sample-to-specimen crosswalk from scripts/map_cbioportal_samples.py",
    )
    parser.add_argument(
        "--consequence-lookup",
        type=Path,
        default=Path("mappings/sssom/variant_consequence.sssom.tsv"),
    )
    parser.add_argument(
        "--classification-lookup",
        type=Path,
        default=Path("mappings/sssom/variant_classification.sssom.tsv"),
    )
    parser.add_argument("--source-url", default="", help="Provenance note for the source file")
    parser.add_argument(
        "--require-specimen-coverage",
        type=float,
        default=None,
        metavar="FRACTION",
        help="Fail if fewer than this fraction of observations resolve to a specimen "
             "(e.g. 0.9). Off by default; set it in CI to catch crosswalk regressions.",
    )
    args = parser.parse_args(argv)
    output = args.output or Path("data/rdf/variants") / f"{args.study_id}.ttl"

    builder = variants_to_rdf(
        alleles=args.alleles,
        observations=args.observations,
        output_ttl=output,
        study_id=args.study_id,
        crosswalk_path=args.crosswalk,
        consequence_lookup=args.consequence_lookup,
        classification_lookup=args.classification_lookup,
        source_url=args.source_url,
    )

    counts = builder.counts
    observations = counts["observations"] or 1
    coverage = counts["observations_with_specimen"] / observations
    print(f"study                        {args.study_id}")
    print(f"variant nodes                {counts['variants']}")
    print(f"  not fully justified        {counts['variants_not_fully_justified']}")
    print(f"unnormalized variant nodes   {counts['variants_unnormalized']}")
    print(f"observations                 {counts['observations']}")
    print(f"  linked to a specimen       {counts['observations_with_specimen']} ({coverage:.1%})")
    print(f"  linked to an individual    {counts['observations_with_individual']}")
    print(f"  NOT linked to a specimen   {counts['observations_without_specimen']}")
    print(f"  linked to a gene           {counts['observations_with_gene']}")
    print(f"  NOT linked to a gene       {counts['observations_without_gene']}")
    print(f"consequence via fallback     {counts['consequence_from_classification']}")
    print(f"triples                      {len(builder.graph)}")
    print(f"output                       {output}")
    if builder.unmapped_consequences:
        print("UNMAPPED consequence terms (add to the SSSOM lookup):")
        for term, n in builder.unmapped_consequences.most_common():
            print(f"    {term}\t{n}")

    if args.require_specimen_coverage is not None and coverage < args.require_specimen_coverage:
        print(
            f"FAIL specimen coverage {coverage:.1%} < required "
            f"{args.require_specimen_coverage:.1%}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
