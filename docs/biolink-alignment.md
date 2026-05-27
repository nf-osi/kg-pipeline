# BioLink Alignment

Tracks how `schema/ontology.ttl` aligns NF-OSI entity classes to the [BioLink Model](https://biolink.github.io/biolink-model/). Introduced in [#61](https://github.com/nf-osi/kg-pipeline/issues/61) to enable cross-portal interoperability (initially NF + ALS portals) and NCATS alignment.

## Namespace

```turtle
@prefix biolink: <https://w3id.org/biolink/vocab/> .
```

## Replaced classes

These `nf:` classes had no external ontology mappings worth preserving, so they were removed from the ontology and replaced directly with BioLink classes in RML mappings and SPARQL queries.

| Removed | Replaced with | Notes |
|---|---|---|
| `nf:Study` | `biolink:Study` | No external mapping |
| `nf:Dataset` | `biolink:Dataset` | No external mapping |
| `nf:Publication` | `biolink:Publication` | No external mapping |
| `nf:Chemical` | `biolink:ChemicalEntity` | No external mapping; BioLink already maps to CHEBI:24431 |

## Subclassed under BioLink (with preserved mappings)

These `nf:` classes carried `owl:equivalentClass` links to external ontologies that BioLink does not include. They were kept as NF classes with `rdfs:subClassOf` the BioLink parent, preserving the external alignment.

| Class | Added | Preserved mapping | Why not replace |
|---|---|---|---|
| `nf:Genotype` | `rdfs:subClassOf biolink:Genotype` | `owl:equivalentClass efo:EFO_0000513` | BioLink maps to GENO:0000536, not EFO |
| `nf:Gene` | `rdfs:subClassOf biolink:Gene` | `owl:equivalentClass <uniprot:Gene>` | BioLink maps to SO:0000704, not UniProt |
| `nf:Variant` | `rdfs:subClassOf biolink:SequenceVariant` | `owl:equivalentClass obo:SO_0001564` | BioLink has SO:0001060 (close), not SO:0001564 (exact) |

## Superclassed under BioLink (NF-specific subclasses)

These `nf:` classes are NF-specific specializations. They gain a BioLink parent via `rdfs:subClassOf`, and their own subclasses inherit through the NF class hierarchy.

| Class | Added | Inheriting subclasses |
|---|---|---|
| `nf:CellLine` | `rdfs:subClassOf biolink:CellLine` | `nf:NormalCellLine`, `nf:CancerCellLine`, all cell line types |
| `nf:Mutation` | `rdfs:subClassOf biolink:SequenceVariant` | `nf:SinglePointMutation`, `nf:Insertion`, all mutation types |
| `nf:ComputationalTool` | `rdfs:subClassOf biolink:Software` | — |
| `nf:Antibody` | `rdfs:subClassOf biolink:Protein` | — |
| `nf:Investigator` | `rdfs:subClassOf biolink:Person` | — |

## Classes with no BioLink equivalent

These remain in the `nf:` namespace only:

`nf:File`, `nf:Tool`, `nf:GeneticReagent` (and all vector/reagent subtypes), `nf:AnimalModel` (and species subtypes), `nf:Donor`, `nf:MutationSet`, `nf:Biobank`, `nf:ClinicalAssessmentTool`, `nf:PatientDerivedModel`, `nf:OrganoidProtocol`, `nf:Initiative`, `nf:Development`, `nf:Funder`, `nf:Data`, `nf:Observation` (and subtypes), `nf:DiseaseAnnotation`, `nf:MaterialsTransferAgreement`

## Files affected

- `schema/ontology.ttl` — class definitions and property domains/ranges
- `mappings/rml/{studies,datasets,publications}.rml.ttl` — `rr:constant` type declarations
- `pubs/scripts/pubtator3_to_qlever.py` — text entity type for Chemical
- `test/conftest.py` — added `BIOLINK` namespace
- `test/test_rml_{studies,datasets}.py`, `test/test_rml_development.py` — SPARQL queries
- `scripts/test_sparql.sh`, `scripts/test_sparql_with_text.sh` — SPARQL queries
