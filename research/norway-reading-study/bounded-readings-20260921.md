# More detail, within one step of the book

Assessment by Astra, 21 September 2026. This is a design proposal grounded in the
current code and six new Tana entries. The separate source-intake batch is actual
content work; the reading feature described here is **not implemented**.

## Recommendation

Add a small optional **Forklar kort** reference beside material the reader has
already recorded. Answer one concrete wondering, clarify one term, or provide one
missing geographical/chronological connection. End with **Tilbake til øving** and
**Velg spørsmål å øve på**. A reading cannot generate another reading.

The book remains the spine. The app helps the reader make sense of a passage and
keep selected ideas available for subsequent reading. It should not build a
parallel curriculum from every named entity or convert curiosity into a backlog.

The user's firm requirement is one degree from original voice material. Proposed
starting limits are 150–300 words, one optional illustration/map, two or three
verified references and at most three selectable questions. These are adjustable
pilot defaults, not user-specified limits or evidence of optimal learning dosage.
Keep the first queue to three useful explanations; retain other wonderings as
unprocessed source material rather than generating an unread library.

## What the new material actually contains

Full search of journal tag `0VhmSsp1En` in workspace `VSazTvUjtQ`, limit 100,
returned twelve nodes on 21 September: four original study sources, six new study
entries and two 2023 demo nodes. This is coverage of that tag in that workspace,
not proof that no untagged recordings exist elsewhere.

| Entry | Evidence type and scope | Implication |
|---|---|---|
| `2AkbRRPlkU86`, 18 September | Explicit “what do I remember?” reflection on Stone/Bronze Age reading | Preserve informal recall and its uncertainties. Do not relabel it as book-open quotation, standardized assessment or a pre-app baseline. |
| `OGLwE6QWJuYV`, 18 September | Reading starting p.147, stopping p.181 | Monumental graves, prestige exchange, cremation, uneven change. Some earlier animal questions are already partly answered here. |
| `uz6cLbUazk3r`, 18 September | Reading from p.181; ironworking, Europe and chieftains | Numerous explicit geography/chronology/language wonderings. Keep these separate from the surrounding historical assertions. |
| `NrCkgJIldk4R`, 18 September | Reading p.206–228 | Farm expansion, longhouses, infield/outfield and material evidence. Good mechanism and term targets. |
| `U2heFUejwo2h`, 20 September | Reading from p.229, stopping p.256 | Networks, language evidence, runes, fortifications and the transition around 550. Contains an explicit unfamiliar-term report. |
| `ObOYtNsQWS_G`, 20 September | Reading from p.256, stopping p.277 | Merovingian-period change, farms, centres and monumental mounds. Separate observed objects from political interpretations. |

These are stated reading anchors. They do not establish that every intervening
page was read or recorded, nor that every statement is the reader's own synthesis.

## Three good first readings

| Original anchor | Bounded question | What earns a place | Stop here |
|---|---|---|---|
| Reflection `3UUxGgxv-Naz`: difficulty understanding cutting/polishing and rock-art styles | What am I looking at when a book shows a rock carving? | One concrete example; distinguish making technique, motif and later presentation. An image needs a source/rights record. | No survey of all Scandinavian rock-art sites or generated links to their religions. |
| Iron Age note `yLjBUnqQZgQK`: why 1177 and which regions collapsed? | Why is 1177 a useful anchor without being the end of every Bronze Age? | Place the eastern Mediterranean episode beside the Norway sequence already being read. Make approximate/regional chronology explicit. | No chain of separate readings on each collapsed kingdom. Returning to Cline's book is a valid next step. |
| Migration-period note `NQYbf2adqHfU`: “karveskurden … Det vet jeg ikke hva er” | What does karveskurd look like, and why does the book mention it on metalwork? | A visual term explanation and a comparison grounded in an actual object. | No full typology of ornament or obligatory specialist vocabulary. |

