"""
Tests for Publication Author ORCIDs RML mapping

Tests the publication_author_orcids.rml.ttl mapping against
test/publication_author_orcids.csv
"""

import pytest
from rdflib import URIRef
from rdflib.namespace import RDF


@pytest.fixture
def pub_author_orcid_graph(rml_runner, namespaces):
    """Load publication author ORCID RDF graph from test data"""
    graph = rml_runner(
        mapping_file="publication_author_orcids.rml.ttl",
        csv_replacements={
            "data/csv/publication_author_orcids.csv": "test/publication_author_orcids.csv"
        }
    )
    return graph


@pytest.fixture
def publications_graph(rml_runner, namespaces):
    """Load publications RDF graph from test data"""
    graph = rml_runner(
        mapping_file="publications.rml.ttl",
        csv_replacements={"data/csv/publications.csv": "test/publications.csv"}
    )
    return graph


class TestPublicationAuthorOrcidCore:
    """Test core publication-author-ORCID link properties"""

    def test_doi_subject_is_iri(self, pub_author_orcid_graph):
        """Subjects should be DOI IRIs"""
        NF = "http://nf-osi.github.com/terms#"
        subjects = set(pub_author_orcid_graph.subjects(URIRef(NF + "authorOrcid"), None))
        assert len(subjects) == 2, f"Expected 2 distinct DOIs, got {len(subjects)}"
        for s in subjects:
            assert isinstance(s, URIRef)
            assert str(s).startswith("https://doi.org/")

    def test_doi_not_percent_encoded(self, pub_author_orcid_graph):
        """DOI IRIs should not percent-encode the '/' in the DOI path"""
        NF = "http://nf-osi.github.com/terms#"
        subjects = {str(s) for s in pub_author_orcid_graph.subjects(URIRef(NF + "authorOrcid"), None)}
        assert "https://doi.org/10.1038/test001" in subjects
        assert "https://doi.org/10.1016/test002" in subjects
        assert not any("%2F" in s for s in subjects), \
            f"DOI IRIs should not be percent-encoded: {subjects}"

    def test_author_orcid_is_iri(self, pub_author_orcid_graph, namespaces):
        """authorOrcid objects should be ORCID IRIs"""
        NF = namespaces["nf"]

        query = """
        SELECT ?doi ?orcid
        WHERE {
            ?doi nf:authorOrcid ?orcid .
        }
        """
        results = list(pub_author_orcid_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 3, f"Expected 3 author-orcid links, got {len(results)}"
        for row in results:
            assert isinstance(row.orcid, URIRef)
            assert str(row.orcid).startswith("https://orcid.org/")

    def test_multiple_authors_per_doi(self, pub_author_orcid_graph, namespaces):
        """A single DOI can have multiple author ORCID links"""
        NF = namespaces["nf"]

        query = """
        SELECT ?orcid
        WHERE {
            <https://doi.org/10.1038/test001> nf:authorOrcid ?orcid .
        }
        """
        results = list(pub_author_orcid_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 2, f"Expected 2 authors for test001, got {len(results)}"


class TestPublicationDoiLinkage:
    """Test that the DOI IRI hub matches across publications and author-ORCID links"""

    def test_doi_iri_matches_publication_doi(self, pub_author_orcid_graph, publications_graph, namespaces):
        """The DOI IRI used here should be the same IRI publications.rml.ttl emits via nf:doi"""
        NF = namespaces["nf"]

        pub_query = """
        SELECT ?doi
        WHERE {
            ?publication nf:doi ?doi .
        }
        """
        pub_dois = {str(row.doi) for row in publications_graph.query(pub_query, initNs={"nf": NF})}

        author_orcid_dois = {
            str(s) for s in pub_author_orcid_graph.subjects(URIRef(str(NF) + "authorOrcid"), None)
        }

        shared = pub_dois & author_orcid_dois
        assert len(shared) > 0, (
            f"Expected shared DOI IRIs between publications and publication_author_orcids, "
            f"got publications={pub_dois}, author_orcids={author_orcid_dois}"
        )


# Run with: pytest test/test_rml_publication_author_orcids.py -v
