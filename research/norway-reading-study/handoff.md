# Continue the Norwegian-history experiment

Handoff prepared 13 September 2026 at the user's explicit request. Read this first. Updated after the approved assessment/learning implementation on 13 September.
It consolidates the current state; earlier protocol and release freezes remain
historical evidence. No separate agent has been started and no review is claimed.

See the [running record](running-record.md) for consolidated status, latest release identifiers, conversation coverage and explicit open work.

## Current update — 14 September: focused practice and real-data audit

See [practice audit](practice-audit-20260914.md) and decisions D017–D018. Practice starts directly without an open-book question, under the participant's explicit closed-book practice policy. Normal reading recordings stay open-book unless explicitly recall. Learning aids are now **I dag → Valg → Bilder og tidslinje**; overview is **Fortell → Valg → Fortell oversikten**. Session choices are also inside Valg.

The 09:02 audit confirms 20 completions, 25 graded parts and 15 introductions with consistent saved scheduling. Self-reports apply only to tested questions; Traktbegerkulturen dates remain untested. Old exposure events and timing have documented limits. Latest deployed app adoption before this patch is confirmed by real events from 01a09bca (the update-notice release); earlier claims below that adoption was unconfirmed are historical. No new overview or study response audio exists in this export.

## Current release addendum — assessment, learning aids and intake

Phone entries: **Fortell → Fortell oversikten · uten fasit** and **I dag → Se og forstå · bilder og tidslinje**. Assessment freezes narrative + five cues, confidence, context, original-question pairs at volume end and a three-axis rubric. It never reveals answers or changes memory schedules. Term familiarity is now captured before the initial definition. Ard/åkerrein illustrations, near-application examples and a shared-axis timeline are live. Existing 76 practice items are preserved.

Read [assessment release](assessment-release-v1.md), [learning aids](learning-aids-v1.md) and [intake/monthly/backup runbook](intake-v1.md). The latter supplies operator tooling, not an unattended collector. A new recording is still needed to verify the physical iPhone microphone and genuine new-source intake. The independent backup destination is pending. No pre-app observation, completed-volume observation or monthly result is fabricated.

The earlier state below is retained as historical context where explicitly dated. Current iOS update is `01a09b90-7e08-713b-9102-659bd174dcad` from code `61d0fcd`; all release identifiers and verification are recorded in intake-v1.md. Reopen to download, leave open briefly, then quit/reopen to apply. Device adoption remains unconfirmed.

## Immediate orientation

The phone phase is live: **76 items**, comprising 68 silent Review items and eight
voice prompts, across seven themes. Other curricula remain reversibly paused.
The user liked all original Review cards and has time for substantially more
practice over the next few days, with little new reading. The immediate learning
gap is grounding concrete terms visually and comparatively: the user could not
picture an **ard** or distinguish it from a plow, and also looked up **åkerrein**.

On 13 September the study interface was redesigned after the user supplied physical
iPhone screenshots and described the screen as overwhelming. The core loop is now
session context → attempt → reveal → main-idea judgment; recognition and feedback
choices acknowledge taps visibly, while capture and provenance are collapsed under
“Mer om dette kortet”. This is an interface intervention only: content payloads,
events, grading and schedules were preserved. See the newest experiment-log entry
and the release identifiers below.

Read in this order:

1. [Decisions and corrections](decisions.md), especially D014–D015 and O001–O002/C003.
2. [Live intensive phase](intensive-v2.md): content, scheduling, dependencies,
   hypotheses, interpretation limits and exact release verification.
3. [Full experimental design](experimental-design-review.md) and
   [retention/connection criteria](retention-and-connections-v1.md).
4. [Measurement gaps](measurement-gaps.md), including the v2 status addendum.
5. [Evidence index](evidence-index.md), current snapshots below, and
   [independent-review instructions](reviewer-brief.md) if assigned a review.

## Goals and constraints that must survive the handoff

Read all twelve volumes of Aschehougs Norgeshistorie. Current volume is *Fra jeger
til bonde*, reading coverage approximately pp. 13–146. Success means a confident,
connected overview of Norwegian history, periods/dates connected to other places,
understanding major changes and mechanisms, language/identity questions, trade
networks including copper, and useful recognition/rough meaning of specific terms.
Do not turn every book detail or uncertain argument into a memory obligation.

The eventual comprehensive blog should compare pre-reading, post-reading and
months-later understanding with credible time/exposure data and transparent design
iterations. The fixed assessment instrument now operates; monthly selection is operator-run and waits for completed-volume observations. Continue reading should also elicit justified
connections to previous reading. No background reminder or collector is active.

Tana recording is continuous **during book-open reading**. The user often reads
verbatim, including the author's summaries. Never interpret polished speech or
summary-like passages as the user's integration. Keep unresolved authorship
unresolved. Proposed markers such as “Min tanke”, “Jeg lurer på”, “Min kobling …
fordi …”, “Tilbake til boka” are optional and have no implemented automatic parser.
Do not silently rewrite older interpretation; preserve corrections and provenance.

