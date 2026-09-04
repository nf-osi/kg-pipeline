## Evaluation

Ground-truth datasets live in `evaluation/` — see [`evaluation/README.md`](evaluation/README.md) for dataset details and statistics.

Evaluation uses the [AstaBench](https://github.com/allenai/asta-bench) framework (built on [InspectAI](https://inspect.aisi.org.uk/)).
`astabench` is a git submodule pointing to the [nf-osi fork](https://github.com/nf-osi/asta-bench) that adds NF-specific tasks.

```bash
git submodule update --init              # first time
git submodule update --remote astabench  # pull latest from fork
cd astabench
# install deps
```

### Eval Tasks

| Task | Data | Docker Image | Metrics | Description |
|------|------|-------------|---------|-------------|
| `nf_rag` | `evaluation/main/` | `kg-qlever:build-32` | recall | Research tools discovery — structured SPARQL queries against the portal KG |
| `nf_rag_pubs` | `evaluation/qa/` | `kg-qlever:eval-pubs-v*` (text-indexed) | accuracy, citation_f1 | Publication QA — SPARQL+Text retrieval with passage attribution |

### Running Evals

#### 1. Serve the knowledge graph

Because ground truth is developed with specific snapshots of the data, 
build the local image with the expected content or 
pull and run the appropriate [eval-tagged image](https://github.com/orgs/nf-osi/packages?repo_name=kg-pipeline).

```bash
# For nf_rag (Synapse portal graph only)
# build-32 is the current v0.4-schema baseline (effectively "eval-main-v2";
# not yet retagged in the registry -- see evaluation/main/CHANGELOG.md v2.0).
# It is develop plus a Dagster dependency fix; data_sources.yaml is identical to
# develop, so the graph content matches those pins.
# build-31 (develop) failed to build -- a harmonize step race, fixed in build-32.
# build-30 was the same schema but built off issue-87's older `files` pin (268).
# build-29 was built from a stale mutation_model pin and is broken -- do not use it.
docker run -p 7001:7001 ghcr.io/nf-osi/kg-qlever:build-32

# For nf_rag_pubs (adds full-text index)
docker run -p 7001:7001 ghcr.io/nf-osi/kg-qlever:eval-pubs-v0.1
```

#### 2. Set API keys

Keys can be exported in the shell or placed in a `.env` file at the repo root.

```bash
export ANTHROPIC_API_KEY=...
```

#### 3a. Run nf_rag (Research Tools Discovery)

[![asciicast](https://asciinema.org/a/wIQ6eZrkLEXfLDdN.svg)](https://asciinema.org/a/wIQ6eZrkLEXfLDdN)

The `astabench.py` script can be used for all eval suites. 
The default invocation runs the main benchmark, first merging `evaluation/main/*_ground*.yaml` into `eval_data.yaml` before running eval.

```bash
python scripts/astabench.py --full             # + gemini-3.1-pro-preview, gpt-5.6-luna
python scripts/astabench.py --google           # Gemini only (no Anthropic key needed)
python scripts/astabench.py --openai           # OpenAI only (no Anthropic key needed)
python scripts/astabench.py --google --openai  # both non-Anthropic providers
python scripts/astabench.py --full --epochs 3  # extra args forwarded to inspect eval
```

See [`astabench/evals/nf_rag/README.md`](astabench/evals/nf_rag/README.md) for more details.

#### 3b. Run nf_rag_pubs (Publication QA)

Add `--pubs` for the pub-RAG eval. Similarly to above, this first builds `eval_data.yaml` from `evaluation/qa/qa_PMC*.yaml` files before running eval.

```bash
python scripts/astabench.py --pubs
python scripts/astabench.py --pubs --full
python scripts/astabench.py --pubs --full --epochs 3
```

**Scoring**: `nf_rag_pubs` reports two separate metrics:
- **accuracy** — fraction of questions with the correct multiple-choice answer
- **citation_f1** — mean F1 over `(pmid, passage_num)` attribution tuples, rewarding both precision and recall of cited passages

### Publishing Results

The evaluation results dashboard is automatically published to GitHub Pages via CI when `evaluation/runs.json` is updated. The workflow:

1. **Extract runs**: Use `scripts/extract_runs.py` to aggregate scored runs from `astabench/logs/` into `evaluation/runs.json`
2. **Commit & push**: When `evaluation/runs.json` is pushed to `develop`, GitHub Actions builds and deploys the dashboard
3. **View results**: Dashboard is available at the GitHub Pages URL

The dashboard is a single self-contained `index.html` with one tab per eval
module. All aggregation happens in the browser from an embedded JSON payload, so
the same file works served from Pages or opened straight off disk.

Shared shell:

- Filter row that scopes every figure and table below it
- Headline figure plus KPI row, with the full run tables behind disclosures
- Chart/table toggle on every figure &mdash; no value is reachable only by hovering
- Light and dark themes, each with its own selected colour steps. Series colours
  come from a colourblind-safe categorical palette; the text and accent-as-text
  tokens are stepped to clear WCAG AA (4.5:1) on both the page and card surfaces,
  verified by walking every rendered text node in both themes
- Deep links: `index.html#tools` and `index.html#pubs` (the old `main.html` and
  `pubs.html` URLs redirect to these)

**For `main` eval** (`#tools`)

- Filters: question set version, model
- Recall against cost per question, with the cost/quality frontier emphasised
- Recall by reasoning complexity and a baseline-vs-advanced dumbbell. The complexity,
  level and frustration axes are read from the run data like the categories are, so a
  new bucket (3-hop arrived with the PUB questions) appears without a code change
- Recall by resource category as a heatmap &mdash; **driven by the data, so a newly
  added question category appears automatically and is flagged `new`**
- A dedicated section per new category, listing its questions
- Recall against portal pain (user frustration), with the grading explained inline
- Progress over time as two charts on a shared time axis: best recall, and best
  (lowest) cost per question. Both are recomputed against the selected models and
  span every question-set version
- High-impact questions, all runs, and per-question per-model recall as tables

**For `pubs` eval** (`#pubs`)

- Filters: question phrasing (natural / precise / compare), model
- Answer accuracy against citation F1 as a dumbbell &mdash; the attribution gap
- Citation F1 against cost per question, frontier emphasised
- Citation F1 by difficulty and by question type
- Citation F1 per paper
- All runs and per-paper tables

Only scored runs that covered a complete question set are included. Partial
development runs and runs the harness could not score are dropped when the page
is built, so they never reach the payload — `build_site.py` reports how many it
excluded. The untouched extract, including those runs, is published alongside as
`runs.json`.

Question-set versions are not comparable to each other: a later set adds whole
categories of question rather than making the same questions harder. The
dashboard therefore treats the question set as a filter (defaulting to the
latest) rather than as a table column.

Presentation lives in `scripts/site/` (`dashboard.css`, `charts.js`,
`dashboard.js`) and is inlined into the output at build time. Edit those files
rather than the Python string templates.

#### Adding New Runs

After running evaluations, extract runs to the appropriate JSON file:

```bash
# For nf_rag (main)
python scripts/extract_runs.py
# Reads astabench/logs/, updates evaluation/runs.json

# For nf_rag_pubs
python scripts/extract_runs.py --pubs
# Reads astabench/logs/*nf-rag-pubs*.eval, writes evaluation/pubs_runs.json
```

Then commit and push:

```bash
git add evaluation/runs.json evaluation/pubs_runs.json
git commit -m "Add evaluation runs"
git push origin develop
# CI will automatically build and deploy the updated dashboard
```

Optional arguments for `extract_runs.py`:
- `--pubs`: Extract pubs eval results from `.eval` files instead of main eval
- `--log-dir PATH`: Custom logs directory (default: `astabench/logs`)
- `--eval-metadata PATH`: Custom metadata file (default: `evaluation/main/eval_tools.yaml`)
- `--output PATH`: Output JSON file (default: `evaluation/runs.json` or `evaluation/pubs_runs.json`)

#### Preview Locally

To preview the dashboard:

```bash
python scripts/build_site.py --out preview/
# View preview/index.html in a browser
```

Both modules are built in one pass. Optional arguments for `build_site.py`:
- `runs_json`: Tools eval runs (default: `evaluation/runs.json`)
- `--pubs-json PATH`: Pubs eval runs (default: `evaluation/pubs_runs.json`)
- `--out PATH`: Output directory (default: `_site`)
- `--eval-metadata PATH`: Question attributes (default: `evaluation/main/dataset_attributes.yaml`)
- `--ground-truth-dir PATH`: Where `eval_tools_ground_*.yaml` live, used for the
  wording of questions that do not yet have a `dataset_attributes.yaml` entry
  (default: `evaluation/main`)
- `--qa-dir PATH`: Where `qa_PMC*.yaml` live, used for paper titles (default: `evaluation/qa`)


