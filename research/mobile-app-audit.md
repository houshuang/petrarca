# Mobile App Audit: Plans vs Reality

**Date**: March 10, 2026
**Scope**: Comprehensive review of mobile app implementation against all design specs, planned features, and code robustness

---

## Executive Summary

The app is **~95% implemented** against the combined specs (design guide, UX redesign, feed redesign, novelty architecture). The knowledge system, reader, feed with lens tabs, voice notes, feedback capture, interest model, AI chat, and queue auto-advance are all working. The four-font typography system and color palette are correctly applied throughout.

The gaps are concentrated in: (1) visual polish/micro-delights from the design guide, (2) a few UX affordances that were planned but never built, and (3) defensive coding patterns (error boundaries, async safety).

---

## 1. Design System Compliance

### Fully Implemented

| Element | Location | Notes |
|---------|----------|-------|
| **Color palette** | `design/tokens/colors.ts` | All colors (parchment, ink, rubric, claim states, etc.) correctly defined and used throughout |
| **Four-font typography** | `design/tokens/typography.ts` | Cormorant Garamond (display), EB Garamond (titles/sections), Crimson Pro (reading), DM Sans (UI/meta) — all correct |
| **Design tokens** | `design/tokens/` | Colors, typography, spacing tokens consistently imported and used |
| **Claim cards** | Reader + feed | Left-bordered (2px), no background. Colors: default=#e4dfd4, new=#2a7a4a, known=#d0ccc0 |
| **Novelty badges/card** | Reader | "What's new" card with ✦ marker, gradient background, rubric left border, animated claim reveal |
| **Rubric dots** | Feed + reader | 4px circle as active indicator, list bullets, novelty markers |
| **Topic tags** | Feed + reader | EB Garamond italic 11.5px in rubric color |
| **Pull-to-refresh ✦ rotation** | `index.tsx` | ✦ ornament rotates during refresh, no spinner |
| **Claim reveal stagger** | `reader.tsx` (AnimatedClaimItem) | 80ms delay per item, slide-up + opacity, 250ms duration |
| **Completion flash** | `reader.tsx` | Gold (#c9a84c) runs along progress bar |
| **Knowledge bars** | Reader web margins | Three-color novelty bar animates from 0→actual width |

### Partially Implemented

| Element | Status | Issue |
|---------|--------|-------|
| **Double Rule** | On feed only | Design guide says "at the top of every screen below subtitle." Missing from reader, topics, queue screens. Component exists (`DoubleRule.tsx`) — just needs adding to other screens. |
| **✦ Section markers** | ~70% coverage | Present on feed sections (Up Next, Recommended, Topics) and reader sections (What's New, Further Inquiry, Connected Reading). Missing on some secondary section heads. Inconsistently applied. |
| **Entry row sidebar** | Layout correct | Two-column layout with left border separator present. Missing: large Cormorant numbers (depth/claim count), depth dots visual, "side label/value" styling from spec. |

### Missing

| Element | Design Guide Reference | Impact |
|---------|----------------------|--------|
| **AnimatedHighlightWrap** | G13 — long-press amber border fade | Long-press toggles highlight instantly. The *animated* fade-in of warm amber (#92600e) left border from 0→3px over 200ms is not built. Haptic works. |
| **Depth Navigator** | Summary / Claims / Sections / Full zones | The four-zone depth navigation model with rubric underline on active zone was never built. Reading modes (Full/Guided/New Only) are a different concept — modes control dimming, not navigation depth. |
| **Note Saved animation** | Quill-stroke (✎) appears briefly | No visual feedback animation when notes are saved |
| **Reading Progress zone fill** | Depth zone labels fill as you scroll | Not implemented — would require depth navigator first |
| **Traditional tab bar** | EB Garamond 11px text labels, no icons, rubric dot | Tab bar is hidden entirely (session 9 redesign). Replaced by lens tabs + ✦ drawer. This was an intentional design decision, but differs from the original design guide spec. |

---

## 2. Feature Completeness

### Feed Screen (`app/app/(tabs)/index.tsx`)

| Feature | Status | Notes |
|---------|--------|-------|
| Unified single-screen feed | WORKING | Single FlatList with lens tabs, ListHeaderComponent pattern |
| Lens tabs (Latest/Best/Topics/Quick) | WORKING | `LensTabs.tsx`, EB Garamond 13px, rubric underline active indicator, sticky on scroll |
| Up Next section | WORKING | `UpNextSection.tsx` — in-progress with progress bar, or next queued, or algorithmic pick |
| Recommended section | WORKING | `RecommendedSection.tsx` — hero card, claim preview, novelty badge |
| Topic pills section | WORKING | `TopicPillsSection.tsx` — horizontal scroll, tap to filter + activate Topics lens |
| Double rule separator | WORKING | `DoubleRule.tsx` between sections |
| 2-col grid (web) / list (mobile) | WORKING | Fully separate implementations (session 14) |
| Pull-to-refresh | WORKING | ✦ ornament rotation, calls `refreshContent()` |
| Dynamic reranking on return | WORKING | `useFocusEffect` + `bumpFeedVersion()`, blended score: interest 60% + curiosity 40% |
| Hover actions (web) | WORKING | ✓ (archive) and ✕ (dismiss) on hover |
| Swipe dismiss (mobile) | WORKING | Left swipe → dismiss, logs `swipe_dismiss` |
| Swipe queue (mobile) | WORKING | Right swipe → queue, logs `swipe_queue` |
| Ingest metadata (Latest lens) | WORKING | Relative time ("2h ago") + source label |
| Curiosity scoring integration | WORKING | Peaks at 70% novelty, Gaussian σ=0.15 |
| **Swipe hint tooltip** | **MISSING** | "← dismiss · queue →" hint for first-time users never built |
| **"All topics >" entry point** | **MISSING** | No way to enter Topics lens unfiltered from feed (only via drawer or filtered pill tap) |

### Reader (`app/app/reader.tsx`)

| Feature | Status | Notes |
|---------|--------|-------|
| 3 reading modes (Full/Guided/New Only) | WORKING | `ReadingModeToggle`, dimming + collapsed bars |
| Paragraph dimming for known content | WORKING | `computeParagraphDimming()` → opacity 0.55 for familiar |
| Long-press highlight on paragraphs | WORKING | Amber highlight + haptic. No animated fade-in (see design gaps) |
| Claim cards with classification | WORKING | NEW/EXTENDS/KNOWN via cosine + LLM verdict. Priority sorted. Capped at 3. |
| Entity deep-dive | WORKING | `EntityHighlightText` + `EntityPopup` marginalia card |
| Bookmark (☆) | WORKING | Toggle, signal recording, keyboard `s` |
| Menu (⋯) | WORKING | Article info, source link, report scrape, Ask AI, voice note, research, disregard |
| Queue auto-advance | WORKING | `advanceOrGoBack()` → next queued via `router.replace()`. Toast with escape. |
| Interest card on completion | WORKING | `PostReadInterestCard` — new topics +/−, known topics tap-to-cycle |
| Further inquiry / more questions | WORKING | Tappable question cards, "More questions ✦" generates 3 more via `/generate-questions` |
| AI chat bottom sheet | WORKING | `AskAI` modal with article context, `POST /chat` |
| Cross-article connections | WORKING | `getCrossArticleConnections()` → "✦ CONNECTED READING" section |
| Scroll-aware encounter tracking | WORKING | `markArticleReadUpTo()`, skim vs read engagement, milestone logging |
| Ingest from reader links | WORKING | Tap link → auto-ingest, "processing…" → "queued" badge |
| 3-column web layout | WORKING | Left margin (220px), center (article), right margin (240px) |
| Keyboard shortcuts | WORKING | j/k, gi, s, e, d, m, a, ?, Escape — multi-key sequences |
| Report bad scrape | WORKING | `POST /report-scrape` |
| Disregard action | WORKING | Dismiss + signal + navigate back |
| **Per-paragraph action menu** | **PARTIAL** | Spec showed inline popup with Highlight/Research/Ask AI per paragraph. Current: long-press only toggles highlight. Research/Ask AI are in the global ⋯ menu, not contextual to paragraph. |
| **Related articles grouping** | **PARTIAL** | Spec called for "Same topic" / "Shared concepts" / "From same source" groups. Current implementation is flat. |

### Knowledge System

| Feature | Status | Notes |
|---------|--------|-------|
| FSRS claim decay | WORKING | `getRetrievability()` with stability: skim=9d, read=30d, highlight=60d. Reinforcement 2.5×. Forgotten R<0.3 |
| Claim classification | WORKING | KNOWN ≥0.78, EXTENDS ≥0.68, NEW <0.68. LLM verdict for 0.68-0.78 range |
| Scroll-aware encounters | WORKING | Estimates furthest paragraph, marks only encountered claims |
| Curiosity scoring | WORKING | `getArticleNovelty().curiosity_score`, peaks at 70% novelty |
| Paragraph dimming | WORKING | Per-paragraph opacity + novelty classification |
| Knowledge index loading | WORKING | Graceful fallback if index missing |
| Knowledge ledger persistence | WORKING | AsyncStorage `@petrarca/knowledge_ledger`, persists on every update |
| LLM judge (ambiguous range) | WORKING | Pre-computed verdicts from `build_knowledge_index.py` |

### Other Features

| Feature | Status | Notes |
|---------|--------|-------|
| Voice notes (record + transcribe) | WORKING | `VoiceFeedback.tsx` → expo-av → Soniox transcription |
| Voice notes browser | WORKING | `voice-notes.tsx` — date-grouped, transcript preview, action chips |
| Voice note action extraction | WORKING | Gemini extracts intents (research/tag/remember) |
| PetrarcaDrawer (✦ drawer) | WORKING | Bottom sheet, dark ink bg, quick actions + nav items |
| Floating feedback capture | WORKING | ✦ button, voice/text, auto-context, screenshot, server upload |
| Interest model + topic signals | WORKING | `recordTopicInterestSignalAtLevel()`, 30-day decay, Bayesian smoothing |
| Hybrid topic signals | WORKING | Interested/neutral/less, new vs known topic display |
| Topics screen | WORKING | Grouped by broad topic, delta reports, "Find more" research |
| Queue screen | WORKING | FlatList, swipe-to-remove, tap to open |
| Activity Log | WORKING | Vertical timeline, filter toggles, colored dots, paged fetch |

---

## 3. Code Robustness Issues

### Critical

#### 3.1 No Error Boundary in Reader
- **File**: `app/app/reader.tsx` (3,664 lines)
- **Issue**: If article markdown parsing fails or article data is malformed, the entire reader screen crashes with no recovery
- **Fix**: Wrap content rendering in an error boundary component

#### 3.2 Reader Web Scroll Race Condition
- **File**: `app/app/reader.tsx:1666-1691`
- **Issue**: Manually manipulates `document.body.style.overflow` to fix React Native Web's `overflow: hidden` default. Uses 300ms setTimeout for `window.scrollTo()` — if it doesn't execute, arrow keys don't work until manual focus
- **Risk**: Race condition between RNW's body style override and manual restoration

### High Priority

#### 3.3 FlatList Memory
- **File**: `app/app/(tabs)/index.tsx:757`
- **Issue**: `removeClippedSubviews={false}` disables view recycling. No `maxToRenderPerBatch` limiting
- **Risk**: With 186+ articles (growing), memory consumption could spike on Android
- **Fix**: Test with 500+ articles, consider re-enabling `removeClippedSubviews` or setting `maxToRenderPerBatch`

#### 3.4 Unwaited Async Queue Operations
- **File**: `app/app/(tabs)/index.tsx:117` (swipe handler), `app/data/queue.ts:35-39`
- **Issue**: `addToQueue()` returns `Promise<void>` but is not awaited in swipe handlers
- **Risk**: If AsyncStorage write fails, article not added to queue but UI shows success (swipe animation completes)
- **Fix**: Await the promise or add error callback

#### 3.5 Knowledge Engine Init Race
- **File**: `app/data/store.ts:116-131`
- **Issue**: `refreshContent()` called without `await` during init (fire-and-forget)
- **Risk**: If knowledge index updates mid-read, paragraph dimming could briefly show stale data. No error handling if refresh fails.

#### 3.6 Mobile Sticky Tab Overlap
- **File**: `app/app/(tabs)/index.tsx:771-775, 793-802`
- **Issue**: Absolute-positioned sticky tabs could overlap content during scroll transitions when `showStickyTabs` toggles at 300px scroll threshold
- **Impact**: ~16ms visual glitch on slower devices during fast scrolling

### Medium Priority

#### 3.7 Console Warnings in Production
- **Files**: `persistence.ts:14,23,46,56,75`, `VoiceFeedback.tsx:29,41,65`, `voice-notes.tsx:75`
- **Issue**: 5+ `console.warn` calls visible to users on real devices
- **Fix**: Replace with `logEvent()` for telemetry

#### 3.8 Unsafe Type Assertions (30+ instances)
- **Files**: `index.tsx:161,181,552-557`, `landscape.tsx:180,196,296`, `trails.tsx:180,234,353,358,361,378,382`, `reader.tsx:1127,1167,1170,1172,1213,1215,1226,1235`
- **Pattern**: `as any` bypasses TypeScript for CSS-in-JS and platform-specific styles
- **Risk**: Low runtime impact but reduces safety during refactors

#### 3.9 Voice Recording Silent Failure
- **File**: `app/components/VoiceFeedback.tsx:101-119`
- **Issue**: Recording errors logged as console warnings but don't set error state consistently
- **Risk**: User may think recording worked when it failed mid-session

#### 3.10 Interest Model Async Save
- **File**: `app/data/interest-model.ts:98-130`
- **Issue**: `recordSignal()` is sync but `saveInterestProfile()` is async and not awaited
- **Risk**: Profile could be lost on crash

#### 3.11 Landscape useMemo Stale Data
- **File**: `app/app/landscape.tsx:12-15`
- **Issue**: `useMemo(() => getTopicBubbles(), [])` — empty deps means data never refreshes after feed changes
- **Fix**: Add `getFeedVersion()` to dependency array

#### 3.12 FeedbackCapture Screenshot Not Nullable on Error
- **File**: `app/components/FeedbackCapture.tsx:63-66`
- **Issue**: If `captureScreen()` fails, `screenshotUri` stays null but no error shown to user
- **Risk**: User thinks feedback includes screenshot when it doesn't

#### 3.13 Reader Scroll Position Save
- **File**: `app/app/reader.tsx:34`
- **Issue**: Scroll position saved every 2s (`SCROLL_POSITION_SAVE_INTERVAL_MS`). If app closes within 2s of last save, position lost
- **Impact**: Minor — user may lose a few paragraphs of scroll position

### Lower Priority

#### 3.14 Voice Notes Empty State
- **File**: `app/app/voice-notes.tsx:52-57`
- **Issue**: If `fetchAllNotes()` fails, screen shows empty list with no error or retry

#### 3.15 PetrarcaDrawer Recompute on Every Open
- **File**: `app/components/PetrarcaDrawer.tsx:17-24`
- **Issue**: `readCount` and `queueCount` computed via `useMemo` with `[visible]` dep
- **Impact**: 50-100ms stall opening drawer on large datasets

#### 3.16 Log Event Throughput
- **File**: `app/data/logger.ts:181-204`
- **Issue**: `logEvent()` called 30+ times per page load; batch flush every 5s
- **Concern**: On slow networks, could create backpressure

#### 3.17 Hardcoded Values
- `reader.tsx:1168` — sticky top: 42px (should use design token)
- `reader.tsx:200` — hardcoded color `#6a6458` (should reference `colors.textSecondary`)
- `knowledge-engine.ts:15-22` — threshold constants not centralized with other tokens

---

## 4. Summary: What's Actually Missing

### Design Elements Never Built
1. AnimatedHighlightWrap (amber border fade animation)
2. Depth Navigator (Summary/Claims/Sections/Full zones)
3. Double Rule on non-feed screens
4. Entry row depth count numbers (large Cormorant)
5. Note Saved animation (✎)
6. Reading Progress zone fill

### UX Affordances Never Built
1. Swipe hint tooltip ("← dismiss · queue →")
2. Per-paragraph action menu (Highlight/Research/Ask AI inline)
3. "All topics >" entry point from feed
4. Related articles grouped by relationship type

### Robustness Gaps
1. No error boundary in reader
2. Unwaited async operations (queue, signals)
3. FlatList memory with growing article count
4. Silent failures (voice recording, screenshots, voice notes fetch)
5. Stale data in landscape screen
6. Console warnings in production

---

## 5. Recommended Fix Order

### Quick Wins (1-2 hours total)
1. Add error boundary wrapper around reader content
2. Await `addToQueue()` in swipe handlers
3. Add `DoubleRule` to reader, topics, queue screens
4. Replace `console.warn` with `logEvent()` calls
5. Fix landscape `useMemo` deps

### Half-Day Work
6. Build swipe hint tooltip (show once per install)
7. Add error/retry states to voice notes and feedback capture
8. Profile FlatList with 300+ articles, tune `maxToRenderPerBatch`
9. Add entry row claim/depth count (Cormorant numbers in sidebar)

### Larger Efforts
10. AnimatedHighlightWrap — amber border fade + haptic (design spec G13)
11. Per-paragraph action menu — inline popup on long-press
12. Depth Navigator UI — Summary/Claims/Sections/Full with rubric underline
13. TypeScript strict mode + remove `as any` assertions
