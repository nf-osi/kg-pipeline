# Mappings

Two types of mappings convert portal data into RDF, running at different pipeline stages.

## SSSOM (`sssom/`)

[SSSOM](https://mapping-commons.github.io/sssom/) (Simple Standard for Sharing Ontological Mappings) TSV files that map source labels to ontology IRIs. These run **before** RML as a pre-processing step: Python harmonization scripts read the SSSOM lookups, resolve raw CSV values to IRIs, and write enriched `*_harmonized.csv` files.

| File | Source column | Target |
|------|--------------|--------|
| `data_lookup.sssom.tsv` | `dataType` | Data type class IRIs |
| `observation_type_mapping.sssom.tsv` | `observationType` | Observation subclass IRIs |
| `nf1_genotype_lookup.sssom.tsv` | `nf1Genotype` | NF1 genotype class IRIs |
| `nf2_genotype_lookup.sssom.tsv` | `nf2Genotype` | NF2 genotype class IRIs |
| `cell_line_category_lookup.sssom.tsv` | `cellLineCategory` | CellLine subclass IRIs |

## RML (`rml/`)

[RML](https://rml.io/) (RDF Mapping Language) Turtle files that define how CSV rows become RDF triples. These run **after** SSSOM harmonization, reading the enriched CSVs and producing the final RDF output via RMLMapper.

```
Portal CSV
  --> [prepare_portal_tables.py] --> data/csv/*.csv
  --> [SSSOM harmonization scripts] --> data/csv/*_harmonized.csv
  --> [RMLMapper + rml/*.rml.ttl] --> data/rdf/*.ttl
```
