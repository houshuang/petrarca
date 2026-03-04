# Book Reader Walkthrough: The Arabic-Latin Bridge

*Simulated user journey through 4 books over 6 weeks, grounded in the reading cluster at `reading-clusters/arabic-latin-bridge.md` and the implementation at `app/app/book-reader.tsx`.*

---

## The Setup

Stian has four EPUBs ready:

| # | Book | Author | ~Words | Status |
|---|------|--------|--------|--------|
| 1 | *Mahomet et Charlemagne* | Pirenne | 95K | Unread (has EPUB) |
| 2 | *The Arabic Role in Medieval Literary History* | Menocal | 87K | Unread |
| 3 | *Arabic into Latin in the Middle Ages* | Burnett | 168K | Unread |
| 4 | *In Good Faith* | Gilbert | 142K | **30% read on Kindle** |

Total: ~492,000 words across 4 books. The cluster document identifies 6 cross-book themes: Mediterranean unity/rupture, translator identities, what was translated, Toledo, anxiety of influence, disciplinary blind spots.

### The Kindle Wrinkle

Gilbert's *In Good Faith* is 30% read on Kindle. That means Stian has read the Introduction ("The Arabic Voices of Imperial Spain") and Chapter 1 ("Morisco Spain — foundations of fiduciary translation"), roughly 50K words. He has highlights and notes from those chapters. **The system should recognize this.**

With Readwise integration, Kindle highlights can be pulled in. The ingestion pipeline should:
1. Process all 5 chapters + intro + epilogue into sections
2. Mark Introduction and Ch 1 sections as having prior engagement (via Readwise highlight matching)
3. Generate briefings that reference his existing highlights: "You highlighted this passage about fiduciary translation in your Kindle reading..."

---

## Day 0: Ingestion

### What happens on the server

Stian runs the ingestion from his phone (or SSH into the Hetzner VM):

```
POST /ingest-book {"path": "~/Downloads/pirenne_mahomet.epub"}
POST /ingest-book {"path": "~/Downloads/The Arabic Role...epub"}
POST /ingest-book {"path": "~/Downloads/Arabic into Latin...epub"}
POST /ingest-book {"path": "~/Downloads/In Good Faith...epub"}
```

The `ingest_book_petrarca.py` pipeline processes each book:

**Pirenne** (~95K words, French):
- pymupdf extracts TOC: Part I (5 chapters) + Part II (4 chapters) = 9 chapters
- Each chapter (~10K words) splits into 2-4 sections at H2/H3 boundaries
- Result: ~25 sections, each 3-5K words (6-10 min read)
- Gemini Flash extracts per section: summary, 3-5 claims, 2-4 key terms
- Language: French. Summaries/briefings generated in English with French terms preserved.

**Menocal** (~87K words, English):
- 6 chapters + afterword
- Chapters split into 2-3 sections each
- Result: ~17 sections, each ~5K words (8-12 min read)
- Literary analysis — claims are interpretive (e.g., "troubadour poetry derives from Arabic muwashshaḥāt forms")

**Burnett** (~168K words, English, collected essays):
- 9 self-contained essays, each IS a natural section
- Some long essays (>18K words) split into 2-3 subsections
- Result: ~15 sections (variable: 8-20K words each)
- Special handling: each essay has addenda/corrigenda that should be merged
- Technical/scholarly — claims are more factual, heavily cited

**Gilbert** (~142K words, English):
- Introduction + 5 chapters + Epilogue = 7 units
- Each chapter ~25K words, splits into 3-5 sections
- Result: ~22 sections
- **Cross-matching detects connections to the other 3 books** (Toledo, translators, Mediterranean, Arabic influence)

### Cross-book matching at ingestion

After all 4 books are processed, the cross-matching pass runs:

```
Pirenne §I.2 claim: "Mediterranean trade continued uninterrupted through Germanic invasions"
  ↔ Gilbert §Intro.1 claim: "Arabic remained embedded in Spanish institutions long after political 'rupture'"
  Relationship: EXTENDS (both argue for continuity despite apparent breaks)

Menocal §3.1 claim: "Troubadour poetry originated from Arabic muwashshaḥāt forms"
  ↔ Burnett §VII.2 claim: "Toledo's translation program was coherent and deliberate"
  Relationship: SAME_TOPIC (both discuss Toledo as cultural hinge)

Pirenne §II.3 claim: "Islam broke Mediterranean unity, forcing Europe northward"
  ↔ Menocal §1.1 claim: "The myth of Western literary autonomy erases Arabic contributions"
  Relationship: DISAGREES (rupture thesis vs. continuity thesis)
```

The pipeline generates ~40-60 cross-book connections total. Each section's briefing incorporates relevant connections.

### Output served via nginx

