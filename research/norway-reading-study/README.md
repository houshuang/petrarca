# Norway history: a twelve-volume reading study

> Current status, 13 September: the 13-item phone pilot is deployed. Earlier “not imported/deployed” statements below describe historical stages. The comprehensive design review and its measurement gaps supersede broad promises of exact time or complete analytics; proposed follow-ups are not active.


Started 12 September 2026. Owner/participant: Stian. Current phase: volume 1,
*Fra jeger til bonde*. The phone implementation and measurement contract are in
[analytics-v1.md](analytics-v1.md); see its release record for deployment status.

Start with the [study index](study-index.md) for conversations, sources and coverage.
The [decision/correction ledger](decisions.md) records changes in user goals and
interpretation. Latest instructions: keep all other cards paused while rapidly iterating on this
phone pilot, with detailed source-linked analytics and versioned research changes.
Verbatim book reading (including summaries) remains exposure rather than evidence
of reader integration; concept familiarity remains a core outcome.

## Review this experiment

Start with [reviewer-brief.md](reviewer-brief.md), then the [full experimental design](experimental-design-review.md). The [evidence index](evidence-index.md) links directly to local conversations, transcripts, audio and the runtime snapshot. Review from this repository; no ZIP or extraction is needed.

For the current interaction loop and competing predictions, read [pilot hypotheses](pilot-hypotheses.md).

[Retention and connections working specification](retention-and-connections-v1.md) records the three-month candidate standard, assessment method, connections during later reading and optional spoken markers.

## The question

Can rapid reading of all twelve volumes of *Aschehougs Norgeshistorie*, supported
by continuous spoken notes and a small amount of selective retrieval, produce a
durable, connected overview of Norwegian history? The outcome is being able to
locate an unfamiliar event, explain a transition, compare societies and connect
Norway to the wider world—not remembering everything that was extracted.

Stian's priorities, recorded explicitly in this conversation:

- Periods and their approximate dates; what was happening elsewhere at the time.
- How and why things change: settlement, subsistence, institutions, power.
- Languages: origins, spread, contact and the formation of Norwegian/Swedish identity.
- Trade and networks, including the supply of copper and tin.
- Familiarity with concepts and specific terms: recognize a later occurrence and
  have a rough idea of its meaning, making other historical texts easier to read.
