# Norwegian history reading study: experimental design for independent review

**Design dossier v1 · 13 September 2026 · participant: Stian Håklev**

This is the complete design account for review, including the implemented pilot,
its evidence, and the proposed longitudinal study. It is not a claim that the
entire design is already implemented or that learning gains have been observed.
The latest user request is `codex-20260912-L1438`: build a confident, connected
understanding of Norwegian history and preserve enough detailed evidence for a
comprehensive public account, including months-later retention and integration.

Start with this document, then [evidence-index.md](evidence-index.md),
[measurement-gaps.md](measurement-gaps.md), and [reviewer-brief.md](reviewer-brief.md).
The private packet includes complete exported conversations, transcripts and a
consistent runtime-data snapshot. No further research intervention, app change,
assessment schedule or publication is enacted by writing this dossier.

## 1. The two outcomes we want

**For the reader:** a good, confident overview across all twelve volumes of
*Aschehougs Norgeshistorie*: periods and approximate dates; important people,
places, events and institutions; changing everyday life; mechanisms of change;
language and identity; trade and international relationships. Confidence should
be grounded in accessible understanding and an ability to recognize uncertainty,
not just familiarity with app answers. Stian also wants modest but useful knowledge
of specific terms: enough to recognize them, understand their rough meaning and
read another historical text with less effort.

**For the experiment:** an evidence-rich account of what he did, how much time it
cost, how his explanations and questions changed, and what remained accessible
months later. It should describe unsuccessful designs and missing observations
as carefully as successful episodes. A useful personal outcome and a persuasive
causal research claim are different achievements.

