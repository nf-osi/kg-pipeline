# Variant layer (cBioPortal somatic variants) — PoC notes

Working notes for [#95](https://github.com/nf-osi/kg-pipeline/issues/95): add a somatic
variant observation layer from two public NF cBioPortal studies, joined back to the
specimens and individuals already in the graph.

**Status.** Source retrieval and the sample→specimen crosswalk are in place; the RDF
ingest follows in a later PR. Scoped to `nst_nfosi_ntap` (see Finding 1). This document
grows with each PR in the sequence.

`nf:Specimen` / `nf:Individual` were a missing prerequisite and were built first as a
**core graph** entity layer — see [`entity-layers.md`](entity-layers.md) — because
`specimenID`/`individualID` existed only as string literals on `nf:File`, leaving the
issue's model nothing to attach to.

One issue premise does not hold: there is **no named-graph mechanism** — every
`data/rdf/*.ttl` is `cat`-ed into one default graph at index time — so reversibility
will be delivered by independent opt-in gates instead.

## Source data — what is actually retrievable

| Study | cBioPortal `referenceGenome` | Samples | Mutation rows | `data_mutations.txt` |
|---|---|---|---|---|
| `nst_nfosi_ntap` | hg38 | 80 sequenced (134 total) | 23,741 | 27 MB, retrievable |
| `nfib_ctf_biobank_2025` | hg38 | 38 | 64,338 | 497 MB, **not** retrievable (see below) |

Both are `MUTATION_EXTENDED` / `MAF` profiles, i.e. somatic by construction — neither
carries a per-row `Mutation_Status`.

Three possible sources, in descending order of column coverage:

1. **`nf-osi/datahub` fork** (`public/nst_nfosi_ntap/data_mutations.txt`, git LFS).
   The richest form: 113 columns including `Consequence` (VEP Sequence Ontology terms),
   `HGVSc`/`HGVSp`/`HGVSp_Short`, `Transcript_ID`, `Gene` (Ensembl), `HGNC_ID`,
   `dbSNP_RS`, gnomAD AFs, `IMPACT`, `FILTER`. This fork is pinned at 2025-02 while
   cBioPortal's own import is 2026-01, so it is stale but complete. Fetch without
   cloning via the LFS batch API:

   ```sh
   OID=$(gh api repos/nf-osi/datahub/contents/public/nst_nfosi_ntap/data_mutations.txt \
           --jq '.content' | base64 -d | sed -n 's/.*sha256://p')
   # POST {"operation":"download","objects":[{"oid":"'$OID'","size":27602051}]} to
   # https://github.com/nf-osi/datahub.git/info/lfs/objects/batch, then curl the href.
   ```

2. **Upstream `cBioPortal/datahub`** has both studies, but its LFS objects return
   `404 Object does not exist on the server` — so `nfib_ctf_biobank_2025`'s MAF is **not
   obtainable this way**. Needs another route (Synapse copy, the NF-OSI cBioPortal
   staging pipeline, or asking cBioPortal).

3. **cBioPortal REST API** — `POST /api/molecular-profiles/{profile}/mutations/fetch?projection=DETAILED`
   with `{"sampleListId": "{study}_all"}`. Always current and needs no LFS, but returns
   a reduced field set: it has `mutationType` (= `Variant_Classification`),
   `proteinChange`, `ncbiBuild`, `tumorAltCount`/`tumorRefCount`, and **not**
   `Consequence` (SO terms), `HGVSc`, `HGVSp`, `HGNC_ID`, or gnomAD AF. Usable as a
   fallback and as a cross-check on the MAF, but it costs the SO-term mapping the issue
   proposes.

### Finding 1 — the specimen join is study-specific and incomplete

This is the load-bearing assumption of the whole PoC ("joined back to the specimens and
individuals already present"), and neither study's barcodes join directly.

**`nst_nfosi_ntap`** — `Tumor_Sample_Barcode` looks like `JH-2-001-8A1B1-A`.

| Join attempt | Coverage against `data/csv/files_harmonized.csv` |
|---|---|
| barcode → `specimenID`, verbatim | **0 / 80** |
| barcode minus the last `-`-delimited segment → `specimenID` | **71 / 80** (89%) |
| barcode minus a trailing `-A` → `specimenID` | 68 / 80 |
| first three segments (`JH-2-001`) → `individualID` | **50 / 51** individuals (98%) |

So a normalization step is required, and "minus the last segment" is the better rule —
three barcodes end in something other than `-A` (`…-GAF53-A1011`, `…-GAF53-FB9H7`,
`…-1419H-9GG15`). The 9 leftovers are real gaps, not rule failures:
`JH-2-054-241HF`, `JH-2-054-9255F`, `JH-2-060-19EC4`, `JH-2-060-4CE8D`, `JH-2-068-A733G`,
`JH-2-068-A7488`, `JH-2-068-FH52C`, `JH-2-079-9D31F`, `JH-2-102-3B72A`. The matched
specimens sit mostly under `syn4939902` (71), with a few in `syn21984813` (4) and
`syn11638893` (1).

**`nfib_ctf_biobank_2025`** — sample ids are `Patient10_Tumor1`, patient ids
`Patient_10`.

| Join attempt | Coverage |
|---|---|
| `sampleId` → `specimenID` | **0 / 38** |
| `patientId` → `individualID` | **8 / 10** patients (`Patient_3`, `Patient_11` absent) |

The KG's specimens for those same individuals are named `HM4959`, `HM5085`, `HM5230`, …
— cBioPortal's sample ids were renamed during submission, and **there is no
deterministic mapping** from `Patient10_Tumor1` back to `HM5230`. Consequences:

- specimen-level questions ("which specimens carry this variant?") are answerable for
  `nst_nfosi_ntap` only;
- `nfib_ctf_biobank_2025` can only be attached at the individual level, which also
  breaks the "and which datasets/files correspond to those specimens" drill-down;
- either obtain a sample→specimen crosswalk for the cNF study, or scope the PoC to
  `nst_nfosi_ntap` and say so.

Whichever is chosen, the barcode→specimen rule belongs in a checked-in lookup (like the
existing SSSOM lookups) rather than a regex in a script, and the unmatched counts belong
in `validate_fks.py` as an asserted number — not a silent drop.
