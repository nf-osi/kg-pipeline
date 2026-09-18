# Demo 1 — Patient alleles vs. model systems: covered and not covered

> **Status: built.** The demo itself, with every number from a real run, is
> [model-coverage.md](model-coverage.md). This file is the plan it was built to; it is
> kept as the record of what was asked for. Where the two differ, the demo says why —
> the ClinVar-bridged mutation count is 45 of 118 rather than 40 of 109 (the core
> snapshot moved), and run-level provenance lives in the TSV headers rather than in a
> column repeating one value per row.

Handoff doc. Self-contained, but read
[variant-layer-demo.md §B5](variant-layer-demo.md#b5-from-a-patients-allele-to-a-model-system-that-carries-it)
and [new-layers.md §1](new-layers.md) before starting; every number quoted here comes
from one of those two documents.

## Concept

§B5 already demonstrates the forward direction: 5 NF1 protein changes observed in patient
specimens match 11 curated cell lines, down to a published ASO rescue experiment for one of
them. This demo builds the **inversion**: the gap list.

> **Which recurrent patient alleles in these cohorts have no model system in the registry —
> ranked by how many specimens carry them?**

And its mirror: which curated models carry mutations never observed in any patient
specimen (a model-relevance audit).

The audience is the funders and program staff who commission model development (NTAP, CTF,
GFF). The match list is a nice story; the *gap list* is a work order. That is what makes
this demo compelling: the output is a short, ranked, actionable table that did not exist
before, produced by joining two curation efforts that were never designed to meet.

## What exists today

| Piece | State |
|---|---|
| Patient side | 607,690 VRS-identified alleles, `nf:hgvsP` on observations, 169 specimens |
| Model side | `nf:Mutation` nodes with `nf:proteinVariation` / `nf:sequenceVariation` (HGVS strings); reached via `?resource nf:hasMutation` or `nf:hasNf1MutationSet/nf:hasMutation` |
| Join today | **protein string + gene constraint on both sides** (`--canned variant-model-match`) — works, but documented as fragile ([pitfall 2](variant-layer-demo.md#pitfalls-these-queries-encode): without the gene constraint it matched TTLL12, LPCAT1, PLCG2, DUSP2, ANKS6, CD164) |
| Animal models | **Zero matches, structurally.** Curated with mouse/zebrafish symbols (`Nf1`, `Trp53`, `nf1a`) and non-human coordinates; they can never meet a human `nf:hgvsP`. `data/csv/mutations.csv` holds 22 such symbols (orthologs + transgenes like `Cre`) |
| ClinVar bridge | 40 of 109 model mutations carry `nf:humanClinVarMutation` strings, e.g. `"NM_000267.3(NF1):c.910C>T (p.Arg304Ter)"` |
| Known blocker | Cell-line nodes in the current core snapshot have **no `nf:name`** — §B5 returns UUIDs. Fixed in mappings (`75eafb62`, 2026-08-31) but the local `cell_lines.ttl` predates it |

## Data legwork

Two bounded acquisitions, both already named as gaps in the existing docs:

### 1. Ortholog crosswalk (unlocks animal models)

(Covered in https://github.com/nf-osi/kg-pipeline/issues/110)

- Source: **HCOP** (HGNC Comparison of Orthology Predictions, bulk TSV from HGNC) or the
  **Alliance of Genome Resources** orthology download. Either gives HGNC ↔ MGI (mouse) and
  HGNC ↔ ZFIN (zebrafish) with per-pair supporting-source counts.
- Pin the download (URL + date + digest) the way every other source in this repo is pinned;
  add an entry to `scripts/check_source_versions.py`.
- Scope it: we need orthologs for **the ~20 genes in `data/csv/mutations.csv`**, not the
  genome. A `mappings/orthologs.tsv` (SSSOM-style, like the existing lookups in
  `mappings/sssom/`) with ~40 rows is the entire deliverable. Transgenes (`Cre`) get no
  row — they are constructs, not orthologs; keep an explicit exclusion list so their
  absence reads as deliberate.
- Keying rule: human side is the **HGNC IRI** (`https://identifiers.org/hgnc:`), never the
  symbol ([variant-layer.md](../variant-layer.md) explains why). Model side is
  MGI/ZFIN id, with the model-organism symbol carried as a label only.

### 2. VRS identity for curated mutations (upgrades the cell-line join)

- Route, per [new-layers.md §1](new-layers.md): take the 40 `nf:humanClinVarMutation`
  strings → resolve to ClinVar records → GRCh38 coordinates → mint `ga4gh:VA.*` with
  `vrsify` (`--vcf` path, reference + seqmap already in `data/reference/GRCh38/` per the
  new-layers repro section). Attach the digest to the `nf:Mutation` node as a new predicate
  (suggest `nf:mutationVrsId`, keep it distinct from the allele nodes' `nf:vrsId`).
- The remaining 69 mutations have only `nf:sequenceVariation` cDNA strings
  (`c.910C>T`) — transcript-relative, needing VariantValidator/VEP projection. **Out of
  scope for the demo.** For those, the existing hgvsP-plus-gene-constraint join stays as
  the documented fallback tier.
- The result is a **two-tier join** and the demo should present it that way: tier 1
  allele-identity (digest = digest), tier 2 protein-string (gene-constrained). Tier
  labels travel with every row.

## Implementation steps

1. **Rebuild the core cell-line snapshot** so `nf:name` is populated
   (`mappings/rml/cell_lines.rml.ttl` already emits it; the local `cell_lines.ttl` is
   stale). A UUID in the demo table is a demo-killer. Verify with a one-line query before
   proceeding.
2. Build `mappings/orthologs.tsv` (legwork §1). Add a small materialization step (pattern:
   `scripts/materialize_genes.py`) emitting
   `<hgnc-iri> nf:hasOrtholog <mgi-iri>` (+ inverse) into a new `data/rdf/` file — this is
   core-graph-sized (tens of triples), so it can live in the default glob; confirm with
   maintainers.
3. Mint VRS for the 40 ClinVar-bridged mutations (legwork §2); emit `nf:mutationVrsId`
   triples. This can be a standalone script + checked-in TSV
   (`mappings/model_mutation_vrs.tsv`) rather than a Dagster asset — 40 rows does not need
   orchestration, it needs provenance columns (ClinVar VCV id, coordinates, mint date,
   vrsify version).
4. Write the queries, then add them as canned queries in `scripts/query_sparql.py`
   (project convention: recurring patterns become `--canned` entries):
   - `variant-model-gap` — protein-altering alleles ranked by
     `COUNT(DISTINCT ?specimen)` (reuse the §A3 consequence `VALUES` set), with
     `FILTER NOT EXISTS` against both join tiers. Columns: gene, hgvsP, VRS id, specimens,
     cohorts, tumour types (`GROUP_CONCAT` over the file layer — mind
     [pitfall 5](variant-layer-demo.md#pitfalls-these-queries-encode), fan-out).
   - `variant-model-gap-genes` — same inversion at gene level, *including animal models
     via the ortholog hop*: recurrently-hit genes (≥N specimens) with no model carrying
     any mutation in that gene or its ortholog.
   - `model-without-patient-allele` — the mirror: models whose curated mutations match no
     observed allele on either tier.
5. Re-run §B5's `variant-model-match` on the new tier-1 join and record whether the 5
   matches survive digest-level identity (expected: yes for the ClinVar-bridged ones;
   any that *don't* survive are themselves a finding — a protein-string match that is not
   an allele match).
6. Write the demo section (follow the variant-layer-demo.md house style: every number from
   a real run, caveats inline). Deliverable tables: top-10 gap list, animal-model
   gene-level coverage, mirror audit.

## Acceptance criteria

- Animal models return **non-zero** gene-level coverage rows (today: structurally zero).
- The gap list is ≤ 1 page, ranked, with tier labels and tumour-type context per row.
- Every §B5 match is reproduced or its loss explained.
- All three queries exist as `--canned` entries and run against a `runtime-variants`
  index without exceeding memory (subselect the specimen sets — pitfall 6).

## Caveats to state on stage

- A gene-level animal-model match is **not** an allele match; a mouse `Nf1` knockout
  "covers" NF1 patients only at the mechanism level. Say so in the column header.
- Recurrence in these four cohorts is not population recurrence (§A1's caveat inherits).
- The gap list ranks by *our* specimen counts; an allele can be rare here and common in
  the wider NF population. Frame as "unmodelled in this registry, observed in these
  cohorts", nothing stronger.
- ADPRHL1-class artifacts (§A2/§A3: high specimen count, gnomAD-frequent) must be filtered
  or flagged before ranking, or the top of the gap list is germline leakage. Reuse the
  §A3 alleles-per-specimen heuristic plus gnomAD AF as flags, and keep the flag columns
  visible rather than silently dropping rows.

## Out of scope

- Projecting the 69 cDNA-only mutations to coordinates (tracked as follow-up).
- Ortholog coverage beyond the genes in `mutations.csv`.
- Any change to how models are curated upstream.

## Coordination

- Step 1 (core rebuild) also benefits Demo 2 (model names appear in its narrative). Do it
  once, early, and tell the Demo 2 owner.
- All three demos add canned queries to `scripts/query_sparql.py` — keep additions in
  clearly-bounded blocks to avoid merge conflicts.
