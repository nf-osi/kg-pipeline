import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.materialize_observation_links import materialize_observation_links


NF = Namespace("http://nf-osi.github.com/terms#")


def test_materialize_observation_links_joins_on_resource_id(tmp_path):
    resources_ttl = tmp_path / "resources.ttl"
    observations_ttl = tmp_path / "observations.ttl"
    output_ttl = tmp_path / "observation_links.ttl"

    resource_graph = Graph()
    resource_graph.bind("nf", NF)
    cell_1 = NF["cellLine/test-cell-1"]
    cell_2 = NF["cellLine/test-cell-2"]

    resource_graph.add((cell_1, RDF.type, NF.CellLine))
    resource_graph.add((cell_1, NF.resourceId, Literal("res-1")))
    resource_graph.add((cell_2, RDF.type, NF.CellLine))
    resource_graph.add((cell_2, NF.resourceId, Literal("res-2")))
    resource_graph.serialize(destination=resources_ttl, format="turtle")

    obs_graph = Graph()
    obs_graph.bind("nf", NF)
    obs_1 = NF["observation/test-obs-1"]
    obs_2 = NF["observation/test-obs-2"]
    obs_orphan = NF["observation/test-obs-orphan"]

    obs_graph.add((obs_1, RDF.type, NF.Observation))
    obs_graph.add((obs_1, NF.forResourceId, Literal("res-1")))
    obs_graph.add((obs_1, NF.observationText, Literal("First observation about cell 1.")))

    obs_graph.add((obs_2, RDF.type, NF.Observation))
    obs_graph.add((obs_2, NF.forResourceId, Literal("res-1")))
    obs_graph.add((obs_2, NF.observationText, Literal("Second observation about cell 1.")))

    obs_graph.add((obs_orphan, RDF.type, NF.Observation))
    obs_graph.add((obs_orphan, NF.forResourceId, Literal("res-missing")))
    obs_graph.add((obs_orphan, NF.observationText, Literal("Orphaned observation, no matching resource.")))
    obs_graph.serialize(destination=observations_ttl, format="turtle")

    materialize_observation_links(resources_ttl, observations_ttl, output_ttl)

    derived = Graph()
    derived.parse(output_ttl, format="turtle")

    assert (cell_1, NF.hasObservation, obs_1) in derived
    assert (cell_1, NF.hasObservation, obs_2) in derived
    assert (obs_1, NF.aboutResource, cell_1) in derived
    assert (obs_2, NF.aboutResource, cell_1) in derived
    assert len(list(derived.triples((cell_2, NF.hasObservation, None)))) == 0
    assert len(list(derived.triples((None, NF.hasObservation, obs_orphan)))) == 0
    assert len(list(derived.triples((obs_orphan, NF.aboutResource, None)))) == 0
