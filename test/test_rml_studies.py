"""
Tests for Studies RML mapping

Tests the studies.rml.ttl mapping against test/studies.csv
Includes tests for IRI transformation (initiative, fundingAgency, dataType)
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def studies_graph(rml_runner, namespaces):
    """Load studies RDF graph from test data"""
    graph = rml_runner(
        mapping_file="studies.rml.ttl",
        csv_replacements={"data/csv/studies_harmonized.csv": "test/studies.csv"}
    )
    return graph


SYN_BASE = "https://www.synapse.org/Synapse:"


class TestStudiesCore:
    """Test core study properties"""

    def test_study_has_correct_type(self, studies_graph, namespaces):
        """All studies should have type biolink:Study"""
        studies = list(studies_graph.subjects(RDF.type, namespaces["biolink"].Study))
        assert len(studies) > 0

    def test_study_id_is_iri(self, studies_graph, namespaces):
        """Study subjects should be Synapse URL IRIs"""
        studies = list(studies_graph.subjects(RDF.type, namespaces["biolink"].Study))
        for study in studies:
            assert isinstance(study, URIRef)
            assert str(study).startswith(SYN_BASE), \
                f"Study IRI should start with {SYN_BASE}, got {study}"

    def test_studies_exist(self, studies_graph, namespaces):
        """Should have at least 4 studies"""
        BIOLINK = namespaces["biolink"]
        query = """
        SELECT ?study WHERE { ?study a biolink:Study . }
        """
        results = list(studies_graph.query(query, initNs={"biolink": BIOLINK}))
        assert len(results) >= 4


class TestStudiesMultiValue:
    """Test multi-value field handling"""

    def test_study_leads_multi_value_split(self, studies_graph, namespaces):
        """StudyLeads should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?lead WHERE {
            <https://www.synapse.org/Synapse:syn0000002> nf:studyLeads ?lead .
        }
        """
        leads = [str(r.lead) for r in studies_graph.query(query, initNs={"nf": NF})]
        assert "John Smith" in leads
        assert "Alice Brown" in leads

    def test_institutions_multi_value_split(self, studies_graph, namespaces):
        """Institutions should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?inst WHERE {
            <https://www.synapse.org/Synapse:syn0000002> nf:institutions ?inst .
        }
        """
        insts = [str(r.inst) for r in studies_graph.query(query, initNs={"nf": NF})]
        assert "University A" in insts
        assert "University B" in insts

    def test_manifestation_multi_value_split(self, studies_graph, namespaces):
        """Manifestation should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?m WHERE {
            <https://www.synapse.org/Synapse:syn0000003> nf:manifestation ?m .
        }
        """
        manifestations = [str(r.m) for r in studies_graph.query(query, initNs={"nf": NF})]
        assert "Schwannoma" in manifestations
        assert "Meningioma" in manifestations

    def test_disease_focus_multi_value_split(self, studies_graph, namespaces):
        """DiseaseFocus should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?df WHERE {
            <https://www.synapse.org/Synapse:syn0000003> nf:diseaseFocus ?df .
        }
        """
        foci = [str(r.df) for r in studies_graph.query(query, initNs={"nf": NF})]
        assert "Neurofibromatosis type 1" in foci
        assert "Neurofibromatosis type 2" in foci


class TestStudiesIRIFields:
    """Test IRI-valued fields"""

    def test_data_type_iri(self, studies_graph, namespaces):
        """dataType should emit IRIs from dataTypeIRI column"""
        NF = namespaces["nf"]
        query = """
        SELECT ?dt WHERE {
            <https://www.synapse.org/Synapse:syn0000001> nf:dataType ?dt .
        }
        """
        iris = [str(r.dt) for r in studies_graph.query(query, initNs={"nf": NF})]
        assert "http://nf-osi.github.com/terms#GeneExpression" in iris
        assert "http://nf-osi.github.com/terms#DrugScreen" in iris

    def test_related_studies_iri(self, studies_graph, namespaces):
        """relatedStudies should emit Synapse IRIs"""
        NF = namespaces["nf"]
        query = """
        SELECT ?rs WHERE {
            <https://www.synapse.org/Synapse:syn0000003> nf:relatedStudies ?rs .
        }
        """
        iris = [str(r.rs) for r in studies_graph.query(query, initNs={"nf": NF})]
        assert len(iris) == 2
        assert "https://www.synapse.org/Synapse:syn0000001" in iris
        assert "https://www.synapse.org/Synapse:syn0000002" in iris

    def test_grant_doi_iri(self, studies_graph, namespaces):
        """grantDOI should emit DOI IRI"""
        NF = namespaces["nf"]
        query = """
        SELECT ?doi WHERE {
            <https://www.synapse.org/Synapse:syn0000001> nf:grantDOI ?doi .
        }
        """
        results = list(studies_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0
        assert "https://doi.org/10.1234/test1" in [str(r.doi) for r in results]

    def test_grant_doi_placeholder_produces_no_triple(self, studies_graph, namespaces):
        """A non-URL placeholder value (e.g. 'N/A') should not produce a grantDOI triple"""
        NF = namespaces["nf"]
        query = """
        SELECT ?doi WHERE {
            <https://www.synapse.org/Synapse:syn0000005> nf:grantDOI ?doi .
        }
        """
        results = list(studies_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0

    def test_initiative_iri(self, studies_graph, namespaces):
        """Initiative should be an IRI with spaces replaced"""
        NF = namespaces["nf"]
        query = """
        SELECT ?init WHERE {
            <https://www.synapse.org/Synapse:syn0000003> nf:initiative ?init .
        }
        """
        results = list(studies_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0
        init_str = str(results[0].init)
        assert isinstance(results[0].init, URIRef)
        assert "Synodos" in init_str


class TestStudiesEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_study_leads_produces_no_triple(self, studies_graph, namespaces):
        """Empty studyLeads should not create triple"""
        NF = namespaces["nf"]
        query = """
        SELECT ?lead WHERE {
            <https://www.synapse.org/Synapse:syn0000004> nf:studyLeads ?lead .
        }
        """
        results = list(studies_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0

    def test_no_empty_literal_values(self, studies_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(studies_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


# Run with: pytest test/test_rml_studies.py -v
