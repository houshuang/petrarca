# Knowledge System Implementation Status

**Date**: March 9, 2026 (last updated — session 11)
**Status**: Full corpus deployed with knowledge system, reader interactions, voice notes, AI chat, research agents, entity deep-dive, follow-up research, voice note browser + action extraction, activity log tab, scroll-aware encounter tracking, curated novelty card, hierarchical topic feedback, cross-article connections, LLM-verified topic normalization, automatic defragmentation, **unified single-screen feed with lens tabs**, **dynamic reranking**, **✦ drawer navigation**, **clipper auto-save countdown**, **tweet URL ingestion via twikit**, **auto-sync Twitter cookies**, **clipper immediate save via background worker**, **reader disregard + report bad scrape**, **feed ingest metadata**
**Latest commits**: Session 11 — Clipper: immediate save via background service worker (survives popup close), cancel/note via separate endpoints, PETRARCA wordmark opens app. Reader: Disregard action + Report bad scrape queue. Feed: Latest lens shows relative ingest time + source. Pipeline: `ingested_at` ISO timestamp on all new articles.

---

## What Was Built

On March 8, 2026, the full knowledge-aware reading system was implemented end-to-end based on the design in `research/novelty-system-architecture.md` and validated by 11 experiments documented in `research/experiment-results-report.md`. Subsequently, the full 182-article corpus was restored with claims, embeddings, and knowledge index, and a cost auditing system was added. In session 4, the LLM infrastructure was migrated from litellm to the native `google.genai` SDK (fixing output truncation with newer Gemini models), topic research was rewritten from `claude -p` to Gemini search grounding (reducing latency from 60-120s to ~2.5s), and write contention was fixed with file locking. In session 5, four features were implemented via parallel agents: entity deep-dive (long-press entities in reader), follow-up research prompts (end-of-article questions), voice note browser (new screen), and voice note action extraction (LLM intent extraction from transcripts). In session 6, the Activity Log tab (G7) was implemented: a 4th tab showing a vertical timeline of reading sessions, system/pipeline events, research dispatches, and interest signals. The logger was enhanced with an AsyncStorage-backed offline queue for reliable event delivery, and the pipeline now writes structured JSONL events to the interaction log for server-side aggregation via `GET /activity/feed?days=N` on the research server.

### Architecture Overview

The system splits into **server-computed INDEX** (user-independent) and **client-side LEDGER** (user-specific):

```
Server Pipeline (cron every 4 hours):
  Twitter + Readwise → build_articles.py --claims → atomic claims + entities + follow-up questions
  → build_claim_embeddings.py → Gemini embedding-001 (batch 100)
  → build_knowledge_index.py → knowledge_index.json (parallel delta reports, 10 workers)
  → All LLM calls via gemini_llm.py (google.genai SDK, Gemini 3.1 Flash-Lite)
  → All calls tracked by llm_audit.py → data/llm_audit.jsonl

App (Expo SDK 54):
  content-sync.ts downloads knowledge_index.json
  → knowledge-engine.ts classifies claims against user's ledger
  → paragraph dimming, curiosity scoring, delta reports
  → AsyncStorage persists knowledge ledger (@petrarca/knowledge_ledger)
  → All interactions logged via logger.ts → local + server (port 8091)
```

### Files Created/Modified

#### New Files

| File | Description |
|------|-------------|
| `app/data/knowledge-engine.ts` | Core knowledge engine — FSRS decay, claim classification, paragraph dimming, curiosity scoring, knowledge ledger persistence. Module-level state (singleton). |
| `app/data/queue.ts` | Reading queue with AsyncStorage persistence. Add/remove/list queued article IDs. |
| `app/app/(tabs)/topics.tsx` | Topics screen — articles grouped by broad topic, expandable clusters with delta report summaries and top claims. |
| `app/app/(tabs)/queue.tsx` | Queue screen — saved-for-later articles with swipe-to-remove. |
| `scripts/build_knowledge_index.py` | Server pipeline — loads articles + embeddings, computes cosine similarity matrix, extracts cross-article pairs, builds paragraph mappings, generates LLM delta reports (parallel, 10 workers). Outputs `data/knowledge_index.json`. |
| `scripts/deploy_knowledge_index.sh` | Deploys knowledge_index.json to nginx + updates manifest hash. Supports `--local` mode. |
| `scripts/llm_audit.py` | Thread-safe JSONL audit trail for all LLM calls. Tracks tokens, cost, cache hits per-call. CLI: `python3 scripts/llm_audit.py --days 7`. |
| `scripts/log_server.py` | HTTP server (port 8091) for collecting app interaction logs. Accepts POST /log with JSONL body, stores as daily files in `/opt/petrarca/data/logs/`. |
| `app/data/bookmarks.ts` | Article bookmarking with AsyncStorage persistence. Toggle, query, list bookmarked IDs. |
| `app/components/AskAI.tsx` | Bottom-sheet AI chat modal. Conversation threading, Gemini Flash via `/chat` server endpoint. Article context (title, summary, claims, topics, truncated text) passed as context. |
| `app/components/VoiceFeedback.tsx` | Compact voice note recording bar. Records audio via expo-av, uploads to server `/note` endpoint for async Soniox transcription. Auto-closes on send. |
| `app/lib/chat-api.ts` | API client for research server: `askAI()`, `uploadVoiceNote()`, `spawnTopicResearch()`, `fetchNotes()`, `ingestUrl()`, `getIngestStatus()`, `reportBadScrape()`. |
| `app/public/guide/index.html` | HTML user guide (Annotated Folio styled). Covers all 5 capture flows, 3 tabs, reader modes, knowledge system, usage patterns. Linked from Feed header. |
| `research/user-guide.md` | Markdown source for user guide. Describes all implemented features accurately. |
| `scripts/gemini_llm.py` | Shared Gemini LLM wrapper (google.genai SDK). Three functions: `call_llm()`, `call_chat()`, `call_with_search()`. Default model: `gemini-3.1-flash-lite-preview` (via `PETRARCA_LLM_MODEL` env var). Replaces all litellm usage. |
| `app/app/voice-notes.tsx` | Voice notes browser screen. Global notes view with date-grouped sections, ✦ markers, Cormorant Garamond header. Accessible from Feed header "Notes" link. |
| `app/components/VoiceNoteCard.tsx` | Reusable voice note card component. Shows timestamp, duration badge, transcript (3-line max), article link, action chips with type-colored borders. |
| `app/lib/voice-notes-api.ts` | Voice notes API module. `fetchAllNotes()`, `fetchArticleNotes()`, `executeNoteAction()`. TypeScript interfaces for `VoiceNote` and `NoteAction`. |

