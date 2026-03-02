# Prior Art: Tools, Libraries, and Open Source Projects

Research into existing tools, libraries, and open source projects relevant to building Petrarca -- a "smart read-later" app combining article collection, knowledge modeling, intelligent filtering, incremental reading, and spaced repetition.

---

## 1. Read-Later / RSS Apps

### Readwise Reader (Proprietary)
- **What it does well**: The gold standard for power readers. Supports 15+ formats (web articles, PDFs, EPUBs, newsletters, RSS, Twitter threads). AI-powered text extraction (99.2% success rate). Automatic content categorization and tagging based on topics and reading history. Semantic search across all documents. The killer feature is the **Daily Review**: unprocessed highlights are surfaced randomly, while "Mastery" highlights follow a spaced repetition schedule. Users can generate flashcard-like questions (Q&A or cloze deletion) from any highlight. Themed Reviews let you build review sets by topic/tag. API-first design with good export to Obsidian, Notion, etc.
- **What's missing**: No true incremental reading (no priority queues, no extract-schedule-review pipeline). Knowledge modeling is implicit (highlight history) rather than explicit (no "I already know this" signals). The SRS is limited to highlights, not applied to article prioritization. Closed source, subscription ($8/mo).
- **Learn from**: Daily Review UX, highlight-to-flashcard workflow, API-first architecture, the way they combine read-later + SRS in one product.
- **Source**: https://readwise.io/read

### Omnivore (Open Source, Defunct Service)
- **What it does well**: Was the most complete open-source read-later app. Clean reading experience, highlights, annotations, labels, newsletter ingestion, API. Full TypeScript stack: Next.js frontend, GraphQL API, PostgreSQL, Mozilla Readability for content extraction, Stitches/Radix UI for components. Docker Compose for self-hosting.
- **What's missing**: Team was acquihired by ElevenLabs in October 2024; cloud service shut down November 2024. No smart filtering, no SRS, no knowledge modeling. Code remains on GitHub under AGPL-3.0 but is essentially unmaintained.
- **Build on**: Excellent reference architecture for a read-later app. Study its content extraction pipeline, label system, and GraphQL API design. The codebase is a template for what "table stakes" features look like.
- **Source**: https://github.com/omnivore-app/omnivore

### Matter (Proprietary)
- **What it does well**: Beautiful mobile reading experience. Three integrated paradigms: read-it-later, subscriptions (follow writers/newsletters), and discovery (algorithmic recommendations). AI "Summarize" and "See more content like this" features. Text-to-speech for hands-free listening. Transcribes YouTube and podcasts to time-synced text.
- **What's missing**: Closed source. Recommendation algorithm is opaque. No SRS or knowledge modeling. No incremental reading features.
- **Learn from**: The three-paradigm organization (save, subscribe, discover) is a good mental model. The TTS-for-articles feature is useful for commuting. YouTube/podcast transcription is a differentiator.
- **Source**: https://hq.getmatter.com/

### Pocket (Proprietary, Mozilla)
- **What it does well**: Largest read-later userbase. Good browser extension. "Pocket Recommendations" surface popular/trending content. Integration with Firefox.
- **What's missing**: Minimal intelligence in filtering. No SRS. No knowledge modeling. Recommendation is editorial/popularity-based, not personalized to what you already know. The product has stagnated.
- **Learn from**: The browser extension UX for quick saving is the baseline expectation. Their "Recommended" feed shows the appetite for discovery features.
- **Source**: https://getpocket.com/

### Instapaper (Proprietary)
- **What it does well**: Clean reading experience. Highlighting with export. OAuth API for bookmarks and highlights. Obsidian plugin. Good import/export.
- **What's missing**: API has a 500-item-per-folder limit. Highlights limited to 5/month for free users. No SRS, no smart filtering. Development has been slow.
- **Learn from**: API design is well-documented and simple. Good reference for highlight data model (highlight_id, bookmark_id, text, position, timestamp).
- **Source**: https://www.instapaper.com/api

