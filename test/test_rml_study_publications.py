"""
Tests for Study Publications RML mapping (main portal listing, syn16857542)

Tests study_publications.rml.ttl against test/study_publications.csv.
This source has no stable primary key, so publications are keyed by DOI with a
"pmid-<pmid>" fallback -- see apply_derived_columns in prepare_portal_tables.py.
"""

import pytest
from rdflib import URIRef, Namespace
from rdflib.namespace import RDF, RDFS

PROV = Namespace("http://www.w3.org/ns/prov#")


@pytest.fixture
def study_pub_graph(rml_runner):
    return rml_runner(
        mapping_file="study_publications.rml.ttl",
        csv_replacements={
            "data/csv/study_publications.csv": "test/study_publications.csv"
        },
    )


class TestStudyPublicationKeying:
    """Subjects are keyed by DOI, falling back to pmid."""

    def test_only_rows_with_a_key_become_publications(self, study_pub_graph, namespaces):
        """The fixture's fourth row has neither DOI nor PMID and must be skipped."""
        pubs = list(study_pub_graph.subjects(RDF.type, namespaces["biolink"].Publication))
        assert len(pubs) == 3, f"Expected 3 publications (1 row skipped), got {len(pubs)}"
        assert not any("Ghost" in str(o) for o in study_pub_graph.objects(None, RDFS.label))

    def test_doi_keyed_subject(self, study_pub_graph, namespaces):
        pubs = {str(p) for p in study_pub_graph.subjects(RDF.type, namespaces["biolink"].Publication)}
        # rr:template percent-escapes the "/" inside the DOI
        assert any("10.1000%2Fvalid-doi" in p for p in pubs), pubs

    def test_pmid_fallback_subject(self, study_pub_graph, namespaces):
        """A row whose doi column was not a real DOI is keyed by pmid instead."""
        pubs = {str(p) for p in study_pub_graph.subjects(RDF.type, namespaces["biolink"].Publication)}
        assert any(p.endswith("publication/pmid-22222222") for p in pubs), pubs

    def test_no_doi_emitted_when_source_doi_was_not_a_doi(self, study_pub_graph, namespaces):
        """cleanDoi is blank for the fallback row, so it must not get an nf:doi
        pointing at a bogus doi.org IRI."""
        NF = namespaces["nf"]
        subj = URIRef("http://nf-osi.github.com/terms#publication/pmid-22222222")
        assert list(study_pub_graph.objects(subj, NF.doi)) == []
        # ...but it still gets a pmid
        assert list(study_pub_graph.objects(subj, NF.pmid)) != []

    def test_real_doi_is_not_percent_escaped_in_nf_doi(self, study_pub_graph, namespaces):
        """The nf:doi value is the join key, so its "/" must stay unescaped."""
        NF = namespaces["nf"]
        dois = {str(o) for o in study_pub_graph.objects(None, NF.doi)}
        assert "https://doi.org/10.1000/valid-doi" in dois, dois
        assert not any("%2F" in d for d in dois), dois


class TestStudyPublicationContent:
    def test_carries_source_collection(self, study_pub_graph, namespaces):
        """Every node records that it came from the main portal listing, so it
        stays distinguishable from Tools Central publications."""
        NF = namespaces["nf"]
        pubs = list(study_pub_graph.subjects(RDF.type, namespaces["biolink"].Publication))
        for pub in pubs:
            assert list(study_pub_graph.objects(pub, PROV.wasDerivedFrom)) == \
                [NF.MainPortalPublications], f"{pub} missing MainPortalPublications provenance"

    def test_multi_valued_study_links(self, study_pub_graph, namespaces):
        """studyId is a list; each becomes its own nf:aboutStudy Synapse IRI."""
        NF = namespaces["nf"]
        subj = URIRef("http://nf-osi.github.com/terms#publication/10.1000%2Fvalid-doi")
        studies = {str(o) for o in study_pub_graph.objects(subj, NF.aboutStudy)}
        assert studies == {
            "https://www.synapse.org/Synapse:syn111111",
            "https://www.synapse.org/Synapse:syn222222",
        }, studies

    def test_no_study_link_when_blank(self, study_pub_graph, namespaces):
        NF = namespaces["nf"]
        subj = URIRef("http://nf-osi.github.com/terms#publication/10.1000%2Fno-study")
        assert list(study_pub_graph.objects(subj, NF.aboutStudy)) == []

    def test_authors_split_on_pipe(self, study_pub_graph, namespaces):
        NF = namespaces["nf"]
        subj = URIRef("http://nf-osi.github.com/terms#publication/10.1000%2Fvalid-doi")
        authors = {str(o) for o in study_pub_graph.objects(subj, NF.authors)}
        assert authors == {"Jane Doe", "John Smith"}, authors

    def test_no_empty_literals(self, study_pub_graph):
        results = list(study_pub_graph.query(
            'SELECT ?s ?p ?o WHERE { ?s ?p ?o . FILTER(isLiteral(?o) && str(?o) = "") }'
        ))
        assert len(results) == 0, f"Found {len(results)} empty literals"


# Run with: pytest test/test_rml_study_publications.py -v
