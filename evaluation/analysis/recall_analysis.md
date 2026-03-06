# Recall Analysis: Research Tool Discovery Evaluation

Analysis of question-level recall across all evaluation runs (10 runs, 3 models: Claude Sonnet 4.5, Claude Haiku 4.5, GPT-5.2).

---

## Part 1: Bottom 5 Questions (Best Recall 0.000-0.250)

Four of five scored 0.000 across **every model and every run**. These represent fundamental gaps.

| Rank | Question ID | Category | Best Recall | Overall Avg | Level | Complexity | User Frustration |
|------|------------|----------|-------------|-------------|-------|------------|-----------------|
| 1 | CL-003 | Cell Line | 0.000 | 0.000 | baseline | 1-hop | moderate |
| 2 | AM-002 | Animal Model | 0.000 | 0.000 | baseline | 0-hop | high |
| 3 | GR-004 | Genetic Reagent | 0.000 | 0.000 | advanced | 1-hop | high |
| 4 | AM-004 | Animal Model | 0.000 | 0.000 | advanced | 1-hop | very_high |
| 5 | CR-001 | Cross-Resource | 0.500 | 0.062 | advanced | 1-hop | high |

### 1. CL-003: "I need normal schwann cell lines"

**Target:** 1 UUID | **All models returned:** 0 correct out of 7 retrieved

**Root Cause: Ambiguous "normal" semantics + over-retrieval**

The model interprets "normal" as "not cancer" (a reasonable interpretation), finding 7 non-cancer schwann cell lines. But the benchmark expects a specific single cell line. The model lacks the domain knowledge to distinguish between immortalized, primary, and NF1-patient-derived schwann cell lines.

The correct answer likely requires filtering for `cellLineGeneticDisorder = "No known genetic disorder"` AND schwann cell type — a specific combination the model didn't narrow down to.

**Data quality note:** Text search returns healthy cell lines at very bottom because affected cell lines are incorrectly categorized.

### 2. AM-002: "Help me find animal models suitable for energy expenditure studies"

**Target:** 2 UUIDs | **All models:** No valid answer (ran out of turns)

**Root Cause: Semantic gap — no direct link between "energy expenditure" and animal model properties**

The term "energy expenditure" doesn't appear anywhere in the knowledge graph. The connection requires understanding that:
- "Energy expenditure" studies use "metabolic screening" and "oxygen consumption" assays
- These assays are performed using specific animal models
- The link goes through `File` entities via `modelSystemName`, not directly through animal model properties

Requires translation from "energy expenditure" to "metabolic function" via ontology — a 0-hop question by complexity but requires **semantic reasoning** that none of the models could perform.

### 3. GR-004: "Find NF1 expression vectors compatible with high-copy E. coli systems"

**Target:** 4 UUIDs | **All models returned:** Wrong UUIDs

**Root Cause: Missing data — `copyNumber` property is empty**

The `copyNumber` property exists in the schema but is **not populated** in the data. Answering correctly requires specialized molecular biology knowledge about plasmid copy numbers and vector backbones (pET, pUC, pBR322) that goes beyond what's explicit in the graph data.

### 4. AM-004: "Which mouse model has the earliest observed tumor development?"

**Target:** 2 UUIDs | **All models returned:** 1 wrong UUID (a zebrafish)

**Root Cause: Missed species constraint — returned zebrafish instead of mouse**

The question explicitly asks for "mouse model" but all models found a zebrafish with earlier tumor onset (7 days larval phase) and returned that instead. The species constraint parsing failure is consistent across all models — even the best models don't add a species filter to their SPARQL queries.

### 5. CR-001: "Which cell lines have shown sensitivity to HDAC inhibitors?"

**Target:** 2 UUIDs | **Best recall:** 0.500 (Haiku, 1 run) — 0.0 in all other runs

**Root Cause: Multi-hop reasoning across Observations + domain knowledge of HDAC inhibitor names**

The answer requires knowing the full set of HDAC inhibitor compound names, searching observation text for these terms, distinguishing sensitivity from resistance, and tracing observations back to cell lines via `forResourceId`. Evidence is scattered across observation text and file metadata.

