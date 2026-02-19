# NF Knowledge Graph Pipeline - Dagster Orchestration

This directory contains the Dagster orchestration for the NF Knowledge Graph pipeline.

## Architecture

The pipeline is organized as a DAG of **assets**:

```
Synapse Tables → CSV → [Harmonize] → RML → RDF (.ttl)
```

- **Harmonize** (studies, observations, files, genetic_reagents, mutations): classify/link CSV data before RML mapping

### Asset Groups

Each portal table has its own asset group (17 tables total):

1. **CSV Asset** (`portal/csv/{table}`)
   - Downloads from Synapse
   - Applies transformations (string_list, synapse_id, etc.)
   - Writes to `data/csv/`

2. **Harmonize Asset** (`portal/harmonized/{table}`) - *studies, observations, files, cell_lines, genetic_reagents, mutations*
   - Runs classification/linking scripts on CSV data
   - Writes to `data/csv/{table}_harmonized.csv`

3. **RDF Asset** (`portal/rdf/{table}`)
   - Runs RMLMapper (CSV → RDF)
   - Writes to `data/rdf/`

4. **FK Validation Asset** (`portal/quality/fk_validation`) - *single asset, runs once*
   - Depends on all CSV assets
   - Checks referential integrity across tables (see [HARMONIZATION.md](../HARMONIZATION.md))
   - Non-blocking: logs results and attaches metadata but never raises

## Setup

**⚠️ Python Version:** Requires Python 3.11 or 3.12 (Python 3.13+ has compatibility issues with Dagster CLI)

```bash
cd orchestration

# Create virtual environment with Python 3.11 or 3.12
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

## Usage

**With CLI:**

```bash
# Materialize all assets
dagster asset materialize -m dagster_pipeline

# Materialize a single asset
dagster asset materialize -m dagster_pipeline --select "portal/csv/donors"

# Materialize multiple assets (comma-separated)
dagster asset materialize -m dagster_pipeline --select "portal/rdf/donors,portal/rdf/antibodies"

# Materialize all assets in a table group (CSV + harmonize + RDF)
dagster asset materialize -m dagster_pipeline --select "group:donors"

# Materialize an asset and all its upstream dependencies
dagster asset materialize -m dagster_pipeline --select "+portal/rdf/studies"

# Run FK validation only
dagster asset materialize -m dagster_pipeline --select "group:validation"
```

### With Dagster UI

```bash
cd orchestration
dagster dev -m dagster_pipeline
```

Then open http://localhost:3000

**From the UI:**
- Navigate to "Assets" tab
- Select the assets you want to build
- Click "Materialize selected"

## Asset Selection Patterns

Asset keys follow the pattern `portal/{stage}/{table}`:

- `portal/csv/donors` — single asset
- `group:donors` — all assets in the donors group (CSV + harmonize + RDF)
- `group:validation` — FK validation asset
- `+portal/rdf/studies` — asset and all upstream dependencies
- `portal/csv/studies+` — asset and all downstream dependents

## Project Structure

```
orchestration/
├── dagster_pipeline/
│   ├── __init__.py       # Dagster Definitions
│   ├── assets.py         # Asset definitions
│   ├── config.py         # Table configurations
│   └── resources.py      # Resources (Synapse, RMLMapper)
├── pyproject.toml        # Dependencies
└── README.md             # This file
```

## Development

### Adding a New Table

1. Add table config to `scripts/prepare_portal_tables.py`
2. Create RML mapping in `mappings/rml/`
3. Reload Dagster - assets auto-generate from `TABLE_CONFIGS`

No need to modify Dagster code - assets are generated dynamically,

### Testing

```bash
# Test that assets load
dagster asset list -m dagster_pipeline

# Test a single asset
dagster asset materialize -m dagster_pipeline --select portal/csv/donors
```
