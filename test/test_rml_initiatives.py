"""
Tests for Initiatives RML mapping

Tests the initiatives.rml.ttl mapping against test/initiatives.csv.
IRIs are constructed from the initiative name (spaces → underscores),
matching the pattern already used in studies.rml.ttl for nf:initiative links.
"""

import pytest
from rdflib import URIRef, Literal, Namespace
from rdflib.namespace import RDF


NF = Namespace("http://nf-osi.github.com/terms#")


@pytest.fixture
def initiative_graph(rml_runner, namespaces):
    """Load initiatives RDF graph from test data"""
    graph = rml_runner(
        mapping_file="initiatives.rml.ttl",
        csv_replacements={
            "data/csv/initiatives.csv": "test/initiatives.csv"
        }
    )
    return graph


class TestInitiativeCore:
    """Test core initiative properties"""

    def test_has_correct_type(self, initiative_graph, namespaces):
        """All entries should have type nf:Initiative"""
        initiatives = list(initiative_graph.subjects(RDF.type, NF.Initiative))
        assert len(initiatives) == 3, f"Expected 3 initiatives, got {len(initiatives)}"

    def test_subject_is_iri(self, initiative_graph, namespaces):
        """Subjects should be IRIs"""
        initiatives = list(initiative_graph.subjects(RDF.type, NF.Initiative))
        for ini in initiatives:
            assert isinstance(ini, URIRef), f"Subject should be IRI, got {type(ini)}"

    def test_iri_encodes_spaces_as_underscores(self, initiative_graph, namespaces):
        """IRI should replace spaces with underscores for the CTF initiative"""
        initiatives = list(initiative_graph.subjects(RDF.type, NF.Initiative))
        iris = [str(i) for i in initiatives]
        # "Children's_Tumor_Foundation" — spaces replaced by underscores in initiativeKey column
        assert any("Tumor_Foundation" in iri for iri in iris), \
            f"Expected underscore-encoded initiative IRI, got: {iris}"

    def test_name_present(self, initiative_graph, namespaces):
        """nf:name should contain the initiative full name"""
        query = """
        SELECT ?ini ?name
        WHERE {
            ?ini a nf:Initiative ;
                 nf:name ?name .
            FILTER(CONTAINS(STR(?ini), "Children"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].name) == "Children's Tumor Foundation"

    def test_abbreviation_present(self, initiative_graph, namespaces):
        """abbreviation should be present"""
        query = """
        SELECT ?abbr
        WHERE {
            ?ini a nf:Initiative ;
                 nf:abbreviation ?abbr .
            FILTER(CONTAINS(STR(?ini), "Children"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].abbr) == "CTF"

    def test_description_present(self, initiative_graph, namespaces):
        """nf:description (from summary) should be present"""
        query = """
        SELECT ?desc
        WHERE {
            ?ini a nf:Initiative ;
                 nf:description ?desc .
            FILTER(CONTAINS(STR(?ini), "Children"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert "NF research" in str(results[0].desc)

    def test_website_is_iri(self, initiative_graph, namespaces):
        """website should be an IRI"""
        query = """
        SELECT ?web
        WHERE {
            ?ini a nf:Initiative ;
                 nf:website ?web .
            FILTER(CONTAINS(STR(?ini), "Children"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].web, URIRef)
        assert str(results[0].web) == "https://www.ctf.org"

    def test_funder_links_present(self, initiative_graph, namespaces):
        """hasFunder should link to funder IRIs"""
        query = """
        SELECT ?funder
        WHERE {
            ?ini a nf:Initiative ;
                 nf:hasFunder ?funder .
            FILTER(CONTAINS(STR(?ini), "Therapeutic_Acceleration"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) >= 1, "NTAP initiative should have at least one funder"
        for row in results:
            assert isinstance(row.funder, URIRef), "hasFunder should be IRI"


class TestInitiativeMultiValue:
    """Test multi-value funding agency handling"""

    def test_single_funder(self, initiative_graph, namespaces):
        """CTF should have exactly one funder"""
        query = """
        SELECT ?funder
        WHERE {
            ?ini a nf:Initiative ;
                 nf:hasFunder ?funder .
            FILTER(CONTAINS(STR(?ini), "Children"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1

    def test_multi_funder(self, initiative_graph, namespaces):
        """NTAP should have two funders (NTAP|JHMI)"""
        query = """
        SELECT ?funder
        WHERE {
            ?ini a nf:Initiative ;
                 nf:hasFunder ?funder .
            FILTER(CONTAINS(STR(?ini), "Therapeutic_Acceleration"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 2, f"Expected 2 funders for NTAP, got {len(results)}"

    def test_no_empty_literals(self, initiative_graph):
        """Graph should not contain empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(initiative_graph.query(query))
        assert len(results) == 0, f"Found {len(results)} empty literal values"
