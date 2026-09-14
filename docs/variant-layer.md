# Variant layer (cBioPortal somatic variants) — PoC notes

Working notes for [#95](https://github.com/nf-osi/kg-pipeline/issues/95): add a somatic
variant observation layer from two public NF cBioPortal studies, joined back to the
specimens and individuals already in the graph.

**Status.** Built and running end to end on `nst_nfosi_ntap`: 23,181 variant nodes and
23,741 observations, 90.2% of which reach a portal specimen. Scoped to that one study
(see Finding 1), with all consequences retained rather than filtered.

Two prerequisites were missing and were built first, as **core graph** entity layers
(permanent) — see [`entity-layers.md`](entity-layers.md):

* `nf:Specimen` / `nf:Individual`, because `specimenID`/`individualID` existed only as
  string literals on `nf:File`, leaving the issue's model nothing to attach to;
* `biolink:Gene`, so `nf:affectsGene` is a real edge rather than a literal.

One issue premise still does not hold: there is **no named-graph mechanism** — every
`data/rdf/*.ttl` is `cat`-ed into one default graph at index time — so reversibility is
delivered by three independent opt-in gates instead (see "Feature gates" below).

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

### Finding 2 — per-row data quality

- **Mixed assemblies inside one study.** `nfib_ctf_biobank_2025` has **29 `GRCh37` rows**
  among 64,309 `GRCh38` ones (samples `Patient1_Tumor9`, `Patient3_Tumor2`,
  `Patient8_Tumor5`), even though the study declares hg38. Hashing those against GRCh38
  refget accessions would mint wrong VRS ids silently. The tool refuses to.
- **28% of `nfib_ctf_biobank_2025` rows have `t_alt_count = 0`** (17,848 / 64,338) — no
  read in the tumor supports the allele. Ingesting them asserts a specimen carries a
  variant it has no support for. Use `--min-tumor-alt-count 1` for that study.
- `nst_nfosi_ntap`'s MAF has `t_depth`/`t_ref_count`/`t_alt_count` columns that are
  **entirely empty**, so no VAF is derivable for study 1 from the MAF (the API's
  `tumorAltCount`/`tumorRefCount` are populated — another reason to cross-check).
- `nst_nfosi_ntap` is unfiltered by consequence (5,659 `Intron`, 3,897 `Silent` rows);
  `nfib_ctf_biobank_2025` is coding-only. Decide whether the layer holds everything or
  only impactful consequences: 23,741 rows / 23,181 distinct alleles unfiltered vs
  12,614 rows / 12,362 alleles coding-only — **1.9×**, not the order of magnitude a
  glance at the `Intron` count suggests.

## Ingest tooling — `vrsify maf`

The VRS identity engine in `vrsify` (`digest`/`vrs`/`normalize`/`refget`) is
format-agnostic; only the front end is format-specific. So the tool was **extended**
with a `maf` subcommand (M7) rather than replaced — see `docs/vrsify-handoff.md` in that
repo for the full brief.

`vrsify` lives at `~/sage/nf/vrsify`, outside this repo. It was called `vcf2vrs` until
the MAF front end landed; the name changed because the input is no longer just VCF.

The contract that matters here: **the same variant gets the same `ga4gh:VA.` id through
either front end.** Integration tests gate it — a MAF SNP row for rs7412 reproduces the
GA4GH `vrs@2.0` golden id `ga4gh:VA.0AePZIWZUNsUlQTamyLrjm2HWUw2opLt`, and a deletion and
an insertion expressed in MAF's trimmed `-` form and in VCF's anchored form collapse to
one id. Without that, a variant from cBioPortal would not join to one from a VCF, to
ClinVar, or to gnomAD, and the issue's "future joins are lookups" claim is empty.

MAF is in fact a *better* input than VCF here: it already stores indels trimmed with `-`
placeholders, so projecting into VRS's interbase coordinates needs no anchor-base
reference lookup — the step a MAF→VCF conversion needs a FASTA for:

| MAF row | VRS interbase | state |
|---|---|---|
| SNP `Start=100 End=102 ACG→TTT` | `[99, 102)` | `"TTT"` |
| DEL `Start=100 End=102 ACG→-` | `[99, 102)` | `""` |
| INS `Start=100 End=101 -→TT` | `[100, 100)` | `"TT"` |

Run:

```sh
# One-time: derive refget SQ. accessions for the assembly the MAF declares.
vrsify seqmap --fasta GRCh38.fa --assembly GRCh38 --out seqmap.tsv

vrsify maf \
  --maf data_mutations.txt \
  --seqmap seqmap.tsv \
  --reference GRCh38.fa \          # required: see below
  --out-alleles alleles.ndjson \
  --out-observations obs.ndjson \
  --study-id nst_nfosi_ntap \
  --source "cbioportal:nst_nfosi_ntap/data_mutations.txt"
```

Behaviour the pipeline depends on:

- **`--reference` is not optional for us.** Substitutions are byte-exact without it, but
  indels only converge with vrs-python/ClinVar/the VCF path after fully-justified
  normalization. Without it, indel alleles come out tagged `"fullyJustified": false` and
  the count is printed as a warning. `nst_nfosi_ntap` has 941 indels (786 DEL, 155 INS),
  ~4% of rows; `nfib_ctf_biobank_2025` has none (all SNP).
- **`chr` prefixes are bridged** — MAFs write `19`, `1_KI270706v1_random`; a UCSC-derived
  seqmap is keyed `chr19`, `chr1_KI270706v1_random`.
- **Nothing is dropped.** Rows that cannot be given a VRS identity (contig absent from
  the seqmap, `NCBI_Build` disagreeing with the seqmap, non-nucleotide alleles) go to the
  alleles stream as `{"type": "UnnormalizedVariant", "unnormalized": true, "id":
  "nf:variant/{assembly}:{chrom}:{pos}:{ref}:{alt}", "reason": …}`, deduplicated on that
  key and counted — the fallback the issue asks for. `--strict` makes them fatal.
- Observations carry no zygosity (MAF has no `GT`). They carry the tumor/normal barcode
  pair, allele depths + derived VAF, `studyId`, and `Consequence` as a **list** of SO
  terms, so each term can go through SSSOM independently.

Smoke test actually run: the full 23,741-row `nst_nfosi_ntap` MAF against a real GRCh38
chr17+chr19 reference → 3,028 unique alleles from 3,157 observations in 0.5 s, 0
not-fully-justified indels, off-target contigs routed to the unnormalized stream. The
derived chr19 accession is `SQ.IIB53T8CNeJJdUqzn9V_JnRtQadwWCbl`, byte-identical to
GA4GH's canonical accession for GRCh38 chr19.

## The pipeline

```
                                         data/csv/files_harmonized.csv
                                                     |
                        scripts/materialize_specimens.py   (CORE graph)
                                                     |
                                        data/rdf/specimens.ttl
                                    nf:Specimen / nf:Individual nodes
                                                     |
  fetch_cbioportal_maf.py  ->  data/raw/<study>_data_mutations.txt
           |                                         |
           |                       map_cbioportal_samples.py
           |                                         |
           |                    mappings/cbioportal_sample_specimen.tsv
           |                                         |
     vrsify maf  --reference GRCh38.fa               |
           |                                         |
   data/variants/<study>_{alleles,observations}.ndjson
           |                                         |
           +----------------> variants_to_rdf.py <---+
                                         |
                            data/rdf/variants/<study>.ttl
                     biolink:SequenceVariant / nf:VariantObservation
```

Every step is a Dagster asset (`orchestration/dagster_pipeline/assets.py`). To run it:

```sh
# One-time: a reference FASTA and its refget accessions. Load-bearing for indels.
vrsify seqmap --fasta hg38.fa --assembly GRCh38 --out seqmap.tsv
export VRSIFY_BIN=~/sage/nf/vrsify/target/release/vrsify
export VRSIFY_REFERENCE=/path/to/hg38.fa VRSIFY_SEQMAP=/path/to/seqmap.tsv

export KG_INCLUDE_VARIANTS=1        # gate 1: generate the layer at all
dagster asset materialize --select 'variants/*' -m orchestration.dagster_pipeline
```

Or step by step, which is what the assets shell out to:

```sh
python scripts/fetch_cbioportal_maf.py --study nst_nfosi_ntap
python scripts/materialize_specimens.py
python scripts/map_cbioportal_samples.py \
    --maf data/raw/nst_nfosi_ntap_data_mutations.txt --study-id nst_nfosi_ntap
$VRSIFY_BIN maf --maf data/raw/nst_nfosi_ntap_data_mutations.txt \
    --seqmap "$VRSIFY_SEQMAP" --reference "$VRSIFY_REFERENCE" \
    --out-alleles data/variants/nst_nfosi_ntap_alleles.ndjson \
    --out-observations data/variants/nst_nfosi_ntap_observations.ndjson \
    --study-id nst_nfosi_ntap
python scripts/variants_to_rdf.py \
    --alleles data/variants/nst_nfosi_ntap_alleles.ndjson \
    --observations data/variants/nst_nfosi_ntap_observations.ndjson \
    --study-id nst_nfosi_ntap
```

Measured on the real study, ~36 s total excluding the reference download: MAF fetch 4 s,
specimens 5 s, `vrsify maf` over 23,741 rows against the full 3.1 GB hg38 7 s, RDF
projection 23 s.

## The model as built

Abridged from the real output for the NF1 nonsense variant `p.R1276*`:

```turtle
# --- core graph (data/rdf/specimens.ttl) ---
nf:specimen/JH-2-111-G645D  a nf:Specimen ;
    nf:specimenID "JH-2-111-G645D" ;
    nf:fromIndividual nf:individual/JH-2-111 ;
    nf:hasFile <https://www.synapse.org/Synapse:syn26470374> .   # 4x RNA-seq, 2x WES

# --- variant layer (data/rdf/variants/nst_nfosi_ntap.ttl) ---
nf:specimen/JH-2-111-G645D
    nf:hasVariantObservation
        nf:variantObservation/nst_nfosi_ntap/JH-2-111-G645D-A/VA.rDRjZ2kX3o3hvEAykAwbNXMw4dkisxiw .

nf:variantObservation/nst_nfosi_ntap/JH-2-111-G645D-A/VA.rDRjZ2kX3o3hvEAykAwbNXMw4dkisxiw
    a nf:VariantObservation ;
    nf:observesVariant nf:variant/VA.rDRjZ2kX3o3hvEAykAwbNXMw4dkisxiw ;
    nf:fromSpecimen   nf:specimen/JH-2-111-G645D ;
    nf:fromIndividual nf:individual/JH-2-111 ;
    nf:fromVariantDataset nf:variantDataset/nst_nfosi_ntap ;
    nf:hasConsequence obo:SO_0001587 ;              # stop_gained, via SSSOM
    nf:variantClassification "Nonsense_Mutation" ; nf:variantImpact "HIGH" ;
    nf:affectedGeneSymbol "NF1" ; nf:hgncId "HGNC:7765" ;
    nf:ensemblGeneId "ENSG00000196712" ; nf:entrezGeneId "4763" ;
    nf:transcriptId "ENST00000356175" ; nf:exonNumber "28/57" ;
    nf:aminoacidChange "p.R1276*" ; nf:hgvsP "p.Arg1276Ter" ;
    nf:hgvsC "ENST00000356175.7:c.3826C>T" ; nf:proteinPosition "1276" ;
    nf:dbsnpId "rs199474742" ; nf:gnomadAlleleFrequency 6.57e-06 ;
    nf:mutationStatus "Somatic" ; nf:matchedNormalSampleBarcode "NORMAL" ;
    nf:normalDepth 127 ; nf:normalRefCount 125 ; nf:normalAltCount 0 ;
    nf:assemblyId "GRCh38" ; nf:sourceContig "17" ; nf:sourcePos 31235728 .

nf:variant/VA.rDRjZ2kX3o3hvEAykAwbNXMw4dkisxiw
    a biolink:SequenceVariant ;
    nf:vrsId "ga4gh:VA.rDRjZ2kX3o3hvEAykAwbNXMw4dkisxiw" ;
    nf:refgetAccession "SQ.upqChCoU-Gtd_61IidCsln-r8cxUTFeP" ;   # GRCh38 chr17
    nf:variantStart 31235727 ; nf:variantEnd 31235728 ; nf:variantState "T" .
```

No `nf:tumorAltCount` or `nf:variantAlleleFrequency` above, and that is the source, not
a bug: `nst_nfosi_ntap`'s MAF ships `t_depth`/`t_ref_count`/`t_alt_count` columns that
are entirely empty (Finding 2), so only the *normal* depths survive. The REST API does
populate the tumour counts, which is one reason to cross-check against it.

Three decisions:

* **`biolink:SequenceVariant`, not `nf:Variant`.** `nf:Variant` already means "a variant
  mentioned in publication text" (PubTator3) and has no coordinates. Using the Biolink
  class directly follows `docs/biolink-alignment.md`'s "replaced classes" convention.
* **The variant node carries nothing sample-specific** — no barcode, gene, consequence
  or depth. That is what lets one allele shared by several samples stay one node, and it
  is asserted in `test/test_variants_to_rdf.py`. A resolvable `ga4gh:` IRI namespace does
  not exist, so the node lives under `nf:variant/` and keeps the canonical CURIE in
  `nf:vrsId` rather than minting an IRI that 404s.
* **`nf:affectsGene` is on the observation, not the variant.** The gene association
  comes from the transcript the caller picked, so it is annotation, not identity: the
  same allele annotated against another transcript could name another gene. 23,716 of
  23,741 observations reach a gene node; the 25 that do not had no Ensembl gene id.

## Feature gates

The issue asks for the layer to be droppable in a later release. There is no named-graph
machinery in this pipeline, so that is delivered as three independent opt-ins:

| Gate | Default | Effect |
|---|---|---|
| `KG_INCLUDE_VARIANTS=1` | off | Registers the variant Dagster assets. Unset, the layer cannot be generated at all. |
| output path `data/rdf/variants/` | — | Both the QLever index and `rdf_to_edgelist.py` glob `data/rdf/*.ttl`, which is non-recursive, so a generated layer still stays out of the published index and the embeddings. |
| `docker build --target runtime-variants` | `runtime-rdf` | The only way the layer reaches a served index. |

Plus `rdf_to_edgelist.py --include-variants` to fold it into an embedding deliberately.
Keeping it out by default is not only about reversibility: 23k variant and 24k
observation nodes would swamp 8k specimens and dominate every random walk while adding
no edges between portal entities.

## Verification

`test/test_variants_to_rdf.py` covers the invariants that make the layer worth having
(the two-layer split, multi-term consequences, the keep-don't-drop paths);
`test/test_materialize_specimens.py` and `test/test_materialize_genes.py` cover the
entity layers' source-data traps ([`entity-layers.md`](entity-layers.md)).

Beyond unit tests, the four use cases from the issue are canned queries in
`scripts/query_sparql.py`, so they are exercised rather than asserted:

```sh
python scripts/query_sparql.py --canned variant-in-cases \
    --bind gene=NF1 --bind change='p.R1276*'
python scripts/query_sparql.py --canned variant-gene-summary
python scripts/query_sparql.py --canned variant-recurrent
python scripts/query_sparql.py --canned variant-genotype-cohort \
    --bind gene=NF1 --bind assay=RNA-seq
python scripts/query_sparql.py --canned variant-layer-summary
```

Results on the real layer (local pyoxigraph, core graph + variant layer):

| Query | Result |
|---|---|
| `variant-in-cases` NF1 `p.R1276*` | 1 specimen `JH-2-111-G645D`, individual `JH-2-111`, with its 4 RNA-seq and 2 WES files |
| `variant-gene-summary` | **NF1 top at 25 specimens**, then ADPRHL1 19, TTN 15, MUC16 12 |
| `variant-genotype-cohort` NF1 + RNA-seq | 19 specimens — a genotype predicate the cohort builder could not express before |
| `variant-layer-summary` | 23,181 variants, 23,741 observations, 21,421 with a specimen, 70 specimens, 48 individuals |

`NF1` ranking first in an NF cohort is the sanity check. The genes just below it
(ADPRHL1, TTN, MUC16, CCDC168) are the usual long-gene/artifact suspects, which is why
`variant-gene-summary` filters to protein-altering consequences — without that filter
the ranking is essentially gene length.

`validate_fks.py` gained a check that every specimen named in the crosswalk exists,
aimed at hand-authored rows; and the variant RDF asset fails the build if specimen
coverage drops below 85% (currently 90.2%).

## Still open

1. **Pathway layer.** Gene nodes now exist, but nothing links them to Reactome, so the
   issue's "which pathways are recurrently hit" use case is still unanswerable. This is
   now one hop away rather than two: a Reactome layer attaching to
   `https://identifiers.org/ensembl:*` would complete it.
2. **`nfib_ctf_biobank_2025`.** Needs a `Patient10_Tumor1` → `HM5230` crosswalk before
   it can join at specimen level. The crosswalk file is already the right shape to
   receive it: add rows with `method=manual` and they are preserved on regeneration.
3. **The 9 unresolved barcodes** (2,320 observations, 9.8%). They are in the graph but
   unattached. `JH-2-054`, `JH-2-060`, `JH-2-068`, `JH-2-079`, `JH-2-102` look like
   specimens the portal simply does not have; worth a curation check rather than a code
   fix.
4. **Class-name drift in `vrsify`.** Its VCF front end still emits
   `"type": "VariantCall"` while the MAF front end emits `"VariantObservation"`. Only
   the MAF path is used here, but the two should be unified before anything consumes the
   VCF path.
5. **Stale source.** The `nf-osi/datahub` fork is pinned at 2025-02 while cBioPortal's
   own import is 2026-01. Worth diffing against the REST API before the PoC is shown to
   users.
