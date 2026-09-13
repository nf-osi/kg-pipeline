# Specimen, Individual and Gene layers

Three entity types the portal referenced only as string literals, promoted to nodes.
**Core graph** — permanent, not behind a feature gate.

| Layer | Class | Key | Count | Built by |
|---|---|---|---|---|
| Specimen | `nf:Specimen` + `biolink:MaterialSample` | portal `specimenID` | 8,117 | `scripts/materialize_specimens.py` |
| Individual | `nf:Individual` + `biolink:IndividualOrganism` | portal `individualID` | 4,506 | same |
| Gene | `biolink:Gene` | Ensembl gene id | 11,233 | `scripts/materialize_genes.py` |

```turtle
<syn26470374>  nf:fromSpecimen   nf:specimen/JH-2-111-G645D ;
               nf:fromIndividual nf:individual/JH-2-111 .
nf:specimen/JH-2-111-G645D  a nf:Specimen, biolink:MaterialSample ;
    nf:specimenID "JH-2-111-G645D" ; nf:hasFile <syn26470374> ;
    nf:fromIndividual nf:individual/JH-2-111 .
nf:individual/JH-2-111  a nf:Individual, biolink:IndividualOrganism ;
    nf:individualID "JH-2-111" ; nf:hasSpecimen nf:specimen/JH-2-111-G645D .

<https://identifiers.org/ensembl:ENSG00000196712>  a biolink:Gene ;
    rdfs:label "NF1" ; nf:geneSymbol "NF1" ; nf:geneName "neurofibromin 1" ;
    nf:ensemblGeneId "ENSG00000196712" ; nf:entrezGeneId "4763" ;
    nf:hgncId "HGNC:7765" ; skos:exactMatch <https://identifiers.org/hgnc:7765> .
```

```sh
python scripts/materialize_specimens.py          # -> data/rdf/specimens.ttl
python scripts/materialize_genes.py --maf data/raw/nst_nfosi_ntap_data_mutations.txt
                                                 # -> data/rdf/genes.ttl
```

## Why these classes

- **`biolink:Gene`, not `nf:Gene`.** `nf:Gene` already means "a gene mentioned in
  publication text" (PubTator3) and has no identifiers; reusing it would conflate a
  literature mention with an annotated locus.
- **`nf:Individual` is not `nf:Donor`.** `nf:Donor` is the UUID-keyed source donor of a
  cell line or animal model. The two identifier spaces share **zero** values.
- **Subclassed under BioLink, not replaced by it.** There is no `biolink:Sample`
  ("sample"/"biospecimen" are aliases of `biolink:MaterialSample`), and BioLink maps
  `MaterialSample` to OBI:0000747 while the NF sense is OBI:0100051 — *siblings* under
  BFO material entity, so equating them would be false. `biolink:IndividualOrganism`,
  not `biolink:Case`: Case is human-patient-only and many NF individuals are animals.
  Nodes carry **both** types, because the QLever index does no reasoning and a bare
  `rdfs:subClassOf` would leave `?s a biolink:MaterialSample` matching nothing.
- File→individual is asserted directly, not only via the specimen: 28% of files carry an
  `individualID` with no `specimenID`, and routing through specimens would lose them.

## Source-data traps (each has a test)

**Specimen / individual** — `scripts/materialize_specimens.py`:

- ids are **pipe-delimited multi-values** (`N10|N5`); the files RML splits them, so this
  must too, or a file is attributed to a specimen literally named `"N10|N5"`;
- `na`, `nan`, `n/a`, `none`, `unknown` are placeholders, not ids — same exclusion list
  as the files RML;
- **2,188 strings are used as both a specimen and an individual id**, so the two node
  types need separate IRI stems;
- 1,276 specimen ids need percent-encoding. `#` especially: `nf:` is itself a fragment
  namespace, so an unescaped `#` truncates the IRI and merges nodes.

Faithful to the source, not curated: some portal specimen ids are DICOM instance UIDs
and some individual ids are experiment group labels (`cre- veh 52`). They become nodes
because the portal calls them specimen ids.

**Gene** — `scripts/materialize_genes.py`. The MAF's gene columns disagree, and only one
pairing is clean (23,741 rows):

| Mapping | Ambiguous keys |
|---|---|
| `Gene` (ENSG) → `HGNC_ID` | **0** of 11,211 |
| `Hugo_Symbol` → `Gene` | 82 of 11,304 |
| `Gene` → `Hugo_Symbol` | 148 of 11,233 |
| `HGNC_ID` → `Hugo_Symbol` | 146 of 11,210 |

`Hugo_Symbol` is the *picked transcript's* symbol, so an overlapping antisense or
readthrough transcript reports a neighbouring gene's symbol and HGNC id — `HGNC:11033`
appears as both `SLC4A7` and `UBA52P4`. Hence **ENSG is the key**, and symbols come from
**HGNC**, accepted only when HGNC's own `ensembl_gene_id` agrees with the MAF's. That
cross-check holds for 11,208 / 11,233 (99.8%) and corrects 271 symbols, cutting symbols
that label two different genes from 53 to 1. Without it, `NF1` labelled both NF1 and
EVI2A (which sits inside the NF1 locus), so "how many samples are altered in NF1" split
across two nodes.

The 25 unverified genes keep the MAF symbol and are counted, not silently trusted.
`--no-hgnc` skips the lookup for offline runs and warns.

**Not folded in:** `data/csv/mutations.csv`'s 22 gene symbols. Only 11 overlap the MAF;
the rest are model-organism orthologs (`Nf1`, `Trp53` mouse; `nf1a` zebrafish) or
transgenes (`Cre`, `CAG-cre/Esr1*`). Symbol matching would merge mouse `Nf1` into human
`NF1` — false, and mouse genes belong to MGI. Those rows keep their
`nf:affectedGeneSymbol` literal.

## Effect on the default build

These are core, so they enter the published index and the embeddings: specimens add
149,944 triples (137,321 IRI→IRI edges over 58,815 nodes), genes 89,746 triples. Not
reversible.

The gene layer's *generation* is gated with the variant assets (`KG_INCLUDE_VARIANTS`)
only because the MAF is where the annotation comes from; its output is core either way,
so if the variant study were dropped `genes.ttl` would stay and simply stop growing.
Sourcing genes from HGNC directly would decouple the two, at the cost of ~45,000 nodes
of which only ~11,200 are referenced.
