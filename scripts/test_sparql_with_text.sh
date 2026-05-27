#!/usr/bin/env bash
# Test graph + SPARQL+Text queries against the QLever endpoint.
# Starts qlever-text, runs queries, then stops the service.
#
# Usage:
#   ./scripts/test_sparql_with_text.sh          # manage server lifecycle automatically
#   ./scripts/test_sparql_with_text.sh <url>    # run against an already-running endpoint
#
# Prerequisite: docker compose build qlever-text

SERVER_SERVICE="qlever-text"
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

# 4. Entity type counts
query "Entity type counts" \
  "PREFIX nf: <http://nf-osi.github.com/terms#>
  PREFIX biolink: <https://w3id.org/biolink/vocab/>
  PREFIX obo: <http://purl.obolibrary.org/obo/>
  SELECT ?type (COUNT(?e) AS ?count) WHERE {
    VALUES ?type { nf:Gene nf:DiseaseAnnotation biolink:ChemicalEntity obo:NCBITaxon_species nf:CellLine nf:Variant }
    ?e a ?type
  }
  GROUP BY ?type
  ORDER BY DESC(?count)"

# ============================================================
# BioLink alignment (#61)
# ============================================================

# 5. BioLink-typed text entities — Chemical is now biolink:ChemicalEntity
query "BioLink text entity: biolink:ChemicalEntity count" \
  "PREFIX biolink: <https://w3id.org/biolink/vocab/>
  SELECT (COUNT(?e) AS ?count) WHERE {
    ?e a biolink:ChemicalEntity
  }"

# 6. Subclass traversal for text entities — nf:Gene subClassOf biolink:Gene
query "Subclass traversal: biolink:Gene text entities" \
  "PREFIX nf: <http://nf-osi.github.com/terms#>
  PREFIX biolink: <https://w3id.org/biolink/vocab/>
  PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
  SELECT ?type (COUNT(?e) AS ?count) WHERE {
    ?type rdfs:subClassOf biolink:Gene .
    ?e a ?type .
  } GROUP BY ?type"

# ============================================================
# Text queries
# ============================================================

echo "=== SPARQL+Text queries ==="
echo

# 7. Word search
query "Text search: neurofibromatosis" \
  "SELECT (COUNT(?text) AS ?count) WHERE {
    ?text ql:contains-word \"neurofibromatosis\"
  }"

# 8. Prefix search
query "Prefix search: schwann*" \
  "SELECT ?text WHERE {
    ?text ql:contains-word \"schwann*\"
  } LIMIT 5"

# 9. Entity + word — passages mentioning NF1 gene with "mutation"
query "Entity + word: NF1 gene + mutation" \
  "SELECT (COUNT(?text) AS ?count) WHERE {
    ?text ql:contains-entity <https://www.ncbi.nlm.nih.gov/gene/4763> .
    ?text ql:contains-word \"mutation*\"
  }"

# 10. Entity + word — MeSH disease with "treatment"
query "Entity + word: neurofibromatosis MeSH + treatment" \
  "SELECT ?text WHERE {
    ?text ql:contains-entity <http://id.nlm.nih.gov/mesh/D009456> .
    ?text ql:contains-word \"treatment\"
  } LIMIT 5"

# 11. Word + entity co-occurrence — tumor near NF1 gene
query "Co-occurrence: tumor + NF1 gene" \
  "SELECT ?text WHERE {
    ?text ql:contains-word \"tumor\" .
    ?text ql:contains-entity <https://www.ncbi.nlm.nih.gov/gene/4763>
  } LIMIT 5"

# 12. Text + graph join
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

# 13. Multi-word search — passages containing both "clinical" and "trial"
query "Multi-word search: clinical trial*" \
  "SELECT (COUNT(?text) AS ?count) WHERE {
    ?text ql:contains-word \"clinical trial*\"
  }"

# 14. Publication passage count — entity-only via wildcard trick
query "Publication passages: PMID 16822308" \
  "SELECT (COUNT(DISTINCT ?text) AS ?passages) WHERE {
    ?text ql:contains-entity <https://pubmed.ncbi.nlm.nih.gov/16822308> .
    ?text ql:contains-word \"*\"
  }"

echo "All queries completed."
echo "Log: $LOG_FILE"
