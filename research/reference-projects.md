# Reference Projects Analysis

## ../otak — Claims-First Knowledge System (CRITICAL REFERENCE)

Otak ("brain" in Malay) is a working claims-first personal research knowledge system with ~67,000 nodes across 40+ domains. Highly relevant to Petrarca.

### Directly Reusable Code
1. **`scripts/fetch_twitter_bookmarks.py`** (268 lines) — Twitter/X bookmark extractor using twikit (internal GraphQL API, no API key needed). Cookie-based auth from Chrome. Already fetched 2,010 bookmarks (2026-02-23).
2. **`scripts/fetch_readwise_reader.py`** (264 lines) — Readwise Reader document fetcher with incremental updates. Already fetched 11,598 documents.
3. **`scripts/llm_providers.py`** (424 lines) — Multi-provider LLM abstraction (Anthropic, Gemini, OpenAI) with async concurrency.
4. **`scripts/ingest_source.py`** (2,312 lines) — Full single-source ingestion: fetch → extract → place → balance. Source-type-specific prompts. Trafilatura HTML→markdown.
5. **`scripts/match_lenses.py`** — Embedding-based personal interest matching (salience lenses).

### Architectural Patterns to Steal
1. **Claims as atomic units** (not documents) — every claim has provenance, evidence level, debate stance
2. **Personal salience lenses** (8 types: belief, interest, open_question, hunch) — attention routing during ingestion
3. **Embedding pre-routing** for deduplication/filing (95.3% recall@20)
4. **Source-type-specific extraction** (different prompts for opinion piece vs. empirical article vs. press release)
5. **Hierarchical tree with include/exclude descriptions** — progressive disclosure
6. **Layered architecture with pace separation** (storage decades > logic years > query months > AI weeks > UI days)
7. **Filing friction = deduplication** (always query existing before inserting)
8. **Staging files for resumability** (survive interruption)

### Research Documents (enormous value)
- `research/claims-knowledge-systems-2026-02-22.md` — Landscape of claim extraction tools
- `research/rich-knowledge-and-salience-2026-02-27.md` — Rich knowledge objects, personal salience
- `research/research-knowledge-system-2026-02-22.md` — Tool landscape (Readwise, Zotero, etc.)
- `research/deep-research-2026-02-23/` — 357KB across 8 files including:
  - `deep_matuschak.md` — Evergreen notes, mnemonic medium
  - `deep_synthesis.md` — Pirolli & Card's foraging theory, sensemaking
  - `deep_joel_chan.md` — Discourse Graphs protocol
- `research/readwise-reader-scan-2026-02-23.md` — Scan of 11,598 Readwise docs, 10 design principles

### Data Already Available
- `data/twitter_bookmarks.json` — 2,010 bookmarks
- `data/readwise_reader.json` — 11,598 documents (15MB)
- `data/joelchan_index.json` — 26K-file discourse graph index

---

## ../bookifier — AI-Enhanced EPUB Generation

TypeScript CLI toolkit for processing books with AI enhancements (OCR, translation, vocabulary).

### Relevant Patterns
1. **Stage-based pipeline** with checkpoints (PipelineStage abstract class) — modular, resumable
2. **Content-based caching** via SHA256 hashing — prevents re-processing
3. **SQLite for persistent state** (WAL mode, separate tables per concern)
4. **Rate-limited API calls** using Bottleneck
5. **Vocabulary/enhancement metadata** stored alongside primary content with HTML anchors for cross-referencing

### Tech Stack
- TypeScript, Node.js, Commander CLI
- SQLite (better-sqlite3)
- Claude 3.5 Sonnet for text processing
- Gemini 2.0 Flash for OCR
- EPUB generation via adm-zip + archiver

### What's Useful for Petrarca
- Pipeline architecture for processing reading material
- Caching patterns for LLM-processed content
- Book enhancement concept (pre-reads, vocabulary, translations)
- Could adapt for Kindle book companion features

---

## ../alif — Arabic Reading Trainer (Mobile Reference)

Expo (React Native) app with FSRS spaced repetition, knowledge tracking at word level.

### Relevant for Petrarca
1. **Mobile setup**: Expo + React Native Web, single codebase iOS/Android/Web
2. **Knowledge modeling**: FSRS at word/lemma level — adapt to concept level
3. **Textbook scanning**: OCR → word-level analysis → knowledge state update
4. **Physical-digital integration**: Scan physical book → update digital model
5. **Session building**: Intelligent selection of what to show next
6. **Interaction signals**: Tap unknown words = rich signal (unmarked = known)

---

## Twitter Bookmark Extraction

**Use**: otak's `fetch_twitter_bookmarks.py` (modern, no API key needed, uses twikit + Chrome cookies)

Legacy alternative: `../twitter-to-bullet/index.mjs` (Node.js, requires Twitter API OAuth — older)
