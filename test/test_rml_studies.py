"""
Tests for Studies RML mapping

Tests the portal_studies.rml.ttl mapping against test/studies.csv
Includes tests for IRI transformation (initiative, fundingAgency)
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def studies_graph(rml_runner, namespaces):
    """Load studies RDF graph from test data (before IRI transformation)"""
    graph = rml_runner(
        mapping_file="portal_studies.rml.ttl",
        csv_replacements={"data/csv/studies.csv": "test/studies.csv"}
    )
    return graph


@pytest.fixture
def studies_graph_transformed(studies_graph, transform_iris):
    """Load studies RDF graph after IRI transformation"""
    return transform_iris(studies_graph)


class TestStudiesCore:
    """Test core study properties"""

    def test_study_has_correct_type(self, studies_graph, namespaces):
        """All studies should have type nf:Study"""
        studies = list(studies_graph.subjects(RDF.type, namespaces["nf"].Study))
        assert len(studies) > 0, "No studies found in graph"

    def test_study_id_is_iri(self, studies_graph, namespaces):
        """Study subjects should be IRIs (Synapse IDs)"""
        studies = list(studies_graph.subjects(RDF.type, namespaces["nf"].Study))
        for study in studies:
            assert isinstance(study, URIRef), \
                f"Study ID should be IRI, got {type(study)}"
            # Should contain synapse ID format
            study_str = str(study)
            assert "syn" in study_str.lower(), \
                f"Study IRI should contain Synapse ID: {study_str}"

    def test_studies_exist(self, studies_graph, namespaces):
        """Studies should exist in the graph"""
        NF = namespaces["nf"]

        query = """
        SELECT ?study
        WHERE {
            ?study a nf:Study .
        }
        """
        results = list(studies_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Should have Study entities"


class TestStudiesIRITransformation:
    """Test IRI transformation for initiative and fundingAgency fields"""

    def test_initiative_with_spaces_becomes_iri(self, studies_graph_transformed, namespaces):
        """Initiative with spaces should become IRI with underscores"""
        NF = namespaces["nf"]

        # "Cutaneous Neurofibroma Initiative" should become nf:Cutaneous_Neurofibroma_Initiative
        query = """
        SELECT ?study ?initiative
        WHERE {
            ?study a nf:Study ;
                   nf:initiative ?initiative .
        }
        """
        results = studies_graph_transformed.query(query, initNs={"nf": NF})
        initiatives = [str(row.initiative) for row in results]

        # Check for transformed IRI
        assert any("Cutaneous_Neurofibroma_Initiative" in init for init in initiatives), \
            f"Expected 'Cutaneous_Neurofibroma_Initiative' IRI, got {initiatives}"

    def test_initiative_without_spaces(self, studies_graph_transformed, namespaces):
        """Initiative without spaces should remain as is"""
        NF = namespaces["nf"]

        query = """
        SELECT ?study ?initiative
        WHERE {
            ?study a nf:Study ;
                   nf:initiative ?initiative .
        }
        """
        results = studies_graph_transformed.query(query, initNs={"nf": NF})
        initiatives = [str(row.initiative) for row in results]

        # "Synodos" should be found as an IRI
        assert any("Synodos" in init for init in initiatives), \
            f"Expected 'Synodos' IRI, got {initiatives}"

    def test_funding_agency_with_spaces_becomes_iri(self, studies_graph_transformed, namespaces):
        """FundingAgency with spaces should become IRI with underscores"""
        NF = namespaces["nf"]

        # "CTF Foundation" should become nf:CTF_Foundation
        query = """
        SELECT ?study ?funder
        WHERE {
            ?study a nf:Study ;
                   nf:hasFunder ?funder .
        }
        """
        results = studies_graph_transformed.query(query, initNs={"nf": NF})
        funders = [str(row.funder) for row in results]

        assert any("CTF_Foundation" in funder for funder in funders), \
            f"Expected 'CTF_Foundation' IRI, got {funders}"

    def test_funding_agency_without_spaces(self, studies_graph_transformed, namespaces):
        """FundingAgency without spaces should remain as is"""
        NF = namespaces["nf"]

        query = """
        SELECT ?study ?funder
        WHERE {
            ?study a nf:Study ;
                   nf:hasFunder ?funder .
        }
        """
        results = studies_graph_transformed.query(query, initNs={"nf": NF})
        funders = [str(row.funder) for row in results]

        # "NTAP" should be found as an IRI
        assert any("NTAP" in funder for funder in funders), \
            f"Expected 'NTAP' IRI, got {funders}"

    def test_gilbert_family_foundation_transformation(self, studies_graph_transformed, namespaces):
        """Gilbert Family Foundation should transform correctly"""
        NF = namespaces["nf"]

        query = """
        SELECT ?study ?funder
        WHERE {
            ?study a nf:Study ;
                   nf:hasFunder ?funder .
        }
        """
        results = studies_graph_transformed.query(query, initNs={"nf": NF})
        funders = [str(row.funder) for row in results]

        assert any("Gilbert_Family_Foundation" in funder for funder in funders), \
            f"Expected 'Gilbert_Family_Foundation' IRI, got {funders}"

    def test_no_url_encoded_spaces(self, studies_graph_transformed):
        """Transformed IRIs should not contain %20 (URL-encoded spaces)"""
        # Get all triples and check objects for %20
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(CONTAINS(STR(?o), "%20"))
        }
        """
        results = list(studies_graph_transformed.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} IRIs with %20 encoding"


