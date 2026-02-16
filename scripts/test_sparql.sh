#!/usr/bin/env bash
# Test queries against the QLever SPARQL endpoint.
# Usage: ./scripts/test_sparql.sh [endpoint]

set -euo pipefail

ENDPOINT="${1:-http://localhost:7001}"

query() {
  local description="$1" sparql="$2" format="${3:-tsv}"
  echo "--- $description ---"
  if [ "$format" = "tsv" ]; then
    response=$(curl -s -w "\n%{http_code}" "$ENDPOINT" \
      --data-urlencode "query=$sparql" \
      --data-urlencode "action=tsv_export")
  else
    response=$(curl -s -w "\n%{http_code}" "$ENDPOINT" \
      --data-urlencode "query=$sparql")
  fi
  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')
  if [ "$http_code" -ne 200 ]; then
    echo "FAIL (HTTP $http_code)"
    echo "$body" | head -5
    return 1
  fi
  echo "$body"
  echo
}

echo "Endpoint: $ENDPOINT"
echo

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

echo "All queries completed."
