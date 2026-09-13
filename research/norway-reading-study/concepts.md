# Concept and term familiarity

User goal, 13 September 2026: when encountering a term later, have at least a loose
concept of its meaning, so historical reading takes less effort and offers more
connections. This is a core goal alongside chronology, mechanisms and comparison.
It supersedes the first-batch implication that terms are merely optional enrichment.

## Desired depth is specific to each concept

| Dimension | Sufficient observation | What it does not prove |
|---|---|---|
| Familiarity | "I've encountered this" | Correct meaning |
| Rough meaning | A broad category, image, example or simple association | A precise definition or complete explanation |
| Contextual understanding | Interpret what the term means in a new sentence | Ability to retrieve its name unaided |
| Explanation/application | Explain an important distinction or use it in reasoning | All earlier knowledge is permanently retained |
| Name retrieval | Supply the label from a description when useful | Required success for every recognition-oriented target |

Record actual observations, cue format, answer exposure, date and source; do not
automatically promote between these dimensions. A multiple-choice success is a
recognition observation under those options, not free recall. Missing the name
does not invalidate understanding of a term encountered in prose.

## Candidate terms from the first batch

These are **encounters**, not established knowledge. The private
`concept-candidates-v1.json` carries source timestamps and intended depth; definitions
are pending source checking, not silently generated as authoritative answers.

| Family | Examples present in the recordings | First design direction |
|---|---|---|
| Landscape and settlement | marin grense, morenejord, sedimentær jord, heller | Simple image/rough meaning and relevance in a sentence |
| Material techniques | mikrolitt, flateretusjering, asbestmagring | Show what the operation/object is; one useful contrast |
| Agriculture and production | ard, avdrått, åkerrein, svibruk | Recognize the term and understand a passage using it |
| Archaeological labels | Nøstvetkultur, båndkeramikk, Traktbegerkultur, stridsøkskultur | Broad association and approximate context; avoid exhaustive taxonomies |
| Interpretive concepts | kulturdualisme, totemisme | Basic idea plus limits of applying the label to evidence |

Preserve Norwegian forms and useful synonyms or English equivalents when verified.
Recognition of one language's label does not establish recognition of all aliases.
Link a concept to multiple encounters rather than making a new item each time.

## Proposed companion behavior

- For an unfamiliar term: a short explanation or visual before any question.
- On a later encounter: optionally ask for a rough interpretation in context;
  accept wording that preserves the central idea rather than a dictionary definition.
- Offer deeper explanation for concepts that organize many later passages or
  matter to the user's interests. Keep low-cost familiarity available for others.
- Track spontaneous recognition in later reading when it is reported, and keep
  prompted practice distinct. "This made the paragraph easier" is a useful
  self-report; it is not an objectively measured reduction in cognitive load.

A companion could show "encountered here; intended goal: rough meaning" until
there is a real observation. It must not say "you know this" because the word
appears in a recording. These are documented design requirements; the app has
not yet implemented the new study introduction or observation paths.
