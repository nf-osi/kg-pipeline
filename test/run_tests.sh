#!/usr/bin/env bash
# Master test runner - executes all RML test suites
# Usage: bash run_tests.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "   NF Knowledge Graph - Test Suite       "
echo "=========================================="
echo

EXIT_CODE=0

# Run IRI transformation tests (Studies & Files)
echo ">>> Running IRI Transformation Tests (Studies & Files)..."
echo
if bash test_iri_transform.sh; then
    echo
    echo "✓ IRI transformation tests passed"
else
    echo
    echo "✗ IRI transformation tests failed"
    EXIT_CODE=1
fi

echo
echo "=========================================="
echo

# Run intermediate RML tests (all other entities)
echo ">>> Running Intermediate RML Tests (Mutations, Reagents, Animals, Cells, Donors, Antibodies)..."
echo
if bash test_rml_intermediate.sh; then
    echo
    echo "✓ Intermediate RML tests passed"
else
    echo
    echo "✗ Intermediate RML tests failed"
    EXIT_CODE=1
fi

echo
echo "=========================================="
echo "           FINAL SUMMARY                  "
echo "=========================================="

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ All test suites passed!"
else
    echo "❌ Some test suites failed"
fi

exit $EXIT_CODE
