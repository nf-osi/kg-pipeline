## Proposed

Analysis of recall from first phase suggests improvements that can be mostly categorized as better graph construction/configuration, prompt engineering, or tooling.

### Graph Construction/Configuration

#### Populate missing data property in the knowledge graph

- **Finding:** GR-004 fails because `copyNumber` exists in the schema but is empty in the data. The agent discovers the right property but finds no values. This was an easy question and actually just Finding a bug in our graph construction pipeline.

- **Potential improvement:** Fix is just to make sure it gets into the graph.

- **Questions improved:** GR-004 (0.000 -> potential solve)

#### Add shortcuts or ontology hints for cross-resource queries

- **Finding:** Questions requiring multiple joins (e.g., CR-002 links Files to CellLines via `modelSystemName`, AM-002 links through File assays) fail because agents have to dynamically discover these relationship paths.

- **Potential improvement:** Materialize common indirect relationships as direct graph edges (shortcut), and/or document key indirect relationships in the ontology.

- **Questions improved:** CR-002 (0.267 avg), AM-002 (0.000), CL-008 (0.114 avg)

#### Add ontology/bridging bridging layer for semantic gap questions

- **Finding:** Questions like AM-002 ("energy expenditure") fail because the natural language term doesn't appear in the KG. The agent must know that "energy expenditure" maps to "metabolic screening" / "oxygen consumption" assays. CR-001 (HDAC inhibitor compound names) fails because classification is currently not in the graph.

- **Potential improvement:** Expand the ontology layer that the agent can use before constructing SPARQL. This could define the relationships: `energy expenditure -> [metabolic screening, oxygen consumption, calorimetry]`

- **Questions improved:** AM-002 (0.000 -> potential solve), CL-003 (clarifying "normal"), CR-001 (HDAC inhibitor compound names)

### Prompt Engineering

#### Improve agent constraint extraction from natural language

- **Finding:** AM-004 asks for "mouse model" but all agents return a zebrafish because they don't add a species filter. The constraint is explicit in the question but ignored in SPARQL construction. Agents are not being detailed-oriented enough (surprisingly, Sonnet fails here).

- **Potential improvement:** Add a system prompt instruction or a pre-processing step to help emphasize/extract entity-type constraints from questions. Or include representative SPARQL patterns in the agent's system prompt examples.

- **Questions improved:** AM-004 (0.000 -> potential solve), CL-004 (race value matching)

#### Add structured property preference guidance to reduce run-to-run instability

- **Finding:** AM-001 ("optic glioma") scores range from 0.0 to 1.0 across runs of the same model because the agent non-deterministically chooses between structured properties (`animalModelOfManifestation`) and free-text search (description contains "optic glioma").

- **Potential improvement:** Add agent guidance to prefer structured/enumerated properties over free-text search when both are available. Consider adding a "property confidence" annotation to schema descriptions (this would be more under Graph Construction/Configuration type of improvement).

- **Questions improved:** AM-001 (0.500 -> higher consistency), CL-004 (0.200 -> more consistent)

### Tools

#### Add value discovery tooling for enumerated properties

- **Finding:** CL-004 fails partly because agents don't know the exact values used for race categories ("Black" vs. "Black or African American"). Similarly for genetic disorder labels and manifestation values.

- **Potential improvement:**
  - Add a tool or query pattern that returns distinct values for a given property (e.g., `SELECT DISTINCT ?race WHERE { ?x nf:race ?race }`)
  - Include "value discovery" as a recommended first step in the agent's exploration protocol
  - Pre-populate common enumerated values in schema descriptions

- **Questions improved:** CL-004 (0.200 -> better value matching), AM-001 (correct manifestation values)

### Other 

#### Improve handling of large answer sets in benchmark scoring

- **Finding:** CL-008 has 51 target UUIDs. Even Sonnet's reasonable approach (finding one isogenic family) yields only 0.382 recall. The scoring penalizes partial but correct understanding.

- **Potential improvement:**
  - Consider partial-credit weighting for questions with very large answer sets (e.g., score by "families Finding" rather than individual UUIDs)
  - Add sub-questions that break large queries into discoverable chunks
  - Document expected difficulty calibration so large-target questions aren't compared directly with small-target ones

- **Questions improved:** CL-008 (fairer scoring), overall benchmark interpretability
