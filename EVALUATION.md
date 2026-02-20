## Evaluation

Ground-truth datasets live in `evaluation/<dataset>/`.

Evaluation uses the [AstaBench](https://github.com/allenai/asta-bench) framework (built on [InspectAI](https://inspect.aisi.org.uk/)).
`astabench` is a git submodule pointing to the [nf-osi fork](https://github.com/nf-osi/asta-bench) that adds NF-specific tasks.

```bash
git submodule update --init              # first time
git submodule update --remote astabench  # pull latest from fork
cd astabench
# install deps
```

The convenience script for running eval will process ground truth files into the single
`eval_data.yaml` expected and runs benchmarking with Anthropic models by default.

Steps (from the repo root):
1. Serve the knowledge graph; because ground truth is developed with specific snapshots of the data,
pull and run the appropriate [eval-tagged image](https://github.com/orgs/nf-osi/packages?repo_name=kg-pipeline).

For example:

```bash
docker run -p 7001:7001 ghcr.io/nf-osi/kg-qlever:eval-main-v1
```

or

```bash
docker run -p 7001:7001 ghcr.io/nf-osi/kg-qlever:eval-paperqa-v0.1
```

2. Set API keys (`ANTHROPIC_API_KEY` for standard, additional keys for `--full`/`--google`/`--openai`).
Keys can be exported in the shell or placed in a `.env` file at the repo root.

[![asciicast](https://asciinema.org/a/wIQ6eZrkLEXfLDdN.svg)](https://asciinema.org/a/wIQ6eZrkLEXfLDdN)

```bash
export ANTHROPIC_API_KEY=...                   # required
python scripts/astabench.py
```

```bash
python scripts/astabench.py --full             # + gemini-2.5-pro, gpt-5.2
python scripts/astabench.py --google       # Gemini only (no Anthropic key needed)
python scripts/astabench.py --openai       # OpenAI only (no Anthropic key needed)
python scripts/astabench.py --google --openai  # both non-Anthropic providers
python scripts/astabench.py --full --epochs 3  # extra args forwarded to inspect eval
```

See [`astabench/evals/nf_rag/README.md`](astabench/evals/nf_rag/README.md) for more details.

### Limitations

This evaluates retrieval from one knowledge source in isolation.
In production, an agent switches between two or more sources (e.g. the KG and a vector DB that indexes help documentation).
