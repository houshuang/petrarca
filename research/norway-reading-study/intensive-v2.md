# Intensive Norway practice — v2

Registered 13 September 2026 before implementation in [the experiment log](../experiment-log.md).
User instruction: significant time for atomic practice over the next few days and
little new reading; be substantially more ambitious about visiting and revisiting.
This phase supersedes the v1 content volume and early scheduling, while retaining
the original protocol, thirteen items, recordings and all observed history.

## Delivered scope

76 items: 50 short prompts, 14 term cards, 4 structural cards and 8 voice prompts.
There are 83 positions, including two visible anchors: 81 testable positions.
68 items can be used silently on a train. Seven selectable themes cover chronology,
landscape, livelihoods/farming, materials/networks, concepts/cultures,
language/identity/evidence, and connections. Original items retain their original
payloads; for filtering, untagged v1 items appear under concepts.

The 63 additions include eight term introductions and contextual applications,
six applications of existing terms, 36 short recall/comparison/application questions,
and five voice prompts. They cover already-read themes from volume 1; the questions
and hypothetical examples are assistant-authored, not quotations or observed learner
knowledge. Reading timestamps establish topic exposure, not a verbatim source for
every answer. Historical support is linked per item separately. No baseline statement
has been converted into evidence of independent integration.

[The exact seed](intensive-v2.json) preserves source IDs, transcript versions,
segment/timestamp references, Tana journal links, references, target IDs, question
families, prerequisites, cue type and content authorship. References include NGU,
University of Bergen, University of Oslo terminology, Nationalmuseet, and signed
encyclopedia entries. Regional date differences and archaeological inference limits
are explicit; imported objects do not prove direct travel or a particular language.

## Phone workflow

Open **I dag** and choose the response context once for the session: “Fra
hukommelsen · boken lukket” allows the answer to affect later scheduling, while
“Med støtte · boken åpen” records practice without moving the schedule. Each card
then states the response type, asks for one attempt, exposes one dominant reveal
action, labels the concise answer “Det viktigste”, and ends with “Jeg hadde
hovedideen” or “Jeg trengte svaret”. Six items form a batch, not a daily limit.

Session type and topic are summarized in one compact row under “Denne økten”; use
“Bytt” to change them. Extra practice remains available when no scheduled review is
due, with a one-minute item cooldown. Voice has the same theme/mode controls; unseen
supporting concepts can appear first there too.

A rough planning estimate is 40–80 minutes for an initial traversal including
introductions and voice, spread over sessions. This is not measured and does not
promise that much material will be immediately unlocked. Repeated rounds can support
several further sessions over the coming days. Actual useful duration depends on
thinking time, familiar material, dependency exposure, voluntary elaboration and
feedback. Card count is not an outcome or a retention target.

Optional feedback, source links and recording actions live under “Mer om dette
kortet” so they do not compete with the answer loop. Use “For lett”, “For
detaljert”, “Uklart” or “Nyttig” there to identify what earns its place. Each choice
now shows a persistent selected state and a confirmation. “Jeg lurer på …”, “Noe er
feil”, and “Tanken min har endret seg” preserve spoken qualitative feedback against
the exact item/run. Stop or change topic when practice becomes automatic. The
purpose is useful historical hooks, not accumulating taps.

## Scheduling and dependencies

New scheduled, closed-book answers use the canonical FSRS rescheduler with the
study-consolidation-v2 policy: knew → Good, missed → Again, desired retention 0.90,
learning steps 10 minutes / 20 minutes / 1 day; relearning 10 minutes / 1 day.
An initial success is due in 20 minutes; an initial miss in 10 minutes. A subsequent
successful learning step reaches one day before graduating to adaptive intervals.
The retention parameter is a scheduler target, not a measured retention rate.
Existing graduated state is preserved. A pending v1 run retains its original policy;
it is not retrospectively reinterpreted under v2.

Extra practice records answers and exposure but does not change FSRS state. Nor do
introductions, open-book/unknown-book-state responses, or the open-ended personal
connection prompt. Its self-assessment is reflection, not a fixed-answer memory grade.
Extra exposures can improve later performance: scheduled answers therefore are not
uncontaminated delayed tests. Analysis must calculate time since ANY relevant family
exposure, alongside time since the preceding scheduled test.

Prerequisites are explicit, acyclic item-ID links. An introduction, answer reveal or
completion unlocks dependent tasks; this indicates exposure, never mastery. Skipping
alone does not unlock. A selected theme includes unseen supporting prerequisites
from other themes. Selection takes due reviewed items before new ones, and at most
one item per family in a six-item batch. Extra mode prioritizes least-recently-visited
items. This is not a full conceptual mastery graph, a cross-variant shared FSRS model,
or a guaranteed minimum gap between variants across batches.

Structural cards still become due at their earliest testable position and may
retest other positions; item/family exposure must be used when interpreting that.
Durable events/audio survive network failure, but loading and advancing still need
connectivity. A native iPhone journey and reliable disconnected train use remain
separate validation gaps.

## Hypotheses and decision rules

