# Unified User Journeys & Platform Consistency Plan

**Date**: March 10, 2026
**Scope**: All user journeys across mobile and web, with platform-specific interaction design and shared/separate code boundaries

---

## Philosophy

**Mobile** = touch-first, single-column, gesture-driven. The phone is for reading sessions and quick triage.

**Web** = keyboard-first, multi-column, hover-enhanced. The desktop is for browsing, deep reading with margin annotations, and knowledge exploration.

**Shared** = all business logic, data, design tokens, ranking algorithms, API calls. Never duplicate state or computation.

---

## Architecture: Shared vs Separate

### Always Shared (never fork)
- **Data layer**: `store.ts`, `queue.ts`, `knowledge-engine.ts`, `interest-model.ts`, `persistence.ts`, `logger.ts`
- **API calls**: `chat-api.ts`, fetch functions
- **Design tokens**: `colors.ts`, `typography.ts`, `spacing.ts`
- **Types**: `types.ts`
- **Utilities**: `display-utils.ts`, `reading-insights.ts`
- **Pure display components**: `DoubleRule`, `LensTabs` (already width-constrained)

### Separate Render Paths (Platform.OS branching)
- **Feed layout**: FlatList (mobile) vs ScrollView + CSS Grid (web) — *already done*
- **Reader layout**: Full-width (mobile) vs 3-column grid (web) — *already done*
- **Topics layout**: needs web path — *TODO*
- **Queue layout**: needs web path — *TODO*
- **Trails layout**: needs web path — *TODO*
- **Landscape layout**: needs web path — *TODO*
- **Gesture vs hover**: Swipeable cards (mobile) vs hover action buttons (web) — *already done on feed, needed on queue*

### Platform-Exclusive Features
| Feature | Mobile Only | Web Only |
|---------|-------------|----------|
| Swipe gestures | ✓ (feed, queue) | — |
| Haptic feedback | ✓ | — |
| Voice recording | ✓ (expo-av) | — |
| Screenshot capture | ✓ (react-native-view-shot) | — |
| Pull-to-refresh ✦ rotation | ✓ | — |
| Hover actions (✓/✕) | — | ✓ |
| Keyboard shortcuts | — | ✓ |
| KeyboardHintBar | — | ✓ |
| 3-column reader margins | — | ✓ |
| 2-column feed grid | — | ✓ |
| Browser-native scroll | — | ✓ |
| Sticky overlay tabs | ✓ | — |

---

## User Journeys

### J1: Content Discovery (Feed Browsing)

**Goal**: Find something worth reading from 180+ articles.

**Flow**:
```
Open app → See Up Next (resume or recommendation) → Browse lens (Latest/Best/Topics/Quick)
  → Decide per article: Read now / Queue for later / Dismiss / Ignore
```

**Mobile interactions**:
- Pull-to-refresh (✦ rotation)
- Scroll FlatList, sticky lens tabs appear after 300px
- Swipe right → queue, swipe left → dismiss (with reveal animations)
- Tap → open in reader
- Topic pills → filter by topic

**Web interactions**:
- Scroll 2-column grid (CSS Grid, max-width 1100px)
- Hover article → show ✓ (archive) and ✕ (dismiss) buttons
- Click → open in reader
- Keyboard: j/k navigate, Enter open, 1-4 switch lens
- Topic pills → filter by topic

**Shared**: Ranking algorithm (interest 60% + curiosity 40%), lens filtering, Up Next selection, Recommended selection, topic pills data, article cards (content, not layout).

**Gaps to fix**:
- [x] Feed web/mobile split already done (session 14)
- [ ] **Swipe hint tooltip** — show "← dismiss · queue →" once per install on mobile
- [ ] **"All topics >"** button on topic pills to enter Topics lens unfiltered

---

### J2: Deep Reading

**Goal**: Read an article with knowledge-aware assistance — see what's new, skip what's known, capture insights.

**Flow**:
```
Open article → See "What's New" card (novel claims) → Read with dimmed familiar paragraphs
  → Long-press to highlight → Tap entities for deep-dive → Ask AI questions
  → Tap in-article links to auto-ingest → Reach end → Completion flash
```

**Mobile interactions**:
- Full-width vertical scroll
- Long-press paragraph → amber highlight + haptic
- Tap entity → popup card (inline)
- ⋯ menu → Voice Note, Ask AI, Research, Report Scrape, Disregard
- ☆ bookmark toggle
- Progress bar at bottom

