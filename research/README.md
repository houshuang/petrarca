# Petrarca Research Index

Master index of all research documents. **Always update this file when adding new research.**

## Essential Reading (start here)

| When | Document | Why |
|------|----------|-----|
| **Every session** | [implementation-status.md](implementation-status.md) | Current system snapshot — architecture, all screens/scripts/endpoints, algorithm parameters |
| **Current restart** | [restart-plan-2026-08-24.md](restart-plan-2026-08-24.md) | Production-history survey, preservation boundary, private Companion experiment, research-library bridge, and delivery gates |
| **Design decisions** | [design-vision.md](design-vision.md) | Master "why" — "hooks not facts", Mode A vs B, three layers |
| **Retention/review** | [review-system-architecture.md](review-system-architecture.md) | Knowledge-centric (not source-centric) review design |
| **Retention/review** | [reading-companion-process-design.md](reading-companion-process-design.md) | How reading companion flows during active reading |
| **Curriculum/entities** | [overlapping-curricula-vision.md](overlapping-curricula-vision.md) | Bounded courses, shared entities, nexus points |
| **Curriculum architecture** | [curriculum-system-audit.md](curriculum-system-audit.md) | Where curriculum earns its keep, code paths, what's missing |
| **Deep intellectual "why"** | [matuschak-petrarca-analysis.md](../research/notes/matuschak-petrarca-analysis.md) | Critical flaws identified + 8 improvements |
| **Understanding the reader** | [beyond-flashcards-knowledge-retention.md](beyond-flashcards-knowledge-retention.md) | Why SRS fails for conceptual knowledge, 7 experimental designs |

## Read When Working On...

- **v2 Redesign (START HERE)**: [structural-review-redesign.md](structural-review-redesign.md) — Quiz-first app, structural cards, aspect-based grading, voice priority, 8-phase plan
- **Feed/ranking** *(DISABLED)*: [novelty-system-architecture.md](novelty-system-architecture.md), [claims-topics-feedback-spec.md](claims-topics-feedback-spec.md)
- **Synthesis**: [synthesis-pipeline-design.md](synthesis-pipeline-design.md), [synthesis-knowledge-tracking.md](synthesis-knowledge-tracking.md)
- **Books**: [book-companion-handoff.md](book-companion-handoff.md), [book-companion-experiments.md](book-companion-experiments.md)
- **Knowledge mapping**: [knowledge-curriculum-vision.md](knowledge-curriculum-vision.md), [curriculum-system-audit.md](curriculum-system-audit.md), [learning-science-for-knowledge-mapping.md](learning-science-for-knowledge-mapping.md)
- **Historiographic/interpretive knowledge**: [historiographic-knowledge-design.md](historiographic-knowledge-design.md)
- **Wikidata entity resolution**: [wikidata-deployment-guide.md](wikidata-deployment-guide.md) (runbook), `scripts/backfill_wikidata.py` (4-pass pipeline), `scripts/merge_entity_dupes.py`, `scripts/reprocess_voice_with_qids.py`
- **Growth measurement**: [knowledge-growth-measurement-proposal.html](knowledge-growth-measurement-proposal.html)
- **Calibration/thresholds**: [experiment-results-report.md](experiment-results-report.md), `scripts/ground-truth/`
- **UX**: [ux-redesign-spec.md](ux-redesign-spec.md), [web-app-audit.md](web-app-audit.md), [mobile-app-audit.md](mobile-app-audit.md)
- **Agent architecture**: [autonomous-agent-frameworks-2025-2026.md](autonomous-agent-frameworks-2025-2026.md), [always-on-agent-cost-comparison.md](always-on-agent-cost-comparison.md)

---

## Master Reference
| Document | Description | Status |
|----------|-------------|--------|
| [implementation-status.md](implementation-status.md) | **CURRENT STATE** — System snapshot: architecture, screens, scripts, endpoints, algorithms, deployment | Active |
| [session-changelog.md](session-changelog.md) | **HISTORY** — Session-by-session implementation log (sessions 20-62) | Active |
| [system-state-of-the-art.md](system-state-of-the-art.md) | **COMPREHENSIVE** — Single file covering all research, validated algorithms, data structures, UI mockups, pipeline architecture | Active |

## Operational
| Document | Description | Status |
|----------|-------------|--------|
| [wikidata-deployment-guide.md](wikidata-deployment-guide.md) | Step-by-step runbook for Wikidata entity resolution: schema migration, backfill, dedup merges, admin triage | Active |

