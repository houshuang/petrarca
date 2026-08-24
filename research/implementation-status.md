# Petrarca: Current System State

**Last rewritten**: April 4, 2026 (session 45)
**Last updated**: August 24, 2026 (session 94: preserved-system restart + private Companion)
**For session-by-session history**: see `research/session-changelog.md`

> **Current product posture (Session 94).** The system below is preserved, not
> reset, but its generated review queue is no longer the default product
> contract. The active restart surface is a private HTTPS Companion: one exact
> old excerpt from firsthand speech, an intentional **Another/Context** action,
> and a browser recorder that retains raw audio and creates no cards, quizzes,
> or FSRS work. See [restart-plan-2026-08-24.md](restart-plan-2026-08-24.md).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ PRESERVED CLIENT (Expo SDK 54, React Native)                │
│ Old native/review UI remains in source and production data. │
│ Private Companion is a bookmarkable HTTPS page.             │
│                                                             │
│ 4 tabs: Review | Voice | Stats | More                       │
│ Review: landing screen, card stream + floating mic FAB      │
│ Voice: elicitation, capture, sweeps, notes                  │
│ Stats: structural progress, knowledge levels, heatmap       │
│ More: library, explore, projects, system settings            │
│                                                             │
│ State: module-level vars in store.ts → AsyncStorage          │
│ Sync:  content-sync.ts (manifest hash comparison + ?since=)  │
│ Lazy:  article-content.ts (in-memory + disk cache)           │
└────────────────┬────────────────────────────────────────────┘
                 │ HTTPS capability (exact routes only)
