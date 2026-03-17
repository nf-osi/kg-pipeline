#!/usr/bin/env python3
"""Generate evaluation QA pairs from PubTator3 full-text papers.

Builds prompts for an LLM to produce QA pairs grounded in paper passages and
entity annotations.  By default the script prints the prompt to stdout so you
can inspect or pipe it.  Use --generate to call the selected provider API.

Usage:
    # Show prompt for the random-15 selection (first paper only by default)
    python evaluation/qa/generate_qa.py

    # Show prompt for a specific paper
    python evaluation/qa/generate_qa.py --pmcid PMC7952412

    # Show prompts for several papers
    python evaluation/qa/generate_qa.py --pmcid PMC7952412 PMC3578816

    # Actually call the API and write qa_{PMCID}.yaml per paper
    python evaluation/qa/generate_qa.py --generate

    # Generate for one specific paper
    python evaluation/qa/generate_qa.py --generate --pmcid PMC7952412

    # Validate existing output only
    python evaluation/qa/generate_qa.py --validate-only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from pathlib import Path

import anthropic
import jsonschema
from google import genai
from google.genai import types as google_types
from openai import OpenAI
import yaml
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class _FlowList(list):
    """List subclass that YAML will render in flow style: [1, 2, 3]."""


def _flow_list_representer(dumper: yaml.Dumper, data: _FlowList) -> yaml.Node:
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True)


yaml.add_representer(_FlowList, _flow_list_representer)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PUBTATOR_DIR = REPO_ROOT / "pubs" / "pubtator3"
SCHEMA_PATH = Path(__file__).resolve().parent / "qa.schema.json"
OUTPUT_DIR = Path(__file__).resolve().parent

SEED = 42
N_PAPERS = 15
ANTHROPIC_MODEL = "claude-opus-4-6"
GOOGLE_MODEL = "gemini-3.1-pro-preview"
OPENAI_MODEL = "gpt-5.4"
MAX_TOKENS = 8192
MAX_RETRIES = 3
RETRY_DELAY = 30  # seconds

# Section types that carry scientific content.
CONTENT_SECTIONS = {
    "TITLE",
    "ABSTRACT",
    "INTRO",
    "RESULTS",
    "DISCUSS",
    "TABLE",
    "FIG",
    "METHODS",
    "CONCL",
}


def resolve_pmcids(pmcids: list[str]) -> list[Path]:
    """Resolve explicit PMCIDs to their JSON file paths."""
    paths = []
    for pmcid in pmcids:
        p = PUBTATOR_DIR / f"{pmcid}.json"
        if not p.exists():
            logger.error("File not found for %s: %s", pmcid, p)
            sys.exit(1)
        paths.append(p)
    return paths


def select_papers(n: int = N_PAPERS, seed: int = SEED) -> list[Path]:
    """Randomly select *n* PubTator3 JSON files with a fixed seed."""
    all_files = sorted(PUBTATOR_DIR.glob("*.json"))
    rng = random.Random(seed)
    return rng.sample(all_files, min(n, len(all_files)))


def load_paper(path: Path) -> dict:
    """Load a PubTator3 JSON and return the first document object."""
    with open(path) as f:
        data = json.load(f)
    return data["PubTator3"][0]


def extract_content_passages(doc: dict) -> list[dict]:
    """Return content-bearing passages with index, section_type, text, and annotations."""
    passages = []
    for idx, p in enumerate(doc.get("passages", [])):
        section = p.get("infons", {}).get("section_type", "")
        if section not in CONTENT_SECTIONS:
            continue
        text = p.get("text", "").strip()
        if not text:
            continue
        annotations = []
        for a in p.get("annotations", []):
            ann = {
                "text": a.get("text", ""),
                "type": a.get("infons", {}).get("type", ""),
                "identifier": a.get("infons", {}).get("identifier", ""),
            }
            if ann["text"]:
                annotations.append(ann)
        passages.append(
            {
                "index": idx,
                "section_type": section,
                "text": text,
                "annotations": annotations,
            }
        )
    return passages


def build_prompt(pmcid: str, passages: list[dict], schema: dict) -> str:
    """Build the system+user prompt for QA generation."""
    passage_block = ""
    for p in passages:
        ann_str = ""
        if p["annotations"]:
            # Deduplicate annotations by unique (text, type, identifier) tuple
            unique_anns = {}
            for a in p["annotations"]:
                key = (a['text'], a['type'], a['identifier'])
                if key not in unique_anns:
                    unique_anns[key] = f"  - {a['text']} [{a['type']}:{a['identifier']}]"
            ann_str = "\nAnnotated entities:\n" + "\n".join(unique_anns.values())
        passage_block += (
            f"\n--- Passage index {p['index']} [{p['section_type']}] ---\n"
            f"{p['text']}"
            f"{ann_str}\n"
        )

    return f"""You are a scientific QA generation expert. Given the passages and entity