---

## Part 2: Mid-Tier Questions (Ranks 6-15, Best Recall 0.451-1.000)

This tier splits into two groups:
- **Ranks 6-8:** Best recall < 1.0 — no model fully solves these
- **Ranks 9-15:** Best recall = 1.0 but with high variance across models and runs

| Rank | Question ID | Category | Best Recall | Overall Avg | Level | Complexity | User Frustration | Target Size |
|------|------------|----------|-------------|-------------|-------|------------|-----------------|-------------|
| 6 | CL-008 | Cell Line | 0.451 | 0.114 | advanced | 2-hop | very_high | 51 |
| 7 | CL-004 | Cell Line | 0.556 | 0.200 | baseline | 0-hop | low | 9 |
| 8 | CR-002 | Cross-Resource | 0.667 | 0.267 | advanced | 2-hop | very_high | 3 |
| 9 | CL-009 | Cell Line | 1.000 | 0.633 | advanced | 1-hop | very_high | 3 |
| 10 | CL-001 | Cell Line | 1.000 | 0.980 | baseline | 0-hop | low | 10 |
| 11 | AB-002 | Antibody | 1.000 | 0.500 | baseline | 0-hop | moderate | 7 |
| 12 | CL-002 | Cell Line | 1.000 | 1.000 | baseline | 0-hop | low | 3 |
| 13 | AB-001 | Antibody | 1.000 | 0.900 | baseline | 0-hop | low | 1 |
| 14 | AM-001 | Animal Model | 1.000 | 0.500 | baseline | 0-hop | low | 2 |
| 15 | AB-003 | Antibody | 1.000 | 0.967 | advanced | 1-hop | high | 6 |

### 6. CL-008: "Find isogenic cell line pairs that differ only in NF1 status"

**Best recall:** 0.451 (Sonnet) | **Overall avg:** 0.114 | **Target:** 51 UUIDs
**Per-model:** Sonnet 0.379, Haiku 0.000, GPT 0.000

**Root Cause: Massive answer set + complex graph traversal through parentDonorId**

The largest target set in the benchmark (51 cell lines). Requires understanding that "isogenic pairs" means cell lines sharing a common parent through `parentDonorId`, then finding HEK293 wild-type/knockout derivatives and patient-derived cell line families. Even Sonnet's best run (achieving 0.451 recall) yields low recall due to the large target set.

### 7. CL-004: "Find NF1 cell lines from black patients"

**Best recall:** 0.556 (Sonnet) | **Overall avg:** 0.200 | **Target:** 9 UUIDs
**Per-model:** Sonnet 0.481, Haiku 0.185, GPT 0.000

**Root Cause: Incomplete donor-to-cell-line join + race value matching**

Despite being classified as baseline/0-hop, the SPARQL equivalent requires knowing exact race category labels (e.g., "Black or African American" vs. "Black") and genetic disorder strings — values the agent must discover through exploration.

### 8. CR-002: "Find human cell lines with the most diverse data types available on the portal"

**Best recall:** 0.667 (Sonnet) | **Overall avg:** 0.267 | **Target:** 3 UUIDs
**Per-model:** Sonnet 0.444, GPT 0.250, Haiku 0.111

**Root Cause: Indirect File-to-CellLine linking via modelSystemName + ranking ambiguity**

Requires cross-resource aggregation and ranking through an indirect join via `modelSystemName` that agents must discover.

### 9. CL-009: "Find cell lines from different tissues of the same donor"

**Best recall:** 1.000 (Haiku) | **Overall avg:** 0.633 | **Target:** 3 UUIDs
**Per-model:** Haiku 0.778, Sonnet 0.667, GPT 0.500

**Root Cause: Incomplete donor grouping in most runs**

Most runs find the same 2 of 3 cell lines. The third cell line belongs to a different donor group with less obviously distinct tissue values. One Haiku run achieved perfect recall, but this was not consistent.

### 10. CL-001: "Show me plexiform neurofibroma cell lines"

