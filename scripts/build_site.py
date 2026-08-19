#!/usr/bin/env python3
"""Build the NF knowledge graph evaluation dashboard.

Reads the extracted run summaries (``evaluation/runs.json`` for the research
tools discovery eval, ``evaluation/pubs_runs.json`` for the publication QA
eval) plus the question metadata that sits alongside the ground truth, and
emits a single self-contained ``index.html``.

The page is one artifact with a tab per eval module. All aggregation and
filtering happens client side from an embedded JSON payload, so the same file
works from a web server or straight off disk. Presentation lives in
``scripts/site/`` and is inlined at build time.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - yaml is required for question metadata
    yaml = None  # type: ignore[assignment]

SITE_DIR = Path(__file__).parent / "site"

# --------------------------------------------------------------------------- #
# Static labelling
# --------------------------------------------------------------------------- #

# Column order for the resource-category views. Any category found in the run
# data but missing here is appended alphabetically, so a newly added module
# shows up without a code change.
CATEGORY_ORDER = ["MUT", "AM", "CL", "AB", "GR", "ST", "PUB", "PI", "CR"]

# A question set's expected size is taken as the largest sample count recorded
# for it. That breaks down when a set has only targeted development runs: the
# largest is then tiny, and a 5-question run would certify itself as complete.
# Every real full set here has been 34-46 questions and every development run
# under 10, so a run must also clear this floor to count as complete. A set with
# no complete run then simply does not appear as a filter option.
MIN_FULL_RUN_SAMPLES = 20

CATEGORY_LABELS = {
    "MUT": "Mutation",
    "AM": "Animal model",
    "CL": "Cell line",
    "AB": "Antibody",
    "GR": "Genetic reagent",
    "PI": "Investigator",
    "CR": "Cross-resource",
    "ST": "Study",
    "PUB": "Publication & people",
}

# Longer framing shown when a category is new in the latest question set.
CATEGORY_BLURBS = {
    "PUB": (
        "Publications and the people behind them: author counts, ORCID coverage, which "
        "authors are Synapse users, publications cross-listed by two portals, and "
        "co-authorship reach. These questions test whether the agent treats ORCID links "
        "as the partial subset they are rather than as the full author list."
    ),
    "ST": (
        "Study-level discovery: finding studies and their associated data files through "
        "study metadata and file-level annotations."
    ),
}

# Buckets for the level / complexity / frustration views. Which buckets appear
# is read from the run data, exactly as categories are: the question set gains
# new ones over time — complexity in particular is an open-ended hop count — and
# a hardcoded list would drop them silently.
LEVEL_LABELS = {"baseline": "Baseline", "advanced": "Advanced"}
LEVEL_ORDER = ["baseline", "advanced"]

COMPLEXITY_LABELS = {
    "0-hop": "Direct lookup",
    "1-hop": "One hop",
    "2-hop": "Two hops",
    "3-hop": "Three hops",
}
COMPLEXITY_ORDER = ["0-hop", "1-hop", "2-hop", "3-hop"]

FRUSTRATION_LABELS = {
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
    "very_high": "Very high",
}
FRUSTRATION_ORDER = ["low", "moderate", "high", "very_high"]

FRUSTRATION_HELP = [
    ["Low", "Answerable with minimal effort through facets or text search."],
    ["Moderate", "Needs the right approach, extra steps, or domain knowledge."],
    ["High", "Incomplete or misleading results, painful workarounds, or a single weak path."],
    ["Very high", "Cannot be answered at all, or needs expert workarounds most users would never find."],
]

PUBS_DIFFICULTIES = [("easy", "Easy"), ("medium", "Medium"), ("hard", "Hard")]

PUBS_STYLES = [
    ("user_query", "Natural", "Phrased the way a user would actually ask"),
    ("precise", "Precise", "Phrased with the exact terminology of the paper"),
]

HIGH_IMPACT_THRESHOLD = 0.95

TOOLS_ABOUT = [
    "Each question is answered by an agent with SPARQL access to the NF portal knowledge "
    "graph. Ground truth is a curated set of resource identifiers, and the score is recall "
    "— the share of expected identifiers the agent returned. Precision is deliberately not "
    "scored here: the task is discovery, where a missed resource costs a researcher more "
    "than an extra one to skim.",
    "Question sets are versioned. A later set is not a harder version of the earlier one — "
    "it adds whole categories of question — so recall is only comparable within a single "
    "set. That is why the question set is a filter rather than a column.",
    "Only scored runs that covered a complete question set appear here. Development runs "
    "over part of a set, and runs the harness could not score, are excluded when this page "
    "is built, since a partial run is not comparable to a full one. The untouched extract, "
    "including those runs, is published alongside as runs.json.",
    "Every question also carries an estimate of how painful it is on today's portal, which "
    "is what the high-impact table is built from: questions users struggle with now, and "
    "that the graph already answers well.",
]

PUBS_ABOUT = [
    "The agent answers multiple-choice questions over full-text publications, retrieved "
    "with SPARQL over a text-indexed copy of the graph.",
    "Answer accuracy is the share of questions answered correctly. Citation F1 is the mean "
    "F1 over (PMID, passage) attribution tuples — precision is the share of cited passages "
    "that were relevant, recall the share of expected passages that were cited.",
    "Every question exists in two phrasings. Precise phrasing (question_style "
    "\"precise\") uses the paper's own terminology; natural phrasing (\"user_query\") is "
    "how a researcher would actually ask, with the ambiguity that implies. Scores are "
    "close, and natural phrasing is the default view because it is the realistic one.",
]


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _iso_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return str(value)[:10]


def _duration_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    except (ValueError, TypeError):
        return None


def _version_label(value) -> str:
    if value is None or value == "":
        return "unversioned"
    text = str(value)
    return text if text.startswith("v") else f"v{text}"


def _sort_key(started_at: str | None) -> str:
    return started_at or ""


def _per_question(cost: float | None, samples: int | None) -> float | None:
    if cost is None or not samples:
        return None
    return cost / samples


def _buckets(
    runs: list[dict],
    field: str,
    prefix: str,
    labels: dict[str, str],
    order: list[str],
) -> list[dict]:
    """Buckets the runs actually scored, in a stable, sensible order.

    Known values keep their curated order and label. An unrecognised one still
    appears rather than vanishing: an ``N-hop`` value sorts by N, anything else
    sorts last alphabetically, and both fall back to the raw value as a label.
    """
    present: set[str] = set()
    for run in runs:
        for key in run[field]:
            head, sep, name = key.partition("/")
            if sep and head == prefix and name:
                present.add(name)

    def rank(name: str) -> tuple[int, int, str]:
        if name in order:
            return (0, order.index(name), "")
        hops = name.partition("-")[0]
        return (1, int(hops) if hops.isdigit() else 10**6, name)

    return [
        {"key": f"{prefix}/{name}", "label": labels.get(name, name)}
        for name in sorted(present, key=rank)
    ]


def _clean(value):
    """Drop NaN/inf so the payload stays valid JSON."""
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
    return value


# --------------------------------------------------------------------------- #
# Question metadata
# --------------------------------------------------------------------------- #

def load_question_metadata(path: Path) -> dict[str, dict]:
    """Per-question attributes from ``dataset_attributes.yaml``."""
    if yaml is None or not path.exists():
        if yaml is None:
            print("Warning: pyyaml not installed; question metadata skipped", file=sys.stderr)
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:
        print(f"Warning: failed to parse {path}: {exc}", file=sys.stderr)
        return {}
    out: dict[str, dict] = {}
    for component in data.get("components", []) or []:
        for question in component.get("questions", []) or []:
            qid = question.get("id")
            if not qid:
                continue
            out[qid] = {
                "question": question.get("question", ""),
                "level": question.get("level", ""),
                "complexity": question.get("complexity", ""),
                "frustration": question.get("user_frustration", ""),
                "component": component.get("name", ""),
            }
    return out


def load_ground_truth_questions(paths: list[Path]) -> dict[str, str]:
    """Question text for ids that only exist in the ground-truth files.

    The newest question categories are curated straight into the ground truth
    before they get an entry in ``dataset_attributes.yaml``, so this is how the
    dashboard learns their wording.
    """
    if yaml is None:
        return {}
    out: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            continue
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except Exception as exc:
            print(f"Warning: failed to parse {path}: {exc}", file=sys.stderr)
            continue
        for qid, entry in (data.get("ground_truth") or {}).items():
            if isinstance(entry, dict) and entry.get("question") and qid not in out:
                out[qid] = entry["question"]
    return out


def load_paper_metadata(qa_dir: Path) -> dict[str, dict]:
    """Paper titles and question counts from ``evaluation/qa/qa_PMC*.yaml``."""
    if yaml is None or not qa_dir.exists():
        return {}
    out: dict[str, dict] = {}
    for path in sorted(qa_dir.glob("qa_PMC*.yaml")):
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except Exception as exc:
            print(f"Warning: failed to parse {path}: {exc}", file=sys.stderr)
            continue
        pmcid = data.get("pmcid") or path.stem.replace("qa_", "")
        out[pmcid] = {
            "title": data.get("title", ""),
            "questions": len(data.get("questions", []) or []),
            "pmid": data.get("pmid", ""),
        }
    return out


# --------------------------------------------------------------------------- #
# Model registry — one colour slot per model, assigned once
# --------------------------------------------------------------------------- #

def build_model_registry(tools_runs: list[dict], pubs_runs: list[dict]) -> list[dict]:
    """Assign each model a categorical slot in order of first appearance.

    Slots are stable as new models arrive (a new model takes the next free
    slot), and are shared across both tabs, so a model keeps one colour
    everywhere. Colour therefore follows the model, never its current rank.
    """
    first_seen: dict[str, str] = {}
    for run in tools_runs + pubs_runs:
        model = run.get("model")
        if not model:
            continue
        stamp = _sort_key(run.get("started_at"))
        if model not in first_seen or stamp < first_seen[model]:
            first_seen[model] = stamp

    ordered = sorted(first_seen, key=lambda m: (first_seen[m], m))
    registry = []
    for index, model in enumerate(ordered):
        provider, _, short = model.partition("/")
        if not short:
            provider, short = "", model
        registry.append(
            {
                "id": model,
                "label": short,
                "provider": provider,
                "slot": index,
                # Eight categorical slots is the ceiling; past it the palette
                # cannot keep pairs apart, so the tail recedes to gray rather
                # than inventing a ninth hue.
                "color": f"var(--series-{index + 1})" if index < 8 else "var(--muted-mark)",
            }
        )
    if len(ordered) > 8:
        print(
            f"Warning: {len(ordered)} models but only 8 categorical slots; "
            "models past the eighth share the de-emphasis gray",
            file=sys.stderr,
        )
    return registry


# --------------------------------------------------------------------------- #
# Tools module (nf_rag)
# --------------------------------------------------------------------------- #

def _question_scores(run: dict) -> dict[str, float]:
    """Per-question scores, unioned over whichever sample lists are present."""
    scores: dict[str, float] = {}
    for key in ("level_samples", "complexity_samples", "frustration_samples", "question_samples"):
        for sample in run.get(key) or []:
            qid = sample.get("id")
            if qid and sample.get("score") is not None:
                scores[qid] = sample["score"]
    return scores


def build_tools_payload(
    runs_raw: list[dict],
    question_meta: dict[str, dict],
    ground_truth_text: dict[str, str],
) -> dict:
    # --- question-set sizes, measured over every recorded run --------------- #
    # The expected size of a set has to come from the full extract: it is the
    # yardstick a run is judged complete against, so it must be known before
    # anything is filtered out.
    version_samples: dict[str, int] = {}
    version_first: dict[str, str] = {}
    for run in runs_raw:
        version = _version_label(run.get("task_version"))
        samples = run.get("total_samples") or 0
        version_samples[version] = max(version_samples.get(version, 0), samples)
        stamp = _sort_key(run.get("started_at"))
        if version not in version_first or stamp > version_first[version]:
            version_first[version] = stamp

    # --- runs: scored and complete only ------------------------------------- #
    # Development runs that cover part of a set, or that the harness could not
    # score, are dropped here rather than shown and dimmed. They are not
    # comparable to a full run, so there is nothing useful to do with them on a
    # dashboard. The untouched extract stays available as runs.json.
    runs: list[dict] = []
    excluded = 0
    for index, raw in enumerate(runs_raw):
        version = _version_label(raw.get("task_version"))
        samples = raw.get("total_samples")
        expected = version_samples.get(version, 0)
        score = _clean(raw.get("score"))
        threshold = max(MIN_FULL_RUN_SAMPLES, round(expected * 0.9))
        if score is None or not samples or samples < threshold:
            excluded += 1
            continue
        cost = _clean(raw.get("cost"))
        runs.append(
            {
                "id": raw.get("run") or f"run-{index}",
                "model": raw.get("model") or "unknown",
                "version": version,
                "date": _iso_date(raw.get("started_at")),
                "commit": raw.get("git_commit") or "",
                "samples": samples,
                "score": score,
                "stderr": _clean(raw.get("score_stderr")),
                "cost": cost,
                "costPerQuestion": _clean(_per_question(cost, samples)),
                "duration": _clean(_duration_seconds(raw.get("started_at"), raw.get("completed_at"))),
                "avgSampleTime": _clean(raw.get("avg_sample_time")),
                "minSampleTime": _clean(raw.get("min_sample_time")),
                "maxSampleTime": _clean(raw.get("max_sample_time")),
                "tokIn": raw.get("input_tokens"),
                "tokOut": raw.get("output_tokens"),
                "tokCacheWrite": raw.get("cache_write_tokens"),
                "tokCacheRead": raw.get("cache_read_tokens"),
                "tokTotal": raw.get("total_tokens"),
                "difficulty": {k: _clean(v) for k, v in (raw.get("difficulty_scores") or {}).items()},
                "category": {k: _clean(v) for k, v in (raw.get("category_scores") or {}).items()},
                "frustration": {k: _clean(v) for k, v in (raw.get("frustration_scores") or {}).items()},
                "questionScores": _question_scores(raw),
            }
        )

    # Only offer a question set as a filter if a complete run actually used it.
    version_order = sorted(
        {r["version"] for r in runs}, key=lambda v: version_first.get(v, "")
    )
    latest_version = version_order[-1] if version_order else None
    versions = [
        {
            "id": version,
            "label": version,
            "questions": version_samples[version],
            "isLatest": version == latest_version,
        }
        for version in version_order
    ]

    # --- categories, discovered from the data ------------------------------ #
    seen_versions: dict[str, set[str]] = {}
    for run in runs:
        for key in run["category"]:
            seen_versions.setdefault(key, set()).add(run["version"])

    def category_rank(key: str) -> tuple[int, str]:
        code = key.split("/", 1)[-1]
        if code in CATEGORY_ORDER:
            return (CATEGORY_ORDER.index(code), code)
        return (len(CATEGORY_ORDER), code)

    # question ids per category prefix, across both metadata sources
    all_question_ids = set(question_meta) | set(ground_truth_text)
    per_category_ids: dict[str, list[str]] = {}
    for qid in sorted(all_question_ids):
        code = qid.rsplit("-", 1)[0]
        per_category_ids.setdefault(code, []).append(qid)

    categories = []
    for key in sorted(seen_versions, key=category_rank):
        code = key.split("/", 1)[-1]
        # New = the category has only ever been scored on the latest set.
        is_new = latest_version is not None and seen_versions[key] == {latest_version} and len(version_order) > 1
        ids = per_category_ids.get(code, [])
        entry = {
            "key": key,
            "code": code,
            "label": CATEGORY_LABELS.get(code, code),
            "isNew": is_new,
            "questions": len(ids),
        }
        if is_new:
            entry["blurb"] = CATEGORY_BLURBS.get(code)
            entry["items"] = [
                {
                    "id": qid,
                    "question": (question_meta.get(qid) or {}).get("question")
                    or ground_truth_text.get(qid, ""),
                }
                for qid in ids
            ]
        categories.append(entry)

    # --- question table ---------------------------------------------------- #
    questions = []
    for qid in sorted(all_question_ids):
        code = qid.rsplit("-", 1)[0]
        meta = question_meta.get(qid) or {}
        questions.append(
            {
                "id": qid,
                "category": code,
                "categoryLabel": CATEGORY_LABELS.get(code, code),
                "question": meta.get("question") or ground_truth_text.get(qid, ""),
                "level": meta.get("level", ""),
                "complexity": meta.get("complexity", ""),
                "frustration": meta.get("frustration", ""),
            }
        )

    # --- high-impact questions -------------------------------------------- #
    # Questions that hurt on today's portal. Per-model recall is kept raw so
    # the client can recompute "best" against the current model selection.
    frustration_of: dict[str, str] = {}
    for run in runs_raw:
        for sample in run.get("frustration_samples") or []:
            if sample.get("id") and sample.get("frustration"):
                frustration_of[sample["id"]] = sample["frustration"]

    by_question: dict[str, dict[str, list[float]]] = {}
    for run in runs:
        for qid, score in run["questionScores"].items():
            by_question.setdefault(qid, {}).setdefault(run["model"], []).append(score)

    high_impact = []
    for qid, per_model in by_question.items():
        frustration = frustration_of.get(qid) or (question_meta.get(qid) or {}).get("frustration", "")
        if frustration not in ("high", "very_high"):
            continue
        means = {
            model: sum(values) / len(values)
            for model, values in per_model.items()
            if values
        }
        if not means or max(means.values()) < HIGH_IMPACT_THRESHOLD:
            continue
        meta = question_meta.get(qid) or {}
        code = qid.rsplit("-", 1)[0]
        high_impact.append(
            {
                "id": qid,
                "question": meta.get("question") or ground_truth_text.get(qid, ""),
                "frustration": "Very high" if frustration == "very_high" else "High",
                "complexity": meta.get("complexity", ""),
                "category": CATEGORY_LABELS.get(code, code),
                "byModel": means,
            }
        )
    high_impact.sort(key=lambda q: (-max(q["byModel"].values()), q["id"]))

    task_names = [r.get("task_name") for r in runs_raw if r.get("task_name")]
    task = task_names[-1].rpartition("/")[2] if task_names else "nf_rag"

    return {
        "task": task,
        "excluded": excluded,
        "versions": versions,
        "categories": categories,
        "levels": _buckets(runs, "difficulty", "level", LEVEL_LABELS, LEVEL_ORDER),
        "complexities": _buckets(
            runs, "difficulty", "complexity", COMPLEXITY_LABELS, COMPLEXITY_ORDER
        ),
        "frustrations": _buckets(
            runs, "frustration", "frustration", FRUSTRATION_LABELS, FRUSTRATION_ORDER
        ),
        "frustrationHelp": FRUSTRATION_HELP,
        "runs": runs,
        "questions": questions,
        "highImpact": high_impact,
        "highImpactThreshold": HIGH_IMPACT_THRESHOLD,
        "about": TOOLS_ABOUT,
    }


# --------------------------------------------------------------------------- #
# Pubs module (nf_rag_pubs)
# --------------------------------------------------------------------------- #

def build_pubs_payload(runs_raw: list[dict], papers_meta: dict[str, dict]) -> dict | None:
    if not runs_raw:
        return None

    runs = []
    excluded = 0
    for index, raw in enumerate(runs_raw):
        cost = _clean(raw.get("cost"))
        samples = raw.get("samples")
        total = raw.get("total_samples")
        # same rule as the tools eval: only scored, complete runs are shown
        if raw.get("status") != "success" or not samples or (total and samples < total):
            excluded += 1
            continue
        # citation_f1 is the current key; older extracts wrote passage_f1
        f1 = _clean(raw.get("citation_f1") if raw.get("citation_f1") is not None else raw.get("passage_f1"))
        f1_stderr = _clean(
            raw.get("citation_f1_stderr")
            if raw.get("citation_f1_stderr") is not None
            else raw.get("passage_f1_stderr")
        )
        runs.append(
            {
                "id": raw.get("log_file") or f"pubs-{index}",
                "model": raw.get("model") or "unknown",
                "style": raw.get("question_style") or "unknown",
                "status": raw.get("status") or "",
                "samples": samples,
                "totalSamples": raw.get("total_samples"),
                "version": _version_label(raw.get("task_version")),
                "date": _iso_date(raw.get("started_at")),
                "accuracy": _clean(raw.get("accuracy")),
                "accuracyStderr": _clean(raw.get("accuracy_stderr")),
                "f1": f1,
                "f1Stderr": f1_stderr,
                "cost": cost,
                "costPerQuestion": _clean(_per_question(cost, samples)),
                "duration": _clean(_duration_seconds(raw.get("started_at"), raw.get("completed_at"))),
                "avgSampleTime": _clean(raw.get("avg_sample_time")),
                "minSampleTime": _clean(raw.get("min_sample_time")),
                "maxSampleTime": _clean(raw.get("max_sample_time")),
                "tokIn": raw.get("input_tokens"),
                "tokOut": raw.get("output_tokens"),
                "tokCacheWrite": raw.get("input_tokens_cache_write"),
                "tokCacheRead": raw.get("input_tokens_cache_read"),
                "tokTotal": raw.get("total_tokens"),
                "difficultyAcc": {k: _clean(v) for k, v in (raw.get("difficulty_accuracy") or {}).items()},
                "difficultyF1": {k: _clean(v) for k, v in (raw.get("difficulty_f1") or {}).items()},
                "qtypeAcc": {k: _clean(v) for k, v in (raw.get("question_type_accuracy") or {}).items()},
                "qtypeF1": {k: _clean(v) for k, v in (raw.get("question_type_f1") or {}).items()},
                "paperAcc": {k: _clean(v) for k, v in (raw.get("paper_accuracy") or {}).items()},
                "paperF1": {k: _clean(v) for k, v in (raw.get("paper_f1") or {}).items()},
            }
        )

    if not runs:
        return None

    qtype_keys = sorted({key for run in runs for key in run["qtypeF1"]})
    paper_ids = sorted({key for run in runs for key in run["paperF1"]})

    present_styles = {run["style"] for run in runs}
    styles = [
        {"id": sid, "label": label, "title": title}
        for sid, label, title in PUBS_STYLES
        if sid in present_styles
    ]
    for sid in sorted(present_styles):
        if not any(s["id"] == sid for s in styles):
            styles.append({"id": sid, "label": sid, "title": sid})
    default_style = "user_query" if any(s["id"] == "user_query" for s in styles) else styles[0]["id"]

    papers = []
    for pid in paper_ids:
        meta = papers_meta.get(pid, {})
        papers.append(
            {
                "id": pid,
                "label": meta.get("title", ""),
                "questions": meta.get("questions"),
            }
        )

    question_count = max(
        [run["totalSamples"] or 0 for run in runs]
        + [sum(p["questions"] or 0 for p in papers)]
    )

    # the task name is not recorded in the pubs extract, so read it off a log name
    task = "nf_rag_pubs"
    for raw in runs_raw:
        match = re.search(r"(nf[-_]rag[-_]pubs)", str(raw.get("log_file", "")))
        if match:
            task = match.group(1).replace("-", "_")
            break

    return {
        "task": task,
        "excluded": excluded,
        "runs": runs,
        "styles": styles,
        "defaultStyle": default_style,
        "styleLabel": {s["id"]: s["label"] for s in styles},
        "difficulties": [
            {"key": k, "label": v}
            for k, v in PUBS_DIFFICULTIES
            if any(k in run["difficultyF1"] for run in runs)
        ],
        "qtypes": [{"key": k, "label": k.replace("_", " ").capitalize()} for k in qtype_keys],
        "papers": papers,
        "paperCount": len(papers),
        "questionCount": question_count,
        "about": PUBS_ABOUT,
    }


# --------------------------------------------------------------------------- #
# HTML shell
# --------------------------------------------------------------------------- #

REDIRECT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Moved &mdash; NF Knowledge Graph Evaluation</title>
  <meta http-equiv="refresh" content="0; url=index.html#{anchor}" />
  <link rel="canonical" href="index.html#{anchor}" />
  <style>
    body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 4rem auto;
           max-width: 34rem; padding: 0 1.5rem; color: #0b0b0b; background: #f9f9f7; }}
  </style>
</head>
<body>
  <p>This dashboard now lives on one page.
     <a href="index.html#{anchor}">Continue to {name}</a>.</p>
</body>
</html>
"""


