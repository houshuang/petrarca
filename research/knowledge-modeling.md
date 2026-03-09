# Personal Knowledge Modeling and Novelty-Aware Reading: Tools, Algorithms, and Approaches

Research into existing tools, open-source projects, and algorithms for modeling user knowledge, detecting novelty in reading material, extracting claims, organizing topics hierarchically, and recommending content based on what someone *knows* rather than just what they *like*.

*Last updated: 2026-03-07*

---

## 1. Read-Later / Knowledge Tools with Novelty Features

### What exists today

No existing read-later app models user knowledge or detects novelty in any meaningful way. This is Petrarca's core differentiation. Here is what each major player actually does:

**Readwise Reader** — The current leader for power readers. AI features (via "Ghostreader" powered by GPT-4o) include inline summarization, flashcard generation from highlights, term definitions, and chat with documents. The Daily Review surfaces highlights on a spaced repetition schedule. However, Readwise models *reading behavior* (what you highlighted, when), not *knowledge state* (what you know). There is no "I already know this" signal, no novelty scoring, no knowledge-aware ranking. The Readwise Reader MCP Server now allows AI agents to query your reading data programmatically.
- Source: https://readwise.io/read
- Blog: https://learningaloud.com/blog/2025/02/12/ai-in-readwise/

**Matter** — Beautiful mobile reading with three paradigms (save, subscribe, discover). AI summary feature. Integrates with Obsidian, Readwise, Notion for export. No knowledge modeling whatsoever.
- Source: https://hq.getmatter.com/

**Pocket** — Recently added AI summaries and key point extraction. Still purely popularity-based recommendation. No personalization beyond "more/less like this."
- Source: https://getpocket.com/

**Omnivore** — Shut down November 2024 (acquired by ElevenLabs). Open-source code remains on GitHub but is unmaintained.

### Newer AI-powered reading tools

**Atlas Workspace** — The most interesting newer entrant. Turns highlights, notes, and summaries into a connected knowledge graph. AI analyzes uploaded content, extracts concepts, and creates connections automatically (mind map view). When you add new content, it shows how it relates to what you already have. This is the closest to "knowledge-aware" reading in the market, though it's built for study/research rather than read-later.
- Source: https://www.atlasworkspace.ai/
- **Petrarca can borrow**: The automatic concept extraction and connection visualization. Atlas proves that users value seeing how new content relates to existing knowledge.

**Kognara** — AI reading platform that claims to adapt to the user's knowledge level. Smart highlighting categorizes highlights by themes, concepts, and importance. AI assistant provides personalized explanations based on reading level. Available on web.
- Source: https://kognara.app/
- **Petrarca can borrow**: The idea of adapting explanations/presentation to the user's knowledge level. Though Kognara seems more oriented toward books than articles.

**Scholarcy** — Focused on academic papers. Generates structured "flashcard" summaries with key findings, methodology, limitations, and citations. Extracts structured data from each paper.
- Source: https://www.scholarcy.com/
- **Petrarca can borrow**: The structured extraction template — key findings, methodology, limitations — could be adapted for article claim extraction.

**Elicit** — AI research assistant by Ought. Uses language models to search 138M academic papers (via Semantic Scholar), extract key findings into a structured matrix, and support literature review workflows. All AI claims are backed by sentence-level citations.
- Source: https://elicit.com/
- **Petrarca can borrow**: The "research matrix" pattern — extracting specific structured fields from each article and presenting them in a comparable format. The citation-backed claims pattern.

**Semantic Scholar (Semantic Reader)** — AI-powered augmented reader for academic papers. Provides context for citations, highlights key passages, links to related work.
- Source: https://www.semanticscholar.org/
- **Petrarca can borrow**: The augmented reader concept — overlaying intelligence on top of the reading experience.

### Gap confirmed

The gap identified in `prior-art.md` remains: **no tool models what the user already knows and uses that to detect novelty in incoming content.** Atlas comes closest with its knowledge graph, but it doesn't explicitly score "how much of this is new to you." This remains Petrarca's unique positioning.

