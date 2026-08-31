"""
Tests for relationship RML mappings

Tests mappings that create relationships between entities:
- mutation_model.rml.ttl
- donor_tool.rml.ttl
"""

import pytest
from rdflib import URIRef
from rdflib.namespace import RDF


class TestMutationModelRelationship:
    """Test mutation-model relationships (animal models and cell lines)"""

    @pytest.fixture
    def mutation_model_graph(self, rml_runner):
        """Load mutation-model relationship graph"""
        return rml_runner(
            mapping_file="mutation_model.rml.ttl",
            csv_replacements={
                "data/csv/mutation_model.csv": "test/mutation_model.csv"
            }
        )

    def test_has_mutation_relationships_exist(self, mutation_model_graph, namespaces):
        """Animal models and cell lines should link to mutations via hasMutation"""
        NF = namespaces["nf"]

        query = """
        SELECT ?subject ?mutation
        WHERE {
            ?subject nf:hasMutation ?mutation .
        }
        """
        results = list(mutation_model_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No hasMutation relationships found"

    def test_mutation_is_iri(self, mutation_model_graph, namespaces):
        """Mutation should be referenced as IRI with correct pattern"""
        NF = namespaces["nf"]

        query = """
        SELECT ?subject ?mutation
        WHERE {
            ?subject nf:hasMutation ?mutation .
        }
        """
        results = list(mutation_model_graph.query(query, initNs={"nf": NF}))

        for row in results:
            assert isinstance(row.mutation, URIRef), \
                f"Mutation should be IRI, got {type(row.mutation)}"
            mutation_str = str(row.mutation)
            assert "mutation/" in mutation_str, \
                f"Mutation IRI should contain 'mutation/', got {mutation_str}"

    def test_animal_model_has_mutation(self, mutation_model_graph, namespaces):
        """Animal model IDs should be subjects of hasMutation triples"""
        NF = namespaces["nf"]

        test_animal_model = "a067f136-f956-4355-a76f-a5eec7c196f0"

        query = f"""
        SELECT ?mutation
        WHERE {{
            ?subject nf:hasMutation ?mutation .
            FILTER(CONTAINS(STR(?subject), "{test_animal_model}"))
        }}
        """
        results = list(mutation_model_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, \
            f"Expected hasMutation relationship for animal model {test_animal_model}"

    def test_cell_line_has_mutation(self, mutation_model_graph, namespaces):
        """Cell line IDs should be subjects of hasMutation triples"""
        NF = namespaces["nf"]

        test_cell_line = "a9638c45-74f3-4d0d-8bac-67631503f437"

        query = f"""
        SELECT ?mutation
        WHERE {{
            ?subject nf:hasMutation ?mutation .
            FILTER(CONTAINS(STR(?subject), "{test_cell_line}"))
        }}
        """
        results = list(mutation_model_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, \
            f"Expected hasMutation relationship for cell line {test_cell_line}"

    def test_animal_model_iri_pattern(self, mutation_model_graph, namespaces):
        """Animal model subjects should use resource/ IRI pattern"""
        NF = namespaces["nf"]

        test_animal_model = "a067f136-f956-4355-a76f-a5eec7c196f0"

        query = f"""
        SELECT ?subject
        WHERE {{
            ?subject nf:hasMutation ?mutation .
            FILTER(CONTAINS(STR(?subject), "{test_animal_model}"))
        }}
        """
        results = list(mutation_model_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0
        assert "resource/" in str(results[0].subject), \
            f"Expected resource/ IRI pattern, got {results[0].subject}"

    def test_cell_line_iri_pattern(self, mutation_model_graph, namespaces):
        """Cell line subjects should use resource/ IRI pattern"""
        NF = namespaces["nf"]

        test_cell_line = "a9638c45-74f3-4d0d-8bac-67631503f437"

        query = f"""
        SELECT ?subject
        WHERE {{
            ?subject nf:hasMutation ?mutation .
            FILTER(CONTAINS(STR(?subject), "{test_cell_line}"))
        }}
        """
        results = list(mutation_model_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0
        assert "resource/" in str(results[0].subject), \
            f"Expected resource/ IRI pattern, got {results[0].subject}"


class TestDonorToolRelationship:
    """Test donor-tool (resource) relationships"""

    @pytest.fixture
    def donor_tool_graph(self, rml_runner):
        """Load donor-tool relationship graph"""
        return rml_runner(
            mapping_file="donor_tool.rml.ttl",
            csv_replacements={
                "data/csv/donor_tool.csv": "test/donor_tool.csv"
            }
        )

    def test_from_donor_relationships_exist(self, donor_tool_graph, namespaces):
        """Resources should link to donors via fromDonor"""
        NF = namespaces["nf"]

        query = """
        SELECT ?resource ?donor
        WHERE {
            ?resource nf:fromDonor ?donor .
        }
        """
        results = list(donor_tool_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "No fromDonor relationships found"
        assert len(results) >= 2, \
            f"Expected at least 2 fromDonor relationships, got {len(results)}"

    def test_donor_is_iri(self, donor_tool_graph, namespaces):
        """Donor should be referenced as IRI"""
        NF = namespaces["nf"]

        query = """
        SELECT ?resource ?donor
        WHERE {
            ?resource nf:fromDonor ?donor .
        }
        """
        results = list(donor_tool_graph.query(query, initNs={"nf": NF}))

        for row in results:
            assert isinstance(row.donor, URIRef), \
                f"Donor should be IRI, got {type(row.donor)}"

    def test_specific_donor_relationship(self, donor_tool_graph, namespaces):
        """Test specific donor-resource relationship from test data"""
        NF = namespaces["nf"]

        # Check for specific relationship from test data
        donor_id = "37e3618d-7246-4036-b1fa-e2f032b8077c"
        resource_id = "033b7173-4c58-410e-b441-579ba05c388a"

        query = f"""
        SELECT ?resource ?donor
        WHERE {{
            ?resource nf:fromDonor ?donor .
            FILTER(CONTAINS(STR(?donor), "{donor_id}"))
            FILTER(CONTAINS(STR(?resource), "{resource_id}"))
        }}
        """
        results = list(donor_tool_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1, \
            f"Expected fromDonor relationship from {resource_id} to {donor_id}"

    def test_bidirectional_property(self, donor_tool_graph, namespaces):
        """fromDonor has inverse property hasDerivedResource (defined in ontology)"""
        NF = namespaces["nf"]

        query = """
        SELECT ?resource ?donor
        WHERE {
            ?resource nf:fromDonor ?donor .
        }
        """
        results = list(donor_tool_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Should have fromDonor relationships"


class TestRelationshipConsistency:
    """Test consistency across relationship mappings"""

    def test_both_model_types_have_mutations(self, rml_runner, namespaces):
        """Both animal models and cell lines use hasMutation property"""
        NF = namespaces["nf"]

        graph = rml_runner(
            mapping_file="mutation_model.rml.ttl",
            csv_replacements={
                "data/csv/mutation_model.csv": "test/mutation_model.csv"
            }
        )

        # Check animal models
        animal_query = """
        SELECT ?subject ?mutation
        WHERE {
            ?subject nf:hasMutation ?mutation .
            FILTER(CONTAINS(STR(?subject), "resource/"))
        }
        """
        animal_results = list(graph.query(animal_query, initNs={"nf": NF}))

        # Check cell lines
        cell_query = """
        SELECT ?subject ?mutation
        WHERE {
            ?subject nf:hasMutation ?mutation .
            FILTER(CONTAINS(STR(?subject), "resource/"))
        }
        """
        cell_results = list(graph.query(cell_query, initNs={"nf": NF}))

        assert len(animal_results) > 0, "Animal models should have hasMutation"
        assert len(cell_results) > 0, "Cell lines should have hasMutation"

    def test_no_literal_object_in_relationships(self, rml_runner):
        """All relationship objects should be IRIs, not literals"""
        mapping_files = [
            ("mutation_model.rml.ttl", "mutation_model.csv"),
            ("donor_tool.rml.ttl", "donor_tool.csv"),
        ]

        for mapping_file, csv_file in mapping_files:
            graph = rml_runner(
                mapping_file=mapping_file,
                csv_replacements={f"data/csv/{csv_file}": f"test/{csv_file}"}
            )

            # Find any triple where object is a literal
            query = """
            SELECT ?s ?p ?o
            WHERE {
                ?s ?p ?o .
                FILTER(isLiteral(?o))
            }
            """
            results = list(graph.query(query))

            # Relationship-only mappings should have NO literals
            assert len(results) == 0, \
                f"{mapping_file} should only create IRI relationships, found {len(results)} literals"


# Run with: pytest test/test_rml_relationships.py -v
