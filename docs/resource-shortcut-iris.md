# Resource IRIs: How Tool Identity Landed on `resource/{resourceId}`

**Status: resolved (KG v0.4).** This documented a deliberate type-specific-IRI tradeoff and a
defect it left behind. Upstream's LinkML migration forced the tradeoff to be revisited, and
resolving it fixed the defect. Kept as the record of why the design changed, so neither the
original decision nor its reversal looks arbitrary. See
`docs/upstream-schema-migration.md` for the migration itself.

## The original design (retired)

Every `nf:Tool` was minted under a **type-specific IRI**: `cellLine/{cellLineId}`,
`antibody/{antibodyId}`, `animalModel/{animalModelId}`, and so on
(`mappings/rml/resources.rml.ttl`, since deleted).

**Claimed advantage**: the common queries — "find all cell lines," "what kind of resource is
this" — need no extra join, because the IRI itself tells you the type.

**Cost**: `nf:Development` records carry only a generic `resourceId`, with no way to know at
mapping time which type-specific template that id belongs under. So a `Development` could not
link to its `Tool` by IRI; the link went through a literal id match
(`?dev nf:forResourceId ?rid . ?tool nf:resourceId ?rid`) — a 2-hop, string-keyed join.

## Why it was reversed

Two things, one of which was not true when the tradeoff was first written:

1. **The claimed advantage was already redundant.** Each per-type mapping *also* asserts a real
   class on the same subject — `mappings/rml/cell_lines.rml.ttl:32` emits `a nf:CellLine`, and
   likewise for the other eight. `?s a nf:CellLine` already answered "find all cell lines"
   without touching the IRI. The type-in-IRI was carrying no unique weight.
2. **Upstream removed the keys it depended on.** The LinkML migration re-keyed every tool-type
   table from `<type>Id` onto a shared `resourceId` and retired the central `Resource` table
   (syn26450069) that was the only place `<type>Id` still existed. Since `<type>Id` and
   `resourceId` are different UUIDs for 1144 of 1218 tools, keeping type-specific IRIs would
   have meant preserving a retired table purely to mint identities.

Tool nodes are now minted at `nf:resource/{resourceId}` — a clean break, no `owl:sameAs` bridge.
Old IRIs remain resolvable from any archived graph, because every tool node carries its
`nf:resourceId` as a string literal (verified: 1215 of 1215 nodes in the pre-migration graph).

## The defect this resolved

`development.rml.ttl` and `donor_tool.rml.ttl` had four triples maps
(`map:ResourceHasFunder`, `map:ResourceHasInvestigator`, `map:ResourceHasPublication`,
`map:ToolFromDonor`) that still targeted `resource/{resourceId}` — an IRI that commit `8e29858b`
("Revise owl:sameAs usage", 2026-02-18) had retired as a real node. Every triple they emitted
landed on a subject with no `rdf:type`, no name, and no bridge to the real tool sharing that
`resourceId`.

Because the migration moves tool nodes onto *exactly that* IRI, those four maps became correct
without being touched:

| Measure | Before | After |
|---|---|---|
| Distinct `resource/{id}` IRIs that are the subject of something | 844 | 1218 |
| ...with no `rdf:type` | **844** | **1** |
| Dead `hasFunder` / `hasInvestigator` / `hasPublication` triples | 415 | 2 |

The one remaining untyped node is `resource/19bba596-fc3d-479b-9675-afa369b44dee`, a cell line
deleted upstream while still referenced by `Development` and `Observation` — an upstream data
lag, not a mapping defect. It shows up in `scripts/validate_fks.py` output and is recorded in
`docs/upstream-mutation-resourceid-bug.md`.

The same change also retired the `mutation_model` bug formerly described in `HARMONIZATION.md`,
where 77 of 268 rows held a `resourceId` in a `cellLineId` column: with one key per resource,
that confusion is no longer representable.

## Loose ends from the original writeup

- `nf:resourceId`'s declaration was reported here as `owl:ObjectProperty` with
  `rdfs:range nf:Tool`, contradicting its use as a string literal. It is now (and was, by the
  time of the migration) correctly `owl:DatatypeProperty` with `rdfs:range xsd:string`.
- `nf:forResourceId` was reported as undeclared; it is declared in `schema/ontology.ttl`.
- The three "shortcut" maps were kept rather than dropped, since they now land on real nodes and
  save a 2-hop join. The sibling shortcuts on `funder/{funderId}` and `publication/{publicationId}`
  were always fine and are unchanged.
