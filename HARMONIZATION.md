# Harmonization and Data Transform Notes

This document describes the data transformations applied between the raw Synapse
export and the final RDF, and documents known upstream data quality issues.

## Pipeline stages

```
Synapse tables
  --> [prepare_portal_tables.py] --> data/csv/*.csv          (raw export + formatting)
  --> [harmonization scripts]    --> data/csv/*_harmonized.csv (classification + ID minting)
  --> [RMLMapper + rml/*.rml.ttl]--> data/rdf/*.ttl           (RDF triples)
```

### 1. prepare_portal_tables.py

Downloads each Synapse table and writes a processed CSV:
- Flattens Synapse `STRING_LIST` columns to pipe-delimited strings.
- Coerces numeric columns (e.g. `progressReportNumber`).
- Converts empty strings to null so RMLMapper skips them.

### 2. Harmonization scripts

Each script reads one processed CSV, applies SSSOM lookups or other
enrichments, and writes a `*_harmonized.csv` consumed by RML:

| Script | Input | What it does |
|--------|-------|-------------|
| `classify_datatypes.py` | `studies.csv` | Maps `dataType` labels to ontology IRIs via `data_lookup.sssom.tsv` |
| `classify_observations.py` | `observations.csv` | Maps `observationType` to observation subclass IRIs; **mints UUID `observationId`** for rows that lack one (~89% of rows, all AI-extracted) |
| `classify_cell_lines.py` | `cell_lines.csv` | Maps `cellLineCategory` to CellLine subclass IRIs |
| `classify_mutations.py` | `mutations.csv` | Maps `mutationType` to mutation class IRIs |
| `classify_genetic_reagents.py` | `genetic_reagents.csv` | Maps `vectorType` to reagent class IRIs |
| `harmonize_files.py` | `files.csv` + `resources.csv` | Resolves `modelSystemName` to resource IRIs; maps `dataType`, `nf1Genotype`, `nf2Genotype` labels to class IRIs |

### 3. RML mapping

RML Turtle files under `mappings/rml/` define CSV-to-RDF transformations.
Multi-value pipe-delimited fields are split using `grel:string_split`.

## FK validation

Foreign key relationships between tables are declared inline in the `TABLES`
dict in `prepare_portal_tables.py` (a `references` key on each FK column) and
checked by `scripts/validate_fks.py`. 22 FK constraints are tracked across 9
tables. Validation is non-blocking — it reports orphaned FK values but does not
stop the pipeline.

### Running

```bash
# Standalone — check all FK constraints across processed CSVs
python scripts/validate_fks.py

# Custom data directory
python scripts/validate_fks.py --data-dir data/csv

# Machine-readable JSON output
python scripts/validate_fks.py --json

# Fail with exit code 1 on any violation (for CI)
python scripts/validate_fks.py --strict

# Integrated — run validation after downloading/processing tables
python scripts/prepare_portal_tables.py --from-cache --validate
```

### Reading the output

```
FK validation: 22 constraints across 9 tables

FAIL  mutation_model.cellLineId -> cell_lines.cellLineId
      76 / 263 populated rows orphaned (28.9%), 50 unique values
      sample: 0360411b-..., 09c988ab-...

 ok   development.resourceId -> resources.resourceId
 ...

Summary: 5 failures, 17 passed
```

Each line shows a FK constraint. `FAIL` means some populated FK values were not
found in the referenced table's primary key column. The report shows:
- **populated rows**: rows where the FK column is non-empty
- **orphaned**: populated rows whose value is missing from the target PK set
- **unique values**: distinct orphaned values (helps gauge whether it's a
  systemic issue or a few bad rows)
- **sample**: up to 5 example orphaned values for investigation

Use `--json` for machine-readable output with the same fields, suitable for
dashboards or CI checks.

### Dagster

The `fk_validation` asset (under `portal > quality`) depends on all `*_csv`
assets and runs automatically after CSV extraction. Results are logged via
`context.log` and attached as asset metadata (`total_constraints`, `failures`,
`passed`). The asset never raises, so downstream RDF generation is not blocked.

### Extending

To add a new FK constraint, add a `references` key to the column definition in
the `TABLES` dict:

```python
{"target": "cellLineId", "type": "iri", "references": {"table": "cell_lines", "column": "cellLineId"}}
```

The validator discovers constraints automatically — no changes to
`validate_fks.py` are needed.

## Known upstream data quality issues

### observationId missing for AI-extracted rows

~89% of observations (all with `observationSubmitterName = "AI-extracted - IN BETA"`)
arrive from Synapse with no `observationId`. The `classify_observations.py`
script mints a stable UUID-4 for each such row during harmonization. These
minted IDs are **not** written back to Synapse, so they are regenerated on each
pipeline run (not stable across runs).

### resourceId / entity ID confusion (mutation_model, donors)

Two tables have foreign key columns populated with `resourceId` values from
`resources.csv` instead of the expected entity-specific IDs:

- **mutation_model.cellLineId**: 77 of 268 rows (29%) contain a `resourceId`
  instead of a `cellLineId`. The `resources` table is a polymorphic wrapper
  with its own primary key (`resourceId`) and a separate `cellLineId` FK.
  Upstream data entry confused the two. The affected rows produce broken
  `nf:cellLine/{resourceId}` IRIs in the RDF graph.

- **donors.parentDonorId**: 6 of 7 orphaned `parentDonorId` values are
  actually `resourceId` UUIDs for cell line resources, not donor UUIDs.
  1 additional value is completely dangling (not found anywhere).

Both issues originate in the upstream Synapse tables and need to be corrected
there. The pipeline currently passes them through as-is.