## Foundational
| Document | Description | Status |
|----------|-------------|--------|
| [design-vision.md](design-vision.md) | **Master synthesis** — all interviews + research into coherent design vision | Done |
| [interview-analysis.md](interview-analysis.md) | Analysis of initial LLM interview — incremental reading ideas extracted | Done |
| [user-requirements.md](user-requirements.md) | User interview round 1 — reading contexts, pain points, design insights | Done |
| [user-requirements-2.md](user-requirements-2.md) | User interview round 2 — history reading, voice notes, background agents | Done |
| [user-requirements-3.md](user-requirements-3.md) | User interview round 3 — otak status, first experiment, cost prefs | Done |
| [user-requirements-4.md](user-requirements-4.md) | User interview round 4 — hooks philosophy, note-taking paradox | Done |
| [reference-projects.md](reference-projects.md) | Analysis of ../otak, ../bookifier, ../alif — reusable code & patterns | Done |
| [incremental-reading.md](incremental-reading.md) | Deep dive on incremental reading: SuperMemo, theory, implementations | Done |

## External Research & Prior Art
| Document | Description | Status |
|----------|-------------|--------|
| [kolja-sam-learning-tools-analysis.md](kolja-sam-learning-tools-analysis.md) | **Analysis of Kolja Sam's learning tool portfolio** (koljasam.com): 20+ projects, digital garden on learning science. Key insights for Petrarca: learning bugs vs fatigue lapses, SR prediction≠learning, overlearn→refresh, confidence trajectories, serendipitous self-knowledge resurfacing, interdependent cards. Actionable summary with priorities. | Done |

