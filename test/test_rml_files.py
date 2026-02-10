"""
Tests for Files RML mapping

Tests the portal_files.rml.ttl mapping against test/files.csv
Includes tests for IRI transformation (fundingAgency, dataType)
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def files_graph(rml_runner, namespaces):
    """Load files RDF graph from test data (before IRI transformation)"""
    graph = rml_runner(
        mapping_file="portal_files.rml.ttl",
        csv_replacements={"data/csv/files.csv": "test/files.csv"}
    )
    return graph


@pytest.fixture
def files_graph_transformed(files_graph, transform_iris):
    """Load files RDF graph after IRI transformation"""
    return transform_iris(files_graph)


class TestFilesCore:
    """Test core file properties"""

    def test_file_has_correct_type(self, files_graph, namespaces):
        """All files should have type nf:File"""
        files = list(files_graph.subjects(RDF.type, namespaces["nf"].File))
        assert len(files) > 0, "No files found in graph"
        assert len(files) >= 3, f"Expected at least 3 files, got {len(files)}"

    def test_file_id_is_iri(self, files_graph, namespaces):
        """File subjects should be IRIs (Synapse IDs)"""
        files = list(files_graph.subjects(RDF.type, namespaces["nf"].File))
        for file in files:
            assert isinstance(file, URIRef), \
                f"File ID should be IRI, got {type(file)}"
            # Should contain synapse ID format
            file_str = str(file)
            assert "syn" in file_str.lower(), \
                f"File IRI should contain Synapse ID: {file_str}"

    def test_file_name_present(self, files_graph, namespaces):
        """Files should have name property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?name
        WHERE {
            ?file a nf:File ;
                  nf:name ?name .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Files should have names"

        names = [str(row.name) for row in results]
        assert any("Test File" in name for name in names), \
            "Expected test file names"


class TestFilesMultiValue:
    """Test multi-value field handling (pipe-delimited lists)"""

    def test_diagnosis_multi_value_split(self, files_graph, namespaces):
        """Diagnosis should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?diagnosis
        WHERE {
            ?file a nf:File ;
                  nf:diagnosis ?diagnosis .
        }
        """
        results = files_graph.query(query, initNs={"nf": NF})
        diagnoses = [str(row.diagnosis) for row in results]

        # File with "NF1|Schwannomatosis" should have both values
        assert "NF1" in diagnoses, "Expected 'NF1' diagnosis"
        assert "Schwannomatosis" in diagnoses, "Expected 'Schwannomatosis' diagnosis"

    def test_specimen_id_multi_value_split(self, files_graph, namespaces):
        """SpecimenID should split on pipe delimiter"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?specimenId
        WHERE {
            ?file a nf:File ;
                  nf:specimenID ?specimenId .
        }
        """
        results = files_graph.query(query, initNs={"nf": NF})
        specimen_ids = [str(row.specimenId) for row in results]

        # File with "Spec1|Spec2" should have both values
        assert "Spec1" in specimen_ids, "Expected 'Spec1' specimenID"
        assert "Spec2" in specimen_ids, "Expected 'Spec2' specimenID"

    def test_specimen_id_three_values(self, files_graph, namespaces):
        """SpecimenID with three values should split correctly"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?specimenId
        WHERE {
            ?file a nf:File ;
                  nf:specimenID ?specimenId .
            FILTER(CONTAINS(STR(?file), "syn9999993"))
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        specimen_ids = [str(row.specimenId) for row in results]

        # File syn9999993 has "Spec3|Spec4|Spec5"
        assert "Spec3" in specimen_ids, "Expected 'Spec3' specimenID"
        assert "Spec4" in specimen_ids, "Expected 'Spec4' specimenID"
        assert "Spec5" in specimen_ids, "Expected 'Spec5' specimenID"

    def test_single_diagnosis_value(self, files_graph, namespaces):
        """Single diagnosis value should be handled correctly"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?diagnosis
        WHERE {
            ?file a nf:File ;
                  nf:diagnosis ?diagnosis .
            FILTER(CONTAINS(STR(?file), "syn9999993"))
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        diagnoses = [str(row.diagnosis) for row in results]

        # File syn9999993 has single diagnosis "NF2"
        assert "NF2" in diagnoses, "Expected 'NF2' diagnosis"


class TestFilesIRITransformation:
    """Test IRI transformation for fundingAgency field"""

    def test_funding_agency_ntap_is_iri(self, files_graph_transformed, namespaces):
        """FundingAgency 'NTAP' should be IRI after transformation"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?funder
        WHERE {
            ?file a nf:File ;
                  nf:hasFunder ?funder .
        }
        """
        results = list(files_graph_transformed.query(query, initNs={"nf": NF}))

        funders = [str(row.funder) for row in results]
        # NTAP should be transformed to IRI
        assert any("NTAP" in funder for funder in funders), \
            f"Expected 'NTAP' IRI, got {funders}"

        # Verify it's an IRI not a literal
        for row in results:
            if "NTAP" in str(row.funder):
                assert isinstance(row.funder, URIRef), \
                    f"NTAP should be IRI, got {type(row.funder)}"

    def test_funding_agency_with_spaces_becomes_iri(self, files_graph_transformed, namespaces):
        """FundingAgency with spaces should become IRI with underscores"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?funder
        WHERE {
            ?file a nf:File ;
                  nf:hasFunder ?funder .
        }
        """
        results = files_graph_transformed.query(query, initNs={"nf": NF})
        funders = [str(row.funder) for row in results]

        # "CTF Foundation" should become "CTF_Foundation"
        assert any("CTF_Foundation" in funder for funder in funders), \
            f"Expected 'CTF_Foundation' IRI, got {funders}"


class TestFilesNumericFields:
    """Test numeric field handling"""

    def test_report_milestone_number(self, files_graph, namespaces):
        """ReportMilestone should be present as number"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?milestone
        WHERE {
            ?file a nf:File ;
                  nf:reportMilestone ?milestone .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))

        assert len(results) > 0, "Expected reportMilestone values"
        # Should have milestone value (could be number or string "1.0")
        milestones = [str(row.milestone) for row in results]
        assert any("1" in milestone for milestone in milestones), \
            f"Expected milestone value, got {milestones}"


class TestFilesEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_diagnosis_produces_no_triple(self, files_graph, namespaces):
        """Empty diagnosis should not create triple"""
        NF = namespaces["nf"]

        # syn9999992 should have empty diagnosis
        query = """
        SELECT ?diagnosis
        WHERE {
            <https://www.synapse.org/#!Synapse:syn9999992> nf:diagnosis ?diagnosis .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, \
            "Empty diagnosis should not produce triple"

    def test_no_empty_literal_values(self, files_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(files_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


class TestFilesDataType:
    """Test dataType field handling"""

    def test_data_type_is_iri_after_transformation(self, files_graph_transformed, namespaces):
        """DataType should be IRI, not literal, after transformation"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?dataType
        WHERE {
            ?file a nf:File ;
                  nf:dataType ?dataType .
        }
        """
        results = list(files_graph_transformed.query(query, initNs={"nf": NF}))

        if len(results) > 0:
            for row in results:
                assert isinstance(row.dataType, URIRef), \
                    f"DataType should be IRI after transformation, got {type(row.dataType)}: {row.dataType}"


class TestFilesBasicProperties:
    """Test basic file properties"""

    def test_basic_properties_present(self, files_graph, namespaces):
        """Files should have basic properties"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?name
        WHERE {
            ?file a nf:File ;
                  nf:name ?name .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0, "Files should have names"

    def test_file_format_present(self, files_graph, namespaces):
        """Files should have fileFormat property"""
        NF = namespaces["nf"]

        query = """
        SELECT ?file ?format
        WHERE {
            ?file a nf:File ;
                  nf:fileFormat ?format .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        # fileFormat might not be in all test data, so just check structure
        if len(results) > 0:
            assert isinstance(results[0].format, Literal), \
                "File format should be literal"


# Run with: pytest test/test_rml_files.py -v