**Web interactions**:
- 3-column layout: left margin (220px) + center (article) + right margin (240px)
- Left margin: metadata, reading mode toggle, novelty bar, bookmark/actions as text links
- Right margin: section navigation, connected reading, further inquiry
- Keyboard: s=bookmark, a=Ask AI, d=done, e=toggle mode, m=toggle mode, Escape=back
- Progress bar fixed at page top
- Arrow keys scroll immediately (body overflow fix)

**Shared**: Reading modes (Full/Guided/New Only), paragraph dimming, claim classification, entity highlighting, encounter tracking, auto-ingest from links, all knowledge system logic.

**Gaps to fix**:
- [ ] **Per-paragraph action menu** — long-press should show Highlight/Research/Ask AI (both platforms, but contextual popup vs bottom sheet)
- [ ] **Reader date format** — left margin shows raw ISO for some articles
- [ ] **DoubleRule in reader** — add below title/meta section (both platforms)

---

### J3: Article Completion & Feedback

**Goal**: After finishing an article, record interest signals and move to next reading.

**Flow**:
```
Scroll to end → Completion flash (gold along progress bar) → "Done" button
  → PostReadInterestCard (new topics: +/−, known topics: tap-to-cycle)
  → Close card → Auto-advance to next queued article (with toast) OR back to feed
```

**Mobile interactions**:
- Tap "Done" at article end
- Interest card as overlay
- Toast: "UP NEXT: {title}" with "← Feed" escape
- `router.replace()` for auto-advance

**Web interactions**:
- Click "Done" or keyboard 'd'
- Interest card as overlay
- Auto-advance same logic
- Keyboard Escape to cancel auto-advance

**Shared**: PostReadInterestCard, interest signal recording, queue auto-advance logic, encounter finalization.

**Gaps to fix**:
- [ ] **Keyboard shortcut for interest card** — Enter to confirm, Escape to dismiss

---

### J4: Queue Management

**Goal**: Maintain a reading list, read articles sequentially.

**Flow**:
```
Add to queue (swipe/hover/in-reader-link) → Open Queue screen → Browse queued articles
  → Tap to read → Auto-advance through queue → Remove items by swiping/clicking
```

**Mobile interactions**:
- Access: ✦ drawer → Queue
- FlatList with Swipeable cards (swipe right to remove)
- Tap to open in reader

**Web interactions** (TODO):
- Access: ✦ drawer → Queue
- Max-width container, comfortable list layout
- Hover action: ✕ button to remove
- Click to open in reader
- Keyboard: j/k navigate, Enter open, x remove

**Shared**: Queue data (AsyncStorage), addToQueue/removeFromQueue, article display data.

**Gaps to fix**:
- [ ] **Web layout for Queue** — max-width container, hover remove button, no swipe
- [ ] **Await addToQueue** in swipe handlers (async safety)

---

### J5: Topic Exploration

**Goal**: Dive deep into a topic cluster, see what's new, find more reading.

**Flow**:
```
✦ drawer → Topics (or topic pill tap from feed) → Browse topic clusters
  → Expand cluster → See articles + delta report → Tap "Find more" → Research agent
  → Tap article → Reader
```

**Mobile interactions**:
- Access: ✦ drawer → Topics, or topic pill in feed
- ScrollView with expandable clusters
- Tap cluster header to expand/collapse
- Tap article row to read
- "Find more" triggers research agent

**Web interactions** (TODO):
- Same access paths
- Multi-column layout: topic list (left) + expanded detail (right)? Or just max-width centered with wider cards
- Hover on articles for quick actions
- Delta report more prominent on wider screen

**Shared**: Topic grouping from store, delta reports from knowledge engine, "Find more" research API call.

**Gaps to fix**:
- [ ] **Web layout for Topics** — centered max-width, wider cluster cards, possibly 2-column for expanded view
- [ ] **DoubleRule on Topics screen** — add below header

---

### J6: Research & Inquiry

**Goal**: Ask questions, spawn research, get answers.

**Flow**:
```
Reader → ⋯ menu → Ask AI → Chat with article context
Reader → Further Inquiry → Tap question → Chat opens with question
Reader → ⋯ menu → Research → Background agent launched
```

**Mobile interactions**:
- Ask AI: bottom sheet modal
- Further Inquiry: tappable question cards, "More questions ✦"
- Research: launches via API, results in Topics

**Web interactions**:
- Ask AI: bottom sheet modal (same)
- Keyboard 'a' opens Ask AI
- Further Inquiry: right margin section, clickable questions

**Shared**: Chat API, question generation, research agent spawning.

