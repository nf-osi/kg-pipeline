"""
Tests for Organoid Protocols RML mapping

Tests the organoid_protocols.rml.ttl mapping against test/organoid_protocols.csv
"""

import pytest
from rdflib import URIRef, Literal, Namespace
from rdflib.namespace import RDF


@pytest.fixture
def op_graph(rml_runner, namespaces):
    """Load organoid protocols RDF graph from test data"""
    graph = rml_runner(
        mapping_file="organoid_protocols.rml.ttl",
        csv_replacements={
            "data/csv/organoid_protocols.csv": "test/organoid_protocols.csv"
        }
    )
    return graph


class TestOrganoidProtocolCore:
    """Test core organoid protocol properties"""

    def test_has_correct_type(self, op_graph, namespaces):
        """All entries should have type nf:OrganoidProtocol"""
        protocols = list(op_graph.subjects(RDF.type, namespaces["nf"].OrganoidProtocol))
        assert len(protocols) == 3, f"Expected 3 organoid protocols, got {len(protocols)}"

    def test_subject_is_iri(self, op_graph, namespaces):
        """Subjects should be IRIs"""
        protocols = list(op_graph.subjects(RDF.type, namespaces["nf"].OrganoidProtocol))
        for p in protocols:
            assert isinstance(p, URIRef), f"Subject should be IRI, got {type(p)}"

    def test_iri_uses_correct_template(self, op_graph, namespaces):
        """IRI should use resource/{id} pattern"""
        protocols = list(op_graph.subjects(RDF.type, namespaces["nf"].OrganoidProtocol))
        iris = [str(p) for p in protocols]
        assert any("resource/op-001" in iri for iri in iris), \
            f"Expected IRI with resource/op-001, got: {iris}"

    def test_model_type_present(self, op_graph, namespaces):
        """modelType should be present"""
        NF = namespaces["nf"]
        query = """
        SELECT ?type
        WHERE {
            ?op a nf:OrganoidProtocol ;
                nf:modelType ?type .
            FILTER(CONTAINS(STR(?op), "op-001"))
        }
        """
        results = list(op_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].type) == "Tumor organoid"

    def test_derivation_source_present(self, op_graph, namespaces):
        """derivationSource should be present"""
        NF = namespaces["nf"]
        query = """
        SELECT ?src
        WHERE {
            ?op a nf:OrganoidProtocol ;
                nf:derivationSource ?src .
            FILTER(CONTAINS(STR(?op), "op-001"))
        }
        """
        results = list(op_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].src) == "Patient biopsy"

    def test_passage_number_present(self, op_graph, namespaces):
        """passageNumber should be present"""
        NF = namespaces["nf"]
        query = """
        SELECT ?passage
        WHERE {
            ?op a nf:OrganoidProtocol ;
                nf:passageNumber ?passage .
            FILTER(CONTAINS(STR(?op), "op-001"))
        }
        """
        results = list(op_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].passage) == "P8"

    def test_empty_cryopreservation_produces_no_triple(self, op_graph, namespaces):
        """Empty cryopreservationProtocol should not produce a triple"""
        NF = namespaces["nf"]
        query = """
        SELECT ?cryo
        WHERE {
            ?op a nf:OrganoidProtocol ;
                nf:cryopreservationProtocol ?cryo .
            FILTER(CONTAINS(STR(?op), "op-002"))
        }
        """
        results = list(op_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, "Empty cryopreservationProtocol should produce no triple"


class TestOrganoidProtocolMultiValue:
    """Test multi-value field handling"""

    def test_cell_types_split(self, op_graph, namespaces):
        """cellTypes should split on pipe"""
        NF = namespaces["nf"]
        query = """
        SELECT ?ct
        WHERE {
            ?op a nf:OrganoidProtocol ;
                nf:cellTypes ?ct .
            FILTER(CONTAINS(STR(?op), "op-001"))
        }
        """
        results = list(op_graph.query(query, initNs={"nf": NF}))
        values = [str(r.ct) for r in results]
        assert "Schwann cells" in values
        assert "Fibroblasts" in values
        assert len(results) == 2

    def test_characterization_methods_split(self, op_graph, namespaces):
        """characterizationMethods should split on pipe"""
        NF = namespaces["nf"]
        query = """
        SELECT ?method
        WHERE {
            ?op a nf:OrganoidProtocol ;
                nf:characterizationMethods ?method .
            FILTER(CONTAINS(STR(?op), "op-001"))
        }
        """
        results = list(op_graph.query(query, initNs={"nf": NF}))
        values = [str(r.method) for r in results]
        assert "Immunostaining" in values
        assert "qPCR" in values
        assert "Brightfield" in values
        assert len(results) == 3

    def test_quality_control_metrics_split(self, op_graph, namespaces):
        """qualityControlMetrics should split on pipe"""
        NF = namespaces["nf"]
        query = """
        SELECT ?metric
        WHERE {
            ?op a nf:OrganoidProtocol ;
                nf:qualityControlMetrics ?metric .
            FILTER(CONTAINS(STR(?op), "op-001"))
        }
        """
        results = list(op_graph.query(query, initNs={"nf": NF}))
        values = [str(r.metric) for r in results]
        assert "Viability" in values
        assert "Morphology" in values

    def test_no_empty_literals(self, op_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(op_graph.query(query))
        assert len(results) == 0, f"Found {len(results)} empty literal values"
