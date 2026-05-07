"""
Tests for Computational Tools RML mapping

Tests the computational_tools.rml.ttl mapping against test/computational_tools.csv
"""

import pytest
from rdflib import URIRef, Literal, Namespace
from rdflib.namespace import RDF


@pytest.fixture
def ct_graph(rml_runner, namespaces):
    """Load computational tools RDF graph from test data"""
    graph = rml_runner(
        mapping_file="computational_tools.rml.ttl",
        csv_replacements={
            "data/csv/computational_tools.csv": "test/computational_tools.csv"
        }
    )
    return graph


class TestComputationalToolCore:
    """Test core computational tool properties"""

    def test_has_correct_type(self, ct_graph, namespaces):
        """All entries should have type nf:ComputationalTool"""
        tools = list(ct_graph.subjects(RDF.type, namespaces["nf"].ComputationalTool))
        assert len(tools) == 3, f"Expected 3 computational tools, got {len(tools)}"

    def test_subject_is_iri(self, ct_graph, namespaces):
        """Subjects should be IRIs"""
        tools = list(ct_graph.subjects(RDF.type, namespaces["nf"].ComputationalTool))
        for tool in tools:
            assert isinstance(tool, URIRef), f"Subject should be IRI, got {type(tool)}"

    def test_iri_uses_correct_template(self, ct_graph, namespaces):
        """IRI should use computationalTool/{id} pattern"""
        tools = list(ct_graph.subjects(RDF.type, namespaces["nf"].ComputationalTool))
        iris = [str(t) for t in tools]
        assert any("computationalTool/ct-001" in iri for iri in iris), \
            f"Expected IRI with computationalTool/ct-001, got: {iris}"

    def test_software_name_present(self, ct_graph, namespaces):
        """softwareName should be present"""
        NF = namespaces["nf"]
        query = """
        SELECT ?name
        WHERE {
            ?tool a nf:ComputationalTool ;
                  nf:softwareName ?name .
            FILTER(CONTAINS(STR(?tool), "ct-001"))
        }
        """
        results = list(ct_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].name) == "NF-Classifier"

    def test_software_version_present(self, ct_graph, namespaces):
        """softwareVersion should be present"""
        NF = namespaces["nf"]
        query = """
        SELECT ?ver
        WHERE {
            ?tool a nf:ComputationalTool ;
                  nf:softwareVersion ?ver .
            FILTER(CONTAINS(STR(?tool), "ct-001"))
        }
        """
        results = list(ct_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].ver) == "1.2.0"

    def test_license_type_present(self, ct_graph, namespaces):
        """licenseType should be present"""
        NF = namespaces["nf"]
        query = """
        SELECT ?lic
        WHERE {
            ?tool a nf:ComputationalTool ;
                  nf:licenseType ?lic .
            FILTER(CONTAINS(STR(?tool), "ct-001"))
        }
        """
        results = list(ct_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].lic) == "MIT"

    def test_source_repository_is_iri(self, ct_graph, namespaces):
        """sourceRepository should be an IRI"""
        NF = namespaces["nf"]
        query = """
        SELECT ?repo
        WHERE {
            ?tool a nf:ComputationalTool ;
                  nf:sourceRepository ?repo .
            FILTER(CONTAINS(STR(?tool), "ct-001"))
        }
        """
        results = list(ct_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].repo, URIRef), "sourceRepository should be IRI"
        assert str(results[0].repo) == "https://github.com/nf-osi/nf-classifier"

    def test_documentation_is_iri(self, ct_graph, namespaces):
        """documentation should be an IRI"""
        NF = namespaces["nf"]
        query = """
        SELECT ?doc
        WHERE {
            ?tool a nf:ComputationalTool ;
                  nf:documentation ?doc .
            FILTER(CONTAINS(STR(?tool), "ct-001"))
        }
        """
        results = list(ct_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].doc, URIRef)

    def test_empty_fields_produce_no_triple(self, ct_graph, namespaces):
        """Empty analyticalPlatformSupport should not produce a triple"""
        NF = namespaces["nf"]
        query = """
        SELECT ?plat
        WHERE {
            ?tool a nf:ComputationalTool ;
                  nf:analyticalPlatformSupport ?plat .
            FILTER(CONTAINS(STR(?tool), "ct-002"))
        }
        """
        results = list(ct_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, "Empty analyticalPlatformSupport should produce no triple"


class TestComputationalToolMultiValue:
    """Test multi-value field handling"""

    def test_programming_language_split(self, ct_graph, namespaces):
        """programmingLanguage should split on pipe"""
        NF = namespaces["nf"]
        query = """
        SELECT ?lang
        WHERE {
            ?tool a nf:ComputationalTool ;
                  nf:programmingLanguage ?lang .
            FILTER(CONTAINS(STR(?tool), "ct-001"))
        }
        """
        results = list(ct_graph.query(query, initNs={"nf": NF}))
        values = [str(r.lang) for r in results]
        assert "Python" in values
        assert "R" in values
        assert len(results) == 2

    def test_dependencies_split(self, ct_graph, namespaces):
        """dependencies should split on pipe"""
        NF = namespaces["nf"]
        query = """
        SELECT ?dep
        WHERE {
            ?tool a nf:ComputationalTool ;
                  nf:dependencies ?dep .
            FILTER(CONTAINS(STR(?tool), "ct-001"))
        }
        """
        results = list(ct_graph.query(query, initNs={"nf": NF}))
        values = [str(r.dep) for r in results]
        assert "scikit-learn" in values
        assert "pandas" in values
        assert "rpy2" in values
        assert len(results) == 3

    def test_no_empty_literals(self, ct_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(ct_graph.query(query))
        assert len(results) == 0, f"Found {len(results)} empty literal values"