class TestStudiesMultiValue:
    """Test multi-value field handling"""

    def test_study_leads_multi_value_split(self, studies_graph, namespaces):
        """StudyLeads should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?study ?lead
        WHERE {
            ?study a nf:Study ;
                   nf:studyLeads ?lead .
        }
        """
        results = list(studies_graph.query(query, initNs={"nf": NF}))

        # Should have multiple study leads from pipe-delimited values
        assert len(results) > 0, "Expected study leads"


class TestStudiesEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_study_leads_produces_no_triple(self, studies_graph, namespaces):
        """Empty studyLeads should not create triple"""
        NF = namespaces["nf"]

        # syn0000004 should have empty studyLeads
        query = """
        SELECT ?lead
        WHERE {
            <https://www.synapse.org/#!Synapse:syn0000004> nf:studyLeads ?lead .
        }
        """
        results = list(studies_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty studyLeads should not produce triple"

    def test_no_empty_literal_values(self, studies_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(studies_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


class TestStudiesIRIFields:
    """Test that appropriate fields are IRIs after transformation"""

    def test_initiative_is_iri_after_transformation(self, studies_graph_transformed, namespaces):
        """Initiative should be IRI, not literal, after transformation"""
        NF = namespaces["nf"]

        query = """
        SELECT ?study ?initiative
        WHERE {
            ?study a nf:Study ;
                   nf:initiative ?initiative .
        }
        """
        results = list(studies_graph_transformed.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "No initiatives found"

        for row in results:
            assert isinstance(row.initiative, URIRef), \
                f"Initiative should be IRI after transformation, got {type(row.initiative)}: {row.initiative}"

    def test_has_funder_is_iri_after_transformation(self, studies_graph_transformed, namespaces):
        """hasFunder should link to IRI, not literal, after transformation"""
        NF = namespaces["nf"]

        query = """
        SELECT ?study ?funder
        WHERE {
            ?study a nf:Study ;
                   nf:hasFunder ?funder .
        }
        """
        results = list(studies_graph_transformed.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "No funders found"

        for row in results:
            assert isinstance(row.funder, URIRef), \
                f"Funder should be IRI after transformation, got {type(row.funder)}: {row.funder}"


# Run with: pytest test/test_rml_studies.py -v
