#!/usr/bin/env bash
# Validate that all expected RDF output files exist and are non-empty

set -e

RDF_DIR="${1:-data/rdf}"

# Derived from scripts/prepare_portal_tables.py's TABLES dict (the single
# source of truth for portal tables) rather than hardcoded, so this check
# can't drift out of sync when a new table is added.
expected="$(python3 -c '
import sys
sys.path.insert(0, ".")
from scripts.prepare_portal_tables import TABLES
print(" ".join(sorted(TABLES.keys())))
')"

fail=0
for name in $expected; do
  f="${RDF_DIR}/${name}.ttl"
  if [ ! -e "$f" ]; then
    echo "::error::Missing: $f"
    fail=$((fail + 1))
  elif [ ! -s "$f" ]; then
    echo "::error::Empty: $f"
    fail=$((fail + 1))
  else
    echo "  ok: $f ($(wc -c < "$f") bytes)"
  fi
done

if [ "$fail" -gt 0 ]; then
  echo "::error::$fail RDF files failed validation"
  exit 1
fi

echo "All $(echo "$expected" | wc -w) RDF outputs validated"

# Check for malformed placeholder-base IRIs. These appear when an RML
# FunctionTermMap object is declared rr:termType rr:IRI without an
# rr:template prefix: RMLMapper resolves the non-absolute value against its
# default base IRI (http://example.com or http://example.org), concatenating
# it directly with no separator (e.g. http://example.comsyn12345). See the
# nf:relatedStudies / nf:grantDOI fix in mappings/rml/studies.rml.ttl for a
# worked example and fix pattern.
echo ""
echo "Checking for malformed placeholder-base IRIs..."
bad=0
for f in "${RDF_DIR}"/*.ttl; do
  [ -e "$f" ] || continue
  count=$(grep -c "example\.com\|example\.org" "$f" || true)
  if [ "${count:-0}" -gt 0 ]; then
    echo "::error::$f has $count triples with a malformed example.com/example.org IRI"
    grep -o "example\.\(com\|org\)[^ ;,>]*" "$f" | sort -u | head -5 | sed 's/^/::error::  e.g. /'
    fail=$((fail + 1))
    bad=1
  fi
done

if [ "$bad" -gt 0 ]; then
  echo "::error::RDF build contains malformed placeholder IRIs — check RML mappings for FunctionTermMap object maps missing an rr:template"
  exit 1
fi

echo "No malformed placeholder IRIs found"

# Check for schema drift: rdf:type values not declared as owl:Class in
# schema/ontology.ttl (e.g. a typo'd class IRI, or a new value introduced in
# an RML mapping / SSSOM lookup without a matching ontology update).
echo ""
python3 scripts/validate_schema_drift.py --rdf-dir "${RDF_DIR}"
