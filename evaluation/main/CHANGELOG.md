# Changelog - NF Research Tools Discovery Dataset

All notable changes to the NF Research Tools Discovery evaluation dataset will be documented in this file.

## [v1.4] - 2026-08-27

Minimal correctness pass for KG v0.4 (the upstream LinkML schema adoption, #87).
Deliberately **not** a re-baseline: ground truth is still the v0.2-eval answer
set, so the additions-direction staleness described below is a known, open gap.

### Fixed
- **MUT-001 listed 2 answers that never existed.** `03ecfea8-e812-40a8-8938-0979f15b3f53`
  and `530e83c9-385e-40f5-8f89-5728f5db211d` were emitted by
  `generate_ground_truth.py` straight from `mutation_model.animalModelId` /
  `.cellLineId`, which are orphaned FK values — they resolve to no tool in the
  eval's own frozen snapshot, nor in any table before or since. This is the
  `mutation_model` FK orphan bug (`HARMONIZATION.md`) leaking into ground truth,
  **not** a consequence of the KG v0.4 migration; it was equally broken under
  the old pins
  - **This one does move a score.** MUT-001's achievable recall was 14/16 = 0.875
    and is now 14/14 = 1.0, so recorded MUT-001 recall is not comparable across
    this change. Every other question is untouched
  - Checked exhaustively afterwards: 0 unresolvable uuid answers remain across
    both `eval_tools_ground_auto.yaml` and `eval_tools_ground_manual.yaml`
  - The generator still has no FK validation on the ids it emits, so this class
    of bad answer can recur. Worth adding when the generator is ported (below)

- **Agent prompt advertised properties that no longer exist.** `task.py`'s
  `INSTRUCTION_PREFIX` said "Prefer using nf:resourceId over type-specific IDs
  (e.g. cellLineId, animalModelId)". KG v0.4 removed `nf:cellLineId` and its
  eight siblings entirely, so that sentence pointed at a fallback that silently
  returns nothing. Replaced with the actual rule: one IRI template
  (`terms#resource/{resourceId}`) for every tool type, uuid from `nf:resourceId`,
  type from `rdf:type`
  - Also documented the direct `nf:Tool -> nf:hasInvestigator / nf:hasFunder /
    nf:hasPublication` shortcut in the topology block. Those 415 triples existed
    but landed on unreachable IRIs before v0.4; they now resolve, and the
    one-hop path is cheaper than going via `nf:Development`
  - Prompt changes normally invalidate recorded runs, and this is no exception —
    but it only takes effect against a v0.4 graph, which needs a newly built
    `eval-*` image, and the underlying data change already breaks comparability
    at that point. It adds no breakage that building that image does not

### Known gap (not addressed)
- **Answer sets are stale in the additions direction.** KG v0.4 repinned every
  source table forward, and upstream curation moved the data — e.g. NF1 MPNST
  cell lines went from 19 to 29 between `cell_lines` v9 and v51. Questions whose
  correct answer grew now under-count, penalising an agent that finds the new
  resources. Re-baselining means porting `generate_ground_truth.py` to the new
  schema (~56 references to removed columns, the deleted `resources.csv`, and
  `development_investigator.csv` / `development_funder.csv` which the current
  pipeline does not emit) and would reset comparability for all 52 recorded runs.
  Tracked as its own change; see `docs/upstream-schema-migration.md`

## [v1.3] - 2026-08-18

Declares the publication and people questions, and corrects a species predicate
that counted humanized mouse samples as human.

### Added
- **Publication & People Discovery (PUB)** component — 6 questions (PUB-001 – PUB-006) covering author counts, ORCID coverage, Synapse account linkage, cross-listing overlap, and co-authorship reach. All 6 are manually curated
  - The ground truth for these landed in #75, together with the people and publication ingest that supports them: `people.rml.ttl`, `publication_author_orcids.rml.ttl`, `study_publications.rml.ttl`, and the `nf:authors` / `nf:authorOrcid` / `nf:hasSynapseProfile` ontology terms
  - Several items deliberately probe known upstream data problems — duplicate listings and DOI normalisation — documented in `docs/publication-issues.md`
- Question attributes for the PUB component: `level`, `complexity`, `facet_answerable`, `text_search_answerable`, `user_frustration`, `demo_priority`, and per-item notes. Without these, `extract_runs.py` had no metadata to join against, so the 6 items scored into `category/PUB` but contributed to **no** level, complexity, or frustration breakdown and had no per-question recall recorded

### Fixed
- **Species predicate matched humanized mouse samples as human.** `generate_ground_truth.py` tested species with a plain substring alternation, which also matches `Mus musculus (humanized)` — there is no word boundary between "human" and "ized". Replaced with a single `HUMAN_SPECIES_PATTERN` using word boundaries, applied to all four affected questions: **CL-005**, **CL-006**, **CR-002**, **ST-003**
  - The pattern still matches multi-valued cells such as `Rattus norvegicus,Homo sapiens` and `Homo sapiens|Mus musculus`, so nothing legitimate is lost
  - **No ground-truth answer changes.** Regenerated and diffed: the one humanized-mouse study in the snapshot already qualified on its human files, so every answer set is identical. This is a correctness-of-intent fix, and it invalidates no recorded result
  - Found while investigating why claude-sonnet-5 scored 0.10 on ST-003. The model wrote `CONTAINS(LCASE(?species), "human")`, which excludes `Homo sapiens` and selects only humanized mice; it returned 1 of 10 studies. The graph and the ground truth were both right, but the ground truth relied on the same loose matching and was a latent version of the same bug

- **Question wording in `dataset_attributes.yaml` drifted from the prompt actually in use** for AM-004 and CR-004. Both now match their ground-truth entry verbatim
  - Aligned in that direction because the ground truth is what the agent sees: `astabench.py` builds `eval_data.yaml` from the `*_ground*.yaml` files, and the recorded eval logs confirm the prompt matches those files verbatim for all 10 manually curated questions. The attribute file is documentation, so no prompt changed and no result is invalidated
  - CR-004 was not cosmetic drift: the attribute file offered lettered options `(A) Yes (B) No …`, while the prompt in use asks for the exact phrase. An agent answering "A" would fail the phrase-containment scorer, so promoting that wording into the ground truth would have broken the item
  - AM-004's attribute wording ("Which mouse model has…?") reads better than the prompt in use ("Find mouse model with…"). Improving the prompt itself is a deliberate change that would invalidate recorded runs, so it is deliberately not done here

- **Runs that executed the v1.3 set reported v1.2.** Because the PUB questions predate the version bump, their eval logs carry `task_version: v1.2`. `extract_runs.py` now corrects this when writing `runs.json`
  - Keyed on `category/PUB`, which the harness derives from per-sample metadata in the log. That makes the rule independent of `dataset_attributes.yaml`, so it holds whether or not the PUB attributes are present, and a sample count would not work since most of these are targeted development runs covering one or two questions
  - 19 runs relabelled v1.2 → v1.3; the 2026-05-27 ST-only development run correctly keeps v1.2. No other field on any run changes
  - Done in the extractor rather than by editing `runs.json`, so it survives re-extraction

### Changed
- `complexity` now uses **3-hop** for the first time. PUB-003 and PUB-005 traverse Synapse profile → ORCID → DOI before filtering, one hop further than anything earlier
- New personas in `user_story`: **Portal Contributor** (PUB-003, PUB-005) and **Data Curator** (PUB-004)

### Notes
- Re-extract with `python scripts/extract_runs.py` to pick up the PUB attributes on already-recorded runs
- PUB-003 is a designed trap and both evaluated models currently fail it: 19 publication nodes deduplicate to 14 distinct papers, and a raw node count is the expected wrong answer
- PUB-004 awards partial credit by construction — matching on `nf:pmid` yields the correct 22, while matching on DOI or title yields 19

### Dataset Overview
- **Total Questions:** 46 (36 automated + 10 manual)
- **Question Categories:**
  - Mutations (MUT): 6 questions
  - Animal Models (AM): 6 questions
  - Cell Lines (CL): 9 questions
  - Genetic Reagents (GR): 5 questions
  - Antibodies (AB): 3 questions
  - Investigators (PI): 2 questions
  - Cross-Resource (CR): 4 questions
  - Studies (ST): 5 questions
  - Publications & People (PUB): 6 questions
- **Complexity Levels:** 0-hop, 1-hop, 2-hop, 3-hop queries
- **Difficulty Levels:** Baseline (20), Advanced (26)
- **Manual ground truth:** AM-004, CL-003, CR-001, CR-004, PUB-001 – PUB-006 (was AM-004, CL-003, CR-001, CR-004)

## [v1.2] - 2026-05-27

### Added
- **Study Discovery (ST)** component — 5 questions (ST-001 – ST-005) finding studies and their data files by joining study metadata with file-level annotations (#66)
- `data_sources_profile: evaluation` and `data_sources_version: KG v0.2-eval` in dataset metadata, so a question set records the graph build it was developed against (#66)

### Dataset Overview
- **Total Questions:** 40 (36 automated + 4 manual)
- **Question Categories:** ST added with 5 questions; all others unchanged from v1.1
- **Manual ground truth:** AM-004, CL-003, CR-001, CR-004 (unchanged)

> **Note on runs reporting v1.2.** The 6 PUB questions were added to the ground
> truth in #75 without a version bump, so eval logs from 2026-07-25 onward record
> `task_version: v1.2` while already executing the 46-question set. v1.3 is the
> first version to declare that set, and `extract_runs.py` now corrects the label
> when writing `runs.json`, so those 19 runs report v1.3. The one genuine v1.2
> run — an ST-only development run from 2026-05-27 — keeps its label.

## [v1.1] - 2026-04-17

### Added
- **CR-004**: MTA (Materials Transfer Agreement) question for SZ-NF1 cell line — tests agent calibration and hallucination resistance with multiple-choice format
- Scorer support for non-UUID free-text answers (phrase containment matching)
- `scripts/quick_eval.py` for running targeted evaluations on individual questions

### Changed
- **CL-003**: Corrected ground truth from 1 result (YST-1, a miscategorized schwannoma) to 4 normal Schwann cell lines (hTERT SC ipn97.4, hTERT ipn02.3 2λ, hTERT ipn02.8, ScienCell Schwann cells)
- `generate_ground_truth.py`: Switched question source from removed `eval_tools.yaml` to `dataset_attributes.yaml`; CL-003 now searches name/description/synonyms via resources join and excludes schwannoma and NF1 knockout lines
- `nf_rag/task.py`: `task_filter` and `task_category` now accept both string and list inputs

### Ground truth corrections (from PR #47)
- **AM-001**: Added description search for 'optic glioma' instead of only matching on manifestation property, catching 2 additional models
- **CL-004**: Added NF1 filter + fixed race column handling after join suffix changes, excludes 3 non-NF1 KRAS-mutant lung lines from Black donors
- **CL-005**: Correctly excludes 2 canine cell lines with pediatric-age donors; simplified species column reference
- **CL-006**: Same species column cleanup as CL-005, no changes to answer set
- **CL-008**: Rewrote isogenic pair logic — builds donor families via parentDonorId chains, requires exactly 1 total mutation (must be NF1), matching tissue/organ/category, and a 0-mutation wildtype counterpart in the same family. Reduced from 50 to 10 results.

### Dataset Overview
- **Total Questions:** 35 (31 automated + 4 manual)
- **Question Categories:** CR now has 4 questions (was 3)
- **Manual ground truth:** AM-004, CL-003, CR-001, CR-004 (was AM-004, CR-001)

## [v1] - 2026-02-12

### Notes
- Merged in PR#12.
- Previously tracked as v0 during development; v0 and v1 content are identical

### Dataset Overview
- **Total Questions:** 34 (32 automated + 2 manual)
- **Question Categories:**
  - Mutations (MUT): 6 questions
  - Animal Models (AM): 6 questions
  - Cell Lines (CL): 9 questions
  - Genetic Reagents (GR): 5 questions
  - Antibodies (AB): 3 questions
  - Investigators (PI): 2 questions
  - Cross-Resource (CR): 3 questions
- **Complexity Levels:** 0-hop, 1-hop, 2-hop queries
- **Difficulty Levels:** Baseline, Advanced
- **Task:** SPARQL query generation against NF-OSI knowledge graph
- **Metric:** Recall (F1 over retrieved resource IDs)

### Question Types
- **Baseline questions:** Queries answerable with current portal capabilities
- **Advanced questions:** Queries requiring semantic understanding, complex joins, ranking/aggregation

### Data Sources
- Portal entity tables: animal_models, cell_lines, genetic_reagents, antibodies, mutations
- Cross-referenced via resources table (unified resource IDs)
- Donor and investigator metadata tables

### Ground Truth Generation
- Automated ground truth computed from CSV exports via `generate_ground_truth.py`
- Manual ground truth for edge cases (AM-004: tumor detection timing requires observation text interpretation)
- Results validated against portal data snapshots

## [v0] - Development

Initial development version. Content identical to v1.
