# Patient alleles vs. model systems representation and gaps

"Is any patient allele already modelled?" can be answered, leading to one result with 5 protein changes and
11 cell lines. This demo addresses another question a funder might ask:

> **Which recurrent patient alleles in these cohorts have no model system — ranked by how
> many specimens carry them?**

and its mirror, which curated models carry mutations no patient has.

## What makes it answerable

| | Before | After |
|---|---|---|
| Curated mutations with an allele identity | none — the join was a protein string | 45 of 118 carry `nf:mutationVrsId` |
| Animal models reaching a human gene | 4 of 130, and 2 of those 4 are Cre drivers | 31 of 130 |

- **[`mappings/orthologs.tsv`](../../mappings/orthologs.tsv)** — 7 ortholog pairs over
   the genes in `mutations.csv`, from a digest-pinned Alliance of Genome Resources
   release. This is what lets a mouse `Nf1` model meet a human `NF1` gene node.
- **[`mappings/model_mutation_vrs.tsv`](../../mappings/model_mutation_vrs.tsv)** — VRS
   digests for the 45 curated mutations that carry a ClinVar expression, minted with the same
   `vrsify` and GRCh38 reference as the patient alleles. This is what turns
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

```sh
Q="python scripts/query_sparql.py --endpoint http://localhost:7004 --format tsv"
$Q --canned variant-model-match        --bind gene=NF1
$Q --canned variant-model-gap          --bind minSpecimens=4
$Q --canned variant-model-gap-genes    --bind minSpecimens=10
$Q --canned model-without-patient-allele
```

---

## 1. Two matching tiers

Every result records how the patient and model variants were matched because the two matching strategies support different claims.

| Tier | Join | What it asserts |
|---|---|---|
| **1 — allele identity** | `nf:mutationVrsId` == `nf:vrsId` | the curated mutation *is* the patient's allele. Nothing is compared but the digest |
| **2 — protein string** | `nf:proteinVariation` == `nf:hgvsP`, gene constrained on both sides | the two spell the same protein change in the same gene; nucleotide alleles can differ |

Tier 2 supplies matches only where an allele-identity match is unavailable for the same model-mutation/patient-allele pair. 
A Tier 1 match suppresses the corresponding Tier 2 result for that pair, but another patient allele producing the same protein change can still appear as Tier 2.

The gap analysis operates at the VRS allele level: if any gene/protein annotation for an allele matches a model, that allele is considered represented. 
This prevents alternate transcript annotations from causing the same biological allele to appear both matched and unmatched.

Of 118 curated mutations, 45 contain a ClinVar expression with enough transcript information to resolve genomic coordinates. 
The remaining 73 contain only bare cDNA expressions such as c.910C>T or free-text descriptions such as Ex16-35del. 
Without a transcript accession, those records cannot be projected reliably to genomic coordinates and therefore cannot currently receive VRS identity.

The 118 mutations divide as follows:

| | has a protein string | no protein string |
|---|---|---|
| **has a VRS digest** | 40 — both tiers | 5 — tier 1 only |
| **no VRS digest** | **10 — tier 2 only** | 63 — reachable by neither |

**With the current data, tier 2 does not add any additional patient matches.** Of 65,163
protein-altering patient alleles, 5 are modelled at tier 1 and 
**0 additional alleles are represented only through Tier 2**. 

The 10 Tier-2-only mutations remain potentially useful if future cohorts contain matching protein changes. 
More importantly, the 63 mutations reachable by neither tier identify a clear model-curation gap.

## 2. Patient alleles represented in the current model registry

`--canned variant-model-match --bind gene=NF1`.