#### New Files (Session 6: Activity Log)

| File | Description |
|------|-------------|
| `app/app/(tabs)/log.tsx` | Activity Log tab — vertical timeline with reading/system/research/interest nodes. Filter toggles (All/Reading/System/Research). Paged fetch: loads last day first, then 7 days in background. Colored dots per event type, ✦ markers for interest signals, day separators. |

#### New Files (Session 9: Unified Feed Redesign)

| File | Description |
|------|-------------|
| `app/components/DoubleRule.tsx` | Reusable double rule separator (2px + 5px gap + 1px ink lines) using layout tokens. |
| `app/components/LensTabs.tsx` | Horizontal tab switcher for Latest/Best/Topics/Quick lenses. EB Garamond 13px, rubric underline active indicator, logs `lens_switch`. |
| `app/components/UpNextSection.tsx` | Pinned top section: shows in-progress article (with progress bar), next queued, or algorithmic pick. Contains ✦ drawer trigger button. Logs `up_next_tap` with type. |
| `app/components/RecommendedSection.tsx` | Hero card for algorithmically top-ranked article. Cormorant Garamond 20px title, claim preview (green left border), novelty badge, "See all" link. Logs `recommended_tap`. |
| `app/components/TopicPillsSection.tsx` | Horizontal scroll of topic pills from `getArticlesGroupedByTopic()`. First pill gets ink (dark) treatment. Logs `topic_pill_tap`. |
| `app/components/TopicsGroupedList.tsx` | Articles grouped by topic with tree-line indentation. Expand/collapse (shows 3, "+N more" to expand). Optional `topicFilter` prop. Logs `topic_group_article_tap`. |
| `app/components/PetrarcaDrawer.tsx` | Bottom sheet (ink background). Quick actions: Triage, Voice Note. Nav items: Voice Notes, Activity Log, Reading Progress, Queue. Logs `drawer_open/close`, `drawer_item_tap`. |
| `research/feed-redesign-plan.md` | Comprehensive plan: 3 rounds of mockup feedback, approved architecture, screen layout, 5-phase implementation order, component specs. |

#### Modified Files (Session 11: Clipper Immediate Save + Reader Actions + Feed Metadata)

| File | Changes |
|------|---------|
| `clipper/popup.js` | Save moved to background worker via `fireImmediateSave()`. `doSave()` simplified to send note (if any) and show saved state. Cancel/Escape send `cancelSave` message. |
| `clipper/popup.html` | PETRARCA wordmark changed to clickable `<a>` with `id="open-app"`. |
| `clipper/popup.css` | Wordmark hover style (opacity 0.7 transition). |
| `clipper/background.js` | Added `addNote` → `POST /ingest-note`, `cancelSave` → `POST /ingest-cancel` handlers. `saveClip` gets offline fallback via `storeLocally()`. |
| `app/app/(tabs)/index.tsx` | Added `formatRelativeDate()` (minute/hour/day precision from ISO timestamps), `formatSourceLabel()` (maps source types to display labels). `ArticleCard` gets `showIngestInfo` prop, shown only on Latest lens. |
| `app/app/reader.tsx` | Added "Report bad scrape" menu item (`reportBadScrape()` → `/report-scrape`). Added "Disregard" menu item (dismiss + navigate back). Imported `dismissArticle` from store. |
| `app/lib/chat-api.ts` | Added `reportBadScrape()` function. |
| `app/data/types.ts` | Added `ingested_at?: string` to Article interface. |
| `scripts/import_url.py` | Added `ingested_at` ISO timestamp to article dict. |
| `scripts/build_articles.py` | Added `ingested_at` ISO timestamp to article dict. |
| `scripts/research-server.py` | Added `SCRAPE_REPORTS_PATH`. New endpoints: `POST /ingest-note` (sidecar write), `POST /ingest-cancel` (remove from articles.json), `POST /report-scrape` (append to scrape queue), `GET /scrape-reports` (list pending). |

#### Modified Files (Session 10: Clipper + Tweet Ingestion)