## Domain Research
| Document | Description | Status |
|----------|-------------|--------|
| [~/src/research/notes/atomic-deep-analogue-digital-research.md](../../research/notes/atomic-deep-analogue-digital-research.md) | **CROSS-PROJECT — Atomic↔Deep / Analogue↔Digital framework**: Comprehensive literature review (March 2026) on the tension between fragmented/microlearning and deep/focused learning. Covers: Marton & Säljö (1976) deep/surface approaches, Bjork desirable difficulties, Laufer & Hulstijn Involvement Load Hypothesis, Schmidt Noticing Hypothesis, Wolf reading circuit, Delgado screen vs paper meta-analysis, Loewenstein curiosity/information gap, tools landscape (Anki/LingQ/Migaku/jpdb.io/Quantum Country), Refold/AJATT methodology. Includes specific "Implications for Petrarca" and "Implications for Alif" sections as research from 5 deep-dive subagents completes (ongoing). | **Active — growing** |
| [~/src/research/notes/matuschak-petrarca-analysis.md](../../research/notes/matuschak-petrarca-analysis.md) | **CRITICAL — Matuschak vs. Petrarca architecture deep analysis** (March 2026): Read TTFT, Timeful Texts, "Why books don't work", "How to write good prompts", Quantum Country empirical data, full Matuschak notes corpus, then compared against Petrarca architecture. Where Matuschak agrees (atomic claims, dim-not-hide, FSRS decay). **Critical flaws identified**: claim extraction ≠ SRS prompts (LLM generates surface claims, not understanding-probe questions); no retrieval practice (only exposure tracking — the Readwise failure mode); reading/review decoupled (loses narrative context). 8 prioritized improvements including embedded retrieval questions, section-break micro-reviews, retrieval-gated absorption, two-tier architecture proposal. | **Active — essential reading** |
| [andy-matuschak-research.md](andy-matuschak-research.md) | **Deep research**: Andy Matuschak's work on reading, memory, knowledge resurfacing — Mnemonic Medium, Quantum Country results, Timeful Texts, Orbit, author-vs-reader prompts, comprehension-before-memory finding, "How Might We Learn?" AI framework, collaboration with Nielsen, criticisms, relevance to Petrarca | Done |
| [prior-art.md](prior-art.md) | Existing tools, libraries, open source projects | Done |
| [knowledge-modeling.md](knowledge-modeling.md) | **Comprehensive research**: tools, algorithms, approaches for personal knowledge modeling, novelty detection, claim extraction, topic hierarchies, curiosity-driven recommendation | Done |
| [hci-reading-systems.md](hci-reading-systems.md) | **HCI literature survey**: CHI/CSCW/UIST research on augmented reading tools, sensemaking, cross-document synthesis, implicit feedback, incremental reading, topic granularity | Done |
| [knowledge-mapping-20-questions.md](knowledge-mapping-20-questions.md) | **Comprehensive research**: Adaptive "20 Questions" binary-search approach to rapidly map personal knowledge via self-report. Covers Knowledge Space Theory (Doignon & Falmagne, ALEKS), CAT/IRT, LLM-generated assessment, knowledge elicitation techniques, personal knowledge graphs, information-theoretic question selection, Bloom's taxonomy depth probing, Dunning-Kruger mitigation. Novel combination analysis, implementation architecture, question selection algorithm. | Done |
| [knowledge-deduplication.md](knowledge-deduplication.md) | **Scalable deduplication**: embedding models, vector storage, semantic dedup, hierarchical comparison, claim matching, incremental updates — full architecture for 13K+ claims/year | Done |
| [knowledge-representation-novelty.md](knowledge-representation-novelty.md) | **Deep dive**: structured knowledge representation for novelty comparison — atomic fact decomposition, claim normalization, NLI-based entailment, proposition embeddings, non-factual knowledge, proposed architecture | Done |
| [article-synthesis-prior-art.md](article-synthesis-prior-art.md) | **Comprehensive survey**: products that synthesize multiple articles into combined views — news aggregators (Google News, Particle, Ground News, Artifact, Semafor), research tools (NotebookLM, Consensus, Elicit, Semantic Scholar), digest/newsletter tools (Feedly, Mailbrew, TLDR, Kagi, Readwise), search/report tools (Perplexity, Arc Search), DIY approaches (Fabric, GitHub projects), failure modes, and recommended synthesis patterns for Petrarca | Done |
| [multi-article-synthesis-systems.md](multi-article-synthesis-systems.md) | **Technical deep dive**: academic & algorithmic foundations for multi-article synthesis — MDS with attribution (PRIMERA, WebCiteS, FActScore), clustering (BERTopic, iFacetSum, TOMDS), cross-document alignment (QA-Align, CDA, event coreference), diff interfaces (CiteSee, Semantic Reader, NewsDiffs), GraphRAG/STORM, proposed 5-phase synthesis architecture | Done |
| [knowledge-diff-interfaces.md](knowledge-diff-interfaces.md) | **Knowledge-diff reading interfaces**: HCI literature survey on adaptive presentation (dimming, stretchtext, fisheye), skimming tools (Scim), diff patterns (Wikipedia, VS Code), progressive disclosure, and proposed interaction model for "skip to the new stuff" reading | Done |
| [knowledge-tracing-for-reading.md](knowledge-tracing-for-reading.md) | **Deep research**: adapting Knowledge Tracing (BKT, DKT, DKVMN, FSRS) from educational technology to model reader knowledge state from articles -- observation models for passive reading, KC granularity, forgetting/decay, preference tracing, proposed 6-layer architecture combining soft BKT with FSRS decay | Done |
| [knowledge-assessment-research.md](knowledge-assessment-research.md) | **Deep research**: Knowledge state assessment — concept inventories, expert/novice knowledge structures, free recall protocols, concept maps, Pathfinder networks, spaced retrieval beyond flashcards, longitudinal tracking, voice-based elicitation, existing systems (BKT, DKT, SPARFA, iSTART) | Done |
| [knowledge-systems-deep-dive.md](knowledge-systems-deep-dive.md) | **Deep research + design**: Researchers (ALEKS/KST, GENCAT, SPARFA, Matuschak, Karpicke, Pathfinder, SNAFU), published Python tools/libraries, type-differentiated scheduling (Fuzzy-Trace Theory), knowledge growth measurement via voice sweeps + Pathfinder distance, DB schema, implementation plan | Done |
| [topic-normalization-spec.md](topic-normalization-spec.md) | **Topic normalization & defragmentation**: canonical registry, LLM merge-or-create, periodic defrag, Otak lessons applied | Done |
| [article-selection.md](article-selection.md) | Algorithms for filtering/ranking/scoring articles | TODO |
| [spaced-attention.md](spaced-attention.md) | Matuschak & Haisfield's spaced attention concepts | Done |
| [progressive-summarization.md](progressive-summarization.md) | Tiago Forte's method + related approaches | TODO |
| [reading-ui-research.md](reading-ui-research.md) | CHI/HCI research on novel reading/triage UIs, gesture vocabularies, progressive disclosure | Done |
| [interaction-signals.md](interaction-signals.md) | Mobile interaction design for reading feedback | TODO |
| [voice-processing.md](voice-processing.md) | Soniox API integration, multilingual STT, Expo patterns | Done |
| [open-algorithms.md](open-algorithms.md) | Transparent, user-configurable ranking | TODO |
| [hci-book-reading-annotation.md](hci-book-reading-annotation.md) | **HCI research survey for book companion**: CHI/UIST 2022-2025 augmented reading tools (constrained highlighting, Scim, CiteSee, ReaderQuizzer, Priming at Scale), annotation/marginalia research (physical vs digital, expert practices), sensemaking frameworks (Pirolli & Card, Russell learning loops, Fuse, Threddy), context restoration/reading resumption (spatial memory, reviews/previews, EyeBookmark), voice annotation (self-explanation effect g=0.55, production effect, generation effect), cross-document synthesis (Passages, syntopical reading, Orbit). 8 concrete experimental directions for book companion. | Done |

