import sys
from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import RDF

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.materialize_shared_donor_links import materialize_shared_donor_links


NF = Namespace("http://nf-osi.github.com/terms#")


def test_materialize_shared_donor_links_only_for_transplant_matches(tmp_path):
    cell_lines_ttl = tmp_path / "cell_lines.ttl"
    animal_models_ttl = tmp_path / "animal_models.ttl"
    output_ttl = tmp_path / "shared_donor_links.ttl"

    cell_graph = Graph()
    cell_graph.bind("nf", NF)
    cell_1 = NF["resource/test-cell-1"]
    cell_2 = NF["resource/test-cell-2"]
    donor_a = NF["donor/test-donor-a"]
    donor_b = NF["donor/test-donor-b"]

    cell_graph.add((cell_1, RDF.type, NF.CellLine))
    cell_graph.add((cell_1, NF.donorId, donor_a))
    cell_graph.add((cell_2, RDF.type, NF.CellLine))
    cell_graph.add((cell_2, NF.donorId, donor_b))
    cell_graph.serialize(destination=cell_lines_ttl, format="turtle")

    animal_graph = Graph()
    animal_graph.bind("nf", NF)
    animal_1 = NF["resource/test-animal-1"]
    animal_2 = NF["resource/test-animal-2"]

    animal_graph.add((animal_1, RDF.type, NF.AnimalModel))
    animal_graph.add((animal_1, NF.transplantationDonorId, donor_a))
    animal_graph.add((animal_1, NF.donorId, donor_b))

    animal_graph.add((animal_2, RDF.type, NF.AnimalModel))
    animal_graph.add((animal_2, NF.donorId, donor_a))
    animal_graph.serialize(destination=animal_models_ttl, format="turtle")

    materialize_shared_donor_links(cell_lines_ttl, animal_models_ttl, output_ttl)

    derived = Graph()
    derived.parse(output_ttl, format="turtle")

    assert (animal_1, NF.sharedDonor, donor_a) in derived
    assert (cell_1, NF.sharedDonor, donor_a) in derived

    assert (animal_1, NF.sharedDonor, donor_b) not in derived
    assert (animal_2, NF.sharedDonor, donor_a) not in derived
    assert (cell_2, NF.sharedDonor, donor_b) not in derived
