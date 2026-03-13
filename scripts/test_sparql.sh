#!/usr/bin/env bash
# Test graph queries against the QLever endpoint.
# Starts qlever-server, runs queries, then stops the service.
#
# Usage:
#   ./scripts/test_sparql.sh          # manage server lifecycle automatically
#   ./scripts/test_sparql.sh <url>    # run against an already-running endpoint

SERVER_SERVICE="qlever-server"
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

echo "All queries completed."
