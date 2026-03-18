# Changelog - NF Publication QA Dataset

All notable changes to the NF Publication QA evaluation dataset will be documented in this file.

## [v1] - 2026-03-18

### Notes
- Dataset can be used for evaluation and benchmarking.

### Changes from v0
- **Question Metadata**
  - Add `reviewer` and `editor_note` for question items
  - Add (optional) `persona` to align with the practice for `main` eval
- **Question Refinements**:
  - PMC7305302-01: Refined question specificity ("first available treatment" vs "current treatment") to improve cross-paper disambiguation
  - PMC9221468-01: Updated distractor choice from "Everolimus" to "Mirdametinib" to test agent grounding vs embedded knowledge
  - Enhanced editor notes documenting question design intent and difficulty rationale
- **Quality Improvements**:
  - Added inferential question type for questions requiring logical inference from text
  - Improved cross-paper question relationships and disambiguation challenges
  - Enhanced distractor quality to test agent adherence to knowledge base vs parametric knowledge

### Dataset Overview
- **Total Questions:** 130
- **Total Papers:** 14 NF-related publications (PMC IDs)
- **Question Styles:**
  - `precise`: Formally-phrased questions with more complete context
  - `user_query`: Colloquial questions as researchers would actually ask
- **Task:** Multiple-choice QA with passage citation over full-text biomedical literature
- **Retrieval:** SPARQL+Text queries against NF-OSI knowledge graph with indexed publication text
- **Metrics:**
  - Accuracy: Fraction of questions with correct answer selected
  - Citation F1: F1 score over (PMID, passage_index) tuples

### Question Distribution
- **By Difficulty:**
  - Easy: Direct lookup, single fact
  - Medium: Simple synthesis from 2-3 facts
  - Hard: More complex synthesis/inference, multiple steps, domain expertise

- **By Question Type:**
  - Factual: What/which/who questions about specific entities
  - Causal: How/why questions about biological processes and mechanisms
  - Comparative: Comparing conditions, treatments, or outcomes
  - Inferential: Questions requiring logical inference from text
  - Methodological: Questions about research methods and experimental approaches
  - Hypothetical: Questions about potential scenarios or applications
  - Other: Questions not fitting other categories

- **By Persona:**
  - Bench Scientist: 76 (58.5%) - Lab/experimental questions
  - Researcher: 29 (22.3%) - General research questions
  - Bioinformatician: 21 (16.2%) - Computational/analysis questions
  - Patient Advocate: 4 (3.1%) - Patient-centered questions

### Answer Format
- **Multiple Choice:** 4 options per question (A, B, C, D)
- **"Not in knowledgebase" option:** Included to test abstention
- **Ideal Answer:** Reference answer text provided for semantic evaluation
- **Passage Attribution:** Ground truth passage indices for each question

### Question Authoring
- **Model-Generated Questions:**
  - claude-opus-4-6: 83 questions (63.8%)
  - gemini-3.1-pro-preview: 40 questions (30.8%)
  - gpt-5.4: 7 questions (5.4%)
- **Manual Review:** First round review and validation of all questions by NF-OSI staff (ORCID: 0000-0003-1488-6730)
- **Dual Phrasing:** Each question includes both precise academic and natural user query versions

### Paper Coverage
Questions span 14 NF research papers covering:
- Neurofibromin function and signaling pathways
- NF1-associated tumors (plexiform neurofibromas, MPNST, gliomas)
- Molecular mechanisms and therapeutic targets
- Preclinical models and experimental approaches
- Clinical manifestations and treatment outcomes

### Known Limitations
- Question distribution varies across papers (some papers have more questions)
- Difficulty distribution: Weighted toward medium complexity
- Some multi-passage answers may benefit from additional passage refinement

## [v0] - 2026-03-17

### Initial Draft Release
- 130 questions across 14 NF-related papers
- Dual question styles: precise (academic) and user_query (colloquial)
- Multiple-choice format with 4 options per question
- Citation attribution via passage indices
- Question metadata: difficulty, question_type, author
- Ideal answer text for (later) semantic evaluation
- Successful integration into astabench evaluation framework

### Question Generation
- Model-generated questions (gpt-5.4, gemini-3.1-pro-preview, claude-opus-4-6)
- Manual review and validation by domain expert (ORCID: 0000-0003-1488-6730)
- Difficulty levels: easy, medium, hard
- Question types: factual, causal, comparative, inferential, methodological, hypothetical, other
