# Draft issues: curation defects in `syn26486835` surfaced while building demo 1

Two defects in the NF Research Tools Central `mutations` table, found while giving
curated model-system mutations a VRS identity ([model-coverage.md](model-coverage.md),
`scripts/mint_model_mutation_vrs.py`). None was looked for; all are visible only because
the exercise forced columns that had never been compared to agree.

> **The two issue bodies below are written for external maintainers and are deliberately
> self-contained** — no references to this repo, its pipeline, its file paths, its commits,
> or GA4GH digests that mean nothing outside it. Everything a reader needs is either in the
> issue or in Synapse/ClinVar. Paste between the `--- 8< ---` markers.
>
> This section, above those markers, is internal context and must **not** be pasted.

## Internal: how the table version was established

The issues are against **`syn26486835` version 11** (`post-linkml-migration-2026-08-24`,
snapshotted 2026-08-24), which is the latest stable snapshot — the daily repin job last ran
2026-09-17 (`30c2c079`) and left the pin at 11.

That needed checking rather than quoting, because our artifacts are ambiguous on their
face: `data/raw/mutations_raw.csv` is dated 2026-08-27, when the *committed* pin in
`data_sources.yaml` was still 4 (it moved to 11 in `75eafb62`, merged 2026-08-31), so the
fetch evidently ran from the in-progress #88 branch. Row counts settle it:

| | Rows |
|---|---|
| `syn26486835.4` (2026-03-19) | 111 |
| **`syn26486835.11` (2026-08-24)** | **120** |
| local `data/raw/mutations_raw.csv` | **120** |

Both defects are present in v4 as well as v11, so neither was introduced by the LinkML
migration.

A third thing this turned up — the byte-identical duplicate row `c33eaa9c-…`
(`NM_001042492.3(NF1):c.3233C>G`) — is **already filed upstream**, so it is deliberately
left out of issue 2. Issue 2's row/id arithmetic still counts it (120 rows, 118 distinct
ids come from two duplicated pairs), and says only that one pair is out of scope, without
re-describing it.

Counts quoted in the issues are **source-table** counts (120 rows, 47 with a
`humanClinVarMutation`). Counts in [model-coverage.md](model-coverage.md) are graph-side
(119 rows / 118 mutation nodes, 46 ClinVar rows → 45 with a digest), because one
byte-identical duplicate collapses during CSV processing. Both are right; don't mix them.

---
--- 8< --- paste from here ---

## Issue 1

**Title:** `mutations` (syn26486835 v11): `NF1 c.2542G>T` contradicts the ClinVar expression and protein change on the same row

### Summary

One row gives three descriptions of the same allele, and the cDNA column disagrees with the
other two. `sequenceVariation` says `c.2542G>T`; `humanClinVarMutation` and
`proteinVariation` both say `c.2542G>C` / `p.Gly848Arg`. `c.2542G>T` does not produce
p.Gly848Arg, and it is not a variant ClinVar has a record of.

### The row

Table `syn26486835`, version 11 (`post-linkml-migration-2026-08-24`).

| Column | Value |
|---|---|
| `mutationDetailsId` | `7658c873-27ea-481f-bdee-abd08fd0ff2a` |
| `affectedGeneSymbol` | `NF1` |
| `humanClinVarMutation` | `NM_000267.3(NF1):c.2542G>C (p.Gly848Arg)` |
| `sequenceVariation` | **`c.2542G>T`** ← inconsistent |
| `proteinVariation` | `p.Gly848Arg` |
| `chromosome` | `17` |
| `alleleType` / `mutationMethod` | `Null/knockout` / `Spontaneous` |

### Evidence

Codon 848 of `NM_000267.3` is **`GGG`** (GRCh38 `chr17:31,229,157-31,229,159`, 1-based; NF1
is on the + strand and `c.2542` is the first base of the codon):

