# Petrarca — Intelligent Read-Later App

A mobile-first read-later app combining incremental reading, user knowledge modeling, and algorithmic article selection. Named after Francesco Petrarca, pioneer of systematic reading methods.

> **This is a personal project shared as-is.** It was built for one power user's reading workflow using Claude Code. It is not a polished open-source product — there are hardcoded server addresses, personal deployment scripts, and opinionated design decisions throughout. It works well, but setting it up requires reading the code and adapting things to your own setup.

## What it does

- **Incremental reading** — articles are broken into atomic claims, tracked across sources
- **Knowledge modeling** — the system maps what you know and surfaces articles at ~70% novelty (zone of proximal development)
- **AI claim extraction** — LLM-powered extraction of claims from articles, books, and highlights
- **Multi-source ingestion** — email web clipper, Twitter/X bookmarks with speech transcription, Kindle highlights, Chrome extension
- **Curriculum-based organization** — Opus-generated curriculum nodes (50-80 per domain) connect books, articles, and review
- **Microlearning cards** — review cards with primary sources, material evidence, and cultural artifacts
- **Book companion** — structured reading support with chapter-level knowledge tracking

## Architecture

**Frontend**: Expo SDK 54 (React Native), 2-tab layout (Feed / Library) + drawer navigation.

**Backend**: Hetzner VM — nginx reverse proxy, Python research server, 4-hour cron pipeline for article processing.

**Data**: SQLite (canonical store), with [limbic](https://github.com/houshuang/limbic) for embeddings and semantic search.

**Chrome extension** (`clipper/`): Save articles from the browser, capture Kindle highlights and notes.

**Scripts** (`scripts/`): Data processing pipeline — article extraction, claim embedding, curriculum bootstrapping, book research agents.

## Local development (Mac or Linux)

Rough path for a second machine; paths are examples — adjust to your layout.

1. **Clone** the repo and create a Python **venv** at the repo root: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`  
   Optional: `pip install -e /path/to/limbic` if you use embeddings features that need it.

2. **API keys (repo root)** — copy templates and edit (never commit filled files):
   - `cp .env.keys.template .env` — set at least **`GEMINI_KEY`** or **`GEMINI_API_KEY`** (book research and many interactive paths use Gemini + Google Search via `scripts/gemini_llm.py`). OpenAI-only mode has **no live web search** for `call_with_search`.
   - Optional: `ANTHROPIC_*`, `OPENAI_API_KEY`, `PETRARCA_OPENAI_MODEL`, `PETRARCA_BOOK_RESEARCH_MODEL` — see comments in `.env.keys.template` and `scripts/env.mac-mini.example`.

3. **Data layout** — `bash scripts/bootstrap-mac-mini.sh` creates `scripts/.env.mac-mini` from `scripts/env.mac-mini.example` (first run), sets `PETRARCA_DATA`, SQLite under `~/petrarca-data` by default, and `CURRICULUM_DIR`. Edit `scripts/.env.mac-mini` for your disk layout; that file is **gitignored** once it exists.

4. **Expo app** — `cp app/.env.example app/.env` and set **`EXPO_PUBLIC_RESEARCH_SERVER_URL`** to your research host (e.g. `http://192.168.x.x:8090` on the same Wi‑Fi, or Tailscale). Restart Metro after any change to `app/.env`.

5. **Run** — from repo root: `bash scripts/dev-all.sh` starts `research-server.py` on **:8090** (health check) then Expo Metro on **:8081**. Or run `bash scripts/run-research-server.sh` and `cd app && npx expo start` in two terminals.

6. **Sanity** — `curl -sS http://127.0.0.1:8090/health` should return `{"status":"ok"}`. More detail: `research/implementation-status.md`, `CLAUDE.md` (deploy and store rules).

## Tech highlights (for Claude Code users)

This project demonstrates several patterns that may be interesting:

- **Claude as sub-agent**: Uses `claude -p` for content generation, claim extraction, and curriculum research
- **Multi-model orchestration**: Claude for complex reasoning, Gemini for vision and post-processing, local models for embeddings
- **Systematic data processing**: Pipeline scripts that process hundreds of articles through LLM extraction
- **Chrome Extension integration**: Browser clipper that feeds into the mobile app's reading queue
- **[limbic](https://github.com/houshuang/limbic) integration**: Semantic search, novelty detection, and knowledge clustering

## Related

- [Blog post on Substack](https://networkedthought.substack.com/)
- [limbic](https://github.com/houshuang/limbic) — shared data curation backend
- [Alif](https://github.com/houshuang/alif) — sister project for Arabic language learning, similar architecture
