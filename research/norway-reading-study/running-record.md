## 22 September 2026 — bounded readings published

GPT-5.6 Sol implemented and Astra reviewed the accepted one-degree reading feature. **Valg → Det du lurte på** contains three source-checked explanations (bergkunst techniques, 1177 BCE and karveskurd) with six optional quiz targets, initially unselected. There are no generated descendants or automatic quiz obligations. Returning restores the same practice card; using reading help prevents scheduling credit for the assisted answer.

The study still has **99 items / 106 positions / 10 sources / 14 runs / 355 events**. All prior exported table hashes were preserved exactly; publication added only reading definitions. Live private API, import idempotence, client/server tests and isolated browser checks passed. Server/iOS release is `4f5b009`; EAS group `ece28250-1624-4d49-8ab9-51713e45e90a`. Device adoption remains unconfirmed. See [release evidence](readings-v1.md). The prior capture-mode correction remains pending and the older proposal/status statements below are historical.

---

## 21 September 2026 — six new sources, 23 new questions

Tag-based Tana discovery and GPT-5.6 Sol ingestion are complete, with Astra review.
The study now has **99 items / 106 positions / 10 sources**. All original 76 items,
83 scheduling rows, 14 frozen runs and 355 learner events were preserved exactly.
No new app code or mobile release. See [batch report](intake-20260921.md) for exact
draft hashes, factual review, publication retries, before/after exports and source
metadata limitations. The new items follow due and older unseen items in selection.

[Bounded short readings](bounded-readings-20260921.md) is the current design
proposal: one explanation rooted in original voice material, no generated descendants,
and explicitly selected quiz targets. Seven wonderings are preserved privately.
This feature is not yet implemented. A metadata correction sidecar qualifies the
new reflection as explicit informal recall with unknown aid conditions; the runtime
capture-mode label still overstates unaided status and needs an audited correction
path. Do not use it as proof of unaided assessment or mastery.

The older record below is preserved as the September 14 snapshot.

---

# Norway study running record

Updated 14 September 2026 after “keep track of everything” (`codex-20260913-review-followup-L1289`). Start here for status; use [study-index.md](study-index.md) for the complete evidence map and [decisions.md](decisions.md) for dated reasoning and corrections.

## Participant decisions

- Purpose: connected historical understanding, approximate chronology, important mechanisms and useful familiarity with terms across twelve volumes.
- Normal reading recordings are open-book. They may quote the book, including its summaries; record exposure and retain unresolved authorship rather than infer independent synthesis. Explicit recall and practice answers are closed-book. Do not ask the mode each session (D017; source L1036).
- Expected depth must be explicit. Who, when, where and what happened are distinct aspects; success on one does not imply the others. Use old Petrarca's separate positions where useful, without turning every detail into a requirement (D018; L1034).
- Keep practice focused on the current question. Preserve feedback, real observations, interventions, corrections and releases as part of the experiment (L889, L1289).
- App updates should show a small Alif-style notice when a new version has loaded (L719).

Source IDs above use the prefix `codex-20260913-review-followup-`. The precise texts are preserved in the private conversation freeze below.

## Delivered

| Area | Current state | Evidence |
|---|---|---|
| Practice content | 76 items with separate position scheduling, introductions and short v2 consolidation | [Intensive v2](intensive-v2.md) |
| Overview assessment | Narrative plus five cues, confidence and frozen rubric; no automatic knowledge grade or FSRS changes | [Assessment release](assessment-release-v1.md) |
| Learning aids | Ard/åkerrein diagrams, application examples and parallel timeline | [Learning aids](learning-aids-v1.md) |
| Source intake and monthly sampling | Operator tooling implemented; not an automatic collector | [Intake and backup](intake-v1.md) |
| Update notification | Small once-per-loaded-update toast; released in cce54ff | Prior iOS update 01a09bca-8649-71ba-a896-a924ea5fa03f |
| Focused practice UI | Direct card opening, compact progress, options hidden under Valg, answer state retained on return; no book-mode question | [Practice audit/release](practice-audit-20260914.md), code 4eaebb0 |
| Exposure correction | Distinguish card presentation from definition presentation; hidden options panel does not count as card display | visible-card-v2, 14 focused tests and isolated browser check |

