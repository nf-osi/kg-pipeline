#!/usr/bin/env bash
# Test script for IRI transformation
# Tests Studies and Files (entities with SPARQL IRI transformation after RML)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RMLMAPPER_JAR="$PROJECT_DIR/tools/rmlmapper-8.1.0.jar"
RML_FUNCTION_FILES="-f $PROJECT_DIR/tools/functions_grel.ttl -f $PROJECT_DIR/tools/grel_java_mapping.ttl"
OUTPUT_FILE="$SCRIPT_DIR/output.ttl"
TEMP_MAPPING="$SCRIPT_DIR/temp_mapping.rml.ttl"

cd "$PROJECT_DIR"

echo "=== IRI Transformation Test Suite ==="
echo

# Create temporary mapping that points to test CSV
echo "Creating temporary mapping pointing to test CSV..."
sed 's|data/csv/portal_studies.csv|test/portal_studies.csv|g' \
    mappings/rml/portal_studies.rml.ttl > "$TEMP_MAPPING"

# Run RMLMapper
echo "Running RMLMapper..."
java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

echo
echo "=== Generated RDF Output ==="
cat "$OUTPUT_FILE"
echo

# Validation tests
echo "=== Running Validation Tests ==="
PASS=0
FAIL=0

# Test 1: initiative with spaces should become IRI with underscores
echo -n "Test 1: initiative 'Cutaneous Neurofibroma Initiative' -> nf:Cutaneous_Neurofibroma_Initiative ... "
if grep -q "nf:Cutaneous_Neurofibroma_Initiative" "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected: nf:Cutaneous_Neurofibroma_Initiative"
    echo "  Checking for URL-encoded version..."
    grep -o "nf:Cutaneous[^>]*" "$OUTPUT_FILE" || echo "  Not found"
fi

# Test 2: initiative without spaces
echo -n "Test 2: initiative 'Synodos' -> nf:Synodos ... "
if grep -q "nf:Synodos" "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
fi

# Test 3: fundingAgency with spaces should become IRI with underscores
echo -n "Test 3: fundingAgency 'CTF Foundation' -> nf:CTF_Foundation ... "
if grep -q "nf:CTF_Foundation" "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Checking for URL-encoded version..."
    grep -o "nf:CTF[^>]*" "$OUTPUT_FILE" || echo "  Not found"
fi

# Test 4: fundingAgency without spaces
echo -n "Test 4: fundingAgency 'NTAP' -> nf:NTAP ... "
if grep -q "nf:NTAP" "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
fi

# Test 5: fundingAgency 'Gilbert Family Foundation'
echo -n "Test 5: fundingAgency 'Gilbert Family Foundation' -> nf:Gilbert_Family_Foundation ... "
if grep -q "nf:Gilbert_Family_Foundation" "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Checking actual output..."
    grep -o "nf:Gilbert[^>]*" "$OUTPUT_FILE" || echo "  Not found"
fi

# Test 6: Check no %20 remains in IRIs
echo -n "Test 6: No URL-encoded spaces (%20) in IRIs ... "
if grep -q "%20" "$OUTPUT_FILE"; then
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Found %20 in output:"
    grep "%20" "$OUTPUT_FILE"
else
    echo "PASS"
    PASS=$((PASS + 1))
fi

# Test 7: Study with empty studyLeads should not produce studyLeads triple
echo -n "Test 7: Empty studyLeads for syn0000004 produces no studyLeads triple ... "
if grep -q '<syn:syn0000004>' "$OUTPUT_FILE" && ! grep -q '<syn:syn0000004>.*nf:studyLeads' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected no studyLeads triple for syn0000004"
fi

echo
echo "=== Testing Portal Files Mapping ==="

# Create temporary mapping for files
echo "Creating temporary mapping for files..."
sed 's|data/csv/portal_files.csv|test/portal_files.csv|g' \
    mappings/rml/portal_files.rml.ttl > "$TEMP_MAPPING"

# Run RMLMapper
echo "Running RMLMapper for files..."
java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

echo
echo "=== Generated RDF Output (Files) ==="
cat "$OUTPUT_FILE"
echo

# Validation tests for files
echo "=== Running Validation Tests (Files) ==="

# Test F1: File name
echo -n "Test F1: name 'Test File One' -> nf:name 'Test File One' ... "
if grep -q 'nf:name "Test File One"' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected: nf:name \"Test File One\""
fi

# Test F2: Diagnosis list split
echo -n "Test F2: diagnosis 'NF1|Schwannomatosis' -> nf:diagnosis values ... "
if grep -q '"NF1"' "$OUTPUT_FILE" && grep -q '"Schwannomatosis"' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected \"NF1\" and \"Schwannomatosis\""
fi

# Test F3: SpecimenID list split
echo -n "Test F3: specimenID 'Spec1|Spec2' -> nf:specimenID values ... "
if grep -q '"Spec1"' "$OUTPUT_FILE" && grep -q '"Spec2"' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected \"Spec1\" and \"Spec2\""
fi

# Test F4: Funding Agency as IRI
echo -n "Test F4: fundingAgency 'NTAP' -> nf:fundingAgency nf:NTAP ... "
if grep -q 'nf:fundingAgency nf:NTAP' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected nf:fundingAgency nf:NTAP"
fi

# Test F5: Report Milestone number
echo -n "Test F5: reportMilestone 1.0 -> nf:reportMilestone 1.0 ... "
if grep -q 'nf:reportMilestone 1.0' "$OUTPUT_FILE" || grep -q 'nf:reportMilestone "1.0"' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected nf:reportMilestone 1.0 or \"1.0\""
fi

# Test F6: Empty diagnosis field should not produce diagnosis triples for File Two
echo -n "Test F6: Empty diagnosis field for syn9999992 produces no diagnosis triple ... "
if grep -q '<syn:syn9999992>' "$OUTPUT_FILE" && ! grep -q '<syn:syn9999992>.*nf:diagnosis' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected no diagnosis triple for syn9999992"
fi

# Test F7: Multiple specimenID values split correctly for File Three
echo -n "Test F7: specimenID 'Spec3|Spec4|Spec5' -> three values ... "
if grep -q '"Spec3"' "$OUTPUT_FILE" && grep -q '"Spec4"' "$OUTPUT_FILE" && grep -q '"Spec5"' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected \"Spec3\", \"Spec4\", and \"Spec5\""
fi

# Test F8: Single diagnosis value for File Three
echo -n "Test F8: Single diagnosis 'NF2' -> nf:diagnosis 'NF2' ... "
# Check that syn9999993 exists and has diagnosis NF2
if grep -q '<syn:syn9999993>' "$OUTPUT_FILE" && grep -A20 '<syn:syn9999993>' "$OUTPUT_FILE" | grep -q 'nf:diagnosis.*"NF2"'; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected nf:diagnosis \"NF2\" for syn9999993"
fi

# Test F9: FundingAgency with spaces converted to IRI with underscores
echo -n "Test F9: fundingAgency 'CTF Foundation' -> nf:fundingAgency nf:CTF_Foundation ... "
if grep -q 'nf:fundingAgency nf:CTF_Foundation' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected nf:fundingAgency nf:CTF_Foundation"
fi
