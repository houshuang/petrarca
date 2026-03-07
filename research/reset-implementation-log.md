# Petrarca Reset: Implementation Log & Design Spec

**Date:** 2026-03-07
**Scope:** Full app reset — strip to essentials, fix pipeline, add interest model

---

## What Was Done

### The Problem
The app had accumulated 15+ features that didn't work end-to-end. The server pipeline was broken (wrong cron, `claude -p` dependency), concepts were wiped, no new content was ingesting. The app had too many half-working features (6-level depth zones, concept chips, spaced review, voice notes, book reader, research agents).

### The Solution
Declare bankruptcy on complexity. Ship a working end-to-end system: content flows in reliably → user reads on mobile → interest model learns → feed improves.

---

## Architecture After Reset

### App (Expo React Native)

```
Feed (single tab)
  ├── FlatList of articles, ranked by interest model
  ├── Swipe left → dismiss (negative signal)
  ├── Tap → open Reader
  └── Read articles shown below separator (muted)

Reader
  ├── Title + metadata
  ├── "What's new" card (novelty_claims)
  ├── Full article markdown
  ├── Long-press → paragraph highlight (positive signal)
  ├── Done button → mark read (positive signal)
  └── Post-Read Interest Card
        ├── 2-4 topic chips from interest_topics
        ├── [+] / [-] per chip (strong signals)
        └── Close (no forced interaction)
```

### Data Layer

```
store.ts (270 lines, was 1,188)
  ├── articles[]          — loaded from server/cache/bundled
  ├── readingStates       — Map<id, {status, time_spent_ms, ...}>
  ├── highlights[]        — paragraph highlights
  ├── signals[]           — user interaction signals
  ├── dismissedArticles   — Set<id>
  └── getRankedFeedArticles() → interest-scored list

interest-model.ts (250 lines, new)
  ├── InterestProfile     — topic → score mapping
  ├── recordSignal()      — applies weighted signal to topics
  ├── scoreArticle()      — 4-factor ranking
  └── Persisted to AsyncStorage

persistence.ts (78 lines, was 158)
  └── signals, reading_states, highlights only

content-sync.ts (137 lines, was 311)
  └── articles only (no concepts/syntheses/books)
```

### Pipeline (Hetzner Server)

```
content-refresh.sh (runs every 4h via cron)
  ├── fetch_twitter_bookmarks.py  → data/twitter_bookmarks.json
  │     └── NEW: thread reconstruction (follows in_reply_to chains)
  ├── fetch_readwise_reader.py    → data/readwise_reader.json
  ├── build_articles.py           → data/articles.json
  │     ├── LLM via litellm (gemini/gemini-2.0-flash by default)
  │     ├── NEW: extracts interest_topics[] and novelty_claims[]
  │     └── NEW: enhanced clean_markdown() (strips nav/cookie/subscribe cruft)
  ├── validate_articles.py --fix
  ├── extract_entity_concepts.py  → data/concepts.json
  │     ├── LLM via litellm
  │     └── Safety guard: won't overwrite non-empty with empty
  └── Copy to nginx /opt/petrarca/data/ + app/data/
```

---

## Interest Model Design

### Signal Weights

| Action | Type | Weight | When |
|--------|------|--------|------|
| Swipe right (keep) | positive | 1.0 | Feed triage |
| Swipe left (dismiss) | negative | 0.5 | Feed triage |
| Open article | positive | 0.5 | Feed tap |
| Tap Done | positive | 1.5 | Reader completion |
| Highlight paragraph | positive | 1.0 | Reader long-press |
| Interest chip [+] | positive | 2.0 | Post-Read card |
| Interest chip [-] | negative | 2.0 | Post-Read card |

Signals on a specific topic propagate 0.3x to the parent broad topic.

### Topic Scoring

Each topic has `positive_signals` and `negative_signals` (weighted sums). Score computed as:

```
raw_score = positive / (positive + negative)
confidence = min(total_signals / 10, 1)
smoothed = 0.5 * (1 - confidence) + raw_score * confidence   # Bayesian smoothing
final = smoothed * decay                                      # 30-day half-life
```

