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

## Architecture (TBD — in research/planning phase)
- **Frontend**: Likely Expo (React Native) — see ../alif for reference mobile setup
- **Backend**: TBD
- **Knowledge Model**: Track user's knowledge state per topic/concept (inspired by ../alif's word-level FSRS tracking, but at concept/topic level)

## Research & Documentation Organization
All research lives in `research/` directory:
- `research/README.md` — Master index of all research documents (ALWAYS update when adding new docs)
- `research/interview-analysis.md` — Analysis of initial interview.md brainstorm
- `research/incremental-reading.md` — Deep dive on incremental reading
- `research/prior-art.md` — Existing tools, libraries, open source projects
- `research/knowledge-modeling.md` — How to model user knowledge/interests
- `research/article-selection.md` — Algorithms for filtering/ranking articles
- `research/experiment-log.md` — Append-only log of all experiments and prototypes

## Critical Rules

### 1. Research Organization
- ALL research goes in `research/` directory, linked from `research/README.md`
- Read `research/README.md` FIRST when starting new research to avoid duplication
- Update the index whenever adding new research documents

### 2. Experiment Logging
- `research/experiment-log.md` is **append-only** — new entries at top
- Log BEFORE making changes, not after
- Include: date, what was tried, results, conclusions

### 3. Code & Development
- Branch prefix: `sh/` for all GitHub branches
- No test plans or checklists in PR descriptions
- Commit after every significant change

### 4. Reference Projects
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
