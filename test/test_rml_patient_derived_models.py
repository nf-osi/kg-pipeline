"""
Tests for Patient Derived Models RML mapping

Tests the patient_derived_models.rml.ttl mapping against test/patient_derived_models.csv
"""

import pytest
from rdflib import URIRef, Literal, Namespace
from rdflib.namespace import RDF


@pytest.fixture
def pdm_graph(rml_runner, namespaces):
    """Load patient derived models RDF graph from test data"""
    graph = rml_runner(
        mapping_file="patient_derived_models.rml.ttl",
        csv_replacements={
            "data/csv/patient_derived_models.csv": "test/patient_derived_models.csv"
        }
    )
    return graph


class TestPatientDerivedModelCore:
    """Test core patient derived model properties"""

    def test_has_correct_type(self, pdm_graph, namespaces):
        """All entries should have type nf:PatientDerivedModel"""
        models = list(pdm_graph.subjects(RDF.type, namespaces["nf"].PatientDerivedModel))
        assert len(models) == 3, f"Expected 3 patient derived models, got {len(models)}"

    def test_subject_is_iri(self, pdm_graph, namespaces):
        """Subjects should be IRIs"""
        models = list(pdm_graph.subjects(RDF.type, namespaces["nf"].PatientDerivedModel))
        for model in models:
            assert isinstance(model, URIRef), f"Subject should be IRI, got {type(model)}"

    def test_iri_uses_correct_template(self, pdm_graph, namespaces):
        """IRI should use resource/{id} pattern"""
        models = list(pdm_graph.subjects(RDF.type, namespaces["nf"].PatientDerivedModel))
        iris = [str(m) for m in models]
        assert any("resource/pdm-001" in iri for iri in iris), \
            f"Expected IRI with resource/pdm-001, got: {iris}"

    def test_model_system_type_present(self, pdm_graph, namespaces):
        """modelSystemType should be present"""
        NF = namespaces["nf"]
        query = """
        SELECT ?type
        WHERE {
            ?model a nf:PatientDerivedModel ;
                   nf:modelSystemType ?type .
            FILTER(CONTAINS(STR(?model), "pdm-001"))
        }
        """
        results = list(pdm_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].type) == "PDX"

    def test_patient_diagnosis_present(self, pdm_graph, namespaces):
        """patientDiagnosis should be present"""
        NF = namespaces["nf"]
        query = """
        SELECT ?diag
        WHERE {
            ?model a nf:PatientDerivedModel ;
                   nf:patientDiagnosis ?diag .
            FILTER(CONTAINS(STR(?model), "pdm-001"))
        }
        """
        results = list(pdm_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].diag) == "NF1-associated MPNST"

    def test_tumor_type_present(self, pdm_graph, namespaces):
        """tumorType should be present"""
        NF = namespaces["nf"]
        query = """
        SELECT ?tumor
        WHERE {
            ?model a nf:PatientDerivedModel ;
                   nf:tumorType ?tumor .
            FILTER(CONTAINS(STR(?model), "pdm-001"))
        }
        """
        results = list(pdm_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].tumor) == "MPNST"

    def test_donor_link_is_iri(self, pdm_graph, namespaces):
        """donorId and fromDonor should be IRIs"""
        NF = namespaces["nf"]
        query = """
        SELECT ?donor
        WHERE {
            ?model a nf:PatientDerivedModel ;
                   nf:donorId ?donor .
            FILTER(CONTAINS(STR(?model), "pdm-001"))
        }
        """
        results = list(pdm_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].donor, URIRef), "donorId should be IRI"
        assert "donor-001" in str(results[0].donor)

    def test_from_donor_link(self, pdm_graph, namespaces):
        """fromDonor should also link to the donor IRI"""
        NF = namespaces["nf"]
        query = """
        SELECT ?donor
        WHERE {
            ?model a nf:PatientDerivedModel ;
                   nf:fromDonor ?donor .
            FILTER(CONTAINS(STR(?model), "pdm-001"))
        }
        """
        results = list(pdm_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].donor, URIRef)

    def test_empty_donor_produces_no_triple(self, pdm_graph, namespaces):
        """Empty donorId should not produce donor triples"""
        NF = namespaces["nf"]
        query = """
        SELECT ?donor
        WHERE {
            ?model a nf:PatientDerivedModel ;
                   nf:donorId ?donor .
            FILTER(CONTAINS(STR(?model), "pdm-002"))
        }
        """
        results = list(pdm_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, "Empty donorId should produce no triple"


class TestPatientDerivedModelMultiValue:
    """Test multi-value field handling"""

    def test_molecular_characterization_split(self, pdm_graph, namespaces):
        """molecularCharacterization should split on pipe"""
        NF = namespaces["nf"]
        query = """
        SELECT ?char
        WHERE {
            ?model a nf:PatientDerivedModel ;
                   nf:molecularCharacterization ?char .
            FILTER(CONTAINS(STR(?model), "pdm-001"))
        }
        """
        results = list(pdm_graph.query(query, initNs={"nf": NF}))
        values = [str(r.char) for r in results]
        assert "WGS" in values
        assert "RNA-seq" in values
        assert len(results) == 2

    def test_validation_methods_split(self, pdm_graph, namespaces):
        """validationMethods should split on pipe"""
        NF = namespaces["nf"]
        query = """
        SELECT ?method
        WHERE {
            ?model a nf:PatientDerivedModel ;
                   nf:validationMethods ?method .
            FILTER(CONTAINS(STR(?model), "pdm-001"))
        }
        """
        results = list(pdm_graph.query(query, initNs={"nf": NF}))
        values = [str(r.method) for r in results]
        assert "IHC" in values
        assert "Drug response" in values

    def test_no_empty_literals(self, pdm_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(pdm_graph.query(query))
        assert len(results) == 0, f"Found {len(results)} empty literal values"