Other explicitly grounded candidates include Hittite geography, Celtic/Germanic
language labels versus political groups, and early domesticated animals. These
should not all be generated now. The later note “Så det svarer på noen av
spørsmålene mine om kuer og sånn” is evidence that reading itself sometimes closes
the question. Check newer notes before preparing an explanation.

An inferred interest is weaker than an explicit wondering. A name mentioned in a
quotation is not consent to expand it. For inferred interests, offer a title only;
require selection before generating the explanation. Never use fluency in a
recording as evidence that introductory context can safely be omitted.

## Two small content sketches

These illustrate scope; they are not published cards or a complete reviewed pilot.

**Hva er egentlig hugget i berget?**

En helleristning er laget ved å bearbeide steinoverflaten. Et hellemaleri er malt
på den. Dette er et skille mellom teknikker; det sier ikke alene hvem som laget
bildet eller hva det betydde. I Hjemmeluft i Alta ble figurene hugget i berg ved
strandsonen. Ferske hoggespor var lyse mot den jernholdige, rødbrune bergflaten.
Det gir en konkret måte å forestille seg synligheten på, uten å tenke på moderne
skiltmaling. [Alta Museum om teknikk og synlighet](https://www.altamuseum.no/no/bergkunst/de-rodmalte-helleristningene),
[museets forklaring av hellemaleri](https://www.altamuseum.no/no/bergkunst/bergkunstfigurer/hellemaleri).

Mange kjente fotografier viser røde figurer fordi ristningene ble malt opp i
moderne tid. Fargen er derfor ikke i seg selv dokumentasjon på forhistorisk
maling. Når du vender tilbake til boka, skill mellom sporene i steinen,
motivet og hvordan fotografiet eller tegningen gjør motivet synlig.
[Museets dokumentasjon av den moderne oppmalingen](https://www.altamuseum.no/no/bergkunst/de-rodmalte-helleristningene).

Optional target: distinguish an incised/hugged surface from applied pigment.
Technique alone should not become a quiz claiming a secure religious meaning.
Polished carvings need their own verified specimen before this sketch could answer
that part of the original question.

**Hvorfor akkurat 1177?**

Eric Cline bruker 1177 f.Kr. som et holdepunkt i fortellingen om sammenbruddet
i det østlige Middelhavet: angrepet på Egypt som knyttes til Ramses III.
Han understreker at sammenbruddet strakte seg over omtrent et århundre; det var
ikke én hendelse som samtidig avsluttet bronsealderen overalt. Byer og stater i
blant annet Hellas, Anatolia og Kanaan var allerede svekket eller ødelagt.
[Cline forklarer avgrensningen i et intervju](https://www.worldhistory.org/article/1446/interview-the-mysterious-bronze-age-collapse-with/).

Når du leser Norgeshistorie, kan dette være en forbindelse mellom to tidslinjer.
Det er ikke et nytt navn på overgangen til norsk jernalder. Hold fra hverandre
en boktittels valgte årstall, en langvarig regional krise og arkeologiske perioder
som avgrenses forskjellig fra sted til sted.

Optional target: explain why a historical anchor date need not be a universal
period boundary. Do not make an exact Egyptian regnal chronology the obligation.

## Current architecture: useful boundaries and real gaps

Inspected Petrarca commit `02301a61911abe2ec04afca5a58cb699adb2e064`, fetched
from origin/main. The shared main checkout was older and dirty; it is not the
reference for this assessment. The pre-intake production export at
2026-09-21T09:44:09.899Z has 76 items, 83 positions, 14 runs and 355 events.
The existing audit reports 42 completions across 27 distinct items, 47 graded
parts (42 knew, five missed), zero study response audio and zero assessments.
These are recorded practice self-reports, not independently established mastery.
The new Tana informal-recall recording is separate from those app tables.

| Area | Existing behavior | Consequence |
|---|---|---|
| Intake | `reading_study_archive.py` preserves checksummed originals; `study_intake.py` records source, draft and reviewed hash in SQLite | Reuse this publication boundary. Do not POST excerpts as synthetic learner voice captures. |
| Review protection | Append-only new items/positions; frozen revisions and runs; canonical study scheduling | Existing memory history can survive content expansion without invented grades. |
| Evidence | Exact transcript substring plus a required HTTPS reference | A matching quote proves transcript presence, not correctness or that the external URL supports the answer. Human/agent factual review remains necessary. |
| Drafting | Up to 20 candidates/source, fixed seven topics, `term`/`prompt`/`voice` | Enough for today's intake. The cap is a ceiling, not a quota. No need to redesign before importing. |
| Deduplication | Exact case-folded title/question pair only | Rewordings and cross-source repeats need operator review. Repeated evidence should normally strengthen a source link, not create another obligation. |
| Family selection | Six cards/session, one per family, due before new | Intake assigns each candidate a new family. It does not recognize several phrasings of one fact as one family. Avoid creating such clusters now; add stable target/family keys in a later narrow change. |
| New-content visibility | New items append after old ordinals; unseen eligible items follow existing order | Published does not mean next in the queue. A future explicit latest-reading/source filter could surface the new batch without rewriting due dates or old observations. Existing theme selection narrows topics, not source age. |
| Knowledge dimensions | General engine supports separately scheduled positions; intake creates only one | Separate important who/when/where/why targets where useful. A correct mechanism answer must not imply the date was tested. Today's safe content limit is fewer independent targets, not manufactured compound cards. |
| Attribution | Intake-generated item source stamps are uniformly `unresolved_book_or_reader` / `exposure_only` | Conservatively avoids mastery claims, but loses the difference between explicit informal recall and reading. Preserve richer source metadata now; later support per-span evidence kind. |
| Learning aids | `StudyLearningAids.tsx` has three hardcoded choices; `study_reference.py` freezes reference runs from a committed JSON manifest | Good interaction and exposure pattern. Dynamic brief content would need canonical SQLite storage and a server-provided catalogue, not another hardcoded list. |
| Old microlearning | `MICROLEARNING_PROMPT` requests 3–5 quizzes and six sideways queries, explicitly opening rabbit holes | Reusing that generator unmodified violates the user's new limit. Its output and automatic mixing policy are unsuitable defaults here. |

## Proposed data contract

Use small study-scoped SQLite records. Do not change the canonical store to JSONL,
build a general knowledge graph, or import the old feed machinery.

1. **Source anchor:** existing source ID plus transcript revision/hash; exact
   quote, character offsets, prefix/suffix and child node ID when available.
   Audio offsets only when actually aligned. Keep `reading_quote`,
   `explicit_wondering`, `explicit_recall`, `reader_reflection` and `unresolved`
   separate from factual truth status. An edited transcript creates a new version.
2. **Intent:** root source anchor, reader's question or bounded target,
   `explicit`/`inferred` basis, and status such as candidate/selected/resolved by
   later reading/deferred. Any `resolved by later reading` decision needs a later
   source anchor, not an LLM guess from topical similarity.
3. **Brief version:** stable brief ID, root intent ID, depth=1, scope question,
   text/optional asset, checked claims and sources, content hash, source/prompt/model
   versions, reviewer, status. Preserve versions; a correction must not alter a
   past reference run.
4. **Quiz target/selection:** stable target/family key, brief-version ID, exact
   supporting claim, independently testable aspect, proposed question/answer,
   intended depth and reader opt-in receipt. Reuse an existing target when the
   same learning goal already exists. Selection creates or activates only the
   chosen items through canonical publication, with fresh scheduling.

Make the one-degree rule executable: brief creation accepts a root intent backed
by original reader source evidence. It refuses a generated brief or its quiz as
the parent. The service assigns depth itself; a client cannot bypass it by sending
`depth: 1`. A uniqueness constraint for active brief/root-intent prevents retries
from growing multiple branches. A genuinely new user voice note may establish a
new root, but automatic retagging of generated content may not.

External citations remain available for verification and actual further reading.
This limit controls app-generated exploration; it is not a browser restriction on
the reader. No automatic ingestion of a clicked citation.

## Phone flow

Keep the compact practice screen. After the answer is revealed, expose **Forklar
kort** only when that target has a relevant prepared brief. Preserve the current
card and attempt state when opening and returning. Reading support before a
subsequent answer counts as exposure/help, so the response cannot silently be
classified as an unaided delayed test.

The alternative entry is **Valg → Det du lurte på**, a finite source-based list.
Each entry shows the question, original note/date and a modest length estimate.
No feed, search box, infinite scroll, recommended-topic carousel or badge demanding
that every wondering be cleared. Use the existing parchment/serif/rubric language;
keep provenance and technical detail collapsed under a source link.

The brief ends with **Tilbake til øving** as the normal exit. **Velg spørsmål å
øve på** opens at most three clearly worded candidates, initially unselected.
Show what each asks and whether an equivalent target is already being practiced.
The confirmation says exactly how many were added. Double taps and retry produce
one selection receipt. “I read it” is never a memory grade.

## Limbic: adopt small pieces at the boundary

Inspected clean Limbic HEAD `9e77ed5` on 21 September, including `docs/packet.md`,
`docs/apply.md`, `limbic/cerebellum/calls.py`, `packet.py` and the latest changelog.
The relevant redesign is already committed, not merely planned. Its first consumer
reports also document why forcing an existing pipeline into an incompatible helper
can invalidate paid caches or evidence anchors.

For this batch, one GPT-5.6 Sol worker handles acquisition, review and the existing
intake. Extraction should be bounded stateless calls with a fixed prefix/schema,
source-specific bodies and retained output, not a separate roaming agent per note.
Begin with one representative source and inspect useful yield before scaling the
remaining five; “50 items” from large-corpus examples is not a reason to manufacture
a larger pilot than this dataset.

Useful narrow imports are `text_quote_anchor` for evidence and `make_packet` /
`lint_packet` for reproducible requests. `cached_call` can preserve repeated work
with explicit project/purpose/model/prompt-version attribution. Its defaults must
not silently select another model or transport: keep Codex and explicitly choose
the requested 5.6 model. Do not replace the existing authenticated CLI with a paid
HTTP transport just to use the helper. Log usable accepted targets, not just calls.

There are two compatibility traps. Limbic's `text_quote_anchor` normalizes
whitespace, matches without case sensitivity and reports offsets in normalized
text; retain the original raw-substring check and label these offsets correctly.
Its generic data-project checklist assumes text is canonical and databases are
derived. Petrarca's explicit SQLite runtime rule takes precedence: private packet
files are evidence/cache artifacts, not an alternative runtime store.

Do not apply `hippocampus.apply` to database-shaped dictionaries outside a SQLite
transaction and claim concurrency safety. Existing `study_intake.publish` is the
correct atomic runtime boundary. Similarly, semantic similarity can nominate
duplicate targets, but cannot decide that two historical claims agree. Exact
hashes and target identity come first; do not install an embedding stack for six
sources without a demonstrated need. Dates must remain in historical target keys.

## Acceptance criteria for the future feature

Reject unsupported original-source anchors and any generated parent. Demonstrate
idempotent brief creation and opt-in, versioned corrections, no quiz on mere view,
independent position scheduling and unchanged prior observations. Exercise a
duplicate target across two sources and an uncertain/outdated book statement.
Verify actual phone display → source → quiz selection → return with the card state
retained; log displayed brief version and help/exposure. Keep those observations
separate from memory grades and from claims about active attention.

The useful pilot question is whether one small explanation makes the next book
passage easier to read and whether the reader chooses a few worthwhile targets.
Completion rate or time spent reading in the app is not the success criterion.
