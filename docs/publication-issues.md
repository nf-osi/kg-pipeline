# Publication and People Data Issues

Publications reach the knowledge graph from **two independent portal listings**. The same paper can
therefore appear as more than one `biolink:Publication` node, and a handful of source records carry
defects that survive into the graph. This page explains the duplication, quantifies it, shows how to
count publications correctly, and logs the specific upstream records that need curator attention.

Issues are grouped as:

- [Expected duplication](#why-there-are-duplicates) — inherent to ingesting two listings; handle by deduplicating
- [Upstream defects](#upstream-defects) — data-entry errors in the source tables that should be fixed at source

## Why there are duplicates

| | Tools Central | Main portal |
|---|---|---|
| Synapse table | `syn26486839` | `syn16857542` |
| Synapse project | `syn26338068` | `syn26451327` |
| Source collection | `nf:ToolsCentralPublications` | `nf:MainPortalPublications` |
| Keyed by | internal `publicationId` (UUID) | DOI, falling back to `pmid-<id>` |
| Scope | papers describing research tools/resources, reachable via `nf:Development` | papers associated with portal studies, carrying `nf:aboutStudy` |

Because the two listings mint IRIs from different keys, a paper present in both gets **two distinct
node IRIs**. There is deliberately no reconciliation step: neither key is available in both sources,
so merging would require matching on DOI/PMID at build time, and the records carry genuinely
different fields (Tools Central has abstracts and citations; the main portal has study links,
disease focus and manifestation).

Every publication node records which listing it came from:

```sparql
?pub prov:wasDerivedFrom ?collection .   # nf:ToolsCentralPublications | nf:MainPortalPublications
```

## How much duplication (as of KG v0.3)

| Measure | Count |
|---|---|
| `biolink:Publication` nodes | 937 |
| distinct PMIDs | 906 |
| papers present as more than one node | 23 |
| of those, author counts **agree** | 21 |
| of those, author counts **disagree** | 2 |

So a raw node count overstates distinct papers by roughly 23 (~2.5%).

## Counting publications correctly

**Do not** use `SELECT (COUNT(?pub) …) WHERE { ?pub a biolink:Publication }` — that counts *records*,
not papers. Deduplicate on `nf:pmid`, falling back to `nf:doi`, then `nf:publicationTitle`:

```sparql
PREFIX nf: <http://nf-osi.github.com/terms#>
PREFIX biolink: <https://w3id.org/biolink/vocab/>

SELECT (COUNT(DISTINCT ?pmid) AS ?papers) WHERE {
  ?pub a biolink:Publication ;
       nf:pmid ?pmid .
}
```

PMID is the most reliable dedup key here (906 distinct, vs 807 for DOI), because the main portal's
`doi` column is only a real DOI in about 87% of rows — the rest hold article numbers (`720`,
`e98601`, `tgac021`) or Elsevier PIIs (`S1044-579X(18)30003-8`). The ingest already filters those
out, so `nf:doi` is never emitted for them; that is why DOI coverage is lower.

## Upstream defects

All of the following are data-entry errors in the source tables. The pipeline passes them through
unchanged; they should be corrected in Synapse.

### 1. Contaminated author lists (`syn16857542`)

In both papers where the two listings disagree, the **main portal record contains the correct author
list plus extra names appended after the true final author**, and those extra names belong to a
different paper. Tools Central is correct in both cases.

#### PMID 30302402 — *Genetically engineered minipigs model the major clinical features of human neurofibromatosis type 1*

- Tools Central: **22 authors** (correct), ending `… David A Largaespada | Adrienne L Watson`
- Main portal: **25 authors** — the same 22 plus `Jody F Longo`, `Joshua C Anderson`, `Steven L Carroll`
- Those three appear together on PMID 37328102 (*Inhibition of Erb-B2 Receptor Tyrosine Kinase 3 …*), an unrelated Steven L Carroll paper

#### PMID 27617404 — *Immortalization of human normal and NF1 neurofibroma Schwann cells*

- Tools Central: **5 authors** (correct) — David F Muir, Debbie R Neubauer, Hua Li, Lung-Ji Chang, Margaret R Wallace
- Main portal: **26 authors** — the same 5 plus 21 others (Arie Perry, David Raleigh, Frank McCormick, Melike Pekmezci, Stephen Magill, …), which read as a separate UCSF neuro-oncology author group

**Action:** correct the author lists in `syn16857542`. Until then, prefer the Tools Central record
when the two listings disagree on authorship.

### 2. Case-sensitive DOI keying fails to merge one paper (pipeline + `syn16857542`)

PMID **37406085** (*Combined CDK4/6 and ERK1/2 Inhibition Enhances Antitumor Activity …*) becomes
**two nodes inside the same collection** (`nf:MainPortalPublications`), unlike every other paper that
appears on multiple rows.

The main portal listing has one row per paper-per-study, so a paper linked to two studies legitimately
occupies two rows. Those rows normally collapse to a single node because they share a DOI. Here they
do not, because the two rows write the DOI differently:

```
10.1158/1078-0432.CCR-22-2854                    studyId = syn47857478
https://doi.org/10.1158/1078-0432.ccr-22-2854    studyId = syn5714288
```

`format_doi` strips the `https://doi.org/` prefix, leaving values that differ **only in letter case**
— and the publication key is compared case-sensitively, so two IRIs are minted.

This is as much a pipeline gap as a source problem: **DOIs are case-insensitive by specification**, so
two spellings denote the same DOI and should key to the same node. The upstream inconsistency is
untidy, but a case-insensitive key would absorb it.

Consequences today:

- Counting "papers with more than one node" gives **23**, whereas only **22** papers are genuinely
  present in both listings; this pair inflates the total.
- Deduplicating on PMID absorbs it correctly. Deduplicating on DOI does **not**, unless the DOI is
  lowercased first.
- The two nodes carry one study link each, so neither has the paper's full set of studies.

**Status: fixed in the pipeline.** `format_doi` now lowercases DOIs before they are used in IRI
templates, so the two spellings key to one node carrying both `nf:aboutStudy` links, and DOI-based
deduplication is reliable for consumers. DOI IRIs are lowercase throughout the graph as a result —
match case-insensitively, or prefer PMID, when joining against a DOI quoted from a publisher.

Still worth correcting upstream: normalising DOI capitalisation and prefix usage in `syn16857542`
would remove the inconsistency at source. A case-insensitive DOI uniqueness check on that table
would prevent recurrence.

### 3. Non-DOI values in the `doi` column (`syn16857542`)

About **13% of rows** (33 of 260) hold something other than a DOI in the `doi` column — article
numbers (`720`, `e98601`, `tgac021`, `e2208960120`) or Elsevier PIIs (`S1044-579X(18)30003-8`). One
row has neither a DOI nor a usable PMID.

The ingest guards against this: a `cleanDoi` derived column keeps the value only when it really is a
DOI, so `nf:doi` is never emitted pointing at a bogus `doi.org` IRI, and publication keys fall back
to `pmid-<id>`. The cost is reduced DOI coverage (807 distinct DOIs vs 906 PMIDs), which is why PMID
is the recommended dedup key.

Related: several `pmid` values are also malformed — `PMID:` (empty), `PMID:syn30283982` (a Synapse
ID), and values with stray whitespace. These fail the numeric guard and produce no key.

**Action:** move article numbers/PIIs out of the `doi` column, and correct the malformed PMIDs.

> Note all of the above are distinct from the *expected* case where one ORCID maps to several Synapse
> profiles (a person with more than one account) — that is legitimate and documented on
> `nf:SynapseUser`.

### 4. `onProject` is truncated at 100 entries (`syn23564971`)

The People table's `onProject` column is an `ENTITYID_LIST` with
`maximumListLength: 100`, and **32 of 434 people with projects sit at exactly that
cap**. Their real project membership is unknown (>= 100), so `nf:onProject` is a
**lower bound** for those people.

This censors the top of the distribution, which is where ranking questions look:

| | project collaborators |
|---|---|
| top 8 people | 265 — all tied, all capped |
| top uncapped person | 183 — itself a 3-way tie |

The 265 is an artefact of several people's lists being truncated to overlapping
100-item subsets, not a real figure. **Do not rank people by project count or
project-collaborator count** until the cap is lifted; per-person questions about
someone below the cap are fine.

**Action:** raise `maximumListLength` on `onProject` in `syn23564971`, or model
project membership as one row per person-project pair instead of a list column.

## Effect on evaluation

`PUB-001` (an author-count question) originally used PMID 30302402. It was repointed to
PMID 34230197 once the main portal listing was ingested, because an agent landing on the corrupted
node answered 25 with no principled way to detect the error. The replacement paper exists as exactly
one node. See `evaluation/main/eval_tools_ground_manual.yaml` for the full history.

`PUB-003` (a personalized-discovery count) had its expected answer changed from 8 to 15 by this
ingest, and now requires deduplication. It moved again to **14** when the author-ORCID source was
repointed (below): the two routes now return 19 nodes representing 14 distinct papers.

`PUB-002`, `PUB-005` and `PUB-006` were also recomputed for that repoint — see
`evaluation/main/eval_tools_ground_manual.yaml`, where each carries a `HISTORY` note.

## People and author-ORCID sourcing changed (2026-08-10)

`syn76406574`, the standalone publication-mining table that supplied `nf:authorOrcid`, was **deleted
upstream**. Both the people ingest and the author-ORCID ingest now read the portal people registry,
`syn23564971`, which absorbed the publication list.

Two consequences worth knowing when querying:

1. **ORCID coverage went up.** `nf:authorOrcid` now spans 284 DOIs (was 218) and reaches 286 of 937
   publication nodes, ~30% versus ~3% before.
2. **`biolink:Person` is no longer always a Synapse profile.** Only 458 of the registry's 1518 rows
   are Synapse accounts; the rest are researchers known only from authorship. A person node is keyed
   by `https://www.synapse.org/Profile:{id}` when they have an account and by
   `https://orcid.org/{orcid}` when they do not — never both, so `?p a biolink:Person` still counts
   people rather than identifiers.

3. **`nf:SynapseUser` was removed; use `nf:hasSynapseProfile`.** The class asserted
   `rdfs:subClassOf biolink:Person` on the ORCID IRI of a person already typed at their Profile IRI,
   so materializing that axiom duplicated every account-holder — the exact double-count the class
   claimed to prevent. It also carried no data: 0 of 329 instances had `nf:onProject` and 2 had a
   name, so every useful follow-up needed a hop anyway. The replacement is a property that answers
   the same question and returns the profile in the same triple:

   ```sparql
   ?pub nf:doi ?doi .
   ?doi nf:authorOrcid ?orcid .
   ?orcid nf:hasSynapseProfile ?profile .    # was: ?orcid a nf:SynapseUser
   ```

   It is deliberately domain-free: declaring `rdfs:domain biolink:Person` would re-introduce the
   inference that duplicates account-holders. The relation is one-to-many — 3 people hold two
   Synapse accounts — so count DISTINCT subjects when counting people.

Person nodes now also carry `nf:name` / `rdfs:label`, so an author name is reachable from an ORCID:

```sparql
{ ?orcid nf:name ?name }                            # no Synapse account
UNION { ?orcid owl:sameAs ?p . ?p nf:name ?name }   # has one
```

Note the registry's display-name spelling need not match the `nf:authors` spelling on a
publication, so these names are for display and disambiguation, not for joining.
