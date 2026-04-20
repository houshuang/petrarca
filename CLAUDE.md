# Petrarca — Quiz-First Knowledge Retention App

A mobile-first knowledge retention app combining structural review cards, voice input, and user knowledge modeling. Named after Francesco Petrarca, pioneer of systematic reading methods. Built for one power user (Stian), not a social platform.

**Frontend**: Expo SDK 54 (React Native), review-first layout. **Backend**: Hetzner VM — nginx (:8083 content, :8084 web), research-server.py (:8090). **Data**: SQLite (petrarca.db, canonical). **Design doc**: `research/structural-review-redesign.md`

## DISABLED SUBSYSTEMS (Session 71, 2026-04-14)

The following code is **preserved but disabled**. Do NOT build features on top of, maintain, or fix bugs in these subsystems unless explicitly asked:

- **Feed tab** (`app/(tabs)/index.tsx`) — read-later article discovery, disabled
- **Article ingestion** (`scripts/build_articles.py`, `scripts/import_url.py`) — no feed to populate
- **Twitter bookmark fetch** (`scripts/fetch_twitter_bookmarks.py`) — content source disabled
- **Readwise sync** (`scripts/fetch_readwise_reader.py`) — content source disabled
- **Email ingestion** (`research-server.py _handle_ingest_email()`) — content source disabled
- **Kindle sync launchd** (`scripts/com.petrarca.kindle-sync.plist`) — book progress not critical
- **Amazon scraper** (`scripts/amazon_library_scraper.py`) — metadata enrichment disabled
- **Podcast sync** (`scripts/podcast_sync.py`) — not integrated into review
- **Synthesis reader** (`app/app/synthesis-reader.tsx`) — depends on article pipeline
- **Article reader** (`app/app/reader.tsx`) — depends on article pipeline
- **Reading trails** (`app/app/trails.tsx`) — depends on article pipeline
- **Landscape view** (`app/app/landscape.tsx`) — article visualization
- **Queue tab** (`app/(tabs)/queue.tsx`) — article queue
- **Topics tab** (`app/(tabs)/topics.tsx`) — article topics
- **Standalone HTML visualizations** (`scripts/knowledge_atlas.html`, `knowledge_growth.html`, etc.) — moving to native app

**Active subsystems**: Review stream, voice elicitation/capture, physical books + curriculum mapping, curriculum generation, entity system + Wikidata resolution, microlearning cards, FSRS scheduling, interaction logging.

## Design Principles & North Star

These principles are the intellectual foundation of the project. They override implementation convenience. Read the linked docs when making design decisions beyond bug fixes.

1. **"Hooks, not facts."** Reading success = building frameworks (Caesar, Alexander, Charlemagne), not fact-drilling. The system builds scaffold knowledge that makes everything you read richer. *(research/design-vision.md)*

2. **"I'll manage your memory."** The fear of forgetting stops reading nonfiction. Like Michel Thomas: the system takes responsibility for retention so the user can focus on reading. Frame knowledge maps as positive progress, never anxiety-inducing gaps. *(memory/feedback_michel_thomas.md)*

