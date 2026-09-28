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
| `variant_consequence.sssom.tsv` | MAF `Consequence` | Sequence Ontology IRIs |
| `variant_classification.sssom.tsv` | MAF `Variant_Classification` | Sequence Ontology IRIs (fallback) |
| `tumor_type_lookup.sssom.tsv` | `tumorType` | EFO / MONDO disease IRIs |

`tumor_type_lookup.sssom.tsv` is **additive**, unlike the others: `nf:tumorType` keeps the
curated string and the resolved term goes on `nf:tumorClass`. Most of the distinct
`tumorType` values have no exact ontology term, and several that do not are the
clinically meaningful categories (`ANNUBP`, `Atypical Neurofibroma`, `Recurrent MPNST`),
so replacing the label the way `dataType` does would delete the tumour type from those
files. Values with no term keep `object_id = sssom:NoTermFound` and a note giving the
reason, so what the file refuses to assert is as visible as what it does — the same rule
`orthologs.tsv` follows with `status=excluded`.

Mapped rows were resolved by exact, case-folded label match against the EFO/MONDO terms
in a pinned Open Targets release. This is the seed for more systematic tumour-type mapping later on.

## Identifier crosswalks

Not SSSOM (these map identifiers, not ontology terms), but the same idea: a checked-in,
diffable mapping rather than a regex buried in a script.

| File | Maps | Regenerate with |
|------|------|-----------------|
| `cbioportal_sample_specimen.tsv` | cBioPortal `Tumor_Sample_Barcode` → portal `specimenID`/`individualID` | `scripts/map_cbioportal_samples.py` |
| `orthologs.tsv` | model-organism gene (MGI/ZFIN/RGD) → human gene (HGNC IRI) | `scripts/fetch_orthologs.py` |
| `model_mutation_vrs.tsv` | curated `humanClinVarMutation` → GRCh38 coordinates → `ga4gh:VA.*` | `scripts/mint_model_mutation_vrs.py` |

Rows whose `method` is not one of the derived values (`strip_last_segment`,
`prefix_guess`, `unmatched`) are treated as human-authored and preserved on
regeneration — set `method=manual` to fix a barcode by hand. `scripts/validate_fks.py`
checks that every specimen named here actually exists.

`orthologs.tsv` and `model_mutation_vrs.tsv` are the two bridges between the curated
model-system layer and the somatic variant layer. Both are checked in rather than fetched at build time since neither
changes on a build cadence. `orthologs.tsv` is ~20 rows keyed to the genes in
`mutations.csv`, and `model_mutation_vrs.tsv` is 46. They are turned into triples
offline by `scripts/materialize_orthologs.py` and
`scripts/materialize_model_mutation_vrs.py`.

`orthologs.tsv` includes a `status` column to make exclusions explicit. 
Cre driver lines curated under promoter symbols such as `Dhh`, `GFAP`, and `SynI` are marked `status=excluded` with a reason. 
The source is SHA-256 pinned in `fetch_orthologs.py`, and `check_source_versions.py --check-external` reports source drift without modifying the pin.

## RML (`rml/`)

[RML](https://rml.io/) (RDF Mapping Language) Turtle files that define how CSV rows become RDF triples. These run **after** SSSOM harmonization, reading the enriched CSVs and producing the final RDF output via RMLMapper.

```
Portal CSV
  --> [prepare_portal_tables.py] --> data/csv/*.csv
  --> [SSSOM harmonization scripts] --> data/csv/*_harmonized.csv
  --> [RMLMapper + rml/*.rml.ttl] --> data/rdf/*.ttl
```
