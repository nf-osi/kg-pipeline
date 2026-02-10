"""
Tests for Antibodies RML mapping

Tests the portal_antibodies.rml.ttl mapping against test/antibodies.csv
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def antibodies_graph(rml_runner, namespaces):
    """Load antibodies RDF graph from test data"""
    graph = rml_runner(
        mapping_file="portal_antibodies.rml.ttl",
        csv_replacements={"data/csv/antibodies.csv": "test/antibodies.csv"}
    )
    return graph


class TestAntibodiesCore:
    """Test core antibody properties"""

    def test_antibody_has_correct_type(self, antibodies_graph, namespaces):
        """All antibodies should have type nf:Antibody"""
        antibodies = list(antibodies_graph.subjects(RDF.type, namespaces["nf"].Antibody))
        assert len(antibodies) > 0, "No antibodies found in graph"
        assert len(antibodies) >= 3, f"Expected at least 3 antibodies, got {len(antibodies)}"

    def test_antibody_id_is_iri(self, antibodies_graph, namespaces):
        """Antibody subjects should be IRIs"""
        antibodies = list(antibodies_graph.subjects(RDF.type, namespaces["nf"].Antibody))
        for antibody in antibodies:
            assert isinstance(antibody, URIRef), \
                f"Antibody ID should be IRI, got {type(antibody)}"


class TestAntibodiesIRIFields:
    """Test fields that should be IRIs (not literals)"""

    def test_uniprot_id_as_iri(self, antibodies_graph, namespaces):
        """UniprotId should be an IRI, not a literal"""
        NF = namespaces["nf"]

        query = """
        SELECT ?antibody ?uniprotId
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:uniprotId ?uniprotId .
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "No uniprotId found"

        for row in results:
            assert isinstance(row.uniprotId, URIRef), \
                f"uniprotId should be IRI, got {type(row.uniprotId)}"
            # Should contain a UniProt-style ID
            uniprot_str = str(row.uniprotId)
            assert "P" in uniprot_str or "Q" in uniprot_str or "uniprot" in uniprot_str.lower(), \
                f"Expected UniProt ID format, got {row.uniprotId}"


class TestAntibodiesMultiValue:
    """Test multi-value field handling (pipe-delimited lists)"""

    def test_reactive_species_multi_value_split(self, antibodies_graph, namespaces):
        """ReactiveSpecies should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?antibody ?species
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:reactiveSpecies ?species .
            FILTER(CONTAINS(STR(?antibody), "test-ab-001"))
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))
        species_values = [str(row.species) for row in results]

        # test-ab-001 has "Human|Mouse|Rat"
        assert "Human" in species_values, "Expected 'Human' in reactive species"
        assert "Mouse" in species_values, "Expected 'Mouse' in reactive species"
        assert "Rat" in species_values, "Expected 'Rat' in reactive species"

    def test_single_reactive_species_value(self, antibodies_graph, namespaces):
        """Single reactiveSpecies value should be handled correctly"""
        NF = namespaces["nf"]

        query = """
        SELECT ?antibody ?species
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:reactiveSpecies ?species .
            FILTER(CONTAINS(STR(?antibody), "test-ab-002"))
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))
        species_values = [str(row.species) for row in results]

        # test-ab-002 has single value "Human"
        assert "Human" in species_values, "Expected 'Human' reactive species"
        # Should only have one value for this antibody
        assert len(results) == 1, f"Expected single species value, got {len(results)}"


class TestAntibodiesBasicFields:
    """Test basic antibody fields"""

    def test_host_organism_present(self, antibodies_graph, namespaces):
        """Host organism field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?antibody ?host
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:hostOrganism ?host .
            FILTER(CONTAINS(STR(?antibody), "test-ab-001"))
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected hostOrganism for test-ab-001"
        assert str(results[0].host) == "Rabbit", \
            f"Expected 'Rabbit', got {results[0].host}"

    def test_conjugate_present(self, antibodies_graph, namespaces):
        """Conjugate field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?antibody ?conjugate
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:conjugate ?conjugate .
            FILTER(CONTAINS(STR(?antibody), "test-ab-001"))
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected conjugate for test-ab-001"
        assert "Nonconjugated" in str(results[0].conjugate), \
            f"Expected 'Nonconjugated', got {results[0].conjugate}"

    def test_clonality_present(self, antibodies_graph, namespaces):
        """Clonality field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?antibody ?clonality
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:clonality ?clonality .
            FILTER(CONTAINS(STR(?antibody), "test-ab-001"))
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected clonality for test-ab-001"
        assert "Polyclonal" in str(results[0].clonality), \
            f"Expected 'Polyclonal', got {results[0].clonality}"

    def test_all_basic_fields_together(self, antibodies_graph, namespaces):
        """Antibodies should have host organism, conjugate, and clonality together"""
        NF = namespaces["nf"]

        query = """
        SELECT ?antibody ?host ?conjugate ?clonality
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:hostOrganism ?host ;
                      nf:conjugate ?conjugate ;
                      nf:clonality ?clonality .
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "At least one antibody should have all basic fields"


class TestAntibodiesTargetFields:
    """Test target antigen fields"""

    def test_target_antigen_present(self, antibodies_graph, namespaces):
        """Target antigen field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?antibody ?target
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:targetAntigen ?target .
            FILTER(CONTAINS(STR(?antibody), "test-ab-001"))
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected targetAntigen for test-ab-001"
        assert "NF1" in str(results[0].target), \
            f"Expected 'NF1', got {results[0].target}"


class TestAntibodiesEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_clone_id_produces_no_triple(self, antibodies_graph, namespaces):
        """Empty cloneId should not create triple"""
        NF = namespaces["nf"]

        # test-ab-002 should have empty cloneId
        query = """
        SELECT ?cloneId
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:cloneId ?cloneId .
            FILTER(CONTAINS(STR(?antibody), "test-ab-002"))
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty cloneId should not produce triple"

    def test_empty_uniprot_id_produces_no_triple(self, antibodies_graph, namespaces):
        """Empty uniprotId should not create triple"""
        NF = namespaces["nf"]

        # test-ab-003 should have empty uniprotId
        query = """
        SELECT ?uniprotId
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:uniprotId ?uniprotId .
            FILTER(CONTAINS(STR(?antibody), "test-ab-003"))
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty uniprotId should not produce triple"

    def test_no_empty_literal_values(self, antibodies_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(antibodies_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


class TestAntibodiesBasicProperties:
    """Test basic antibody properties"""

    def test_antibody_ids_present(self, antibodies_graph, namespaces):
        """Antibodies should have IDs"""
        NF = namespaces["nf"]

        query = """
        SELECT ?antibody ?antibodyId
        WHERE {
            ?antibody a nf:Antibody ;
                      nf:antibodyId ?antibodyId .
        }
        """
        results = list(antibodies_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Antibodies should have antibodyId"


# Run with: pytest test/test_rml_antibodies.py -v
