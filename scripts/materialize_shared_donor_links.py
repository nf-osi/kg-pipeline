"""Materialize derived sharedDonor links after core RDF generation.

sharedDonor is only asserted when an animal model's transplantation donor
matches a cell line's donor. This avoids implying that every donor-linked
resource participates in a shared-donor cross-resource match.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from rdflib import Graph, Namespace


NF = Namespace("http://nf-osi.github.com/terms#")

CONSTRUCT_QUERY = """
PREFIX nf: <http://nf-osi.github.com/terms#>

CONSTRUCT {
  ?animal nf:sharedDonor ?donor .
  ?cell nf:sharedDonor ?donor .
}
WHERE {
  ?animal a nf:AnimalModel ;
          nf:transplantationDonorId ?donor .

  ?cell a nf:CellLine ;
        nf:donorId ?donor .
}
"""


def materialize_shared_donor_links(
    cell_lines_ttl: Path,
    animal_models_ttl: Path,
    output_ttl: Path,
) -> Path:
    """Build derived sharedDonor triples from existing RDF."""
    from reasonable import PyReasoner

    reasoner = PyReasoner()
    reasoner.load_file(str(cell_lines_ttl))
    reasoner.load_file(str(animal_models_ttl))

    graph = Graph()
    for triple in reasoner.reason():
        graph.add(triple)
    graph.bind("nf", NF)

    derived = graph.query(CONSTRUCT_QUERY).graph
    derived.bind("nf", NF)

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
        "--animal-models",
        default="data/rdf/animal_models.ttl",
        type=Path,
        help="Path to animal model RDF Turtle",
    )
    parser.add_argument(
        "--output",
        default="data/rdf/shared_donor_links.ttl",
        type=Path,
        help="Output path for derived sharedDonor Turtle",
    )
    args = parser.parse_args()

    materialize_shared_donor_links(
        cell_lines_ttl=args.cell_lines,
        animal_models_ttl=args.animal_models,
        output_ttl=args.output,
    )


if __name__ == "__main__":
    main()
