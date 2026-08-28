# Draft issue for nf-osi/nf-research-tools-schema

Not yet filed. Surfaced while adopting the post-LinkML schema in kg-pipeline
(nf-osi/kg-pipeline#87). See `docs/upstream-schema-migration.md` for the wider
migration and `scripts/prepare_portal_tables.py` for the workaround this
describes.

---

**Title:** `Mutation` (syn26486834): `resourceId` column holds legacy `<type>Id` values, not resourceIds

## Summary

The LinkML migration renamed `Mutation`'s `animalModelId` / `cellLineId` columns
into a single `resourceId` column, but the **values were not migrated**. 265 of
277 rows still hold a legacy `cellLineId` / `animalModelId`, so the column does
not mean what its name says.

Because `<type>Id` and `resourceId` are different UUIDs for 1144 of 1218
resources, consumers that join `Mutation.resourceId` to a tool-type table's
`resourceId` silently get almost nothing.

## Evidence

Against live tables (2026-08-27):

| Measure | Count |
|---|---|
| `Mutation` rows | 277 |
| distinct `resourceId` values | 127 |
| values matching a real `resourceId` in any of the 9 tool tables | **12** |
| values matching a legacy `cellLineId` in the retired `Resource` table | 95 |
| values matching a legacy `animalModelId` in the retired `Resource` table | 30 |
| values matching neither | 0 |

So 125 of 127 distinct values (265 of 277 rows) are legacy per-type keys.

Reproduce:

```sql
-- returns ~12 of 277
SELECT COUNT(*) FROM syn26486834 M
  JOIN syn26486823 C ON M.resourceId = C.resourceId
```

```python
# 265 of 277 resolve only via the retired Resource table's cellLineId/animalModelId
mm = syn.tableQuery('SELECT resourceId FROM syn26486834').asDataFrame()
cw = syn.tableQuery(
    'SELECT resourceId, cellLineId, animalModelId FROM syn26450069').asDataFrame()
```

## Scope: `Mutation` only

Every other table carrying a `resourceId` FK was checked and is correct, so this
looks like a single missed backfill rather than a systemic migration gap:

| Table | rows | valid resourceId | legacy `<type>Id` | neither |
|---|---:|---:|---:|---:|
| `Mutation` (syn26486834) | 277 | 12 | **265** | 0 |
| `Observation` (syn26486836) | 1063 | 1060 | 0 | 3 |
| `Development` (syn26486807) | 223 | 222 | 0 | 1 |
| `Usage` (syn26486841) | 1897 | 1890 | 0 | 7 |
| `VendorItem` (syn26486843) | 590 | 583 | 5 | 2 |
| DonorTool MV (syn51735419) | 794 | 794 | 0 | 0 |

`VendorItem` has 5 rows in the same state — small enough to fix in the same pass.
The "neither" counts are a separate, much smaller issue: references to resources
deleted upstream (e.g. `19bba596-fc3d-479b-9675-afa369b44dee`,
`bd49d4e2-575e-4e89-8317-cff02db4882c`, the HS-Sch-2 / HS-PSS stub cell lines).

## Impact

Any consumer joining on `Mutation.resourceId` loses ~96% of mutation-to-resource
links. In kg-pipeline this would have dropped 265 of 277 `nf:hasMutation` edges
and emptied all 62 NF1 mutation sets.

It also silently re-creates, in mirror image, the bug that
`nf-osi/nf-research-tools-schema` previously tracked in the other direction:
resourceIds appearing in `cellLineId` columns. Consolidating onto one key was
supposed to make that class of confusion unrepresentable — it does, but only once
the values are migrated too.

## Suggested fix

Backfill `Mutation.resourceId` (and the 5 `VendorItem` rows) by translating each
legacy `<type>Id` through the retired `Resource` table (syn26450069), which is
the only surviving `<type>Id` → `resourceId` crosswalk:

```
UPDATE Mutation SET resourceId = Resource.resourceId
  WHERE Mutation.resourceId IN (Resource.cellLineId, Resource.animalModelId, ...)
```

Coverage is complete: all 277 rows resolve this way (verified). **This depends on
syn26450069 still existing** — once it is deleted, the mapping is unrecoverable
from Synapse and these rows become permanently ambiguous. Worth doing before any
cleanup of that table.

A post-migration integrity check asserting that every `resourceId`-named column
resolves to some tool-type table's `resourceId` would have caught this, and would
catch the next one.

## Workaround in kg-pipeline (to be removed)

`scripts/prepare_portal_tables.py` translates these values at build time via the
same crosswalk (`translate_legacy_resource_ids`, applied to `mutation_model` in
`apply_derived_columns`). It is deliberately scoped to translation only —
syn26450069 is not read for any Tool facts.

The pipeline prints `upstream appears fixed` when a build finds nothing left to
translate; that is the signal to delete the workaround. Removal checklist is in
`docs/upstream-schema-migration.md`.
