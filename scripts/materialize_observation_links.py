"""Materialize derived hasObservation / aboutResource links after core RDF generation.

nf:Observation only links back to its resource via nf:forResourceId, a string
that must be joined against nf:resourceId on the resource -- there is no
direct edge. This flattens that join into nf:hasObservation (resource ->
observation) and its inverse nf:aboutResource (observation -> resource), so
either direction can be found in one hop. Keeping the link to the full
nf:Observation node (rather than copying out observationText) preserves the
ability to filter by observation type and to retrieve provenance (submitter,
publication, phase, ratings).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from rdflib import Graph, Namespace


NF = Namespace("http://nf-osi.github.com/terms#")

CONSTRUCT_QUERY = """
PREFIX nf: <http://nf-osi.github.com/terms#>

CONSTRUCT {
  ?resource nf:hasObservation ?obs .
  ?obs nf:aboutResource ?resource .
}
WHERE {
  ?obs a nf:Observation ;
       nf:forResourceId ?resourceId .

  ?resource nf:resourceId ?resourceId .
}
"""


def materialize_observation_links(
    resources_ttl: Path,
    observations_ttl: Path,
    output_ttl: Path,
) -> Path:
    """Build derived hasObservation/aboutResource triples from existing RDF."""
    graph = Graph()
    graph.parse(resources_ttl, format="turtle")
    graph.parse(observations_ttl, format="turtle")
    graph.bind("nf", NF)

    derived = graph.query(CONSTRUCT_QUERY).graph
    derived.bind("nf", NF)

    output_ttl.parent.mkdir(parents=True, exist_ok=True)
    derived.serialize(destination=output_ttl, format="turtle")
    return output_ttl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resources",
        default="data/rdf/resources.ttl",
        type=Path,
        help="Path to resource RDF Turtle",
    )
    parser.add_argument(
        "--observations",
        default="data/rdf/observations.ttl",
        type=Path,
        help="Path to observation RDF Turtle",
    )
    parser.add_argument(
        "--output",
        default="data/rdf/observation_links.ttl",
        type=Path,
        help="Output path for derived hasObservation Turtle",
    )
    args = parser.parse_args()

    materialize_observation_links(
        resources_ttl=args.resources,
        observations_ttl=args.observations,
        output_ttl=args.output,
    )


if __name__ == "__main__":
    main()