Bayesian smoothing means < 10 signals → score stays near 0.5 (neutral). After ~20 decisions, personalization kicks in.

### Feed Ranking

```
score = interest_match * 0.40    # how much user likes these topics
      + freshness * 0.25         # sigmoid decay, 0.5 at 7 days
      + discovery_bonus * 0.20   # unknown topics get a boost
      + variety * 0.15           # penalize same-topic runs
```

Cold start (< 10 total signals): fall back to date sort.

### Data Model

```typescript
interface InterestProfile {
  topics: Record<string, TopicInterest>;
  updated_at: number;
}

interface TopicInterest {
  topic: string;
  level: 'broad' | 'specific' | 'entity';
  parent?: string;
  positive_signals: number;
  negative_signals: number;
  interest_score: number;    // 0-1, computed with decay
  last_signal: number;
  articles_seen: number;
}
```

Persisted as `@petrarca/interest_profile` in AsyncStorage.

---

## Article Schema (New Fields)

```typescript
interface Article {
  // ... existing fields ...
  interest_topics?: InterestTopic[];   // hierarchical topic tags
  novelty_claims?: NoveltyClaim[];     // what's genuinely new
}

interface InterestTopic {
  broad: string;      // "artificial-intelligence"
  specific: string;   // "ai-orchestration"
  entity?: string;    // "Claude Code"
}

interface NoveltyClaim {
  claim: string;      // "Claude Code now supports background agents"
  specificity: 'high' | 'medium' | 'low';
}
```

### Reading State (Simplified)

```typescript
type ReadingStatus = 'unread' | 'reading' | 'read';

interface ReadingState {
  article_id: string;
  status: ReadingStatus;
  last_read_at: number;
  time_spent_ms: number;
  started_at: number;
  completed_at?: number;
  scroll_position_y: number;
}
```

Migration: old `depth` field mapped → `unread` stays `unread`, any other depth → `reading`, if `completed_at` exists → `read`.

---

## Pipeline: LLM Provider

Using **litellm** for all LLM calls. Advantages:
- Unified API across Gemini/Anthropic/OpenAI
- Easy to switch models via `PETRARCA_LLM_MODEL` env var
- Handles auth, retries, error formatting

Default model: `gemini/gemini-2.0-flash` (cheap, fast, good enough for extraction).

Can override globally: `PETRARCA_LLM_MODEL=anthropic/claude-sonnet-4-20250514` in .env.

API key bridging: `GEMINI_KEY` → `GEMINI_API_KEY` (litellm convention).

---

## Files Changed

### Modified (significant rewrites)
- `app/app/(tabs)/index.tsx` — 1,679→270 lines. Clean feed with swipeable cards.
- `app/app/reader.tsx` — 2,826→700 lines. Simple markdown reader + Done + Interest Card.
- `app/data/store.ts` — 1,188→270 lines. Articles + reading states + interest signals.
- `app/data/persistence.ts` — 158→78 lines. Just signals/states/highlights.
- `app/data/content-sync.ts` — 311→137 lines. Articles only.
- `app/data/types.ts` — Added InterestTopic, NoveltyClaim, simplified ReadingState.
- `scripts/build_articles.py` — litellm, interest_topics/novelty_claims extraction, enhanced clean_markdown.
- `scripts/extract_entity_concepts.py` — litellm, safety guard.
- `scripts/content-refresh.sh` — Full pipeline with logging, validation, syntheses disabled.
- `scripts/fetch_twitter_bookmarks.py` — Thread reconstruction.
- `scripts/import_url.py` — litellm, interest_topics/novelty_claims in output.

### New
- `app/data/interest-model.ts` — Topic interest tracking, scoring, feed ranking.