| Change | Codon | Residue | Matches the row's `proteinVariation`? |
|---|---|---|---|
| `c.2542G>C` | `CGG` | Arg | **yes** — `p.Gly848Arg` |
| `c.2542G>T` | `TGG` | Trp | no — would be `p.Gly848Trp` |

Two further checks:

- **ClinVar has no `NM_000267.3:c.2542G>T` record.** A quoted E-utilities search
  (`esearch db=clinvar term="NM_000267.3:c.2542G>T"`) returns 0 hits;
  `"NM_000267.3:c.2542G>C"` returns exactly one.
- **Another row in the same table records this allele correctly.**
  `mutationDetailsId = da07b349-d70f-4b21-bdff-ee2de5e05493` (the humanized mouse knock-in,
  `affectedGeneSymbol = Nf1`, `externalMutationID = MGI:6153137`) carries the identical
  `humanClinVarMutation` and has `sequenceVariation = c.2542G>C`.

Also present in version 4 (2026-03-19), so it predates the LinkML migration.

### What is affected

One cell line carries this mutation through the `mutation_model` junction table
(`syn26486834`): **hTERT NF1 ipn06.2 A**.

The practical risk is that consumers disagree depending on which column they read. Anything
resolving the allele from `humanClinVarMutation` or `proteinVariation` gets
`NC_000017.11:g.31229157G>C`; anything resolving it from `sequenceVariation` gets a
different and non-existent variant.

### Suggested fix

Change `sequenceVariation` on `7658c873-27ea-481f-bdee-abd08fd0ff2a` from `c.2542G>T` to
`c.2542G>C`.

If `G>T` was actually intended, then `proteinVariation` and `humanClinVarMutation` are the
wrong columns and should become `p.Gly848Trp` with no ClinVar expression — but the
correctly-recorded sibling row and the absence of any `c.2542G>T` ClinVar record both point
to a typo in the cDNA column.

### How it was found

Resolving each row's `humanClinVarMutation` to GRCh38 coordinates (NCBI Variation Services,
cross-checked against the ClinVar record), then comparing that allele back against the same
row's `sequenceVariation` and `proteinVariation`.

---

## Issue 2

**Title:** `mutations` (syn26486835 v11): one `humanClinVarMutation` no longer resolves in ClinVar (stale transcript version), and `mutationDetailsId` is not unique

### Summary

Two independent problems with `humanClinVarMutation`:

- **A. Stale transcript *versions*.** 26 of the 47 rows that carry a `humanClinVarMutation`
  name a RefSeq version NCBI has since superseded, and one of them can no longer be found
  in ClinVar by the string the table records.
- **B. `mutationDetailsId` is not unique.** 120 rows, 118 distinct ids. In one of the
  duplicated pairs the two rows differ only in which NF1 transcript the ClinVar expression
  uses, so one allele is stored twice under one id.

Neither moves any coordinates (checked below). A makes the table unreliable to look things
up in; B makes it unsafe to key on.

**This is not a request to standardise on one transcript per gene.** Using `NM_000267` for
NF1 and `NM_000546` for TP53 is a defensible curation decision and this issue assumes it is
deliberate — see "On transcript choice" at the end. A is about *versions of one accession*
(`.5` vs `.6`), where no such rationale applies.

Both are present in version 4 (2026-03-19) as well as version 11, so neither was introduced
by the LinkML migration.

## Symptom A — superseded transcript versions

### What is stale

Note the distinction this table is making: the left column mixes two separate things — the
*accession* chosen for a gene (a curation decision) and its *version* (which simply goes
stale).

| Accession used in the table | Current RefSeq | Rows |
|---|---|---|
| `NM_000267.3` (NF1, transcript variant 2) | `NM_000267.4` | 24 |
| `NM_000546.5` (TP53) | `NM_000546.6` | 2 |
| `NM_001042492.3` (NF1, MANE Select) | current | 16 |
| `NM_000546.6` (TP53) | current | 2 |
| `NM_000059.4`, `NM_000090.4`, `NM_006218.4` | current | 1 each |

