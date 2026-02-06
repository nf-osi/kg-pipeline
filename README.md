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
├── data/
│   ├── csv/                 # Processed CSVs from Synapse
│   ├── raw/                 # Raw Synapse exports
│   └── rdf/                 # Generated RDF
├── mappings/
│   ├── rml/                 # RML mapping files
│   │   └── portal_studies.rml.ttl
│   └── data_lookup.ttl      # SKOS vocabulary for dataType normalization
├── scripts/
│   ├── prepare_portal_tables.py
│   └── transform_iris.py
├── test/                    # Test inputs and validation
│   ├── portal_studies.csv
│   └── run_tests.sh
└── tools/                   # RMLMapper [2] JAR and GREL functions
```

### Testing

```bash
./test/run_tests.sh
```

Validates that RML mappings correctly transform:
- `nf:initiative` values to IRIs (e.g., "Cutaneous Neurofibroma Initiative" → `nf:Cutaneous_Neurofibroma_Initiative`)
- `nf:fundingAgency` values to IRIs with proper splitting

### Dependencies

- Java 21+ (for RMLMapper 8.x)
- Python 3.9+ with `rdflib`, `synapseclient`, `pandas`

### References

1. RML — Docs: https://rml.io/docs/, Specification: https://rml.io/specs/rml/
2. RMLMapper — GitHub: https://github.com/RMLio/RMLMapper, Docs: https://rml.io/tools/rmlmapper/
