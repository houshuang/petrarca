# Decisions, corrections and open questions

Append dated entries. Status matters: user decisions govern the study; assistant
proposals remain proposals until tried or accepted. References resolve through
[study-index.md](study-index.md) and the private conversation archive.

| ID | Date | Kind / status | Decision or interpretation | Evidence |
|---|---|---|---|---|
| D001 | 2026-09-10 | User goal, active | Twelve-volume Norwegian-history overview | Claude L11 |
| P001 | 2026-09-10/12 | Earlier method, superseded | Capture after chapters with book closed | Earlier conversation; superseded by D003 |
| D002 | 2026-09-12 | User goals, active | Track time; prioritize periods/world comparisons, mechanisms, language, trade; select important detail and major debates | Codex L317 |
| D003 | 2026-09-12 | User method, active | Continuous recording while reading with book open; chapter-end capture loses too much detail | Codex L385 |
| P002 | 2026-09-12 | Assistant proposal, provisional | Twelve initial topic-level targets and lightweight later recall | First-batch artifacts; these are not twelve atomic memory obligations |
| C001 | 2026-09-13 | Correction, active | Withdraw claim that farming s009 demonstrates the reader's own compression/integration; it may quote the book's summary | Codex L653 corrected by L663 |
| D004 | 2026-09-13 | User clarification, active | Spoken notes often quote book sentences, including summaries; surface wording cannot identify who synthesized them | Codex L663 |
| D005 | 2026-09-13 | User goal, active | Familiarity with concepts and specific terms should reduce effort and provide connections in future historical reading | Codex L663 |
| D006 | 2026-09-13 | User requirement, active | Document and index experiment conversations as well as recordings and decisions | Codex L663 |
| P003 | 2026-09-13 | Assistant implementation policy | Unverified open-book passages default to unresolved book/reader origin and exposure-only learning evidence | Implements D004; no claim every passage is a quotation |
| P004 | 2026-09-13 | Assistant design proposal | Track recognition, rough meaning, contextual interpretation and optional explanation separately | Implements D005; not a deployed scoring model |

## D007 and C002: phone delivery, 13 September

**D007 — User requirement, active:** Use Petrarca's existing mechanisms away from
the keyboard. Source: `codex-20260912-L842`. Native Review and Voice are the main delivery
surfaces for this study. Chat prompts are not the required testing interface.

**C002 — Assistant framing corrected:** The separate desktop Companion is narrower
than the native app. Its selection constraints do not describe the full set of
mobile mechanisms. Native cards, guided recall and other voice tools exist; the
mobile API is healthy. The gap is the study content/introduction/scoping and
provenance path, not absence of the original mobile mechanisms. See
[mobile-workflow.md](mobile-workflow.md) for the verified audit and integration work.

The three earlier chat prompts have no recorded response or grade. Preserve the
questions as possible app prompts, with delivery marked superseded.

## C001: exact scope of the correction

The original assistant response described farming s009 (03:26–04:03) as "explicitly
your attempt to say what the details amount to." The transcript alone does not
support that attribution. It could be quotation, paraphrase, reader synthesis or
a mixture. Preserve the passage as a useful source summary; do not treat it as
evidence that Stian independently integrated or retained its content.

Apply the same restraint to other apparent causal explanations, connections and
questions. First-person markers may suggest a reader comment but do not prove it.
Confirmed original open-book interpretation would still not establish delayed
unaided recall. The earlier analysis is not erased; the archive and corrected
analysis document identify this claim as withdrawn.

## Open questions

- Q001: How many terms merit light familiarity versus deeper explanation? Learn
  from later reading encounters and burden; do not impose one depth on all terms.
- Q002: Which recordings contain identifiable quotations? Book-page comparison
  can establish text overlap when needed. No compulsory speech-labeling ritual.
- Q003: How much time is spent reading, speaking and taking breaks? File duration
  is known; silence is not proof of active reading and missing markers stay missing.
- Q004: What should enter Petrarca first? Concepts/terms now accompany verified
  chronology and mechanisms in the introduction-path design; no production import yet.
- Q005: Are there relevant Claude web or forum discussions not in the local logs?
  Coverage remains explicit until independently located.

### D008 — Isolate the phone pilot; preserve other curricula (13 September)

User source `codex-20260912-L920`: proceed with implementation and temporarily
suspend all other cards while finding what works here. Implement as a reversible
global focus gate, preserving old cards, history and due dates. Native Review,
Voice and Stats show the study; old selection/grading routes reject activity
while focus is active. Broader curricula remain the eventual goal.

### D009 — Detailed, versioned research observations (13 September)

User source `codex-20260912-L974`: rapidly iterate, correlate reading recordings
and wonderings with mobile interactions, and retain design changes for later
analysis of interaction and changing understanding. Adopt immutable session
snapshots, source/target links, exact app/backend/content/design versions, durable
events and purpose-labelled original audio. Keep changes prospective in the
experiment log and interpretations revisable. The measurement contract and
limitations are in [analytics-v1.md](analytics-v1.md). No randomized comparison or
automatic evaluation of comprehension has been authorized by these observations.

