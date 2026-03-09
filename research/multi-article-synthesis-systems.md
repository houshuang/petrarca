# Multi-Article Synthesis Systems: Academic & Technical Deep Dive

Deep research into the algorithms, architectures, and HCI patterns underlying systems that synthesize multiple articles on the same topic into unified, navigable reports with source attribution and drill-down.

Complements `article-synthesis-prior-art.md` (product-focused survey) with academic literature, technical approaches, and implementation strategies.

---

## 1. Multi-Document Summarization with Source Attribution

### 1.1 The Core Problem

Standard multi-document summarization (MDS) produces a single text from multiple inputs. But for Petrarca's use case -- synthesizing 20 articles about "Claude Code" into a navigable report -- we need more: every claim must trace to its source article, the reader must be able to drill down, and the synthesis must be structured by subtopic rather than flattened into a single narrative.

### 1.2 PRIMERA: Pre-Trained Multi-Document Summarization

**Paper:** Xiao et al., "PRIMERA: Pyramid-based Masked Sentence Pre-training for Multi-document Summarization" (ACL 2022)
**Link:** https://arxiv.org/abs/2110.08499
**Code:** https://github.com/allenai/PRIMER

PRIMERA is a pre-trained encoder-decoder transformer designed specifically for multi-document inputs. Key innovations:

- **Gap Sentence Generation (GSG) objective**: During pre-training, important sentences are masked across document boundaries, forcing the model to learn cross-document information aggregation
- **Efficient attention via Longformer**: Handles concatenated multi-document input with linear complexity through local + global attention patterns
- **Entity pyramid**: Selects sentences for masking based on entity frequency across documents, biasing toward cross-document content

PRIMERA outperforms prior models on 6 MDS datasets across zero-shot, few-shot, and supervised settings. It is available as a Hugging Face model (`allenai/PRIMERA-multixscience`).

**Petrarca relevance:** PRIMERA demonstrates that cross-document pre-training objectives dramatically improve synthesis quality. However, it produces flat text without source attribution. For Petrarca, PRIMERA-style models would need to be combined with citation generation (see WebCiteS below) or used in an extractive-then-abstractive pipeline where source tracking is maintained.

### 1.3 WebCiteS: Attributed Query-Focused Summarization

**Paper:** "WebCiteS: Attributed Query-Focused Summarization on Chinese Web Search Results with Citations" (ACL 2024)
**Link:** https://aclanthology.org/2024.acl-long.806/
**Code:** https://github.com/HarlynDN/WebCiteS

This is the most directly relevant academic work for Petrarca's synthesis needs. Key contributions:

- **Task definition**: Given a query and multiple retrieved documents, generate a summary with inline citations that trace each claim to its source passage
- **Fine-grained attribution**: Unlike prior work that evaluates whole-summary attribution, WebCiteS distinguishes between *groundedness errors* (claims not supported by any source) and *citation errors* (claims supported but citing the wrong source)
- **Sub-claim decomposition**: Complex sentences are decomposed into atomic sub-claims, each verified independently against cited sources -- critical for multi-source sentences where different parts come from different articles
- **Human-LLM collaborative annotation**: Annotators extract useful information from documents, LLMs generate candidate summaries, annotators select and refine

**Key finding:** Even the best LLMs (GPT-4, Claude) struggle to correctly cite sources. The paper quantifies how often models fabricate citations, cite the wrong source, or fail to cite at all.

**Petrarca relevance:** This is the template for Petrarca's synthesis output format. Each bullet point in a topic synthesis should carry inline citations like `[Article 3, para 7]`, and the system should decompose complex claims to verify each sub-claim independently. The sub-claim decomposition approach aligns perfectly with Petrarca's existing `novelty_claims` extraction.

### 1.4 "Do Multi-Document Summarization Models Synthesize?"

**Paper:** DeYoung et al., "Do Multi-Document Summarization Models Synthesize?" (TACL 2024)
**Link:** https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00687/124262/

A critical evaluation paper that asks whether MDS models actually perform synthesis (combining information across documents) or just select from individual documents. Key findings:

- **Partial synthesis at best**: Even GPT-4 only partially synthesizes -- models are over-sensitive to input ordering and under-sensitive to input composition changes
- **Ordering sensitivity**: Simply reordering the input documents significantly changes the output summary, suggesting models lean heavily on positional bias rather than content integration
- **Composition insensitivity**: Adding or removing documents sometimes does not change the summary at all, suggesting the model ignored those documents
- **Proposed fix**: Generate diverse candidate summaries, then select the one best aligned with expected aggregate measures

**Petrarca relevance:** This is a cautionary finding. Simply concatenating 20 articles and asking an LLM to "synthesize" will produce unreliable results. Petrarca should instead: (1) extract claims/facts from each article independently, (2) cluster/align claims across articles, (3) generate synthesis from the structured claim data rather than raw text. This extract-then-synthesize pipeline is more robust than end-to-end synthesis.

### 1.5 Cross-Document Event-Keyed Summarization (CDEKS)

**Paper:** "Cross-Document Event-Keyed Summarization" (2024)
**Link:** https://arxiv.org/abs/2410.14795

