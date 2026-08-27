# Upstream Schema Migration (issue #87)

Review of the July–August 2026 `nf-osi/nf-research-tools-schema` changes and what they
require here. Findings are verified against **live Synapse**, not just the upstream repo's
git history (the local clone is ahead of some deployed state, and behind others).

## Context

Upstream completed a CSV → LinkML migration (their #223/#229, phases 1–7). The load-bearing
consequence for this pipeline: **the central `Resource` table (syn26450069) was retired**, and
every tool-type table was re-keyed from its own `<type>Id` primary key to a single shared
`resourceId`. Core `Tool` fields (`resourceName`, `description`, `rrid`, `howToAcquire`, …) are
now denormalized into all nine tool-type tables, so there is no central table to join through.

### The build is not broken — but it can no longer move forward

Verified: 0 of 26 release tables fail against their **currently pinned** versions in
`data_sources.yaml`. Version snapshots preserve the old column schema, so today's build is fine.

But 10 of those 26 fail against **live**:

| Table | Fails because |
|---|---|
| `cell_lines`, `animal_models`, `antibodies`, `genetic_reagents`, `biobanks`, `clinical_assessment_tools`, `patient_derived_models`, `organoid_protocols`, `computational_tools` | `<type>Id` no longer exists (now `resourceId`) |
| `mutation_model` | `animalModelId` / `cellLineId` no longer exist (now `resourceId`) |

Pins are 1–42 versions stale (`cell_lines` 9→51, `development` 4→46, `animal_models` 8→33).
`check_source_versions.py` runs daily and opens repin PRs — **those PRs would break the build if
merged.** That is the active hazard: the pipeline is frozen in a pre-migration world and the
automation keeps proposing a change it cannot survive.

### Why the tool IRIs have to change

`<type>Id` and `resourceId` are **different UUIDs** for 1144 of 1218 tools, and `<type>Id` now
exists *only* in the retired `resources` table. So tool node identity has to move onto
`resourceId`. Decision taken: mint `nf:resource/{resourceId}`, **clean break** (no `owl:sameAs`
bridge).

This is a deliberate reversal of the tradeoff recorded in `docs/resource-shortcut-iris.md`. It is
justified because the stated advantage of type-specific IRIs — "the IRI itself tells you the
type" — is **already redundant**: every per-type mapping already asserts a real class
(`mappings/rml/cell_lines.rml.ttl:32` → `nf:CellLine`, and similarly for the other eight), on the
same subject IRI. `?s a nf:CellLine` already works.

The migration also fixes two documented defects for free, because `development.rml.ttl` and
`donor_tool.rml.ttl` already target `nf:resource/{resourceId}`:

- **415 dead triples across 844 orphan IRIs** — the stale shortcut maps in
  `docs/resource-shortcut-iris.md:59-78` become correctly connected.
- **77 of 268 broken `nf:cellLine/{resourceId}` IRIs** in `mutation_model`
  (`HARMONIZATION.md:123-136`) — the resourceId/entityId confusion class becomes impossible once
  there is only one id.

### Scope

**This plan covers P1 only** — unblocking the pins. P2/P3 are recorded at the end and deferred.

**No crosswalk artifact is needed.** `<type>Id` has no forward use, and every tool node already
carries its `resourceId` as a string literal — verified 1215 of 1215 `nf:Tool` nodes in the
current graph, zero missing. So any archived graph (or the pinned `rdf_archive`) is already a
complete old-IRI → `resourceId` mapping, recoverable with a one-line query. The retired
syn26450069 does not need to be preserved separately.

---

## P1 — Migrate tool identity to `resourceId` and retire the frozen Resource table

### 1. `data_sources.yaml`
- Remove the `resources` entry from the **`release`** profile (no longer a source).
- Repin every remaining release table. **Re-derive the numbers at implementation time** with
  `python scripts/check_source_versions.py --dry-run` rather than copying today's snapshot.
- Mark the `evaluation` profile archive-only (see item 8). Leave its table entries untouched — they
  are the record of what the benchmark was built from.
- Bump `version` / `comment` (KG v0.4).

### 2. `scripts/prepare_portal_tables.py`
The `TABLES` dict (line 433+) is the single source of truth and drives the Dagster DAG, the
expected-TTL list in `validate_rdf.sh`, and FK discovery. Changes:

- Delete the `resources` entry, `RESOURCES_SELECT` (line 382), and the `"resource"` alias
  (line 414).
- **Per-table pattern, all nine tool tables:** `<type>Id as <type>Id` → `resourceId as resourceId`,
  and add the core Tool columns now present on every table: `rrid`, `resourceName`, `synonyms`,
  `resourceType`, `description`, `usageRequirements`, `howToAcquire`, `dateAdded`, `dateModified`
  (+ `aiSummary`, which was never ingested and is free to pick up here — LLM-authored summaries,
  useful for retrieval). Reuse the existing `transform` values: `string_list` for `synonyms` /
  `usageRequirements`, `number` for the two dates.
- Table-specific column changes verified against live:

  | Table | Change |
  |---|---|
  | `animal_models` | drop `species` from the SELECT; `animalModelOfManifestation` → `manifestation`; `animalModelGeneticDisorder` → `geneticDisorder` |
  | `cell_lines` | drop `race` and `contaminatedMisidentified`; `cellLineManifestation` → `manifestation`; `cellLineGeneticDisorder` → `geneticDisorder` |
  | `biobanks` | drop `diseaseType` (removed upstream) |
  | `mutation_model` | `animalModelId`, `cellLineId` → `resourceId` |
  | `mutations` | **no change** — already aliases `mutationDetailsId as mutationId` (line 76), so the MutationDetails rename is handled and mutation IRIs stay stable |

  `species`/`race` are already derived from `donors` by `apply_derived_columns`
  (lines 1267-1278 and 1281-1292); both guard on `if "<col>" in df.columns` and currently
  short-circuit because the tool table supplies the column. Dropping it from the SELECT activates
  the donor merge — the intended path. **Verify the merged values match the old ones** on a sample.
- Update every `references` FK spec that names a `<type>Id` (lines 575-577, 595, 616-621, 759-760,
  and the deleted `resources` block) to `resourceId`. `references` is consumed only by
  `validate_fks.py:discover_constraints()`.
- Relax `check_config()` (line 1451): it requires `TABLES.keys()` to equal *every* profile's table
  names in both directions, so dropping `resources` from `TABLES` would fail on the frozen
  `evaluation` profile. Add an archive-only marker to that profile and skip the bidirectional name
  check for it — this makes decision 8 machine-enforced rather than a comment.

### 3. `mappings/rml/`
- **Delete `resources.rml.ttl`** (695 lines, nine near-identical copies of the same 11 core
  predicates).
- In each of the nine per-type mappings: change the subject template from
  `terms#<type>/{<type>Id}` to `terms#resource/{resourceId}`, and add the core Tool
  predicate/object maps. For `synonyms` and `usageRequirements` reuse the `grel:string_split`
  `FunctionTermMap` pattern already present in each file for its own multivalued fields.
- `mutation_model.rml.ttl:24,40` — both subject templates → `terms#resource/{resourceId}`; the two
  triples maps collapse into one (there is no longer a separate animal-model vs cell-line path).
- Keep the three `map:Resource*` shortcuts in `development.rml.ttl:86,99,112` and
  `donor_tool.rml.ttl:24` **unchanged** — they already target the new IRI and start working.

### 4. `scripts/harmonize_files.py`
`build_lookup()` (lines 38-70) reads `resources.csv` and mints `animalModel/`/`cellLine/` IRIs to
resolve `files.modelSystemName` → `modelSystemId`. Repoint it at `cell_lines.csv` +
`animal_models.csv`, keyed on `resourceId`, emitting `nf:resource/{resourceId}`. Update the
`--resources` arg in `orchestration/dagster_pipeline/config.py:72`.

### 5. `scripts/materialize_observation_links.py`
Takes a single `resources_ttl`. Change it to accept several TTL paths and update
`observation_links_asset` (`orchestration/dagster_pipeline/assets.py:315-341`) to depend on the
nine per-type RDF assets instead of `["portal","rdf","resources"]`.

Keep the literal-join CONSTRUCT rather than templating the IRI directly from
`observations.resourceId` — the join filters dangling references, and there are real ones
(5 `Usage` and 5 `VendorItem` resourceIds do not resolve).

### 6. `schema/ontology.ttl`
- `nf:resourceId` is declared `owl:ObjectProperty` with `rdfs:range nf:Tool` but emitted as an
  `xsd:string` literal. Fix to `owl:DatatypeProperty` / `xsd:string`. Load-bearing: this is the
  property whose identity semantics the migration turns on.
- Declare `nf:forResourceId`, currently used in the data but absent from the ontology.
- Widen `nf:organ`'s domain (line 1188) — it is `unionOf(File, CellLine)` but `organ` is now live
  on `patient_derived_models` and `organoid_protocols` too.

### 7. Tests (`test/`)
- 11 fixture CSVs carry `<type>Id` headers: `test/{cell_lines,animal_models,antibodies,`
  `genetic_reagents,biobanks,clinical_assessment_tools,patient_derived_models,organoid_protocols,`
  `computational_tools,mutation_model}.csv` and `test/resources.csv`.
- `test/files.csv:2` embeds full literal IRIs (`…terms#cellLine/1`, `…terms#animalModel/2`).
- `test/test_rml_resources.py` tests a mapping that no longer exists — delete or repurpose. Note
  `:261-278` currently asserts `"resource/" not in tool_str`, i.e. it asserts the *opposite* of the
  target state; do not just tweak it, remove the premise.
- IRI-shape assertions to update: `test_rml_relationships.py:94,108-127,227,237`,
  `test_rml_{organoid_protocols,clinical_assessment_tools,computational_tools,`
  `patient_derived_models}.py:39-43`, `test_rml_files.py:348-349`, and the hand-built fixture IRIs
  in `test_{shared_donor_links,nf1_mutation_sets,observation_links}.py`.

### 8. Docs and downstream
- Rewrite `docs/resource-shortcut-iris.md` — its defect is resolved and its tradeoff reversed.
  Record *why*, so the reversal is as legible as the original decision.
- Update `HARMONIZATION.md:123-136` (the 77-row `mutation_model.cellLineId` bug is moot) and the
  IRI-design section of `docs/kg-pipeline-architecture.md:233-236,420`.
- `docs/kg-pipeline-architecture.md:420` states IRIs should not change without a deprecation
  strategy. The strategy here is an explicit clean break, on the grounds that `nf:resourceId` is
  carried on every tool node in every archived graph and is therefore sufficient to resolve any
  old IRI retrospectively. Write that down rather than leaving the policy silently contradicted.
- **Evaluation:** leave the profile frozen and archive-only. Ground truth stores bare `resourceId`
  UUIDs (not IRIs) and `astabench` grading regex-matches them, so the IRI change does **not**
  break grading. Reproducibility already rests on the pinned `ghcr.io/nf-osi/kg-qlever:eval-*`
  images. Two hazards to note in the doc: `create_archive.py` fetches tables *without* version
  pinning and would silently un-freeze the benchmark if run against `--profile evaluation`; and
  `release.rdf_archive` / `evaluation.rdf_archive` currently point at the same unpinned entity
  (syn74703004).
- **Embeddings:** the pinned `embeddings_archive` (syn74760478 / syn74760481) is keyed by node IRI
  and becomes unmatchable. Nothing detects this. Rebuild and re-pin, or mark the entry stale.
- Re-baseline the RDF diff archive after the first post-migration build.

---

## Deferred

**P2 — new tables (highest data value once P1 lands; all keyed on `resourceId`).**

| Table | Rows | Value |
|---|---|---|
| `Usage` (syn26486841) | 1897 | **1862 brand-new resource↔publication edges** over 632 resources / 660 pubs. `Development` currently supplies only 199 pairs across 89 pubs. All publicationIds resolve cleanly. Note `development` v4→v46 includes rows *moved* to `Usage`, so tool↔publication linkage is incomplete without it. |
| `VendorItem` (syn26486843) | 590 | Vendor + catalog number + purchase URL for 586 of 1218 resources — directly answers "how do I obtain this tool". |
| `Vendor` (syn26486850) | 61 | Vendor names/URLs. |

**P3 — newly populated facets.** Verified fill rates: `availability` (100%, e.g. Unknown / Vendor /
Contact Developer), `tissueList` (181/664 cell lines), PDM `modelType` and `tumorType` (100%),
`cognitiveAndBehavioralDomains`. Unified `manifestation` / `geneticDisorder` arrive with P1's
renames.

**Not worth modelling yet.** Upstream added a large translational/drug-development field family
(`bbbIntegrityStatus`, `routeOfAdministration`, `pkpdCapabilities`,
`mechanismOfActionValidation`, `pediatricSuitability`, `timelineToResults`, `modelLimitations`,
`regulatoryAcceptanceHistory`, `mtaRequired`, `ngnriRepositoryStatus`,
`clinicalTranslationHistory`, …). Spot-checked with real value counts: **essentially all empty** —
the columns exist, the data does not. Do not build ontology for them yet; revisit when populated.

---

## Verification

Run in this order; each step gates the next.

1. `python scripts/prepare_portal_tables.py --check-config` — TABLES vs `data_sources.yaml`.
2. `pytest test/` — the RML suite shells out to the real RMLMapper against fixture CSVs, so it
   catches subject-template and column errors without touching Synapse.
3. Single-table smoke, cheapest first:
   `python scripts/prepare_portal_tables.py donors cell_lines animal_models`
   (`donors` is auto-reordered first because of the derived `species`/`race` merge). Inspect
   `data/csv/cell_lines.csv` for the core Tool columns and confirm `species`/`race` are populated
   via the donor merge.
4. `dagster asset materialize -m dagster_pipeline --select "group:cell_lines"` — CSV → harmonize →
   RDF for one group.
5. Full build: `dagster asset materialize -m dagster_pipeline --select "*"` then
   `./scripts/validate_rdf.sh` (file existence, placeholder-IRI grep, schema-drift, collections).
6. `python scripts/validate_fks.py` — expect the `mutation_model` FK violations to **drop**
   (the 77 resourceId/cellLineId confusions become well-formed).
7. `python scripts/diff_rdf.py` — expect ~1218 tools removed + ~1218 added. Confirm this is an
   identity change and not data loss by matching `nf:resourceId` literals across the two sides:
   both the old and new nodes carry it, so the sets should be equal modulo genuine upstream
   adds/deletes (currently 2 in, 2 out). This is the key review artifact.
8. Spot-check with `scripts/query_sparql.py` that the previously-dead shortcuts now resolve:
   a tool reached via `nf:hasFunder` / `nf:hasInvestigator` / `nf:hasPublication` should have an
   `rdf:type` and a name. Previously 0 of 844 did.
