# Petrarca Design Guide — "Annotated Folio"

A Renaissance-inspired design system for a scholarly reading app. Modeled after the annotated folios of humanist scholars — clean typography, red rubrics, marginal annotations, and maximum information density on warm parchment.

---

## Philosophy

**The Annotated Folio** treats the screen as a page from a humanist's working manuscript. Every element earns its place through utility. Decoration is structural, never ornamental. Red rubrics guide the eye. Margins carry metadata. Typography does the heavy lifting.

Core principles:
- **Typography over decoration** — Serif fonts carry authority; hierarchy is expressed through weight, size, and color, not boxes and shadows
- **Information density** — Pack information tightly but legibly, like a well-typeset folio page
- **Red rubric as wayfinding** — A single accent color (#8b2500) guides navigation, marks importance, and creates visual rhythm
- **Warm parchment ground** — The background suggests aged paper without being kitschy
- **Structural ornament only** — Double rules, section markers (✦), and hairlines serve as page architecture

---

## Color Palette

### Primary Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `parchment` | `#f7f4ec` | Primary background |
| `parchment-dark` | `#f0ece2` | Tab bar, secondary surfaces |
| `ink` | `#2a2420` | Primary text, headings, strong elements |
| `ink-light` | `#1a1a18` | Slightly lighter primary text |
| `rubric` | `#8b2500` | Accent color — navigation, emphasis, section heads |

### Text Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `text-primary` | `#1a1a18` | Titles, headings |
| `text-body` | `#333333` | Body text, claims |
| `text-secondary` | `#6a6458` | Summaries, descriptions |
| `text-muted` | `#b0a898` | Metadata, timestamps, placeholders |
| `text-faint` | `#ccc` | Disabled states, inactive tabs |

### Structural Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `rule` | `#e4dfd4` | Hairline dividers between entries |
| `rule-dark` | `#2a2420` | Double-rule top border, tab bar border |
| `border-claim` | `#e4dfd4` | Default claim left border |
| `border-claim-new` | `#2a7a4a` | "New to me" claim state |
| `border-claim-known` | `#d0ccc0` | "Knew this" claim state (+ reduced opacity) |
| `border-rubric` | `#8b2500` | User notes, saved items, rubric borders |

### Rating Colors

| State | Border | Text | Background |
|-------|--------|------|------------|
| Again | `#e0c0b8` | `#8b2500` | transparent |
| Hard | `#e0d8c0` | `#7a5a20` | transparent |
| Good | `#c0dcc8` | `#2a6a3a` | transparent |
| Easy | `#c0d0e0` | `#2a4a6a` | transparent |

### Semantic Colors (sparingly used)

| Token | Hex | Usage |
|-------|-----|-------|
| `success` | `#2a7a4a` | New knowledge, completion |
| `warning` | `#92600e` | Highlights, amber states |
| `info` | `#2a4a6a` | Links, external references |
| `danger` | `#8b2500` | Same as rubric — delete, dismiss |

---

## Typography

### Font Stack

| Role | Font | Fallback |
|------|------|----------|
| **Display** | Cormorant Garamond | Georgia, serif |
| **Body/Titles** | EB Garamond | Georgia, serif |
| **Reading text** | Crimson Pro | Georgia, serif |
| **UI/Meta** | DM Sans | -apple-system, sans-serif |

### Type Scale

| Element | Font | Size | Weight | Color | Extra |
|---------|------|------|--------|-------|-------|
| Screen title | Cormorant Garamond | 24px | 600 | `ink` | — |
| Screen subtitle | Cormorant Garamond | 13px | 400 | `text-muted` | italic |
| Section heading | EB Garamond | 11px | 500 | `rubric` | uppercase, 0.15em spacing |
| Entry title | EB Garamond | 16px | 500 | `text-primary` | line-height: 1.3 |
| Entry summary | Crimson Pro | 13.5px | 400 | `text-secondary` | line-height: 1.5 |
| Claim text | Crimson Pro | 14px | 400 | `text-body` | line-height: 1.45 |
| Review concept | EB Garamond | 18px | 500 | `text-primary` | line-height: 1.4 |
| Reader title | Cormorant Garamond | 24px | 600 | `ink` | line-height: 1.2 |
| Reader body | Crimson Pro | 16px | 400 | `text-body` | line-height: 1.7 |
| Metadata | DM Sans | 11px | 400 | `text-muted` | — |
| Topic tag | EB Garamond | 11.5px | 400 | `rubric` | italic |
| Tab label | EB Garamond | 11px | 400 | varies | — |
| Stat number | Cormorant Garamond | 24px | 600 | `ink` | — |
| Stat label | DM Sans | 9px | 500 | `text-muted` | uppercase, 0.08em spacing |
| Rating label | EB Garamond | 13px | 400 | varies by state | — |
| Rating hint | DM Sans | 9px | 400 | `text-muted` | — |
| Side label | DM Sans | 9px | 500 | `text-muted` | uppercase, 0.06em spacing |
| Side value | EB Garamond | 14px | 500 | `ink` | — |
| Side note | EB Garamond | 11px | 400 | `rubric` | italic |

### React Native Font Mapping

```
Cormorant Garamond → "Cormorant Garamond" (load via expo-font) or Georgia fallback
EB Garamond → "EB Garamond" (load via expo-font) or Georgia fallback
Crimson Pro → "Crimson Pro" (load via expo-font) or Georgia fallback
DM Sans → "DM Sans" (load via expo-font) or system default
```

---

## Layout Patterns

### The Double Rule

Used at the top of every screen below the subtitle. Signals the start of content.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━  (2px, ink color)
─────────────────────────────  (1px, ink color)
     5px gap between rules
```

### Entry Row (Feed, Library)

Two-column grid: content (1fr) | sidebar (76px)

```
┌─────────────────────────┬──────────┐
│ Entry Title              │ TIME     │
│ Summary text that wraps  │ 4 min    │
│ across lines naturally   │          │
│ topic tag  topic tag     │ DEPTH    │
│ Source · 4 min           │ Claims   │
├─────────────────────────┴──────────┤  ← 1px hairline
```

The sidebar is separated by a 1px left border (`rule` color). It contains small-caps labels and values. Optionally, a rubric-colored italic annotation ("side note").

### Section Header

Red rubric text, uppercase, letterspaced, with optional ✦ prefix:

```
✦ CONTINUE READING
✦ NEW TEXTS
✦ KNOWLEDGE BY TOPIC
```

### Claim Card (Reader)

Left-bordered text block. No background color, no card surface.

```
 ┃ Claim text runs here across the full width
 ┃ of the content area with comfortable reading
 ┃ measure.
 ┃   Knew this    New to me
```

Border colors: default `#e4dfd4`, new-to-me `#2a7a4a`, knew-this `#d0ccc0` (+ opacity 0.55)

### Review Card

Full-width, no card background. Generous vertical spacing.

```
 topic tag (italic, rubric)

 Concept text in EB Garamond 18px

 Review #3 · 4 days since last review

 ┃ "User's note text in italic Crimson Pro"
 ┃ (rubric left border)

 Prompt text in italic

 ┌──────┐┌──────┐┌──────┐┌──────┐
 │Again ││ Hard ││ Good ││ Easy │
 │ <1d  ││  2d  ││  8d  ││ 21d  │
 └──────┘└──────┘└──────┘└──────┘
```

### Rating Buttons

Grid of 4 equal columns. Bordered rectangles (1.5px), 3px border-radius. Each has a serif label and a small sans-serif interval hint below. Colors match the rating semantic.

### Progress Bars

Thin (3px), no border-radius. Track color: `rule`. Fill color: `ink` (default) or `rubric` (highlighted topics).

```
Medieval History                    21
███████████████████████████░░░░░░░░░░
```

### Tab Bar

- Background: `parchment-dark`
- Top border: 1.5px `rule-dark`
- Labels: EB Garamond 11px
- Active: `ink` color
- Inactive: `text-muted`
- Active indicator: 4px circle in `rubric`
- No icons — text labels only (Feed, Library, Review, Progress)

### Depth Navigator (Reader)

Horizontal row of 4 zones. Active zone has rubric-colored underline (2px) and rubric text. Others are muted.

```
  Summary    Claims    Sections    Full
             ━━━━━━
```

---

## Logo

### Mark: The Petrarca Monogram

A ligature of **P** and the Renaissance long-s (**ſ**), set in a style inspired by printer's marks of the Aldine Press. The P's bowl intersects with the descending stroke of the ſ.

Rendered in the rubric color (#8b2500) on parchment, or reversed (parchment on ink) for dark contexts.

### Wordmark

"PETRARCA" set in Cormorant Garamond, weight 600, letterspacing 0.12em, uppercase. Used alongside or below the mark.

### Favicon / App Icon

The monogram P set within a circle or rounded square. Rubric on parchment. For small sizes (16px), simplify to just the P glyph.

### Icon Specifications

```
App icon: 1024×1024, rounded corners (Apple standard)
  - Background: #f7f4ec (parchment)
  - Monogram: #8b2500 (rubric)
  - Subtle double-rule ornament below mark

Favicon: 32×32 and 16×16
  - Simplified P glyph
  - Rubric on parchment

Chrome extension icon: 128×128, 48×48, 16×16
  - Same as favicon variants
```

---

## Graphical Elements & Delights

### Structural Ornaments

1. **Section markers** — ✦ (four-pointed star) before section headings. Always rubric colored.
2. **Double rules** — The signature element. 2px + 1px rules with 5px gap. Used once per screen at the top.
3. **Ornamental break** — ⁂ (asterism) centered between major sections. Color: `text-faint`. Used sparingly.
4. **Rubric dot** — 4px circle, rubric color. Used as active tab indicator and list bullets.

### Transitions & Animations

1. **Page turn** — When navigating between tabs, content slides horizontally with a subtle 200ms ease-out. No bounce.
2. **Claim reveal** — Claims animate in with a staggered 80ms delay per item, sliding up 8px with opacity 0→1. Duration 250ms.
3. **Rating selection** — Selected button fills with its semantic color background (very subtle, 10% opacity) with a 150ms transition. Border thickens to 2px.
4. **Depth zone transition** — The active underline slides smoothly between zones (300ms ease-in-out).
5. **Long-press highlight** — On paragraphs, a warm amber left border (#92600e) fades in from 0→3px width over 200ms. Subtle haptic on native.
6. **Pull-to-refresh** — A small ✦ rotates at the top during refresh. No spinner — the ornament IS the spinner.

### Micro-delights

1. **Reading progress** — As you scroll the reader, the depth indicator zone labels subtly fill from left to right, showing reading progress within each zone.
2. **Completion state** — When all claims are reviewed, a brief flash of gold (#c9a84c, 200ms) runs along the double rule, then fades. Celebration without fanfare.
3. **Note saved** — When a note is saved, a small quill-stroke animation (✎) appears briefly next to the entry, then fades.
4. **Knowledge growth** — In Progress, when topic bars are first rendered, they animate from 0% to their actual width over 400ms, staggered by 60ms. The rubric-highlighted bars animate last for emphasis.

---

## UX Guidelines

### Navigation & Information Architecture

```
Tab Bar (persistent, text-only labels):
├── Feed (primary landing)
│   ├── List view (default)
│   ├── Topics view (grouped by topic)
│   └── Triage view (card stack)
├── Library
│   ├── Recent
│   ├── By Topic
│   ├── Shelf (books)
│   └── Highlights
├── Review (spaced attention)
└── Progress (dashboard)
    └── Reader (full screen, tab bar hidden)
```

### Depth Model

The reader has four progressive depth zones. Users can enter at any depth and move freely between them. The depth indicator always shows current position.

```
Summary → Claims → Sections → Full Article
   ↑         ↑         ↑          ↑
  30 sec    2 min     5 min      10+ min
```

**Key UX rule:** Never force users deeper. Show what's available, let them choose. The depth indicator shows counts ("8 claims", "6 sections") to signal what awaits.

### Interaction Patterns

1. **Tap** — Primary action. Open article, navigate, select.
2. **Long-press** — Secondary action. Highlight paragraphs (reader), expand previews (feed).
3. **Swipe** — Only in triage mode. Left=skip, right=save, up=read now.
4. **Pull-down** — Refresh content. Uses the ✦ ornament as spinner.

### Claim Interaction Flow

```
1. Read claim text
2. Tap "Knew this" or "New to me"
   → Border color changes
   → "Knew this" dims the claim (opacity 0.55)
   → "New to me" marks with green border
3. Optional: Tap "Research" to spawn background research
4. Progress counter updates: "4 of 8 claims reviewed"
5. Scroll to next claim
```

### Review Session Flow

```
1. Enter Review tab → see "3 of 7" progress
2. Concept card shows with topic, text, notes, source articles
3. Optional: Add a text note
4. Rate: Again / Hard / Good / Easy
   → Card animates out
   → Next card animates in
5. Completion: "Done for now" with stats
```

### Triage Flow

```
1. Card stack (3 visible, stacked with offset)
2. Swipe or tap buttons
3. Counter: "12 remaining"
4. Completion: "All caught up" with counts
```

### Content Density Rules

- **Feed:** Show title + 1-line summary + topics + meta. No multi-line summaries.
- **Reader summary:** Full summary text, comfortable reading measure.
- **Claims:** Full claim text, tight vertical spacing, staggered borders.
- **Review:** Large concept text, generous spacing for focus.
- **Progress:** Dense numbers grid + bar charts. Maximum data, minimum chrome.

### Touch Targets

- Minimum tap target: 44×44pt (Apple HIG)
- Rating buttons: Full-width grid, generous padding (10px vertical minimum)
- Claim action buttons: 44pt tall tap area even if text is smaller
- Tab bar items: Full equal-width columns

### Responsive Behavior

| Breakpoint | Behavior |
|------------|----------|
| < 390px (small phone) | Single column, no sidebar on entries |
| 390–428px (standard phone) | Full two-column entry layout |
| 429–768px (large phone/small tablet) | Wider margins, larger type scale |
| 769px+ (tablet/web) | Multi-column feed, wider reading measure (max 680px) |

### Accessibility

- All text meets WCAG AA contrast on parchment background
- Rubric red (#8b2500) on parchment (#f7f4ec) = contrast ratio ~5.8:1 ✓
- Primary text (#1a1a18) on parchment = ~14.5:1 ✓
- Rating buttons use both color AND text labels
- Claim states use border color AND text change ("✓")
- Support Dynamic Type / font scaling on native

---

## Platform-Specific Notes

### Mobile (Expo/React Native)

- Load custom fonts via `expo-font`: Cormorant Garamond, EB Garamond, Crimson Pro, DM Sans
- Use `Platform.select` for font family names (Android may need different names)
- Tab bar uses text labels only — no Ionicons
- Status bar: dark content on light background
- Safe area insets: parchment color extends into safe areas
- Haptic feedback on: claim actions, rating selection, long-press highlight

### Web

- Google Fonts CDN for all four font families
- CSS custom properties for all design tokens
- Reading measure: `max-width: 680px; margin: 0 auto` for reader content
- Hover states: entry rows get subtle `background: rgba(139,37,0,0.03)` on hover
- Keyboard navigation: Tab through claims, Enter to select rating
- Print stylesheet: hide tab bar, expand to full width, use black text

### Chrome Extension (Clipper)

- Popup: 360×480px, parchment background
- Shows article title, extracted summary, detected topics
- "Save to Petrarca" button in rubric color
- Minimal UI: title field, topic tags, one-tap save
- Badge: rubric dot on icon when new articles available
- Content script overlay: small floating ✦ button in bottom-right, rubric colored

---

## File Organization

```
design/
├── DESIGN_GUIDE.md          ← This file
├── tokens/
│   ├── colors.ts            ← Color constants
│   ├── typography.ts         ← Font families, sizes, weights
│   ├── spacing.ts            ← Spacing scale
│   └── index.ts              ← Re-exports
├── components/
│   └── (shared component styles)
└── assets/
    ├── logo-mark.svg         ← Monogram
    ├── logo-wordmark.svg     ← Full wordmark
    ├── icon-1024.png         ← App icon
    ├── icon-192.png          ← Web manifest
    ├── favicon.svg           ← Favicon
    └── ornaments/
        ├── double-rule.svg
        └── asterism.svg
```

---

## Design Token Quick Reference

```typescript
// Colors
const colors = {
  parchment: '#f7f4ec',
  parchmentDark: '#f0ece2',
  ink: '#2a2420',
  rubric: '#8b2500',
  textPrimary: '#1a1a18',
  textBody: '#333333',
  textSecondary: '#6a6458',
  textMuted: '#b0a898',
  textFaint: '#cccccc',
  rule: '#e4dfd4',
  ruleDark: '#2a2420',
  claimNew: '#2a7a4a',
  claimKnown: '#d0ccc0',
  success: '#2a7a4a',
  warning: '#92600e',
  info: '#2a4a6a',
  ratingAgain: '#8b2500',
  ratingHard: '#7a5a20',
  ratingGood: '#2a6a3a',
  ratingEasy: '#2a4a6a',
  ratingAgainBorder: '#e0c0b8',
  ratingHardBorder: '#e0d8c0',
  ratingGoodBorder: '#c0dcc8',
  ratingEasyBorder: '#c0d0e0',
}

// Typography
const fonts = {
  display: 'Cormorant Garamond',
  body: 'EB Garamond',
  reading: 'Crimson Pro',
  ui: 'DM Sans',
}
```
