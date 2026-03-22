import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF, RDFS

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.materialize_nf1_mutation_sets import materialize_nf1_mutation_sets


NF = Namespace("http://nf-osi.github.com/terms#")


def test_materialize_nf1_mutation_sets_reuses_stable_set_ids_and_comments(tmp_path):
    cell_lines_ttl = tmp_path / "cell_lines.ttl"
    mutations_ttl = tmp_path / "mutations.ttl"
    output_ttl = tmp_path / "nf1_mutation_sets.ttl"

    cell_graph = Graph()
    cell_graph.bind("nf", NF)
    cell_a = NF["cellLine/test-a"]
    cell_b = NF["cellLine/test-b"]
    cell_c = NF["cellLine/test-c"]
    mut_1 = NF["mutation/11111111-1111-1111-1111-111111111111"]
    mut_2 = NF["mutation/22222222-2222-2222-2222-222222222222"]
    mut_3 = NF["mutation/33333333-3333-3333-3333-333333333333"]

    for cell_line in (cell_a, cell_b, cell_c):
        cell_graph.add((cell_line, RDF.type, NF.CellLine))

    cell_graph.add((cell_a, NF.hasMutation, mut_2))
    cell_graph.add((cell_a, NF.hasMutation, mut_1))
    cell_graph.add((cell_b, NF.hasMutation, mut_1))
    cell_graph.add((cell_b, NF.hasMutation, mut_2))
    cell_graph.add((cell_c, NF.hasMutation, mut_3))
    cell_graph.serialize(destination=cell_lines_ttl, format="turtle")

    mutation_graph = Graph()
    mutation_graph.bind("nf", NF)
    mutation_graph.add((mut_1, RDF.type, NF.Mutation))
    mutation_graph.add((mut_1, NF.affectedGeneSymbol, Literal("NF1")))
    mutation_graph.add((mut_2, RDF.type, NF.Mutation))
    mutation_graph.add((mut_2, NF.affectedGeneSymbol, Literal("NF1")))
    mutation_graph.add((mut_3, RDF.type, NF.Mutation))
    mutation_graph.add((mut_3, NF.affectedGeneSymbol, Literal("TP53")))
    mutation_graph.serialize(destination=mutations_ttl, format="turtle")

    materialize_nf1_mutation_sets(cell_lines_ttl, mutations_ttl, output_ttl)

    derived = Graph()
    derived.parse(output_ttl, format="turtle")

    set_a = derived.value(cell_a, NF.hasNf1MutationSet)
    set_b = derived.value(cell_b, NF.hasNf1MutationSet)
    set_c = derived.value(cell_c, NF.hasNf1MutationSet)

    assert set_a is not None
    assert set_b == set_a
    assert set_c is not None
    assert set_c != set_a

    assert (set_a, RDF.type, NF.MutationSet) in derived
    assert (set_a, RDF.type, NF.Nf1MutationSet) in derived
    assert (set_a, NF.hasMutation, mut_1) in derived
    assert (set_a, NF.hasMutation, mut_2) in derived
    assert (set_c, NF.hasMutation, mut_3) not in derived

    comment_a = derived.value(set_a, RDFS.comment)
    comment_c = derived.value(set_c, RDFS.comment)
    assert comment_a is not None
    assert "11111111-1111-1111-1111-111111111111" in str(comment_a)
    assert "22222222-2222-2222-2222-222222222222" in str(comment_a)
    assert comment_c == Literal("Derived NF1 mutation set with member mutation UUIDs: (empty)")
