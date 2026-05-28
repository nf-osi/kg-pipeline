# PMC Full-Text and License Retrieval

## Overview

Pipeline for retrieving PubMed Central (PMC) IDs, license info, and full-text content in various formats (if available).

## Pipeline

```
tools-portal-pubs.tsv ──┐
main-portal-pubs.tsv ───┤
                        ▼
          scripts/fetch_pmc_and_licenses.py ──► NCBI E-utilities
                        │
                        ├──► pmc_fulltext_xml/*.xml
                        │
                        ▼
          subsets/tools-portal-pmc-with-licenses.tsv  (339 papers)
                        │
                        ▼
                scripts/select_pubs.py
                   │         │
   --permissive ◄──┘         └──► --derivatives-ok
        │                              │
        ▼                              ▼
   subsets/..permissive.tsv    subsets/..derivatives-ok.tsv
     (124 papers)                (139 papers)
        │                              │
        ▼                              ▼
 scripts/xml_to_markdown.py    scripts/fetch_pubtator3.py ──► PubTator 3.0 API
        │                              │
        ▼                              ├──► pubtator3/*.json
 markdown_papers/*.md                  │
                                       ▼
                              scripts/pubtator3_stats.py
                              scripts/pubtator3_entities.py
                                       │
                                       ▼
                              subsets/pubtator3_entities.tsv
```

## First Fetch

**`scripts/fetch_pmc_and_licenses.py`**:

- Reads all publications from `tools-portal-pubs.tsv`
- Fetches PMC IDs for all PMIDs using NCBI E-utilities
- Retrieves license metadata from PMC or cached XML (CC-BY, NIH manuscripts, etc.)
- Extracts license URLs and full license text from XML
- Parses licenses from embedded URLs and text patterns
- Downloads full-text XML files for each PMC article (skips if already present locally)
- Verifies full-text availability (not just abstract)
- Outputs augmented pub metadata table

```bash
# Default: Use cached XML files if available
python3 scripts/fetch_pmc_and_licenses.py

# Force re-fetching from NCBI (ignores cache)
python3 scripts/fetch_pmc_and_licenses.py --no-cache
```

### Output Files

#### 1. `subsets/tools-portal-pmc-with-licenses.tsv`

Tab-separated table with the following columns:

| Column | Description |
|--------|-------------|
| `publicationId` | Unique publication identifier |
| `doi` | Digital Object Identifier |
| `pmid` | PubMed ID |
| `pmcid` | PubMed Central ID (e.g., PMC1234567) |
| `journal` | Journal name |
| `publicationDate` | Publication date |
| `publicationTitle` | Article title |
| `license` | License type (CC-BY, CC-BY-4.0, NIH manuscript, etc.) - See LICENSE_REVIEW.md |
| `is_open_access` | Yes/No - Publisher open access flag from PMC |
| `has_fulltext` | Yes/No (abstract only)/Unknown |
| `xml_file` | Path to downloaded XML file |
| `in_main_portal` | Yes/No - Also appears in main-portal-pubs.tsv |
| `license_url_or_text` | License URL or full license text statement |
| `authors` | Author list |
| `abstract` | Article abstract |
| `citation` | Full citation |

#### 2. `pmc_fulltext_xml/` Directory

Contains individual XML files, one per PMC article:
- Format: `PMC######.xml`
- Size: ~31 MB total
- Content: Full JATS XML including metadata, abstract, body, references

### Results Summary (2026-03-12)

#### PMC Coverage
- **339 publications (49.1%)** have PMC IDs
- **338 XML files** successfully downloaded
- **253 articles (74.6%)** have full-text available
- **82 articles (24.2%)** have abstract only

#### Full-Text Availability

Articles marked as `has_fulltext: Yes` contain:
- Complete article body with sections
- Methods, results, discussion
- References
- Figures and tables (metadata)

Articles marked as `No (abstract only)`:
- Metadata and abstract only
- Common for author manuscripts
- May have restricted full-text access

**Dependencies:** All scripts use Python 3 stdlib only, except `scripts/pubtator3_stats.py` which requires [`tiktoken`](https://github.com/openai/tiktoken) (`pip install tiktoken`).

## Downstream Processing

### License Review

Not all open-access full-text content can be integrated into a RAG application, as many are open-access for limited purposes. 
Licenses are reviewed first for determining which publications are incorporated. 

#### Defined License Sets and Criteria

License is derived from the `<license>` element (parsed from `href` attribute or `license-p` text) field in PMC XML metadata. 
A good number of publications have a standard license, while the rest state "fair use", point to journal-specific terms, or are not yet clearly specified/retrievable. 
Use `scripts/select_pubs.py --analyze` to get current counts for defined sets as well as by each license type. 

For a RAG application, substantial content is indexed and redistributed, which exceeds [fair use](https://www.copyright.gov/fair-use/) -- papers with "fair use" terms are excluded. 
Because an agentic RAG system remixes/transforms original content, papers with no-derivatives terms are excluded. 

The most permissive set is defined as some version of CC-BY and Public Domain licenses. 
Because we are a non-commercial product that intends to comply with ShareAlike (sharing our derivatives publicly), an expanded feasible set of papers is the `--derivatives-ok`.

| Set | Licenses | Use case |
|-----|----------|----------|
| `--permissive` | CC-BY, CC-BY-4.0, Public Domain | Commercial use, redistribution |
| `--derivatives-ok` | Permissive + CC-BY-NC, CC-BY-NC-SA | Non-commercial derivatives |

CC-BY-NC-ND is excluded from both sets (no derivatives allowed).

#### Publication Selection

**`scripts/select_pubs.py`** filters publications by license set:

> [!IMPORTANT]
> The current full-text index is built from `subsets/tools-portal-pmc-derivatives-ok.tsv`.
> In other words, publications considered "in the full-text index" correspond to the `--derivatives-ok` set, not the narrower `--permissive` set.

```bash
python scripts/select_pubs.py --permissive      # CC-BY, CC-BY-4.0, Public Domain (124 papers)
python scripts/select_pubs.py --derivatives-ok  # + CC-BY-NC, CC-BY-NC-SA (139 papers)
```

Output: `subsets/tools-portal-pmc-<set>.tsv`

### PubTator 3.0 Entity Annotations

Pre-computed biomedical entity annotations (genes, diseases, chemicals, species, cell lines, variants) are fetched from the [PubTator 3.0](https://academic.oup.com/nar/article/52/W1/W540/7640526) API.

```bash
python scripts/fetch_pubtator3.py subsets/tools-portal-pmc-derivatives-ok.tsv  # Fetch annotations
python scripts/pubtator3_stats.py                                              # Print corpus stats
python scripts/pubtator3_entities.py                                           # Export unique entities
```

Output: `pubtator3/<PMCID>.json` (139 papers, 71,791 entity annotations, 5,181 unique entities)

See [PUBTATOR_USAGE.md](PUBTATOR_USAGE.md) for API details, entity types, annotation structure, and section types.