### Wallabag (Open Source)
- **What it does well**: Most mature open-source read-later app. Self-hosted, PHP-based. Content extraction with offline storage. Tags, favorites, annotations, highlighting. Automated tagging rules (based on domain, reading time, keywords). Export to EPUB, MOBI, PDF. Native iOS/Android apps. Robust OAuth-protected API with webhooks. Import from Pocket, Instapaper, Readability, Pinboard.
- **What's missing**: No SRS. No smart filtering or recommendations. No knowledge modeling. PHP stack is harder to extend with ML features. UI feels dated compared to Readwise/Matter.
- **Build on**: Could use as an article ingestion/storage backend. The tagging rules system is a good pattern for automated organization. API with webhooks is useful for integration.
- **Source**: https://github.com/wallabag/wallabag

### Readeck (Open Source)
- **What it does well**: Lightweight, modern read-later app. Single Go binary, easy to self-host. Multi-color highlighting with sidebar aggregation. Adjustable typography (font, width, text size, line height). EPUB export. Content stored locally (no external requests after save). Mastodon thread capture. Clean, minimal UI.
- **What's missing**: No PDF support. No integrations with PKM apps. No TTS. No RSS ingestion. No SRS or smart features. Relatively new project.
- **Learn from**: Good example of a lightweight, focused read-later app. The multi-color highlighting UX and typography controls are worth studying.
- **Source**: https://codeberg.org/readeck/readeck

### Karakeep / Hoarder (Open Source)
- **What it does well**: Modern "bookmark everything" app with **AI-based automatic tagging** and summarization. Supports links, notes, images, PDFs. Uses LLM inference (OpenAI or local Ollama models) to generate tags and summaries. Full-text search via Meilisearch. Modern stack: Next.js App Router, Drizzle ORM, NextAuth, tRPC, Puppeteer for crawling. AGPL-3.0.
- **What's missing**: No reading experience (just bookmarking). No SRS. No incremental reading. AI features are tag/summary only, not filtering/ranking.
- **Build on**: The AI tagging architecture is directly relevant. Their pattern of async AI processing via job queues (OpenAIQueue) is a good model. The Ollama integration for privacy-first AI is valuable. The tRPC + Next.js architecture is modern and well-structured.
- **Source**: https://github.com/karakeep-app/karakeep

### Miniflux (Open Source)
- **What it does well**: Minimalist RSS reader in Go. Fast, light, PostgreSQL backend. Strong readability extraction. Supports Atom, RSS, JSON Feed. OPML import/export. YouTube video playback. REST API. Good for "set and forget."
- **What's missing**: Deliberately minimal -- no smart features, no annotations, no SRS.
- **Build on**: Could serve as the RSS ingestion layer. Clean API for feed management. Good reference for how to handle feed polling, content extraction, and deduplication.
- **Source**: https://github.com/miniflux/v2

### FreshRSS (Open Source)
- **What it does well**: Feature-rich, extensible PHP RSS reader. Extension/plugin system. Multiple database backends (SQLite, PostgreSQL, MySQL). Multi-user support. Web UI with keyboard shortcuts. Active community.
- **What's missing**: No smart features. Plugin system could theoretically be extended but PHP is limiting for ML.
- **Learn from**: Extension architecture for adding features. Shows how a mature RSS reader handles the full feed lifecycle.
- **Source**: https://github.com/FreshRSS/FreshRSS

### Feedbin (Open Source)
- **What it does well**: Clean, polished RSS reader. Supports RSS, email newsletters, podcasts, YouTube. Full content extraction. Good API. Open source (Ruby on Rails) under MIT license.
- **What's missing**: Complex to self-host (many moving parts). $5/month hosted. No smart features.
- **Learn from**: Multi-source ingestion (RSS + newsletters + podcasts + YouTube) is the right model for Petrarca's intake layer.
- **Source**: https://github.com/feedbin/feedbin

---

## 2. Knowledge Management + Reading

### Polar Bookshelf (Open Source)
- **What it does well**: The closest existing tool to Petrarca's vision. PDF and web content reader with **incremental reading** features. "Pagemarks" for tracking reading progress with suspend/resume across weeks/months. Text and area highlights. Annotation system. Flashcard creation from highlights with SRS (Anki-compatible). Built on Electron + React + pdf.js.
- **What's missing**: Primarily desktop (Electron). No article recommendation or filtering. No knowledge modeling beyond flashcards. No RSS integration. GPLv3 license. Project activity has slowed.
- **Build on**: The Pagemark concept is directly relevant -- tracking where you are in multiple articles simultaneously is core to incremental reading. Their highlight-to-flashcard pipeline is a pattern to study.
- **Source**: https://github.com/SilverHoodCorp/polar-bookshelf

