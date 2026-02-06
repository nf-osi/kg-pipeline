# RML Mapping Tests

This directory contains tests for validating RML mappings that transform CSV data into RDF triples.

## Test Structure

Tests are organized into two suites:

1. **IRI Transformation Tests** (`test_iri_transform.sh`) - Studies & Files with SPARQL IRI transformation
2. **Intermediate RML Tests** (`test_rml_intermediate.sh`) - All other entities (Mutations, Reagents, Animals, Cells, Donors, Antibodies)

### Test Scripts

- **`run_tests.sh`** - Master runner (executes both suites)
- **`test_iri_transform.sh`** - IRI transformation tests
- **`test_rml_intermediate.sh`** - Intermediate RML tests

## Running Tests

```bash
# Run all tests
bash test/run_tests.sh

# Run specific suite
bash test/test_iri_transform.sh
bash test/test_rml_intermediate.sh
```

## Test Coverage

### Portal Studies (7 tests)
- ✅ Initiative field with spaces → IRI with underscores
- ✅ Initiative without spaces → direct IRI
- ✅ FundingAgency with spaces → IRI with underscores
- ✅ FundingAgency without spaces → direct IRI
- ✅ No URL-encoded spaces (%20) in IRIs
- ✅ Empty studyLeads field produces no triple

### Portal Files (9 tests)
- ✅ File name as literal string
- ✅ Diagnosis list split correctly (pipe-delimited)
- ✅ SpecimenID list split correctly
- ✅ FundingAgency as IRI
- ✅ ReportMilestone as number
- ✅ Empty diagnosis produces no triple
- ✅ Multiple specimenID values split
- ✅ Single diagnosis value handled
- ✅ FundingAgency with spaces → IRI with underscores

### Portal Donors (7 tests)
- ✅ Donor has correct type (nf:Donor)
- ✅ Single species value as literal
- ✅ Multi-valued species split correctly (pipe-delimited)
- ✅ ParentDonorId as IRI reference
- ✅ TransplantationDonorId as IRI reference
- ✅ Empty parentDonorId produces no triple
- ✅ Basic fields (race, sex, age) present

### Portal Antibodies (8 tests)
- ✅ Antibody has correct type (nf:Antibody)
- ✅ UniprotId as IRI
- ✅ Multi-valued reactiveSpecies split correctly (pipe-delimited)
- ✅ Single reactiveSpecies value
- ✅ Basic fields (hostOrganism, conjugate, clonality)
- ✅ TargetAntigen field present
- ✅ Empty cloneId produces no triple
- ✅ Empty uniprotId produces no triple

## Test Data Format

Each test CSV includes edge cases:
- Empty/missing values
- Single values
- Multi-valued pipe-delimited fields (`value1|value2|value3`)
- IRI fields
- String fields with spaces

## What Tests Validate

1. **Type declarations**: Each entity has correct `rdf:type`
2. **Field datatypes**: Strings as literals, IDs as IRIs
3. **Multi-valued fields**: Pipe-delimited values split into multiple triples
4. **Empty values**: No triples generated for missing/empty fields
5. **IRI formatting**: Spaces converted to underscores, no URL encoding
6. **Required fields**: Core identifiers always present

## Adding New Table Tests

1. **Create test CSV**: `test/portal_{table}.csv`
   - Include 3-4 test records
   - Cover edge cases (empty, single, multiple values)

2. **Add test section** to `run_tests.sh`:
   ```bash
   echo
   echo "=== Testing Portal {Table} Mapping ==="

   # Create temporary mapping
   sed 's|data/csv/portal_{table}.csv|test/portal_{table}.csv|g' \
       mappings/rml/portal_{table}.rml.ttl > "$TEMP_MAPPING"

   # Run RMLMapper
   java -jar "$RMLMAPPER_JAR" $RML_FUNCTION_FILES \
       -m "$TEMP_MAPPING" -s turtle -o "$OUTPUT_FILE"

   # Show output
   echo "=== Generated RDF Output ({Table}) ==="
   cat "$OUTPUT_FILE"

   # Add validation tests...
   ```

3. **Add validation tests**:
   - Check entity type
   - Validate multi-valued field splitting
   - Verify IRI vs literal handling
   - Confirm empty fields don't generate triples

## Test Output

Success:
```
=== Test Summary ===
Passed: 31
Failed: 0
All tests passed!
```

Failure:
```
=== Test Summary ===
Passed: 30
Failed: 1

Some tests failed. Output preserved at: test/output.ttl
```

Inspect `test/output.ttl` to debug failures.

## CI/CD Integration

Add to your CI pipeline:
```yaml
- name: Run RML tests
  run: bash test/run_tests.sh
```

## Notes

- Tests run **before** IRI transformation (testing `.rml.ttl` output)
- Tests use temporary modified mappings pointing to test CSVs
- RMLMapper JAR must be present at `tools/rmlmapper-8.1.0.jar`
- Function files must be at `tools/functions_grel.ttl` and `tools/grel_java_mapping.ttl`
