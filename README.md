## NF POC

Knowledge graph materialization pipeline for NF portal assets.

Data integration sources:
- "Main" data portal assets from project syn26451327
- Tools portal assets from project syn26338068 

> [!IMPORTANT]
> Synapse tables ETL runs using anonymous user (no auth) to use open-access data only.

For reproducibility and easy distribution, archives are created with `scripts/create_archive.py`

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
      ▼ (IRI transforms, harmonization)
data/rdf/*.ttl         ←── normalized IRIs
```

### Portal table data retrieval

`scripts/prepare_portal_tables.py` downloads all relevant tables via `synapseclient`, 
writes the raw exports to `data/raw/`, and creates pre-processed CSVs in `data/csv/`. 
The script keeps column order and naming explicit; 
if upstream tables add/remove fields, it will fail early instead of leading to misaligned templates.

### RDF generation pipeline

#### Step 1: RML mapping

RML mappings [1] in `mappings/rml/` materializes pre-processed CSVs to RDF. The mappings handle:

- **IRI generation** for subjects (e.g., `syn:syn123` study IDs)
- **Multi-valued fields** split by `|` delimiter
- **Controlled vocabulary IRIs** for `nf:initiative` and `nf:fundingAgency` (spaces → underscores)

#### Step 2: Harmonization

Harmonization scripts (`classify_datatypes.py`, `link_model_systems.py`, etc.) map
dataType labels to ontology IRIs using the SSSOM mapping (`mappings/data_lookup.sssom.tsv`).

### Project structure

```
├── data/
│   ├── csv/                 # Processed CSVs from Synapse
│   ├── raw/                 # Raw Synapse exports
│   └── rdf/                 # Generated RDF
├── mappings/
│   ├── rml/                 # RML mapping files
│   │   └── portal_studies.rml.ttl
│   └── data_lookup.sssom.tsv # SSSOM mapping for dataType normalization
├── scripts/
│   ├── prepare_portal_tables.py
│   └── classify_datatypes.py
├── test/                    # Test inputs and validation
│   ├── portal_studies.csv
│   └── run_tests.sh
└── tools/                   # RMLMapper [2] JAR and GREL functions
```

### Testing

See test/README.md

### Dependencies

- Java 21+ (for RMLMapper 8.x)
- Python 3.9+ with `rdflib`, `synapseclient`, `pandas`

### References

1. RML — Docs: https://rml.io/docs/, Specification: https://rml.io/specs/rml/
2. RMLMapper — GitHub: https://github.com/RMLio/RMLMapper, Docs: https://rml.io/tools/rmlmapper/
