# Shared helpers for QLever test scripts. Source this, don't execute it.
#
# Expected variables (set before sourcing):
#   SERVER_SERVICE  — docker compose service name
#
# Provides:
#   ENDPOINT, query(), server lifecycle (start/wait/stop via trap)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

MANAGED=false
if [ -n "${1:-}" ]; then
  ENDPOINT="$1"
else
  ENDPOINT="http://localhost:7001"
  MANAGED=true
fi

cleanup() {
  if $MANAGED; then
    echo
    echo "Stopping $SERVER_SERVICE ..."
    docker compose -f "$PROJECT_DIR/docker-compose.yml" down "$SERVER_SERVICE" 2>/dev/null
  fi
}

wait_for_server() {
  local max_attempts=30
  local attempt=0
  echo "Waiting for $ENDPOINT ..."
  while ! curl -sf "$ENDPOINT" --data-urlencode "query=ASK { ?s ?p ?o }" > /dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "FAIL: server did not become ready after ${max_attempts}s"
      exit 1
    fi
    sleep 1
  done
  echo "Server ready."
  echo
}

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

if $MANAGED; then
  trap cleanup EXIT
  echo "Starting $SERVER_SERVICE ..."
  docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d "$SERVER_SERVICE"
  wait_for_server
fi

echo "Endpoint: $ENDPOINT"
echo
