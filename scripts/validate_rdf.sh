#!/usr/bin/env bash
# Validate that all expected RDF output files exist and are non-empty

set -e

RDF_DIR="${1:-data/rdf}"

expected="animal_models antibodies biobanks cell_lines development donor_tool donors files funders genetic_reagents investigators mutation_model mutations observations publications resources studies"

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

echo "All 17 RDF outputs validated"
