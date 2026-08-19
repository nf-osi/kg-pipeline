# Evaluation Suite

This directory contains two evaluation tracks:

| Track | Directory | Purpose |
|-------|-----------|---------|
| **Research Tools Discovery** | [`main/`](main/) | Structured queries against the Research Tools Portal (facets, text search, graph hops) |
| **Publication QA** | [`qa/`](qa/) | LLM-generated question-answer pairs grounded in PubTator3 full-text papers |

---

## Publication QA Evaluation

To evaluate the overall RAG-based system for publications, we primarily use multiple-choice QA pairs, a similar format to [PaperQA2](https://huggingface.co/datasets/futurehouse/lab-bench/viewer/LitQA2) and [Humanity's Last Exam](https://www.nature.com/articles/s41586-025-09962-4). 
Items are first generated using current frontier models with PubTator3 full-text papers, then further curated and edited by the NF-OSI team.
Each paper has between 5 to 15 questions spanning different difficulty levels and question types.
How well the system performs is based on *both* the ergonomics of retrieval (influenced by what and how things are indexed) as well as the agent chosen for the system.

Important item characteristics:

- **question_type**: `factual`, `causal`, `comparative`, `inferential`, `methodological`, `hypothetical`, `other` — weighted toward factual, comparative, and methodological by design
- **difficulty**: `easy` (single-fact lookup), `medium` (within-passage synthesis), `hard` (cross-passage inference)

#### Curation process

After initial generation, items undergo manual review and editing to address several types of issues that have well-known precedents. 
For example, in an earlier version of Humanity’s Last Exam, ~30% of the text-only chemistry and biology questions had answers with directly conflicting evidence in peer reviewed literature, requiring additional rounds of removal and editing ([ref](https://www.futurehouse.org/research-announcements/hle-exam)).

- **Cross-paper overlap and conflict**: When the same fact appears in multiple papers with potentially different answers, overlapping questions are either removed, deduplicated, or made more specific. An example of a question removed was one with slightly different reported values for NF1 population incidence -- 1:2000 vs 1:2500. An example for a question that was made more specific: For "What is the current treatment for symptomatic PNs?", where one paper says surgery and another says selumetinib, to distinguish questions we can use the keyword "pharmacotherapy". Potential overlaps are noted in `editor_note` field. 
- **Hallucinated content**: LLM-generated ideal answers sometimes include facts not present in the source paper (e.g. have found citation of a specific mutation variant that doesn't appear in the paper). These are corrected against the actual paper text.
- **Vague study anchoring**: Questions like "What was the CS in the eyeblink conditioning experiments?" or "What are the limitations of the isogenic cell line experiments?" are too generic — the same methodology or finding may appear across multiple indexed papers. Questions are rewritten to better anchor to the specific study (e.g. "In the Nf1+/- mouse eyeblink conditioning study, what was used as the CS?", "What are the key limitations acknowledged in the Cancer Pathway Knockout Panel study?"). **This is important because questions are presented in the eval without explicit info on which paper to reference, in order to implicitly test paper selection as well, and during eval the models cannot ask for clarification.** 
- **Difficulty calibration**: Questions that appear simple in isolation but require cross-paper disambiguation are upgraded from `easy` to `medium`.
- **Trivial or obvious questions**: Removal of questions where the answer is obvious without retrieval (e.g. what protein does the NF1 mutation affect) or the distractors are implausible/absurd (e.g. which standard technique was used for proteomics analysis and no distractors are even proteomics assays), as these don't meaningfully test the system or are unlikely to be asked by a real researcher.

#### Limitations

- The dataset so far has undergone only one round of review -- potentially, we may add additional rounds of review to yield a more ideal and tighter final version. 
- Questions may ask to provide answers by drawing conclusions *across passages in the same paper*, but currently *not across papers*; this would be considered a new *very hard* level, potentially for a dataset sequel.
- Ground truth for the exact attribution passage list can be especially hard to finalize.  
- While designed for multiple-choice eval format first and foremost, the dataset should be usable for short-answer eval format as well, though any tweaks needed have not been comprehensively evaluated.
- *question_type* classification is probably still somewhat fudgy.

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

- **Total Papers**: 14
- **Total Questions**: 130
- **Average Questions/Paper**: 9.3

#### By Difficulty
- **Easy**: 31 (23.8%)
- **Medium**: 61 (46.9%)
- **Hard**: 38 (29.2%)

#### By Question Type
- **factual**: 46 (35.4%)
- **methodological**: 31 (23.8%)
- **comparative**: 29 (22.3%)
- **causal**: 14 (10.8%)
- **inferential**: 10 (7.7%)

#### By Author/Model
- **claude-opus-4-6**: 83 (63.8%)
- **gemini-3.1-pro-preview**: 40 (30.8%)
- **gpt-5.4**: 7 (5.4%)

#### By Persona
- **Bench Scientist**: 76 (58.5%)
- **Researcher**: 29 (22.3%)
- **Bioinformatician**: 21 (16.2%)
- **Patient Advocate**: 4 (3.1%)


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

- **`main/dataset_attributes.yaml`**: Question definitions and metadata (stats below)
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

**Dataset Version**: v1.3

Built against **KG v0.2-eval**, `evaluation` profile in `data_sources.yaml`

---

### Dataset Statistics

- **Total Questions**: 46
  - Complete: 46
  - Incomplete/WIP: 0

#### By Complexity
- **0-hop**: 15
- **1-hop**: 17
- **2-hop**: 12
- **3-hop**: 2

#### By Difficulty Level
- **advanced**: 26
- **baseline**: 20

#### By Persona
- **Researcher**: 33
- **Gene Therapy Developer**: 4
- **Program Officer**: 3
- **Bioinformatician**: 2
- **Portal Contributor**: 2
- **Data Curator**: 1
- **Pharmacologist**: 1

*Total unique personas: 7*

#### By Demo Priority
- **high**: 22
- **medium**: 16
- **low**: 8

#### Answerability via Current Technologies

| Technology | Yes | Partial | No |
|------------|-----|---------|-----|
| **Facet Filters** | 11 | 4 | 31 |
| **Text Search** | 14 | 10 | 22 |

#### Ground Truth Availability

- **Automated** (generated from CSV data): 36
- **Manual** (curated, requires interpretation): 10

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
| AM-001 | I want animal models to study optic glioma | baseline | 0-hop | Yes | Yes |
| AM-002 | Help me find animal models suitable for energy expenditure studies | baseline | 0-hop | Partial | Partial |
| AM-003 | Are there any non-mouse mammalian models available? | baseline | 0-hop | Yes | Partial |
| AM-004 | Find mouse model with the earliest observed tumor development | advanced | 1-hop | No | No |
| AM-005 | Find transplantation mouse models (xenografts) and related donor cell lines | advanced | 2-hop | No | No |
| AM-006 | Which animal models develop café-au-lait spots? | advanced | 1-hop | No | No |


#### Cell Line Discovery
*Finding cell lines by type, tissue, manifestation, growth characteristics, donor characteristics*

**Questions: 9/9 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| CL-001 | Show me plexiform neurofibroma cell lines | baseline | 0-hop | Yes | Yes |
| CL-002 | What hybridoma cell lines are available? | baseline | 0-hop | Yes | Yes |
| CL-003 | I need normal schwann cell lines | baseline | 1-hop | Partial | Yes |
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
| AB-003 | Give me antibodies for studying NF1 phosphorylation and post-translational re... | advanced | 1-hop | No | Partial |


#### Genetic Reagent Discovery
*Finding vectors, plasmids, and other genetic tools*

**Questions: 5/5 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| GR-001 | Need CRISPR vectors | baseline | 0-hop | Yes | Yes |
| GR-002 | Need lentiviral vectors for RNAi | baseline | 0-hop | Yes | Yes |
| GR-003 | Find vectors with a CMV promoter | baseline | 0-hop | No | Yes |
| GR-004 | Find NF1 expression vectors compatible with high-copy E. coli systems | advanced | 1-hop | No | Partial |
| GR-005 | Find vectors with resistance markers suitable for mammalian selection | advanced | 1-hop | No | No |


#### By Investigator
*Find tool by investigator*

**Questions: 2/2 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| PI-001 | What tools have been developed by Piotr Topilko | baseline | 1-hop | Yes | Yes |
| PI-002 | How many tools have been funded by GFF? | advanced | 2-hop | No | No |


#### Integrated Resource Queries
*Questions that integrate data across multiple resource types or with additional semantics*

**Questions: 4/4 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| CR-001 | Which cell lines have shown sensitivity to HDAC inhibitors? | advanced | 1-hop | No | Partial |
| CR-002 | Find human cell lines with the most diverse data types available on the portal. | advanced | 2-hop | No | No |
| CR-003 | Find animal models and cell lines that are derived from the same donor | advanced | 2-hop | No | No |
| CR-004 | Does the SZ-NF1 cell line require MTA? Please answer exactly: 'Yes', 'No', 'N... | advanced | 1-hop | No | No |


#### Study Discovery
*Finding studies and their associated data files via study metadata and file-level annotations*

**Questions: 5/5 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| ST-001 | Find studies focused on schwannoma | baseline | 1-hop | Yes | Partial |
| ST-002 | What studies for MPNST have RNA-seq data? | advanced | 2-hop | No | No |
| ST-003 | Which studies have whole genome sequencing data from human female subjects? | advanced | 2-hop | No | No |
| ST-004 | Which schwannomatosis studies have data available for download? | baseline | 1-hop | Yes | Partial |
| ST-005 | What studies on plexiform neurofibroma have drug screening data? | advanced | 2-hop | No | No |


#### Publication & People Discovery
*Finding publications and the people behind them via authorship, ORCID coverage, and Synapse account linkage*

**Questions: 6/6 complete**

| ID | Question | Level | Complexity | Facet | Text Search |
|----|----------|-------|------------|-------|-------------|
| PUB-001 | How many authors are on 'Validating Techniques for Measurement of Cutaneous N... | baseline | 0-hop | Partial | Yes |
| PUB-002 | Which authors for 'Genetically engineered minipigs model the major clinical f... | advanced | 2-hop | No | No |
| PUB-003 | I have Synapse profile 3334263. How many of my publications are on the portal? | advanced | 3-hop | No | No |
| PUB-004 | Some publications are listed by both NF Research Tools Central and the main N... | advanced | 2-hop | No | No |
| PUB-005 | I have Synapse profile 3334263. Among the co-authors on my papers who have an... | advanced | 3-hop | No | No |
| PUB-006 | Across the publications in this knowledge graph, which researcher has the mos... | advanced | 2-hop | No | No |


---

*Generated by `evaluation/generate_eval_tools_readme.py`*

<!-- END AUTO-GENERATED SECTION -->
