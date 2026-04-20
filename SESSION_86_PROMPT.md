# Session 86 continuation — Voice Calibration with Real Audio

**Status at start of this session:** Session 85 completed (evidence gate, recency decay, front-load, alignment). Session 86 (April 19–20, 2026) completed out-of-band: calibration page built, synthetic capture incident discovered + cleaned up, three-layer provenance hardening shipped (commit `daad91b`). See `research/session-changelog.md` § "Session 86" for the full narrative.

**What Stian will do before starting:** record a fresh voice capture (real audio, on the mobile app) about whatever he's just read or listened to. This produces a new `voice_transcripts` row with `input_mode='audio'` — the first real data-point to calibrate against since the synthetic rows were cleaned.

---

## Priority 0 — Verify the fresh capture round-trips cleanly

1. Smoke-test: `ssh alif "sqlite3 /opt/petrarca/data/petrarca.db \"SELECT id, source, input_mode, audio_bytes, length(transcript) AS tlen, substr(transcript, 1, 120) FROM voice_transcripts WHERE source IN ('voice_capture','voice_capture_entity') ORDER BY created_at DESC LIMIT 3\""` — the newest row should have `input_mode='audio'`. If it shows `text_json` or `NULL`, something is wrong with the provenance-stamping path; check `_handle_explore_capture` and `process_voice_capture(input_mode=...)` threading in `scripts/research-server.py` + `scripts/review_engine.py`.
2. Open `http://alifstian.duckdns.org:8090/voice/calibration?limit=5` and confirm:
   - 🎙 audio badge appears on the new row (green)
   - The real Sicily `vt_1775365719` from Apr 5 still shows `? mode` (pre-migration, correct)
   - Disfluency pattern in the new transcript — should have real `uh/um` markers from Soniox

## Priority 1 — Calibrate against real data

Once a real capture exists, use it to investigate the pipeline gaps that the calibration page surfaced in Session 86 but that weren't fixed yet. From `research/session-changelog.md` § Session 86 § "Pipeline gaps observed":

1. **Entity-path facts don't generate multicue quizzes** — if the new capture triggers the entity path (topic outside existing curricula), does the calibration page show 0 `microlearning_quizzes` rows for the entity's `key_facts`? If so, `generate_multicue_quizzes()` needs extending to the entity path, or the entity key_facts need to enter a shared multicue pipeline with curriculum-path facts.

2. **Unrouted facts** — likely 30–40% of extracted facts will have `node_ids=[]` and `entities=[]`. These are captured but have no downstream consumer. Is there a useful intervention (e.g., auto-propose curriculum expansion, or surface as a "what is this?" gap-fill prompt) or should they simply be discarded?

3. **Wonderings never surface as cards** — the `llm_result.wonderings[]` array is populated but nothing displays them. Each wondering is a "productive gap" the user has flagged; could surface as ML cards of `source_type='voice_wondering'` (infrastructure exists via `create_microlearning_request`).

4. **Provenance asymmetry**: `knowledge_items.sources[]` voice_capture entries lack `capture_id`, so "which voice capture touched this KI?" is unreconstructible. Fix by adding `capture_id` to the curriculum-path source entry (one line in `process_voice_capture` where it appends to `sources`).

5. **Memory_hook missing on book-sourced KIs**: `cached_question` from book ingestion lacks `memory_hook`. Two options: (a) backfill by running enrichment over all book-sourced KIs; (b) change the question generator to always produce a hook. Inconsistency is probably worse than either option.

## Where to look
- **Calibration page**: `scripts/voice_calibration.py` (builder), `scripts/voice_calibration.html` (renderer), `scripts/research-server.py` (routes at line ≈7349), route `/voice/calibration` / `/voice/calibration-data?limit=N`
- **Ingest paths + provenance**: `_log_voice_transcript` (review_engine.py:25), `process_voice_capture` (review_engine.py:4895, accepts `input_mode` param), `_handle_explore_capture` (research-server.py:4607, assigns based on whether audio_path was set)
- **Cleanup**: `scripts/cleanup_voice_dupes.py` uses new dedup key `(substr(transcript, 1, 200), 10-min bucket)`
- **CLAUDE.md § Production Data Discipline**: rule forbidding agents from POSTing synthetic text to ingest endpoints

## Not priorities for this session
- Don't re-investigate the synthetic capture incident — it's resolved, documented, and the 9 test rows are deleted.
- Don't touch the 11 surviving `knowledge_entities` created from synthetic captures (Karl XII, Rollo, etc.) — user chose to keep them since he has real knowledge of those topics from reading.