Extends event-keyed summarization to the cross-document setting. Given multiple articles about the same event from different sources, produce a summary that synthesizes all accounts.

- **SEAMuS dataset**: High-quality dataset for CDEKS based on expert reannotation of FAMuS (cross-document argument extraction)
- **Event as organizing unit**: Rather than summarizing "all articles," the system summarizes a specific event as described across multiple sources -- a more tractable unit of synthesis
- **Baseline results**: Both fine-tuned smaller models and prompted LLMs (zero/few-shot) were evaluated, with LLMs performing well but not perfectly

**Petrarca relevance:** The "event as organizing unit" concept is powerful. When synthesizing 20 articles about Claude Code, the system should first identify discrete events/developments (e.g., "release of feature X," "benchmark result Y," "user workflow Z") and synthesize each event separately across sources, rather than trying to synthesize everything at once.

### 1.6 Atomic Fact Extraction (FActScore, AFEV)

**Paper:** "Fact in Fragments: Deconstructing Complex Claims via LLM-based Atomic Fact Extraction and Verification" (2025)
**Link:** https://arxiv.org/html/2506.07446v1

The atomic fact decomposition paradigm is critical infrastructure for multi-article synthesis:

- **Atomic facts**: Complex claims are decomposed into minimal, standalone, irreducible propositions (e.g., "Claude Code was released by Anthropic in 2025 and supports autonomous coding" becomes two atomic facts)
- **AFEV framework**: Iteratively decomposes complex claims, enables fine-grained retrieval and verification of each atomic unit
- **Deduplication**: Once claims are decomposed to atomic level, semantic deduplication becomes tractable -- two articles saying the same thing in different words produce matching atomic facts
- **FActScore pipeline**: Atomic fact generation -> evidence retrieval -> fact validation -> score computation

**Petrarca relevance:** Petrarca already extracts `novelty_claims` per article. Taking this to the atomic level enables: (1) deduplication across articles ("articles 1, 4, and 12 all say X"), (2) contradiction detection ("article 3 says X but article 7 says not-X"), (3) coverage analysis ("only article 9 mentions Y"). This is the foundation for the structured comparison matrix recommended in the prior-art document.

### 1.7 Cluster Shapley: Attributing Value in Multi-Document Summaries

**Paper:** "Document Valuation in LLM Summaries: A Cluster Shapley Approach" (2025)
**Link:** https://arxiv.org/html/2505.23842v1

Uses game-theoretic Shapley values to quantify each source document's contribution to a synthesis:

- **Marginal contribution**: Each document's value is its marginal contribution to the summary -- how much information would be lost without it
- **Cluster approximation**: Documents are clustered by semantic similarity, and Shapley values are computed at the cluster level for efficiency
- **Practical attribution**: Can identify which documents are essential vs. redundant in a synthesis

**Petrarca relevance:** Could power a "source importance" ranking in topic syntheses. When showing 20 articles about Claude Code, the system could rank them by contribution: "Articles 2 and 8 are the primary sources; articles 5, 11, 14 are largely redundant with these."

---

## 2. Article Clustering and Subtopic Identification

### 2.1 BERTopic: Embedding-Based Topic Modeling

**Tool:** BERTopic
**Link:** https://bertopic.com/
**Paper:** https://arxiv.org/abs/2203.05794

BERTopic is the current practical standard for document clustering and topic modeling. Its pipeline:

1. **Embed** documents using sentence-transformers (default: `all-MiniLM-L6-v2`)
2. **Reduce dimensionality** with UMAP, preserving semantic structure
3. **Cluster** with HDBSCAN (density-based, handles noise/outliers, no fixed k)
4. **Represent topics** with class-based TF-IDF (c-TF-IDF) -- words important to a cluster vs. the corpus

Key features for Petrarca:
- **Hierarchical topic modeling**: Can produce a topic tree, not just flat clusters
- **Dynamic topic modeling**: Track how topics evolve over time (relevant for "what's new since last week")
- **Online learning**: Update topics incrementally as new articles arrive (no full recomputation)
- **LLM integration**: Can use LLMs to generate human-readable topic labels and descriptions
- **Outlier reduction**: Documents that don't clearly belong to any cluster are flagged rather than forced into one

**Petrarca relevance:** BERTopic is likely the right clustering engine for Petrarca's article grouping. Given 20 articles about Claude Code, BERTopic would identify subtopics like "autonomous coding capabilities," "pricing and availability," "comparison to GitHub Copilot," "user workflow integration." The hierarchical mode could reveal that "pricing" and "enterprise adoption" are sub-clusters of a broader "commercial" cluster. The online learning mode means clusters update naturally as new articles arrive without reprocessing the entire corpus.

### 2.2 Sub-Event Detection in News Streams

**Paper:** "Detection and context reconstruction of sub-events that influence the course of a news event from microblog discussions" (Journal of Computational Social Science, 2024)
**Link:** https://link.springer.com/article/10.1007/s42001-024-00279-2