**No major gaps** — this works consistently.

---

### J7: Knowledge Landscape & Reading Trails

**Goal**: Understand your reading territory — what topics you've explored, how they connect, what threads you're following.

**Flow — Landscape**:
```
✦ drawer → Your Landscape → Topic bubble map → Reading stats → Cross-thread bridges
```

**Flow — Trails**:
```
✦ drawer → Reading Trails → Active threads → Thread detail (article list) → Tap to read
```

**Mobile interactions**:
- ScrollView, topic bubbles as sized circles
- Tap bubble → navigate to topic in Topics screen? (currently no action)
- Thread cards with article dot indicators

**Web interactions** (TODO):
- Landscape: wider bubble grid, stats in side column
- Trails: 2-column — thread cards (left) + expanded detail (right)
- Keyboard navigation for thread selection

**Shared**: `reading-insights.ts` functions (getTopicBubbles, getActiveThreads, etc.), stats computation.

**Gaps to fix**:
- [ ] **Web layout for Landscape** — max-width, wider bubble grid, side-by-side stats
- [ ] **Web layout for Trails** — max-width, 2-column when expanded
- [ ] **Use DoubleRule component** (currently inline double rule in both)
- [ ] **Landscape useMemo stale data** — add feedVersion to deps
- [ ] **Bubble tap action** — navigate to topic cluster

---

### J8: Content Capture

**Goal**: Get articles into the system from various sources.

**Flow**:
```
Twitter bookmarks → automatic every 4h
Readwise Reader → automatic every 4h
Chrome clipper → ✦ button → auto-save with 10s countdown
Email forward → Cloudflare worker → /ingest-email
In-reader links → tap → auto-ingest + queue
Manual → import_url.py via SSH
```

**No platform-specific UI** — capture is either external (clipper, email) or in-reader (link tap works same on both platforms).

**No gaps** — capture flows are complete.

---

### J9: Voice Notes & Feedback

**Goal**: Capture thoughts while reading or browsing.

**Flow — Voice feedback**:
```
✦ floating button → Tap → Voice/Text overlay → Record or type → Auto-context detection → Submit
```

**Flow — Voice notes from reader**:
```
Reader → ⋯ menu → Voice Note → Record → Transcribe → Action extraction
```

**Flow — Browse voice notes**:
```
✦ drawer → Voice Notes → Date-grouped list → Transcripts → Action chips
```

**Mobile interactions**:
- Voice recording via expo-av
- Screenshot capture before modal opens
- Haptic on record start/stop

**Web interactions**:
- Text-only feedback (no recording)
- No screenshot
- Voice Notes browser needs web layout

**Shared**: Feedback storage, Soniox transcription, voice note display, action extraction.

**Gaps to fix**:
- [ ] **Voice Notes web layout** — max-width, wider cards
- [ ] **Silent failure handling** — voice recording errors should set error state

---

### J10: Navigation & Wayfinding

**Goal**: Move between screens, understand where you are.

**Current navigation model**:
```
Feed (home) ←→ Reader (push/back)
✦ Drawer → Topics, Queue, Voice Notes, Landscape, Trails, Activity Log
Reader → auto-advance → next queued article (replace, not push)
```

**Mobile interactions**:
- ✦ button in ReadingDeskHeader opens drawer
- Bottom sheet drawer (ink dark)
- Back gesture from reader
- Tab bar hidden (intentional)

**Web interactions**:
- Same drawer
- Keyboard: gi = go to index (feed), Escape = back from reader
- Reader top bar: prev/next article links

**Drawer quick actions**:
- "Triage" — **currently no-op, needs to launch triage mode**
- "Voice Note" — **currently no-op, needs to open voice recorder**

**Gaps to fix**:
- [ ] **Fix drawer quick actions** — Triage → navigate to feed triage view, Voice Note → open VoiceFeedback or navigate to voice-notes
- [ ] **DoubleRule on all screens** — currently only on feed + inline on trails/landscape

---

## Implementation Priorities

### Phase 1: Consistency & Bug Fixes (quick wins)

| # | Task | Files | Platform | Effort |
|---|------|-------|----------|--------|
| 1.1 | DoubleRule on Topics, Queue, Voice Notes screens | topics.tsx, queue.tsx, voice-notes.tsx | Both | Low |
| 1.2 | Fix drawer quick actions (Triage → feed triage, Voice Note → voice recorder) | PetrarcaDrawer.tsx | Both | Low |
| 1.3 | Await addToQueue in swipe handlers | index.tsx | Mobile | Low |
| 1.4 | Fix landscape useMemo stale deps | landscape.tsx | Both | Low |
| 1.5 | Fix reader date format in left margin | reader.tsx | Web | Low |
| 1.6 | Replace console.warn with logEvent | persistence.ts, VoiceFeedback.tsx, voice-notes.tsx | Both | Low |

