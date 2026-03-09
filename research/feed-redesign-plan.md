# Feed & Navigation Redesign Plan

**Date**: 2026-03-09
**Status**: Approved direction, ready for implementation
**Based on**: 3 rounds of mockup exploration + user interview

## Design Philosophy

> "This is a river, not a todo list. The most important thing is that important stuff rises to the top."

The redesign replaces the 4-tab architecture (Feed / Topics / Queue / Log) with a **single unified screen** organized into scrollable sections with **lens-based switching** for the article list. Queue becomes "Up Next" integrated into the flow. Topics becomes a lens. Log, Voice Notes, and secondary features move into a **✦ drawer** (bottom sheet).

## Key Design Principles

1. **No counts, no stats** — Don't show "47 unread", "12 new". This isn't email. Content is a flowing river.
2. **Dynamic reranking** — Article position is never final. Reading a related article should deprioritize similar content. Marking topic interest should promote matching articles. Knowledge model updates (FSRS decay, new claims becoming "known") continuously reshape the feed.
3. **One screen, multiple lenses** — Same articles, different organizations. Switch with a tap, not a tab.
4. **Queue is position, not destination** — "Up Next" is the first thing you see, whether algorithmically chosen or manually queued.
5. **✦ is the escape hatch** — The ornament glyph becomes the menu button for everything secondary.

---

## Screen Architecture

### Before (4 tabs)
```
[Feed] [Topics] [Queue] [Log]     ← bottom tab bar (80px iOS)
```

### After (1 screen + drawer)
```
┌─────────────────────────────┐
│ [Up Next]        [✦ drawer] │  ← pinned top section
│─────────────────────────────│
│ ✦ RECOMMENDED              │  ← hero article (algorithmic pick)
│   [hero card with claim]    │
│─────────────────────────────│
│ ✦ TOPICS                   │  ← horizontal scroll of topic pills
│   [AI Agents] [Dev Tools].. │
│─────────────────────────────│
│ ═══════════════════════════ │  ← double rule
│ Latest │ Best │ Topics │Quick│  ← lens tabs (sticky on scroll)
│─────────────────────────────│
│ Article list...             │  ← full list, sorted by active lens
│ Article list...             │
│ Article list...             │
└─────────────────────────────┘
                                  ← NO bottom tab bar
```

### ✦ Drawer (bottom sheet)
```
┌─────────────────────────────┐
│ ── handle ──                │
│ ✦ Petrarca                  │
│                             │
│ ┌──────────┐ ┌────────────┐ │
│ │ Triage   │ │ Voice Note │ │  ← quick actions (2x2 grid)
│ └──────────┘ └────────────┘ │
│                             │
│ Voice Notes          ›      │  ← secondary nav items
│ Activity Log         ›      │
│ Reading Progress     ›      │
│ Queue Management     ›      │
└─────────────────────────────┘
```

---

## Sections Detail

### 1. Up Next (pinned, always visible)

Shows the next thing to read. Priority order:
1. **In-progress article** — with circular progress ring + "Resume" + "X min left"
2. **Next queued article** — if queue has items, shows the front of queue
3. **Algorithmic pick** — if no queue/in-progress, shows highest-curiosity-score article

If both in-progress AND queued exist, show in-progress with subtitle "then: [queued title]".

The ✦ button is right-aligned in this row, always accessible.

**Components needed**: `UpNextSection` (new)

### 2. Recommended (hero card)

The single highest-value article based on curiosity score × interest model × freshness. Gets prominent treatment:
- Large Cormorant Garamond title
- 1-2 line summary in Crimson Pro
- Best novelty claim with green left border (if available)
- Source + read time metadata
- "See all ›" link navigates to "Best" lens

This is NOT the same article as "Up Next" — it's the top-ranked unread that isn't already queued/in-progress.

**"See all ›" action**: Scrolls down and activates the "Best" lens.

**Components needed**: `RecommendedSection` (new)

### 3. Topics (horizontal scroll)

Horizontal scroll of topic cards showing the user's top topics by article count. Each card shows:
- Topic name (EB Garamond)
- Article count (DM Sans, muted)
- First card uses ink background (most active topic)

**Tap action**: Scrolls down, activates "Topics" lens, and filters to that topic.

**"All topics ›"** link: Activates Topics lens without a filter.

**Components needed**: `TopicPillsSection` (new)

### 4. Lens Tabs + Article List

A set of horizontal tabs that control how the article list below is sorted/organized. Tabs become sticky when scrolled to (stick below the status bar area).

#### Lens: Latest
- Chronological sort by `date` field (newest first)
- Compact article rows: title + source + relative time ("3h ago")
- No summaries (density optimized)

#### Lens: Best
- Sorted by curiosity_score × interest_score (current algorithm)
- Top article gets hero treatment (larger title, summary, claim preview)
- Rest are standard rows with optional "X new claims" badge