annotations from a paper, generate evaluation question-answer pairs. 
The questions may be presented in free-response / short-answer format or in multiple-choice format,
hence you will provide answers for both formats. 
IMPORTANT: Because questions are drawn and presented randomly from multiple papers
to also test relevant paper selection, have questions be self-contained and sufficiently suggestive 
regarding the desired material and subject entity (gene, protein, disease, organism, etc.); 
don't use phrases like "in this study", "the authors", or "the results shown here" 
that assume the reader already knows which paper is being discussed, 
and don't reference entities too generically -- for example, 
instead of "the cell line developed had which mutations", use "the HS-PSS cell line developed had which mutations".

PAPER: {pmcid}

PASSAGES:
{passage_block}

TASK: Generate between 5 and 15 question-answer pairs for this paper.

REQUIREMENTS:
- At least 1 easy, 1 medium, and 1 hard question.
- At least 2 different question_type values. Weight toward factual, comparative, and methodological questions — the majority of generated pairs should use one of these three types.
- Questions drawn from at least 2 different sections of the paper.
- Each QA pair must include ALL of these fields:
  * question: a precisely worded scientific question
  * user_query: a colloquial, less precise rephrasing of the same question as a real user might type it — use abbreviations, casual phrasing, occasional typos, vague wording, or incomplete sentences
  * ideal: the ideal free-response / short-answer answer, grounded in the passage text
  * choices: array of 3-4 multiple-choice options including the correct answer and plausible distractors (always include "Not in knowledgebase" as one option)
  * correct_choice_index: zero-based index of the correct answer within choices
  * passage_indices: array of 1+ passage indices (from the list above) that provide evidence
  * difficulty: "easy" (single-fact lookup), "medium" (synthesis within a passage), or "hard" (inference or cross-passage reasoning)
  * question_type: "factual" (factoid), "causal" (cause-effect reasoning), "comparative" (contrasting entities or findings), "inferential" (drawing conclusions beyond stated facts), "methodological" (study design, techniques, or limitations), "hypothetical" (counterfactual or speculative scenarios), or "other" (does not fit the above)

- Easy questions should reference a single passage with a directly stated fact.
- Medium questions should require synthesizing information within a passage.
- Hard questions should require cross-passage reasoning and reference multiple passage_indices.
- Distractors in choices must be plausible but clearly wrong when compared to the source text.
- Randomize the position of the correct answer within choices (do not always place it first or last).

