# Knowledge Graph Pipeline: Architecture and Design Guide

**Audience:** Implementers building or adapting a portal knowledge graph on Synapse  
**Status:** Draft  

---

## Overview

This document describes the design and architecture for knowledge graph construction based on the NF-OSI Knowledge Graph (KG) pipeline. 
The pipeline was first developed for the [NF Data Portal](https://nf.synapse.org) but is adaptable to other Synapse-based portals.

The goal of the pipeline is to convert structured metadata stored in Synapse tables into a queryable RDF knowledge graph, with optional additional layers as needed.  
This graph serves as the retrieval backbone for search and discovery questions requiring cross-entity reasoning and especially advantageous for multi-hop, aggregation, and comparison queries.

## Graph Layers

The knowledge graph is organized into conceptual layers. Not all layers need to be implemented for a minimum viable deployment.

### Layer 1 — Portal Entities (Core)

This is the foundational layer: portal metadata converted to RDF. Portals already conceptualize their domain in terms of entity types (classes) — Datasets, Publications, Tools, Model Systems, and so on. These entity types are surfaced as tables in Synapse, where each row is an instance of that class. The pipeline formalizes this implicit model into an explicit OWL ontology (`schema/ontology.ttl`), assigns each instance a stable IRI, and maps relationships between entity types as object properties.

> **Layer 1 uses public metadata only.** The Synapse tables ingested at this layer are open, publicly accessible portal metadata — not restricted datasets or patient-level data. This is a deliberate design constraint: the graph contains no data that requires access controls, and the pipeline can in principle be run by anyone without special data access permissions.

Layer 1 requires two inputs: the **data sources** (Synapse tables declared in a file such as `data_sources.yaml`) and the **internal ontology** (`schema/ontology.ttl`). The ontology defines the classes and properties that the portal entities conform to — it is not an optional enhancement but a required foundation that every subsequent stage depends on.

**Scoping with the portal owner / data manager.** Before building Layer 1, it is important to consult the portal owner / data manager who can make the call on which entity types exist, which tables are the authoritative source for each, and what the priority order is for inclusion. **They should also provide example queries to help knowledge engineers analyze feasibility given current data, adapt the construction, and later validate that the graph meets use cases.** Not every table in Synapse needs to be in the graph, as some may be internal, incomplete, or low-priority. The portal owner can also clarify which tables are actively maintained, which are stable, and which may be deprecated or restructured soon. This conversation should happen early, as it shapes the ontology design and the scope of downstream harmonization work.

For the NF graph, representative use cases that have driven design and prioritization:

**Resource discovery: Tools shopping** — finding tools or models that match specific experimental criteria:
- *"Which cell lines carry NF1 mutations and have associated RNA-seq data?"*
- *"What genetic reagents target genes studied in schwannoma models?"*

**Resource discovery: Data reuse** — finding existing studies or datasets relevant to a research question:
- *"Which studies have RNA-seq data for NF1 schwannoma samples?"*
- *"What datasets are available for a specific disease focus and assay type?"*

**Landscape and coverage analysis** — portfolio-level questions about the state of NF research resources, useful to program officers and community stakeholders:
- *"What NF disease manifestations have animal models but no corresponding cell lines?"*
- *"Which genes are targeted by the most tools on the portal?"*
- *"Which disease focus areas are data-rich vs. data-sparse across studies and datasets?"*

**Scientific reasoning** — linking observational or experimental outcomes to resources:
- *"Which cell lines have shown sensitivity to HDAC inhibitors?"*

> Note: For the NF graph, scientific reasoning is currently supported by integrating associations extracted from publications (Layer 3) and external ontologies (Layer 4). Other efforts may also want to include experimental data file extraction (Layer 5) to directly surface measured outcomes such as drug sensitivities or variant calls.

**Networking** — understanding the network, finding collaborators or the resources they have produced:
- *"How large is the community working on manifestation topic A vs manifestation topic B?"*
- *"How is Contributor A connected to Contributor B?"* — e.g., through other contributors, shared disease focus, co-participation in the same initiative

> Note: Potential collabs could be considered a highly valuable resource, thus this may also be considered resource discovery.

These questions share a common structure: they require traversing relationships across entity types that live in separate tables or handling more analytical queries, which are not supported well by search today.

**Versioning and maintenance.** Data sources must be versioned and treated as a maintained configuration artifact. `data_sources.yaml` is the canonical record of which Synapse tables are included and at which version. Each table entry should record its Synapse ID, `concrete_type`, and a pinned `source_version` (snapshot version for `TableEntity` and `EntityView` tables). This ensures that the graph is reproducible — two pipeline runs against the same `data_sources.yaml` will produce the same output — and that changes to source tables are deliberate and tracked. When a portal owner updates a table, the pipeline maintainer should review the change, update the pinned version, and re-run affected assets.

Different portals surface different entity types. The table below illustrates which entity types appear across several Synapse-based portals (representative, not exhaustive):

| Entity Type | NF | ALS | CCKP | ADKP | EL |
|---|:---:|:---:|:---:|:---:|:---:|
| Study | Yes | ? | ? | ? | ? |
| Dataset | Yes | ? | ? | ? | ? |
| File | Yes | ? | ? | ? | ? |
| Publication | Yes | ? | ? | ? | ? |
| Computational Tool | Yes | ? | ? | ? | ? |
| Model System (Cell Line / Animal Model) | Yes | ? | ? | ? | ? |
| Funder / Initiative | Yes | ? | ? | ? | ? |

> **Note on table types:** `data_sources.yaml` records each table's `concrete_type` (TableEntity, EntityView, MaterializedView). Only `TableEntity` and `EntityView` support snapshot versioning in Synapse; `MaterializedView` tables are live and not versionable. This affects reproducibility: pipeline runs against a `MaterializedView` may produce different output at different times.

**Defining semantics.** Most portals have a data model but *not* a formal ontology. In this case, semantics *can* be inferred from table structure, field names, and controlled vocabularies, but ideally it is also cross-checked with the current data model and done collaboratively with the portal owner and domain experts. Decisions such as which field values represent class distinctions versus instance attributes, how to scope properties, whether to align with external ontologies — propagate through every downstream stage and are difficult to revise later.

### Layer 2 — Derived Relationships (Optional)

Some edges in the graph are not directly represented in any single Synapse table — they require **inference** or cross-table joins. These are materialized as separate RDF assets after the initial table mapping.

Examples in the NF pipeline:
- `nf:sharedDonor` — links an animal model and a cell line that were derived from the same donor (requires joining `animal_models` and `cell_lines` on donor ID)
- `nf:Nf1MutationSet` — a derived entity representing a unique combination of NF1 mutations present in a cell line

This layer is optional for a minimal deployment but significantly improves the expressiveness of the graph for complex queries.

### Layer 3 — Publication Full-Text Index (Optional)

Full-text content from publications (PubMed/PMC) can be ingested and linked to the graph using entity annotations from tools like [PubTator3](https://www.ncbi.nlm.nih.gov/research/pubtator3/). This enables SPARQL+Text queries that combine structured entity matching with free-text retrieval.

In the NF pipeline, this layer:
- Indexes NF-related PMC publications at passage granularity
- Annotates passages with NCBI Gene, MeSH, OMIM, Cellosaurus, and NCBITaxon entities
- Links publications back to studies and datasets in the core graph

This layer requires additional infrastructure (QLever's text indexing feature) and increases the build complexity and image size. It is optional for initial deployments. For graph engines without SPARQL+Text capability, extracted entity annotations (genes, diseases, cell lines, etc.) can still be loaded as standard RDF triples, enabling structured queries such as "what drugs were mentioned alongside gene X in NF publications?" via regular SPARQL — without free-text passage retrieval.

### Layer 4 — External Ontologies and Datasets (Optional)

The graph can be extended with triples from external sources: other ontologies, databases, or domain-specific datasets, e.g., OpenTargets gene-disease associations.

For most implementations, this layer is deferred until the core graph is operational and query gaps are identified.

### Layer 5 — Experimental Data Extraction (Optional, **Not Implemented**)

This layer brings actual experimental measurements and findings from portal data files into the graph — not just metadata about them. Where Layer 1 captures that a study exists and what assays it used, Layer 5 captures what those assays found: gene expression values, drug sensitivity measurements, variant calls, phenotypic observations, and similar structured results.

This layer is the primary enabler of scientific reasoning use cases. For example, answering "which cell lines have shown sensitivity to HDAC inhibitors?" requires not just knowing which cell lines exist and which studies involved them, but extracting the actual sensitivity measurements from the underlying data files. A drug sensitivity table might look like:

| cellLineId | drug | ic50 | assay | studyId |
|---|---|---|---|---|
| NF0001 | Vorinostat (HDAC inhibitor) | 0.42 µM | CellTiter-Glo | syn123 |
| NF0002 | Selumetinib | 1.8 µM | CellTiter-Glo | syn456 |

A processed variant call file might look like:

| sampleId | gene | chromosome | position | ref | alt | consequence | studyId |
|---|---|---|---|---|---|---|---|
| NF0001 | NF1 | chr17 | 31094050 | C | T | stop_gained | syn123 |
| NF0003 | NF2 | chr22 | 29999545 | G | A | missense_variant | syn789 |

When such tabular data files are available, RML mappings can be applied directly to them — the same pipeline machinery used for Synapse metadata tables works equally well for structured data files, linking measurement triples back to the cell line and study entities already in the graph.

Example questions enabled by this layer:

*Drug sensitivity:*
- *"Which cell lines show the lowest IC50 for HDAC inhibitors, and how do NF1 vs. NF2 cell lines compare?"*
- *"Which drugs have consistent sensitivity (IC50 < 1 µM) across multiple NF1 cell lines?"*

*Variant calls:*
- *"Which genes have the highest mutation burden across sequenced NF1 patient samples?"*

> If variant calls are extracted from an NF1 cohort and another rare-disease cohort, one can also ask: *"Which mutations are shared between NF1 patients and patients with [other rare disease], and which are disease-specific?"*

Key challenges: portal files are heterogeneous in format and schema, extraction logic is dataset-specific, and result interpretation may require domain expertise. We want to target standardized files first, but implementation will likely involve per-dataset extraction pipeline and close collaboration with data contributors to understand data formats and semantics.

---

## Pipeline Architecture

The pipeline materializes the graph in five stages. Stages 1 and 3 are core and required. Stage 2 is optional per table. Stages 4 and 5 are add-ons; Stage 5 sits outside the core graph construction pipeline.

```
Synapse Tables
      │
      ▼  Stage 1: Extract
   data/csv/*.csv              (raw CSV, normalized)
      │
      ▼  Stage 2: Harmonize    [optional per table]
   data/csv/*_harmonized.csv   (ontology IRIs resolved)
      │
      ▼  Stage 3: Map to RDF
   data/rdf/*.ttl              (RDF triples, one file per table)
      │
      ▼  Stage 4: Derive       [optional]
   data/rdf/shared_donor_links.ttl, nf1_mutation_sets.ttl
      │
      ▼  Stage 5: Embed        [optional]
   data/embeddings/kg.emd      (128-dim node2vec embeddings)
```

Each stage is described below with expected effort for initial implementation and adaptation.

---

### Stage 1 — Extract *(Core)*

**Purpose:** Download Synapse portal tables and normalize them into clean CSV files suitable for RML mapping.

**Key operations:**
- Queries Synapse table entities via `synapseclient` using configurable SELECT clauses
- Flattens `STRING_LIST` columns to pipe-delimited strings (for multi-value handling downstream)
- Coerces numeric columns (counts, timestamps, byte sizes) and converts empty strings to null so that the RML mapper skips missing values
- Optionally applies derived columns — values computed by joining other tables (e.g., `species` joined from `donors` into `animal_models`)
- Archives raw exports for reproducibility; supports `--from-cache` for re-runs without Synapse access
- Validates foreign key constraints (non-blocking: logs violations but does not fail)

**Configuration:** `scripts/prepare_portal_tables.py` holds a `TABLES` dict with one entry per Synapse table. Version pinning is managed via `data_sources.yaml`.

**Effort (initial, for a new portal):**
- Understanding the table schema and relationships: **1–2 days**
- Writing `TABLES` config entries (one per table): **~1 hour per table**
- Setting up FK validation declarations: **~30 min per FK relationship**
- Total for a 10-table portal: **~3–5 days**

**Effort (adapting from NF):**
- If your Synapse portal follows similar table conventions: **~1 day** to update `TABLES` and `data_sources.yaml`

---

### Stage 2 — Harmonize *(Optional per table)*

**Purpose:** Map human-readable label values (e.g., `"Cancer Cell Line"`, `"Zebrafish"`) to stable ontology IRIs before RML mapping. This step is optional per table — tables with no controlled vocabulary fields can skip it.

> **Recommendation: skip unless the portal owner has a strong idea of appropriate ontology alignments or working group agreements.** Harmonization maps portal vocabulary to external ontology IRIs, which is most valuable if multiple portals align to the same IRIs, enabling cross-portal queries. If working independently, some mappings may need to be revised later. Ask the portal owner whether cross-portal alignment standards have been established before investing in this step — if not, recommend skipping it and revisiting later.

**This is where ontology alignment work happens.** See [Ontology Alignment](#ontology-alignment) for a deeper discussion.

**Key operations:**
- A Python script reads a source CSV and an SSSOM mapping file, and writes a `_harmonized.csv` with a new column containing the resolved IRI
- SSSOM (Simple Standard for Sharing Ontology Mappings) is the standard format for the lookup tables; see [SSSOM specification](https://mapping-commons.github.io/sssom/)
- Unmapped values are logged and passed through as-is; no data is silently dropped

**Which tables need harmonization?**  
Any table where field values are user-supplied enumerated labels that correspond to ontology classes. In the NF pipeline:
- `cell_lines` → `cellLineCategory` → `nf:CancerCellLine`, `nf:NormalCellLine`, etc.
- `animal_models` → `species` → `nf:MouseModel`, `nf:ZebrafishModel`, etc.
- `mutations` → `mutationType` → mutation subclasses
- `files` → `dataType`, `nf1Genotype`, `nf2Genotype`
- `studies` → `dataType`
- `observations` → `observationType`
- `genetic_reagents` → `vectorType`

Tables with only free-text or numeric fields (e.g., `donors`, `funders`) do not need a harmonization step.

**Effort (per table requiring harmonization):**
- Initial SSSOM file creation (reviewing portal vocabulary, matching to ontology): **1–3 days per table** depending on vocabulary size
- Script to apply the mapping: **~2–4 hours** (straightforward once the SSSOM file exists)
- Ongoing maintenance as vocabulary evolves: **low** (update SSSOM file)

---

### Stage 3 — Map to RDF *(Core)*

**Purpose:** Transform each CSV (raw or harmonized) into RDF triples using RML (RDF Mapping Language) and the RMLMapper tool.

RML ([spec](https://rml.io/specs/rml/), [RMLMapper](https://github.com/RMLio/rmlmapper-java)) is a declarative mapping language for converting tabular or semi-structured data into RDF. Each mapping file specifies a logical source (the CSV), a subject template (how to construct the IRI for each row), and a set of predicate-object mappings (which columns become which properties with which values or linked IRIs). RML mappings are written in Turtle syntax and executed by the RMLMapper engine, which outputs `.ttl` files. The key advantage of RML over custom scripts is that the transformation logic is explicit, testable, and independent of the data — changing a field name or IRI template requires editing the mapping file, not the pipeline code.

**Key operations:**
- Each table has a corresponding `.rml.ttl` file in `mappings/rml/` that defines subject IRIs, predicate-object mappings, and data types
- Multi-value fields (pipe-delimited) use GREL function chains in the RML to split and emit multiple triples
- Stable, dereferenceable IRIs are minted per entity type (e.g., Synapse URLs for files and studies; `nf:` namespace URIs for tools and reagents)
- Outputs one `.ttl` file per table in `data/rdf/`

**IRI design decisions:**
- Synapse entities (studies, files, datasets) use `https://www.synapse.org/Synapse:{id}` — these are human-browsable and globally unique
- Portal-specific entities (tools, donors, mutations) use `http://nf-osi.github.com/terms#{entityType}/{entityId}` — scoped to the portal namespace
- Text-keyed entities (initiatives, funders) use name-derived IRIs with spaces replaced by underscores

**Tools:** RMLMapper (Java 21+). GREL function support is required for multi-value splitting. The pipeline depends on the released JAR.

**Effort (per table):**
- Simple table (all literals, no multi-value, straightforward subject IRI): **~2–4 hours**
- Complex table (multi-value fields, function maps, IRI joins): **~1 day**
- Writing and running RML unit tests: **~2–4 hours per table**
- Total for a 10-table portal: **~1–2 weeks**

---

### Stage 4 — Inference *(Add-on)*

**Purpose:** Materialize additional RDF triples representing relationships that span multiple tables or that require inference beyond what RML can express directly.

**When to implement:** When you want to pre-compute derived entities or materialize statements from "reasoning" that simplify downstream queries and add knowledge from ontology axioms.

**Implementation approaches:**
- **Custom scripts** — load source `.ttl` files via `rdflib`, construct new triples via SPARQL CONSTRUCT or Python logic, and write to a new `.ttl` file in `data/rdf/`. Best for domain-specific relationships that require programmatic logic.
- **Dedicated reasoner** — apply OWL or RDFS reasoning (e.g., using `reasonable` or a triplestore's built-in reasoner) to materialize entailed triples from the ontology. Best for class membership inference, property chains, or transitivity.

In both cases, the output is registered as an orchestration asset with explicit upstream dependencies.

**Effort:** **~1–2 days per derived relationship**, including design and testing.

---

### Stage 5 — Derive Graph Embeddings *(Add-on, outside core pipeline)*

> Note: This is currently implemented but this stage is technically **outside the core graph construction pipeline**. Embeddings are derived from the completed graph as a downstream artifact and are not required for the graph to be queryable.

**Purpose:** Train node2vec embeddings over the graph's structural (IRI-to-IRI) edges, producing 128-dimensional vectors for each entity. These enable use cases such as similarity/personalized search, query suggestion, and downstream ML tasks.

**When to implement:** If your application requires similarity-based retrieval or if you plan to use the KG for ML tasks beyond SPARQL querying. Not required for a SPARQL-only deployment.

**Implementation:** `scripts/rdf_to_edgelist.py` extracts IRI-to-IRI edges from all `.ttl` files, then PecanPy runs node2vec random walks and trains word2vec embeddings. Output is in word2vec text format.

**Effort:** **~1 day** to set up.

---

## Ontology Alignment

Ontology alignment is the most intellectually intensive part of the pipeline. It is also where the graph gains its semantic value: by mapping portal vocabulary to a shared ontology, entities become queryable by type, comparable across datasets, and linkable to external knowledge bases.

### Internal Ontology (`schema/ontology.ttl`)

Each portal should define an OWL ontology covering its entity types and properties. The approach can be outlined as:

- **BioLink Model for schema-level type assertions** — where a BioLink class exists (e.g., `biolink:CellLine`, `biolink:Gene`, `biolink:Study`), use it as the primary `rdf:type`. This provides a graph-native vocabulary shared with federated KG projects and enables cross-portal querying without requiring full ontology alignment.
- **Domain ontologies for semantic precision** — portals that require more specificity can additionally align classes to domain ontologies (e.g., [CL](https://obofoundry.org/ontology/cl.html) for cell types, [Mondo](https://mondo.monarchinitiative.org/) for diseases, [NCBITaxon](https://www.ncbi.nlm.nih.gov/taxonomy) for species). Prefer `rdfs:subClassOf` over `owl:equivalentClass` for these alignments — `owl:equivalentClass` asserts bidirectional subsumption and can be computationally expensive for reasoners. This depends on the portal's demand for precision (i.e. for better scientific reasoning) and can be optional.
- **Portal namespace for gaps** — entity types not covered by BioLink or a suitable domain ontology should use a portal-specific namespace (e.g., `nf:GeneticReagent`, `nf:AnimalModel`).

Both BioLink and domain ontologies provide alignment; the difference is pace and granularity. BioLink alignment is faster to adopt and immediately enables cross-portal schema-level queries. Domain ontology alignment is a slower path that requires more curation effort but yields greater semantic precision for scientific reasoning use cases. Portals can start with BioLink and layer in domain ontology alignments incrementally.

For the NF portal, the current ontology uses a custom `nf:` namespace throughout, predating this recommendation. Migration to BioLink where applicable is a planned improvement.

The ontology should also declare datatype and object properties with `rdfs:domain`, `rdfs:range`, and cardinality constraints, and subclass hierarchies for typed entities.

### SSSOM Mapping Files (`mappings/sssom/`)

SSSOM files are TSV tables that record how each portal label maps to an ontology class IRI. Each row includes:
- `subject_id` — the portal label (e.g., `"Cancer Cell Line"`)
- `object_id` — the target ontology class IRI (e.g., `nf:CancerCellLine`)
- `predicate_id` — the mapping relationship (typically `skos:exactMatch`)
- `mapping_justification` — provenance (e.g., `semapv:ManualMappingCuration`)

**Practical guidance:**
- Start with a survey of all distinct values in controlled vocabulary fields
- Decide which values map to ontology classes vs. literal data (e.g., is `"Zebrafish"` a class, or just a string label on `nf:species`?)
- Where external ontologies exist (e.g., NCBITaxon for species, EFO for experimental factors), prefer reusing their IRIs over minting custom ones
- Document unmappable or ambiguous values — these are candidates for data quality feedback to upstream curators

**External ontologies referenced in the NF pipeline:**
- [EFO](https://www.ebi.ac.uk/efo/) — genotype concepts (NF1/NF2 genotypes)
- [OBO SO](http://www.sequenceontology.org/) — sequence feature types (sgRNA, RNAi)
- [NCBITaxon](https://www.ncbi.nlm.nih.gov/taxonomy) — species
- [Cellosaurus](https://www.cellosaurus.org/) — cell line identities
- [NCBI Gene, MeSH, OMIM](https://pubchem.ncbi.nlm.nih.gov/)

**Suggested ontologies for cross-portal alignment:**

The following ontologies are candidates for shared alignment across Synapse-based portals. Using these consistently would enable cross-portal querying as more portals adopt the pipeline.

> **Note:** These suggestions have not yet been confirmed by a working group and depend on promised adoption across different DCCs. Treat these as starting points for discussion, not established standards. Implementers should verify current working group status before committing to any of these alignments.

| Domain | Suggested Ontology | Notes |
|---|---|---|
| Species | [NCBITaxon](https://www.ncbi.nlm.nih.gov/taxonomy) | Widely used across biomedical data resources |
| Disease / phenotype | [Mondo](https://mondo.monarchinitiative.org/) | Harmonized disease ontology; preferred over MeSH for cross-portal use |
| Assay / data type | [EFO](https://www.ebi.ac.uk/efo/) | Covers experimental factors including assay types and platforms |
| Cell type | [CL (Cell Ontology)](https://obofoundry.org/ontology/cl.html) | OBO standard for cell types |
| Anatomy / tissue | [UBERON](https://obofoundry.org/ontology/uberon.html) | Cross-species anatomical ontology |
| Gene / variant | [NCBI Gene](https://www.ncbi.nlm.nih.gov/gene), [SO](http://www.sequenceontology.org/) | Gene identifiers and sequence feature types |

An alternative to aligning against individual ontologies is to adopt [BioLink Model](https://biolink.github.io/biolink-model/), a high-level schema designed specifically for biological knowledge graphs. BioLink defines a standardized set of classes (e.g., `biolink:Gene`, `biolink:Disease`, `biolink:CellLine`) and predicates that already map to the major domain ontologies above. Using BioLink as a shared alignment target — rather than aligning directly to individual ontologies — would provide a single, graph-native vocabulary already used by large federated KG projects (e.g., NCATS Translator, Monarch Initiative), making cross-portal queries more tractable. The tradeoff is that BioLink is a higher-level abstraction and may not cover all portal-specific entity types, requiring some custom extension. This approach has been suggested as a candidate for cross-DCC standardization but has not yet been evaluated or adopted.

Overall, agreement on an alignment strategy — whether individual ontologies or BioLink — needs to come first across participating DCCs. This is precisely why harmonization is recommended to be skipped until that agreement exists: implementing mappings before consensus is reached risks creating work that will need to be revised or discarded.

### Alignment Effort Summary

| Ontology work | Effort estimate |
|---|---|
| Design internal ontology schema (10–20 classes, 30–50 properties) | 3–5 days |
| Create SSSOM file for one small controlled vocabulary (< 20 values) | ~2 hours |
| Create SSSOM file for one large controlled vocabulary (100+ values) | 2–4 days |
| Aligning to an external ontology (finding equivalences, resolving ambiguities) | 1–3 days per ontology |
| Ongoing vocabulary maintenance | Low (update SSSOM as new values appear) |

---

## Orchestration

The pipeline stages are independent and can be run sequentially by any DAG-capable orchestrator, or even as a simple Makefile (`make all`). The choice of orchestration tool depends on team familiarity and infrastructure. The current solution uses [Dagster](https://dagster.io/), but alternatives such as Apache Airflow, Prefect, or a shell script are equally viable.

In the Dagster implementation, each Synapse table is represented as a chain of assets:

```
portal/csv/{table}
  └─→ portal/harmonized/{table}   [if table has harmonization]
        └─→ portal/rdf/{table}
```

Derived assets are declared with explicit upstream dependencies, so the full graph can be materialized in one command, with selective re-runs of individual tables or groups as needed. The Dagster config auto-generates assets from the `TABLES` configuration, so no manual orchestration code changes are needed when adding new tables.

---

## Quality Assurance

The pipeline includes several quality gates. Note that there is intentionally little data validation before the transformation stage — portal metadata is presumed to be relatively clean, having already passed through the portal's own curation and submission processes. Validation effort is therefore concentrated on the transformation output (RML correctness, graph structure) rather than the input data.

| Check | When | Blocking? |
|---|---|---|
| Foreign key validation | After Extract | No (logged only) |
| RML unit tests (pytest + SPARQL) | After Map | Yes |
| SPARQL output validation | After Map | Yes |
| SHACL validation | After Map | No (logged only) |
| End-to-end use case queries | After graph is loaded | Recommended |
| RDF archive + diff generation | After all stages | No |

**FK validation** checks referential integrity across declared constraints (e.g., `cell_lines.donorId` must exist in `donors.donorId`). Violations are non-blocking because they often reflect upstream data quality issues in Synapse, not pipeline bugs. They are logged and tracked.

**RML unit tests** use `pytest` + SPARQL queries against the output of individual RML mappings to assert expected triple counts and structure. These are fast and catch mapping regressions early.

**SHACL validation** checks the output RDF against shape constraints declared in `schema/shapes.ttl` — required properties, cardinality, and IRI patterns. Currently non-blocking and coverage is incomplete; expanding shapes is a planned improvement.

**End-to-end use case queries** run the agreed query use cases (see Scoping section) against the loaded graph and verify that results are correct and complete. This is the most direct validation that the graph meets its intended purpose and should be performed before any handoff or release. In the NF pipeline, this is implemented via an agentic evaluation suite (AstaBench) that poses natural-language questions to an AI agent backed by the graph and scores recall against ground-truth answers.

---

## Optional Components Summary

| Component | Required? | When to include |
|---|---|---|
| Harmonization step (per table) | Optional (per table) | When table has controlled vocabulary fields needing IRI resolution |
| Derived RDF materialization | Optional | When cross-table relationships matter for your use case |
| Publication full-text indexing | Optional | When free-text retrieval over publications is needed |
| Node embeddings | Optional | When similarity search or downstream ML is required |
| External ontology/dataset layers | Optional | After core graph is operational and query gaps are identified |
| RDF archiving and diff generation | Optional | For incremental graph database updates (e.g., Amazon Neptune) |

---

## Adapting for Another Synapse Portal

This pipeline was built for the NF Research Tools Portal but is designed with generalization in mind. The core Extract → Harmonize → Map stages are reusable for any Synapse-based data portal that:
- Stores entity metadata in Synapse tables (TableEntity)
- Uses controlled vocabulary fields that map to ontology classes
- Wants to expose entities as linked data queryable via SPARQL

### What can be reused as-is
- The extraction framework and orchestration infrastructure (RMLMapper setup, Dagster asset pattern)
- The SSSOM harmonization pattern and lookup format
- The data validation framework (FK checks, RML tests)

### What to adapt
- **`prepare_portal_tables.py`** — reuse as a template, but the `TABLES` dict, SELECT clauses, column definitions, and any derived column logic (`apply_derived_columns`) are NF-specific and must be replaced for your portal's tables
- **`schema/ontology.ttl`** — replace or extend with your entity types and properties
- **`mappings/rml/*.rml.ttl`** — one file per table; reuse patterns but update class names, properties, and IRI templates
- **`mappings/sssom/*.sssom.tsv`** — new SSSOM files for your vocabulary
- **`data_sources.yaml`** — version pinning for your Synapse tables

### What to keep in mind
- **IRI stability matters**: once published, IRIs should not change without a deprecation strategy. Choose your IRI templates carefully before going live.
- **Vocabulary governance**: SSSOM files reflect a design decision about what your portal labels *mean*. This requires domain expertise and may involve iteration with data contributors.
- **Start with 3–5 core tables**: get the Extract → Map loop working end-to-end before adding harmonization and derived layers. A small working graph is more valuable than a large planned graph.

### Rough total effort for a new implementation

| Phase | Scope | Effort |
|---|---|---|
| Bootstrap | Highest-priority entity types, minimal ontology, no harmonization | 2–3 weeks |
| Core | Priority tables complete, harmonization for key vocabulary fields, basic derived relationships | Scales with number of tables and vocabulary complexity |
| Full | Publication indexing, external ontology alignment, embeddings, evaluation framework | Additional months |

These estimates assume one (human) engineer with familiarity with RDF/SPARQL and Python. Each additional table adds roughly 2–8 hours of RML mapping work depending on complexity, plus separate effort for harmonization if the table has controlled vocabulary fields. Ontology alignment work benefits significantly from a domain expert collaborating on vocabulary decisions.

Agent tooling can significantly reduce mechanical implementation time — writing RML mappings, extraction config, and unit tests — but **is not expected to proportionally reduce** the design, alignment, and validation effort. Scoping with the portal owner, ontology design decisions, and SSSOM curation still require domain expertise and stakeholder input regardless of automation.

---

## Future Development

This is an evolving pipeline. The following are known limitations and ideas for improvement, in rough priority order.

**Generalizing the extraction layer.** `prepare_portal_tables.py` is currently a mix of framework code and NF-specific configuration. The `TABLES` dict, SELECT clauses, and `apply_derived_columns` logic could be externalized into a declarative config format, making the script a generic engine that any portal can drive without code changes.

**Incremental graph updates.** The pipeline currently does full rebuilds. RDF diff generation (`data/diff/added.ttl`, `data/diff/removed.ttl`) exists but is not yet used for incremental loading into the graph engine. Wiring this up would significantly reduce update latency and compute cost for large graphs.

**Writing derived identifiers back to Synapse.** Some entities (e.g., AI-extracted observations) have IDs minted by the pipeline that are not persisted upstream. This means IRIs differ across pipeline runs, breaking link stability. Closing this loop — writing minted IDs back to Synapse — would improve reproducibility and allow external references to stay valid.

**Automated vocabulary monitoring.** New values in controlled vocabulary fields currently require manual detection and SSSOM updates before they are mapped. An automated check that flags unmapped values after each extract run — and optionally suggests candidate mappings using an LLM — would reduce maintenance burden.

**External data layers.** Layer 4 (external ontologies and datasets) is not yet implemented. Near-term candidates include disease-gene associations (e.g., OpenTargets), cross-portal entity linking, and importing relevant ontology subgraphs (e.g., NCBITaxon, Mondo) as first-class graph nodes to enable richer traversal.

**Multi-portal graph federation.** As more portals adopt the pipeline, querying across portal graphs becomes valuable. This could be approached through graph merging at build time (shared IRIs where entities overlap) or at query time via federated SPARQL.

**SHACL validation.** `schema/shapes.ttl` exists but coverage is incomplete. Expanding SHACL shapes to validate required properties, cardinality constraints, and IRI patterns would catch data quality issues earlier in the pipeline.

**Faster RML mapping engine.** RMLMapper is the reference tool but is slow for large tables (the NF files table has 400k+ rows). [Morph-KGC](https://github.com/morph-kgc/morph-kgc) (Python-based, significantly faster) has been evaluated as a candidate replacement. Any replacement must support GREL function maps for multi-value splitting and maintain compatibility with RML 8.x mappings.

---

## Technology Stack Reference

| Component | Technology | Notes |
|---|---|---|
| Data source | Synapse (TableEntity) | Any table accessible via `synapseclient` |
| Ontology format | OWL 2 (Turtle) | `schema/ontology.ttl`, `schema/shapes.ttl` |
| Mapping format | RML (Turtle) | RMLMapper 8.x, Java 21+ |
| Vocabulary mapping | SSSOM TSV | `mappings/sssom/` |
| Function support | GREL (via YARRRML/FnO) | Required for multi-value splitting |
| Orchestration | Dagster | Replaceable with any DAG runner |
| Graph engine | QLever | High-performance SPARQL; served via Docker |
| Optional: text index | QLever SPARQL+Text | Requires separate `words`/`docs` files |
| Optional: embeddings | PecanPy (node2vec) | Word2vec output format |
| Optional: evaluation | AstaBench (InspectAI fork) | LLM-based recall scoring |

---

## Further Reading

- `docs/kg-pipeline-skill.md` — Step-by-step guide for adding a new resource type or table
- `HARMONIZATION.md` — Data quality notes, FK validation details, and harmonization logic
- `README.md` — Quick-start and local execution guide
- `evaluation/` — Benchmark design, sample questions, and results
