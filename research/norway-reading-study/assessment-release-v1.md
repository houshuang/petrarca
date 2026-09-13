# Phone assessment v1

Approved 13 September 2026; registered in the experiment log before code changes.

Fortell → Fortell oversikten. Declare occasion, volume, actual page/chapter coverage and help state. Record a free narrative (up to three minutes), then five neutral cues (up to 45 seconds each). No answer keys appear. Confidence precedes each cued response. A missing answer can be explicitly unknown or skipped; neither silently becomes a score. At volume/project end a bounded rotating pair of original questions follows. No observation updates FSRS, practice items or knowledge levels.

Frozen wording: [assessment-v1.json](assessment-v1.json). Scoring guidance: [rubric-v1.json](rubric-v1.json). Source-bound questions: [sentinel-questions-v1.json](sentinel-questions-v1.json). Each session stores the entire selected form and protocol hash, context and execution commit. Original item/run payloads are untouched. Exact core recording allowance is 6m45s; this is not a verified total interaction burden. Pilot actual use before committing to a burden estimate.

The next current observation follows reading, AI explanations, external lookups and app practice. It cannot be labelled pre-app or a complete-volume assessment unless those conditions hold. Before-volume samples only cover prospectively chosen volumes. Generic cues stay fixed; volume coverage can differ. Fixed cues may themselves rehearse retrieval; report repeated assessment exposure.

Additive SQLite tables: `study_assessments` and `study_audio_attempts`; canonical operations remain under `curriculum_db.study_action`. Assessment metadata links to `study_runs`, frozen prompts and standard durable events/audio/transcriptions. A capture attempt is generated at record start, preserved through local storage/upload and linked to server audio/hash. Upload is acknowledged before removing the local retry copy. Legacy upload clients remain supported without retrospectively inventing attempt identity. Concurrent attempt retries are serialized.

Comparison tool (server export first):

```sh
python3 scripts/reading_study_assessment_report.py --export PRIVATE_EXPORT --out NEW_PRIVATE_REPORT.md
```

It aligns actual recorded/transcribed answers by volume and prompt. It produces no simulated learner answers, no inferred scores and no fabricated before/after improvement. A scorer should independently inspect audio-critical ambiguities and source-check historical claims, retain historical dates in speech while hiding occasion metadata, and keep all score revisions. No automatic scoring is active.

Reading recordings may include verbatim book text: keep them and their source excerpts private; publication requires separately selected permissible excerpts. The user's own assessment material still needs a publication selection/privacy pass. No raw recording is made public by this release.

Still separate work: fresh-context application, independent backup destination/restore, visual grounding and the incremental intake loop. No reminder is activated by this document.

Validation before release: 28 isolated Python study checks, 11 focused client checks and TypeScript passed. At 390×844, local browser verified narrative-first navigation, explicit missingness, confidence before recording and no answer reveal. Real iPhone microphone/upload remains to be verified by a genuine recording.