Return ONLY a JSON object with a single key "qa_pairs" containing an array of QA objects.
Do not include any text outside the JSON. Do not include fields like pmcid, id, or author — only the fields listed above.
"""


def validate_qa_item(item: dict, schema: dict) -> list[str]:
    """Validate a single QA item against the schema. Returns list of errors."""
    errors = []
    validator = jsonschema.Draft202012Validator(schema)
    for err in validator.iter_errors(item):
        errors.append(f"{err.json_path}: {err.message}")
    return errors


def extract_anthropic_text(response: anthropic.types.Message) -> str:
    """Collect visible text blocks from an Anthropic response."""
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "\n".join(parts).strip()


def extract_openai_text(response) -> str:
    """Return text from an OpenAI Responses API payload."""
    text = getattr(response, "output_text", None)
    if text:
        return text.strip()

    parts = []
    for item in getattr(response, "output", []):
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", []):
            if getattr(content, "type", None) == "output_text":
                parts.append(content.text)
    return "\n".join(parts).strip()


def generate_for_paper(
    client: anthropic.Anthropic | genai.Client | OpenAI,
    path: Path,
    schema: dict,
    provider: str = "anthropic",
    model_name: str = ANTHROPIC_MODEL,
) -> list[dict]:
    """Generate QA pairs for one paper with retries."""
    doc = load_paper(path)
    pmcid = doc.get("pmcid", path.stem)
    passages = extract_content_passages(doc)

    if not passages:
        logger.warning("No content passages found in %s, skipping", pmcid)
        return []

    logger.info(
        "Processing %s: %d content passages, %d total annotations",
        pmcid,
        len(passages),
        sum(len(p["annotations"]) for p in passages),
    )

    prompt = build_prompt(pmcid, passages, schema)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if provider == "anthropic":
                response = client.messages.create(
                    model=model_name,
                    max_tokens=MAX_TOKENS,
                    thinking={"type": "enabled", "budget_tokens": min(4096, MAX_TOKENS)},
                    messages=[{"role": "user", "content": prompt}],
                )
                text = extract_anthropic_text(response)
            elif provider == "google":
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=google_types.GenerateContentConfig(
                        max_output_tokens=MAX_TOKENS,
                        thinking_config=google_types.ThinkingConfig(
                            thinking_level=google_types.ThinkingLevel.HIGH,
                        ),
                    ),
                )
                text = response.text.strip()
            else:
                response = client.responses.create(
                    model=model_name,
                    input=prompt,
                    max_output_tokens=MAX_TOKENS,
                    reasoning={"effort": "high"},
                )
                text = extract_openai_text(response)

            # Strip markdown fences if present.
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

            result = json.loads(text)
            qa_pairs = result.get("qa_pairs", result if isinstance(result, list) else [])

            # Validate each item (without id — we assign that ourselves).
            gen_schema = {
                **schema,
                "additionalProperties": True,
                "required": [r for r in schema["required"] if r not in ("id", "pmcid", "author")],
            }
            valid_pairs = []
            for i, item in enumerate(qa_pairs):
                item.pop("id", None)
                errs = validate_qa_item(item, gen_schema)
                if errs:
                    logger.warning(
                        "%s QA item %d has validation errors: %s", pmcid, i, errs
                    )
                else:
                    valid_pairs.append(item)

            # Assign deterministic IDs: PMC1234567-01, PMC1234567-02, ...
            if valid_pairs:
                for idx, item in enumerate(valid_pairs, 1):
                    item["id"] = f"{pmcid}-{idx:02d}"
                    item["pmcid"] = pmcid
                    item["author"] = model_name
                logger.info(
                    "%s: %d/%d QA pairs passed validation",
                    pmcid,
                    len(valid_pairs),
                    len(qa_pairs),
                )
                return valid_pairs

            logger.warning(
                "%s: no valid QA pairs on attempt %d/%d", pmcid, attempt, MAX_RETRIES
            )

        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(
                "%s: parse error on attempt %d/%d: %s", pmcid, attempt, MAX_RETRIES, exc
            )
        except Exception as exc:
            logger.warning(
                "%s: API error on attempt %d/%d: %s", pmcid, attempt, MAX_RETRIES, exc
            )

        if attempt < MAX_RETRIES:
            logger.info("Retrying in %ds...", RETRY_DELAY)
            time.sleep(RETRY_DELAY)

    logger.error("%s: failed after %d attempts", pmcid, MAX_RETRIES)
    return []


def validate_output_file(path: Path, schema: dict) -> bool:
    """Validate every item in a YAML output file against the schema."""
    if not path.exists():
        logger.error("Output file not found: %s", path)
        return False

    with open(path) as f:
        data = yaml.safe_load(f)

    if isinstance(data, dict):
        items = data.get("questions", [])
    elif isinstance(data, list):
        items = data
    else:
        logger.error("%s: expected a YAML dict or list, got %s", path.name, type(data).__name__)
        return False

    errors = 0
    for i, item in enumerate(items):
        errs = validate_qa_item(item, schema)
        if errs:
            logger.error("%s item %d (%s): %s", path.name, i, item.get("id", "?"), errs)
            errors += 1

    logger.info("Validated %s: %d items, %d errors", path.name, len(items), errors)
    return errors == 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pmcid",
        nargs="+",
        metavar="PMCID",
        help="One or more PMCIDs to process (e.g. PMC7952412). "
        "If omitted, uses the random-15 selection.",
    )
    parser.add_argument(
        "--provider",
        choices=["anthropic", "google", "openai"],
        default="anthropic",
        help="Model provider to use (default: anthropic).",
    )
    parser.add_argument(
        "--model",
        help="Specific model to use. If omitted, defaults to "
        f"{ANTHROPIC_MODEL} for anthropic, {GOOGLE_MODEL} for google, "
        f"or {OPENAI_MODEL} for openai.",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Call the LLM API and write qa_{PMCID}.yaml per paper. "
        "Without this flag the prompt is printed to stdout.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing output file without generating.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    schema = json.loads(SCHEMA_PATH.read_text())

    if args.validate_only:
        files = sorted(OUTPUT_DIR.glob("qa_PMC*.yaml"))
        if not files:
            logger.error("No qa_PMC*.yaml files found in %s", OUTPUT_DIR)
            sys.exit(1)
        ok = all(validate_output_file(f, schema) for f in files)
        sys.exit(0 if ok else 1)

    # Resolve paper list.
    if args.pmcid:
        papers = resolve_pmcids(args.pmcid)
    else:
        papers = select_papers()

    logger.info("Selected %d papers: %s", len(papers), [p.stem for p in papers])

    if not args.generate:
        # Prompt-only mode: print the prompt for each paper and exit.
        for paper_path in papers:
            doc = load_paper(paper_path)
            pmcid = doc.get("pmcid", paper_path.stem)
            passages = extract_content_passages(doc)
            if not passages:
                logger.warning("No content passages in %s, skipping", pmcid)
                continue
            prompt = build_prompt(pmcid, passages, schema)
            print(prompt)
        return

    model_name = args.model
    if not model_name:
        if args.provider == "google":
            model_name = GOOGLE_MODEL
        elif args.provider == "openai":
            model_name = OPENAI_MODEL
        else:
            model_name = ANTHROPIC_MODEL

    if args.provider == "anthropic":
        client = anthropic.Anthropic()
    elif args.provider == "google":
        client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
    else:
        client = OpenAI()

    total_pairs = 0
    all_ok = True
    for i, paper_path in enumerate(papers, 1):
        pmcid = paper_path.stem
        logger.info("=== Paper %d/%d: %s ===", i, len(papers), pmcid)
        doc = load_paper(paper_path)
        pairs = generate_for_paper(client, paper_path, schema, provider=args.provider, model_name=model_name)

        # Order keys for readability; passage_indices as flow list.
        ordered_pairs = [
            {k: (_FlowList(item[k]) if k == "passage_indices" else item[k]) for k in (
                "id", "pmcid", "author", "question", "user_query",
                "ideal", "choices", "correct_choice_index",
                "passage_indices", "difficulty", "question_type",
            )}
            for item in pairs
        ]
        output_data = {
            "title": doc["passages"][0].get("text", ""),
            "pmcid": pmcid,
            "pmid": str(doc.get("pmid", "")),
            "reviewer": None,
            "questions": ordered_pairs,
        }
        base = OUTPUT_DIR / f"qa_{pmcid}.yaml"
        if base.exists():
            v = 2
            while (OUTPUT_DIR / f"qa_{pmcid}_v{v}.yaml").exists():
                v += 1
            out_path = OUTPUT_DIR / f"qa_{pmcid}_v{v}.yaml"
        else:
            out_path = base
        with open(out_path, "w") as f:
            yaml.dump(
                output_data, f,
                default_flow_style=False, allow_unicode=True,
                sort_keys=False, width=120,
            )
        logger.info("Wrote %d QA pairs to %s", len(pairs), out_path)

        if pairs and not validate_output_file(out_path, schema):
            all_ok = False

        total_pairs += len(pairs)

    logger.info("Done: %d papers, %d total QA pairs", len(papers), total_pairs)
    if not all_ok:
        logger.warning("Some items failed validation — review output")
        sys.exit(1)


if __name__ == "__main__":
    main()
