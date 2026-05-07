"""
Tests for Initiatives RML mapping

Tests the initiatives.rml.ttl mapping against test/initiatives.csv.
IRIs are constructed from the initiativeKey column (initiative name with spaces
replaced by underscores), matching the IRI scheme used in studies.rml.ttl.
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
        assert len(initiatives) == 4, f"Expected 4 initiatives, got {len(initiatives)}"

    def test_subject_is_iri(self, initiative_graph, namespaces):
        """Subjects should be IRIs"""
        initiatives = list(initiative_graph.subjects(RDF.type, NF.Initiative))
        for ini in initiatives:
            assert isinstance(ini, URIRef), f"Subject should be IRI, got {type(ini)}"

    def test_iri_uses_underscores_for_spaces(self, initiative_graph, namespaces):
        """IRI should use underscores in place of spaces"""
        initiatives = list(initiative_graph.subjects(RDF.type, NF.Initiative))
        iris = [str(i) for i in initiatives]
        assert any("Brain_Tumor_Initiative" in iri for iri in iris), \
            f"Expected underscore-encoded IRI, got: {iris}"

    def test_name_is_full_initiative_name(self, initiative_graph, namespaces):
        """nf:name should be the full human-readable initiative name"""
        query = """
        SELECT ?name
        WHERE {
            ?ini a nf:Initiative ;
                 nf:name ?name .
            FILTER(CONTAINS(STR(?ini), "Brain_Tumor_Initiative"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].name) == "Brain Tumor Initiative"

    def test_abbreviation_present(self, initiative_graph, namespaces):
        """abbreviation should be present"""
        query = """
        SELECT ?abbr
        WHERE {
            ?ini a nf:Initiative ;
                 nf:abbreviation ?abbr .
            FILTER(CONTAINS(STR(?ini), "Brain_Tumor_Initiative"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].abbr) == "BTI"

    def test_description_from_summary(self, initiative_graph, namespaces):
        """nf:description should contain the initiative summary text"""
        query = """
        SELECT ?desc
        WHERE {
            ?ini a nf:Initiative ;
                 nf:description ?desc .
            FILTER(CONTAINS(STR(?ini), "Brain_Tumor_Initiative"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert "Gilbert Family Foundation" in str(results[0].desc)

    def test_website_is_iri(self, initiative_graph, namespaces):
        """website should be an IRI"""
        query = """
        SELECT ?web
        WHERE {
            ?ini a nf:Initiative ;
                 nf:website ?web .
            FILTER(CONTAINS(STR(?ini), "Brain_Tumor_Initiative"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].web, URIRef)
        assert "gilbertfamilyfoundation" in str(results[0].web)

    def test_empty_website_produces_no_triple(self, initiative_graph, namespaces):
        """BTD has no website — should produce no website triple"""
        query = """
        SELECT ?web
        WHERE {
            ?ini a nf:Initiative ;
                 nf:website ?web .
            FILTER(CONTAINS(STR(?ini), "Biology_and_Therapeutic"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, "BTD has no website — should produce no triple"

    def test_funder_is_iri(self, initiative_graph, namespaces):
        """hasFunder should link to a funder IRI"""
        query = """
        SELECT ?funder
        WHERE {
            ?ini a nf:Initiative ;
                 nf:hasFunder ?funder .
            FILTER(CONTAINS(STR(?ini), "Brain_Tumor_Initiative"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].funder, URIRef)
        assert "GFF" in str(results[0].funder)

    def test_long_summary_preserved(self, initiative_graph, namespaces):
        """Multi-sentence summary (with commas) should be stored as a single literal"""
        query = """
        SELECT ?desc
        WHERE {
            ?ini a nf:Initiative ;
                 nf:description ?desc .
            FILTER(CONTAINS(STR(?ini), "Biology_and_Therapeutic"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        desc = str(results[0].desc)
        assert "9 laboratories" in desc
        assert "NF1" in desc

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


class TestInitiativeFunders:
    """Test funder link handling"""

    def test_ntap_initiatives_have_funder(self, initiative_graph, namespaces):
        """BTD, CCI, and cNF are all funded by NTAP"""
        query = """
        SELECT ?ini ?funder
        WHERE {
            ?ini a nf:Initiative ;
                 nf:hasFunder ?funder .
            FILTER(CONTAINS(STR(?funder), "NTAP"))
        }
        """
        results = list(initiative_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 3, \
            f"Expected 3 NTAP-funded initiatives, got {len(results)}"

    def test_all_initiatives_have_at_least_one_funder(self, initiative_graph, namespaces):
        """Every initiative should have at least one funder"""
        query = """
        SELECT DISTINCT ?ini
        WHERE { ?ini a nf:Initiative ; nf:hasFunder ?funder . }
        """
        with_funders = list(initiative_graph.query(query, initNs={"nf": NF}))
        all_ini = list(initiative_graph.subjects(RDF.type, NF.Initiative))
        assert len(with_funders) == len(all_ini), \
            "All initiatives should have at least one funder"
