"""
Tests for Donors RML mapping

Tests the donors.rml.ttl mapping against test/donors.csv
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def donors_graph(rml_runner, namespaces):
    """Load donors RDF graph from test data"""
    graph = rml_runner(
        mapping_file="donors.rml.ttl",
        csv_replacements={"data/csv/donors.csv": "test/donors.csv"}
    )
    return graph


class TestDonorsCore:
    """Test core donor properties"""

    def test_donor_has_correct_type(self, donors_graph, namespaces):
        """All donors should have type nf:Donor"""
        donors = list(donors_graph.subjects(RDF.type, namespaces["nf"].Donor))
        assert len(donors) > 0, "No donors found in graph"
        assert len(donors) >= 3, f"Expected at least 3 donors, got {len(donors)}"

    def test_donor_id_is_iri(self, donors_graph, namespaces):
        """Donor subjects should be IRIs"""
        donors = list(donors_graph.subjects(RDF.type, namespaces["nf"].Donor))
        for donor in donors:
            assert isinstance(donor, URIRef), \
                f"Donor ID should be IRI, got {type(donor)}"


class TestDonorsSpeciesField:
    """Test species field handling (can be single or multi-value)"""

    def test_single_species_value(self, donors_graph, namespaces):
        """Single species value should be handled correctly"""
        NF = namespaces["nf"]

        query = """
        SELECT ?donor ?species
        WHERE {
            ?donor a nf:Donor ;
                   nf:species ?species .
            FILTER(CONTAINS(STR(?donor), "test-donor-001"))
        }
        """
        results = list(donors_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected species for test-donor-001"
        # Should have single species
        species_values = [str(row.species) for row in results]
        assert "Homo sapiens" in species_values, \
            f"Expected 'Homo sapiens', got {species_values}"

    def test_multi_valued_species_split(self, donors_graph, namespaces):
        """Multi-valued species should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?donor ?species
        WHERE {
            ?donor a nf:Donor ;
                   nf:species ?species .
            FILTER(CONTAINS(STR(?donor), "test-donor-002"))
        }
        """
        results = list(donors_graph.query(query, initNs={"nf": NF}))
        species_values = [str(row.species) for row in results]

        # test-donor-002 has "Homo sapiens|Mus musculus"
        assert "Homo sapiens" in species_values, \
            "Expected 'Homo sapiens' from multi-valued species"
        assert "Mus musculus" in species_values, \
            "Expected 'Mus musculus' from multi-valued species"


class TestDonorsIRIFields:
    """Test fields that should be IRIs (not literals)"""

    def test_parent_donor_id_as_iri(self, donors_graph, namespaces):
        """ParentDonorId should be an IRI reference"""
        NF = namespaces["nf"]

        query = """
        SELECT ?donor ?parentDonorId
        WHERE {
            ?donor a nf:Donor ;
                   nf:parentDonorId ?parentDonorId .
        }
        """
        results = list(donors_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "No parentDonorId found"

        for row in results:
            assert isinstance(row.parentDonorId, URIRef), \
                f"parentDonorId should be IRI, got {type(row.parentDonorId)}"
            # Should reference another donor
            assert "test-donor" in str(row.parentDonorId) or len(str(row.parentDonorId).split('/')[-1]) > 10, \
                f"parentDonorId should be valid donor IRI: {row.parentDonorId}"

    def test_transplantation_donor_id_as_iri(self, donors_graph, namespaces):
        """TransplantationDonorId should be an IRI reference"""
        NF = namespaces["nf"]

        query = """
        SELECT ?donor ?transplantDonorId
        WHERE {
            ?donor a nf:Donor ;
                   nf:transplantationDonorId ?transplantDonorId .
        }
        """
        results = list(donors_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "No transplantationDonorId found"

        for row in results:
            assert isinstance(row.transplantDonorId, URIRef), \
                f"transplantationDonorId should be IRI, got {type(row.transplantDonorId)}"


class TestDonorsEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_parent_donor_id_produces_no_triple(self, donors_graph, namespaces):
        """Empty parentDonorId should not create triple"""
        NF = namespaces["nf"]

        # test-donor-001 should have empty parentDonorId
        query = """
        SELECT ?parentDonorId
        WHERE {
            ?donor a nf:Donor ;
                   nf:parentDonorId ?parentDonorId .
            FILTER(CONTAINS(STR(?donor), "test-donor-001"))
        }
        """
        results = list(donors_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty parentDonorId should not produce triple"

    def test_no_empty_literal_values(self, donors_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(donors_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


class TestDonorsBasicFields:
    """Test basic donor demographic fields"""

    def test_race_field_present(self, donors_graph, namespaces):
        """Race field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?donor ?race
        WHERE {
            ?donor a nf:Donor ;
                   nf:race ?race .
            FILTER(CONTAINS(STR(?donor), "test-donor-001"))
        }
        """
        results = list(donors_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected race for test-donor-001"
        assert str(results[0].race) == "White", \
            f"Expected 'White', got {results[0].race}"

    def test_sex_field_present(self, donors_graph, namespaces):
        """Sex field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?donor ?sex
        WHERE {
            ?donor a nf:Donor ;
                   nf:sex ?sex .
            FILTER(CONTAINS(STR(?donor), "test-donor-001"))
        }
        """
        results = list(donors_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected sex for test-donor-001"
        assert str(results[0].sex) == "Male", \
            f"Expected 'Male', got {results[0].sex}"

    def test_age_field_present(self, donors_graph, namespaces):
        """Age field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?donor ?age
        WHERE {
            ?donor a nf:Donor ;
                   nf:age ?age .
            FILTER(CONTAINS(STR(?donor), "test-donor-001"))
        }
        """
        results = list(donors_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected age for test-donor-001"
        assert str(results[0].age) == "25", \
            f"Expected '25', got {results[0].age}"

    def test_all_demographic_fields_together(self, donors_graph, namespaces):
        """Donors should have race, sex, and age together"""
        NF = namespaces["nf"]

        query = """
        SELECT ?donor ?race ?sex ?age
        WHERE {
            ?donor a nf:Donor ;
                   nf:race ?race ;
                   nf:sex ?sex ;
                   nf:age ?age .
        }
        """
        results = list(donors_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "At least one donor should have all demographic fields"


class TestDonorsBasicProperties:
    """Test basic donor properties"""

    def test_donor_ids_present(self, donors_graph, namespaces):
        """Donors should have IDs"""
        NF = namespaces["nf"]

        query = """
        SELECT ?donor ?donorId
        WHERE {
            ?donor a nf:Donor ;
                   nf:donorId ?donorId .
        }
        """
        results = list(donors_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Donors should have donorId"


# Run with: pytest test/test_rml_donors.py -v
