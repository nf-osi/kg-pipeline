"""
Tests for Mutations RML mapping

Tests the portal_mutations.rml.ttl mapping against test/mutations.csv
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def mutations_graph(rml_runner, namespaces):
    """Load mutations RDF graph from test data"""
    graph = rml_runner(
        mapping_file="portal_mutations.rml.ttl",
        csv_replacements={"data/csv/mutations.csv": "test/mutations.csv"}
    )
    return graph


class TestMutationsCore:
    """Test core mutation properties"""

    def test_mutations_have_correct_type(self, mutations_graph, namespaces):
        """All mutations should have type nf:Mutation"""
        mutations = list(mutations_graph.subjects(RDF.type, namespaces["nf"].Mutation))
        assert len(mutations) > 0, "No mutations found in graph"

    def test_mutation_id_is_iri(self, mutations_graph, namespaces):
        """Mutation subjects should be IRIs"""
        mutations = list(mutations_graph.subjects(RDF.type, namespaces["nf"].Mutation))
        for mutation in mutations:
            assert isinstance(mutation, URIRef), \
                f"Mutation ID should be IRI, got {type(mutation)}"

    def test_mutations_have_required_properties(self, mutations_graph, namespaces):
        """Mutations should have basic required properties"""
        NF = namespaces["nf"]

        query = """
        SELECT ?mutation
        WHERE {
            ?mutation a nf:Mutation .
            FILTER NOT EXISTS { ?mutation nf:mutationId ?id }
        }
        """
        results = list(mutations_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, "All mutations should have mutationId"


class TestMutationsMultiValue:
    """Test multi-value field handling (pipe-delimited lists)"""

    def test_allele_type_multi_value_split(self, mutations_graph, namespaces):
        """AlleleType should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?mutation ?alleleType
        WHERE {
            ?mutation a nf:Mutation ;
                      nf:alleleType ?alleleType .
        }
        """
        results = mutations_graph.query(query, initNs={"nf": NF})
        allele_types = [str(row.alleleType) for row in results]

        # Should have both values from pipe-delimited list
        assert "Somatic" in allele_types, "Expected 'Somatic' alleleType"
        assert "Germline" in allele_types, "Expected 'Germline' alleleType"

    def test_mutation_method_multi_value_split(self, mutations_graph, namespaces):
        """MutationMethod should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?mutation ?method
        WHERE {
            ?mutation a nf:Mutation ;
                      nf:mutationMethod ?method .
        }
        """
        results = mutations_graph.query(query, initNs={"nf": NF})
        methods = [str(row.method) for row in results]

        # Should have multiple values from split
        assert "Spontaneous" in methods, "Expected 'Spontaneous' mutation method"
        assert "ENU" in methods, "Expected 'ENU' mutation method"

    def test_mutation_type_multi_value_split(self, mutations_graph, namespaces):
        """MutationType should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?mutation ?type
        WHERE {
            ?mutation a nf:Mutation ;
                      nf:mutationType ?type .
        }
        """
        results = mutations_graph.query(query, initNs={"nf": NF})
        types = [str(row.type) for row in results]

        assert "Nonsense" in types, "Expected 'Nonsense' mutation type"
        assert "Frameshift" in types, "Expected 'Frameshift' mutation type"


class TestMutationsIRIFields:
    """Test fields that should be IRIs (not literals)"""

    def test_external_mutation_id_as_iri(self, mutations_graph, namespaces):
        """ExternalMutationID should be an IRI, not a literal"""
        NF = namespaces["nf"]

        query = """
        SELECT ?mutation ?externalId
        WHERE {
            ?mutation a nf:Mutation ;
                      nf:externalMutationID ?externalId .
        }
        """
        results = list(mutations_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "No externalMutationID found"

        for row in results:
            assert isinstance(row.externalId, URIRef), \
                f"externalMutationID should be IRI, got {type(row.externalId)}"
            # Should contain a valid external ID (COSM, MGI, etc.)
            external_str = str(row.externalId)
            assert "COSM" in external_str or "MGI" in external_str or len(external_str) > 3, \
                f"Expected valid external mutation ID, got {row.externalId}"


class TestMutationsEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_fields_produce_no_triples(self, mutations_graph, namespaces):
        """Empty CSV fields should not create triples"""
        NF = namespaces["nf"]

        # test-mut-003 should have empty humanClinVarMutation
        test_mut_003 = URIRef("http://nf-osi.github.com/terms#mutation/test-mut-003")

        # Verify mutation exists
        assert (test_mut_003, RDF.type, NF.Mutation) in mutations_graph, \
            "test-mut-003 not found in graph"

        # Verify no humanClinVarMutation triple
        query = """
        SELECT ?clinvar
        WHERE {
            <http://nf-osi.github.com/terms#mutation/test-mut-003>
                nf:humanClinVarMutation ?clinvar .
        }
        """
        results = list(mutations_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty humanClinVarMutation should not produce triple"

    def test_no_empty_literal_values(self, mutations_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(mutations_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


class TestMutationsDataTypes:
    """Test that fields have correct data types"""

    def test_mutation_id_is_string(self, mutations_graph, namespaces):
        """mutationId should be xsd:string literal"""
        NF = namespaces["nf"]

        query = """
        SELECT ?mutation ?mutationId
        WHERE {
            ?mutation a nf:Mutation ;
                      nf:mutationId ?mutationId .
        }
        """
        results = list(mutations_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "No mutations with mutationId found"

        for row in results:
            assert isinstance(row.mutationId, Literal), \
                f"mutationId should be Literal, got {type(row.mutationId)}"


# Run with: pytest test/test_rml_mutations.py -v
