# Petrarca Research Index

Master index of all research documents. **Always update this file when adding new research.**

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
| [knowledge-modeling.md](knowledge-modeling.md) | Modeling user knowledge and interests | TODO |
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
| [user-journey-weeks.md](user-journey-weeks.md) | Detailed 4-week user journey narrative, grounded in interviews + design research | Done |
| [user-guide.md](user-guide.md) | **User guide** — capture flows, reading modes, integrations, non-obvious features, hypotheses to test | Done |
