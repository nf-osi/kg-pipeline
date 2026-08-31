"""Materialize derived hasObservation / aboutResource links after core RDF generation.

nf:Observation only links back to its resource via nf:forResourceId, a string
that must be joined against nf:resourceId on the resource -- there is no
direct edge. The join is kept (rather than templating the resource IRI straight
from the observation's resourceId) because it also filters dangling references:
an observation naming a resourceId that no longer exists produces no link. This flattens that join into nf:hasObservation (resource ->
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

# The nine per-type graphs that together replace the retired resources.ttl.
TOOL_GRAPHS = [
    "cell_lines",
    "animal_models",
    "antibodies",
    "genetic_reagents",
    "biobanks",
    "clinical_assessment_tools",
    "patient_derived_models",
    "organoid_protocols",
    "computational_tools",
]

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
    resources_ttl: Path | list[Path],
    observations_ttl: Path,
    output_ttl: Path,
) -> Path:
    """Build derived hasObservation/aboutResource triples from existing RDF.

    ``resources_ttl`` accepts one path or several. Since upstream retired the
    central Resource table there is no single resources.ttl any more -- tool
    nodes are spread across the nine per-type graphs, so all of them are loaded
    to resolve nf:forResourceId.
    """
    if isinstance(resources_ttl, (str, Path)):
        resources_ttl = [Path(resources_ttl)]

    graph = Graph()
    for resource_ttl in resources_ttl:
        graph.parse(resource_ttl, format="turtle")
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
        default=[Path(f"data/rdf/{name}.ttl") for name in TOOL_GRAPHS],
        nargs="+",
        type=Path,
        help="Paths to the tool-type RDF Turtle files carrying nf:resourceId",
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
