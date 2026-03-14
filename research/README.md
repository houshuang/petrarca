# Petrarca Research Index

Master index of all research documents. **Always update this file when adding new research.**

## Master Reference
| Document | Description | Status |
|----------|-------------|--------|
| [implementation-status.md](implementation-status.md) | **CURRENT STATE** — Comprehensive implementation status: all files created/modified, algorithm parameters, deployment status, known issues, next steps. Read this first for what's built and what's pending. | Active |
| [system-state-of-the-art.md](system-state-of-the-art.md) | **COMPREHENSIVE** — Single file covering all research, validated algorithms, data structures, UI mockups, pipeline architecture. | Active |

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

## Domain Research
| Document | Description | Status |
|----------|-------------|--------|
| [prior-art.md](prior-art.md) | Existing tools, libraries, open source projects | Done |
| [knowledge-modeling.md](knowledge-modeling.md) | **Comprehensive research**: tools, algorithms, approaches for personal knowledge modeling, novelty detection, claim extraction, topic hierarchies, curiosity-driven recommendation | Done |
| [hci-reading-systems.md](hci-reading-systems.md) | **HCI literature survey**: CHI/CSCW/UIST research on augmented reading tools, sensemaking, cross-document synthesis, implicit feedback, incremental reading, topic granularity | Done |
| [knowledge-deduplication.md](knowledge-deduplication.md) | **Scalable deduplication**: embedding models, vector storage, semantic dedup, hierarchical comparison, claim matching, incremental updates — full architecture for 13K+ claims/year | Done |
| [knowledge-representation-novelty.md](knowledge-representation-novelty.md) | **Deep dive**: structured knowledge representation for novelty comparison — atomic fact decomposition, claim normalization, NLI-based entailment, proposition embeddings, non-factual knowledge, proposed architecture | Done |
| [article-synthesis-prior-art.md](article-synthesis-prior-art.md) | **Comprehensive survey**: products that synthesize multiple articles into combined views — news aggregators (Google News, Particle, Ground News, Artifact, Semafor), research tools (NotebookLM, Consensus, Elicit, Semantic Scholar), digest/newsletter tools (Feedly, Mailbrew, TLDR, Kagi, Readwise), search/report tools (Perplexity, Arc Search), DIY approaches (Fabric, GitHub projects), failure modes, and recommended synthesis patterns for Petrarca | Done |
| [multi-article-synthesis-systems.md](multi-article-synthesis-systems.md) | **Technical deep dive**: academic & algorithmic foundations for multi-article synthesis — MDS with attribution (PRIMERA, WebCiteS, FActScore), clustering (BERTopic, iFacetSum, TOMDS), cross-document alignment (QA-Align, CDA, event coreference), diff interfaces (CiteSee, Semantic Reader, NewsDiffs), GraphRAG/STORM, proposed 5-phase synthesis architecture | Done |
| [knowledge-diff-interfaces.md](knowledge-diff-interfaces.md) | **Knowledge-diff reading interfaces**: HCI literature survey on adaptive presentation (dimming, stretchtext, fisheye), skimming tools (Scim), diff patterns (Wikipedia, VS Code), progressive disclosure, and proposed interaction model for "skip to the new stuff" reading | Done |
| [knowledge-tracing-for-reading.md](knowledge-tracing-for-reading.md) | **Deep research**: adapting Knowledge Tracing (BKT, DKT, DKVMN, FSRS) from educational technology to model reader knowledge state from articles -- observation models for passive reading, KC granularity, forgetting/decay, preference tracing, proposed 6-layer architecture combining soft BKT with FSRS decay | Done |
| [topic-normalization-spec.md](topic-normalization-spec.md) | **Topic normalization & defragmentation**: canonical registry, LLM merge-or-create, periodic defrag, Otak lessons applied | Done |
| [article-selection.md](article-selection.md) | Algorithms for filtering/ranking/scoring articles | TODO |
| [spaced-attention.md](spaced-attention.md) | Matuschak & Haisfield's spaced attention concepts | Done |
| [progressive-summarization.md](progressive-summarization.md) | Tiago Forte's method + related approaches | TODO |
| [reading-ui-research.md](reading-ui-research.md) | CHI/HCI research on novel reading/triage UIs, gesture vocabularies, progressive disclosure | Done |
| [interaction-signals.md](interaction-signals.md) | Mobile interaction design for reading feedback | TODO |
| [voice-processing.md](voice-processing.md) | Soniox API integration, multilingual STT, Expo patterns | Done |
| [open-algorithms.md](open-algorithms.md) | Transparent, user-configurable ranking | TODO |

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
| [kindle-integration.md](kindle-integration.md) | Kindle data integration: APIs, highlights export, reading progress, Readwise middleware, practical plan | Done |

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
