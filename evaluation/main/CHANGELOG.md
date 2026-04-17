# Changelog - NF Research Tools Discovery Dataset

All notable changes to the NF Research Tools Discovery evaluation dataset will be documented in this file.

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
