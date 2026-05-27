#!/usr/bin/env bash
# Test graph queries against the QLever endpoint.
# Starts qlever-rdf, runs queries, then stops the service.
#
# Usage:
#   ./scripts/test_sparql.sh          # manage server lifecycle automatically
#   ./scripts/test_sparql.sh <url>    # run against an already-running endpoint

SERVER_SERVICE="qlever-rdf"
source "$(dirname "$0")/qlever_test_helpers.sh"

# 1. Health check (JSON -- ASK returns boolean)
query "Health check" \
  "ASK { ?s ?p ?o }" json

# 2. Total triple count
query "Triple count" \
  "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }"

# 3. Instance counts by type
query "Instance counts by type" \
  "SELECT ?type (COUNT(?s) AS ?count) WHERE { ?s a ?type } GROUP BY ?type ORDER BY DESC(?count)"

# 4. Predicate usage
query "Predicate usage" \
  "SELECT ?p (COUNT(*) AS ?count) WHERE { ?s ?p ?o } GROUP BY ?p ORDER BY DESC(?count) LIMIT 20"

# 5. Sample instances from the NF namespace
query "Sample NF instances" \
  "SELECT ?s ?type WHERE { ?s a ?type . FILTER(STRSTARTS(STR(?type), 'http://nf-osi.github.com/terms#')) } LIMIT 10"

# ============================================================
# New resource types (#56)
# ============================================================

PREFIX="PREFIX nf: <http://nf-osi.github.com/terms#>
PREFIX biolink: <https://w3id.org/biolink/vocab/>"

# 6. New type counts — all six new types must be non-zero
query "New type counts" \
  "$PREFIX
  SELECT ?type (COUNT(?s) AS ?count) WHERE {
    VALUES ?type {
      nf:ClinicalAssessmentTool nf:PatientDerivedModel nf:OrganoidProtocol
      nf:ComputationalTool nf:Initiative biolink:Dataset
    }
    ?s a ?type
  } GROUP BY ?type ORDER BY ?type"

# 7. New tool types carry registry metadata from resources table
query "New tool types have name and resourceId" \
  "$PREFIX
  SELECT ?type (COUNT(?s) AS ?count) WHERE {
    VALUES ?type {
      nf:ClinicalAssessmentTool nf:PatientDerivedModel nf:OrganoidProtocol nf:ComputationalTool
    }
    ?s a ?type ; nf:name ?name ; nf:resourceId ?rid .
  } GROUP BY ?type ORDER BY ?type"

# 8. Initiatives link to funders
query "Initiatives with funder links" \
  "$PREFIX
  SELECT ?name ?funder WHERE {
    ?ini a nf:Initiative ; nf:name ?name ; nf:hasFunder ?funder .
  } ORDER BY ?name LIMIT 10"

# 9. Datasets link to parent studies
query "Datasets with parent study links" \
  "$PREFIX
  SELECT (COUNT(?ds) AS ?total) (COUNT(?study) AS ?with_study) WHERE {
    ?ds a biolink:Dataset .
    OPTIONAL { ?ds nf:parentStudy ?study }
  }"

# 10. Datasets with numeric counts are typed correctly
query "Dataset numeric fields are integers" \
  "$PREFIX
  SELECT ?ds ?items ?individuals WHERE {
    ?ds a biolink:Dataset ;
        nf:datasetItemCount ?items ;
        nf:individualCount ?individuals .
  } LIMIT 5"

# 11. PatientDerivedModel → donor links
query "Patient derived models with donor links" \
  "$PREFIX
  SELECT ?model ?donor WHERE {
    ?model a nf:PatientDerivedModel ; nf:fromDonor ?donor .
  } LIMIT 5"

# 12. Cross-type: datasets sharing disease focus with studies
query "Datasets and studies sharing NF1 disease focus" \
  "$PREFIX
  SELECT (COUNT(DISTINCT ?ds) AS ?datasets) (COUNT(DISTINCT ?study) AS ?studies) WHERE {
    { ?ds a biolink:Dataset ; nf:diseaseFocus ?focus . FILTER(CONTAINS(?focus, 'Neurofibromatosis')) }
    UNION
    { ?study a biolink:Study ; nf:diseaseFocus ?focus . FILTER(CONTAINS(?focus, 'Neurofibromatosis')) }
  }"

# ============================================================
# BioLink alignment (#61)
# ============================================================

# 13. BioLink direct type counts — replaced classes should have instances
query "BioLink direct type counts" \
  "$PREFIX
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  SELECT ?type (COUNT(?s) AS ?count) WHERE {
    VALUES ?type { biolink:Study biolink:Dataset biolink:Publication }
    ?s a ?type
  } GROUP BY ?type ORDER BY ?type"

# 14. BioLink subclass declarations — ontology should assert all 8 alignments
query "BioLink subclass declarations in ontology" \
  "$PREFIX
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  SELECT ?nfClass ?biolinkClass WHERE {
    VALUES (?nfClass ?biolinkClass) {
      (nf:CellLine        biolink:CellLine)
      (nf:Mutation         biolink:SequenceVariant)
      (nf:Gene             biolink:Gene)
      (nf:Variant          biolink:SequenceVariant)
      (nf:Genotype         biolink:Genotype)
      (nf:Antibody         biolink:Protein)
      (nf:ComputationalTool biolink:Software)
      (nf:Investigator     biolink:Person)
    }
    ?nfClass rdfs:subClassOf ?biolinkClass .
  }"

# 15. Subclass traversal: find all biolink:CellLine entities (1-hop)
query "Subclass traversal: biolink:CellLine entities" \
  "$PREFIX
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  SELECT ?subtype (COUNT(?x) AS ?count) WHERE {
    ?subtype rdfs:subClassOf* nf:CellLine .
    ?x a ?subtype .
  } GROUP BY ?subtype ORDER BY DESC(?count)"

# 16. Subclass traversal: biolink:SequenceVariant coverage (2-hop)
query "Subclass traversal: biolink:SequenceVariant coverage" \
  "$PREFIX
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  SELECT ?subtype (COUNT(?x) AS ?count) WHERE {
    ?subtype rdfs:subClassOf* nf:Mutation .
    ?x a ?subtype .
  } GROUP BY ?subtype ORDER BY DESC(?count)"

# 17. Cross-portal query: studies with their datasets using BioLink types
query "Cross-portal pattern: biolink:Study with biolink:Dataset" \
  "$PREFIX
  SELECT ?study ?studyName (COUNT(?ds) AS ?datasetCount) WHERE {
    ?ds a biolink:Dataset ;
        nf:parentStudy ?study .
    ?study a biolink:Study ;
           nf:name ?studyName .
  } GROUP BY ?study ?studyName ORDER BY DESC(?datasetCount) LIMIT 10"

echo "All queries completed."
echo "Log: $LOG_FILE"