## Knowledge Curriculum & Mapping
| Document | Description | Status |
|----------|-------------|--------|
| [structured-curricula-survey.md](structured-curricula-survey.md) | **SURVEY**: Comprehensive survey of freely available structured curricula for self-education knowledge mapping — AP World History (66 topics), AP European History (88 topics), OpenStax World History (130 sections), IB History (12 world topics), OCR Classical Civilisation, AQA/Edexcel A-Level History, Norwegian LK20, Khan Academy, MIT OCW, Yale Open Courses. Coverage gap analysis, node estimates, recommended curriculum stack (~400 topic-level nodes, ~1,500-2,000 fine-grained). Full topic breakdowns and direct URLs to specification PDFs. | Done |
| [knowledge-curriculum-vision.md](knowledge-curriculum-vision.md) | **VISION DOC**: Curriculum-based knowledge mapping — all ideas from brainstorming session. Bottom-up curriculum generation, books as knowledge signals, knowledge+interest two dimensions, 20Q card-flip UI, Alif parallels (collateral credit), layering principle (ZPD), book significance rating, Otak connection, open questions on structure/depth/growth. | Active |
| [knowledge-curriculum-implementation-plan.md](knowledge-curriculum-implementation-plan.md) | **IMPLEMENTATION PLAN**: First experiments and build plan for curriculum-based knowledge mapping system | Active |
| [knowledge-elicitation-iteration-notes.md](knowledge-elicitation-iteration-notes.md) | **ITERATION NOTES**: Insights from first real 20Q session — learning while testing, graduated depth probing, latent vs active knowledge, voice dump prompts, 5 iteration variants (A-E) | Active |
| [learning-science-for-knowledge-mapping.md](learning-science-for-knowledge-mapping.md) | **LEARNING SCIENCE RESEARCH**: 8-area deep dive — testing effect (Roediger/Karpicke), CMU Knowledge Components (KLI framework), L@S 2024 papers, backward design (UbD/Bloom's), graduated depth (ZPD/CAT/MIRT), self-assessment in humanities (Seixas' historical thinking, Dunning-Kruger, CBM), open curricula (AP/IB frameworks, CASE standards), innovative question formats (VSAQs, comparative judgment, timelines). 8 prioritized recommendations for iterating on 20Q format. | Done |
| [overlapping-curricula-vision.md](overlapping-curricula-vision.md) | **VISION**: Overlapping curricula as bounded college courses that cross-reference — shared entities with curriculum-specific lenses, nexus points where concepts span multiple domains, temporal cross-referencing. Phases 1-3 implemented in session 54. | Active |
| [curriculum-system-audit.md](curriculum-system-audit.md) | **AUDIT (Session 54)**: Comprehensive audit of where curriculum earns its keep (dedup, progress viz, voice elicitation, key_facts) vs under-utilized (cross-domain connections). Documents multi-domain mapping, cross-curriculum context, temporal cross-refs, nexus cards, book prescan. Key code paths. | Active |
| [reading-companion-process-design.md](reading-companion-process-design.md) | **PROCESS DESIGN**: How the reading companion flows during active book reading — temporal hooks (4 types, priority order), 3 interaction moments (chapter complete card, cross-book review, map old book), chapter dropdown semantics, pre-reading book scan, rapid feedback calibration pattern, integration with Amygdala. Active design doc for long-term iteration. | Active |
| [entity-profiles-design.md](entity-profiles-design.md) | **DESIGN SKETCH**: Entity profiles as lightweight knowledge structures for historical figures — person≡period duality, 4-layer scaffold (identity/context/connections/significance), question generation from key_facts + cross-curriculum bridges + reading triggers, proto-curriculum growth pattern, implementation plan. Examples: Roger II, Karl XII, Frederick II. | Active |
| [entity-first-architecture.md](entity-first-architecture.md) | **ARCHITECTURE PROPOSAL**: Invert the dependency — entities (Wikidata QIDs) as primary knowledge unit, curricula as optional overlay for gap analysis and structural review. Dependency audit of all curriculum assumptions. 5-phase migration: entity-keyed knowledge table → entity-based question gen → unified review stream → curriculum as lens → organic growth. Supersedes curriculum-as-foundation assumption. | Active |

