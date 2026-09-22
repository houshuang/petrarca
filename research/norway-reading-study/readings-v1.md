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

## Implementation review and validation

GPT-5.6 Sol implemented the feature; Astra reviewed the data flow, source material, selection transaction and phone-sized UI. Review caught and corrected a missing private mobile-gateway allowlist entry and both paths back to the preserved practice card. The final implementation candidate is `3da52a710133a9c1c20aadb12115d9b53dec5815`.

The affected checks passed: 42 Python study tests, 16 client tests across five suites, four mobile gateway tests, and full TypeScript checking. The last navigation correction also passed its focused test and TypeScript check. Independent browser checks at 390 × 844 used a private SQLite copy, not production: viewing added zero questions; selecting one added exactly one fresh position; reopening showed it already selected; returning preserved the revealed current card; completing after reading recorded `reading_help=true` and `scheduled=false`. Browser checks do not establish native iPhone rendering.

The latest local and remote Git origin Limbic revision inspected was `ac4815c12ca640491f8a148dd05aa3b836997bd1`. Its source-anchor and expected-count helpers checked the three-record seed offline; exact raw quotes were independently checked because normalized matching alone is insufficient for immutable transcript offsets. New Codex CLI, review and audit helpers are relevant to later authoring batches, but this small source-reviewed pilot needs no model invocation from the phone and no production Limbic upgrade. Production Limbic was still `d68cef3` at preflight. The current cached-call registry does not accept a `codex_cli` provider name; a future integration must use the supported callable route rather than assuming it does.

The three texts cite Alta Museum and Meløy municipality for rock-art techniques, Eric Cline's interview and Store norske leksikon for the regional 1177 BCE comparison, and Store norske leksikon plus Bente Magnus, “Ørnen flyr – om Stil I i Norden,” Hikuin 29 (2002), p. 110, for karveskurd. The metal brooch example is explicitly distinguished from carving wood. All six target claims were checked against their brief and compared with the 99 existing questions.

Before release, the canonical export had 99 items, 106 positions, 10 sources, 8 revisions, 14 runs and 355 events. Its manifest hashes were independently verified and the private snapshot retained at `~/.agents/research/petrarca-norway-study/readings-20260922/pre-readings-20260922/`. The original recording's overconfident unaided-recall metadata remains a separate known issue; this release does not rewrite it.