┌────────────────▼────────────────────────────────────────────┐
│ HETZNER VM                                                   │
│                                                             │
│ nginx :443 — public static/read-only allowlist + private      │
│              Companion exact-route proxy                     │
│ nginx :8083/:8084 — legacy public read-only/static surfaces  │
│ research-server.py 127.0.0.1:8090 — loopback API only        │
│ log_server.py :8091 — disabled legacy service                │
│                                                             │
│ petrarca.db (SQLite, WAL) — canonical data store             │
│ /opt/petrarca/data/ — JSON fallback + cache files            │
│   voice_elicit_cache/ — idempotent retry cache (24h TTL)     │
│ Root-only env files — no secrets in Git or public bundles    │
│ Daily verified DB + durable-audio backup; off-host point copy│
│ Content-refresh cron is disabled.                            │
└─────────────────────────────────────────────────────────────┘
```

## Content Numbers (production audit, Aug 24, 2026)

The canonical DB contains 36 transcript rows (about 35 distinct firsthand
records after duplicate handling), 895 transcript chunks, 265 knowledge items,
17 knowledge entities, 1,119 curriculum nodes, 590 structural cards / 2,434
positions, 1,279 microlearning-card rows, 4,849 quizzes, and 3,528 interaction
events. Only 11 structural cards, one microlearning card, and 25 distinct
microlearning quizzes were ever reviewed. These generated inventories are
preserved as archive/research material, not presented as a debt to clear.

## Private Companion (Session 94)

- `GET /companion` — standalone private page, served only through an unlogged
  nginx capability path;
- `POST /resurfacing/select` — one channel-neutral exact firsthand excerpt;
- `POST /resurfacing/context` — full canonical transcript on demand;
- `POST /resurfacing/event` — typed identifiers/metrics only, never transcript
  or free-text query content;
- `POST /commonplace/capture` — browser audio retained first, then Soniox
  transcription, `voice_transcripts(source='commonplace_capture')`, exact
  `raw_speech` chunks, and optional old-speech echoes.

`resurfacing_runs`, `resurfacing_run_items`, and `resurfacing_events` store
selection/delivery provenance without duplicating authored text. New capture
audio is mode 0600 under `data/audio/commonplace/`; the DB stores its durable
relative path. Browser recovery is capability-keyed AES-GCM ciphertext, and
audio-content IDs make upload retries idempotent. The route performs no
curriculum/entity learner-state updates, card generation, quiz generation, or
scheduling.

## App Screens

### Tab Screens (4 visible + 5 hidden)
| Screen | File | Visible | Role |
|--------|------|---------|------|
| **Review** | `(tabs)/index.tsx` | Yes (landing) | FSRS-6 review card stream. Status bar (due count, domains, progress). Floating mic FAB for quick voice capture. Rich narrative answers, memory hooks, 6 follow-ups, quiz suggestions, "Same topic" checklist, existing quiz listing. Multi-cue quizzes. Suspend via menu. Entity/date taps navigate to timeline. |
| **Voice** | `(tabs)/voice.tsx` | Yes | Hub for all voice features: Guided Recall (elicitation), Capture Voice (free-form), Knowledge Sweep, Voice Notes history. |
| **Stats** | `(tabs)/stats.tsx` | Yes | Rich stats: structural progress bars per domain (reviewed/total), knowledge level stacked bars (anchored/engaged/mentioned/unknown), 8-week activity heatmap, score distribution, card type breakdown pills. `/stats/native` endpoint. Link to full web dashboard. |
| **More** | `(tabs)/more.tsx` | Yes | Library (physical books, Kindle), Explore (knowledge map, timeline, ancient map), Tools (projects, activity log), System (user guide, feedback). |
| Feed | `(tabs)/feed.tsx` | Hidden | *Disabled (session 71)*. Was `index.tsx`. ContinueBar + ArticleRow list. |
| Library | `(tabs)/library.tsx` | Hidden | Accessible from More tab. Physical+Kindle books. |
| Topics | `(tabs)/topics.tsx` | Hidden | *Disabled*. Synthesis-led view. |
| Queue | `(tabs)/queue.tsx` | Hidden | *Disabled*. Reading queue. |
| Log | `(tabs)/log.tsx` | Hidden | Accessible from More tab. Activity timeline. |

### Stack Screens
| Screen | File | Role |
|--------|------|------|
| Reader | `reader.tsx` | Article reader — Full/Guided/New Only modes, paragraph dimming, briefing card |
| Synthesis Reader | `synthesis-reader.tsx` | 3-column "Restrained Folio" reader |
| Book Detail | `book-detail.tsx` | Book metadata, captures (photo/voice/text), curriculum context, chapter review, "Record what I remember" book-level recall |
| Add Book | `add-book.tsx` | Camera capture → Gemini identification |
| Knowledge Map | `knowledge-map.tsx` | Tree view of curricula with knowledge dots |
| Curriculum Scan | `curriculum-scan.tsx` | v2 card-based self-assessment (3-level) |
| Hamarquizen | `hamarquizen.tsx` | Book-specific PRIME→READ→TEST review |
| Voice Elicitation | `voice-elicitation.tsx` | Free recall voice prompts for curriculum nodes + chapter/book recall + era sweeps (SWEEP badge). "Know nothing" vs "Skip" buttons. Auto-loads more prompts when batch exhausted. Fire-and-forget uploads with `request_id` caching. |
| Defender | `defender.tsx` | Adversarial-retrieval debate (Pearl 4, Tibetan monastic debate). Thesis (text or audio) → 2-3 angled objections (empirical/methodological/contextual/contrarian/counterfactual) → defense (text or audio) → grade + follow-up → concluded. Optional domain scope chip-picker pulls from `/curriculum/list`. Session history. Server: `defender_engine.py`. |
| Commonplace | `commonplace.tsx` | Locke + Bjornstad resurfacing. Type or speak a prompt → top-N old `transcript_chunks` above similarity threshold, filtered by min_age_days. Age chips (>1mo/>3mo/>6mo/none) + threshold chips (loose/default/tight). Tap echo to expand surrounding context. Server: `commonplace_engine.py`. |
| Knowledge Sweep | `knowledge-sweep.tsx` | Full-domain voice recall assessment. Domain select → 7-era recording → parallel transcription → LLM scoring (Opus) → results with coverage/accuracy/connectivity/organization. System-vs-self comparison. |
| Voice Notes | `voice-notes.tsx` | Voice note list + playback |
| Kindle Browse | `kindle-browse.tsx` | Full Kindle library browser — search, filter (status/category/tracked), sort, pagination, include books, EPUB badge |
| Kindle Curation | `kindle-curation.tsx` | Triage screen for Kindle library |
| Projects | `projects.tsx` | Project list |
| Project Detail | `project-detail.tsx` | Project notes + voice routing |
| Review Session | `review-session.tsx` | Legacy review (may be unused) |
| Resurfacing | `resurfacing.tsx` | Cross-book resurfacing prompts |
| Landscape | `landscape.tsx` | Knowledge landscape visualization |
| Trails | `trails.tsx` | Learning trails |
| Map | `map.tsx` | Geographic/concept map |

### Key Components
| Component | Role |
|-----------|------|
| `ContinueBar` | Dark ink bar for in-progress article at feed top |
| `SynthesisScroll` | Horizontal synthesis cards with margin numbers |
| `ArticleRow` | Tabular article row with novelty badge + swipe gestures |
| `FeedSidebar` | Web: sticky sidebar with topic/source filters |
| `FeedFilterPills` | Mobile: topic + source filter pills |
| `ArticlePopover` | Web: hover popover for article links |
| `MarkdownLink` | Cross-platform link handling (web `<a>`, native `onPress`) |
| `MicButton` | Reusable record-stop button with timer. Used by Defender + Commonplace screens. Web-aware (hides itself). |
| `PetrarcaDrawer` | ✦ navigation drawer (must be added per tab screen). Includes Knowledge Sweep in Explore section. |
| `FeedbackCapture` | Global ✦ feedback button (voice + text + screenshot) |
| `VoiceUploadToast` | Global toast for background voice upload success/failure |
| `BookCurriculumContext` | Book-detail curriculum coverage section |
| `ChapterContext` | Chapter preview/review with temporal hooks |
| `EntitySheet` | Entity detail bottom sheet — backlinks, notes, "3 questions", "Research this", "View in timeline" |
| `KnowledgeExplorer` | Reusable 3-tab explorer: Timeline (century groups, era bands) / Persons (450) / Places (384) |
| `ExplorerCapture` | Voice/text entity note capture |
| `VoiceUploadToast` | Global toast for background voice upload success/failure |
| `SynthesisChat` | Inline chat modal for synthesis |
| `AspectCard` | Structural review: multi-signal per topic. Trust line ("3/4 known · due Thu"), Know All, reveal-then-mark, binary grading, type-specific mnemonics (temporal_anchor/role_chain/cause_effect/contrast/vivid_detail). |
| `SequenceCard` | Structural review: timeline with dot/connector layout, 2 rotating blanks, anchor positions dimmed, scale annotations between milestones ("— 46 years — roughly a human lifetime"). |
| `SynchronicCard` | Structural review: geographic layout (domain rows), 3 blanks, connection text per position. Tests cross-domain awareness at a single year. |
| `CastCard` | Structural review: cast of characters. Person-focused with event-specific roles. Anchor persons dimmed, 2-3 blanks by FSRS urgency, role + significance after reveal. Purple badge (#6B4C8A). |
| `CausalChainCard` | Structural review: causal chains with vertical arrows. Connection text shown only when both adjacent links visible. 2 blanks per card, first link always anchor. Brown badge (#8B5E3C). |

### Client Data Layer
| Module | Role |
|--------|------|
| `store.ts` | Feed ranking, filtering, state management. Module-level vars → AsyncStorage. |
| `content-sync.ts` | Incremental sync from server. Manifest hash comparison, `?since=` for articles. |
| `article-content.ts` | Lazy article content loading. In-memory + disk cache. Prefetch for offline. |
| `knowledge-engine.ts` | FSRS decay, claim classification, paragraph dimming, curiosity scoring |
| `book-store.ts` | Book + capture persistence. Reactive listeners (`onBookStoreChange`). |
| `interest-model.ts` | Topic-level interest tracking with Bayesian smoothing, 30-day decay |
| `queue.ts` | Reading queue with AsyncStorage persistence + content prefetch |
| `logger.ts` | Interaction event logging (`logEvent()`) — sends to `/log/events` (research-server.py :8090), dual-layer: SQLite `interaction_log` + JSONL |
| `voice-upload-service.ts` | Background retry of pending voice elicitation uploads on app foreground. 48h expiry. Idempotent via request_id. Failed uploads (422) kept on device for manual retry. |
| `upload-queue.ts` | Persistent background upload queue for book page photos with exponential backoff |
| `book-api.ts` | Book API client — `fetchKindleBrowse()`, `includeKindleBook()`, `curateKindleBook()`, `classifyKindleBooks()`, `gradeStructuralCard()`, `recordReviewResult()` |
| `types.ts` | `ArticleMeta`, `ArticleContent`, `Article`, `TopicSynthesis`, etc. |

## Server: Key Modules

### Core Infrastructure
| Script | Role |
|--------|------|
| `research-server.py` | HTTP server (:8090) — all API endpoints, LLM orchestration |
| `db.py` | SQLite schema + sync helpers (`sync_articles`, `sync_knowledge_index`, etc.) |
| `gemini_llm.py` | `call_llm()`, `call_chat()`, `call_with_search()`, `call_vision()`, `call_llm_tool()`. Default: gemini-3.1-flash-lite-preview. **Primary for interactive/user-facing LLM calls** (follow-up generation, targeted quizzes, article questions) — direct API, ~2-5s latency |
| `claude_llm.py` | Claude wrapper via `claude -p` subprocess. **Batch/pipeline only** — process spawn adds 5-15s overhead. Used for question generation, microlearning research, curriculum generation (Opus only) |
| `review_engine.py` | **FSRS-6 scheduling** (py-fsrs, desired_retention=0.80), `record_answer()` (+ **leech detection**: auto-suspend at 7 consecutive misses), `record_structural_answer()` (per-position FSRS for aspect+sequence+synchronic+cast+causal cards + **collateral exposure**: anchor positions get 30% FSRS credit), `generate_question()` (+ `_build_quiz_suggestions()`), `get_candidates()`, `process_voice_capture()` (knowledge graph ingestion from voice — **handles novel topics outside curricula**: extracts facts/wonderings → ML cards even when no curriculum nodes match), `run_voice_elicitation()` (recall assessment + era sweeps), multi-domain chapter mapping, cross-curriculum context & temporal cross-refs in question gen, **knowledge sweeps**: `run_era_sweep()`, `get_sweep_plan()`, `score_sweep()`, `get_sweep_gaps()`, `get_sweep_history()`, `_era_sweep_candidates()`, **knowledge profile**: `create_transcript_chunks()`, `get_learner_context()`, `get_learner_context_for_entity()`, `generate_domain_summary()` |
| `reprocess_transcripts.py` | One-off backfill: chunks existing voice_transcripts, embeds, links to nodes/entities, generates domain portraits |
| `curriculum_db.py` | **Runtime reads/writes** — `load_curriculum()`, `update_knowledge()`, `load_knowledge_states()`, `generate_review_stream()` (with nexus cards + structural card mixing + `_recency_boost()` helper applied to unreviewed knowledge_items + knowledge_entities, `4.0/(1+age_days/7)` continuous decay, never zero), `_mix_structural_cards()` (aspect + sequence + synchronic + cast + causal, **per-node book+voice evidence gate** (Session 85 replaces old ≥5 KI domain gate), domain-diverse via window function, **type round-robin** so first 5 structural slots = one of each type, **front-loaded rhythm** at merged pos 3/6/9/12/15 for first 10 items then every 3rd, STRUCTURAL_ONLY temp flag, `hidden` column filters speculative cards via `migrate_hide_speculative_structural.py`), `get_book_prescan()` |
| `curriculum.py` | Curriculum generation (Opus) + graph utilities. Generates JSON + inserts into SQLite. Entity tagging (Gemini Flash) + JSON entity index. NOT for runtime data |
| `bootstrap_entities.py` | Extracts rich entities (descriptions, Wikipedia, coordinates) from curricula via Gemini Flash → `shared_entities` + `entity_curriculum_links` SQLite tables. Run after curriculum generation for voice capture entity matching |
| `backfill_wikidata.py` | 4-pass Wikidata entity resolution: (1) deterministic scoring, (2) anchor-boosted re-pass, (3) Gemini Flash LLM disambiguation, (4) no-match rescue with alternate queries. Writes `entity_resolutions` audit trail + `entity_external_ids`. 528/590 entities resolved (89.5%). Session 78: resolver hardened with regnal-name variants (Karl↔Carl↔Charles etc.) and weak-match downgrade (type<0.5 + date<0.5 → ambiguous) |
| `merge_entity_dupes.py` | Find-and-merge duplicate entities sharing the same Wikidata QID. Safety classifier: SAFE (suffix-dupe, known-alias, of-place, regnal) vs REVIEW. SQL merge across 5 tables |
| `reprocess_voice_with_qids.py` | Standalone tool to resolve a voice transcript's entities to Wikidata QIDs. Validates resolver pipeline without touching live code |
| `migrate_wikidata_schema.py` | Idempotent schema migration: adds `wikidata_qid` column + `entity_resolutions` + `entity_external_ids` tables |
| `cleanup_stale_resolutions.py` | Remove stale/superseded resolution audit rows |
| `log_server.py` | Legacy interaction log collection (:8091) — replaced by `/log/events` in research-server.py |
| `server_log.py` | Dual-layer logging: `log_interaction()` (SQLite + JSONL), `log_client_events()` (batch JSONL parser) |
| `enrich_entities.py` | Entity enrichment batch: Gemini Flash extraction from card content → shared_entities dedup + insert |

### Pipeline (runs via cron every 4h)
| Script | Role |
|--------|------|
| `content-refresh.sh` | Orchestrator — runs all pipeline steps in sequence |
| `fetch_twitter_bookmarks.py` | Fetch bookmarks via twikit |
| `fetch_readwise_reader.py` | Fetch from Readwise Reader API |
| `build_articles.py` | Gemini Flash extraction → summary, claims, topics, entities, questions |
| `build_claim_embeddings.py` | MiniLM 384d embeddings via limbic.amygdala |
| `build_knowledge_index.py` | Claim similarities, article similarities, paragraph mappings, delta reports |
| `build_concept_clusters.py` | Graph-based spectral bisection clustering |
| `generate_syntheses.py` | Monolithic synthesis per cluster (server version) |
| `build_curriculum_embeddings.py` | Embed curriculum nodes, map article claims → nodes (0.65 threshold) |
| `extract_entity_concepts.py` | Entity concept extraction for articles |

### Books & Kindle
| Script | Role |
|--------|------|
| `process_kindle_books.py` | Kindle → unified book conversion (reads from SQLite) |
| `kindle_sync.py` | Kindle library sync from Mac SQLite DB |
| `amazon_library_scraper.py` | Amazon library scraper via agent-browser + Chrome cookies. Daily launchd job. |
| `book_research_agent.py` | Autonomous book research via Gemini+Search |
| `resurfacing_engine.py` | Cross-book resurfacing prompts |
| `extract_key_facts.py` | Key facts extraction from curriculum nodes |
| `generate_aspect_cards.py` | Generate aspect cards from key_facts: non-leaking titles + reverse cues via Gemini Flash. **~523 cards across 7 domains** (Sicily, Rome, Greece, Byzantine, Islamic, Music, Architecture). ~2234 positions total |
| `generate_sequence_cards.py` | Generate sequence cards from key_facts + entity dates: natural chronological sequences via Gemini Flash. **18 sequences, ~94 milestones** across 5 domains (Sicily, Rome, Greece, Byzantine, Islamic). Scale annotations via `generate_scale_annotations.py` |
| `generate_synchronic_cards.py` | Generate synchronic cards — cross-domain contemporaries at a single year. Finds well-reviewed anchors, queries shared_entities for contemporaries active at anchor year from other studied domains, generates via Gemini Flash with connection texts. **10 cards, 48 positions** spanning 734 BC – 1194 AD across 7 domains |
| `generate_cast_cards.py` | Generate cast of characters cards from nodes with ≥3 person-type entities via `entity_curriculum_links`. Gemini Flash generates event-specific roles + significance. **25 cards, 81 positions** across 8 domains |
| `generate_causal_cards.py` | Generate causal chain cards from significance/connection key_facts. 3-5 chains per historical domain with 4-7 links each. **14 chains, 63 links** across 5 domains (Greece, Rome, Sicily, Byzantine, Islamic) |
| `generate_quick_quizzes.py` | Generate diverse quiz types from key_facts: `date_reverse` (deterministic), `order` (deterministic pairs), `role` (Gemini Flash), `causal`/`location` (Gemini Flash). Dedup at 0.82 cosine. **4,724 quizzes** |
| `generate_aspect_mnemonics.py` | Batch Gemini Flash job: type-specific mnemonics for aspect positions keyed by hook_type (temporal_anchor/role_chain/cause_effect/contrast/vivid_detail). ~520 cards |
| `generate_scale_annotations.py` | Batch Gemini Flash job: historical-anchor gap comparisons between sequence milestones. Uses user's studied domains for personalized references. 18 cards, 76 annotations |
| `generate_from_suggestions.py` | Generate structural cards from approved `suggested_cards` entries via Gemini Flash. Supports sequence + synchronic types with entity-level overlap detection |
| `detect_card_suggestions.py` | Scan voice transcript entities for temporal sequences (same-domain, <200y gaps) + contemporaries (cross-domain, overlapping lifetimes) → `suggested_cards` table |
| `measure_collateral_exposure.py` | E3 experiment analysis: compare knew% for positions with/without prior collateral exposure. Reports sample sizes, flags when N < 20 |
| `optimize_fsrs.py` | FSRS-6 parameter optimizer — extracts review history from interaction_log, runs py-fsrs Optimizer. Requires `fsrs[optimizer]` (torch+pandas). Baseline: 0% improvement at 195 events |

### Experiments & Utilities
| Script | Role |
|--------|------|
| `experiment_*.py` (13 files) | Algorithm experiments (NLI, clustering, dedup, decay, etc.) |
| `synthesis_pipeline.py` | Multi-stage synthesis (local only, not on server) |
| `import_url.py` | Manual URL ingestion |
| `export_content_json.py` | Manual JSON export (removed from pipeline cron) |
| `verify_migration.py` | Deep semantic comparison for SQLite migration |

### Standalone Web Pages (served via `_serve_html_file()`)
| Page | URL | Role |
|------|-----|------|
| `statistics_dashboard.html` | `/stats/dashboard` | Comprehensive statistics: today's summary, knowledge state bars per curriculum, review/quiz stats (7d/30d/all), books in progress, voice elicitation recall distribution, activity timeline. All items linked to atlas/coverage/book pages. |
| `knowledge_atlas.html` | `/knowledge/atlas` | D3.js knowledge state visualization across curricula |
| `knowledge_growth.html` | `/knowledge/growth` | Longitudinal growth tracking: coverage timeline per domain, edge overlap trajectory (Goldsmith C metric), weekly review performance, stability trends. D3.js charts from `knowledge_transitions` + `network_metrics_log`. |
| `curriculum_graph.html` | `/curriculum/graph` | D3.js curriculum concept graph |
| `curriculum_timeline.html` | `/curriculum/timeline` | D3.js historical timeline per curriculum |

## API Endpoints (research-server.py :8090)

### Content API (`/api/*`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/articles` | All article metadata (ArticleMeta). `?since=` for incremental. |
| GET | `/api/article/:id` | Full article content (ArticleContent) |
| GET | `/api/knowledge-index` | Claim similarities, paragraph mappings |
| GET | `/api/clusters` | Concept clusters |
| GET | `/api/syntheses` | All syntheses |
| GET | `/api/manifest` | Content hashes for incremental sync |

### Ingestion
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/ingest` | Chrome clipper / manual URL ingestion |
| POST | `/ingest-youtube` | YouTube transcript ingestion |
| POST | `/ingest-email` | Email-to-article ingestion |
| POST | `/ingest-book` | Book ingestion |
| POST | `/ingest-note` | Reader note ingestion |
| POST | `/ingest-cancel` | Cancel pending ingestion |
| GET | `/ingest-status` | Ingestion progress |

### Review & Knowledge
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/curriculum/review/generate` | Generate review question for a knowledge item |
| POST | `/curriculum/review/result` | Record review answer (FSRS update) |
| POST | `/review/microlearning` | Generate microlearning card from research query |
| POST | `/review/microlearning/dismiss` | Dismiss card or individual quiz (card_id and/or quiz_id) |
| POST | `/review/batch-generate` | Batch generate questions for knowledge items |
| POST | `/review/follow-up/trigger` | Trigger microlearning from follow-up query |
| POST | `/review/follow-up/generate` | Generate sideways follow-up queries via Gemini Flash |
| POST | `/review/create-factual-quiz` | One-click create microlearning_quiz from key_fact suggestion (passes fact_id for linking) |
| POST | `/review/suspend-fact` | Suspend all quizzes sharing a fact_id ("Not interested in this fact") |
| POST | `/structural/grade` | Grade structural card positions (aspect + sequence + synchronic). Per-position FSRS scheduling. `{card_id, results: [{position_id, score}]}` |
| POST | `/log/events` | Client interaction event ingestion (replaces log_server.py:8091). JSONL body. Dual-layer: SQLite + JSONL. |
| GET | `/review/queue` | Review queue candidates |
| GET | `/review/stats` | Review statistics |
| POST | `/review/voice-elicit` | Voice free-recall elicitation (transcription + LLM). Supports curriculum nodes, `chapter:{id}:{num}`, and `book:{id}` node types. Auto-detects domain_id for book/chapter. Idempotent via `request_id`. |
| POST | `/review/voice-memo` | Voice memo for review item |
| GET | `/review/elicit-candidates` | Voice elicitation candidates (curriculum nodes + chapter recalls) |
| POST | `/review/elicit-know-nothing` | Record that user knows nothing about a topic (sets knowledge=unknown, confidence=0.8). Auto-detects domain for book/chapter node_ids. |
| GET | `/knowledge/sweep/domains` | Available domains for sweeping |
| GET | `/knowledge/sweep/plan/{id}` | Sweep plan for a domain (eras, node counts) |
| POST | `/knowledge/sweep/submit` | Submit full-domain sweep for scoring |
| GET | `/knowledge/sweep/gaps` | Gap analysis from sweep results |
| POST | `/knowledge/sweep/transcribe` | Transcribe sweep audio |
| GET | `/knowledge/sweep/history/{id}` | Sweep history for a domain |

### Entity
| POST | `/entity/tap` | Log entity tap, generate entity intro |
| POST | `/entity/questions` | Generate entity questions |
| POST | `/entity/research` | Entity research via Gemini+Search |
| POST | `/entity/notes` | Save user note about an entity |
| POST | `/explore/capture` | Voice/text capture → entity detection → curriculum node mapping → knowledge state updates, quiz generation, microlearning from wonderings. Full knowledge graph ingestion via `process_voice_capture()`. Supports `capture_type='insight'` for saving unverified theories/hypotheses — transcribes + links to curriculum nodes but skips all LLM analysis and processing. |
| GET | `/entities` | List all entities |
| GET | `/entity/:id` | Entity detail (includes user notes) |

### Books
| POST | `/book/identify` | Gemini Vision book identification |
| POST | `/book/ocr-toc` | OCR table of contents |
| POST | `/book/ocr-page` | OCR page photo |
| POST | `/book/upload-photo` | Upload book photo |
| POST | `/book/photo-results` | Get photo OCR results |
| POST | `/book/voice-note` | Upload voice note |
| POST | `/book/research` | Trigger book research |
| POST | `/book/chapter-insights` | Chapter insights generation |
| POST | `/book/story-so-far` | Story So Far briefing |
| GET/POST | `/book/sync` | Book + capture sync |
| POST | `/book/resurfacing/*` | Generate/respond/skip resurfacing prompts |
| GET | `/book/resurfacing/status` | Resurfacing status |

### Kindle
| POST | `/kindle/sync` | Sync Kindle library data |
| POST | `/kindle/include` | Include specific book from Kindle |
| POST | `/kindle/curate` | Curate Kindle library |
| POST | `/kindle/classify` | Classify Kindle books |
| POST | `/kindle/resolve-titles` | Resolve Kindle titles |
| GET | `/kindle/library` | Kindle library (filterable) |
| GET | `/kindle/recently-started` | Recently started Kindle books |
| GET | `/kindle/browse` | Full query: search, status/category/tracked filters, sort, pagination → `{books, total}` |
| POST | `/kindle/scan-epubs` | Scan server EPUBs, extract metadata, fuzzy-match to kindle_books |
| GET | `/kindle/highlights` | Kindle highlights |

### Curriculum
| POST | `/curriculum/generate` | Generate new curriculum |
| POST | `/curriculum/map-book` | Map book to curriculum |
| POST | `/curriculum/elicit/start` | Start knowledge elicitation |
| GET | `/curriculum/list` | List all curricula |
| GET | `/curriculum/graph-data` | Graph data for D3 visualization |
| GET | `/curriculum/graph` | Force-directed graph HTML |
| GET | `/curriculum/timeline` | Timeline visualization HTML |
| GET | `/curriculum/entity-index` | Entity index |
| GET | `/curriculum/book-context/:id` | Book-curriculum context |
| GET | `/curriculum/:domain` | Curriculum detail with knowledge annotations |
| GET | `/curriculum/:domain/coverage` | Curriculum coverage stats |
| GET | `/book/prescan/:id` | Book pre-scan: known/new nodes, missing prerequisites, cross-book overlaps |

### Admin (Entity Resolution)
| GET | `/admin/entity-queue` | HTML review page for unresolved/ambiguous entities |
| GET | `/admin/entity-queue-data` | JSON: latest-per-entity resolution data |
| GET | `/admin/entity/<qid>` | Consolidated entity view |
| POST | `/admin/entity/resolve` | Manual QID commit (409 on conflict) |

### Defender (Pearl 4 — adversarial retrieval)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/defender/start` | Begin a debate session. Body: `{thesis, domain_id?, node_id?, entity_name?}` → `{session_id, objections[], context_summary}` |
| POST | `/defender/respond` | Submit defense; receive grade + follow-up. Body: `{session_id, response_text, objection_index?}` → `{grade, next_move, follow_up?, conclusion?, status, knowledge_writes}` |
| POST | `/defender/transcribe` | Multipart audio → `{transcript}`. Used by both Defender + Commonplace screens; user edits transcript before submitting on Defender side. |
| GET  | `/defender/sessions[?limit]` | List recent sessions for history view |
| GET  | `/defender/sessions/{id}` | Full session detail with all rounds |

### Commonplace (Pearl 8 — Locke's commonplace book)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/commonplace/resurface` | Find old `transcript_chunks` matching query. Body: `{query_text, min_age_days?, threshold?, max_results?, exclude_transcript_ids?}` → `{echoes[], meta, event_id}` |
| POST | `/commonplace/resurface-audio` | Multipart audio → record-transcribe-search round-trip in one request |
| GET  | `/commonplace/events[?limit]` | Recent resurfacing queries (for tuning thresholds) |

### Other
| POST | `/chat` | Research chat |
| POST | `/research/topic` | Topic research |
| POST | `/research/explore` | Exploration research |
| POST | `/research/explore-batch` | Batch exploration |
| POST | `/feedback` | User feedback |
| POST | `/projects` | Create project |
| POST | `/projects/note` | Add project note |
| GET | `/projects` | List projects |
| GET | `/stats/dashboard` | Statistics dashboard HTML page |
| GET | `/stats/dashboard-data` | Dashboard stats JSON (today summary, knowledge per curriculum, review/quiz, books, voice, timeline, knowledge_profile) |
| GET | `/stats/native` | Native Stats tab JSON — structural progress per domain, knowledge levels, 8-week activity heatmap, score distribution, card type counts, item totals |
| GET | `/knowledge/profile/{domain_id}` | Domain knowledge portrait (cached, auto-regenerates if >24h stale) |
| POST | `/knowledge/profile/regenerate/{domain_id}` | Force-regenerate domain portrait |
| GET | `/knowledge/growth-data` | Growth tracking JSON: transitions, network metrics history, review performance, stability trends, current per-domain metrics |
| POST | `/knowledge/snapshot-metrics` | Compute and store network metrics for all domains (cron-ready) |
| GET | `/health` | Health check |

## SQLite Schema (petrarca.db)

39 tables organized into 9 areas:

**Content pipeline**: `articles`, `article_sections`, `atomic_claims`, `claim_similarities`, `nli_verdicts`, `article_similarities`, `article_novelty_matrix`, `paragraph_claim_map`, `article_curriculum_nodes`, `delta_reports`, `concept_clusters`, `near_duplicates`, `syntheses`, `pipeline_meta`, `cluster_meta`

**Books & Kindle**: `physical_books`, `book_captures`, `book_curriculum_mappings`, `kindle_books`, `available_epubs`

**Curriculum & Knowledge**: `curriculum_domains`, `curriculum_nodes`, `curriculum_prerequisites`, `knowledge_states`, `knowledge_items`, `knowledge_entities` (Session 76: entity-first, parallel to knowledge_items; Session 78: `wikidata_props_json` column for cached Wikidata structured properties), `timeline_entries`, `shared_entities` (with `wikidata_qid`), `entity_curriculum_links`

**Entity Resolution**: `entity_resolutions` (append-only audit trail — every Wikidata resolution decision with candidates, confidence, reasoning, supersede chain), `entity_external_ids` (1906 VIAF/GND/GeoNames/Pleiades/Getty/MusicBrainz/BnF/LCCN IDs harvested from resolved entities)

**Review & Microlearning**: `review_items`, `microlearning_cards`, `microlearning_quizzes` (fact_id + rich_answer columns for multi-cue linking)

**Knowledge Profile**: `transcript_chunks` (embedded voice pieces), `chunk_node_links` (chunks↔nodes), `chunk_entity_links` (chunks↔entities), `domain_knowledge_summaries` (per-domain portraits)

**Knowledge Growth Tracking**: `knowledge_transitions` (event log of level changes with timestamps), `network_metrics_log` (periodic snapshots of node coverage, edge overlap, density per domain), `knowledge_sweeps` (domain-wide voice recall assessments with per-era scores, node-level results, correction/timeline feedback)

**Interaction Logging**: `interaction_log` (dual-layer with JSONL — event, item_id, score, session_id, response_ms, card_type, domain, node_title, extra)

**Defender + Commonplace** (Session 92): `defender_sessions` (one row per debate, JSON `rounds` log, optional domain/node/entity scope, status active/concluded), `commonplace_events` (every resurfacing query: text, source manual/audio, audio_bytes, returned chunk_ids, count) — tuning data, not load-bearing.

**Other**: `projects`, `project_notes`, `voice_transcripts` (now includes `source='defender_response'` rows from Session 92, embedded into `transcript_chunks` and findable by commonplace queries — defender writes feed back into the same retrieval substrate as voice elicitation/capture)

**Key relationships**: `atomic_claims` uses composite PK `(article_id, id)`. `knowledge_items` is the review data source. `microlearning_quizzes` holds individual quiz questions from ML cards, each independently FSRS-scheduled — the ML card is a content container, quizzes are the review atoms. All scheduling tables have `fsrs_card_json TEXT` for py-fsrs Card state. Voice uploads use `request_id` for idempotent retry caching. `curriculum_db.py` reads from SQLite; `curriculum.py` reads from JSON.

## Algorithm Parameters (experiment-validated)

### Claim Similarity
- **KNOWN**: ≥ 0.82 cosine (MiniLM 384d)
- **EXTENDS**: ≥ 0.74
- **NLI cascade**: 0.74–0.82 zone, 59% accurate (consider disabling)
- **FORGOTTEN**: retrievability R < 0.3

### Article Similarity
- Weighted 0.5×summary + 0.5×claims via `find_similar_documents()`
- Calibrated on 18 human + 300 LLM-rated pairs: AUROC=0.930, 94% accuracy, ρ=0.818
- **Briefing card**: 0.52, **Feed ranking**: 0.49, **Dedup**: 0.64
- Ground truth: `scripts/ground-truth/`, config: `threshold_config.json`

### Quiz Dedup
- MiniLM 384d cosine via limbic, threshold ≥ 0.82 (same as claim KNOWN)
- Checked against all existing `microlearning_quizzes` + curriculum `key_facts`
- Similarity scores logged: `journalctl -u petrarca-research | grep quiz-dedup`
- Calibration review scheduled ~2026-04-18

### Curriculum Mapping
- Article claim → curriculum node: ≥ 0.65 cosine (broader than claim-claim)
- Active book feed boost: +0.15
- Multi-domain chapter mapping: top-2-3 curricula with book similarity score ≥ 0.40
- Gap-fill: prerequisites only (siblings removed), enriched with book_curriculum_mappings when available
- Gap-fill scoring: -5.0 penalty, capped at 3 per review batch

### Review Scheduling (FSRS-6)
- **Algorithm**: py-fsrs 6.3.0, `desired_retention=0.80`, `learning_steps=()`, `relearning_steps=()`
- **Grade mapping**: knew→Easy (~8.3d initial stability, ~28d first due), partly→Good (~2.3d, ~8d), missed→Again (~0.2d, ~1d)
- **Easy progression**: 8.3d → 13d → 20d → 30d → ... stability
- **FSRS card state**: stored as `fsrs_card_json` JSON column on all scheduling tables
- **Article novelty**: binary seen/unseen (NOT FSRS-based)

### Feed Scoring
- Curiosity peak: 70% novelty, Gaussian σ=0.15
- Synthesis coverage: ≥80% → hide from feed, ≥50% → demote

### Pipeline
- Extraction model: gemini-3.1-flash-lite-preview (5% factual claim rate)
- Curriculum generation: Opus only (Gemini Flash quality rejected)

### Reader
- 3 modes: Full / Guided / New Only
- Familiar paragraph opacity: 0.55

## Deployment

### Commands
```bash
# Mobile + server (the ONLY correct deploy):
git add . && git commit && git push origin main
bash ~/src/expo/scripts/deploy.sh petrarca

# Web (optional, for cache busting):
bash app/deploy-web.sh

# Native rebuild (only for new native modules):
cd app && eas build --profile development --platform ios
```

### Infrastructure
- SSH: `ssh alif`
- nginx :8083 (content JSON), :8084 (web app static)
- research-server.py :8090 (API + interaction logging via /log/events)
- log_server.py :8091 (legacy — replaced by /log/events)
- Cron: `/etc/cron.d/petrarca-refresh` (every 4 hours)
- DuckDNS: `/etc/cron.d/duckdns` (every 30 min)
- Config: `~/src/expo/config.json` (ports, services, paths)
- Server env: `/opt/petrarca/.env` (GEMINI_KEY, ANTHROPIC_KEY)
- limbic: `/opt/limbic` (rsynced by deploy.sh, editable-installed in venv)

## Known Issues & Gaps

1. **Screens possibly unused**: `review-session.tsx`, `resurfacing.tsx`, `landscape.tsx`, `trails.tsx`, `map.tsx` — may be stubs or superseded
2. **synthesis_pipeline.py** not deployed to server — still uses monolithic `generate_syntheses.py`
3. **NLI cascade** (59% accurate) — may be adding noise rather than signal
4. **knowledge-engine.ts** still has full FSRS code — intended to simplify to binary seen/unseen for articles
5. **No centralized error boundaries** in React Native
6. **Podcast ingestion** — sync script built (`podcast_sync.py`), server endpoint exists (`/media/sync`), but no transcript fetching, no article pipeline integration, and episodes only go to flat JSON file (not SQLite). See session-changelog podcast integration section for details.
7. **466 curriculum nodes** with no knowledge_items — need discovery probes (multi-domain mapping will help activate more)
8. **Key_facts only extracted for Sicily Greek** — remaining 8 curricula + 6 Sicily areas pending
9. **3 curricula inactive** (AP European, AP World History Modern, Ancient & Classical World) — generated but no books mapped, 0 knowledge_items
10. **Nexus cards not yet rendered in client** — `type: 'nexus'` cards returned in review stream but client review.tsx doesn't have a renderer for them yet
11. **Book prescan not yet surfaced in UI** — endpoint works (`/book/prescan/:id`) but no client integration
