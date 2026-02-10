"""
Tests for Animal Models RML mapping

Tests the portal_animal_models.rml.ttl mapping against test/animal_models.csv
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def animal_models_graph(rml_runner, namespaces):
    """Load animal models RDF graph from test data"""
    graph = rml_runner(
        mapping_file="portal_animal_models.rml.ttl",
        csv_replacements={"data/csv/animal_models.csv": "test/animal_models.csv"}
    )
    return graph


class TestAnimalModelsCore:
    """Test core animal model properties"""

    def test_animal_model_has_correct_type(self, animal_models_graph, namespaces):
        """All animal models should have type nf:AnimalModel"""
        models = list(animal_models_graph.subjects(RDF.type, namespaces["nf"].AnimalModel))
        assert len(models) > 0, "No animal models found in graph"
        assert len(models) >= 3, f"Expected at least 3 models, got {len(models)}"

    def test_animal_model_id_is_iri(self, animal_models_graph, namespaces):
        """Animal model subjects should be IRIs"""
        models = list(animal_models_graph.subjects(RDF.type, namespaces["nf"].AnimalModel))
        for model in models:
            assert isinstance(model, URIRef), \
                f"Animal model ID should be IRI, got {type(model)}"


class TestAnimalModelsIRIFields:
    """Test fields that should be IRIs (not literals)"""

    def test_donor_id_as_iri(self, animal_models_graph, namespaces):
        """DonorId should be an IRI reference"""
        NF = namespaces["nf"]

        query = """
        SELECT ?model ?donorId
        WHERE {
            ?model a nf:AnimalModel ;
                   nf:donorId ?donorId .
        }
        """
        results = list(animal_models_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "No donorId found"

        for row in results:
            assert isinstance(row.donorId, URIRef), \
                f"donorId should be IRI, got {type(row.donorId)}"
            # Check it contains expected donor ID format
            assert "test-donor" in str(row.donorId) or len(str(row.donorId).split('/')[-1]) > 10, \
                f"donorId should be valid IRI: {row.donorId}"

    def test_transplantation_donor_id_as_iri(self, animal_models_graph, namespaces):
        """TransplantationDonorId should be an IRI reference"""
        NF = namespaces["nf"]

        query = """
        SELECT ?model ?transplantDonorId
        WHERE {
            ?model a nf:AnimalModel ;
                   nf:transplantationDonorId ?transplantDonorId .
        }
        """
        results = list(animal_models_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "No transplantationDonorId found"

        for row in results:
            assert isinstance(row.transplantDonorId, URIRef), \
                f"transplantationDonorId should be IRI, got {type(row.transplantDonorId)}"


class TestAnimalModelsMultiValue:
    """Test multi-value field handling (pipe-delimited lists)"""

    def test_animal_model_of_manifestation_multi_value_split(self, animal_models_graph, namespaces):
        """AnimalModelOfManifestation should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?model ?manifestation
        WHERE {
            ?model a nf:AnimalModel ;
                      nf:animalModelOfManifestation ?manifestation .
        }
        """
        results = animal_models_graph.query(query, initNs={"nf": NF})
        manifestations = [str(row.manifestation) for row in results]

        # Should have both values from pipe-delimited list
        assert "Plexiform Neurofibroma" in manifestations, \
            "Expected 'Plexiform Neurofibroma' manifestation"
        assert "Optic Glioma" in manifestations, \
            "Expected 'Optic Glioma' manifestation"

    def test_single_genetic_disorder_value(self, animal_models_graph, namespaces):
        """AnimalModelGeneticDisorder should handle single values"""
        NF = namespaces["nf"]

        query = """
        SELECT ?model ?disorder
        WHERE {
            ?model a nf:AnimalModel ;
                      nf:animalModelGeneticDisorder ?disorder .
            FILTER(CONTAINS(STR(?model), "test-animal-002"))
        }
        """
        results = list(animal_models_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected genetic disorder for test-animal-002"
        assert str(results[0].disorder) == "Neurofibromatosis type 2", \
            f"Expected 'Neurofibromatosis type 2', got {results[0].disorder}"


class TestAnimalModelsStrainFields:
    """Test strain-related fields"""

    def test_background_strain_present(self, animal_models_graph, namespaces):
        """Background strain field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?model ?strain
        WHERE {
            ?model a nf:AnimalModel ;
                      nf:backgroundStrain ?strain .
            FILTER(CONTAINS(STR(?model), "test-animal-001"))
        }
        """
        results = list(animal_models_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected backgroundStrain for test-animal-001"
        assert str(results[0].strain) == "C57BL/6J", \
            f"Expected 'C57BL/6J', got {results[0].strain}"

    def test_strain_nomenclature_present(self, animal_models_graph, namespaces):
        """Strain nomenclature field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?model ?nomenclature
        WHERE {
            ?model a nf:AnimalModel ;
                      nf:strainNomenclature ?nomenclature .
            FILTER(CONTAINS(STR(?model), "test-animal-001"))
        }
        """
        results = list(animal_models_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected strainNomenclature for test-animal-001"
        assert "Nf1" in str(results[0].nomenclature), \
            f"Expected nomenclature with 'Nf1', got {results[0].nomenclature}"


class TestAnimalModelsEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_donor_id_produces_no_triple(self, animal_models_graph, namespaces):
        """Empty donorId should not create triple"""
        NF = namespaces["nf"]

        # test-animal-003 should have empty donorId
        query = """
        SELECT ?donorId
        WHERE {
            ?model a nf:AnimalModel ;
                      nf:donorId ?donorId .
            FILTER(CONTAINS(STR(?model), "test-animal-003"))
        }
        """
        results = list(animal_models_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty donorId should not produce triple"

    def test_no_empty_literal_values(self, animal_models_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(animal_models_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


class TestAnimalModelsBasicProperties:
    """Test basic animal model properties"""

    def test_animal_model_ids_present(self, animal_models_graph, namespaces):
        """Animal models should have IDs"""
        NF = namespaces["nf"]

        query = """
        SELECT ?model ?animalModelId
        WHERE {
            ?model a nf:AnimalModel ;
                      nf:animalModelId ?animalModelId .
        }
        """
        results = list(animal_models_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Animal models should have animalModelId"


# Run with: pytest test/test_rml_animal_models.py -v
