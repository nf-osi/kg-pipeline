#!/usr/bin/env python3
"""Materialize `nf:mutationVrsId` from `mappings/model_mutation_vrs.tsv`.

Turns the minted digests (scripts/mint_model_mutation_vrs.py) into triples on the
curated `nf:Mutation` nodes, upgrading the model<->patient join from a protein-string
comparison to allele identity:

    ?mutation nf:mutationVrsId ?vrs .          # curated model mutation
    ?variant  nf:vrsId         ?vrs .          # patient allele, somatic variant layer

## A literal, not an edge to the allele node

The patient-side allele node's own IRI is `ga4gh:VA.<digest>`, so emitting
`?mutation nf:hasAllele <ga4gh:VA...>` would be tempting and would be wrong here: 36
of the 37 minted alleles are not observed in any of these cohorts, so it would mint 36
allele nodes that exist only to be pointed at, and `?v a biolink:SequenceVariant`
would stop meaning "observed in a patient specimen". A literal joins just as well and
asserts nothing that was not measured.

## Kept distinct from nf:vrsId

Same identifier space, different subject and different provenance: `nf:vrsId` is
minted from a sequenced sample's MAF row, `nf:mutationVrsId` from a curator's ClinVar
expression resolved through NCBI. Collapsing them onto one predicate would make
"which alleles were observed in a patient" unanswerable without also knowing the
subject's type.

Rows that did not resolve to a digest carry no triple -- their absence is recorded in
the TSV's `evidence` column, which is where an unresolved row belongs.

Usage:
    python scripts/materialize_model_mutation_vrs.py
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import XSD

REPO_ROOT = Path(__file__).resolve().parent.parent
NF = Namespace("http://nf-osi.github.com/terms#")

DEFAULT_INPUT = REPO_ROOT / "mappings" / "model_mutation_vrs.tsv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "rdf" / "model_mutation_vrs.ttl"

#: Matches mappings/rml/mutations.rml.ttl's subject template. Kept as one constant so
#: an IRI change there is a one-line change here rather than a silent orphan.
MUTATION_IRI = "http://nf-osi.github.com/terms#mutation/{}"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        rows = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(rows, delimiter="\t"))


def build_graph(rows: list[dict[str, str]]) -> Graph:
    graph = Graph()
    graph.bind("nf", NF)
    for row in rows:
        if not row["vrs_id"]:
            continue
        mutation = URIRef(MUTATION_IRI.format(row["mutation_id"]))
        graph.add((mutation, NF.mutationVrsId,
                   Literal(row["vrs_id"], datatype=XSD.string)))
    return graph


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    rows = read_rows(args.input)
    graph = build_graph(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=args.output, format="turtle")

    evidence = Counter(r["evidence"] for r in rows if r["vrs_id"])
    print(f"wrote {args.output}: {len(graph)} triples over "
          f"{len({r['vrs_id'] for r in rows if r['vrs_id']})} distinct alleles; "
          f"{sum(1 for r in rows if not r['vrs_id'])} rows had no digest")
    print("  evidence: " + ", ".join(f"{k}={v}" for k, v in sorted(evidence.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
