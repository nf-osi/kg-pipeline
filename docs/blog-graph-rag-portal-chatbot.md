# Building and evaluating a graph-RAG assistant for a rare disease data portal

**Draft — NF-OSI, August 2026**

A researcher planning an experiment on plexiform neurofibromas comes to the NF Data Portal with a question that sounds simple: *I need isogenic cell line pairs that differ only in NF1 status.* The portal has the answer. It has cell lines, donors, genotypes, and the provenance that links them. What it does not have is a way to ask.

The search box matches text. The facet filters match values that someone thought to make into a facet. Neither can express "pairs," "differ only in," or "same donor" — those are relationships, and relationships live between records rather than inside them. When we assembled a benchmark of 35 questions that NF researchers actually ask, only 9 were fully answerable through the portal's facet filters and 13 through its text search. Twenty-three could not be answered by facets at all.

This post describes what we built to close that gap — a knowledge graph the portal assistant queries directly, in SPARQL, as an agent — and, more importantly, how we measure whether it works. The building was the easy part. Knowing whether an agentic retrieval system is trustworthy enough to put in front of scientists turned out to be the harder and more interesting problem.

## A graph instead of an index

The conventional recipe for a document assistant is to chunk text, embed it, and retrieve by vector similarity. That works when the answer is a passage. It works poorly when the answer is a *set* — every cell line meeting four constraints, no more and no fewer — because similarity search has no notion of completeness, and no way to enforce a join.

