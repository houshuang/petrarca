# Consolidation through the Petrarca phone app

13 September 2026. User requirement: use Petrarca's mechanisms away from the
keyboard. The assistant's chat-based three-question check is superseded as a
delivery mechanism; its unanswered prompts remain candidate study material.

## Verified capability versus study readiness

Read the native app, not only the separate desktop Companion. On this date both
remote main and deployed server were `b7716e5`. A read-only request through the
private mobile HTTPS gateway returned health `ok`; its curriculum list contained
the four Norway curricula covering 800–2000 CE. No pre-800 Norway curriculum was
present. The installed phone build was not inspected and no device end-to-end
test was performed. The study sources/targets remain private artifacts, not
production items. No deployment or live ingestion occurred in this audit.

Native Review renders all five structural card types, entity introductions,
microlearning and quizzes. Voice exposes Guided Recall, Capture Voice, Knowledge
Sweep, Defender Mode, What You Said Before and Voice Notes. These are reusable
implemented screens, not merely ideas in old design documents. The desktop
Companion's previously-reviewed-only selection rule does not govern the native
review stream. Its narrower scope must not become a reason to ignore the app.

## Put each mechanism to a specific use

| Mechanism | Study use | First-batch candidate / adaptation |
|---|---|---|
| Sequence cards | Period order, approximate boundaries and duration | Stone Age divisions and Bronze Age transition; explicit regional/conventional ranges |
| Aspect cards | A few related dimensions of one concept or transition | A selected archaeological culture: rough identity, time and place; do not require exhaustive detail |
| Synchronic cards | Norway alongside familiar world history | A verified Bronze Age comparison anchored to material the reader actually knows |
| Causal cards | Explain relationships rather than repeat dates | Resources, settlement, subsistence and exchange; keep speculative links qualified |
| Cast cards | People in roles and relationships | Useful in later volumes with historical actors; no need to force into prehistory |
| Microlearning, rich answers and follow-ups | Understand before testing; pursue an inquiry | Term explanation, a useful illustration, source evidence or an investigation prompted by the notes |
| Multiple retrieval cues | Encounter an idea through different prompts | Term → rough meaning; interpret term in a sentence; picture → function. Name recall is a different optional goal |
| Guided voice recall / book recall | Short independent explanation on the phone | One focused question about a read section, recorded with book closed |
| Knowledge Sweep | Occasional broad comparison with the initial baseline | At a substantial milestone; not a seven-era obligation after every reading session |
| Defender | Work through a consequential interpretation | An occasional claim about technological/economic change; debate performance is not a memory score |
| Commonplace, entities, timeline/map | Revisit context and connect later reading to earlier encounters | Attributed book passages versus confirmed reader comments; links to source time/page |
| FSRS and interaction logs | Return to selected material and preserve actual observations | Separate cue-specific response, help, reveal, exposure and skip; no mastery from source import |

## Proposed ordinary phone experience

Open Review with a Norway-study scope: recently read material plus selected older
anchors, mixed through existing card types. No typing is needed to think, reveal
and tap a grade. A concept can receive a brief introduction before an unfamiliar
term is tested. Offer a focused voice response when an explanation is more useful
than a tap. A session can stop naturally after a few cards; do not demand every
mechanism on every visit. Continue Tana recording during reading as before.

Longer voice synthesis and Defender are occasional deliberate choices. Follow-up
explanations should be available where needed, without turning every unknown
term or interesting detail into a large research assignment.

Phone use with taps and voice answers is the first requirement. Fully screen-free
use would additionally need prompt/answer speech and hands-free controls. No
text-to-speech path was found in the inspected native app; do not advertise an
implemented walking/audio-only mode merely because audio recording exists.

## Bounded first implementation

1. Introduce selected verified pre-800 material through an explicit study source
   path, retaining recording, transcript version, segment/page and authorship
   uncertainty. Do not submit Tana book quotations through legacy free-capture
   assessment and treat them as remembered knowledge.
2. Associate the batch with the twelve-volume project and read coverage. Add a
   native study focus and scoped selection, so sessions do not depend on finding
   Norway among the entire existing corpus. Default to a small curated mixture.
3. Populate a first usable set of sequence/aspect/causal/synchronic items, several
   concept introductions and a few guided voice prompts. Existing twelve topic
   targets and twenty term candidates are a source pool, not a mandatory queue.
4. For term familiarity, distinguish recognition/rough meaning from exact label
   retrieval. Existing multi-cue sharing must not equate different intended
   depths of knowledge. Source occurrence is not a successful learning event.
5. Preserve response/audio, prompt and answer version, assistance, reveal and
   actual grade. Verify voice audio durability on the reused path. Existing
   structural anchor exposure gives scheduling credit; report it as exposure,
   never as a correct answer in the study's measurements. Sweeps must not score
   omitted or unread material as established ignorance.
6. Exercise source import against isolated fixtures; then deploy through the
   repository's current mobile/server paths and verify the actual phone flow.
   No synthetic text into production user-ingest endpoints. Keep SQLite runtime
   access through curriculum_db and scheduling through canonical functions.

This is the implementation handoff, not a statement that Norway study cards are
already available. A working gateway and preserved card components remove the
need for a new standalone learning interface; content, selection and evidence
handling are the immediate integration work.
