# Knowledge System Implementation Status

**Date**: March 8, 2026 (last updated, late evening — session 5)
**Status**: Full corpus deployed with knowledge system, reader interactions, voice notes, AI chat, research agents, entity deep-dive, follow-up research, voice note browser + action extraction
**Latest commits**: Session 5 parallel agent implementation (entity deep-dive, follow-up prompts, voice notes browser, action extraction)

---

## What Was Built

On March 8, 2026, the full knowledge-aware reading system was implemented end-to-end based on the design in `research/novelty-system-architecture.md` and validated by 11 experiments documented in `research/experiment-results-report.md`. Subsequently, the full 182-article corpus was restored with claims, embeddings, and knowledge index, and a cost auditing system was added. In session 4, the LLM infrastructure was migrated from litellm to the native `google.genai` SDK (fixing output truncation with newer Gemini models), topic research was rewritten from `claude -p` to Gemini search grounding (reducing latency from 60-120s to ~2.5s), and write contention was fixed with file locking. In session 5, four features were implemented via parallel agents: entity deep-dive (long-press entities in reader), follow-up research prompts (end-of-article questions), voice note browser (new screen), and voice note action extraction (LLM intent extraction from transcripts).

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
| `app/lib/chat-api.ts` | API client for research server: `askAI()`, `uploadVoiceNote()`, `spawnTopicResearch()`, `fetchNotes()`. |
| `app/public/guide/index.html` | HTML user guide (Annotated Folio styled). Covers all 5 capture flows, 3 tabs, reader modes, knowledge system, usage patterns. Linked from Feed header. |
| `research/user-guide.md` | Markdown source for user guide. Describes all implemented features accurately. |
| `scripts/gemini_llm.py` | Shared Gemini LLM wrapper (google.genai SDK). Three functions: `call_llm()`, `call_chat()`, `call_with_search()`. Default model: `gemini-3.1-flash-lite-preview` (via `PETRARCA_LLM_MODEL` env var). Replaces all litellm usage. |
| `app/app/voice-notes.tsx` | Voice notes browser screen. Global notes view with date-grouped sections, ✦ markers, Cormorant Garamond header. Accessible from Feed header "Notes" link. |
| `app/components/VoiceNoteCard.tsx` | Reusable voice note card component. Shows timestamp, duration badge, transcript (3-line max), article link, action chips with type-colored borders. |
| `app/lib/voice-notes-api.ts` | Voice notes API module. `fetchAllNotes()`, `fetchArticleNotes()`, `executeNoteAction()`. TypeScript interfaces for `VoiceNote` and `NoteAction`. |

#### Modified Files (Session 4+5: LLM migration + four features)

| File | Changes |
|------|---------|
| `scripts/build_articles.py` | Migrated from litellm to `gemini_llm.call_llm()`. Added `_locked_append_article()` with `fcntl.flock` for write contention safety. Extended prompt schema with `entities[]` and `follow_up_questions[]`. Fixed `normalize_topic()` to handle dict inputs. |
| `scripts/research-server.py` | Migrated chat from litellm to `gemini_llm.call_chat()`. Rewrote topic research from `claude -p` to `gemini_llm.call_with_search()` (Gemini search grounding). Added `extract_note_actions()` for LLM intent extraction from transcripts. Added `POST /notes/{note_id}/execute-action` endpoint. |
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
| `app/app/(tabs)/_layout.tsx` | 3-tab layout: Feed / Topics / Queue. Text-only labels (EB Garamond), rubric dot active indicator. |
| `app/data/logger.ts` | Dual-write logging: local (localStorage/filesystem) + server buffer (batched POST to port 8091 every 5s). |
| `scripts/content-refresh.sh` | Full 6-step pipeline: fetch sources → build articles → validate → extract entities → extract claims → embed claims → build knowledge index → copy to nginx. |

### Data Generated

| File | Size | Contents |
|------|------|----------|
| `data/articles.json` | ~7 MB | 182 articles with `atomic_claims[]`, `entities[]`, `follow_up_questions[]` |
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
| Static web app (:8084) | ✅ Deployed | Rebuilt Mar 8 with bookmarks, AI chat, voice notes, research agents, guide |
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
| Research server endpoints | ✅ Updated | `/chat`, `/note`, `/research/topic`, `/notes`, `/notes/{id}/execute-action`, `/research`, `/research/results` on port 8090 |

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

### Immediate (next session)
23. **Resourceful bookmark pipeline enhancement** — When a tweet mentions a book/product/article without linking, pipeline should web-search, gather info, synthesize a small article.

### Short-term (quality improvements)
8. **Incremental embedding** — Only embed new claims, append to existing .npz
9. **LLM judge for ambiguous range** — 0.68-0.78 cosine gets LLM verification
11. **Production bundle optimization** — Remove bundled `knowledge_index.json` from JS bundle

### Medium-term (feature completion)
12. **Micro-delights** — Pull-to-refresh ✦ ornament, claim reveal animations, completion flash
13. **Entry row sidebar** — 76px sidebar with large numbers + depth dots

### Longer-term
14. **Contradiction detection** — Needs diverse sources
15. **Book reader** — Section-based long-form reading

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
| `research/user-guide.md` | User-facing guide (markdown source) — also at `app/public/guide/index.html` (HTML) |

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/gemini_llm.py` | Shared Gemini LLM wrapper (google.genai SDK). `call_llm()`, `call_chat()`, `call_with_search()`. Model: `gemini-3.1-flash-lite-preview` |
| `scripts/build_articles.py --claims` | Extract atomic claims, entities, and follow-up questions (Gemini 3.1 Flash-Lite, 10 parallel workers) |
| `scripts/build_articles.py --claims-only` | Extract claims/entities/questions for articles that don't have them yet |
| `scripts/build_claim_embeddings.py` | Generate Gemini embeddings for all claims (batch 100) |
| `scripts/build_knowledge_index.py` | Build knowledge_index.json from embeddings (parallel delta reports) |
| `scripts/build_knowledge_index.py --skip-delta` | Build without LLM delta reports (faster) |
| `scripts/llm_audit.py` | View LLM usage/cost audit. `--days 7`, `--since 2026-03-01`, `--json` |
| `scripts/log_server.py` | Interaction log collector (port 8091, systemd `petrarca-log`) |
| `scripts/deploy_knowledge_index.sh` | Deploy to nginx + update manifest |
| `scripts/content-refresh.sh` | Full cron pipeline (fetch → extract → claims → embed → index → deploy) |
| `scripts/experiment_*.py` | 11 experiment scripts (see experiment-results-report.md) |