def _embed_json(payload: dict) -> str:
    """Serialise for a <script type="application/json"> block."""
    text = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _read_asset(name: str) -> str:
    path = SITE_DIR / name
    if not path.exists():
        raise SystemExit(f"Missing site asset: {path}")
    return path.read_text()


def render_html(payload: dict) -> str:
    css = _read_asset("dashboard.css")
    charts_js = _read_asset("charts.js")
    dashboard_js = _read_asset("dashboard.js")
    generated = payload["generated"]

    tools_runs = len(payload["tools"]["runs"])
    pubs_runs = len(payload["pubs"]["runs"]) if payload.get("pubs") else 0
    description = (
        "Benchmark results for agents answering neurofibromatosis research questions "
        f"against the NF portal knowledge graph — {tools_runs} research-tools discovery "
        f"runs and {pubs_runs} publication QA runs."
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>NF Knowledge Graph Evaluation</title>
<meta name="description" content="{description}" />
<meta name="color-scheme" content="light dark" />
<style>
{css}
</style>
</head>
<body>

<header class="masthead">
  <div class="masthead-inner">
    <div class="brand">
      <h1 class="brand-title">
        <span class="brand-mark">NF&nbsp;KG</span>
        <span>Evaluation</span>
      </h1>
    </div>
    <div class="masthead-tools">
      <span class="stamp">Updated {generated}</span>
      <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Switch theme">
        <svg class="icon-light" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"
             stroke-linecap="round" aria-hidden="true">
          <circle cx="8" cy="8" r="3.1" />
          <path d="M8 1v1.6M8 13.4V15M1 8h1.6M13.4 8H15M3.05 3.05l1.13 1.13M11.82 11.82l1.13 1.13M12.95 3.05l-1.13 1.13M4.18 11.82l-1.13 1.13" />
        </svg>
        <svg class="icon-dark" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M13.5 9.9A5.6 5.6 0 0 1 6.1 2.5a5.9 5.9 0 1 0 7.4 7.4z" />
        </svg>
      </button>
    </div>
    <div class="tabs" id="tab-bar" role="tablist" aria-label="Evaluation modules"></div>
  </div>
</header>

<main>
  <noscript>
    <p class="chart-empty">This dashboard renders its figures in the browser. The underlying data is
      available as <a href="runs.json">runs.json</a> and <a href="pubs_runs.json">pubs_runs.json</a>.</p>
  </noscript>
  <section class="panel" id="panel-tools" role="tabpanel" aria-labelledby="tab-tools" tabindex="0" hidden></section>
  <section class="panel" id="panel-pubs" role="tabpanel" aria-labelledby="tab-pubs" tabindex="0" hidden></section>
</main>

<footer class="site-footer">
  <span>Generated {generated}</span>
  <span class="spacer"></span>
  <a href="runs.json">runs.json</a>
  <a href="pubs_runs.json">pubs_runs.json</a>
  <a href="https://github.com/nf-osi/kg-pipeline">kg-pipeline</a>
  <a href="https://github.com/nf-osi/asta-bench">asta-bench</a>
</footer>

<script id="site-data" type="application/json">{_embed_json(payload)}</script>
<script>
{charts_js}
</script>
<script>
{dashboard_js}
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def build(
    runs_json: Path,
    pubs_json: Path | None,
    destination: Path,
    eval_metadata: Path,
    ground_truth_dir: Path,
    qa_dir: Path,
) -> None:
    tools_raw = json.loads(runs_json.read_text()) if runs_json.exists() else []
    if not tools_raw:
        raise SystemExit(f"No runs found in {runs_json}")

    pubs_raw: list[dict] = []
    if pubs_json and pubs_json.exists():
        pubs_raw = json.loads(pubs_json.read_text())
    elif pubs_json:
        print(f"Warning: {pubs_json} not found; the publication QA tab will be empty", file=sys.stderr)

    question_meta = load_question_metadata(eval_metadata)
    ground_truth_text = load_ground_truth_questions(
        sorted(ground_truth_dir.glob("eval_tools_ground_*.yaml"))
    )
    papers_meta = load_paper_metadata(qa_dir)

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "models": build_model_registry(tools_raw, pubs_raw),
        "tools": build_tools_payload(tools_raw, question_meta, ground_truth_text),
        "pubs": build_pubs_payload(pubs_raw, papers_meta) or {"runs": [], "styles": [], "about": []},
    }

    destination.mkdir(parents=True, exist_ok=True)
    (destination / "index.html").write_text(render_html(payload))
    (destination / "runs.json").write_text(json.dumps(tools_raw, indent=2))
    if pubs_raw:
        (destination / "pubs_runs.json").write_text(json.dumps(pubs_raw, indent=2))

    # keep the previously published URLs working
    (destination / "main.html").write_text(
        REDIRECT_TEMPLATE.format(anchor="tools", name="research tools discovery")
    )
    (destination / "pubs.html").write_text(
        REDIRECT_TEMPLATE.format(anchor="pubs", name="publication QA")
    )

    new_categories = [c["code"] for c in payload["tools"]["categories"] if c.get("isNew")]
    tools, pubs = payload["tools"], payload["pubs"]
    print(f"✓ Dashboard written to {destination / 'index.html'}")
    print(
        f"  {len(tools['runs'])} tools runs, {len(pubs.get('runs', []))} pubs runs, "
        f"{len(payload['models'])} models"
    )
    dropped = tools.get("excluded", 0) + pubs.get("excluded", 0)
    if dropped:
        print(
            f"  excluded {dropped} unscored or partial runs "
            f"({tools.get('excluded', 0)} tools, {pubs.get('excluded', 0)} pubs)"
        )
    if new_categories:
        print(f"  new question categories surfaced: {', '.join(new_categories)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "runs_json",
        type=Path,
        nargs="?",
        default=Path("evaluation/runs.json"),
        help="Path to the tools eval runs.json (default: evaluation/runs.json)",
    )
    parser.add_argument(
        "--pubs-json",
        type=Path,
        default=Path("evaluation/pubs_runs.json"),
        help="Path to the pubs eval runs json (default: evaluation/pubs_runs.json)",
    )
    parser.add_argument("--out", type=Path, default=Path("_site"), help="Output directory")
    parser.add_argument(
        "--eval-metadata",
        type=Path,
        default=Path("evaluation/main/dataset_attributes.yaml"),
        help="Question metadata for the tools eval",
    )
    parser.add_argument(
        "--ground-truth-dir",
        type=Path,
        default=Path("evaluation/main"),
        help="Directory holding eval_tools_ground_*.yaml",
    )
    parser.add_argument(
        "--qa-dir",
        type=Path,
        default=Path("evaluation/qa"),
        help="Directory holding qa_PMC*.yaml (paper titles)",
    )
    parser.add_argument(
        "--pubs",
        action="store_true",
        help=argparse.SUPPRESS,  # legacy: both modules are now built in one pass
    )
    args = parser.parse_args()

    runs_json = args.runs_json
    pubs_json = args.pubs_json
    if args.pubs:
        # Old call shape: `build_site.py evaluation/pubs_runs.json --pubs`.
        print(
            "Note: --pubs is no longer needed; both modules are built in one pass.",
            file=sys.stderr,
        )
        pubs_json = args.runs_json
        runs_json = Path("evaluation/runs.json")

    if not runs_json.exists():
        raise SystemExit(f"Input file {runs_json} does not exist")

    build(runs_json, pubs_json, args.out, args.eval_metadata, args.ground_truth_dir, args.qa_dir)


if __name__ == "__main__":
    main()