### Phase 2: Web Layouts for Secondary Screens

| # | Task | Files | Notes |
|---|------|-------|-------|
| 2.1 | Queue web layout | queue.tsx | Max-width container (680px), hover ✕ remove button, no swipe |
| 2.2 | Topics web layout | topics.tsx | Max-width (960px), wider cluster cards, delta reports more visible |
| 2.3 | Trails web layout | trails.tsx | Max-width (960px), 2-column: thread list + expanded detail |
| 2.4 | Landscape web layout | landscape.tsx | Max-width (960px), CSS Grid bubble layout, stats sidebar |
| 2.5 | Voice Notes web layout | voice-notes.tsx | Max-width (680px), wider cards, transcript more visible |

### Phase 3: Interaction Parity ✅ Complete

| # | Task | Notes | Status |
|---|------|-------|--------|
| 3.1 | Queue keyboard shortcuts (web) | j/k navigate, Enter open, x remove. Focused card gets rubric left border. | ✅ |
| 3.2 | Topics keyboard shortcuts (web) | j/k navigate topics, Enter select/expand, o open first article. Focus + selected visual states. | ✅ |
| 3.3 | Swipe hint tooltip (mobile) | "← dismiss · queue →" pill over first card, once per install. Dismisses on swipe/tap/4s timeout. | ✅ |
| 3.4 | "All topics >" in feed topic pills | EB Garamond italic pill at end of pill scroll, switches to Topics lens. | ✅ |

### Phase 4: Polish & Design Gaps ✅ Complete

| # | Task | Notes | Status |
|---|------|-------|--------|
| 4.1 | AnimatedHighlightWrap | 200ms amber border fade-in (3px, #c9a84c) + background wash + padding shift. Light haptics on mobile. | ✅ |
| 4.2 | Knowledge bar staggered animation | 3 segments animate 0→actual width over 400ms, staggered 60ms. Percentage-based interpolation. | ✅ |
| 4.3 | DoubleRule in reader below title section | Both web and mobile paths, between meta row and novelty card. | ✅ |
| 4.4 | Error boundary in reader | ReaderErrorBoundary class component wraps content. Recovery UI with "Go back" button. Logs reader_error. | ✅ |

---

## Web Layout Patterns (Reference)

All secondary screens on web should follow this pattern:

```tsx
// Standard web container for content screens
const webContainer = Platform.OS === 'web' ? {
  maxWidth: 960,          // or 680 for reading-focused screens
  marginHorizontal: 'auto',
  width: '100%',
  paddingHorizontal: 32,  // more generous than mobile's 16
} : {};

// For screens with sidebar detail (Topics, Trails):
// CSS Grid: list (360px) | detail (1fr), maxWidth 1100
```

### Queue (web) — Reading-width
- Single column, 680px max-width centered
- Cards: title + summary + meta + hover ✕
- No swipe — hover removes

### Topics (web) — Content-width
- 960px max-width centered
- Cluster headers wider with delta report inline
- Expanded cluster: 2-column article grid

### Trails (web) — Split panel
- 960px max-width
- Thread cards in responsive grid (2-3 columns)
- Expanded thread: side panel or below, article list

### Landscape (web) — Full canvas
- 960px max-width
- Bubble grid uses CSS Grid for positioning
- Stats and sessions in 2-column layout

### Voice Notes (web) — Reading-width
- 680px max-width centered
- Wider transcript cards
- Action chips inline

---

## Interaction Consistency Rules

1. **Every destructive action has undo** — dismiss = can restore from archive, remove from queue = can re-add
2. **Every mobile gesture has a web equivalent** — swipe dismiss = hover ✕, swipe queue = hover +, long-press = right-click or button
3. **Every screen has DoubleRule** — below subtitle, above content
4. **Every screen logs navigation** — `screen_open` event with context
5. **Keyboard shortcuts on web are discoverable** — KeyboardHintBar or '?' overlay
6. **Drawer is the secondary nav for both platforms** — same items, same order, same destination
7. **No mobile UI leaks to web** — no touch targets, swipe hints, or bottom sheet styling on desktop
8. **No web UI leaks to mobile** — no hover states, keyboard hints, or multi-column layouts on phone
