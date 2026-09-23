<p align="center"><img src="design/assets/logo-combined.svg" width="320" alt="Petrarca" /></p>

# Petrarca — reading and memory companion

A personal mobile app for remembering what you read in nonfiction books. You read physical books; Petrarca maps chapters onto LLM-generated curricula (people, events, periods), asks you to recall what you read by voice, and schedules quiz and "structural" cards (timelines, contemporaries, cause-and-effect chains) with FSRS. Named after Francesco Petrarca, pioneer of systematic reading methods.

It started in March 2026 as an intelligent read-later app. In April it was redesigned around review and voice recall, and the article feed and ingestion pipeline were switched off (the code is still in the repo). Its current use is a self-study of a twelve-volume history of Norway ([`research/norway-reading-study/`](research/norway-reading-study/study-index.md)).

Blog post: [Petrarca: an intelligent companion](https://networkedthought.substack.com/p/petrarca-an-intelligent-companion)

## How it was built

Built with Claude Code (recent work also with Codex) over about 600 commits and 90+ numbered agent sessions, steered by one person. The agent configuration is the most reusable part:

- [`CLAUDE.md`](CLAUDE.md): design principles that override implementation convenience, a list of disabled subsystems agents must not build on, a "where to look" table per area, and production-data rules added after agents destroyed real data.
- [`research/`](research/README.md): design documents, experiment log (append-only) and per-session changelog; agents read these before changing an area.
- [`design/DESIGN_GUIDE.md`](design/DESIGN_GUIDE.md): the visual language every UI change must follow.
- `SESSION_*_PROMPT.md`: handoff prompts from one agent session to the next.

> **Shared as-is.** Built for one person's reading, not packaged as an open-source product. It contains the author's server references and deployment scripts.

## Architecture

- **App** (`app/`): Expo SDK 54 (React Native), iOS standalone build with OTA updates, plus web.
- **Server** (`scripts/research-server.py`): a single Python HTTP server on port 8090 behind nginx; runtime reads and writes go through `scripts/curriculum_db.py`, review logic in `scripts/review_engine.py`.
- **Data**: SQLite (`petrarca.db`) as the only store; [limbic](https://github.com/houshuang/limbic) for embeddings, similarity and clustering; Wikidata for entity resolution.
- **LLMs**: Claude via `claude -p` for batch work and curriculum generation (Opus). Older call sites still use Gemini Flash and are being migrated.
- **Chrome extension** (`clipper/`): saves articles and Kindle highlights (part of the disabled read-later path).

## Running it

The server is written for one Linux host: data paths default to `/opt/petrarca/...` and are overridden by environment variables at the top of `scripts/research-server.py` (for example `PETRARCA_DB_PATH`).

```bash
pip install -r requirements.txt
python3 scripts/research-server.py      # http://127.0.0.1:8090

cd app && npm install
npx expo start --web                    # the web build calls <host>:8090
npm test                                # jest
```

Pipeline prompt/model regression tests: `python3 scripts/pipeline-tests/run.py`.

## Related

- [Alif](https://github.com/houshuang/alif): Arabic reading trainer with the same stack (Expo, FSRS, `claude -p`)
- [limbic](https://github.com/houshuang/limbic): shared embedding and data-curation library