**Best recall:** 1.000 | **Overall avg:** 0.980 | **Target:** 10 UUIDs
**Per-model:** Sonnet 1.000, GPT 0.975, Haiku 0.967

A straightforward filter on `manifestation = "Plexiform Neurofibroma"`. Near-perfect across all models with a 0.975 overall average.

### 11. AB-002: "Find antibodies targeting the C-terminal region of neurofibromin"

**Best recall:** 1.000 | **Overall avg:** 0.500 | **Target:** 7 UUIDs
**Per-model:** Haiku 1.000, Sonnet 0.667, GPT 0.000

Strong model bifurcation — Claude succeeds through progressive search widening (C-term patterns, then phospho-specific antibodies at C-terminal positions), while GPT fails completely.

### 12. CL-002: "What hybridoma cell lines are available?"

**Best recall:** 1.000 | **Overall avg:** 1.000 | **Target:** 3 UUIDs
**Per-model:** Haiku 1.000, Sonnet 1.000, GPT 1.000

Trivially answered via `Hybridoma` class query. Perfect recall across all models — validates the benchmark baseline.

### 13. AB-001: "Find drosophila neurofibromin antibodies"

**Best recall:** 1.000 | **Overall avg:** 0.900 | **Target:** 1 UUID
**Per-model:** Haiku 1.000, Sonnet 1.000, GPT 0.750

Single-target precision. Small target sets are unforgiving — any miss drops recall significantly.

### 14. AM-001: "I want animal models to study optic glioma"

**Best recall:** 1.000 | **Overall avg:** 0.500 | **Target:** 2 UUIDs
**Per-model:** Haiku 1.000, Sonnet 0.333, GPT 0.250

Most striking example of **run-to-run instability**. Whether the model searches structured `animalModelOfManifestation` vs. free-text description varies across runs, yielding completely different results. A baseline/0-hop question with only a 0.500 average reveals a major reliability concern.

### 15. AB-003: "Give me antibodies for studying NF1 phosphorylation and post-translational regulation"

**Best recall:** 1.000 | **Overall avg:** 0.967 | **Target:** 6 UUIDs
**Per-model:** Sonnet 1.000, GPT 0.958, Haiku 0.944

Demonstrates that well-structured property values (explicit phospho labels) enable even complex domain queries to achieve high recall.

---

## Cross-Cutting Failure Themes

### 1. Semantic Gap (AM-002, CL-003)
Questions using natural language concepts ("energy expenditure," "normal") that don't map directly to graph properties or values. Requires ontology bridging or domain-specific interpretation.

### 2. Missing/Sparse Data (GR-004)
Schema properties exist but aren't populated, forcing the agent into heuristic reasoning from free-text descriptions — a task more suited to domain experts.

### 3. Constraint Parsing Failure (AM-004)
Models fail to translate implicit constraints in natural language ("mouse model") into explicit SPARQL filters. Models consistently take the "best overall" result rather than respecting species boundaries.

### 4. Multi-Source Evidence Fusion (CR-001)
Answers requiring synthesis from multiple entity types (observations, files, cell lines) with domain knowledge to identify relevant terms.

### 5. Large Target Sets Penalize Partial Understanding (CL-008)
When the target contains 51 UUIDs, even a reasonable approach yields very low recall. The benchmark should consider partial-credit weighting for large answer sets.

### 6. Run-to-Run Instability (AM-001, CL-004)
Same model produces different recall scores across runs. Primary cause: non-deterministic SPARQL query construction — whether the model searches structured properties vs. free-text fields varies per run.

### 7. Model Bifurcation Pattern
Claude models (Sonnet/Haiku) consistently outperform GPT on complex queries. Claude's verbose chain-of-thought approach to schema exploration is better suited to SPARQL-based discovery tasks. On 3 of 7 questions with best recall = 1.0, Claude achieves 1.0 while GPT scores 0.0.

### 8. Baseline Questions That Aren't Easy (CL-003, AM-002, CL-004, AM-001)
Several baseline/low-frustration questions have surprisingly low averages. The "baseline" label reflects portal UI capability, not LLM difficulty — a gap that should inform benchmark design.