### Archived (moved to `app/_archive/`)
- `app/book-reader.tsx` — Book chapter reader with depth zones
- `app/(tabs)/library.tsx` — Library tab (in-progress articles)
- `app/(tabs)/review.tsx` — Spaced attention review tab
- `app/(tabs)/stats.tsx` — Progress/stats dashboard
- `components/WebSidebar.tsx` — Desktop web sidebar navigation
- `data/transcription.ts` — Soniox voice transcription
- `data/research.ts` — Research agent client
- `data/exploration-queue.ts` — Concept exploration queue
- `__tests__/transcript-concepts.test.ts` — Tests for removed functions
- `__tests__/transcription.test.ts` — Tests for removed functions

---

## Server Deployment Status

- **Code**: deployed to `/opt/petrarca/` on Hetzner
- **litellm**: installed in venv
- **GEMINI_API_KEY**: added to `.env`
- **Cron**: updated to run `content-refresh.sh` every 4 hours
- **Expo**: restarted, running on port 8082
- **Content**: 157 articles, 24 concepts, manifest updated
- **Pipeline test**: Successfully ingested 3 new articles with interest_topics extraction

---

## Next Steps

### Immediate (this week)
1. **Seed test batch**: Ingest ~25 Claude Code/AI agent articles via `import_url.py` to build a topic-focused corpus for testing the interest model
2. **Use the app for 2-3 days**: Triage articles, read a few, exercise the interest model
3. **Verify interest learning**: Check if topic scores diverge after 20+ signals (debug screen or console)
4. **Content quality audit**: Review clean_markdown output on real articles — are nav menus actually stripped?

### Short-term improvements
5. **Debug screen**: Add a gear icon in feed header → shows top interest topics with scores, total signal count, article count. Essential for validating the model.
6. **Swipe right to keep**: Currently only swipe-left (dismiss) is wired. Add swipe-right with a visual indicator and `swipe_keep` signal.
7. **Reprocess existing articles**: Run updated pipeline on existing 154 articles to backfill interest_topics/novelty_claims (those articles currently lack them).
8. **Pull-to-refresh**: Add pull-to-refresh on feed to trigger content sync manually.

### Medium-term
9. **Email forwarding**: Test and wire the `/ingest-email` endpoint on the research server for forwarded article emails.
10. **Web clipper**: The `clipper/` directory has a Chrome extension — wire it to the `/ingest` endpoint.
11. **Better topic hierarchy**: Currently topics are flat strings. Build a topic taxonomy (broad → specific → entity) from accumulated data.
12. **Interest model decay tuning**: The 30-day half-life may be too aggressive or too slow. Adjust based on actual usage patterns.
13. **Migrate litellm to google.genai**: If litellm feels heavy, the new `google.genai` SDK is lighter. But litellm's multi-provider support is worth the weight for now.

### Potential resurrections from archive
14. **Paragraph highlighting → research**: Re-enable "Research this highlight" once the basic loop is solid.
15. **Spaced review**: The concept review system was well-built. Could revive it once the interest model has identified which topics matter.
16. **Voice notes**: Useful for capturing thoughts while reading. Lower priority than getting the basic loop working.

---

## Design Decisions & Rationale

### Why strip instead of fix?
The old app had 15+ features at various levels of brokenness. Fixing each one would take longer than rebuilding the core. The archived code is still there — nothing is lost, just parked.

### Why interest model instead of just chronological?
40+ articles/week from diverse sources. Without ranking, the user sees whatever came in last. The interest model means articles about topics you care about float to the top, while still showing diverse content (20% discovery bonus).

### Why Bayesian smoothing?
Without smoothing, a single dismiss on a topic would tank its score to 0. With smoothing, it takes ~10 signals before the model confidently deviates from 0.5 (neutral). This prevents snap judgments.

### Why litellm instead of direct API?
Three reasons: (1) unified interface, (2) easy model switching via env var, (3) future-proof if we want to try Claude/GPT for specific tasks.

### Why 3 reading states instead of 6?
The old depth system (unread → summary → claims → concepts → sections → full) was confusing. Users just want: haven't seen it, started reading it, finished it. Everything else is UI affordance, not state.

### Why no concepts in the app?
Concepts are still extracted by the pipeline (24 in the database). But the concept chips/ConceptSheet/spaced review added complexity without clear value yet. Once the interest model proves useful, concepts can be layered back in as a "deep dive" feature.