---

## 2. Claim Extraction / Argument Mining Libraries

### Production-ready tools

**Open Argument Mining Framework (oAMF)** — The most significant recent development. Presented at ACL 2025. An open-source, modular platform that unifies 17+ argument mining methods into composable pipelines. Modules are dockerized Flask services using xAIF format for interoperability. Supports claim detection, argument structure extraction, and argument relationship classification.
- Interfaces: Python API, web UI, drag-and-drop pipeline builder (via n8n)
- GitHub: https://github.com/arg-tech/oAMF
- Paper: https://aclanthology.org/2025.acl-demo.31/
- **Petrarca can borrow**: The modular pipeline architecture. Could potentially use individual oAMF modules (via Docker) for claim detection on articles during pipeline processing. However, the framework is heavyweight for our use case — running Gemini Flash with structured output is simpler and likely sufficient.

**Canary** — A simpler Python argument mining library by Open-Argumentation. Extracts argumentative components and their relationships from text. Open source, designed to be easy to integrate. Currently under active development and not fully feature-complete.
- GitHub: https://github.com/Open-Argumentation/Canary
- **Petrarca can borrow**: If we want a lightweight local alternative to LLM-based claim extraction, Canary could be a starting point. But LLMs currently outperform specialized models for this task.

### Hugging Face models for zero-shot claim/topic classification

**facebook/bart-large-mnli** — Zero-shot classification via natural language inference. Can classify text into arbitrary categories without training. Works by framing classification as NLI: "This text is about [topic]" → entailment/contradiction/neutral.
- Hugging Face: https://huggingface.co/facebook/bart-large-mnli

**MoritzLaurer/mDeBERTa-v3-base-mnli-xnli** — Multilingual version (100 languages). Good for Petrarca's multilingual content.
- Hugging Face: https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli

**Zero-shot classification pipeline** — Hugging Face's `pipeline("zero-shot-classification")` makes it trivial to classify text against arbitrary label sets. Could be used to verify/refine LLM-generated topic assignments.
- Hugging Face: https://huggingface.co/models?pipeline_tag=zero-shot-classification
- **Petrarca can borrow**: Use zero-shot NLI models as a cheap validation layer on top of LLM-generated topics. Given a claim like "Mediterranean trade routes enabled knowledge transfer," classify against the user's topic hierarchy to find the best match.

### LLM-based claim extraction (the practical approach)

**Instructor + Pydantic** — The most practical approach for Petrarca. Instructor (11k GitHub stars, 3M monthly PyPI downloads) patches LLM clients to return validated Pydantic models. Define a schema like `class ArticleClaims(BaseModel): claims: list[Claim]` and get structured, validated JSON from any LLM.
- GitHub: https://github.com/567-labs/instructor
- **Petrarca can borrow**: Directly. Replace the current raw JSON parsing in `build_articles.py` with Instructor + Pydantic for more robust claim extraction. Works with Gemini, OpenAI, Anthropic, and local models.

**Simon Willison's `llm` tool** — CLI tool for LLMs that added structured output via JSON schemas in v0.23 (Feb 2025). Willison notes: "the single most commercially valuable application of LLMs is turning unstructured content into structured data." The `llm` tool supports schemas across multiple providers (Anthropic, Gemini, OpenAI).
- GitHub: https://github.com/simonw/llm
- Blog: https://simonwillison.net/2025/Feb/28/llm-schemas/
- **Petrarca can borrow**: The framing is exactly right for our pipeline. Could use `llm` as an alternative to direct API calls for pipeline processing, gaining provider-switching flexibility.

### What Petrarca should do

The current approach (Gemini Flash with JSON extraction) is reasonable. Improvements:
1. Add Pydantic validation via Instructor for schema enforcement and automatic retries
2. Design claim schemas more carefully: `{claim_text, topic, novelty_type, confidence, source_passage}`
3. Consider a two-pass approach: LLM extracts claims, then zero-shot NLI validates topic assignments

