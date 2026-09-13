# First batch — 12 September 2026

Status: three complete Norwegian ASR reruns and annotated editorial versions;
original English baseline preserved; initial source index and 12 selected learning
targets prepared. None of these captures has been represented as successful recall
or automatically scheduled in production.

**13 September interpretation update:** Stian often reads book sentences verbatim,
including its summaries. The captured prose cannot establish reader synthesis.
Use the versioned `source-annotations-v2.json` and `reader-signals-v2.json` in the
private batch for current interpretation; earlier artifacts remain preserved.
Concept/term familiarity is now an explicit core goal, superseding the initial
treatment of definitions solely as enrichment. See [decisions.md](decisions.md).


## Observed sessions

Stian confirms that recording runs continuously while he reads and speaks notes
with the book open. These times therefore measure the recorded reading-and-note
sessions, including any unmarked breaks. They do not isolate silent reading time.

| Recording | Tana source | Duration | Stated checkpoints |
|---|---|---:|---|
| Pre-reading baseline (English) | [Questions before reading Norway’s history to 800 AD](https://app.tana.inc/?nodeid=QeF0kKB-QEJN) | 08:50.100 | Before volume 1 |
| Reading session 1 | [Jegere og samlere i Norge etter istiden](https://app.tana.inc/?nodeid=gi9oYzu422Pf) | 39:32.904 | 13 → 33 → 51 → 59 |
| Reading session 2 | [Fra jeger- og samlerkultur til det eldste jordbruket](https://app.tana.inc/?nodeid=gibRpJlrxEaD) | 29:25.080 | 58 → 70 → 90 |
| Reading session 3 | [Overgangen fra yngre steinalder til bronsealder](https://app.tana.inc/?nodeid=VlbnpbwlxQNw) | 40:05.376 | 90 → 109 → 111 → 132 → 146 |

**Recorded reading + notes: 1:49:03.360.** Including the separate baseline:
1:57:53.460. These are first-batch totals, not a claim about all study time.
The three new ASR outputs contain 5,190 whitespace-separated words and 189 timed
segments (including a few punctuation-only segments omitted from the reader).

Page 13 to page 146 is 133 pages of forward advance. There is an overlap at
58–59, and the user explicitly skips details. Do not report 133 exhaustively read
pages or sum the three ranges as unique coverage. The first recording explicitly
reports 20 pages in approximately 22 minutes at offset 22:13; its audio timing
is consistent with that report, without establishing the precise initial page-
reading instant. Later recorded page checkpoints enable finer pace analysis.

## Archive and runnable outputs

Private archive (audio and personal speech remain outside Git):
`/Users/stian/.agents/research/petrarca-norway-study/2026-09-12/`.

- `manifest.json`: four recording identities, hashes, source node IDs, languages,
  confirmed capture mode and page checkpoints.
- `*-original.mp3`: original recordings, including the English baseline.
- `<node-id>.md`: unmodified Tana source snapshots.
- `recordings/{hunters,farming,bronze}/soniox-context-v1/`: immutable raw ASR,
  input bindings, timed segments, measured durations and review candidates.
- `recordings/{hunters,farming,bronze}/editorial-v1/`: conservative annotated
  transcript, exact editorial preimages/reasons and unresolved readings.
- `learning-targets-v1.json`: 12 targets with recording/version/segment references,
  candidate prompts and selection reasons. All are ungraded and pending suitable
  source verification/introduction before app scheduling.
- `reader-signals-v1.json`: 21 source-linked page/timing/question/uncertainty
  passages. Compound passages may need further splitting in future extraction.
- `index.html`: searchable local reader, original audio players and timestamp
  buttons for source checking; also displays the selected-target proposals.

ASR was `stt-async-v5` with `no`/`en` hints and the committed vocabulary context.
The original baseline was not re-transcribed or fact-corrected. Provider file/job
cleanup succeeded after each raw result was saved. All numerical disputes are
still visible. The artifact is an ASR-assisted editorial record, not an
independently listened-to gold transcript.

## What the full rerun showed

The domain vocabulary recovered plausible readings including `mammutknokler`,
`reinrosen`, `Nøstvetøks`, `tamdyr` and `båndkeramikere`. It also produced regressions:

| Passage | Original Tana | New ASR | Editorial treatment |
|---|---|---|---|
| farming 08:21, s020 | Det skjøt særlig fart | Stedskjøp særlig fart | Restore coherent original wording; log version selection |
| bronze 02:17, s004 | 2000 helleristninger | 2004, helleristninger | Preserve numeric disagreement; no exact-count target |
| bronze 17:05, s027 | smør og ost | spørreost | Restore original wording; log version selection |
| farming 24:44, s056 | 3008–3007 f.Kr. | 3008–3007 f.Kr. | Still unresolved; no guessed date |
| hunters 39:10, s072 | Regnvakt / regnen | Regnvakt / reinen | Reindeer term improved; hunting term explicitly tentative |

Eleven editorial interventions are recorded with preimages and reasons. Fifteen
passages carry specific review notes. These are not exhaustive word-error counts.
Context-guided ASR is helpful, but neither a new version nor high confidence makes
it ground truth. Several ambiguities concern small, skippable details; they need
not all be solved before the reader continues. Uncertain core chronology or a
negation affecting a selected claim must be resolved before grading that claim.

Highest-priority remaining checks: period/phase boundaries; the malformed farming
date; the possible missing negation about grain growing near Alta (bronze s011);
and the difference between a named book part's endpoint and an archaeological
period's endpoint (bronze s019). Do not let these turn into incorrect questions.

## First selected scaffold

These are 12 *targets*, not 12 compulsory new quizzes and not twelve asserted
historical answers. Exact prompts and provenance are in the private index.

| Target | Why keep it | First suitable format |
|---|---|---|
| Periods and approximate boundaries | Organizes everything else; explicit reader difficulty | Order and approximate timeline |
| Ice, sea, rebound and land resources | Explains geography and later agricultural landscapes | Short causal explanation |
| Hunter-gatherer mobility | A usable picture of life before farming | Seasonal-life portrait |
| Agriculture as a long uneven transition | Separates introduction from widespread change | Sequence + explain phases |
| Everyday life before/after farming | Directly serves the project's central comparative question | Compare common dimensions |
| Flint and other raw-material networks | Connects tools, geography and external dependence | Resource network |
| Why bronze changed possibilities | Mechanism rather than a list of artifacts | Materials → properties → uses |
| Copper, tin, amber and European networks | Explicit interest; connects Norway to Europe | Reconstruct a network |
| Different northern/southern connections | Prevents a falsely uniform national narrative | Compare subsistence and routes |
| Language, migration and archaeological culture | Explicit interest; important evidential distinction | Explain what can/cannot be inferred |
| Norway in the contemporary wider world | Builds temporal hooks | A familiar cross-region comparison |
| What material evidence establishes | One reusable distinction avoids memorizing every debate | Observation vs interpretation |

Keep as selected enrichment, not automatic retention: visual demonstrations of
flintworking, examples of rock-art styles, definitions of `heller`, `ard`,
`åkerrein`, `avdrått` and `asbestmagring`, and the question about people moving trout
into high mountain lakes. Keep exhaustive find counts, site inventories, named
minor artifacts and speculative ritual reconstructions in the searchable archive.
Do not erase reader curiosity merely because it is not a scheduled target.

## A useful periodization check

The [University Museum of Bergen overview](https://steinalder.w.uib.no/) places
older Stone Age on the west coast from the earliest settlement to about 4000 BCE,
and younger Stone Age at about 4000–1700 BCE. It emphasizes continued hunting and
fishing into the younger Stone Age and a later rise in the importance of farming.
An [NTNU museum account](https://blogg.vm.ntnu.no/samlingsglimt/2011/04/07/grovkornet_stykke_steinalder/)
uses roughly 4000–1800 BCE for younger Stone Age. These are conventions and scopes,
not a reason to mark 1700 versus 1800 wrong in a broad-overview exercise.

For the initial scaffold, accept the approximate transition around 1800–1700 BCE
and keep the selected source convention visible. Do not drill finer subdivisions
until useful. The Bergen webpage also contains an apparent inconsistency in its
late-Neolithic subdivision; that line was deliberately not copied into a target.
The remaining source claims—especially language/migration and dated archaeological
interpretations—have not been comprehensively fact-checked in this transcription
batch. A transcript can faithfully preserve an outdated source claim.

## Product handoff

The current Companion deliberately draws from previously reviewed material. New
study targets therefore need a provenance-preserving introduction path rather
than fabricated review counts. Also, the Norway curricula created September 10
start at 800 CE: volume 1 currently has no matching Norway prehistory scaffold.

The next bounded implementation is a small source-backed pre-800 introduction
and recall slice, with explicit open-book provenance, approximate-date grading,
question-version snapshots and actual delayed-recall observations. Do not revive
the old mass-generation pipeline or automatically make a card for every claim.
For the full protocol and schema boundary, see [README.md](README.md).