### D010 — Longitudinal outcomes and a reviewable public account (13 September)

User source `codex-20260912-L1438`: aim for a confident, connected overview of
Norwegian history and a comprehensive blog like the original Petrarca essay.
Preserve detailed time, pre/post knowledge dumps, later retention/integration,
conversations and transcript links so another agent can review the design.

**P005 — Proposed design dossier, not activated:**
[Experimental-design review](experimental-design-review.md) supplies outcome axes,
comparable assessment proposals, delayed follow-up options, burden tradeoffs,
measurement limitations, analysis and publication-evidence requirements. Writing
this proposal does not activate assessments, reminders, an RCT or publication.

**Status annotation to Q004:** superseded by the 13-item production pilot deployed
13 September. Its content and activation are recorded in analytics-v1; Q004's
“no production import yet” describes an earlier state. **Qualification to D009:**
immutable selection snapshots and client update IDs are implemented, but execution
backend/policy stamps and some capture/timing joins remain incomplete (M02–M05).

### D011 — Explain and examine the pilot hypotheses (13 September)

User source `codex-20260912-L1664`: specify actual engagement, expected outcomes, competing hypotheses, and how interaction/qualitative feedback can challenge the design. [Pilot hypotheses](pilot-hypotheses.md) documents the current loop and proposed H1–H6 interpretation rules. Predictions are not findings; formal outcome probes and automatic monitoring remain unimplemented. Conversation snapshot `dd4ad3dfc1727e4d` preserves this request.

### D012 — Preserve an editable retention standard (13 September)

User source `codex-20260912-L1749`: write down the preceding retention/measurement proposal and
refine it as we go. [Working specification](retention-and-connections-v1.md) preserves
five substantive areas plus terms, proposed 0–3 rubric, level-2/8-of-10/2-of-3 candidate
thresholds and assessment sequence. These remain revisable practical proposals; no
fixed assessment has been deployed or threshold empirically validated.

### D013 and P006 — Connections and optional speech markers (13 September)

Same user source: connections to earlier reading while continuing to read are another
indicator of success. Adopt this outcome; distinguish personal/source-supplied/prompted
connections and preserve what they help explain. No connection quota or automatic
mastery upgrade. User tentatively suggests “I think” / “I wonder” markers. P006 records
optional distinctive start/return phrases and bounded, uncertain attribution; it does
not assume consistent adoption. Markers identify intended contribution, not independent
recall or correctness. Unmarked recordings retain unresolved authorship.

## D014 — Intensive practice while new reading is limited (13 September 2026)

User requests substantially more material to visit and revisit over the coming days.
Implement [intensive v2](intensive-v2.md): 76 items, thematic selection, exposure
prerequisites, short initial FSRS steps, and optional extra practice recorded without
postponing scheduled reviews. These choices are an observational design revision,
not user evidence of mastery. Original recordings, items and events remain intact.
“Too easy” feedback supports pruning and improving the expanded set.

## D015 / O001 — Original cards welcomed; independent term lookups (13 September 2026)

**User report:** “i've already gone through all the cards that were there before
this expansion. I like them all. I did separately look up some of the terms like
ard to get a better idea.” Source: `codex-20260912-L2217`,
2026-09-13T09:32:02.783Z; conversation freeze `d0d5698b87862347`
(135 messages: 38 Claude, 97 Codex).

**Telemetry check at 09:32:41Z:** all ten original non-voice Review items have at
least one introduction or completion. Six terms were introduced; marin grense and
ard also had completed recall encounters. The period sequence has two completions,
bronze aspect and landheving causal cards one each; the synchronic card has an
introduction. The three original voice prompts have no logged encounters at this
cutoff. This is consistent with having traversed the available Review material;
visited/introduction/completed recall remain different measures. Do not recode the
user's report as thirteen tested items or universal correct recall.

**Interpretation:** explicit positive feedback supports retaining the original set
and its level of relevance. It does not yet measure delayed retention. Looking up
ard and unspecified other terms is self-reported external learning exposure and
may express curiosity, insufficient explanatory detail, or both. The user sought a
better idea of the term, not necessarily a more exact verbal definition. Background
events cannot establish what site was visited, lookup duration, or its effect.

**Research record:** ard is the only named lookup. Other terms, sources, times,
modalities and sequence relative to recall are unknown. Do not fabricate in-app
lookup events or adjust FSRS/knowledge state from this message. Later ard recall
must be interpreted in the presence of reported outside exposure, with unknown lag.
Documentation and the source conversation retain the observation; it is not yet a
structured external-exposure table or mobile logging feature.

**Proposed next experiment, not deployed:** optional image or concrete use example
for object terms, followed later by contextual recognition/application. Preserve
the short card flow. Compare user-reported clarification and voluntary enrichment
with subsequent application, without attributing causality from one lookup.

Read-only telemetry evidence:
[original-feedback-check.json](/Users/stian/.agents/research/petrarca-norway-study/phone-practice-v2/original-feedback-check.json).
This archive cutoff includes the report and initial acknowledgment, not this turn's
eventual final response. No content, scheduling or production data changed.