- What everyday life was like at different moments.
- A few major interpretations where they earn their attention (for example,
  competing accounts of Rome's fall), without memorizing every speculative
  archaeological argument or minor find.

## The actual reading method

The original September 10 conversation proposed closed-book chapter-end recall.
On September 12 Stian explicitly revised this: chapters are too fact-dense for
that to preserve enough material. **He leaves Tana recording continuously and
speaks notes while reading with the book open.** Norwegian is the main language;
some passages and baseline reflections are English. Do not try to force the old
protocol back onto this project.

On 13 September he clarified that he often reads sentences verbatim, including
summaries written by the book's author. Default open-book passages to
`text_origin=unresolved_book_or_reader`. Neither a summary, a causal explanation
nor first-person wording by itself establishes reader synthesis. Quotation versus
paraphrase requires evidence; no mandatory verbal labeling convention is imposed.
Even confirmed original open-book interpretation is not unaided delayed recall.
See correction C001 in [decisions.md](decisions.md).

This produces several different evidence types. Keep them separate:

| Evidence | What it can support | What it cannot establish |
|---|---|---|
| Unattributed open-book passage | Recorded encounter with content; explicit page markers | Authorship of the formulation, independent synthesis, comprehension or recall |
| Verified book quotation/paraphrase | Source claims and exposure | Reader-authored interpretation or mastered knowledge |
| Reader question or uncertainty | Curiosity, an unresolved interpretation, need for explanation | An error or a knowledge downgrade |
| Confirmed reader-authored connection | An interpretation expressed at this moment, under recorded assistance conditions | Long-term retention without another observation |
| Closed-book baseline/recall | Accessible knowledge under the stated cue conditions | Everything the reader knows; omission is not ignorance |
| Revealed answer | Exposure to an answer | Successful retrieval |
| Explicit recall grade | A scheduling signal for that target | Understanding of the entire topic |

The first English capture is a valuable pre-reading baseline. Preserve its
mistakes, hedges and unanswered questions as baseline data, rather than improving
it retrospectively. Reading notes provide detail; later retrieval is a separate,
lightweight activity over selected targets.

## Timing and page accounting

Store the measured duration of each original audio file, its hash, Tana node IDs,
Tana creation timestamp, and page checkpoints. Tana's creation time is a metadata
timestamp; do not silently assume it is the start of recording.

For this confirmed continuous-capture mode, file duration measures the recorded
reading session, including spoken notes and any unmarked interruption. Report
three distinct quantities:

1. Recorded reading-session duration: observed exactly to the file's resolution.
2. Active reading time excluding spoken notes and breaks: unknown unless separately
   marked; never estimate this by equating silence with reading.
3. Additional learning work: baseline, recall, app review, discussion and research,
   separately recorded and not silently charged to reading speed.

Going forward, retain the current natural method. At the start, say volume and
page; at a break, say "pause" and "back" if the recorder continues; at the end,
say the final page and whether a section was skipped. These are sufficient
minimal markers. If recording is stopped during a break, store both files as
segments of the same session. Missing markers stay missing.

Page checkpoints define traversal, not proof of exhaustive reading. Distinguish
page advance, unique page coverage, revisits and explicitly skipped sections.
The first captures overlap around pages 58–59; do not sum them as distinct pages.
Compare reading rates by section descriptively; section difficulty and attention
are confounders, so faster reading alone is not better learning.

## Repeatable capture-to-review workflow

1. **Discover and archive.** Search the actual #journal tag, then its audio
   descendants. Snapshot source text before edits; fetch original audio. Record
   source node IDs, language hints, book/volume/page markers and SHA-256. One
   journal capture and its audio child are one recording, not two observations.
2. **Transcribe.** Run [reading_study.py](../../scripts/reading_study.py) with the
   versioned [context](transcription-context-v1.json). Retain raw provider tokens,
   confidence, timestamps, exact config and file hash. No translations. Prior
   versions are immutable; the same completed inputs are reused rather than
   generating another paid job.
3. **Clean conservatively.** Read the timestamped transcript. Correct plausible
   terminology only with evidence; document original, proposed reading, time,
   reason and review status. Never turn an uncertain speaker statement into a
   certain one. ASR confidence is not historical confidence. Supplying expected
   vocabulary can bias ASR, so agreement with the vocabulary is not independent
   audio verification.
4. **Triage disputes.** Replay ambiguous names, negatives and dates at their
   timestamps. Unresolved speech remains flagged; it cannot become a graded
   exact-date question. Distinguish an ASR error, a spoken slip, an outdated book
   interpretation, and an unresolved historical debate. Each needs a different
   response. Do not use a language model to silently "repair" history.
5. **Index the full source.** Preserve the searchable, timestamped archive even
   for facts excluded from review. Assign each extracted item to quotation,
   paraphrase, reader inference, question, connection, timing marker, or recall.
   These are candidate functions unless authorship is verified. A summary-shaped
   passage is not automatically a reader synthesis. Keep assistance conditions,
   textual origin and demonstrated learning as separate fields.
   Every interpretation points back to a recording/version/segment, and to a page
   when explicitly stated. An inferred page span is marked inferred.
6. **Select a compact scaffold.** Cluster repeated claims into targets. Use the
   selection policy below. Archive detail remains retrievable without becoming
   a queue. All new LLM-assisted extraction uses Codex, per project policy; the
   first batch can be curated directly by the current Codex task.
7. **Present small retrieval opportunities.** Teach an unfamiliar concept first.
   Then ask one question, reveal, and record response/skip/feedback. An initial
   target is 2–5 minutes of review on reading days, adjustable by observed burden;
   this is a hypothesis, not a quota. No backlog or penalty for stopping.
8. **Inspect longitudinally.** After a section/volume, compare current independent
   recall with the baseline and previous probes. Track which cues were shown,
   answer exposure and elapsed time. Revisit the selection policy when targets
   prove trivial, frustrating, obscure or unhelpful.

Runnable transcription example (private manifest/audio, no database writes):

```sh
python3 scripts/reading_study.py \
  --manifest /path/to/private/batch/manifest.json \
  --context research/norway-reading-study/transcription-context-v1.json \
  --version soniox-context-v1
```

Replay reviewed editorial decisions and regenerate the audio reader:

```sh
python3 scripts/reading_study_review.py \
  --manifest /path/to/private/batch/manifest.json \
  --asr-version soniox-context-v1 \
  --editorial-version editorial-v1
```

This consumes per-recording `review.json` files with the raw ASR hash, exact
old/new text edits, reasons and uncertainty flags. It refuses mismatched preimages
or changed evidence. It also displays the batch's optional `learning-targets-v1.json` (or the manifest's
`learning_targets_file`). Batch labels and baseline links come from the manifest.
Selection and editorial judgment remain explicit research steps, not hidden
rewrites. New editorial decisions require a new editorial version.

