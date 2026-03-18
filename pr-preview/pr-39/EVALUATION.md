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
| `nf_rag` | `evaluation/main/` | `kg-qlever:eval-main-v1` | recall | Research tools discovery — structured SPARQL queries against the portal KG |
| `nf_rag_pubs` | `evaluation/qa/` | `kg-qlever:eval-pubs-v*` (text-indexed) | accuracy, citation_f1 | Publication QA — SPARQL+Text retrieval with passage attribution |

### Running Evals

#### 1. Serve the knowledge graph

Because ground truth is developed with specific snapshots of the data, 
build the local image with the expected content or 
pull and run the appropriate [eval-tagged image](https://github.com/orgs/nf-osi/packages?repo_name=kg-pipeline).

```bash
# For nf_rag (Synapse portal graph only)
docker run -p 7001:7001 ghcr.io/nf-osi/kg-qlever:eval-main-v1

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
python scripts/astabench.py --full             # + gemini-2.5-pro, gpt-5.4
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

The dashboard features:

**For `main` eval**
- Summary table of all runs (sortable, filterable by model)
- Cost vs recall and time vs recall scatter plots
- Breakdown by difficulty level (baseline/advanced) and complexity (0-hop/1-hop/2-hop)
- Category analysis (mutations, animal models, cell lines, etc.)
- User frustration analysis showing recall degradation
- High-impact questions table (queries users struggle with that the KG handles well)

**For `pubs` eval**
- Summary table with accuracy, citation F1, cost, and timing
- Breakdown by difficulty (easy/medium/hard)
- Breakdown by question type (causal, comparative, factual, inferential, methodological)

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
# Main eval dashboard
python scripts/build_site.py evaluation/runs.json --out preview/
# View preview/index.html in a browser

# Pubs eval dashboard
python scripts/build_site.py evaluation/pubs_runs.json --pubs --out preview/
# View preview/pubs.html in a browser
```

Optional arguments for `build_site.py`:
- `--pubs`: Generate pubs eval dashboard (input is `pubs_runs.json`)
- `--out PATH`: Output directory (default: `_site`)
- `--eval-metadata PATH`: Custom metadata file (default: `evaluation/main/eval_tools.yaml`)


