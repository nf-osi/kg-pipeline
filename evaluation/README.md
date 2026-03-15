# Evaluation Suite

This directory contains two evaluation tracks:

| Track | Directory | Purpose |
|-------|-----------|---------|
| **Research Tools Discovery** | [`main/`](main/) | Structured queries against the Research Tools Portal (facets, text search, graph hops) |
| **Publication QA** | [`qa/`](qa/) | LLM-generated question-answer pairs grounded in PubTator3 full-text papers |

---

## Publication QA Evaluation

To evaluate publication RAG, we primarily use multiple-choice QA pairs generated from PubTator3 full-text papers in `pubs/pubtator3/`. 
Each paper yields 5-15 questions spanning different difficulty levels and question types.

Important item characteristics:

- **question_type**: `factual`, `causal`, `comparative`, `inferential`, `methodological`, `hypothetical`, `other` — weighted toward factual, comparative, and methodological
- **difficulty**: `easy` (single-fact lookup), `medium` (within-passage synthesis), `hard` (cross-passage inference)

### Files

| File | Description |
|------|-------------|
| `qa/qa.schema.json` | JSON Schema for QA items |
| `qa/generate_qa.py` | Generation script (prompt-only by default, `--generate` to call API) |
| `qa/qa_{PMCID}.yaml` | Generated QA pairs, one file per paper |


### Usage

PubTator3 full-text biocjson must be available locally as input for generation, i.e. in a `pubs` directory. 
The Anthropic default has average cost of ~$0.40/paper; other providers and models can be specified. 
Requires `ANTHROPIC_API_KEY` or `GOOGLE_API_KEY`.

```bash
# Preview prompt for a specific paper
python evaluation/qa/generate_qa.py --pmcid PMC7952412

# Generate QA pairs (calls Anthropic API by default)
python evaluation/qa/generate_qa.py --generate --pmcid PMC7952412

# Generate for the default random-15 selection
python evaluation/qa/generate_qa.py --generate

# Generate QA pairs using the Google Gemini model
python generate_qa.py --generate --provider google

# Validate all generated output files
python evaluation/qa/generate_qa.py --validate-only
```

<!-- BEGIN AUTO-GENERATED QA STATS -->

### Dataset Statistics

- **Total Papers**: 13
- **Total Questions**: 133
- **Average Questions/Paper**: 10.2

#### By Difficulty
- **Easy**: 41 (30.8%)
- **Medium**: 55 (41.4%)
- **Hard**: 37 (27.8%)

#### By Question Type
- **factual**: 53 (39.8%)
- **comparative**: 29 (21.8%)
- **methodological**: 29 (21.8%)
- **causal**: 13 (9.8%)
- **inferential**: 9 (6.8%)

#### By Author/Model
- **claude-opus-4-6**: 92 (69.2%)
- **gemini-3.1-pro-preview**: 41 (30.8%)


<!-- END AUTO-GENERATED QA STATS -->

---

## Research Tools Discovery Evaluation

Benchmark suite for evaluating search/discovery queries across the Research Tools Portal entities using Synapse metadata. 

Important item characteristics:

