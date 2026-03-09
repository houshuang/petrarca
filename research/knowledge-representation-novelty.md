# Knowledge Representation for Novelty Comparison: A Deep Research Survey

How to represent knowledge extracted from articles so that the same insight, phrased differently, can be reliably identified as redundant -- and genuinely new knowledge can be surfaced. This is the core unsolved problem for Petrarca's novelty detection.

*Last updated: 2026-03-07*

---

## Table of Contents

1. [The Core Problem](#1-the-core-problem)
2. [Atomic Fact Decomposition](#2-atomic-fact-decomposition)
3. [Claim Normalization and Canonicalization](#3-claim-normalization-and-canonicalization)
4. [Textual Entailment for Novelty](#4-textual-entailment-for-novelty)
5. [Structured Knowledge Representations Beyond Embeddings](#5-structured-knowledge-representations-beyond-embeddings)
6. [Proposition-Level Embeddings](#6-proposition-level-embeddings)
7. [Non-Factual Knowledge: Arguments, Workflows, Theories](#7-non-factual-knowledge-arguments-workflows-theories)
8. [Practical Systems and Implementations](#8-practical-systems-and-implementations)
9. [Synthesis: A Proposed Architecture for Petrarca](#9-synthesis-a-proposed-architecture-for-petrarca)

---

## 1. The Core Problem

When we extract "knowledge contributions" from articles, the same insight can appear in radically different phrasings:

- "Transformer models benefit from longer context windows" vs "Extending the context length of attention-based architectures improves performance"
- "SpaceX reduced launch costs by 90%" vs "Reusable rockets brought the price per kilogram to orbit down tenfold"
- "Sleep deprivation impairs memory consolidation" vs "Getting less than 6 hours of sleep hurts your ability to form long-term memories"

Simple embedding cosine similarity catches some of these, but it has well-documented failure modes:

**Why embeddings alone are not enough.** A 2024 paper "Is Cosine-Similarity of Embeddings Really About Similarity?" (ACM Web Conference 2024) showed that embedding spaces from pretrained transformers are non-smooth and deviate from normal distributions, making cosine similarity yield arbitrary results in many cases. Another 2024 study found that LLM-based comparison produced low similarity scores (0.00-0.29) for genuinely different meanings, while embedding methods incorrectly assigned high scores (0.82-0.99) to dissimilar content. A 2025 paper "Semantics at an Angle" demonstrated strong position-dependence in cosine similarity -- where semantic changes occur in the text affects the score more than what the changes are.

The research literature offers several complementary strategies. No single approach solves the problem; the most promising path is a pipeline combining multiple techniques.

---

## 2. Atomic Fact Decomposition

### What it is

Breaking complex, multi-clause sentences into minimal factual units, each expressing a single, irreducible proposition. This is the foundational step before any comparison can happen.

### Key Work

**FActScore** (Min et al., EMNLP 2023) is the seminal paper. It breaks LLM-generated text into "atomic facts" and computes the percentage supported by a knowledge source. The decomposition uses an LLM to split text into minimal units. Key insight: the *method* of decomposition significantly affects downstream scores -- different strategies (semantic parses, LLM prompts, Russellian/Neo-Davidsonian breakdowns) produce different sets of atomic facts.
- Paper: "FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation"
- [arXiv](https://arxiv.org/abs/2305.14251) | [GitHub](https://github.com/shmsw25/FActScore)

**SAFE** (Wei et al., Google DeepMind + Stanford, NeurIPS 2024) builds on FActScore. The Search-Augmented Factuality Evaluator uses an LLM agent to (1) decompose text into atomic facts, (2) send search queries to Google, and (3) determine if each fact is supported. On ~16k facts, SAFE agreed with human annotators 72% of the time, and won 76% of disagreement cases. Over 20x cheaper than human annotation.
- Paper: "Long-form factuality in large language models"
- [arXiv](https://arxiv.org/abs/2403.18802) | [GitHub](https://github.com/google-deepmind/long-form-factuality)

**AFEV** (2025) introduces dynamic, iterative decomposition -- instead of static prompting, it integrates verification feedback into each decomposition step, enabling adaptive reasoning pathways. Results show +32% DecompScore improvement and 0.12 accuracy gain over static approaches.
- Paper: "Fact in Fragments: Deconstructing Complex Claims via LLM-based Atomic Fact Extraction and Verification"
- [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0957417425041879)

**Extractive Fact Decomposition** (EMNLP 2025) proposes extractive rather than abstractive decomposition -- the JEDI model extracts atomic fact spans using an encoder-only architecture in a single forward pass, eliminating the need for generative LLMs at inference time. This is much faster and cheaper.
- [ACL Anthology](https://aclanthology.org/2025.emnlp-main.1615.pdf)

### Desiderata for atomic facts

The literature converges on three properties:
1. **Minimality** -- irreducible, cannot be broken down further
2. **Interpretability** -- standalone semantics, understandable without context
3. **Completeness** -- the set of atoms jointly covers all information in the original

### Application to Petrarca

Atomic decomposition is the natural first step in the pipeline. When Petrarca extracts "novelty claims" from articles via Gemini, it is already doing a rough version of this. The research suggests we should:
- Decompose claims more aggressively into truly atomic units
- Use few-shot prompting with curated examples (the most effective technique per the literature)
- Consider extractive approaches (JEDI-style) for cost efficiency at scale
- Ensure each atom is self-contained (decontextualized) -- see Section 3

---

## 3. Claim Normalization and Canonicalization

### What it is

Transforming extracted claims into standardized, unambiguous, context-independent statements. This is crucial: two claims from different articles about the same insight need to be in comparable form before any similarity check can work.

### Key Work

**ClaimNorm / "From Chaos to Clarity"** (Sundriyal et al., Findings of EMNLP 2023) introduced claim normalization as a formal NLP task. The CACN approach uses chain-of-thought reasoning and claim check-worthiness estimation to transform noisy social media posts into normalized claims. The CLAN dataset provides 6k+ examples of post-to-normalized-claim pairs.
- Paper: "From Chaos to Clarity: Claim Normalization to Empower Fact-Checking"
- [arXiv](https://arxiv.org/abs/2310.14338) | [ACL Anthology](https://aclanthology.org/2023.findings-emnlp.439/)

**CLEF-2025 CheckThat! Lab Task 2** established claim normalization as a shared task spanning 20 languages. The winning approaches use lightweight retrieval-first, LLM-backed pipelines that dynamically prompt models with in-context examples. This confirms that LLM-based normalization is the current state of the art.
- [arXiv](https://arxiv.org/abs/2503.14828)

**Document-level Claim Extraction and Decontextualization** (Deng, Schlichtkrull, Vlachos, ACL 2024) tackles the problem of extracting claims from full documents (not just sentences) and making them self-contained. The pipeline: (1) sentence extraction via extractive summarization, (2) context generation, (3) sentence decontextualization, (4) check-worthiness estimation. This is directly relevant to Petrarca -- articles are documents, and claims extracted from them need decontextualization to be comparable.
- [ACL Anthology](https://aclanthology.org/2024.acl-long.645/) | [GitHub](https://github.com/Tswings/AVeriTeC-DCE)

**Microsoft Claimify** (2025) is the most practical recent system. Its three-stage pipeline -- Selection, Disambiguation, Decomposition -- achieves 99% entailment rate with 87.6% coverage and 96.7% precision. Key innovation: it detects when source text has multiple interpretations and only extracts claims with high-confidence resolution. This is important for articles where context is ambiguous.
- [Microsoft Research Blog](https://www.microsoft.com/en-us/research/blog/claimify-extracting-high-quality-claims-from-language-model-outputs/)
- [arXiv](https://arxiv.org/pdf/2502.10855)

**Extract-Define-Canonicalize (EDC)** (Zhang & Soh, EMNLP 2024) provides a three-phase framework for knowledge graph construction: (1) open information extraction producing natural-language triples, (2) schema definition (automatic if no predefined schema exists), (3) post-hoc canonicalization using trained retrieval components. This is the most relevant architecture for Petrarca's problem: extract claims freely, then define and canonicalize them.
- [ACL Anthology](https://aclanthology.org/2024.emnlp-main.548/) | [GitHub](https://github.com/clear-nus/edc)

**CESI** (Vashishth et al., WWW 2018) remains relevant as the canonical approach to canonicalizing Open Knowledge Bases. It learns embeddings for noun phrases and relation phrases using side information, then clusters them. The three-step procedure -- side information acquisition, embedding learning, clustering -- could be adapted for claim canonicalization.
- [ACL](https://dl.acm.org/doi/fullHtml/10.1145/3178876.3186030) | [GitHub](https://github.com/malllabiisc/cesi)

### Application to Petrarca

The normalization step is where the biggest gains are for novelty comparison. After atomic decomposition:
1. **Decontextualize** each claim (resolve pronouns, add necessary context from the article)
2. **Normalize** into a canonical form (consistent tense, remove hedging language, standardize entities)
3. **Canonicalize** entities and relations (e.g., "SpaceX" and "Space Exploration Technologies" map to the same entity)

The EDC framework's approach of extracting freely and then canonicalizing post-hoc is more practical than trying to extract into a fixed schema upfront.

---

## 4. Textual Entailment for Novelty

### What it is

Using Natural Language Inference (NLI) to determine whether a new claim is *entailed by* (already covered by) existing knowledge. If claim B is entailed by your knowledge base, it is not novel. If it is "neutral" (not entailed, not contradicted), it is potentially novel.

### Key Work

**Ghosal et al. (Computational Linguistics 2022)** provide the definitive survey connecting novelty detection to NLI. Their core argument: multi-premise entailment is the closest formal approximation to identifying semantic-level redundancy. If a document's claims are all entailed by the union of previously seen documents, that document contains nothing new. The challenge is that non-novel information may be "assimilated from multiple source documents" -- you need multi-hop reasoning across premises.
- Paper: "Novelty Detection: A Perspective from Natural Language Processing"
- [MIT Press](https://direct.mit.edu/coli/article/48/1/77/108847/Novelty-Detection-A-Perspective-from-Natural)

**Multi-Premise Entailment (MPE)** is a variant of standard NLI where the premise consists of multiple independently written sentences. For Petrarca, the "premises" are all previously extracted claims from all previously read articles. The entailment model must determine whether a new claim is entailed by this collection. Ghosal et al.'s architecture uses a relevance detection module (which premises are relevant?) followed by a novelty detection module (aggregating partial entailments). This two-stage design -- retrieve relevant premises, then check entailment -- is directly applicable.
- Paper: "Document Level Novelty Detection: Textual Entailment Lends a Helping Hand"
- [ACL Anthology](https://aclanthology.org/W17-7517/)

**Atomic-SNLI** (2025) addresses a critical gap: current NLI models work at sentence level but perform poorly on atomic-level inference. The paper constructs a dataset by decomposing SNLI examples into atomic facts and shows that existing models perform "substantially worse on atomic-level inference." Fine-tuning on Atomic-SNLI fixes this while maintaining sentence-level performance. This is directly relevant: Petrarca needs atomic-level entailment, not sentence-level.
- [arXiv](https://arxiv.org/abs/2601.06528)

**"NLI under the Microscope"** (Srikanth & Rudinger, NAACL 2025) uses atomic hypothesis decomposition to analyze NLI failures, showing that decomposition reveals systematic patterns in model errors. This suggests that decompose-then-entail is more reliable than whole-sentence entailment.
- [ACL Anthology](https://aclanthology.org/2025.naacl-long.130/)

**Retrieve-and-Aggregate for Document-Level NLI** (2024) provides practical methods: split documents into sentences, score each against the hypothesis using sentence-pair NLI models, then apply aggregation heuristics (max, mean, weighted). Advanced pipelines concatenate top-ranked spans and reapply the NLI model. This is the scalable approach for Petrarca -- you do not need to feed the entire knowledge base as premise.

**Knowledge-Enabled Textual Entailment** (IBM Research) incorporates background knowledge from ConceptNet or LLM-generated "commonsense axioms" to bridge gaps where the hypothesis requires unstated facts. For Petrarca, this means the system could infer that "reusable rockets" and "SpaceX's Falcon 9" are related even if the knowledge base never explicitly links them.
- [GitHub](https://github.com/IBM/knowledge-enabled-textual-entailment)

**Exploring Factual Entailment with NLI** (*SEM 2024) applies NLI specifically to news media factual claims, the closest domain to Petrarca's use case.
- [ACL Anthology](https://aclanthology.org/2024.starsem-1.15/)

### Application to Petrarca

The entailment approach is the most principled way to check novelty. The pipeline would be:
1. Maintain a "knowledge base" of all previously extracted, normalized claims
2. For each new claim from a new article, retrieve the top-k most similar existing claims (using embeddings for retrieval)
3. Run NLI to check entailment: is the new claim entailed by any combination of existing claims?
4. If entailed: mark as "known." If neutral: mark as "potentially novel." If contradictory: mark as "challenges existing knowledge" (very interesting to the user).

The retrieve-then-entail pattern makes this scalable. The Atomic-SNLI finding that atomic-level NLI needs specific training is important -- we should use models fine-tuned for atomic inference.

---

## 5. Structured Knowledge Representations Beyond Embeddings

### Open Information Extraction (OpenIE) Triples

**What it is**: Extracting (subject, predicate, object) triples from text without a predefined schema. Example: "SpaceX reduced launch costs by 90%" becomes `(SpaceX, reduced, launch costs) + qualifier(by 90%)`.

**State of the art**: A comprehensive 2024 survey (EMNLP Findings 2024) covers the evolution from rule-based to neural to LLM-based OpenIE. Key finding: OIE-based embeddings consistently outperform other representations (lexical, dependency parse, SRL) for downstream comparison tasks. Modern LLM-based extractors can produce high-quality triples via few-shot prompting.
- [ACL Anthology](https://aclanthology.org/2024.findings-emnlp.560/)

**Canonicalization challenge**: Raw OpenIE triples have the same paraphrase problem as free text -- "Barack Obama" and "Obama" and "the 44th president" all refer to the same entity. CESI and EDC (described above) address this with embedding-based clustering and schema-driven canonicalization.

**For Petrarca**: OpenIE triples provide more structure than free-text claims but less than a full ontology. They enable comparison at the predicate level (did another article already say something about the same subject with the same type of relation?) without requiring a predefined schema. The EDC framework's approach of extracting triples freely and canonicalizing post-hoc is particularly relevant.

### Abstract Meaning Representation (AMR)

**What it is**: A semantic formalism that represents the meaning of a sentence as a rooted, directed graph. Nodes are concepts (often aligned with PropBank framesets), edges are semantic relations. AMR abstracts away from surface syntax, so paraphrases map to the same (or very similar) graph structures.

**Recent work**: A 2025 survey (arXiv) covers the full history and current state. AMR parsing accuracy has improved substantially with transformer models (Smatch scores ~76.5% for hybrid neuro-symbolic pipelines). AMR has been used as a "semantic interlingua" for translation and for hallucination detection.
- [arXiv](https://arxiv.org/html/2505.03229v1)

**Limitations**: AMR omits tense, aspect, morphology, word order, and figurative language. Accurate alignment between text and graph nodes remains an open problem. Cross-lingual AMR shows that source language significantly influences graph structure.

**For Petrarca**: AMR is theoretically ideal -- paraphrases converge to the same graph -- but practical AMR parsing is still error-prone and computationally expensive. It may be useful as a research direction but is not ready for a production pipeline.

### Semantic Frames (FrameNet)

**What it is**: FrameNet defines ~1,200 "frames" (schematic representations of situations) with "frame elements" (participants, props, locations). Sentences evoke frames and fill frame elements. Example: the "Commerce_buy" frame has elements like Buyer, Goods, Seller, Money.

**Recent work**: LLM-based frame-semantic parsing (2024) achieves ~77 F1 on FrameNet 1.7 using conditional random fields on top of LLM representations. In-context learning with LLMs for frame parsing has been explored for the first time. Framester links FrameNet to WordNet, VerbNet, BabelNet, and DBpedia in a large-scale linguistic KG (~30M triples).
- [arXiv](https://arxiv.org/html/2507.23082v1)

**For Petrarca**: Frames provide a middle ground between raw text and formal logic. Two articles describing "buying a company" would evoke the same frame even with completely different wording. However, FrameNet's fixed frame inventory may not cover the diverse topics in Petrarca's articles (history, AI, policy, literature). Custom frame induction (FrameEOL, 2024) using causal language models could address this.

### Discourse Graphs

**What it is**: An information model that treats discourse moves (questions, claims, evidence) and their relations (supports, opposes, extends) as first-class units, rather than papers or sources. Developed by Joel Chan at the University of Maryland's OASIS lab.

**Implementation**: The Roam Research Discourse Graph extension lets users structure notes with typed pages (Question, Claim, Evidence) and typed links (supports, opposes, informs). The grammar is client-agnostic and has been implemented in Obsidian, Logseq, and other tools.
- [Discourse Graphs](https://discoursegraphs.com/)
- [Joel Chan, "Discourse Graphs for Augmented Knowledge Synthesis"](https://joelchan.me/assets/pdf/Discourse_Graphs_for_Augmented_Knowledge_Synthesis_What_and_Why.pdf)

**For Petrarca**: Discourse graphs are the closest existing model to what Petrarca needs. Instead of just storing claims, Petrarca could store a discourse graph where:
- **Claims** are the atomic units extracted from articles
- **Evidence** links point back to the source article/paragraph
- **Support/oppose** relations connect claims across articles
- **Questions** represent the user's interests or open threads

This would enable novelty detection at the structural level: a new claim is novel not just if its text is new, but if it adds a new node to the discourse graph that is not entailed by existing nodes.

---

## 6. Proposition-Level Embeddings

### What it is

Standard sentence embeddings encode entire sentences into single vectors, which conflates multiple propositions. Proposition-level embeddings learn distinct vector representations for each atomic proposition *within* a sentence, enabling fine-grained semantic comparison.

### Key Work

**Dense X Retrieval** (Chen et al., EMNLP 2024) introduces "propositions" as a retrieval unit, defined as "atomic expressions within text, each encapsulating a distinct factoid and presented in a concise, self-contained natural language format." Indexing a corpus by propositions significantly outperforms passage-level and sentence-level retrieval. Retrieval by propositions enables higher density of relevant information in prompts.
- Paper: "Dense X Retrieval: What Retrieval Granularity Should We Use?"
- [ACL Anthology](https://aclanthology.org/2024.emnlp-main.845/)

**Sub-Sentence Encoder** (Chen et al., NAACL 2024) is the most directly relevant work. It learns contextual embeddings corresponding to different atomic propositions within a text sequence, contrastively trained to recognize semantic equivalence between propositions across different texts. Key properties:
- Same inference cost and space complexity as standard sentence encoders
- Demonstrated effectiveness in retrieving supporting facts for fine-grained text attribution
- Recognizes conditional semantic similarity (two texts are similar with respect to a specific proposition, even if they differ in others)
- Released T5-large model and proposition segmentation tools on HuggingFace
- Paper: "Sub-Sentence Encoder: Contrastive Learning of Propositional Semantic Representations"
- [ACL Anthology](https://aclanthology.org/2024.naacl-long.89/) | [GitHub](https://github.com/schen149/sub-sentence-encoder)

### Application to Petrarca

Sub-sentence encoders are extremely relevant. Instead of comparing full claims as single vectors, Petrarca could:
1. Decompose claims into atomic propositions
2. Encode each with a sub-sentence encoder
3. Compare at the proposition level, getting fine-grained similarity
4. A claim is "known" only if *all* its propositions are similar to existing ones; if some propositions are new, the claim contains partial novelty

This also solves a practical problem: articles often combine known background with a novel finding in a single sentence. Proposition-level comparison can identify which part is new.

---

## 7. Non-Factual Knowledge: Arguments, Workflows, Theories

A significant challenge for Petrarca: many interesting "knowledge contributions" from articles are not verifiable facts. They are arguments, theories, workflows, perspectives, or experiential reports. How do you represent and compare these?

### Argument Mining

**What it is**: Automatically identifying argumentative structures -- claims, premises, and relations (support, attack) -- from text. Active since ~2015, with dedicated ACL workshops annually.

**Recent developments**: The 11th Workshop on Argument Mining at ACL 2024 and the planned 2025 workshop show continued activity. LLMs have been applied to argument mining tasks, including factual vs. opinion classification (achieving F1 ~0.80). Counterfactual calibration and actor masking techniques reduce partisan bias in stance detection.
- [ACL 2024 Workshop](https://argmining-org.github.io/2024/)
- [LLMs in Argument Mining Survey](https://arxiv.org/html/2506.16383v3)

**Perspectivism** is an emerging paradigm in computational argumentation (2024) that ensures captured views are representative of relevant social groups, not just majority opinions.

**For Petrarca**: Articles about policy, society, or technology often contain arguments, not facts. "Universal basic income would reduce poverty" is a claim with supporting arguments, not a verifiable fact. Argument mining provides:
- A taxonomy for non-factual claims (opinion, prediction, recommendation, value judgment)
- Structure for linking claims to their evidence/warrants
- Methods for detecting when two articles make the *same* argument even with different wording

### The AFaCTA Taxonomy of Claim Types

**AFaCTA** (Ni et al., ACL 2024) addresses a fundamental problem: the blurry boundary between factual claims and opinions. The framework identifies claim types including:
- Quoting quantities, statistics, and data
- Claiming correlations or causation
- Asserting existing laws or rules
- Pledging future plans or making predictions
- Personal opinions explicitly based on verifiable facts

This taxonomy is directly useful for Petrarca. Different claim types need different comparison strategies:
- **Factual claims** can be compared via entailment
- **Causal claims** should be compared by their causal structure (X causes Y)
- **Predictions** should be compared by their prediction target and direction
- **Opinions/values** should be compared by their stance on a topic
- [ACL Anthology](https://aclanthology.org/2024.acl-long.104/)

### Procedural Knowledge (How-To)

**What it is**: Knowledge about how to perform tasks, as opposed to declarative knowledge about what is true.

**Research**: Procedural knowledge extraction from instructional texts uses semantic role labeling to identify steps, preconditions, and goals. Knowledge graphs have been extended to support both declarative ("what is") and procedural ("how to") knowledge. A 2024 study at LREC found that LLMs benefit more from declarative knowledge in most tasks, but procedural knowledge outperforms in reasoning tasks.
- [LREC 2024](https://aclanthology.org/2024.lrec-main.980.pdf)

**For Petrarca**: Many technology articles describe novel workflows, techniques, or methodologies. Representing these as step sequences with preconditions and outcomes would enable comparison: "This article describes a new data pipeline" vs "I already know a similar pipeline from article X." The comparison is structural (same steps, different tools?) rather than textual.

### Narrative and Experiential Knowledge

**What it is**: Knowledge embedded in stories, case studies, and experience reports. "We tried X and it failed because Y" is experiential knowledge that does not fit the fact/opinion dichotomy.

**Research**: The Relatio pipeline (Ash et al., 2024) extracts narrative chains as sequences of semantic roles (actor, act, acted-upon). The 6th Workshop on Narrative Understanding at EMNLP 2024 explored computational models of narrative. Stanford's Narrative Chains project studies the best representations for narrative knowledge (graph, linear chain, or frame).
- [Narrative Understanding Workshop](https://aclanthology.org/volumes/2024.wnu-1/)

**For Petrarca**: Experience reports and case studies are common in technology articles. A representation that captures (agent, action, outcome, context) would enable comparison: "Company X tried microservices and had scaling problems" is similar to "We adopted a service-oriented architecture and struggled with distributed tracing." The structural similarity (tried-architecture-had-problems) is the same even though the surface text differs.

### Automated Novelty Evaluation

**Wu et al. (JASIST 2025)** directly address the problem of automated novelty assessment. Their approach uses LLMs to summarize methodology sections and human peer-review reports as complementary knowledge sources, then fine-tunes BERT-class models with a sparse-attention fusion module. Key insight: human experts have judgment abilities that LLMs lack, and LLMs have broader knowledge than any individual expert. The combination outperforms either alone.
- [JASIST](https://asistdl.onlinelibrary.wiley.com/doi/10.1002/asi.70005)

---

## 8. Practical Systems and Implementations

### Wikidata's Claim Model

Wikidata represents knowledge as **statements** composed of a **claim** (property-value pair) plus optional qualifiers, references, and ranks. This is a production-tested model for structured knowledge at massive scale. Key patterns relevant to Petrarca:
- **Property-value structure**: Every claim has a typed property and a typed value
- **Qualifiers**: Add context (time period, location, conditions)
- **Ranks**: Preferred, normal, deprecated -- for handling conflicting claims
- **Deduplication**: Entity merging through community processes and automated detection
- [Wikidata Help: Statements](https://www.wikidata.org/wiki/Help:Statements)

### Cognee + Obsidian

The Cognee integration with Obsidian (2024) demonstrates automated knowledge graph construction from personal notes using LLMs. It extracts entities, builds graphs, and summarizes clusters of related content. This is the closest existing tool to what Petrarca would build.

### Microsoft GraphRAG

Released open-source in 2024, GraphRAG uses LLMs to build knowledge graphs from document collections, then applies community detection to create hierarchical summaries. It solves the "whole-dataset understanding" problem that traditional RAG cannot handle. The community detection approach could be adapted for Petrarca's topic clustering.

### KGGen (2025)

A recent tool for extracting knowledge graphs from plain text using language models, representing the latest in practical KG construction.
- [arXiv](https://arxiv.org/html/2502.09956v1)

---

## 9. Synthesis: A Proposed Architecture for Petrarca

Based on this research, here is an architecture for knowledge representation that enables reliable novelty comparison. It combines the most promising techniques from each area.

### Representation: The Atomic Claim Store

Each article produces a set of **atomic claims**, stored in a normalized form:

```
AtomicClaim {
  id: string
  source_article_id: string
  source_paragraph: string          // for attribution

  // The claim in normalized natural language
  normalized_text: string           // decontextualized, canonical form

  // Structured representation
  claim_type: enum {
    FACTUAL,                        // verifiable fact
    CAUSAL,                         // X causes/leads to Y
    COMPARATIVE,                    // X is more/less than Y
    PROCEDURAL,                     // how to do X
    EVALUATIVE,                     // X is good/bad/important
    PREDICTIVE,                     // X will happen
    EXPERIENTIAL                    // we tried X and found Y
  }

  // Optional structured fields (depending on type)
  subject: string                   // canonicalized entity
  predicate: string                 // normalized relation
  object: string                    // canonicalized entity/value
  qualifiers: {                     // context
    time_period?: string
    domain?: string
    conditions?: string[]
  }

  // Embeddings for retrieval
  proposition_embedding: float[]    // sub-sentence encoder embedding

  // Novelty status (computed)
  novelty_status: enum { NEW, KNOWN, CONTRADICTS, EXTENDS }
  entailed_by: string[]             // IDs of existing claims that entail this

  // Topic linkage
  topics: string[]                  // normalized topic labels

  // User interaction
  user_marked_known: boolean
  user_marked_interesting: boolean
}
```

### Pipeline: Extract -> Normalize -> Compare -> Classify

**Step 1: Atomic Decomposition** (per article)
- Use LLM (Gemini Flash) with few-shot prompting to decompose article into atomic claims
- Apply the AFEV principle of iterative decomposition for complex claims
- Classify each claim by type (using the AFaCTA taxonomy)

**Step 2: Decontextualization and Normalization** (per claim)
- Resolve pronouns, add necessary context from the article
- Normalize to canonical form (consistent tense, standardized entities)
- Extract structured fields (subject, predicate, object) where applicable
- This is where the Claimify three-stage pipeline (Selection, Disambiguation, Decomposition) applies

**Step 3: Embedding and Retrieval** (per claim)
- Encode normalized claim using sub-sentence encoder (or standard sentence encoder as fallback)
- Retrieve top-k most similar existing claims from the claim store

**Step 4: Entailment Check** (per claim)
- Run NLI model on (retrieved existing claims, new claim) pairs
- Use a model fine-tuned for atomic-level inference (Atomic-SNLI-style)
- Apply multi-premise aggregation for claims entailed by *combinations* of existing claims
- Classify: ENTAILED (known), NEUTRAL (novel), CONTRADICTION (challenges existing knowledge)

**Step 5: Interest Scoring** (per claim)
- Cross-reference with user's topic interests from the interest model
- Novel claims in high-interest topics = highest priority
- Contradictions to existing knowledge = flagged for attention
- Known claims = filtered out of presentation

### Practical Considerations

**Cost**: The full pipeline (LLM decomposition + embedding + NLI) is expensive per article. Mitigation:
- Use Gemini Flash for decomposition (cheap, fast)
- Use extractive decomposition (JEDI-style) once the claim store is large enough to train on
- Cache embeddings; NLI is only needed for the top-k retrieved candidates
- Run pipeline on the server (Hetzner) during the 4-hour cron job

**Scale**: For a single user reading ~5-10 articles/day, the claim store grows at maybe 50-100 claims/day. After a year that is ~20-30k claims. This is easily manageable for embedding search (FAISS or similar). NLI checks on top-k (k=5-10) retrieved claims are fast.

**Bootstrapping**: The claim store starts empty. Initially, everything is "novel." The system becomes useful after the user has read ~50-100 articles and the store has ~1000+ claims. User feedback ("I knew this") accelerates bootstrapping.

**Non-factual claims**: The claim_type field is critical here. For EVALUATIVE and PREDICTIVE claims, entailment is less meaningful. Instead, compare by (topic, stance) -- "Does another article already express the same opinion about the same topic?" For PROCEDURAL claims, compare by (goal, method) -- "Does another article already describe a way to achieve the same goal?"

**Incremental approach**: Start with just Steps 1 + 3 (decompose + embed), which is cheap and already better than whole-article embedding. Add NLI-based entailment checking later as the claim store grows and the system needs to distinguish fine-grained differences.

### Key Open Questions

1. **Granularity calibration**: How atomic is atomic enough? Too fine-grained and you lose meaning ("SpaceX" is an entity, not a claim). Too coarse and paraphrases slip through. The literature suggests targeting propositions that would be one row in a fact-checking spreadsheet.

2. **Claim drift**: The same concept evolves across articles. "GPT-4 is the best LLM" was true in 2023 but not in 2025. Time-qualified claims need temporal reasoning.

3. **Subjective novelty**: What counts as "novel" is subjective and depends on the user's prior knowledge, which is not fully captured in the claim store. The user's "I knew this" signal is essential for calibration.

4. **Cross-article synthesis**: Some novelty only appears when combining claims from multiple articles. "Article A says X, Article B says Y, and together X+Y implies Z which nobody stated explicitly." This is multi-hop reasoning and is the hardest form of novelty detection.

5. **Schema evolution**: As the claim store grows, the implicit schema (what topics, what predicates, what entity types) evolves. The EDC framework's approach of automatic schema definition and self-canonicalization is the right model here.

---

## References Summary

| Paper | Venue | Year | Key Contribution |
|-------|-------|------|------------------|
| FActScore | EMNLP | 2023 | Atomic fact decomposition for factuality evaluation |
| SAFE | NeurIPS | 2024 | Search-augmented atomic fact verification at scale |
| AFEV | Expert Systems | 2025 | Dynamic iterative claim decomposition |
| JEDI (Extractive Fact Decomposition) | EMNLP | 2025 | Encoder-only extractive atomic fact extraction |
| ClaimNorm / "From Chaos to Clarity" | EMNLP Findings | 2023 | Claim normalization as formal NLP task |
| Document-level Claim Extraction | ACL | 2024 | Claim decontextualization from full documents |
| Claimify | Microsoft Research | 2025 | Production-quality claim extraction pipeline |
| EDC | EMNLP | 2024 | Extract-Define-Canonicalize for KG construction |
| CESI | WWW | 2018 | Canonicalization of Open KBs via embeddings |
| Novelty Detection survey (Ghosal) | Comp. Linguistics | 2022 | NLI-based novelty detection framework |
| Atomic-SNLI | arXiv | 2025 | Fine-grained atomic NLI dataset and training |
| NLI under the Microscope | NAACL | 2025 | Atomic hypothesis decomposition for NLI analysis |
| Dense X Retrieval | EMNLP | 2024 | Propositions as retrieval units |
| Sub-Sentence Encoder | NAACL | 2024 | Proposition-level contrastive embeddings |
| AFaCTA | ACL | 2024 | Claim type taxonomy with factual/opinion boundary |
| Automated Novelty Evaluation | JASIST | 2025 | Human+LLM collaborative novelty assessment |
| OpenIE Survey | EMNLP Findings | 2024 | Comprehensive survey of OpenIE methods |
| AMR Survey | arXiv | 2025 | State of Abstract Meaning Representation |
| Discourse Graphs (Chan) | -- | 2022 | Knowledge synthesis via discourse structure |
| Cosine Similarity critique | ACM Web | 2024 | Limitations of embedding-based similarity |
| CLEF-2025 CheckThat! | CLEF | 2025 | Shared task on claim normalization (20 languages) |
