# Specimen and Individual layers

Two entity types the portal referenced only as string literals, promoted to nodes.
**Core graph** — permanent, not behind a feature gate.

| Layer | Class | Key | Count | Built by |
|---|---|---|---|---|
| Specimen | `nf:Specimen` + `biolink:MaterialSample` | portal `specimenID` | 8,117 | `scripts/materialize_specimens.py` |
| Individual | `nf:Individual` + `biolink:IndividualOrganism` | portal `individualID` | 4,506 | same |

```turtle
<syn26470374>  nf:fromSpecimen   nf:specimen/JH-2-111-G645D ;
               nf:fromIndividual nf:individual/JH-2-111 .
nf:specimen/JH-2-111-G645D  a nf:Specimen, biolink:MaterialSample ;
    nf:specimenID "JH-2-111-G645D" ; nf:hasFile <syn26470374> ;
    nf:fromIndividual nf:individual/JH-2-111 .
nf:individual/JH-2-111  a nf:Individual, biolink:IndividualOrganism ;
    nf:individualID "JH-2-111" ; nf:hasSpecimen nf:specimen/JH-2-111-G645D .
```

```sh
python scripts/materialize_specimens.py          # -> data/rdf/specimens.ttl
```

## Why these classes

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

## Effect on the default build

These are core, so they enter the published index and the embeddings: **149,944 triples**
(137,321 IRI→IRI edges over 58,815 nodes). Not reversible.

## Also in this PR: gene terms, no gene data

`schema/ontology.ttl` declares the `biolink:Gene` property vocabulary
(`nf:geneSymbol`, `nf:geneName`, `nf:hgncId`, `nf:ensemblGeneId`, `nf:entrezGeneId`) so
the schema for all three entity layers is reviewed in one place. Nothing emits gene
nodes yet — the layer that populates them arrives with the cBioPortal ingest
([#95](https://github.com/nf-osi/kg-pipeline/issues/95)), which is where the gene
section of this document will be filled in.