**Paper:** "Using LLM for Improving Key Event Discovery: Temporal-Guided News Stream Clustering with Event Summaries" (2024)
**Link:** https://openreview.net/forum?id=lojtRAQOls

Sub-event detection addresses a core question: within a cluster of articles about the same broad topic, what are the distinct sub-events or developments?

Key approaches:
- **Temporal clustering**: Articles are grouped not just by content similarity but by temporal proximity -- two articles about Claude Code from the same week likely discuss the same development
- **LLM-generated event summaries**: Use an LLM to summarize each temporal cluster, producing a "key event" description that serves as the cluster label
- **Outlier detection**: Identify articles that discuss genuinely novel sub-events vs. articles that rehash known events
- **Event evolution tracking**: Model how a sub-event develops over time (announcement -> reactions -> analysis -> consequences)

**Petrarca relevance:** Critical for the "what's new since you last looked" feature. When synthesizing 20 Claude Code articles collected over a week, the system should identify: "Days 1-2: Feature X announced (articles 1, 3, 5, 8). Day 3: Benchmark results published (articles 9, 12). Days 4-7: User experience reports (articles 14, 16, 18, 20)." This temporal sub-event structure becomes the navigation skeleton for the synthesis report.

### 2.3 Faceted Summarization

**Paper:** "iFacetSum: Coreference-based Interactive Faceted Summarization for Multi-Document Exploration" (EMNLP 2021)
**Link:** https://arxiv.org/abs/2109.11621
**Code:** https://github.com/BIU-NLP/iFACETSUM

iFacetSum is the most relevant academic system for Petrarca's synthesis UI. Key ideas:

- **Automatic facet generation**: Cross-document coreference pipelines identify recurring concepts, entities, and statements across the document set. These become navigable facets (subtopics)
- **Faceted navigation + summarization**: Clicking a facet generates an abstractive summary of just that facet across all documents -- "show me what all 20 articles say about pricing"
- **Interactive exploration**: Users can combine facets, drill down, or browse the facet hierarchy
- **Coreference-driven**: Facets are discovered through cross-document coreference resolution, ensuring they reflect actual content overlap rather than keyword matching

**Petrarca relevance:** iFacetSum's interaction model is almost exactly what Petrarca needs. The synthesis report for 20 Claude Code articles would present auto-discovered facets (pricing, capabilities, comparisons, limitations, user workflows) as navigable sections, each with its own cross-article summary. Users can drill into any facet to see the contributing passages from each article. The demo at https://nlp.biu.ac.il/~hirsche5/ifacetsum/ shows the interaction pattern.

### 2.4 TOMDS: Topic-Oriented Multi-Document Summarization

**Paper:** "TOMDS: Enabling Personalized Customization of Multi-Document Summaries" (Applied Sciences, 2024)
**Link:** https://www.mdpi.com/2076-3417/14/5/1880

TOMDS lets users specify the topic/angle they want the multi-document summary to focus on:

- **Two-stage pipeline**: (1) Extractive stage retrieves paragraphs relevant to the user's specified topic, sorted by relevance. (2) Abstractive stage generates a summary focused on that topic
- **Discourse parsing**: Analyzes both within-paragraph semantic relationships and inter-paragraph connections
- **Topic-aware attention**: The decoder uses a topic-aware attention mechanism to focus on information relevant to the chosen topic

**Petrarca relevance:** Directly applicable to user-driven synthesis angles. After auto-generating a default synthesis, the user might want to refocus: "Show me only what these 20 articles say about Claude Code's autonomous coding capabilities." TOMDS's approach -- first retrieve relevant paragraphs, then summarize -- is a clean architecture for this. Combined with Petrarca's interest model, the default "topic" could be auto-selected based on the user's interest profile.

### 2.5 Multi-Granularity Extraction

**Paper:** "From coarse to fine: Enhancing multi-document summarization with multi-granularity relationship-based extractor" (Information Processing & Management, 2024)
**Link:** https://www.sciencedirect.com/science/article/abs/pii/S0306457324000566

This approach models documents at multiple granularities simultaneously:

- **Heterogeneous graph**: Nodes represent documents, paragraphs, sentence-sets, and individual sentences. Edges connect across granularities
- **Multi-granularity scoring**: Each node is scored for importance at its own level, then scores propagate across levels
- **Noise and redundancy removal**: Graph pruning removes noisy and redundant content before final sentence selection

**Petrarca relevance:** The multi-granularity graph maps naturally to Petrarca's article structure: articles -> sections -> paragraphs -> claims. The graph can represent "Article 3's section on pricing is highly similar to Article 7's section on costs" as an edge, enabling structured cross-article navigation.

---

## 3. Cross-Document Alignment

### 3.1 QA-Align: Aligning Content Across Documents via Question-Answer Propositions

**Paper:** "QA-Align: Representing Cross-Text Content Overlap by Aligning Question-Answer Propositions" (EMNLP 2021)
**Link:** https://arxiv.org/abs/2109.12655
**Code:** https://github.com/DanielaBWeiss/QA-ALIGN
**Dataset:** https://huggingface.co/datasets/biu-nlp/qa_align

QA-Align proposes a general framework for representing content overlap between documents:

