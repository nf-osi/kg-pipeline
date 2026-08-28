"""
Tests for Clinical Assessment Tools RML mapping

Tests the clinical_assessment_tools.rml.ttl mapping against test/clinical_assessment_tools.csv
"""

import pytest
from rdflib import URIRef, Literal, Namespace
from rdflib.namespace import RDF


@pytest.fixture
def cat_graph(rml_runner, namespaces):
    """Load clinical assessment tools RDF graph from test data"""
    graph = rml_runner(
        mapping_file="clinical_assessment_tools.rml.ttl",
        csv_replacements={
            "data/csv/clinical_assessment_tools.csv": "test/clinical_assessment_tools.csv"
        }
    )
    return graph


class TestClinicalAssessmentToolCore:
    """Test core clinical assessment tool properties"""

    def test_has_correct_type(self, cat_graph, namespaces):
        """All entries should have type nf:ClinicalAssessmentTool"""
        tools = list(cat_graph.subjects(RDF.type, namespaces["nf"].ClinicalAssessmentTool))
        assert len(tools) == 3, f"Expected 3 clinical assessment tools, got {len(tools)}"

    def test_subject_is_iri(self, cat_graph, namespaces):
        """Subjects should be IRIs"""
        tools = list(cat_graph.subjects(RDF.type, namespaces["nf"].ClinicalAssessmentTool))
        for tool in tools:
            assert isinstance(tool, URIRef), f"Subject should be IRI, got {type(tool)}"

    def test_iri_uses_correct_template(self, cat_graph, namespaces):
        """IRI should use resource/{id} pattern"""
        tools = list(cat_graph.subjects(RDF.type, namespaces["nf"].ClinicalAssessmentTool))
        iris = [str(t) for t in tools]
        assert any("resource/cat-001" in iri for iri in iris), \
            f"Expected IRI with resource/cat-001, got: {iris}"

    def test_assessment_name_present(self, cat_graph, namespaces):
        """Entries should have assessmentName property"""
        NF = namespaces["nf"]
        query = """
        SELECT ?tool ?name
        WHERE {
            ?tool a nf:ClinicalAssessmentTool ;
                  nf:assessmentName ?name .
            FILTER(CONTAINS(STR(?tool), "cat-001"))
        }
        """
        results = list(cat_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1, "Expected assessmentName for cat-001"
        assert str(results[0].name) == "NF1 Quality of Life Scale"

    def test_assessment_type_present(self, cat_graph, namespaces):
        """Entries should have assessmentType property"""
        NF = namespaces["nf"]
        query = """
        SELECT ?type
        WHERE {
            ?tool a nf:ClinicalAssessmentTool ;
                  nf:assessmentType ?type .
            FILTER(CONTAINS(STR(?tool), "cat-001"))
        }
        """
        results = list(cat_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].type) == "Patient-reported"

    def test_scoring_method_present(self, cat_graph, namespaces):
        """scoringMethod should be present"""
        NF = namespaces["nf"]
        query = """
        SELECT ?score
        WHERE {
            ?tool a nf:ClinicalAssessmentTool ;
                  nf:scoringMethod ?score .
            FILTER(CONTAINS(STR(?tool), "cat-001"))
        }
        """
        results = list(cat_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].score) == "Likert scale"

    def test_empty_field_produces_no_triple(self, cat_graph, namespaces):
        """Empty psychometricProperties should not produce a triple"""
        NF = namespaces["nf"]
        query = """
        SELECT ?props
        WHERE {
            ?tool a nf:ClinicalAssessmentTool ;
                  nf:psychometricProperties ?props .
            FILTER(CONTAINS(STR(?tool), "cat-002"))
        }
        """
        results = list(cat_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, "Empty psychometricProperties should produce no triple"


class TestClinicalAssessmentToolMultiValue:
    """Test multi-value field handling"""

    def test_validated_languages_split(self, cat_graph, namespaces):
        """validatedLanguages should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?lang
        WHERE {
            ?tool a nf:ClinicalAssessmentTool ;
                  nf:validatedLanguages ?lang .
            FILTER(CONTAINS(STR(?tool), "cat-001"))
        }
        """
        results = list(cat_graph.query(query, initNs={"nf": NF}))
        values = [str(r.lang) for r in results]
        assert "English" in values, "Expected English in validated languages"
        assert "French" in values, "Expected French in validated languages"
        assert len(results) == 2, f"Expected 2 languages, got {len(results)}"

    def test_single_language_not_split(self, cat_graph, namespaces):
        """Single validatedLanguage should produce one triple"""
        NF = namespaces["nf"]
        query = """
        SELECT ?lang
        WHERE {
            ?tool a nf:ClinicalAssessmentTool ;
                  nf:validatedLanguages ?lang .
            FILTER(CONTAINS(STR(?tool), "cat-002"))
        }
        """
        results = list(cat_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].lang) == "English"

    def test_no_empty_literals(self, cat_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(cat_graph.query(query))
        assert len(results) == 0, f"Found {len(results)} empty literal values"