Current mobile release: code **4eaebb0c5d83c02497f0b8bc678dae1e01044e78**, iOS update **01a09ede-7cd8-7b26-b408-bf2881a60a82**, EAS group **095af5f9-dd34-4fba-9b68-0bcadbe380a6**, preview/runtime 1.0.0. Published successfully; post-deploy API health/status/summary verified. Physical-device adoption of this latest release remains unverified. Documentation-only commits after it are not new mobile releases.

## Observed learning data

Immutable export through 14 September 09:02 Oslo: **239 events, 20 completed cards across 17 distinct items, 25 graded parts (23 knew, 2 missed), 15 introductions**. Stored counts, grades and FSRS states reconcile. These are self-reports, not independently scored knowledge. No study response audio or overview assessment exists at that cutoff; reading-source audio is separate.

Traktbegerkulturen: term familiarity reported; one Oslofjord/material-evidence connection missed; dates not separately tested. Mikrolitt's context question is the other miss. Do not describe either as ignorance of the whole topic.

Historical exposure events can precede actual content display. Secondary lifecycle logging is incomplete, elapsed timing is not active-learning time, and six early completions retain v1 long schedules. Preserve those qualifications. Full private [audit](/Users/stian/.agents/research/petrarca-norway-study/audit-20260914/audit.md) and immutable export remain unchanged.

## Open work

| Work | Status / next action | Dependency |
|---|---|---|
| Separate culture aspects | Specify selected identity, rough time, place and significance targets; source-check and version new positions. Do not transfer old grades to untested aspects. | Agent content/design work; no new user permission needed for routine continuation |
| Real overview observation | Fortell → Valg → Fortell oversikten; short unprepared account from memory, then cues. No exhaustive chapter recital or separate Tana capture required. | Genuine participant response; never fabricate a baseline before app exposure |
| Real phone audio/intake verification | Verify first genuine recall audio and next new reading source through the implemented paths | New participant recording |
| Measurement limits | Define durable encounter identity and active timing before claiming accurate exposure duration; preserve known old-data limits | Further implementation, not solved by the display fix |
| Monthly follow-up | Tool waits for a completed-volume assessment; dedicated one-cue phone delivery and automatic reminders remain absent | Completed volume; future implementation |
| Automatic source intake | No recurring collector configured; operator can discover and ingest actual new recordings | Future implementation; do not promise a 24-hour service |
| Independent raw-audio backup | Original archives verified locally; off-device destination still unresolved | Destination decision previously requested, not requested again here |

## Preserved evidence and maintenance

Conversation freeze **4ea49a84dd64420c** contains **189 user/assistant text records** across the initial Claude session, original archived Codex task and this follow-up task. It includes the preceding completion report, all recent participant corrections and the current tracking request; it excludes this turn's eventual final answer. The original task's moved archive path has been repaired in the private registry. [Conversation archive](/Users/stian/.agents/research/petrarca-norway-study/conversations/README.md).

The pasted external review and original phone screenshot have unchanged private copies with SHA-256 hashes under `/Users/stian/.agents/research/petrarca-norway-study/attachments/20260914/manifest.json`. External-review recommendations remain attributed input; user instructions and later decisions govern implementation. Prior freezes, recordings, transcripts, original claims and corrections are retained.

At each study continuation: update this status, append dated decisions/corrections, register interventions before changes, refresh the registered conversation archive, and record code/content/data cutoffs plus test/deployment evidence. Distinguish proposed, implemented, deployed, observed and unresolved. Do not silently promote absence into a negative knowledge score.

This is a maintained record and a handoff procedure. It does not imply an unattended recorder for every future task or coverage of unregistered conversations, other devices, reasoning/tool payloads or image bytes inside the text archive. Referenced supplied images are preserved separately above.