## Voice & Microlearning
| Document | Description | Status |
|----------|-------------|--------|
| [voice-microlearning-integration.md](voice-microlearning-integration.md) | **DESIGN**: Voice → microlearning bridge — 3 integration points (elicitation wonderings, review memo questions, feedback research_request), auto-trigger with rate limits, dedup, response shape changes, client toast UX, what NOT to auto-trigger. Implementation order: elicitation first (purest signal), then review memos, then feedback routing. | Active |

## Knowledge Retention
| Document | Description | Status |
|----------|-------------|--------|
| [knowledge-growth-measurement-proposal.html](knowledge-growth-measurement-proposal.html) | **GROWTH MEASUREMENT**: Three-tier proposal synthesized from 7 research docs. Tier 1 (passive tracking — implemented session 62): knowledge_transitions table, Goldsmith edge overlap metric, D3 growth viz at `/knowledge/growth`. Tier 2 (voice sweeps): monthly free recall scored against curriculum. Tier 3 (type-differentiated scheduling): FTT verbatim/gist decay rates. Literature: Pathfinder networks (r=.74), Fuzzy-Trace Theory, SNAFU, Karpicke testing effect. | Active |
| [review-system-architecture.md](review-system-architecture.md) | **CRITICAL DESIGN DOC**: Deep analysis of the KRI review system — fundamental flaw (node×chapter vs node-centric), data model redesign, multi-book/multi-curriculum workflow, coverage measurement, 4-phase implementation roadmap. Written after first end-to-end test. | Active |
| [review-system-hypotheses.md](review-system-hypotheses.md) | **MEASUREMENT PLAN**: 9 testable hypotheses for the KRI review system — TEMPORAL lens advantage, time-to-reveal as confidence proxy, voice memo encoding benefit, dependency cascade impact, explore-as-curiosity vs avoidance, depth ordering, stability plateau, session fatigue, temporal hook recall. Full log event schema, baseline metrics, Python analysis patterns. | Active |
| [beyond-flashcards-knowledge-retention.md](beyond-flashcards-knowledge-retention.md) | **Deep research**: Why SRS fails for conceptual knowledge, gist vs verbatim memory decay, elaborative retrieval, connection-based resurfacing, spreading activation, analogical reminding. 7 experimental designs for Petrarca: concept encounters, evolving summaries, argument challenges, reading echoes, knowledge half-life dashboard, prompted self-explanation, concept constellation. Prioritized implementation plan. | Done |
| [mnemonic-medium-physical-books.md](mnemonic-medium-physical-books.md) | **Deep research**: Andy Matuschak's mnemonic medium / timeful text vision applied to physical books. Covers: Matuschak's research arc 2019–2025 (Quantum Country results, comprehension-not-memory pivot, highlight-driven prototype, Great Books problem, BookBridge, Latticework), Nielsen's contributions, desirable difficulties research (generation effect, testing effect, elaborative interrogation), LLM prompt generation limitations, existing physical-to-digital workflows (Readwise, Screvi, Dendro). 7 concrete experimental directions for Petrarca's book companion: resonance resurfacing, comprehension audit, chapter digest, cross-book threads, wizard-of-oz highlighter, incremental rethinking, conversational review. | Done |

