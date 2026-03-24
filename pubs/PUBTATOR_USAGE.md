# PubTator 3.0 Usage for Entity-Annotated Paper Pipeline

## Overview

[PubTator 3.0](https://doi.org/10.1093/nar/gkae235) is an NCBI service that provides pre-computed biomedical entity annotations for PubMed abstracts and PMC full-text articles. The advantages of the PubTator3 data:

1. **Semantic chunking** — PubTator3 already provides text passages semantically chunked, saving us resources on this processing step.
2. **Entity-linked text** — PubTator3 provides recognized entities using state-of-the-art biomedical NER models, so we get high-quality annotations that can be indexed and used for improved RAG. Entities are already resolved to NCBI Gene, MeSH, OMIM, NCBITaxon, Cellosaurus, and HGVS identifiers, which map directly to KG IRIs without needing us to build a custom entity normalization pipeline.
3. **Improved ground generation** — Entity-linked text also makes it easier to create ground truth evaluation datasets. For example, passages annotated with multiple entity types, such as both gene and disease or both disease and chemical, can be selected for generating highly natural questions asking about relationships between these entities.

## Pipeline Integration

### Current files

- `pubtator3/*.json` — BioC JSON for incorporated papers (full text), one file per PMCID
- `subsets/pubtator3_entities.tsv` — unique entities with mention/paper counts
- `scripts/fetch_pubtator3.py` — fetching script
- `scripts/pubtator3_stats.py` — stats script
- `scripts/pubtator3_entities.py` — entity export script

## API

**Base URL:** `https://www.ncbi.nlm.nih.gov/research/pubtator3-api`

**Full-text annotations by PMID:**

```
GET /publications/export/biocjson?pmids={PMID}&full=true
```

**Abstract-only annotations by PMID:**

```
GET /publications/export/biocjson?pmids={PMID}
```

**Rate limit:** 20 requests/second.

**Response format:** BioC JSON. Each article contains `passages` (title, abstract, body sections) with inline `annotations` array.

### Example

```bash
curl -s "https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?pmids=35741605&full=true" \
  -o pubtator3/PMC9221468.json
```

## Entity Types

PubTator 3.0 recognizes six biomedical entity types:

| Type | Database Field | Identifier Source | Example |
|---|---|---|---|
| **Gene** | `ncbi_gene` | NCBI Gene ID | NF1 (4763) |
| **Disease** | `ncbi_mesh`, `omim`, or absent | MeSH (94%), OMIM (0.3%), unmapped (5.8%) | Neurofibromatosis 1 (MESH:D009456), OMIM:614327 |
| **Chemical** | `ncbi_mesh` | MeSH | Selumetinib (C517975) |
| **Species** | `ncbi_taxonomy` | NCBI Taxonomy | Human (9606), Mouse (10090) |
| **CellLine** | `cvcl` | Cellosaurus | E217 (CVCL:E217) |
| **Variant** | `litvar` | LitVar / HGVS | p.R524M |

Each annotation includes:
- `text` — the surface form in the article
- `locations` — character offset and length
- `infons.identifier` — normalized database ID
- `infons.name` — canonical name
- `infons.type` — entity type

## Annotation Structure

```json
{
  "id": "1",
  "infons": {
    "identifier": "MESH:D009456",
    "type": "Disease",
    "name": "Neurofibromatosis 1",
    "database": "ncbi_mesh",
    "normalized_id": "D009456"
  },
  "text": "NF1",
  "locations": [{ "offset": 115, "length": 3 }]
}
```

Passages include a `section_type` field that maps to the paper structure. All values observed across the corpus:

| `section_type` | Passages | Description |
|---|---|---|
| `TITLE` | 122 | Article title |
| `ABSTRACT` | 383 | Abstract text |
| `INTRO` | 637 | Introduction |
| `METHODS` | 2,655 | Materials and methods |
| `RESULTS` | 1,929 | Results |
| `DISCUSS` | 869 | Discussion |
| `CONCL` | 85 | Conclusions |
| `FIG` | 1,204 | Figure captions |
| `TABLE` | 493 | Table captions / content |
| `REF` | 5,966 | References |
| `SUPPL` | 350 | Supplementary materials |
| `ABBR` | 623 | Abbreviations |
| `ACK_FUND` | 125 | Acknowledgements / funding |
| `AUTH_CONT` | 180 | Author contributions |
| `COMP_INT` | 123 | Competing interests |
| `REVIEW_INFO` | 158 | Review / editorial info |
| `APPENDIX` | 14 | Appendix |
| `KEYWORD` | 2 | Keywords |

## Corpus Stats

Full-text annotations fetched for 139 papers (derivatives-ok set: CC-BY, CC-BY-4.0, Public Domain, CC-BY-NC, CC-BY-NC-SA).
Stored in `pubtator3/` as individual BioC JSON files named by PMCID.

- **139 files**, all with annotations (0 empty)
- **71,791 total entity annotations**
- **5,181 unique entities** (exported to `subsets/pubtator3_entities.tsv`)

| Entity Type | Mentions | Unique | Identifier Source | Examples |
|---|---|---|---|---|
| Gene | 29,040 | 2,160 | NCBI Gene (`ncbi_gene`) | PIK3CA (5290), NF1 (4763), MYC (4609) |
| Disease | 18,053 | 683 | MeSH (`ncbi_mesh`) | Neuroblastoma (D009447), Neurofibromatosis 1 (D009456) |
| Chemical | 11,626 | 764 | MeSH (`ncbi_mesh`) | Selumetinib (C517975), Magnesium Chloride (D015636) |
| Species | 6,117 | 62 | NCBI Taxonomy (`ncbi_taxonomy`) | Human (9606), Mouse (10090) |
| CellLine | 5,304 | 739 | Cellosaurus (`cvcl`) | E217 (CVCL:E217) |
| Variant | 1,651 | 773 | LitVar/HGVS (`litvar`) | p.R524M, p.E982D |

## Scripts

### Fetch annotations: `scripts/fetch_pubtator3.py`

Reads a TSV with pmcid/pmid columns, fetches full-text PubTator3 annotations for each unique paper, and writes BioC JSON files to `pubtator3/`. Skips papers already cached. Respects rate limits.

```bash
python scripts/fetch_pubtator3.py                                                # default: subsets/tools-portal-pmc-permissive.tsv
python scripts/fetch_pubtator3.py subsets/tools-portal-pmc-derivatives-ok.tsv     # expanded set
```

### Annotation stats: `scripts/pubtator3_stats.py`

Scans all JSON files in `pubtator3/` and prints entity type counts, unique entities, token distribution per section type, and per-file summary.

```bash
python scripts/pubtator3_stats.py
```

### Export unique entities: `scripts/pubtator3_entities.py`

Exports all unique entities across the corpus to `subsets/pubtator3_entities.tsv` with columns:

| Column | Description |
|---|---|
| `type` | Entity type (Gene, Disease, Chemical, Species, CellLine, Variant) |
| `identifier` | Normalized ID (e.g., NCBI Gene ID, MeSH ID) |
| `name` | Canonical name |
| `database` | Source database (ncbi_gene, ncbi_mesh, ncbi_taxonomy, cvcl, litvar) |
| `mention_count` | Total mentions across all papers |
| `paper_count` | Number of papers mentioning this entity |
| `pmcids` | Comma-separated list of PMCIDs |

```bash
python scripts/pubtator3_entities.py
```