Phone use away from the keyboard is required. Quick practice remains valuable.
Positive card feedback can coexist with incomplete comprehension. “Hadde hovedideen”
is a self-report about the attempted answer, not proof of visual or transferable
understanding. Do not manufacture telemetry or retrospectively change grades from
this conversation.

## Earlier live state before the assessment release

- Deployed server study code: `d21ba9f0e5d239ac2e6047fa51540ada5e282b67`.
- Deployed mobile interface code: `e985e4ec47143186b497d3efabaf40d5a610c2d8`.
- Design: `norway-intensive-v2`; seed: [intensive-v2.json](intensive-v2.json).
- Study revision: `7cd0fa3244e5613db93a5480e38ff2559feea4aa03f350dc5f6d1f2143bcb698`.
- Current iOS preview update: `01a09b5e-2f11-7e6c-85ff-0c0a01392206`, runtime `1.0.0`.
- Current EAS group: `3db534d1-7702-4b48-9f1d-994784c53847`.
- Previous v2 content release update: `01a09a19-423a-7eb7-b8e5-1870f756e28a`.
- Health, study status and summary returned HTTPS 200; manifest private API
  configuration matched. The device's adoption of v2 has not been confirmed.
- The v2 content release retained its 24 isolated Python and six client checks. For
  the interface release, TypeScript, 12 focused client tests and a 390 × 844 isolated
  browser journey passed. It is not a physical-iPhone microphone test.
- Original thirteen item payloads and previous runs/events preserved. Eight legacy
  tables matched the pre-activation DB backup. Details and hash in intensive-v2.md.
- Repository commit `e985e4e` after the v2 server release changes only the mobile
  interface, client test support and documentation.

Scheduled new closed-book answers use the canonical study-only FSRS policy: Good
for knew, Again for missed; 10m/20m/1d learning steps. First correct → 20m, first miss
→ 10m. Existing graduated state is retained. Extra practice records exposure/answers
without moving FSRS due dates. Introduction, unknown/open-book context and the
personal-connection reflection prompt do not earn memory scheduling credit.
Pending v1 runs retain their v1 grading policy. Do not reactivate the default old
seed or reset old schedules to make the data look uniform.

Six items per batch, one per family. Prerequisites gate on prior **exposure**, not
mastery. A chosen theme can bring in unseen supporting cards from other themes.
Structural cards become due at their earliest testable position and can retest
others. Extra practice and related cues contaminate an otherwise delayed test;
measure elapsed time since all relevant exposure, not just the last scheduled grade.

Event/audio retries are durable, but loading and advancing need connectivity.
There is no complete offline train workflow. Visual enrichment has since shipped in learning-aids-v1; this provides original explanatory diagrams and optional near application, not a broad transfer result.

## Latest participant evidence

- `codex-20260912-L2217`: traversed original cards, likes all, looked up terms such
  as ard. Logs at 09:32:41 UTC show all ten original Review items visited: some only
  introduced, others answered; three original voice prompts have no encounters.
- `codex-20260912-L2275`: ard's appearance and distinction from a plow were unknown;
  åkerrein also looked up. The specific difficulty with åkerrein is not yet stated.
- `codex-20260912-L2315`: explicit request for complete documentation and continuation.

Ard and åkerrein are named self-reported outside learning exposures. Source URLs,
durations, exact times relative to recall, and the remaining terms meant by “etc.”
are unknown. Backgrounding is not evidence of a particular lookup. These are
recorded in the conversation/decision ledger; a structured outside-exposure table
and phone feature are not implemented. Avoid attributing subsequent gains entirely
to Petrarca.

## Evidence a successor can open directly

Conversation snapshot **01c7581bc6c044e8**, 142 message records: 38 Claude and 104
Codex. Includes both recent feedback clarifications, the prior final responses,
this handoff request and the initial acknowledgment. It excludes this turn's
later tools/progress/final response. The exporter deliberately omits tool payloads,
reasoning, system/developer packets and image bytes, reducing credential leakage.
Original append-only logs remain referenced by the private source registry.

- [Current archived Codex conversation](/Users/stian/.agents/research/petrarca-norway-study/conversations/snapshots/01c7581bc6c044e8/codex-20260912.md)
- [Archived Claude discussion](/Users/stian/.agents/research/petrarca-norway-study/conversations/snapshots/01c7581bc6c044e8/claude-20260910.md)
- [Searchable message records](/Users/stian/.agents/research/petrarca-norway-study/conversations/snapshots/01c7581bc6c044e8/messages.jsonl)
- [Coverage and hashes](/Users/stian/.agents/research/petrarca-norway-study/conversations/snapshots/01c7581bc6c044e8/coverage.json)
- [Audio/transcript reader](/Users/stian/.agents/research/petrarca-norway-study/2026-09-12/index.html)
- [Original recording manifest](/Users/stian/.agents/research/petrarca-norway-study/2026-09-12/manifest.json)
- [Corrected authorship annotations](/Users/stian/.agents/research/petrarca-norway-study/2026-09-12/source-annotations-v2.json)
- [Release and preservation evidence](/Users/stian/.agents/research/petrarca-norway-study/phone-practice-v2)
- [Fresh consistent SQLite-table export](/Users/stian/.agents/research/petrarca-norway-study/handoffs/20260913T094108Z/runtime/manifest.json)