- Each item represents a user **Persona**, which have descriptions [here](https://docs.google.com/spreadsheets/d/15KSQJn4F7nk8d3v2N9StILFhdyD5AiamTtnfr-QwusQ/edit?gid=0#gid=0)
- **Complexity**: Number of graph hops required (0-hop, 1-hop, 2-hop, 3-hop)
- **Level**: Difficulty/capability level of the question
  - `baseline`: baseline functionality established by current portal technologies and configuration
  - `advanced`: harder questions not handled by portal infra currently (e.g. missing materialization and aggregation, missing integration of additional semantics)
- **Facet**: Whether answerable via portal UI facets alone
  - `Yes`: fully answerable using available facets
  - `Partial`: answerable but requires workarounds, manual filtering, or multiple steps
  - `No`: cannot be answered via facets alone
- **Text Search**: Whether answerable via MySQL text search today
  - `Yes`: fully answerable using text search
  - `Partial`: answerable but with limitations, missing results, or requires knowing exact terms
  - `No`: cannot be answered via text search 


### Files

- **`main/eval_tools.yaml`**: Question definitions and metadata (stats below)
- **`main/eval_tools_ground_auto.yaml`**: Automatically generated ground truth
- **`main/eval_tools_ground_manual.yaml`**: Manually curated ground truth
- **`main/generate_ground_truth.py`**: Ground truth generation script

Ground truth data is split into two files:
- `main/eval_tools_ground_auto.yaml`: Automatically generated from raw CSVs.
- `main/eval_tools_ground_manual.yaml`: Manually curated for complex queries requiring nuanced interpretation.

### Ground Truth Generation

Ground truth IDs for evaluation questions are partially generated using the `main/generate_ground_truth.py` script. 
This script processes the raw CSV data located in `../data/csv` to extract relevant entity IDs for specific queries and outputs them to `eval_tools_ground_auto.yaml`.

#### Identifier Standardization

All ground truth IDs in the generated files should be standardized to use `resourceId` (instead of `cellLineID` or `geneticReagentId`, etc.). 
There is only one question that returns a number (count) instead of uuid(s).

---

<!-- BEGIN AUTO-GENERATED SECTION - DO NOT EDIT MANUALLY -->

### Data Versioning

**Dataset Version**: v1

Data archived at **syn73695746**

---

### Dataset Statistics

- **Total Questions**: 34
  - Complete: 34
  - Incomplete/WIP: 0

#### By Complexity
- **0-hop**: 14
- **1-hop**: 14
- **2-hop**: 6

#### By Difficulty Level
- **advanced**: 17
- **baseline**: 17

#### By Persona
- **Researcher**: 28
- **Gene Therapy Developer**: 4
- **Bioinformatician**: 1
- **Program Officer**: 1

*Total unique personas: 4*

#### By Demo Priority
- **high**: 14
- **medium**: 13
- **low**: 7

#### Answerability via Current Technologies

| Technology | Yes | Partial | No |
|------------|-----|---------|-----|
| **Facet Filters** | 9 | 3 | 22 |
| **Text Search** | 13 | 8 | 13 |

#### Ground Truth Availability

- **Automated** (generated from CSV data): 32
- **Manual** (curated, requires interpretation): 2

---

### Question Categories

#### Discovery via Mutation of Interest
*Finding animal and/or cell line models by mutation*

**Questions: 6/6 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| MUT-001 | What animal or cell line models are available with mutation NM_000267.3(NF1):... | baseline | 1-hop | No | Yes |
| MUT-002 | Find NF1 floxed mice | baseline | 0-hop | No | Yes |
| MUT-003 | Which cell lines have the 'c.104del' sequence variation? | advanced | 1-hop | No | No |
| MUT-004 | Show me animal or cell line models with splice-site variants | advanced | 1-hop | No | Partial |
| MUT-005 | Which cell lines have mutations in multiple genes? | advanced | 1-hop | No | No |
| MUT-006 | Which mutations are available in both animal models and cell lines? | advanced | 2-hop | No | Partial |


#### Animal Model Discovery
*Finding animal models by manifestation, phenotype observations, strain*

**Questions: 6/6 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| AM-001 | What animal models are available for optic glioma? | baseline | 0-hop | Yes | Yes |
| AM-002 | Help me find animal models suitable for energy expenditure studies | baseline | 0-hop | Partial | Partial |
| AM-003 | Are there any non-mouse mammalian models available? | baseline | 0-hop | Yes | Partial |
| AM-004 | Which mouse model has the earliest observed tumor development? | advanced | 1-hop | No | No |
| AM-005 | Find transplantation mouse models (xenografts) and related donor cell lines | advanced | 2-hop | No | No |
| AM-006 | Which animal models develop café-au-lait spots? | advanced | 1-hop | No | No |


#### Cell Line Discovery
*Finding cell lines by type, tissue, manifestation, growth characteristics, donor characteristics*

**Questions: 9/9 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| CL-001 | Show me plexiform neurofibroma cell lines | baseline | 0-hop | Yes | Yes |
| CL-002 | What hybridoma cell lines are available? | baseline | 0-hop | Yes | Yes |
| CL-003 | Find normal schwann cell lines | baseline | 1-hop | Partial | Yes |
| CL-004 | Find NF1 cell lines from black patients | baseline | 0-hop | Yes | Partial |
| CL-005 | Find human cell lines from pediatric donors | baseline | 1-hop | Partial | No |
| CL-006 | Find human lung cell lines for pulmonary toxicity assessment | baseline | 0-hop | No | Yes |
| CL-007 | Find MPNST cell lines with population doubling times under 48 hours | advanced | 0-hop | No | No |
| CL-008 | Find isogenic cell line pairs that differ only in NF1 status | advanced | 2-hop | No | No |
| CL-009 | Find cell lines from different tissues of the same donor | advanced | 1-hop | No | No |


#### Antibody Discovery
*Finding antibodies by target, species reactivity, and epitope specificity*

**Questions: 3/3 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| AB-001 | Find drosophila neurofibromin antibodies | baseline | 0-hop | Yes | Yes |
| AB-002 | Find antibodies targeting the C-terminal region of neurofibromin | baseline | 0-hop | No | Yes |
| AB-003 | Find antibodies for studying NF1 phosphorylation and post-translational regul... | advanced | 1-hop | No | Partial |


#### Genetic Reagent Discovery
*Finding vectors, plasmids, and other genetic tools*

**Questions: 5/5 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| GR-001 | Find CRISPR vectors | baseline | 0-hop | Yes | Yes |
| GR-002 | Find lentiviral vectors for RNAi | baseline | 0-hop | Yes | Yes |
| GR-003 | Find vectors with a CMV promoter | baseline | 0-hop | No | Yes |
| GR-004 | Find NF1 expression vectors compatible with high-copy E. coli systems | advanced | 1-hop | No | Partial |
| GR-005 | Find vectors with resistance markers suitable for mammalian selection | advanced | 1-hop | No | No |


#### By Investigator
*Find tool by investigator*

**Questions: 2/2 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| PI-001 | Find tools developed by Piotr Topilko | baseline | 1-hop | Yes | Yes |
| PI-002 | How many tools have been funded by GFF? | advanced | 2-hop | No | No |


#### Integrated Resource Queries
*Questions that integrate data across multiple resource types or with additional semantics*

**Questions: 3/3 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| CR-001 | Which cell lines have shown sensitivity to HDAC inhibitors? | advanced | 1-hop | No | Partial |
| CR-002 | Find human cell lines with the most diverse data types available on the portal. | advanced | 2-hop | No | No |
| CR-003 | Find animal models and cell lines that are derived from the same donor | advanced | 2-hop | No | No |


---

*Generated by `evaluation/generate_eval_tools_readme.py`*

<!-- END AUTO-GENERATED SECTION -->
