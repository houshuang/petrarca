# Petrarca — Intelligent Read-Later App

## Project Overview
A mobile-first read-later app combining incremental reading (SuperMemo-inspired), user knowledge modeling, and algorithmic article selection. The app helps the user pre-read, filter, and deeply engage with articles from RSS feeds, Twitter bookmarks, and other sources — surfacing content with genuinely new and interesting information based on a model of what the user already knows and cares about.

## Project Name
Named after Francesco Petrarca (Petrarch), pioneer of humanist reading practices and one of the first to develop systematic methods for reading, annotating, and synthesizing knowledge from texts.

## Key Design Principles
- **Knowledge-aware filtering**: Model what the user knows and is interested in; score incoming articles for novelty and relevance
- **Incremental reading**: Don't just save articles — progressively extract, summarize, and schedule key insights for review
- **Active signals**: Easy user feedback during reading: "I know this", "interesting, tell me more", "save this segment", "not relevant"
- **Open algorithms**: Selection/ranking algorithms should be transparent and configurable
- **Personal, not social**: Built for one power user (Stian), not a social platform

## Current Implementation Status
**See `research/implementation-status.md` for comprehensive details** — all files, algorithms, deployment status, known issues, and next steps.

### Architecture
- **Frontend**: Expo SDK 54 (React Native), 3-tab layout (Feed / Topics / Queue), deployed at `exp://alifstian.duckdns.org:8082` (native) and `http://alifstian.duckdns.org:8084` (web)
- **Backend**: Hetzner VM — nginx content server (:8083), research server (:8090), 4-hour cron pipeline
- **Pipeline**: Twitter bookmarks + Readwise Reader → Gemini Flash extraction → atomic claims → Nomic embeddings → knowledge index → served via nginx
- **State**: Module-level vars in `store.ts`, persisted to AsyncStorage. No Redux/Context.
- **Interest Model**: Topic-level interest tracking with Bayesian smoothing, 30-day decay, feed ranking
- **Knowledge System**: Server-computed INDEX (claim similarities, paragraph mappings, delta reports) + client-side LEDGER (FSRS decay, claim classification, paragraph dimming)

### Key Files (Knowledge System)
| File | Role |
|------|------|
| `app/data/knowledge-engine.ts` | Core engine — FSRS decay, claim classification, paragraph dimming, curiosity scoring |
| `app/data/queue.ts` | Reading queue with AsyncStorage persistence |
| `app/app/(tabs)/topics.tsx` | Topics screen — articles grouped by topic, delta reports |
| `app/app/(tabs)/queue.tsx` | Queue screen — saved-for-later articles |
| `scripts/build_knowledge_index.py` | Server pipeline — embeddings → similarity matrix → delta reports → knowledge_index.json |
| `scripts/build_claim_embeddings.py` | Generate Nomic-embed-text-v1.5 embeddings for claims |
| `scripts/deploy_knowledge_index.sh` | Deploy knowledge_index.json to nginx + update manifest |

### Algorithm Parameters (experiment-validated)
- KNOWN threshold: ≥ 0.78 cosine, EXTENDS: ≥ 0.68, FORGOTTEN: R < 0.3
- FSRS stability: skim=9d, read=30d, highlight=60d, reinforcement=2.5×
- Curiosity peak: 70% novelty, Gaussian σ=0.15
- Reader: 3 modes (Full / Guided / New Only), familiar paragraph opacity=0.55

## Design System — "The Annotated Folio"

**CRITICAL: Read `design/DESIGN_GUIDE.md` before making ANY UI changes.** The app has a carefully designed Renaissance-inspired visual language. Every new screen, component, or modification must follow this system.

### Philosophy
The screen is a page from a humanist's working manuscript. Typography over decoration. Red rubrics guide the eye. Margins carry metadata. Structural ornament only — no gratuitous boxes or shadows.

