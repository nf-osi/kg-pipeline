# Harmonization and Data Transform Notes

This documents data transformations applied between the raw Synapse
export and the final RDF and known upstream data quality issues.

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
| `harmonize_files.py` | `files.csv` + `animal_models.csv` + `cell_lines.csv` | Resolves `modelSystemName` to resource IRIs; maps `dataType`, `nf1Genotype`, `nf2Genotype` labels to class IRIs |

### 3. RML mapping

RML Turtle files under `mappings/rml/` define CSV-to-RDF transformations.
Multi-value pipe-delimited fields are split using `grel:string_split`.

## FK validation

Foreign key relationships between tables are declared inline in the `TABLES`
dict in `prepare_portal_tables.py` (a `references` key on each FK column) and
checked by `scripts/validate_fks.py`. 16 FK constraints are tracked across 8
tables. Validation is non-blocking — it reports orphaned FK values but does not
stop the pipeline.

A `references` entry may name either a single target table (`"table"`) or several
(`"tables"`), in which case the FK passes if the value exists in ANY of them. The
multi-target form exists because a `resourceId` can live in any of the nine
tool-type tables now that the central Resource table is retired; the shared spec
is `TOOL_RESOURCE_REF` in `prepare_portal_tables.py`.

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
FK validation: 16 constraints across 8 tables

FAIL  donors.parentDonorId -> donors.donorId
      11 / 57 populated rows orphaned (19.3%), 7 unique values
      sample: 077ce9fd-..., 2eb64d9c-...

 ok   development.resourceId -> <9 tool tables>.resourceId
 ...

Summary: 4 failures, 12 passed
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
# single target
{"target": "donorId", "type": "iri", "references": {"table": "donors", "column": "donorId"}}

# union of targets — passes if the value exists in any of them
{"target": "resourceId", "type": "iri", "references": TOOL_RESOURCE_REF}
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

- **mutation_model.cellLineId**: An upstream migration introduce 
  renamed `Mutation`'s (syn26486834) `animalModelId`/`cellLineId` columns to
  `resourceId` **without migrating previous type-specific ID values**, so 265 of 277 rows now hold a
  legacy `<type>Id` in a column named `resourceId`. `prepare_portal_tables.py`
  translates these at build time; upstream fix is pending.

- **donors.parentDonorId**: 6 of 7 orphaned `parentDonorId` values are
  actually `resourceId` UUIDs for cell line resources, not donor UUIDs.
  1 additional value is completely dangling (not found anywhere). Still
  outstanding — `donors` was not re-keyed by the migration, so this one is
  unaffected by the above and needs correcting upstream. The pipeline passes
  it through as-is.

### Duplicated publications and conflicting author lists

Publications are ingested from two portal listings that key their records
differently, so the same paper can appear as two `biolink:Publication` nodes.
See [docs/publication-issues.md](docs/publication-issues.md) for details 
of known issues, the correct way to count publications, and the specific 
records needing curator attention.