TP53 is curated at **both** `.5` and `.6` within the table:

```
5e242b5d-05d0-45de-8568-faff055ba53f  NM_000546.5(TP53):c.405C>G (p.Cys135Trp)
18a17da2-d726-4ea2-97ee-0a8cbffb6f3a  NM_000546.5(TP53):c.745A>G (p.Arg249Gly)
be2e8f7c-08d6-476b-a7f4-62534a5e2406  NM_000546.6(TP53):c.329G>C (p.Arg110Pro)
389f0524-1d80-497d-9007-35acbe165c6f  NM_000546.6(TP53):c.96+1G>A
```

### This is not a coordinate problem — checked

These version bumps change 5′UTR length, not the CDS, so `c.` numbering is unchanged and
both versions land on the same genomic position (NCBI Variation Services, HGVS →
contextual SPDI → canonical representative; SPDI positions are 0-based):

| HGVS | Transcript SPDI | Genomic SPDI |
|---|---|---|
| `NM_000267.3:c.910C>T` | `NM_000267.3:1292:C:T` | `NC_000017.11:31200442:C:T` |
| `NM_000267.4:c.910C>T` | `NM_000267.4:1242:C:T` | `NC_000017.11:31200442:C:T` |
| `NM_000546.5:c.405C>G` | `NM_000546.5:606:C:G` | `NC_000017.11:7675206:G:C` |
| `NM_000546.6:c.405C>G` | `NM_000546.6:546:C:G` | `NC_000017.11:7675206:G:C` |

The transcript offset moves by 50 and 60 bases respectively; the genomic answer is
identical. **No coordinate already derived from this table is wrong because of the stale
versions.**

### What it does break

ClinVar's HGVS index holds whatever expressions submitters supplied, so whether an old
version resolves is **per record, not per transcript version**. The failure is therefore
unpredictable:

| `esearch db=clinvar`, quoted term | Hits |
|---|---|
| `NM_000267.3:c.910C>T` | 1 |
| `NM_000267.4:c.910C>T` | 1 |
| `NM_000546.5:c.745A>G` | 1 |
| **`NM_000546.5:c.405C>G`** | **0** |
| `NM_000546.6:c.405C>G` | 1 |

So `NM_000546.5(TP53):c.405C>G (p.Cys135Trp)`, carried by cell line
**NCC-MPNST3-X2-C1**, cannot be found in ClinVar by the current record string, while
another row on the same stale transcript can. A user verifying the reference
gets "not found" with no indication why. The record does exist: it is `VCV000376561`, filed
as `NM_000546.6(TP53):c.405C>G (p.Cys135Trp)`.

## Symptom B — `mutationDetailsId` is not unique

Version 11 has 120 rows but **118 distinct `mutationDetailsId`**: two ids appear twice.
One of those pairs is a straightforward duplicated row and is out of scope here. This is
the other one, where the two rows are *not* identical.

**`2a86a4da-6852-4f7e-854f-8f64097d93f3`** — identical in every column except one:

```
humanClinVarMutation = NM_000267.3(NF1):c.3158C>G (p.Ser1053Ter)
humanClinVarMutation = NM_001042492.3(NF1):c.3158C>G (p.Ser1053Ter)

both rows: affectedGeneSymbol = NF1, sequenceVariation = c.3158C>G,
           proteinVariation = p.Ser1053Ter, chromosome = 17,
           alleleType = Null/knockout, mutationMethod = Spontaneous
```

Both expressions resolve to the same genomic position (`NC_000017.11:g.31230886C>G`,
GRCh38), so this is one allele stored twice under one id, because two transcripts were used
to name it. Note this is a *within-record* collision, not the per-gene transcript choice
discussed at the end — and it is why this is not simply a duplicate row to delete: the two
rows carry different information and a reviewer has to decide which expression survives.

`mutationDetailsId` reads like a primary key. Any consumer that treats it as one — a
`GROUP BY`, a join, a dictionary build — silently keeps whichever of the two rows it
happened to see last, and which one that is is not deterministic.

