"""
Tests for Datasets RML mapping

Tests the datasets.rml.ttl mapping against test/datasets.csv
"""

import pytest
from rdflib import URIRef, Literal, Namespace, XSD
from rdflib.namespace import RDF


NF = Namespace("http://nf-osi.github.com/terms#")
SYN = Namespace("https://www.synapse.org/Synapse:")


@pytest.fixture
def datasets_graph(rml_runner, namespaces):
    """Load datasets RDF graph from test data"""
    graph = rml_runner(
        mapping_file="datasets.rml.ttl",
        csv_replacements={
            "data/csv/datasets.csv": "test/datasets.csv"
        }
    )
    return graph


class TestDatasetCore:
    """Test core dataset properties"""

    def test_has_correct_type(self, datasets_graph, namespaces):
        """All entries should have type nf:Dataset"""
        datasets = list(datasets_graph.subjects(RDF.type, NF.Dataset))
        assert len(datasets) == 3, f"Expected 3 datasets, got {len(datasets)}"

    def test_subject_is_iri(self, datasets_graph, namespaces):
        """Subjects should be IRIs"""
        datasets = list(datasets_graph.subjects(RDF.type, NF.Dataset))
        for ds in datasets:
            assert isinstance(ds, URIRef), f"Subject should be IRI, got {type(ds)}"

    def test_iri_uses_synapse_pattern(self, datasets_graph, namespaces):
        """IRI should use https://www.synapse.org/Synapse:{id} pattern"""
        datasets = list(datasets_graph.subjects(RDF.type, NF.Dataset))
        iris = [str(ds) for ds in datasets]
        assert any("Synapse:syn29654184" in iri for iri in iris), \
            f"Expected Synapse IRI pattern, got: {iris}"

    def test_title_present(self, datasets_graph, namespaces):
        """name (from title) should be present"""
        query = """
        SELECT ?name
        WHERE {
            ?ds a nf:Dataset ;
                nf:name ?name .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].name) == "Patient-derived cNF RNA-seq Counts"

    def test_parent_study_is_iri(self, datasets_graph, namespaces):
        """parentStudy should be a Synapse IRI"""
        query = """
        SELECT ?study
        WHERE {
            ?ds a nf:Dataset ;
                nf:parentStudy ?study .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].study, URIRef)
        assert "syn11374339" in str(results[0].study)

    def test_disease_focus_present(self, datasets_graph, namespaces):
        """diseaseFocus should be present"""
        query = """
        SELECT ?focus
        WHERE {
            ?ds a nf:Dataset ;
                nf:diseaseFocus ?focus .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].focus) == "Neurofibromatosis type 1"

    def test_access_type_present(self, datasets_graph, namespaces):
        """accessType should be present"""
        query = """
        SELECT ?access
        WHERE {
            ?ds a nf:Dataset ;
                nf:accessType ?access .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert str(results[0].access) == "Public Access"

    def test_license_is_iri(self, datasets_graph, namespaces):
        """license should be an IRI"""
        query = """
        SELECT ?lic
        WHERE {
            ?ds a nf:Dataset ;
                nf:license ?lic .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].lic, URIRef)
        assert "creativecommons" in str(results[0].lic)

    def test_doi_is_iri(self, datasets_graph, namespaces):
        """doi should be an IRI"""
        query = """
        SELECT ?doi
        WHERE {
            ?ds a nf:Dataset ;
                nf:doi ?doi .
            FILTER(CONTAINS(STR(?ds), "syn29783617"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].doi, URIRef)

    def test_empty_doi_produces_no_triple(self, datasets_graph, namespaces):
        """Empty doi should not produce a triple"""
        query = """
        SELECT ?doi
        WHERE {
            ?ds a nf:Dataset ;
                nf:doi ?doi .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 0, "Empty doi should produce no triple"

    def test_external_repository_is_iri(self, datasets_graph, namespaces):
        """externalRepositoryUri should be an IRI when set"""
        query = """
        SELECT ?repo
        WHERE {
            ?ds a nf:Dataset ;
                nf:externalRepositoryUri ?repo .
            FILTER(CONTAINS(STR(?ds), "syn12345678"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].repo, URIRef)
        assert "zenodo" in str(results[0].repo)

    def test_numeric_counts_are_integers(self, datasets_graph, namespaces):
        """datasetItemCount, individualCount, specimenCount, yearPublished should be typed integers"""
        query = """
        SELECT ?itemCount ?indCount ?year
        WHERE {
            ?ds a nf:Dataset ;
                nf:datasetItemCount ?itemCount ;
                nf:individualCount ?indCount ;
                nf:yearPublished ?year .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1, "Expected one result for syn29654184"
        row = results[0]
        assert isinstance(row.itemCount, Literal), "datasetItemCount should be Literal"
        assert row.itemCount.datatype == XSD.integer, \
            f"datasetItemCount should be xsd:integer, got {row.itemCount.datatype}"
        assert int(row.itemCount) == 24
        assert row.indCount.datatype == XSD.integer
        assert int(row.indCount) == 10
        assert row.year.datatype == XSD.integer
        assert int(row.year) == 2022

    def test_dataset_size_is_long(self, datasets_graph, namespaces):
        """datasetSizeInBytes should be typed as xsd:long"""
        query = """
        SELECT ?size
        WHERE {
            ?ds a nf:Dataset ;
                nf:datasetSizeInBytes ?size .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        row = results[0]
        assert isinstance(row.size, Literal)
        assert row.size.datatype == XSD.long, \
            f"datasetSizeInBytes should be xsd:long, got {row.size.datatype}"
        assert int(row.size) == 52000000


class TestDatasetMultiValue:
    """Test multi-value field handling"""

    def test_data_type_split(self, datasets_graph, namespaces):
        """dataType should split on pipe"""
        query = """
        SELECT ?dt
        WHERE {
            ?ds a nf:Dataset ;
                nf:dataType ?dt .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        values = [str(r.dt) for r in results]
        assert "count matrix" in values
        assert "gene expression" in values
        assert len(results) == 2

    def test_manifestation_split(self, datasets_graph, namespaces):
        """manifestation should split on pipe"""
        query = """
        SELECT ?m
        WHERE {
            ?ds a nf:Dataset ;
                nf:manifestation ?m .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        values = [str(r.m) for r in results]
        assert "Cutaneous Neurofibroma" in values
        assert "Plexiform Neurofibroma" in values

    def test_species_split(self, datasets_graph, namespaces):
        """species should split on pipe"""
        query = """
        SELECT ?sp
        WHERE {
            ?ds a nf:Dataset ;
                nf:species ?sp .
            FILTER(CONTAINS(STR(?ds), "syn29783617"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        values = [str(r.sp) for r in results]
        assert "Homo sapiens" in values
        assert "Mus musculus" in values

    def test_contributor_split(self, datasets_graph, namespaces):
        """contributor should split on pipe"""
        query = """
        SELECT ?contrib
        WHERE {
            ?ds a nf:Dataset ;
                nf:contributor ?contrib .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        values = [str(r.contrib) for r in results]
        assert "Jane Smith" in values
        assert "Bob Jones" in values
        assert len(results) == 2

    def test_funder_links(self, datasets_graph, namespaces):
        """hasFunder should link to funder IRIs"""
        query = """
        SELECT ?funder
        WHERE {
            ?ds a nf:Dataset ;
                nf:hasFunder ?funder .
            FILTER(CONTAINS(STR(?ds), "syn29654184"))
        }
        """
        results = list(datasets_graph.query(query, initNs={"nf": NF}))
        assert len(results) == 1
        assert isinstance(results[0].funder, URIRef)

    def test_no_empty_literals(self, datasets_graph):
        """Graph should not contain empty string literals"""
        query = """
        SELECT ?s ?p ?o
        WHERE {
            ?s ?p ?o .
            FILTER(isLiteral(?o) && str(?o) = "")
        }
        """
        results = list(datasets_graph.query(query))
        assert len(results) == 0, f"Found {len(results)} empty literal values"