## Physical Book Companion
| Document | Description | Status |
|----------|-------------|--------|
| [book-companion-experiments.md](book-companion-experiments.md) | **MASTER EXPERIMENT PLAN**: 8 prioritized experiments synthesized from 6 research agents. Reading Echoes (books enriching articles), Smart Page Photos (vision-enhanced capture), Voice Self-Explanation, Constrained Capture, Resonance Resurfacing, Cross-Source Synthesis, Context Restoration, Chapter Digests. Anti-patterns, build order, research principles. | Active |
| [book-companion-experiment-protocols.md](book-companion-experiment-protocols.md) | **DETAILED PROTOCOLS**: Full specifications for all 8 experiments — hypothesis, algorithm (with code), UI descriptions, user journeys, data requirements, metrics to log, dependency graph, minimum data for testing. Grounded in existing infrastructure (BookCapture, call_vision, Gemini embeddings, cosine thresholds). | Active |
| [book-companion-implementation-plan.md](book-companion-implementation-plan.md) | **BUILD PLAN**: Combined implementation for Sprint A — Book Research Agent (passive book knowledge via Gemini+Search), cross-source embedding pipeline, Story So Far briefing, chapter insights, suggested reading + auto-ingestion, enhanced page photos. Testing strategy (4 tiers). All deferred ideas listed. | Active |
| [kindle-book-experiments.md](kindle-book-experiments.md) | **KINDLE EXPERIMENTS**: 6 experiments for finished + in-progress Kindle books. Knowledge Archaeology (reading landscape), Resonance Resurfacing (highlight re-encounters with voice prompts), Cross-Book Voice Dialogues (claim pairs from different books), Active Content Discovery (books → articles), Completion Retrospectives, EPUB Deep Processing. Scheduling, prioritization, algorithms, UI descriptions. | Active |
| [book-companion-handoff.md](book-companion-handoff.md) | **HANDOFF**: Complete reference for continuing book companion work. All files, endpoints, types, architecture decisions, pipeline diagram, what's built vs. designed, current live state. | Active |
| [physical-book-digital-bridge-research.md](physical-book-digital-bridge-research.md) | **Comprehensive landscape scan**: Products (Readwise, Highlighted, Screvi, Basmo, BookPace, Mark), OCR vs vision models, voice-first interaction, progress tracking, "book club of one" concept, NFC/AR/QR bridges, e-ink devices, community pain points, market gaps, Petrarca opportunities | Done |
| [ai-book-captures-research.md](ai-book-captures-research.md) | **AI-augmented book reading (2024-2026)**: Landscape survey (NotebookLM, Kindle Ask This Book, Readwise Ghostreader, Kairos, Emdash, Chapters, reader3), vision model capabilities for page photos, voice-to-knowledge pipelines, elaborative interrogation research, synthesis from captures, 8 prioritized experiments for Petrarca's physical book companion | Done |

## Book Reader (Mode B)
| Document | Description | Status |
|----------|-------------|--------|
| [book-reader-design.md](book-reader-design.md) | Full design: section-based reading, cross-book connections, topic shelves, data structures, pipeline | Done |
| [innovative-reading-patterns.md](innovative-reading-patterns.md) | Research report: multi-book UX, context restoration, cross-text connections, progressive disclosure, argument tracking, experimental ideas (Heptabase, Kairos, Scite.ai, InfraNodus, Orbit, Kialo, etc.) | Done |
| [innovative-reading-ux.md](innovative-reading-ux.md) | Deep UX research: cross-text visualization (LiquidText, Passages CHI 2022, Roam), context restoration psychology, argument tracking/mapping, interleaved reading pedagogy, gesture vocabularies, design recommendations | Done |
| [reading-clusters/arabic-latin-bridge.md](reading-clusters/arabic-latin-bridge.md) | First reading cluster: 4 books on Arabic-Latin transmission (Pirenne, Menocal, Burnett, Gilbert) — themes, reading journeys, cross-book connections | Done |
| [book-reader-walkthrough.md](book-reader-walkthrough.md) | Simulated 6-week user journey through the Arabic-Latin bridge cluster — day-by-day interactions, cross-book connections, context restoration, synthesis moments, UX gaps identified | Done |

