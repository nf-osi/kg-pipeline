"""
Tests for Biobanks RML mapping

Tests the biobanks.rml.ttl mapping against test/biobanks.csv
"""

import pytest
from rdflib import URIRef, Literal, Namespace
from rdflib.namespace import RDF


@pytest.fixture
def biobanks_graph(rml_runner, namespaces):
    """Load biobanks RDF graph from test data"""
    graph = rml_runner(
        mapping_file="biobanks.rml.ttl",
        csv_replacements={"data/csv/biobanks.csv": "test/biobanks.csv"}
    )
    return graph


class TestBiobanksCore:
    """Test core biobank properties"""

    def test_biobank_has_correct_type(self, biobanks_graph, namespaces):
        """All biobanks should have type nf:Biobank"""
        biobanks = list(biobanks_graph.subjects(RDF.type, namespaces["nf"].Biobank))
        assert len(biobanks) > 0, "No biobanks found in graph"
        assert len(biobanks) == 3, f"Expected 3 biobanks, got {len(biobanks)}"

    def test_biobank_id_is_iri(self, biobanks_graph, namespaces):
        """Biobank subjects should be IRIs"""
        biobanks = list(biobanks_graph.subjects(RDF.type, namespaces["nf"].Biobank))
        for biobank in biobanks:
            assert isinstance(biobank, URIRef), \
                f"Biobank ID should be IRI, got {type(biobank)}"

    def test_biobank_name_present(self, biobanks_graph, namespaces):
        """Biobanks should have a name"""
        NF = namespaces["nf"]

        query = """
        SELECT ?biobank ?name
        WHERE {
            ?biobank a nf:Biobank ;
                     nf:name ?name .
            FILTER(CONTAINS(STR(?biobank), "test-res-001"))
        }
        """
        results = list(biobanks_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1, "Expected name for test-res-001"
        assert str(results[0].name) == "Test Biobank One"

    def test_biobank_url_is_iri(self, biobanks_graph, namespaces):
        """biobankURL should be an IRI"""
        NF = namespaces["nf"]

        query = """
        SELECT ?biobank ?url
        WHERE {
            ?biobank a nf:Biobank ;
                     nf:biobankURL ?url .
        }
        """
        results = list(biobanks_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No biobankURL found"
        for row in results:
            assert isinstance(row.url, URIRef), \
                f"biobankURL should be IRI, got {type(row.url)}"

    def test_resource_id_is_string(self, biobanks_graph, namespaces):
        """resourceId should be a string literal"""
        NF = namespaces["nf"]

        query = """
        SELECT ?biobank ?resourceId
        WHERE {
            ?biobank a nf:Biobank ;
                     nf:resourceId ?resourceId .
        }
        """
        results = list(biobanks_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No resourceId properties found"
        for row in results:
            assert isinstance(row.resourceId, Literal), \
                f"resourceId should be Literal, got {type(row.resourceId)}"


class TestBiobanksMultiValue:
    """Test multi-value field handling (pipe-delimited lists)"""

    def test_specimen_preparation_method_multi_value(self, biobanks_graph, namespaces):
        """specimenPreparationMethod should split on pipe"""
        NF = namespaces["nf"]

        query = """
        SELECT ?method
        WHERE {
            ?biobank a nf:Biobank ;
                     nf:specimenPreparationMethod ?method .
            FILTER(CONTAINS(STR(?biobank), "test-res-001"))
        }
        """
        results = list(biobanks_graph.query(query, initNs={"nf": NF}))
        values = [str(row.method) for row in results]

        assert "Flash frozen" in values
        assert "FFPE" in values

    def test_specimen_type_multi_value(self, biobanks_graph, namespaces):
        """specimenType should split on pipe"""
        NF = namespaces["nf"]

        query = """
        SELECT ?type
        WHERE {
            ?biobank a nf:Biobank ;
                     nf:specimenType ?type .
            FILTER(CONTAINS(STR(?biobank), "test-res-001"))
        }
        """
        results = list(biobanks_graph.query(query, initNs={"nf": NF}))
        values = [str(row.type) for row in results]

        assert "cell lines" in values
        assert "human tissue" in values

    def test_tumor_type_multi_value(self, biobanks_graph, namespaces):
        """tumorType should split on pipe"""
        NF = namespaces["nf"]

        query = """
        SELECT ?tumor
        WHERE {
            ?biobank a nf:Biobank ;
                     nf:tumorType ?tumor .
            FILTER(CONTAINS(STR(?biobank), "test-res-001"))
        }
        """
        results = list(biobanks_graph.query(query, initNs={"nf": NF}))
        values = [str(row.tumor) for row in results]

        assert "malignant peripheral nerve sheath tumor" in values
        assert "plexiform neurofibroma" in values

    def test_specimen_format_multi_value(self, biobanks_graph, namespaces):
        """specimenFormat should split on pipe"""
        NF = namespaces["nf"]

        query = """
        SELECT ?format
        WHERE {
            ?biobank a nf:Biobank ;
                     nf:specimenFormat ?format .
            FILTER(CONTAINS(STR(?biobank), "test-res-003"))
        }
        """
        results = list(biobanks_graph.query(query, initNs={"nf": NF}))
        values = [str(row.format) for row in results]

        assert "DNA" in values
        assert "RNA" in values
        assert "cells" in values
        assert len(results) == 3

    def test_specimen_tissue_type_multi_value(self, biobanks_graph, namespaces):
        """specimenTissueType should split on pipe"""
        NF = namespaces["nf"]

        query = """
        SELECT ?tissue
        WHERE {
            ?biobank a nf:Biobank ;
                     nf:specimenTissueType ?tissue .
            FILTER(CONTAINS(STR(?biobank), "test-res-003"))
        }
        """
        results = list(biobanks_graph.query(query, initNs={"nf": NF}))
        values = [str(row.tissue) for row in results]

        assert "Blood" in values
        assert "Skin" in values
        assert "Tumor" in values
        assert len(results) == 3


class TestBiobanksEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_contact_produces_no_triple(self, biobanks_graph, namespaces):
        """Empty contact should not create triple"""
        NF = namespaces["nf"]

        query = """
        SELECT ?contact
        WHERE {
            ?biobank a nf:Biobank ;
                     nf:contact ?contact .
            FILTER(CONTAINS(STR(?biobank), "test-res-001"))
        }
        """
        results = list(biobanks_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, "Empty contact should not produce triple"

    def test_contact_present_when_set(self, biobanks_graph, namespaces):
        """Contact should be present when it has a value"""
        NF = namespaces["nf"]

        query = """
        SELECT ?contact
        WHERE {
            ?biobank a nf:Biobank ;
                     nf:contact ?contact .
            FILTER(CONTAINS(STR(?biobank), "test-res-003"))
        }
        """
        results = list(biobanks_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1, "Expected contact for test-res-003"
        assert str(results[0].contact) == "test-contact@example.org"

    def test_no_empty_literal_values(self, biobanks_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(biobanks_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


# Run with: pytest test/test_rml_biobanks.py -v
