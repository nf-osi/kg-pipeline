# Variant layer (cBioPortal somatic variants) — PoC notes

Working notes for [#95](https://github.com/nf-osi/kg-pipeline/issues/95): add a somatic
variant observation layer from the public NF cBioPortal studies, joined back to the
specimens and individuals already in the graph.

**Status.** Built and running end to end on four studies, with all consequences
retained rather than filtered:

| Study | Rows | Observations | Reach a portal specimen | Barcode rule |
|---|---|---|---|---|
| `nst_nfosi_ntap` | 23,741 | 23,741 | 90.2% | `strip_last_segment` |
| `schw_ctf_synodos_2025` | 41,874 | 41,874 | **100%** | `verbatim` |
| `lgg_ctf_synodos_2025` | 61,890 | 61,890 | **100%** | `verbatim` |
| `nfib_ctf_biobank_2025` | 680,335 | 493,060 | **100%** (crosswalk) | `verbatim` |

`nfib` drops 187,275 rows to `--min-tumor-alt-count 1` (27.5% of its rows have no
tumour read supporting the allele); nothing else is filtered.

Depending on the graph infra, there may be **no named-graph mechanism** — every
`data/rdf/*.ttl` is `cat`-ed into one default graph at index time, reversibility is
delivered by three independent opt-in gates instead (see "Feature gates" below).

## Linked core entities (specimen, individual, gene)

| Layer | Class | Key | Count | Built by |
|---|---|---|---|---|
| Specimen | `nf:Specimen` + `biolink:MaterialSample` | portal `specimenID` | 8,117 | `scripts/materialize_specimens.py` |
| Individual | `nf:Individual` + `biolink:IndividualOrganism` | portal `individualID` | 4,506 | same |
| Gene | `biolink:Gene` | HGNC id, Ensembl as fallback | 39,160 | `scripts/materialize_genes.py` |

```turtle
nf:specimen/JH-2-111-G645D  a nf:Specimen, biolink:MaterialSample ;
    nf:specimenID "JH-2-111-G645D" ; nf:hasFile <syn26470374> ;
    nf:fromIndividual nf:individual/JH-2-111 .
nf:individual/JH-2-111  a nf:Individual, biolink:IndividualOrganism ;
    nf:individualID "JH-2-111" ; nf:hasSpecimen nf:specimen/JH-2-111-G645D .

<https://identifiers.org/hgnc:7765>  a biolink:Gene ;
    rdfs:label "NF1" ; nf:geneSymbol "NF1" ; nf:geneName "neurofibromin 1" ;
    nf:hgncId "HGNC:7765" ; nf:ensemblGeneId "ENSG00000196712" ;
    nf:entrezGeneId "4763" ;
    skos:exactMatch <https://identifiers.org/ensembl:ENSG00000196712> .
```

### Gene nodes are created as part of this layer and uses HGNC

Gene nodes are named by their HGNC IRI. With HGNC the stable authority, HGNC-keyed
sources join by IRI; the Ensembl id stays as `nf:ensemblGeneId` and `skos:exactMatch`. 
Genes with no HGNC id fall back to Ensembl IRI rather than being dropped.

The layer is built from **all** studies' MAFs folded into one index, not one graph per
study. Over the four MAFs that is **39,160 nodes — 30,252 HGNC-keyed and 8,908 Ensembl-keyed**.
The fallback share jumped from 0.2% (exome-only) to 23% when the whole-genome studies
landed, because WGS reaches non-coding loci HGNC has never named. That is the fallback
doing its job: dropping those would lose a quarter of the gene layer to keep the keying
tidy.

Symbols (`Hugo_Symbol`) should never be used for key or a join. `Hugo_Symbol` is the 
*picked transcript's* symbol, so an overlapping antisense or readthrough transcript 
reports a neighbouring gene's symbol — `HGNC:11033` appears as both `SLC4A7` and `UBA52P4`. 
Symbols therefore come from HGNC, accepted only when HGNC's own `ensembl_gene_id` agrees with the MAF's. 
That cross-check has corrected symbols and cut symbols labelling two different genes. 
Without it `NF1` labelled both NF1 and EVI2A (which sits inside the NF1
locus), splitting "how many samples are altered in NF1" across two nodes. 
`--no-hgnc` skips the lookup for offline runs and warns.

**Not folded in:** `data/csv/mutations.csv`'s 22 gene symbols. 
These are model-organism orthologs (`Nf1`, `Trp53` mouse; `nf1a` zebrafish) or transgenes (`Cre`).

#### Effect on the default build

The gene layer's *generation* is gated with the variant assets (`KG_INCLUDE_VARIANTS`)
only because the MAF is where the annotation comes from; its output is core either way,
so if the variant study were dropped `genes.ttl` would stay and simply stop growing.
Sourcing genes from HGNC directly would decouple the two, at the cost of ~45,000 nodes
of which only ~11,200 are referenced.

## Source data

| Study | Samples | Mutation rows | Source (all hg38) |
|---|---|---|---|
| `nst_nfosi_ntap` | 80 sequenced (134 total) | 23,741 | 27 MB, upstream @ `86690e1e` |
| `schw_ctf_synodos_2025` | 40 | 41,874 | 47 MB, upstream @ `1cc0ead2` |
| `lgg_ctf_synodos_2025` | 21 | 61,890 | 36 MB, upstream @ `d84cab37` |
| `nfib_ctf_biobank_2025` | 38 | 680,335 | 496 MB, upstream @ `3ffe91da` |

Both are `MUTATION_EXTENDED` / `MAF` profiles, i.e. somatic by construction — neither
carries a per-row `Mutation_Status`.

Why source pins:

1. **`cBioPortal/datahub` at a pinned commit** — In general, use the original contribution commit 
   or carefully curated commit, because cBioPortal can do unexpected reprocessing of studies *in place*; 
   for example, they renamed sample ids from `patient10tumor1` to `Patient10_Tumor1` 
   (creating issues for linkage back to portal files), and with `schw_ctf_synodos_2025` 
   reprocessed using genome-nexus / `isoform: mskcc`, which removed 57 columns including the required `HGNC_ID`. 
   Studies at the indicated commits have full 113/114 columns: `Consequence` (VEP SO terms), 
   `HGVSc`/`HGVSp`/`HGVSp_Short`, `Transcript_ID`, `Gene` (Ensembl), `HGNC_ID`, `dbSNP_RS`, gnomAD AFs, `IMPACT`, `FILTER`. 

   ```sh
   # data_mutations.txt at a pinned commit is an LFS pointer; fetch the bytes with:
   curl -s https://raw.githubusercontent.com/cBioPortal/datahub/<sha>/public/<study>/data_mutations.txt
   # -> read oid/size, POST to .../datahub.git/info/lfs/objects/batch, curl the href.
   ```

2. **Don't use `datahub.assets.cbioportal.org/<study>.tar.gz`.** An unversioned
   "latest": no commit, no digest, contents change. Not hypothetical — the
   tarball and git copies of `schw_ctf_synodos_2025` already differ on 98 `Hugo_Symbol`
   values (`DDX58`/`RIGI`, `KIAA0100`/`BLTP2`, …), and the `nst_nfosi_ntap` tarball is a
   gnomAD-filtered re-release: 955 rows over 19 samples against the original 23,741 over 80.

3. **cBioPortal REST API** — `POST /api/molecular-profiles/{profile}/mutations/fetch?projection=DETAILED`
   with `{"sampleListId": "{study}_all"}`. Always current and needs no LFS, but returns
   a reduced field set: it has `mutationType` (= `Variant_Classification`),
   `proteinChange`, `ncbiBuild`, `tumorAltCount`/`tumorRefCount`, and **not**
   `Consequence` (SO terms), `HGVSc`, `HGVSp`, `HGNC_ID`, or gnomAD AF. Usable as a
   fallback and as a cross-check on the MAF, but it costs the SO-term mapping the issue
   proposes.

`fetch_cbioportal_maf.py` checks every fetched MAF for the columns the pipeline needs
(`Gene`, `HGNC_ID`, `Hugo_Symbol`, `Tumor_Sample_Barcode`) and a per-study row floor, so
a source that has been rewritten into a poorer form fails the run instead of losing data value.

### Note 1 — specimen join is study-specific

Three of the four studies join verbatim at 100%; only
`nst_nfosi_ntap` needs a derivation rule, and only it has residual gaps.

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

**The three CTF/Synodos studies** — their barcodes **are** the portal `specimenID`,
verbatim, at full coverage:

| Study | Barcode looks like | → specimenID | → individualID | Files | Project |
|---|---|---|---|---|---|
| `schw_ctf_synodos_2025` | `swn_patient_10_tumor_108` | **40 / 40** | 40 / 40 (22 individuals) | 474 | `syn9727752` |
| `nfib_ctf_biobank_2025` | `patient10tumor1` | **38 / 38** | 38 / 38 (10 individuals) | 487 | `syn4984604` |
| `lgg_ctf_synodos_2025` | `SYN_NF_004` | **21 / 21** | 21 / 21 (21 individuals) | 110 | `syn5698493` |

When no normalization rule, `BARCODE_RULES` tries `verbatim` before
`strip_last_segment` and each study falls to the rule that fits it. All three reach the
files the issue's drill-down needs, across WGS, WES, methylation array, RNA-seq, SNP
array and MudPIT.

The barcode→specimen rule belongs in a checked-in lookup (like the existing SSSOM
lookups) and unmatched counts belong in `validate_fks.py` as an asserted number. One crosswalk file holds
every study; a run rebuilds only the specified study and carries the others across, so
adding a study cannot delete another's rows (including hand-authored ones).

### Note 2 — per-row data quality

- **Assemblies.** Currently every one of the four pinned MAFs is 100% `GRCh38`.
- **27.5% of `nfib_ctf_biobank_2025` rows have `t_alt_count = 0`** (187,275 / 680,335) —
  no read in the tumor supports the allele. Ingesting them asserts a specimen carries a
  variant it has no support for, so that study runs with `--min-tumor-alt-count 1`
  (`MIN_TUMOR_ALT_COUNT` in `assets.py`), dropping them to 493,060 observations. The
  other three studies have at most 8 such rows and need no filter.
- `nst_nfosi_ntap`'s MAF has `t_depth`/`t_ref_count`/`t_alt_count` columns that are
  **entirely empty**, so no VAF is derivable for that study from the MAF (the API's
  `tumorAltCount`/`tumorRefCount` are populated — another reason to cross-check).
  `schw_ctf_synodos_2025`, `lgg_ctf_synodos_2025` and `nfib_ctf_biobank_2025` populate
  all three on every row, so VAF is real there.
- **`schw_ctf_synodos_2025` is the cleanest of the three**: 100% `GRCh38`, 
  **0** rows with `t_alt_count = 0`, `Consequence` and `IMPACT` on every row.
  Its `Mutation_Status` is blank throughout, so it relies on `vrsify --mutation-status
  Somatic` (the default, and correct for a `MUTATION_EXTENDED` profile). 83 rows carry
  neither an Ensembl nor an HGNC gene id and 128 carry Ensembl only; the latter fall back to
  Ensembl-keyed gene nodes and are reported as `gene via Ensembl only`.
- **Whole-genome studies reach where genes are not.** 32% of `lgg_ctf_synodos_2025`
  observations (19,946 / 61,890) resolve to no gene at all, compared to 25 / 23,741 for the
  exome-based `nst_nfosi_ntap`.
- `nst_nfosi_ntap` is unfiltered by consequence (5,659 `Intron`, 3,897 `Silent` rows), while 
  an earlier reprocessed `nfib_ctf_biobank_2025` was coding-only. 
  Decide whether the layer holds everything or only impactful consequences: 
  23,741 rows / 23,181 distinct alleles unfiltered vs
  12,614 rows / 12,362 alleles coding-only — **1.9×**, not the order of magnitude a
  glance at the `Intron` count suggests.

## Ingest tooling — `vrsify maf`

`vrsify` is a separate tool, published at
[nf-osi/vrsify](https://github.com/nf-osi/vrsify). Install it from the `develop` branch
rather than from a working copy, so every run of this pipeline uses the same build:

```sh
cargo install --git https://github.com/nf-osi/vrsify --branch develop
```

Run:

```sh
# One-time: derive refget SQ. accessions for the assembly the MAF declares.
vrsify seqmap --fasta GRCh38.fa --assembly GRCh38 --out seqmap.tsv

vrsify maf \
  --maf data_mutations.txt \
  --seqmap seqmap.tsv \
  --reference GRCh38.fa \               # required: see below
  --out-alleles alleles.ndjson \
  --out-observations obs.ndjson \
  --study-id nst_nfosi_ntap \
  --variant-id-prefix "nf:variant/" \   # required: see below
  --source "cbioportal:nst_nfosi_ntap/data_mutations.txt"
```

Behaviour the pipeline depends on:

- **`--reference` is not optional.** Substitutions are byte-exact without it, but
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
- **`--variant-id-prefix` is ours to supply.** A `ga4gh:VA.` id is a digest and means the
  same thing everywhere; the id of a row that *cannot* be normalized is only a key over
  the source coordinates, meaningful only inside the namespace that minted it. `vrsify`
  refuses to guess one, so it has no default and the run fails up front without either
  `--variant-id-prefix` or `--strict`. We pass `nf:variant/` — the prefix is
  concatenated verbatim, so the trailing separator is part of the value, and it is the
  namespace `variants_to_rdf.py` strips back off when it mints the IRI.
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
  vrsify maf --reference GRCh38.fa                  |
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
# One-time: install the ingest tool, then build a reference FASTA's refget accessions.
# The seqmap is load-bearing for indels.
cargo install --git https://github.com/nf-osi/vrsify --branch develop
vrsify seqmap --fasta hg38.fa --assembly GRCh38 --out seqmap.tsv
export VRSIFY_REFERENCE=/path/to/hg38.fa VRSIFY_SEQMAP=/path/to/seqmap.tsv
# VRSIFY_BIN only if `vrsify` is not on PATH (default: `vrsify`).

export KG_INCLUDE_VARIANTS=1        # gate 1: generate the layer at all
dagster asset materialize --select 'variants/*' -m orchestration.dagster_pipeline
```

The studies built are `VARIANT_STUDY_IDS` in `assets.py`; the gene layer is one asset
over **all** of their MAFs, not one per study.

Or step by step, which is what the assets shell out to (substitute any study id):

```sh
python scripts/fetch_cbioportal_maf.py --study nst_nfosi_ntap
python scripts/materialize_specimens.py
python scripts/map_cbioportal_samples.py \
    --maf data/raw/nst_nfosi_ntap_data_mutations.txt --study-id nst_nfosi_ntap
vrsify maf --maf data/raw/nst_nfosi_ntap_data_mutations.txt \
    --seqmap "$VRSIFY_SEQMAP" --reference "$VRSIFY_REFERENCE" \
    --out-alleles data/variants/nst_nfosi_ntap_alleles.ndjson \
    --out-observations data/variants/nst_nfosi_ntap_observations.ndjson \
    --study-id nst_nfosi_ntap --variant-id-prefix "nf:variant/"
python scripts/variants_to_rdf.py \
    --alleles data/variants/nst_nfosi_ntap_alleles.ndjson \
    --observations data/variants/nst_nfosi_ntap_observations.ndjson \
    --study-id nst_nfosi_ntap
```

Measured on `nst_nfosi_ntap`, ~36 s total excluding the reference download: MAF fetch
4 s, specimens 5 s, `vrsify maf` over 23,741 rows against the full 3.1 GB hg38 7 s, RDF
projection 23 s.

**`nfib_ctf_biobank_2025` is a different size of problem, and it set the memory
budget.** `vrsify` handles its 680,335 rows in about 4 s, but `variants_to_rdf.py`
originally built one rdflib `Graph` and serialized at the end — 493,060 observations →
17,587,310 triples took **~19 GB resident**, which is not a CI-sized job.

It now streams: triples go into a 50k-triple buffer that is serialized and appended,
so memory is a function of the batch, not the study. rdflib still does the serializing,
one batch at a time, so escaping and prefixed names are unchanged rather than
reimplemented by hand.

| | in-memory `Graph` | batched sink |
|---|---|---|
| `nst_nfosi_ntap` (856k triples) | 988 MB, 21.6 s, 46,330,768 B | **142 MB**, 20.6 s, 46,338,394 B |
| `nfib_ctf_biobank_2025` (17.6M triples) | ~19 GB, ~490 s | **150 MB**, 424 s, 945 MB |

Peak memory is now flat across a 20× difference in study size. Output is still prefixed,
subject-grouped Turtle — the file grew 0.02% on `nst_nfosi_ntap`, and its triple set is
identical to what the in-memory path produced (asserted in
`test_streaming_output_matches_an_in_memory_graph`). Plain N-Triples would have been
simpler but ~4× larger.

The catch batching introduces is the prefix table: a batch's `@prefix` header is written
only the first time each prefix appears, and a namespace rdflib invents in a later batch
is declared when it appears, which Turtle permits mid-document. Stripping headers
blindly would emit a file referencing an undeclared prefix; two tests cover it.

## The model

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
    nf:observesVariant ga4gh:VA.rDRjZ2kX3o3hvEAykAwbNXMw4dkisxiw ;
    nf:fromSpecimen   nf:specimen/JH-2-111-G645D ;
    nf:fromIndividual nf:individual/JH-2-111 ;
    nf:fromVariantDataset nf:variantDataset/nst_nfosi_ntap ;
    nf:hasConsequence obo:SO_0001587 ;              # stop_gained, via SSSOM
    nf:variantClassification "Nonsense_Mutation" ; nf:variantImpact "HIGH" ;
    nf:affectedGeneSymbol "NF1" ;
    nf:affectedGene <https://identifiers.org/hgnc:7765> ,          # the gene node
                    <https://identifiers.org/ensembl:ENSG00000196712> ;
    nf:ensemblGeneId "ENSG00000196712" ; nf:entrezGeneId "4763" ;
    nf:transcriptId "ENST00000356175" ; nf:exonNumber "28/57" ;
    nf:aminoacidChange "p.R1276*" ; nf:hgvsP "p.Arg1276Ter" ;
    nf:hgvsC "ENST00000356175.7:c.3826C>T" ; nf:proteinPosition "1276" ;
    nf:dbsnpId "rs199474742" ; nf:gnomadAlleleFrequency 6.57e-06 ;
    nf:mutationStatus "Somatic" ; nf:matchedNormalSampleBarcode "NORMAL" ;
    nf:normalDepth 127 ; nf:normalRefCount 125 ; nf:normalAltCount 0 ;
    nf:assemblyId "GRCh38" ; nf:sourceContig "17" ; nf:sourcePos 31235728 .

ga4gh:VA.rDRjZ2kX3o3hvEAykAwbNXMw4dkisxiw
    a biolink:SequenceVariant ;
    nf:vrsId "ga4gh:VA.rDRjZ2kX3o3hvEAykAwbNXMw4dkisxiw" ;
    nf:refgetAccession "SQ.upqChCoU-Gtd_61IidCsln-r8cxUTFeP" ;   # GRCh38 chr17
    nf:variantStart 31235727 ; nf:variantEnd 31235728 ; nf:variantState "T" .
```

No `nf:tumorAltCount` or `nf:variantAlleleFrequency` above, and that is the source, not
a bug: `nst_nfosi_ntap`'s MAF ships `t_depth`/`t_ref_count`/`t_alt_count` columns that
are entirely empty, so only the *normal* depths survive. The REST API does
populate the tumour counts, which is one reason to cross-check against it.

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
entity layers' source-data traps (see "Core entity layers" above).

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
coverage drops below 85% (currently 90.2% for `nst_nfosi_ntap`, 100% for
`schw_ctf_synodos_2025`).

## Still open

- **The 9 unresolved barcodes** in `nst_nfosi_ntap` (2,320 observations, 9.8%). They
   are in the graph but unattached. `JH-2-054`, `JH-2-060`, `JH-2-068`, `JH-2-079`,
   `JH-2-102` look like specimens the portal simply does not have; worth a curation
   check rather than a code fix. The other three studies have no equivalent gap.