## Suggested fix

In rough order of value:

1. **Re-point the two `NM_000546.5` rows at `NM_000546.6`** (`c.405C>G`, `c.745A>G`). That
   removes the one silent lookup failure and makes TP53 internally consistent.
2. **Merge the two `2a86a4da-…` rows**, keeping whichever transcript expression you
   consider authoritative for that allele, and add a uniqueness constraint on
   `mutationDetailsId` if the platform supports one.
3. **Record the ClinVar VCV accession alongside the HGVS expression.** `VCV000376561` never
   goes stale; an HGVS string against a versioned transcript does. If a column can be
   added, this removes the whole class of problem rather than one instance of it.
4. **If two transcripts stay in use for one gene, make the record say which one is
   authoritative for that row** — either by always including the accession in
   `humanClinVarMutation` (most rows already do) or, better, via item 3. The thing to avoid
   is not two transcripts across the table; it is two transcripts inside one logical
   record, which is what produced symptom B.

Items 1–3 are small edits. Item 4 is the only one touching curation practice, and it is
deliberately narrow — see below.

## On transcript choice — why this issue does *not* ask you to normalise

An obvious-looking fix would be "pick MANE Select for every gene and rewrite the
expressions". We are not asking for that, for three reasons that seem to favour the
current practice:

1. **Verbatim recording is traceable; re-expression is a transformation.** If a record
   states the allele the way the originating paper, vendor page or repository entry states
   it, a reader can check it against that source. Re-numbering it against a different
   transcript makes the curator the author of a claim the source never made.

2. **The existing numbering is load-bearing in your own portal.** `NM_000267` numbering is
   embedded in resource names and filenames, not just in the mutation record:

   | | |
   |---|---|
   | animal model | `Nf1pArg1947mp1` (description: *"recurrent nonsense mutation p.Arg1947\*(R1947\*)"*) |
   | cell lines | `HEK293 NF1 -/- with R1947X mNf1 cDNA`, `… R816X …`, `… R681X …`, `Nf1Gly848Arg/Gly848Arg` |
   | files | `1229C_NF1_R1947X-NF1_R1947X.seq`, `2683.2.FB_NF1_R1947X-NF1_R1947X.seq`, … |

   Under `NM_001042492` that allele is `p.Arg1968Ter`. Renormalising the mutation record
   would leave it disagreeing with the name of the very model that carries it. The same
   argument applies to TP53, where the IARC/UMD codon numbering used throughout the p53
   literature is `NM_000546`-based.

3. **For most rows it makes no difference anyway.** The two NF1 transcripts differ by a
   single 63 bp (21-codon) alternatively spliced exon, with the boundary between
   `NM_000267.3` `c.3916` and `c.5425`. Projecting each distinct `NM_000267.3` expression
   in this table against both transcripts (NCBI Variation Services):

   | | Distinct expressions |
   |---|---|
   | same allele under either transcript | **14** |
   | genuinely differ (3′ of the alternative exon, offset +63 nt / +21 residues) | 4 |

   So the transcript label is cosmetic for 14 of 18 rows, and the 4 where it matters are
   exactly the ones with entrenched community numbering.

What all three arguments point at is **item 3**: keep the human-readable expression
verbatim in whatever transcript the source used, and add a stable machine key
(ClinVar VCV, or a genomic HGVS / SPDI) beside it. That preserves traceability, keeps the
numbering your models and files already use, and still lets anyone dedupe and join
reliably. Items 1 and 2 are then just cleanup of two rows and a duplicate.


### How it was found

Resolving every `humanClinVarMutation` to GRCh38 coordinates against two independent NCBI
services — Variation Services for the HGVS → coordinate projection, ClinVar for the record
itself — and requiring the two to agree. The `c.405C>G` row returned no ClinVar record at
all; the duplicate ids showed up as two rows resolving to one and the same genomic allele.

--- 8< --- end paste ---
