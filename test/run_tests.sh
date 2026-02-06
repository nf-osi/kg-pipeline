#!/usr/bin/env bash
# Test script for RML mappings
# Uses actual mappings from mappings/rml/ with test CSV inputs

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RMLMAPPER_JAR="$PROJECT_DIR/tools/rmlmapper-8.1.0.jar"
RML_FUNCTION_FILES="-f $PROJECT_DIR/tools/functions_grel.ttl -f $PROJECT_DIR/tools/grel_java_mapping.ttl"
OUTPUT_FILE="$SCRIPT_DIR/output.ttl"
TEMP_MAPPING="$SCRIPT_DIR/temp_mapping.rml.ttl"

cd "$PROJECT_DIR"

echo "=== RML Mapping Test Suite ==="
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

echo
echo "=== Testing Portal Donors Mapping ==="

# Create temporary mapping for donors
echo "Creating temporary mapping for donors..."
sed 's|data/csv/portal_donors.csv|test/portal_donors.csv|g' \
    mappings/rml/portal_donors.rml.ttl > "$TEMP_MAPPING"

# Run RMLMapper
echo "Running RMLMapper for donors..."
java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

echo
echo "=== Generated RDF Output (Donors) ==="
cat "$OUTPUT_FILE"
echo

# Validation tests for donors
echo "=== Running Validation Tests (Donors) ==="

# Test D1: Donor exists with correct type
echo -n "Test D1: donor 'test-donor-001' has type nf:Donor ... "
if grep -q '<http://nf-osi.github.com/terms#donor/test-donor-001>' "$OUTPUT_FILE" && grep -q 'a nf:Donor' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected donor IRI and type nf:Donor"
fi

# Test D2: Single species value
echo -n "Test D2: species 'Homo sapiens' -> nf:species 'Homo sapiens' ... "
if grep -q 'nf:species "Homo sapiens"' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected nf:species \"Homo sapiens\""
fi

# Test D3: Multi-valued species split
echo -n "Test D3: species 'Homo sapiens|Mus musculus' -> two values ... "
if grep -A10 'test-donor-002' "$OUTPUT_FILE" | grep -q '"Homo sapiens"' && grep -A10 'test-donor-002' "$OUTPUT_FILE" | grep -q '"Mus musculus"'; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected both \"Homo sapiens\" and \"Mus musculus\" for test-donor-002"
fi

# Test D4: Parent donor as IRI
echo -n "Test D4: parentDonorId 'test-donor-001' is an IRI reference ... "
if grep -q 'nf:parentDonorId.*test-donor-001' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected nf:parentDonorId as IRI"
fi

# Test D5: Transplantation donor as IRI
echo -n "Test D5: transplantationDonorId 'test-donor-003' is an IRI reference ... "
if grep -q 'nf:transplantationDonorId.*test-donor-003' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected nf:transplantationDonorId as IRI"
fi

