# NF Knowledge Graph Pipeline - Dagster Orchestration

This directory contains the Dagster orchestration for the NF Knowledge Graph pipeline.

## Architecture

The pipeline is organized as a DAG of **assets**:

```
Synapse Tables → CSV Files → RML RDF (.rml.ttl) → Final RDF (.ttl)
                                                  (transform for studies/files only)
```

**File Naming:**
- `.rml.ttl` - RMLMapper output (intermediate)
- `.ttl` - Final output (IRI-transformed for studies/files, copied for others)

### Asset Groups

Each portal table (study, file, mutation, reagent, animal, cell, donor, antibody) has its own asset group:

1. **CSV Asset** (`portal/csv/{table}_csv`)
   - Downloads from Synapse
   - Applies transformations (string_list, synapse_id, etc.)
   - Writes to `data/csv/`

2. **RDF Asset** (`portal/rdf/{table}_rdf_raw` or `portal/rdf/{table}_rdf`)
   - Runs RMLMapper
   - Generates RDF from CSV
   - Writes to `data/rdf/`

3. **Transform Asset** (`portal/rdf/{table}_rdf`) - *studies/files only*
   - Runs IRI transformation via SPARQL
   - Converts literals to IRIs
   - Writes final RDF to `data/rdf/`

## Setup

**⚠️ Python Version:** Requires Python 3.11 or 3.12 (Python 3.13+ has compatibility issues with Dagster CLI)

```bash
cd orchestration

# Create virtual environment with Python 3.11 or 3.12
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Or with uv (faster)
uv pip install -e ".[dev]"
```

## Usage

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

**With CLI:**

```bash
# Materialize all assets
dagster asset materialize --module-name dagster_pipeline

# Materialize specific table
dagster asset materialize --module-name dagster_pipeline --select "portal_donors*"

# Materialize multiple tables
dagster asset materialize --module-name dagster_pipeline --select "portal_donors* portal_antibodies*"

# Materialize all CSV assets
dagster asset materialize --module-name dagster_pipeline --select "tag:compute_kind=synapse"

# Materialize all RML assets
dagster asset materialize --module-name dagster_pipeline --select "tag:compute_kind=rml"
```

## Asset Selection Patterns

Dagster supports asset selection:

- `portal_donors_csv` - Single asset
- `portal_donors*` - All assets in the donors group
- `*rdf` - All RDF assets
- `tag:compute_kind=rml` - All RML mapping assets
- `+portal_studies_rdf` - Asset and all upstream dependencies
- `portal_studies_rdf+` - Asset and all downstream dependencies

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
dagster asset list --module-name dagster_pipeline

# Test a single asset
dagster asset materialize --module-name dagster_pipeline --select portal_donors_csv
```

