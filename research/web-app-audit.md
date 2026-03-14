# Web App Audit: Plans vs Reality

**Date**: 2026-03-10
**Scope**: Full comparison of DESIGN_GUIDE.md, CLAUDE.md design specs, and implementation status against actual deployed code

## Summary

The core architecture is solid — the 3-column reader, 2-column feed grid, keyboard navigation, knowledge system, and design token infrastructure all work well. But there's a meaningful gap between the polished, detailed designs documented in `DESIGN_GUIDE.md` and what's actually on screen. Issues fall into three buckets: **design elements designed but never built**, **features that work but lack polish**, and **drawer/navigation items that are stub or broken**.

---

## A. DESIGNED BUT NOT IMPLEMENTED

### 1. Entry Row Sidebar Pattern (major visual gap)
- **Design guide** (`DESIGN_GUIDE.md:131-145`): two-column layout for feed article cards — content (1fr) | sidebar (76px) with read time, depth labels, and a left border
- `layout.sidebarWidth: 76` is defined in spacing tokens but **never used in active code**
- Current `ArticleCard` is a flat single-column layout: title → summary → claim preview → metadata row
- This is a **signature visual element** listed in CLAUDE.md and completely absent

### 2. Depth Navigator (Summary / Claims / Sections / Full)
- **Design guide**: 4-zone horizontal navigator with rubric underline on active zone
- Token `depthUnderlineHeight: 2` is defined
- Type `ReadingDepth` exists in `types.ts:90` with all values
- **Not built** — the reader has a `ReadingModeToggle` (Full/Guided/New Only) which is a different concept
- These are orthogonal: depth navigator = what content to show, reading mode = how to show it

### 3. Claim Cards with Individual Left Borders
- **Design guide** (`DESIGN_GUIDE.md:157-168`): claims should be individual left-bordered text blocks with action buttons ("Knew this" / "New to me")
- Current: claims appear inside a "What's new for you" card as a list with small dots, not as individual bordered cards with classification buttons
- Per-claim interaction model (classify individual claims) isn't implemented in the reader

### 4. AnimatedHighlightWrap (long-press amber fade)
- **Design guide + CLAUDE.md**: "Warm amber left border fades in + haptic"
- Current: long-press creates an instant amber border with haptic feedback
- Missing: the animated fade-in transition
- Listed as "G13 remaining" in implementation-status

### 5. Knowledge Bar Staggered Animation
- **Design**: "Animate from 0% to actual width, staggered 60ms"
- Current: novelty bars render at their final width immediately, no animation
- Affects both feed novelty display and reader left margin bar

### 6. Quill-Stroke Note Save Animation
- **Design guide**: "✎ appears briefly next to the entry, then fades"
- Not implemented anywhere

### 7. Swipe Hint Text
- **Design**: "Subtle hint text: '← dismiss · queue →' shown once per session"
- Not implemented — swipe gestures work but have no onboarding affordance

---

## B. PARTIALLY IMPLEMENTED / NEEDS POLISH

### 8. Drawer Quick Actions Don't Do Anything
- "Triage" and "Voice Note" quick actions in `PetrarcaDrawer.tsx:65-72` call `quickAction()` which just **logs the event and closes the drawer** — no navigation, no action
- Should launch triage mode or open voice recorder respectively

### 9. Delta Reports — Built But Barely Surfaced
- Server generates 300 delta reports, `getDeltaReportForTopic()` works
- Topics screen (`topics.tsx:106-121`) shows them when a cluster is expanded — works correctly
- **Not shown in the reader** — no delta context when reading an article
- Topics screen only accessible via drawer, easy to never discover

### 10. Topics Screen Not Web-Optimized
- `topics.tsx` has no `Platform.OS === 'web'` branching
- No max-width container, no grid layout on desktop
- Renders as narrow mobile list on wide screens

### 11. Queue Screen Not Web-Optimized
- Same issue — `queue.tsx` only has mobile layout
- Accessible only via drawer, no web-specific treatment

### 12. Trails & Landscape — New Screens, Basic Implementation
- `app/trails.tsx` and `app/landscape.tsx` added in latest commit
- Import from `../lib/reading-insights` for threads, topic bubbles, etc.
- Issues:
  - No web-specific layout
  - Use inline double-rule instead of `DoubleRule` component
  - Topic bubbles use absolute positioning that may not work across screen sizes

### 13. Reader Date Format
- Known issue: left margin shows raw ISO timestamp for some articles instead of formatted date
- No `formatRelativeDate()` applied to left margin date display

### 14. Completion Flash Visibility
- Gold `#c9a84c` sweep animation on Done is implemented (`reader.tsx:1884-1886`)
- Progress bar positioning differs: mobile at bottom, web fixed at top
- Animation may not be visually prominent on mobile

---

## C. ARCHITECTURE & TOKEN GAPS

### 15. Design Tokens Defined But Unused

| Token | Defined | Used |
|-------|---------|------|
| `layout.sidebarWidth: 76` | Yes | No (only in archived code) |
| `layout.depthUnderlineHeight: 2` | Yes | No |
| `layout.ratingBorderWidth: 1.5` | Yes | Only in archived review screen |
| `layout.tabBarHeight: 80` | Yes | Partially (tab bar hidden) |

### 16. Rating/Review System
- Design guide has full "Review Card" spec (lines 170-189) with Again/Hard/Good/Easy buttons
- `ratingBorderWidth` token defined, rating color palette defined
- **Entire review/SRS flow not implemented** — was in `_archive/app/review.tsx`
- FSRS stability values used for passive decay, but no active review UI exists

---

## D. WHAT'S WORKING WELL

- **3-column reader layout** — grid, margins, sticky sections, italic labels, polished
- **2-column feed grid** — hover actions, keyboard nav, web scroll
- **4-font system** — consistently used with proper web fallbacks
- **Color palette** — no hardcoded colors in active components
- **Keyboard shortcuts** — multi-key sequences, j/k, gi, arrow keys
- **Knowledge system** — FSRS decay, paragraph dimming, claim classification, curiosity scoring
- **Interaction logging** — comprehensive coverage across all screens
- **Reader features** — 3 reading modes, entity deep-dive, AI chat, voice notes, cross-article connections, further inquiry, auto-advance
- **Swipe gestures** — queue left, dismiss right, with animated actions
- **Pull-to-refresh** — rotating ✦ ornament
- **Claim reveal animation** — staggered 80ms slide-up
- **Entity highlighting** — dotted underline + popup with research/ingest actions
- **Queue auto-advance** — next article + toast with escape hatch
- **Feedback capture** — floating ✦ button with screenshot + voice + text + context

---

## Recommended Priority Order

| Priority | Item | Impact | Effort |
|----------|------|--------|--------|
| 1 | Entry row sidebar pattern | High — transforms every feed card | Medium |
| 2 | Drawer quick actions | Medium — currently broken no-ops | Low |
| 3 | Web layouts for topics/queue/trails/landscape | Medium — unusable on desktop | Low-Medium |
| 4 | Depth navigator | Medium — designed feature, adds real value | Medium |
| 5 | Knowledge bar animations + highlight fade | Low-Medium — polish | Low |
| 6 | Delta reports in reader | Low-Medium — data exists, needs UI | Low |
| 7 | Reader date format fix | Low — cosmetic | Low |
| 8 | Claim cards with per-claim interaction | High — core knowledge loop | High |
| 9 | Swipe hint text | Low — onboarding | Low |
| 10 | Review/SRS UI | High — designed but unbuilt | High |