```
/opt/petrarca/data/books/pirenne-mahomet/meta.json
/opt/petrarca/data/books/pirenne-mahomet/ch1_sections.json
/opt/petrarca/data/books/pirenne-mahomet/ch2_sections.json
...
/opt/petrarca/data/books/menocal-arabic-role/meta.json
...
/opt/petrarca/data/books.json  (array of Book metadata for all 4)
```

`manifest.json` updated with new `books_hash`.

---

## Day 1: First Open — The Shelf Appears

### App sync

Stian opens the app. `checkForUpdates()` detects the new `books_hash` → downloads `books.json` (4 books' metadata). The Library tab now has a "Shelf" toggle.

### What Stian sees: Library → Shelf

```
┌─────────────────────────────────────┐
│ [Recent] [By Topic] [Shelf] [High…] │
├─────────────────────────────────────┤
│                                     │
│ ── Arabic-Latin Transmission ───── │
│   📖 Mahomet et Charlemagne        │
│      Pirenne · 0% · 25 sections    │
│   📖 The Arabic Role in...         │
│      Menocal · 0% · 17 sections    │
│   📖 Arabic into Latin in...       │
│      Burnett · 0% · 15 sections    │
│   📖 In Good Faith                 │
│      Gilbert · 32% · 22 sections   │
│      ▓▓▓▓▓▓▓░░░░░░░░░░░░░░        │
│                                     │
│   📰 "Modica's Baroque Heritage"   │
│   📰 "Sicily Norman Architecture"  │
│                                     │
│ ── Medieval History ─────────────── │
│   📖 Mahomet et Charlemagne        │
│      (also in Arabic-Latin...)      │
│   📰 3 articles                    │
│                                     │
└─────────────────────────────────────┘
```

**Key observations**:
- Books are grouped by **topic**, not by book. "Arabic-Latin Transmission" is a topic shared by all 4 books.
- Gilbert shows 32% because her Introduction + Ch 1 are marked as previously read (from Kindle/Readwise data).
- Articles from the Sicily exploration appear alongside book sections under shared topics.
- The topic grouping is the primary organizing principle — Stian doesn't think "I want to read Burnett," he thinks "I want to explore Arabic-Latin transmission."

### Tapping into a book: The Briefing

Stian taps Pirenne. He gets the **book landing page** (the first section of Ch 1):

```
┌─────────────────────────────────────┐
│ ← Mahomet et Charlemagne            │
│    Henri Pirenne, 1937               │
│                                      │
│ ╔═══════════════════════════════════╗ │
│ ║ WHAT YOU BRING                    ║ │
│ ║                                   ║ │
│ ║ You've read Gilbert's intro +     ║ │
│ ║ Ch 1 on Kindle. She references    ║ │
│ ║ Pirenne's rupture thesis — this   ║ │
│ ║ is the original argument.         ║ │
│ ║                                   ║ │
│ ║ Your 3 Sicily articles touch on   ║ │
│ ║ Mediterranean trade — Pirenne's   ║ │
│ ║ central theme.                    ║ │
│ ╚═══════════════════════════════════╝ │
│                                      │
│ THESIS                               │
│ "Sans l'Islam, l'empire franc        │
│ n'aurait sans doute jamais existé."  │
│ Islam created the conditions for     │
│ Charlemagne's empire by breaking     │
│ Mediterranean unity.                 │
│                                      │
│ ─── Chapters ─────────────────────── │
│ I.1  Roman Commerce (3 sections)     │
│      ●○○                             │
│ I.2  Eastern Influence (3 sections)  │
│      ○○○                             │
│ I.3  ...                             │
│                                      │
│ [Start with Part I, Chapter 1 →]     │
└─────────────────────────────────────┘
```

**The "What You Bring" box** is the key innovation. It doesn't just show the book in isolation — it connects to everything Stian has already read. This is the "hooks" principle from the design vision: new knowledge has somewhere to land.

---

## Day 1-3: Reading Pirenne, Part I

### Session 1: Pirenne I.1.1 — "Le commerce dans l'empire romain" (8 min)

Stian taps "Start with Part I, Chapter 1." The book reader opens to section 1 of chapter 1.

**Briefing zone** (visible first):
```
BRIEFING — Pirenne I.1 §1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pirenne opens with a sweeping claim: Roman commercial
unity survived the Germanic invasions intact. Trade
routes, currency, and cultural exchange continued
from the 4th through 7th centuries.

This matters because: The standard narrative says
the Germanic invasions ended the Roman world. Pirenne
says no — it was Islam. Everything in Part I builds
this case.

🔗 CONNECTS TO:
📖 Gilbert, Intro §1 — She cites Pirenne's
   continuity argument as background for her
   own thesis about Arabic persistence in Spain.
   "You highlighted: 'the long afterlife of
   Arabic in Christian Spain'"
```

Stian reads the briefing (~30 seconds), then scrolls down to **Claims**:

```
KEY CLAIMS  (4 claims)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

M1: Roman Mediterranean trade continued through
    the 5th-7th centuries despite Germanic
    political fragmentation.

    Source: "Le commerce qui s'exerçait dans
    l'Empire romain..."

    [Knew this] [New to me] [Save]

    🟣 Compare: Gilbert argues trade patterns
       persisted even into the 16th century
       (In Good Faith, Ch 3 §2)

S1: Papyrus imports from Egypt prove continued
    Eastern Mediterranean contact.

    [Knew this] [New to me] [Save]
```

Stian taps "New to me" on M1 (he'd read about this generally but not Pirenne's specific evidence). Taps "Knew this" on S1 (he remembers papyrus as an indicator from somewhere). These signals update the knowledge model:
- Concepts related to "Pirenne thesis" → encountered
- Concepts related to "Mediterranean trade" → known (because he already had hooks from Gilbert)

**Key Terms zone**:
```
KEY TERMS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pirenne thesis — The argument that Islamic
expansion, not Germanic invasions, ended the
ancient world by closing the Mediterranean.
⚠️ Menocal challenges this thesis — she
argues Arabic culture flowed INTO Europe
continuously (Ch 1 §1).

Translatio imperii — Transfer of political
authority from one empire to another. Pirenne
traces it from Rome → Franks.
```

The "⚠️ Menocal challenges" note is a cross-book connection. Stian hasn't read Menocal yet, but the system is planting a seed — when he does read Menocal, the connection will be explicit.

**Full Text zone**: The actual French text with English glosses. Stian scrolls through, highlights a passage about Syrian traders in Gaul.

**Section completion**: After reaching the bottom, a small card appears:
```
┌─────────────────────────────────────┐
│ ✓ Section complete · 8 min          │
│                                     │
│ Pirenne argues Roman trade survived │
│ Germanic invasions — papyrus and    │
│ Syrian merchants prove continuity.  │
│                                     │
│ [Add a thought...] [Voice note 🎤] │
│                                     │
│ [→ Next: I.1 §2 "Les commerçants"] │
└─────────────────────────────────────┘
```

Stian records a voice note: "The papyrus argument is clever — physical evidence of trade routes. I wonder if Burnett has evidence from the translation side."

Voice note → transcribed → matched to concepts → research agent triggered? The transcript mentions Burnett, which creates a connection intent. The system notes this for when Stian reads Burnett later.

### Session 2: Pirenne I.1.2 and I.1.3 (15 min on the commute)

The next morning on the commute, Stian opens the app. The feed shows his continue-reading state:

```
┌─────────────────────────────────────┐
│ Continue Reading                     │
│                                     │
│ 📖 Pirenne — I.1 §2                │
│    "Les commerçants syriens"        │
│    Next section · 6 min              │
│                                     │
│ 📖 Gilbert — Ch 2 §1               │
│    "Presidio families"              │
│    Resuming where Kindle left off   │
│    12 min                            │
└─────────────────────────────────────┘
```

He reads two more Pirenne sections. By section 3, the claims are becoming familiar — Pirenne is building his case brick by brick, and each section reinforces the same thesis (Roman continuity). Stian starts skipping claims and reading at section depth.

**What the system learns**: Stian engaged deeply with section 1 (signaled on all claims, recorded voice note, read full text). Sections 2-3 he read at claims/briefing depth only. The depth falloff is normal — the thesis is established, subsequent sections provide evidence. The system doesn't penalize this; it records the pattern and adjusts future briefings.

### Session 3: Pirenne I.2.1 — A new chapter (10 min, evening)

Chapter 2 ("Eastern Influence on the West") starts with a **chapter-level briefing**:

```
Chapter I.2: Eastern Influence on the West
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

THE ARGUMENT SO FAR (Chapter 1):
Pirenne established that Roman commercial networks
survived the Germanic invasions intact. Mediterranean
trade continued, Eastern goods flowed west, Syrian
and Jewish merchants operated freely.

WHAT'S COMING:
Chapter 2 shifts from trade to culture. Pirenne
argues Eastern (and specifically Greek/Byzantine)
intellectual influence persisted in the West through
the 7th century — monasteries, church architecture,
literary production all show Eastern DNA.

WHY THIS MATTERS:
This is the setup for Part II's bombshell: if all
this continuity persisted through the Germanic
invasions, then what actually ended it? Pirenne's
answer: Islam.
```

This chapter-level "argument so far" is critical for the reading experience. Books are different from articles — there's a developing argument that builds across chapters. Without this, a reader returning after a day might forget where the argument stands.

---

## Day 4-7: Entering Menocal

### The deliberate interleave

Stian has read Pirenne Part I (5 chapters, ~50K words). Before starting Part II, he's curious about Menocal's counter-argument — the cross-book connections in Pirenne's briefings kept mentioning her.

He opens the Shelf, taps Menocal:

```
┌─────────────────────────────────────┐
│ ← The Arabic Role in Medieval       │
│   Literary History                   │
│   María Rosa Menocal, 1987           │
│                                      │
│ ╔═══════════════════════════════════╗ │
│ ║ WHAT YOU BRING                    ║ │
│ ║                                   ║ │
│ ║ You've read Pirenne's Part I —    ║ │
│ ║ his case for Roman continuity     ║ │
│ ║ through Germanic invasions.       ║ │
│ ║ Menocal starts where Pirenne is   ║ │
│ ║ weakest: she asks what happened   ║ │
│ ║ to the Arabic contribution to     ║ │
│ ║ the West, which Pirenne ignores.  ║ │
│ ║                                   ║ │
│ ║ Your voice note from Pirenne I.1: ║ │
│ ║ "I wonder if Burnett has evidence ║ │
│ ║ from the translation side"        ║ │
│ ║ — Menocal covers the literary     ║ │
│ ║ side of that same question.       ║ │
│ ╚═══════════════════════════════════╝ │
│                                      │
│ THESIS                               │
│ European literary history has         │
│ systematically erased its Arabic      │
│ origins. Troubadour poetry, Dante,    │
│ courtly love all have Arabic roots.   │
│                                      │
│ [Start with Chapter 1 →]             │
└─────────────────────────────────────┘
```

**The critical moment**: The briefing references Stian's own voice note from Pirenne. This is the personal thread working — his spoken thought 3 days ago is now context for his next reading. The system connects his curiosity to the available content.

### Menocal Ch 1 §1 — "The Myth of Westernness"

```
BRIEFING — Menocal Ch 1 §1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Menocal's opening chapter is a direct attack on
the disciplinary assumption that Western literature
developed independently. She argues this is a modern
construction — medieval scholars knew better.

⚡ KEY TENSION WITH PIRENNE:
Pirenne claims Islam "broke" Mediterranean unity.
Menocal argues the opposite for literature: Arabic
culture didn't break Western literary tradition,
it CREATED it. You'll see this tension develop
across both books.

The Eco epigraph sets the tone: "the Arab Averroes
almost convinced everyone" — the threat that Arabic
philosophy might be right.
```

Stian reads this section in 10 minutes. The claims are powerful:

```
M1: The standard narrative of Western literary
    autonomy is a modern invention, not a
    medieval reality.

    Source: "The myth of a Western literary
    tradition developing in isolation..."

    [Knew this] [New to me] [Save]

    🟣 TENSION: Pirenne's thesis assumes a rupture
       that Menocal denies ever existed at the
       literary level. (Pirenne II.1 §1)

    🟣 EXTENDS: Gilbert documents how Arabic
       continued in Spanish institutions centuries
       after the supposed "reconquest."
       (In Good Faith, Intro §2)
```

Stian taps "New to me" on M1 — he knew vaguely about Arabic influence on European literature but hadn't encountered this specific historiographic argument.

He records a voice note: "Menocal is making me rethink Pirenne. He's good on trade evidence but completely ignores cultural transmission. Is this a blindspot of economic history?"

This voice note is gold for the personal thread. It captures a **cross-book synthesis moment** that the system can surface later.

### The interleaved week

Over days 4-7, Stian reads:
- Menocal Ch 1 and Ch 2 (the Andalusian background)
- Pirenne Part II, Ch 1 (Islam enters the picture)
- Menocal Ch 3 (courtly love and Arabic origins)

He's reading two books simultaneously, alternating based on interest and time available. The system supports this naturally — each section is self-contained with a briefing that restores context.

**What the knowledge model looks like at day 7**:

| Concept | State | Source Books |
|---------|-------|-------------|
| Pirenne thesis | Known | Pirenne, Menocal, Gilbert |
| Mediterranean trade continuity | Known | Pirenne |
| Arabic literary influence | Encountered | Menocal |
| Troubadour-muwashshaḥāt connection | Encountered | Menocal |
| Convivencia | Encountered | Menocal |
| Fiduciary translation | Known | Gilbert (Kindle) |
| Translation movement (Toledo) | Encountered | Menocal, Gilbert |

The knowledge model is building across books. "Pirenne thesis" is now "known" because Stian has engaged with it from three angles — Pirenne's own argument, Menocal's critique, and Gilbert's extension.

---

## Week 2: Burnett and the Mechanics of Transmission

### Why Burnett now?

Stian's voice note from Pirenne ("I wonder if Burnett has evidence from the translation side") was captured. The shelf now shows:

```
Continue Reading
📖 Pirenne — II.2 §1 (3 days ago)
📖 Menocal — Ch 4 §1 (yesterday)

Suggested Next:
📖 Burnett — Essay III: "Adelard of Bath"
   Your question from Pirenne I.1:
   "evidence from the translation side"
   Burnett provides exactly this — named
   translators with specific manuscripts.
```

The system doesn't just track reading order — it connects the reader's expressed curiosity to available content. This is the research agent pattern applied to the book shelf.

### Burnett's collected essays: A different reading pattern

Burnett's book is 9 self-contained essays, not a continuous narrative. The section reader handles this differently:

```
BRIEFING — Essay III: "Adelard of Bath"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Burnett profiles Adelard of Bath (1080-1152),
an English natural philosopher who traveled to
Antioch and Sicily to learn Arabic. He translated
Euclid's Elements and al-Khwārizmī's astronomical
tables from Arabic to Latin.

WHERE THIS FITS:
- Pirenne argued trade connected East and West.
  Adelard IS that connection, embodied in a person.
- Menocal argued literary influence was anonymous.
  Burnett shows the scientific transmission had
  specific, named translators.

🔗 CONNECTS TO:
📖 Pirenne I.1 — Mediterranean trade routes that
   made Adelard's travel possible
📖 Menocal Ch 2 — The Andalusian intellectual
   world Adelard encountered
📖 Gilbert Ch 2 — Much later translators in
   military outposts (similar to Adelard's
   Crusader-era Antioch)
```

Stian reads the essay in one sitting (20 min). The claims are factual and specific:

```
M1: Adelard of Bath translated Euclid's Elements
    from Arabic, not from the original Greek.

    Source: "Adelard's version of the Elements..."

    [Knew this] [New to me] [Save]

    KEY TERM: al-Khwārizmī — The mathematician
    whose name gives us "algorithm." Adelard
    translated his astronomical tables.
    ⚠️ Different from Menocal's literary Averroes —
    same cultural encounter, different domain.
```

The "⚠️ Different from" annotation is a definitional tension — the key term "Arabic scholarship" means literary philosophy to Menocal but mathematical science to Burnett. Both are part of the same cultural encounter, but from different disciplinary angles.

### Cross-book synthesis starts forming

By the end of week 2, Stian has read across 3 books (Pirenne Part I + half of II, Menocal Ch 1-4, Burnett Essays III, IV, VII). The system generates a **topic-level synthesis**:

```
┌─────────────────────────────────────┐
│ 🟣 SYNTHESIS: Translation Movement  │
│    3 books · 14 sections read       │
│                                     │
│ Three very different views of the   │
│ same phenomenon:                    │
│                                     │
│ Pirenne sees TRADE as the medium    │
│ of cultural exchange — papyrus,     │
│ gold, Syrian merchants.             │
│                                     │
│ Menocal sees LITERATURE as the      │
│ medium — poetry forms, narrative    │
│ conventions, courtly love ideology. │
│                                     │
│ Burnett sees NAMED TRANSLATORS as   │
│ the medium — Adelard, Michael Scot, │
│ the Johns of Seville.              │
│                                     │
│ YOUR THREAD: "Is this a blindspot   │
│ of economic history?" (voice note,  │
│ day 5). All three answer yes — but  │
│ from different directions.          │
│                                     │
│ UNRESOLVED: Does Pirenne's "rupture"│
│ thesis hold up against Burnett and  │
│ Menocal's evidence of continuity?   │
│ You haven't finished Pirenne Part II│
│ yet — his argument about Islam may  │
│ change the picture.                 │
│                                     │
│ [Continue with Pirenne Part II →]   │
└─────────────────────────────────────┘
```

This synthesis:
1. Weaves across 3 books' claims
2. References the reader's own voice note
3. Identifies an unresolved tension
4. Suggests what to read next to resolve it

This is the "scaffolding, not counting" principle from the honest assessment. The system isn't telling Stian "you know 47% of medieval history concepts." It's telling him the state of an ongoing intellectual conversation across his reading.

---

## Week 3: Gilbert — The Kindle Reunion

### Context restoration after a break

Stian hasn't opened the book reader for 3 days (busy week). When he opens the app:

```
┌─────────────────────────────────────┐
│ 🔖 Pick up where you left off       │
│                                     │
│ 📖 Pirenne — Part II, Ch 2 §1      │
│    "L'expansion de l'Islam"         │
│    3 days ago · You were exploring  │
│    how Islam changed Mediterranean  │
│    trade                            │
│                                     │
│ 📖 Menocal — Ch 4 §1               │
│    "The muwashshaḥāt"              │
│    5 days ago · The hybrid          │
│    Arabic-Romance poetry forms      │
│                                     │
│ 📖 Burnett — Essay VII              │
│    "Toledo Translation Program"     │
│    4 days ago · The coherence of    │
│    the 12th-century program         │
│                                     │
│ 📖 Gilbert — Ch 2 §1 [NEW]         │
│    "Presidio families"              │
│    Continues from your Kindle       │
│    reading · 12 min                 │
└─────────────────────────────────────┘
```

The amber "pick up where you left off" banner shows 4 options. Gilbert Ch 2 is marked [NEW] because Stian hasn't read it in the app yet — but the system knows he finished Ch 1 on Kindle.

### Gilbert Ch 2: Building on Kindle reading

Stian taps Gilbert Ch 2 §1. The briefing is rich because it can reference his Kindle highlights:

```
BRIEFING — Gilbert Ch 2 §1: "Presidio Families"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You read the Introduction and Chapter 1 on Kindle.
Your highlights from Ch 1:
  • "Fiduciary translation was never merely
    linguistic — it was a legal and political act"
  • "The romanceador occupied a unique social
    position between Arabic and Spanish worlds"

Chapter 2 extends the story to MILITARY contexts.
The "presidio families" are translation dynasties
in Mediterranean frontier outposts — families where
Arabic/Spanish bilingualism was inherited and
professionalized.

🔗 CONNECTS TO:
📖 Burnett Essay III — Adelard of Bath was a
   solo scholar-translator. Gilbert's presidio
   translators are family businesses — translation
   as inherited craft, not individual adventure.
📖 Pirenne II.1 — The Mediterranean military
   outposts Gilbert describes exist in the
   commercial geography Pirenne mapped.
```

**The Kindle highlight integration** is the killer feature here. Stian's own words from Kindle reading appear as context for the next chapter. He didn't have to do anything — the Readwise → Petrarca pipeline pulled his highlights automatically.

### The fiduciary translation concept

Gilbert's key concept — "fiduciary translation" — appears across multiple sections. The key terms zone tracks how she develops it:

```
KEY TERM: Fiduciary translation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ch 1 definition: Translation as an act of trust
between parties, carrying legal weight.

Ch 2 evolution: In presidio contexts, fiduciary
translation becomes hereditary — families entrusted
with translation across generations.

⚠️ CONTRAST with Burnett: Burnett's translators
are scholars working on TEXTS. Gilbert's are
translators working on PEOPLE and INSTITUTIONS.
Same word ("translation"), different social function.

YOUR HIGHLIGHT (Kindle, Ch 1): "Fiduciary
translation was never merely linguistic"
```

The system tracks how an author's key term evolves across chapters — this is the "argument tracking" feature that no existing reading app provides.

---

## Week 4-5: The Cross-Book Argument

### The Toledo convergence

All four books converge on Toledo. By week 4, Stian has read:
- Pirenne's argument about Mediterranean trade routes (the world Toledo existed in)
- Menocal's literary culture of Andalusia (Toledo as cultural capital)
- Burnett's Essay VII: "The Coherence of the Toledo Translation Program" (the mechanics)
- Gilbert's Ch 1 and Ch 5: Toledo's afterlife in early modern Spain

The topic synthesis for "Toledo" is now a substantial document:

```
┌─────────────────────────────────────┐
│ 🟣 SYNTHESIS: Toledo                │
│    4 books · 8 sections · 3 voice   │
│    notes · 2 Kindle highlights      │
│                                     │
│ Toledo as civilizational hinge:     │
│                                     │
│ PIRENNE: Toledo existed because     │
│ Mediterranean trade survived the    │
│ Germanic invasions. The commercial  │
│ infrastructure made cultural        │
│ exchange possible.                  │
│                                     │
│ MENOCAL: Toledo was where Arabic    │
│ literary culture became European    │
│ literary culture. Multilingual      │
│ poets, Jewish intermediaries,       │
│ bilingual courts.                   │
│                                     │
│ BURNETT: Toledo's translation       │
│ program was "coherent and           │
│ deliberate" — not random scholars   │
│ but an organized effort to transfer │
│ Arabic scientific knowledge.        │
│                                     │
│ GILBERT: Toledo's legacy continued  │
│ into the 16th century. The "end"    │
│ of the translation era was a myth.  │
│                                     │
│ YOUR THREAD:                        │
│ Voice note (day 5): "Is this a      │
│ blindspot of economic history?"     │
│ Voice note (day 12): "Burnett gives │
│ the specific names and manuscripts  │
│ that Menocal says were erased"      │
│ Kindle highlight: "Fiduciary        │
│ translation was never merely        │
│ linguistic"                         │
│                                     │
│ TENSION: Pirenne says Islam broke   │
│ the Mediterranean. The other three  │
│ argue it never really broke —       │
│ translation, literature, and legal  │
│ practice all continued. The answer  │
│ may be "both": political rupture    │
│ AND intellectual permeability.      │
│                                     │
│ BLIND SPOTS:                        │
│ - Pirenne ignores cultural exchange │
│ - Menocal ignores the economics    │
│ - Burnett focuses narrowly on      │
│   science, missing literature      │
│ - Gilbert focuses on Spain, missing│
│   Sicily, Southern Italy, Antioch  │
│                                     │
│ WHAT'S NEXT:                        │
│ - Finish Pirenne Part II to see     │
│   his "rupture" argument in full    │
│ - Menocal Ch 5: Dante and Arabic    │
│   philosophy — the anxiety of       │
│   influence at its most intense     │
│ - Burnett Essay VIII: Michael Scot  │
│   at Frederick II's court — Toledo  │
│   to Sicily connection              │
└─────────────────────────────────────┘
```

This synthesis is the payoff of the entire system. It:
- Weaves 4 books' arguments into a coherent narrative
- Incorporates the reader's own voice notes and highlights
- Identifies tensions and blind spots
- Suggests what to read next to deepen understanding

### Review tab: Book concepts

By week 4, book concepts are appearing in the review queue:

```
REVIEW — 6 concepts due
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Pirenne thesis
   Encountered in: Pirenne I.1, Menocal Ch 1,
   Gilbert Intro
   Your voice note: "Menocal is making me rethink
   Pirenne..."

   How does your understanding of the Pirenne
   thesis differ now from when you first read it?

   [Confused] [Fuzzy] [Solid] [Could teach]

2. Fiduciary translation
   From: Gilbert Ch 1-2 (Kindle + app)
   Your highlight: "never merely linguistic"

   How does fiduciary translation compare to
   the scholarly translation Burnett describes?
```

Book concept reviews are richer than article concept reviews because:
- They reference multiple books (cross-book encounters)
- They include the reader's own voice notes and highlights
- The prompts are specific, not generic ("How does X compare to Y?" not just "How does this connect?")
- 14-day initial intervals (longer than article concepts) because book knowledge is deeper

---

## Week 6: Book Completion and Reflection

### Finishing Pirenne

Stian finishes Pirenne's Part II. The **book completion synthesis** fires:

```
┌─────────────────────────────────────┐
│ ✓ Completed: Mahomet et Charlemagne │
│   Henri Pirenne, 1937               │
│   25 sections · 12 hours · 4 weeks  │
│                                     │
│ THE FULL ARGUMENT:                  │
│ Pirenne argued that Germanic         │
│ invasions did NOT end the ancient   │
│ world — Mediterranean trade and     │
│ cultural exchange continued. It was │
│ Islam's expansion in the 7th-8th    │
│ centuries that closed the           │
│ Mediterranean, forced Europe        │
│ northward, and created the          │
│ conditions for Charlemagne's empire.│
│                                     │
│ YOUR JOURNEY:                       │
│ - 3 voice notes recorded            │
│ - 12 claims signaled "new to me"    │
│ - 8 claims "knew this" (growing     │
│   familiarity with the thesis)      │
│ - 5 highlights saved                │
│                                     │
│ KEY EVOLUTION:                      │
│ Your early voice note questioned    │
│ whether Pirenne's economic focus    │
│ was a "blindspot." By Part II, you  │
│ saw that Pirenne DOES acknowledge   │
│ cultural factors, but weights them  │
│ less than trade. Menocal and        │
│ Burnett provide the evidence he     │
│ lacks.                              │
│                                     │
│ CROSS-BOOK POSITION:               │
│ Of Pirenne's 47 main claims:       │
│ - 12 are supported by Burnett      │
│ - 8 are challenged by Menocal      │
│ - 5 are extended by Gilbert         │
│ - 22 are unique to Pirenne          │
│                                     │
│ [Write a final reflection...]       │
│ [Continue with other books →]       │
└─────────────────────────────────────┘
```

This is the "synthesis over source" principle in action. The completion screen doesn't just summarize the book — it situates it within the reader's multi-book journey, incorporating their own voice notes and claim signals.

---

## What Makes This Different

### vs. Kindle/Apple Books
- Those apps track page position. Petrarca tracks **argument position** — where you are in the developing thesis, not just what page you're on.
- No cross-book connections. Each book is a silo.
- No briefings or claim extraction. You start each chapter cold.

### vs. Readwise Reader
- Readwise is excellent for highlights and annotations, but doesn't extract arguments or track developing theses.
- No cross-book synthesis — highlights are siloed per book.
- No "what you bring" briefings that connect prior reading to current sections.

### vs. LiquidText/MarginNote
- Those tools require manual annotation to create connections. Petrarca generates connections automatically from claim matching.
- Both are desktop-first. Petrarca is mobile-first with 5-15 min reading sessions.
- No argument tracking or thesis development visualization.

### vs. Obsidian/Roam (manual knowledge graphs)
- Those require the reader to build the graph manually. Petrarca builds it from reading signals.
- "The note-taking paradox" from user interviews: taking notes takes as long as reading. Petrarca's signals (claim buttons, voice notes, highlights) are 10x faster than writing notes.
- Obsidian/Roam don't schedule re-engagement. Petrarca's spaced attention system keeps knowledge alive.

### The unique combination
No existing tool does ALL of:
1. Break books into section-sized reading units
2. Extract claims and track arguments across chapters
3. Match claims across multiple books automatically
4. Generate briefings that connect current section to prior reading
5. Incorporate the reader's own voice notes and highlights into briefings
6. Schedule spaced re-engagement with book concepts
7. Generate cross-book synthesis that includes the reader's personal thread

---

## Assumptions and Risks

### What we're betting on

1. **Readers will actually read multiple books simultaneously on the same topic.** This is central to the design. If readers finish one book before starting another, cross-book connections happen too late.
   - *Evidence for*: The user explicitly describes reading "Pirenne, Huizinga, and Tuchman at the same time." Academic readers do this naturally.
   - *Evidence against*: Casual readers generally don't. This is a power-user feature.

2. **Section-level granularity is right for books.** Too fine (paragraphs) and the overhead of briefings/claims per section is excessive. Too coarse (chapters) and the 5-15 minute promise breaks.
   - *Evidence for*: The reading cluster analysis shows chapters are 10-25K words — too big for a session. Sections at 3-5K words match article length.
   - *Risk*: Some sections may be too small to stand alone (a 500-word subsection of a longer argument).

3. **Cross-book claim matching via word overlap is accurate enough.** The prototype uses the same Jaccard similarity as article concept matching.
   - *Evidence for*: Books on the same topic share substantial vocabulary. "Mediterranean trade," "Toledo translation," "Arabic influence" will match well.
   - *Risk*: False negatives for conceptual matches with different vocabulary ("Pirenne thesis" won't match "rupture of Mediterranean unity" at the word level).

4. **LLM-extracted claims faithfully represent the author's argument.** Gemini Flash does the extraction.
   - *Evidence for*: Claims are paired with source passages, so the reader can verify.
   - *Risk*: Nuanced academic arguments are easy to misrepresent. Pirenne's "Islam broke Mediterranean unity" is a simplification of a subtle, qualified argument.

5. **The briefing quality is high enough to be useful, not annoying.** Bad briefings would be worse than no briefings.
   - *Mitigation*: Briefings are the first thing the reader sees. If they're consistently wrong, the reader will learn to skip them. Log briefing dwell time to detect this.

### What we don't know yet

- **How many cross-book connections are genuinely useful vs. noise?** The pipeline might generate 60 connections, of which 15 are insightful, 30 are obvious, and 15 are false matches. We need reader signal on connections.
- **Does the personal thread (voice notes + highlights + claim signals) produce good synthesis input?** The synthesis quality depends on having enough reader signal. A reader who only taps "new to me" gives less than one who also records voice notes.
- **Is the Kindle highlight import reliable enough?** Readwise provides highlights, but matching them to specific book sections requires position mapping between Kindle locations and EPUB sections.

---

## Measurement Plan

| Question | How to measure | What validates |
|----------|---------------|----------------|
| Do users read multiple books simultaneously? | Track reading sessions across books within same week | >2 books with reading activity in any given week |
| Are briefings read or skipped? | Briefing zone dwell time | >10 seconds median dwell on briefings |
| Do cross-book connections get tapped? | `cross_book_connection_tap` event | >20% of shown connections are tapped |
| Do voice notes reference other books? | Transcript analysis for cross-book mentions | >30% of voice notes mention another book in the cluster |
| Does argument-so-far aid context restoration? | Time to first interaction after >2 day gap | <30 seconds from open to reading (vs. baseline) |
| Are section completion reflections written? | `section_reflection` events with text | >15% of completed sections get a text reflection |
| Does claim signaling taper off over sections? | Signal rate per section position | Rate stays >50% of section-1 rate through book |
| Is cross-book synthesis viewed? | `synthesis_viewed` events | >80% of generated syntheses are opened |

---

## Implementation Gaps to Address

Based on this walkthrough, the current implementation needs:

1. **Kindle highlight integration** — needs Readwise → section matching pipeline
2. **Book landing page** — the "What You Bring" briefing for the whole book (not just per-section)
3. **Chapter-level "argument so far"** — between chapters, not just per-section
4. **Topic-level cross-book synthesis** — the purple synthesis cards from articles, extended to books
5. **Personal thread surfacing in briefings** — voice notes from Book A appearing in Book B's briefings
6. **Book completion synthesis** — end-of-book reflection with cross-book position map
7. **"Suggested Next" in shelf** — using voice notes and reading patterns to recommend sections
8. **Key term evolution tracking** — how a term's definition changes across chapters/books
9. **Cross-book connection tappability** — tap a connection → navigate to the referenced section
10. **Reading journey views** — visualize the path through multiple books (which sections were read in what order)
