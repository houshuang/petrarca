# Pilot engagement, hypotheses and decision rules

Recorded 2026-09-13T07:36:55.033165+00:00. Assistant proposals prompted by Stian's request to explain
exact engagement, outcomes, competing hypotheses and how feedback changes the design.
User source: `codex-20260912-L1664` in conversation snapshot `dd4ad3dfc1727e4d`.
These predictions elaborate the existing pilot; they do not activate new assessments
or change selection, scheduling or telemetry. This is not retrospective evidence
that every prediction was specified before any participant exposure.

## What to do in the current app

For the first visit, try one Review batch (up to six items), approximately five to
eight minutes as a suggested stopping point, not a timed requirement. Keep the book
closed and select “Boken lukket”; if using the book, select “Boken åpen.” Continue
normal reading with continuous Tana recording outside this practice session. Do not
rehearse the entire transcript or finish every card to satisfy the experiment.

On first introductions, read for rough meaning and press “Lest · fortsett.” This is
exposure, not a test. On later term encounters, report whether the word looks familiar,
then formulate its rough meaning before revealing. Recognition alone does not earn
“Hadde hovedideen.” After reveal, compare against what was available beforehand;
use “Trengte hjelp med hovedideen” when the explanation supplied the missing idea.
Equivalent wording and appropriate uncertainty are fine. Structural cards use their
own per-position reveal/self-grade controls: attempt hidden parts before revealing.
Dates or anchors already displayed are assistance, not something independently recalled.

Use “Hopp over” for unsuitable or inconvenient cards. Rate useful/unclear/too detailed
before advancing when you have a reaction; there is no requirement to rate every card.
Sources can be opened to investigate, preferably after an unaided attempt. If another
source helped before answering, mention that explicitly: the present book-state control
does not capture every kind of assistance.

In a comfortable place to speak, optionally try one Voice prompt for 30–90 seconds.
The prompts concern the farming transition, metal/contact networks and a broad period
timeline. Say what you think, what you are uncertain about and why, without polishing
it into an essay. “Start opptak” → “Stopp opptak” → “Lagre opptaket” → “Se holdepunkter
for svaret” → self-assess the original response. Saving requires connectivity.
Voice is optional on a public train; skipping because of the setting is not ignorance.
The app is tap-and-voice based, not fully hands-free. Current practice requires network
access to load/advance; retry preservation is not a complete offline mode.

On a relevant card use “Jeg lurer på …” for a question, “Noe er feil” for a suspected
mistake and “Tanken min har endret seg” for a revised interpretation. A concrete short
observation is more valuable than trying to narrate every thought. For broader UX
feedback, use conversation/voice dictation rather than mislabelling it as historical
recall. End-of-visit prompts: What helped you think? What felt pointless or awkward?
What wanted a different explanation or interaction? One concrete example is sufficient.

## Hypotheses and competing explanations

| ID | Proposed benefit and predicted evidence | Alternative / evidence against | Design decision if observed |
|---|---|---|---|
| H1 Selective coverage | A few central anchors help organize much more reading. Later unaided accounts use periods, transitions and connections to structure examples; participant names occasions when an anchor helped. | Selection is too narrow, obvious or unimportant; card success rises but broader explanations remain disconnected, or omitted topics are repeatedly wanted. | Change target selection and intended depth before simply increasing card count. Include everyday life/language as reading and evidence warrant. |
| H2 Term familiarity | Recognition plus rough meaning makes terms easier to interpret in later historical text. Predict meaningful use in a new sentence and participant-reported reduced lookup/friction. | Familiar-looking words lack usable meaning; memorized definitions fail in context; selected terms rarely matter. | Compare recognition with meaning/context separately. Try contextual examples or reduce/deprioritize terms. Don't demand exact definitions as the default remedy. |
| H3 Structural formats | Sequence, aspect, causal and same-time cards organize information usefully. Predict later recall with anchors removed or cues changed, including warranted cross-country connections. | Visible cues do the work; the interface teaches a layout or answer string; independent explanation does not transfer. | Reduce or vary assistance and compare equivalent targets. If layout is confusing, simplify it before interpreting misses as a knowledge deficit. |
| H4 Brief voice explanation | Short spoken responses reveal useful models, uncertainty and misconceptions beyond binary taps, and can support later comparison. | Eloquence, copying supplied phrasing, ASR errors or performance pressure dominate; captured detail adds burden without actionable insight. | Preserve raw audio and score-critical uncertainty; shorten/alter prompts or use occasional broader dumps. Book-open recordings remain exposure evidence, never presumed synthesis. |
| H5 Sustainable practice | Short phone sessions are useful enough to return to voluntarily while reading continues; concrete benefits outweigh disruption. | Use is driven by novelty/obligation; logging and quizzes impede reading; train connectivity or speaking context makes interaction impractical. | Simplify duration/controls/capture expectations, fix delivery failures, or drop formats. Do not increase reminders or treat all abandonment as low motivation. |
| H6 Responsive feedback | Linked wonderings, corrections and reflections let us improve material and follow changing understanding. Predict identifiable issue → change → later encounter → resolved problem or useful new question. | Feedback accumulates without resolution; extra explanations create irrelevant detail or induce confidence without understanding. | Keep a resolution/change ledger and examine later evidence. Limit expansion to questions that serve the participant's goals. The complete automated wondering lifecycle is not implemented yet. |