---

## 3. Topic Hierarchy / Ontology Systems

### Wikidata as a topic backbone

**Wikidata** — The most comprehensive, freely accessible topic hierarchy. 100M+ items organized via `subclass of` (P279) and `instance of` (P31) properties. The ontology root is `entity` (Q35120). Every concept has a unique QID, multilingual labels, and rich relationships.
- SPARQL endpoint: https://query.wikidata.org/
- API: https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service
- **Petrarca can borrow**: Use Wikidata QIDs as canonical topic identifiers. When the LLM extracts a topic like "Mediterranean trade," map it to a Wikidata entity (e.g., Q1247232). This gives us: (a) a unique identifier, (b) the full topic hierarchy (trade → economic activity → human activity), (c) multilingual labels, (d) related topics via Wikidata properties. Practical approach: use the Wikidata API to resolve topic strings to QIDs during pipeline processing.

**wdtaxonomy** — Command-line tool (Node.js) to extract and display taxonomies from Wikidata using SPARQL. Given a Wikidata item, it shows the full subclass hierarchy.
- GitHub: https://github.com/nichtich/wikidata-taxonomy
- Docs: https://wdtaxonomy.readthedocs.io/
- **Petrarca can borrow**: Use wdtaxonomy to bootstrap the topic hierarchy. Run it for key domains (history, AI, politics, etc.) and cache the results as the initial topic tree.

**DBpedia Spotlight** — Entity linking service that finds mentions of DBpedia (and thus Wikipedia/Wikidata) entities in text. Free API, multilingual (English, German, French, Italian, etc.), Apache 2.0 licensed. Can be used for automatic topic detection: if many linked entities are politicians, the text is likely about politics.
- API: https://api.dbpedia-spotlight.org/
- GitHub: https://github.com/dbpedia-spotlight/dbpedia-spotlight-model
- spaCy integration: https://github.com/MartinoMensio/spacy-dbpedia-spotlight
- **Petrarca can borrow**: Run DBpedia Spotlight on article text during pipeline processing to get entity-linked topics grounded in Wikidata/DBpedia. This gives free topic hierarchy via the knowledge graph. The spaCy wrapper makes integration trivial.

### Academic/domain taxonomies

**ACM Computing Classification System** — Hierarchical taxonomy for computing topics. Well-maintained, used by all ACM publications.

**Library of Congress Subject Headings (LCSH)** — Comprehensive topic hierarchy used by libraries worldwide. Available as linked data.

**Medical Subject Headings (MeSH)** — NIH's controlled vocabulary for biomedical literature. Hierarchical, well-maintained.

These are relevant if Petrarca needs domain-specific topic granularity, but Wikidata subsumes most of them.

### LLM-generated topic hierarchies

**TopicGPT** — Uses GPT-3.5/4 for topic modeling. Iteratively prompts the LLM with document samples and previously generated topics. Supports hierarchical topic modeling: top-level topics can be expanded into subtopics via further prompting. Topics are human-readable descriptions, not just keyword lists.
- GitHub: https://github.com/ArikReuter/TopicGPT
- Paper: https://arxiv.org/html/2311.01449v2
- **Petrarca can borrow**: The iterative refinement approach. Start with broad topics from the first batch of articles, then let the LLM refine the hierarchy as more articles arrive. The hierarchy grows organically from the user's actual reading, not from a pre-built ontology.

**BERTopic** — The leading open-source topic modeling library. Uses transformer embeddings + UMAP + HDBSCAN + c-TF-IDF for topic clustering. Supports hierarchical topics (tree-structured topic merging). LLM integration lets you generate human-readable topic labels. Can push/pull models from Hugging Face Hub.
- GitHub: https://github.com/MaartenGr/BERTopic
- Docs: https://maartengr.github.io/BERTopic/
- **Petrarca can borrow**: BERTopic's hierarchical topic modeling could be used to automatically organize the user's topic space as articles accumulate. The guided/seeded topic modeling feature lets you steer topics toward the user's interests.

