# Changelog - NF Research Tools Discovery Dataset

All notable changes to the NF Research Tools Discovery evaluation dataset will be documented in this file.

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
