# Phone pilot v1: protocol, observations and release ledger

Registered 13 September 2026, before production activation. This is an
observational, single-reader feasibility pilot, not a randomized experiment.
The first question is which small set of phone interactions is useful enough
to keep doing while reading continues. Success is useful practice and interpretable
evidence; activity counts alone do not establish comprehension or retention.

## Intervention and content

[Immutable seed](pilot-v1.json): 13 items: six term introductions, one aspect,
one sequence, one causal, one synchronic introduction, and three voice prompts.
[Source registry](sources-v1.json): four real recordings, including the separate
pre-reading baseline. Three reading recordings total 6,543.360 seconds. This is
continuous recorded reading, speech and possible pauses, not isolated active
reading. Page endpoints do not prove every page was read.

The seed includes target IDs shared across different prompts, intended depth,
source recording/segment/offset and transcript version, and verification links.
A card source records an encounter with the subject, not reader authorship or
understanding. The Mycenaean comparison is explicitly introduced as an added
world-history connection, not assumed prior knowledge. Exact disputed ASR dates,
unverified migration/language claims and the full set of extracted details are
excluded from grading. Language remains a study priority for a later carefully
sourced prompt; it has not been silently dropped from the overall curriculum.

Selection: six at a time, due items first then curated order, separate Review and
Voice sessions, ten-minute cooldown after completion/introduction/skip. First
concept and Mycenaean introductions record exposure only. Existing FSRS handles
only tested positions when the reader declares the book closed; open/unknown
context is saved without memory credit. Visible structural anchors get no credit.
Knew/missed is a self-report, not external scoring. FSRS may produce long intervals;
inspect those against the pilot's needs before changing the registered policy.

## What is actually retained

| Record | Meaning / linkage |
|---|---|
| `study_sources` | Audio hashes, Tana journal/audio IDs, book volume, page checkpoints, recording duration and capture method |
| `study_items` | Immutable prompt, answer, references, format, target IDs and intended depth; replacement requires a new ID/version |
| `study_revisions` | Full seed and selection/evidence policy, backend Git commit, design version, activation/restoration history |
| `study_runs.snapshot` | Exact selected item/answer/position/scheduling state, revision and app client context when the session was created |
| `study_events` | Stable event ID, run/item ID, original client wall time, receipt time, elapsed time since appearance, book context, app/runtime/OTA version, event details and scheduling result |
| `study_audio` | Original response audio path/hash, run/item/purpose, receipt time, audio provenance and current transcription status |
| `study_transcriptions` | Append-only transcription attempts, model/pipeline/actual worker Git commit, text and status |
| `study_positions` | Current FSRS state for explicitly tested positions; no automatic knowledge-state upgrades |

Events include card/introduction mounting, individual/mass answer reveals,
per-position self-grades, completion, skip, book-open/closed declaration, term
recognition, source opens, quality feedback, capture intention/start/stop/failure,
upload/playback, scroll endpoint/viewport size, app foreground/background and
leaving the screen. Spoken purposes are recall, wondering, correction, reflection.
Generic app interactions also continue through `logEvent`; Stats has study-specific
events and displays activity rather than a mastery percentage.

Events are persisted on the phone before transmission and retried with unchanged
IDs, occurrence times and payloads. A separate network queue lets new actions be
persisted during a slow request. The server atomically deduplicates grades;
resuming a run returns already-completed items. Audio is copied to app documents
and indexed before upload; its original URI remains indexed if copying fails.
It is deleted locally only after server and upload-event acknowledgements.
Network failures leave a retry action. Backgrounding or leaving recording stops
and retains the capture. Abrupt OS termination, storage failure, mic permission
failure and inaccessible browser blob recordings cannot be represented as zero
risk; the native phone is the supported durable recording path.

A mount or scroll event is a visibility proxy, not eye tracking. Elapsed foreground
time includes thought, distraction and reading; do not call it precise attention
or subtract it from Tana duration without a justified alignment. Existing ASR text
is a fallible derivative of retained audio, never an automatic grade. Recognition,
rough meaning, explanation and exact-date recall are different outcomes. Repeated
exposure through another format is a possible practice effect, not an independent
baseline; use shared target IDs and full reveal histories during analysis.

## Rapid iteration procedure

1. Snapshot study tables and relevant conversations before analysis. Join events
   to their run snapshot and source IDs; compare like intended depths and declared
   context. Examine raw spoken responses and wonderings, not just grade counts.
2. Log the problem, proposed design change, hypothesis and expected observable
   effect in `research/experiment-log.md` **before applying** it. Change one
   meaningful feature at a time where practical. Preserve the rejected design.
3. Revise source/answer interpretations with a correction record. Do not rewrite
   old prompts, transcripts, decisions or observations. Use new item IDs for
   content changes and a new design version when the selection/measurement policy
   changes. The installer suspends superseded seed items without deleting them.
4. Commit and deploy from the owned checkout. Activate that revision explicitly;
   subsequent run snapshots bind to it. Existing runs keep their original content.
   An OTA identifier on each event distinguishes a new client used on an old run.
5. Inspect the first real phone session for source linkage, event ordering,
   pending audio/transcription and whether feedback is usable. No fabricated
   voice test rows in production. Do not expand other curricula until this loop
   proves useful to Stian.

No automatic experiment assignment, automatic interpretation of understanding,
TTS/hands-free flow, general curriculum expansion, or randomized comparison has
been implemented in v1. Cast cards, broader sweeps and Defender remain later
options. The old card stream and grading routes are paused globally while focus
is active; old rows and due dates are untouched, so resuming can expose overdue
items. Restoring focus is an explicit operation, not a hidden reset.

## Operations

Run from the integrated server checkout using its configured Python environment:

```sh
python3 scripts/reading_study_admin.py activate
python3 scripts/reading_study_admin.py status
python3 scripts/reading_study_admin.py export --output /private/new-export-directory
python3 scripts/reading_study_admin.py retry-transcription
python3 scripts/reading_study_admin.py restore
```

Exports are consistent SQLite snapshots with per-file row counts and hashes,
including source/configuration links and transcription history. Audio paths and
hashes remain in the export; audio files are retained separately under the server's
study audio directory and require the same backup discipline as existing recordings.
Keep exports private. `activate` and `restore` are administrative actions, not
phone ingestion endpoints. Back up SQLite before first activation.

Deploy with `scripts/deploy-study.sh`: it runs an unchanged copy of the sanctioned
unified `~/src/expo/scripts/deploy.sh` using a temporary config whose only change
is this owned checkout's path. This avoids deploying or modifying unrelated work
in the old shared checkout. Then it installs the versioned private mobile route
allowlist and publishes the iOS preview OTA. No native dependency change.

## Validation / release record

Pre-release: 13 isolated SQLite/HTTP guard tests and five client durability tests
pass; TypeScript passes. Backend tests run actual canonical FSRS while replacing
only external database bootstrap and LLM dependencies. Generated, ignored legacy
article JSON files were copied read-only from the existing local cache solely to
satisfy the unchanged TypeScript test imports; no feed subsystem changes.
The 390×844 web rendering of the native components was exercised with an isolated
SQLite fixture: introduction, chronology reveal/self-grade/advance and voice
entry. This does not verify a real iPhone microphone or installed OTA reception.
Production activation and release identifiers are recorded separately after deploy.

Pre-activation SQLite backup: `/opt/petrarca/data/backups/norway-pilot-before-20260913T062235Z.db`
(46,645,248 bytes; SHA-256 `6c56d5f4013a53a571d963ccf564cd150d0baad4cc84eebbe0503561d56248ff`).