Set `SONIOX_API_KEY` through the environment. Requires Python's standard library
and `ffprobe`. To resume one file add `--recording hunters`. Changing any source
metadata, audio or ASR context requires a new version. `raw.json`, `binding.json`,
`segments.json`, `transcript.md`, `metrics.json` and `review-candidates.json` are
research artifacts, not a replacement runtime data store. A candidate flagged
for review is not a detected factual error. The transcription CLI does not run
semantic extraction, publish to Tana, grade knowledge or populate the app.

Private first-batch archive:
`/Users/stian/.agents/research/petrarca-norway-study/2026-09-12/`.
Keep audio, signed media URLs and raw personal speech out of source control.

## What deserves retention

Select targets before multiplying them into cue variants. A target can be a
period, a mechanism, a comparison, a network, a person or a major interpretation.
Use four questions: Is it load-bearing for understanding later reading? Does it
serve Stian's stated interests? Does it connect several observations? Is it
sufficiently clear and well-supported for the kind of retrieval proposed?

Selection outcomes (revised 13 September):

- **Core scaffold:** approximate period boundaries, major transitions and durable
  explanatory relationships. First-batch hypothesis: roughly 10–15 targets for
  pages 13–146, to be reduced if their review becomes burdensome.
- **Chosen enrichment:** a memorable example, language question, object or trade
  connection that makes the scaffold useful. Do not promote all vivid details.
- **Concept familiarity:** terms that will help future reading, even when peripheral
  to this narrative. Rough meaning or recognition in context can be sufficient;
  do not require precise definition recall. See [concepts.md](concepts.md).
- **Archive/reference:** lists of sites and artifacts, variants of the same
  explanation, low-impact disputed reconstructions and things deliberately
  skipped. Searchable and available sideways; no scheduled memory obligation.

Historical uncertainty is not a reason to omit every interesting topic. For a
central contested question, retain the question, 2–4 substantial explanations
and their evidential limits. For a minor contested detail, preserve it only in
the archive. Selectivity belongs to the system, not to an endless curation chore
for the reader.

## Periodization and worldwide connections

Use BCE/CE as the display convention (f.Kr./e.Kr. in Norwegian), with approximate
ranges where appropriate. Preserve the exact source wording separately.
Do not convert an unqualified "years ago" using today's year. Archaeological BP
may use a 1950 origin, calibrated dates differ from uncalibrated radiocarbon
ages, and a 1990s book may use a publication-relative phrase. Unknown reference
frames remain unknown until checked.

Store each boundary with geographic scope, convention/source, uncertainty and
an acceptable response range. A climate phase, archaeological period, economic
transition and book-part title are different axes; they need not start together.
Do not falsely turn a gradual or regional transition into one national event.

Cross-world anchors should first use knowledge the reader actually has. The
English baseline supplies evidence of interest/familiarity with Rome, the wider
European context, sagas and Constantinople. Interest alone does not establish
knowledge of a specific date. Check a proposed anchor once before using it as
known context. Accept approximate placement when exact precision adds no value.

## Retrieval formats and Petrarca fit

**13 September delivery correction:** Use Petrarca's native phone Review/Voice
mechanisms, away from the keyboard. The desktop Companion described below is a
separate interface; its prior-review-only selector is not the native selector.
The live mobile gateway is healthy. The curated pre-800 study import, study focus
and evidence handling remain to be integrated. See [mobile-workflow.md](mobile-workflow.md).


