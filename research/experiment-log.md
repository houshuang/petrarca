# Experiment Log

> Append-only. New entries at top. Never delete existing entries.

---

## 2026-03-09 — Session 10: Chrome Clipper Countdown + Tweet Ingestion + Cookie Auto-Sync

**What**: Three features for the Chrome clipper extension and server-side tweet processing.

### Clipper Auto-Save Countdown
- **Design exploration**: 2 rounds of mockups (5 each) via design-explorer
- Round 1: Circular ring, progress bar, typography-first, pulsing button, marginalia — all too large
- Round 2 (refined): Big number minimal, bar under rule, inline countdown button, compact margin, **double rule as timer** (selected)
- **Variant #5 chosen**: The signature double rule IS the countdown timer. Rubric color drains to gray over 10s. Countdown number (Cormorant 22px) in header top-right.
- **States**: counting (10s, auto-save) → paused (typing triggers) → saving → saved (gold flash + auto-close)
- **Implementation**: `requestAnimationFrame` for smooth 60fps timer (not CSS animation — need precise pause). Note field always visible with dashed border placeholder. Visible Cancel button (Esc unreliable in Chrome popups).
- **Removed**: Note toggle button (note field always shown), centered header (now flex row with countdown number)

### Tweet URL Ingestion via Twikit
- **Problem**: Clipping a twitter.com/x.com page via the clipper went through generic URL import, which fails on Twitter's hostile DOM
- **Solution**: `/ingest` endpoint detects tweet URLs → routes to `run_ingest_tweet()` → twikit `get_tweet_by_id()` → thread reconstruction → extract linked article URLs → ingest through normal pipeline
- **Three paths**: (1) Tweet has URLs → resolve t.co, ingest linked article, tweet text as context note. (2) No URLs → tweet/thread text becomes article content. (3) Twikit fails → fallback to normal URL import.
- **Reuses**: `tweet_to_dict()`, `reconstruct_thread()` from `fetch_twitter_bookmarks.py`, `_collect_urls_from_bookmark()` from `build_articles.py`

### Twitter Cookie Auto-Sync
- **Problem**: twikit cookies expire, requiring manual SSH to refresh
- **Solution**: Chrome extension extracts `auth_token` + `ct0` via `chrome.cookies.get()` API whenever user visits X.com. POSTs to `POST /twitter/cookies` endpoint. Throttled to 4h via `chrome.storage.local` timestamp.
- **Also added**: `GET /twitter/status` health check (validates cookies, returns age)
- **Key insight**: `chrome.cookies` API can read HttpOnly cookies (which page JS cannot), making the extension the ideal place for this

### Files Changed
- `clipper/popup.html`, `clipper/popup.css`, `clipper/popup.js` — countdown UI
- `clipper/manifest.json` — added `cookies` + `host_permissions`
- `clipper/background.js` — cookie auto-sync on X.com visits
- `scripts/research-server.py` — tweet ingestion, cookie endpoints

---

## 2026-03-09 — Session 9: Feed & Navigation Redesign (Design + Implementation)

**What**: Major UX redesign — 3 rounds of mockups (15 total), user interview, full implementation of unified single-screen architecture replacing the 4-tab layout. Complete rebuild of feed, navigation, and ranking system.

### Design Exploration
- **Round 1** (5 mockups): Compact Timeline, Sectioned Feed, Source Streams, Magazine Hero, Dual Mode Triage. All neutral — too incremental.
- **Round 2** (5 mockups): Reading Desk, Swipeable Lenses, Contextual Home, Manuscript Marginalia, Card Stack Tinder. Three thumbs up (Desk, Lenses, Contextual Home). Card Stack interesting as alternative mode.
- **Round 3** (5 mockups): Unified Sections, Lens Tabs, Hybrid Scroll+Lenses, Topics Lens Active, ✦ Drawer. All thumbs up. Direction approved.

### User Interview Findings
- **Mindset varies by day** — needs easy mode switching, not one fixed default
- **Queue should be integrated into feed** as "Up Next", not a separate destination
- **Topics and Log are secondary** — can be demoted from top-level nav
- **Mental model is mixed** — topic, urgency, commitment all matter at different times
- **"This is a river, not a todo list"** — no counts, no stats, important stuff rises to top
- **Dynamic reranking** — reading related content should deprioritize similar articles

### Implementation (all 5 phases complete)

#### New Components (7 files)
- `DoubleRule.tsx` — Reusable double rule separator (2px + 5px gap + 1px)
- `LensTabs.tsx` — Latest/Best/Topics/Quick tab switcher, rubric underline active indicator, sticky on scroll
- `UpNextSection.tsx` — Pinned top: in-progress resume (with progress bar) → next queued → algorithmic pick. ✦ drawer trigger button.
- `RecommendedSection.tsx` — Hero card for top-ranked article with Cormorant title, claim preview, novelty badge
- `TopicPillsSection.tsx` — Horizontal scroll of topic pills (first gets ink treatment), article counts
- `TopicsGroupedList.tsx` — Articles grouped by topic with tree-line indentation, expand/collapse (+N more)
- `PetrarcaDrawer.tsx` — Bottom sheet (ink bg): Triage/Voice Note quick actions + nav to Voice Notes, Log, Progress, Queue

#### Rewritten Files
- `app/(tabs)/index.tsx` — Complete rewrite. Single FlatList: ListHeaderComponent (UpNext → Recommended → Topics → DoubleRule), lens tabs as sticky data[0], articles sorted/grouped by lens. No header chrome. Swipe dismiss/queue preserved.
- `app/(tabs)/_layout.tsx` — Tab bar hidden (display:none), Topics/Queue/Log routes kept with `href:null` for drawer access.

#### Data Layer
- `store.ts` — Added `FeedLens` type, `getTopRecommendedArticle()`, `getArticlesByLens()`, `getArticlesGroupedByTopic()`, `getInProgressArticles()`, `getFeedVersion()`/`bumpFeedVersion()`. Integrated knowledge engine curiosity scores into `getRankedFeedArticles()`: blended ranking = interest model (60%) + curiosity score (40%).
- `queue.ts` — Added `getNextQueued()`, `peekQueue(n)`

#### Dynamic Reranking
- `useFocusEffect` on feed screen bumps `feedVersion` when returning from reader → triggers full re-rank
- `getRankedFeedArticles()` now blends interest model (60%) with knowledge curiosity (40%)
- Reading article X → `markArticleEncountered()` → FSRS ledger updated → articles sharing claims (cosine ≥0.78) lose novelty → rank lower on return
- Topic interest changes (+/- chips in reader) → `recordTopicSignalAtLevel()` → immediate effect on next feed render

### Hypotheses to Validate
1. **Lens usage distribution** — Which lenses get used most? Hypothesis: "Best" is default but "Latest" gets used when user wants to see what just arrived. Track via `lens_switch` events.
2. **Up Next engagement** — Does integrating queue into feed increase queue-to-read conversion? Track `up_next_tap` events by type (resume/queued/algorithmic).
3. **Topic pills → deeper exploration** — Do topic pills drive users into the Topics lens? Track `topic_pill_tap` → subsequent `lens_switch` to topics.
4. **Drawer discoverability** — Is ✦ obvious enough? Track `drawer_open` frequency. If low, may need onboarding hint.
5. **Dynamic reranking perceptibility** — After reading an article and returning to feed, does the user notice articles have moved? No direct metric — observe via session logs whether user scrolls to find things they saw before.
6. **Blended ranking quality** — 60/40 interest/curiosity blend: does curiosity scoring add value over pure interest model? Compare `recommended_tap` click-through rates with knowledge engine on vs. cold start.
7. **Chrome reduction** — Old: ~210px fixed chrome. New: ~56px (UpNext). Does content density improve engagement? Track scroll depth and articles-per-session.
8. **Quick lens utility** — Are ≤3min articles actually read more when surfaced separately? Track `lens_switch` to quick + subsequent article opens.

### Events Logged
- `lens_switch` — { from, to }
- `recommended_tap` — { article_id }
- `topic_pill_tap` — { topic }
- `up_next_tap` — { article_id, type: resume/queued/algorithmic }
- `drawer_open` / `drawer_close`
- `drawer_item_tap` — { item }
- `topic_group_article_tap` — { article_id, topic }
- All existing events preserved (feed_article_tap, feed_swipe_dismiss, feed_swipe_queue, feed_pull_refresh, feed_articles_visible)

### Mockups
- Approved mockups in `/mockups/`: unified-sections, lens-tabs-top, hybrid-scroll-lenses, topic-lens-view, drawer-menu

---