| File | Changes |
|------|---------|
| `clipper/popup.html` | Header gets countdown number + timer overlays on double rule. Note field always visible (dashed placeholder). Note toggle button removed. Cancel button added. |
| `clipper/popup.css` | Timer overlay animation (rubric drains to gray), countdown number (Cormorant 22px), dashed→solid note field transition on focus, Cancel button, gold completion flash (#c9a84c). |
| `clipper/popup.js` | Complete rewrite of save flow. 10s countdown via `requestAnimationFrame` (smooth pause/resume). States: counting → paused (on typing) → saving → saved. Auto-save at 0, Cancel button + Esc. |
| `clipper/manifest.json` | Added `cookies` permission + `host_permissions` for `*.x.com` and `*.twitter.com`. |
| `clipper/background.js` | Added `maybeSyncTwitterCookies()`: extracts `auth_token` + `ct0` via `chrome.cookies.get()` on X.com visits, POSTs to `/twitter/cookies`. Throttled to 4h via `chrome.storage.local` timestamp. `tabs.onUpdated` listener triggers on page load complete. |
| `scripts/research-server.py` | Added tweet URL detection (`_is_tweet_url`), `run_ingest_tweet()` (twikit fetch → thread reconstruction → URL extraction → normal pipeline), `_fetch_tweet_via_twikit()` (async), `_check_twikit_cookies()`. New endpoints: `GET /twitter/status`, `POST /twitter/cookies`. `/ingest` now routes tweet URLs through twikit. |

#### Modified Files (Session 9: Unified Feed Redesign)

| File | Changes |
|------|---------|
| `app/app/(tabs)/index.tsx` | Complete rewrite. Single FlatList with ListHeaderComponent (UpNext → Recommended → Topics → DoubleRule). Lens tabs as sticky `data[0]` via `stickyHeaderIndices={[0]}`. Articles sorted/grouped by active lens. Swipe dismiss/queue preserved. `useFocusEffect` triggers rerank on return from reader. No header chrome (no app name, no date). ~320 lines (was 728). |
| `app/app/(tabs)/_layout.tsx` | Tab bar hidden (`display: 'none'`). Topics/Queue/Log routes preserved with `href: null` for drawer navigation access. ~40 lines (was 82). |
| `app/data/store.ts` | Added `FeedLens` type, `getTopRecommendedArticle()` (highest-scored not in queue/in-progress), `getArticlesByLens()` (filters+sorts by lens), `getArticlesGroupedByTopic()` (groups by broad topic), `getInProgressArticles()`, `getFeedVersion()`/`bumpFeedVersion()` (reactive counter). Integrated `isKnowledgeReady()` + `_getArticleNovelty()` into `getRankedFeedArticles()`: blended score = interest (60%) + curiosity (40%). Quick lens also uses blended scoring. |
| `app/data/queue.ts` | Added `getNextQueued()` (front of queue without removing), `peekQueue(n)` (first N items). |
| `research/README.md` | Added UX Redesign section linking to `feed-redesign-plan.md`. |
| `research/experiment-log.md` | Session 9 entry: design exploration (3 rounds), user interview findings, implementation details, 8 hypotheses to validate, events logged. |

#### New Files (Session 8: Swarm Build + Topic Normalization)

| File | Description |
|------|-------------|
| `app/components/RelatedArticles.tsx` | Related articles component at bottom of reader. Three relationship finders (same topic, shared concepts via knowledge index, same source). Deduped, max 3 per group. Design system tokens. |

#### New Files (Session 8: Topic Hierarchy + Cross-Article + Normalization)

| File | Description |
|------|-------------|
| `scripts/topic_registry.json` | Canonical topic registry — 12 broad categories, 21 specific topics, each with include/exclude descriptions for LLM disambiguation. Hard limits: `max_broad: 25`, `max_specific_per_broad: 15`. Inspired by Otak's `tree_balance.py` approach but avoids its unbounded growth. |
| `scripts/topic_normalizer.py` | Topic normalization + defragmentation. `normalize_article_topics()` validates against registry via LLM merge-or-create. `defragment_registry()` consolidates overpopulated categories. `registry_needs_defrag()` checks if limits exceeded. |

#### Modified Files (Session 8: Topic Hierarchy + Cross-Article + Normalization)

| File | Changes |
|------|---------|
| `app/app/reader.tsx` | Redesigned `PostReadInterestCard` with hierarchical topic display: `TopicGroup` interface, `groupTopicsByBroad()`, `TopicLevelRow` with tree lines + level badges (broad/topic/entity), smart expand (≤2 broad → expanded). Added `ConnectedReadingSection` (bottom section: shared claim counts, read status, queue buttons). Added `InlineCrossArticleAnnotation` (inline "Also in: [title]" below paragraphs). ~400 lines added. |
| `app/data/interest-model.ts` | Added `recordTopicSignalAtLevel()` — signals at exactly one hierarchy level without cascading. Updated `computeInterestMatch()` to include entity-level scores via `Math.max(specificScore, broadScore * 0.7, entityScore)`. |
| `app/data/queue.ts` | Added `addToQueueFront()` — LIFO queue insertion for cross-article connections (user wants "next article I see would be this one"). |
| `app/data/knowledge-engine.ts` | Added `CrossArticleConnection` interface and two new functions: `getCrossArticleConnections()` (groups similar claims by article, max 5 results), `getParagraphConnections()` (maps paragraph indices to connected articles via claim-to-paragraph mapping from knowledge index). |
| `app/data/store.ts` | Added export wrappers: `recordTopicInterestSignalAtLevel()`, `getCrossArticleConnections()`, `getParagraphConnections()`. |
| `scripts/build_articles.py` | Integrated topic normalizer: loads registry once, normalizes each article's `interest_topics` via `normalize_interest_topics()`. Added `_get_topic_hint()` — injects existing categories into LLM extraction prompt. Added `--normalize-topics` for batch re-normalization, `--defrag-topics` for automatic defragmentation. Extended `--enrich` to also backfill `interest_topics`. |
| `scripts/content-refresh.sh` | Added step 3c3: automatic topic defragmentation check after article processing. |

#### Modified Files (Session 6: Activity Log)

| File | Changes |
|------|---------|
| `app/data/logger.ts` | Added AsyncStorage-backed offline queue (`savePendingPayload`, `flushPendingLogs`). Failed server sends are persisted and retried on session start + piggybacked on successful flushes. |
| `app/app/(tabs)/_layout.tsx` | Added 4th "Log" tab to tab bar. |
| `app/design/tokens/colors.ts` | Added `research: '#6a3a8a'` color token for research event dots. |
| `scripts/research-server.py` | Added `GET /activity/feed?days=N` endpoint. Aggregates interaction logs, pipeline events, and research results into grouped timeline nodes (reading sessions, interest signals within 60s, pipeline runs within 15min). |
| `scripts/content-refresh.sh` | Added `pipeline_log()` function writing structured JSONL to interaction log dir. Logs pipeline_start, each major step, and pipeline_complete with elapsed time. |

#### Modified Files (Session 4+5: LLM migration + four features)

| File | Changes |
|------|---------|
| `scripts/build_articles.py` | Migrated from litellm to `gemini_llm.call_llm()`. Added `_locked_append_article()` with `fcntl.flock` for write contention safety. Extended prompt schema with `entities[]` and `follow_up_questions[]`. Fixed `normalize_topic()` to handle dict inputs. |
| `scripts/research-server.py` | Migrated chat from litellm to `gemini_llm.call_chat()`. Rewrote topic research from `claude -p` to `gemini_llm.call_with_search()` (Gemini search grounding). Added `extract_note_actions()` for LLM intent extraction from transcripts. Added `POST /notes/{note_id}/execute-action` endpoint. `/ingest` now returns `ingest_id` + deterministic `article_id`. Added `GET /ingest-status?id=` for polling. |
| `scripts/import_url.py` | Added import of `_locked_append_article` from `build_articles` for concurrent write safety. |
| `app/data/types.ts` | Added `ArticleEntity` interface (7 entity types), `FollowUpQuestion` interface, extended `Article` with `entities?` and `follow_up_questions?`. |
| `app/app/reader.tsx` | Added `EntityHighlightText` (dotted underline on entity mentions, long-press popup), `EntityPopup` (inline marginalia card with entity info + "Research more"), `FollowUpSection` ("✦ FURTHER INQUIRY" section after article with tappable research questions). ~320 lines added. |
| `app/app/(tabs)/index.tsx` | Added "Notes" link in feed header navigating to `/voice-notes`. |
| `app/app/_layout.tsx` | Added `voice-notes` screen to Stack navigator. |

#### Modified Files (Mar 8 session 2)

| File | Changes |
|------|---------|
| `app/app/reader.tsx` | Added ⋯ menu (article info, source, Ask AI, voice note, research topic), ☆ bookmark toggle, AI chat modal, voice feedback panel. `buildAIChatContext()` builds article context string for LLM. |
| `app/app/(tabs)/index.tsx` | Guide link in header, topic normalization for filter chips and tags, `minHeight: 44` on filter scroll. |
| `app/app/(tabs)/topics.tsx` | "↗ Find more on [Topic]" research button in expanded topic clusters. Topic normalization for grouping/display. |
| `app/data/interest-model.ts` | Added `bookmark_add` (weight 1.5) and `bookmark_remove` (weight 0.5) signal types. |
| `app/data/store.ts` | Loads bookmarks on init alongside queue. |
| `app/lib/display-utils.ts` | Added `normalizeTopic()` and `displayTopic()` shared utilities. |
| `scripts/research-server.py` | Added `/chat` (Gemini Flash chat), `/note` (audio upload + Soniox transcription), `/research/topic` (claude -p topic research + auto-ingest), `/notes` GET. |

#### Modified Files (original build)

| File | Changes |
|------|---------|
| `app/data/types.ts` | Added 9 types: `KnowledgeIndex`, `DeltaReport`, `NoveltyClassification`, `ClaimKnowledgeEntry`, `ClaimClassification`, `ParagraphDimming`, `ArticleNovelty` |
| `app/data/content-sync.ts` | Downloads `knowledge_index.json` alongside articles. Added `KNOWLEDGE_INDEX_URL`, `knowledge_index_hash` to manifest checking, graceful fallback if index doesn't exist. |
| `app/data/store.ts` | Imports and initializes knowledge engine + queue in `initStore()`. Exports wrapper functions. Added bundled fallback `require('./knowledge_index.json')`. |
| `app/app/reader.tsx` | 3 reading modes (Full/Guided/New Only), paragraph dimming via `blockDimming` map, collapsible familiar sections (`CollapsedBar` component), "What's new for you" claims card, `ReadingModeToggle` component, `buildParagraphToBlockMap()` for mapping pipeline paragraph indices to markdown block indices. Calls `markArticleEncountered()` on Done. |
| `app/app/(tabs)/index.tsx` | Curiosity-zone re-ranking (with 0.05 threshold for stability), topic filter chips (horizontal ScrollView), swipe-right-to-queue, novelty hints ("N new claims"), `ContinueReadingCard` component (limited to 2 most recent). Interaction logging for swipe-dismiss and swipe-queue. |
| `app/app/(tabs)/_layout.tsx` | Originally 3-tab layout → expanded to 4 tabs (session 6) → **session 9: tab bar hidden, single screen with drawer**. Routes preserved via `href: null`. |
| `app/data/logger.ts` | Dual-write logging: local (localStorage/filesystem) + server buffer (batched POST to port 8091 every 5s). AsyncStorage-backed offline queue retries failed sends on session start. |
| `scripts/content-refresh.sh` | Full 6-step pipeline: fetch sources → build articles → validate → extract entities → extract claims → embed claims → build knowledge index → copy to nginx. Writes structured JSONL pipeline events to interaction log for activity feed. |

### Data Generated

| File | Size | Contents |
|------|------|----------|
| `data/articles.json` | ~7 MB | 186 articles with `atomic_claims[]`, `entities[]`, `follow_up_questions[]` |
| `data/claim_embeddings.npz` | 33 MB | 2,954 Gemini embedding-001 vectors |
| `data/knowledge_index.json` | 4.3 MB | 2,954 claims, cross-article similarity pairs (≥0.68), 126 article paragraph maps, article novelty matrix (3,488 pair entries), 300 LLM delta reports |
| `data/llm_audit.jsonl` | ~77 KB | Per-call LLM usage records (tokens, cost, model, purpose) |

### Algorithm Parameters (validated by experiments)

| Parameter | Value | Source |
|-----------|-------|--------|
| KNOWN threshold | ≥ 0.78 cosine | Nomic calibration experiment |
| EXTENDS threshold | ≥ 0.68 cosine | Nomic calibration experiment |
| FORGOTTEN threshold | R < 0.3 | FSRS standard |
| Stability (skim) | 9 days | FSRS experiment |
| Stability (read) | 30 days | FSRS experiment |
| Stability (highlight) | 60 days | FSRS experiment |
| Reinforcement factor | 2.5× | FSRS standard |
| Curiosity peak | 70% novelty | Curiosity zone experiment |
| Curiosity Gaussian σ | 0.15 | Curiosity zone experiment |
| Similarity index threshold | ≥ 0.68 | Pairs below this are always NEW |
| Feed re-rank threshold | 0.05 | Prevents unstable sorts when scores are close |

---

## Deployment Status

### Server (Hetzner: alifstian.duckdns.org)

| Component | Status | Notes |
|-----------|--------|-------|
| nginx content server (:8083) | ✅ Working | Serves articles.json, knowledge_index.json, manifest.json |
| Static web app (:8084) | ✅ Deployed | Session 11: clipper immediate save, reader disregard/report, feed ingest metadata |
| Expo native (:8082) | ✅ Running | systemd `petrarca-expo` |
| Log server (:8091) | ✅ Running | systemd `petrarca-log`, collects app interaction logs |
| articles.json | ✅ 182 articles | Full corpus with atomic claims, entities, follow-up questions |
| knowledge_index.json | ✅ 4.3MB | 300 delta reports, novelty matrix, paragraph maps |
| claim_embeddings.npz | ✅ 33MB | Gemini embedding-001, 2,954 vectors |
| manifest.json | ✅ Updated | `articles_hash` + `knowledge_index_hash` |
| llm_audit.jsonl | ✅ Collecting | 330 records from pipeline run ($0.035 total) |
| Python deps | ✅ All installed | numpy, google-genai (native SDK) in `/opt/petrarca/.venv` |
| Cron pipeline | ✅ Working | `content-refresh.sh` runs full pipeline including claims + embeddings + knowledge index |
| GEMINI_KEY | ✅ Configured | In `/opt/petrarca/.env` (used by `gemini_llm.py`, also `GEMINI_API_KEY` alias) |
| Voice notes storage | ✅ Working | `/opt/petrarca/data/notes/` (JSON) + `/opt/petrarca/data/audio/` (m4a) |
| Chat conversations | ✅ Working | `/opt/petrarca/data/chats/` (JSON, per conversation_id) |
| Research server endpoints | ✅ Updated | `/chat`, `/note`, `/research/topic`, `/notes`, `/notes/{id}/execute-action`, `/research`, `/research/results`, `/twitter/status`, `/twitter/cookies`, `/ingest-note`, `/ingest-cancel`, `/report-scrape`, `/scrape-reports` on port 8090 |
| Scrape reports queue | ✅ Working | `/opt/petrarca/data/scrape_reports.json` — user-reported bad scrapes, `GET /scrape-reports` lists pending. **Review periodically** to identify scraping failure patterns and strengthen the pipeline (e.g. site-specific extractors, better fallback logic). |

### SSH Access
- Use `ssh alif` (configured in `~/.ssh/config` → `root@46.225.75.29` via `~/.ssh/hetzner_ed25519`)

---

## Known Issues & Bugs

### UI Issues (from user screenshot, Mar 8)

1. **Filter chips row clipped** — **RESOLVED**: Changed `maxHeight: 40` to `flexGrow: 0`.
2. **Continue Reading section too large** — **RESOLVED**: Limited to 2 most recent.
3. **Continue Reading cards have card-like backgrounds** — **RESOLVED**: Removed parchmentDark background.
4. ~~**UI not visually tested**~~ — **RESOLVED**: Visual testing done with agent-browser. Confirmed all screens render correctly. Topics expansion works (Playwright click issue was a false positive — React Native Web Pressable needs DOM `.click()`, not Playwright's `click @ref`).

### Data Issues

5. ~~**Server has only 47 articles**~~ — **RESOLVED**: Full 171-article corpus restored with 2,954 atomic claims, embeddings, and knowledge index.
6. ~~**Duplicate topic variants**~~ — **RESOLVED**: Added client-side topic normalization in `app/lib/display-utils.ts` (`normalizeTopic()` + `displayTopic()`). Used across feed filter chips, topic tags, and Topics tab grouping. Reduced 67→58 topic groups.
7. ~~**google.generativeai deprecation warning**~~ — **RESOLVED**: Migrated all LLM calls to `google.genai` SDK via shared `gemini_llm.py` wrapper. litellm fully removed.
11. ~~**Twitter cookies expire**~~ — **RESOLVED**: Chrome extension auto-syncs cookies to server on X.com visits (4h throttle). Also available via `POST /twitter/cookies` API and `GET /twitter/status` health check.

### Logic Issues

8. **Reading mode toggle shows even when no dimming** — Fixed: now checks `Array.from(blockDimming.values()).some(d => d.opacity < 1)`.
9. **Feed sort unstable with empty ledger** — Fixed: added 0.05 threshold + rank tiebreaker so interest model order is preserved until curiosity scores meaningfully diverge.
10. **Paragraph-to-block mapping is heuristic** — `buildParagraphToBlockMap()` uses text prefix matching (first 50 chars). May mismap in articles with repeated paragraph openings.

---

## How the Knowledge System Works (User Perspective)

### First Use (Empty Ledger)
1. All claims classify as NEW (no ledger entries to compare against)
2. Feed shows articles ranked by interest model (curiosity scoring has no effect yet)
3. Reader shows "What's new for you" card with novel claims from the knowledge index
4. Reading mode toggle does NOT appear (no familiar blocks to dim)
5. User reads article → Done → claims recorded in ledger with stability=30d

### After Reading Several Articles
1. Open an article on a related topic → knowledge engine finds similar claims via cosine similarity
2. Claims matching ledger entries at ≥0.78 → KNOWN, ≥0.68 → EXTENDS, <0.68 → NEW
3. Paragraph dimming computed: familiar paragraphs get opacity 0.55, novel get 1.0, mixed get blended
4. Reading mode toggle appears:
   - **Full** — all content at normal opacity
   - **Guided** — familiar paragraphs dimmed (opacity from dimming map)
   - **New Only** — familiar blocks collapsed into "N familiar sections" bars, tap to expand
5. Feed re-ranks: articles with ~70% novelty ratio score highest (curiosity zone)

### Knowledge Decay
- Claims fade over time: R = e^(-t/S) where S = stability_days
- Skim=9d, Read=30d, Highlight=60d
- Re-reading reinforces: stability × 2.5
- Forgotten when R < 0.3 → claim treated as unknown again

### Topics & Delta Reports
- Topics tab groups articles by broad topic from `interest_topics`
- Expanding a topic shows the LLM-generated delta report: "What's new in [topic]"
- Delta reports are pre-generated by `build_knowledge_index.py` using Gemini Flash
- Each report: summary paragraph + top 5 claims

---

## Next Steps (Priority Order)

### Completed
1. ~~**Visual testing**~~ — DONE
2. ~~**Topic normalization**~~ — DONE
10. ~~**Research agent button**~~ — DONE: "↗ Research [topic]" in reader menu and Topics tab, spawns `claude -p`, auto-ingests found articles
11. ~~**Voice notes**~~ — DONE: Record in reader → upload to server → async Soniox transcription → stored as notes linked to article + topics
12. ~~**Resourceful bookmark pipeline**~~ — DONE: `build_articles.py --entities` detects short tweets mentioning books/people/products, uses Gemini Flash to extract entities, synthesizes mini-articles. Runs as step 3c2 in cron pipeline. Tested: 5 entity articles ingested successfully.
13. ~~**Topic +/- buttons fixed**~~ — DONE: Per-topic signals (not all topics), visual feedback on votes
14. ~~**Feed refresh on return from reader**~~ — DONE: `useFocusEffect` triggers recalculation of feed, read articles, and continue reading lists
15. ~~**Robust voice recording**~~ — DONE: Saves locally first → uploads in background → retry queue for failures
16. ~~**Long-press entity research**~~ — DONE: Long-press paragraph → action menu (Highlight / Research / Ask AI). Research opens AI chat with passage context.
17. ~~**Feed "..." menu**~~ — DONE: Voice feedback + stats from main feed screen
18. ~~**Inline topic chips**~~ — DONE: +/- buttons at end of article content, not just post-read modal
19. ~~**AskAI initialQuestion**~~ — DONE: Pre-fill AI chat with questions from research context

### Completed (Session 4+5)
4. ~~**Voice note visibility**~~ — DONE: Voice notes browser screen (`voice-notes.tsx`), accessible from Feed header "Notes" link. Date-grouped notes with transcript, duration, article link, action chips.
5. ~~**Voice note action extraction**~~ — DONE: `extract_note_actions()` in research-server.py uses Gemini to extract research/tag/remember intents from transcripts. Actions shown as tappable chips in VoiceNoteCard. Execute via `POST /notes/{id}/execute-action`.
6. ~~**Claude CLI token expired**~~ — RESOLVED: Topic research completely rewritten from `claude -p` to Gemini search grounding (`call_with_search()`). No longer depends on Claude CLI.
7. ~~**Follow-up research prompts**~~ — DONE: Pipeline extracts 2-3 curiosity-driven questions per article. "✦ FURTHER INQUIRY" section in reader after claims. Tap to spawn topic research via `/research/topic`.
20. ~~**Entity deep-dive**~~ — DONE: Pipeline extracts entities (person/book/company/concept/event/place/technology). Reader highlights entity mentions with dotted underline. Long-press shows marginalia popup with synthesis + "Research more".
21. ~~**LLM migration**~~ — DONE: All LLM calls use `google.genai` SDK via `gemini_llm.py`. litellm removed. Default model: Gemini 3.1 Flash-Lite.

### Completed (Session 6)
22. ~~**Re-run pipeline for entities/questions**~~ — DONE: Added `--enrich` flag to `build_articles.py`. All 182 articles now have entities (1,062 total) and follow-up questions (499 total).
23. ~~**Resourceful bookmark pipeline enhancement**~~ — DONE: `research_entity()` now uses Gemini search grounding (`call_with_search()`) for real Google-grounded results instead of plain LLM synthesis.
24. ~~**Server robustness**~~ — DONE: Added `_read_json_body()` / `_send_json_response()` helpers to research server. All 8 POST endpoints now return clean 400 errors on malformed JSON instead of crashing. File read errors in `execute-action` also handled.
25. ~~**Voice notes error handling**~~ — DONE: `handleActionExecute` in `voice-notes.tsx` now catches errors instead of crashing on network failures.
11. ~~**Production bundle optimization**~~ — Already done: `knowledge_index.json` is gitignored, not bundled.

### Completed (Session 7)
26. ~~**Scroll-aware encounter tracking**~~ — DONE: `markArticleReadUpTo()` only marks claims in paragraphs the user scrolled past. Estimates furthest paragraph from `(maxScrollY + viewportHeight) / contentHeight`. Engagement: 'read' (>60s) or 'skim' (≤60s). "Done" button still marks all claims.
27. ~~**Curated "What's new" card**~~ — DONE: Prioritizes non-factual claim types (causal, evaluative, comparative, procedural) over plain factual. Capped at 3 items. Added `claim_type` to `ClaimClassification`.
28. ~~**G1 descoped**~~ — Per-claim feedback UI explored via 4 design mockups. Decided knowledge model should infer from behavioral signals, not explicit per-claim buttons.

### Completed (Session 8)
29. ~~**Hierarchical topic feedback (G9)**~~ — DONE: PostReadInterestCard redesigned with hierarchical display (broad → specific → entity). `recordTopicSignalAtLevel()` for level-specific signaling without cascade. Smart expand logic.
30. ~~**Cross-article connections (G10)**~~ — DONE: Inline "Also in: [title]" annotations below paragraphs + "✦ CONNECTED READING" bottom section with queue-first behavior (LIFO via `addToQueueFront()`). Max 2 annotations per paragraph, max 5 connected articles.
31. ~~**LLM-verified topic normalization**~~ — DONE: Canonical topic registry (`topic_registry.json`) with include/exclude descriptions. `topic_normalizer.py` validates new topics against registry via LLM merge-or-create decisions. Build pipeline injects existing categories into extraction prompt for consistency from the start. Lessons from Otak's `tree_balance.py` applied: include/exclude descriptions work, but avoid unbounded tree growth.
32. ~~**Automatic topic defragmentation**~~ — DONE: `defragment_registry()` consolidates when limits exceeded. Phase 1: merge similar specifics per overpopulated broad. Phase 2: minimal broad merges. Phase 3: update all articles. Auto-runs as pipeline step 3c3. First run: 28→25 broad, 263→172 specific. See `research/topic-normalization-spec.md` for full spec.
33. ~~**Backfill interest_topics**~~ — DONE: Extended `--enrich` to also generate `interest_topics`. All 185 articles now have hierarchical topics, normalized and defragmented.

### Completed (Session 9)
34. ~~**Entity-link merge**~~ — DONE: When text is both a markdown link and a pipeline entity, the entity popup wins. URL is passed as context: shown in popup, used for smart actions. Article-like URLs (containing `/blog/`, `/article/`, `/introducing/`) get "Save article" (auto-ingest). All others get "Research more" with URL as context for Gemini search grounding. Linked entity mentions get rubric-colored dotted underline.
35. ~~**Ingest auth fix**~~ — DONE: Reader-originated ingests (`source: reader_link`) skip auth token check on `/ingest` endpoint. Previously all ingests required `X-Petrarca-Token`, causing 401 failures from the app.
36. ~~**Entity tap (not just long-press)**~~ — DONE: Entity mentions respond to `onPress` instead of `onLongPress` for better discoverability.

### Completed (Session 11)
41. ~~**Clipper immediate save**~~ — DONE: Save fires immediately via background service worker on popup open (survives popup close). Cancel/Escape sends `POST /ingest-cancel` to undo. Notes sent separately via `POST /ingest-note`. Offline fallback queues to `chrome.storage.local`.
42. ~~**PETRARCA wordmark opens app**~~ — DONE: Clicking the wordmark in clipper popup cancels capture + opens web app in new tab.
43. ~~**Reader "Disregard" action**~~ — DONE: ⋯ menu gets "Disregard" (muted text, below divider). Calls `dismissArticle()` with reason `reader_disregard`, records interest signal, navigates back to feed.
44. ~~**Report bad scrape queue**~~ — DONE: ⋯ menu gets "Report bad scrape". Sends to `POST /report-scrape` → stored in `/opt/petrarca/data/scrape_reports.json`. `GET /scrape-reports` lists pending reports. Deduplicated by article_id.
45. ~~**Feed ingest metadata**~~ — DONE: Latest lens shows relative ingest time ("2h ago", "yesterday") + source label (Twitter, Readwise). Uses `ingested_at` ISO timestamp (new field) with fallback to `date`.
46. ~~**`ingested_at` timestamp**~~ — DONE: Both `import_url.py` and `build_articles.py` now write `ingested_at: datetime.now(UTC).isoformat()` on all new articles. Existing articles fall back to `date` (day-level precision only).

### Completed (Session 10)
37. ~~**Clipper auto-save countdown**~~ — DONE: Chrome clipper popup auto-saves after 10 seconds (fire-and-forget via Cmd+Shift+S). Signature double rule acts as countdown timer (rubric drains to gray). Typing in note field pauses countdown. Visible Cancel button + Esc. Gold completion flash (#c9a84c) on save. requestAnimationFrame for smooth 60fps timer.
38. ~~**Tweet URL ingestion via twikit**~~ — DONE: `/ingest` endpoint detects twitter.com/x.com URLs and routes through twikit instead of generic URL import. Fetches full tweet metadata, reconstructs threads (same-author reply chains), extracts + resolves t.co links. If tweet has URLs → ingests linked article with tweet context. If no URLs → uses tweet/thread text as article content. Falls back to normal import if twikit fails.
39. ~~**Auto-sync Twitter cookies**~~ — DONE: Chrome extension silently extracts `auth_token` + `ct0` cookies when user visits X.com and pushes to server via `POST /twitter/cookies`. Throttled to once per 4 hours. Eliminates manual SSH cookie refresh. New manifest permissions: `cookies` + `host_permissions` for x.com/twitter.com.
40. ~~**Cookie health endpoints**~~ — DONE: `GET /twitter/status` checks cookie validity + age. `POST /twitter/cookies` accepts `{auth_token, ct0}` for remote cookie refresh.

### Gap Analysis: Built vs. Full Spec (updated end of session 8)

#### COMPLETED — Original Gaps Now Resolved

| # | Feature | Resolution |
|---|---------|-----------|
| G1 | Claim-level feedback UI | **Descoped** → behavioral inference via scroll-aware tracking + curated "What's new" card |
| G3 | Incremental embedding | **DONE** — only embeds new claims, prunes removed, `--force` for full rebuild |
| G4 | Related articles at reader bottom | **DONE** — 3 groups (same topic / shared concepts / same source) with "+ Queue" buttons |
| G5 | Reader "Up next" footer | **DONE** — footer bar with Done + next queued article title, `router.replace()` flow |
| G6 | Auto-ingest from links | **DONE** — tap link → POST `/ingest` → poll `/ingest-status` → inline badges |
| G7 | Activity Log tab | **DONE** — 4th tab, server aggregation via `/activity/feed`, offline log queue |
| G9 | Topic hierarchy feedback | **DONE** — hierarchical PostReadInterestCard, `recordTopicSignalAtLevel()`, entity scoring |
| G10 | Cross-article connections | **DONE** — inline "Also in: [title]" annotations + "✦ CONNECTED READING" bottom section |
| G12 | Novel section markers | **DONE** — 2px green left border on novel/mostly_novel paragraphs in Guided/New Only modes |
| G13 | Micro-delights (partial) | **DONE** — ✦ pull-to-refresh ornament, claim reveal stagger (80ms), completion flash. AnimatedHighlightWrap deferred. |

#### REMAINING GAPS

| # | Feature | Priority | Notes |
|---|---------|----------|-------|
| G2 | **LLM judge for ambiguous claims** | Medium | 0.68–0.78 cosine range gets LLM verification. Experiment validated, not integrated into pipeline. |
| G8 | **Web split panel + keyboard shortcuts** | Medium | Desktop experience. Left pane article list + right pane reader, `j/k/d/x/q/Space/s` keys. |
| G11 | **Scrollbar novelty minimap** | Low | Colored dots on scrollbar showing novel content locations. |
| G14 | **Scrape report triage + pipeline hardening** | Medium | Periodically review `/opt/petrarca/data/scrape_reports.json` (`GET /scrape-reports`). Analyze failure patterns (paywalls, JS-rendered sites, unusual DOM structures). Use findings to add site-specific extractors, improve `clean_markdown`, or add fallback scraping strategies. First report: Claude docs page (2026-03-09). |
| G13 | **AnimatedHighlightWrap** | Low | Amber long-press border animation. Deferred due to block rendering complexity. |
| G14 | **Entry row sidebar** | Low | 76px sidebar with large Cormorant numbers + depth dots. Design polish. |
| G15 | **Depth navigator** | Low | Summary / Claims / Sections / Full horizontal toggle in reader. |
| G16 | **Novelty badges** | Low | "Mostly new" / "72% new" / "Partly familiar" semantic badges. |
| G17 | **Dismissed articles archive** | Low | Archive view for swiped-left articles. |
| G18 | **Structured comparison** | Low | Elicit-style multi-article comparison matrix. |
| G19 | **Blindspot detection** | Low | Topics with many articles but few absorbed claims. |
| G20 | **Contradiction detection** | Deferred | Corpus too harmonious (86% compatible). |
| G21 | **Book reader** | Deferred | Section-based long-form reading. |
| G22 | **Nomic embeddings** | Low | Experiments preferred Nomic over Gemini embeddings. Works fine with Gemini. |

### User Feedback Summary (from voice notes, Mar 8)
- **Article `6e3cb28c19e1`** (NotebookLM learning compression): User wants to bookmark AND follow multiple topics (AI-assisted learning, learning strategies). Wants topic overview to surface recently-bookmarked articles prominently. Voice feedback should support actionable commands (add tags, research topics, express interest).
- **Article `0708161ff37b`**: 94-second voice note recorded but transcription was client-side (old code). Note may not have been stored server-side — check logs. This was the last interaction before the backend transcription refactor.

---

## Key Design Documents

| Document | Purpose |
|----------|---------|
| `research/system-state-of-the-art.md` | **START HERE** — Comprehensive reference covering all research, algorithms, data structures, experiments, UI mockups |
| `research/novelty-system-architecture.md` | Architecture design for the knowledge-aware system |
| `research/experiment-results-report.md` | Results from 11 validation experiments |
| `research/experiment-log.md` | Append-only chronological experiment log |
| `research/ux-redesign-spec.md` | 2 rounds of mockup feedback, approved interaction models |
| `design/DESIGN_GUIDE.md` | The Annotated Folio design system specification |
| `research/knowledge-diff-interfaces.md` | HCI research on adaptive presentation (dimming, stretchtext) |
| `research/knowledge-tracing-for-reading.md` | FSRS/BKT adaptation for reading knowledge |
| `research/knowledge-deduplication.md` | Embedding + dedup architecture |
| `research/topic-normalization-spec.md` | Topic normalization & defragmentation spec — registry design, LLM merge-or-create, defrag algorithm, Otak lessons |
| `research/user-guide.md` | User-facing guide (markdown source) — also at `app/public/guide/index.html` (HTML) |

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/gemini_llm.py` | Shared Gemini LLM wrapper (google.genai SDK). `call_llm()`, `call_chat()`, `call_with_search()`. Model: `gemini-3.1-flash-lite-preview` |
| `scripts/build_articles.py --claims` | Extract atomic claims, entities, and follow-up questions (Gemini 3.1 Flash-Lite, 10 parallel workers) |
| `scripts/build_articles.py --claims-only` | Extract claims/entities/questions for articles that don't have them yet |
| `scripts/build_articles.py --enrich` | Backfill entities + follow-up questions for existing articles (10 parallel workers) |
| `scripts/build_claim_embeddings.py` | Generate Gemini embeddings for all claims (batch 100) |
| `scripts/build_knowledge_index.py` | Build knowledge_index.json from embeddings (parallel delta reports) |
| `scripts/build_knowledge_index.py --skip-delta` | Build without LLM delta reports (faster) |
| `scripts/llm_audit.py` | View LLM usage/cost audit. `--days 7`, `--since 2026-03-01`, `--json` |
| `scripts/log_server.py` | Interaction log collector (port 8091, systemd `petrarca-log`) |
| `scripts/deploy_knowledge_index.sh` | Deploy to nginx + update manifest |
| `scripts/content-refresh.sh` | Full cron pipeline (fetch → extract → claims → embed → index → deploy) |
| `scripts/topic_normalizer.py` | Topic normalization + defragmentation. Normalize, defrag, enforce limits |
| `scripts/topic_registry.json` | Canonical topic registry — 25 broad, 172 specific topics with include/exclude descriptions. Auto-updated by normalizer, consolidated by defrag |
| `scripts/experiment_*.py` | 11 experiment scripts (see experiment-results-report.md) |
