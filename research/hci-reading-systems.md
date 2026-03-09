# HCI and Information Science Research: Reading Systems, Knowledge Modeling, and Sensemaking

A comprehensive survey of CHI, CSCW, UIST, IUI, SIGIR, and related conference research relevant to Petrarca's core goals: knowledge-aware reading, claim extraction, personalized novelty detection, topic granularity, incremental reading, implicit feedback signals, and cross-article synthesis.

*Complements `knowledge-modeling.md` (tools/algorithms focus) with an HCI/research systems perspective.*

*Last updated: 2026-03-07*

---

## 1. Knowledge-Aware Reading Tools

### The Semantic Reader Project (Allen AI)

The most significant body of work on augmented reading interfaces comes from the Semantic Reader Project at Allen AI, a multi-institution collaboration that has produced over a dozen reading interface prototypes.

**ScholarPhi** (CHI 2021) -- Head, Lo, et al. Augments scientific papers with just-in-time, position-sensitive definitions of terms and symbols. When a reader clicks a technical term, a tooltip shows the relevant definition from elsewhere in the paper. Key features: (1) position-sensitive tooltips, (2) a "declutter filter" that reveals how a term is used across the paper, (3) automatic equation diagrams, (4) auto-generated glossary. A lab study showed scholars answered questions in significantly less time while viewing less of the paper.
- Paper: https://dl.acm.org/doi/fullHtml/10.1145/3411764.3445648
- GitHub: https://github.com/allenai/scholarphi
- **Petrarca relevance**: The core pattern -- overlaying contextual intelligence on reading -- is exactly what Petrarca does with novelty claims. ScholarPhi's specific technique (tooltips for definitions) could inform how Petrarca presents "you already know this" annotations inline.

**CiteRead** (IUI 2022) -- Rachatasumrit, Bragg, Zhang, Weld. Integrates localized citation contexts into paper reading. When reading a paper, CiteRead shows how subsequent papers have discussed, extended, or contradicted specific passages. Citation contexts appear as marginal notes, localized to relevant sections. A user study with 12 scientists showed better comprehension and retention of follow-on work compared to a simple list of citing papers.
- Paper: https://dl.acm.org/doi/10.1145/3490099.3511162
- **Petrarca relevance**: The marginal note pattern for cross-document context is directly applicable. When a user reads an article that connects to previously read articles, Petrarca could show marginal annotations like "relates to [claim from article X]" or "contradicts what you read in [article Y]."

**Papeos** (UIST 2023) -- Augments papers by segmenting and localizing talk video clips alongside relevant paper passages. Readers can visually skim through clip thumbnails and fluidly switch between dense text and visual summaries. A study (n=16) found Papeos reduced mental load and scaffolded navigation.
- **Petrarca relevance**: The multi-modal progressive disclosure pattern. Petrarca's depth navigator (Summary / Claims / Sections / Full) follows a similar philosophy -- let users choose their engagement level.

**Semantic Reader Open Research Platform** (UIST 2023) -- Open-sourced the NLP toolkits and React UI libraries behind these prototypes:
- **PaperMage** (EMNLP 2023): Unified Python toolkit for processing scholarly PDFs. Extracts document structure, figures, tables, references as annotated layers. Powers Semantic Scholar's production system for millions of PDFs.
  - GitHub: https://github.com/allenai/papermage
- **PaperCraft**: React UI component library for building augmented reading interfaces.
  - GitHub: https://openreader.semanticscholar.org/

**Lumi** (Google PAIR) -- AI-augmented reading prototype for arXiv papers. Highlights main points directly, generates collapsible one-line section summaries in the side margin, supports select-and-ask Q&A tied to specific selections. Designed by Ellen Jiang, Vivian Tsai, and Nada Hussein.
- Website: https://lumi.withgoogle.com/
- GitHub: https://github.com/PAIR-code/lumi
- **Petrarca relevance**: Lumi's approach to inline, non-disruptive AI augmentation is a good model. Its one-line summaries in the table of contents enable rapid navigation, similar to Petrarca's section-level depth navigator.

### Key Patterns for Petrarca