## 2026-03-09 — Session 7: Claim feedback design exploration + behavioral encounter tracking

**What**: Explored claim-level feedback UI via 4 design mockups, then pivoted to behavioral inference approach. Implemented scroll-aware encounter tracking and curated "What's new" card.

### Design Exploration (G1)
- Generated 4 mockups via design-explorer: Margin Glyphs, Inline Callouts, Hybrid Overview+Markers, Progressive Reveal
- "Hybrid: Overview + Inline Markers" got thumbs up (colored left-margin bars, tap to reveal claim panel)
- **Key decision**: User decided per-claim feedback is wrong direction. Knowledge model should infer from reading behavior (scroll depth, time, highlights), not explicit "I knew this" buttons. G1 descoped.
- "Tell me more" / research spawn remains valuable as a separate feature

### Data Analysis
- Inspected claim_type distribution: 60% factual (514), 17% procedural (148), 11% evaluative (96), 6% causal (53), 2% comparative/experiential/predictive
- Many "factual" claims are trivial (e.g., "project claims to be made by one person") — not useful to surface in UI
- All 858 claims have source_paragraphs (avg 1.1 per claim) — good for paragraph-level tracking

### Implementation
- **`knowledge-engine.ts`**: Added `markArticleReadUpTo(articleId, maxParagraphIndex, engagement)` — only marks claims in paragraphs up to estimated scroll depth. Added `getArticleParagraphCount()`. Added `claim_type` to ClaimClassification output.
- **`reader.tsx`**: Track `maxScrollY` (furthest scroll position). On reader close, estimate paragraph read up to from `(maxScrollY + viewportHeight) / contentHeight`. Call `markArticleReadUpTo` with 'skim' (≤60s) or 'read' (>60s). "Done" button still marks ALL claims.
- **"What's new" card**: Prioritize non-factual claim types, cap at 3 items (was 5).
- **`types.ts`**: Added `claim_type: string` to `ClaimClassification` interface.

### Conclusions
- Behavioral signals (scroll depth, time, highlights) are the right approach for knowledge modeling — not explicit per-claim UI
- Claim type filtering significantly improves "What's new" card quality (causal > evaluative > comparative >> factual)
- The encounter tracking linear approximation (scroll % → paragraph %) is imperfect (header takes space) but much better than previous all-or-nothing approach

---

## 2026-03-09 — Session 6: Deployment, data migration, server hardening

**What**: Deployed all session 4+5 code, ran entity enrichment on full corpus, polished server robustness.

### Deployment
- Committed session 4+5 changes (45 files, +3750/-432 lines)
- Deployed scripts (gemini_llm.py, build_articles.py, research-server.py, import_url.py) to server
- Rebuilt and deployed web app (Expo SDK 54 web export → `/opt/petrarca/web/`)
- Installed `google-genai` SDK in server venv, restarted research server
- Verified end-to-end: research server health, nginx content serving, manifest hash updated

### Data Migration
- Added `--enrich` flag to `build_articles.py` — targeted LLM extraction of entities + follow-up questions for existing articles
- Enriched all 182 articles: **1,062 entities** and **499 follow-up questions** (10 parallel workers, ~2 min)
- Data live via nginx immediately (serves from `/opt/petrarca/data/` directly)

### Polish
- Upgraded `research_entity()` from `call_llm()` to `call_with_search()` — entity research now uses Gemini search grounding for real Google-grounded results
- Added `_read_json_body()` / `_send_json_response()` helpers to research server — all 8 POST endpoints now return clean 400 errors on malformed JSON instead of crashing the server (-46 lines of boilerplate)
- Fixed unhandled promise rejection in `voice-notes.tsx` `handleActionExecute`

---

## 2026-03-08 — Session 4+5: LLM migration + four parallel features

**What**: Major infrastructure overhaul (litellm → google.genai) + four features implemented via parallel agent worktrees.

### Session 4: LLM Infrastructure Migration
- **Problem**: litellm 1.82.0 truncates output from Gemini 2.5+/3.1 models
- **Solution**: Created `scripts/gemini_llm.py` — shared wrapper using native `google.genai` SDK
- Default model: `gemini-3.1-flash-lite-preview` (configurable via `PETRARCA_LLM_MODEL`)
- Migrated all callers: `build_articles.py`, `research-server.py`, `import_url.py`
- **Topic research rewrite**: `claude -p` (broken, 60-120s, hallucinated URLs) → Gemini search grounding (2.5s, real URLs)
- **Write contention fix**: `fcntl.flock` in `_locked_append_article()` for concurrent `import_url.py` processes

### Session 5: Four Features via Parallel Agents
Used isolated git worktrees with non-overlapping file ownership. Agent A owned pipeline+reader, Agent B owned server+new screens.

1. **Entity deep-dive** (Agent A): Pipeline extracts entities (7 types) + follow-up questions in existing LLM call. Reader: `EntityHighlightText` (dotted underline on mentions), `EntityPopup` (marginalia card), `FollowUpSection` (end-of-article questions). New types: `ArticleEntity`, `FollowUpQuestion`.

2. **Follow-up research prompts** (Agent A): 2-3 curiosity-driven questions generated during article processing. Displayed as "✦ FURTHER INQUIRY" section with left-bordered cards. Tap spawns topic research via `/research/topic`.

3. **Voice note browser** (Agent B): New `voice-notes.tsx` screen with date-grouped notes. `VoiceNoteCard.tsx` reusable component. `voice-notes-api.ts` API module. Accessible from Feed header "Notes" link.

4. **Voice note action extraction** (Agent B): `extract_note_actions()` uses Gemini to extract research/tag/remember intents from transcripts. Actions shown as tappable chips. `POST /notes/{id}/execute-action` endpoint.

### Results
- All four features implemented, merged, deployed, and verified working
- Entity/question pipeline fields added but only ~7 articles populated (need full pipeline re-run)
- Design reviewed via design-explorer before implementation (all 4 mockups thumbs-up)

---

## 2026-03-08 — Contradiction detection experiment

**What**: Tested LLM-based contradiction detection between claims across articles.

### Setup
- Candidate generation: pairs with cosine 0.55-0.85, different articles, shared topics, opinion-type preference
- 9,312 candidates found, judged top 50 with Gemini Flash
- LLM classifies as: HARD_CONTRADICTION, SOFT_CONTRADICTION, TENSION, COMPATIBLE

### Results
- COMPATIBLE: 43 (86%), TENSION: 5 (10%), HARD_CONTRADICTION: 2 (4%)
- **Both "hard contradictions" are false positives** — LLM stretches to find conflict between unrelated claims
- Tensions are real but weak (e.g., "LLMs are good at looping" vs "system needed 1,197 invocations")
- **Conclusion**: This tech blog corpus is inherently non-contradictory. Contradictions would emerge from diverse/opposing sources (competing reviews, political debate). For now, CONTRADICTS classification can be deprioritized.

Script: `scripts/experiment_contradiction_detection.py`

---

## 2026-03-08 — Dedup, reading order, knowledge map experiments

**What**: Three more experiments building on the validated embedding/scoring system.

### Claim deduplication (complete-linkage)
- **Initial attempt** (single-linkage / union-find): produced runaway transitive chains — largest cluster had 133 members with avg internal similarity 0.660. Clearly wrong.
- **Fixed** with complete-linkage: all members must be pairwise ≥ 0.78
- **Result**: 174 clusters, 858 → 404 unique claims (47.1% remain, 52.9% reduction)
- Largest cluster: 26 claims (dcg articles), avg sim=0.853 — correctly grouped
- 12 cross-article clusters, 162 intra-article clusters
- 3,657 near-duplicate pairs in 0.72-0.78 range
- **Insight**: Most duplication is intra-article (claims within same article that overlap)
- Script: `scripts/experiment_claim_dedup.py`

### Reading order optimization
- Simulated 4 strategies across 47 articles: Curiosity Zone, Chronological, Random (avg 5 runs), Most Novel First
- **Curiosity Zone wins**: reaches 50% coverage by article 24 (vs 25 chrono, 25 most-novel), 75% by article 34 (vs 37 chrono, 35 most-novel)
- Curiosity Zone finds optimal article 5 at step 5 (AGENTS.md) — 64% novel with high context bonus from related claims already read
- 11.4% wasted reading (familiar content consumed) — comparable across strategies
- **Key pattern**: Curiosity Zone front-loads interconnected articles, reads isolated articles last
- HTML visualization: `data/reading_order_curves.html`, Script: `scripts/experiment_reading_order.py`

