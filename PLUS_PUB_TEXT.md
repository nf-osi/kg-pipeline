# SPARQL+Text: Publication Full-Text Index

QLever supports combining SPARQL graph queries with full-text search over
text records via its [SPARQL+Text](https://github.com/ad-freiburg/qlever/blob/master/docs/sparql_plus_text.md)
feature. We use this to index passage-level text and biomedical entity
annotations from 139 NF-related publications (sourced via PubTator 3.0) so
that the KG endpoint can answer queries like "which genes are mentioned in
papers about neurofibromatosis treatment?"

## Pipeline overview

```
pubtator3/*.json  (139 BioC JSON files, 71,791 annotations)
        │
        ▼  pubs/scripts/pubtator3_to_qlever.py
qlever_text/
  ├── wordsfile.tsv       words + entity IRIs per passage
  ├── docsfile.tsv        passage text per record
  └── text_entities.ttl   companion RDF (entity types + labels)
        │
        ▼  docker compose run --rm qlever-index-text
QLever index with text  (qlever-index -w ... -d ... -t)
        │
        ▼  docker compose up qlever-server-text
SPARQL+Text endpoint on :7001
```

## Design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Record granularity | Per passage (~11k records) | Natural unit from PubTator3; finer than per-paper |
| Section filtering | Exclude `REF` only | Not much return expected for additional indexing of references, which may also degrade retrieval with added noise |
| Score boosting | TITLE/ABSTRACT = 2, body = 1 | Configurable via `--title-boost` / `--abstract-boost` |
| Word tokenization | Regex `[a-z0-9]+` on lowercased text | Simple, no stopwords; QLever handles ranking |
| Entity deduplication | Per passage | Same entity mentioned multiple times in a passage gets one IRI entry |
| Invalid annotations | Skip (`valid=false`, null/dash identifiers) | ~8k annotations filtered out |
| Multi-value Gene IDs | First ID only (9 cases with `;`) | Avoids ambiguity |
| Variants without HGVS | Skip entity IRI (166 cases) | Text like "G to T" is too vague to have IRI assigned by PubTator; words still indexed |

## Entity IRI scheme

| PubTator3 type | IRI pattern | Example |
|---|---|---|
| Gene | `<https://www.ncbi.nlm.nih.gov/gene/{id}>` | `<https://www.ncbi.nlm.nih.gov/gene/4763>` (NF1) |
| Disease (MeSH) | `<http://id.nlm.nih.gov/mesh/{id}>` | `<http://id.nlm.nih.gov/mesh/D009456>` |
| Disease (OMIM) | `<https://omim.org/entry/{id}>` | `<https://omim.org/entry/614327>` |
| Chemical (MeSH) | `<http://id.nlm.nih.gov/mesh/{id}>` | `<http://id.nlm.nih.gov/mesh/D015811>` |
| Species | `<http://purl.obolibrary.org/obo/NCBITaxon_{id}>` | `<http://purl.obolibrary.org/obo/NCBITaxon_9606>` |
| CellLine | `<https://www.cellosaurus.org/CVCL_{id}>` | `<https://www.cellosaurus.org/CVCL_E217>` |
| Variant (HGVS) | `<https://www.ncbi.nlm.nih.gov/research/litvar2-api/variant/autocomplete/?query={url_encoded}>` | `<...?query=p.G12V>` |

MeSH/OMIM/CVCL prefixes in the source data (e.g. `MESH:D009447`) are stripped
to bare IDs. HGVS values are URL-encoded (`>` becomes `%3E`).

## QLever text input format

QLever requires two tab-separated files:

**wordsfile.tsv** — one line per word/entity occurrence:
```
word_or_iri	is_entity	record_id	score
```
```
<https://pubmed.ncbi.nlm.nih.gov/16822308>	1	0	2
mutations	0	0	2
in	0	0	2
pik3ca	0	0	2
<https://www.ncbi.nlm.nih.gov/gene/5290>	1	0	2
```

**docsfile.tsv** — one line per text record:
```
record_id	passage_text
```
```
0	Mutations in PIK3CA are infrequent in neuroblastoma
```

## Companion RDF

`text_entities.ttl` declares entity classes and labels so that entities
referenced in the wordsfile exist in the RDF graph for joins:

```turtle
nf:Gene a owl:Class ; rdfs:label "Gene" .

<https://www.ncbi.nlm.nih.gov/gene/4763> a nf:Gene ; rdfs:label "NF1" .
<http://id.nlm.nih.gov/mesh/D009456> a nf:DiseaseConcept ; rdfs:label "Neurofibromatosis 1" .
```

Classes: `nf:Gene`, `nf:DiseaseConcept`, `nf:Chemical`, `nf:Species`,
`nf:CellLine` (already in ontology), `nf:Variant`.

Publication IRIs (`<https://pubmed.ncbi.nlm.nih.gov/{pmid}>`) are included in
the wordsfile to link passages to papers. These require the upstream KG to use
the same IRI scheme; until then, QLever logs warnings for unmatched entities
but text search still works.

## Output stats

| Output | Lines | Size |
|---|---|---|
| `wordsfile.tsv` | 902,655 | 15 MB |
| `docsfile.tsv` | 11,109 | 5.3 MB |
| `text_entities.ttl` | 9,830 | 432 KB |

| Metric | Count |
|---|---|
| Files processed | 139 |
| Passages indexed | 11,109 |
| Word entries | 857,387 |
| Entity IRI entries | 45,268 |
| Unique entities | 4,904 |
| Skipped (invalid) | 4,311 |
| Skipped (no identifier) | 47 |
| Skipped (no IRI) | 162 |

## Scripts

**`pubs/scripts/pubtator3_to_qlever.py`** — stdlib-only Python, single-pass
over all JSON files. Outputs wordsfile, docsfile, and companion TTL.

```bash
python pubs/scripts/pubtator3_to_qlever.py
python pubs/scripts/pubtator3_to_qlever.py --title-boost 3 --abstract-boost 2
python pubs/scripts/pubtator3_to_qlever.py --output-dir /tmp/text
```

Options:
- `--pubtator-dir` — input directory (default: `pubs/pubtator3`)
- `--output-dir` — output directory (default: `pubs/qlever_text`)
- `--title-boost` — score for TITLE passages (default: 2)
- `--abstract-boost` — score for ABSTRACT passages (default: 2)

## Docker compose

The compose file defines two service pairs. The base pair (`qlever-index` /
`qlever-server`) builds a graph-only index. The text pair adds the text index:

| Service | Description |
|---|---|
| `qlever-index` | Build RDF-only index |
| `qlever-server` | Serve RDF-only on :7001 |
| `qlever-index-text` | Build RDF + text index (mounts `pubs/qlever_text/`) |
| `qlever-server-text` | Serve RDF + text on :7001 (`-t` flag) |

The text indexer adds three flags to `qlever-index`:
- `-w /input/text/wordsfile.tsv` — wordsfile
- `-d /input/text/docsfile.tsv` — docsfile
- Feeds `text_entities.ttl` into the RDF input stream

The text server requires `-t` to load the text index at startup.

```bash
# Build and test (RDF + text)
docker compose run --rm qlever-index-text    # ~5s
./scripts/test_sparql_with_text.sh           # starts server, tests, stops

# Rebuild from scratch
docker compose down -v
docker compose run --rm qlever-index-text
```

Each pair uses its own named volume (`qlever-index` vs `qlever-index-text`),
so both can coexist. Only one server should run at a time (both bind port 7001).

## Test queries

Two test scripts share common helpers via `scripts/qlever_test_helpers.sh`:

| Script | Services | Queries |
|---|---|---|
| `scripts/test_sparql.sh` | `qlever-server` | 5 graph queries |
| `scripts/test_sparql_with_text.sh` | `qlever-server-text` | 3 graph + 8 text queries |

Both scripts manage the server lifecycle automatically (start, wait for
readiness, run queries, stop on exit). Pass a URL argument to skip lifecycle
management and query an already-running endpoint.

### SPARQL+Text query examples

QLever text queries use the `ql:` namespace. Every `ql:contains-entity` must
be paired with a `ql:contains-word` in the same pattern.

**Word search** — find passages mentioning "neurofibromatosis":
```sparql
SELECT (COUNT(?text) AS ?count) WHERE {
  ?text ql:contains-word "neurofibromatosis"
}
```

**Prefix search** — words starting with "schwann":
```sparql
SELECT ?text WHERE {
  ?text ql:contains-word "schwann*"
} LIMIT 5
```

**Entity + word** — passages with NF1 gene entity and "mutation":
```sparql
SELECT (COUNT(?text) AS ?count) WHERE {
  ?text ql:contains-entity <https://www.ncbi.nlm.nih.gov/gene/4763> .
  ?text ql:contains-word "mutation*"
}
```

**Text + graph join** — genes co-mentioned with "neurofibromatosis", ranked:
```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?entity ?label (COUNT(?text) AS ?mentions) WHERE {
  ?text ql:contains-word "neurofibromatosis" .
  ?text ql:contains-entity ?entity .
  ?entity a <http://nf-osi.github.com/terms#Gene> .
  ?entity rdfs:label ?label
}
GROUP BY ?entity ?label
ORDER BY DESC(?mentions)
LIMIT 10
```

Sample result from the last query:

| Gene | Label | Mentions |
|---|---|---|
| gene/4763 | NF1 | 129 |
| gene/18015 | Nf1 | 49 |
| gene/5594 | MAPK1 | 16 |
| gene/5609 | MAP2K7 | 12 |
| gene/207 | AKT1 | 9 |

## Timings

| Step | Time |
|---|---|
| `pubtator3_to_qlever.py` | < 2s |
| `qlever-index-text` | ~5s |
| `qlever-server-text` startup | ~2s |
| Full test suite | ~10s (including server start/stop) |

## Known limitations

- **Publication IRIs not in KG yet** — `<https://pubmed.ncbi.nlm.nih.gov/{pmid}>`
  is used in the wordsfile but the upstream KG uses different publication IRIs.
  QLever warns about 11,109 unmatched entity mentions. Text search still works;
  publication-entity joins will work once the KG adopts the same IRI scheme.
- **No `ql:score()` in SELECT** — QLever's current version does not support
  `ql:score()` as a SPARQL function. Score boosting affects result ordering
  internally but cannot be projected.
- **Companion RDF not in ontology** — the new classes (`nf:Gene`,
  `nf:DiseaseConcept`, etc.) are declared in `text_entities.ttl` only, not in
  `schema/ontology.ttl`.
