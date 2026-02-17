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
data/
  csv/                           Source and harmonized CSVs
  rdf/                           Generated RDF (Turtle)
  raw/                           Raw Synapse exports (cache)
orchestration/dagster_pipeline/  Dagster asset definitions for the full pipeline
evaluation/                      Eval datasets for KG quality + RAG
test/                            RML mapping tests (pytest + rdflib)
tools/                           RMLMapper JAR + GREL function files
```

### Testing

```
pytest test/
```

Each RML mapping has a corresponding test that runs RMLMapper against a small
fixture CSV and validates the output graph with SPARQL. See `test/README.md`.

### Dependencies

- Java 21+ (RMLMapper 8.x)
- Python 3.10+ with `rdflib`, `synapseclient`, `pandas`