### RemNote (Proprietary)
- **What it does well**: Best integration of note-taking and spaced repetition. Knowledge graph with bidirectional linking. Any text can become a flashcard. Visual knowledge graph for exploring connections. FSRS algorithm support. The "incremental-everything" plugin (by bjsi) adds SuperMemo-style incremental reading -- interleaving flashcard reviews with notes, paragraphs, websites, video snippets.
- **What's missing**: Closed source. No article ingestion/read-later features. Incremental reading is a third-party plugin, not core. No RSS or content discovery.
- **Learn from**: The seamless note-to-flashcard conversion UX. The knowledge graph visualization. The incremental-everything plugin is the closest implementation of what Petrarca wants to do.
- **Source**: https://help.remnote.com/, https://github.com/bjsi/incremental-everything

### Logseq (Open Source)
- **What it does well**: Privacy-first, open-source PKM. Block-based outliner with bidirectional links. PDF annotation with highlighting and linked notes. Built-in flashcards with spaced repetition. Zotero integration for academic reading. Whiteboards. Advanced queries (Datalog). Plugins/themes ecosystem. New DB version with real-time collaboration.
- **What's missing**: No article ingestion or read-later. No smart filtering. No incremental reading workflow. Flashcard SRS is basic. Not mobile-first.
- **Learn from**: PDF annotation linked back to notes is a good pattern. The block-based structure could inform how extracted segments from articles are stored and linked.
- **Source**: https://github.com/logseq/logseq

### Obsidian + Spaced Repetition Plugin (Proprietary + Open Source Plugin)
- **What it does well**: Obsidian is the most popular PKM tool. The Spaced Repetition plugin supports flashcards (single-line, multi-line, cloze) and **note-level spaced repetition** -- scheduling entire notes for review. Tags/folders for card organization. SM-2 algorithm variant.
- **What's missing**: Obsidian is closed source (free for personal use). No article ingestion. The SRS plugin is for review, not for reading prioritization. No knowledge modeling.
- **Learn from**: The concept of note-level spaced repetition (not just flashcard-level) is relevant -- in Petrarca, this maps to scheduling entire articles or extracts for review.
- **Source**: https://github.com/st3v3nmw/obsidian-spaced-repetition

### Mochi (Proprietary, Free Tier)
- **What it does well**: Markdown-first flashcard app with spaced repetition. Beautiful, minimal UX. AI-powered dynamic review scheduling (adapts in real time). Canvas for drawing/writing answers. Image occlusion. Built-in dictionaries, TTS, translation. OpenAI integration for dynamic card generation.
- **What's missing**: Closed source. No reading features. No article ingestion. No knowledge modeling beyond card history.
- **Learn from**: The markdown-first approach to cards. AI-powered card generation from content. The clean, focused UX.
- **Source**: https://mochi.cards/

### Orbit (Open Source, Research)
- **What it does well**: Andy Matuschak's experimental platform for "programmable attention." Embeds spaced repetition prompts within narrative prose (the "mnemonic medium" -- see Quantum Country). Tasks can be ingested from the web via embedded iframes or APIs. Desktop, mobile, and web review. Aspires to generalize beyond flashcards.
- **What's missing**: Primarily a research vehicle, not a production tool. No article ingestion or filtering. Direction determined by Matuschak's research agenda. Limited adoption.
- **Build on**: The concept of embedding review prompts within reading material is directly relevant. The "programmable attention" framing -- using SRS to ensure you revisit important ideas -- is Petrarca's core thesis applied to reading.
- **Source**: https://github.com/andymatuschak/orbit, https://withorbit.com/

---

## 3. Article Recommendation / Filtering

### Nuzzle (Defunct, 2014-2021)
- **What it does well**: Pioneered "social aggregation" -- surfacing articles trending in your Twitter/Facebook network. No editorial or ML curation; purely based on share counts within your social graph. Configurable thresholds (e.g., "show articles shared by 3+ people I follow in the last hour"). Simple, effective, transparent algorithm.
- **What's missing**: Died when acquired by Twitter/Scroll in 2021. No personalization beyond social graph. No knowledge modeling.
- **Learn from**: The core insight that "what people I trust are reading" is a powerful signal. The threshold-based, user-configurable approach is a model for Petrarca's "open algorithms" principle.
- **Source**: https://nuzzel.com/ (defunct)

