# Petrarca UX Redesign Specification

**Date**: March 7, 2026
**Status**: Design exploration complete, ready for implementation planning
**Design rounds**: 2 rounds of mockup feedback via design-explorer

## Summary

After two rounds of mockup exploration (10 initial mockups → 7 refined mockups), we've converged on a set of interaction models for the app. All 7 final mockups received thumbs up. This spec captures the approved direction for each screen/feature.

---

## Design System

**Non-negotiable**: The "Annotated Folio" design system in `design/DESIGN_GUIDE.md` is fully approved and loved. All implementation must follow it exactly. Key elements:
- Double rule (2px + 1px, 5px gap) at top of every screen
- ✦ section markers in rubric (#8b2500)
- Four-font typography (Cormorant Garamond / EB Garamond / Crimson Pro / DM Sans)
- Parchment backgrounds, ink text, rubric accents
- Text-only tab bar with rubric dot active indicator
- Claim cards with left borders, topic tags in EB Garamond italic

---

## App Structure

### Tab Bar (Bottom)
Four tabs, text-only, EB Garamond 12px:
1. **Feed** — Main reading list with swipe gestures
2. **Topics** — Topic cluster browser
3. **Queue** — Reading queue / playlist
4. **Log** — Activity timeline (user + system actions)

### Navigation Flow
```
Feed ──tap──→ Reader ──done──→ Post-Read Interest Card ──close──→ Feed (or next in queue)
       │                 │
       │              ──→──→ Next queued article (via "Up next" footer)
       │
       swipe right ──→ Add to Queue
       swipe left  ──→ Dismiss (archive)
```

---

## Screen 1: Feed (Mobile)

**Based on**: Mockup 1 (Feed with Swipe + Topic Drill-Down)

### Layout
- Header: "Petrarca" (Cormorant 24px) + article count (italic)
- Double rule
- ✦ "Continue reading" section (articles with reading progress)
- ✦ "New texts" section
- Topic filter chips below "New texts" header
- Tab bar

### Continue Reading Section
- Compact cards: title (EB Garamond 15px) + meta (source, time, % read)
- Progress bar (rubric fill on rule-color track)
- Sorted by recency of last read

### New Texts Section
- **Topic chips**: horizontally scrollable, EB Garamond italic 12px, counts shown
  - "All (8)", "medieval-sicily (2)", "AI & tools (3)", etc.
  - Active chip = ink background, parchment text
  - Tapping filters the list below
- **Articles**: each shows:
  - Title (EB Garamond 16px)
  - Summary (Crimson Pro 13px, 2-3 lines)
  - One ✦ novelty claim preview (12px, green left border) — the most novel claim
  - Bottom row: source · author · read time | topic tag(s)
- **No visible scores** — ranking speaks through ordering
- Sorted by interest model (interest_match 40%, freshness 25%, discovery 20%, variety 15%)

### Swipe Gestures
- **Swipe right** → "Queue" reveal (rubric tinted background) — adds to reading queue
- **Swipe left** → "Dismiss" reveal (grey background) — archives article
- Subtle hint text: "← dismiss · queue →" shown once per session
- Dismissed articles accessible from a secondary view (not front and center)

### Open Questions
- Where do dismissed/archived articles live? Probably a filter in Topics or a hidden section
- Swipe should not be the ONLY way to queue/dismiss — need tap alternatives too

---

## Screen 2: Reader (Mobile)

**Based on**: Mockups 4, 11, 12 (three complementary reader approaches)

### Top Bar
- "← Feed" back button (DM Sans, rubric)
- Queue indicator: "**3** in queue" (pill badge)
- "Source ↗" link to original

### Progress
- 2px progress bar below top bar (rubric fill)

### Content Layout
- Title (Cormorant 24px)
- Meta: author · source · date · read time (DM Sans 11px, muted)
- ✦ "What's new for you" card (parchment bg, rubric left border)
  - Bullet list of novelty claims
- Article body (Crimson Pro 16px, 27px line height)
- Long-press → paragraph highlight (amber background, haptic feedback)

### Claim Interaction (see separate deep-dive doc)
This is the most complex and least resolved part of the reader. See `research/claims-topics-feedback-spec.md` for the full exploration context. The core tension:
- Claims can appear as margin annotations (mockup 4), interleaved callouts (mockup 12), or just in the "What's new" card
- Each approach has different trade-offs for density, flow interruption, and signal capture
- The feedback mechanism (N/K/★, "I knew this"/"Save"/"Tell me more") needs exploration

### In-Article Links
- Tapping a link in article text should trigger auto-ingest:
  1. Immediately start downloading + processing the linked article
  2. Show "processing…" badge next to the link (DM Sans 8px, grey)
  3. When done, update to "queued" badge (green)
  4. Article appears at top of reading queue
  5. Reading continues uninterrupted — no navigation away

### Related Articles (at bottom of article)
- Section with rubric double rule separator
- ✦ "Related reading" header
- Three groups:
  - **Same topic** — articles sharing interest_topics
  - **Shared concepts** — articles with overlapping claims/entities
  - **From same source** — same hostname
- Each shows: title, meta, and action button:
  - "+ Queue" (tap to add)
  - "✓ Read" (already in library)
  - Long-press → open directly

### Footer
- Left: "Done" button (ink bg, parchment text, pill shape)
- Right: "Up next" preview (DM Sans label + EB Garamond title + → arrow)
  - Tapping flows directly to next queued article without returning to feed
  - If nothing queued, shows "← Back to feed"

---

## Screen 3: Topic Browser (Mobile)

**Based on**: Mockup 15 (Topic Browser)

### Layout
- Header with Feed/Topics toggle (EB Garamond, ink buttons)
- Double rule
- Expandable topic clusters

### Topic Clusters
- Ranked by interest model score (no visible numbers)
- Each cluster:
  - Header: topic name (EB Garamond italic 16px, rubric) + article count + expand/collapse arrow
  - Progress bar showing engagement with cluster (rubric fill)
  - When expanded: article cards inside
- Article cards within cluster:
  - Title with reading state dot (rubric = reading, green = done)
  - Meta: source · read time · % read
  - ✦ novelty claim preview where available
- Collapsed clusters show just header + count
- Tap header to expand/collapse
- Tap article to open in reader

### Purpose
"I want to go deep on medieval Sicily today" — lets you focus on a topic cluster and read through related articles sequentially.

---

## Screen 4: Queue (Mobile)

Not fully mocked up yet, but implied by the interaction model:
- Shows ordered list of queued articles
- Reorderable (drag handles?)
- Each item: title, source, read time, novelty claim
- Tap to open in reader (which then flows through queue via "Up next")
- Swipe to remove from queue
- Could also show "processing…" articles that were auto-ingested from links

---

## Screen 5: Activity Log (Mobile)

**Based on**: Mockup 13 (Activity Log)

### Layout
- Header: "Petrarca" + "activity log" subtitle
- Double rule
- Filter toggle: All / Reading / System / Research
- Vertical timeline

### Timeline Nodes
Four types, each with distinct visual:

**Reading actions** (colored dots on timeline):
- Green filled dot = finished reading (shows title, time, highlights, interest signal chips)
- Rubric ring = started/in progress (shows title, % read, novelty claim)
- Grey dot = dismissed (muted title, source)

**System events** (small blue dots):
- "Ingested **12** Twitter bookmarks · **3** matched your interests"
- "Processed **5** Readwise articles · extracted **14** novelty claims"
- Compact, informational

**Research agent** (purple dots):
- "Research agent dispatched: 'multicultural governance in Norman Sicily'"
- "Research agent completed: 3 results found" (with tap to review)
- Shows trigger context ("Triggered by reading Arab-Norman Palace Chapel")

**Interest signals** (✦ marker):
- "You signaled interest in `agent-coordination` `distributed-systems` and dismissed ~~benchmarks~~"
- Green chips for positive, grey strikethrough for negative

### Time Labels
- Day separators: "Today", "Yesterday", "Mar 5"
- Optional timestamps on individual nodes

### Purpose
Makes the "invisible work" of the system visible. Shows ingestion, processing, research agents alongside reading activity. Helps build trust in the algorithm by making it transparent.

---

## Screen 6: Web Split Panel

**Based on**: Mockup 14 (Web Split Panel + Keyboard)

### Layout
- Left pane (300px): article list with queue + new texts sections
- Right pane: reader (same as mobile reader)
- Keyboard shortcut bar at bottom of left pane

### Left Pane
- Header: "Petrarca" + article/queue counts
- Double rule
- ✦ "Queue" section (queued articles with progress)
- ✦ "New texts" section
- Each item: title, summary, source, time, topic tags
- Active item: rubric left border, parchment background
- Focused item: rubric outline (keyboard navigation indicator)

### Keyboard Shortcuts
- `j` / `k` — navigate up/down in list
- `Enter` — open selected article in reader pane
- `d` — mark current article as done
- `x` — dismiss article
- `q` — add to queue
- `Space` — scroll reader pane
- `s` — save/star current claim
- Shortcut bar visible at bottom: `j k navigate · ⏎ open · d done · x dismiss · q queue`

### Reader Pane
- Same content as mobile reader
- Prev/Next buttons with keyboard hints in footer
- Queue position indicator: "1 of 3 in queue"

---

## Rejected Interaction Models

These were explored and explicitly rejected:

1. **Inline expansion** (reading articles inside feed list) — "I definitely don't want to inline expand an article in a list of articles"
2. **Bottom sheet reader** — rejected without comment
3. **High-density table** — "Looks ugly and overloaded"
4. **Knowledge-first with novelty rings** — "I don't like the knowledge coverage at all"
5. **Large visible scores/numbers** — "The numbers are distracting", "The large numbers next to the articles are distracting"
6. **Magazine hero layout** — Minutes too prominent, numbers not useful, bars confusing

### Key Anti-Patterns
- Don't show numerical scores (interest, novelty) to the user — let ranking speak through ordering
- Don't duplicate information (e.g., read time in sidebar AND meta line)
- Don't make the UI feel like a dashboard or analytics tool
- Don't add more UI elements than needed — each article needs enough info to decide, but not more

---

## New Concepts Introduced

### Reading Queue / Playlist
- Articles can be added to a queue via swipe right, "+ Queue" buttons, or auto-ingest from links
- Queue provides a sequential reading flow — "Up next" in reader footer
- Queue is a separate tab, but the primary interaction is through the reader flow

### Auto-Ingest from Links
- Tapping a link in an article triggers background download + processing
- Shows processing state inline next to the link
- Processed article goes to top of queue
- No navigation interruption — keep reading current article

### Dismissed/Archived Articles
- Swiped-left articles go to an archive
- Accessible but not prominent — maybe a filter in Topics or a separate view
- Provides safety net for accidental dismissal

### System Transparency via Log
- Show all system actions (ingestion, processing, research agents)
- Make the algorithm's work visible to build trust
- Toggle between user actions and system events

---

## Implementation Priority (Suggested)

1. **Feed with swipe gestures + topic chips** — core interaction, start here
2. **Reader with "What's new" card + highlights** — already partially built
3. **Queue system** — needed for swipe-right and reader flow
4. **Reader "Up next" footer** — connects queue to reading flow
5. **Topic browser** — alternative navigation view
6. **Activity log** — transparency feature
7. **Auto-ingest from links** — requires pipeline integration
8. **Web split panel** — separate web layout
9. **Claim interaction system** — needs more design exploration (see separate doc)

---

## Files Referenced

- `design/DESIGN_GUIDE.md` — Visual design system (490 lines)
- `research/reset-implementation-log.md` — Current architecture
- `app/data/types.ts` — Data types
- `app/data/store.ts` — State management
- `app/data/interest-model.ts` — Interest scoring
- `app/app/(tabs)/index.tsx` — Current feed implementation
- `app/app/reader.tsx` — Current reader implementation
- `mockups/` — All HTML mockups from design exploration
- `app/data/synthetic-articles.json` — 15 test articles with varied states