| Tier | Patient change | Curated protein | Curated ClinVar expression | Model | Kind | Specimens |
|---|---|---|---|---|---|---|
| 1 | `p.Arg192Ter` | `p.Arg192Ter` | `NM_000267.3(NF1):c.574C>T` | HEK293 NF1 −/− with R192X mNf1 cDNA | cell line | 2 |
| 1 | `p.Arg816Ter` | `p.Arg816Ter` | `NM_000267.3(NF1):c.2446C>T` | hTERT NF1 ipNF95.6 | cell line | 1 |
| 1 | `p.Arg816Ter` | `p.Arg816Ter` | ″ | NCC-MPNST3-C1, NCC-MPNST3-X2-C1, iPSC NF1 +/− BJFF.6 bkgd, HEK293 & Schwann cell R816X lines | cell line | 1 |
| 1 | `p.Gly629Arg` | `p.Gly629Arg` | `NM_000267.3(NF1):c.1885G>A` | HEK293 NF1 −/− Exon 17 #A15 / #B48 G629R cryptic splice | cell line | 1 |
| 1 | `p.Arg304Ter` | `p.Arg304Ter` | `NM_000267.3(NF1):c.910C>T` | **ST88-14** | cell line | 1 |
| 1 | `p.Arg1968Ter` | `p.Arg1968Ter` | `NM_001042492.3(NF1):c.5902C>T` | RG-315 | cell line | 1 |
| **1** | **`p.Arg1968Ter`** | — | **`NM_000267.3(NF1):c.5839C>T (p.Arg1947Ter)`** | **Nf1pArg1947mp1** | **animal model** (*Sus scrofa*) | **1** |

**5 alleles, 11 cell lines, 1 animal model, 6 patient specimens.**

`Nf1pArg1947mp1` is an Ossabaw minipig — *"[From GFF:] Minipig model containing a recurrent
nonsense mutation p.Arg1947\*(R1947\*)"* — commercially available, with a linked
publication. It carries the **same allele** as a cutaneous neurofibroma from
`patient9tumor1` in the `nfib_ctf_biobank_2025` cohort: `ga4gh:VA.XdnQRoJrH9WSI8nL-PwhTedWxDF9K0s3`,
a `stop_gained` (`obo:SO_0001587`).

A protein-string join would not find it, for two independent reasons:

- The curated record has **no `nf:proteinVariation` at all**, only the ClinVar
  expression. There is no string for tier 2 to compare.
- Even if there were, it would be `p.Arg1947Ter` (NM_000267.3 numbering) against the
  patient's `p.Arg1968Ter` (NM_001042492.3). The strings differ because of transcript choice;
  the VRS identity shows that they represent the same allele.

Minting VRS for the curated mutations collapses five such pairs:

| One allele | Curated as | and as |
|---|---|---|
| `ga4gh:VA.XdnQRoJrH9WSI8nL…` | `c.5839C>T (p.Arg1947Ter)` | `c.5902C>T (p.Arg1968Ter)` |
| `ga4gh:VA.YKk2jMj6SzNIt6Op…` | `c.5425C>T (p.Arg1809Cys)` | `c.5488C>T (p.Arg1830Cys)` |
| `ga4gh:VA.8dFC65IBLKl0Isk0…` | `NM_000267.3:c.3158C>G` | `NM_001042492.3:c.3158C>G` |
| `ga4gh:VA.pjTOXfH_cUb4dtkw…` | `NF1 c.2041C>T` | `Nf1 c.2041C>T` (mouse casing) |
| `ga4gh:VA.QRPxJFmsOsOhfJOR…` | `NF1 c.2542G>C` | `Nf1 c.2542G>C` |

The 40 distinct curated ClinVar expressions therefore resolve to 37 distinct alleles.

## 3. Patient alleles not represented in the model registry

Running:

`$Q --canned variant-model-gap --bind minSpecimens=4`

returns protein-altering alleles observed in at least 4 specimens that have no matching model under either tier.

There are 54 such alleles. The top 12 by specimen count are:

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

**Read the flag column before reading the ranking.** 

A high specimen count does not by itself identify a biologically meaningful recurrent event. 
The top two rows are a known artifact: `gene alleles/specimen` far below 1 means a handful of alleles shared by many samples, 
which is the signature of germline leakage or a mapping artifact, not of a recurrent somatic driver. 
ADPRHL1 has 5 alleles across 28 specimens; KRTAP1-3 is a keratin-associated protein in a repeat family. 
These rows remain visible rather than being silently filtered so that the ranking stays auditable.

The one row on this list with the driver signature is **NF1 `p.Arg1534Ter`** — 0.95 alleles
per specimen, 6 specimens, 3 of 4 cohorts, 5 tumour types, gnomAD AF 6.6e-6, and no model
system in the registry. 

p.Arg1534Ter and p.Arg1513Ter are two transcript-level protein descriptions of the same VRS allele. 
Grouping by nf:vrsId correctly treats them as one event.