### Interactive knowledge map
- D3.js force-directed graph of 47 articles connected by 393 edges (≥3 shared claims)
- UMAP 2D layout from article-level embeddings (average of claim embeddings)
- Categories: 17 AI/Agents, 5 History, 5 Literature, 3 Dev Tools, 5 Knowledge, 12 Other
- Hover shows article title + top claims, search and topic filtering
- Annotated Folio styled (parchment, rubric, Cormorant Garamond)
- HTML: `data/knowledge_map.html`, Script: `scripts/experiment_knowledge_map.py`

---

## 2026-03-08 — Algorithm experiments: NLI, clustering, decay, curiosity

**What**: Ran 5 experiments to test algorithms from the research literature against the 47-article/858-claim corpus. Full results in `research/experiment-results-report.md`.

### Nomic vs Gemini embeddings
- Nomic-embed-text-v1.5 (768 dim, local) beats Gemini embedding-001 (3072 dim, API)
- 4x smaller, 10x faster, wider discriminable range (0.68-0.93 vs 0.62-0.73)
- **Decision**: Nomic is default going forward. Scripts updated.

### NLI entailment (LLM judge)
- 32 claim pairs judged across 4 similarity buckets
- 75% agreement with cosine-only classification
- **Key finding**: Cosine overestimates in 0.65-0.80 range — LLM says UNRELATED where cosine says EXTENDS (4 cases)
- Below 0.65: perfect agreement, no LLM needed. Above 0.80: mostly agree.
- **Recommendation**: Add LLM judge only in 0.68-0.78 Nomic range (~5% of pairs)

### Topic clustering (BERTopic-style)
- UMAP + HDBSCAN found 59 clusters from 858 claims (7.8% noise)
- ~75 LLM topics map cleanly (purity > 0.6), ~6 broad topics fragment naturally (ai-agents → 9 clusters)
- No emergent topics found — LLM topic assignment is comprehensive
- **Recommendation**: Use clusters for sub-topic splitting on broad topics

### FSRS knowledge decay
- Initial BASE_STABILITY=5 days was far too aggressive (83% forgotten after 7 days!)
- Tuned to BASE_STABILITY=30 days — realistic for reading comprehension
- Engagement multipliers: skim(0.3x=9d), read(1x=30d), highlight(2x=60d), annotate(4x=120d)
- Spaced re-encounter multiplies stability by 2.5x (natural spaced repetition)
- **New classification**: PARTIALLY_KNOWN (R between 0.3-0.5) — "seen before, details fuzzy"

