"""
Tests for Cell Lines RML mapping

Tests the portal_cell_lines.rml.ttl mapping against test/cell_lines.csv
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def cell_lines_graph(rml_runner, namespaces):
    """Load cell lines RDF graph from test data"""
    graph = rml_runner(
        mapping_file="portal_cell_lines.rml.ttl",
        csv_replacements={"data/csv/cell_lines.csv": "test/cell_lines.csv"}
    )
    return graph


class TestCellLinesCore:
    """Test core cell line properties"""

    def test_cell_line_has_correct_type(self, cell_lines_graph, namespaces):
        """All cell lines should have type nf:CellLine"""
        cell_lines = list(cell_lines_graph.subjects(RDF.type, namespaces["nf"].CellLine))
        assert len(cell_lines) > 0, "No cell lines found in graph"
        assert len(cell_lines) >= 3, f"Expected at least 3 cell lines, got {len(cell_lines)}"

    def test_cell_line_id_is_iri(self, cell_lines_graph, namespaces):
        """Cell line subjects should be IRIs"""
        cell_lines = list(cell_lines_graph.subjects(RDF.type, namespaces["nf"].CellLine))
        for cell_line in cell_lines:
            assert isinstance(cell_line, URIRef), \
                f"Cell line ID should be IRI, got {type(cell_line)}"


class TestCellLinesIRIFields:
    """Test fields that should be IRIs (not literals)"""

    def test_donor_id_as_iri(self, cell_lines_graph, namespaces):
        """DonorId should be an IRI reference"""
        NF = namespaces["nf"]

        query = """
        SELECT ?cellLine ?donorId
        WHERE {
            ?cellLine a nf:CellLine ;
                      nf:donorId ?donorId .
        }
        """
        results = list(cell_lines_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "No donorId found"

        for row in results:
            assert isinstance(row.donorId, URIRef), \
                f"donorId should be IRI, got {type(row.donorId)}"
            # Check it contains expected donor ID format
            assert "test-donor" in str(row.donorId) or len(str(row.donorId).split('/')[-1]) > 10, \
                f"donorId should be valid IRI: {row.donorId}"


class TestCellLinesMultiValue:
    """Test multi-value field handling (pipe-delimited lists)"""

    def test_cell_line_manifestation_multi_value_split(self, cell_lines_graph, namespaces):
        """CellLineManifestation should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?cellLine ?manifestation
        WHERE {
            ?cellLine a nf:CellLine ;
                      nf:cellLineManifestation ?manifestation .
        }
        """
        results = cell_lines_graph.query(query, initNs={"nf": NF})
        manifestations = [str(row.manifestation) for row in results]

        # Should have both values from pipe-delimited list
        assert "Plexiform Neurofibroma" in manifestations, \
            "Expected 'Plexiform Neurofibroma' manifestation"
        assert "Malignant Peripheral Nerve Sheath Tumor" in manifestations, \
            "Expected 'Malignant Peripheral Nerve Sheath Tumor' manifestation"

    def test_single_genetic_disorder_value(self, cell_lines_graph, namespaces):
        """CellLineGeneticDisorder should handle single values"""
        NF = namespaces["nf"]

        query = """
        SELECT ?cellLine ?disorder
        WHERE {
            ?cellLine a nf:CellLine ;
                      nf:cellLineGeneticDisorder ?disorder .
            FILTER(CONTAINS(STR(?cellLine), "test-cell-001"))
        }
        """
        results = list(cell_lines_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected genetic disorder for test-cell-001"
        assert str(results[0].disorder) == "Neurofibromatosis type 1", \
            f"Expected 'Neurofibromatosis type 1', got {results[0].disorder}"


class TestCellLinesSpecificFields:
    """Test cell line specific fields"""

    def test_resistance_field_present(self, cell_lines_graph, namespaces):
        """Resistance field should be present for relevant cell lines"""
        NF = namespaces["nf"]

        query = """
        SELECT ?cellLine ?resistance
        WHERE {
            ?cellLine a nf:CellLine ;
                      nf:resistance ?resistance .
            FILTER(CONTAINS(STR(?cellLine), "test-cell-001"))
        }
        """
        results = list(cell_lines_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected resistance for test-cell-001"
        assert "Cisplatin" in str(results[0].resistance), \
            f"Expected 'Cisplatin', got {results[0].resistance}"

    def test_origin_year_field_present(self, cell_lines_graph, namespaces):
        """Origin year field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?cellLine ?year
        WHERE {
            ?cellLine a nf:CellLine ;
                      nf:originYear ?year .
            FILTER(CONTAINS(STR(?cellLine), "test-cell-001"))
        }
        """
        results = list(cell_lines_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected originYear for test-cell-001"
        assert "2015" in str(results[0].year), \
            f"Expected '2015', got {results[0].year}"

    def test_str_profile_field_present(self, cell_lines_graph, namespaces):
        """STR profile field should be present"""
        NF = namespaces["nf"]

        query = """
        SELECT ?cellLine ?profile
        WHERE {
            ?cellLine a nf:CellLine ;
                      nf:strProfile ?profile .
            FILTER(CONTAINS(STR(?cellLine), "test-cell-001"))
        }
        """
        results = list(cell_lines_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected strProfile for test-cell-001"
        assert "STR-" in str(results[0].profile), \
            f"Expected STR profile ID, got {results[0].profile}"


class TestCellLinesEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_donor_id_produces_no_triple(self, cell_lines_graph, namespaces):
        """Empty donorId should not create triple"""
        NF = namespaces["nf"]

        # test-cell-003 should have empty donorId
        query = """
        SELECT ?donorId
        WHERE {
            ?cellLine a nf:CellLine ;
                      nf:donorId ?donorId .
            FILTER(CONTAINS(STR(?cellLine), "test-cell-003"))
        }
        """
        results = list(cell_lines_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty donorId should not produce triple"

    def test_no_empty_literal_values(self, cell_lines_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(cell_lines_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


class TestCellLinesBasicProperties:
    """Test basic cell line properties"""

    def test_cell_line_ids_present(self, cell_lines_graph, namespaces):
        """Cell lines should have IDs"""
        NF = namespaces["nf"]

        query = """
        SELECT ?cellLine ?cellLineId
        WHERE {
            ?cellLine a nf:CellLine ;
                      nf:cellLineId ?cellLineId .
        }
        """
        results = list(cell_lines_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Cell lines should have cellLineId"


# Run with: pytest test/test_rml_cell_lines.py -v
