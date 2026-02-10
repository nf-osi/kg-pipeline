"""
Tests for Observations RML mapping

Tests the observations.rml.ttl mapping against test/observations.csv
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def observations_graph(rml_runner, namespaces):
    """Load observations RDF graph from test data"""
    graph = rml_runner(
        mapping_file="observations.rml.ttl",
        csv_replacements={"data/csv/observations.csv": "test/observations.csv"}
    )
    return graph


class TestObservationsCore:
    """Test core observation properties"""

    def test_observations_have_correct_type(self, observations_graph, namespaces):
        """All observations should have type nf:Observation"""
        NF = namespaces["nf"]
        observations = list(observations_graph.subjects(RDF.type, NF.Observation))
        assert len(observations) > 0, "No observations found in graph"
        assert len(observations) >= 3, f"Expected at least 3 observations, got {len(observations)}"

    def test_observation_id_is_string(self, observations_graph, namespaces):
        """Observation ID should be a string literal property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?id
        WHERE {
            ?observation a nf:Observation ;
                        nf:observationId ?id .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No observations with observationId found"

        for row in results:
            assert isinstance(row.id, Literal), \
                f"observationId should be Literal, got {type(row.id)}"

    def test_observations_have_text(self, observations_graph, namespaces):
        """Observations should have observationText property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?text
        WHERE {
            ?observation a nf:Observation ;
                        nf:observationText ?text .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No observations with text found"

        texts = [str(row.text) for row in results]
        assert any("cell line" in text.lower() for text in texts), \
            "Expected observation text from test data"

    def test_observations_have_submitter_name(self, observations_graph, namespaces):
        """Observations should have submitter name"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?submitter
        WHERE {
            ?observation a nf:Observation ;
                        nf:observationSubmitterName ?submitter .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No observations with submitter name found"

        submitters = [str(row.submitter) for row in results]
        assert "Dr. Jane Smith" in submitters, "Expected Dr. Jane Smith from test data"

    def test_observations_have_phase(self, observations_graph, namespaces):
        """Observations should have observationPhase property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?phase
        WHERE {
            ?observation a nf:Observation ;
                        nf:observationPhase ?phase .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No observations with phase found"

        phases = [str(row.phase) for row in results]
        assert "In vitro" in phases, "Expected 'In vitro' phase from test data"
        assert "In vivo" in phases, "Expected 'In vivo' phase from test data"


class TestObservationsMultiValue:
    """Test multi-value field handling (pipe-delimited lists)"""

    def test_observation_type_multi_value_split(self, observations_graph, namespaces):
        """ObservationType should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?type
        WHERE {
            ?observation a nf:Observation ;
                        nf:observationType ?type .
        }
        """
        results = observations_graph.query(query, initNs={"nf": NF})
        observation_types = [str(row.type) for row in results]

        # Should have multiple values from pipe-delimited list
        # "Phenotype|Growth Rate" should split into separate values
        assert "Phenotype" in observation_types, "Expected 'Phenotype' observation type"
        assert "Growth Rate" in observation_types, "Expected 'Growth Rate' observation type"

    def test_observation_type_single_value(self, observations_graph, namespaces):
        """Single-value observationType should not be split"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?type
        WHERE {
            ?observation a nf:Observation ;
                        nf:observationType ?type .
        }
        """
        results = observations_graph.query(query, initNs={"nf": NF})
        observation_types = [str(row.type) for row in results]

        # Should have "Specificity" as a single value
        assert "Specificity" in observation_types, "Expected 'Specificity' observation type"


class TestObservationsIRIFields:
    """Test IRI vs literal field types"""

    def test_synapse_id_is_iri(self, observations_graph, namespaces):
        """Synapse ID should be IRI, not literal"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?synapseId
        WHERE {
            ?observation a nf:Observation ;
                        nf:synapseId ?synapseId .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No observations with synapseId found"

        for row in results:
            assert isinstance(row.synapseId, URIRef), \
                f"synapseId should be IRI, got {type(row.synapseId)}"

    def test_observation_link_is_iri(self, observations_graph, namespaces):
        """Observation link should be IRI, not literal"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?link
        WHERE {
            ?observation a nf:Observation ;
                        nf:observationLink ?link .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No observations with observationLink found"

        for row in results:
            assert isinstance(row.link, URIRef), \
                f"observationLink should be IRI, got {type(row.link)}"

    def test_text_fields_are_literals(self, observations_graph, namespaces):
        """Text fields should be literals, not IRIs"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?text ?submitter ?phase
        WHERE {
            ?observation a nf:Observation ;
                        nf:observationText ?text ;
                        nf:observationSubmitterName ?submitter ;
                        nf:observationPhase ?phase .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No observations with text fields found"

        for row in results:
            assert isinstance(row.text, Literal), \
                f"observationText should be Literal, got {type(row.text)}"
            assert isinstance(row.submitter, Literal), \
                f"observationSubmitterName should be Literal, got {type(row.submitter)}"
            assert isinstance(row.phase, Literal), \
                f"observationPhase should be Literal, got {type(row.phase)}"


class TestObservationsRelationships:
    """Test observation relationships to other entities"""

    def test_observation_about_resource(self, observations_graph, namespaces):
        """Observations should link to resources via aboutResource"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?resource
        WHERE {
            ?observation a nf:Observation ;
                        nf:aboutResource ?resource .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No aboutResource relationships found"

        # Resource IDs should be IRIs
        for row in results:
            assert isinstance(row.resource, URIRef), \
                f"resourceId should be IRI, got {type(row.resource)}"

    def test_observation_references_publication(self, observations_graph, namespaces):
        """Observations should link to publications via referencesPublication"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?publication
        WHERE {
            ?observation a nf:Observation ;
                        nf:referencesPublication ?publication .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No referencesPublication relationships found"

        # Publication IDs should be IRIs
        for row in results:
            assert isinstance(row.publication, URIRef), \
                f"publicationId should be IRI, got {type(row.publication)}"

    def test_specific_observation_relationships(self, observations_graph, namespaces):
        """Test specific observation-resource-publication connections"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?resource ?publication
        WHERE {
            ?observation nf:aboutResource ?resource ;
                        nf:referencesPublication ?publication .
            FILTER(CONTAINS(STR(?resource), "test-res-001"))
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No observation with both resource and publication found"


class TestObservationsEmptyFields:
    """Test that empty fields don't create triples"""

    def test_no_triples_for_empty_publication_id(self, observations_graph, namespaces):
        """Empty publicationId should not create referencesPublication triple"""
        NF = namespaces["nf"]

        # obs-003 has empty publicationId in test data
        query = """
        SELECT ?observation ?publication
        WHERE {
            ?observation nf:observationId "obs-003" ;
                        nf:referencesPublication ?publication .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty publicationId should not create referencesPublication triple"

    def test_no_triples_for_empty_ease_of_use_rating(self, observations_graph, namespaces):
        """Empty easeOfUseRating should not create triple"""
        NF = namespaces["nf"]

        # obs-003 has empty easeOfUseRating in test data
        query = """
        SELECT ?observation ?rating
        WHERE {
            ?observation nf:observationId "obs-003" ;
                        nf:easeOfUseRating ?rating .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty easeOfUseRating should not create triple"


class TestObservationsDataQuality:
    """Test data quality and consistency"""

    def test_ratings_are_present(self, observations_graph, namespaces):
        """Observations with ratings should have proper values"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?reliability ?ease
        WHERE {
            ?observation a nf:Observation .
            OPTIONAL { ?observation nf:reliabilityRating ?reliability }
            OPTIONAL { ?observation nf:easeOfUseRating ?ease }
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No observations found"

        # At least some observations should have ratings
        ratings_found = sum(1 for row in results if row.reliability is not None)
        assert ratings_found > 0, "Expected some observations with reliability ratings"

    def test_time_and_units_consistency(self, observations_graph, namespaces):
        """Observations with time should have time units"""
        NF = namespaces["nf"]

        query = """
        SELECT ?observation ?time ?units
        WHERE {
            ?observation a nf:Observation ;
                        nf:observationTime ?time ;
                        nf:observationTimeUnits ?units .
        }
        """
        results = list(observations_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No observations with time and units found"

        # Check that time values are numeric-like
        for row in results:
            time_val = str(row.time)
            units_val = str(row.units)
            assert time_val, "Time should not be empty"
            assert units_val in ["hours", "days", "weeks", "months"], \
                f"Expected valid time unit, got {units_val}"
