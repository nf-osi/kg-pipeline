# Demo 1 — Patient alleles vs. model systems: covered, and not covered

The inversion of [variant-layer-demo.md §B5](variant-layer-demo.md#b5-from-a-patients-allele-to-a-model-system-that-carries-it).
§B5 asks "is any patient allele already modelled?" and answers with 5 protein changes and
11 cell lines. This asks the question a funder asks:

> **Which recurrent patient alleles in these cohorts have no model system — ranked by how
> many specimens carry them?**

and its mirror, which curated models carry mutations no patient here has.

Built to the plan in [demo-1-model-coverage.md](demo-1-model-coverage.md). Every number
below is the result of a real run against the index described under Build context, not an
illustration.

## What changed to make it answerable

Three things, all of which §B5 named as blockers.

| | Before | After |
|---|---|---|
| Cell-line names | 0 of 636 cell lines carried `nf:name`; §B5's answer was a UUID | 664 of 664 |
| Curated mutations with an allele identity | none — the join was a protein string | 45 of 118 carry `nf:mutationVrsId` |
| Animal models reaching a human gene | 4 of 130, and 2 of those 4 are Cre drivers | 31 of 130 |

1. **Core rebuild.** The local snapshot predated `75eafb62` (2026-08-31), which both
   added `nf:name` and re-keyed every tool-type resource from `nf:cellLine/{id}` onto a
   shared `nf:resource/{resourceId}`. Rebuilding only `cell_lines.ttl` would have
   orphaned it from `mutation_model.ttl`, `nf1_mutation_sets.ttl`, `observation_links.ttl`
   and `files.ttl`, all of which still pointed at the old IRIs — so the whole core was
   rebuilt from the 2026-09-02 CSVs, `files.ttl` included.
2. **[`mappings/orthologs.tsv`](../../mappings/orthologs.tsv)** — 7 ortholog pairs over
   the genes in `mutations.csv`, from a digest-pinned Alliance of Genome Resources
   release. This is what lets a mouse `Nf1` model meet a human `NF1` gene node.
3. **[`mappings/model_mutation_vrs.tsv`](../../mappings/model_mutation_vrs.tsv)** — VRS
   digests for the 45 curated mutations that carry a ClinVar expression, minted with the
   same `vrsify` and the same GRCh38 reference as the patient alleles. This is what turns
   the model↔patient join from a string comparison into an identity.

## Build context

| | |
|---|---|
| Repo | `c1c7b0a2` (`impl-demo-1`) |
| Index | `docker build --target runtime-variants -t kg:variants-demo1 .` → **26,898,127 triples**, served on `:7004` |
| Contents | `schema/{ontology,shapes}.ttl` + `data/rdf/*.ttl` + `data/rdf/variants/*.ttl` |
| Core snapshot | rebuilt 2026-09-18 from `data/csv/*` (2026-09-02); `specimens.ttl`/`genes.ttl` 2026-09-17 |
| Variant layer | 4 studies, built 2026-09-17 — 607,690 alleles, 620,565 observations, 169 specimens |
| Ortholog source | Alliance of Genome Resources 9.0.0, Stringent filter, file generated 2026-04-05 UTC, `sha256:977ad252…` |
| Coordinate sources | NCBI Variation Services + ClinVar E-utilities, accessed 2026-09-18 |
| Model mutation VRS | `vrsify 0.1.0`, GRCh38 (`hg38.fa` + `seqmap.tsv`), minted 2026-09-18 |

The previous index (`:7002`, 26,124,204 triples) is the one §B5 was measured on. The
774k-triple difference is the core rebuild plus 87 triples of new bridge.

```sh
Q="python scripts/query_sparql.py --endpoint http://localhost:7004 --format tsv"
$Q --canned variant-model-match        --bind gene=NF1
$Q --canned variant-model-gap          --bind minSpecimens=4
$Q --canned variant-model-gap-genes    --bind minSpecimens=10
$Q --canned model-without-patient-allele
```

---

## 1. The two tiers, and what the second one is for

Every query here labels the tier a row came from, because they do not mean the same thing.

| Tier | Join | What it asserts |
|---|---|---|
| **1 — allele identity** | `nf:mutationVrsId` == `nf:vrsId` | the curated mutation *is* the patient's allele. Nothing is compared but the digest |
| **2 — protein string** | `nf:proteinVariation` == `nf:hgvsP`, gene constrained on both sides | the two spell the same protein change. Same locus, probably the same allele |

Tier 2 is not a weaker tier 1; it is the tier for mutations that can never reach tier 1.
Of 118 curated mutations, 45 carry a ClinVar expression with a transcript accession and so
have coordinates. The other 73 carry a bare cDNA string (`c.910C>T`) or free text
(`Ex16-35del`, *"De novo Alu repeat insertion in intron between exons 5 and 6"*) — with no
transcript there is nothing to project, and [new-layers.md §1](new-layers.md) puts
VariantValidator/VEP projection out of scope.

How the two tiers divide the 118:

| | has a protein string | no protein string |
|---|---|---|
| **has a VRS digest** | 40 — both tiers | 5 — tier 1 only |
| **no VRS digest** | **10 — tier 2 only** | 63 — reachable by neither |

**Measured on this index, tier 2 adds nothing tier 1 does not already find.** Of 65,163
protein-altering patient alleles, 5 are modelled at tier 1 and **0 more at tier 2 only** —
none of the 10 tier-2-only mutations matches a call in these cohorts. That is a result
about this data, not a property of the design. Tier 2 stays because those 10 are one
curation pass away from mattering, and because 63 mutations reachable by neither tier is
the number that should drive the next curation ask.

## 2. §B5 reproduced, and one model it could not see

`--canned variant-model-match --bind gene=NF1`. All 5 of §B5's protein changes and all 11
of its cell lines survive digest-level identity — and the names are names now.

| Tier | Patient change | Curated protein | Curated ClinVar expression | Model | Kind | Specimens |
|---|---|---|---|---|---|---|
| 1 | `p.Arg192Ter` | `p.Arg192Ter` | `NM_000267.3(NF1):c.574C>T` | HEK293 NF1 −/− with R192X mNf1 cDNA | cell line | 2 |
| 1 | `p.Arg816Ter` | `p.Arg816Ter` | `NM_000267.3(NF1):c.2446C>T` | hTERT NF1 ipNF95.6 | cell line | 1 |
| 1 | `p.Arg816Ter` | `p.Arg816Ter` | ″ | NCC-MPNST3-C1, NCC-MPNST3-X2-C1, iPSC NF1 +/− BJFF.6 bkgd, HEK293 & Schwann cell R816X lines | cell line | 1 |
| 1 | `p.Gly629Arg` | `p.Gly629Arg` | `NM_000267.3(NF1):c.1885G>A` | HEK293 NF1 −/− Exon 17 #A15 / #B48 G629R cryptic splice | cell line | 1 |
| 1 | `p.Arg304Ter` | `p.Arg304Ter` | `NM_000267.3(NF1):c.910C>T` | **ST88-14** | cell line | 1 |
| 1 | `p.Arg1968Ter` | `p.Arg1968Ter` | `NM_001042492.3(NF1):c.5902C>T` | RG-315 | cell line | 1 |
| **1** | **`p.Arg1968Ter`** | — | **`NM_000267.3(NF1):c.5839C>T (p.Arg1947Ter)`** | **Nf1pArg1947mp1** | **animal model** (*Sus scrofa*) | **1** |

**5 alleles, 11 cell lines, 1 animal model, 6 patient specimens.** §B5 measured 5 / 11 / 6
on the protein string alone; the pig is what identity adds.

The last row is new, and it is the clearest single argument for the allele-identity tier.

`Nf1pArg1947mp1` is an Ossabaw minipig — *"[From GFF:] Minipig model containing a recurrent
nonsense mutation p.Arg1947\*(R1947\*)"* — commercially available, with a linked
publication. It carries the **same allele** as a cutaneous neurofibroma from
`patient9tumor1` in the `nfib_ctf_biobank_2025` cohort: `ga4gh:VA.XdnQRoJrH9WSI8nL-PwhTedWxDF9K0s3`,
a `stop_gained` (`obo:SO_0001587`).

The protein-string join could not find it, for two independent reasons:

- The curated record has **no `nf:proteinVariation` at all** — only the ClinVar
  expression. There is no string for tier 2 to compare.
- Even if there were, it would be `p.Arg1947Ter` (NM_000267.3 numbering) against the
  patient's `p.Arg1968Ter` (NM_001042492.3). Different strings, one allele. This is
  [pitfall 3](variant-layer-demo.md#pitfalls-these-queries-encode) with a model system on
  the other end of it.

Minting VRS for the curated mutations collapses five such pairs:

| One allele | Curated as | and as |
|---|---|---|
| `ga4gh:VA.XdnQRoJrH9WSI8nL…` | `c.5839C>T (p.Arg1947Ter)` | `c.5902C>T (p.Arg1968Ter)` |
| `ga4gh:VA.YKk2jMj6SzNIt6Op…` | `c.5425C>T (p.Arg1809Cys)` | `c.5488C>T (p.Arg1830Cys)` |
| `ga4gh:VA.8dFC65IBLKl0Isk0…` | `NM_000267.3:c.3158C>G` | `NM_001042492.3:c.3158C>G` |
| `ga4gh:VA.pjTOXfH_cUb4dtkw…` | `NF1 c.2041C>T` | `Nf1 c.2041C>T` (mouse casing) |
| `ga4gh:VA.QRPxJFmsOsOhfJOR…` | `NF1 c.2542G>C` | `Nf1 c.2542G>C` |

40 distinct curated expressions, **37 distinct alleles**.

## 3. The gap list

`--canned variant-model-gap --bind minSpecimens=4`. Protein-altering alleles in ≥4
specimens with no model on either tier. 54 rows; the top 12:

| Gene | Protein change(s) | Specimens | Cohorts | gnomAD AF | Gene alleles/specimen | Flag | Tumour types |
|---|---|---|---|---|---|---|---|
| ADPRHL1 | `p.Arg1805Trp` / `p.Arg1441Trp` | 25 | 3 | 1.6e-4 | 0.18 | **artifact + gnomAD-frequent** | MPNST, pNF, cNF, DIN, PA, PMA, LGG |
| KRTAP1-3 | `p.Phe44Cys` | 12 | 4 | — | 0.08 | **artifact** | cNF, pNF, schwannoma, PA |
| LRRCC1 | `p.Ala6Val` | 11 | 2 | 6.6e-6 | 0.65 | — | MPNST, cNF, pNF, aNF, schwannoma |
| HELLS | `p.Ser425Gly` | 8 | 1 | — | 0.62 | — | schwannoma |
| BMP6 | `p.Gln118Leu` | 7 | 1 | — | 0.50 | — | schwannoma |
| DYNC1I1 | `p.Thr602Ala` | 7 | 1 | — | 0.40 | **artifact** | schwannoma |
| ARGFX | `p.Ala71Gly` | 6 | 1 | — | 0.50 | — | schwannoma |
| LNP1 | `p.His65Leu` | 6 | 3 | — | 0.31 | **artifact** | MPNST, pNF, cNF, schwannoma |
| MYEOV | `p.Leu307Ile` | 6 | 2 | 2.6e-4 | 0.17 | **artifact + gnomAD-frequent** | MPNST, pNF, schwannoma |
| **NF1** | **`p.Arg1534Ter` / `p.Arg1513Ter`** | **6** | **3** | 6.6e-6 | **0.95** | — | **pNF, DIN, aNF, cNF, PA** |
| UNC80 | `p.Asp749Val` | 6 | 2 | — | 1.15 | — | cNF, diffuse astrocytoma |
| BICDL1 | `p.Ala42del` | 5 | 1 | 6.6e-6 | 0.57 | — | schwannoma |

**Read the flag column before reading the ranking.** The top two rows are what
[§A3](variant-layer-demo.md#a3-ranking-genes-without-being-fooled-by-gene-length) predicts:
`gene alleles/specimen` far below 1 means a handful of alleles shared by many samples,
which is the signature of germline leakage or a mapping artifact, not of a recurrent
somatic driver. ADPRHL1 has 5 alleles across 28 specimens; KRTAP1-3 is a keratin-associated
protein in a repeat family. Both are flagged and both stay on the list — the plan asked
for flags rather than silent filtering, and a demo that quietly drops rows is not auditable.

The one row on this list with the driver signature is **NF1 `p.Arg1534Ter`** — 0.95 alleles
per specimen, 6 specimens, 3 of 4 cohorts, 5 tumour types, gnomAD AF 6.6e-6, no model
system in the registry. That is the work order. (And it is one allele: `p.Arg1534Ter` and
`p.Arg1513Ter` are the same call spelled against two transcripts, which is why the query
groups on `nf:vrsId`. Grouped on the protein string it would appear twice, lower down.)

Restricted to NF1, the complete list of unmodelled recurrent alleles is short enough to act
on:

| NF1 allele | Specimens | Cohorts | Tumour types |
|---|---|---|---|
| `p.Arg1534Ter` / `p.Arg1513Ter` | 6 | 3 | pNF, cNF, aNF, DIN, PA |
| `p.Phe2083ProfsTer15` | 4 | 1 | MPNST, pNF |
| `p.Arg2450Ter` | 2 | 1 | cNF |
| `p.Gln1703Ter` | 2 | 1 | pNF |

How much of the list is threshold: 563 alleles in ≥2 specimens, 144 in ≥3, 54 in ≥4, 21 in
≥5. At ≥4, 13 of 54 carry a flag.

## 4. Gene-level coverage, with the animal models finally in it

`--canned variant-model-gap-genes`. Before the ortholog crosswalk, **4 of 130 animal models
reached any human gene**, and two of those four were Gfap-Cre drivers. Now 31 do.

| Gene | Specimens | Alleles | Cohorts | Cell lines | Animal models | Route | Model species |
|---|---|---|---|---|---|---|---|
| **NF1** | 42 | 40 | 4 | 89 | **30** | direct + ortholog | mouse, zebrafish, pig, unstated |
| COL3A1 | 8 | 13 | 3 | 4 | 0 | direct | — |
| MTOR | 8 | 13 | 3 | 1 | 0 | direct | — |
| ARAF | 7 | 8 | 3 | 1 | 0 | direct | — |
| BRCA2 | 7 | 15 | 3 | 1 | 0 | direct | — |
| **SUZ12** | 7 | 6 | 2 | 0 | **1** | **ortholog only** | mouse |
| KDM6A | 6 | 12 | 3 | 5 | 0 | direct | — |
| **TP53** | 6 | 7 | 3 | 8 | **3** | direct + ortholog | mouse |
| GFAP | 4 | 4 | 2 | 0 | 2 | direct | mouse — ⚠ *driver line* |
| PIK3CA | 4 | 5 | 3 | 2 | 0 | direct | — |
| TSC1 | 4 | 5 | 2 | 1 | 0 | direct | — |
| **PTPN11** | 3 | 4 | 2 | 0 | **1** | **ortholog only** | mouse |

Those twelve are the whole of it. Every other observed gene has zero models, including the
top of the cohort ranking:

| Gene | Specimens | Alleles | Cohorts | Models |
|---|---|---|---|---|
| TTN | 43 | 218 | 3 | **0** |
| MUC16 | 29 | 81 | 4 | **0** |
| ADPRHL1 | 28 | 5 | 3 | **0** |
| **NF2** | **28** | **28** | **3** | **0** |
| LRTM3 | 26 | 50 | 3 | **0** |
| OBSCN | 25 | 52 | 4 | **0** |

TTN, MUC16, OBSCN and LRTM3 are the long-gene passenger signature §A3 describes — no model
is needed and none should be built. **NF2 is not.** 28 specimens, 28 alleles, 1.00 alleles
per specimen across 3 cohorts: the same driver signature as NF1, and not one cell line or
animal model in the registry carries an NF2 mutation. For a portfolio that funds
NF2-related schwannomatosis, that is the single most consequential row in this document.

Three caveats belong on the slide with this table:

- **A gene-level match is not an allele match.** A mouse `Nf1` knockout covers an NF1
  patient at the mechanism level. The `route` column says which rows depend on that
  weaker claim, and `mappings/orthologs.tsv` carries the per-pair supporting-algorithm
  counts (NF1↔Nf1 is 10/10; NF1↔`nf1b` is 1/10).
- **GFAP's two models are Cre drivers**, not GFAP models — the curated symbol names the
  promoter driving Cre, not a broken gene. The query flags this from
  `nf:alleleType = Recombinase`, and `mappings/orthologs.tsv` lists `GFAP`, `SynI` and
  `Dhh` as `status=excluded` with the reason, so their absence from the ortholog graph is
  a decision on the record. The `GFAP` row survives only because `GFAP` is also a real
  human symbol and reaches the gene by the direct route, where no ortholog row exists to
  exclude it. **This is a curation problem, not a query problem**: a driver line should
  not be curated as a mutation in the promoter's gene.
- **CDKN2A does not appear**, despite having 5 cell lines and 1 mouse model. It scores
  0 of 169 specimens because this layer carries small variants only and CDKN2A is lost by
  deletion. Absence from this table is not absence of alteration — see
  [demo 3](demo-3-copy-number.md).

## 5. The mirror: models carrying alleles no patient here has

`--canned model-without-patient-allele`. Of the 111 curated mutations attached to a model,
**8 match a patient allele and 103 do not** — split into two findings that should not be
read as one:

| Reason | Mutations | Models affected | What it means |
|---|---|---|---|
| 1 — allele minted, never observed | 33 | 100 | a real statement about these four cohorts |
| 2 — no VRS identity mintable | 70 | 142 | a statement about the curation, not about patients |

(The two model counts overlap: a line carrying both an `Nf1` allele and a Cre transgene is
in both rows.)

Examples of the first kind, which is the kind that can be quoted:

| Gene | Curated | Allele | Models |
|---|---|---|---|
| NF1 | `c.2041C>T` (`p.Arg681*`) | `ga4gh:VA.pjTOXfH_cUb4dtkw…` | **12** (mouse Nf1 R681X series) |
| NF1 | `c.5492G>A` (`p.Trp1831Ter`) | `ga4gh:VA.HxX91-uLiT_BHxVf…` | 5 (RG-137 … RG-141) |
| NF1 | `c.1756_1759del` (`p.Thr586fs`) | `ga4gh:VA.bPbJsk8rEE-uTMSj…` | 4 |
| COL3A1 | `c.766delA` (`p.Ile256Tyrfs*7`) | `ga4gh:VA.AUrZTFqDgja7bDWX…` | 4 (GM22606–GM22609) |
| NF1 | `c.6641+1G>T` | `ga4gh:VA.Snm0jh43GQWHRQUL…` | 4 (icNF98.4c/d, cNF98.4c/d) |
| PIK3CA | `c.1624G>A` (`p.Glu542Lys`) | `ga4gh:VA.EQ5CsXtT8KcVEtOU…` | 2 (NCC-MPNST3 pair) |

The `p.Arg681*` row is the honest reading of the whole exercise: twelve model systems carry
an allele that none of 169 sequenced specimens here does. That is **not** evidence the
models are wrong — R681X is a well-known recurrent NF1 allele and these cohorts are four
convenience samples, not a population. It is evidence that *this registry's model portfolio
and this registry's sequenced patients were assembled independently*, which is exactly the
thing the graph is now able to say.

The second group is mostly HEK293/Schwann-cell engineering lines whose curated
`nf:sequenceVariation` records the editing scar (`c.101del`, `c.102del`, `c.103del`,
`c.103_104delins122`, each on 14 or 4 lines) rather than a patient-comparable allele. Those
should never appear in a coverage claim in either direction, and the `reason` column keeps
them from doing so.

## 6. Two curation defects the crosswalk surfaced

Neither was looked for.

1. **`NF1 c.2542G>T` vs `c.2542G>C`.** Mutation `7658c873…` records
   `humanClinVarMutation: NM_000267.3(NF1):c.2542G>C (p.Gly848Arg)` and
   `sequenceVariation: c.2542G>T`. Codon 848 is `GGG`; `G>C` gives `CGG` (Arg, as
   curated), `G>T` gives `TGG` (Trp). The cDNA column contradicts the other two columns
   on the same row, and ClinVar has no `NM_000267.3:c.2542G>T` record at all. Minting
   from the ClinVar expression is what made the two columns comparable.
2. **`NM_000546.5(TP53):c.405C>G` is pinned to a retired transcript version.** ClinVar
   indexes HGVS against the *current* RefSeq version only, so the curated string finds
   nothing; NCBI now files it under `NM_000546.6`. The minting script walks the version
   forward and records the substitution in the row's `notes`, and the digest is still only
   accepted because the two independent resolvers agree on the coordinates.

A third, found while pinning down which table version the first two are against:
`mutationDetailsId` is not unique in `syn26486835` v11 — 120 rows, 118 distinct ids. Of the
two duplicated pairs, one is a plain duplicated row already filed upstream; the other holds
the same allele written against two NF1 transcripts, and is the one worth reporting.

All three are written up as submittable issue text, with the source-version provenance
worked out, in [curation-issues-from-demo-1.md](curation-issues-from-demo-1.md). The first
two are visible in `mappings/model_mutation_vrs.tsv`.

## What this cannot answer

- **Recurrence here is not population recurrence.** Four cohorts, four assay designs, four
  calling pipelines. "Unmodelled in this registry, observed in these cohorts" is the
  strongest claim any row supports. An allele can be rare here and common in NF overall,
  and the reverse.
- **No model ≠ no relevant model.** Coverage is computed over what NF-OSI curates. A model
  that exists but is not in the registry, or is in the registry with its mutation
  uncurated, reads as a gap. 73 of 118 curated mutations have no mintable identity, so the
  tier-1 gap list is an upper bound on the gap.
- **Small variants only.** No CNV, no structural variants, no fusions; CDKN2A's absence
  above is the visible consequence.
- **Absence of a call is not wild type.** A specimen with no call in a gene may be
  uncovered or filtered.
- **The artifact flags are heuristics.** `alleles/specimen` has no background model and no
  gene-length term, and gnomAD AF is present on only a minority of calls, so an unflagged
  row is not certified somatic.
- **`nf:orthologOf` says nothing about the allele.** The ortholog layer is 7 pairs over 5
  human genes, and covers only the genes in `mutations.csv` — by design
  ([out of scope](demo-1-model-coverage.md#out-of-scope)), not by omission.

## Reproducing this

```sh
# 1. Rebuild the core. The whole core, not just cell_lines: 75eafb62 re-keyed the
#    resource IRIs, so a partial rebuild orphans the mutation and observation links.
#    This run reused the 2026-09-02 CSVs rather than re-fetching from Synapse: every
#    mapping was re-run with RMLMapper directly (files.rml.ttl chunked at 100k rows via
#    RMLMapperResource.run_chunked), then the three derived materializers.
dagster asset materialize --select 'portal/*' -m orchestration.dagster_pipeline

# 2. The two bridges. Both need the network and neither is a pipeline asset; both write
#    a reviewed TSV into mappings/ that the pipeline then serializes.
python scripts/fetch_orthologs.py                 # -> mappings/orthologs.tsv
python scripts/mint_model_mutation_vrs.py         # -> mappings/model_mutation_vrs.tsv
python scripts/materialize_orthologs.py           # -> data/rdf/orthologs.ttl
python scripts/materialize_model_mutation_vrs.py  # -> data/rdf/model_mutation_vrs.ttl

# 3. Index and serve.
export KG_INCLUDE_VARIANTS=1
dagster asset materialize --select 'variants/*' -m orchestration.dagster_pipeline
docker build --target runtime-variants -t kg:variants-demo1 .
docker run -d --name kg-variants-demo1 -p 7004:7001 kg:variants-demo1
```

`fetch_orthologs.py --check` fails if the checked-in TSV is stale.
`check_source_versions.py --check-external` re-hashes the pinned Alliance release and
reports drift without editing the pin.

## New pitfalls, for the list in variant-layer-demo.md

10. **QLever's `GROUP_CONCAT` returns the empty string for the whole group if any member
    is unbound.** Concatenating `nf:species` over a gene's models blanked the column for
    every gene that has both cell lines (no species) and animal models (species) — not
    just the cell-line rows, the entire cell. `COALESCE(?species, "unstated")` fixes it.
    Same failure family as [pitfall 4](variant-layer-demo.md#pitfalls-these-queries-encode)
    (`GROUP_CONCAT` over an IRI), and just as silent.
11. **A canned-query parameter that lands outside a string literal cannot be made safe by
    escaping quotes.** `HAVING(… >= {minSpecimens})` interpolates into SPARQL, not into a
    literal, so `query_sparql.py` validates numeric binds as integers instead. See
    `numeric_binds` in `CANNED_QUERIES`.
12. **Group the gap list on `nf:vrsId`, not on the protein string** — the allele-level
    counterpart of pitfall 3. ADPRHL1's single allele reports as 18 + 7 specimens when
    grouped by string and 25 when grouped by digest, which moves it four places up the
    ranking and changes which flag fires.
