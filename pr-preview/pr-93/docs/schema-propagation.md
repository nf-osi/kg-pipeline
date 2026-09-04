# Schema Propagation and Silent Breaks

A column's definition is repeated in up to six places between Synapse and the graph. When two of
them disagree the pipeline does not fail — it quietly emits fewer triples. This page records a
concrete instance, measures how widespread the pattern is, and collects directions for making the
chain either self-consistent or self-checking.

Filed as background for a future research issue; nothing here is a decided design.

## The incident: `nf:createdBy` / `nf:modifiedBy`

`files.rml.ttl` has always mapped these two properties, and the Synapse source has a value for every
row. They produced **zero triples** for as long as the mapping has existed. The chain:

| Step | State |
|---|---|
| `files.rml.ttl` maps `{createdBy}` / `{modifiedBy}` | ✅ present |
| `FILES_SELECT` fetches both columns | ✅ present |
| `data/raw/files_raw.csv` | ✅ populated in every row |
| `TABLES["files"]["columns"]` | ❌ **omits them** |
| `data/csv/files.csv`, `files_harmonized.csv` | ❌ column absent |
| built RDF | ❌ 0 triples |

The break is that **`*_SELECT` controls what is fetched, while `TABLES[...]["columns"]` controls what
is written**, and nothing reconciles them:

```python
def build_rows(df, columns):
    for col in columns:                  # iterates the TABLES list, not the DataFrame
        value = record.get(source, "")

def write_processed_csv(path, columns, rows):
    writer.writerow([col["target"] for col in columns])
```

Fixed by adding the two columns; the graph gained 414,160 `nf:createdBy` triples and `files.ttl` grew
from 124 MB to 172 MB. Those IRIs resolve to `biolink:Person` nodes that already existed, so file
contributions are now connected to the same identities used by ORCID, `nf:SynapseUser` and
`nf:onProject`.

## Why nothing caught it

Every stage succeeded on its own terms. The SELECT was valid, the CSV wrote cleanly, RMLMapper
exited 0, and the RDF validated.

The deeper reason is that **absence is ambiguous**. RML's null-propagation — emit nothing when a
referenced value is missing — is relied on *deliberately* throughout this pipeline (optional fields,
`synapseUserOrcid`, `cleanDoi`, `publicationKey`). So "this property produced no triples" is exactly
what a correctly-skipped optional field looks like. A broken chain and an empty column are
indistinguishable from the outside.

Existing checks do not close this. `validate_rdf.sh` verifies outputs exist and are non-empty, that
no placeholder-base IRIs leaked, and that every `rdf:type` is a declared `owl:Class`;
`validate_collections.py` and `validate_fks.py` cover provenance and referential integrity. None
inspects **property-level coverage**.

## How widespread

Of **228 properties declared in `schema/ontology.ttl`, 23 appear nowhere in the built RDF.** A rough
classification:

| Category | Count | Meaning |
|---|---|---|
| mapped, source column present, all values empty | 16 | legitimately empty — not a defect |
| declared but never mapped in any RML file | 3 | orphan declaration (`aboutResource`, `hasResource`, `inFullTextIndex`) |
| unresolved by the classifier | 4 | nested FunctionTermMaps the quick script could not parse — need manual review |

The classifier was a throwaway regex, so those 4 are "unknown", not "confirmed broken". That
imprecision is itself the point: **there is currently no reliable way to tell the three categories
apart**, which is why `createdBy` survived so long.

## Directions to explore

### 1. Make the schema propagate from one source

`fetch_table` already derives a SELECT from the column list when no manual clause is given:

```python
select_clause = _normalize_select_clause(manual_clause) if manual_clause \
                else _synapse_select_clause(columns)
```

but **all 26 tables define a manual `select_clause`**, so the derived path is dead code and the two
definitions are free to drift. Options:

- drop manual clauses where the derived one would do, leaving divergence structurally impossible;
- keep them only where genuinely needed (quoting reserved words like `"year"`, renaming
  `mutationDetailsId` → `mutationId`, the `"5primer"` style columns) and assert the manual clause
  covers every declared column;
- generate one from the other at build time.

### 2. Add property-level checks

- **RML reference → CSV column.** Parse each mapping's `rml:reference` and `rr:template` variables
  and assert each names a column in the CSV that mapping reads. This alone would have caught
  `createdBy` at build time, cheaply and with no false positives.
- **Declared property → used, or explicitly expected-empty.** Fail when a declared property emits
  nothing unless it is annotated as legitimately sparse. Needs a way to record intent — an ontology
  annotation, or a manifest of known-empty properties.
- **Emitted predicate → declared.** The mirror of the existing `rdf:type` check, catching typo'd
  predicate IRIs.

### 3. Represent "expected to be empty"

The blocker for check 2 is that the pipeline cannot express the difference between *no data yet* and
*broken*. Whatever form it takes, recording that intent is what turns a noisy report into a gate.

## Related

- [publication-issues.md](publication-issues.md) — source-data defects, including several found the
  same way (by hand, while investigating something else)
- `scripts/validate_rdf.sh`, `scripts/validate_collections.py`, `scripts/validate_fks.py` — existing
  checks, and the precedent for adding another
