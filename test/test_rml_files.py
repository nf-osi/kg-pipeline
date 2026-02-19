"""
Tests for Files RML mapping

Tests the files.rml.ttl mapping against test/files.csv
Includes tests for multi-value pipe splitting and IRI fields
"""

import pytest
from rdflib import URIRef, Literal
from rdflib.namespace import RDF


@pytest.fixture
def files_graph(rml_runner, namespaces):
    """Load files RDF graph from test data"""
    graph = rml_runner(
        mapping_file="files.rml.ttl",
        csv_replacements={"data/csv/files_harmonized.csv": "test/files.csv"}
    )
    return graph


SYN_BASE = "https://www.synapse.org/Synapse:"


class TestFilesCore:
    """Test core file properties"""

    def test_file_has_correct_type(self, files_graph, namespaces):
        """All files should have type nf:File"""
        files = list(files_graph.subjects(RDF.type, namespaces["nf"].File))
        assert len(files) >= 3, f"Expected at least 3 files, got {len(files)}"

    def test_file_id_is_iri(self, files_graph, namespaces):
        """File subjects should be Synapse URL IRIs"""
        files = list(files_graph.subjects(RDF.type, namespaces["nf"].File))
        for file in files:
            assert isinstance(file, URIRef)
            assert str(file).startswith(SYN_BASE), \
                f"File IRI should start with {SYN_BASE}, got {file}"

    def test_file_name_present(self, files_graph, namespaces):
        """Files should have name property"""
        NF = namespaces["nf"]
        query = """
        SELECT ?file ?name WHERE {
            ?file a nf:File ; nf:name ?name .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0
        names = [str(row.name) for row in results]
        assert any("Test File" in name for name in names)

    def test_parent_study_is_iri(self, files_graph, namespaces):
        """parentStudy should be a Synapse IRI"""
        NF = namespaces["nf"]
        query = """
        SELECT ?study WHERE {
            ?file a nf:File ; nf:parentStudy ?study .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0
        for row in results:
            assert str(row.study).startswith(SYN_BASE)


class TestFilesMultiValue:
    """Test multi-value field handling (pipe-delimited lists)"""

    def test_diagnosis_multi_value_split(self, files_graph, namespaces):
        """Diagnosis should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?diagnosis WHERE {
            ?file a nf:File ; nf:diagnosis ?diagnosis .
        }
        """
        diagnoses = [str(r.diagnosis) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "NF1" in diagnoses
        assert "Schwannomatosis" in diagnoses

    def test_specimen_id_multi_value_split(self, files_graph, namespaces):
        """SpecimenID should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?specimenId WHERE {
            ?file a nf:File ; nf:specimenID ?specimenId .
        }
        """
        ids = [str(r.specimenId) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "Spec1" in ids
        assert "Spec2" in ids

    def test_specimen_id_three_values(self, files_graph, namespaces):
        """SpecimenID with three values should split correctly"""
        NF = namespaces["nf"]
        query = """
        SELECT ?specimenId WHERE {
            <https://www.synapse.org/Synapse:syn9999993> nf:specimenID ?specimenId .
        }
        """
        ids = [str(r.specimenId) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "Spec3" in ids
        assert "Spec4" in ids
        assert "Spec5" in ids

    def test_single_diagnosis_value(self, files_graph, namespaces):
        """Single diagnosis value should be handled correctly"""
        NF = namespaces["nf"]
        query = """
        SELECT ?diagnosis WHERE {
            <https://www.synapse.org/Synapse:syn9999993> nf:diagnosis ?diagnosis .
        }
        """
        diagnoses = [str(r.diagnosis) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "NF2" in diagnoses

    def test_individual_id_split(self, files_graph, namespaces):
        """individualID should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?iid WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:individualID ?iid .
        }
        """
        ids = [str(r.iid) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "Ind1" in ids
        assert "Ind2" in ids

    def test_nf1_genotype_split(self, files_graph, namespaces):
        """nf1Genotype should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?g WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:nf1Genotype ?g .
        }
        """
        genotypes = [str(r.g) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "+/-" in genotypes
        assert "+/+" in genotypes

    def test_cell_type_split(self, files_graph, namespaces):
        """cellType should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?ct WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:cellType ?ct .
        }
        """
        types = [str(r.ct) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "Schwann Cell" in types
        assert "arachnoid" in types

    def test_tissue_split(self, files_graph, namespaces):
        """tissue should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?t WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:tissue ?t .
        }
        """
        tissues = [str(r.t) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "Nerve" in tissues
        assert "skin" in tissues

    def test_funding_agency_split(self, files_graph, namespaces):
        """fundingAgency should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?fa WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:funder ?fa .
        }
        """
        funders = [str(r.fa) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "NTAP" in funders
        assert "NFRI" in funders

    def test_compound_name_split(self, files_graph, namespaces):
        """compoundName should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?c WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:compoundName ?c .
        }
        """
        compounds = [str(r.c) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "DrugA" in compounds
        assert "DrugB" in compounds

    def test_experimental_condition_split(self, files_graph, namespaces):
        """experimentalCondition should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?ec WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:experimentalCondition ?ec .
        }
        """
        conditions = [str(r.ec) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "ConditionX" in conditions
        assert "ConditionY" in conditions

    def test_model_system_name_split(self, files_graph, namespaces):
        """modelSystemName should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?m WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:modelSystemName ?m .
        }
        """
        models = [str(r.m) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "ModelA" in models
        assert "ModelB" in models

    def test_tumor_type_split(self, files_graph, namespaces):
        """tumorType should split on pipe delimiter"""
        NF = namespaces["nf"]
        query = """
        SELECT ?tt WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:tumorType ?tt .
        }
        """
        types = [str(r.tt) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "Neurofibroma" in types
        assert "Schwannoma" in types


class TestFilesIRIFields:
    """Test IRI-valued fields"""

    def test_model_system_iri(self, files_graph, namespaces):
        """hasModelSystem should emit pipe-split IRIs"""
        NF = namespaces["nf"]
        query = """
        SELECT ?ms WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:hasModelSystem ?ms .
        }
        """
        iris = [str(r.ms) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "http://nf-osi.github.com/terms#cellLine/1" in iris
        assert "http://nf-osi.github.com/terms#animalModel/2" in iris

    def test_data_type_iri(self, files_graph, namespaces):
        """dataType should emit IRI from dataTypeIRI column"""
        NF = namespaces["nf"]
        query = """
        SELECT ?dt WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:dataType ?dt .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0
        iris = [str(r.dt) for r in results]
        assert "http://nf-osi.github.com/terms#GeneExpression" in iris

    def test_nf1_genotype_iri_multi(self, files_graph, namespaces):
        """hasNF1Genotype should emit pipe-split genotype class IRIs"""
        NF = namespaces["nf"]
        query = """
        SELECT ?g WHERE {
            <https://www.synapse.org/Synapse:syn9999991> nf:hasNF1Genotype ?g .
        }
        """
        iris = [str(r.g) for r in files_graph.query(query, initNs={"nf": NF})]
        assert "http://nf-osi.github.com/terms#NF1Heterozygous" in iris
        assert "http://nf-osi.github.com/terms#NF1WildType" in iris

    def test_nf1_genotype_iri_single(self, files_graph, namespaces):
        """hasNF1Genotype should work for single genotype value"""
        NF = namespaces["nf"]
        query = """
        SELECT ?g WHERE {
            <https://www.synapse.org/Synapse:syn9999992> nf:hasNF1Genotype ?g .
        }
        """
        iris = [str(r.g) for r in files_graph.query(query, initNs={"nf": NF})]
        assert len(iris) == 1
        assert "http://nf-osi.github.com/terms#NF1WildType" in iris

    def test_nf2_genotype_iri(self, files_graph, namespaces):
        """hasNF2Genotype should emit genotype class IRI"""
        NF = namespaces["nf"]
        query = """
        SELECT ?g WHERE {
            <https://www.synapse.org/Synapse:syn9999992> nf:hasNF2Genotype ?g .
        }
        """
        iris = [str(r.g) for r in files_graph.query(query, initNs={"nf": NF})]
        assert len(iris) == 1
        assert "http://nf-osi.github.com/terms#NF2WildType" in iris

    def test_empty_genotype_iri_produces_no_triple(self, files_graph, namespaces):
        """Empty nf1GenotypeIRI/nf2GenotypeIRI should not create triples"""
        NF = namespaces["nf"]
        for pred in ["hasNF1Genotype", "hasNF2Genotype"]:
            query = f"""
            SELECT ?g WHERE {{
                <https://www.synapse.org/Synapse:syn9999993> nf:{pred} ?g .
            }}
            """
            results = list(files_graph.query(query, initNs={"nf": NF}))
            assert len(results) == 0, f"Expected no {pred} for syn9999993"


class TestFilesNumericFields:
    """Test numeric field handling"""

    def test_report_milestone_number(self, files_graph, namespaces):
        """ReportMilestone should be present as number"""
        NF = namespaces["nf"]
        query = """
        SELECT ?milestone WHERE {
            ?file a nf:File ; nf:reportMilestone ?milestone .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        assert len(results) > 0
        milestones = [str(row.milestone) for row in results]
        assert any("1" in m for m in milestones)


class TestFilesEmptyFields:
    """Test that empty fields are handled correctly"""

    def test_empty_diagnosis_produces_no_triple(self, files_graph, namespaces):
        """Empty diagnosis should not create triple"""
        NF = namespaces["nf"]
        query = """
        SELECT ?diagnosis WHERE {
            <https://www.synapse.org/Synapse:syn9999992> nf:diagnosis ?diagnosis .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0

    def test_empty_funding_agency_produces_no_triple(self, files_graph, namespaces):
        """Empty fundingAgency should not create triple"""
        NF = namespaces["nf"]
        query = """
        SELECT ?fa WHERE {
            <https://www.synapse.org/Synapse:syn9999992> nf:funder ?fa .
        }
        """
        results = list(files_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0

    def test_no_empty_literal_values(self, files_graph):
        """Graph should not contain any empty string literals"""
        query = """
        SELECT ?s ?p ?o WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(files_graph.query(query))
        assert len(results) == 0, \
            f"Found {len(results)} empty literal values in graph"


# Run with: pytest test/test_rml_files.py -v