The model for the eventual writing is Stian's [Petrarca: An Intelligent Companion
for the Self-Taught Reader](https://networkedthought.substack.com/p/petrarca-an-intelligent-companion)
(7 April 2026). That essay connects personal experience, product design and the
ambition of tracking richer knowledge over time; it explicitly leaves trustworthy
evidence of deep learning open. This study should supply longitudinal evidence
rather than recycle its illustrative app scenarios as measured results.

The original aspiration to know roughly what a university course would provide
comes from Claude conversation L11. It is an aspiration, not an established
benchmark, syllabus mapping or certification. Before using that comparison in a
blog, define an independently reviewed scope and assessment standard.

## 2. What kind of study this is

A prospective, adaptive, single-person observational study of a reading workflow
and an evolving learning app. The system being studied includes reading, continuous
spoken notes, conversations with AI, selected explanations and phone practice.
Stian is participant, co-designer and eventual author. The assistant helps select
and present material, interpret data and build the system; those roles can bias
both intervention and analysis.

The pilot has no random assignment, untreated baseline period, independent outcome
scoring or validated global knowledge measure. A later improvement cannot, by
itself, tell us what Petrarca caused beyond reading, speaking, prior knowledge,
additional sources and repeated testing. We can describe trajectories and mechanisms
plausibly illustrated by individual episodes. We cannot yet estimate a causal
percentage improvement, claim superiority over another method or generalize to
other people.

**Status vocabulary throughout the record:**

- **User requirement:** an explicit goal, preference or clarification.
- **Implemented:** verified in the named released code or stored evidence.
- **Observed:** an actual recording/event/response with conditions and provenance.
- **Proposed:** a design choice for review, not a completed implementation or an
  agreement inferred from silence.
- **Unknown:** data missing, attribution unresolved or coverage not verified.

## 3. How the design developed with Stian

The full wording is preserved in the linked conversation exports. This chronology
is an interpretation index, not a substitute for those conversations.

| Source | Contribution and current consequence |
|---|---|
| Claude L11, 10 Sep | Twelve used volumes; connected overview, international relations and differences in everyday life across centuries; use Petrarca while reading quickly |
| Claude assistant L158 onward | Proposed building a broad curriculum/scaffold first; estimated burdens and confident predictions were proposals, not findings. Four later Norway domains were generated; their existence does not establish content quality or learner knowledge |
| Codex L9–L240, 12 Sep | Recover Claude context and #journal audio, resolve Tana access, assess poor Norwegian transcription, retain original audio and redo ASR where useful |
| Codex L317 | Explicit self-study experiment; all twelve books; timing; selective retention of important detail; chronology/world connections, mechanisms, language and copper trade; a repeatable audio-to-learning process |
| Codex L385 | Continuous recording while reading with the book open. Chapter-end capture was abandoned because chapters were too fact-dense. Preserve this actual method |
| Codex L634 and assistant L653 | Requested analysis of baseline and notes; an assistant inferred integration from summary-shaped speech |
| Codex L663 | Corrected that inference: speech often quotes book sentences, including the book's summaries. Also made term familiarity and complete project documentation explicit |
| C001 | Withdraw attribution of farming s009 as Stian's synthesis. Original claim remains visible with the correction |
| Codex L816–L842 | Consolidate while continuing to read, using the existing phone app away from the keyboard. Earlier chat-delivered probes have no responses and are superseded |
| Codex L920 | Implement a bounded Norway pilot and suspend other cards until this workflow works; eventual goal remains broader curricula |
| Codex L974 | Capture detailed app/source/response analytics and version research changes for rapid iteration |
| Codex L1438, current request | Make long-term confident understanding and an evidence-rich blog explicit joint outcomes; compare pre/post dumps and months-later performance; prepare a full account for another agent's review |

No forum publication was verified. The archive covers the two identified local
sessions, not every conversation on every device. Technical access discussion is
included; hidden reasoning, credentials/tool payloads, environment instructions
and image bytes are excluded. See the evidence index for discovery scope and cutoff.

## 4. Reading method and evidence already in hand

Stian reads physical books while Tana records continuously. He speaks Norwegian
mostly, sometimes English. Some utterances are quotations, some paraphrases,
questions or possible interpretations; authorship cannot be recovered reliably
from fluent wording alone. He skips substantial detail intentionally. Completion
must therefore distinguish reaching the end of a volume from close reading of
every page or retaining every fact.

| Recording | File duration | Page checkpoints | Evidence role |
|---|---:|---|---|
| English pre-reading baseline | 8:50.100 | None | Unstructured account of prior ideas, uncertainty and questions about the first volume's era |
| Hunters and gatherers | 39:32.904 | 13 → 33 → 51 → 59 | Open-book reading and spoken notes |
| Early farming | 29:25.080 | 58 → 70 → 90 | Open-book reading and spoken notes |
| Bronze transition | 40:05.376 | 90 → 109 → 111 → 132 → 146 | Open-book reading and spoken notes |

The three reading files total **1:49:03.360**. Including the baseline gives
**1:57:53.460 of recorded audio**, not total project effort. Overlapping checkpoints
and unknown skips prevent an exact unique-page count. Tana node creation times
are metadata times, not proven recording start times.

The Norwegian batch has 189 timed ASR segments and 5,190 words in the saved ASR
version. Eleven editorial interventions and fifteen flagged passages are auditable;
there is no audio-verified gold transcript or defensible word-error-rate estimate.
The later attribution overlay marks all 189 segments unresolved as to book/reader
origin. Earlier candidate function labels must be interpreted under that correction.

The initial English dump contains interests and tentative models, not simply
zero knowledge: prehistoric evidence, wider European connections, metallurgy and
trade, language, Norway/Sweden identity, and questions about meaningful detail.
Its statements are unscored and may be mistaken. Do not correct the baseline to
make a cleaner starting point or count omission as ignorance.

This baseline is **not a systematic assessment of all twelve volumes**. It cannot
serve as an item-by-item zero score for unread later eras. Explanations and answers
have already appeared in AI conversations, even though the phone snapshot below
has no study sessions. A new test now is a first post-reading observation, not a
pristine pre-exposure baseline.

## 5. Current implementation and its boundaries

The phone pilot was activated on 13 September at approximately 06:25 UTC:

- Backend/content commit `c6db8f317bcf16eee3343aea658610be9a6da4a7`.
- Design `norway-phone-pilot-v1`; seed `pilot-v1`.
- Study revision `9c9a656aaa2a85f5da0b4e1b5631969f3f1a40875e1ff7f2f06053223347b38e`.
- iOS preview update `01a09970-8e48-74db-938d-76a5ac8cb74f`, runtime `1.0.0`.

There are six term introductions; one each of sequence, aspect, causal and
synchronic cards; and three spoken prompts. Review and Voice select separately,
up to six items, due-first then curated order, with a ten-minute cooldown after
completion/introduction/skip. Terms and the new Mycenaean time connection start
as exposure-only introductions. Definitions and selected claims have references.
Source/target IDs allow different formats for the same subject to be linked.

Existing FSRS schedules explicitly tested positions only when the user declares
the book closed. Visible anchors and open/unknown-context responses receive no
memory credit. Binary grades are self-reported; no independent assessor has
validated them. The old card selection/grading paths are paused; eight inspected
legacy tables matched a pre-activation backup exactly. The pilot is phone/tap/
voice based, not a fully hands-free spoken-question experience.

The **runtime snapshot at 06:51:08 UTC on 13 September** contains 13 items, 20
positions, four sources and one revision; **zero runs, events, app audio responses
or app transcriptions**. This is a dated observation, not a claim that the user
will never have interacted by the time the packet is reviewed. It says nothing
about unlogged app activity or reading outside this study. The microphone/upload
path on the physical iPhone still needs validation through a real session.

The first pilot implements practice and evidence collection. It does not implement
a broad post-volume assessment, longitudinal scoring rubric, independent retention
cohort, follow-up scheduler, complete time accounting or an analysis dashboard
of changing understanding. See [analytics-v1.md](analytics-v1.md) for the release
contract and [measurement-gaps.md](measurement-gaps.md) for corrections to overly
broad interpretations of that contract.

## 6. Outcomes and how we propose to observe them

Avoid collapsing these into one unvalidated "knowledge score."

| Outcome | Proposed observation | Main interpretation limit |
|---|---|---|
| Broad overview | Unprompted period narrative, then a fixed set of broad prompts | Prompting changes what is retrieved; omitted topics remain unobserved |
| Chronological orientation | Period order, approximate ranges, placement of selected anchors | Exact-year performance differs from useful period orientation |
| International integration | Locate a Norwegian development beside a familiar external event; explain a justified relationship | Simultaneity is not causation or evidence of direct contact |
| Mechanisms of change | Explain one transition, contrast regions/periods, distinguish an explanation from an established fact | Reproducing a supplied causal chain is a practiced task, not automatically transfer |
| Concept familiarity | Recognize term, give rough meaning, interpret it in a new historical sentence | Recognition, meaning and exact naming must be measured separately |
| Practical reading benefit | Interpret an unfamiliar passage using earlier knowledge; note lookup needs and perceived effort | Passage length/difficulty and previous exposure affect performance |
| Calibrated confidence | Confidence stated before feedback; compare to independently coded adequacy where possible | Current binary self-grade is not a confidence instrument |
| Evolving understanding | Compare actual explanations, uncertainty, qualified inferences and revised questions | Longer or more fluent speech is not necessarily deeper understanding |
| Sustainable cost | Reading-session time, app foreground/practice time, interruptions and burden reports | Device activity is not direct measurement of attention |

**Proposed rubrics, to freeze before scoring:** separate axes for factual adequacy,
chronological placement, explanatory structure, warranted connections, appropriate
uncertainty and evidence/source discrimination. A simple 0–3 scale can mean absent
under that cue, fragmentary, adequate, and coherent/transferable, but requires
axis-specific examples. "Not elicited," "inaudible," "not yet read," and "not
scorable" are separate missingness codes, never zero performance by default.

Keep raw propositions, supporting audio spans, rubric judgments and scorer
confidence. Record actual misconceptions and later revisions as linked claims,
not silent substitutions. Historical disagreement or an outdated book account
needs an attributed reference judgment; the assistant's first answer is not the
gold standard. Self-reported understanding stays separate from assessor inference.

For concept recognition, preserve whether familiarity was reported before meaning
or examples appeared. For accuracy/calibration, obtain a pre-feedback confidence
rating only if the added burden is worthwhile; e.g. low/medium/high or a consistently
anchored numerical scale. Do not manufacture confidence retrospectively from "knew."

## 7. Proposed assessment sequence and long-term follow-up

**This timetable is a proposal for review; no reminders or appointments have been
created.** Delays are anchored to actual volume completion, not today's date.
Record scheduled and actual dates, elapsed days and reasons for missed assessments.

| Point | Proposed task / burden | What it supplies |
|---|---|---|
| Now, before further targeted feedback where possible | First post-reading sample about pages already traversed; roughly 5–10 min | Initial assessment after reading and some conversational exposure; cannot repair missing earlier baselines |
| Before a new volume or unfamiliar major era | Brief broad unaided dump and questions, roughly 3–5 min | Prospective domain baseline, labelled with prior exposures |
| Natural reading milestone | Optional 30–90-second prompt or reflection | Low-burden process data; not mandatory chapter-end capture |
| End of a volume | Approximately 8–12 min: unaided account, fixed core prompts, selected new-context task | Comparable post-reading sample with an explicit stopping rule |
| +1 month | Approximately 5–10 min: parallel core prompts and fresh-context item | Shorter-term delayed accessibility |
| +3 months | Same outcome domains, controlled cue sequence, new variants | Medium-term maintenance and integration |
| +6 months | Same design, plus an example from later reading if available | Longer-term accessibility under actual continuing exposure |
| End of all twelve volumes | Bounded cross-period synthesis and world-history connections | Whole-project outcome; not simply sum of card scores |
| Whole-project +3/+6 months | Repeat comparable overview/transfer tasks | Whether the complete framework remains usable |

Avoid multiplying every row into an exhausting obligation. A review decision is
needed on follow-up sampling: every volume versus predetermined sentinel volumes
(e.g. 1, 6 and 12), or a rotating sample covering all eras. If this reduces burden,
choose the sampling rule prospectively; do not later select only well-retained
volumes. End-of-project assessments can replace coincident volume follow-ups,
with that deviation recorded. An optional +12-month check is not a commitment.

**Within a formal assessment:** first unprompted recall; then neutral, prewritten
cues; then recognition/application items; then feedback. Record the transition
and assistance for every stage. Do not show the earlier dump, ideal answer or a
new explanatory map before the unaided portion. Keep ordinary practice and formal
assessment distinguishable in the data and, where feasible, in the interface.
The current voice practice shows an answer after a saved recording; that is useful
practice, but it is not the whole proposed assessment workflow.

Use a stable common core plus logged parallel forms. The common core supports
comparison; new formulations help detect dependence on a memorized cue. Repeat
some exact questions only if that repetition is part of the stated measurement.
Log any test as an additional learning exposure. We cannot assume tests leave
subsequent memory unchanged.

The baseline is English and reading captures are primarily Norwegian. Keep the
original language and, where practical, comparable assessment language within a
pair. Permit natural switching but record it. Translation is a separately versioned
view, not replacement evidence. Do not use word count or English/Norwegian fluency
as an implicit knowledge score.

## 8. What months-later "retention" should mean here

Continuing to read later volumes, seeing related cards and discussing history
will expose earlier material again. A test after six calendar months therefore
measures accessibility **with the observed maintenance and further learning**.
It does not measure six months of unassisted decay.

For each tested target retain: time since first recorded encounter, last source
encounter, last answer reveal, last attempted retrieval, last feedback, relevant
external reading and last formal assessment. Report unknown encounters explicitly.
A cross-period connection learned later may be a new integration outcome, not
retention of something already present in the initial dump.

A future contrast between maintenance schedules or formats is possible, but would
need a separately registered assignment rule, comparable targets, common outcomes,
carryover accounting and participant agreement if it withholds useful practice.
Selection of easier topics into one format will confound a naive comparison.
For now, inspect usefulness and trajectories descriptively. Do not label rapid
interface iterations as randomized A/B experiments.

## 9. Time measurement: the exact quantities and the unknowns

We should satisfy the desire for detailed time data without naming a proxy more
precisely than the evidence allows. Define quantities before producing totals.

| Quantity | Current status | Proposed operational definition |
|---|---|---|
| Recorded reading-session duration | Exact to audio-file resolution for four archived files | Sum nonduplicate reading recording segments, with preserved file hashes |
| Reading time excluding speech and breaks | Unknown for unmarked intervals | Prospective activity markers; report marked components and unresolved time separately |
| App foreground time | Lifecycle events exist, but reliable total not implemented | Union of visibility intervals per device/visit, with crash/missing-end handling |
| Active app learning time | Not directly observed | Separate foreground, explicit pause/idle, response recording, feedback and navigation; label any idle-threshold estimate as an estimate |
| Prompt deliberation time | Partly recoverable from event history | First eligible prompt visibility to first reveal/response, subtract only observed background intervals |
| Answer-reading time | Partly observable | Reveal to leaving/continuing, again with visibility intervals; not all of it is attention |
| Total personal project effort | Incomplete | Non-overlapping reading/practice/assessment/discussion/admin intervals where alignment is known |
| Agent/computation time and cost | Not systematically registered for this study | Separate infrastructure/process cost ledger; never call agent runtime Stian's learning time |

Keep session envelope, speaking, marked break and unresolved intervals. Voice
activity detection can estimate speech intervals, with algorithm/version/error
recorded; **silence is not proof of reading**. Continuous recording remains Stian's
chosen method. Minimal spoken markers of volume/page, pause/resume, end and major
skips are proposed aids, not a newly imposed annotation ritual.

Prospective app instrumentation should add stable device-install, app-boot, visit,
encounter and recording-attempt IDs; client sequence numbers; wall-clock and
monotonic timestamps; lifecycle/pause/heartbeat events; and the effective software
version on each event. Record clock anomalies. A heartbeat only bounds the last
observed foreground interval; it does not prove attention. A configurable idle
rule should be sensitivity-tested because thinking or listening can be motionless.

Never sum each event's elapsed-since-appearance value: these overlap. The current
`reveal_time_ms` field in structural completion results is time **after reveal
until completion**, not time spent retrieving before reveal. It also does not
itself remove background time. This is a concrete analysis hazard.

If reading audio and app use overlap, use interval unions only when their clocks
are aligned with known uncertainty. Do not silently double-count a recorded
reading session and the app activity happening inside it. Without alignment,
report separate totals and possible overlap, not a spurious exact combined figure.
For timing by chapter, require page/section markers or explicit interval annotations;
page advance alone is not a reliable denominator for reading speed.

## 10. Data and provenance contract

The intended relationship is:

`project → volume/edition → reading session → recording → transcript version → segment → target → item/version → encounter/response → assessment/judgment`

Design versions, deployments, assignment rules and conversation decisions are
linked across that chain. This is the desired model, not a claim that every table
already exists. Current schema and the exported runtime snapshot are in the packet.

**Implemented:** audio/source hashes and Tana IDs; source durations/page checkpoints;
immutable card content with target/source references; frozen run snapshots; durable
client events with original occurrence and server receipt times; app/OTA context;
original purpose-labelled response audio; append-only ASR attempts; FSRS positions;
and a revision ledger. Duplicate grades and uploads are guarded. Raw audio is
retained; ASR does not automatically create knowledge grades.

**Required additions or formalization for longitudinal analysis:**

- Bibliography/edition, volume/chapter registry, reading-session/segment IDs,
  explicit coverage/skip/reread and timing-marker uncertainty.
- Assessment occasion and form IDs, scheduled/actual delay, cue order, intended
  outcome, assistance, language, confidence and stopping conditions.
- Recording-attempt ID linking start/stop/upload/retranscription to a returned
  server audio ID; current client upload ID is not the server audio ID. With
  several recordings for the same run/item/purpose, exact attempt linkage is weak.
- Versioned rubric, scoring model/prompt/settings, scorer and adjudication records;
  supporting response spans; missingness codes; independent ratings where used.
- A target identity/lineage registry for merges/splits/rewordings. Different intended
  depths must not be collapsed just because a factual subject is shared.
- Effective backend/analysis policy at grading time, not only the code version
  stored when a run was selected. Old runs can survive new deployments.
- Supplementary source/exposure and wondering lifecycle records: raised, researched,
  answer encountered, unresolved, explanation revised, revisited later.
- Append-only design-change/deviation/decision records linked to deployments and
  affected targets, plus versioned analysis exports and reproducible derivations.

Retain raw, cleaned and interpreted evidence as separate layers. Preserve uncertain
negations, dates and names; distinguish ASR error, spoken error, book claim and
historical disagreement. Model choice, vocabulary hints and transcript edits can
change the apparent meaning of a response. Store original audio, alternative ASR,
edit decisions and who verified them. Current mobile ASR text is not token-timed
like the original reading batch; that limits span-level coding until extended.

## 11. Analysis plan for changing knowledge and understanding

**Before looking at scored outcomes**, freeze the core outcome definitions, sampling
rule, rubric and what counts as comparable. Keep room for exploratory qualitative
findings, clearly labelled after the fact.

Build paired displays with the original wording and dates: initial question/model,
source encounters, subsequent independent explanation, later revisions, and a
delayed response. Use a stable target ledger and cited audio spans. A meaningful
change might be replacing a single national story with regionally qualified
explanations, or distinguishing exchange evidence from certainty about a route.
These are examples of coding targets, not findings about Stian already established.

For quantitative summaries report denominators: targets actually probed, scorable
responses, assistance conditions, delays, intervening exposures and missing data.
Never treat untested curriculum nodes as failed recall. Report distributions and
trajectories separately for chronology, concept meaning, explanation and transfer.
Self-grades are descriptive practice signals. Do not use FSRS stability as a direct
measurement of broad comprehension or independent proof of retention.

An independent reviewer/scorer should code a predetermined subset with dates/order
masked where feasible. Agreement, disagreements and adjudication should be retained.
If AI helps score, keep its exact rubric/model/prompt, evidence citations and human
checks. The AI that selected facts and wrote answers should not silently be the
sole authority validating those same answers. Correctness references should retain
historical uncertainty. Scores can be revised with a new version, never overwritten.

Track representative unsuccessful episodes, abandoned formats and topics that were
not selected. Avoid choosing only eloquent before/after passages for the blog.
Include raw excerpts supporting both progress and persistent uncertainty. A changed
question may be valuable even without more correct facts; an increased fact count
may simply reflect longer speaking or more prompting.

## 12. Rapid iteration without erasing the experimental conditions

Separate **practice design**, which can change rapidly to remain useful, from a
small **measurement core**, which should remain comparable. Proposed iteration
cycle: inspect the first real session for data integrity; review the first few
sessions for usefulness/friction; make one meaningful change when evidence warrants
it; record its rationale before activation. No fixed cadence or quota is imposed.

Each change record should contain ID/date, triggering observation, user request or
assistant hypothesis, old/new behavior, affected targets/forms, predicted observable
effect, decision-maker, code/content/design versions, actual activation, rollback
and deviations. Technical fixes also matter if they change timing, exposure or
which responses can be recorded. Preserve old versions and stale-run behavior.

Add a phase label to analysis. Reading progression, target difficulty, familiarity
with the app and evolving content are competing explanations for phase differences.
Changing many features at once may be sensible product work, but makes attribution
harder; say so. If a later formal comparison is desired, register it separately.

**Proposed reasons to simplify or stop a format:** it causes reading avoidance,
repeatedly obscures the question, creates disproportionate detail burden, or cannot
preserve interpretable responses. These are reviewable criteria, not measured
failures already observed. The broader project can continue while a format stops.

## 13. Missing data, reliability and preservation

Missing recording, failed upload, off-device activity, unread material, a skipped
question, no recording permission and an unscorable answer are different events.
Preserve missingness reason and uncertainty. No response is not automatically a
memory failure. An absent log is not proof an activity did not happen.

Run integrity checks for orphaned source/response references, duplicate IDs, audio
hashes, unexpected clock jumps, missing lifecycle ends, unresolved uploads, empty
or failed ASR, stale configuration and snapshot coverage. Validate with the first
real iPhone session, not fabricated production responses. Retry tests have passed
in isolation; real-device adoption remains unobserved in the frozen snapshot.

Raw reading evidence and conversation exports currently live on this Mac. Runtime
SQLite and app audio live on the server. A pre-activation SQLite backup exists,
but a verified, comprehensive off-device backup and restore drill for audio,
transcript versions, conversations and analysis artifacts has **not** been shown.
A database-only backup or export is not a backup of audio bytes.

Before accumulating months of data, create a documented backup inventory with
checksums, independent copies, recovery location and a tested restore sample.
Do not put credentials, signed audio download tokens or server capabilities in
review packets or blog assets. The text packet retains safe source links and hashes;
large original audio stays in the linked private archive. Publication should use
reviewed excerpts and appropriately summarized book content; private project
capture does not automatically authorize publishing every conversation or recording.

## 14. Eventual blog and reproducibility package

Proposed article structure: original problem and starting knowledge; chosen books
and real reading method; the evolving product/design; a dated effort timeline;
carefully paired explanations; chronology/concept/transfer trajectories; months-later
results with maintenance exposure; failures and course corrections; limitations;
and the reusable protocol/code/data dictionary.

Plan the figures now so the required inputs can be retained:

| Planned exhibit | Necessary evidence |
|---|---|
| Reading by volume/chapter over calendar time | File/session markers, page coverage, skipped/reread flags, clock uncertainty |
| Personal time budget | Separate reading, practice, formal assessment, discussion and overhead; overlap handling |
| Design/deployment timeline | Prospective change ledger, effective dates and actual client/backend versions |
| Pre/post/delayed examples | Original audio/transcript spans, cue/assistance/order, rubric and scoring versions |
| Knowledge profile over time | Stable outcome domains and tested denominator, not only generated knowledge graphs |
| Retention under maintenance | Actual delays plus review/feedback/external exposure history |
| Concept use in new reading | Previously unseen passage/task version, lookup/assistance and interpretation evidence |
| Missingness and feasibility | Skips, failed capture, incomplete sessions, burden and abandoned designs |
| Curiosity and revised models | Linked wondering → encounter → explanation revision chains, including unresolved ones |

Archive machine-readable tables, derivation scripts and checksummed analysis
snapshots behind every published number. Store a claim-to-evidence table for the
article: claim, figure/table, query/analysis revision, inclusion rules, supporting
observations, caveats and publication approval. Distinguish data recorded at the
time from later recollection. Label illustrative scenarios as illustrations.

This dossier is preparation for that article, not a draft announcing results.
Writing or reviewing it does not authorize sending the packet to other people,
publishing private material, or scheduling follow-up messages.

## 15. Decisions the independent reviewer should help settle first

1. Can the timing model deliver honest operational totals with tolerable burden,
   and what must be added before the next substantial reading sessions?
2. What is the smallest stable assessment core that tests overview, warranted
   world connections, term meaning and transfer rather than practiced answers?
3. How should the incomplete English baseline and already-exposed first-volume
   material be handled without inventing a before score?
4. Which monthly follow-ups are worth the burden, and how should their targets and
   maintenance exposure be sampled and recorded?
5. Which event/version/recording identifiers and backup gaps are urgent before
   interpreting outcomes or changing the design again?
6. Which claims could this single-person adaptive design honestly support in a
   public account, and what stronger comparison would require a separate study?

The reviewer should return prioritized findings with source/code pointers and
concrete repairs. Ask for design critique first, not a replacement curriculum or
an unsolicited app rewrite. [reviewer-brief.md](reviewer-brief.md) is ready to paste.
