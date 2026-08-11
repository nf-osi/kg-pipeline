"""
Tests for People RML mapping

Tests the people.rml.ttl mapping against test/people.csv
"""

import re

import pytest
from rdflib import URIRef
from rdflib.namespace import RDF, RDFS


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
        """Every source row yields exactly one biolink:Person -- 3 with a
        Synapse account, 2 publication-derived people keyed by ORCID."""
        people = list(people_graph.subjects(RDF.type, namespaces["biolink"].Person))
        assert len(people) == 5, f"Expected 5 people, got {len(people)}"

    def test_person_subject_is_profile_or_orcid_iri(self, people_graph, namespaces):
        """Person subjects are the Synapse Profile IRI when the person has an
        account, and the ORCID IRI when they do not. Nothing else."""
        people = list(people_graph.subjects(RDF.type, namespaces["biolink"].Person))
        profiles = {str(p) for p in people if str(p).startswith("https://www.synapse.org/Profile:")}
        orcids = {str(p) for p in people if str(p).startswith("https://orcid.org/")}
        assert len(profiles) == 3, profiles
        assert len(orcids) == 2, orcids
        assert len(profiles) + len(orcids) == len(people), \
            f"Unexpected person subject IRIs: {[str(p) for p in people]}"

    def test_person_keyed_by_only_one_identifier(self, people_graph, namespaces):
        """A person with a Synapse account is a Person node at their Profile
        IRI only -- their ORCID IRI must not ALSO be typed biolink:Person, or
        class counts would double-count them."""
        people = {str(p) for p in people_graph.subjects(RDF.type, namespaces["biolink"].Person)}
        assert "https://orcid.org/0000-0002-3127-5045" not in people, \
            "ORCID of an account-holder should not be a separate biolink:Person"

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


class TestPeopleNames:
    """nf:name / rdfs:label make a person's display name reachable, which is
    what lets an agent answer 'who wrote this' from a publication's
    nf:authorOrcid rather than only returning bare identifiers."""

    def test_account_holder_has_name(self, people_graph, namespaces):
        NF = namespaces["nf"]
        subj = URIRef("https://www.synapse.org/Profile:3324237")
        assert [str(o) for o in people_graph.objects(subj, NF.name)] == ["David Gutmann"]
        assert [str(o) for o in people_graph.objects(subj, RDFS.label)] == ["David Gutmann"]

    def test_orcid_only_person_has_name(self, people_graph, namespaces):
        """The publication-derived majority of the source: no Synapse account,
        so the name hangs off the ORCID IRI."""
        NF = namespaces["nf"]
        subj = URIRef("https://orcid.org/0000-0001-5030-9354")
        assert [str(o) for o in people_graph.objects(subj, NF.name)] == ["Nancy Ratner"]
        assert [str(o) for o in people_graph.objects(subj, RDFS.label)] == ["Nancy Ratner"]

    def test_name_reachable_from_orcid_for_both_kinds(self, people_graph, namespaces):
        """Starting from an ORCID -- the only identifier nf:authorOrcid gives
        you -- a name must be reachable whether or not the author has a Synapse
        account: directly for ORCID-only people, one owl:sameAs hop otherwise."""
        query = """
        SELECT ?orcid ?name
        WHERE {
            VALUES ?orcid {
                <https://orcid.org/0000-0002-3127-5045>
                <https://orcid.org/0000-0001-5030-9354>
            }
            { ?orcid nf:name ?name }
            UNION
            { ?orcid owl:sameAs ?profile . ?profile nf:name ?name }
        }
        """
        results = list(people_graph.query(
            query, initNs={"nf": namespaces["nf"], "owl": namespaces["owl"]}
        ))
        assert {str(r.name) for r in results} == {"David Gutmann", "Nancy Ratner"}, results

    def test_person_without_name_emits_none(self, people_graph, namespaces):
        """Not every row has a name; those must simply emit no name triple."""
        NF = namespaces["nf"]
        subj = URIRef("https://orcid.org/0000-0002-9752-3689")
        assert list(people_graph.objects(subj, NF.name)) == []
        assert (subj, RDF.type, namespaces["biolink"].Person) in people_graph, \
            "A nameless ORCID-only person is still a person node"


class TestPeopleOrcidOnly:
    """People with an ORCID but no Synapse account -- 1061 of 1519 source rows."""

    def test_orcid_only_person_not_typed_synapse_user(self, people_graph, namespaces):
        """nf:SynapseUser means 'has BOTH an ORCID and a Synapse profile'.
        Typing the bare orcid column would falsely mark every publication-derived
        researcher as a Synapse user, which is the failure this guards."""
        NF = namespaces["nf"]
        users = {str(u) for u in people_graph.subjects(RDF.type, NF.SynapseUser)}
        assert "https://orcid.org/0000-0001-5030-9354" not in users, \
            f"ORCID-only person must not be typed nf:SynapseUser: {users}"
        assert "https://orcid.org/0000-0002-9752-3689" not in users, users

    def test_orcid_only_person_has_no_profile_link(self, people_graph, namespaces):
        """No ownerID means no Profile IRI to point at, so no owl:sameAs."""
        OWL = namespaces["owl"]
        subj = URIRef("https://orcid.org/0000-0001-5030-9354")
        assert list(people_graph.objects(subj, OWL.sameAs)) == []

    def test_no_profile_iri_minted_without_owner_id(self, people_graph):
        """An empty ownerID must null-propagate, never produce 'Profile:' or
        a stringified NaN in an IRI."""
        subjects = {str(s) for s in people_graph.subjects()}
        objects = {str(o) for o in people_graph.objects() if isinstance(o, URIRef)}
        for iri in subjects | objects:
            assert not iri.endswith("/Profile:"), f"Empty Profile IRI minted: {iri}"
            assert "Profile:nan" not in iri, f"NaN leaked into IRI: {iri}"
            assert not re.search(r"/Profile:\d+\.0$", iri), \
                f"Float-formatted ownerID leaked into IRI: {iri}"


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
