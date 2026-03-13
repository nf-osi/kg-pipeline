#!/usr/bin/env bash
# Test graph + SPARQL+Text queries against the QLever endpoint.
# Starts qlever-server-text, runs queries, then stops the service.
#
# Usage:
#   ./scripts/test_sparql_with_text.sh          # manage server lifecycle automatically
#   ./scripts/test_sparql_with_text.sh <url>    # run against an already-running endpoint
#
# Prerequisite: docker compose run --rm qlever-index-text

SERVER_SERVICE="qlever-server-text"
source "$(dirname "$0")/qlever_test_helpers.sh"

# ============================================================
# Graph queries
# ============================================================

# 1. Health check (JSON -- ASK returns boolean)
query "Health check" \
  "ASK { ?s ?p ?o }" json

# 2. Total triple count
query "Triple count" \
  "SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }"

# 3. Instance counts by type
query "Instance counts by type" \
  "SELECT ?type (COUNT(?s) AS ?count) WHERE { ?s a ?type } GROUP BY ?type ORDER BY DESC(?count)"

# ============================================================
# Text queries
# ============================================================

echo "=== SPARQL+Text queries ==="
echo

# 4. Text index health check
query "Text search: neurofibromatosis" \
  "SELECT (COUNT(?text) AS ?count) WHERE {
    ?text ql:contains-word \"neurofibromatosis\"
  }"

# 5. Prefix search
query "Prefix search: schwann*" \
  "SELECT ?text WHERE {
    ?text ql:contains-word \"schwann*\"
  } LIMIT 5"

# 6. Entity + word — passages mentioning NF1 gene with "mutation"
query "Entity + word: NF1 gene + mutation" \
  "SELECT (COUNT(?text) AS ?count) WHERE {
    ?text ql:contains-entity <https://www.ncbi.nlm.nih.gov/gene/4763> .
    ?text ql:contains-word \"mutation*\"
  }"

# 7. Entity + word — MeSH disease with "treatment"
query "Entity + word: neurofibromatosis MeSH + treatment" \
  "SELECT ?text WHERE {
    ?text ql:contains-entity <http://id.nlm.nih.gov/mesh/D009456> .
    ?text ql:contains-word \"treatment\"
  } LIMIT 5"

# 8. Word + entity co-occurrence — tumor near NF1 gene
query "Co-occurrence: tumor + NF1 gene" \
  "SELECT ?text WHERE {
    ?text ql:contains-word \"tumor\" .
    ?text ql:contains-entity <https://www.ncbi.nlm.nih.gov/gene/4763>
  } LIMIT 5"

# 9. Text + graph join
query "Text + graph join: genes mentioned with neurofibromatosis" \
  "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  SELECT ?entity ?label (COUNT(?text) AS ?mentions) WHERE {
    ?text ql:contains-word \"neurofibromatosis\" .
    ?text ql:contains-entity ?entity .
    ?entity a <http://nf-osi.github.com/terms#Gene> .
    ?entity rdfs:label ?label
  }
  GROUP BY ?entity ?label
  ORDER BY DESC(?mentions)
  LIMIT 10"

# 10. Entity type counts
query "Entity type counts" \
  "PREFIX nf: <http://nf-osi.github.com/terms#>
  PREFIX obo: <http://purl.obolibrary.org/obo/>
  SELECT ?type (COUNT(?e) AS ?count) WHERE {
    VALUES ?type { nf:Gene nf:DiseaseAnnotation nf:Chemical obo:NCBITaxon_species nf:CellLine nf:Variant }
    ?e a ?type
  }
  GROUP BY ?type
  ORDER BY DESC(?count)"

# 11. Multi-word search — passages containing both "clinical" and "trial"
query "Multi-word search: clinical trial*" \
  "SELECT (COUNT(?text) AS ?count) WHERE {
    ?text ql:contains-word \"clinical trial*\"
  }"

echo "All queries completed."
