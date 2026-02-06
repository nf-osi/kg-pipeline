#!/usr/bin/env bash
# Test script for intermediate RML output (.rml.ttl)
# Tests RMLMapper output BEFORE IRI transformation
# Validates proper type assignment, field splitting, and empty value handling

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RMLMAPPER_JAR="$PROJECT_DIR/tools/rmlmapper-8.1.0.jar"
RML_FUNCTION_FILES="-f $PROJECT_DIR/tools/functions_grel.ttl -f $PROJECT_DIR/tools/grel_java_mapping.ttl"
OUTPUT_FILE="$SCRIPT_DIR/output_intermediate.ttl"
TEMP_MAPPING="$SCRIPT_DIR/temp_mapping.rml.ttl"

cd "$PROJECT_DIR"

echo "=== RML Intermediate Output Test Suite ==="
echo "Testing .rml.ttl generation for non-transformed entities"
echo

PASS=0
FAIL=0

# =============================================================================
# MUTATIONS
# =============================================================================

echo "=== Testing Portal Mutations Mapping ==="
sed 's|data/csv/portal_mutations.csv|test/portal_mutations.csv|g' \
    mappings/rml/portal_mutations.rml.ttl > "$TEMP_MAPPING"

java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

echo "=== Validation Tests (Mutations) ==="

echo -n "Test M1: Mutation has type nf:Mutation ... "
if grep -q 'a nf:Mutation' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test M2: AlleleType multi-value split (Somatic|Germline) ... "
if grep -A10 'test-mut-002' "$OUTPUT_FILE" | grep -q '"Somatic"' && \
   grep -A10 'test-mut-002' "$OUTPUT_FILE" | grep -q '"Germline"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test M3: MutationMethod multi-value split ... "
if grep -A10 'test-mut-002' "$OUTPUT_FILE" | grep -q '"Spontaneous"' && \
   grep -A10 'test-mut-002' "$OUTPUT_FILE" | grep -q '"ENU"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test M4: MutationType multi-value split ... "
if grep -A10 'test-mut-002' "$OUTPUT_FILE" | grep -q '"Nonsense"' && \
   grep -A10 'test-mut-002' "$OUTPUT_FILE" | grep -q '"Frameshift"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test M5: ExternalMutationID as IRI ... "