### Color Palette
| Token | Hex | Usage |
|-------|-----|-------|
| `parchment` | `#f7f4ec` | Primary background |
| `parchmentDark` | `#f0ece2` | Tab bar, secondary surfaces |
| `ink` | `#2a2420` | Primary text, headings |
| `rubric` | `#8b2500` | THE accent color — navigation, emphasis, section heads |
| `textPrimary` | `#1a1a18` | Titles |
| `textBody` | `#333333` | Body text |
| `textSecondary` | `#6a6458` | Summaries |
| `textMuted` | `#b0a898` | Metadata |
| `rule` | `#e4dfd4` | Hairline dividers |
| `claimNew` | `#2a7a4a` | "New to me" / success |
| `claimKnown` | `#d0ccc0` | "Knew this" (+ opacity 0.55) |

### Typography — Four-Font System
| Role | Font | Usage |
|------|------|-------|
| **Display** | Cormorant Garamond | Screen titles, large numbers, reader titles (600 weight) |
| **Body/Titles** | EB Garamond | Entry titles, section heads (uppercase + letterspaced), claim text |
| **Reading** | Crimson Pro | Reader body, summaries, long-form text |
| **UI/Meta** | DM Sans | Metadata, labels, small caps, buttons |

### Signature Visual Elements
These elements define Petrarca's identity. Never omit them:

1. **Double rule** — 2px + 1px rules with 5px gap, at the top of every screen below subtitle. The signature element.
2. **✦ Section markers** — Four-pointed star before section headings, always rubric colored
3. **Entry row sidebar** — Two-column grid: content (1fr) | sidebar (76px) with large Cormorant numbers + DM Sans labels + depth dots
4. **Text-only tab bar** — EB Garamond 11px labels on parchmentDark, active = ink + 4px rubric dot indicator. NO icons.
5. **Depth navigator** — Horizontal row: Summary / Claims / Sections / Full, active has rubric underline (2px)
6. **Claim cards** — Left-bordered text blocks (2px), no background. Border colors: default=#e4dfd4, new=#2a7a4a, known=#d0ccc0
7. **Novelty badges** — "Mostly new" / "72% new" / "Partly familiar" with semantic colors
8. **Rubric dot** — 4px circle as active tab indicator and list bullets
9. **Topic tags** — EB Garamond italic 11.5px in rubric color

