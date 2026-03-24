"""Materialize derived NF1 mutation sets for cell lines after core RDF generation."""

from __future__ import annotations

import argparse
import hashlib
from collections import defaultdict
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF, RDFS


NF = Namespace("http://nf-osi.github.com/terms#")


def _uuid_from_iri(iri) -> str:
    return str(iri).rsplit("/", 1)[-1]


def _mutation_set_iri(mutation_uuids: tuple[str, ...]):
    if not mutation_uuids:
        return NF["mutationSet/nf1_none"]
    joined = "|".join(mutation_uuids)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]
    return NF[f"mutationSet/nf1_{digest}"]


def materialize_nf1_mutation_sets(
    cell_lines_ttl: Path,
    mutations_ttl: Path,
    output_ttl: Path,
    mutation_model_ttl: Path | None = None,
) -> Path:
    """Build derived NF1 mutation set triples from existing RDF."""
    graph = Graph()
    graph.parse(cell_lines_ttl, format="turtle")
    graph.parse(mutations_ttl, format="turtle")
    if mutation_model_ttl and mutation_model_ttl.exists():
        graph.parse(mutation_model_ttl, format="turtle")

    derived = Graph()
    derived.bind("nf", NF)
    derived.bind("rdfs", RDFS)

    mutation_to_gene = {}
    for mutation, _, gene in graph.triples((None, NF.affectedGeneSymbol, None)):
        mutation_to_gene[mutation] = str(gene).strip().lower()

    cell_to_nf1_mutations: dict = defaultdict(set)
    for cell_line, _, mutation in graph.triples((None, NF.hasMutation, None)):
        if (cell_line, RDF.type, NF.CellLine) not in graph:
            continue
        if mutation_to_gene.get(mutation) == "nf1":
            cell_to_nf1_mutations[cell_line].add(mutation)

    all_cell_lines = {
        cell_line
        for cell_line, _, _ in graph.triples((None, RDF.type, NF.CellLine))
    }

    for cell_line in all_cell_lines:
        mutation_iris = sorted(cell_to_nf1_mutations.get(cell_line, set()), key=str)
        mutation_uuids = tuple(_uuid_from_iri(mutation) for mutation in mutation_iris)
        mutation_set = _mutation_set_iri(mutation_uuids)

        derived.add((cell_line, NF.hasNf1MutationSet, mutation_set))
        derived.add((mutation_set, RDF.type, NF.MutationSet))
        derived.add((mutation_set, RDF.type, NF.Nf1MutationSet))
        derived.add((mutation_set, RDFS.label, Literal(f"NF1 mutation set {mutation_set.split('#')[-1]}")))

        uuid_list = ", ".join(mutation_uuids) if mutation_uuids else "(empty)"
        derived.add((
            mutation_set,
            RDFS.comment,
            Literal(f"Derived NF1 mutation set with member mutation UUIDs: {uuid_list}"),
        ))

        for mutation in mutation_iris:
            derived.add((mutation_set, NF.hasMutation, mutation))

    output_ttl.parent.mkdir(parents=True, exist_ok=True)
    derived.serialize(destination=output_ttl, format="turtle")
    return output_ttl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cell-lines",
        default="data/rdf/cell_lines.ttl",
        type=Path,
        help="Path to cell line RDF Turtle",
    )
    parser.add_argument(
        "--mutations",
        default="data/rdf/mutations.ttl",
        type=Path,
        help="Path to mutation RDF Turtle",
    )
    parser.add_argument(
        "--mutation-model",
        default="data/rdf/mutation_model.ttl",
        type=Path,
        help="Path to mutation model RDF Turtle (cell/animal to mutation links)",
    )
    parser.add_argument(
        "--output",
        default="data/rdf/nf1_mutation_sets.ttl",
        type=Path,
        help="Output path for derived NF1 mutation set Turtle",
    )
    args = parser.parse_args()

    materialize_nf1_mutation_sets(
        cell_lines_ttl=args.cell_lines,
        mutations_ttl=args.mutations,
        output_ttl=args.output,
        mutation_model_ttl=args.mutation_model,
    )


if __name__ == "__main__":
    main()
