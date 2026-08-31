# Petrarca Restart Plan: Companion, Not Queue

**Date:** 2026-08-24
**Status:** Session 95 revision implemented: desktop recall is the primary
Companion interaction; exact excerpts and recording remain preserved as
secondary tools
**Scope:** Preserve the full project and its data while testing a much smaller
way for Petrarca to earn a place in ordinary life.

## Decision

Petrarca is not intellectually abandoned. Its central thesis remains strong:
authentic reading happens elsewhere, speaking forces useful prioritisation, and
a small amount of well-timed retrieval can make later reading richer. That is
also the clearest through-line in the original essay,
[“Petrarca: An Intelligent Companion for the Self-Taught Reader”](https://networkedthought.substack.com/p/petrarca-an-intelligent-companion).

The failed part was the product contract. Capture became an input to an expanding
factory of curricula, researched cards, structural cards, and quizzes. The app
then became a destination with a large implicit obligation. That contradicted the
essay's most important lived constraint: 5% with the app, 95% with books,
podcasts, museums, travel, and historical fiction.

The restart therefore begins with one contract:

> Petrarca may keep something alive, but it may not turn a thought into homework.

## What the production history says

The useful signal and the generated inventory must be distinguished.

### Strong firsthand signal

- 36 persisted voice-transcript rows, representing about 35 distinct recordings
  after exact duplicate handling;
- 30 elicitation recordings in the strongest active period, with roughly 58,000
  transcript characters about Sicily, Rome, Greece, Byzantium, and Islamic
  history;
- 895 embedded transcript chunks, including 169 exact `raw_speech` chunks;
- 19 physical-book captures, including photographs, OCR, voice notes, and text;
- 154 canonical review answers plus 11 structural grades;
- interaction history showing a credible active stretch in April, then only
  isolated experiments and abandoned launches.

### Generated inventory with little behavioural uptake

- 590 structural cards and 2,434 positions, but only 11 cards / 33 positions
  reviewed;
- 1,279 microlearning card rows, only one of which was reviewed;
- 4,849 quizzes, only 25 distinct quizzes reviewed;
- 182 microlearning jobs still pending from April and 53 failed;
- almost the whole scheduled corpus now technically overdue.

This is not evidence that contextual resurfacing, voice elicitation, or knowledge
scaffolds failed. It is evidence that generation outpaced attention by orders of
magnitude.

## Preservation boundary

Nothing is deleted or reset.

- The canonical SQLite database remains the authoritative record.
- Existing curricula, knowledge states, entities, cards, quizzes, schedules,
  book captures, feedback, interaction logs, and sophisticated interfaces remain
  preserved.
- The old generated review queue is treated as an archive and research corpus,
  not as the starting screen or a debt to clear.
- Old Expo screens remain available in source history; the Phase 1 experiment
  does not require reviving the public Metro server or reopening port 8090.
- Raw audio is retained for all new Companion captures. A transcript is no
  longer accepted as an adequate substitute for the original recording.

The production data and configuration have a verified point-in-time off-host
snapshot. Recurring verified server backups include the Petrarca database and
durable data tree. A recurring off-host pull still needs to be added once the Mac
has adequate free space.

## Session 95 revision — recall first on desktop

First use of the Session 94 page established that an exact old excerpt is
interesting but does not, by itself, enact Petrarca's central promise. The
ordinary context is a desktop during work, where a microphone is usually not
available. The primary interaction is therefore now one question at a time:

1. show one question that is backed by a review the user previously made;
2. leave unhurried space to recall before revealing anything;
3. reveal the answer;
4. record **I remembered** or **I didn't remember** through canonical FSRS;
5. optionally mark the question **Good** or **Bad** and attach a thought,
   inquiry, correction, or explanation of why the question is weak;
6. stop, or deliberately ask for another question.

There is no due count, backlog, target, session size, streak, or timer. A skip is
neutral. Selection does not generate or repair questions: it draws only from
active reviewed quizzes whose parent research completed, plus previously reviewed
knowledge items with a non-generic cached question. Each run snapshots the exact
question, answer, source, type, and selection version so question quality can be
analysed even if the source cue later changes.

The Session 94 exact-excerpt and encrypted recorder paths remain intact beneath
a collapsed **Commonplace excerpts & recording** section. This is a change in
default interaction, not deletion or migration of the earlier work.

## Preserved Session 94 Companion tools

The first experiment is a private, bookmarkable HTTPS page with two actions.

### One old thought

On opening the page, show one excerpt taken directly from the user's canonical
speech—not an LLM summary, assessment, “interesting connection,” or feedback
message. The excerpt:

- is an exact substring of a real eligible transcript;
- excludes test provenance and collapses duplicate captures;
- is at least 30 days old;
- carries date/source provenance;
- has no question, answer, score, interval, due date, or knowledge-level claim;
- can be replaced deliberately with **Another**;
- can reveal the full recording context on demand.

Selection is channel-neutral and persistent. A daily run can later be rendered by
web, email, or audio without each medium independently choosing a different item.
Selection itself is not treated as exposure; only a rendered/opened item starts a
cooldown. Non-action is neutral.

### Record a thought

The browser recorder accepts a new thought after reading, listening, travel, or
conversation. The server performs only this pipeline:

1. write and fsync the raw recording with private permissions;
2. transcribe it;
3. persist a `voice_transcripts` row with `source='commonplace_capture'`, audio
   provenance, and no LLM result;
4. make deterministic `raw_speech` chunks and embeddings for later retrieval;
5. search old exact-speech chunks for up to three associative echoes.

It does **not** invoke domain routing, curriculum assessment, entity enrichment,
microlearning research, card generation, quiz generation, or FSRS scheduling.
If transcription or indexing fails, the audio remains recoverable and the page
receives its capture ID.

Before upload, the browser keeps an AES-GCM-encrypted recovery copy in
IndexedDB, keyed from the private capability path; it is cleared only after the
server confirms durability. The server derives a content-addressed capture ID
from the audio bytes, so retrying the same Blob after a lost HTTPS response is
idempotent rather than creating another recording or paid transcription.

### Privacy and access

- The Python research server remains loopback-only.
- nginx exposes only the exact Companion page and its four required endpoints
  beneath a private capability path; the capability does not open the broad
  research/admin API.
- Access logging is disabled for that path and responses use `no-store`.
- The capability and stable HMAC key are generated outside Git and stored mode
  0600; the HMAC key has a separate encrypted/off-host recovery copy so old
  identifiers remain resolvable after a rebuild.
- The public read-only Petrarca site and explicit `/content/` allowlist remain
  unchanged.

## Phase 2 — Research-library bridge

The Estonia and Crete/Sicily manuscripts should become retrieval sources, but
never evidence of remembered knowledge.

Build a separate, rebuildable, read-only `source-library.db`; do not ingest the
books into `voice_transcripts`, knowledge items, knowledge states, curricula,
microlearning, structural cards, or article ingestion.

### Estonia

Canonical inputs:

- `estonia-book/rewrite/front-matter.md`;
- `estonia-book/rewrite/chapters/[0-9][0-9]-*.md`;
- `estonia-book/rewrite/reference/claims.jsonl` (383 checked claim records).

Label the edition as Codex-generated under Stian's direction, read by Stian, with
the verified claim ledger preserved field-for-field. “Read” means exposure, not
known or retained.

### Crete and Sicily

Canonical inputs are the first edition that was actually read, plus its Codex
narrative audit. Results must always state that this is an AI-agent-produced,
audited draft with known causal overclaims. The unfinished replacement manuscript
must not silently substitute for the read edition.

The entire `crete-sicily-book` directory is currently untracked. Pin the edition
with a file manifest and bundle hash, and keep it inside the verified research
backup before building the derived index.

### Retrieval presentation

Keep two visually and semantically distinct sections:

- **Your words** — exact speech from Petrarca captures;
- **From books** — attributed passage with title, chapter, edition, and trust
  warning before the excerpt.

Book passages may inform a response or future on-demand audio recap, but they may
not write back into learner-knowledge or review state.

## Delivery experiments, in order

Do not build all media at once. Each step is earned by actual voluntary use of the
previous one.

1. **Private web companion.** Lowest friction during work and usable from the
   phone without installing or reviving the old app.
2. **Email, at most one gentle item.** Opt-in and initially manual/weekly. Generic
   subject; no personal transcript in notifications or previews unless explicitly
   chosen. The link opens the same canonical daily run.
3. **On-demand private audio.** A 3–7 minute recap assembled from one current
   recording, one older personal echo, and clearly attributed book context. No
   automatic podcast feed until listening behaviour proves useful.
4. **Optional scheduled delivery.** Only after at least two weeks of voluntary use
   and explicit preference data. No streaks, escalating reminders, or catch-up.

## Measurement

For the first two weeks after the Session 95 revision, measure only behaviour
that actually occurred:

- distinct voluntary-use days and questions actually opened;
- answer reveals, neutral skips, and explicit recall marks;
- good/bad question ratios by source and question type;
- time to reveal and time to grade as descriptive—not normative—signals;
- linked thoughts, inquiries, corrections, and question feedback;
- use of the preserved excerpt/context/recording tools.

Do not count generated items, selector runs, background jobs, app launches, or an
unopened delivery as engagement. Success is repeated voluntary use and reports
that later reading/travel became richer—not queue completion.

## Explicit non-goals

- clearing or rescheduling the overdue queue;
- regenerating missing questions;
- producing an Estonia curriculum before capture behaviour is established;
- feeding manuscripts into the learner model;
- adding notifications, streaks, goals, badges, or guilt-framed gaps;
- building email and podcast adapters before the web interaction proves itself;
- deleting, flattening, or “simplifying away” the prior system.

## Decision gates

After two weeks of the recall-first page:

- If questions are voluntarily opened and mostly rated good, tune the mix from
  observed recall/quality data before adding content.
- If use recurs but bad-question feedback clusters by source or question type,
  repair or suppress that class explicitly; do not hide the evidence by silently
  regenerating it.
- If the interaction is useful but the existing encountered pool is too narrow,
  add a deliberate path from new reading notes to reviewed questions, starting
  with the Sumer/Tvedt material the user actually wants to retain.
- Only then test a workday email link or on-demand recap against the same
  canonical run. Do not create independent delivery queues.
- If the page is not reused, preserve the experiment and stop. Do not respond by
  increasing reminders or content volume.

The sophisticated Petrarca remains the archive and laboratory. The Companion is
the small surface through which it can become part of life again.