The fresh runtime export was taken **2026-09-13T09:41:09.981Z** in one SQLite read
transaction. It contains 76 items, 83 positions, two revisions, four sources, five
runs, 96 events and zero study audio/transcription rows. All nine exported table
files were copied directly, with SHA-256 hashes checked against the manifest.
Original mobile-audio paths, if rows arrive later, refer to the server; JSONL does
not itself include audio bytes. Remote export: `/opt/petrarca/data/study-exports/handoff-20260913T094108Z`.

Initial audio: baseline 530.100s; hunters 2372.904s; farming 1765.080s; bronze
2405.376s. Reading recordings total 1:49:03.360, or 1:57:53.460 including baseline.
These are exact recording durations, **not exact active reading times**. Three
reading transcripts have 189 segments / approximately 5190 ASR words, with
versioned editorial edits/uncertainties. Do not overwrite originals or strip the
source provenance. Avoid copying raw signed source URLs into public docs.

Only the two registered local conversation sources and the initial recording batch
are verified as covered. Claude web, other devices/chats and forum publication
remain unverified. Mac evidence has no verified independent backup/restore. Server
DB backups do not prove original Mac recordings are backed up. No ZIP is needed.

## Smallest useful continuation

If assigned implementation, first inspect current live versions and user activity.
Then prepare a bounded visual-grounding experiment for **ard and åkerrein**:
verified images/diagrams, clearly indicated parts, plain use/formation explanations,
and a relevant comparison. Record asset/source/rights provenance, content versions
and uncertainty. Provide enrichment before asking for memory judgment, retain the
quick flow, and later use a different image/example for recognition/application.
Avoid assuming a picture has improved understanding merely because it was opened.
Register the intervention before changing it, with explicit exposure events and
feedback. Do not silently mutate the immutable original item payloads.

Coordinate this with measurement priorities: stable encounter/capture IDs and
foreground timing (M02–M04), outside-exposure linkage (M12), comparable outcome forms
(M06–M07), and independent backup verification (M08). The user's rapid iteration
request is not a reason to promise complete logging before these exist. Formal
review and implementing the next experiment are separate assignments; follow the
reviewer's read-only scope when assigned only review.

## Code and operational entry points

Selection: `scripts/study_selection.py`; immutable sessions/content/events:
`scripts/study_engine.py`; canonical scheduling: `scripts/review_engine.py`
`_fsrs_reschedule`; HTTP/admin/export: `scripts/study_http.py`,
`scripts/reading_study_admin.py`. Client: `app/components/study/StudyReview.tsx`,
`StudyPracticeOptions.tsx`, `StudyCard.tsx`, `StudyRecorder.tsx`,
`app/lib/study-api.ts`. Tests: `scripts/tests/test_study*.py`,
`app/__tests__/study-api.test.ts`. Runtime database remains server-only SQLite.

Owned checkout: `/Users/stian/src/petrarca/.codex/worktrees/norway-reading-study`,
branch `sh/norway-reading-study`. It will be clean and pushed when handed off.
Read `/Users/stian/.agents/workflows/parallel-work.md`, run agent-start, and
explicitly assume the released continuation lane before edits. Registry:
`/Users/stian/.agents/lanes/petrarca-norway-reading-study-20260912.json`.
The shared `/Users/stian/src/petrarca` checkout is dirty at an older base; do not
reset, stash, switch or copy it over the owned worktree. Latest committed docs are
on origin/main even if that shared working directory looks stale.

Commit/push before deployment. Use `bash scripts/deploy-study.sh` from the clean
owned checkout for combined changes (unchanged unified deploy with an owned-root
configuration, private API install, mobile publish); its message currently describes
v2 and must be revised for a new combined release. Use `app/deploy-mobile.sh` for
app-only updates; the interface release above used this path. Check Expo skills and
compatibility. Never print the private API capability.
Do not POST synthetic captures or grades to production. Test in isolated SQLite.
Tana access must use installed authenticated tana-cli or the appropriate MCP,
never browser automation. No dev servers or browser sessions are left running.

Refresh conversations with `scripts/reading_study_conversations.py` using the
private registry and output paths documented in [study-index.md](study-index.md).
Append decisions and experiment entries, update indexes, freeze evidence with a
cutoff, and retain superseded versions. Do not imply future conversations are
captured automatically. The successor should continue from this evidence, without
reconstructing the study from scratch or treating previous assistant proposals as
implemented behavior.