## Infrastructure & Integrations
| Document | Description | Status |
|----------|-------------|--------|
| [ingestion-sources.md](ingestion-sources.md) | Email-to-article ingestion (Cloudflare Email Workers, Postfix) and browser web clipper extension | Done |
| [knowledge-elicitation-20-questions.md](knowledge-elicitation-20-questions.md) | **Knowledge elicitation research**: "20 Questions"-style adaptive questioning for mapping user knowledge. Information theory (Shannon, entropy, information gain), Knowledge Space Theory (ALEKS), Bayesian belief models (Akinator), adaptive testing (CAT/IRT), LLM tutoring (INTERACT, Khanmigo), self-assessment reliability (Dunning-Kruger), hierarchical knowledge structures for history/humanities, concept inventories, prior art survey. Practical architecture for 15-25 question conversational knowledge mapping. | Done |
| [kindle-integration.md](kindle-integration.md) | Kindle data integration: APIs, highlights export, reading progress, Readwise middleware, practical plan | Done |
| [agent-security-architecture.md](agent-security-architecture.md) | **Security architecture for autonomous AI agent on production VM**: sandboxing (systemd, bubblewrap, Docker, Firecracker), permission models, authentication/secrets management, audit/monitoring, supervisor-worker architecture, backup/recovery, cost optimization. Concrete implementation plan for Hetzner VM. | Done |
| [autonomous-agent-frameworks-2025-2026.md](autonomous-agent-frameworks-2025-2026.md) | **Comprehensive survey (March 2026)**: 18+ AI coding/agent frameworks evaluated for always-running autonomous agent use. Claude Agent SDK, Claude Code CLI, OpenHands, SWE-agent, Aider, Open Interpreter, Cline, Goose, CrewAI, AutoGen, LangGraph, Pydantic AI, Computer Use, and more. Comparison matrix, daemon readiness, multi-LLM support, memory, security, sub-agents, Claude Max usage limits. | Done |
| [agent-communication-interface.md](agent-communication-interface.md) | **Agent communication research**: 10 messaging platforms (Telegram, Signal, Matrix, WhatsApp, iMessage, Discord, Slack, PWA, email, SMS), 4 voice processing options (Soniox, Whisper, whisper.cpp, Deepgram), existing AI assistant projects surveyed. Comparison matrix, recommended architecture (Telegram bot primary + Soniox voice). | Done |
| [always-on-agent-cost-comparison.md](always-on-agent-cost-comparison.md) | **Architecture & cost comparison**: 7 approaches evaluated for always-on personal agent. Pure `claude -p` wrapper, Claude Agent SDK (API keys), Gemini Flash + claude -p hybrid, three-tier hybrid, OpenRouter, local models (Ollama), Claude Code as daemon. ToS analysis, per-token pricing, monthly cost estimates ($5-160), latency, implementation effort. Recommended: Gemini Flash (free tier) + Claude Haiku API + Claude Agent SDK Sonnet, ~$5-25/month. | Done |

## Cross-Project & Amygdala
| Document | Description | Status |
|----------|-------------|--------|
| [books-articles-connection-proposal.md](books-articles-connection-proposal.md) | **PROPOSAL**: Connecting books and articles via curriculum as bridge — not direct claim matching. 5-phase plan: embed curriculum nodes, map article claims to nodes, reading boost in feed, chapter-complete article suggestions, reading echo badges. What NOT to build (no cross-claim matching, no recommendation engine). | Active |
| [cross-project-similarity-applications.md](cross-project-similarity-applications.md) | **Cross-project similarity via amygdala**: Analysis of content similarity needs across Petrarca, Alif, and Hamarquizen. Per-project content types, similarity semantics, ground truth. 4 common patterns (novelty, EXTENDS, curriculum, interference). 3 concrete amygdala proposals (ContentSimilarityIndex, SimilarityCalibrator, InterferenceFilter). Shared calibration data format. Priority-ranked next steps. | Active |
| [auto-research-patterns.md](auto-research-patterns.md) | **Auto-research patterns**: Karpathy's autoresearch loop (700 experiments/2 days, 11% gain), three-file architecture (program.md + immutable eval + mutable experiment), failure modes (agent drift, problem redefinition, context overflow), autoresearch-anything generalization. Applied to Petrarca similarity calibration (30 ground-truth pairs, fast eval loop) and amygdala `auto_calibrate()` API sketch. Practical implementation plan with Claude Code agents. | Active |

## UX Redesign
| Document | Description | Status |
|----------|-------------|--------|
| [feed-redesign-plan.md](feed-redesign-plan.md) | **Navigation overhaul**: Replace 4-tab layout with single unified screen + lens tabs + ✦ drawer. Queue → "Up Next", Topics → lens, Log → drawer. 3 rounds of mockup exploration, approved direction, detailed implementation plan. | Active |