- **QA-SRL decomposition**: Each sentence is decomposed into question-answer pairs that capture predicate-argument relations (e.g., "Who released Claude Code?" -> "Anthropic")
- **Cross-document alignment**: QA pairs from different documents are aligned when they answer the same question with compatible answers
- **Beyond coreference**: QA-Align captures more than entity coreference -- it aligns propositions, arguments, and relationships across documents
- **Content overlap representation**: The alignment graph shows exactly which propositions are shared, which are unique to one document, and where documents provide complementary information

**Petrarca relevance:** This is the technical foundation for the "claim comparison matrix" recommended in the prior-art document. For 20 Claude Code articles, QA-Align would identify: "Q: What language does Claude Code support? Articles 1,3,5 answer Python; Article 8 also mentions JavaScript; Articles 12-20 don't address this." This produces a structured, navigable comparison rather than a flat summary.

### 3.2 Multilevel Text Alignment with Cross-Document Attention

**Paper:** Zhou, Pappas, and Smith, "Multilevel Text Alignment with Cross-Document Attention" (EMNLP 2020)
**Link:** https://arxiv.org/abs/2010.01263
**Code:** https://github.com/XuhuiZhou/CDA

Proposes learning cross-document attention at multiple levels:

- **Document-to-document alignment**: Learns which documents are most related
- **Sentence-to-document alignment**: For any sentence in Document A, identifies which parts of Document B are most relevant
- **Weakly supervised**: Trained from document-pair labels without sentence-level annotation
- **Hierarchical attention encoders**: Extend standard attention with cross-document connections

**Petrarca relevance:** This architecture could power a "related passages" feature in the reader. While reading paragraph 3 of Article 5 about Claude Code's pricing, the system could highlight: "Articles 2 and 11 discuss the same topic in paragraphs 7 and 4 respectively." This enables seamless jumping between articles at the relevant section level, not just article-to-article linking.

### 3.3 Cross-Document Event Coreference Resolution

**Paper:** "Improving cross-document event coreference resolution by discourse coherence and structure" (Information Processing & Management, 2025)
**Link:** https://www.sciencedirect.com/science/article/abs/pii/S0306457325000275

**Paper:** "Synergetic Event Understanding: A Collaborative Approach to Cross-Document Event Coreference Resolution with Large Language Models" (2024)
**Link:** https://arxiv.org/abs/2406.02148

Cross-document event coreference resolution (CD-ECR) determines when different articles are describing the same event:

- **Challenge**: Cross-document event mentions lack the rich connecting context available within a single document
- **Discourse coherence approach**: Selects coherent sentences from across documents to reconstruct a unified narrative, bridging the context gap
- **LLM + small model collaboration**: LLMs summarize events through prompting; smaller fine-tuned models refine event representations based on these summaries
- **Benchmark datasets**: ECB+ (Event Coreference Bank Plus) and GVC (Gun Violence Corpus)

**Petrarca relevance:** Essential for knowing when two articles are discussing the same event vs. different events. Without this, a synthesis of 20 Claude Code articles might conflate an article about Claude Code's v1 release with an article about v2 features, producing an incoherent synthesis.

---

## 4. Diff-Like Reading Interfaces and "What's New" Detection

### 4.1 CiteSee: Personalized Citation Context Based on Reading History

**Paper:** "CiteSee: Augmenting Citations in Scientific Papers with Persistent and Personalized Historical Context" (CHI 2023, Best Paper Award)
**Link:** https://arxiv.org/abs/2302.07302
**Live:** https://openreader.semanticscholar.org/CiteSee

CiteSee is the closest existing system to Petrarca's "what's new to me" vision:

- **Reading history tracking**: Maintains a persistent record of which papers the user has opened, saved, and cited
- **Visual augmentation**: Inline citations are color-coded based on familiarity:
  - Green = previously opened
  - Red = saved to library
  - Yellow shades = cited by papers in reading history (familiar but not directly read)
  - Uncolored = novel/unknown
- **Personalized context**: When hovering over a citation, shows WHY the cited paper is familiar (e.g., "cited in Paper X that you read last week")
- **Study results**: Significantly more effective for paper discovery than baselines; helps users maintain situational awareness across reading sessions

**Petrarca relevance:** CiteSee's design philosophy is exactly right for Petrarca. In a synthesis report of 20 Claude Code articles, claims and sources should be visually coded by familiarity: claims the user has already encountered (from articles they've read) should be visually de-emphasized, while genuinely novel claims should stand out. The color-coding scheme (green = known, rubric/red = saved, unmarked = novel) fits Petrarca's existing design system. The "here's why this is familiar" hover context is a powerful trust-building pattern.

### 4.2 The Semantic Reader Project

**Paper:** "The Semantic Reader Project: Augmenting Scholarly Documents through AI-Powered Interactive Reading Interfaces" (Communications of the ACM, 2024)
**Link:** https://arxiv.org/abs/2303.14334
**Open platform:** https://openreader.semanticscholar.org/

An umbrella project from AI2/UW/Berkeley that explores augmented reading interfaces:

- **AI-generated highlights**: Key sentences are marked with category labels (Goal, Method, Result), with adjustable quantity and opacity
- **Inline reference cards**: Hovering over a citation shows a popup with TLDR, context, and relevance explanation
- **PaperMage**: Open-source library for processing and analyzing scholarly PDFs -- extracts structure, entities, references
- **PaperCraft**: React UI component library for building augmented reading interfaces

**Petrarca relevance:** PaperCraft's React components could be adapted for Petrarca's reader. The highlight categorization (Goal/Method/Result) could translate to (New Claim/Known Claim/Disputed Claim). The open-source nature means the UI patterns are available for adaptation. The overall philosophy -- "augment the document, don't replace it" -- aligns with Petrarca's approach.

### 4.3 NewsDiffs and DiffEngine: Version Tracking for News

**NewsDiffs:** https://github.com/ecprice/newsdiffs (http://newsdiffs.org/)
**DiffEngine:** https://github.com/DocNow/diffengine

These tools track how individual news articles change over time:

- **NewsDiffs**: Scrapes NYT, CNN, WaPo, Politico, BBC front pages. When articles change, stores both versions and generates a diff view
- **DiffEngine**: Works with any RSS feed. Archives snapshots at the Internet Archive. Generates diffs. Can tweet changes. Uses SQLite for version history
- **Limitation**: Both track changes to individual articles, not changes across a topic's coverage

**Petrarca relevance:** The concept is relevant but needs inversion. Instead of "how has this one article changed?" Petrarca needs "how has coverage of this topic changed since I last looked?" This requires: (1) timestamp-aware synthesis ("new since March 5"), (2) claim-level diffing ("these 3 claims are new since your last session"), (3) article-level freshness indicators.

### 4.4 Progressive Summarization (Tiago Forte)

**Source:** Forte Labs, "Progressive Summarization: A Practical Technique for Designing Discoverable Notes"
**Link:** https://fortelabs.com/blog/progressive-summarization-a-practical-technique-for-designing-discoverable-notes/

While not an academic system, Progressive Summarization articulates a widely-adopted design pattern:

- **Layer 1**: Full captured text
- **Layer 2**: Bold the main points (10-20% of layer 1)
- **Layer 3**: Highlight the boldest points (10-20% of layer 2)
- **Layer 4**: Executive summary in your own words
- Each layer preserves the context of the previous layer, enabling drill-down

**Petrarca relevance:** This layered approach maps directly to Petrarca's synthesis UI. A topic report could present:
- **Layer 4** (executive summary): "Here's the one-paragraph synthesis of 20 Claude Code articles"
- **Layer 3** (key claims): "These 8 claims are the most important, with novelty and agreement indicators"
- **Layer 2** (full claim set): "All 47 extracted claims across articles, grouped by subtopic"
- **Layer 1** (source passages): "Tap any claim to see the original passage from the source article"

The critical insight is that each layer is always accessible -- the user chooses their depth, and can move between layers fluidly.

---

## 5. GraphRAG and Knowledge Graph Approaches

### 5.1 Microsoft GraphRAG

**Paper:** "From Local to Global: A Graph RAG Approach to Query-Focused Summarization" (2024)
**Link:** https://arxiv.org/abs/2404.16130
**Code:** https://microsoft.github.io/graphrag/

GraphRAG represents the state-of-the-art for structured synthesis from a document corpus:

**Pipeline (5 phases):**
1. **Text chunking**: Source documents are split into manageable text units
2. **Entity & relationship extraction**: An LLM extracts named entities and relationships, building a knowledge graph
3. **Community detection**: The Leiden algorithm identifies hierarchical communities of densely connected entities
4. **Community summarization**: Each community (at each hierarchy level) gets an LLM-generated summary
5. **Query answering**: For global questions, community summaries are aggregated. For local questions, entity-specific subgraphs are used

**Key innovation -- hierarchical communities:**
- The knowledge graph is partitioned at multiple levels (like a zoom lens)
- High-level communities capture broad themes ("AI coding tools")
- Low-level communities capture specific details ("Claude Code v2 pricing for enterprise")
- Queries can be answered at the appropriate level of specificity

**Query modes:**
- **Global Search**: Answers questions about the entire corpus using community summaries (e.g., "What are the main themes across these 20 articles?")
- **Local Search**: Answers questions about specific entities using entity neighborhoods (e.g., "What do articles say about Anthropic's pricing?")
- **DRIFT Search**: Combines entity-specific queries with community context for nuanced answers

**Petrarca relevance:** GraphRAG's architecture maps remarkably well to Petrarca's synthesis needs:
- Entities extracted from 20 articles (Claude Code, Anthropic, VS Code, autonomous coding, pricing tiers...) form a knowledge graph
- Community detection reveals subtopic clusters without manual specification
- Hierarchical summaries provide the "adjustable depth" that users want
- The system can answer both broad ("what are the main themes?") and specific ("what about pricing?") queries

The main concern is computational cost -- building a full GraphRAG index for 20 articles requires many LLM calls. However, since Petrarca's pipeline already extracts claims and topics, much of the entity extraction is already done. A lightweight GraphRAG that leverages existing pipeline outputs could be feasible.