The current published base is `b7716e5`, verified from origin on 12 September.
Its [Companion restart](../restart-plan-2026-08-24.md) intentionally limits the
recall screen to questions backed by prior review. `scripts/recall_engine.py`
snapshots question/answer/source/version and records grades through canonical
FSRS. It will not automatically show this new study's material.

| Desired learning | Format | Existing path / remaining work |
|---|---|---|
| Period order and approximate bounds | Timeline/order/range recall | Existing sequence/aspect machinery; verified pre-800 source coverage needed |
| How a change happened | Explain a short causal chain | Existing causal cards; source-backed curated targets needed |
| Same time elsewhere | Synchronic comparison | Existing synchronic cards, grounded in genuinely familiar anchors |
| Trade networks | Route reconstruction: resources, regions, dependencies | A simple textual cue can work first; map UI is a separate design task |
| Language history | Explain contact/spread; distinguish evidence from speculation | Selected conceptual prompts; do not assert unsupported prehistoric language identity |
| Everyday life at two dates | Compare the same social dimensions | Period-portrait format is still unbuilt |
| Major interpretive disputes | Defend/compare 2–4 accounts | Existing defender mode; engagement is not an FSRS grade |
| Broad durable understanding | Occasional closed-book synthesis | Separate probe with raw response, cue, assistance, date and rubric |

Important gaps: the four Norway curricula created September 10 start at 800 CE;
volume 1 needs its own pre-800 scaffold. Their entity/key-fact steps were paused.
Continuous open-book captures must not enter paths that infer mastered knowledge
from voice statements. The current recall selector also needs an explicit,
source-backed introduction path for *selected* new study targets. Do not fake a
prior review to bypass that selector.

Future canonical study records belong in server SQLite through `curriculum_db.py`:
projects/volumes; capture identity and audio provenance; session segments and
clock evidence; immutable transcript versions; typed source passages; curated
learning targets and source links; probe/review events with cue-version snapshots.
Connect scheduling only through `record_answer`, `record_structural_answer` or
`_fsrs_reschedule`. Keep ASR processing, source exposure and actual recall events
separate. Integrate and test a bounded import/intro path before any app changes;
this research batch is not silently posted to a production ingest endpoint.

## Measurement and interpretation

Keep a dated record of changes in transcription, selection, prompts and review
policy. For each volume, report session time, stated pages/sections, missing
intervals, capture volume, selected-target count, review burden and independent
recall observations. Do not invent a total-facts-known denominator from an
extraction model's output.

Probe dimensions: approximate temporal placement, causal explanation, geographic
or trade-network structure, cross-period comparison, calibrated uncertainty,
and spontaneous useful connections in later reading. Use a short rubric with
examples and preserve the raw answer. A graded recall of the same cue measures
that retrieval opportunity; a new formulation or later synthesis gives a
stronger check on transfer. These are planned measures, not evidence of a
benefit yet.

Potential observation windows are next day, about a week, at volume completion
and at a later cross-volume revisit. Let normal app use supply most observations;
do not create a research ritual larger than the reading. Record missingness and
skips neutrally. Any comparison between formats is initially descriptive: topic
difficulty, prior knowledge, self-selection and repeated exposure confound it.
If we later randomize comparable targets to cues, specify eligibility, allocation,
primary outcome and contamination rules in the experiment log first. A one-person
study can guide this person's tool; it does not by itself establish general efficacy.

## Current batch and next concrete step

See [first-batch.md](first-batch.md) for recordings, observed durations, transcription
findings, source-indexed selected targets and remaining ambiguities. Preserve the
user's reading method. The next product slice is a small pre-800 introduction and
recall path for verified core targets, with timing/provenance preserved, rather
than generating cards for every extracted detail.

Sources for the ASR implementation: [Soniox context](https://soniox.com/docs/stt/concepts/context)
and [async transcription](https://soniox.com/docs/stt/async/async-transcription).
The term list contains expected vocabulary, not a hidden answer key or a
historical source. All research decisions here are provisional unless explicitly
attributed to Stian above.