## Audits & Platform Consistency
| Document | Description | Status |
|----------|-------------|--------|
| [user-journeys-platform-plan.md](user-journeys-platform-plan.md) | **Unified user journeys & platform plan**: All 10 user journeys across mobile/web, shared vs separate code boundaries, web layout specs for secondary screens, 4-phase implementation plan | Active |
| [web-app-audit.md](web-app-audit.md) | **Web app audit**: comprehensive comparison of DESIGN_GUIDE.md specs vs actual implementation — 16 gaps identified across design elements, polish issues, and broken stubs, with prioritized recommendations | Active |
| [mobile-app-audit.md](mobile-app-audit.md) | **Mobile app audit**: comprehensive review of plans vs reality — design system compliance, feature completeness (~95%), code robustness issues (error boundaries, async safety, FlatList memory), prioritized fix list | Active |

## Cross-Article Synthesis
| Document | Description | Status |
|----------|-------------|--------|
| [synthesis-pipeline-design.md](synthesis-pipeline-design.md) | **Session 17+19**: Concept cluster detection (graph-based + spectral bisection), synthesis generation (Gemini 3 Flash + tool calling), junk cleanup, two-pass contrastive labeling. 26 syntheses across 29 clusters. Session 19: prompt overhaul (humanist scholar voice, article reference links, structured tensions, progressive disclosure markers). Scripts: `build_concept_clusters.py`, `generate_syntheses.py`, `cleanup_articles.py`, `compare_synthesis_models.py`. | Active |
| [synthesis-knowledge-tracking.md](synthesis-knowledge-tracking.md) | **Session 18**: System design for synthesis read tracking → feed filtering → ingestion novelty. Covers: feed coverage threshold (80%), partial coverage demotion, richer SynthesisReadState, chat as knowledge artifact. **Feed filtering implemented in session 19**: ≥80% coverage excluded, ≥50% demoted. | Active |

## Experiments & Development
| Document | Description | Status |
|----------|-------------|--------|
| [design-experiments-plan.md](design-experiments-plan.md) | Comprehensive plan: content expansion, reader experiments, triage, knowledge model | Active |
| [experiment-log.md](experiment-log.md) | Append-only log of all experiments and prototypes | Active |
| [development-reference.md](development-reference.md) | **Complete dev reference** — architecture, all experiments, hypotheses, decisions, file index, event log | Active |
| [user-journey-analysis.md](user-journey-analysis.md) | Assumptions vs. reality: expected user journey over weeks, gap analysis, prioritized recommendations | Done |
| [content-refresh-design.md](content-refresh-design.md) | Architecture for scheduled pipeline on Hetzner + HTTP content serving + app sync | Done |
| [honest-assessment.md](honest-assessment.md) | Frank self-critique: what works, what doesn't, risk-ranked assumptions, experiments needed | Done |
| [reset-implementation-log.md](reset-implementation-log.md) | **Major reset**: strip to feed+reader, litellm pipeline, interest model — full design spec + next steps | Done |
| [ux-redesign-spec.md](ux-redesign-spec.md) | **UX redesign spec**: 2 rounds of mockup feedback, approved interaction models for all screens (feed, reader, topics, queue, log, web) | Done |
| [novelty-system-architecture.md](novelty-system-architecture.md) | **MASTER ARCHITECTURE**: Consolidated design for knowledge-aware novelty system — atomic claim store, pipeline (extract→normalize→embed→compare→score), delta reports, reader UI, knowledge tracing, implementation plan. Start here. | Active |
| [claims-topics-feedback-spec.md](claims-topics-feedback-spec.md) | **Deep exploration**: claim presentation, topic hierarchy feedback, cross-article connections — context doc for dedicated design agent | Active |
| [overnight-system-report.md](overnight-system-report.md) | **System validation report**: end-to-end test of atomic claims → embeddings → knowledge tracking → delta reports → reading simulations. 47 articles, 858 claims, 3 scenarios. | Done |
| [experiment-results-report.md](experiment-results-report.md) | **Algorithm experiments**: NLI entailment (LLM judge), BERTopic clustering, FSRS knowledge decay, curiosity zone scoring, Nomic vs Gemini embeddings — consolidated results + recommendations | Done |
| [implementation-status.md](implementation-status.md) | **V1 implementation log**: knowledge-aware reading system — all files, merge history, deployment, known issues, next steps | Active |
| [user-journey-weeks.md](user-journey-weeks.md) | Detailed 4-week user journey narrative, grounded in interviews + design research | Done |
| [user-guide.md](user-guide.md) | **User guide** — capture flows, reading modes, integrations, non-obvious features, hypotheses to test | Done |