**Turftopic (KeyNMF)** — Lighter alternative to BERTopic. Seeded KeyNMF combines a seed phrase (what you're interested in) with NMF-based topic modeling. scikit-learn compatible API. Published in JOSS 2025.
- GitHub: https://github.com/x-tabdeveloping/turftopic
- **Petrarca can borrow**: The seeded approach fits Petrarca well — start with the user's declared interests as seeds, then discover subtopics within articles. Simpler than BERTopic for our single-user case.

### Recommended approach for Petrarca

A hybrid strategy:
1. **LLM extraction**: Gemini Flash extracts topics from each article (current approach)
2. **Wikidata grounding**: Map extracted topic strings to Wikidata QIDs via API/DBpedia Spotlight for canonical identifiers and hierarchy
3. **User-driven refinement**: Let the user's feedback (topic chip +/-) adjust the effective hierarchy over time
4. **Periodic BERTopic/TopicGPT clustering**: Batch-process accumulated articles to discover emergent topic structures

---

## 4. Personal Knowledge Graph Tools

### Current landscape

**Obsidian** — Page-based PKM with bidirectional links. Graph view shows connections between notes. The graph view is visually appealing but practically useless for most users — it becomes a hairball. Local-first, markdown files. Massive plugin ecosystem (1700+ plugins). The Obsidian Spaced Repetition plugin adds note-level SRS.
- Source: https://obsidian.md/

**Logseq** — Block-based outliner with bidirectional links. Open source. Built-in flashcards with SRS. PDF annotation. More structured than Obsidian (everything is a block/bullet that can be individually referenced). Free and open source.
- GitHub: https://github.com/logseq/logseq

**Roam Research** — Pioneered bidirectional linking and block references in PKM. Daily notes as default entry point. Powerful queries. Expensive ($15/month), closed source.
- Source: https://roamresearch.com/

**RemNote** — The most relevant for Petrarca. Combines note-taking with deep spaced repetition. Any text can become a flashcard. Knowledge graph with bidirectional links (backlinks are first-class). FSRS algorithm support. The key insight: RemNote treats knowledge as a *graph of concepts with retention states*, not just a collection of documents.
- Source: https://www.remnote.com/
- Knowledge Graph docs: https://help.remnote.com/en/articles/8771354-knowledge-graph
- **Petrarca can borrow**: The concept of tracking retention state per topic/concept. RemNote knows not just "you saw this" but "how well do you remember this." Petrarca could adapt this: track not just interest scores but knowledge confidence per topic, decaying over time.

**InfraNodus** — Text network analysis tool that visualizes text as a knowledge graph (words as nodes, co-occurrences as edges). Key feature: **structural gap detection** — identifies parts of the graph that could be connected but aren't, suggesting blind spots in your knowledge.
- Source: https://infranodus.com/
- Paper: https://dl.acm.org/doi/10.1145/3308558.3314123
- **Petrarca can borrow**: The structural gap detection concept is directly relevant to novelty. If a user's knowledge graph has a gap between "medieval history" and "trade networks," an article about medieval trade routes fills that gap and should score high for novelty. Could implement a simplified version: track which topic pairs co-occur in the user's reading history, and boost articles that bridge unconnected clusters.

### LLM-powered knowledge graph tools

**Graphiti (by Zep)** — Framework for building temporally-aware knowledge graphs. Three-tier architecture: episodic subgraph (raw events), semantic entity subgraph (extracted concepts), community subgraph (clusters). Key innovation: **bi-temporal tracking** — records both when an event occurred and when it was ingested. Supports real-time incremental updates without batch recomputation. Hybrid retrieval (semantic + BM25 + graph traversal).
- GitHub: https://github.com/getzep/graphiti
- Paper: https://arxiv.org/abs/2501.13956
- **Petrarca can borrow**: The temporal knowledge graph architecture is highly relevant. Petrarca could use a simplified version: each article reading is an episode, claims/topics are entities, and the user's knowledge state is the accumulated graph with temporal decay. The bi-temporal model (event time vs. ingestion time) maps to "when was this published" vs. "when did the user read it."

**Neo4j LLM Graph Builder** — Transforms unstructured documents into Neo4j knowledge graphs using LLMs + LangChain. Handles PDFs, web pages, videos.
- GitHub: https://github.com/neo4j-labs/llm-graph-builder
- **Petrarca can borrow**: The pattern of using LLMs to extract SPO triples from articles. But Neo4j is heavyweight for a single-user mobile app — a simpler in-memory or JSON-based graph would suffice.

### What Petrarca should do

Don't build a full knowledge graph. Instead, maintain a **topic-claim matrix**:
- Rows = topics (grounded in Wikidata where possible)
- Columns = claim types (factual, methodological, opinion, connection)
- Cells = knowledge state (unknown, encountered, understood, confident) with timestamps and decay

This is lighter than a graph database but captures the essential structure needed for novelty detection.

---

## 5. Recommendation Algorithms That Model User Knowledge

### The key distinction: preference vs. knowledge

Most recommendation systems model **preference** — what the user likes. Petrarca needs to model **knowledge** — what the user knows. This is a fundamentally different problem:

| Dimension | Preference-based | Knowledge-based |
|-----------|-----------------|-----------------|
| Signal | "User liked X" | "User knows X" |
| Goal | Show more like X | Show what's new given X |
| Decay | Preferences shift gradually | Knowledge persists (with decay) |
| Redundancy | OK to show similar content | Must avoid redundant content |
| Novelty | Nice-to-have metric | Core objective |

### Curiosity-driven recommendation

**Loewenstein's Information Gap Theory** (1994) — Curiosity arises when attention focuses on a gap in one's knowledge. The curious individual is motivated to obtain the missing information. Applied to recommendations: the ideal article is one that makes the user aware of a gap they didn't know they had.
- Paper: https://www.cmu.edu/dietrich/sds/docs/golman/golman_loewenstein_curiosity.pdf
- **Petrarca can borrow**: Frame novelty scoring in terms of information gaps. An article is maximally interesting when it's *adjacent* to what the user knows — close enough to be comprehensible, far enough to be genuinely new. This maps to the concept of a "Curiosity Zone" (Comfort Zone boundary).

**ACM TKDD paper: "Modeling Users' Curiosity in Recommender Systems"** — Proposes using curiosity traits to capture individual differences. Models an individual's curiosity distribution over different stimulus levels. Uses an item's "surprise level" to estimate stimulus, checking whether it falls in the user's "Comfort Zone."
- Paper: https://dl.acm.org/doi/10.1145/3617598
- **Petrarca can borrow**: The comfort zone concept maps directly to our topic-level interest model. Articles with topics mostly in the user's comfort zone but with 1-2 novel claims are in the curiosity sweet spot.

### Beyond-accuracy metrics for recommender systems

**Survey: "Diversity, Serendipity, Novelty, and Coverage"** (Kaminskas & Bridge, ACM TIIS 2017) — The definitive survey on beyond-accuracy objectives. Defines:
- **Novelty**: How different items are from what the user has seen before (user-dependent)
- **Serendipity**: Unexpectedness AND relevance combined
- **Diversity**: How different items are from each other in a recommendation list
- **Coverage**: What fraction of the item catalog gets recommended
- Paper: https://dl.acm.org/doi/10.1145/2926720
- **Petrarca can borrow**: Novelty and serendipity should be explicit scoring dimensions. Formula: `novelty_score = 1 - max_similarity(article_topics, user_known_topics)`. Serendipity requires both novelty AND topic-relevance: `serendipity = novelty * relevance`.

**Eugene Yan's practical guide: "Serendipity: Accuracy's Unpopular Best Friend"** — Excellent practitioner-oriented overview of implementing serendipity in production recommenders. Discusses the serendipity-oriented greedy (SOG) algorithm for reranking.
- Blog: https://eugeneyan.com/writing/serendipity-and-accuracy-in-recommender-systems/
- **Petrarca can borrow**: The reranking approach. Generate a candidate set ranked by relevance, then rerank for serendipity/novelty. This is simpler than jointly optimizing for multiple objectives.

**Google/YouTube intent-based recommendations** (Stanford, 2025) — Research on predicting whether a user's real-time intent is for familiarity or novelty. Incorporating this prediction improved recommendation effectiveness. Different sessions have different intents.
- Source: https://news.stanford.edu/stories/2025/09/behavioral-insights-user-intent-ai-driven-recommendations-youtube
- **Petrarca can borrow**: Session-level intent detection. When the user opens the app, are they in "catch up" mode (familiar topics) or "explore" mode (novel topics)? Could be inferred from time of day, session length, or explicit mode selection.

### Knowledge tracing (from education)

**Deep Knowledge Tracing (DKT)** — Originally from education: models a student's evolving knowledge state by tracking performance on exercises over time. Uses RNNs/LSTMs to predict future performance based on interaction history.
- Survey: https://arxiv.org/html/2105.15106v4

**Knowledge graph + reinforcement learning for learning paths** — Systems that encode prerequisite and semantic relations between topics, update learner mastery in real time via interaction feedback and graph-based propagation, with exponential forgetting mechanisms.
- Paper: https://www.nature.com/articles/s41598-025-17918-x
- **Petrarca can borrow**: The core ideas translate directly:
  - **Interaction history → knowledge state**: Each article read updates the user's topic knowledge
  - **Exponential forgetting**: Knowledge confidence decays if not reinforced (already in our interest model as 30-day decay)
  - **Prerequisite relations**: Some topics require understanding other topics first (e.g., "transformer architecture" before "attention mechanisms")
  - **Mastery estimation**: Don't just track "seen this topic" but "how well does the user understand this topic" based on reading depth, time spent, claims marked as known

### Recommended approach for Petrarca

Combine the curiosity model with knowledge tracing:

```
novelty_score(article) = weighted_avg(
    claim_novelty,          # what fraction of claims are new to user
    topic_gap_bridging,     # does it connect unconnected topic clusters
    depth_advancement,      # does it go deeper than user's current level
    information_gap_fit     # is it in the user's curiosity zone
)

interest_score(article) = weighted_avg(
    topic_match,            # user's interest in the article's topics
    freshness,              # publication recency
    source_trust,           # trust in the source
    exploration_bonus       # epsilon-greedy for discovery
)

final_score = alpha * novelty_score + (1-alpha) * interest_score
# alpha adjustable by user (or inferred from session intent)
```

---

## 6. LLM-Based Approaches

### Topic modeling with LLMs

**BERTopic + LLM integration** — BERTopic can use LLMs to generate human-readable topic labels from keyword clusters. The LLM receives candidate keywords + representative documents and generates a descriptive topic name. Works with any LLM (GPT-4, Claude, local models via Ollama).
- Docs: https://maartengr.github.io/BERTopic/getting_started/representation/llm.html
- **Petrarca can borrow**: Use this for periodic topic space reorganization. After accumulating 100+ articles, run BERTopic to discover emergent topic clusters, then use Gemini to generate readable labels.

**Topic Modeling Techniques for 2026** (Towards Data Science) — Reviews seeded topic modeling, LLM integration, and data summarization techniques. Recommends combining traditional models (for structure) with LLMs (for labels and summarization).
- Article: https://towardsdatascience.com/topic-modeling-techniques-for-2026-seeded-modeling-llm-integration-and-data-summaries/

### Claim extraction with LLMs

**Current best practice**: Use structured output (JSON mode / function calling / Instructor) with a carefully designed schema. The key insight from practitioners is that LLMs are excellent at claim extraction when given:
1. A clear definition of what constitutes a "claim" for your use case
2. A structured output format (Pydantic model or JSON schema)
3. Examples in the prompt (few-shot)

**Petrarca's current approach** (Gemini Flash in `build_articles.py`) is already on the right track. Improvements:

1. **Better claim taxonomy**: Instead of extracting generic "novelty_claims," define types:
   - `factual_claim`: "X happened / X is true" (verifiable)
   - `causal_claim`: "X causes Y" / "X is related to Y"
   - `evaluative_claim`: "X is better/worse than Y"
   - `methodological_claim`: "The way to do X is Y"
   - `predictive_claim`: "X will happen"

2. **Claim-to-topic linking**: Each claim should be tagged with its topic(s), enabling the novelty score: "Is this claim new given what the user knows about these topics?"

3. **Confidence scoring**: LLMs can estimate their confidence in each extracted claim, which helps filter noise.

### Knowledge graph construction with LLMs

**Taxonomy-Driven Knowledge Graph Construction** (ACL Findings 2025) — Combines structured taxonomies, LLMs, and RAG for knowledge graph construction. Key finding: taxonomy-guided LLM prompting combined with RAG-based validation reduces hallucinations by 23.3% while improving F1 scores by 13.9%.
- Paper: https://aclanthology.org/2025.findings-acl.223/
- **Petrarca can borrow**: When extracting topics from articles, provide the existing topic hierarchy as context to the LLM. This anchors extraction to known topics (reducing hallucination of spurious new topics) while still allowing genuine new topics to emerge.

### Novelty detection with LLMs

No widely adopted open-source system exists for "novelty detection" in reading. But the building blocks are all available:

1. **Embedding similarity**: Compute semantic similarity between article claims and the user's known-claims database. New claims with low max-similarity to known claims are novel.
2. **LLM-as-judge**: Ask the LLM directly: "Given that the user knows [these topics/claims], how much of this article is genuinely new?" This is expensive but effective for high-value articles.
3. **Zero-shot NLI**: Frame novelty as textual entailment. For each new claim, check if any known claim entails it. If none do, it's novel.

### LLM-powered personal knowledge management

**Graphiti/Zep** (covered in section 4) is the most sophisticated approach: episodic memory → entity extraction → temporal knowledge graph. For Petrarca, a simplified version:
- Each article reading creates an "episode"
- Claims extracted from the article become entities
- User feedback (known/new, topic +/-) updates entity confidence
- Temporal decay reduces confidence over time
- Novelty = inverse of confidence for matching entities

---

## 7. Practical Recommendations for Petrarca

### Immediate improvements (low effort, high impact)

1. **Add Instructor/Pydantic to the pipeline** for schema-validated claim extraction. Replace raw JSON parsing with typed models. ~2 hours of work.

2. **Implement claim-level novelty tracking**: When the user marks a claim as "knew this," record it. On future articles, compare new claims against the known-claims set using embedding similarity. Surface the novelty ratio ("72% new") prominently.

3. **Use DBpedia Spotlight for entity linking**: Run article text through the free API during pipeline processing. Get Wikidata-grounded entities and their categories for free. ~1 hour to integrate.

4. **Add session-level intent**: Let the user toggle between "catch up" (prioritize familiar topics) and "explore" (prioritize novel topics) modes. Different ranking weights for each.

### Medium-term improvements (1-2 weeks)

5. **Build a topic-claim matrix**: Accumulate claims by topic over time. Track user knowledge state per topic: {unknown, encountered, familiar, confident}. Use this for novelty scoring.

6. **Wikidata topic grounding**: Map LLM-extracted topics to Wikidata QIDs. Get the hierarchy for free. Enables "you know a lot about X but nothing about its parent category Y" insights.

7. **Curiosity zone detection**: Implement Loewenstein's information gap theory. Score articles highest when they're adjacent to (but not within) the user's known topic clusters.

8. **Reranking for serendipity**: After generating the relevance-ranked feed, apply a serendipity reranker that boosts articles bridging unconnected topic clusters.

### Longer-term explorations (experimental)

9. **Periodic BERTopic clustering**: Run BERTopic on all accumulated article text monthly. Discover emergent topic structures. Compare with the user's explicit topic hierarchy.

10. **InfraNodus-style gap detection**: Build a simple topic co-occurrence graph from reading history. Identify structural gaps (topic pairs that should be connected but aren't). Recommend articles that bridge those gaps.

11. **Knowledge tracing adaptation**: Apply DKT-like models to predict the user's topic mastery over time. Use this for more sophisticated novelty scoring.

12. **Two-pass pipeline**: First pass extracts claims (fast, Gemini Flash). Second pass scores claims against the user's knowledge state for novelty (could be local model or embedding comparison — no API cost).

---

## Key Takeaways

1. **Nobody does knowledge-aware reading** — this is genuinely unexplored territory in consumer tools. The closest analogues are in adaptive learning (DKT, knowledge tracing) and PKM tools (RemNote, Atlas).

2. **LLMs are the right tool for claim extraction** — purpose-built NLP models (oAMF, Canary) exist but are outperformed by prompted LLMs with structured output. Use Instructor + Pydantic for robustness.

3. **Wikidata is the free topic hierarchy** — don't build a custom ontology. Ground topics in Wikidata for hierarchy, multilingual labels, and interoperability. Use DBpedia Spotlight for automatic entity linking.

4. **The curiosity zone is the sweet spot** — articles are maximally interesting when adjacent to known territory. This maps to Loewenstein's information gap theory and the comfort zone model from curiosity research.

5. **Temporal decay is essential** — both the adaptive learning literature and knowledge graph research (Graphiti/Zep) emphasize that knowledge confidence should decay over time. The current 30-day decay in the interest model is a reasonable starting point.

6. **Serendipity requires active engineering** — beyond-accuracy research shows that novelty and serendipity must be explicitly optimized, not just hoped for. The reranking approach (generate candidates by relevance, rerank for novelty) is the practical pattern.

---

## References and Links

### Tools and Libraries
- Instructor (structured LLM output): https://github.com/567-labs/instructor
- BERTopic: https://github.com/MaartenGr/BERTopic
- Turftopic/KeyNMF: https://github.com/x-tabdeveloping/turftopic
- TopicGPT: https://github.com/ArikReuter/TopicGPT
- oAMF (argument mining): https://github.com/arg-tech/oAMF
- Canary (argument mining): https://github.com/Open-Argumentation/Canary
- Graphiti/Zep: https://github.com/getzep/graphiti
- DBpedia Spotlight: https://github.com/dbpedia-spotlight/dbpedia-spotlight-model
- wdtaxonomy: https://github.com/nichtich/wikidata-taxonomy
- Simon Willison's llm: https://github.com/simonw/llm

### Reading/Knowledge Tools
- Readwise Reader: https://readwise.io/read
- Atlas Workspace: https://www.atlasworkspace.ai/
- Kognara: https://kognara.app/
- Elicit: https://elicit.com/
- InfraNodus: https://infranodus.com/
- RemNote: https://www.remnote.com/
- Semantic Scholar: https://www.semanticscholar.org/

### Key Papers
- Loewenstein (1994) — Information Gap Theory of Curiosity
- Kaminskas & Bridge (2017) — Diversity, Serendipity, Novelty, and Coverage (ACM TIIS): https://dl.acm.org/doi/10.1145/2926720
- Modeling Users' Curiosity (ACM TKDD 2023): https://dl.acm.org/doi/10.1145/3617598
- Knowledge Tracing survey: https://arxiv.org/html/2105.15106v4
- Taxonomy-Driven KG Construction (ACL 2025): https://aclanthology.org/2025.findings-acl.223/
- Zep Temporal KG Architecture: https://arxiv.org/abs/2501.13956
- oAMF (ACL 2025 Demo): https://aclanthology.org/2025.acl-demo.31/
- Eugene Yan on Serendipity: https://eugeneyan.com/writing/serendipity-and-accuracy-in-recommender-systems/
- Google/Stanford intent-based recommendations: https://news.stanford.edu/stories/2025/09/behavioral-insights-user-intent-ai-driven-recommendations-youtube
