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
        assert len(people) == 2, f"Expected 2 people, got {len(people)}"

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


# Run with: pytest test/test_rml_people.py -v
