#!/usr/bin/env bash
# Validate that expected QLever text index files exist and are non-empty

set -e

TEXT_DIR="${1:-pubs/qlever_text}"

expected="wordsfile.tsv docsfile.tsv text_entities.ttl"

fail=0
for name in $expected; do
  f="${TEXT_DIR}/${name}"
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
  echo "::error::$fail QLever text index files failed validation"
  exit 1
fi

echo "All 3 QLever text index files validated"