3. **Comprehension before memory.** Ensure understanding before testing (Matuschak's key finding). SRS-style flashcards fail for conceptual knowledge — we need elaborative retrieval, connection-based resurfacing, spreading activation. *(research/andy-matuschak-research.md, research/beyond-flashcards-knowledge-retention.md)*

4. **Atomic claims are the fundamental unit.** Not articles, not words. Claims enable cross-article tracking, knowledge state management, and novelty detection. Delta-only reports show what's new since last read. *(research/novelty-system-architecture.md)*

5. **Curriculum as bridge.** Don't match claims directly across sources. Curriculum nodes (50-80 per domain, Opus-generated) are the organizing principle — they connect books, articles, and review into a coherent structure. *(research/overlapping-curricula-vision.md)*

6. **Temporal hooks are the key retention mechanism.** Priority: (1) anchor to known events, (2) same-moment connections, (3) causal chains, (4) cross-domain surprises only if the reader knows the other domain. *(memory/feedback_temporal_hooks.md)*

7. **Facts first, then concepts.** Dates, key figures, key events are load-bearing scaffolding. Generate factual questions DETERMINISTICALLY from structured `key_facts` data. Only use LLM for rich answers and analytical questions. Never delegate to LLM what can be computed from structure. *(memory/feedback_rules.md § Knowledge System Design)*

8. **Books encode, system maintains.** Books provide initial encoding through narrative/structure. Maintaining and integrating knowledge is the system's job. Not SRS — but real decay exists. Voice dumps as knowledge elicitation. *(memory/feedback_knowledge_encoding.md)*

9. **Curiosity zone at 70% novelty.** Articles with ~70% novel claims + ~30% familiar context are most engaging (zone of proximal development). "Most novel" ≠ "most interesting." *(research/experiment-results-report.md)*

10. **Dim familiar, don't hide.**

11. **Cards are mini-encyclopedias.** Microlearning card content MUST include primary sources (who wrote about this), material evidence (what survives, where to visit), and cultural artifacts (art, opera, literature). Follow-up queries go SIDEWAYS (geography, counter-narratives, structural causes) — not deeper into what the card already said. Familiar paragraphs at 0.55 opacity, not hidden. Constrained highlighting (150 words) improves comprehension 11-19% over highlighting everything (CHI 2024). *(research/knowledge-diff-interfaces.md)*

**Flag design drift proactively.** If implementation diverges from these principles, raise it before the user discovers it.

## Where to Look

| Working on... | Read first |
|--------------|-----------|
| **v2 Redesign (START HERE)** | `research/structural-review-redesign.md` — Quiz-first app, structural cards, 8-phase plan, experiments, open questions |
| **Any feature work** | `research/implementation-status.md` (architecture, screens, scripts, endpoints, algorithms) |
| **UI changes** | `design/DESIGN_GUIDE.md` — MUST READ. "The Annotated Folio" Renaissance visual language. |
| **Review/retention** | `research/review-system-architecture.md`, `research/reading-companion-process-design.md`, `research/unified-scoring-design.md` (entity weight tuning + E5 baseline) |
| **Structural cards** | `generate_aspect_cards.py`, `generate_sequence_cards.py`, `generate_synchronic_cards.py`, `generate_cast_cards.py`, `generate_causal_cards.py` (generation — all gate on per-node/domain book+voice evidence), `generate_aspect_mnemonics.py` (type-specific mnemonics batch), `generate_scale_annotations.py` (sequence gap comparisons batch), `migrate_hide_speculative_structural.py` (Session 85 migration: adds `hidden` column, flags cards lacking evidence), `curriculum_db.py` `_mix_structural_cards()` (stream mixing, **per-node book+voice evidence gate** (Session 85 replaces old ≥5 KI domain gate), **front-loaded rhythm** (FRONTLOAD_UNTIL=10, FRONTLOAD_INTERVAL=2 — structurals at merged pos 3/6/9/12/15 for first 10 items, then every 3rd), domain diversity, type round-robin so first 5 structural slots = one of each type, STRUCTURAL_ONLY flag), `review_engine.py` `record_structural_answer()` (FSRS + collateral exposure for anchors), `AspectCard.tsx` (trust line + mnemonics), `SequenceCard.tsx` (scale annotations), `SynchronicCard.tsx`, `CastCard.tsx`, `CausalChainCard.tsx` (components) |
| **Microlearning cards** | `review_engine.py` (MICROLEARNING_PROMPT, _run_microlearning_research), `curriculum_db.py` (generate_review_stream ML mixing), `generate_quick_quizzes.py` (batch quiz generation: date_reverse, order, role, causal types) |
| **Curriculum/entities** | `research/entity-first-architecture.md` (PROPOSED: entity-first with curriculum as overlay), `research/curriculum-system-audit.md` (audit + code paths), `research/overlapping-curricula-vision.md`, `research/entity-profiles-design.md` |
| **Wikidata/entity resolution** | `research/wikidata-deployment-guide.md` (runbook), `scripts/backfill_wikidata.py` (4-pass pipeline), `scripts/merge_entity_dupes.py`, `scripts/reprocess_all_transcripts.py` (voice transcript entity backfill). Admin: `/admin/entity-queue` |
| **Card suggestions** | `scripts/detect_card_suggestions.py` (voice entity → sequence/synchronic suggestions), `scripts/generate_from_suggestions.py` (approved → structural cards via Gemini Flash), `suggested_cards` table, `GET /admin/suggested-cards`, `POST /admin/suggested-cards/approve`, `POST /admin/suggested-cards/reject` |
| **Synthesis** | `research/synthesis-pipeline-design.md`, `memory/feedback_synthesis_design.md` |
| **Books** | `research/book-companion-handoff.md`, `research/book-companion-experiments.md` |
| **Voice recall** | `voice-elicitation.tsx` — Know Nothing + Skip, book/chapter/curriculum recall, auto-loads more. Server: `review_engine.py` `run_voice_elicitation()`. Voice capture: domain routing (Gemini) + background Wikidata entity resolution |
| **Historiographic/insights** | `research/historiographic-knowledge-design.md` (theories, debates, attributed claims — layered proposal). Voice capture `source='insight'` in `review_engine.py`. |
| **Knowledge atlas** | `scripts/knowledge_atlas.html` (standalone D3 web viz), `curriculum_db.py` `get_knowledge_atlas_data()`, served at `/knowledge/atlas` |
| **Knowledge growth** | `scripts/knowledge_growth.html` (D3 viz), `curriculum_db.py` (`compute_network_metrics`, `get_knowledge_growth_data`), `research/knowledge-growth-measurement-proposal.html` |
| **Feed/ranking** | `research/novelty-system-architecture.md` |
| **Deep "why"** | `research/design-vision.md` (master synthesis of all interviews + research) |
| **Research index** | `research/README.md` (50+ docs, tiered reading guide) |
| **Past sessions** | `research/session-changelog.md` |

## Working on This Codebase

This project is exploratory — 60+ sessions in many directions. That means:

1. **There is stale code.** Dead imports, unused tables, deprecated modules. Don't assume everything exists for a reason. Verify before building on it.
2. **Trace data flows before changing them.** Where does it write → what store → who reads → what displays? Critical bugs came from write/read mismatches (JSON vs SQLite).
3. **Test endpoints before telling user to test.** `curl` with realistic data after server changes. Deploy mobile after client changes. "It should work" is not verification.
4. **Clean up what you touch.** Remove dead code, unused imports, stale data when you encounter them.
5. **Diagnose before patching.** Read the full error, check concurrency, understand architecture. One correct fix beats four incremental attempts.

## User triggers (natural language)

When the user says something matching one of these — even loosely — run the associated runbook immediately.

### "I've recorded a voice, do the calibration" (or: "run the voice calibration", "check my new capture", "calibrate the voice capture")
1. Verify the newest `voice_capture` / `voice_capture_entity` row arrived cleanly:
   ```
   ssh alif "sqlite3 /opt/petrarca/data/petrarca.db \"SELECT id, source, input_mode, length(transcript) AS tlen, substr(transcript,1,140) FROM voice_transcripts WHERE source IN ('voice_capture','voice_capture_entity') ORDER BY created_at DESC LIMIT 3\""
   ```
   The newest row should have `input_mode='audio'`. If it's `text_json` or `NULL` (on a row created *after* 2026-04-20), investigate the provenance-stamping path in `_handle_explore_capture` + `process_voice_capture`.
2. Open `http://alifstian.duckdns.org:8090/voice/calibration?limit=5` (use `agent-browser` to load + screenshot if headless). The new row should show the 🎙 audio badge.
3. Use the new capture as ground truth to investigate the pipeline gaps logged in `research/session-changelog.md` § Session 86 (entity-path multicue coverage, unrouted facts, wonderings-never-carded, knowledge_items.sources provenance asymmetry, book-sourced KIs lack `memory_hook`). Pick whichever the new capture illustrates most clearly.
4. Report findings; don't start refactors without checking in.

Background: Session 86 (2026-04-20) cleaned up 9 synthetic `voice_capture` rows that prior agents had POSTed as text for pipeline validation. User recorded a fresh real audio capture after that session for calibration; this runbook picks up there.

## Critical Rules

### Data Store Discipline
- **SQLite is the ONLY data store** for knowledge states, review items, and all runtime data
- **Review stream pipeline**: `generate_question()` → `cached_question` JSON on `knowledge_items` (includes rich_answer, memory_hook, 6 follow_up_queries via Gemini Flash, quiz_suggestions from key_facts) → `generate_review_stream()` in `curriculum_db.py` assembles cards (with nexus cards + related_facts checklist + existing_quizzes listing) → client `review.tsx`. Microlearning cards flow separately: `_run_microlearning_research()` → `microlearning_cards` table → mixed into stream.
- **Multi-cue quiz generation**: On grading a knowledge_item, background thread calls `generate_multicue_quizzes()` → Gemini Flash generates 2-4 alternate retrieval cues per key_fact (date/event/person types only). All cues for one fact share `fact_id` + `rich_answer` (shared detail card). Dedup at 0.82 cosine via limbic. Suspend all cues for a fact via `POST /review/suspend-fact`.
- **Review card features**: ⋯ menu (About this card, Bad question, Suspend), origin badge (📖/🔗/🎙/🔍/💬/🔷 — Session 78 added 💬 unresolved entity + 🔷 Wikidata-linked entity), instant fade transitions, session-tracked graded IDs (no re-showing within 60s), generic entity filtering (`_GENERIC_ENTITIES`), "Same topic" related_facts checklist, factual quiz suggestions (fire-and-forget creation via QuizSuggestions component), "Quizzes for this topic" existing quiz listing. Card provenance data (origin, scores, scheduling state) attached to every card from server. About-this-card modal shows voice-capture source excerpts + Wikidata QID for entity_capture items (Session 78).
- **Structural cards (5 types)**: `structural_cards` table (~523 aspect, 18 sequence, 10 synchronic, 25 cast, 14 causal) + `structural_positions` table (~2434 positions). Generation via `generate_aspect_cards.py`, `generate_sequence_cards.py`, `generate_synchronic_cards.py`, `generate_cast_cards.py`, `generate_causal_cards.py` (Gemini Flash). **Activation-gated**: aspect cards require ≥5 knowledge_items in domain, sequence cards additionally require ≥3 reviewed aspect positions, synchronic cards require ≥5 KI in anchor domain. Domain-diverse selection via `ROW_NUMBER() OVER (PARTITION BY domain_id)`. **Type round-robin (Session 84)**: structural items reordered after build so first 5 slots in any session are aspect → sequence → synchronic → cast → causal, then repeats. Without this, all aspect cards appeared first and rare types got pushed past where most sessions ended. Currently active: Sicily, Rome, Greece, Byzantine, Islamic, Classical Reception, Philosophy. `STRUCTURAL_ONLY=False` (normal mixed stream). `POST /structural/grade` endpoint → `record_structural_answer()` in `review_engine.py` for per-position FSRS. **Collateral exposure (Session 81)**: anchor positions (visible but not tested) get 30% FSRS stability credit, logged as `collateral_exposure`. **Trust line (Session 83)**: AspectCard shows "3/4 known · 'What year?' due Thu" from position FSRS state. **Type-specific mnemonics (Session 83)**: 5 strategies (temporal_anchor/role_chain/cause_effect/contrast/vivid_detail) via `generate_aspect_mnemonics.py`. **Scale annotations (Session 83)**: sequence gap comparisons ("— 46 years — roughly a human lifetime") via `generate_scale_annotations.py`, stored in `question_variants.scale_to_next`. Client: `AspectCard.tsx` (trust line + mnemonics), `SequenceCard.tsx` (scale annotations), `SynchronicCard.tsx`, `CastCard.tsx` (person-in-role identification with question variants), `CausalChainCard.tsx` (why-testing with connection visibility logic).
- **Entity-keyed knowledge items (Session 76 Phase 1, Session 77 cleanup, Session 78 Phase 2)**: `knowledge_entities` table parallel to `knowledge_items`, keyed by entity slug (`ent:{slug}`) instead of `{domain}:{node_id}`. Used when voice captures can't route to curriculum nodes (novel topics). Same FSRS/cached_question/key_facts schema. Voice capture entity path in `_process_voice_capture_entity_path()` fires when (a) no candidate curriculum nodes OR (b) curriculum LLM returns `node_assessments=[]`. Uses `VOICE_CAPTURE_ENTITY_PROMPT` that groups facts by entity name AND outputs an `entity_types` map ({"Karl XII of Sweden": "person", ...}) with explicit canonical-naming rules (strip parentheticals, strip honorifics unless canonical, prefer common English spellings). The entity path fires its own background Wikidata resolution; the curriculum path's resolution thread is **skipped** when the entity path triggered (avoids 2× LLM/Wikidata cost — guarded by `entity_path_triggered` flag). Entity items render in review stream as `type:'review'` through existing `ReviewCard` with `provenance.origin='entity_capture'` and `knowledge_weight=6.0`. `generate_entity_question()` now also calls `_generate_follow_up_queries()` so entity cards get the same sideways "Also explore…" chips as curriculum cards. **Phase 2 (Session 78)**: `generate_entity_question()` builds a three-signal context block for `_ENRICH_PROMPT`: (1) Wikidata structured properties via `_fetch_wikidata_props()` (per-type P22/P26/P39 for persons, P710/P276 for battles, etc.), cached in `wikidata_props_json` column with 90d TTL; (2) scoped temporal neighbors via `_get_scoped_temporal_neighbors()` (±50y window, only entities the user has in `knowledge_entities` or `knowledge_items`); (3) voice co-occurrence via `_get_voice_cooccurring_entities()`. Enrichment STRICT RULE: never assert Wikidata facts user didn't capture — frame as retrieval prompts. Stretch UX: origin badge (💬 unresolved / 🔷 Wikidata-linked), voice-capture source excerpts + QID in About-this-card modal, `_build_entity_capture_intros()` inserts entity_intro before first review when description ≥20 chars. See `research/entity-first-architecture.md` and `research/session-77-observations.md`.
- **Review scheduling**: FSRS-6 via py-fsrs (`desired_retention=0.80`, `learning_steps=()`, `maximum_interval=3650`). Grade mapping: knew→Easy (~28d), partly→Good (~8d), missed→Again (~1d). All scheduling tables have `fsrs_card_json` column. **ALL scheduling MUST go through `record_answer()`, `record_structural_answer()`, or `_fsrs_reschedule()`** — never raw SQL arithmetic on `stability_days`/`due_at`. **Leech detection (Session 81)**: 7 consecutive misses → auto-suspend 30 days + clear cached_question. FSRS optimizer (`scripts/optimize_fsrs.py`): 0% improvement at 195 events — re-run at 500+.
- **Review scheduling priority**: SR cards first (book-sourced highest, gap-fill penalized -5.0 and capped at 3/batch). ML cards interleaved by `source_type`: voice_wondering/correction at 1:3, follow_up at 1:7. Never front-load ML cards.
- **Unreviewed-item recency boost (Session 85)**: `_recency_boost(created_at_ms, now_ms)` in `curriculum_db.py` returns `4.0 / (1.0 + age_days/7.0)` — continuous decay, never reaches zero. Applied ONLY when `review_count == 0` in both `knowledge_items` and `knowledge_entities` scoring loops. Once FSRS takes over, no boost is added (avoids double-counting with scheduling). Surfaced in `_provenance.recency_boost` so the About-this-card modal can show why a card was prioritized. Replaces the old hard-cutoff formula that zeroed at 48h.
- **Voice elicitation → knowledge_items**: `run_voice_elicitation()` creates knowledge_items for nodes that don't have one yet (14-day initial stability). Uses `confidence_tagged` to create `correction` ML cards for wrong facts. Does NOT create ML cards from missed facts (user prefers reading to fill gaps).
- **Voice capture dedup**: `process_voice_capture()` checks SHA-256 hash of transcript text before processing — prevents duplicate ingestion of same podcast/voice note.
- **Voice capture domain routing**: When entity matching finds <5 linked nodes, Gemini Flash picks top-3 curriculum domains → all nodes from those domains become candidates. Fixes novel-entity transcripts (e.g., Rollo/Normandy). Background thread then resolves `entities_mentioned` to Wikidata QIDs via `_resolve_voice_entities_background()`.
- **Voice capture novel topics**: When no curriculum nodes match (e.g., podcast about Iran crisis, Norman France), the pipeline still extracts facts + wonderings and creates ML cards from them. Prompt explicitly requires fact/wondering extraction regardless of node matching. Fallback ML creation when 0 `node_assessments` but facts exist.
- **Wikidata entity resolution**: `shared_entities.wikidata_qid` (92.2% coverage, 568/616). Date coverage: 486/590 (82.4%) after Session 79 backfills. Audit trail in `entity_resolutions` table (1,429 total: 1,301 backfill + 94 voice + 34 other). External IDs in `entity_external_ids` (1906 VIAF/GND/GeoNames/etc.). Admin review at `/admin/entity-queue`. **Session 78 hardening** (limbic `e7d8498`): `REGNAL_NAME_VARIANTS` retry (Karl↔Carl↔Charles etc. for regnal-shaped mentions) + `_is_weak_structural_match()` downgrade (type<0.5 + date<0.5 → ambiguous instead of accepting wrong matches). `_coerce_year()` in voice resolver defensively handles Gemini returning date strings. See `research/wikidata-resolution-quality.md` for failure-mode documentation.
- **Voice transcript reprocessing (DONE)**: `scripts/reprocess_all_transcripts.py` backfilled all 10 voice_capture/entity_capture transcripts. 94 voice resolutions, 87 with QIDs, 29 new entities created. Script is idempotent. Must stop research server before running (SQLite write lock).
- **Card suggestion detection**: `scripts/detect_card_suggestions.py` scans voice entities → temporal sequences (same-domain, <200y gaps) + contemporaries (cross-domain, overlapping lifetimes) → `suggested_cards` table. Admin: `GET /admin/suggested-cards`.
- **Interaction logging**: Dual-layer via `/log/events` endpoint — SQLite `interaction_log` table + JSONL files. Server-side logging on both grading endpoints. Client sends via `logger.ts` to `:8090/log/events`.
- **Multi-domain chapter mapping**: `create_review_items_for_chapter()` maps against top-2-3 curricula (similarity >= 0.40), not just one domain. Cross-curriculum context + temporal cross-refs injected into question generation.
- **Book pre-scan**: `GET /book/prescan/{book_id}` shows known/new/missing nodes + cross-book overlaps.
- **`curriculum_db.py`** for ALL runtime reads/writes. **`curriculum.py`** is ONLY for generation/CLI.
- **Knowledge levels only upgrade**: unknown → mentioned → engaged → anchored. Never downgrade.
- **Server-first**: All data lives on server. Local storage is cache only.

### Deploy
- **Commit + push first**, then `bash ~/src/expo/scripts/deploy.sh petrarca`
- **After ANY `app/` change**: deploy mobile immediately
- **Web**: `bash app/deploy-web.sh` (optional, for cache busting)
- **NEVER**: rsync to server, `git clean` on server, skip `deploy.sh`
- See `memory/feedback_rules.md` for full deploy details and anti-patterns

### Interaction Logging
- ALL user interactions via `logEvent()` from `app/data/logger.ts`
- Every screen MUST call `setFeedbackContext()` on focus/mount
- New screens: add `setFeedbackContext({ screen: 'screen-name' })` in `useFocusEffect` or `useEffect`

### Production Data Discipline
- **NEVER POST synthetic/test text to `/explore/capture`, `/review/voice-elicit`, `/review/voice-memo`, `/book/voice-note`, or any other user-data ingest endpoint on the live server.** These endpoints treat all input as user-authored. Test rows are indistinguishable from real ones downstream and can be silently destroyed by dedup jobs — we lost real captures this way in Session 86 (2026-04-20).
- To test a voice/capture pipeline: use `scripts/pipeline-tests/run.py` with fixtures, or write a unit test that calls `process_voice_capture()` against an in-memory SQLite, or `curl` a dedicated dev/staging server — never alif's prod DB.
- If a test MUST write to prod (rare), pass `input_mode='test'` through and document why in the session prompt so the data can be cleaned up.
- `voice_transcripts.input_mode` is stamped at ingest (`audio` / `text_json` / `test`) — check it on `/voice/calibration` to verify provenance before treating a row as real user data.

### Pipeline Testing
- Use `scripts/pipeline-tests/run.py` when iterating on prompts/models/extraction
- Always run relevant fixtures before AND after changes

### Research Organization
- ALL research in `research/`, linked from `research/README.md`
- `research/experiment-log.md` is **append-only** — new entries at top, log BEFORE making changes

### LLM Calling Discipline
- **⚠️ Claude-only directive (2026-04-20, Session 87)**: All new LLM code MUST use Claude, never Gemini. See `memory/feedback_claude_only_never_gemini.md`. Triggered by a Gemini 429 that silently dropped Khomeini's `cached_question` during the Iran Revolution capture. Existing Gemini call sites are being migrated under SESSION_88 — until complete, follow the Claude-only rule for any new code and avoid adding Gemini imports even when touching legacy paths.
- **`claude -p` subprocess (`claude_llm.py`)** is the batch/pipeline LLM path — process spawn + CLI startup adds 5-15s of overhead on top of the actual API call. Free via Max plan.
- **Gemini direct API (`gemini_llm.py`)** — LEGACY. Currently still used by ~60 call sites across 32 files. Being phased out. Do not add new callers.
- **Curriculum generation**: Opus-only via `claude -p` — unchanged.

### Code Conventions
- **Entity spans are offset-based on plain text.** `_compute_entity_spans()` in `review_engine.py` uses `text.find(name)`. Content must be markdown-stripped before span computation — use `_strip_markdown()`. Structured display uses `sections` JSON alongside flat `content`.
- Branch prefix: `sh/` for all GitHub branches
- No test plans or checklists in PR descriptions
- Component files under ~300 lines. Extract reusable UI into `app/components/`.
- **React Native Web links**: Use `MarkdownLink` component. Never `<Text onPress href>` (RNW blocks it).
- **KeyboardAvoidingView**: Required for bottom-sheet Modals with TextInput on iOS.
- **✦ Drawer**: Must be explicitly added to each tab screen (import `PetrarcaDrawer`).
- **No `as any`** — add proper types instead.
- **limbic.amygdala**: `pip install -e ~/src/limbic`. Server: `/opt/limbic`. Used for embeddings, similarity, clustering.
- **Standalone web pages**: HTML files in `scripts/` served via `_serve_html_file()` in research-server.py. Pattern: D3.js CDN, fetch from `/endpoint`, Petrarca design tokens. Examples: `curriculum_graph.html`, `curriculum_timeline.html`, `knowledge_atlas.html`.
- **DB is server-only**: `petrarca.db` lives at `/opt/petrarca/data/` on Hetzner. Local Python can't query it. Verify functions with `ast.parse()` for syntax, then `curl` the live endpoint after deploy.
- **Query server DB**: Write Python to `/tmp/script.py`, then `scp /tmp/script.py alif:/tmp/ && ssh alif "cd /opt/petrarca && python3 /tmp/script.py"`. Inline heredoc Python via SSH has quoting issues.

### Curriculum Generation
- Generate locally via `claude -p`, parse JSON, run through `curriculum.py` node builder

## User Preferences
- Prefers Claude Code agents (Max plan) over Anthropic API calls
- Rapid prototyping in small chunks, research depth before building
- Broad interests: history, classical philology, educational research, green party policy, AI
- Languages: Norwegian, Swedish, Danish, Italian, German, Spanish, French, Chinese, Indonesian, Esperanto, English

## Voice Processing
- **Soniox API**: Key in `/Users/stian/src/alignment/.env`, base: `https://api.soniox.com/v1`
- Patterns: `../alif/backend/app/services/soniox_service.py`

## Reference Projects
- **../alif**: Arabic learning app — Expo mobile, FSRS, `claude -p` wrapper
- **../otak**: Twitter bookmarks, Readwise, LLM providers (knowledge graph is a failed experiment)
- **../bookifier**: Pipeline/caching patterns