### 5.2 Stanford STORM

**Paper:** "Assisting in Writing Wikipedia-like Articles From Scratch with Large Language Models" (2024)
**Link:** https://arxiv.org/abs/2402.14207
**Code:** https://github.com/stanford-oval/storm
**Live demo:** https://storm.genie.stanford.edu/

STORM generates full Wikipedia-style articles with citations by simulating a multi-perspective research process:

- **Perspective discovery**: Identifies diverse perspectives/angles on a topic
- **Simulated conversations**: Generates conversations between "experts" carrying different perspectives, with questions grounded in source material
- **Outline generation**: Curates collected information into a structured outline
- **Article generation**: Produces a full article following the outline, with inline citations
- **Citation quality**: Achieves 84.83% citation recall and 85.18% citation precision

**Petrarca relevance:** STORM's multi-perspective simulation could drive Petrarca's synthesis. Instead of a single summary, the system simulates perspectives relevant to the user's interests: "As someone interested in developer productivity, how does Claude Code compare?" + "From a cost perspective, how do the pricing models work?" + "For someone who already knows GitHub Copilot, what's genuinely different?" The outline-first approach ensures structural coherence.

---

## 6. Practical Implementations and Tools

### 6.1 auto-news: Personal LLM News Aggregator

**Link:** https://github.com/finaldie/auto-news
**Blog:** https://finaldie.com/blog/auto-news-an-automated-news-aggregator-with-llm/

An open-source personal news aggregator using LangChain with ChatGPT/Gemini/Ollama:

- Sources: RSS, Tweets, YouTube, Reddit, Web Articles, personal journal notes
- Filters content based on personal interests (removes 80%+ noise)
- Generates weekly top-k recaps
- Can deliver to Notion or RSS reader-style UI

**Petrarca relevance:** Closest open-source analog to Petrarca's pipeline. Worth studying the codebase for patterns around multi-source aggregation and LLM-based filtering. However, it does single-article summarization, not cross-article synthesis.

### 6.2 NewsGPT (Neotice)

**Link:** https://www.llamaindex.ai/blog/newsgpt-neotice-summarize-news-articles-with-llamaindex-hackathon-winning-app

A hackathon-winning app built with LlamaIndex that:
- Collates 3-5 articles from different sources about the same news story
- Generates a unified summary
- Identifies and highlights *discrepancies* between sources
- Helps readers identify which information can be trusted by comparing sources

**Petrarca relevance:** The discrepancy detection feature is particularly interesting. When synthesizing 20 Claude Code articles, identifying where sources disagree ("Article 3 claims free tier; Article 12 says enterprise-only") is more valuable than consensus.

### 6.3 Google NotebookLM Architecture

**Link:** https://notebooklm.google/
**Analysis:** https://medium.com/@jimmisound/the-cognitive-engine-a-comprehensive-analysis-of-notebooklms-evolution-2023-2026-90b7a7c2df36

NotebookLM's core architectural principle:

- **Source-grounding constraint**: The model is constrained to ONLY use information from user-provided sources. No external knowledge, no hallucination from training data
- **1M+ token context**: Gemini 1.5/2.0 can ingest up to 50 sources simultaneously
- **Multi-modal synthesis**: Text, audio (podcast-style "Audio Overviews"), structured data tables, mind maps
- **Inline citations**: Generated text links back to specific source passages
- **Limitations discovered by users**: Citation depth is shallow ("Source 3" not "Source 3, paragraph 7"); early sources get de-prioritized as context fills; accuracy degrades near the 50-source limit

**Petrarca relevance:** Source-grounding is essential -- Petrarca's synthesis should never introduce claims not present in the user's articles. The citation depth problem is solvable: since Petrarca controls the pipeline, citations can reference specific claims/paragraphs. The context window limitation is relevant: 20 full articles may exceed context limits, necessitating the extract-then-synthesize approach rather than stuff-all-text-in-context.

### 6.4 Perplexity's Multi-Source Synthesis

**Link:** https://www.perplexity.ai/hub/blog/introducing-perplexity-deep-research

Perplexity's synthesis pipeline:
1. Interpret query intent and context
2. Conduct parallel web searches
3. Evaluate and rank sources (relevance, freshness, authority, structure)
4. Synthesize from top sources with inline numbered citations
5. For Deep Research: iterative analysis cycles, dozens of searches, hundreds of sources, 2-4 minute comprehensive reports

**Petrarca relevance:** The numbered citation system and the source evaluation pipeline are worth emulating. Petrarca has an advantage: sources are already curated by the user, so the evaluation step can focus on relevance to the specific synthesis query rather than general authority.

### 6.5 Elicit's Structured Matrix

**Link:** https://elicit.com/
**Evaluation:** https://onlinelibrary.wiley.com/doi/full/10.1002/cesm.70050

Elicit's most innovative contribution is the structured extraction matrix:
- Users define columns/dimensions (sample size, methodology, findings, conclusion)
- The system extracts answers from each paper for each dimension
- Every extracted answer is linked to a supporting quote
- Reports synthesize across the matrix with frequency counts and methodology sections
- 94-99% accuracy on data extraction tasks

