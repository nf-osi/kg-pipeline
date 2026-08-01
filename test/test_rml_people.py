"""
Tests for People RML mapping

Tests the people.rml.ttl mapping against test/people.csv
"""

import pytest
from rdflib import URIRef
from rdflib.namespace import RDF


@pytest.fixture
def people_graph(rml_runner, namespaces):
    """Load people RDF graph from test data"""
    graph = rml_runner(
        mapping_file="people.rml.ttl",
        csv_replacements={"data/csv/people.csv": "test/people.csv"}
    )
    return graph


class TestPeopleCore:
    """Test core person properties"""

    def test_person_has_correct_type(self, people_graph, namespaces):
        """All people should have type biolink:Person"""
        people = list(people_graph.subjects(RDF.type, namespaces["biolink"].Person))
        assert len(people) == 3, f"Expected 3 people, got {len(people)}"

    def test_person_subject_is_synapse_profile_iri(self, people_graph, namespaces):
        """Person subjects should be Synapse Profile IRIs"""
        people = list(people_graph.subjects(RDF.type, namespaces["biolink"].Person))
        for person in people:
            assert isinstance(person, URIRef)
            assert str(person).startswith("https://www.synapse.org/Profile:"), \
                f"Expected Synapse Profile IRI, got {person}"

    def test_person_same_as_orcid_iri(self, people_graph, namespaces):
        """Person owl:sameAs should point to an ORCID IRI, not a literal"""
        OWL = namespaces["owl"]

        query = """
        SELECT ?person ?orcid
        WHERE {
            ?person a biolink:Person ;
                    owl:sameAs ?orcid .
        }
        """
        results = list(people_graph.query(
            query, initNs={"owl": OWL, "biolink": namespaces["biolink"]}
        ))
        assert len(results) == 2, f"Expected 2 people with owl:sameAs, got {len(results)}"

        for row in results:
            assert isinstance(row.orcid, URIRef), \
                f"orcid {row.orcid} should be IRI, not literal"
            assert str(row.orcid).startswith("https://orcid.org/"), \
                f"Expected orcid.org IRI, got {row.orcid}"

    def test_orcid_value_in_iri(self, people_graph, namespaces):
        """The bare ORCID iD should be embedded in the orcid.org IRI"""
        OWL = namespaces["owl"]

        query = """
        SELECT ?orcid
        WHERE {
            ?person a biolink:Person ;
                    owl:sameAs ?orcid .
            FILTER(CONTAINS(STR(?orcid), "3127-5045"))
        }
        """
        results = list(people_graph.query(
            query, initNs={"owl": OWL, "biolink": namespaces["biolink"]}
        ))
        assert len(results) == 1
        assert str(results[0].orcid) == "https://orcid.org/0000-0002-3127-5045"


class TestPeopleSynapseUser:
    """Test nf:SynapseUser typing (asserted on the ORCID IRI, not the profile)"""

    def test_orcid_typed_as_synapse_user(self, people_graph, namespaces):
        """Every person's ORCID IRI should be typed nf:SynapseUser"""
        NF = namespaces["nf"]
        users = list(people_graph.subjects(RDF.type, NF.SynapseUser))
        assert len(users) == 2, f"Expected 2 SynapseUser instances, got {len(users)}"
        for u in users:
            assert str(u).startswith("https://orcid.org/"), \
                f"SynapseUser should be an ORCID IRI, got {u}"

    def test_profile_iri_not_typed_synapse_user(self, people_graph, namespaces):
        """The Synapse Profile IRI must NOT carry the SynapseUser type -- typing
        both identifiers would double-count people in class counts."""
        NF = namespaces["nf"]
        users = [str(u) for u in people_graph.subjects(RDF.type, NF.SynapseUser)]
        assert not any("synapse.org/Profile:" in u for u in users), \
            f"Profile IRIs should not be typed nf:SynapseUser: {users}"

    def test_synapse_user_reachable_from_orcid_value(self, people_graph, namespaces):
        """An ORCID value should be testable for the SynapseUser type directly,
        which is the join an agent makes from a publication's nf:authorOrcid."""
        NF = namespaces["nf"]

        query = """
        ASK {
            <https://orcid.org/0000-0002-3127-5045> a nf:SynapseUser .
        }
        """
        assert people_graph.query(query, initNs={"nf": NF}).askAnswer, \
            "Expected the ORCID IRI to be directly typed nf:SynapseUser"


class TestPeopleProjects:
    """nf:onProject drives project-collaboration queries."""

    def test_projects_emitted_as_synapse_iris(self, people_graph, namespaces):
        NF = namespaces["nf"]
        subj = URIRef("https://www.synapse.org/Profile:3324237")
        projs = {str(o) for o in people_graph.objects(subj, NF.onProject)}
        assert projs == {
            "https://www.synapse.org/Synapse:syn111",
            "https://www.synapse.org/Synapse:syn222",
        }, projs

    def test_person_without_orcid_still_gets_projects(self, people_graph, namespaces):
        """Most Synapse profiles have no ORCID but are still project members;
        excluding them would undercount collaboration."""
        NF = namespaces["nf"]
        OWL = namespaces["owl"]
        subj = URIRef("https://www.synapse.org/Profile:3399999")
        assert len(list(people_graph.objects(subj, NF.onProject))) == 2
        # ...and gets no owl:sameAs or SynapseUser typing, since it has no ORCID
        assert list(people_graph.objects(subj, OWL.sameAs)) == []

    def test_person_without_projects_emits_none(self, people_graph, namespaces):
        NF = namespaces["nf"]
        subj = URIRef("https://www.synapse.org/Profile:3342573")
        assert list(people_graph.objects(subj, NF.onProject)) == []

    def test_shared_project_links_two_people(self, people_graph, namespaces):
        """syn222 is shared, which is what makes the two people collaborators."""
        NF = namespaces["nf"]
        shared = set(people_graph.subjects(NF.onProject,
                     URIRef("https://www.synapse.org/Synapse:syn222")))
        assert len(shared) == 2, shared


# Run with: pytest test/test_rml_people.py -v
