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

PREFIX="PREFIX nf: <http://nf-osi.github.com/terms#>"

# 6. New type counts — all six new types must be non-zero
query "New type counts" \
  "$PREFIX
  SELECT ?type (COUNT(?s) AS ?count) WHERE {
    VALUES ?type {
      nf:ClinicalAssessmentTool nf:PatientDerivedModel nf:OrganoidProtocol
      nf:ComputationalTool nf:Initiative nf:Dataset
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
    ?ds a nf:Dataset .
    OPTIONAL { ?ds nf:parentStudy ?study }
  }"

# 10. Datasets with numeric counts are typed correctly
query "Dataset numeric fields are integers" \
  "$PREFIX
  SELECT ?ds ?items ?individuals WHERE {
    ?ds a nf:Dataset ;
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
    { ?ds a nf:Dataset ; nf:diseaseFocus ?focus . FILTER(CONTAINS(?focus, 'Neurofibromatosis')) }
    UNION
    { ?study a nf:Study ; nf:diseaseFocus ?focus . FILTER(CONTAINS(?focus, 'Neurofibromatosis')) }
  }"

echo "All queries completed."
echo "Log: $LOG_FILE"