**Petrarca relevance:** The matrix UI is the most promising pattern for Petrarca's synthesis view. For 20 Claude Code articles, auto-generated dimensions might include: "Features discussed," "Pricing mentioned," "Comparison targets," "User sentiment," "Technical details." Each cell in the matrix is an extracted fact with a source link. The matrix is the intermediate representation; narrative synthesis can be generated from it.

### 6.6 Particle News Processing Pipeline

**Link:** https://techcrunch.com/2024/11/12/particle-launches-an-ai-news-app-to-help-publishers-instead-of-just-stealing-their-work/

Particle's documented pipeline for multi-article synthesis:
1. Cluster related articles about the same event/story
2. Process cluster through AI pipeline: extract bullet points, headline, sub-headline, quotes, links
3. Post-process: AI must find supporting material for every claim in the summary
4. Quality control: human + automated oversight, "reality checks" verify faithfulness to sources
5. Multi-perspective: "Opposite Sides" shows how different-leaning outlets cover the same story
6. Error reduction: Detects AI problems occurring 1/100 times and reduces to 1/10,000

**Petrarca relevance:** The post-processing verification step (AI must cite supporting evidence for every claim) is a strong quality pattern. The Opposite Sides feature could inspire a "different angles" view for Petrarca's synthesis.

---

## 7. Proposed Architecture for Petrarca Topic Synthesis

Based on all the research above, here is a recommended technical architecture:

### 7.1 Pipeline: Extract -> Cluster -> Align -> Synthesize -> Present

```
PHASE 1: EXTRACTION (already partially done)
  For each article in topic cluster:
    - Extract atomic claims (extend existing novelty_claims)
    - Extract entities and relationships
    - Extract temporal markers (when events occurred)
    - Tag claims with subtopic facets

PHASE 2: CLUSTERING & ALIGNMENT
  - Cluster articles by sub-event/subtopic (BERTopic or embedding + HDBSCAN)
  - Within each cluster, align claims across articles (QA-Align style)
  - Identify: shared claims, unique claims, contradictory claims
  - Deduplicate: merge semantically identical claims, keep source attribution

PHASE 3: SYNTHESIS GENERATION
  For each subtopic cluster:
    - Generate abstractive summary from aligned claims (not raw text)
    - Attach inline citations [Article N, claim M]
    - Mark agreement/disagreement/uniqueness per claim
    - Identify coverage gaps (subtopics mentioned in few articles)

PHASE 4: KNOWLEDGE-AWARE FILTERING
  Using Petrarca's interest model:
    - Score each claim against user's known topics
    - Mark claims as: NEW (high novelty), KNOWN (already encountered),
      DEEPENING (extends known topic)
    - Prioritize NEW and DEEPENING in the synthesis view
    - Collapse/dim KNOWN content (still accessible, not hidden)

PHASE 5: PRESENTATION
  Render as navigable report with:
    - Executive summary (Layer 4 / progressive summarization)
    - Subtopic navigation (iFacetSum-style facets)
    - Claim-level detail with novelty/agreement indicators
    - Source passage drill-down (tap any claim -> see original text)
    - Temporal view (when did each development occur?)
```

### 7.2 LLM Call Strategy

Given that Petrarca uses Gemini Flash for its pipeline:

- **Extraction** (Phase 1): One Gemini call per article (already happening for novelty_claims)
- **Alignment** (Phase 2): Embedding-based, no LLM calls needed -- use sentence-transformers for claim similarity
- **Synthesis** (Phase 3): One Gemini call per subtopic cluster (typically 3-7 clusters per topic)
- **Filtering** (Phase 4): Purely algorithmic, no LLM needed -- compare claim embeddings against interest model

Total additional LLM calls per synthesis: ~5-10 Gemini Flash calls. At current pricing, this is negligible.

### 7.3 Key Technical Decisions

1. **Extract-then-synthesize vs. stuff-and-summarize**: The research strongly favors extraction first. Stuffing 20 full articles into context produces unreliable synthesis (per the "Do MDS Models Synthesize?" findings). Extracting structured claims first, then synthesizing from claims, is more robust.

2. **Faceted navigation vs. linear report**: iFacetSum's faceted navigation is superior to a linear report for 20+ articles. Users can enter at any subtopic and drill down.

3. **Claim-level attribution vs. article-level**: WebCiteS shows that claim-level attribution (with sub-claim decomposition) is feasible and necessary. Article-level attribution ("Source 3") is insufficient for trust.

4. **Progressive disclosure layers**: Forte's progressive summarization maps perfectly to Petrarca's depth navigator (Summary / Claims / Sections / Full).

5. **Temporal organization**: Sub-event detection (section 2.2) should organize the synthesis chronologically as a primary navigation axis, alongside thematic facets.

---

## Sources

