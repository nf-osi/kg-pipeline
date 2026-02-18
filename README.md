## NF POC

Knowledge graph materialization pipeline for NF portal assets.

Data integration sources:
- "Main" data portal assets are from project syn26451327
- Tools portal assets are from project syn26338068 

### Overview

```
Synapse tables
      │
      ▼ (prepare_portal_tables.py)
data/csv/*.csv
      │
      ▼ (RML mapping)
data/rdf/*_raw.ttl     ←── literal values
      │
      ▼ (IRI transform script)
data/rdf/*.ttl         ←── normalized IRIs
```

### Quick start

```bash
# Generate final RDF (runs full pipeline)
make

# Or step by step:
make rml_portal_studies   # Step 1: RML mapping only
make portal_studies       # Step 2: + IRI transform script

# Data quality check
make check_datatypes      # Find unmatched dataType literals
```

### Portal table data retrieval

`scripts/prepare_portal_tables.py` downloads the current `portal_files` (syn16858331) and `portal_studies`
(syn52694652) tables via `synapseclient`, writes the raw exports to `data/raw/`, and creates
pre-processed CSVs in `data/csv/`.

Run before the RML pipeline whenever Synapse tables change. The script keeps column order and
naming explicit; if upstream tables add/remove fields, it will fail early instead of producing
misaligned template calls.

### RDF generation pipeline

#### Step 1: RML mapping

RML mappings [1] in `mappings/rml/` materializes pre-processed CSVs to RDF. The mappings handle:

- **IRI generation** for subjects (e.g., `syn:syn123` study IDs)
- **Multi-valued fields** split by `|` delimiter
- **Controlled vocabulary IRIs** for `nf:initiative` and `nf:fundingAgency` (spaces → underscores)

```bash
make rml_portal_studies  # Produces data/rdf/portal_studies_raw.ttl
```

#### Step 2: IRI transform

`scripts/transform_iris.py` transforms `nf:dataType` literals to ontology IRIs using a SKOS
lookup vocabulary (`mappings/data_lookup.ttl`).

The lookup maps source literals (with synonyms via `skos:altLabel`) to target IRIs,

```bash
make portal_studies      # Produces data/rdf/portal_studies.ttl
```

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

### Testing

```bash
./test/run_tests.sh
```

Validates that RML mappings correctly transform:
- `nf:initiative` values to IRIs (e.g., "Cutaneous Neurofibroma Initiative" → `nf:Cutaneous_Neurofibroma_Initiative`)
- `nf:fundingAgency` values to IRIs with proper splitting

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

- Java 21+ (for RMLMapper 8.x)
- Python 3.9+ with `rdflib`, `synapseclient`, `pandas`

### References

1. RML — Docs: https://rml.io/docs/, Specification: https://rml.io/specs/rml/
2. RMLMapper — GitHub: https://github.com/RMLio/RMLMapper, Docs: https://rml.io/tools/rmlmapper/