#### Lens: Topics
- Articles grouped by broad topic
- Each group: ✦ section header + topic name + count
- Articles indented with left tree-line border
- Expandable: shows top 3-4 per topic, "+N more ›" to expand
- Groups sorted by user's topic interest score

#### Lens: Quick
- Filtered to articles with `estimated_read_minutes <= 3`
- Sorted by curiosity score within that filter
- Shows read time prominently

**Components needed**: `LensTabs` (new), `ArticleList` (refactor from current), `TopicsGroupedList` (extract from topics.tsx)

---

## ✦ Drawer Detail

Bottom sheet triggered by tapping the ✦ ornament. Dark ink background (#2a2420), rubric accents.

### Quick Actions (top, 2-column grid)
- **Triage** — Enters card-stack triage mode (future implementation, card-by-card skip/queue/read decisions)
- **Voice Note** — Opens voice recording overlay (reuse existing `VoiceFeedback` component)

### Navigation Items
- **Voice Notes** — Links to existing `/voice-notes` screen
- **Activity Log** — Links to existing log screen (demoted from tab, kept as standalone screen)
- **Reading Progress** — Links to stats/progress view (if exists)
- **Queue Management** — Shows full queue with reorder capability (demoted from tab)

### Implementation
- Use React Native `Modal` or a bottom sheet library
- Animate slide-up with backdrop dimming
- Swipe down to dismiss
- The drawer is where the app name "Petrarca" lives — not in the main header

**Components needed**: `PetrarcaDrawer` (new)

---

## Dynamic Reranking System

This is the most important behavioral change. Currently articles are ranked once and stay put. The new system continuously adjusts:

### Signals that trigger reranking
1. **Reading an article** → All articles with overlapping claims (similarity ≥ 0.68) get deprioritized
2. **Topic interest change** (via +/- chips in reader) → All articles matching that topic get boosted/penalized
3. **Knowledge model update** (FSRS decay) → Articles whose claims have become "known" (R < 0.3) or "forgotten" lose novelty score
4. **Queue action** → Queued article removed from feed ranking (appears only in Up Next)
5. **Dismiss action** → Article removed entirely
6. **Time decay** → Freshness component continues to decay over time

### Implementation approach
The current `getRankedFeedArticles()` in `store.ts` already combines interest model + curiosity scoring. Changes needed:
- Make `feedArticles` reactive to reading state changes (currently only recomputes on mount via `useMemo([])`)
- Add `useMemo` dependency on a `readingStateVersion` counter that increments on any state change
- The reranking is already computed client-side — just needs to recompute more often

---

## File Changes Required

### Delete / Remove
- **Remove bottom tab bar**: Modify `app/(tabs)/_layout.tsx` to hide `tabBarStyle` or replace with a `Stack` layout
- **Remove tab references** from the layout

### Major Refactors

#### `app/(tabs)/_layout.tsx` → Unified layout
- Remove `Tabs` component entirely
- Replace with a single screen layout (or keep as single-tab with hidden bar)
- Alternative: Convert to `Stack` navigator showing only `index` as main, with `log`, `queue` as push targets from drawer

#### `app/(tabs)/index.tsx` → New unified home screen
The biggest change. Current feed screen becomes the entire app home. New structure:

```tsx
export default function HomeScreen() {
  return (
    <View style={styles.container}>
      {/* Status bar space */}

      {/* Up Next section (pinned) */}
      <UpNextSection />

      {/* Scrollable content */}
      <ScrollView stickyHeaderIndices={[stickyIndex]}>
        {/* Recommended hero */}
        <RecommendedSection />

        {/* Topic pills */}
        <TopicPillsSection />

        {/* Double rule */}
        <DoubleRule />

        {/* Lens tabs (becomes sticky) */}
        <LensTabs activeLens={lens} onLensChange={setLens} />

        {/* Article list (changes based on lens) */}
        <ArticleList lens={lens} topicFilter={topicFilter} />
      </ScrollView>

      {/* ✦ Drawer */}
      <PetrarcaDrawer visible={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </View>
  );
}
```

**Note**: Using `ScrollView` with `stickyHeaderIndices` for sticky lens tabs. The article list inside must NOT be a nested `FlatList` (RN doesn't support nested virtualized lists in ScrollView). Options:
- Use a single `FlatList` with section headers as list items (recommended)
- Or use `FlashList` which handles this better
- Or the sections above the lens tabs are the `ListHeaderComponent` of the FlatList

**Recommended approach**: Single `FlatList` where:
- `ListHeaderComponent` = UpNext + Recommended + Topics + DoubleRule + LensTabs
- `data` = articles sorted/grouped by active lens
- `stickyHeaderIndices` for lens tabs (tricky with ListHeaderComponent — may need to be a list item instead)

#### `app/(tabs)/topics.tsx` → Demoted to lens + standalone screen
- Extract `TopicCluster` component for reuse in Topics lens
- Keep as a full screen accessible from drawer (for deep topic exploration with delta reports)
- The Topics lens on home is a lighter version (grouped list, no delta reports)

#### `app/(tabs)/queue.tsx` → Demoted to drawer item
- Keep as standalone screen for queue management (reorder, remove)
- "Up Next" on home replaces its primary function
- Accessible via ✦ drawer → "Queue Management"

#### `app/(tabs)/log.tsx` → Demoted to drawer item
- No changes to the screen itself
- Just moved from tab to drawer navigation

### New Components

| Component | File | Purpose |
|-----------|------|---------|
| `UpNextSection` | `app/components/UpNextSection.tsx` | Pinned section showing in-progress + next queued |
| `RecommendedSection` | `app/components/RecommendedSection.tsx` | Hero card for top algorithmic pick |
| `TopicPillsSection` | `app/components/TopicPillsSection.tsx` | Horizontal scroll topic entry points |
| `LensTabs` | `app/components/LensTabs.tsx` | Latest / Best / Topics / Quick tab switcher |
| `TopicsGroupedList` | `app/components/TopicsGroupedList.tsx` | Articles grouped by topic with tree indentation |
| `PetrarcaDrawer` | `app/components/PetrarcaDrawer.tsx` | Bottom sheet with secondary nav |
| `DoubleRule` | `app/components/DoubleRule.tsx` | Extract existing double rule to reusable component |

### Store Changes

#### `app/data/store.ts`
- Add `getTopRecommendedArticle()` — returns single highest-scored article not in queue/in-progress
- Add `getArticlesByLens(lens, topicFilter?)` — unified function returning articles sorted by lens
- Add `getFeedVersion()` / state version counter for reactive reranking
- Export topic aggregation functions (currently computed inline in feed screen)

#### `app/data/queue.ts`
- Add `getNextQueued()` — returns front of queue without removing
- Add `peekQueue()` — returns first N items

---

## Implementation Order

### Phase 1: Foundation (can be parallelized)
1. **Extract reusable components**: DoubleRule, ArticleRow (from existing ArticleCard)
2. **Create PetrarcaDrawer**: Bottom sheet with navigation items
3. **Create UpNextSection**: In-progress + queue peek display
4. **Create LensTabs**: Tab switcher component with active state
5. **Add store functions**: `getTopRecommendedArticle()`, `getArticlesByLens()`

### Phase 2: Home Screen Assembly
6. **Rebuild index.tsx**: Assemble sections into single scrollable home
7. **Create RecommendedSection**: Hero card with claim preview
8. **Create TopicPillsSection**: Horizontal scroll topic cards
9. **Implement Latest lens**: Chronological sort
10. **Implement Best lens**: Current curiosity-scored ranking

### Phase 3: Topics Lens + Polish
11. **Create TopicsGroupedList**: Grouped view with tree indentation
12. **Implement Quick lens**: Filtered ≤3 min articles
13. **Implement sticky lens tabs**: Stick on scroll past sections

### Phase 4: Navigation Restructure
14. **Modify _layout.tsx**: Remove bottom tab bar, restructure routing
15. **Wire drawer navigation**: Log, Queue, Voice Notes accessible from drawer
16. **Update reader.tsx**: "Done" button returns to home (not tab)

### Phase 5: Dynamic Reranking
17. **Add reactive reranking**: Feed recomputes on reading state changes
18. **Cross-article deprioritization**: Reading article X deprioritizes similar articles
19. **Topic boost propagation**: Interest signals immediately affect feed order

---

## Mockup Reference

The approved mockups from round 3 are in `/Users/stian/src/petrarca/mockups/`:
- `mockup-unified-sections.html` — Main home screen layout (**primary reference**)
- `mockup-lens-tabs-top.html` — "Best" lens active state
- `mockup-hybrid-scroll-lenses.html` — Dark hero + horizontal recommended
- `mockup-topic-lens-view.html` — Topics lens with grouped articles
- `mockup-drawer-menu.html` — ✦ drawer bottom sheet

## Design System Compliance

All new components must follow `design/DESIGN_GUIDE.md`:
- Colors from `design/tokens/` (never hardcode)
- Four-font system: Cormorant (display), EB Garamond (titles), Crimson Pro (reading), DM Sans (UI)
- Double rule as section separator
- ✦ section markers in rubric color
- No icons — text-only navigation
- Touch targets ≥ 44×44pt
- Claim cards: left-bordered, no background

## Interaction Logging

All new UI elements must include `logEvent()` calls:
- `lens_switch` — { from, to }
- `recommended_tap` — { article_id }
- `topic_pill_tap` — { topic }
- `up_next_tap` — { article_id, type: 'resume' | 'queued' | 'algorithmic' }
- `up_next_skip` — { article_id }
- `drawer_open` / `drawer_close`
- `drawer_item_tap` — { item }
- `triage_mode_enter`