### Multi-Document Summarization & Attribution
- [PRIMERA: Pyramid-based Masked Sentence Pre-training](https://arxiv.org/abs/2110.08499)
- [WebCiteS: Attributed Query-Focused Summarization (ACL 2024)](https://aclanthology.org/2024.acl-long.806/)
- [Do Multi-Document Summarization Models Synthesize? (TACL 2024)](https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00687/124262/)
- [Cross-Document Event-Keyed Summarization](https://arxiv.org/abs/2410.14795)
- [Multi-LLM Text Summarization](https://arxiv.org/abs/2412.15487)
- [Cluster Shapley: Document Valuation in LLM Summaries](https://arxiv.org/html/2505.23842v1)
- [Incentive-Aligned Multi-Source LLM Summaries](https://arxiv.org/pdf/2509.25184)
- [Atomic Fact Extraction and Verification (AFEV)](https://arxiv.org/html/2506.07446v1)
- [FActScore: Fine-grained Atomic Evaluation of Factual Precision](https://www.emergentmind.com/topics/factscore)

### Article Clustering & Subtopic Detection
- [BERTopic: Neural Topic Modeling](https://arxiv.org/abs/2203.05794) / [bertopic.com](https://bertopic.com/)
- [iFacetSum: Interactive Faceted Summarization (EMNLP 2021)](https://arxiv.org/abs/2109.11621)
- [TOMDS: Topic-Oriented Multi-Document Summarization (2024)](https://www.mdpi.com/2076-3417/14/5/1880)
- [Multi-Granularity Relationship-based Extractor (2024)](https://www.sciencedirect.com/science/article/abs/pii/S0306457324000566)
- [LLM for Temporal-Guided News Stream Clustering](https://openreview.net/forum?id=lojtRAQOls)
- [Sub-event Detection in Microblog Discussions (2024)](https://link.springer.com/article/10.1007/s42001-024-00279-2)
- [LimTopic: LLM-based Topic Modeling (2024)](https://arxiv.org/abs/2503.10658)
- [Google News Clustering Algorithm](https://searchengineland.com/google-news-ranking-stories-30424)
- [News Article Clustering Technical Deep Dive](https://dev.to/mayankcse/clustering-news-articles-for-topic-detection-a-technical-deep-dive-2692)

### Cross-Document Alignment
- [QA-Align: Cross-Text Content Overlap (EMNLP 2021)](https://arxiv.org/abs/2109.12655)
- [Multilevel Text Alignment with Cross-Document Attention (EMNLP 2020)](https://arxiv.org/abs/2010.01263)
- [Cross-Document Event Coreference via Discourse Coherence (2025)](https://www.sciencedirect.com/science/article/abs/pii/S0306457325000275)
- [Synergetic Cross-Document Event Coreference with LLMs (2024)](https://arxiv.org/abs/2406.02148)
- [Cross-Document Contextual Coreference in Knowledge Graphs (2025)](https://arxiv.org/abs/2504.05767)
- [Multi-Document Event Relation Graph Reasoning (2025)](https://arxiv.org/html/2506.12978)

### Diff-Like Reading Interfaces
- [CiteSee: Personalized Citation Context (CHI 2023, Best Paper)](https://arxiv.org/abs/2302.07302)
- [Semantic Reader Project (CACM 2024)](https://arxiv.org/abs/2303.14334)
- [Semantic Reader Open Platform](https://openreader.semanticscholar.org/)
- [NewsDiffs (GitHub)](https://github.com/ecprice/newsdiffs)
- [DiffEngine: RSS Feed Change Tracking](https://github.com/DocNow/diffengine)
- [Progressive Summarization (Forte Labs)](https://fortelabs.com/blog/progressive-summarization-a-practical-technique-for-designing-discoverable-notes/)

### Knowledge Graph & RAG Approaches
- [GraphRAG: Graph-Based Query-Focused Summarization (2024)](https://arxiv.org/abs/2404.16130) / [microsoft.github.io/graphrag](https://microsoft.github.io/graphrag/)
- [STORM: Wikipedia-style Article Generation (Stanford, 2024)](https://arxiv.org/abs/2402.14207) / [GitHub](https://github.com/stanford-oval/storm)

### Practical Tools & Products
- [auto-news: LLM News Aggregator (GitHub)](https://github.com/finaldie/auto-news)
- [NewsGPT/Neotice: Multi-Source Discrepancy Detection](https://www.llamaindex.ai/blog/newsgpt-neotice-summarize-news-articles-with-llamaindex-hackathon-winning-app)
- [Particle News Pipeline (TechCrunch)](https://techcrunch.com/2024/11/12/particle-launches-an-ai-news-app-to-help-publishers-instead-of-just-stealing-their-work/)
- [Perplexity Deep Research](https://www.perplexity.ai/hub/blog/introducing-perplexity-deep-research)
- [NotebookLM Architecture Analysis](https://medium.com/@jimmisound/the-cognitive-engine-a-comprehensive-analysis-of-notebooklms-evolution-2023-2026-90b7a7c2df36)
- [Consensus.app: How It Works](https://consensus.app/home/blog/how-consensus-works/)
- [Elicit: AI for Systematic Review](https://elicit.com/)
- [Fabric: Prompt Pattern Framework (GitHub)](https://github.com/danielmiessler/Fabric)
