"""
Tests for Development RML mappings

Tests mappings for development-related entities:
- development.rml.ttl  (junction table relationships)
- funders.rml.ttl
- investigators.rml.ttl
- publications.rml.ttl
"""

import pytest
from rdflib import URIRef, Literal, Namespace
from rdflib.namespace import RDF


class TestFunder:
    """Test funder entity properties"""

    @pytest.fixture
    def funder_graph(self, rml_runner):
        """Load funder graph"""
        return rml_runner(
            mapping_file="funders.rml.ttl",
            csv_replacements={
                "data/csv/funders.csv": "test/funders.csv"
            }
        )

    def test_funders_have_correct_type(self, funder_graph, namespaces):
        """Funders should have type nf:Funder"""
        NF = namespaces["nf"]
        funders = list(funder_graph.subjects(RDF.type, NF.Funder))
        assert len(funders) > 0, "No funders found in graph"
        assert len(funders) >= 3, f"Expected at least 3 funders, got {len(funders)}"

    def test_funders_have_names(self, funder_graph, namespaces):
        """Funders should have funderName property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?funder ?name
        WHERE {
            ?funder a nf:Funder ;
                    nf:name ?name .
        }
        """
        results = list(funder_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No funders with names found"

        names = [str(row.name) for row in results]
        assert "NTAP" in names, "Expected NTAP funder from test data"
        assert "Children's Tumor Foundation" in names, "Expected CTF funder from test data"

    def test_funder_ids_are_iris(self, funder_graph, namespaces):
        """Funder IDs should be IRIs, not literals"""
        NF = namespaces["nf"]

        query = """
        SELECT ?funder
        WHERE {
            ?funder a nf:Funder .
        }
        """
        results = list(funder_graph.query(query, initNs={"nf": NF}))

        for row in results:
            assert isinstance(row.funder, URIRef), \
                f"Funder {row.funder} should be IRI, not literal"


class TestInvestigator:
    """Test investigator entity properties"""

    @pytest.fixture
    def investigator_graph(self, rml_runner):
        """Load investigator graph"""
        return rml_runner(
            mapping_file="investigators.rml.ttl",
            csv_replacements={
                "data/csv/investigators.csv": "test/investigators.csv"
            }
        )

    def test_investigators_have_correct_type(self, investigator_graph, namespaces):
        """Investigators should have type nf:Investigator"""
        NF = namespaces["nf"]
        investigators = list(investigator_graph.subjects(RDF.type, NF.Investigator))
        assert len(investigators) > 0, "No investigators found in graph"
        assert len(investigators) >= 3, f"Expected at least 3 investigators, got {len(investigators)}"

    def test_investigators_have_names(self, investigator_graph, namespaces):
        """Investigators should have investigatorName property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?investigator ?name
        WHERE {
            ?investigator a nf:Investigator ;
                         nf:name ?name .
        }
        """
        results = list(investigator_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No investigators with names found"

        names = [str(row.name) for row in results]
        assert "John Smith" in names, "Expected John Smith from test data"
        assert "Jane Doe" in names, "Expected Jane Doe from test data"

    def test_investigators_have_institutions(self, investigator_graph, namespaces):
        """Investigators should have institution property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?investigator ?institution
        WHERE {
            ?investigator a nf:Investigator ;
                         nf:institution ?institution .
        }
        """
        results = list(investigator_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No investigators with institutions found"

        institutions = [str(row.institution) for row in results]
        assert "Johns Hopkins University" in institutions, "Expected JHU from test data"

    def test_investigators_have_same_as_orcid_and_profile(self, investigator_graph, namespaces):
        """Investigators should have owl:sameAs links to both their ORCID and Synapse profile IRIs"""
        NF = namespaces["nf"]
        OWL = namespaces["owl"]

        query = """
        SELECT ?investigator ?sameAs
        WHERE {
            ?investigator a nf:Investigator ;
                         owl:sameAs ?sameAs .
        }
        """
        results = list(investigator_graph.query(query, initNs={"nf": NF, "owl": OWL}))
        assert len(results) > 0, "No investigators with owl:sameAs found"

        # owl:sameAs objects should be IRIs
        for row in results:
            assert isinstance(row.sameAs, URIRef), \
                f"owl:sameAs target {row.sameAs} should be IRI, not literal"

        # An investigator should have at most one orcid.org and one Synapse
        # Profile sameAs each (an investigator can have just an orcid with no
        # Synapse profile on record, e.g. test-data inv-004, but never more
        # than one of each)
        by_investigator = {}
        for row in results:
            by_investigator.setdefault(row.investigator, []).append(str(row.sameAs))

        for investigator, targets in by_investigator.items():
            orcid_targets = [t for t in targets if t.startswith("https://orcid.org/")]
            profile_targets = [t for t in targets if t.startswith("https://www.synapse.org/Profile:")]
            assert len(orcid_targets) == 1, \
                f"Expected exactly 1 orcid.org sameAs for {investigator}, got {orcid_targets}"
            assert len(profile_targets) <= 1, \
                f"Expected at most 1 Synapse Profile sameAs for {investigator}, got {profile_targets}"

        # inv-001..003 have both; inv-004 (test data) has only an orcid
        investigators_with_profile = sum(
            1 for targets in by_investigator.values()
            if any(t.startswith("https://www.synapse.org/Profile:") for t in targets)
        )
        assert investigators_with_profile == 3, \
            f"Expected 3 investigators with a Synapse profile sameAs, got {investigators_with_profile}"

    def test_orcid_profile_direct_link_materialized(self, investigator_graph, namespaces):
        """ORCID and Synapse Profile IRIs should be directly linked via owl:sameAs
        (both directions) when an investigator record has both -- this makes the
        link discoverable via plain SPARQL without going through the investigator
        node, matching the direct link the People ingest produces."""
        OWL = namespaces["owl"]

        query = """
        SELECT ?orcid ?profile
        WHERE {
            ?orcid owl:sameAs ?profile .
            FILTER(STRSTARTS(STR(?orcid), "https://orcid.org/"))
            FILTER(STRSTARTS(STR(?profile), "https://www.synapse.org/Profile:"))
        }
        """
        forward = list(investigator_graph.query(query, initNs={"owl": OWL}))
        assert len(forward) == 3, f"Expected 3 direct orcid->profile links, got {len(forward)}"

        reverse_query = """
        SELECT ?profile ?orcid
        WHERE {
            ?profile owl:sameAs ?orcid .
            FILTER(STRSTARTS(STR(?profile), "https://www.synapse.org/Profile:"))
            FILTER(STRSTARTS(STR(?orcid), "https://orcid.org/"))
        }
        """
        reverse = list(investigator_graph.query(reverse_query, initNs={"owl": OWL}))
        assert len(reverse) == 3, f"Expected 3 direct profile->orcid links, got {len(reverse)}"

        # test-data inv-004 has an orcid but no Synapse profile, so its orcid
        # (0000-0004-5678-9012) must not appear in the direct link at all
        forward_orcids = {str(row.orcid) for row in forward}
        assert "https://orcid.org/0000-0004-5678-9012" not in forward_orcids, \
            "orcid-only investigator (no Synapse profile) should not produce a direct link"

    def test_synapse_profile_linked_only_when_profile_present(self, investigator_graph, namespaces):
        """Investigators with both an ORCID and a Synapse profile get an
        nf:hasSynapseProfile edge from their ORCID; an investigator with only an
        ORCID does not."""
        NF = namespaces["nf"]
        pairs = list(investigator_graph.subject_objects(NF.hasSynapseProfile))
        subjects = {str(s) for s, _ in pairs}

        assert len(pairs) == 3, f"Expected 3 account linkages, got {sorted(pairs)}"
        assert all(s.startswith("https://orcid.org/") for s in subjects), \
            f"Subjects should be ORCID IRIs, got {sorted(subjects)}"
        assert all(str(o).startswith("https://www.synapse.org/Profile:") for _, o in pairs), \
            f"Objects should be Profile IRIs, got {sorted(pairs)}"
        assert "https://orcid.org/0000-0004-5678-9012" not in subjects, \
            "investigator with an ORCID but no Synapse profile must not claim one"

    def test_synapse_user_class_is_gone(self, investigator_graph, namespaces):
        """Replaced by nf:hasSynapseProfile -- see schema/ontology.ttl."""
        NF = namespaces["nf"]
        assert list(investigator_graph.subjects(RDF.type, NF.SynapseUser)) == []


class TestPublication:
    """Test publication entity properties"""

    @pytest.fixture
    def publication_graph(self, rml_runner):
        """Load publication graph"""
        return rml_runner(
            mapping_file="publications.rml.ttl",
            csv_replacements={
                "data/csv/publications.csv": "test/publications.csv"
            }
        )

    def test_publications_have_correct_type(self, publication_graph, namespaces):
        """Publications should have type biolink:Publication"""
        BIOLINK = namespaces["biolink"]
        publications = list(publication_graph.subjects(RDF.type, BIOLINK.Publication))
        assert len(publications) > 0, "No publications found in graph"
        assert len(publications) >= 2, f"Expected at least 2 publications, got {len(publications)}"

    def test_publications_carry_source_collection(self, publication_graph, namespaces):
        """Every publication should record the named source collection it came
        from, so it stays distinguishable once other portal publication
        listings are ingested into the same graph."""
        BIOLINK = namespaces["biolink"]
        NF = namespaces["nf"]
        PROV = Namespace("http://www.w3.org/ns/prov#")

        publications = list(publication_graph.subjects(RDF.type, BIOLINK.Publication))
        for pub in publications:
            sources = list(publication_graph.objects(pub, PROV.wasDerivedFrom))
            assert sources == [NF.ToolsCentralPublications], \
                f"{pub} should be derived from exactly nf:ToolsCentralPublications, got {sources}"

    def test_publications_have_titles(self, publication_graph, namespaces):
        """Publications should have publicationTitle property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?publication ?title
        WHERE {
            ?publication a biolink:Publication ;
                        nf:publicationTitle ?title .
        }
        """
        results = list(publication_graph.query(query, initNs={"nf": NF, "biolink": namespaces["biolink"]}))
        assert len(results) > 0, "No publications with titles found"

        titles = [str(row.title) for row in results]
        assert any("Test Publication on NF1" in title for title in titles), \
            "Expected test publication title from test data"

    def test_publications_have_abstracts(self, publication_graph, namespaces):
        """Publications should have abstract property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?publication ?abstract
        WHERE {
            ?publication a biolink:Publication ;
                        nf:abstract ?abstract .
        }
        """
        results = list(publication_graph.query(query, initNs={"nf": NF, "biolink": namespaces["biolink"]}))
        assert len(results) > 0, "No publications with abstracts found"

    def test_publications_have_doi(self, publication_graph, namespaces):
        """Publications should have DOI as IRI"""
        NF = namespaces["nf"]

        query = """
        SELECT ?publication ?doi
        WHERE {
            ?publication a biolink:Publication ;
                        nf:doi ?doi .
        }
        """
        results = list(publication_graph.query(query, initNs={"nf": NF, "biolink": namespaces["biolink"]}))
        assert len(results) > 0, "No publications with DOI found"

        # DOIs should be IRIs
        for row in results:
            assert isinstance(row.doi, URIRef), \
                f"DOI {row.doi} should be IRI, not literal"

    def test_publications_have_pmid(self, publication_graph, namespaces):
        """Publications should have PMID as IRI"""
        NF = namespaces["nf"]

        query = """
        SELECT ?publication ?pmid
        WHERE {
            ?publication a biolink:Publication ;
                        nf:pmid ?pmid .
        }
        """
        results = list(publication_graph.query(query, initNs={"nf": NF, "biolink": namespaces["biolink"]}))
        assert len(results) > 0, "No publications with PMID found"

        # PMIDs should be IRIs
        for row in results:
            assert isinstance(row.pmid, URIRef), \
                f"PMID {row.pmid} should be IRI, not literal"

    def test_publications_have_journal(self, publication_graph, namespaces):
        """Publications should have journal property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?publication ?journal
        WHERE {
            ?publication a biolink:Publication ;
                        nf:journal ?journal .
        }
        """
        results = list(publication_graph.query(query, initNs={"nf": NF, "biolink": namespaces["biolink"]}))
        assert len(results) > 0, "No publications with journal found"

        journals = [str(row.journal) for row in results]
        assert "Nature Medicine" in journals, "Expected Nature Medicine from test data"

    def test_authors_multi_value_split(self, publication_graph, namespaces):
        """Authors field should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?publication ?author
        WHERE {
            ?publication a biolink:Publication ;
                        nf:authors ?author .
        }
        """
        results = publication_graph.query(query, initNs={"nf": NF, "biolink": namespaces["biolink"]})
        authors = [str(row.author) for row in results]

        # Should have multiple values from pipe-delimited list
        assert "John Smith" in authors, "Expected 'John Smith' author"
        assert "Jane Doe" in authors, "Expected 'Jane Doe' author"


class TestDevelopmentRelationships:
    """Test development junction table relationships"""

    @pytest.fixture
    def development_graph(self, rml_runner):
        """Load development graph"""
        return rml_runner(
            mapping_file="development.rml.ttl",
            csv_replacements={
                "data/csv/development.csv": "test/development.csv"
            }
        )

    def test_development_has_funder_relationship(self, development_graph, namespaces):
        """Development entities should link to funders via hasFunder"""
        NF = namespaces["nf"]

        query = """
        SELECT ?dev ?funder
        WHERE {
            ?dev nf:hasFunder ?funder .
            FILTER(CONTAINS(STR(?dev), "development/"))
        }
        """
        results = list(development_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No development-funder relationships found"

    def test_development_has_investigator_relationship(self, development_graph, namespaces):
        """Development entities should link to investigators via hasInvestigator"""
        NF = namespaces["nf"]

        query = """
        SELECT ?dev ?investigator
        WHERE {
            ?dev nf:hasInvestigator ?investigator .
            FILTER(CONTAINS(STR(?dev), "development/"))
        }
        """
        results = list(development_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No development-investigator relationships found"

    def test_development_has_publication_relationship(self, development_graph, namespaces):
        """Development entities should link to publications via hasPublication"""
        NF = namespaces["nf"]

        query = """
        SELECT ?dev ?publication
        WHERE {
            ?dev nf:hasPublication ?publication .
            FILTER(CONTAINS(STR(?dev), "development/"))
        }
        """
        results = list(development_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No development-publication relationships found"

    def test_development_has_resource_id(self, development_graph, namespaces):
        """Development entities should link to resources via forResourceId"""
        NF = namespaces["nf"]

        query = """
        SELECT ?dev ?resourceId
        WHERE {
            ?dev nf:forResourceId ?resourceId .
            FILTER(CONTAINS(STR(?dev), "development/"))
        }
        """
        results = list(development_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No development-resource relationships found"
        for row in results:
            assert isinstance(row.resourceId, Literal), \
                f"forResourceId should be Literal, got {type(row.resourceId)}"

    def test_resource_has_funder_shortcut(self, development_graph, namespaces):
        """Resources should link to funders via hasFunder shortcut"""
        NF = namespaces["nf"]

        query = """
        SELECT ?resource ?funder
        WHERE {
            ?resource nf:hasFunder ?funder .
            FILTER(CONTAINS(STR(?resource), "test-res"))
        }
        """
        results = list(development_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No resource-funder relationships found"

    def test_resource_has_investigator_shortcut(self, development_graph, namespaces):
        """Resources should link to investigators via hasInvestigator shortcut"""
        NF = namespaces["nf"]

        query = """
        SELECT ?resource ?investigator
        WHERE {
            ?resource nf:hasInvestigator ?investigator .
            FILTER(CONTAINS(STR(?resource), "test-res"))
        }
        """
        results = list(development_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No resource-investigator relationships found"

    def test_resource_has_publication_shortcut(self, development_graph, namespaces):
        """Resources should link to publications via hasPublication shortcut"""
        NF = namespaces["nf"]

        query = """
        SELECT ?resource ?publication
        WHERE {
            ?resource nf:hasPublication ?publication .
            FILTER(CONTAINS(STR(?resource), "test-res"))
        }
        """
        results = list(development_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No resource-publication relationships found"


class TestDevelopmentEmptyFields:
    """Test that empty fields in development tables don't create triples"""

    def test_no_triples_for_empty_institution(self, rml_runner, namespaces):
        """Empty institution field should not create triples"""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("investigatorId,investigatorSynapseId,orcid,institution,investigatorName\n")
            f.write("inv-empty,syn123456,0000-0001-2345-6789,,Test Person\n")
            temp_csv = f.name

        try:
            graph = rml_runner(
                mapping_file="investigators.rml.ttl",
                csv_replacements={"data/csv/investigators.csv": temp_csv}
            )

            NF = namespaces["nf"]
            query = """
            SELECT ?investigator ?institution
            WHERE {
                ?investigator nf:institution ?institution .
            }
            """
            results = list(graph.query(query, initNs={"nf": NF}))

            # Should have no institution triples for the empty field
            assert len(results) == 0, "Empty institution should not create triples"
        finally:
            os.unlink(temp_csv)

    def test_no_triples_for_empty_abstract(self, rml_runner, namespaces):
        """Empty abstract field should not create triples"""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("publicationId,doi,pmid,abstract,journal,publicationDate,citation,publicationDateUnix,authors,publicationTitle\n")
            f.write("pub-empty,10.1000/test,12345678,,Test Journal,2024-01-01,Test Citation,1704067200,Author One,Test Title\n")
            temp_csv = f.name

        try:
            graph = rml_runner(
                mapping_file="publications.rml.ttl",
                csv_replacements={"data/csv/publications.csv": temp_csv}
            )

            NF = namespaces["nf"]
            query = """
            SELECT ?publication ?abstract
            WHERE {
                ?publication nf:abstract ?abstract .
            }
            """
            results = list(graph.query(query, initNs={"nf": NF}))

            # Should have no abstract triples for the empty field
            assert len(results) == 0, "Empty abstract should not create triples"
        finally:
            os.unlink(temp_csv)