All six are reviewable working hypotheses, not established findings. A useful
personal workflow does not establish a causal advantage over reading alone.
Continued reading, AI discussion, repeated testing, prior knowledge and novelty can
explain improvement. The present adaptive single-person pilot cannot isolate their
separate effects. Different content across card formats also confounds format ranking.

## How observations become decisions

**Interaction logs tell us what was done:** displayed/revealed positions, recognition
and self-grades, skips, quality taps, source opens, declared book state, voice capture,
and lifecycle events. They do not tell us why a pause occurred or whether a correct
self-grade reflects independent understanding. Current timing and capture-join gaps
are listed in [measurement-gaps.md](measurement-gaps.md). No exact attention total,
automatic hypothesis verdict or validated mastery score exists.

**Qualitative feedback helps explain why:** “Uklart” plus repeated reveals may mean a
bad prompt, unknown content, small-screen confusion or interrupted travel. A short
specific comment distinguishes them. “Nyttig” supports perceived utility but cannot
alone demonstrate retained knowledge. One concrete reproducible defect can justify
an immediate fix; do not wait for statistical significance to fix unusable UI.

**Independent later performance addresses outcomes:** pre-feedback explanation,
rough timelines and previously unseen contextual questions can show accessibility
beyond this card. These formal comparable probes are proposed in the design dossier,
not yet delivered automatically. We must implement/version them before claiming
transfer, months-later retention or improved confidence calibration. Recognition,
self-report, assessor judgment and observed application remain separate variables.

Example: a term is marked familiar and correct repeatedly, but its meaning cannot
be used in a different sentence. That pattern weakens H2 and supports cue familiarity;
it suggests contextual practice, not merely a longer streak. If the participant uses
its meaning accurately in later reading and reports less interruption, H2 gains support,
with intervening exposure still documented. One failure is evidence for investigation,
not definitive falsification of an entire format.

For each inspected episode record hypothesis ID, source/run/item/response references,
observation, participant explanation, competing interpretations, confidence, proposed
change and a future discriminating observation. Preserve disconfirming episodes.
Review the first actual visit for usability/data integrity and the first few visits
for recurring patterns; no autonomous monitoring schedule is created here. In a
follow-up analysis we can inspect the stored events and audio together with feedback.

Change one meaningful practice feature when practical and record old/new versions,
rationale and effective dates before activation. Keep the proposed small measurement
core stable while practice evolves. Report phase differences descriptively, not as an
RCT. Fix capture failures before using missing responses as evidence against learning.

## Expected outcomes by horizon

- First visit: usable controls, honest pre-reveal attempts, interpretable observations,
  specific feedback and perhaps a few clearer connections. No broad mastery claim.
- Subsequent sessions/readings: rough meaning available with fewer lookups, accessible
  period structure, more qualified explanations and useful evolving questions.
  These remain predictions until observed with appropriate cues and assistance recorded.
- Months and twelve volumes: confident connected overview and delayed accessibility
  under the actual ongoing reading/review conditions, with enough evidence for the blog.
  A broader content selection and comparable long-term assessments are still needed.

The thirteen current items are a feasibility sample. They cannot establish a
comprehensive Norwegian-history outcome on their own.
