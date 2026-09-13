# Incremental source intake and monthly observation v1

Registered before implementation in the 13 September experiment log. This release supplies operator tools, an auditable SQLite queue and a reproducible monthly selection. It does not install a recurring collector or promise a 24-hour service. Discovery still requires the authenticated Tana Outliner connector; generation requires a logged-in local Codex CLI. No synthetic learner material enters production.

## Discovery and preservation

Use `mcp__tana_outliner__search_nodes` in workspace `VSazTvUjtQ`, with `and: [{hasType: "0VhmSsp1En"}, {created: {last: 3}}]`, limit 50. Compare journal/audio IDs with the registered source manifest. Read matched journal/audio nodes with `read_node`, retain the original snapshots privately, and download the original audio from the returned media link without logging its signed URL. Widen the time window after a missed interval; a full 50-result response is not proof of complete discovery. Select Norwegian-history reading by actual source contents. Do not infer page coverage, volume or reader authorship from polished prose.

The bounded 13 September check returned only the four already archived recordings. Their original audio hashes were reverified and copied with their original transcripts into the private `source-archive-v1/<audio-sha256>` archive. This is an additional same-disk copy, not an independent backup.

```sh
python3 scripts/reading_study_archive.py archive --source PRIVATE_SOURCE_METADATA.json --audio ORIGINAL_AUDIO --transcript ORIGINAL_TRANSCRIPT --destination PRIVATE_ARCHIVE_ROOT
python3 scripts/reading_study_intake.py register --archive PRIVATE_ARCHIVE_ROOT/AUDIO_SHA256
python3 scripts/reading_study_intake.py status
```

Metadata includes stable source ID, original journal/audio node IDs, Tana link, verified volume or null, capture mode/evidence, known coverage and original timestamps. Do not persist signed media URLs in runtime metadata. Archives are immutable and checksummed; a conflicting transcript/metadata revision is rejected for explicit reconciliation. Originals remain untouched. Registration verifies archive contents; identical audio cannot create another intake row. Already-published original sources are recognized without creating more cards.

## Draft and reviewed publication

```sh
python3 scripts/reading_study_intake.py draft --source-id SOURCE_ID --output NEW_PRIVATE_ATTEMPT_DIRECTORY
python3 scripts/reading_study_intake.py publish --source-id SOURCE_ID --reviewed-sha256 EXACT_RETURNED_HASH --reviewer REVIEWER_ID
```

The draft command uses `codex exec` with read-only sandbox, ephemeral execution and a JSON schema. Original prompt, schema, execution log, stderr and returned draft stay in a private attempt directory. Source text is untrusted data. The prompt retains unresolved book/reader attribution, requires exact source substrings and external factual references, and permits zero useful candidates. Runtime validation rejects invented source spans, unsupported types/topics and absent references. A timeout or validation failure enters the visible failed state; retry uses a new attempt directory. No old draft is automatically published after a failure.

The reviewing operator checks the exact quoted span, author/reader ambiguity, historical accuracy against the linked authoritative pages, usefulness, duplication and phrasing. This is agent work; the reader need not approve individual cards. Review binds the complete draft hash. Publication is atomic and append-only: new items and positions, source provenance and a frozen full seed/policy revision. Prior item payloads, run snapshots and scheduling rows remain untouched. Exact publication retries are safe. Title/question dedup is exact after case folding; semantic duplication still needs review. The new queue is operator-visible, not a new phone notification surface.

Canonical operations are `curriculum_db.study_action('intake', ...)` and `('monthly', ...)`. The stdin-JSON server operator uses existing SSH access; there is no new public ingest endpoint. Runtime state is only in SQLite (`study_intake`, `study_intake_events`, `study_monthly_samples`); private files are original evidence and reproducible batch artifacts. Exports include these tables.

## Monthly selection

```sh
python3 scripts/reading_study_intake.py monthly
```

Waits for at least one fully completed `volume_end` assessment. At first eligible invocation each calendar month, freezes a random seed, eligible volume set, up to three sampled volumes and one fixed cue per volume. Repeated calls return the same sample. Unobserved months are not backfilled; future months cannot be sampled. Stored metadata includes actual completion-event time, latest known card/reference exposure and reading-source timestamp. Source timestamp is not an exact reading time, and unobserved outside exposure stays unknown. This is a bounded observation under ongoing maintenance, not pure forgetting without rehearsal.

The output is an operator-administered prompt sheet with a ten-minute maximum instruction. Record the actual response/help context in an assessment; additional core prompts are additional exposure. A dedicated one-cue-per-volume phone mode and automatic reminders are not implemented. No eligible completed-volume observation exists yet, so there is no monthly sample or invented result.

## Independent backup

```sh
python3 scripts/reading_study_archive.py verify --source PRIVATE_ARCHIVE_ROOT/AUDIO_SHA256
python3 scripts/reading_study_archive.py backup --source PRIVATE_ARCHIVE_ROOT/AUDIO_SHA256 --destination BACKUP_DESTINATION/AUDIO_SHA256
```

Backup verifies all files and restores audio from the destination into a temporary directory for a second hash comparison. It reports filesystem separation but cannot by itself certify provider durability or independence. The destination is still awaiting the reader's choice: no configured Time Machine destination or rclone remote was found. No off-device backup is claimed. Do this for all four original source archives once the destination is known; subsequent source archives follow the same procedure.

Validation: 36 isolated Python study tests passed, including replaced-original rejection, exact source quoting, stale review hash rejection, publication retries, preservation of existing schedules and snapshots, visible failure, monthly freezing, archive corruption and restore checks. The actual Codex CLI/schema path passed an isolated empty-content smoke test, returning zero candidates. Its failure path was also exercised with a fixture. No new reading recording was found, so genuine new-source intake still needs an end-to-end run.


Published code `61d0fcd78e2b8ff813220703277a7c1d422e3726`, iOS update `01a09b90-7e08-713b-9102-659bd174dcad`, EAS group `42a40162-521b-43b7-9d12-417a7b0c9502`, preview runtime `1.0.0`. Private HTTPS health/status/summary returned 200. Production retained 76 items and zero study audio; the four checksum-verified original sources registered as already published with no new cards. September monthly query returned `waiting_for_completed_volume`, creating no sample.

Deployment retained the existing unified script. Its server-side npm install again removed only peer metadata from package-lock; the generated file was archived, the exact metadata-only difference verified and restored, and private gateway/iOS deployment completed. No unrelated server changes were restored.