### Sill (Active, Bluesky/Mastodon)
- **What it does well**: Modern Nuzzle successor for Bluesky and Mastodon. Shows most-shared links from accounts you follow. Daily email digest. Mute by phrase, domain, or account. Works with the open AT Protocol (Bluesky) and ActivityPub (Mastodon).
- **What's missing**: No knowledge modeling. No SRS. No deep personalization -- just share counts.
- **Build on**: The Bluesky AT Protocol integration is interesting as a source for Petrarca. Sill's approach could be one signal in a multi-signal ranking system.
- **Source**: https://sill.social/

### Refind (Proprietary)
- **What it does well**: Curates articles from 100k+ daily links. Uses both algorithmic signals and expert curators. Rich feedback loop: implicit signals (open, read, listen, share) and explicit signals ("more/less like this"). Daily personalized recommendations. Audio versions of articles.
- **What's missing**: Closed source. No knowledge modeling. No SRS. Opaque algorithm. Community-driven, not personal-knowledge-driven.
- **Learn from**: The multi-signal feedback approach (implicit + explicit) is important for Petrarca's ranking. The "more/less like this" explicit feedback is simple but effective.
- **Source**: https://refind.com/

### Artifact (Defunct, 2023-2024)
- **What it does well**: Instagram co-founders' news app. Used transformer-based ML for personalized recommendations. Key insight: measured **reading time** rather than clicks for engagement signals. Epsilon-Greedy exploration (10-20% of recommendations are outside your usual interests). AI headline rewriting (fixing clickbait). AI summaries in various styles.
- **What's missing**: Shut down January 2024 (insufficient market size for standalone news app). No knowledge modeling. No SRS.
- **Learn from**: Reading time as the primary engagement signal (not clicks). Epsilon-Greedy exploration to avoid filter bubbles. AI-rewritten headlines for clickbait mitigation. These are all directly applicable to Petrarca.

### Gorse (Open Source)
- **What it does well**: Production-ready open-source recommendation engine in Go. Multi-source recommendations (popular, latest, user-based, item-based, collaborative filtering). AutoML for model selection. RESTful API. Dashboard for monitoring. Supports multimodal content via embeddings. Distributed architecture (master/worker/server nodes). Stores data in PostgreSQL/MySQL/MongoDB.
- **What's missing**: Designed for multi-user platforms, not single-user personal tools. Heavyweight for our use case. No content-aware filtering (works on interaction signals, not article content).
- **Build on**: Could use as inspiration for the recommendation pipeline architecture. The multi-signal approach (combining different recommendation strategies) is the right pattern. For a single-user app, a much simpler implementation would suffice.
- **Source**: https://github.com/gorse-io/gorse

### Microsoft Recommenders (Open Source)
- **What it does well**: Best-practices library for building recommendation systems. Implementations of state-of-the-art algorithms (collaborative filtering, content-based, hybrid). Well-documented notebooks and examples. Python-based.
- **What's missing**: Framework/library, not a product. Requires significant integration work.
- **Build on**: Excellent reference for algorithm selection. The content-based filtering approaches are most relevant for a single-user system.
- **Source**: https://github.com/recommenders-team/recommenders

---

## 4. Open Source Libraries to Build On

### FSRS (Free Spaced Repetition Scheduler)

**ts-fsrs** (TypeScript) -- **Primary candidate for Petrarca**
- Latest, most actively maintained FSRS implementation. Supports ESM, CommonJS, UMD. Node 18+. npm: `ts-fsrs`.
- FSRS-6 uses 21 parameters, with defaults optimized from hundreds of millions of reviews across ~10k users.
- Parameter optimizer available via `@open-spaced-repetition/binding` (Rust-based, high performance).
- Research-backed: published at ACM KDD and IEEE TKDE.
- **Key insight for Petrarca**: FSRS can be applied not just to flashcards but to any item with a "review" interaction -- including article extracts, key insights, or even article reading priority.
- Source: https://github.com/open-spaced-repetition/ts-fsrs

**fsrs (Python)** -- for backend/analysis
- Python bindings for fsrs-rs (Rust core). pip: `fsrs`.
- Useful if backend processing is in Python.
- Source: https://pypi.org/project/fsrs/

