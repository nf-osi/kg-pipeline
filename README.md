## NF Knowledge Graph Pipeline

Materializes a knowledge graph from [NF Data Portal](https://nf.synapse.org/) assets on Synapse.

Data sources:
- Main portal tables in project syn26451327
- Tools portal tables in project syn26338068

> [!IMPORTANT]
> Synapse ETL uses anonymous access (open data only, no auth should be used).

### Pipeline

```
Synapse tables
      │
      ▼  scripts/prepare_portal_tables.py
data/csv/*.csv                  raw tabular data
      │
      ▼  scripts/classify_*.py, harmonize_files.py
data/csv/*_harmonized.csv       labels resolved to ontology IRIs
      │
      ▼  RMLMapper + mappings/rml/*.rml.ttl
data/rdf/*.ttl                  RDF triples
```

**1. Extract** — `prepare_portal_tables.py` downloads tables via `synapseclient`,
caches raw exports in `data/raw/`, and writes normalized CSVs to `data/csv/`.
Supports `--from-cache` to reprocess without Synapse access.

**2. Harmonize/Transform** — Classification scripts map string labels (e.g. `dataType`,
`mutationType`, `cellLineCategory`) to ontology class IRIs using
[SSSOM](https://mapping-commons.github.io/sssom/) lookups in `mappings/sssom/`.
Six tables have a harmonization step; the rest go directly to RML.

**3. Map/Transform** — [RML](https://rml.io/specs/rml/) mappings convert CSVs to RDF.
They handle IRI minting, pipe-delimited multi-value splits, and
controlled-vocabulary normalization. [RMLMapper](https://github.com/RMLio/RMLMapper)
runs each mapping with GREL function support.

### Project structure

```
schema/ontology.ttl              OWL ontology (classes, properties, hierarchy)
mappings/
  rml/                           RML mapping files (one per table)
  sssom/                         SSSOM label-to-IRI lookups
scripts/
  prepare_portal_tables.py       Synapse download + CSV normalization
  classify_*.py                  Harmonization (one per entity type)
  harmonize_files.py             File-level harmonization (model systems, data types)
  validate_fks.py                CSV-level foreign key validation (see HARMONIZATION.md)
  astabench_data.py              Build eval_data.yaml for astabench from ground-truth files
data/
  csv/                           Source and harmonized CSVs
  rdf/                           Generated RDF (Turtle)
  raw/                           Raw Synapse exports (cache)
orchestration/dagster_pipeline/  Dagster asset definitions for the full pipeline
astabench/                       Eval framework (git submodule, see Evaluation)
evaluation/                      Eval datasets for KG quality + RAG
test/                            RML mapping tests (pytest + rdflib)
tools/                           RMLMapper JAR + GREL function files
```

### Dagster orchestration

The full pipeline can be run as a Dagster asset graph. Each table produces
CSV, (optional) harmonized CSV, and RDF assets. An FK validation asset runs
after all CSVs complete.

```bash
cd orchestration
dagster dev -m dagster_pipeline          # UI at http://localhost:3000
dagster asset materialize -m dagster_pipeline  # materialize all
```

See [orchestration/README.md](orchestration/README.md) for setup, asset
selection patterns, and details.

### Data quality

See [HARMONIZATION.md](HARMONIZATION.md) for harmonization scripts, FK
validation, and known upstream data quality issues.

### Testing

```
pytest test/
```

Each RML mapping has a corresponding test that runs RMLMapper against a small
fixture CSV and validates the output graph with SPARQL. See `test/README.md`.

### Build and Release

Pre-built [QLever](https://github.com/ad-freiburg/qlever) images with indexed data
are published to GHCR on each tagged release.

Run the image:

```
docker run -p 7001:7001 ghcr.io/nf-osi/kg-pipeline:latest
```

The SPARQL endpoint is available at `http://localhost:7001`.

To build locally from materialized RDF instead:
```
docker compose run --rm qlever-index   # build index
docker compose up qlever-server        # serve on :7001
```

### Evaluation

Evaluation uses the [AstaBench](https://github.com/allenai/asta-bench) framework (built on [InspectAI](https://inspect.aisi.org.uk/)).
`astabench` is a git submodule pointing to the [nf-osi fork](https://github.com/nf-osi/asta-bench) that adds NF-specific tasks.

```bash
git submodule update --init              # first time
git submodule update --remote astabench  # pull latest from fork
```

Ground-truth datasets live in `evaluation/<dataset>/` as separate auto-generated and
manually curated YAML files. Before running eval, merge them into the single
`eval_data.yaml` that astabench expects:

```bash
python scripts/astabench_data.py --dataset main
```

Then serve the knowledge graph (either with a [released image](#build-and-release)
or via `docker compose`), set up API keys, and run:

```bash
cd astabench
# install deps as needed
inspect eval astabench/nf_rag --solver react --model anthropic/claude-sonnet-4-5
```

See [`astabench/evals/nf_rag/README.md`](astabench/evals/nf_rag/README.md) for additional details and examples.

#### Limitations

This evaluates retrieval from one knowledge source in isolation.
In production, an agent switches between two or more sources (e.g. the KG and a vector DB that indexes help documentation).

### Dependencies

- Java 21+ (RMLMapper 8.x)
- Python 3.10+ with `rdflib`, `synapseclient`, `pandas`
