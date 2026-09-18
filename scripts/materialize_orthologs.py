#!/usr/bin/env python3
"""Materialize `nf:hasOrtholog` edges from `mappings/orthologs.tsv`.

Core graph, not part of the reversible variant layer: the edges say something about
genes, and they stay whether or not any variant layer is published. Tens of triples,
so this lives in the default `data/rdf/*.ttl` glob rather than a gated subdirectory.

## What it emits, and what it deliberately does not

    <https://identifiers.org/hgnc:7765>  nf:hasOrtholog  <https://identifiers.org/MGI:97306>
    <https://identifiers.org/MGI:97306>  nf:orthologOf   <https://identifiers.org/hgnc:7765>
    <https://identifiers.org/MGI:97306>  a nf:ModelOrganismGene ;
        nf:geneSymbol "Nf1" ; rdfs:label "Nf1" ; nf:species "Mus musculus" .

The model-organism node is typed `nf:ModelOrganismGene`, **not** `biolink:Gene`.
`biolink:Gene` in this graph means a human, HGNC-keyed gene node from the variant layer
(39,160 of them), and every per-gene count in docs/demos/variant-layer-demo.md is a
count over that set. QLever does no OWL reasoning, so declaring the subclass in the
ontology -- which is done, because a mouse gene *is* a gene -- leaves `?s a
biolink:Gene` matching only the human set, which is what those counts mean. The
opposite choice is `materialize_specimens.py`'s: it emits both types explicitly
*because* it wants `?s a biolink:MaterialSample` to match. Same fact about the
indexer, opposite decision, for opposite reasons.

The human side is the node the variant layer already uses, so an ortholog edge lands
directly on a gene the somatic layer can reach -- no lookup table at query time. The
model-organism symbol is carried as a label only: joining curated mutations by bare
symbol is what the gene constraint exists to prevent, and here the symbol is only ever
matched *within* an already-established ortholog pair.

Usage:
    python scripts/materialize_orthologs.py
    python scripts/materialize_orthologs.py --orthologs mappings/orthologs.tsv \
        --output data/rdf/orthologs.ttl
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD

REPO_ROOT = Path(__file__).resolve().parent.parent
NF = Namespace("http://nf-osi.github.com/terms#")

DEFAULT_ORTHOLOGS = REPO_ROOT / "mappings" / "orthologs.tsv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "rdf" / "orthologs.ttl"

#: The prefix is used VERBATIM: identifiers.org serves `MGI:97306` and 404s on
#: `mgi:97306` (ZFIN accepts either). Lower-casing to look tidy would break the MGI half.
IDENTIFIERS_IRI = "https://identifiers.org/{}"


def read_orthologs(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        rows = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(rows, delimiter="\t"))


def build_graph(rows: list[dict[str, str]]) -> Graph:
    graph = Graph()
    graph.bind("nf", NF)

    for row in rows:
        if row["status"] != "ortholog":
            continue
        human = URIRef(row["human_iri"])
        model = URIRef(IDENTIFIERS_IRI.format(row["model_gene_id"]))

        graph.add((human, NF.hasOrtholog, model))
        graph.add((model, NF.orthologOf, human))
        graph.add((model, RDF.type, NF.ModelOrganismGene))
        graph.add((model, RDFS.label, Literal(row["model_gene_symbol"])))
        graph.add((model, NF.geneSymbol,
                   Literal(row["model_gene_symbol"], datatype=XSD.string)))
        graph.add((model, NF.species,
                   Literal(row["model_species"], datatype=XSD.string)))
    return graph


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--orthologs", type=Path, default=DEFAULT_ORTHOLOGS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    rows = read_orthologs(args.orthologs)
    graph = build_graph(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=args.output, format="turtle")

    pairs = sum(1 for r in rows if r["status"] == "ortholog")
    models = len({r["model_gene_id"] for r in rows if r["status"] == "ortholog"})
    humans = len({r["human_iri"] for r in rows if r["status"] == "ortholog"})
    print(f"wrote {args.output}: {len(graph)} triples, "
          f"{pairs} ortholog pairs ({models} model genes -> {humans} human genes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
