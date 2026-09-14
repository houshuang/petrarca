# Focused practice and data audit — 14 September 2026

The participant's iPhone screenshot showed setup controls and explanatory text crowding the current question. The new practice screen has a compact title/progress row and Valg. Session/topic selection, learning aids and overview entry are inside Valg. Revealed content survives opening and closing options. The persistent answer-mode controls and gate are removed under D017: practice is always closed-book; ordinary Tana reading capture remains open-book unless explicitly recall. No old event or schedule is changed.

A private immutable export (239 events through 09:02 Oslo) reconciles 20 completed cards / 17 distinct items / 25 graded parts (23 knew, 2 missed), 15 introductions, 0 study response audio and 0 overview assessments. No completion/schedule integrity discrepancy was found. The secondary interaction log agrees on terminal and answer events but incompletely mirrors lifecycle events.

Exposure logging is corrected prospectively: generic shown is separate from introduction_shown, which only fires once the definition is displayed, and both are paused when options hide the card. Events carry visible-card-v2. Ten old exposures have unknown response context; old introductions could precede definition display. Historical duration measurements are not active-learning time.

Knowledge scope: Traktbegerkulturen familiarity is positive while a specific Oslofjord/material-evidence connection was missed. Its dates have no separate observation. Missing dimensions are untested, never inferred from another grade. Six early completions still have their v1 long intervals; they are not evidence of proven month-long retention. See decisions D017–D018.

Private evidence and complete interpretation: `/Users/stian/.agents/research/petrarca-norway-study/audit-20260914/audit.md`. Reusable read-only checker: `scripts/reading_study_audit.py --export DIR --output NEW_FILE`. It verifies immutable manifest hashes and event/schedule consistency. It assumes a complete export including history. It never queries or mutates production.

Validation: 14 focused client interaction tests and TypeScript; read-only canonical export reconciliation, deliberately corrupted-copy checks for checksum and review-count detection; isolated phone-width browser inspection. The source screenshots and recordings are not copied into Git.