if grep -q 'nf:externalMutationID.*COSM123456' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test M6: Empty fields produce no triples ... "
mut3_has_clinvar=$(awk '
    /<http[^>]*test-mut-003>/ { in_mut=1; next }
    in_mut && /^<http/ { in_mut=0 }
    in_mut && /nf:humanClinVarMutation/ { found=1; exit }
    END { if (found) print "yes"; else print "no" }
' "$OUTPUT_FILE")
if [ "$mut3_has_clinvar" = "no" ]; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

# =============================================================================
# GENETIC REAGENTS
# =============================================================================

echo
echo "=== Testing Portal Genetic Reagents Mapping ==="
sed 's|data/csv/portal_genetic_reagents.csv|test/portal_genetic_reagents.csv|g' \
    mappings/rml/portal_genetic_reagents.rml.ttl > "$TEMP_MAPPING"

java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

echo "=== Validation Tests (Genetic Reagents) ==="

echo -n "Test R1: Reagent has type nf:GeneticReagent ... "
if grep -q 'a nf:GeneticReagent' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test R2: VectorType multi-value split (Plasmid|Viral) ... "
if grep -A20 'test-reagent-001' "$OUTPUT_FILE" | grep -q '"Plasmid"' && \
   grep -A20 'test-reagent-001' "$OUTPUT_FILE" | grep -q '"Viral"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test R3: InsertSpecies multi-value split ... "
if grep -A20 'test-reagent-001' "$OUTPUT_FILE" | grep -q '"Human"' && \
   grep -A20 'test-reagent-001' "$OUTPUT_FILE" | grep -q '"Mouse"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test R4: All tag fields present (nTerminalTag, cTerminalTag) ... "
if grep -A20 'test-reagent-001' "$OUTPUT_FILE" | grep -q 'nf:nTerminalTag "GFP"' && \
   grep -A20 'test-reagent-001' "$OUTPUT_FILE" | grep -q 'nf:cTerminalTag "FLAG"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test R5: Hazardous field present ... "
if grep -A15 'test-reagent-003' "$OUTPUT_FILE" | grep -q 'nf:hazardous "Yes"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test R6: Empty insertEntrezId produces no triple ... "
reagent3_has_entrez=$(awk '
    /<http[^>]*test-reagent-003>/ { in_reagent=1; next }
    in_reagent && /^<http/ { in_reagent=0 }
    in_reagent && /nf:insertEntrezId/ { found=1; exit }
    END { if (found) print "yes"; else print "no" }
' "$OUTPUT_FILE")
if [ "$reagent3_has_entrez" = "no" ]; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

# =============================================================================
# ANIMAL MODELS
# =============================================================================

echo
echo "=== Testing Portal Animal Models Mapping ==="
sed 's|data/csv/portal_animal_models.csv|test/portal_animal_models.csv|g' \
    mappings/rml/portal_animal_models.rml.ttl > "$TEMP_MAPPING"

java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

echo "=== Validation Tests (Animal Models) ==="

echo -n "Test A1: Animal model has type nf:AnimalModel ... "
if grep -q 'a nf:AnimalModel' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test A2: DonorId as IRI reference ... "
if grep -q 'nf:donorId.*test-donor-001' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test A3: TransplantationDonorId as IRI reference ... "
if grep -q 'nf:transplantationDonorId.*test-donor-003' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test A4: AnimalModelOfManifestation multi-value split ... "
if grep -A15 'test-animal-001' "$OUTPUT_FILE" | grep -q '"Plexiform Neurofibroma"' && \
   grep -A15 'test-animal-001' "$OUTPUT_FILE" | grep -q '"Optic Glioma"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test A5: AnimalModelGeneticDisorder single value ... "
if grep -A10 'test-animal-002' "$OUTPUT_FILE" | grep -q 'nf:animalModelGeneticDisorder "Neurofibromatosis type 2"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test A6: Strain fields present (backgroundStrain, strainNomenclature) ... "
if grep -A15 'test-animal-001' "$OUTPUT_FILE" | grep -q 'nf:backgroundStrain "C57BL/6J"' && \
   grep -A15 'test-animal-001' "$OUTPUT_FILE" | grep -q 'nf:strainNomenclature "B6.Nf1+/-"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test A7: Empty donorId produces no triple ... "
animal3_has_donor=$(awk '
    /<http[^>]*test-animal-003>/ { in_animal=1; next }
    in_animal && /^<http/ { in_animal=0 }
    in_animal && /nf:donorId/ { found=1; exit }
    END { if (found) print "yes"; else print "no" }
' "$OUTPUT_FILE")
if [ "$animal3_has_donor" = "no" ]; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

# =============================================================================
# CELL LINES
# =============================================================================

echo
echo "=== Testing Portal Cell Lines Mapping ==="
sed 's|data/csv/portal_cell_lines.csv|test/portal_cell_lines.csv|g' \
    mappings/rml/portal_cell_lines.rml.ttl > "$TEMP_MAPPING"

java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

echo "=== Validation Tests (Cell Lines) ==="

echo -n "Test C1: Cell line has type nf:CellLine ... "
if grep -q 'a nf:CellLine' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test C2: DonorId as IRI reference ... "
if grep -q 'nf:donorId.*test-donor-001' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test C3: CellLineManifestation multi-value split ... "
if grep -A15 'test-cell-001' "$OUTPUT_FILE" | grep -q '"Plexiform Neurofibroma"' && \
   grep -A15 'test-cell-001' "$OUTPUT_FILE" | grep -q '"Malignant Peripheral Nerve Sheath Tumor"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test C4: CellLineGeneticDisorder single value ... "
if grep -A10 'test-cell-001' "$OUTPUT_FILE" | grep -q 'nf:cellLineGeneticDisorder "Neurofibromatosis type 1"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test C5: Resistance field present ... "
if grep -A15 'test-cell-001' "$OUTPUT_FILE" | grep -q 'nf:resistance "Cisplatin"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test C6: Origin and profile fields ... "
if grep -A15 'test-cell-001' "$OUTPUT_FILE" | grep -q 'nf:originYear "2015"' && \
   grep -A15 'test-cell-001' "$OUTPUT_FILE" | grep -q 'nf:strProfile "STR-12345"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test C7: Empty donorId produces no triple ... "
cell3_has_donor=$(awk '
    /<http[^>]*test-cell-003>/ { in_cell=1; next }
    in_cell && /^<http/ { in_cell=0 }
    in_cell && /nf:donorId/ { found=1; exit }
    END { if (found) print "yes"; else print "no" }
' "$OUTPUT_FILE")
if [ "$cell3_has_donor" = "no" ]; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

# =============================================================================
# DONORS
# =============================================================================

echo
echo "=== Testing Portal Donors Mapping ==="
sed 's|data/csv/portal_donors.csv|test/portal_donors.csv|g' \
    mappings/rml/portal_donors.rml.ttl > "$TEMP_MAPPING"

java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

echo "=== Validation Tests (Donors) ==="

echo -n "Test D1: Donor has type nf:Donor ... "
if grep -q 'a nf:Donor' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test D2: Single species value ... "
if grep -q 'nf:species "Homo sapiens"' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test D3: Multi-valued species split ... "
if grep -A10 'test-donor-002' "$OUTPUT_FILE" | grep -q '"Homo sapiens"' && \
   grep -A10 'test-donor-002' "$OUTPUT_FILE" | grep -q '"Mus musculus"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test D4: ParentDonorId as IRI ... "
if grep -q 'nf:parentDonorId.*test-donor-001' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test D5: TransplantationDonorId as IRI ... "
if grep -q 'nf:transplantationDonorId.*test-donor-003' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test D6: Empty parentDonorId produces no triple ... "
donor1_has_parent=$(awk '
    /<http[^>]*test-donor-001>/ { in_donor=1; next }
    in_donor && /^<http/ { in_donor=0 }
    in_donor && /nf:parentDonorId/ { found=1; exit }
    END { if (found) print "yes"; else print "no" }
' "$OUTPUT_FILE")
if [ "$donor1_has_parent" = "no" ]; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test D7: Basic fields present (race, sex, age) ... "
if grep -A10 'test-donor-001' "$OUTPUT_FILE" | grep -q 'nf:race "White"' && \
   grep -A10 'test-donor-001' "$OUTPUT_FILE" | grep -q 'nf:sex "Male"' && \
   grep -A10 'test-donor-001' "$OUTPUT_FILE" | grep -q 'nf:age "25"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

# =============================================================================
# ANTIBODIES
# =============================================================================

echo
echo "=== Testing Portal Antibodies Mapping ==="
sed 's|data/csv/portal_antibodies.csv|test/portal_antibodies.csv|g' \
    mappings/rml/portal_antibodies.rml.ttl > "$TEMP_MAPPING"

java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

echo "=== Validation Tests (Antibodies) ==="

echo -n "Test AB1: Antibody has type nf:Antibody ... "
if grep -q 'a nf:Antibody' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test AB2: UniprotId as IRI ... "
if grep -q 'nf:uniprotId.*P12345' "$OUTPUT_FILE"; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test AB3: Multi-valued reactiveSpecies split ... "
if grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q '"Human"' && \
   grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q '"Mouse"' && \
   grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q '"Rat"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test AB4: Single reactiveSpecies value ... "
if grep -A10 'test-ab-002' "$OUTPUT_FILE" | grep -q 'nf:reactiveSpecies "Human"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test AB5: Basic fields present ... "
if grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q 'nf:hostOrganism "Rabbit"' && \
   grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q 'nf:conjugate "Nonconjugated"' && \
   grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q 'nf:clonality "Polyclonal"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test AB6: TargetAntigen present ... "
if grep -A15 'test-ab-001' "$OUTPUT_FILE" | grep -q 'nf:targetAntigen "NF1"'; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test AB7: Empty cloneId produces no triple ... "
ab2_has_clone=$(awk '
    /<http[^>]*test-ab-002>/ { in_ab=1; next }
    in_ab && /^<http/ { in_ab=0 }
    in_ab && /nf:cloneId/ { found=1; exit }
    END { if (found) print "yes"; else print "no" }
' "$OUTPUT_FILE")
if [ "$ab2_has_clone" = "no" ]; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

echo -n "Test AB8: Empty uniprotId produces no triple ... "
ab3_has_uniprot=$(awk '
    /<http[^>]*test-ab-003>/ { in_ab=1; next }
    in_ab && /^<http/ { in_ab=0 }
    in_ab && /nf:uniprotId/ { found=1; exit }
    END { if (found) print "yes"; else print "no" }
' "$OUTPUT_FILE")
if [ "$ab3_has_uniprot" = "no" ]; then
    echo "PASS"; PASS=$((PASS + 1))
else
    echo "FAIL"; FAIL=$((FAIL + 1))
fi

# =============================================================================
# SUMMARY
# =============================================================================

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
    echo "All intermediate RML tests passed!"
    exit 0
fi
