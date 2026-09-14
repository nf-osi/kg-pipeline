# BioLink Alignment

Tracks how `schema/ontology.ttl` aligns NF-OSI entity classes to the [BioLink Model](https://biolink.github.io/biolink-model/). Introduced in [#61](https://github.com/nf-osi/kg-pipeline/issues/61) to enable cross-portal interoperability (initially NF + ALS portals) and NCATS alignment.

## Namespace

```turtle
@prefix biolink: <https://w3id.org/biolink/vocab/> .
```

## Replaced classes

These `nf:` classes had no external ontology mappings worth preserving, so they were removed from the ontology and replaced directly with BioLink classes in RML mappings and SPARQL queries.

`nf:Study` and `nf:Dataset` were originally in this table and have since been moved to the NF-specific subclass table below. Outright removal turned out to be the wrong call for them: both carry a large set of `nf:`-namespace slots that then had no domain we define, and `shapes:StudyShape` / `shapes:DatasetShape` silently validated nothing because their `sh:targetClass` pointed at a class that no longer existed. Queries written against `biolink:Study` / `biolink:Dataset` are unaffected — instances carry both types.

| Removed | Replaced with | Notes |
|---|---|---|
| `nf:Publication` | `biolink:Publication` | No external mapping |
| `nf:Chemical` | `biolink:ChemicalEntity` | No external mapping; BioLink already maps to CHEBI:24431 |
| _(none — new)_ | `biolink:SequenceVariant` | Used directly for somatic variant nodes in the variant layer. `nf:Variant` was NOT reused: it means "a variant mentioned in publication text" (PubTator3) and carries no coordinates, so overloading it would conflate a literature mention with a called allele. See `docs/variant-layer.md`. |
| _(none — new)_ | `biolink:Gene` | Used directly for the gene entity layer, keyed on Ensembl gene id. `nf:Gene` was NOT reused for the same reason: it means "a gene mentioned in publication text" and carries no identifiers. See `docs/entity-layers.md`. |

## Subclassed under BioLink (with preserved mappings)

These `nf:` classes carried `owl:equivalentClass` links to external ontologies that BioLink does not include. They were kept as NF classes with `rdfs:subClassOf` the BioLink parent, preserving the external alignment.

| Class | Added | Preserved mapping | Why not replace |
|---|---|---|---|
| `nf:Genotype` | `rdfs:subClassOf biolink:Genotype` | `owl:equivalentClass efo:EFO_0000513` | BioLink maps to GENO:0000536, not EFO |
| `nf:Specimen` | `rdfs:subClassOf biolink:MaterialSample` | `owl:equivalentClass obo:OBI_0100051` | BioLink maps `MaterialSample` to OBI:0000747 "material sample"; the NF sense is OBI:0100051 "specimen". Those two are **siblings** under BFO material entity, not equivalents, so `owl:equivalentClass biolink:MaterialSample` would be a false claim. Note there is no `biolink:Sample` — "sample", "biosample" and "biospecimen" are *aliases* of `MaterialSample` (Biolink 4.4.4) |
| `nf:Gene` | `rdfs:subClassOf biolink:Gene` | `owl:equivalentClass <uniprot:Gene>` | BioLink maps to SO:0000704, not UniProt |
| `nf:Variant` | `rdfs:subClassOf biolink:SequenceVariant` | `owl:equivalentClass obo:SO_0001564` | BioLink has SO:0001060 (close), not SO:0001564 (exact) |

## Subclassed under BioLink (NF-specific classes)

These `nf:` classes are NF-specific specializations with no external mappings to preserve. They gain a BioLink parent via `rdfs:subClassOf`, and their own subclasses inherit through the NF class hierarchy.

| Class | Added | Inheriting subclasses |
|---|---|---|
| `nf:CellLine` | `rdfs:subClassOf biolink:CellLine` | `nf:NormalCellLine`, `nf:CancerCellLine`, all cell line types |
| `nf:Mutation` | `rdfs:subClassOf biolink:SequenceVariant` | `nf:SinglePointMutation`, `nf:Insertion`, all mutation types |
| `nf:ComputationalTool` | `rdfs:subClassOf biolink:Software` | — |
| `nf:Antibody` | `rdfs:subClassOf biolink:Protein` | — |
| `nf:Investigator` | `rdfs:subClassOf biolink:Person` | — |
| `nf:Individual` | `rdfs:subClassOf biolink:IndividualOrganism` | — |
| `nf:Study` | `rdfs:subClassOf biolink:Study` | — |
| `nf:Dataset` | `rdfs:subClassOf biolink:Dataset` | — |

## Borrowed classes are declared locally

Every BioLink class the graph instantiates carries a local `a owl:Class` declaration
with an `skos:scopeNote`, in the "Borrowed classes" block of `schema/ontology.ttl`:
`biolink:Person`, `biolink:Publication`, `biolink:Study`, `biolink:Dataset`,
`biolink:ChemicalEntity`, `biolink:Gene`, `biolink:SequenceVariant`,
`biolink:MaterialSample`, `biolink:IndividualOrganism`. Without the declaration a
borrowed class is invisible to class-level introspection (`?c a owl:Class`) and carries
none of our usage caveats, which is how several sat undeclared from #61 until this was
fixed.

`skos:scopeNote` rather than `rdfs:comment` is deliberate — see the convention note above
that block. Where the borrowed class is only a parent (`biolink:Study`, `biolink:Dataset`,
`biolink:MaterialSample`, `biolink:IndividualOrganism`), its scope note is a pointer and
the substantive guidance lives in the `rdfs:comment` of the `nf:` subclass, which is ours
to define.

The declarations are enforced by `scripts/validate_schema_drift.py`, which checks the
`nf:` and `biolink:` namespaces; adding another namespace to its `CHECKED_NAMESPACES`
means committing to a local declaration for every term in it that the graph instantiates.

## SHACL target expansion only runs downward

`sh:targetClass C` binds instances of `C` *and its subclasses* — never its superclasses.
So for a dual-typed pair the shape may target either class and bind the same nodes, but
if only one of the two types is emitted the shape must target that one. `shapes:StudyShape`
and `shapes:DatasetShape` target `nf:Study` / `nf:Dataset`, which works because the RML
emits both types; before the subclasses were restored they targeted classes with no
declaration at all and silently validated zero nodes. A shape that binds nothing reports
`conforms: True`, so this failure mode is invisible unless you count focus nodes.

## Classes with no BioLink equivalent

These remain in the `nf:` namespace only:

`nf:File`, `nf:Tool`, `nf:GeneticReagent` (and all vector/reagent subtypes), `nf:AnimalModel` (and species subtypes), `nf:Donor`, `nf:MutationSet`, `nf:Biobank`, `nf:ClinicalAssessmentTool`, `nf:PatientDerivedModel`, `nf:OrganoidProtocol`, `nf:Initiative`, `nf:Development`, `nf:Funder`, `nf:Data`, `nf:Observation` (and subtypes), `nf:DiseaseAnnotation`, `nf:MaterialsTransferAgreement`, `nf:VariantObservation`

`nf:Individual` is deliberately separate from `nf:Donor`: `nf:Donor` is the UUID-keyed
source donor of a cell line or animal model, `nf:Individual` is the patient or animal an
uploaded file came from, and the two identifier spaces do not overlap at all (0 shared
values across 4,506 individualIDs and the donors table).

`biolink:Case` was rejected for `nf:Individual`: BioLink defines it as "an individual
(human) organism that has a patient role in some clinical context", and a large share of
NF portal individualIDs name mice or zebrafish, so the assertion would be false for them.
`biolink:IndividualOrganism` covers both.

## Reasoning caveat: subclassing alone is not queryable

The QLever index performs no OWL reasoning, so `rdfs:subClassOf` in `schema/ontology.ttl`
is a *declaration only* — `?s a biolink:CellLine` matches nothing today, because the RML
emits just `nf:CellLine`. Where the emitter is ours to change, prefer typing instances
with **both** the `nf:` class and the BioLink parent. `scripts/materialize_specimens.py`
does this (`nf:Specimen` + `biolink:MaterialSample`, `nf:Individual` +
`biolink:IndividualOrganism`) at a cost of 12,623 triples, and
`mappings/rml/{studies,datasets}.rml.ttl` do it for `nf:Study` + `biolink:Study` and
`nf:Dataset` + `biolink:Dataset` at a cost of 527. Retrofitting the remaining subclassed
classes (`nf:CellLine`, `nf:Mutation`, `nf:Antibody`, ...) in the RML mappings is open
work — for those, `?s a biolink:CellLine` still matches nothing.

## Files affected

- `schema/ontology.ttl` — class definitions, borrowed-class declarations, property domains/ranges
- `schema/shapes.ttl` — SHACL shape targets
- `mappings/rml/{studies,datasets,publications}.rml.ttl` — `rr:constant` type declarations (studies and datasets emit both the `nf:` class and the BioLink parent)
- `pubs/scripts/pubtator3_to_qlever.py` — text entity type for Chemical
- `test/conftest.py` — added `BIOLINK` namespace
- `test/test_rml_{studies,datasets}.py`, `test/test_rml_development.py` — SPARQL queries
- `scripts/test_sparql.sh`, `scripts/test_sparql_with_text.sh` — SPARQL queries
