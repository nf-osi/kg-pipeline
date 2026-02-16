# RML Mapping Tests

Pytest-based test suite for validating RML mappings that transform CSV data into RDF triples.

## Quick Start

```bash
# Install and run
pip install -r test/requirements-test.txt
pytest  # Runs 165 tests in ~23 seconds (parallel by default)

# Common usage
pytest test/test_rml_mutations.py                    # Specific module
pytest test/test_rml_mutations.py::TestMutationsCore # Specific class
pytest -k "multi_value"                               # Pattern matching
pytest --cov=scripts --cov-report=html                # With coverage
pytest -n 0                                           # Sequential (debugging)
```

## Test Coverage

**165 tests** covering all RML mappings:

- ✅ **Entity types**: Mutations, Genetic Reagents, Animal Models, Cell Lines, Donors, Antibodies, Resources, Studies, Files, Observations
- ✅ **Development entities**: Funders, Investigators, Publications
- ✅ **Relationships**: Mutation→Resource, Donor→Resource, Resource→Tool-specific IDs (owl:sameAs), Development→Funder/Investigator/Publication
- ✅ **Multi-value fields**: Pipe-delimited list splitting
- ✅ **IRI vs literals**: Proper type assignment
- ✅ **Empty fields**: No triples for missing/empty values
- ✅ **IRI transformation**: Spaces→underscores, no URL encoding
- ✅ **SPARQL validation**: Native RDF queries

### Performance

Tests run in parallel by default (via pytest.ini). Each test is isolated and independent.

| Mode | Time | Speedup |
|------|------|---------|
| Sequential (`-n 0`) | ~140s (2:20) | 1x |
| **Parallel** (default) | **~21s** | **6.5x faster** |

**Bottleneck**: RMLMapper (Java) execution takes ~1s per test (94% of time). RDFLib parsing and SPARQL are very fast (<7% combined).

## Test Structure

### Organization

```
test/
├── conftest.py                 # Shared fixtures (rml_runner)
├── test_rml_mutations.py       # Mutations mapping (10 tests)
├── test_rml_genetic_reagents.py # Genetic reagents (10 tests)
├── test_rml_animal_models.py   # Animal models (11 tests)
├── test_rml_cell_lines.py      # Cell lines (11 tests)
├── test_rml_donors.py          # Donors (13 tests)
├── test_rml_antibodies.py      # Antibodies (14 tests)
├── test_rml_relationships.py   # Mutation/donor relationships (13 tests)
├── test_rml_resources.py       # Resources + owl:sameAs (15 tests)
├── test_rml_studies.py         # Studies + IRI transform (14 tests)
├── test_rml_files.py           # Files + IRI transform (15 tests)
├── test_rml_development.py     # Development tables (22 tests)
├── test_rml_observations.py    # Observations (17 tests)
└── *.csv                       # Test data (3-5 rows each)
```

### Test Categories

Each test module includes:
- **Core tests**: Entity types, IDs, basic properties
- **Multi-value tests**: Pipe-delimited field splitting
- **IRI tests**: URI vs literal validation
- **Empty field tests**: No triples for empty values
- **Data quality tests**: Consistency checks

## Writing New Tests

### Example Test

```python
def test_entity_has_correct_type(self, entity_graph, namespaces):
    """All entities should have correct type"""
    NF = namespaces["nf"]

    query = """
    SELECT ?entity
    WHERE {
        ?entity a nf:Entity .
    }
    """
    results = list(entity_graph.query(query, initNs={"nf": NF}))
    assert len(results) > 0, "No entities found"
```

### Using Fixtures

```python
@pytest.fixture
def my_graph(rml_runner, namespaces):
    """Load specific graph for tests"""
    return rml_runner(
        mapping_file="portal_entity.rml.ttl",
        csv_replacements={"data/csv/entity.csv": "test/entity.csv"}
    )

def test_something(my_graph, namespaces):
    """Test uses the fixture"""
    # Query the graph with SPARQL
    query = "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10"
    results = my_graph.query(query)
    # Make assertions
```

### Available Fixtures (conftest.py)

- `rml_runner(mapping_file, csv_replacements)` - Run RMLMapper and return RDF graph
- `namespaces` - Dict of RDF namespaces (nf, syn, owl, etc.)
- `project_paths` - Dict of important paths

### Development Workflow

```bash
# Run just what you're working on
pytest test/test_rml_mutations.py          # One module
pytest test/test_rml_mutations.py::TestMutationsCore  # One class
pytest -k "multi_value"                    # Tests matching pattern

# Rerun only failures
pytest --lf

# Stop on first failure
pytest -x

# Debug mode (sequential, no capture)
pytest test/test_rml_mutations.py -s --pdb -n 0
```

### Disabling Parallel Execution

Parallel is enabled by default in `pytest.ini`. Disable with `-n 0` when:
- Debugging with `--pdb`
- Need reproducible timing per test
- Troubleshooting test isolation issues

## Troubleshooting

### Common Issues

**Import errors**
```bash
# Install test dependencies
pip install -r test/requirements-test.txt
```

**RMLMapper not found**
```bash
# Check RMLMapper JAR exists
ls tools/rmlmapper-8.1.0.jar
```
