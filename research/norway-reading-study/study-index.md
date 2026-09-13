# Norway study: documentation and evidence index

Updated 13 September 2026. Start here when resuming this project. The latest user
clarifications are in [decisions.md](decisions.md); historical assistant analyses
are evidence of the conversation, not authoritative descriptions of the learner.

## Current understanding

Read all twelve volumes for connected historical understanding, chronological
orientation and familiarity with concepts/terms that makes future reading easier.
Recording is continuous with the book open. Speech often quotes the book verbatim,
including its summaries. Neither summary-like wording nor fluent speech establishes
reader synthesis, comprehension or retention. Unknown authorship stays unknown.
Recognition and a rough conceptual association can be a sufficient learning goal;
precise definition recall is optional and should earn its extra effort.

## Find the record

| Record | Where | Status / purpose |
|---|---|---|
| Current protocol | [README.md](README.md) | Living, version-controlled statement of method |
| Decisions and corrections | [decisions.md](decisions.md) | Dated entries; distinguish user decisions from assistant proposals |
| Concepts and terms | [concepts.md](concepts.md) | Recognition-oriented goals, candidate terms and evidence rules |
| Analysis of baseline/notes | [analysis-2026-09-12.md](analysis-2026-09-12.md) | Claims audited after the quotation clarification |
| Prospective interventions | [experiment-log.md](../experiment-log.md) | Append-only; register changes before applying them |
| Initial audio batch | [first-batch.md](first-batch.md) | Durations, ASR versions, disputes and target proposals |
| Private study hub | [Private README](/Users/stian/.agents/research/petrarca-norway-study/README.md) | Audio, conversations, source annotations and current local paths |
| Conversations | [Archive index](/Users/stian/.agents/research/petrarca-norway-study/conversations/README.md) | Searchable message text, stable source-line IDs, timestamps and hashes |

## Conversation coverage

The registered sources are Claude session `2a532c86-bc04-48ca-a9d3-2a0b123545fb`
(10 September) and Codex task `01a0968c-5d4b-72c2-9d80-10bbdb0488b5`
(12 September onward). On 13 September a search of the local Petrarca Claude
JSONL logs for Aschehoug/Norgeshistorie/study-name terms found only that Claude
session. This is bounded discovery, not proof that no other discussion exists.
Claude web, other devices, other task histories and forum publication are not
verified as covered. Do not claim that every historical or future chat is saved.

Snapshot `d18f4c30d8690197` contains 73 user/assistant message records (38 Claude,
35 Codex), through the user's 13 September clarification and
progress replies before this turn's final response.
It preserves the earlier analysis at `codex-20260912-L653` and the correction
request at `codex-20260912-L663`. Original log timestamps are UTC; audio offsets
and local dates are distinct. Source-line IDs refer to registered append-only
logs; source-prefix and text hashes let a later export detect changed evidence.

The archive omits tool payloads, reasoning, system/developer instructions,
environment/plugin packets, machine task notifications and image bytes. This
avoids calling machine notifications user testimony and copying credentials in
tool logs. Textual attachment references remain. It is a conversation-text archive,
not a raw backup of all application state. Snapshots do not retroactively absorb
later messages; `conversations/current.json` identifies the newest export.

## Topic index

| Topic | Conversation/source anchor | Current interpretation |
|---|---|---|
| Why twelve volumes / overview | `claude-20260910-L11` | Initial project purpose |
| Timing, selection, worldwide chronology, language and trade | `codex-20260912-L317` | User goals, not inferred preferences |
| Continuous open-book recording | `codex-20260912-L385` | User confirmation; supersedes chapter-end capture proposal |
| Initial knowledge and questions | English baseline journal `QeF0kKB-QEJN` | Separate pre-reading observation; no retroactive correction |
| Assistant interpretation of reading | `codex-20260912-L653` | Original preserved; see correction C001 |
| Verbatim reading and book summaries | `codex-20260912-L663` | Unknown authorship; no synthesis inference |
| Concepts, terms and easier future reading | `codex-20260912-L663` | Explicit learning goal in parallel with chronology |
| Book-like summary misattributed to reader | farming s009, 03:26–04:03 | Authorship unresolved; original synthesis attribution withdrawn |
| Periodization difficulty | hunters s034–s035; farming s018–s019 | Apparent expressed difficulty; mixed passages require scoped interpretation |

## Maintenance at every study handoff

1. Add newly identified relevant conversations to the private source registry;
   explicitly record discovery scope and inaccessible sources.
2. Refresh the conversation snapshot using the command below. Record its coverage;
   do not imply the yet-unsent final response is already included.
3. Append new user decisions, assistant proposals, corrections and unresolved
   questions with stable IDs and source references. Keep superseded entries.
4. Update the protocol and affected derived indexes. Never rewrite original
   recordings, prior transcript versions, analyses or measurements to match a
   later interpretation. Point corrected versions back to the originals.
5. Link new research from this index and record the code/data versions used.

```sh
python3 scripts/reading_study_conversations.py \
  --registry /Users/stian/.agents/research/petrarca-norway-study/conversation-sources.json \
  --out /Users/stian/.agents/research/petrarca-norway-study/conversations
```

This is an implemented, manually invoked exporter and a documented handoff
procedure. There is no background collector or guarantee that an unrelated future
task follows it. Private evidence currently lives on this Mac; off-device backup
has not been verified. Git commits preserve the protocol/tools, not raw speech.