So we built the retrieval substrate as an actual graph. The pipeline pulls tables from Synapse, harmonizes free-text labels to ontology IRIs through [SSSOM](https://mapping-commons.github.io/sssom/) mappings, converts them to RDF through [RML](https://rml.io/specs/rml/) mappings, materializes a handful of derived links that no source table contains (a shared-donor edge is inferred only when an animal model's transplantation donor matches a cell line's donor), and serves the result from [QLever](https://github.com/ad-freiburg/qlever).

Alongside the metadata graph we index publication text. Full text for 139 NF-related papers, sourced through PubTator 3.0, is indexed at *passage* granularity — roughly 11,000 records carrying 71,791 entity annotations — using QLever's SPARQL+Text feature. Genes, diseases, chemicals, species, cell lines, and variants are indexed as resolvable IRIs alongside the words they appear with, so a single query can constrain on graph structure and on text at once. Every passage carries an attribution tag of the form `[PMID12345678-3-METHODS]`, which is how the assistant is able to cite exactly what it read.

The assistant is not handed retrieved chunks. It is handed three tools — run a SPARQL query, inspect the ontology's classes and properties, count instances by type — and left to work out the query itself. That is a deliberate choice with a cost attached: it makes the system far more expressive and considerably harder to evaluate, because the same question asked twice does not follow the same path twice.

## Two benchmarks, because there are two failure modes

We run evaluation on the [AstaBench](https://github.com/allenai/asta-bench) framework, built on [Inspect](https://inspect.aisi.org.uk/), through an [NF-OSI fork](https://github.com/nf-osi/asta-bench) that adds two tasks. They exist because the assistant can fail in two unrelated ways: it can retrieve the wrong set of things, or it can say something about the literature that the literature does not support.

### Track 1: can it find the right resources?

`nf_rag` is 35 curated discovery questions across mutations, animal models, cell lines, antibodies, genetic reagents, investigators, and cross-resource queries. Each carries structure that turns a score into a diagnosis:

- **Complexity** — how many graph hops the question requires (14 are 0-hop, 15 are 1-hop, 6 are 2-hop).
- **Level** — `baseline` for what current portal technology already supports, `advanced` for what it does not.
- **Facet and text-search answerability** — recorded per question, which is where the "9 of 35" figure above comes from. This makes the benchmark a direct comparison against the status quo rather than a score in a vacuum.
- **User frustration** — from `low` (answerable with minimal effort today) to `very_high` (a dead end with current tools).

That last field is the one we did not expect to be the most useful. It encodes, per question, how much pain a researcher experiences today, and it lets us ask a question that raw accuracy cannot: *is the system good at the things that are currently hard, or only at the things that were already easy?*

Ground truth is 31 automatically generated sets derived from the source CSVs and 4 hand-curated ones for questions where "correct" requires judgment. The metric is recall over expected identifiers.

Results from our published runs (34 items, four models, `basic_agent` solver):

| Model | Recall | Cost/run |
|---|---|---|
| claude-sonnet-4-5 | 0.77–0.80 | ~$7.50 |
| claude-haiku-4-5 | 0.59–0.61 | ~$2.75 |
| gpt-5.2 | 0.31–0.41 | ~$3.00–4.40 |

Three things in that table matter more than the ranking.

**Variance is a first-class result.** The four `gpt-5.2` rows are the same model, the same solver, the same questions, and the same graph snapshot. They span 0.31 to 0.41 — a third of the model's own score, from nothing but sampling. Any evaluation of an agentic retrieval system that reports a single number from a single run is reporting noise at roughly that amplitude. This is why the harness supports `--epochs` and why we keep every run rather than the best one.

**The frustration breakdown is the argument for the whole project.** For `claude-sonnet-4-5`, questions rated `very_high` frustration — the ones that are simply dead ends in the portal today — scored 0.83, statistically indistinguishable from the `low` frustration questions at 0.84. The graph agent is not merely reproducing what facets already do; it is strongest precisely where the existing interface offers nothing. The weak bucket for both Claude models was `high` frustration at 0.40 — questions where a misleading partial path exists. An imperfect route through the data appears to be more dangerous than no route at all, for models as well as for people.

**Hop count is not difficulty.** Sonnet scored 0.83 on 2-hop questions and 0.69 on 1-hop, inverting the ordering we designed for. With six items in the 2-hop bucket we would not lean on this, but it is a useful corrective: what makes a question hard is vocabulary mismatch and ambiguous intent, not path length. Haiku, by contrast, did degrade with hops (0.70 → 0.59 → 0.42) and collapsed to 0.0 on cross-resource questions, which suggests the smaller model's ceiling is genuinely structural.

One honest caveat: these published runs predate later revisions to the task prompt and scoring, and they were made against a pinned, eval-tagged Docker image of the graph. Both of those are deliberate — ground truth is only valid against the snapshot it was written for — but it means the numbers date a specific configuration rather than describing the current system.

### Track 2: can it be trusted about the literature?

`nf_rag_pubs` is 130 multiple-choice questions over 14 indexed papers, in the format used by [LitQA2](https://huggingface.co/datasets/futurehouse/lab-bench/viewer/LitQA2) and Humanity's Last Exam. Items were generated by frontier models (`claude-opus-4-6`, `gemini-3.1-pro-preview`, `gpt-5.4`) against PubTator3 full text, then reviewed and edited by the NF-OSI team.

The curation pass is where most of the actual work went, and it is worth being specific about what it caught, because these failure modes are generic to LLM-generated benchmarks — an earlier version of Humanity's Last Exam was found to have roughly 30% of its text-only chemistry and biology questions in conflict with the peer-reviewed record.

- **Cross-paper conflict.** Two indexed papers report NF1 population incidence as 1:2000 and 1:2500. A question asking for "the" incidence has no correct answer, so it was removed. Where a fact was merely ambiguous rather than contradictory, questions were narrowed — "current treatment for symptomatic PNs" became a question about pharmacotherapy specifically, distinguishing the paper that says surgery from the one that says selumetinib.
- **Hallucinated ideal answers.** Generated answers sometimes cite mutation variants that do not appear anywhere in the source paper. Every ideal answer was checked against the text.
- **Vague study anchoring.** "What was the CS in the eyeblink conditioning experiments?" is unanswerable when the corpus contains more than one such experiment. Questions were rewritten to anchor to a specific study, because the eval deliberately does not tell the model which paper to read — selecting the right paper is part of the task, and the model cannot ask for clarification.
- **Trivial items.** Questions answerable without retrieval, or with implausible distractors, were dropped. They inflate scores without testing anything.

Scoring reports two independent numbers: **accuracy** on the multiple-choice answer, and **citation F1** over the set of `(pmid, passage)` tuples the model cites. The second is set-based — duplicate citations do not help, extra citations cost precision, missed ones cost recall.

| Model | Question style | Accuracy | Citation F1 | Cost |
|---|---|---|---|---|
| claude-sonnet-4-5 | precise | 0.992 | 0.772 | $18.63 |
| claude-sonnet-4-5 | colloquial | 0.985 | 0.740 | $19.33 |
| gpt-5.4 | precise | 0.985 | 0.730 | $4.34 |
| gpt-5.4 | colloquial | 0.992 | 0.709 | $5.00 |
| claude-haiku-4-5 | precise | 0.962 | 0.689 | $4.69 |
| claude-haiku-4-5 | colloquial | 0.969 | 0.638 | $4.93 |

Accuracy is saturated. Every model is above 96%, and Sonnet misses one question in 130. Read alone, that number says the problem is solved, and it is the number a less careful evaluation would have reported.

Citation F1 says otherwise. It sits between 0.64 and 0.77 — meaning the assistant reliably reaches the right conclusion while getting roughly a quarter of its supporting evidence wrong, by citing passages it did not need or omitting ones it did. For a research portal, that gap is the whole ballgame. A scientist checking an answer follows the citations; an answer that is right for the wrong reasons is worse than an obvious error, because it survives inspection.

The two metrics also diverge under paraphrase. Each question exists in a curated `precise` form and a colloquial `user_query` form, the latter closer to how someone actually types into a chat box. Colloquial phrasing barely touches accuracy — but it costs citation F1 consistently, most for the smallest model (Haiku 0.689 → 0.638). Vague questions do not stop a model from landing on the right answer; they degrade its grip on *why*.

Because multiple choice is nearly exhausted, we have added a semantic-judge scorer for short-answer variants, where the model must produce the answer rather than recognize it. We expect the headroom to reappear immediately.

## What evaluation changed about how we build

Two consequences were not obvious to us at the start.

**The schema is part of the prompt, and therefore part of the release.** The agent gets a compact topology sketch in its instructions — which classes connect to which, and by what predicate. When we recently added people and publication-author links (ORCID IRIs joined to Synapse profiles by `owl:sameAs`, and to investigators the same way), the new edges existed in the graph and were invisible to the assistant until that sketch was updated. Adding data to a graph-RAG system is not the same as making it usable; the model has to be told the shape. Evaluation is what catches the difference, and we now treat the topology block as an artifact that ships with a schema change rather than documentation that trails it.

**Benchmarks are how you decide what *not* to build with an LLM.** The per-question facet and text-search annotations let us draw a line: fast, cheap, familiar keyword search should keep handling known-item lookup and faceted browsing, and the assistant should take the questions that require synthesis across sources, retrieval from publications, comparative judgment, or a suggested next action. The 23-of-35 questions that facets cannot touch are the assistant's actual mandate. Without the annotations we would have been arguing about that division from intuition.

## Limitations

The benchmarks are small — 35 discovery questions and 130 QA items over 14 papers. The QA set has had one round of expert review, not the several we would prefer. Questions require synthesis across passages within a paper but never across papers, which we consider a harder tier and a plausible sequel. Ground-truth attribution lists are genuinely hard to finalize, so citation F1 has irreducible noise from the ground truth itself. Recall on the discovery track does not penalize over-retrieval, which flatters models that return large sets. And the whole apparatus measures the *retrieval* system: it says nothing about how the assistant explains itself, how it behaves over a multi-turn conversation, or whether users trust it.

## Where this goes

The NF graph is one contribution to a larger structure. The intended architecture is federated: each Sage-hosted portal — NF, ALS, Alzheimer's, ELITE — maintains its own pipeline in its own GitHub organization, anchors its entities to shared public ontology IRIs, and deposits RDF into a shared bucket that loads into one graph. Those shared IRIs are the join keys. Portals merge where they anchor to the same term and stay cleanly separate where they mint their own, and each portal's assistant navigates a common substrate while its community continues to own its own region of it.

That only works if quality is measurable at the boundary. A federated graph without shared evaluation is a federated way to accumulate errors. What we have built for NF — questions grounded in real researcher frustration, ground truth pinned to a specific data snapshot, attribution scored separately from correctness, and variance reported rather than averaged away — is meant to be the pattern the other portals inherit, not a one-off.

The recurring lesson, across both tracks, is that the useful metric was never the headline one. Multiple-choice accuracy at 99% and citation F1 at 77% describe the same system. Only one of them tells you whether to ship it.

---

*The pipeline, evaluation datasets, and eval harness are open source: [nf-osi/kg-pipeline](https://github.com/nf-osi/kg-pipeline) and [nf-osi/asta-bench](https://github.com/nf-osi/asta-bench). Results dashboards are published from `evaluation/runs.json` and `evaluation/pubs_runs.json`.*
