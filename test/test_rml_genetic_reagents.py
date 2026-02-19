"""
Tests for Genetic Reagents RML mapping

Tests the genetic_reagents.rml.ttl mapping against test/genetic_reagents.csv
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def genetic_reagents_graph(rml_runner, namespaces):
    """Load genetic reagents RDF graph from test data"""
    graph = rml_runner(
        mapping_file="genetic_reagents.rml.ttl",
        csv_replacements={"data/csv/genetic_reagents_harmonized.csv": "test/genetic_reagents.csv"}
    )
    return graph


class TestGeneticReagentsCore:
    """Test core genetic reagent properties"""

    def test_reagent_has_correct_type(self, genetic_reagents_graph, namespaces):
        """All reagents should have type nf:GeneticReagent"""
        reagents = list(genetic_reagents_graph.subjects(RDF.type, namespaces["nf"].GeneticReagent))
        assert len(reagents) > 0, "No genetic reagents found in graph"
        assert len(reagents) >= 3, f"Expected at least 3 reagents, got {len(reagents)}"

    def test_reagent_id_is_iri(self, genetic_reagents_graph, namespaces):
        """Reagent subjects should be IRIs"""
        reagents = list(genetic_reagents_graph.subjects(RDF.type, namespaces["nf"].GeneticReagent))
        for reagent in reagents:
            assert isinstance(reagent, URIRef), \
                f"Reagent ID should be IRI, got {type(reagent)}"


class TestGeneticReagentsMultiValue:
    """Test multi-value field handling (pipe-delimited lists)"""

    def test_reagent_class_emits_rdf_type(self, genetic_reagents_graph, namespaces):
        """reagentClass IRI should be emitted as rdf:type"""
        NF = namespaces["nf"]
        reagent = URIRef("http://nf-osi.github.com/terms#geneticReagent/test-reagent-003")
        types = list(genetic_reagents_graph.objects(reagent, RDF.type))
        assert NF.CRISPRReagent in types, \
            f"Expected CRISPRReagent from reagentClass, got {types}"

    def test_insert_species_multi_value_split(self, genetic_reagents_graph, namespaces):
        """InsertSpecies should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?reagent ?species
        WHERE {
            ?reagent a nf:GeneticReagent ;
                      nf:insertSpecies ?species .
        }
        """
        results = genetic_reagents_graph.query(query, initNs={"nf": NF})
        species = [str(row.species) for row in results]

        # Should have multiple values from split (test-reagent-001 has "Human|Mouse")
        assert "Human" in species, "Expected 'Human' insertSpecies"
        assert "Mouse" in species, "Expected 'Mouse' insertSpecies"


class TestGeneticReagentsFields:
    """Test specific field handling"""

    def test_tag_fields_present(self, genetic_reagents_graph, namespaces):
        """Tag fields (nTerminalTag, cTerminalTag) should be present"""
        NF = namespaces["nf"]

        # Test for specific reagent with tags
        query = """
        SELECT ?reagent ?nTag ?cTag
        WHERE {
            ?reagent a nf:GeneticReagent ;
                      nf:nTerminalTag ?nTag ;
                      nf:cTerminalTag ?cTag .
            FILTER(CONTAINS(STR(?reagent), "test-reagent-001"))
        }
        """
        results = list(genetic_reagents_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Expected reagent with both tags"

        row = results[0]
        assert str(row.nTag) == "GFP", f"Expected nTerminalTag 'GFP', got {row.nTag}"
        assert str(row.cTag) == "FLAG", f"Expected cTerminalTag 'FLAG', got {row.cTag}"

    def test_hazardous_field_present(self, genetic_reagents_graph, namespaces):
        """Hazardous field should be present for relevant reagents"""
        NF = namespaces["nf"]

        # Test for specific reagent marked as hazardous
        query = """
        SELECT ?reagent ?hazardous
        WHERE {
            ?reagent a nf:GeneticReagent ;
                      nf:hazardous ?hazardous .
            FILTER(CONTAINS(STR(?reagent), "test-reagent-003"))
        }
        """
        results = list(genetic_reagents_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Expected reagent with hazardous field"

        assert str(results[0].hazardous) == "Yes", \
            f"Expected hazardous 'Yes', got {results[0].hazardous}"

    def test_reagent_ids_present(self, genetic_reagents_graph, namespaces):
        """Reagents should have IDs"""
        NF = namespaces["nf"]

        query = """
        SELECT ?reagent ?reagentId
        WHERE {
            ?reagent a nf:GeneticReagent ;
                      nf:geneticReagentId ?reagentId .
        }
        """
        results = list(genetic_reagents_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Reagents should have geneticReagentId"


class TestGeneticReagentsEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_insert_entrez_id_produces_no_triple(self, genetic_reagents_graph, namespaces):
        """Empty insertEntrezId should not create triple"""
        NF = namespaces["nf"]

        # test-reagent-003 should have empty insertEntrezId
        query = """
        SELECT ?entrezId
        WHERE {
            ?reagent a nf:GeneticReagent ;
                      nf:insertEntrezId ?entrezId .
            FILTER(CONTAINS(STR(?reagent), "test-reagent-003"))
        }
        """
        results = list(genetic_reagents_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty insertEntrezId should not produce triple"

    def test_no_empty_literal_values(self, genetic_reagents_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(genetic_reagents_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


class TestGeneticReagentsDataTypes:
    """Test that fields have correct data types"""

    def test_string_fields_are_literals(self, genetic_reagents_graph, namespaces):
        """String fields should be literals"""
        NF = namespaces["nf"]

        query = """
        SELECT ?reagent ?name
        WHERE {
            ?reagent a nf:GeneticReagent ;
                      nf:name ?name .
        }
        """
        results = list(genetic_reagents_graph.query(query, initNs={"nf": NF}))

        for row in results:
            assert isinstance(row.name, Literal), \
                f"Name should be Literal, got {type(row.name)}"


class TestGeneticReagentsReagentClass:
    """Test reagentClass -> rdf:type subclass mapping"""

    def test_crispr_reagent_has_subclass_type(self, genetic_reagents_graph, namespaces):
        """test-reagent-003 with reagentClass should get CRISPRReagent type"""
        NF = namespaces["nf"]
        reagent = URIRef("http://nf-osi.github.com/terms#geneticReagent/test-reagent-003")
        types = list(genetic_reagents_graph.objects(reagent, RDF.type))
        assert NF.CRISPRReagent in types, \
            f"Expected CRISPRReagent type, got {types}"

    def test_empty_reagent_class_no_extra_type(self, genetic_reagents_graph, namespaces):
        """Reagents with empty reagentClass should only have base GeneticReagent type"""
        NF = namespaces["nf"]
        reagent = URIRef("http://nf-osi.github.com/terms#geneticReagent/test-reagent-001")
        types = list(genetic_reagents_graph.objects(reagent, RDF.type))
        assert NF.GeneticReagent in types, "Should have base GeneticReagent type"
        non_base = [t for t in types if t != NF.GeneticReagent]
        assert len(non_base) == 0, \
            f"Should not have extra types, got {non_base}"

    def test_all_reagents_have_base_type(self, genetic_reagents_graph, namespaces):
        """All reagents should have GeneticReagent as base type"""
        NF = namespaces["nf"]
        reagents = list(genetic_reagents_graph.subjects(RDF.type, NF.GeneticReagent))
        assert len(reagents) >= 4, \
            f"Expected at least 4 reagents with base type, got {len(reagents)}"


# Run with: pytest test/test_rml_genetic_reagents.py -v
