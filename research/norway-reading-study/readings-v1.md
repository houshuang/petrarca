# Bounded readings v1 · 22 September 2026

This first release prepares three reviewed Norwegian explanations from explicit original reader wonderings: rock-carving technique, the regional meaning of 1177 BCE, and karveskurd. The fixed [reviewed payload](readings-seed-v1.json) carries the original quote, bounded question, roughly 190-word text, checked external citations, reviewer, and two optional quiz targets each. The karveskurd image is a labeled explanatory schematic, not an archaeological object. No question is scheduled by importing or viewing a reading.

The private operator imports reviewed content into canonical SQLite after the code is deployed:

```sh
python3 scripts/reading_study_readings.py research/norway-reading-study/readings-seed-v1.json
```

The operator uses the existing SSH stdin-JSON admin boundary; it does not POST to a learner-capture endpoint. The import checks each exact quote against `study_intake.source.transcript`, requires an archived source, and stores the original audio and transcript hashes plus raw character offsets. It refuses supplied parent/depth fields, inferred interest, changed content under an existing ID, an unsupported illustration, and a fourth quiz target. The server assigns depth one. A correction uses a new brief ID; the old immutable version remains in SQLite and the new one becomes active. A shared target ID across briefs remains one quiz goal.

`GET /study/readings` serves the finite active catalogue. `POST /study/readings/select` accepts only a current brief ID and one to three of its target IDs. Selection is idempotent and appends a `study_items` prompt plus its own fresh `study_positions` row for each newly selected target. Existing positions, history, and frozen run snapshots stay unchanged. Target IDs are stable; a repeated tap or retry returns the prior selection. Existing study FSRS grading still controls later scheduling.

On the phone, **Valg → Det du lurte på** opens the catalogue; the existing learning-aids page has the same entry. **Forklar kort** appears after revealing a card answer when a prepared reading shares that card's original source. The review component stays mounted under the reading and learning-aid screens, so returning does not reset the current card or answer. A brief displays its source and citations, with the original quote collapsed. Quiz options are initially unselected. The explicit selection receipt states how many new items were added. Loading, empty, offline/error, and retry states are shown; a failed selection keeps the choices.

`study_reading_shown` logs the brief ID, content hash, source and exposure-only status through the app's existing `logEvent` transport, even if no practice item is active. When a practice item is active, opening a brief also emits run/item `feedback` with `dimension=reading_help`; the server sees this before a later completion and withholds FSRS credit for an assisted answer. A displayed explanation is not a memory grade. Citation clicks are links only and do not spawn another brief or ingest the destination. The catalogue has no descendant suggestions or feed.

The pilot uses fixed, reviewed content. It adds no new LLM call path or Limbic runtime dependency; later source-bound batches can reuse the private reviewed import without changing the phone API. This deliberately leaves automated generation, semantic duplicate discovery, and image acquisition outside v1.