**Related resources**:
- Awesome FSRS: https://github.com/open-spaced-repetition/fsrs4anki/wiki/Awesome-FSRS
- Algorithm explanation: https://expertium.github.io/Algorithm.html
- Original paper: "A Stochastic Shortest Path Algorithm for Optimizing Spaced Repetition Scheduling" (ACM KDD)

### RSS Parsing

**rss-parser** (JavaScript/TypeScript)
- Lightweight RSS/Atom parser. Works in Node and browser. Supports callbacks and Promises. npm: `rss-parser`.
- Source: https://github.com/rbren/rss-parser

**@rowanmanning/feed-parser** (Node.js)
- Well-tested, resilient parser. Handles invalid feeds gracefully. Good error codes.
- Source: https://github.com/rowanmanning/feed-parser

**fast-xml-parser** (JavaScript/TypeScript)
- Zero-dependency XML parser (104K). TypeScript support. Good for low-level RSS/Atom parsing.

### Article Content Extraction

**@mozilla/readability** (JavaScript) -- **Recommended**
- Same algorithm as Firefox Reader View. Battle-tested on millions of web pages. Configurable character threshold, candidate analysis. npm: `@mozilla/readability`. Use with jsdom for server-side extraction. Used by Omnivore.
- Source: https://github.com/mozilla/readability

**Trafilatura** (Python)
- Consistently outperforms other open-source extraction libraries in benchmarks. Good for server-side processing.
- Source: https://github.com/adbar/trafilatura

**Newspaper3k/4k** (Python)
- Article extraction with language detection, NLP features. Good API.
- Source: https://github.com/codelucas/newspaper

### Embedding Models for Semantic Similarity

**Sentence Transformers / SBERT** (Python)
- 10,000+ pre-trained models on Hugging Face. State-of-the-art for semantic search, similarity, paraphrase mining. Supports 20+ loss functions for fine-tuning.
- **Recommended models for Petrarca**:
  - `multilingual-e5-large-instruct` (1024d, multilingual, instruction-tuned) -- already used in the MDG project
  - `static-similarity-mrl-multilingual-v1` -- 100-400x faster on CPU, 85% of full model performance. Good for on-device inference.
  - `all-MiniLM-L6-v2` -- fast, English-focused, 384d. Good for prototyping.
- Source: https://github.com/huggingface/sentence-transformers

**LaBSE** -- 109 languages, good for multilingual article comparison.

### Text Summarization

For Petrarca, LLM-based summarization (via API or local model) is the practical choice:
- **Ollama** for local inference (privacy, offline support)
- **OpenAI/Claude API** for higher quality when online
- **SummerTime** (Python) -- open-source library supporting multiple summarization algorithms (TextRank, BART, Longformer). Good for experimentation.
- Source: https://github.com/Yale-LILY/SummerTime

---

## 5. Mobile App Frameworks

### Expo (React Native) -- **Recommended for Petrarca**

Already used in the sibling project `../alif` (Expo 54, React Native 0.81, expo-router 6, TypeScript). Key advantages:
- Officially recommended way to start React Native projects (as of 2026).
- EAS (Expo Application Services) for cloud builds, OTA updates.
- Real native UI components (not WebView).
- Hermes JS engine with New Architecture (JSI + Fabric) for native performance.
- Rich ecosystem of Expo modules (camera, audio, file system, etc.).
- Can reuse knowledge and infrastructure from alif project.

**Relevant libraries for a reading app**:
- `react-native-render-html` -- HTML rendering without WebView. Good for article display. Supports custom renderers, DOM manipulation.
- `react-native-typography` -- pixel-perfect typographic styles.
- React Native Paper -- Material You component library.
- `expo-av` -- audio playback (for TTS features).

### Capacitor
- Web-first approach (HTML/CSS/JS in a WebView with native bridges). Easier if coming from web dev. Less native feel than React Native. Market share under 5%.
- **Verdict**: Not recommended for Petrarca. The reading experience needs to feel native, and we already have Expo expertise from alif.

### Flutter
- Google's framework with Dart. Excellent custom UI/animation. Identical look across platforms.
- **Verdict**: Strong option technically, but switching to Dart means losing JavaScript/TypeScript ecosystem synergy with alif and potential shared backend code. React Native job market is 6x larger.

---

## 6. Notable UX Patterns and Design Insights