1. **Position-sensitive overlays**: Don't put intelligence in a separate panel -- overlay it directly on the text at the point of relevance (ScholarPhi, CiteRead).
2. **Progressive disclosure of intelligence**: Let users control how much AI augmentation they see (Papeos depth, Lumi collapsible summaries).
3. **Marginal annotations over inline modifications**: Show knowledge-aware information in margins rather than modifying the text itself (CiteRead's marginal notes).
4. **Cross-document context at point of reading**: When reading passage X, show relevant connections to previously encountered passages Y and Z (CiteRead's localized citation contexts).

---

## 2. Claim/Insight Extraction from Text

### Argument Mining Research

**Large Language Models in Argument Mining: A Survey** (2025) -- Comprehensive survey covering how LLMs have reshaped argument mining. Canonical subtasks include claim detection, evidence detection, relation prediction, stance classification, argument quality assessment, and argumentative summarization. LLMs now outperform traditional NLP models on most subtasks.
- Paper: https://arxiv.org/abs/2506.16383

**ClaimDistiller** (EEKE 2023) -- Scientific claim extraction using supervised contrastive learning. Achieved F1 of 87.45%, improving state-of-the-art by 7%+. Key finding: contrastive learning requires significantly less training data than transfer learning (6K sentences vs. 2M for pre-training).
- Paper: https://ceur-ws.org/Vol-3451/paper11.pdf
- **Petrarca relevance**: Validates that claim extraction from articles is a tractable NLP task. For Petrarca, LLM-based extraction (Gemini Flash) is the practical choice, but ClaimDistiller's schema of what constitutes a "claim" is instructive.

**Discourse Annotation and Rhetorical Moves** -- Scientific text follows predictable rhetorical patterns. The Argumentative Zoning framework defines four categories: Claim, Method, Result, Conclusion. The SciAnnotDoc model identifies discourse types (hypothesis, definition, result, method) automatically. Key insight: reasoning about problems, research tasks, and solutions follows patterns that can be detected through explicit linguistic markers.
- Teufel & Moens: https://aclanthology.org/D14-1006.pdf
- **Petrarca relevance**: Petrarca's claim extraction could benefit from discourse-aware prompting. Instead of asking "what are the claims?", ask "what are the findings (results), what are the arguments (claims), and what are the methods?" This produces better-structured output for different reading depths.

**Structured Information Extraction with LLMs** (Nature Communications 2024) -- Demonstrated that fine-tuned LLMs can extract complex structured knowledge from scientific text as validated JSON objects. Tasks ranged from linking dopants to host materials, to cataloging metal-organic frameworks.
- Paper: https://www.nature.com/articles/s41467-024-45563-x
- **Petrarca relevance**: Confirms the approach of using LLMs with structured output schemas for claim/topic extraction. The key is careful schema design (already noted in knowledge-modeling.md).

### Practical Tools

**Elicit** -- AI research assistant that extracts claims with sentence-level citations from academic papers. Creates structured comparison tables across papers. Reports 99.4% accuracy on data extraction in some evaluations, though independent research suggests it complements rather than replaces human extraction.
- Website: https://elicit.com/
- **Petrarca relevance**: Elicit's "research matrix" pattern (extracting parallel structured fields from multiple articles) is directly applicable to cross-article claim comparison in Petrarca.

**Scite** -- Smart citation index that classifies citation intent as supporting, contrasting, or mentioning. Has indexed 1.6B+ citations. When viewing a paper, you can see how many subsequent papers support vs. contradict its claims. Users can set alerts for when relied-upon papers receive new contrasting citations.
- Paper: https://direct.mit.edu/qss/article/2/3/882/102990/
- Website: https://scite.ai/
- **Petrarca relevance**: The supporting/contrasting classification is directly relevant to cross-article knowledge synthesis. If Petrarca tracks claims across articles, it could surface contradictions: "Article A said X, but Article B says the opposite."

**Scholarcy** -- Generates structured "flashcard" summaries from papers: key findings, methodology, limitations, citations. Trained to identify these elements regardless of paper length.
- Website: https://www.scholarcy.com/

### Design Patterns for Petrarca

1. **Typed claims**: Don't extract generic "claims" -- classify them as factual, causal, evaluative, methodological, or predictive (already in knowledge-modeling.md recommendations).
2. **Source-grounded claims**: Every extracted claim should point back to the source passage (Elicit's sentence-level citations).
3. **Cross-article claim linking**: Track claims across articles and surface agreements/contradictions (Scite's supporting/contrasting pattern).

---

## 3. Novelty Detection for Individual Users

### The Core Problem

No existing consumer tool models what a user knows and uses that to score incoming content for novelty. The closest analogues come from three research areas: recommendation system "beyond accuracy" metrics, educational knowledge tracing, and curiosity modeling.

### Recommendation Systems: Beyond Accuracy

**"Diversity, Serendipity, Novelty, and Coverage"** (Kaminskas & Bridge, ACM TIIS 2017) -- The definitive survey on beyond-accuracy objectives in recommender systems. Defines novelty as "how different items are from what the user has seen before" (user-dependent). Serendipity requires both unexpectedness AND relevance. Key finding: most evaluation metrics have not considered individual user differences in capacity to experience beyond-accuracy items.
- Paper: https://dl.acm.org/doi/10.1145/2926720

**Modeling Users' Curiosity** (ACM TKDD 2023) -- Proposes using curiosity traits to capture individual user differences. Models an individual's curiosity distribution over different stimulus levels, using the Wundt curve from psychology. Open-minded users embrace a wider range of novelty than conservative users. Uses Information Theory metrics to operationalize curiosity stimulation.
- Paper: https://dl.acm.org/doi/10.1145/3617598
- **Petrarca relevance**: The Wundt curve concept maps to Petrarca's interest model. Each user has a "curiosity zone" -- too familiar is boring, too foreign is overwhelming. The optimal article is in the sweet spot.

**Enhancing Serendipity with Dynamic User Knowledge Graphs** (2025) -- Proposes using LLMs to construct dynamic user knowledge graphs, introducing external knowledge and interventions to disrupt filter bubbles.
- Paper: https://arxiv.org/html/2508.04032v1
- **Petrarca relevance**: The idea of maintaining a dynamic knowledge graph (not just a preference profile) per user is exactly Petrarca's ambition. The LLM-constructed graph addresses the cold start problem.

**Personalized News Recommendation with Novelty** (Mobile Networks 2017) -- Automatic novelty detection in personalized news recommendation improves reader experience by filtering out information the reader already knows. Uses rough set theory combined with collaborative filtering.
- Paper: https://link.springer.com/article/10.1007/s11036-017-0842-9

### Educational Knowledge Tracing

**Bayesian Knowledge Tracing (BKT)** (Corbett & Anderson, 1995) -- The foundational algorithm for modeling learner knowledge state. Models knowledge as a hidden Markov process with binary states (mastered/not mastered) per skill. Updates beliefs as the learner responds to problems.
- Wikipedia: https://en.wikipedia.org/wiki/Bayesian_Knowledge_Tracing
- **Petrarca relevance**: BKT's per-topic binary state (known/unknown) is a starting point, but Petrarca needs gradations: unknown, encountered, familiar, confident. The Bayesian update mechanism (prior * evidence = posterior) is directly applicable to updating topic knowledge based on reading interactions.

**Deep Knowledge Tracing** (Piech et al., Stanford, 2015) -- Uses RNNs to model knowledge trajectories. Captures temporal patterns in learning better than BKT. Dominant on large datasets.
- Paper: https://stanford.edu/~cpiech/bio/papers/deepKnowledgeTracing.pdf
- **Petrarca relevance**: Overkill for a single user, but the core insight is valuable: knowledge state evolves non-linearly and depends on the sequence of experiences, not just their sum.

**Knowledge Graph + Reinforcement Learning for Learning Paths** (2025) -- Fuses direct feedback, graph propagation, and forgetting to maintain real-time mastery states. Uses exponential forgetting mechanisms.
- Paper: https://www.nature.com/articles/s41598-025-17918-x
- **Petrarca relevance**: The combination of explicit signals (user feedback) with implicit propagation (if you know topic A and B, you probably know their intersection) is directly applicable.

### Open Question for Petrarca

The fundamental challenge: knowledge tracing works well in educational settings where you can test the learner. In a reading app, you can't quiz the user. Instead, Petrarca must infer knowledge from reading behavior: what they mark as "knew this" on claims, how much time they spend, which topics they engage with, what they skip. This is a much noisier signal than quiz responses.

---

## 4. Topic Modeling at the Right Granularity

### The Granularity Problem

"AI" is too broad to be useful. "GPT-4o's context window size for JSON-mode structured output" is too specific. The challenge is finding the right level of specificity for each user's needs, which changes over time and across domains.

### Hierarchical Topic Models

**HyHTM: Hyperbolic Geometry-based Hierarchical Topic Model** (ACL Findings 2023) -- Addresses the fundamental problem that traditional hierarchical topic models produce hierarchies where lower-level topics are unrelated and not specific enough to their parent topics. HyHTM uses hyperbolic geometry to produce coherent hierarchies that genuinely specialize in granularity from generic to specific.
- Paper: https://arxiv.org/abs/2305.09258
- **Petrarca relevance**: Validates the importance of genuine hierarchical specialization. Petrarca's topic hierarchy should ensure that child topics (e.g., "attention mechanisms") are genuinely more specific than parents (e.g., "transformer architecture"), not just different.

**On the Affinity, Rationality, and Diversity of Hierarchical Topic Modeling** (AAAI 2024) -- Identifies "rationality" as a key problem in hierarchical models: child topics often have the same granularity as parents instead of being more specific. Proposes contextual topical bias to separate semantic granularity levels.
- Paper: https://arxiv.org/html/2401.14113
- **Petrarca relevance**: The "rationality" metric could be used to evaluate Petrarca's LLM-extracted topic hierarchy quality.

**TopicGPT** (NAACL 2024) -- Uses LLM prompting for topic modeling. Iteratively generates topics from document samples, refining against previously generated topics. Produces natural language topic labels and descriptions, not just keyword bags. Achieves 0.74 harmonic mean purity against human categorizations vs. 0.64 for the strongest baseline. Highly adaptable: users can specify constraints and modify topics without retraining.
- Paper: https://arxiv.org/abs/2311.01449
- GitHub: https://github.com/chtmp223/topicGPT
- **Petrarca relevance**: TopicGPT's iterative refinement loop is a good model for Petrarca's evolving topic hierarchy. As more articles arrive, the topic space can be refined and reorganized by re-prompting the LLM with the current topic set plus new documents.

**Expert-in-the-Loop Hierarchical Topic Models** (2025) -- Enables domain experts to refine topic hierarchies by selecting subtopics for further partitioning. Addresses the limitation of flat models by offering analysis at different granularity levels.
- Paper: https://www.sciencedirect.com/science/article/pii/S0952197625015106
- **Petrarca relevance**: The expert-in-the-loop pattern maps to Petrarca's user feedback. When a user gives +/- feedback on topic chips, they're acting as the expert guiding topic refinement.

### BERTopic's Hierarchical Topics

**BERTopic** (2022) -- The leading open-source topic modeling library. Uses ward linkage on c-TF-IDF topic-term matrix for hierarchical clustering. Smaller distances between c-TF-IDF representations indicate more similar topics. Supports interactive visualization of topic hierarchies.
- Paper: https://arxiv.org/abs/2203.05794
- GitHub: https://github.com/MaartenGr/BERTopic
- **Petrarca relevance**: BERTopic's hierarchical visualization could inform how Petrarca's Topics tab presents the user's topic space. The ability to zoom in/out of the hierarchy maps to the user's need to see both broad interest areas and specific sub-topics.

### Formal Concept Analysis

**Concept Lattices and Faceted Classification** -- Formal Concept Analysis (FCA) formalizes the notions of extension (objects) and intension (attributes) into algebraic structures called concept lattices. These have been applied to information retrieval for progressive exploration of similar objects and their shared attributes. A 2022 paper proposes dynamically constructing topic hierarchies from fine-grained to coarse-grained based on user queries.
- Paper: https://link.springer.com/article/10.1007/s11042-022-13640-2
- **Petrarca relevance**: The dynamic construction principle is key -- the topic hierarchy should emerge from the user's actual reading and interests, not from a static ontology. FCA's formal structure (objects = articles, attributes = topics) could underpin a principled hierarchy.

### Design Recommendations for Petrarca

1. **Adaptive granularity**: Topics should be at the level the user engages with. If a user gives detailed feedback on "transformer architecture" sub-topics, break it down further. If they engage with "history" as a broad category, keep it broad.
2. **User-driven splitting/merging**: Let the user's feedback signal when topics need to be split (too broad, mixing unrelated things) or merged (too specific, cluttering the space).
3. **Grounding in knowledge bases**: Use Wikidata/DBpedia as the backbone for canonical topic identifiers, but let the user's vocabulary override the canonical labels (see knowledge-modeling.md section 3).

---

## 5. Incremental Reading and Spaced Reading Systems

### SuperMemo's Incremental Reading

SuperMemo remains the most fully realized incremental reading system. Key mechanisms:
- **Priority queue**: Each element has a priority (0-100%). Elements sorted by priority form the queue. Priority bias (overvaluing new imports) is countered by the relative queue.
- **Extract-reprioritize cycle**: Read a section, extract key passages, these become new queue items with their own priority and scheduling.
- **Increasing intervals**: Review intervals grow over time, so old unprocessed material fades to lower priority.
- **Article-level SRS**: Not just flashcards -- the articles themselves are scheduled for re-reading at increasing intervals.
- Documentation: https://help.supermemo.org/wiki/Incremental_reading
- **Petrarca relevance**: Petrarca's reading queue should implement a simplified version of this priority queue. The key insight is that articles compete for attention, and the system should surface the highest-value items while allowing lower-priority items to gracefully age out.

### The Mnemonic Medium and Orbit

**Andy Matuschak & Michael Nielsen's Mnemonic Medium** -- Embeds spaced repetition prompts directly within narrative prose. The key innovation: the author provides expert-authored prompts, removing the burden of prompt-writing that blocks SRS adoption. Readers get nearly-immediate reinforcement of what they just read. The "Quantum Country" textbook demonstrated that SRS can deepen conceptual understanding, not just memorize facts.
- Notes: https://notes.andymatuschak.org/Mnemonic_medium

**Orbit** -- Matuschak's open-source experimental platform for the mnemonic medium. Web-based, embeddable in any webpage. Authors interleave review prompts with their text.
- GitHub: https://github.com/andymatuschak/orbit
- **Petrarca relevance**: Petrarca could embed claim review prompts in articles. After reading an article with 5 key claims, the next time the user encounters a related article, Petrarca could briefly surface those claims: "Last time you read about X, the key finding was Y. This article says Z."

### Matuschak's Evergreen Notes

**Evergreen note-writing as fundamental unit of knowledge work** -- Notes should be atomic (one concept), titled as assertions (not topics), and evolve over time. Maintenance of evergreen notes approximates spaced repetition: if you're actively reading/writing about a topic, you revisit related notes regularly. If you stop, they fade.
- Notes: https://notes.andymatuschak.org/Evergreen_notes
- **Spaced repetition for developing inklings**: SRS follows your present interests. If you stop reading about a topic, you'll mostly never revisit it. If you're regularly reading, you'll revisit constantly.
- Notes: https://notes.andymatuschak.org/Spaced_repetition_may_be_a_helpful_tool_to_incrementally_develop_inklings
- **Petrarca relevance**: The "reading inbox" pattern (capture now, process later) maps to Petrarca's read-later queue. The principle that review should follow present interests aligns with Petrarca's interest-based ranking.

### CHI Research on Reading Behavior

**Deep vs. Skim Reading on Smartphones vs. Desktop** (CHI 2023) -- Systematically induced deep and skim reading, then trained classifiers to discriminate the two styles from eye movement patterns and interaction data. Achieved 0.82 AUC. Key finding: deep reading produced significantly better comprehension across all three levels (literal, inferential, evaluative). Skim reading maintained literal comprehension but inferential comprehension suffered.
- Paper: https://dl.acm.org/doi/10.1145/3544548.3581174
- **Petrarca relevance**: Petrarca should distinguish between skim and deep reading sessions. Different reading depths produce different signals: a skim session's "done" signal indicates awareness, not mastery. The depth navigator (Summary / Claims / Full) explicitly supports this distinction.

**Constrained Highlighting** (CHI 2024) -- Constraining the amount a reader can highlight improves reading comprehension. When users are forced to be selective, they engage more deeply with the text.
- Paper: https://dl.acm.org/doi/10.1145/3613904.3642314
- **Petrarca relevance**: This argues against unlimited highlighting. Petrarca's claim-level feedback (marking individual claims as new/known) is inherently constrained and may drive better comprehension than free-form highlighting.

**ReadingQuizMaker** (CHI 2023, Best Paper Honorable Mention) -- Human-NLP collaborative system for designing reading quiz questions. Uses NLP to suggest questions, entity replacements, paraphrasing, and distractors. Received Honorable Mention at CHI 2023.
- Paper: https://dl.acm.org/doi/10.1145/3544548.3580957

**ReaderQuizzer** (CSCW 2023) -- Augments research papers with just-in-time learning questions generated by ChatGPT. Scaffolds critical engagement with text through contextually relevant questions.
- Paper: https://dl.acm.org/doi/10.1145/3584931.3607494
- **Petrarca relevance**: Instead of quiz questions, Petrarca surfaces claims for user assessment. But the "just-in-time" principle is shared: present cognitive scaffolding at the moment it's most useful, not before or after.

### Polar Bookshelf

**Polar** -- Open-source personal knowledge repository for PDF and web content supporting incremental reading and document annotation. Features: pagemarks for tracking reading progress, text/area highlights, flashcard generation via Anki integration, document metadata extraction. Built with Electron and PDF.js. Data stored as JSON on disk.
- GitHub: https://github.com/bitcreative-studios/polar-bookshelf
- **Petrarca relevance**: Polar's pagemark concept (tracking where you stopped in a document) is relevant for Petrarca's reading state management. The Anki integration pattern shows how reading tools can bridge to SRS systems.

### Design Patterns for Petrarca

1. **Priority queue with graceful aging**: Implement SuperMemo-style priority queues where unread articles lose priority over time, preventing an ever-growing backlog.
2. **Claim-level spaced review**: After reading, key claims could resurface when encountering related articles (lighter than full SRS).
3. **Reading depth tracking**: Distinguish skim vs. deep reads and weight knowledge state updates accordingly.
4. **Constrained interaction**: Limit feedback mechanisms to encourage deeper engagement (claim-level yes/no over free highlighting).

---

## 6. User Feedback Signals for Interest/Knowledge Modeling

### Eye Tracking Research

**"Attentive Documents: Eye Tracking as Implicit Feedback"** (ACM TIIS 2011) -- Foundational work on using eye tracking for information retrieval. Behavioral signals investigated include clickthrough data, dwell time, mouse movements, and eye movements. Eye tracking provides information on what document parts users read and how they were read.
- Paper: https://dl.acm.org/doi/10.1145/2070719.2070722

**"Feedback Beyond Accuracy: Eye-Tracking for Comprehensibility and Interest"** (JASIST 2023) -- A study of 30 participants reading 18 news articles. Eye-tracking signals explained 49.93% of variance in comprehensibility and 30.41% of variance in interest at discourse level. This is the first study to demonstrate that eye tracking can detect both comprehensibility and interest during natural reading.
- Paper: https://pmc.ncbi.nlm.nih.gov/articles/PMC10084433/
- **Petrarca relevance**: While Petrarca can't use eye tracking on mobile, the finding that comprehensibility and interest are distinct signals is important. Petrarca should model both: "the user understands this topic" vs. "the user is interested in this topic."

**Implicit Estimation of Paragraph Relevance from Eye Movements** (Frontiers 2021) -- Demonstrates that paragraph-level relevance can be estimated from eye movements during reading. Different reading patterns (scanning vs. deep reading) correlate with task type.
- Paper: https://www.frontiersin.org/journals/computer-science/articles/10.3389/fcomp.2021.808507/full

### Non-Eye-Tracking Implicit Signals

**Segment-Level Display Time** (SIGIR 2009) -- Display time of text segments (the time a segment is visible on screen) can be used as implicit relevance feedback. More reliable than document-level dwell time because it captures which specific parts of a document the user engaged with.
- Paper: https://dl.acm.org/doi/10.1145/1571941.1571955
- **Petrarca relevance**: On mobile, scroll position tracking could approximate segment-level display time. If a user scrolls slowly through one section and quickly past another, the slow section is likely more interesting/relevant.

**User Behavior Modeling in Recommender Systems: A Survey** (IJCAI 2023) -- Comprehensive survey of how user behavior is modeled in recommender systems. Categorizes behaviors by type (click, scroll, dwell, purchase) and modeling approach (sequential, graph-based, attention-based).
- Paper: https://arxiv.org/abs/2302.11087
- **Petrarca relevance**: The hierarchy of signal strength is well-established: explicit feedback > click > dwell time > scroll > impression. Petrarca's signal hierarchy (chip feedback 2.0 > done 1.5 > highlight 1.0 > open 0.5 > swipe 0.5) aligns with this research.

**LinkedIn Dwell Time** (LinkedIn Engineering) -- LinkedIn uses dwell time to improve feed quality. Key insight: dwell time is a more reliable signal than clicks because it indicates actual engagement rather than just curiosity about the headline.
- Blog: https://www.linkedin.com/blog/engineering/feed/leveraging-dwell-time-to-improve-member-experiences-on-the-linkedin-feed
- **Petrarca relevance**: Reading time per article and per section is a cheap, reliable signal. Petrarca already logs reading events; converting these to per-article dwell time and using it as a signal weight would be straightforward.

### Active Reading and Highlighting

**Wigglite: Low-cost Information Collection and Triage** (UIST 2022) -- Explores "wiggling" (rapid back-and-forth pointer/scroll movements) as a gesture to collect, organize, and rate information during reading with a single interaction. Wiggling reduced operational cost by 58% and was 24% faster than traditional collection methods. Users could encode mental context (urgency, pro/con valence) through the gesture's characteristics.
- Paper: https://dl.acm.org/doi/10.1145/3526113.3545661
- **Petrarca relevance**: The insight is that information collection and rating can be combined into a single low-cost gesture. Petrarca's claim-level known/new toggle follows this principle: one tap simultaneously collects the claim and rates it.

**Textlets** (CHI 2020) -- Turns text selections into interactive objects that can be manipulated and saved within a text editor, improving consistency when working with technical documents.
- Paper: (Han et al., CHI 2020)
- **Petrarca relevance**: The concept of turning text selections into persistent, manipulable objects could inform how Petrarca handles highlighted passages and extracted claims.

### Practical Signal Hierarchy for Reading Apps

Based on the research, a signal strength hierarchy for Petrarca (already partially implemented):

| Signal | Strength | Notes |
|--------|----------|-------|
| Explicit claim feedback (new/known) | Highest | Direct knowledge assessment |
| Topic chip +/- | Very high | Explicit interest declaration |
| Completed reading ("Done") | High | Indicates engagement |
| Highlight/save passage | High | Active selection |
| Reading depth reached (full text vs. summary) | Medium | Depth of engagement |
| Dwell time per section | Medium | Implicit attention signal |
| Scroll behavior (speed, pauses) | Low-Medium | Noisy but available on mobile |
| Article opened | Low | Interest, not engagement |
| Article dismissed | Low (negative) | Explicit disinterest |

---

## 7. Cross-Article Knowledge Synthesis

### Sensemaking Theory

**The Cost Structure of Sensemaking** (Russell, Stefik, Pirolli, Card, CHI 1993) -- The seminal paper on sensemaking. Identifies learning loops: searching for representations, instantiating representations, shifting representations, and consuming encodons (coded information from data). Sensemaking is the process of framing, collecting, organizing, and structuring information to understand a problem.
- Paper: https://dl.acm.org/doi/10.1145/169059.169209

**The Sensemaking Process and Leverage Points** (Pirolli & Card, 2005) -- Identifies the sensemaking process as a dual loop: a foraging loop (finding information) and a sensemaking loop (organizing it into a coherent schema). The key insight: tools should support transitions between these loops, not just one of them.
- **Petrarca relevance**: Petrarca's feed is the foraging loop. The Topics tab and cross-article connections serve the sensemaking loop. The app should support fluid transitions between "finding new articles" and "understanding how they connect."

### Modern Sensemaking Tools

**Selenite** (CHI 2024) -- LLM-powered Chrome extension for online sensemaking. When users encounter an unfamiliar topic, Selenite uses GPT-4 to generate a comprehensive overview of options and criteria. As users read articles, the overview adapts and contextualizes content. Upon leaving a page, it summarizes progress and suggests search queries to expand perspectives rather than duplicate existing knowledge. Reduced task completion time by 36% and improved valid criteria identification.
- Paper: https://dl.acm.org/doi/10.1145/3613904.3642149
- GitHub: https://github.com/rrrrrrockpang/llm-chi
- **Petrarca relevance**: Two key ideas. First, generating a structured overview to scaffold reading (Petrarca could generate topic overviews that evolve as the user reads more articles). Second, suggesting searches that "expand perspectives rather than duplicate existing knowledge" -- this is exactly novelty-aware recommendation.

**Fuse: In-Situ Sensemaking Support in the Browser** (UIST 2022) -- Browser extension that externalizes working memory via a compact card-based sidebar. Combines low-cost collection with lightweight organization. 22-month public deployment with 100+ users validated the importance of in-situ organization and identified challenges for supporting sensemaking and task management.
- Paper: https://dl.acm.org/doi/10.1145/3526113.3545693
- **Petrarca relevance**: The card-based sidebar pattern for organizing collected information is applicable to Petrarca's reading queue and topic browser. Fuse's insight that collection and organization must happen together (not sequentially) aligns with Petrarca's inline claim feedback.

**ForSense** (ACM TIIS 2022) -- Browser extension guided by sensemaking theory. Two key innovations: (1) integrating multiple stages of online research (search, browse, collect, organize) and (2) using neural machine reading to provide machine-assisted suggestions. Used as a design probe to study real sensemaking tasks.
- Paper: https://dl.acm.org/doi/10.1145/3532853
- **Petrarca relevance**: The multi-stage integration principle. Petrarca should not just help with reading (one stage) but with the full cycle: discover, read, extract, connect, review.

### Cross-Document Synthesis Systems

**Threddy** (UIST 2022) -- Supports users in collecting patches of text from research articles that contain pre-digested syntheses by other authors (citation contexts). Helps assemble personal research threads from clippings. Extracts referenced papers from highlighted citation contexts. Enables following and curating research threads without breaking out of reading flow.
- Paper: https://dl.acm.org/doi/10.1145/3526113.3545660
- **Petrarca relevance**: The "thread" metaphor is powerful for Petrarca's cross-article knowledge synthesis. When a user reads about a topic across multiple articles, Petrarca could automatically assemble a "thread" showing how the topic evolved across those readings.

**Synergi** (UIST 2023) -- Mixed-initiative system for scholarly synthesis. Provides a structured outline view of research threads that users can interactively review, curate, and modify. A computational pipeline combines user seed threads with citation graphs and LLMs to expand and structure them. Evaluation showed Synergi helps scholars broaden perspectives and increase curiosity.
- Paper: https://dl.acm.org/doi/abs/10.1145/3586183.3606759
- **Petrarca relevance**: The "seed thread + expansion" pattern is directly applicable. A user's topic interests are seed threads. Petrarca could use LLMs to expand these into structured overviews, then recommend articles that fill gaps in the structure.

**Jigsaw** -- Visual analytics tool for document collection sensemaking. Integrates multiple text analysis algorithms with interactive visualizations. Provides a flexible environment for exploring document connections.
- Paper: https://ieeexplore.ieee.org/document/6392833/

**Garden of Papers** (UIST 2025) -- Sketch-based interactive system for finding, reading, and organizing research papers on a 2D canvas. Users create paper nodes and citation links, accumulate thoughts, and progressively shape personalized node-link diagrams. A 4-week in-the-wild study showed 9 usage patterns that enhance literature reviews.
- Paper: https://dl.acm.org/doi/10.1145/3746059.3747637
- **Petrarca relevance**: The spatial metaphor for knowledge organization. While Petrarca is mobile-first (limiting spatial UIs), the web version could support a spatial topic map view.

### Contradiction and Agreement Detection

**Scite Smart Citations** (Quantitative Science Studies 2021) -- Classifies citation intent as supporting, contrasting, or mentioning. This enables automatic detection of when the scientific community agrees or disagrees about a finding.
- Paper: https://direct.mit.edu/qss/article/2/3/882/102990/

**WikiContradict** (NeurIPS 2024) -- Benchmark for evaluating LLMs on detecting contradictions within Wikipedia. Finds that models are significantly worse at identifying contradictory evidence than supporting evidence.
- Paper: https://proceedings.neurips.cc/paper_files/paper/2024/file/c63819755591ea972f8570beffca6b1b-Paper-Datasets_and_Benchmarks_Track.pdf
- **Petrarca relevance**: Contradiction detection is harder than agreement detection for both humans and AI. Petrarca should set realistic expectations: detecting "articles that discuss similar topics" is feasible; detecting "articles that contradict each other" is harder and may require LLM-in-the-loop.

**Automated Fact-Checking Survey** (TACL 2022) -- Comprehensive survey covering claim detection, evidence retrieval, and verdict prediction. Key challenge: sometimes trustworthy sources contradict each other, which current fact-checking systems handle poorly.
- Paper: https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00454/109469/

### Design Patterns for Petrarca

1. **Thread assembly**: Automatically group claims from different articles by topic to create reading threads.
2. **Agreement/contradiction surfacing**: When claims on the same topic come from different articles, flag whether they agree, disagree, or extend each other. Start with LLM-based classification.
3. **Progressive overview generation**: As the user accumulates readings on a topic, generate and maintain an evolving structured overview (Selenite's approach).
4. **Gap identification**: Identify topics adjacent to the user's interests that they haven't explored (InfraNodus structural gap detection, Synergi's expansion).

---

## 8. Open-Source Implementations and Libraries

### For Document Processing
| Tool | Purpose | Link |
|------|---------|------|
| PaperMage | PDF parsing and NLP extraction for scholarly docs | https://github.com/allenai/papermage |
| ScholarPhi | Interactive PDF reader with augmented definitions | https://github.com/allenai/scholarphi |
| BERTopic | Hierarchical topic modeling with transformer embeddings | https://github.com/MaartenGr/BERTopic |
| TopicGPT | LLM-based topic modeling with natural language labels | https://github.com/chtmp223/topicGPT |
| Canary | Simple argument mining library | https://github.com/Open-Argumentation/Canary |
| SPECTER/SPECTER2 | Document-level embeddings for scientific papers | https://github.com/allenai/specter |

### For Reading and Sensemaking
| Tool | Purpose | Link |
|------|---------|------|
| Omnivore | Open-source read-it-later (unmaintained since Nov 2024) | https://github.com/omnivore-app/omnivore |
| Polar Bookshelf | Incremental reading + annotation + Anki integration | https://github.com/bitcreative-studios/polar-bookshelf |
| Orbit | Mnemonic medium / embedded SRS | https://github.com/andymatuschak/orbit |
| Lumi | AI-augmented paper reading (Google PAIR) | https://github.com/PAIR-code/lumi |
| Selenite | LLM-scaffolded online sensemaking | https://github.com/rrrrrrockpang/llm-chi |

### For Knowledge Graphs and Embeddings
| Tool | Purpose | Link |
|------|---------|------|
| Graphiti/Zep | Temporally-aware knowledge graphs | https://github.com/getzep/graphiti |
| Neo4j LLM Graph Builder | LLM-driven KG construction | https://github.com/neo4j-labs/llm-graph-builder |
| DBpedia Spotlight | Entity linking to Wikidata/DBpedia | https://github.com/dbpedia-spotlight/dbpedia-spotlight-model |
| Instructor | Structured LLM output via Pydantic | https://github.com/567-labs/instructor |

---

## 9. Synthesis: What Petrarca Should Borrow

### High-Priority Design Patterns

1. **Position-sensitive knowledge overlays** (ScholarPhi, CiteRead): Annotate articles inline with knowledge-aware information -- "you read about this in [article X]", "this contradicts [claim Y]", "this is new to you."

2. **Selenite's progressive overview**: As a user reads more about a topic, automatically maintain an evolving structured overview. When new articles arrive on that topic, show how they fit into the existing overview.

3. **Constrained claim feedback** (CHI 2024 highlighting research): Petrarca's claim-level new/known toggle is better than free-form highlighting for both comprehension and knowledge modeling.

4. **Thread assembly** (Threddy): Automatically group claims from different articles by topic to create cross-article reading threads. Present these in the Topics tab.

5. **Curiosity zone targeting** (ACM TKDD 2023): Score articles highest when they're adjacent to known territory -- familiar enough to be comprehensible, novel enough to be genuinely new.

### Medium-Priority Design Patterns

6. **Reading depth as signal** (CHI 2023 deep/skim study): Weight knowledge updates by reading depth. A skim read updates "encountered" state; a deep read updates "familiar" or "confident" state.

7. **Section-level dwell time** (SIGIR 2009): Track which sections the user lingers on. Use this as an implicit interest signal for fine-grained topic modeling.

8. **Synergi's seed-and-expand**: Let the user's topic interests serve as seeds. Use LLMs to suggest related areas they haven't explored yet.

9. **Scite's supporting/contrasting classification**: When multiple articles discuss the same topic, classify their relationship (agreeing, contradicting, extending).

### Research Questions Petrarca Could Explore

1. **Can reading behavior (dwell time, depth, claim feedback) produce a useful knowledge model?** Educational knowledge tracing has quizzes; Petrarca has only behavioral signals and optional explicit feedback. Is this enough?

2. **What's the right topic granularity for a general reader?** Academic readers need fine-grained topics. A reader with broad interests (history, AI, policy, languages) might need adaptive granularity that's broad for unfamiliar areas and fine for deep interests.

3. **Do cross-article claim threads actually help comprehension?** Threddy and Synergi show value for academic reading. Does the same hold for news/general articles?

4. **How much novelty detection accuracy is needed?** Is "72% new" meaningfully different from "65% new" to the user? What level of accuracy is good enough to be useful vs. just noise?

---

## References

### CHI / CSCW / UIST Papers
- Head et al., "ScholarPhi" (CHI 2021): https://dl.acm.org/doi/fullHtml/10.1145/3411764.3445648
- Rachatasumrit et al., "CiteRead" (IUI 2022): https://dl.acm.org/doi/10.1145/3490099.3511162
- Liu et al., "Wigglite" (UIST 2022): https://dl.acm.org/doi/10.1145/3526113.3545661
- Kuznetsov et al., "Fuse" (UIST 2022): https://dl.acm.org/doi/10.1145/3526113.3545693
- Kang et al., "Threddy" (UIST 2022): https://dl.acm.org/doi/10.1145/3526113.3545660
- Kang et al., "Synergi" (UIST 2023): https://dl.acm.org/doi/abs/10.1145/3586183.3606759
- Papeos (UIST 2023): related to Semantic Reader Project
- Liu et al., "Selenite" (CHI 2024): https://dl.acm.org/doi/10.1145/3613904.3642149
- Deep vs. Skim Reading (CHI 2023): https://dl.acm.org/doi/10.1145/3544548.3581174
- ReadingQuizMaker (CHI 2023): https://dl.acm.org/doi/10.1145/3544548.3580957
- ReaderQuizzer (CSCW 2023): https://dl.acm.org/doi/10.1145/3584931.3607494
- Constrained Highlighting (CHI 2024): https://dl.acm.org/doi/10.1145/3613904.3642314
- Garden of Papers (UIST 2025): https://dl.acm.org/doi/10.1145/3746059.3747637

### Surveys and Foundational Work
- Russell et al., "Cost Structure of Sensemaking" (CHI 1993): https://dl.acm.org/doi/10.1145/169059.169209
- Kaminskas & Bridge, "Beyond-Accuracy Objectives" (ACM TIIS 2017): https://dl.acm.org/doi/10.1145/2926720
- Curiosity in Recommender Systems (ACM TKDD 2023): https://dl.acm.org/doi/10.1145/3617598
- Eye Tracking for Interest/Comprehensibility (JASIST 2023): https://pmc.ncbi.nlm.nih.gov/articles/PMC10084433/
- User Behavior Modeling Survey (IJCAI 2023): https://arxiv.org/abs/2302.11087
- LLMs in Argument Mining Survey (2025): https://arxiv.org/abs/2506.16383
- Knowledge Tracing Survey: https://arxiv.org/html/2105.15106v4
- Automated Fact-Checking Survey (TACL 2022): https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00454/

### Tools and Platforms
- Semantic Reader Platform: https://openreader.semanticscholar.org/
- PaperMage: https://github.com/allenai/papermage
- ScholarPhi: https://github.com/allenai/scholarphi
- Lumi: https://github.com/PAIR-code/lumi
- Orbit: https://github.com/andymatuschak/orbit
- Scite: https://scite.ai/
- Elicit: https://elicit.com/
- Scholarcy: https://www.scholarcy.com/
- SciSpace: https://typeset.io/
- BERTopic: https://github.com/MaartenGr/BERTopic
- TopicGPT: https://github.com/chtmp223/topicGPT
- SPECTER: https://github.com/allenai/specter
- ForSense: https://dl.acm.org/doi/10.1145/3532853
- Ramos et al., "ForSense" (ACM TIIS): https://dl.acm.org/doi/10.1145/3532853