### Curiosity zone scoring
- Score peaks at ~70% novelty (Gaussian) + context bonus (some KNOWN) + bridge bonus (EXTENDS)
- **Correlation with naive novelty: 0.051** — fundamentally different ranking
- Promotes articles adjacent to existing knowledge (history article #31→#7)
- Demotes completely disconnected 100%-novel articles (#10→#16)
- **Recommendation**: Replace discovery_bonus in feed ranking with curiosity zone

### Scripts created
- `scripts/experiment_nli_entailment.py`
- `scripts/experiment_topic_clustering.py`
- `scripts/experiment_knowledge_decay.py`
- `scripts/experiment_curiosity_zone.py`

---

## 2026-03-08 — End-to-end novelty system validation

**What**: Built and validated the complete novelty-aware reading system pipeline: atomic claims → embeddings → knowledge tracking → delta reports → reading simulations. All 47 articles processed, 858 claims extracted and embedded.

### Claim extraction quality
- Added `_fix_pronoun_starts()` post-processing to `build_articles.py` — deterministic rewrites for "It is recommended..." → "Deploying X is recommended..." patterns
- Increased test runner `max_tokens` from 4096 → 8192 (fixed parse errors on long articles)
- Calibrated evaluator tolerances: self_contained allows 1 or 5%, compound allows 30%
- **Final result: 12/12 fixtures pass all 7/7 structural checks**

### Embedding pipeline
- Built `scripts/build_claim_embeddings.py` using `gemini-embedding-001` (3072 dimensions)
- **Key finding**: Gemini embeddings produce much lower cosine similarities than sentence-transformers. Related claims peak at ~0.73 vs ~0.90 typical.
- Calibrated thresholds: KNOWN ≥ 0.72, EXTENDS ≥ 0.62
- Cross-article similarity: 1 near-duplicate (0.90), 35 pairs > 0.80, 195 pairs > 0.75

### Reading simulations
- Built `scripts/simulate_reading.py` with 3 scenarios (tech, broad, sequential)
- Sequential scenario shows correct novelty decay: 100% → 72.7% → 58.8% → 23.1% as user reads related articles
- Delta reports correctly identify topic coverage: claude-code 91.7% after tech reading vs knowledge-management 8.6%
- HTML report generated at `data/reading_simulation_report.html`

### Conclusions
- The system works end-to-end and produces useful novelty signals
- KNOWN detection is directionally correct but threshold-sensitive
- Should test Nomic-embed-text-v1.5 for wider similarity distribution
- CONTRADICTS detection not yet implemented (needs LLM judge)
- Full report: `research/overnight-system-report.md`

---

## 2026-03-07 — Pipeline testing framework + clean_markdown hardening

**What**: Built a comprehensive testing framework for the article processing pipeline and used it to systematically harden `clean_markdown()` from ~15 patterns to 60+, achieving 25/25 fixture pass rate across diverse content types.

### Pipeline testing framework (`scripts/pipeline-tests/`)
Built a CLI framework with 4 test layers:
- **Layer 1: clean_markdown** — deterministic checks (no nav links, no cookie banners, no HTML residue, content preserved)
- **Layer 2: article_extraction** — LLM extraction with structural validation (required fields, section coverage, claim specificity)
- **Layer 3: entity_concepts** — batch concept extraction with deduplication checks
- **Layer 4: end_to_end** — full fetch→clean→extract pipeline on live URLs

Architecture: fixture-based inputs (HTML/markdown + metadata.json), session persistence (12-char UUID dirs with config/output/evaluation JSON), CLI via argparse with subcommands (`clean`, `extract`, `e2e`, `list`, `inspect`, `compare`, `fixture-list`). LLM calls use litellm with an instrumented wrapper capturing timing + token usage.

### clean_markdown() hardening
Expanded from handling 5 content types to 25+ verified fixture types. Key pattern categories added:

- **Academic**: arXiv nav links (`[View PDF]`, `[HTML...]`), metadata lines (Subjects, Cite as), PDF page headers/footers (`Author et al. — N — Month Year`), author affiliations
- **Platform chrome**: Substack (paywall gates, "Start Writing"), Medium (Member-only, claps, Recommended), Reddit (voting, awards, app CTA), GitHub (badges, Toggle navigation), HN (Guidelines footer)
- **Email**: forwarded message headers (block pattern), unsubscribe/opt-out footers, "sent from my" lines
- **Navigation**: Menu/hamburger, Sign in/up (both standalone and markdown link format), Search prompts
- **Ads/engagement**: ADVERTISEMENT/SPONSORED markers, app store badges, follower counts, emoji CTAs, vote/award lines
- **HTML residue**: `<div>`, `<span>`, `<footer>` tags, `<script>`/`<style>` with content, `<button>` elements, CSS class annotations
- **Multilingual**: NO/SV/DA/DE/FR/ES/IT/ID patterns for subscribe, follow, copyright, nav footers

Notable bugs found and fixed:
- **Regex ordering**: `Subjects?:` arXiv pattern was matching email `Subject:` headers, breaking forwarded-message block detection. Fix: moved email header block stripping before arXiv metadata stripping.
- **Optional group greed**: `<button>.*?(?:</button>)?` failed because non-greedy `.*?` matched empty string when closing tag was optional. Fix: split into separate `<input.../>` and `<button>content</button>` patterns.
- **Wikipedia [[edit]](URL)**: Double-bracket format left orphaned `(URL)` because existing regex only handled single brackets.

### Test results
- 25/25 clean_markdown fixtures pass (5 original + 8 synthetic platform types + 3 structural edge cases + 9 live URL captures)
- 7/7 end-to-end fixtures complete with good extraction quality
- 56 real fetched articles + 47 processed articles validated with 0 issues
- Table content preservation verified (123 pipe chars in → 123 out)
- Minimal content survival verified (2-paragraph article not stripped by aggressive cleaning)

### Fixtures created
**Synthetic**: substack-newsletter, medium-article, pdf-extraction, reddit-thread, github-readme, news-article, corrupted-html, hn-discussion, double-encoding, table-heavy, minimal-content
**Live URL captures**: simonwillison, arxiv, wikipedia (14K words), github/litellm, stackoverflow, codinghorror, paulgraham, gwern (12K words), martinfowler
**End-to-end**: simonwillison, stackoverflow, paulgraham, arxiv, gwern, codinghorror, martinfowler

---

## 2026-03-05 — Concept-Centric Reader: Entity concepts + concept chips + bottom sheet

**What**: Major redesign shifting the knowledge unit from sentence-level claims to named entity concepts. Four changes:

1. **Entity-style concepts**: Replaced 781 verbose sentence-concepts with 120 short named entities ("Garibaldi", "Greek colonization of Sicily", "Archimedes") extracted via `scripts/extract_entity_concepts.py` using Anthropic API. Each concept has: name (1-6 words), description, topic, aliases, related_concepts, source_article_ids.

2. **Concept chips zone**: Reader's second depth zone changed from claim cards to a compact chip layout. Chips color-coded by knowledge state (neutral=unknown, green border=learning, dashed/dimmed=known). Tapping a chip opens the ConceptSheet.

3. **ConceptSheet bottom sheet**: Slides up from bottom on chip tap. Shows: concept name + description, three-button state toggle (Unknown/Learning/Know this), "Also in" articles list (tappable → navigate), related concept chips (tappable → switch sheet), "Explore more" button (placeholder for exploration queue).

4. **Full article zone fix**: Now renders LLM-generated `sections[].content` instead of raw `content_markdown` (which had broken Wikipedia formatting). Falls back to raw markdown only when <2 valid sections. Added "View original source →" link.

**Entity extraction details**: `extract_entity_concepts.py` processes articles in batches of 5 via Anthropic API (claude -p can't run nested inside Claude Code). Extracts 5-12 entities per article, deduplicates by name/alias matching across batches, then runs a second pass for relationship extraction. 120 entities total, 77 with relationships.

**Store matching changes**: `conceptMatchesText()` uses substring matching on short entity names + aliases (much more reliable than old word-overlap on full sentences). Fallback to word-overlap only for legacy long-form concepts (>6 words).

**Result**: Reader feels much more natural — concepts map to real knowledge units. Chip taps → bottom sheet → navigate to related articles creates a clear exploration path. Full article text is readable now. TypeScript compiles clean across all 18 modified files.

---

## 2026-03-04 — Design Explorer v5: Soniox transcription + UX fixes

**What**: Three changes:
1. Replaced local whisper-cpp transcription with Soniox cloud API (`stt-async-v4`). Zero local deps needed — just API key.
2. Replaced confusing 1-5 rating buttons with binary thumbs up/down (👎/👍). Users mistook numbered buttons for navigation tabs.
3. Fixed drawing regression: draw mode now persists across SSE reloads (saved to localStorage), canvas z-index raised to 50 to ensure it's above mockup content, MutationObserver auto-initializes canvases for dynamically-added sections.

**Result**: Transcription should be much faster (cloud GPUs vs local whisper-cpp). Simpler rating UX. Drawing should survive page reloads.

---

## 2026-03-04 — Design Explorer v4: Fragment architecture

**What**: Refactored from single `designs.html` monolith to individual `mockup-N.html` fragment files assembled by the server at request time.

**Problem with monolith**: Claude had to read/write a single huge file containing the harness (300+ lines CSS/JS) plus all mockup sections. Every edit required finding the right mockup in a big file. Appending mockups meant passing the whole file context. The harness boilerplate wasted tokens on every read.

**New architecture**:
- Each mockup is a standalone `<section>` fragment: `mockup-1.html`, `mockup-2.html`, etc. (~20-40 lines each)
- Server reads the harness template (CSS/JS) from `assets/harness-template.html`
- On `GET /`, server globs `mockup-*.html` from the working dir, sorts numerically, injects them into the template
- `fs.watch` on the directory (not a single file) — triggers SSE reload when any `mockup-*.html` changes

**Benefits for LLM workflow**:
- Write: one 20-line file per mockup, no boilerplate
- Edit: read + edit one small file
- Delete: delete the file, page auto-removes it
- Parallel: 5 mockups = 5 parallel Write tool calls
- Never touch harness: CSS/JS updates go to the template, separate from content

**Server changes**: Replaced `DESIGNS_FILE` constant with `assemblePage()` function that globs + sorts + injects fragments. Watcher changed from `fs.watch(file)` to `fs.watch(dir)` with filename filter. Health endpoint now returns `mockupFiles` array.

**SKILL.md**: Updated to reflect fragment workflow — Claude writes `mockup-N.html` files directly.

---

## 2026-03-04 — Design Explorer v3: Fixing persistent UX issues

**What**: Third iteration on the Design Explorer skill. Real-world testing revealed v2 fixes didn't fully solve the core issues — rating buttons still non-interactive, waveform still invisible, audio still recording silence.

**Root causes identified**:

1. **Rating buttons not working**: `initRatings()` attached event handlers per-button at init time. If mockup sections were injected by SSE reload or after script execution, handlers wouldn't attach. **Fix**: Switched to document-level event delegation (`document.addEventListener('click', ...)` with `.closest()`) — works regardless of when mockups appear in DOM. Same for notes and feedback toggles.

2. **Waveform invisible**: `AudioContext` was being created but never resumed. Modern browsers suspend `AudioContext` until a user gesture + explicit `.resume()`. The `AnalyserNode` was connected but returning silence (all 128s in time domain data = flat line). **Fix**: Added `await audioCtx.resume()` immediately after creation. Also made waveform canvas bigger (200x32, was 120x24), added visible border + background, draws center reference line.

3. **Blank audio / wrong mic**: `getUserMedia({ audio: true })` was selecting whatever macOS considers "default" — with headphones plugged in, this could be a non-functional virtual device or headphone port with no mic. **Fix**: Added audio device enumeration dropdown (`enumerateDevices()`), shows all available audio inputs. Shows active device label during recording. User can explicitly select their mic before recording.

4. **Audio level bar CSS bug**: Fill element used `position: relative; bottom: 0` which doesn't anchor to bottom. **Fix**: Changed to `position: absolute; bottom: 0` so the green bar grows upward from the bottom like a real VU meter.

5. **Annotation position context**: composite capture via SVG foreignObject is unreliable (CORS, inline style depth). Even when it works, Claude can't always interpret the image. **Fix**: Now includes `strokeRegions` metadata — bounding box of each stroke as percentages of mockup dimensions (e.g., `{xPct: 15, yPct: 30, wPct: 40, hPct: 20}`). Claude can map these back to the HTML it generated.

**Key architectural lesson**: Event delegation is essential for any UI where DOM elements may be added dynamically (SSE reload, Claude appending mockups). Per-element `addEventListener` in init functions is fragile.

**Status**: Template updated. Needs testing with fresh designs.html generated from new template.

---

## 2026-03-04 — Design Explorer Skill: Build + v2 Fixes

**What**: Built a Claude Code skill (`/design-explorer`) for rapid visual design iteration — local Node.js server + HTML harness that lets users rate, annotate, and voice-critique design mockups, with Claude reading structured feedback and iterating.

**Architecture**:
- Zero-dep Node.js server (`~/.claude/skills/design-explorer/assets/server.js`) with SSE file watching, feedback storage, whisper-cpp transcription
- Single-file HTML harness with embedded CSS/JS — mockup sections appended by Claude
- SKILL.md defines the workflow: generate mockups → wait for feedback → iterate

**v1 issues found during first real use**:
1. Browser didn't auto-open when skill activated
2. Global draw canvas (`position: fixed; z-index: 9999`) blocked ALL clicks — couldn't rate or type notes
3. Annotations disappeared after each stroke (canvas cleared)
4. Annotation images were strokes on transparent background — no context of what was circled
5. No waveform or audio level feedback during recording
6. Headphones plugged in → no mic detected, but no warning shown
7. Voice critiqueSessions array was empty — recording pipeline had issues
8. Claude didn't know when user finished reviewing — had to be manually prompted

**v2 fixes**:
- Auto-open browser on server start (macOS `open`, Linux `xdg-open`)
- Per-mockup `<canvas>` overlays inside `.mockup-content` divs — headers/buttons remain clickable. `body.draw-mode .annotation-canvas { pointer-events: auto }` toggles interaction
- Strokes persist in localStorage, redrawn on reload via stored point arrays. `Ctrl+Z` undo support
- Composite annotation capture: SVG `<foreignObject>` renders mockup HTML to canvas, then overlays strokes. Falls back to strokes-only if browser blocks it
- Real-time waveform via Web Audio API `AnalyserNode` + audio level bar
- "No audio detected" warning after 3 seconds of silence
- `/feedback/wait` long-poll endpoint — Claude blocks until user clicks Submit, creating a closed iteration loop
- Better error handling: blob size check, chunked base64 encoding, toast notifications

**Key insight**: The global canvas pattern (common in drawing tools) is wrong for this use case where you need mixed interaction — rating buttons, text notes, AND drawing. Per-element canvas overlays with CSS-toggled `pointer-events` is the right approach.

**Key insight**: Long-poll (`/feedback/wait`) turns the workflow from "Claude generates, user manually prompts Claude" into a closed loop. Claude blocks on curl, wakes up when feedback arrives, reads it, iterates.

**Status**: Server endpoints verified (health, feedback, long-poll notification). Browser UX needs real-world testing of drawing + voice together.

---

## 2026-03-04 — Book Reader: UX Polish Pass (Session 3)

**What**: Third iteration on the Book Reader, implementing remaining research priorities. Focus: adaptive depth, Socratic reflection, concept familiarity indicators, suggested next sections, and enhanced feed integration.

**Improvements implemented**:

1. **Fixed Argument Skeleton View** — Completed the broken ternary operator in Claims zone from Session 2. Toggle now switches between flat claim list and tree view (main claims + supporting evidence indented). Added claimsHeaderRow, skeletonToggle styles.

2. **Adaptive Depth (Research Priority 7)** — When opening an unread section, analyzes concept familiarity by matching section key terms and claims against the user's known concepts. If 70%+ concepts are familiar, shows a purple "Skip to Claims" banner. Tapping scrolls to the claims zone. Dismissible.

3. **Socratic Reflection Prompts (Research Priority 4)** — Each section gets a deterministic contextual question shown in the reflection card: "What evidence would change your mind?", "How does this connect to what you know about X?", "What's the one key insight?", or "What's missing from this argument?". Amber styling with question icon.

4. **"What You Bring" in Briefing** — Green familiarity card showing concepts the user already knows that are relevant to this section (chips with checkmarks). Shows "N new concepts to discover" count. Uses concept store for real-time personalization.

5. **Key Term Familiarity Indicators** — Key Terms zone now shows "Familiar" badges (green) on terms matching known concepts, plus "Appears in N articles" counts. Terms with prior knowledge get a green left border.

6. **Suggested Next in Shelf** — BookShelfItem in Library now shows a green "Continue: Ch N, §M" button for books with partial progress, jumping directly to the next unread section.

7. **Engagement Stats on Landing Page** — Book Landing Page shows claims reviewed, reflections count, and average minutes per section.

8. **Enhanced Feed Book Cards** — Continue Reading cards for books now show the specific next section (Ch N, §M) and navigate directly to it instead of the landing page.

**Research priorities addressed**:
- Priority 3 (Argument Skeleton View): ✅ Fixed
- Priority 4 (Socratic Mode): ✅ Lightweight version
- Priority 7 (Adaptive Depth): ✅ Concept-based familiarity
- Walkthrough Gap #7 (Suggested Next): ✅ In shelf

**Files modified**: `book-reader.tsx`, `library.tsx`, `index.tsx`

**Build**: `npx tsc --noEmit` clean, `npx expo export --platform web` clean

---

## 2026-03-04 — Book Reader: UX Polish Pass (Session 2)

**What**: Continued iterating on the Book Reader based on the walkthrough analysis and research findings from the previous session. Focused on the moments between sections, chapter transitions, book completion, and the reading footer.

**Improvements implemented**:

1. **Chapter transition card** — When entering Section 1 of a new chapter, a green "Chapter N Complete" card appears showing the previous chapter's title and running argument summary, plus a "Now entering" badge for the new chapter. Addresses the walkthrough gap: "readers lose the forest for the trees."

2. **Personal thread in briefings** — The Briefing zone now surfaces up to 3 recent notes from the user's personal thread (from earlier sections). This means insights from Chapter 2 appear while reading Chapter 5, creating self-referential connections.

3. **Section mini-map in footer** — Replaced the text "§N of M" navigation label with a visual dot map. Each dot is color-coded: gray (unread), blue (in-progress), green (reflected), with the current section larger and highlighted. Dots are tappable to jump to any section in the chapter.

4. **Session stats in reflection card** — The "Section Complete" card now shows claims reviewed and paragraphs highlighted during this section's reading session, giving a sense of engagement depth.

5. **Book completion experience** — When finishing the last section of a book, a special "Book Complete" card replaces the usual "next section" button. Shows: stats grid (sections/minutes/claims/notes), the full running argument across all chapters, and a "Your Journey" section with the last 5 personal thread entries. Logged as `book_completed` event.

6. **Book overview button in Shelf** — Expanded shelf view now includes a "Book overview" button that navigates to the BookLandingPage, providing quick access to the thesis, argument, and chapter map.

7. **Pipeline: cross-connection relationship classification** — The ingestion pipeline now uses an LLM pass to classify connections as `agrees`/`disagrees`/`extends`/`provides_evidence`/`same_topic` instead of defaulting everything to `same_topic`. The book reader UI already had color-coded styling for each type.

8. **Pipeline: topic and thesis extraction** — The pipeline now automatically extracts 3-5 topic tags and a thesis statement from the book's key terms, claims, and running argument. These populate the Book Landing Page.

9. **Pipeline: books manifest generation** — The content-refresh.sh now generates `books.json` from individual book meta files and copies book chapter data to the nginx serving directory.

**Status**: TypeScript clean, web build clean. Pipeline enhancements untested (need Hetzner deploy + real EPUB).

---

## 2026-03-04 — Book Reader: Full Implementation + Research Deep Dive

**What**: Implemented the complete Book Reader feature (Mode B: "Deep Shelf") from the plan at `plans/sleepy-leaping-lagoon.md`, then conducted extensive research and simulated a 6-week user journey through the Arabic-Latin bridge reading cluster.

**Implementation** (all 9 tasks completed, TypeScript clean, web build clean):

1. **Types** (`types.ts`): Book, BookSection, BookClaim, KeyTerm, CrossBookConnection, BookReadingState, SectionReadingState, PersonalThreadEntry — ~80 lines of new interfaces.

2. **Persistence** (`persistence.ts`): loadBookReadingStates/saveBookReadingStates using Map-based `[key, value][]` tuple serialization.

3. **Content sync** (`content-sync.ts`): books_hash in manifest, books.json download, lazy fetchBookChapterSections() with local caching per chapter.

4. **State management** (`store.ts`): Module-level books/bookSections/bookReadingStates vars. Full accessors: getBooks, getBookById, getBookChapterSections, getBookReadingState, updateSectionReadingState, recordBookClaimSignal, addPersonalThreadEntry, getBookProgress, getBooksByTopic, getBooksNeedingContextRestore.

5. **Book reader** (`book-reader.tsx`, ~1100 lines): 4-zone progressive depth reader (Briefing → Claims → Key Terms → Full Text). Includes: CrossBookConnectionCard (tappable, navigates to referenced section), FloatingDepthIndicator, ClaimSignalPill, VoiceRecordButton/TextNoteInput, section completion with reflection prompt, prev/next navigation across chapters. Plus a **Book Landing Page** showing "What You Bring" connections, thesis, chapter map with section dots, running argument, and continue/start buttons.

6. **Library Shelf** (`library.tsx`): New 'shelf' view mode with BookShelfItem (expandable chapters, section dots), ContextRestoreBanner (amber, >2 days), ShelfTopicGroup (interleaved books + articles by topic).

7. **Feed integration** (`index.tsx`): In-progress books appear in Continue Reading horizontal scroll alongside articles, with blue book accent and progress percentage.

8. **Ingestion pipeline** (`ingest_book_petrarca.py`, 807 lines): pymupdf → section splitting → Gemini Flash extraction → cross-book matching. Output: books/{id}/meta.json + ch{N}_sections.json.

9. **Server endpoint** (`research-server.py`): POST /ingest-book with book path + optional chapter number.

**Research produced** (4 new documents):

- `kindle-integration.md` — No official API, Readwise is best middleware for highlights, kindle-api TypeScript lib for progress. Includes complete fetch_kindle_books.py script and EPUB position mapping code.
- `innovative-reading-patterns.md` — Scite.ai citation classification, Socratic AI vs summary AI, InfraNodus gap detection, Heptabase concept-level model.
- `innovative-reading-ux.md` — LiquidText/Passages/Roam cross-text visualization, context restoration psychology, interleaved reading pedagogy (effect size 0.65), gesture vocabulary design, 13 ranked recommendations.
- `book-reader-walkthrough.md` — Day-by-day simulation of reading 4 Arabic-Latin bridge books over 6 weeks: how briefings evolve, cross-book connections surface, personal thread builds, topic synthesis emerges. Identified 10 implementation gaps.

**Key insight from research**: Context restoration is the biggest unsolved problem in reading apps. No mainstream app (Kindle, Readwise, Apple Books) handles resumption after days well. Petrarca's data model already captures everything needed for a differentiated "Welcome Back" experience.

**Status**: Complete implementation. Books ingestion pipeline untested with real EPUBs (needs Hetzner deployment). App compiles and builds cleanly.

---

## 2026-03-04 — Research: Email Ingestion and Browser Web Clipper

**What**: Researched two new content ingestion paths: (1) forwarding emails to the pipeline, (2) a Chrome extension web clipper.

**Findings**:

Email ingestion — best approach is **Cloudflare Email Workers** (free, no port 25 needed, domain required). Worker uses `postal-mime` JS library to parse the raw email stream, extracts `<a href>` links and plain-text URLs, filters out tracking URLs and CDN assets, then POSTs the best candidate URL(s) to a new `/ingest` endpoint on the Hetzner research server. The research server spawns `import_url.py` in a background thread — same pattern as existing research agents. Self-hosted Postfix is the alternative but Hetzner blocks port 25 by default. Mailgun inbound requires paid plan.

Browser clipper — **unpacked Chrome extension** (3 files, no store submission). Manifest V3, popup with single "Save to Petrarca" button, POSTs `{url, title}` to `/ingest`. Same endpoint as email ingestion. Requires HTTPS on the server; Cloudflare Tunnel (`cloudflared`) is the simplest zero-config option.

Both paths converge on the same `/ingest` endpoint in `research-server.py` which calls `import_url.py` — no new pipeline logic needed.

**Status**: Research only, not implemented yet. See `research/ingestion-sources.md` for full code.

---

## 2026-03-04 — Experience Redesign: Connections, Web Notes, Review Context, Sicily Content

**What**: Two-part session. First: 4-part UI redesign making existing features visible and rewarding. Second: ran the Sicily topic exploration to populate the app with real diverse content (205 articles, 781 concepts, 199 cross-article connections).

**Part 1 — UI Redesign** (4 items from plan):

1. **Prominent Connection Moments** (`reader.tsx`): Replaced collapsed purple pill `ConnectionIndicator` with always-visible callout card. Purple-tinted background, left accent border, "Also explored in:" header with tappable article titles that navigate via `router.push`. Always expanded, max 3 connections shown.

2. **Web Note-Taking + Research Buttons** (`reader.tsx`): Added `TextNoteInput` component for web platform (replaces `VoiceRecordButton` which returns null on web). Expandable text input at bottom of reader, submits via `addVoiceNote()` with pre-filled transcript. Added "Research" button on each claim card — calls `triggerResearch()` with claim text + article context. Platform conditional: `Platform.OS === 'web'` switches between `TextNoteInput` and `VoiceRecordButton`.

3. **Review Cards with Real Context** (`review.tsx`, `store.ts`): Changed `getMatchingClaims()` return type from `string[]` to `{claim, articleTitle, articleId}[]`. Claims now show article attribution ("from [Article Title]") and are tappable to navigate to source. Shows 3 recent notes instead of 1. Contextual prompts reference actual articles: "You've seen this in [Article A] and N other articles. How has your understanding evolved?"

4. **Rewarding Progressive Depth** (`reader.tsx`): Enhanced `FloatingDepthIndicator` with claim/section counts ("Claims (3)"), connector lines between zones, active zone bolding. Added zone divider icons: bulb (purple) before Claims, document (amber) before Sections, book (green) before Full. Visual weight to section transitions.

**Part 2 — Content Honesty Check**:

After building UI, audited the data: only 47 articles all about AI coding tools, only 11/170 concepts spanning >1 article. Connection features had nothing to connect. Honest assessment: "lipstick on scaffolding."

**Part 3 — Sicily Topic Exploration** (ran existing but never-executed scripts):

- `explore_topic.py "Sicily — history, literature, geography, culture"` → 15 subtopics (5 foundational, 5 intermediate, 5 deep), 45 URLs
- `import_url.py --from-exploration --chunk` → processed all 45 URLs through full LLM pipeline
- Wikipedia articles chunked at H2 boundaries → rich sections
- **Result**: 205 articles total (195 Sicily + 10 original), 781 concepts, 199 cross-article connections
- Topics: Greek colonization, Arab-Norman culture, Frederick II, Sicilian School, Vespers, Verga, Pirandello, Sciascia, Lampedusa, Mafia, language, cuisine, Risorgimento, Archimedes, Opera dei Pupi, Bellini

**Part 4 — Inline Highlight Annotation** (built while waiting for import):

- Added "Note" button to highlight action bar (appears on long-press paragraph highlight)
- Tapping "Note" expands TextInput below the action bar
- Save persists note to `Highlight.note` field via new `updateHighlightNote()` in store.ts
- Measurement event: `highlight_note_added`

**Deployment**: Built web export (8.2 MB with embedded data), deployed to `http://alifstian.duckdns.org:8084`

**Files changed**: `reader.tsx`, `review.tsx`, `store.ts`

**Measurement events added**: `claim_research_tap`, `text_note_submitted`, `highlight_note_added`

---

## 2026-03-03 — Sprint: Highlighting, Dedup, Exploration, Live Pipeline

**What**: Full implementation sprint covering 8 parts across 19 files. Two concrete use cases driving the work: (1) live Twitter/Readwise pipeline running every 4 hours, (2) guided topic exploration mode for Sicily research trip.

**Implemented**:

1. **Paragraph highlighting** (`types.ts`, `persistence.ts`, `store.ts`, `reader.tsx`, `library.tsx`): Long-press any paragraph in full article view → amber highlight with haptic feedback. Highlights persisted to AsyncStorage. New "Highlights" view mode in Library tab groups highlights by article, sorted by recency. 4-second action bar appears after highlighting with "Research this" option.

2. **Dedup detection** (`build_articles.py`, `types.ts`, `reader.tsx`, `index.tsx`): Pipeline computes Jaccard similarity on topics + claim words between new and existing articles. Articles with score > 0.5 get `similar_articles` array. Reader shows amber "Similar to: [title]" banner below summary. Feed cards show italic dedup indicator.

3. **Topic synthesis prominence** (`content-sync.ts`, `store.ts`, `index.tsx`): Syntheses now downloaded from server alongside articles/concepts. Loaded from cached content on init. Purple synthesis cards shown in topic clusters view.

4. **Research agent enhancement** (`reader.tsx`, `index.tsx`, `stats.tsx`): "Research this" button on highlights sends paragraph text to research server. Auto-fetch research results on app launch with banner "N research results ready". Research results section promoted higher in Progress tab. Purple badge in reader top bar shows count for current article.

5. **Topic exploration mode** (`explore_topic.py`, `import_url.py`, `index.tsx`, `research-server.py`): New `explore_topic.py` takes seed topic, uses `claude -p` to generate 12-15 subtopics with URLs. `import_url.py` fetches and processes URLs through pipeline, supports Wikipedia H2 chunking. Feed shows "Exploring: {tag}" sections with breadth-first subtopic mixing. New `/research/explore` endpoint finds more content for subtopics user shows interest in.

6. **Live content pipeline** (`content-refresh.sh`, `fetch_twitter_bookmarks.py`, `fetch_readwise_reader.py`): Server-side cron every 4 hours. Fetches Twitter bookmarks via twikit + Readwise Reader via API. Runs `build_articles.py` and `generate_syntheses.py`. Copies output to nginx content directory. App syncs on launch via manifest hash comparison.

7. **Honest assessment** (`research/honest-assessment.md`): Frank self-critique document covering what works, what doesn't, risk-ranked assumptions, experiments that would matter.

**Server deployment**:
- Python venv with twikit, requests, trafilatura on Hetzner
- nginx content server on port 8083
- 4-hour cron at `/etc/cron.d/petrarca-refresh`
- Initial run: 50 Twitter bookmarks, 11,900 Readwise items fetched, 10 articles built, 11 concepts extracted
- Research server restarted with `/research/explore` endpoint
- Twikit cookies + Readwise token deployed

**Measurement events added**: `paragraph_highlight`, `paragraph_unhighlight`, `highlight_research_tap`

**Files changed**: 19 files, +2543 lines

---

## 2026-03-03 — Remaining Gap Fixes: Content Refresh, Research Agents, Synthesis, Connections

**What**: 7-agent swarm implementing all remaining gaps from the user journey analysis. These complete the core vision: live content, background research, cross-article synthesis, in-reading connections, knowledge pre-seeding, and scroll position persistence.

**Implemented (7 tasks)**:

1. **Concept ID stability** (`build_articles.py`): Switched from sequential `c0001` to `sha256(text)[:10]` hash-based IDs. Concept states, reviews, and notes now survive pipeline re-runs. All 176 concepts regenerated with stable IDs.

2. **Content refresh** (`content-sync.ts`, `store.ts`, `build_articles.py`, `setup-content-server.sh`): Full architecture for live content updates. Pipeline generates manifest.json with content hashes. App loads cached remote content on launch, checks for updates in background, merges new content preserving all user state. nginx serves on port 8083, cron runs pipeline daily at 7 AM UTC on Hetzner. Pipeline now supports `PETRARCA_SOURCES` env var for server-side source paths.

3. **Pre-seed knowledge** (`preseed_knowledge.py`, `store.ts`): Reads 537 Readwise items with >30% reading progress, matches against concept topics, pre-seeds 61/176 concepts as "encountered" on fresh install. Eliminates cold start — novelty scores differentiate from day 1.

4. **In-reading connection prompts** (`reader.tsx`, `store.ts`): New `getConceptConnections()` finds concepts matching a claim that the user has encountered in other articles. `ConnectionIndicator` component shows subtle purple pill below claims: "{topic} · seen in N other articles". Tappable to expand article titles. Logs `reader_connection_shown` and `reader_connection_tap`.

5. **Background research agents** (`reader.tsx`, `research.ts`, `research-server.py`, `stats.tsx`): Full pipeline: voice note transcription → "Research this?" banner → POST to Hetzner server → `claude -p` background research → results fetched in Progress tab. Server runs as systemd service. Results show perspectives, recommendations, connections in expandable cards.

6. **Cross-article synthesis** (`generate_syntheses.py`, `syntheses.json`, `index.tsx`, `store.ts`): Groups articles by primary topic, generates synthesis via `claude -p` for topics with 3+ articles. 2 syntheses generated (claude-code, ai-agents). Shown as purple-accented cards at top of expanded topic clusters in Topics view.

7. **Return-to-position** (`reader.tsx`, `store.ts`, `types.ts`): Saves scroll position every 2s, restores on re-entry with "Continuing where you left off" fade indicator. Clears when article fully read.

**Measurement events added**: `content_downloaded`, `content_refreshed`, `knowledge_preseed`, `reader_connection_shown`, `reader_connection_tap`, `research_triggered`, `research_result_viewed`, `synthesis_viewed`, `reader_position_restored`, `review_session_end_early`

---

## 2026-03-03 — User Journey Audit + Critical Gap Fixes

**What**: Comprehensive audit of assumed user journey vs. actual implementation, identifying 28 gaps and 5 critical assumption mismatches. Then a 5-agent parallel swarm to research, simulate, and fix the highest-impact gaps.

**User Journey Analysis** (`research/user-journey-analysis.md`):
Walked through 7 phases of expected use (first launch → months of habitual use). Found the biggest mismatches between what the design vision promises and what the implementation delivers:
1. Static content (no refresh mechanism — app dies after week 1)
2. "Reading is the signal" not true (only explicit button taps update knowledge model)
3. Cold start (all articles show "Mostly new", knowledge model too thin)
4. Background research agents unbuilt (key interview request)
5. Full article markdown rendering broken at deepest reading level

**Fixes Applied (3 agents, parallel)**:

1. **Markdown rendering** (`reader.tsx`, `markdown-utils.ts`): Rewrote MarkdownText to use proper block splitting (preserving code fences), ordered lists, blockquotes, italic, image alt-text. Added `splitMarkdownBlocks()` and `parseMarkdownBlock()` with 26 passing tests.

2. **Implicit signals → knowledge model** (`store.ts`, `reader.tsx`): New `processImplicitEncounter(articleId)` function. When user dwells >60s in claims/sections/full zone, all unknown concepts for that article auto-transition to "encountered". Fires once per reader session, excludes summary zone. Logs `implicit_concept_encounter` events.

3. **Review UX** (`review.tsx`, `store.ts`): Session capped at 7 items (`SESSION_CAP = 7`). "Done for now" messaging replaces "Session complete!" — soft hint shows remaining items. New `getMatchingClaims(conceptId)` function finds relevant claim excerpts via contentWords overlap (>0.2 threshold), shown on review cards for context.

**Research Delivered (2 agents, parallel)**:

4. **Knowledge model simulation** (`scripts/simulate_knowledge_model.py`): Modeled behavior over realistic usage. Key findings: 55% of articles had zero concepts (invisible to knowledge model), 25% of concepts unreachable at 0.3 threshold. Recommended: extract concepts for ALL articles, lower threshold, aim for ~280 concepts.

5. **Content refresh architecture** (`research/content-refresh-design.md`): Designed pipeline-on-Hetzner with daily cron, nginx serving JSON on port 8083 with manifest-based change detection, app fetches remote content with bundled fallback. Identified concept ID stability issue (must switch from sequential to hash-based IDs).

**Concept Re-extraction**: Based on simulation findings, re-ran concept extraction on all articles:
- 69 → **186 concepts** (2.7x increase)
- 39 → **107 topics**
- Article coverage: 21/47 (45%) → **47/47 (100%)**
- Concepts per article: median 4, range 2-8
- Cross-article concepts: 8 → **15**

**Measurement events added**: `implicit_concept_encounter` (article_id, trigger_zone, dwell_ms, concepts_updated, concept_ids), `review_session_end_early`

---

## 2026-03-03 — Voice Transcript → Knowledge Model Integration

**What**: Connected voice note transcripts to the knowledge model. Previously, transcripts were displayed but never analyzed. Now they're matched against article concepts, updating concept states and creating linked review notes.

**Implementation**:
- **`processTranscriptForConcepts()`** in `store.ts`: Same content-word matching as claim signals, but with 0.2 threshold (lower than claims' 0.3 — transcripts are noisier, already scoped to article's concepts). Matched concepts marked as `encountered`. Creates `ConceptNote` entries with `voice_note_id` set, deduplicated.
- **`getVoiceNoteById()`** accessor in `store.ts`
- **Wired into transcription flow**: `transcription.ts` calls `processTranscriptForConcepts()` immediately after successful transcription
- **Concept pills in Progress tab**: Expanded voice notes with transcripts show matched concepts as purple pills below the transcript text
- **Voice transcripts in Review tab**: `ReviewCard` shows linked voice note transcripts (mic icon, duration, date) between last note and source articles sections

**Tests**: New `__tests__/transcript-concepts.test.ts` — tests matching, state updates, note creation, deduplication, empty results, `getVoiceNoteById`

**Measurement events**: `transcript_concepts_matched` (article_id, voice_note_id, matched_count, concept_ids)

---

## 2026-03-03 — Spaced Attention Scheduling + Deployment

**What**: Built the spaced attention scheduling system (Phase 4a from plan) and deployed all changes to Hetzner.

**Implementation**:
- **Review tab**: New tab in navigation for concept-level spaced re-engagement
- **Scheduling algorithm**: Expanding intervals with difficulty tracking. Ratings map to multipliers: again(reset to 1d), hard(×1.2), good(×2.5), easy(×3.5). Difficulty adjusts ±0.1-0.3 per review.
- **Priority queue**: Concepts ranked by `overdue × relevance × topic_interest × maturity`. Relevance boosted 1.5× for concepts matching recent reading topics. Topic interest based on article engagement depth. New concepts get 1.3× maturity boost.
- **Review flow**: Card shows concept → previous notes → prompt "How does this connect?" → optional text note → 4-point understanding rating (confused / fuzzy / solid / could teach)
- **Auto-creation**: When claim signals transition a concept from unknown to encountered/known, review states are auto-created. "Known" starts at 7-day interval, "encountered" at 1-day.
- **Knowledge overview**: After completing review session, shows topic-level progress bars

**Types added**: ConceptReview, ConceptNote, ReviewRating
**Store functions**: getReviewQueue(), submitReview(), ensureReviewStates(), getConceptReview()
**Measurement events**: `concept_review` (concept_id, rating, stability_days, engagement_count, has_note)

**Deployment**: `exp://alifstian.duckdns.org:8082` — all features live including fluid reader, triage, knowledge model, voice notes, and review

---

## 2026-03-03 — Bug Fixes + Voice Notes + Connection Prompting

**What**: Fixed critical bugs in knowledge model (NoveltyBadge never rendered, weak concept matching). Added voice note recording, connection prompting, continue reading, and time-aware reading guidance.

**Bug Fixes**:
- NoveltyBadge: returned null when score >= 1.0, which was always true for uninteracted articles. Now returns null only when no concept data available.
- Concept matching: replaced raw word overlap (40% threshold including stop words) with content-word matching (30% threshold, stop words removed). Significantly better matching accuracy.
- Claim highlighting: added fallback word-overlap matching when substring match fails (handles paraphrased claims).
- ClaimSignalPill: now shows current signal state so users know when they've already reviewed a claim.
- triage_complete: moved from render body to useEffect to prevent logging on every render.

**New Features**:
- **Voice notes** (expo-av): mic button in reader top bar, records audio linked to article + reading depth context. VoiceNote type with transcription_status field for future Soniox integration. Voice notes summary in stats screen.
- **Connection prompting**: Related articles section at end of reader shows articles sharing concepts. Uses concept graph to find connections ("Connects via: concept X · concept Y").
- **Continue Reading**: horizontal scroll section at top of feed showing partially-read articles sorted by recency.
- **Time guidance**: bar in reader header showing time budget per depth level (30s summary, 2m claims, Xm sections, Xm full).

**Measurement events added**: `voice_note_start`, `voice_note_added`, `voice_note_permission_denied`, `continue_reading_tap`, `reader_related_tap`

---

## 2026-03-03 — Deep Design Experiments (Phase 1-3)

**What**: Major redesign cycle implementing 5 design experiments with specific hypotheses, building on the article-first foundation. Expanded content pipeline from 12 to ~50 articles across diverse topics (history, literature, AI/tech, policy). Built three experimental reader/feed modes.

**Hypotheses & Experiments**:

1. **Experiment 1A — Fluid Depth Transitions**: Replaced 4 discrete tabs with single scrollable document (Summary → Claims → Sections → Full Article). Hypothesis: continuous scrolling reduces friction and produces deeper reading than tab switching. Sticky floating depth indicator tracks position.

2. **Experiment 1B — Inline Claim Signals**: Claims highlighted in full article text with tap-to-signal floating pill. Hypothesis: in-context claim evaluation produces richer signals than isolated claim list. Color-coded: unsignaled=blue, knew_it=slate, interesting=green, save=blue.

3. **Experiment 1C — Implicit Time Tracking**: Silent instrumentation logging section_enter/exit timestamps, scroll_velocity, pause_duration (>3s), revisit events. Hypothesis: dwell time correlates with explicit interest signals (r>0.5).

4. **Experiment 2A — Card-Stack Triage**: Tinder-style swipe cards (right=save, left=skip, up=read now) with spring physics, rotation, stacked card depth. Hypothesis: forced binary choices produce >3x faster triage than list browsing.

5. **Experiment 2B — Topic Clustering**: Articles grouped by primary topic with collapsible headers. Hypothesis: clustering helps users engage with ≥3 topics per session vs 1-2.

**Pipeline Changes**:
- Removed Claude Code topic filter — processes ALL Twitter bookmarks with fetchable URLs
- Added Readwise Reader as second source (11,598 items, filtered to engaged articles with reading_progress > 0)
- Diversity sampling: round-robin across site_names to ensure topic breadth
- Incremental mode: skip URLs already in articles.json
- Target: ~50 articles across history, AI/tech, policy, literature, cultural theory

**UI Changes**:
- `reader.tsx` — Complete rewrite: fluid scrollable document, zone-based depth tracking, inline claim highlights with floating signal pill, implicit scroll/pause/velocity/revisit tracking
- `index.tsx` — Complete rewrite: 3 view modes (List/Topics/Triage), PanResponder card stack with Animated spring physics, LayoutAnimation topic clusters, AsyncStorage triage state persistence

**Measurement**: All interactions logged via logEvent() to JSONL. Events: reader_scroll_depth, reader_section_enter/exit, reader_scroll_velocity, reader_pause, reader_revisit, reader_claim_signal_inline, triage_swipe, cluster_expand/collapse, feed_view_mode.

---

## 2026-03-02 — Article-First Redesign

**What**: Complete redesign from tweet-triage app to article-first progressive reader. New data pipeline fetches actual article content, LLM processes it into sections/summaries/claims, and the app presents content at four progressive depth levels.

**Changes**:

Pipeline:
- New `scripts/build_articles.py` — 4-step pipeline: filter bookmarks → fetch articles (3-tier: trafilatura → requests+trafilatura → lxml) → deduplicate → LLM section/summary processing via `claude -p`
- Follows URLs in quoted tweets, treats long-form tweets (>100 words) as articles themselves
- Outputs `data/articles.json` with structured article data (sections, summaries, claims, topics)

Data model:
- `Article` replaces `Bookmark` as primary entity — includes content_markdown, sections[], key_claims[], reading state tracking
- `ReadingState` tracks per-article depth (unread → summary → claims → sections → full), section position, time spent
- `UserSignal` now references article_id with depth context

UI:
- **Feed** (index.tsx) — article list with title, source, summary, topics, read time
- **Reader** (reader.tsx) — progressive depth: Summary → Claims → Sections → Full article, with depth indicator tabs
- **Library** (library.tsx) — articles you've engaged with, by recency or topic
- **Progress** (stats.tsx) — reading depth breakdown, time spent, topic coverage

Results: 12 articles extracted from 41 filtered bookmarks. Simonwillison posts (previously failed) now extracted via 3-tier approach. Karpathy's 1125-word tweet treated as article.

---

## 2026-03-02 — Add Comprehensive Interaction Logging

**What**: Added JSONL-based interaction logging, persistent signal storage, and instrumented all screens. Modeled after ../alif's dual-layer logging system.

**Changes**:
- `app/data/logger.ts` — JSONL file logger writing daily files to device filesystem (`logs/interactions_YYYY-MM-DD.jsonl`). Session tracking, sequential write queue, export capability.
- `app/data/persistence.ts` — AsyncStorage-based persistence for user signals (survive app restarts).
- `app/data/store.ts` — Wired up persistence (load on init, save on every signal) and logging (log every signal with bookmark context).
- `app/app/_layout.tsx` — Store initialization, session start on app launch, tab press logging.
- `app/app/index.tsx` — Logs: `triage_swipe` (with direction, signal, position, remaining count, expand state), `card_toggle_expand`, `link_open`, `triage_complete`.
- `app/app/briefing.tsx` — Logs: `briefing_item_toggle`, `briefing_signal`, `briefing_topic_toggle`, `briefing_view_mode`, `link_open`.
- `app/app/claims.tsx` — Logs: `claim_source_toggle`, `claim_signal`, `link_open`.
- `app/app/stats.tsx` — Logs: `stats_refresh`, `logs_exported`. Added Event Log section with file listing and share/export.
- Added `expo-file-system` and `@react-native-async-storage/async-storage` dependencies.

**Events tracked**:
| Event | Screen | Data |
|-------|--------|------|
| `session_start` | global | session_id |
| `store_initialized` | global | total_bookmarks, loaded_signals |
| `tab_press` | global | tab name |
| `triage_swipe` | triage | direction, signal, bookmark_id, position, was_expanded, remaining |
| `signal` | all | bookmark_id, signal, author, topics, relevance, content_type |
| `card_toggle_expand` | triage | bookmark_id, expanded |
| `link_open` | all | bookmark_id, url, screen |
| `triage_complete` | triage | totals by signal type |
| `briefing_item_toggle` | briefing | bookmark_id, expanded |
| `briefing_signal` | briefing | bookmark_id, signal |
| `briefing_topic_toggle` | briefing | topic, collapsed, item_count |
| `briefing_view_mode` | briefing | mode |
| `claim_source_toggle` | claims | bookmark_id, claim excerpt, show |
| `claim_signal` | claims | bookmark_id, signal |
| `stats_refresh` | stats | — |
| `logs_exported` | stats | — |

**Rationale**: Since this is an experimental app, all user interactions need to be captured for later analysis — understanding which UI patterns work, how triage decisions are made, whether the swipe-vs-button paradigm affects signal distribution, etc.

---

## 2026-03-02 — Project Kickoff

**What**: Initialized Petrarca project. Analyzed interview.md for incremental reading concepts. Set up research directory structure. Beginning deep research on incremental reading, prior art, and knowledge modeling.

**Context**: User wants a mobile read-later app combining incremental reading, knowledge modeling (what do I already know?), and intelligent article selection (which articles have genuinely new information for me?). Key test case: Claude Code articles — high interest but overwhelming volume.

**Key reference**: ../alif project as model for mobile setup (Expo) and granular knowledge modeling (FSRS at word level → adapt to concept/topic level).