H7: broader source-linked short practice enables sustained voluntary use without
requiring more reading. Rival: the additions are padding or too trivial. Inspect
unique targets/families visited, active time, skips and “For lett”, and ask which
prompts made later reading easier. Do not count time alone as benefit.

H8: early scheduled checks reveal fragile recall and support consolidation. Rival:
short-lag success is recognition or recent answer memory. Compare first attempts,
repeat lags, cue changes, prior family exposures and later unprompted explanation.
A high same-day success rate cannot establish three-month retention.

H9: foundations followed by applications make history easier to reason about.
Rival: the ordering only teaches the wording of these tasks. Look for explanations
of unfamiliar examples and later spontaneous, justified connections. Exposure gates
are not evidence that this mechanism worked.

Decision triggers: repeated “too easy” across a family suggests retiring redundant
cues or adding a different application; persistent confusion suggests repairing the
explanation/source before increasing repetitions; repeated detail complaints suggest
reducing scope. These are review prompts, not automated outcome thresholds.
Several features change together and practice is self-selected: this observational
phase cannot identify their individual causal effects. The pre-registered longitudinal
assessment proposal remains unimplemented; do not describe practice as a controlled
study or use the same practiced question as unseen transfer evidence.

## Reproducibility and boundaries

Every run freezes practice mode, selected topic, availability, exact item/position
payloads, design/content revision, policy, client context and executing code commit.
Every accepted event records execution commit, practice and scheduling policy. Original
client occurrence time is retained separately from server receipt time. Choice changes
are logged against the current item when one exists; the next run always records the
selection, including changes made at an empty/end screen. No lost-choice inference
should be made from absence of an item-bound feedback event.

Backend SQLite is canonical. A new revision activates the seed without rewriting
old item payloads or runs. Other curricula remain paused through study focus; their
schedules and history are untouched. Administrative activation is explicit, backed up,
and logged by revision. No synthetic captures are sent to the live service.

Validation and release identifiers are recorded below after deployment. Remaining
measurement limitations in [measurement-gaps.md](measurement-gaps.md) still apply.

## Validation before release

24 isolated Python tests pass, including immutable old content/runs, dependency
reachability/cycle rejection, future-card access in extra mode, no extra/reflection
FSRS mutation, short intervals, and idempotency. Six client durability/session tests
pass. TypeScript and whitespace checks pass. A 390 × 844 browser rendering of the
native components against isolated SQLite verifies theme selection, reveal, grade,
advance and extra mode; it does not verify a physical iPhone microphone or offline use.

Conversation freeze `1ee4a5ff8450be4a` contains 130 messages (38 Claude, 92 Codex),
including this request and progress through the pre-release checks. It excludes the
eventual final answer. [Searchable conversation archive](/Users/stian/.agents/research/petrarca-norway-study/conversations/README.md).

## Release and preservation — 13 September 2026

Code `d21ba9f0e5d239ac2e6047fa51540ada5e282b67` was committed, pushed, and
deployed through the owned-checkout wrapper around the unchanged unified deploy.
The server activation reports 76 active items and other curricula paused.
Study revision: `7cd0fa3244e5613db93a5480e38ff2559feea4aa03f350dc5f6d1f2143bcb698`.

iOS preview update `01a09a19-423a-7eb7-b8e5-1870f756e28a`, group
`d077bbb0-01a4-41a2-958e-93a598483049`, runtime `1.0.0`, published at
2026-09-13T09:29:01.754Z. The public update manifest resolves to this update and
contains the expected private API configuration; health/status/summary return HTTP
200. No private capability is stored in this document. Native installation/adoption
is not confirmed: open the app to download, leave it open briefly, then quit/reopen
to apply. The visible “Velg øving og tema” control identifies the new practice UI.

Pre-activation backup: `/opt/petrarca/data/backups/norway-intensive-before-20260913T092725Z.db`,
SHA-256 `c2917cdcdaf42c107e1339ddd90411aa4db1b89960a6106c9b5307d430b92cb0`.
All eight checked legacy tables remain byte-for-value identical. The existing five
study runs and 96 events, and prior audio/transcription rows, remain identical.
These are real observed history counts, not synthetic test sessions. Read-only
production selection confirms chronology foundations are available before their
dependents without creating a live run.

Private verification evidence and phone-sized screenshots:
[phone-practice-v2](/Users/stian/.agents/research/petrarca-norway-study/phone-practice-v2).
The local browser and fixture servers were stopped after checks.

## Interface release — 13 September 2026

The usability intervention registered after the physical-iPhone review was released
from code `e985e4ec47143186b497d3efabaf40d5a610c2d8` as iOS preview update
`01a09b5e-2f11-7e6c-85ff-0c0a01392206`, group
`3db534d1-7702-4b48-9f1d-994784c53847`, runtime `1.0.0`. It changes presentation and
interaction state only; the active content revision and scheduling policy above are
unchanged. TypeScript, 12 focused client tests and the isolated 390 × 844 journey
passed. Apply it by opening Petrarca briefly, then quitting and reopening. Device
adoption and physical-iPhone microphone behavior remain unverified.