Restricted to NF1, the recurrent registry gaps are short enough to inspect directly:

| NF1 allele | Specimens | Cohorts | Tumour types |
|---|---|---|---|
| `p.Arg1534Ter` / `p.Arg1513Ter` | 6 | 3 | pNF, cNF, aNF, DIN, PA |
| `p.Phe2083ProfsTer15` | 4 | 1 | MPNST, pNF |
| `p.Arg2450Ter` | 2 | 1 | cNF |
| `p.Gln1703Ter` | 2 | 1 | pNF |

The size of the gap list is sensitive to the recurrence threshold:
- 563 alleles in ≥2 specimens
- 144 in ≥3
- 54 in ≥4
- 21 in ≥5

But consider that at ≥4, 13 of 54 rows carry an artifact or frequency flag.

## 4. Gene-level model representation

Allele-level matching is appropriate for asking whether a specific patient variant has a corresponding model. 
Animal models also support a broader question: is the altered human gene represented by any curated model of that gene or its ortholog?

The ortholog layer makes this comparison possible.

Before adding it, only 4 of 130 animal models connected to a human gene, and 2 of those 4 were Cre driver lines. With the crosswalk, 31 of 130 do.

Among genes observed in the patient cohorts, the model registry currently contains:

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

These are the only observed genes with a model connection in the current registry.

Several highly observed genes have no corresponding curated model:

| Gene | Specimens | Alleles | Cohorts | Models |
|---|---|---|---|---|
| TTN | 43 | 218 | 3 | **0** |
| MUC16 | 29 | 81 | 4 | **0** |
| ADPRHL1 | 28 | 5 | 3 | **0** |
| **NF2** | **28** | **28** | **3** | **0** |
| LRTM3 | 26 | 50 | 3 | **0** |
| OBSCN | 25 | 52 | 4 | **0** |

TTN, MUC16, OBSCN, and LRTM3 show patterns consistent with long-gene/passenger effects — no model
is needed and none should be built. 

But **NF2** is different in this dataset: 28 specimens contain 28 NF2 alleles across 3 cohorts, 
for exactly 1.00 allele per specimen, yet the current registry contains no cell line or animal model linked to an NF2 mutation.

That makes NF2 a prominent registry representation gap for follow-up, especially in a portfolio that includes NF2-related schwannomatosis.

### Important qualifications

- **A gene-level match is not an allele match.** A mouse `Nf1` knockout covers an NF1
  patient at the mechanism level. The `route` column says which rows depend on that
  weaker claim, and `mappings/orthologs.tsv` carries the per-pair supporting-algorithm
  counts (NF1↔Nf1 is 10/10; NF1↔`nf1b` is 1/10).
- **GFAP's two models are Cre drivers**, not GFAP models — the curated symbol names the
  promoter driving Cre, not a broken gene. The query flags this from
  `nf:alleleType = Recombinase`, and `mappings/orthologs.tsv` lists `GFAP`, `SynI` and
  `Dhh` as `status=excluded` with the reason, so their absence from the ortholog graph is
  clear. The `GFAP` row survives only because `GFAP` is also a real
  human symbol and reaches the gene by the direct route, where no ortholog row exists to
  exclude it. **This is a curation problem, not a query problem**: a driver line should
  not be curated as a mutation in the promoter's gene.
- **CDKN2A does not appear**, despite having 5 cell lines and 1 mouse model. It scores
  0 of 169 specimens because this layer carries small variants only and CDKN2A is lost by
  deletion. Absence from this table is not absence of alteration.

## 5. The mirror analysis: model alleles not observed in these cohorts

Running:

`$Q --canned model-without-patient-allele`

examines the comparison from the model side.

Of 111 curated mutations attached to a model: 8 match a patient allele, 103 do not.

The 103 unmatched mutations fall into two importantly different categories:

| Reason | Mutations | Models affected | What it means |
|---|---|---|---|
| 1 — allele minted, never observed | 33 | 100 | a real statement about these four cohorts |
| 2 — no VRS identity mintable | 70 | 142 | a statement about the curation, not about patients |

(The two model counts can overlap: a line carrying both an `Nf1` allele and a Cre transgene is
in both rows.)

Examples from the first category are:

| Gene | Curated | Allele | Models |
|---|---|---|---|
| NF1 | `c.2041C>T` (`p.Arg681*`) | `ga4gh:VA.pjTOXfH_cUb4dtkw…` | **12** (mouse Nf1 R681X series) |
| NF1 | `c.5492G>A` (`p.Trp1831Ter`) | `ga4gh:VA.HxX91-uLiT_BHxVf…` | 5 (RG-137 … RG-141) |
| NF1 | `c.1756_1759del` (`p.Thr586fs`) | `ga4gh:VA.bPbJsk8rEE-uTMSj…` | 4 |
| COL3A1 | `c.766delA` (`p.Ile256Tyrfs*7`) | `ga4gh:VA.AUrZTFqDgja7bDWX…` | 4 (GM22606–GM22609) |
| NF1 | `c.6641+1G>T` | `ga4gh:VA.Snm0jh43GQWHRQUL…` | 4 (icNF98.4c/d, cNF98.4c/d) |
| PIK3CA | `c.1624G>A` (`p.Glu542Lys`) | `ga4gh:VA.EQ5CsXtT8KcVEtOU…` | 2 (NCC-MPNST3 pair) |

The `p.Arg681*` example is useful for interpreting this analysis correctly: twelve model systems carry
an allele that none of 169 sequenced specimens here does. That is **not** evidence the
models are irrelevant — R681X is a well-known recurrent NF1 allele. 
It indicates that the model portfolio and the sequenced patient cohorts represent 
different subsets of NF variation. The graph now makes that difference measurable.

The second group is mostly HEK293/Schwann-cell engineering lines whose curated
`nf:sequenceVariation` records the editing scar (`c.101del`, `c.102del`, `c.103del`,
`c.103_104delins122`, each on 14 or 4 lines) rather than a patient-comparable allele.
Without sufficient transcript and genomic context, these mutations cannot currently be compared to patient alleles by identity.

The `reason` field keeps these curation limitations separate from genuine "allele not observed" results.

### Important qualifications

- **Recurrence here is not population recurrence.** Four cohorts, four assay designs, four
  calling pipelines. "Unmodelled in this registry, observed in these cohorts" is the
  strongest claim any row supports. An allele can be rare here and common in NF overall,
  and the reverse.
- **No model ≠ no relevant model.** Coverage is computed over what NF-OSI curates. A model
  that exists but is not in the registry, or is in the registry with its mutation
  uncurated, reads as a gap. 73 of 118 curated mutations have no mintable identity, so the
  tier-1 gap list is an upper bound on the gap.
- **Absence of a call is not wild type.** A specimen with no call in a gene may be
  uncovered or filtered.
- **The artifact flags are heuristics.** `alleles/specimen` has no background model and no
  gene-length term, and gnomAD AF is present on only a minority of calls, so an unflagged
  row is not certified somatic.
- **`nf:orthologOf` says nothing about the allele.** The ortholog layer is 7 pairs over 5
  human genes, and covers only the genes in `mutations.csv` by design, not by omission.

## Reproducing this

The published `ghcr.io/nf-osi/kg-qlever` images are the `runtime-rdf` target and carry no
patient variant layer, so none of the queries above return anything against them. Dispatch
**Build image** with `variants: true` for an image that does
(`ghcr.io/nf-osi/kg-qlever-variants`), or rebuild locally:

```sh
# 1. Rebuild the whole core

# 2. Build the two crosswalks. Both need network access; both write
#    a reviewed TSV into mappings/ that the pipeline then serializes.
python scripts/fetch_orthologs.py                 # -> mappings/orthologs.tsv
python scripts/mint_model_mutation_vrs.py         # -> mappings/model_mutation_vrs.tsv
python scripts/materialize_orthologs.py           # -> data/rdf/orthologs.ttl
python scripts/materialize_model_mutation_vrs.py  # -> data/rdf/model_mutation_vrs.ttl

# 3. Index and serve.
export KG_INCLUDE_VARIANTS=1
dagster asset materialize --select 'group:variants' -m orchestration.dagster_pipeline
docker build --target runtime-variants -t kg:variants-demo1 .
docker run -d --name kg-variants-demo1 -p 7004:7001 kg:variants-demo1
```

`fetch_orthologs.py --check` fails if the checked-in TSV is stale.
`check_source_versions.py --check-external` re-hashes the pinned Alliance release and
reports drift without editing the pin.