# Test D6: Empty fields should not produce triples
echo -n "Test D6: Empty parentDonorId for test-donor-001 produces no parentDonorId triple ... "
# Check that test-donor-001's subject IRI doesn't have parentDonorId predicate in its block
# Look for the line with test-donor-001 as subject and check following lines until next subject
donor_has_parent=$(awk '
    /<http[^>]*test-donor-001>/ { in_donor=1; next }
    in_donor && /^<http/ { in_donor=0 }
    in_donor && /nf:parentDonorId/ { found=1; exit }
    END { if (found) print "yes"; else print "no" }
' "$OUTPUT_FILE")

if [ "$donor_has_parent" = "yes" ]; then
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected no parentDonorId triple for test-donor-001"
else
    echo "PASS"
    PASS=$((PASS + 1))
fi

# Test D7: All basic string fields present
echo -n "Test D7: Basic fields (race, sex, age) present for test-donor-001 ... "
if grep -A10 'test-donor-001' "$OUTPUT_FILE" | grep -q 'nf:race "White"' && \
   grep -A10 'test-donor-001' "$OUTPUT_FILE" | grep -q 'nf:sex "Male"' && \
   grep -A10 'test-donor-001' "$OUTPUT_FILE" | grep -q 'nf:age "25"'; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected race, sex, and age fields"
fi

echo
echo "=== Testing Portal Antibodies Mapping ==="

# Create temporary mapping for antibodies
echo "Creating temporary mapping for antibodies..."
sed 's|data/csv/portal_antibodies.csv|test/portal_antibodies.csv|g' \
    mappings/rml/portal_antibodies.rml.ttl > "$TEMP_MAPPING"

# Run RMLMapper
echo "Running RMLMapper for antibodies..."
java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

echo
echo "=== Generated RDF Output (Antibodies) ==="
cat "$OUTPUT_FILE"
echo

# Validation tests for antibodies
echo "=== Running Validation Tests (Antibodies) ==="

# Test A1: Antibody exists with correct type
echo -n "Test A1: antibody 'test-ab-001' has type nf:Antibody ... "
if grep -q '<http://nf-osi.github.com/terms#antibody/test-ab-001>' "$OUTPUT_FILE" && grep -q 'a nf:Antibody' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected antibody IRI and type nf:Antibody"
fi

# Test A2: UniProt ID as IRI
echo -n "Test A2: uniprotId 'P12345' is an IRI ... "
if grep -q 'nf:uniprotId.*P12345' "$OUTPUT_FILE"; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected nf:uniprotId as IRI"
fi

# Test A3: Multi-valued reactiveSpecies split
echo -n "Test A3: reactiveSpecies 'Human|Mouse|Rat' -> three values ... "
if grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q '"Human"' && \
   grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q '"Mouse"' && \
   grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q '"Rat"'; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected \"Human\", \"Mouse\", and \"Rat\" for test-ab-001"
fi

# Test A4: Single reactiveSpecies value
echo -n "Test A4: Single reactiveSpecies 'Human' for test-ab-002 ... "
if grep -A10 'test-ab-002' "$OUTPUT_FILE" | grep -q 'nf:reactiveSpecies "Human"'; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected nf:reactiveSpecies \"Human\""
fi

# Test A5: Basic string fields
echo -n "Test A5: Basic fields (hostOrganism, conjugate, clonality) for test-ab-001 ... "
if grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q 'nf:hostOrganism "Rabbit"' && \
   grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q 'nf:conjugate "Nonconjugated"' && \
   grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q 'nf:clonality "Polyclonal"'; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected hostOrganism, conjugate, and clonality fields"
fi

# Test A6: Target antigen field
echo -n "Test A6: targetAntigen 'NF1' present for test-ab-001 ... "
if grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q 'nf:targetAntigen "NF1"'; then
    echo "PASS"
    PASS=$((PASS + 1))
else
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected nf:targetAntigen \"NF1\""
fi

# Test A7: Empty cloneId should not produce triple
echo -n "Test A7: Empty cloneId for test-ab-002 produces no cloneId triple ... "
if grep -A10 'test-ab-002' "$OUTPUT_FILE" | grep -q 'nf:cloneId'; then
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected no cloneId triple for test-ab-002"
else
    echo "PASS"
    PASS=$((PASS + 1))
fi

# Test A8: Empty uniprotId should not produce triple
echo -n "Test A8: Empty uniprotId for test-ab-003 produces no uniprotId triple ... "
if grep -A10 'test-ab-003' "$OUTPUT_FILE" | grep -q 'nf:uniprotId'; then
    echo "FAIL"
    FAIL=$((FAIL + 1))
    echo "  Expected no uniprotId triple for test-ab-003"
else
    echo "PASS"
    PASS=$((PASS + 1))
fi

# Summary
echo
echo "=== Test Summary ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"

# Cleanup
rm -f "$TEMP_MAPPING"

if [ $FAIL -gt 0 ]; then
    echo
    echo "Some tests failed. Output preserved at: $OUTPUT_FILE"
    exit 1
else
    rm -f "$OUTPUT_FILE"
    echo "All tests passed!"
    exit 0
fi