### Micro-Delights
- **Pull-to-refresh**: ✦ ornament rotates (no spinner)
- **Claim reveal**: Staggered 80ms slide-up animation
- **Long-press highlight**: Warm amber left border fades in + haptic
- **Completion flash**: Brief gold (#c9a84c) runs along double rule
- **Knowledge bars**: Animate from 0% to actual width, staggered 60ms

### Layout Rules
- Reading measure: `max-width: 680px` for reader content
- Screen padding: 16px horizontal
- Touch targets: minimum 44×44pt
- Entry rows: title + 1-line summary + topics + meta (no multi-line summaries in feed)
- Hover on web: subtle `background: rgba(139,37,0,0.03)`

### Design Files
- `design/DESIGN_GUIDE.md` — Complete 490-line design specification
- `design/tokens/` — TypeScript design tokens (colors, typography, spacing)
- `design/assets/` — Logo SVGs (mark, wordmark, combined, favicon)
- `app/mockups/` — Previous design round mockups (feed variants, reader variants)
- `app/preview-mockups/` — Landing page / marketing mockups

## Research & Documentation Organization
All research lives in `research/` directory:
- `research/README.md` — Master index of all research documents (ALWAYS update when adding new docs)
- `research/implementation-status.md` — **CURRENT STATE** — comprehensive implementation status, deployment, known issues, next steps
- `research/novelty-system-architecture.md` — Master architecture for knowledge-aware system
- `research/system-state-of-the-art.md` — Comprehensive reference covering all research, algorithms, data structures, experiments, UI mockups
- `research/experiment-results-report.md` — Results from 11 validation experiments
- `research/experiment-log.md` — Append-only log of all experiments and prototypes
- `research/ux-redesign-spec.md` — 2 rounds of mockup feedback, approved interaction models

## Critical Rules

### 1. Research Organization
- ALL research goes in `research/` directory, linked from `research/README.md`
- Read `research/README.md` FIRST when starting new research to avoid duplication
- Update the index whenever adding new research documents

### 2. Experiment Logging
- `research/experiment-log.md` is **append-only** — new entries at top
- Log BEFORE making changes, not after
- Include: date, what was tried, results, conclusions

### 3. Interaction Logging
- ALL user interactions must be logged via `logEvent()` from `app/data/logger.ts`
- When adding new UI elements (buttons, gestures, toggles), always add a `logEvent()` call
- Log files: `{documentDirectory}/logs/interactions_YYYY-MM-DD.jsonl` (daily, append-only)
- Every event includes: timestamp, event name, session_id, plus context-specific fields
- Signals are persisted to AsyncStorage via `app/data/persistence.ts` — never lose user decisions
- Export logs via the Event Log section in Progress tab, or read JSONL files directly

### 4. Pipeline Prompt & Model Iteration
- Use the **pipeline testing framework** (`scripts/pipeline-tests/run.py`) when iterating on prompts, models, or extraction logic
- Key commands:
  - `run.py clean --fixture NAME` / `--all` — test clean_markdown on fixtures
  - `run.py extract --fixture NAME --model MODEL` — test article extraction with specific models
  - `run.py compare <id_a> <id_b>` — compare two session outputs side-by-side
  - `run.py report` — generate summary report across sessions
  - `run.py fixture-create --url URL --name NAME --layer LAYER` — add new test fixtures from live URLs
- Fixtures live in `scripts/pipeline-tests/fixtures/` organized by layer (clean_markdown, article_extraction, entity_concepts, end_to_end)
- Always run relevant fixtures before and after changing prompts or switching models to measure impact
- Use the `/pipeline-eval` skill for guided evaluation workflows

### 5. Design Iteration & Review
- Use the **design-explorer** skill to generate and compare design mockups with structured feedback
- After creating or modifying any UI component/screen, use the **design review** process:
  1. Generate mockup(s) with design-explorer
  2. Review against `design/DESIGN_GUIDE.md` for adherence to the Annotated Folio design system
  3. Check: correct fonts, colors from palette, signature elements (double rule, section markers, etc.)
- Design tokens are in `design/tokens/` — always use these rather than hardcoding values
- Existing mockups for reference: `app/mockups/` (feed/reader variants), `app/preview-mockups/` (landing page)

### 6. Code & Development
- Branch prefix: `sh/` for all GitHub branches
- No test plans or checklists in PR descriptions
- Commit after every significant change

### 5. Reference Projects
- `../alif` — Arabic learning app with FSRS-based knowledge tracking, Expo mobile setup, good model for "modeling knowledge at granular level"
- `interview.md` — Original brainstorm interview (language learning focus evolved into read-later concept)

## User Preferences
- Prefers Claude Code agents (Max plan) over Anthropic API calls — it's free
- Same pattern as ../alif: use `claude -p` wrapper for LLM work where possible
- Wants rapid prototyping and experimentation in small chunks
- Values research depth before building
- Single user, personal tool first
- Has Hetzner VM available (details in ../alif) for background agents
- Broad interests: history, literature, classical philology, educational research, green party policy, AI/technology
- Languages: Norwegian, Swedish, Danish, Italian, German, Spanish, French, Chinese, Indonesian, Esperanto, English — likes reading multilingual content

## Voice Processing
- **Soniox API**: Key is `SONIX_KEY` in `/Users/stian/src/alignment/.env`
- API base: `https://api.soniox.com/v1`
- Existing integration patterns: `../alif/backend/app/services/soniox_service.py` (async model `stt-async-v4`), `../alignment/transcribe_soniox.py` (older `stt-async-v3`)
- Use latest batch model for voice note transcription
- Voice notes are first-class input: record → transcribe → link to reading context → feed into knowledge model

## Research Agent Feature
- User wants a "quick research button" while reading to capture ideas/questions
- Spawns background research agents (on Hetzner VM) that find interesting diverse perspectives
- Results waiting next time user opens app
- Should find high-value articles from diverse sources
- User can tag promising directions → triggers further research
- Keep research breadth wide but don't go too deep initially

## Reference Projects — Usage Notes
- **../otak**: Scripts are useful (Twitter bookmarks, Readwise, LLM providers). The knowledge graph itself is a failed experiment — do NOT rely on it. Use otak as a code/pattern library.
- **../bookifier**: Pipeline/caching patterns, Kindle epub generation
- **../alif**: Mobile setup (Expo), interaction model, physical-digital integration, `claude -p` wrapper pattern