### From Readwise Reader
- **Ghostreader**: AI assistant that can summarize, generate flashcards, define terms, translate -- all inline while reading.
- **Triage flow**: Inbox -> Shortlist -> Archive, with reading time estimates.
- **Focused reading**: Full-screen reader with minimal chrome, keyboard shortcuts.

### From SuperMemo Incremental Reading
- **Priority queue**: Articles ranked by priority, reviewed in order. Priority adjusts based on reading behavior.
- **Extract and dismiss**: Read until you find something important, extract it, dismiss the rest for now. The extract becomes a new item in the queue.
- **Cloze from extracts**: Automatically or manually create fill-in-the-blank cards from extracted passages.
- **Interleaving**: Alternate between reading new material and reviewing old extracts/cards.

### From Artifact
- **Reading time as signal**: Measure how long the user actually reads, not just what they click.
- **Exploration budget**: Reserve 10-20% of recommendations for content outside the user's comfort zone to prevent filter bubbles.

### From Nuzzle/Sill
- **Social signal transparency**: Show exactly who shared an article and when. Let users set thresholds.
- **Configurable algorithm**: User controls the parameters (minimum shares, time window, sources).

### From Refind
- **Multi-signal feedback**: Combine implicit signals (open, read time, scroll depth) with explicit signals ("more like this", "less like this", "I know this already").

### From Polar Bookshelf
- **Pagemarks**: Visual progress indicators on articles, allowing suspend/resume of reading across many articles simultaneously.

### From Orbit / Mnemonic Medium
- **Embedded prompts**: Place review questions within the reading material itself, not as a separate activity.
- **Programmable attention**: Generalize SRS beyond flashcards to any item that benefits from periodic revisiting.

---

## 7. Gap Analysis: What Nobody Does Well

The following capabilities are core to Petrarca's vision but are not well-served by any existing tool:

1. **Knowledge-aware article ranking**: No tool models what the user already knows and uses that to filter/rank incoming articles by genuine novelty. Readwise sorts by date. Pocket sorts by popularity. Nobody asks "does this article contain information the user doesn't already have?"

2. **Explicit "I know this" signals**: No tool lets users mark concepts/topics as "already known" to reduce redundant content. The closest is Refind's "less like this," but that's preference-based, not knowledge-based.

3. **Incremental reading on mobile**: SuperMemo's incremental reading is powerful but Windows-only and UX-hostile. No mobile app implements the extract-schedule-review pipeline.

4. **Unified pipeline**: No single tool combines RSS ingestion + social bookmarks + content extraction + knowledge modeling + SRS + reading experience. Users cobble together Feedbin + Readwise Reader + Anki + Obsidian.

5. **Open, configurable ranking**: Most recommendation algorithms are black boxes. Petrarca's "open algorithms" principle -- letting the user see and tune the ranking -- is unique.

6. **Concept-level knowledge tracking**: Alif tracks knowledge at the word level (FSRS per word). No reading tool tracks knowledge at the concept/topic level to inform article selection.

---

## 8. Architecture Implications

Based on this research, Petrarca's architecture should consider:

| Layer | Recommended Approach | Key Libraries |
|-------|---------------------|---------------|
| Mobile Frontend | Expo (React Native) with TypeScript | expo-router, react-native-render-html, react-native-typography |
| Article Ingestion | RSS polling + browser extension + API | rss-parser, @mozilla/readability |
| Content Extraction | Readability.js (client) + Trafilatura (server) | @mozilla/readability, trafilatura |
| Embeddings | Sentence Transformers (server) or static models (on-device) | sentence-transformers, multilingual-e5-large-instruct |
| Knowledge Model | Concept-level FSRS + interest decay | ts-fsrs |
| Article Ranking | Multi-signal scoring (novelty, relevance, social, freshness) | Custom, inspired by Gorse/Refind patterns |
| SRS for Extracts | FSRS scheduling of extracted passages | ts-fsrs |
| Summarization | LLM-based (Ollama local / API cloud) | ollama, openai SDK |
| AI Tagging | Pattern from Karakeep (async LLM tagging) | ollama, openai SDK |
| Storage | SQLite (local) + optional sync | better-sqlite3 or expo-sqlite |
| Social Signals | Sill-like aggregation from Bluesky/Mastodon | AT Protocol SDK |

---

*Last updated: 2026-03-02*
