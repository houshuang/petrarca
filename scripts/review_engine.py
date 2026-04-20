#!/usr/bin/env python3
"""
Knowledge Review Engine — spaced retrieval practice from book chapters.

Manages a review_items table with simplified FSRS scheduling, maps book
chapters to curriculum nodes via LLM, and generates personalized
retrieval questions at review time using current knowledge state.
"""

import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from pathlib import Path

from claude_llm import call_claude, call_claude_json, call_claude_or_gemini, call_claude_search
from curriculum_db import load_curriculum, list_curricula, update_knowledge, load_knowledge_states

DATA_DIR = Path(os.environ.get('PETRARCA_DATA', '/opt/petrarca/data'))


def _log_voice_transcript(source: str, node_id: str, domain_id: str,
                          node_title: str, transcript: str, audio_bytes: int,
                          llm_result: dict, ml_triggered: list,
                          vt_id: str = None, input_mode: str = 'audio'):
    """Persist every voice transcript for later analysis. Returns the vt_id used.

    input_mode records how the transcript originally reached us so we can tell
    real audio captures apart from text-path ingests (which can be produced by
    agents or test harnesses). Values: 'audio' | 'text_json' | 'test'.
    """
    try:
        from db import get_connection
        conn = get_connection()
        if not vt_id:
            vt_id = f'vt_{int(time.time())}_{hash(transcript) % 10000:04d}'
        conn.execute(
            '''INSERT OR IGNORE INTO voice_transcripts
               (id, source, node_id, domain_id, node_title, transcript,
                audio_bytes, llm_result, microlearning_triggered, created_at, input_mode)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (vt_id, source, node_id, domain_id, node_title, transcript,
             audio_bytes, json.dumps(llm_result) if llm_result else None,
             json.dumps([m.get('id', m) for m in ml_triggered]) if ml_triggered else '[]',
             int(time.time() * 1000), input_mode),
        )
        conn.commit()
        conn.close()
        return vt_id
    except Exception as e:
        print(f'[voice-log] Failed to persist transcript: {e}', flush=True)
        return vt_id
SCRIPT_DIR = Path(__file__).parent
BOOK_RESEARCH_DIR = SCRIPT_DIR / 'data' / 'book_research'


# ── FSRS-6 scheduling (py-fsrs) ──────────────────────────────────────────────
from datetime import datetime, timezone
from fsrs import Scheduler as _FsrsScheduler, Card as FsrsCard, Rating as FsrsRating

_fsrs_scheduler = _FsrsScheduler(
    desired_retention=0.80,     # More aggressive than default 0.90
    learning_steps=(),          # Skip — daily review app, not per-minute
    relearning_steps=(),        # Skip — same reason
    enable_fuzzing=True,
    maximum_interval=3650,
)

SCORE_TO_FSRS = {
    'knew':   FsrsRating.Easy,     # ~8.3d initial stability, ~28d first due
    'partly': FsrsRating.Good,     # ~2.3d initial stability, ~8d first due
    'missed': FsrsRating.Again,    # ~0.2d initial stability, ~1d first due
}

INITIAL_STABILITY_DAYS = 1.0


def _fsrs_reschedule(item_id: str, score: str, conn, table: str = 'knowledge_items'):
    """Apply FSRS scheduling to an item. Used by voice elicitation and capture
    paths to ensure scheduling stays consistent with record_answer()."""
    row = conn.execute(f'SELECT fsrs_card_json FROM {table} WHERE id=?', (item_id,)).fetchone()
    if not row:
        return
    card_json = row['fsrs_card_json'] if row else None
    if card_json:
        card_data = json.loads(card_json) if isinstance(card_json, str) else card_json
        card = FsrsCard.from_dict(card_data)
    else:
        card = FsrsCard()

    fsrs_rating = SCORE_TO_FSRS.get(score, FsrsRating.Again)
    now_dt = datetime.now(timezone.utc)
    new_card, _ = _fsrs_scheduler.review_card(card, fsrs_rating, now_dt)
    new_stability = new_card.stability or 1.0
    next_due = int(new_card.due.timestamp() * 1000)
    now_ms = int(time.time() * 1000)
    conn.execute(f"""
        UPDATE {table} SET stability_days=?, due_at=?, last_reviewed_at=?,
          last_score=?, review_count=review_count+1, cached_question=NULL, fsrs_card_json=?
        WHERE id=?
    """, (new_stability, next_due, now_ms, score, json.dumps(new_card.to_dict()), item_id))

SCORE_TO_KNOWLEDGE = {
    'knew':   ('anchored', 0.85),
    'partly': ('engaged',  0.55),
    'missed': ('unknown',  0.1),
}

# ── Curriculum auto-detection ─────────────────────────────────────────────────

def detect_curriculum(book_title: str, book_topics: list) -> str:
    """Find the best-matching curriculum for a book using embedding similarity.

    Embeds the book's title + topics and compares against the title + description
    of every available curriculum. Falls back to Sicily if nothing scores above 0.35.
    Returns the single best-matching domain_id.
    """
    curricula = list_curricula()
    if not curricula:
        return 'sicily_history_culture_and_legacy'

    book_text = f"{book_title}. Topics: {', '.join(book_topics)}"

    try:
        from limbic.amygdala import EmbeddingModel
        model = EmbeddingModel()
        book_vec = model.embed(book_text)

        import numpy as np
        best_id, best_score = curricula[0]['id'], -1.0
        for meta in curricula:
            c = load_curriculum(meta['id'])
            if not c:
                continue
            c_text = f"{c.get('title', '')}. {c.get('description', '')} {' '.join(n['title'] for n in c.get('nodes', [])[:10])}"
            c_vec = model.embed(c_text)
            score = float(np.dot(book_vec, c_vec) / (np.linalg.norm(book_vec) * np.linalg.norm(c_vec) + 1e-9))
            if score > best_score:
                best_score, best_id = score, meta['id']

        if best_score >= 0.35:
            return best_id
    except Exception:
        pass

    # Keyword fallback
    text = ' '.join([book_title] + book_topics).lower()
    keyword_map = {
        'sicily_history_culture_and_legacy': ['sicily', 'sicilian', 'syracuse', 'palermo'],
        'ancient_greece_800300_bc_political_military_cultural_and': ['greece', 'greek', 'athens', 'sparta'],
        'roman_republic_and_empire': ['rome', 'roman', 'caesar', 'republic'],
        'byzantine': ['byzantine', 'byzantium', 'constantinople', 'justinian', 'belisarius'],
        'islamic': ['islamic', 'islam', 'arab', 'caliphate', 'muslim', 'ottoman'],
        'classical_reception': ['classics', 'classical education', 'humanism', 'humanist', 'liberal arts', 'trivium', 'quadrivium', 'paideia', 'hellenism', 'renaissance learning', 'erasmus', 'petrarch', 'scriptoria', 'manuscript'],
    }
    for domain_id, keywords in keyword_map.items():
        if any(kw in text for kw in keywords):
            # Check if a curriculum with this prefix actually exists
            for meta in curricula:
                if meta['id'].startswith(domain_id) or meta['id'] == domain_id:
                    return meta['id']

    return curricula[0]['id']  # default to first available


def suggest_curricula_for_book(book_title: str, book_topics: list) -> list[dict]:
    """Return curricula sorted by relevance to a book, with scores.

    Used to suggest which curriculum(a) to map a new book against,
    and to surface gaps where no curriculum exists yet.
    """
    curricula = list_curricula()
    if not curricula:
        return []

    book_text = f"{book_title}. Topics: {', '.join(book_topics)}"
    results = []

    try:
        from limbic.amygdala import EmbeddingModel
        import numpy as np
        model = EmbeddingModel()
        book_vec = model.embed(book_text)

        for meta in curricula:
            c = load_curriculum(meta['id'])
            if not c:
                continue
            c_text = f"{c.get('title', '')}. {' '.join(n['title'] for n in c.get('nodes', [])[:15])}"
            c_vec = model.embed(c_text)
            score = float(np.dot(book_vec, c_vec) / (np.linalg.norm(book_vec) * np.linalg.norm(c_vec) + 1e-9))
            results.append({'id': meta['id'], 'title': meta['title'], 'score': round(score, 3)})

        results.sort(key=lambda x: -x['score'])
    except Exception as e:
        print(f'[review] suggest_curricula embedding failed: {e}', flush=True)
        results = [{'id': m['id'], 'title': m['title'], 'score': 0.0} for m in curricula]

    return results


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _call_claude(prompt: str, timeout: int = 180) -> str | None:
    """Legacy wrapper — delegates to claude_llm module."""
    return call_claude(prompt, timeout=timeout)


def _parse_json(text: str) -> dict | list | None:
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
    for pattern in [r'\[[\s\S]*\]', r'\{[\s\S]*\}']:
        m = re.search(pattern, cleaned)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


# ── Topological ordering ──────────────────────────────────────────────────────

def compute_node_depths(curriculum: dict) -> dict:
    nodes = {n['id']: n for n in curriculum['nodes']}
    depths = {}

    def depth(nid, visited=None):
        if visited is None:
            visited = set()
        if nid in depths:
            return depths[nid]
        if nid in visited:
            return 0
        visited.add(nid)
        prereqs = nodes.get(nid, {}).get('prerequisites', [])
        depths[nid] = (1 + max((depth(p, visited) for p in prereqs), default=-1)) if prereqs else 0
        return depths[nid]

    for nid in nodes:
        depth(nid)
    return depths


def get_dependent_node_ids(target_id: str, curriculum: dict) -> list:
    return [n['id'] for n in curriculum['nodes'] if target_id in n.get('prerequisites', [])]


# ── Prompts ───────────────────────────────────────────────────────────────────

MAP_CHAPTER_PROMPT = """Map a book chapter to curriculum nodes for a knowledge review system.

Book: {book_title}
Chapter {chapter_number}: {chapter_title}
Context:
{chapter_context}

Curriculum nodes ({curriculum_title}) — level 2-3 only:
{nodes_list}

Which 3-6 nodes does this chapter directly cover (not just passing mentions)?

For each matched node:
- "node_id": exact ID from the list
- "node_title": node title
- "source_text": 1-2 sentences of SPECIFIC FACTS from the chapter — exact names, dates, events, numbers. Do NOT write abstract summaries like "the chapter discusses the importance of X" — instead write concrete facts: "Themistocles persuaded Athens to build 200 triremes before Salamis" or "The Macedonian dynasty ruled 867–1056 AD, Byzantium's cultural golden age". If the chapter is thin on specifics, name the most concrete nouns it mentions.
- "lens": best retrieval lens — CAUSAL | COMPARATIVE | SIGNIFICANCE | TEMPORAL | PATTERN | CONSEQUENCE
- "temporal_hook": optional 1-sentence cross-period anchor (e.g. "Simultaneous with the Roman conquest of Carthage" or "Two centuries before the rise of Islam")

Output JSON array only:
[{{"node_id":"...","node_title":"...","source_text":"...","lens":"...","temporal_hook":"..."}}]"""


QUESTION_GEN_PROMPT_FACTUAL = """Generate a factual review question that tests framework knowledge.

The learner is building a mental scaffold of history. They need to recall KEY FACTS:
dates, key figures, key events, and where things fit in the timeline. These facts are
the load-bearing pillars that make everything else they read richer and more connected.

Concept: {node_title}
Curriculum definition: {node_description}

Extract the most important FACTS from this curriculum node and test ONE of them:
- KEY DATES: When did this happen? What century/decade? (e.g., "When was the Battle of Himera?")
- KEY FIGURES: Who was the central person? What was their role? (e.g., "Who was Gelon?")
- KEY EVENTS: What happened? What was the outcome? (e.g., "What ended Arab rule in Sicily?")
- TIMELINE PLACEMENT: What came before/after? What was happening elsewhere? (e.g., "Himera was simultaneous with which Greek battle?")

Pick the single most important fact to test — the one that, once known, makes this
entire period click into place. Prefer dates and figures for early reviews.

DO NOT ask vague conceptual questions like "What characterized..." or "What made X unique..."
— those come later. Right now we need the factual scaffolding.

The answer should be SHORT and specific (a date, a name, a 1-sentence event).

{temporal_context}

{learner_context}

If LEARNER CONTEXT is provided, use it to:
- Reference the learner's own connections and interests
- Address any misconceptions noted in their voice recall
- Build on what they found interesting, not just what they missed
- Avoid asking about things they've already demonstrated mastery of

The rich_answer is shown when the learner gets it wrong — it should be a vivid, memorable mini-narrative,
not an encyclopedia summary. Name specific people (including minor figures), give physical details,
include one anecdote-grade detail that sticks.

BAD rich_answer: "Constantinople fell in 1453 after an Ottoman siege led by Mehmed II. This was a
significant event because it ended the Byzantine Empire and marked the end of the medieval period."
GOOD rich_answer: "Mehmed II was just 21 when he breached the Theodosian Walls on May 29, 1453.
The decisive weapon was a massive cannon cast by the Hungarian engineer Urbán — who had first offered
his services to the Byzantines, but they couldn't afford him. The last emperor, Constantine XI,
died fighting on the walls; his body was never identified. Within hours Mehmed rode to Hagia Sophia
and claimed it as a mosque, while Gutenberg was setting type in Mainz 1,500 miles away."

Output JSON only:
{{"question":"short factual question (6-15 words)","answer_guidance":"the specific factual answer (1-2 sentences max)","rich_answer":"4-5 sentences — vivid narrative with specific names, ages, ironic details, physical description. Include a temporal anchor.","temporal_hook":"connection to another era the learner knows","curriculum_context":"brief placement in the larger history"}}"""


QUESTION_GEN_PROMPT = """Generate an analytical review question.

Concept: {node_title}
Curriculum definition: {node_description}
Review #{review_count}

{difficulty_instruction}

{known_nodes_context}
{temporal_context}

The learner already understands what this concept IS. Now push deeper with the {lens} lens.
The question should connect, compare, or explain — not test an isolated name or date.

Lens options:
- CAUSAL: What caused this? What sequence of events led here?
- COMPARATIVE: How does this compare to another period or polity the learner knows?
- SIGNIFICANCE: What did this change? Why does it matter for what came next?
- TEMPORAL: What else was happening simultaneously? What's the chronological anchor?
- PATTERN: What recurring dynamic does this exemplify across Sicilian/Mediterranean history?
- CONSEQUENCE: What long-term effects did this produce?

{learner_context}

If LEARNER CONTEXT is provided, use it to:
- Reference the learner's own connections and interests
- Address any misconceptions noted in their voice recall
- Build on what they found interesting, not just what they missed
- Avoid asking about things they've already demonstrated mastery of

Keep question under 20 words.

The rich_answer should read like a well-told anecdote, not a textbook paragraph. Name minor figures,
give ages and physical details, include one surprising or ironic detail that makes the answer stick.

BAD rich_answer: "The Norman conquest of Sicily was significant because it brought together
multiple cultural traditions and created a unique multicultural society."
GOOD rich_answer: "When Roger II was crowned in Palermo's cathedral on Christmas Day 1130, his
coronation mantle was sewn by Arab craftsmen in the royal tiraz workshop — its Arabic inscription
dates it precisely. His chief minister George of Antioch was a Greek-speaking Syrian Orthodox
Christian who had previously served the Fatimid rulers of North Africa. The kingdom's three
official languages (Latin, Greek, Arabic) weren't tolerance as ideology — they were the minimum
viable bureaucracy for governing three populations who wouldn't learn each other's language."

Output JSON only:
{{"question":"...","answer_guidance":"2-3 sentences on what a good answer covers","rich_answer":"4-5 sentences — vivid narrative with specific names, ironic details, one anecdote-grade fact. Temporal anchor to another period the learner knows.","temporal_hook":"...","curriculum_context":"..."}}"""


FOLLOW_UP_PROMPT = """A history reader just reviewed a topic. Generate 6 follow-up research questions
that go SIDEWAYS — exploring adjacent angles the card didn't cover, not drilling deeper into
what was already said. The reader should think "oh, I never thought about it from THAT angle."

Topic: {node_title}
Topic description: {node_description}
Specific fact just reviewed: {fact_context}

VARIETY IS ESSENTIAL. Each question should take a DIFFERENT angle. Prioritize these:
- GEOGRAPHY AS EXPLANATION: Why HERE specifically? What about the landscape, harbors, climate,
  trade routes explains why this happened in this place?
  (e.g., "Why did the Greek-Carthaginian border run exactly where it did — what was special about the Halycus river?")
- STRUCTURAL / SYSTEMIC: What institutional, economic, or social structure made this possible or inevitable?
  (e.g., "How did the Norman feudal system interact with the existing Arab land-tenure system?")
- TRANSMISSION & RECEPTION: How did knowledge of this reach us? Who carried it, translated it, debated it?
  (e.g., "How did Western scholars actually access Greek manuscripts in Constantinople before 1453?")
- COUNTER-NARRATIVES: What did the OTHER side think? The conquered, the losers, the minority voices?
  (e.g., "What do we know about how ordinary Sicilian Muslims experienced the Norman conquest?")
- CONNECTED FIGURES: Fascinating people adjacent to this story the reader hasn't met yet
  (e.g., "Who was George of Antioch, and why did a Greek Orthodox Syrian become Roger II's chief minister?")
- MODERN ECHOES: What modern institution, place name, legal concept, or cultural practice traces back here?
  (e.g., "Which Sicilian place names are actually Arabic, and what do they reveal about settlement patterns?")
- ART & CULTURAL AFTERLIFE: Opera, theatre, poetry, novels, films — how this event lives in culture
  (e.g., "Which Verdi opera dramatizes the Sicilian Vespers, and how accurate is it?")

Rules:
- Be SPECIFIC — name real people, places, events, dates. Never generic.
- DO NOT ask about things already covered in the card content. Go sideways, not deeper.
- NO templates like "How does X connect to Y?" or "What was happening elsewhere?" or "Tell me more about X"
- Each question should feel like it could be its own microlearning rabbit hole

{learner_context}

If LEARNER CONTEXT is provided, avoid generating follow-ups that the learner has
already explored via voice recall. Instead, find angles that complement their
existing knowledge and curiosities.

Output JSON array of 6 strings only: ["q1","q2","q3","q4","q5","q6"]"""


EXPLORE_PROMPT = """A learner reviewed this concept and wants to explore further.

Concept: {node_title}
Source: {source_text}
Their score: {score}

Generate 3 research questions to deepen understanding. Vary lenses:
1. Causal depth (why/how)
2. Comparative (relation to other periods/places)
3. Significance (consequences or modern relevance)

Output JSON:
[{{"question":"...","lens":"...","suggested_source":"brief hint where to find the answer"}}]"""


VOICE_EXTRACT_PROMPT = """Extract signals from a learner's voice memo during knowledge review.

Concept being reviewed: {node_title}
Transcript: {transcript}

Extract:
1. What they seem to remember correctly
2. Questions or uncertainties they expressed
3. Connections to other topics they noticed
4. Their apparent confidence level

Output JSON:
{{"remembered":"...","questions":["..."],"connections":["..."],"suggested_score":"knew|partly|missed"}}"""


VOICE_ELICITATION_PROMPT = """Analyze a learner's free recall about a historical topic.

TOPIC: {node_title}
TOPIC DEFINITION: {node_description}

BOOK SOURCES (what the learner has read about this):
{sources_text}

AVAILABLE NODES IN THIS CURRICULUM:
{available_nodes}

LEARNER'S RECALL (transcribed speech):
{transcript}

Compare the learner's recall against the topic definition and book sources. Identify:

1. CAPTURED: Specific facts or concepts from the definition/sources that the learner mentioned (even if imprecisely). Be generous — paraphrases count.
2. MISSED: The 2-3 most structurally important omissions — facts that serve as scaffolding for understanding the broader topic (key dates, actors, causal relationships). Prefer load-bearing facts over colorful details.
3. INTERESTING: Things the learner said that go BEYOND the sources — personal connections, questions, hypotheses, links to other topics. These are valuable signals.
4. WONDERINGS: Extract ALL questioning or curious statements — "I wonder...", "I'm not sure if...", "was it...?", "I'd like to know...", hedged questions, speculative connections, anything where the learner is reaching beyond what they know. These are the most valuable signals — err on the side of including too many. Rephrase as clear research questions.
5. RESEARCH_QUESTIONS: Specific questions that could be researched to deepen the learner's understanding. Derive from wonderings, gaps in knowledge, and interesting but uncertain claims. Frame as searchable questions.
6. ENTITIES_MENTIONED: List ALL people, places, events, and concepts the learner mentions by name. Use canonical forms (e.g., "Alexander the Great" not "Alexander").
7. CONFIDENCE_TAGGED: For each key claim the learner makes, tag their apparent confidence: "certain" (stated as fact), "uncertain" (hedged, "I think...", "maybe..."), or "wrong" (stated confidently but incorrect).
8. ORGANIZING_FRAMEWORK: How does the learner organize this knowledge? Options: "biographical_arc" (follows a person's life), "chronological" (events in order), "geographic" (places and regions), "thematic" (ideas and concepts), "causal" (cause and effect chains).
9. ADJACENT_NODES_COVERED: If the learner discusses topics that clearly overlap with OTHER curriculum nodes (not this one), list the likely node_ids from the available nodes above.

If the learner demonstrates extensive knowledge about adjacent or broader topics beyond the node definition, acknowledge this in feedback_summary and give partial credit in coverage_pct for related knowledge that connects to this topic.

Output JSON:
{{"captured": ["fact1", "fact2"], "missed": ["important_fact1", "important_fact2"], "interesting": ["connection1"], "wonderings": ["I wonder if X was related to Y", "Was it Z who did this?", "I'm curious whether..."], "research_questions": ["What was the relationship between X and Y?", "Did Z lead to the outcome described?"], "entities_mentioned": ["Alexander the Great", "Plato", "Athens"], "confidence_tagged": [{{"fact": "Aristotle was student of Plato", "confidence": "certain"}}, {{"fact": "His father was a tutor to Philip", "confidence": "uncertain"}}], "organizing_framework": "biographical_arc|chronological|geographic|thematic|causal", "adjacent_nodes_covered": ["node_id_1", "node_id_2"], "coverage_pct": 65, "suggested_score": "knew|partly|missed", "feedback_summary": "2-3 sentence personalized feedback highlighting what was strong and what key thing was missed"}}"""


VOICE_CAPTURE_ANALYSIS_PROMPT = """Analyze a voice capture where a learner describes what they know about a topic.
This is NOT a recall test — the learner is freely sharing knowledge from a podcast, book, conversation, or their own thinking.
Your job is to extract concrete facts, map them to curriculum nodes, and identify wonderings.

{context_section}

CURRICULUM NODES (candidate matches — the learner's knowledge may touch any of these):
{nodes_list}

LEARNER'S VOICE CAPTURE (transcribed speech):
{transcript}

Instructions:
1. ALWAYS extract every concrete FACT the learner states or implies, even if no curriculum nodes match. Be thorough — include dates, names, events, causal claims, and connections. Each fact should be a standalone statement. Facts with no matching node should have an empty node_ids array.
2. Map each fact to the most relevant curriculum node from the list above. Use the exact node_id. A fact can map to multiple nodes if relevant. CRITICAL MAPPING RULE: Only map a fact to a node if the fact is GENUINELY ABOUT that node's subject matter. The fact must belong to the same historical period and topic as the node. Do NOT map medieval facts to ancient nodes or vice versa. Do NOT map facts to nodes just because they share a word (e.g., a medieval monk writing is NOT about the Roman historian Tacitus; Arab prisoners are NOT about Roman slavery; medieval church politics is NOT about Roman religion). When in doubt, leave the fact unmapped (empty node_ids) rather than force a bad match.
3. For each node that has at least one mapped fact, assess the knowledge demonstrated:
   - "anchored": learner shows confident, detailed knowledge (multiple facts, connections, temporal placement)
   - "engaged": learner demonstrates real knowledge but with gaps or uncertainty
   - "mentioned": learner references the topic but with little substance
4. ALWAYS extract wonderings, questions, uncertainties, "I think...", "I'm not sure if...", speculative statements — even if no nodes match. These are the most valuable signals. Rephrase as clear research questions.
5. CONFIDENCE_TAGGED: For each key factual claim, tag the learner's apparent confidence: "certain" (stated as fact), "uncertain" (hedged, "I think...", "maybe..."), or "wrong" (stated confidently but incorrect).
6. ALWAYS provide overall_summary and entities_mentioned, regardless of node matching.

IMPORTANT: The transcript may cover topics NOT in the curriculum nodes list. That's fine — still extract all facts, wonderings, entities, and summary. The node matching is optional; fact extraction is mandatory.

Output JSON:
{{"facts": [{{"fact": "specific factual claim", "node_ids": ["node_id_1"], "source_excerpt": "relevant 1-2 sentences from transcript"}}],
"node_assessments": [{{"node_id": "...", "node_title": "...", "knowledge_level": "anchored|engaged|mentioned", "fact_count": 3, "summary": "brief summary of what learner knows about this node"}}],
"wonderings": ["research question 1", "research question 2"],
"entities_mentioned": ["entity name 1", "entity name 2"],
"confidence_tagged": [{{"fact": "specific claim", "confidence": "certain|uncertain|wrong"}}],
"overall_summary": "2-3 sentence summary of what the learner shared"}}"""


VOICE_CAPTURE_ENTITY_PROMPT = """Analyze a voice capture where a learner describes what they know about a topic.
This is NOT a recall test — the learner is freely sharing knowledge from a podcast, book, conversation, or their own thinking.
No curriculum structure exists for this topic. Your job is to extract concrete, testable facts organized by the main entities (people, places, events) being discussed.

{context_section}

{entity_info}

LEARNER'S VOICE CAPTURE (transcribed speech):
{transcript}

Instructions:
1. Identify the primary ENTITIES discussed: people, places, events, or specific concepts.
2. Group facts by entity. For each entity, extract every concrete, testable FACT into a question-answer pair suitable for spaced repetition review:
   - Each fact MUST have a specific question with a definite answer. BAD: "What happened?" GOOD: "In what year did Rollo's Vikings besiege Paris?"
   - "type" classifies the fact: "date" (when), "event" (what happened), "person" (who), "place" (where), "concept" (what/how), "cause" (why), "significance" (why it matters)
   - "source_excerpt" is 1-2 sentences quoted from the transcript that support this fact
3. Be thorough — include dates, names, causal claims, and connections. Aim for 3-8 facts per main entity.
4. Extract ALL wonderings, speculative statements, "I think...", "I'm not sure if..." — rephrase as clear research questions.
5. Tag each factual claim with confidence: "certain" (stated as fact), "uncertain" (hedged), "wrong" (stated confidently but incorrect).
6. List all entities mentioned (even if they don't have associated facts).
7. For each entity discussed OR mentioned, classify its type as one of: "person", "place", "event", "battle", "dynasty", "work", "organization", "concept". Include this in "entity_types".
8. Provide an overall_summary (2-3 sentences).

CANONICAL NAMING — critical for downstream Wikidata resolution:
- Use canonical Wikidata-style names. Prefer the form most likely to match a Wikidata label.
- STRIP parenthetical qualifiers. BAD: "Siege of Paris (885-886)"; GOOD: "Siege of Paris". BAD: "Russian Campaign (1708-1709)"; GOOD: "Russian campaign of Charles XII".
- STRIP honorifics and titles unless they are part of the canonical name. BAD: "Emperor Charles the Fat"; GOOD: "Charles the Fat". BAD: "King Karl XII of Sweden"; GOOD: "Karl XII of Sweden". But KEEP: "Pope Gregory VII" (title is canonical), "Count Odo of Paris" (disambiguation).
- For rulers with common English variants, prefer the most common English form. BAD: "Carl XII"; GOOD: "Karl XII of Sweden".
- This naming rule applies to BOTH the keys of entity_facts AND the entries in entities_mentioned AND the keys of entity_types.

Output JSON:
{{"entity_facts": {{
    "Entity Name 1": [{{"id": "f1", "question": "specific question", "answer": "concise answer", "type": "date|event|person|place|concept|cause|significance", "source_excerpt": "..."}}],
    "Entity Name 2": [{{"id": "f2", "question": "...", "answer": "...", "type": "...", "source_excerpt": "..."}}]
  }},
  "entity_types": {{"Entity Name 1": "person|place|event|battle|dynasty|work|organization|concept", "Entity Name 2": "..."}},
  "wonderings": ["research question 1", "research question 2"],
  "entities_mentioned": ["entity name 1", "entity name 2"],
  "confidence_tagged": [{{"fact": "specific claim", "confidence": "certain|uncertain|wrong"}}],
  "overall_summary": "2-3 sentence summary"}}"""


HAMARQUIZEN_PROMPT = """Generate a Hamarquizen-style micro-lesson for reviewing a book topic.

Book: {book_title} by {book_author}
Curriculum node: {node_title}
Node description: {node_description}
Source text from book: {source_text}
Reader's current knowledge: {knowledge_level} (confidence: {confidence})

Create a PRIME→READ→TEST sequence:

1. PRIME: A casual question to activate memory (8-15 words). Start with "What do you remember about..." or "Do you recall why..." or "Can you picture..."

2. READ: 2-3 vivid, specific sentences that bring the topic alive. Include:
   - Concrete names, dates, places (not abstractions)
   - One sensory or dramatic detail ("the walls were 5km long", "he was 75 when he died in the siege")
   - One surprising connection or temporal anchor to another known event
   Keep it tight — this is a micro-narrative, not a textbook paragraph.

3. TEST: A focused question (6-12 words) whose answer is directly in the READ section. Tests understanding, not trivia. Start with What/Why/How.

4. ANSWER: 1-2 sentence answer guidance drawn from the READ section.

5. TEMPORAL_HOOK: One cross-period anchor connecting this to another era the reader might know.

Output JSON:
{{"prime":"...","read":"...","test":"...","answer":"...","temporal_hook":"..."}}"""


MAP_WHOLE_BOOK_PROMPT = """Map a finished book to curriculum nodes for a knowledge review system.

The reader has finished this book. Identify ALL curriculum nodes the reader would have been meaningfully exposed to through reading it. Include nodes where the book provides substantial content — not passing one-sentence mentions.

Book: {book_title} by {book_author}
Topics: {book_topics}
{book_context}

Curriculum nodes ({curriculum_title}) — level 2+ only:
{nodes_list}

Which nodes does this book substantially cover? For historical fiction, include nodes whose events, figures, or settings form part of the narrative. For nonfiction, include nodes whose subject matter is discussed in depth.

For each matched node:
- "node_id": exact ID from the list
- "node_title": node title
- "source_text": 1-2 sentences of SPECIFIC content from this book relevant to the node — name concrete characters, events, settings, arguments. For fiction: "Cicero's prosecution of Verres is a central plot arc in the novel, depicting the corruption of Roman provincial governance in Sicily." For nonfiction: "Chapter on the Arab conquest covers the fall of Syracuse in 878 and the shift to Palermo as capital."
- "lens": best retrieval lens — CAUSAL | COMPARATIVE | SIGNIFICANCE | TEMPORAL | PATTERN | CONSEQUENCE
- "confidence": how central this node is to the book — "high" (major theme/arc), "medium" (significant coverage), "low" (meaningful but secondary)

Be thorough — a 300-page book about Sicilian history might cover 20+ nodes. Don't under-count.

Output JSON array only:
[{{"node_id":"...","node_title":"...","source_text":"...","lens":"...","confidence":"..."}}]"""

# Minimum score from suggest_curricula_for_book to consider a curriculum relevant
CURRICULUM_RELEVANCE_THRESHOLD = 0.40


# ── Chapter mapping ───────────────────────────────────────────────────────────

def _get_chapter_context(book_id: str, chapter_number: int, chapter_title: str) -> str:
    path = BOOK_RESEARCH_DIR / f'{book_id}.json'
    if not path.exists():
        return f'Chapter: {chapter_title}'
    try:
        research = json.loads(path.read_text())
        ch = research.get('chapter_research', {}).get(str(chapter_number), {})
        parts = []
        if ch.get('summary'):
            parts.append(f"Summary: {ch['summary']}")
        if ch.get('claims'):
            parts.append('Claims:\n' + '\n'.join(f'- {c}' for c in ch['claims']))
        return '\n'.join(parts) or f'Chapter: {chapter_title}'
    except Exception:
        return f'Chapter: {chapter_title}'


def map_chapter_to_nodes(book_id: str, book_title: str, book_topics: list,
                          chapter_number: int, chapter_title: str,
                          domain_id: str | None = None) -> list:
    """Map a chapter to curriculum nodes in a specific domain.

    If domain_id is None, auto-detects via detect_curriculum().
    """
    if not domain_id:
        domain_id = detect_curriculum(book_title, book_topics)
    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return []

    node_lines = [
        f"- {n['id']}: {n['title']} — {n['description'][:120]}..."
        for n in curriculum['nodes'] if n.get('level', 1) >= 2
    ]

    chapter_context = _get_chapter_context(book_id, chapter_number, chapter_title)

    curriculum_title = curriculum.get('title', curriculum.get('name', domain_id.replace('_', ' ').title()))

    prompt = MAP_CHAPTER_PROMPT.format(
        book_title=book_title,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        chapter_context=chapter_context,
        nodes_list='\n'.join(node_lines),
        curriculum_title=curriculum_title,
    )

    mappings = call_claude_json(prompt, timeout=240)
    if not mappings:
        return []

    valid_ids = {n['id'] for n in curriculum['nodes']}
    return [m for m in (mappings if isinstance(mappings, list) else [])
            if isinstance(m, dict) and m.get('node_id') in valid_ids]


def fill_prerequisite_gaps(domain_id: str, mapped_node_ids: list, conn, now: int) -> int:
    """Create knowledge_items for prerequisites of mapped nodes.

    Only creates items for Level 2+ prerequisite nodes that don't already exist.
    Enriches gap-fill sources with book_curriculum_mappings when available,
    rather than relying solely on the curriculum node description.
    Returns count of gap-fill items created.
    """
    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return 0

    nodes_by_id = {n['id']: n for n in curriculum['nodes']}
    gaps_created = 0

    # Only expand prerequisites (not siblings — too speculative)
    candidate_ids: set = set()
    for node_id in mapped_node_ids:
        node = nodes_by_id.get(node_id, {})
        for prereq_id in node.get('prerequisites', []):
            prereq = nodes_by_id.get(prereq_id, {})
            if prereq.get('level', 1) >= 2:
                candidate_ids.add(prereq_id)

    for cand_id in candidate_ids:
        if cand_id in mapped_node_ids:
            continue
        item_id = f"{domain_id}:{cand_id}"
        existing = conn.execute(
            'SELECT id FROM knowledge_items WHERE id=?', (item_id,)
        ).fetchone()
        if existing:
            continue

        node = nodes_by_id.get(cand_id, {})

        # Try to enrich with book content: check if any book covers this node
        book_source = conn.execute("""
            SELECT bcm.book_id, bcm.coverage, pb.title as book_title
            FROM book_curriculum_mappings bcm
            LEFT JOIN physical_books pb ON pb.id = bcm.book_id
            WHERE bcm.domain_id = ? AND bcm.node_id = ?
            ORDER BY CASE bcm.coverage
                WHEN 'deep' THEN 0 WHEN 'moderate' THEN 1 ELSE 2 END
            LIMIT 1
        """, (domain_id, cand_id)).fetchone()

        if book_source:
            source = {
                'book_id': book_source['book_id'],
                'chapter_number': None,
                'chapter_title': f"Covered in: {book_source['book_title'] or book_source['book_id']}",
                'source_text': node.get('description', '')[:400],
                'lens': 'SIGNIFICANCE',
                'temporal_hook': '',
                'added_at': now,
                'coverage': book_source['coverage'],
            }
        else:
            source = {
                'book_id': None,
                'chapter_number': None,
                'chapter_title': 'Prerequisite — not yet covered by a book',
                'source_text': node.get('description', '')[:400],
                'lens': 'SIGNIFICANCE',
                'temporal_hook': '',
                'added_at': now,
            }

        try:
            _new_card = FsrsCard()
            conn.execute('''
                INSERT INTO knowledge_items
                (id, curriculum_node_id, curriculum_domain, stability_days, due_at,
                 sources, question_history, created_at, fsrs_card_json)
                VALUES (?,?,?,?,?,?,?,?,?)
            ''', (
                item_id, cand_id, domain_id,
                INITIAL_STABILITY_DAYS, now,
                json.dumps([source]), '[]', now,
                json.dumps(_new_card.to_dict()),
            ))
            gaps_created += 1
        except Exception as e:
            print(f'[review] gap-fill skip {item_id}: {e}', flush=True)

    return gaps_created


def _upsert_chapter_mappings(domain_id: str, mappings: list, book_id: str,
                              chapter_number: int, chapter_title: str,
                              conn, now: int) -> tuple[int, int, int, list]:
    """Upsert knowledge_items for one domain's chapter mappings. Returns (created, updated, gaps, titles)."""
    created = 0
    updated = 0
    node_titles = []
    mapped_node_ids = []

    for m in mappings:
        item_id = f"{domain_id}:{m['node_id']}"
        mapped_node_ids.append(m['node_id'])

        new_source = {
            'book_id': book_id,
            'chapter_number': chapter_number,
            'chapter_title': chapter_title,
            'source_text': m.get('source_text', ''),
            'lens': m.get('lens', 'SIGNIFICANCE'),
            'temporal_hook': m.get('temporal_hook', ''),
            'added_at': now,
        }

        existing = conn.execute(
            'SELECT id, sources FROM knowledge_items WHERE id=?', (item_id,)
        ).fetchone()

        if existing:
            try:
                sources = json.loads(existing['sources'] or '[]')
            except Exception:
                sources = []
            already = any(
                s.get('book_id') == book_id and s.get('chapter_number') == chapter_number
                for s in sources
            )
            if not already:
                sources.append(new_source)
                conn.execute(
                    'UPDATE knowledge_items SET sources=?, cached_question=NULL WHERE id=?',
                    (json.dumps(sources), item_id)
                )
                updated += 1
        else:
            conn.execute('''
                INSERT INTO knowledge_items
                (id, curriculum_node_id, curriculum_domain, stability_days, due_at,
                 sources, question_history, created_at)
                VALUES (?,?,?,?,?,?,?,?)
            ''', (
                item_id, m['node_id'], domain_id,
                INITIAL_STABILITY_DAYS, now,
                json.dumps([new_source]), '[]', now,
            ))
            created += 1

        node_titles.append(m.get('node_title', m['node_id']))

    gaps_filled = fill_prerequisite_gaps(domain_id, mapped_node_ids, conn, now)
    return created, updated, gaps_filled, node_titles


def create_review_items_for_chapter(book_id: str, book_title: str, book_topics: list,
                                     chapter_number: int, chapter_title: str, conn) -> dict:
    """Map chapter to curriculum nodes across multiple domains and upsert into knowledge_items.

    Maps against the primary domain plus up to 2 secondary domains (score >= 0.40)
    to realize the overlapping-curricula vision.
    """
    # Find relevant curricula ranked by similarity
    suggestions = suggest_curricula_for_book(book_title, book_topics)
    primary_domain = detect_curriculum(book_title, book_topics)

    # Build ordered list: primary first, then high-scoring secondaries
    SECONDARY_THRESHOLD = 0.40
    MAX_SECONDARY = 2
    domains_to_map = [primary_domain]
    for s in suggestions:
        if s['id'] == primary_domain:
            continue
        if s['score'] >= SECONDARY_THRESHOLD and len(domains_to_map) <= MAX_SECONDARY:
            domains_to_map.append(s['id'])

    now = int(time.time() * 1000)
    total_created = 0
    total_updated = 0
    total_gaps = 0
    all_node_titles = []
    all_items_to_pregen = []
    domains_mapped = []

    for domain_id in domains_to_map:
        mappings = map_chapter_to_nodes(
            book_id, book_title, book_topics,
            chapter_number, chapter_title,
            domain_id=domain_id,
        )
        if not mappings:
            continue

        created, updated, gaps, titles = _upsert_chapter_mappings(
            domain_id, mappings, book_id, chapter_number, chapter_title, conn, now,
        )
        total_created += created
        total_updated += updated
        total_gaps += gaps
        all_node_titles.extend(titles)
        domains_mapped.append(domain_id)

        # Collect items needing question pre-generation
        mapped_ids = [m['node_id'] for m in mappings]
        items = conn.execute(
            '''SELECT id FROM knowledge_items
               WHERE curriculum_domain=? AND cached_question IS NULL
                 AND id IN ({})'''.format(','.join('?' * len(mapped_ids))),
            [domain_id] + [f"{domain_id}:{nid}" for nid in mapped_ids]
        ).fetchall()
        all_items_to_pregen.extend(r['id'] for r in items)

        is_secondary = domain_id != primary_domain
        label = f'(secondary)' if is_secondary else '(primary)'
        print(f'[review] Ch{chapter_number} → {domain_id} {label}: '
              f'{created} created, {updated} updated, {gaps} gaps → {titles}', flush=True)

    if not domains_mapped:
        return {'nodes_covered': [], 'items_created': 0, 'items_updated': 0,
                'gaps_filled': 0, 'domain': primary_domain, 'domains_mapped': []}

    conn.commit()

    # Pre-generate questions in background
    if all_items_to_pregen:
        ids_to_gen = list(all_items_to_pregen)
        def _pregen():
            from db import get_connection as _conn
            c = _conn()
            for iid in ids_to_gen:
                try:
                    q = generate_question(iid, c)
                    c.execute('UPDATE knowledge_items SET cached_question=? WHERE id=?',
                              (json.dumps(q), iid))
                    c.commit()
                except Exception as e:
                    print(f'[review] pre-gen failed {iid}: {e}', flush=True)
            c.close()
            print(f'[review] pre-generated {len(ids_to_gen)} questions for ch{chapter_number}', flush=True)
        threading.Thread(target=_pregen, daemon=True).start()

    return {
        'nodes_covered': all_node_titles,
        'items_created': total_created,
        'items_updated': total_updated,
        'gaps_filled': total_gaps,
        'domain': primary_domain,
        'domains_mapped': domains_mapped,
    }


# ── Whole-book mapping ───────────────────────────────────────────────────────

def _get_book_context(book_id: str, book_title: str) -> str:
    """Gather any available context about a book: research, chapters, highlights."""
    parts = []
    # Book research file
    path = BOOK_RESEARCH_DIR / f'{book_id}.json'
    if path.exists():
        try:
            research = json.loads(path.read_text())
            if research.get('summary'):
                parts.append(f"Book summary: {research['summary']}")
            if research.get('chapter_research'):
                ch_titles = []
                for ch_num, ch in sorted(research['chapter_research'].items(), key=lambda x: int(x[0])):
                    title = ch.get('title', f'Chapter {ch_num}')
                    ch_titles.append(f"  Ch {ch_num}: {title}")
                if ch_titles:
                    parts.append("Chapters:\n" + '\n'.join(ch_titles))
        except Exception:
            pass
    # Chapter list from DB
    try:
        from db import get_connection
        conn = get_connection()
        row = conn.execute('SELECT chapters FROM physical_books WHERE id=?', (book_id,)).fetchone()
        conn.close()
        if row and row['chapters']:
            chapters = json.loads(row['chapters'])
            if chapters and not parts:  # Only if we don't already have chapter research
                ch_list = [f"  {ch.get('title', ch.get('number', '?'))}" for ch in chapters[:30]]
                if ch_list:
                    parts.append("Chapter list:\n" + '\n'.join(ch_list))
    except Exception:
        pass
    return '\n'.join(parts) if parts else f'(No additional context available for "{book_title}")'


def _map_book_to_curriculum(book_id: str, book_title: str, book_author: str,
                            book_topics: list, domain_id: str) -> list:
    """Map a whole book against a single curriculum. Returns list of node mappings."""
    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return []

    node_lines = [
        f"- {n['id']}: {n['title']} — {n['description'][:150]}..."
        for n in curriculum['nodes'] if n.get('level', 1) >= 2
    ]
    if not node_lines:
        return []

    book_context = _get_book_context(book_id, book_title)
    curriculum_title = curriculum.get('title', domain_id.replace('_', ' ').title())

    prompt = MAP_WHOLE_BOOK_PROMPT.format(
        book_title=book_title,
        book_author=book_author or 'Unknown',
        book_topics=', '.join(book_topics) if book_topics else 'None specified',
        book_context=book_context,
        nodes_list='\n'.join(node_lines),
        curriculum_title=curriculum_title,
    )

    mappings = call_claude_json(prompt, timeout=240)
    if not mappings:
        return []

    valid_ids = {n['id'] for n in curriculum['nodes']}
    return [m for m in (mappings if isinstance(mappings, list) else [])
            if isinstance(m, dict) and m.get('node_id') in valid_ids]


def map_whole_book(book_id: str, conn) -> dict:
    """Map a finished book to ALL relevant curricula, creating knowledge_items.

    Returns summary with per-curriculum results.
    """
    row = conn.execute(
        'SELECT title, author, topics FROM physical_books WHERE id=?', (book_id,)
    ).fetchone()
    if not row:
        return {'error': f'Book {book_id} not found'}

    book_title = row['title']
    book_author = row['author'] or ''
    book_topics = json.loads(row['topics'] or '[]')

    # Find all relevant curricula
    scored = suggest_curricula_for_book(book_title, book_topics)
    relevant = [c for c in scored if c['score'] >= CURRICULUM_RELEVANCE_THRESHOLD]
    if not relevant:
        return {'error': 'No relevant curricula found', 'scores': scored}

    print(f'[review] Mapping whole book "{book_title}" to {len(relevant)} curricula: '
          f'{[(c["id"][:30], c["score"]) for c in relevant]}', flush=True)

    now = int(time.time() * 1000)
    results = []

    for curr_meta in relevant:
        domain_id = curr_meta['id']
        mappings = _map_book_to_curriculum(
            book_id, book_title, book_author, book_topics, domain_id
        )
        if not mappings:
            results.append({'domain': domain_id, 'score': curr_meta['score'],
                            'nodes_covered': [], 'items_created': 0, 'items_updated': 0})
            continue

        created = 0
        updated = 0
        node_titles = []
        mapped_node_ids = []

        for m in mappings:
            item_id = f"{domain_id}:{m['node_id']}"
            mapped_node_ids.append(m['node_id'])

            new_source = {
                'book_id': book_id,
                'chapter_number': None,
                'chapter_title': f'Whole book: {book_title}',
                'source_text': m.get('source_text', ''),
                'lens': m.get('lens', 'SIGNIFICANCE'),
                'confidence': m.get('confidence', 'medium'),
                'added_at': now,
            }

            existing = conn.execute(
                'SELECT id, sources FROM knowledge_items WHERE id=?', (item_id,)
            ).fetchone()

            if existing:
                try:
                    sources = json.loads(existing['sources'] or '[]')
                except Exception:
                    sources = []
                # Skip if this book already mapped to this node
                already = any(s.get('book_id') == book_id for s in sources)
                if not already:
                    sources.append(new_source)
                    conn.execute(
                        'UPDATE knowledge_items SET sources=?, cached_question=NULL WHERE id=?',
                        (json.dumps(sources), item_id)
                    )
                    updated += 1
            else:
                conn.execute('''
                    INSERT INTO knowledge_items
                    (id, curriculum_node_id, curriculum_domain, stability_days, due_at,
                     sources, question_history, created_at)
                    VALUES (?,?,?,?,?,?,?,?)
                ''', (
                    item_id, m['node_id'], domain_id,
                    INITIAL_STABILITY_DAYS, now,
                    json.dumps([new_source]), '[]', now,
                ))
                created += 1

            node_titles.append(m.get('node_title', m['node_id']))

        gaps_filled = fill_prerequisite_gaps(domain_id, mapped_node_ids, conn, now)
        conn.commit()

        print(f'[review] Book→{domain_id[:30]}: {created} created, {updated} updated, '
              f'{gaps_filled} gaps, {len(node_titles)} nodes', flush=True)

        results.append({
            'domain': domain_id,
            'score': curr_meta['score'],
            'nodes_covered': node_titles,
            'items_created': created,
            'items_updated': updated,
            'gaps_filled': gaps_filled,
        })

    # Pre-generate questions in background for all new items
    all_new_ids = []
    for r in results:
        domain_id = r['domain']
        items = conn.execute(
            'SELECT id FROM knowledge_items WHERE curriculum_domain=? AND cached_question IS NULL',
            (domain_id,)
        ).fetchall()
        all_new_ids.extend(row['id'] for row in items)

    if all_new_ids:
        def _pregen():
            from db import get_connection as _conn
            c = _conn()
            for iid in all_new_ids:
                try:
                    q = generate_question(iid, c)
                    c.execute('UPDATE knowledge_items SET cached_question=? WHERE id=?',
                              (json.dumps(q), iid))
                    c.commit()
                except Exception as e:
                    print(f'[review] pre-gen failed {iid}: {e}', flush=True)
            c.close()
            print(f'[review] pre-generated {len(all_new_ids)} questions for "{book_title}"', flush=True)
        threading.Thread(target=_pregen, daemon=True).start()

    total_created = sum(r.get('items_created', 0) for r in results)
    total_updated = sum(r.get('items_updated', 0) for r in results)
    return {
        'book_id': book_id,
        'book_title': book_title,
        'curricula_mapped': len([r for r in results if r.get('nodes_covered')]),
        'total_items_created': total_created,
        'total_items_updated': total_updated,
        'details': results,
    }


# ── Review queue ──────────────────────────────────────────────────────────────

def _knowledge_item_to_queue_row(ki: dict, curriculum_cache: dict) -> dict:
    """Convert a knowledge_items row to the ReviewItem shape the client expects."""
    domain = ki.get('curriculum_domain', '')
    curriculum = curriculum_cache.get(domain)
    node_id = ki.get('curriculum_node_id', '')

    # Resolve node title from curriculum
    node_title = ''
    if curriculum:
        node = next((n for n in curriculum.get('nodes', []) if n['id'] == node_id), None)
        node_title = node['title'] if node else node_id

    # Pick best source: most recently added (last in array), falling back to first
    try:
        sources = json.loads(ki.get('sources') or '[]')
    except Exception:
        sources = []

    # Determine item_type: gap_fill if all sources have book_id=None, else book_chapter
    item_type = 'gap_fill' if sources and all(s.get('book_id') is None for s in sources) else 'book_chapter'

    # Best source for display: prefer a real book source; within those, most recently added
    book_sources = [s for s in sources if s.get('book_id') is not None]
    best = book_sources[-1] if book_sources else (sources[-1] if sources else {})

    return {
        'id': ki['id'],
        'item_type': item_type,
        'curriculum_domain': domain,
        'curriculum_node_id': node_id,
        'curriculum_node_title': node_title,
        'source_book_id': best.get('book_id'),
        'source_chapter_number': best.get('chapter_number'),
        'source_chapter_title': best.get('chapter_title', ''),
        'source_text': best.get('source_text', ''),
        'lens': best.get('lens', 'SIGNIFICANCE'),
        'temporal_hook': best.get('temporal_hook', ''),
        'stability_days': ki.get('stability_days', 1.0),
        'due_at': ki.get('due_at', 0),
        'last_reviewed_at': ki.get('last_reviewed_at'),
        'last_score': ki.get('last_score'),
        'review_count': ki.get('review_count', 0),
        'sources': sources,
        'cached_question': ki.get('cached_question'),
    }


def get_review_queue(limit: int = 20, book_id: str | None = None, conn=None) -> list:
    now = int(time.time() * 1000)
    soon = now + 24 * 60 * 60 * 1000

    # knowledge_items: core curriculum nodes (book_chapter + gap_fill)
    ki_query = 'SELECT * FROM knowledge_items WHERE due_at <= ?'
    ki_params = [soon]
    if book_id:
        # Filter to items that have at least one source from this book
        # (SQLite JSON: simpler to post-filter in Python)
        ki_rows = conn.execute(ki_query, ki_params).fetchall()
        ki_rows = [r for r in ki_rows
                   if any(s.get('book_id') == book_id
                          for s in (json.loads(r['sources'] or '[]') if r['sources'] else []))]
    else:
        ki_rows = conn.execute(ki_query, ki_params).fetchall()

    # exploration + voice_followup items still live in review_items
    ri_query = "SELECT * FROM review_items WHERE due_at <= ? AND item_type != 'book_chapter'"
    ri_params = [soon]
    if book_id:
        ri_query += ' AND source_book_id = ?'
        ri_params.append(book_id)
    ri_rows = conn.execute(ri_query, ri_params).fetchall()

    # Pre-load curricula for depth ordering
    domains: set = set()
    for r in ki_rows:
        if r['curriculum_domain']:
            domains.add(r['curriculum_domain'])
    for r in ri_rows:
        if r['curriculum_domain']:
            domains.add(r['curriculum_domain'])

    curriculum_cache: dict = {}
    node_meta: dict = {}  # node_id -> {area_order, date_start}
    for domain in domains:
        curriculum = load_curriculum(domain)
        curriculum_cache[domain] = curriculum
        if curriculum:
            # Build area order from Level 1 nodes (their position in the list = priority)
            area_order = {}
            area_pos = 0
            for n in curriculum.get('nodes', []):
                if n.get('level') == 1:
                    area_order[n['id']] = area_pos
                    area_pos += 1
            # Assign each node its area's position
            parent_map = {n['id']: n.get('parent_id') for n in curriculum.get('nodes', [])}
            for n in curriculum.get('nodes', []):
                parent = parent_map.get(n['id'])
                grandparent = parent_map.get(parent) if parent else None
                area_id = grandparent or parent or n['id']
                node_meta[n['id']] = {
                    'area_order': area_order.get(area_id, 99),
                    'date_start': n.get('date_start'),
                }

    def _sort_key(item):
        nid = item.get('curriculum_node_id', '')
        meta = node_meta.get(nid, {})
        area = meta.get('area_order', 99)
        ds = meta.get('date_start')
        date_sort = ds if ds is not None else 5000
        return (area, date_sort, item.get('due_at', 0))

    # Build unified item list
    items = []
    for r in ki_rows:
        items.append(_knowledge_item_to_queue_row(dict(r), curriculum_cache))
    for r in ri_rows:
        items.append(dict(r))

    items.sort(key=_sort_key)
    return items[:limit]


def _generate_follow_up_queries(node_title: str, node_description: str,
                                fact_context: str = '',
                                conn=None, node_id=None, domain_id=None) -> list[str]:
    """Generate 3 LLM-powered follow-up queries for a review item.
    Returns empty list on failure (caller should fall back to templates).

    Uses Gemini Flash directly for interactive latency (~2-5s vs 15-60s
    with claude -p subprocess).
    """
    try:
        learner_ctx = ''
        if conn and node_id and domain_id:
            learner_ctx = get_learner_context(node_id, domain_id, conn)

        prompt = FOLLOW_UP_PROMPT.format(
            node_title=node_title,
            node_description=node_description[:500],
            fact_context=fact_context or '(general review)',
            learner_context=learner_ctx,
        )
        from gemini_llm import call_llm
        raw = call_llm(prompt, model='gemini-2.0-flash',
                       response_mime_type='application/json')
        if raw:
            fq = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(fq, list) and len(fq) >= 2:
                return fq[:6]
    except Exception as e:
        print(f'[review] follow-up gen failed for {node_title}: {e}', flush=True)
    return []


# ── Question generation ───────────────────────────────────────────────────────

def _best_source_for_question(sources: list) -> dict:
    """Pick the most useful source for question generation.

    Prefer real book sources (book_id not None). Among those, prefer the most
    recently added (last) since it tends to have the freshest context.
    Falls back to curriculum gap-fill source if no book sources exist.
    """
    book_sources = [s for s in sources if s.get('book_id') is not None]
    if book_sources:
        # Most recently added = last in the list
        return book_sources[-1]
    return sources[-1] if sources else {}


def _pick_key_fact(key_facts: list, question_history: list) -> dict | None:
    """Pick the highest-priority untested key_fact. Returns None if all tested."""
    tested_ids = {h.get('fact_id') for h in question_history if h.get('fact_id')}
    # Priority ordering, then type ordering within same priority
    type_order = {'event': 0, 'date': 1, 'person': 2, 'connection': 3, 'significance': 4}
    sorted_facts = sorted(key_facts, key=lambda f: (
        f.get('priority', 99),
        type_order.get(f.get('type', ''), 5),
    ))
    for fact in sorted_facts:
        if fact.get('id') not in tested_ids:
            return fact
    # All tested — pick the one with worst score for retry
    return None


def _rank_wonderings(wonderings: list, top_k: int = 5) -> list:
    """Rank wonderings before truncating so the richest ones survive.

    Why: plain `wonderings[:5]` dropped the intellectually richest 6th wondering
    from the Iran Revolution capture (Session 87) — longer, multi-question
    reflections lost to whatever order Gemini happened to emit. Scoring prefers
    length (proxy for specificity / multi-clause reasoning) and explicit
    question marks (genuine curiosity markers).
    """
    def score(w: str) -> float:
        if not isinstance(w, str):
            return -1.0
        return len(w) + 40.0 * w.count('?')
    return sorted(wonderings, key=score, reverse=True)[:top_k]


_ENRICH_PROMPT = """A learner just answered a history review card. Enrich the answer into a learning moment.

Topic: {node_title}
Topic description: {node_description}
Question: {question}
Short answer: {answer}

{learner_context}

{entity_graph_context_block}If learner context is provided, personalize the memory hook using connections the
learner has already made. Reference their known temporal anchors rather than generic ones.

Generate:
1. rich_answer: 4-5 sentences expanding the answer. Include a concrete detail (a name, a place,
   a number), a vivid image, and why this fact matters in the bigger picture.
2. memory_hook: One sentence connecting this to another period or event.
   Be SPECIFIC with dates.
3. temporal_hook: One short phrase anchoring this fact in time using the learner's own
   temporal neighbors (from the "Other entities you've captured from the same period" block
   above, when present). Prefer same-moment connections ("the year Carter took office", "two
   years after the Suez crisis") over generic century markers. Empty string if no suitable
   anchor exists.

BAD temporal_hook: "In the 20th century" (too vague)
BAD temporal_hook: "Around the time of the Cold War" (span, not moment)
BAD temporal_hook: "During the Carter administration" (fine only if Carter is NOT in the
  learner's captured neighbors — otherwise name the specific moment)
GOOD temporal_hook: "444 days from Nov 4 1979 to Jan 20 1981 — Carter's last day, Reagan's first"
GOOD temporal_hook: "Two weeks after the Shah fled, Feb 1979"
GOOD temporal_hook: "1953, 26 years before the revolution — the CIA coup against Mossadegh"

STRICT: do not invent dates or events not present in the provided context. If the context has
no usable temporal anchor, return "".

Output JSON only:
{{"rich_answer":"...","memory_hook":"...","temporal_hook":"..."}}"""


# Wrapper block header used only when entity_graph_context is non-empty.
# Keeping it as a separate constant lets the prompt remain readable when
# there's no graph context to inject (block is omitted entirely, not left
# as a labeled-but-empty section).
_ENRICH_ENTITY_GRAPH_BLOCK = """Entity graph context (from the learner's own captures and Wikidata):
{entity_graph_context}

Use this context to GROUND the memory_hook in what the learner already knows.
STRICT RULE: Do NOT assert facts that don't appear in the "Short answer", the
"Topic description", or the learner's captured facts. Wikidata properties are
hints for ANCHORS, not license to introduce new claims.

When Wikidata properties suggest a natural follow-up fact (e.g. succession,
family), frame it as a RETRIEVAL PROMPT — "do you remember who succeeded
him?" — not as an assertion.

"""


def _key_fact_to_question(fact: dict, node_title: str, node_description: str,
                          conn=None, node_id=None, domain_id=None,
                          entity_graph_context: str = '') -> dict:
    """Convert a key_fact to the cached_question format, with LLM enrichment.

    `entity_graph_context` is the Phase 2 entity-first enrichment block
    (Wikidata properties + scoped temporal neighbors + voice co-occurrence),
    built by `_format_entity_graph_context`. Empty string for curriculum-path
    callers — the prompt block is omitted in that case, keeping behaviour
    identical to Phase 1.
    """
    result = {
        'question': fact['question'],
        'answer_guidance': fact['answer'],
        'rich_answer': fact.get('rich_answer') or fact['answer'],
        'answer_type': fact.get('type', 'event'),
        'temporal_hook': '',
        'curriculum_context': node_description[:200] if node_description else '',
        'fact_id': fact.get('id', ''),
        'entities': fact.get('entities', []),
    }
    # Learner context for enrichment personalization
    learner_ctx = ''
    if conn and node_id and domain_id:
        learner_ctx = get_learner_context(node_id, domain_id, conn)

    egc_block = (
        _ENRICH_ENTITY_GRAPH_BLOCK.format(entity_graph_context=entity_graph_context)
        if entity_graph_context.strip()
        else ''
    )

    # Enrich bare answers with narrative + memory hook
    try:
        enriched = call_claude_json(_ENRICH_PROMPT.format(
            node_title=node_title,
            node_description=node_description[:400],
            question=fact['question'],
            answer=fact['answer'],
            learner_context=learner_ctx,
            entity_graph_context_block=egc_block,
        ), timeout=90, model='sonnet')
        if enriched and isinstance(enriched, dict):
            if enriched.get('rich_answer'):
                result['rich_answer'] = enriched['rich_answer']
            if enriched.get('memory_hook'):
                result['memory_hook'] = enriched['memory_hook']
            th = enriched.get('temporal_hook')
            if isinstance(th, str) and th.strip():
                result['temporal_hook'] = th.strip()
    except Exception as e:
        print(f'[review] enrich failed for {node_title}: {e}', flush=True)
    return result


def _get_cross_curriculum_context(domain_id: str, node_id: str, conn) -> str:
    """Find what the learner knows about related entities from OTHER curricula.

    Queries shared_entities → entity_curriculum_links → knowledge_states to find
    cross-domain perspectives the learner already has on entities in this node.
    Returns a context string for question generation prompts.
    """
    # Find entities linked to this node
    entity_rows = conn.execute("""
        SELECT ecl.entity_id, se.name, ecl.lens_title
        FROM entity_curriculum_links ecl
        JOIN shared_entities se ON se.entity_id = ecl.entity_id
        WHERE ecl.domain_id = ? AND ecl.node_id = ?
    """, (domain_id, node_id)).fetchall()

    if not entity_rows:
        return ''

    entity_ids = [r['entity_id'] for r in entity_rows]
    # Find these entities in OTHER domains where the learner has engaged/anchored knowledge
    cross_perspectives = []
    for eid in entity_ids[:5]:
        rows = conn.execute("""
            SELECT ecl.domain_id, ecl.node_id, ecl.lens_title, ecl.lens_emphasis,
                   se.name as entity_name,
                   ks.knowledge, cn.title as node_title, cd.title as domain_title
            FROM entity_curriculum_links ecl
            JOIN shared_entities se ON se.entity_id = ecl.entity_id
            LEFT JOIN knowledge_states ks ON ks.domain_id = ecl.domain_id AND ks.node_id = ecl.node_id
            LEFT JOIN curriculum_nodes cn ON cn.id = ecl.node_id AND cn.domain_id = ecl.domain_id
            LEFT JOIN curriculum_domains cd ON cd.id = ecl.domain_id
            WHERE ecl.entity_id = ?
              AND ecl.domain_id != ?
              AND ks.knowledge IN ('engaged', 'anchored')
        """, (eid, domain_id)).fetchall()

        for r in rows:
            lens = r['lens_title'] or r['lens_emphasis'] or r['node_title'] or ''
            cross_perspectives.append(
                f"- {r['entity_name']}: learner knows this from {r['domain_title']} "
                f"({r['knowledge']}) — {lens}"
            )

    if not cross_perspectives:
        return ''

    return ('Cross-curriculum context (the learner knows these entities from other domains):\n'
            + '\n'.join(cross_perspectives[:5]))


def _get_temporal_cross_references(domain_id: str, node_id: str, conn) -> str:
    """Find events in OTHER curricula happening at the same time as this node.

    Uses date_start/date_end on curriculum_nodes to find contemporaneous events
    the learner already knows about in different domains.
    """
    # Get this node's date range
    node_row = conn.execute(
        'SELECT date_start, date_end FROM curriculum_nodes WHERE id=? AND domain_id=?',
        (node_id, domain_id)
    ).fetchone()
    if not node_row or node_row['date_start'] is None:
        return ''

    date_start = node_row['date_start']
    date_end = node_row['date_end'] or date_start
    # Allow 50-year overlap window
    window = 50

    # Find nodes in OTHER domains with overlapping dates where learner has knowledge
    rows = conn.execute("""
        SELECT cn.title, cn.date_start, cn.date_end, cn.domain_id,
               cd.title as domain_title, ks.knowledge
        FROM curriculum_nodes cn
        JOIN curriculum_domains cd ON cd.id = cn.domain_id
        JOIN knowledge_states ks ON ks.domain_id = cn.domain_id AND ks.node_id = cn.id
        WHERE cn.domain_id != ?
          AND cn.date_start IS NOT NULL
          AND cn.date_start <= ? + ?
          AND COALESCE(cn.date_end, cn.date_start) >= ? - ?
          AND ks.knowledge IN ('engaged', 'anchored')
          AND cn.level >= 2
        ORDER BY ABS(cn.date_start - ?) ASC
        LIMIT 4
    """, (domain_id, date_end, window, date_start, window, date_start)).fetchall()

    if not rows:
        return ''

    lines = []
    for r in rows:
        date_label = str(r['date_start'])
        if r['date_start'] < 0:
            date_label = f'{abs(r["date_start"])} BC'
        elif r['date_start'] < 1000:
            date_label = f'{r["date_start"]} AD'
        lines.append(f"- Meanwhile in {r['domain_title']}: {r['title']} (~{date_label})")

    return ('Contemporaneous events the learner knows from other domains:\n'
            + '\n'.join(lines))


def generate_question(item_id: str, conn) -> dict:
    # First try knowledge_items (node-centric); fall back to review_items (exploration/voice);
    # finally knowledge_entities (entity-keyed, no curriculum)
    row = conn.execute('SELECT * FROM knowledge_items WHERE id=?', (item_id,)).fetchone()
    if row is None:
        row = conn.execute('SELECT * FROM review_items WHERE id=?', (item_id,)).fetchone()
    if row is None:
        # Entity-keyed items — delegate to the entity question generator
        try:
            ke_row = conn.execute('SELECT id FROM knowledge_entities WHERE id=?', (item_id,)).fetchone()
            if ke_row:
                return generate_entity_question(item_id, conn)
        except Exception:
            pass
    if not row:
        return {}
    item = dict(row)

    domain_id = item.get('curriculum_domain') or 'sicily_history_culture_and_legacy'
    curriculum = load_curriculum(domain_id)
    knowledge_state = load_knowledge_states(domain_id)

    node = next((n for n in (curriculum or {}).get('nodes', [])
                 if n['id'] == item.get('curriculum_node_id')), None)

    # ── Check key_facts FIRST (deterministic, no LLM) ────────────────────────
    # key_facts live in SQLite (not in curriculum JSON files), so query DB directly
    key_facts = []
    node_id = item.get('curriculum_node_id')
    if node_id and domain_id:
        try:
            kf_row = conn.execute(
                'SELECT key_facts FROM curriculum_nodes WHERE id=? AND domain_id=?',
                (node_id, domain_id)
            ).fetchone()
            if kf_row and kf_row['key_facts']:
                key_facts = json.loads(kf_row['key_facts'])
        except Exception:
            key_facts = []

    if key_facts:
        try:
            question_history = json.loads(item.get('question_history') or '[]')
        except Exception:
            question_history = []
        review_count = item.get('review_count', 0) + 1

        if review_count <= len(key_facts):
            fact = _pick_key_fact(key_facts, question_history)
            if fact:
                node_title = node['title'] if node else ''
                node_description = node.get('description', '') if node else ''
                result = _key_fact_to_question(fact, node_title, node_description,
                                                conn=conn, node_id=node_id, domain_id=domain_id)
                fact_q = fact.get('question', '')
                fact_a = fact.get('answer', '')
                fact_ctx = f'{fact_q} — {fact_a}' if fact_a else fact_q
                fqs = _generate_follow_up_queries(node_title, node_description, fact_ctx,
                                                    conn=conn, node_id=node_id, domain_id=domain_id)
                if fqs:
                    result['follow_up_queries'] = fqs
                # No fallback templates — empty is better than generic
                return result

    # ── Serve from cache if no key_facts path applied ─────────────────────────
    if item.get('cached_question'):
        try:
            cached = json.loads(item['cached_question'])
            # If cached question has fact_id, it's from key_facts — serve it
            # If not, it's an old LLM question — still serve as fallback
            return cached
        except Exception:
            pass

    # ── LLM path: reviews 3+ or no key_facts ────────────────────────────────
    node_title = node['title'] if node else item.get('curriculum_node_title', item.get('curriculum_node_id', ''))
    node_description = node.get('description', '') if node else ''

    # Resolve source_text and temporal_hook
    if 'sources' in item and item['sources']:
        try:
            sources = json.loads(item['sources'])
        except Exception:
            sources = []
        best = _best_source_for_question(sources)
        source_text = best.get('source_text', '')
        temporal_hook = best.get('temporal_hook', '')
        lens = best.get('lens', 'SIGNIFICANCE')
    else:
        source_text = item.get('source_text', '')
        temporal_hook = item.get('temporal_hook', '')
        lens = item.get('lens', 'SIGNIFICANCE')

    try:
        question_history = json.loads(item.get('question_history') or '[]')
    except Exception:
        question_history = []

    review_count = item.get('review_count', 0) + 1

    known = [n['title'] for n in (curriculum or {}).get('nodes', [])
             if knowledge_state.get(n['id'], {}).get('knowledge') in ('engaged', 'anchored')
             and n['id'] != item.get('curriculum_node_id')]

    known_ctx = ''
    if known[:3]:
        known_ctx = ('Other concepts the learner knows:\n'
                     + '\n'.join(f'- {t}' for t in known[:3]))

    # Cross-curriculum context: what the learner knows about related entities from other domains
    cross_ctx = _get_cross_curriculum_context(domain_id, node_id, conn)
    if cross_ctx:
        known_ctx = (known_ctx + '\n\n' + cross_ctx) if known_ctx else cross_ctx

    temporal_ctx = ''
    if temporal_hook:
        temporal_ctx = f"Temporal hook: {temporal_hook}"

    # Temporal cross-references: contemporaneous events from other domains
    temporal_xref = _get_temporal_cross_references(domain_id, node_id, conn)
    if temporal_xref:
        temporal_ctx = (temporal_ctx + '\n\n' + temporal_xref) if temporal_ctx else temporal_xref

    # Include mastered key_facts as context for analytical questions
    known_facts_ctx = ''
    if key_facts:
        mastered = [f for f in key_facts if f.get('id') in
                    {h.get('fact_id') for h in question_history if h.get('score') == 'knew'}]
        if mastered:
            known_facts_ctx = 'Facts the learner already knows:\n' + '\n'.join(
                f'- {f["question"]} → {f["answer"]}' for f in mastered[:6])

    # Learner context from voice elicitation
    learner_ctx = get_learner_context(node_id, domain_id, conn) if node_id and domain_id else ''

    if review_count <= 2 and not key_facts:
        # No key_facts available — use LLM factual prompt
        prompt = QUESTION_GEN_PROMPT_FACTUAL.format(
            node_title=node_title,
            node_description=node_description,
            source_text=source_text[:400],
            temporal_context=temporal_ctx,
            learner_context=learner_ctx,
        )
    else:
        if review_count == 3:
            difficulty = f'Review #{review_count} — now that the fact is solid, ask why it mattered or what caused it.'
        else:
            difficulty = f'Review #{review_count} — push for comparisons, patterns, or long-term implications.'

        prompt = QUESTION_GEN_PROMPT.format(
            node_title=node_title,
            node_description=node_description,
            source_text=source_text[:400],
            review_count=review_count,
            lens=lens,
            difficulty_instruction=difficulty,
            known_nodes_context=known_ctx, temporal_context=temporal_ctx,
            learner_context=learner_ctx,
        )
        if known_facts_ctx:
            prompt += f'\n\n{known_facts_ctx}'

    result = call_claude_json(prompt, timeout=120)

    if isinstance(result, dict) and 'question' in result:
        result.setdefault('temporal_hook', temporal_hook)
    else:
        result = {
            'question': f'What was historically significant about {node_title}?',
            'answer_guidance': source_text,
            'temporal_hook': temporal_hook,
            'curriculum_context': '',
        }

    # Generate follow-up research queries via Claude
    if 'follow_up_queries' not in result:
        fqs = _generate_follow_up_queries(node_title, node_description,
                                          source_text[:200] if source_text else '',
                                          conn=conn, node_id=node_id, domain_id=domain_id)
        if fqs:
            result['follow_up_queries'] = fqs

    # Factual quiz suggestions — deterministic from key_facts not yet quizzed
    if conn and node_id and domain_id:
        result['quiz_suggestions'] = _build_quiz_suggestions(node_id, domain_id, conn)

    return result


def _build_quiz_suggestions(node_id: str, domain_id: str, conn) -> list[dict]:
    """Build up to 3 factual quiz suggestions from key_facts not yet covered by quizzes."""
    try:
        node = conn.execute(
            'SELECT key_facts FROM curriculum_nodes WHERE id=? AND domain_id=?',
            (node_id, domain_id)).fetchone()
        if not node or not node['key_facts']:
            return []
        key_facts = json.loads(node['key_facts'])
        if not key_facts:
            return []

        # Find which questions already exist as microlearning_quizzes (via parent knowledge_item)
        ki = conn.execute(
            'SELECT id FROM knowledge_items WHERE curriculum_node_id=? AND curriculum_domain=?',
            (node_id, domain_id)).fetchone()
        existing_qs = set()
        if ki:
            # Check quizzes from ML cards sourced from this node
            quiz_rows = conn.execute('''
                SELECT mq.question FROM microlearning_quizzes mq
                JOIN microlearning_cards mc ON mq.card_id = mc.id
                WHERE mc.source_node_id = ? AND mc.source_domain = ?
            ''', (node_id, domain_id)).fetchall()
            existing_qs = {r['question'].lower().strip() for r in quiz_rows if r['question']}

        suggestions = []
        for fact in key_facts:
            if len(suggestions) >= 3:
                break
            question = fact.get('question', '').strip()
            answer = fact.get('answer', '').strip()
            if not question or not answer:
                continue
            if question.lower().strip() in existing_qs:
                continue
            suggestions.append({
                'question': question,
                'answer': answer,
                'fact_id': fact.get('id', ''),
                'type': fact.get('type', 'fact'),
            })
        return suggestions
    except Exception:
        return []


# ── Entity-keyed question generation (Phase 1 of entity-first architecture) ─
# Phase 2 (Session 78) extends question generation with entity-graph context:
# Wikidata structured properties, scoped temporal neighbors, voice-capture
# co-occurrence. All enrichment preserves the invariant that cards reference
# facts the user has actually captured — Wikidata properties are framed as
# retrieval prompts ("you captured X reigned Y-Z; who succeeded?"), never
# as standalone assertions. See research/entity-first-architecture.md.

# Per-type Wikidata property sets. Conservative starter set — extend as we
# observe which properties produce retention-useful enrichment. Every P-number
# here is verified (P1365=replaces, P1366=replaced by; the Phase 2 prompt's
# "P2962" was wrong).
_WIKIDATA_PROPS_BY_TYPE: dict[str, tuple[str, ...]] = {
    'person': (
        'P22',    # father
        'P25',    # mother
        'P26',    # spouse
        'P40',    # child
        'P27',    # country of citizenship
        'P19',    # place of birth
        'P20',    # place of death
        'P39',    # position held
        'P106',   # occupation
        'P569',   # date of birth
        'P570',   # date of death
        'P1365',  # replaces (predecessor in position)
        'P1366',  # replaced by (successor in position)
    ),
    'battle': (
        'P710',   # participant
        'P276',   # location
        'P585',   # point in time
        'P580',   # start time
        'P582',   # end time
        'P607',   # conflict (parent war)
        'P1542',  # has effect / caused by
    ),
    'event': (
        'P710',   # participant
        'P31',    # instance of
        'P585',   # point in time
        'P580',   # start time
        'P582',   # end time
        'P276',   # location
        'P1542',  # has effect
    ),
    'place': (
        'P17',    # country
        'P131',   # located in administrative territorial entity
        'P571',   # inception
        'P576',   # dissolution
    ),
    'work': (
        'P50',    # author
        'P577',   # publication date
        'P136',   # genre
    ),
}

# Wikidata-props cache freshness: refetch after this many days.
_WIKIDATA_PROPS_TTL_DAYS = 90


def _fetch_wikidata_props(qid: str, entity_type: str | None) -> dict:
    """Fetch structured Wikidata properties for an entity.

    Returns {"P22": [{"qid": "Q...", "label": "..."}, ...], "P569": [{"time": "+1682-..."}], ...}
    Property types are one of:
    - wikibase-item   → {"qid", "label"}  (requires a secondary get_many to resolve labels)
    - time            → {"time"} raw Wikidata string
    - external-id     → {"value"}
    - string          → {"value"}

    Returns {} on any failure (no QID, network error, etc.). Never raises.
    """
    if not qid:
        return {}
    try:
        from limbic.amygdala.wikidata import WikidataClient
    except ImportError:
        return {}

    # Look up props for the given type. For unknown/legacy types (e.g. the
    # literal 'entity' fallback used before Session 77's classifier fix), fetch
    # the UNION of all property sets. Most won't apply to the entity — they
    # just return empty lists — but this avoids missing battle/event props
    # when the type label is stale.
    type_key = (entity_type or '').lower()
    props_to_fetch = _WIKIDATA_PROPS_BY_TYPE.get(type_key)
    if props_to_fetch is None:
        all_props: set[str] = set()
        for ps in _WIKIDATA_PROPS_BY_TYPE.values():
            all_props.update(ps)
        props_to_fetch = tuple(sorted(all_props))

    try:
        client = WikidataClient(user_agent="Petrarca/0.1 (mailto:stian@haklev.com)")
        entity = client.get(qid)
        if entity is None:
            return {}

        result: dict[str, list[dict]] = {}
        qids_needing_labels: set[str] = set()

        for prop in props_to_fetch:
            statements = entity.claims.get(prop, [])
            if not statements:
                continue
            values = []
            for stmt in statements:
                if stmt.get('rank') == 'deprecated':
                    continue
                mainsnak = stmt.get('mainsnak') or {}
                dtype = mainsnak.get('datatype')
                dv = (mainsnak.get('datavalue') or {}).get('value')
                if dv is None:
                    continue
                if dtype == 'wikibase-item' and isinstance(dv, dict) and 'id' in dv:
                    values.append({'qid': dv['id']})
                    qids_needing_labels.add(dv['id'])
                elif dtype == 'time' and isinstance(dv, dict):
                    values.append({'time': dv.get('time', '')})
                elif dtype == 'external-id':
                    values.append({'value': dv})
                elif isinstance(dv, str):
                    values.append({'value': dv})
            if values:
                result[prop] = values

        # Second pass: resolve labels for referenced QIDs
        if qids_needing_labels:
            label_entities = client.get_many(list(qids_needing_labels))
            for prop, values in result.items():
                for v in values:
                    ref_qid = v.get('qid')
                    if ref_qid and ref_qid in label_entities:
                        lbl = label_entities[ref_qid].label('en')
                        if lbl:
                            v['label'] = lbl

        return result
    except Exception as e:
        print(f'[entity-q] wikidata props fetch failed for {qid}: {e}', flush=True)
        return {}


def _get_or_fetch_entity_props(ke_row: dict, conn) -> dict:
    """Return cached Wikidata props, refetching if absent or stale.

    Reads `wikidata_props_json` from the knowledge_entities row. If missing,
    stale (> TTL), or empty, hits Wikidata and caches the fresh result via
    a separate short write transaction. Returns just the {"P..": [...]} dict,
    not the full cache envelope.
    """
    cached_raw = ke_row.get('wikidata_props_json')
    if cached_raw:
        try:
            cached = json.loads(cached_raw)
            fetched_at = cached.get('fetched_at', 0)
            age_days = (time.time() - fetched_at) / 86400.0
            if age_days < _WIKIDATA_PROPS_TTL_DAYS and cached.get('props'):
                return cached['props']
        except (json.JSONDecodeError, TypeError):
            pass

    qid = ke_row.get('wikidata_qid')
    if not qid:
        return {}

    # Release any existing read lock before network I/O
    props = _fetch_wikidata_props(qid, ke_row.get('entity_type'))
    if not props:
        return {}

    # Short write transaction — LLM calls haven't run yet
    envelope = {'fetched_at': int(time.time()), 'props': props}
    try:
        from db import get_connection
        wconn = get_connection()
        wconn.execute(
            'UPDATE knowledge_entities SET wikidata_props_json=? WHERE id=?',
            (json.dumps(envelope), ke_row['id']),
        )
        wconn.commit()
        wconn.close()
    except Exception as e:
        print(f'[entity-q] failed to cache wikidata props for {ke_row.get("id")}: {e}',
              flush=True)

    return props


def _get_scoped_temporal_neighbors(
    entity_id: str | None, qid: str | None,
    date_start: int | None, date_end: int | None,
    conn, window_years: int = 50, limit: int = 5,
) -> list[dict]:
    """Find entities in the user's own graph with overlapping date ranges.

    Scope: `shared_entities` rows that are either (a) keyed in
    `knowledge_entities`, or (b) linked via `entity_curriculum_links` to a
    `knowledge_items` row the user has seen. Excludes the entity itself.

    Returns list of dicts: [{"name", "description", "date_start", "date_end",
    "entity_type", "source"}]. `source` is 'entity' or 'curriculum'. Sorted
    by temporal proximity (closest date_start first).
    """
    if date_start is None and date_end is None:
        return []
    ds = date_start if date_start is not None else date_end
    de = date_end if date_end is not None else date_start
    window_lo = (ds or 0) - window_years
    window_hi = (de or 0) + window_years

    try:
        rows = conn.execute(
            """
            SELECT se.entity_id, se.name, se.description, se.entity_type,
                   se.date_start, se.date_end,
                   CASE
                       WHEN EXISTS (SELECT 1 FROM knowledge_entities ke2
                                    WHERE ke2.entity_id = se.entity_id)
                       THEN 'entity'
                       ELSE 'curriculum'
                   END AS source
            FROM shared_entities se
            WHERE se.date_start IS NOT NULL
              AND se.date_end IS NOT NULL
              AND se.date_start <= ?
              AND se.date_end >= ?
              AND (se.entity_id != ? OR ? IS NULL)
              AND (
                  EXISTS (
                      SELECT 1 FROM knowledge_entities ke
                      WHERE ke.entity_id = se.entity_id
                  )
                  OR EXISTS (
                      SELECT 1 FROM entity_curriculum_links ecl
                      JOIN knowledge_items ki
                          ON ki.curriculum_domain = ecl.domain_id
                         AND ki.curriculum_node_id = ecl.node_id
                      WHERE ecl.entity_id = se.entity_id
                  )
              )
            ORDER BY ABS(se.date_start - ?) ASC
            LIMIT ?
            """,
            (window_hi, window_lo, entity_id, entity_id, ds or 0, limit),
        ).fetchall()
    except Exception as e:
        print(f'[entity-q] temporal-neighbor query failed: {e}', flush=True)
        return []

    return [dict(r) for r in rows]


def _get_voice_cooccurring_entities(
    entity_name: str, conn, limit: int = 3,
) -> list[dict]:
    """Entities most frequently mentioned alongside this one in voice captures.

    Walks `voice_transcripts.llm_result.entities_mentioned`. For each
    transcript that mentions this entity, tally all OTHER entities in the
    same list. Return top-N by count.

    Uses simple name matching (case-insensitive substring) because
    entity_name is what the LLM extracted — not necessarily a QID.
    """
    if not entity_name:
        return []

    target = entity_name.strip().lower()
    counts: dict[str, int] = {}

    try:
        rows = conn.execute(
            """
            SELECT llm_result FROM voice_transcripts
            WHERE llm_result IS NOT NULL
              AND llm_result LIKE ?
            """,
            (f'%{entity_name}%',),
        ).fetchall()
    except Exception as e:
        print(f'[entity-q] co-occurrence query failed: {e}', flush=True)
        return []

    for r in rows:
        try:
            lr = json.loads(r['llm_result']) if r['llm_result'] else {}
        except (json.JSONDecodeError, TypeError):
            continue
        mentioned = lr.get('entities_mentioned') or []
        if not isinstance(mentioned, list):
            continue
        names = [str(m).strip() for m in mentioned if m]
        # Did this transcript actually mention our target?
        if not any(target == n.lower() or target in n.lower() for n in names):
            continue
        for n in names:
            if n.lower() == target or target in n.lower():
                continue
            counts[n] = counts.get(n, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return [{'name': n, 'count': c} for n, c in ranked]


def _format_entity_graph_context(
    entity_name: str,
    props: dict,
    neighbors: list[dict],
    cooccur: list[dict],
) -> str:
    """Render entity-graph context into a prompt-ready text block.

    Returns empty string when nothing to say — the prompt template then
    just emits a blank line rather than a labeled-but-empty section.
    """
    blocks: list[str] = []

    # --- Wikidata structured properties ---
    prop_lines: list[str] = []
    _HUMAN_LABEL = {
        'P22': 'father',
        'P25': 'mother',
        'P26': 'spouse',
        'P40': 'child',
        'P27': 'citizenship',
        'P19': 'birthplace',
        'P20': 'place of death',
        'P31': 'type',
        'P39': 'position held',
        'P106': 'occupation',
        'P569': 'born',
        'P570': 'died',
        'P1365': 'succeeded',   # this entity replaces X
        'P1366': 'succeeded by',  # this entity replaced by X
        'P710': 'participants',
        'P276': 'location',
        'P585': 'date',
        'P580': 'start',
        'P582': 'end',
        'P607': 'part of war',
        'P1542': 'consequence',
        'P17': 'country',
        'P131': 'located in',
        'P571': 'founded',
        'P576': 'dissolved',
        'P50': 'author',
        'P577': 'published',
        'P136': 'genre',
    }

    def _fmt_value(v: dict) -> str:
        if 'label' in v:
            return v['label']
        if 'qid' in v:
            return v['qid']
        if 'time' in v:
            t = v['time'] or ''
            sign = '-' if t.startswith('-') else ''
            year_part = t.lstrip('+-').split('-')[0]
            return f'{sign}{year_part}' if year_part else t
        return str(v.get('value', ''))

    for prop, values in props.items():
        label = _HUMAN_LABEL.get(prop, prop)
        rendered = [_fmt_value(v) for v in values[:5]]
        # Dedup while preserving order (Julian/Gregorian calendar dupes etc.)
        seen: set[str] = set()
        unique_rendered = []
        for r in rendered:
            if r and r not in seen:
                seen.add(r)
                unique_rendered.append(r)
        if unique_rendered:
            prop_lines.append(f'- {label}: {", ".join(unique_rendered[:3])}')
    if prop_lines:
        blocks.append('Wikidata properties for ' + entity_name + ':\n' + '\n'.join(prop_lines))

    # --- Temporal neighbors (scoped) ---
    if neighbors:
        lines = []
        for n in neighbors[:5]:
            dates = ''
            if n.get('date_start') is not None and n.get('date_end') is not None:
                ds = n['date_start']
                de = n['date_end']
                dates = f' ({ds}–{de})' if ds != de else f' ({ds})'
            desc = (n.get('description') or '')[:80]
            lines.append(f'- {n["name"]}{dates}: {desc}'.rstrip(': '))
        blocks.append("Other entities you've captured from the same period:\n" + '\n'.join(lines))

    # --- Voice-capture co-occurrence ---
    if cooccur:
        lines = [f'- {c["name"]} (mentioned together in {c["count"]} capture{"s" if c["count"] != 1 else ""})'
                 for c in cooccur]
        blocks.append("Entities you've discussed alongside " + entity_name + ':\n' + '\n'.join(lines))

    return '\n\n'.join(blocks)


def generate_entity_question(ke_id: str, conn) -> dict:
    """Generate a review question for a knowledge_entities item.

    Phase 1: uses `_key_fact_to_question` with entity_name/desc substituted.
    Phase 2: additionally enriches the LLM prompt with entity-graph context
    (Wikidata props + scoped temporal neighbors + voice co-occurrence). The
    enrichment context is passed to `_key_fact_to_question` via its
    optional `entity_graph_context` parameter. No curriculum context.
    """
    row = conn.execute('SELECT * FROM knowledge_entities WHERE id=?', (ke_id,)).fetchone()
    if not row:
        return {}
    item = dict(row)

    try:
        key_facts = json.loads(item.get('key_facts') or '[]')
    except (json.JSONDecodeError, TypeError):
        key_facts = []
    if not key_facts:
        return {}

    try:
        question_history = json.loads(item.get('question_history') or '[]')
    except (json.JSONDecodeError, TypeError):
        question_history = []

    fact = _pick_key_fact(key_facts, question_history)
    if not fact:
        # All facts tested — rotate back to the first one for continued drilling
        fact = key_facts[0]

    entity_name = item.get('entity_name') or ''
    entity_desc = ''
    entity_date_start = None
    entity_date_end = None
    # Pull description + dates from shared_entities if linked (post Wikidata resolution)
    if item.get('entity_id'):
        try:
            se_row = conn.execute(
                'SELECT description, date_start, date_end FROM shared_entities WHERE entity_id=?',
                (item['entity_id'],)
            ).fetchone()
            if se_row:
                if se_row['description']:
                    entity_desc = se_row['description']
                entity_date_start = se_row['date_start']
                entity_date_end = se_row['date_end']
        except Exception:
            pass

    # --- Phase 2: entity-graph context ---
    # Assemble enrichment BEFORE the LLM call. All three sources degrade
    # gracefully to empty on missing QID / missing dates / DB errors.
    props = _get_or_fetch_entity_props(item, conn) if item.get('wikidata_qid') else {}
    neighbors = _get_scoped_temporal_neighbors(
        item.get('entity_id'), item.get('wikidata_qid'),
        entity_date_start, entity_date_end, conn,
    )
    cooccur = _get_voice_cooccurring_entities(entity_name, conn)
    entity_graph_context = _format_entity_graph_context(
        entity_name, props, neighbors, cooccur,
    )

    result = _key_fact_to_question(
        fact, entity_name, entity_desc,
        conn=None, node_id=None, domain_id=None,
        entity_graph_context=entity_graph_context,
    )

    # Generate sideways follow-up queries (Gemini Flash) so entity cards get
    # the same "Also explore…" chips as curriculum cards.
    # See research/session-77-observations.md Gap A.
    try:
        fact_ctx = f"{fact.get('question', '')} — {fact.get('answer', '')}"
        follow_ups = _generate_follow_up_queries(
            node_title=entity_name,
            node_description=entity_desc,
            fact_context=fact_ctx,
            conn=None, node_id=None, domain_id=None,
        )
        if follow_ups:
            result['follow_up_queries'] = follow_ups
    except Exception as e:
        print(f'[entity-q] follow-up gen failed for {entity_name}: {e}', flush=True)

    return result


# ── Multi-cue quiz generation ────────────────────────────────────────────────

MULTICUE_PROMPT = """Generate 2-4 retrieval cue questions for each historical fact. These are alternate quiz angles for the SAME fact — like flashcard reversals for dates, battles, people, conquests.

Rules:
- Short pub-quiz style questions (under 15 words)
- Short answers (1 sentence)
- Each cue approaches from a different angle: "Who did X?", "When did X happen?", "What did [person] conquer/do?", "What battle decided X?", "What happened in [year]?"
- Only generate angles where the answer is clear and unambiguous
- Do NOT include the original question — only new angles

Facts:
{facts_json}

Return JSON: {{"0": [{{"question": "...", "answer": "..."}}], ...}}
"""


def generate_multicue_quizzes(node_id: str, domain_id: str):
    """Generate multi-angle retrieval cue quizzes for a node's key_facts.

    Called as a background thread after grading. Uses Gemini Flash for
    natural question generation, then deduplicates via embeddings.
    Only processes date/event/person type facts.
    """
    from db import get_connection
    conn = get_connection()
    try:
        node = conn.execute(
            'SELECT key_facts FROM curriculum_nodes WHERE id=? AND domain_id=?',
            (node_id, domain_id)).fetchone()
        if not node or not node['key_facts']:
            return
        all_facts = json.loads(node['key_facts'])

        # Filter to factual types only — skip significance/connection for now
        FACTUAL_TYPES = {'date', 'event', 'person', 'fact', 'place'}
        facts = [f for f in all_facts if f.get('type', 'fact') in FACTUAL_TYPES
                 and f.get('question') and f.get('answer')]
        if not facts:
            return

        # Check which fact_ids already have multi-cue quizzes
        existing_fact_ids = set()
        for row in conn.execute(
            "SELECT DISTINCT fact_id FROM microlearning_quizzes WHERE fact_id IS NOT NULL"
        ).fetchall():
            existing_fact_ids.add(row['fact_id'])

        facts_to_process = [f for f in facts if f.get('id') and f['id'] not in existing_fact_ids]
        if not facts_to_process:
            print(f'[multicue] {node_id}: all facts already have cues, skipping', flush=True)
            return

        # Release DB before LLM call
        conn.close()
        conn = None

        # Build prompt with indexed facts
        facts_for_prompt = {str(i): {'question': f['question'], 'answer': f['answer'],
                                      'entities': f.get('entities', []), 'type': f.get('type', '')}
                            for i, f in enumerate(facts_to_process)}
        prompt = MULTICUE_PROMPT.format(facts_json=json.dumps(facts_for_prompt, indent=2))

        from gemini_llm import call_llm
        result = call_llm(prompt, max_tokens=2000, response_mime_type='application/json')
        if not result:
            print(f'[multicue] {node_id}: Gemini returned no result', flush=True)
            return

        try:
            cues_by_idx = json.loads(result)
        except json.JSONDecodeError as e:
            print(f'[multicue] {node_id}: JSON parse error: {e}', flush=True)
            return

        # Reopen DB for writes
        conn = get_connection()

        # Find or create a ML card container for this node
        mc = conn.execute(
            'SELECT id FROM microlearning_cards WHERE source_node_id=? AND source_domain=? LIMIT 1',
            (node_id, domain_id)).fetchone()
        if mc:
            card_id = mc['id']
        else:
            import hashlib
            card_id = hashlib.md5(f"{node_id}:{domain_id}:multicue".encode()).hexdigest()[:12]
            now_ms = int(time.time() * 1000)
            conn.execute('''
                INSERT OR IGNORE INTO microlearning_cards
                (id, query, source_node_id, source_domain, content, status, created_at, source_type)
                VALUES (?,?,?,?,?,?,?,?)
            ''', (card_id, f"Multi-cue quizzes for {node_id}", node_id,
                  domain_id, '', 'completed', now_ms, 'multicue'))

        # Load embedding model for dedup
        model = None
        existing_embedded = []
        try:
            from limbic.amygdala import EmbeddingModel
            model = EmbeddingModel()
            existing_texts = [r['question'] for r in conn.execute(
                "SELECT question FROM microlearning_quizzes WHERE status='active'"
            ).fetchall()]
            if existing_texts:
                vecs = model.embed_batch(existing_texts)
                existing_embedded = list(zip(existing_texts, vecs))
        except Exception as e:
            print(f'[multicue] dedup init failed, proceeding without: {e}', flush=True)

        stored, skipped = 0, 0
        now_ms = int(time.time() * 1000)

        for idx_str, cues in cues_by_idx.items():
            try:
                fact = facts_to_process[int(idx_str)]
            except (ValueError, IndexError):
                continue

            fact_id = fact.get('id', '')
            rich_answer = fact.get('rich_answer') or fact.get('answer', '')

            for ci, cue in enumerate(cues):
                question = cue.get('question', '').strip()
                answer = cue.get('answer', '').strip()
                if not question or not answer:
                    continue

                # Dedup check
                if model and existing_embedded:
                    dup = _find_duplicate_quiz(question, existing_embedded, model)
                    if dup:
                        skipped += 1
                        continue

                import hashlib
                quiz_id = hashlib.md5(f"{card_id}:{fact_id}:{ci}".encode()).hexdigest()[:12]
                conn.execute('''
                    INSERT OR IGNORE INTO microlearning_quizzes
                    (id, card_id, question, answer, fact_id, rich_answer,
                     status, stability_days, due_at, review_count, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ''', (quiz_id, card_id, question, answer, fact_id, rich_answer,
                      'active', 1.0, now_ms + 86400000, 0, now_ms))

                if model:
                    existing_embedded.append((question, model.embed(question)))
                stored += 1

        conn.commit()
        print(f'[multicue] {node_id}: {stored} cues stored, {skipped} deduped '
              f'from {len(facts_to_process)} facts', flush=True)

    except Exception as e:
        print(f'[multicue] {node_id}: error: {e}', flush=True)
        import traceback; traceback.print_exc()
    finally:
        if conn:
            conn.close()


# ── Record answer ─────────────────────────────────────────────────────────────

def record_answer(item_id: str, score: str, conn) -> dict:
    # Look up in knowledge_items first; fall back to review_items,
    # then microlearning_quizzes, then knowledge_entities, then microlearning_cards
    row = conn.execute('SELECT * FROM knowledge_items WHERE id=?', (item_id,)).fetchone()
    table = 'knowledge_items'
    if row is None:
        row = conn.execute('SELECT * FROM review_items WHERE id=?', (item_id,)).fetchone()
        table = 'review_items'
    if row is None:
        try:
            row = conn.execute('SELECT * FROM microlearning_quizzes WHERE id=?', (item_id,)).fetchone()
            if row:
                table = 'microlearning_quizzes'
        except Exception:
            pass
    if row is None:
        try:
            row = conn.execute('SELECT * FROM knowledge_entities WHERE id=?', (item_id,)).fetchone()
            if row:
                table = 'knowledge_entities'
        except Exception:
            pass
    if row is None:
        row = conn.execute('SELECT * FROM microlearning_cards WHERE id=?', (item_id,)).fetchone()
        table = 'microlearning_cards'
    if not row:
        return {}
    item = dict(row)

    now = int(time.time() * 1000)

    # ── FSRS-6 scheduling ────────────────────────────────────────────────────
    card_json = item.get('fsrs_card_json')
    if card_json:
        card_data = json.loads(card_json) if isinstance(card_json, str) else card_json
        card = FsrsCard.from_dict(card_data)
    else:
        card = FsrsCard()

    fsrs_rating = SCORE_TO_FSRS.get(score, FsrsRating.Again)
    now_dt = datetime.now(timezone.utc)
    new_card, _review_log = _fsrs_scheduler.review_card(card, fsrs_rating, now_dt)
    new_stability = new_card.stability or 1.0
    next_due = int(new_card.due.timestamp() * 1000)
    card_dict = new_card.to_dict()
    fsrs_json = json.dumps(card_dict)

    if table == 'microlearning_quizzes':
        # Individual quiz from a microlearning card
        conn.execute("""
            UPDATE microlearning_quizzes SET stability_days=?, due_at=?, last_reviewed_at=?,
              last_score=?, review_count=review_count+1, fsrs_card_json=?
            WHERE id=?
        """, (new_stability, next_due, now, score, fsrs_json, item_id))
        print(f'[review] ml_quiz {item_id}: {score} → stability={new_stability:.1f}d due={new_card.due.strftime("%m-%d")}', flush=True)

        # Propagate knowledge update via the parent card's curriculum context
        parent = conn.execute(
            'SELECT source_domain, source_node_id FROM microlearning_cards WHERE id=?',
            (item['card_id'],)).fetchone()
        if parent and parent['source_domain'] and parent['source_node_id']:
            knowledge_val, confidence_val = SCORE_TO_KNOWLEDGE.get(score, ('unknown', 0.0))
            update_knowledge(parent['source_domain'], parent['source_node_id'],
                             knowledge=knowledge_val, confidence=confidence_val,
                             source=f"microlearning:{item_id}", conn=conn)

    elif table == 'microlearning_cards':
        # Legacy: whole microlearning card as review unit
        conn.execute("""
            UPDATE microlearning_cards SET stability_days=?, due_at=?, last_reviewed_at=?,
              last_score=?, review_count=review_count+1, fsrs_card_json=?
            WHERE id=?
        """, (new_stability, next_due, now, score, fsrs_json, item_id))
        print(f'[review] microlearning {item_id}: {score} → stability={new_stability:.1f}d', flush=True)

        if item.get('source_domain') and item.get('source_node_id'):
            knowledge_val, confidence_val = SCORE_TO_KNOWLEDGE.get(score, ('unknown', 0.0))
            update_knowledge(item['source_domain'], item['source_node_id'],
                             knowledge=knowledge_val, confidence=confidence_val,
                             source=f"microlearning:{item_id}", conn=conn)
    else:
        # Regular knowledge_items / review_items
        conn.execute(f"""
            UPDATE {table} SET stability_days=?, due_at=?, last_reviewed_at=?,
              last_score=?, review_count=review_count+1, cached_question=NULL, fsrs_card_json=?
            WHERE id=?
        """, (new_stability, next_due, now, score, fsrs_json, item_id))

    # Knowledge state update for non-microlearning items
    if table != 'microlearning_cards' and item.get('curriculum_domain') and item.get('curriculum_node_id'):
        knowledge_val, confidence_val = SCORE_TO_KNOWLEDGE.get(score, ('unknown', 0.0))
        if table == 'knowledge_items':
            try:
                sources = json.loads(item.get('sources') or '[]')
                best = _best_source_for_question(sources)
                src_book = best.get('book_id', '')
                src_chapter = best.get('chapter_number', '')
            except Exception:
                src_book, src_chapter = '', ''
        else:
            src_book = item.get('source_book_id', '')
            src_chapter = item.get('source_chapter_number', '')
        update_knowledge(item['curriculum_domain'], item['curriculum_node_id'],
                         knowledge=knowledge_val, confidence=confidence_val,
                         source=f"review:{src_book}:{src_chapter}", conn=conn)

    # Reschedule dependents on miss (applies to all card types with curriculum context)
    domain = item.get('curriculum_domain') or item.get('source_domain')
    node_id = item.get('curriculum_node_id') or item.get('source_node_id')
    if score == 'missed' and domain and node_id:
        curriculum = load_curriculum(domain)
        if curriculum:
            dep_ids = get_dependent_node_ids(node_id, curriculum)
            if dep_ids:
                soon = now + 24 * 60 * 60 * 1000
                ph = ','.join('?' * len(dep_ids))
                conn.execute(
                    f"UPDATE knowledge_items SET stability_days=1.0, due_at=? WHERE curriculum_node_id IN ({ph}) AND (last_score IS NULL OR last_score != 'knew')",
                    [soon] + dep_ids,
                )
                conn.execute(
                    f"UPDATE review_items SET stability_days=1.0, due_at=? WHERE curriculum_node_id IN ({ph}) AND (last_score IS NULL OR last_score != 'knew')",
                    [soon] + dep_ids,
                )

    conn.commit()

    # ── Leech detection: auto-suspend items with 7+ consecutive misses ───
    leech_suspended = False
    if score == 'missed' and (item.get('review_count') or 0) >= 5:
        try:
            recent = conn.execute("""
                SELECT score FROM interaction_log
                WHERE item_id=? AND score IN ('knew', 'partly', 'missed')
                  AND event IN ('review_answer', 'review_result', 'review_quiz_result')
                ORDER BY created_at DESC LIMIT 7
            """, (item_id,)).fetchall()
            consecutive_misses = 0
            for r in recent:
                if r['score'] == 'missed':
                    consecutive_misses += 1
                else:
                    break
            if consecutive_misses >= 7:
                # Auto-suspend for 30 days
                suspend_until = now + 30 * 24 * 60 * 60 * 1000
                conn.execute(
                    f'UPDATE {table} SET due_at=?, cached_question=NULL WHERE id=?',
                    (suspend_until, item_id))
                conn.commit()
                leech_suspended = True
                print(f'[leech] auto-suspended {item_id} ({consecutive_misses} consecutive misses)', flush=True)
                try:
                    from server_log import log_interaction
                    log_interaction('leech_suspended', item_id=item_id,
                                    item_type=table, consecutive_misses=consecutive_misses)
                except Exception:
                    pass
        except Exception as e:
            print(f'[leech] detection error for {item_id}: {e}', flush=True)

    # Background re-generation — pre-cache question for next session (not for microlearning)
    # For leeches, regeneration happens on unsuspend
    if table != 'microlearning_cards' and not leech_suspended:
        def _regen():
            try:
                from db import get_connection as _conn
                c = _conn()
                q = generate_question(item_id, c)
                c.execute(f'UPDATE {table} SET cached_question=? WHERE id=?',
                          (json.dumps(q), item_id))
                c.commit()
                c.close()
                print(f'[review] re-generated question for {table} item {item_id}', flush=True)
            except Exception as e:
                print(f'[review] re-gen failed for {table} item {item_id}: {e}', flush=True)
        threading.Thread(target=_regen, daemon=True).start()

    # Background multi-cue quiz generation for knowledge_items with key_facts
    if table == 'knowledge_items' and item.get('curriculum_node_id') and item.get('curriculum_domain'):
        _node_id = item['curriculum_node_id']
        _domain_id = item['curriculum_domain']
        threading.Thread(target=generate_multicue_quizzes,
                         args=(_node_id, _domain_id), daemon=True).start()

    result = {'next_due_at': next_due, 'new_stability_days': new_stability}
    if leech_suspended:
        result['leech_suspended'] = True
    return result


# ── Structural card grading ──────────────────────────────────────────────────

def record_structural_answer(card_id: str, results: list, conn) -> dict:
    """Grade an aspect card: apply FSRS to each position independently.

    Args:
        card_id: The structural_cards.id
        results: List of {position_id, score} where score is 'knew' or 'missed'
        conn: SQLite connection

    Returns dict with per-position scheduling and card-level summary.
    """
    now = int(time.time() * 1000)
    now_dt = datetime.now(timezone.utc)
    position_results = []

    for r in results:
        pos_id = r.get('position_id')
        score = r.get('score', 'missed')
        if not pos_id:
            continue

        # Binary grading: aspect cards use knew/missed only
        if score not in ('knew', 'missed'):
            score = 'missed'

        row = conn.execute(
            'SELECT fsrs_card_json, stability_days, review_count FROM structural_positions WHERE id=?',
            (pos_id,)
        ).fetchone()
        if not row:
            print(f'[structural] position {pos_id} not found, skipping', flush=True)
            continue

        # Load or create FSRS card
        card_json = row['fsrs_card_json']
        if card_json:
            card_data = json.loads(card_json) if isinstance(card_json, str) else card_json
            card = FsrsCard.from_dict(card_data)
        else:
            card = FsrsCard()

        fsrs_rating = SCORE_TO_FSRS.get(score, FsrsRating.Again)
        new_card, _ = _fsrs_scheduler.review_card(card, fsrs_rating, now_dt)
        new_stability = new_card.stability or 1.0
        next_due = int(new_card.due.timestamp() * 1000)

        conn.execute("""
            UPDATE structural_positions
            SET stability_days=?, due_at=?, last_reviewed_at=?,
                last_score=?, review_count=review_count+1, fsrs_card_json=?
            WHERE id=?
        """, (new_stability, next_due, now, score, json.dumps(new_card.to_dict()), pos_id))

        position_results.append({
            'position_id': pos_id,
            'score': score,
            'new_stability_days': round(new_stability, 1),
            'next_due_at': next_due,
        })
        print(f'[structural] {pos_id}: {score} → stability={new_stability:.1f}d due={new_card.due.strftime("%m-%d")}', flush=True)

    # ── Collateral exposure: credit anchor positions (visible but not tested) ──
    graded_ids = {r.get('position_id') for r in results if r.get('position_id')}
    anchor_rows = conn.execute(
        'SELECT id, fsrs_card_json, stability_days FROM structural_positions '
        'WHERE card_id=? AND id NOT IN ({})'.format(
            ','.join('?' for _ in graded_ids)
        ),
        (card_id, *graded_ids)
    ).fetchall() if graded_ids else []

    collateral_count = 0
    for ar in anchor_rows:
        anchor_id = ar['id']
        card_json = ar['fsrs_card_json']
        if card_json:
            card_data = json.loads(card_json) if isinstance(card_json, str) else card_json
            card = FsrsCard.from_dict(card_data)
        else:
            card = FsrsCard()

        # Apply Good rating for passive exposure
        new_card, _ = _fsrs_scheduler.review_card(card, FsrsRating.Good, now_dt)
        # Scale stability gain to ~30% of a full review
        old_stability = card.stability or 1.0
        full_gain = (new_card.stability or 1.0) - old_stability
        reduced_stability = old_stability + full_gain * 0.3
        new_card_dict = new_card.to_dict()
        new_card_dict['stability'] = reduced_stability
        next_due = int((now_dt.timestamp() + reduced_stability * 86400) * 1000)

        conn.execute("""
            UPDATE structural_positions
            SET stability_days=?, due_at=?, fsrs_card_json=?
            WHERE id=?
        """, (reduced_stability, next_due, json.dumps(new_card_dict), anchor_id))
        collateral_count += 1

    if collateral_count > 0:
        print(f'[structural] {collateral_count} anchor positions got collateral exposure credit', flush=True)
        try:
            from server_log import log_interaction
            log_interaction('collateral_exposure', card_id=card_id,
                            card_type='structural', count=collateral_count)
        except Exception:
            pass

    # Update card-level review count
    conn.execute(
        'UPDATE structural_cards SET review_count=review_count+1 WHERE id=?',
        (card_id,)
    )

    # Update knowledge state for the card's curriculum node
    card_row = conn.execute(
        'SELECT domain_id, node_id FROM structural_cards WHERE id=?', (card_id,)
    ).fetchone()
    if card_row and card_row['domain_id'] and card_row['node_id']:
        knew_count = sum(1 for r in position_results if r['score'] == 'knew')
        total = len(position_results)
        if total > 0:
            ratio = knew_count / total
            if ratio >= 0.8:
                knowledge_val, confidence_val = 'anchored', 0.85
            elif ratio >= 0.5:
                knowledge_val, confidence_val = 'engaged', 0.55
            else:
                knowledge_val, confidence_val = 'mentioned', 0.3
            update_knowledge(card_row['domain_id'], card_row['node_id'],
                             knowledge=knowledge_val, confidence=confidence_val,
                             source=f"structural:{card_id}", conn=conn)

    conn.commit()

    knew = sum(1 for r in position_results if r['score'] == 'knew')
    return {
        'card_id': card_id,
        'positions': position_results,
        'knew': knew,
        'total': len(position_results),
        'collateral_count': collateral_count,
    }


# ── Microlearning research ────────────────────────────────────────────────────

MICROLEARNING_PROMPT = """You are a knowledgeable historian and educator. Write a microlearning card for
a reader studying history and culture. This reader is especially interested in primary sources,
cultural artifacts, and material evidence — not just "what happened" but "what survives and
what was created."

Research question: {query}

Context — the learner was reviewing this curriculum concept:
{node_title}: {node_description}

{learner_context}

If learner context is provided, tailor the card's depth to what the learner already knows.
Don't explain what they've already demonstrated understanding of. Build on their
existing connections and address their expressed curiosities.

Write:
1. A SHORT TITLE (under 60 chars) that names the specific subject with dates/years when relevant.
   Good: "The Catiline Conspiracy (63 BC)" or "Al-Idrisi's World Map for Roger II (1154)"
   Bad: "Cultural Blending in Medieval Sicily" or "An Ancient Conspiracy"

2. A vivid, specific answer as an array of labeled SECTIONS (total 200-350 words). Each section
   has a "heading" (short label, null for the opening narrative) and "text" (the paragraph).
   REQUIRED sections:
   - Opening narrative (heading: null): who, what, when, why it matters. 2-3 sentences.
     Write like a storyteller, not an encyclopedia. Name people with ages or epithets, give
     one concrete physical detail, make the reader feel the moment.
   - "Sources": Name specific authors and works. If the person wrote anything, mention it.
     If no sources survive, say so — absence is historically significant. Use proper titles
     without markdown formatting.
   - "Still Visible": What can you visit or see today? Buildings, inscriptions, coins,
     manuscripts in specific museums. Be concrete about locations.
   - Optionally one more: "Surprising Detail" or "Cultural Legacy" (art, opera, literature).
     The surprising detail should be genuinely unexpected — an ironic reversal, a personal
     quirk, a telling anecdote. Not just "this was influential."

3. 3-5 quiz questions testing SPECIFIC facts from the content. Short questions (6-15 words)
   with short specific answers (1-2 sentences). Each targets a different detail.

4. 6 follow-up queries that go SIDEWAYS — exploring angles the card DIDN'T cover. Don't repeat
   what's already in the content. Think: geography as explanation, counter-narratives, structural
   causes, transmission history, modern echoes, connected figures. Each should open a new rabbit hole.

5. Entities mentioned — people, places, events, concepts with canonical IDs.

Output JSON only:
{{"title":"short title with dates","sections":[{{"heading":null,"text":"opening narrative"}},{{"heading":"Sources","text":"primary source info"}},{{"heading":"Still Visible","text":"material evidence"}}],"quizzes":[{{"question":"...","answer":"..."}}],"follow_up_queries":["q1","q2","q3","q4","q5","q6"],"entities":[{{"name":"Archimedes","canonical":"archimedes_of_syracuse","type":"person"}}]}}"""


ENTITY_RESEARCH_PROMPT = """You are a knowledgeable historian. Write a rich microlearning card about this entity,
making connections to the learner's known context. Include primary sources and material evidence.

Entity: {entity_name} ({entity_type})
{entity_description}

Related entities from the same period or region that the learner has encountered:
{related_entities}

{learner_context}

If learner context is provided, weave in what the learner already knows about this
entity. Acknowledge their existing connections and build on them rather than repeating
basics they've already demonstrated.

Write:
1. A SHORT TITLE (under 60 chars) with dates when relevant.
   Good: "George of Antioch, Roger II's Admiral (d. 1151)" or "The Motya Charioteer (5th c. BC)"
   Bad: "An Important Historical Figure"

2. A vivid profile (3-5 SHORT paragraphs, 200-350 words) that:
   - Covers who/what this is and why it matters
   - Makes SPECIFIC connections to the related entities listed above
   - Names PRIMARY SOURCES: who wrote about this entity? What survives?
   - Names MATERIAL EVIDENCE: buildings, artifacts, inscriptions, museum objects
   - Includes one surprising or lesser-known detail

3. 3-5 quiz questions testing SPECIFIC facts. Short questions (6-15 words), short answers.

4. 6 follow-up queries latching onto specific details from the card content

5. Entities mentioned in the text

Output JSON only:
{{"title":"short title with dates","content":"the profile text","quizzes":[{{"question":"...","answer":"..."}}],"follow_up_queries":["q1","q2","q3","q4","q5","q6"],"entities":[{{"name":"Name","canonical":"canonical_id","type":"person|place|event|concept|period"}}]}}"""


ENTITY_QUESTIONS_PROMPT = """Generate 3 research questions about this entity that would make a history reader
genuinely curious — the kind that make you go "wait, really?" or "I never thought about it that way."

Entity: {entity_name} ({entity_type})
{entity_description}

Related entities from the same period or region:
{related_entities}

Requirements:
- Be SPECIFIC — name real people, places, events, dates
- At least one question should connect this entity to a related entity listed above
- Vary the angle: one factual/what-happened, one comparative/connection, one surprising/counter-intuitive
- NO generic templates like "How does X connect to Y?"

Output JSON array of 3 strings only: ["q1","q2","q3"]"""


def _find_related_entities(entity_id: str, entity_name: str, entity_type: str,
                           conn) -> list[dict]:
    """Find entities related by time period or location."""
    related = []

    # Get the target entity's details if in shared_entities
    target = conn.execute(
        'SELECT * FROM shared_entities WHERE entity_id = ?', (entity_id,)
    ).fetchone()

    if target:
        target = dict(target)
        date_start = target.get('date_start')
        date_end = target.get('date_end')
        lat = target.get('latitude')
        lon = target.get('longitude')

        # Find temporally overlapping entities (within 100 years)
        if date_start is not None:
            time_related = conn.execute('''
                SELECT entity_id, name, entity_type, date_start, date_end, description
                FROM shared_entities
                WHERE entity_id != ? AND date_start IS NOT NULL
                  AND ABS(date_start - ?) < 100
                ORDER BY ABS(date_start - ?) ASC
                LIMIT 5
            ''', (entity_id, date_start, date_start)).fetchall()
            for r in time_related:
                related.append({
                    'name': r['name'], 'type': r['entity_type'],
                    'relation': 'same period',
                    'detail': f"({r['date_start']} to {r['date_end'] or '?'})" if r['date_start'] else '',
                })

        # Find spatially nearby entities (within ~2 degrees ≈ 200km)
        if lat is not None and lon is not None:
            space_related = conn.execute('''
                SELECT entity_id, name, entity_type, description
                FROM shared_entities
                WHERE entity_id != ? AND latitude IS NOT NULL
                  AND ABS(latitude - ?) < 2.0 AND ABS(longitude - ?) < 2.0
                LIMIT 5
            ''', (entity_id, lat, lon)).fetchall()
            seen = {r['name'] for r in related}
            for r in space_related:
                if r['name'] not in seen:
                    related.append({
                        'name': r['name'], 'type': r['entity_type'],
                        'relation': 'same region',
                    })

    # Also search microlearning cards for co-occurring entities
    try:
        ml_rows = conn.execute(
            "SELECT entities FROM microlearning_cards WHERE status='completed' AND entities LIKE ?",
            (f'%{entity_id}%',)
        ).fetchall()
        co_entities = {}
        eid_lower = entity_id.lower()
        for row in ml_rows:
            ents = json.loads(row['entities'] or '[]')
            for e in ents:
                cid = e.get('canonical', '')
                if cid and cid.lower() != eid_lower and cid not in co_entities:
                    co_entities[cid] = {'name': e['name'], 'type': e.get('type', 'concept'),
                                        'relation': 'co-mentioned in research'}
        seen = {r['name'] for r in related}
        for cid, info in list(co_entities.items())[:5]:
            if info['name'] not in seen:
                related.append(info)
    except Exception:
        pass

    return related[:8]


def _strip_markdown(text: str) -> tuple[str, list[tuple[int, int, int, int]]]:
    """Strip *italic* and **bold** markers from text.
    Returns (clean_text, offset_map) where offset_map maps clean positions to original positions."""
    import re
    # Track removals to build an offset map
    result = []
    i = 0
    while i < len(text):
        if text[i:i+2] == '**':
            # Find closing **
            end = text.find('**', i + 2)
            if end != -1:
                result.append(text[i+2:end])
                i = end + 2
                continue
        if text[i] == '*' and (i == 0 or text[i-1] != '*') and (i + 1 < len(text) and text[i+1] != '*'):
            # Find closing *
            end = text.find('*', i + 1)
            if end != -1 and text[end-1:end+1] != '**':
                result.append(text[i+1:end])
                i = end + 1
                continue
        result.append(text[i])
        i += 1
    return ''.join(result), []


def _compute_entity_spans(text: str, entities: list) -> list:
    """Find entity mentions in text and return span objects for the client."""
    spans = []
    for ent in entities:
        name = ent.get('name', '')
        if not name or len(name) < 2:
            continue
        start = 0
        while True:
            idx = text.find(name, start)
            if idx == -1:
                break
            spans.append({
                'start': idx,
                'end': idx + len(name),
                'entity_id': ent.get('canonical', name.lower().replace(' ', '_')),
                'name': name,
                'entity_type': ent.get('type', 'concept'),
            })
            start = idx + len(name)
    # Sort by position, deduplicate overlapping spans
    spans.sort(key=lambda s: s['start'])
    filtered = []
    last_end = 0
    for s in spans:
        if s['start'] >= last_end:
            filtered.append(s)
            last_end = s['end']
    return filtered


def generate_entity_questions(entity_id: str, entity_name: str,
                              entity_type: str = 'concept',
                              description: str = '') -> list[str]:
    """Generate 3 research questions about an entity, informed by related entities."""
    from db import get_connection
    conn = get_connection(readonly=True)
    related = _find_related_entities(entity_id, entity_name, entity_type, conn)
    conn.close()

    related_text = '\n'.join(
        f'- {r["name"]} ({r["type"]}, {r["relation"]})'
        + (f' {r.get("detail", "")}' if r.get('detail') else '')
        for r in related
    ) if related else '(none found — focus on the entity itself)'

    prompt = ENTITY_QUESTIONS_PROMPT.format(
        entity_name=entity_name,
        entity_type=entity_type,
        entity_description=description or '(no description available)',
        related_entities=related_text,
    )
    result = call_claude_json(prompt, timeout=60, model='sonnet')
    if isinstance(result, list) and len(result) >= 2:
        return result[:3]
    return [f'What was the historical significance of {entity_name}?']


def _find_duplicate_quiz(question: str, existing: list[tuple[str, 'numpy.ndarray']],
                         model, threshold: float = 0.82) -> str | None:
    """Check if a question is semantically duplicate of an existing one.

    Uses MiniLM embeddings via limbic.amygdala with the calibrated 0.82 cosine
    threshold (same as KNOWN for claim similarity).
    Returns the matching question text if duplicate, None otherwise.
    """
    import numpy as np
    if not existing:
        return None
    new_vec = model.embed(question)
    new_norm = np.linalg.norm(new_vec)
    if new_norm < 1e-9:
        return None
    best_score, best_text = 0.0, None
    for ex_text, ex_vec in existing:
        ex_norm = np.linalg.norm(ex_vec)
        if ex_norm < 1e-9:
            continue
        cos = float(np.dot(new_vec, ex_vec) / (new_norm * ex_norm))
        if cos > best_score:
            best_score, best_text = cos, ex_text
    # Log top match for calibration review
    if best_text:
        print(f'[quiz-dedup] best match ({best_score:.3f}): '
              f'"{question[:50]}" ~ "{best_text[:50]}"'
              f'{" → DUPLICATE" if best_score >= threshold else ""}', flush=True)
    if best_score >= threshold:
        return best_text
    return None


def _store_quizzes(card_id: str, quizzes: list, conn) -> int:
    """Store quiz questions, skipping semantic duplicates via limbic embeddings."""
    now_ms = int(time.time() * 1000)

    # Load embedding model for dedup
    model = None
    existing_embedded: list[tuple[str, any]] = []
    try:
        from limbic.amygdala import EmbeddingModel
        model = EmbeddingModel()

        # Collect and embed existing questions
        existing_texts = []
        for row in conn.execute(
            "SELECT question FROM microlearning_quizzes WHERE status='active'"
        ).fetchall():
            existing_texts.append(row['question'])
        try:
            for row in conn.execute(
                "SELECT key_facts FROM curriculum_nodes "
                "WHERE key_facts IS NOT NULL AND key_facts != '[]'"
            ).fetchall():
                facts = json.loads(row['key_facts'] or '[]')
                for f in facts:
                    if f.get('question'):
                        existing_texts.append(f['question'])
        except Exception:
            pass

        if existing_texts:
            vecs = model.embed_batch(existing_texts)
            existing_embedded = list(zip(existing_texts, vecs))
    except Exception as e:
        print(f'[quiz-dedup] embedding init failed, skipping dedup: {e}', flush=True)

    stored = 0
    skipped = 0
    for i, q in enumerate(quizzes):
        question = q.get('question', '').strip()
        answer = q.get('answer', '').strip()
        if not question:
            continue

        # Check for semantic duplicates
        if model and existing_embedded:
            dup = _find_duplicate_quiz(question, existing_embedded, model)
            if dup:
                print(f'[quiz-dedup] skipping: "{question[:50]}" ~ "{dup[:50]}"', flush=True)
                skipped += 1
                continue

        quiz_id = f'{card_id}_q{i}'
        conn.execute('''
            INSERT OR IGNORE INTO microlearning_quizzes
            (id, card_id, question, answer, status, stability_days, due_at,
             review_count, created_at)
            VALUES (?, ?, ?, ?, 'active', 1.0, ?, 0, ?)
        ''', (quiz_id, card_id, question, answer, now_ms, now_ms))
        # Add to existing pool so intra-batch dupes are caught too
        if model:
            existing_embedded.append((question, model.embed(question)))
        stored += 1

    if skipped:
        print(f'[quiz-dedup] {stored} stored, {skipped} skipped for {card_id}', flush=True)

    # Backfill legacy fields with first stored quiz
    if quizzes:
        first = quizzes[0]
        conn.execute(
            'UPDATE microlearning_cards SET question=?, answer_guidance=? WHERE id=?',
            (first.get('question', ''), first.get('answer', ''), card_id))

    return stored


def create_entity_research(entity_id: str, entity_name: str,
                           entity_type: str = 'concept',
                           description: str = '') -> str:
    """Create a microlearning card about an entity with related-entity context.

    Returns the card ID. Research runs in background.
    """
    from db import get_connection
    query = f'Profile: {entity_name} — who/what, why it matters, connections'
    card_id = f'ml_{int(time.time())}_{hash(entity_id) % 10000:04d}'
    now_ms = int(time.time() * 1000)

    conn = get_connection()
    conn.execute('''
        INSERT OR IGNORE INTO microlearning_cards
        (id, query, source_item_id, source_node_id, source_domain,
         content, status, created_at)
        VALUES (?, ?, ?, ?, ?, '', 'pending', ?)
    ''', (card_id, query, f'entity:{entity_id}', None, None, now_ms))
    conn.commit()
    conn.close()

    threading.Thread(
        target=_run_entity_research,
        args=(card_id, entity_id, entity_name, entity_type, description),
        daemon=True,
    ).start()
    return card_id


def _run_entity_research(card_id: str, entity_id: str, entity_name: str,
                          entity_type: str, description: str):
    """Background: generate a rich entity profile with related-entity connections."""
    from db import get_connection
    try:
        conn = get_connection(readonly=True)
        related = _find_related_entities(entity_id, entity_name, entity_type, conn)
        learner_ctx = get_learner_context_for_entity(entity_name, conn)
        conn.close()

        related_text = '\n'.join(
            f'- {r["name"]} ({r["type"]}, {r["relation"]})'
            + (f' {r.get("detail", "")}' if r.get('detail') else '')
            for r in related
        ) if related else '(none known — focus on the entity itself)'

        # Web search for factual accuracy
        search_result = None
        try:
            search_prompt = f'Research: {entity_name} historical significance and connections'
            search_result = call_claude_search(search_prompt, timeout=120)
        except Exception as e:
            print(f'[entity-research] search failed for {card_id}: {e}', flush=True)

        prompt = ENTITY_RESEARCH_PROMPT.format(
            entity_name=entity_name,
            entity_type=entity_type,
            entity_description=description or '(no description available)',
            related_entities=related_text,
            learner_context=learner_ctx,
        )
        if search_result:
            prompt += f'\n\nSearch results to incorporate:\n{search_result[:2000]}'

        result = call_claude_json(prompt, timeout=120)
        if not result or 'content' not in result:
            raise ValueError(f'Invalid response: {str(result)[:200]}')

        entities = result.get('entities', [])
        quizzes = result.get('quizzes', [])
        if not quizzes and result.get('question'):
            quizzes = [{'question': result['question'],
                        'answer': result.get('answer_guidance', '')}]

        now_ms = int(time.time() * 1000)
        conn = get_connection()
        conn.execute('''
            UPDATE microlearning_cards SET
                title=?, content=?, follow_up_queries=?, entities=?,
                status='completed', due_at=?
            WHERE id=?
        ''', (
            result.get('title', entity_name),
            result['content'],
            json.dumps(result.get('follow_up_queries', [])),
            json.dumps(entities),
            now_ms,
            card_id,
        ))
        quiz_count = _store_quizzes(card_id, quizzes, conn)
        conn.commit()
        conn.close()
        print(f'[entity-research] completed {card_id}: {entity_name} '
              f'({quiz_count} quizzes, {len(entities)} entities, {len(related)} related)', flush=True)

    except Exception as e:
        print(f'[entity-research] failed {card_id}: {e}', flush=True)
        import traceback; traceback.print_exc()
        try:
            conn = get_connection()
            conn.execute("UPDATE microlearning_cards SET status='failed' WHERE id=?",
                         (card_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass


def generate_also_want_to_know(item_id: str, question_text: str,
                               entities: list) -> list:
    """Generate tappable 'I also want to know...' suggestions after a review answer.

    Uses entity metadata, key_facts, and node dates to produce 2-4 quick suggestions.
    Each suggestion has: query, type ('simple_fact' or 'research'), label.
    """
    from db import get_connection
    suggestions = []
    conn = get_connection()

    try:
        # Get curriculum node context
        ki = conn.execute(
            'SELECT curriculum_node_id, curriculum_domain FROM knowledge_items WHERE id=?',
            (item_id,)).fetchone()
        if not ki:
            return suggestions
        node_id, domain_id = ki[0], ki[1]

        node = conn.execute(
            'SELECT title, date_start, date_end, key_facts FROM curriculum_nodes '
            'WHERE id=? AND domain_id=?', (node_id, domain_id)).fetchone()
        if not node:
            return suggestions

        node_title = node[0] or ''
        date_start = node[1]
        date_end = node[2]
        key_facts = json.loads(node[3]) if node[3] else []

        # Get already-asked fact_ids from question_history
        ki_full = conn.execute('SELECT question_history FROM knowledge_items WHERE id=?',
                               (item_id,)).fetchone()
        asked_fact_ids = set()
        if ki_full and ki_full[0]:
            try:
                for qh in json.loads(ki_full[0]):
                    if qh.get('fact_id'):
                        asked_fact_ids.add(qh['fact_id'])
            except (json.JSONDecodeError, TypeError):
                pass

        # Entity-based suggestions
        for ent in (entities or []):
            name = ent.get('name', '')
            etype = ent.get('type', ent.get('entity_type', ''))
            if not name:
                continue
            if etype == 'person':
                suggestions.append({
                    'query': f'When did {name} live?',
                    'type': 'simple_fact',
                    'label': f'{name} \u2014 dates',
                })
                if len(suggestions) < 4:
                    suggestions.append({
                        'query': f'Where was {name} primarily based?',
                        'type': 'simple_fact',
                        'label': f'{name} \u2014 location',
                    })
            elif etype == 'place':
                suggestions.append({
                    'query': f'What is the historical significance of {name}?',
                    'type': 'research',
                    'label': f'{name} \u2014 significance',
                })
            elif etype in ('event', 'battle', 'treaty'):
                suggestions.append({
                    'query': f'What were the consequences of {name}?',
                    'type': 'research',
                    'label': f'{name} \u2014 consequences',
                })
            if len(suggestions) >= 4:
                break

        # Key_facts-based suggestions (facts not yet quizzed)
        for fact in key_facts:
            fact_id = fact.get('id', '')
            if fact_id in asked_fact_ids:
                continue
            ft = fact.get('type', '')
            fname = fact.get('name', fact.get('value', ''))
            if ft == 'date' and fname:
                suggestions.append({
                    'query': f'When: {fname}',
                    'type': 'simple_fact',
                    'label': f'Date: {fname}',
                })
            elif ft == 'person' and fname:
                suggestions.append({
                    'query': f'Who was {fname}?',
                    'type': 'simple_fact',
                    'label': f'Person: {fname}',
                })
            elif ft == 'place' and fname:
                suggestions.append({
                    'query': f'Where is {fname}?',
                    'type': 'simple_fact',
                    'label': f'Place: {fname}',
                })
            elif fname:
                suggestions.append({
                    'query': f'What was {fname}?',
                    'type': 'simple_fact',
                    'label': fname,
                })
            if len(suggestions) >= 6:
                break

        # Date-based cross-temporal suggestion
        if date_start and len(suggestions) < 6:
            year_str = f'{abs(int(date_start))} {"BC" if date_start < 0 else "AD"}'
            suggestions.append({
                'query': f'What else was happening around {year_str}?',
                'type': 'research',
                'label': f'Around {year_str}',
            })

    except Exception as e:
        print(f'[also-want-to-know] Error: {e}', flush=True)
    finally:
        conn.close()

    # Deduplicate by query
    seen = set()
    unique = []
    for s in suggestions:
        if s['query'] not in seen:
            seen.add(s['query'])
            unique.append(s)
    return unique[:6]


def create_targeted_quiz(item_id: str, query: str) -> dict:
    """Create a simple quiz card for a specific fact gap (not a full ML research card).

    For quick factual questions like 'When was Cicero assassinated?'
    Returns the created quiz info.
    """
    from db import get_connection
    conn = get_connection()

    try:
        # Get node context for the LLM
        ki = conn.execute(
            'SELECT curriculum_node_id, curriculum_domain FROM knowledge_items WHERE id=?',
            (item_id,)).fetchone()
        if not ki:
            return {'error': 'item not found'}

        node_id, domain_id = ki[0], ki[1]
        node = conn.execute(
            'SELECT title, description FROM curriculum_nodes WHERE id=? AND domain_id=?',
            (node_id, domain_id)).fetchone()
        node_title = node[0] if node else ''
        node_desc = (node[1] or '')[:300] if node else ''

        # Quick LLM call to generate Q+A for this specific fact
        # Uses Gemini directly for interactive latency (~1-3s)
        prompt = f"""Generate a single quiz question and answer for this specific knowledge gap.

Topic: {node_title}
Context: {node_desc}
User wants to know: {query}

Return JSON: {{"question": "...", "answer": "..."}}
The question should be direct and factual. The answer should be 1-2 sentences."""

        from gemini_llm import call_llm
        raw = call_llm(prompt, response_mime_type='application/json')
        result = json.loads(raw) if isinstance(raw, str) else raw

        question = result.get('question', query)
        answer = result.get('answer', '')

        # Store as a microlearning quiz linked to a lightweight ML card
        card_id = f'ml_{int(time.time())}_{hash(query) % 10000:04d}'
        quiz_id = f'mq_{int(time.time())}_{hash(question) % 10000:04d}'
        now_ms = int(time.time() * 1000)

        conn.execute('''
            INSERT OR IGNORE INTO microlearning_cards
            (id, query, source_item_id, source_node_id, source_domain,
             content, status, created_at, source_type, generation_depth, title)
            VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, 'user_request', 0, ?)
        ''', (card_id, query, item_id, node_id, domain_id,
              answer, now_ms, node_title))

        conn.execute('''
            INSERT OR IGNORE INTO microlearning_quizzes
            (id, card_id, question, answer, status, stability_days, due_at, review_count, created_at)
            VALUES (?, ?, ?, ?, 'active', 1.0, ?, 0, ?)
        ''', (quiz_id, card_id, question, answer, now_ms, now_ms))

        conn.commit()
        return {'card_id': card_id, 'quiz_id': quiz_id, 'question': question, 'answer': answer}
    except Exception as e:
        print(f'[targeted-quiz] Error: {e}', flush=True)
        return {'error': str(e)}
    finally:
        conn.close()


def create_microlearning_request(query: str, source_item_id: str | None = None,
                                  source_node_id: str | None = None,
                                  source_domain: str | None = None,
                                  source_type: str = 'follow_up',
                                  generation_depth: int = 0) -> str:
    """Create a pending microlearning card and return its ID.

    source_type: 'voice_wondering', 'follow_up', 'entity_research', 'user_request', 'correction'
    generation_depth: 0 = root, 1+ = child of another ML card

    The actual research runs in a background thread.
    """
    from db import get_connection
    card_id = f'ml_{int(time.time())}_{hash(query) % 10000:04d}'
    now_ms = int(time.time() * 1000)

    conn = get_connection()
    conn.execute('''
        INSERT OR IGNORE INTO microlearning_cards
        (id, query, source_item_id, source_node_id, source_domain,
         content, status, created_at, source_type, generation_depth)
        VALUES (?, ?, ?, ?, ?, '', 'pending', ?, ?, ?)
    ''', (card_id, query, source_item_id, source_node_id, source_domain,
          now_ms, source_type, generation_depth))
    conn.commit()
    conn.close()

    # Run research in background
    threading.Thread(
        target=_run_microlearning_research,
        args=(card_id, query, source_node_id, source_domain),
        daemon=True
    ).start()

    return card_id


def _run_microlearning_research(card_id: str, query: str,
                                 node_id: str | None, domain_id: str | None):
    """Background: run search + LLM, fill in the microlearning card."""
    from db import get_connection
    try:
        # Load node context and learner context if available
        node_title = ''
        node_description = ''
        learner_ctx = ''
        if node_id and domain_id:
            conn = get_connection(readonly=True)
            row = conn.execute(
                'SELECT title, description FROM curriculum_nodes WHERE id=? AND domain_id=?',
                (node_id, domain_id)
            ).fetchone()
            if row:
                node_title = row['title']
                node_description = row['description'] or ''
            learner_ctx = get_learner_context(node_id, domain_id, conn)
            conn.close()

        # Search for factual accuracy via Claude with web search
        search_result = None
        try:
            from claude_llm import call_claude_search
            search_prompt = f"Research this question thoroughly: {query}"
            if node_title:
                search_prompt += f"\nContext: this relates to {node_title}"
            search_result = call_claude_search(search_prompt, timeout=120)
        except Exception as e:
            print(f'[microlearning] search failed for {card_id}: {e}', flush=True)

        # Generate structured microlearning card via Claude
        prompt = MICROLEARNING_PROMPT.format(
            query=query,
            node_title=node_title or 'General history',
            node_description=node_description or '(no curriculum context)',
            learner_context=learner_ctx,
        )
        if search_result:
            prompt += f"\n\nSearch results to incorporate:\n{search_result[:2000]}"

        result = call_claude_json(prompt, timeout=120)

        if not result or ('content' not in result and 'sections' not in result):
            raise ValueError(f'Invalid response: {str(result)[:200] if result else "empty"}')

        # Handle sections format → join into flat content for entity spans
        sections = result.get('sections', [])
        if sections and isinstance(sections, list):
            # Join section texts into flat content
            result['content'] = '\n\n'.join(s.get('text', '') for s in sections)
        elif not result.get('content'):
            result['content'] = ''

        # Strip markdown for entity span computation
        raw_content = result['content']
        clean_content, _ = _strip_markdown(raw_content)
        entities = result.get('entities', [])
        entity_spans = _compute_entity_spans(clean_content, entities)
        spans_json = json.dumps({'content': [
            {'start': s['start'], 'end': s['end'], 'entity_id': s['entity_id'],
             'name': s['name'], 'entity_type': s['entity_type']}
            for s in entity_spans
        ]}) if entity_spans else '{}'

        # Update the card — store clean content (for spans) in content field
        now_ms = int(time.time() * 1000)
        quizzes = result.get('quizzes', [])
        # Backwards compat: if model returned old single-question format
        if not quizzes and result.get('question'):
            quizzes = [{'question': result['question'],
                        'answer': result.get('answer_guidance', '')}]

        conn = get_connection()
        conn.execute('''
            UPDATE microlearning_cards SET
                title=?, content=?, sections=?, follow_up_queries=?, entities=?, entity_spans=?,
                status='completed', due_at=?
            WHERE id=?
        ''', (
            result.get('title', query[:60]),
            clean_content,
            json.dumps(sections) if sections else '[]',
            json.dumps(result.get('follow_up_queries', [])),
            json.dumps(entities),
            spans_json,
            now_ms,
            card_id,
        ))
        quiz_count = _store_quizzes(card_id, quizzes, conn)
        conn.commit()
        conn.close()
        print(f'[microlearning] completed {card_id}: {query[:60]} '
              f'({quiz_count} quizzes, {len(entities)} entities)', flush=True)

    except Exception as e:
        print(f'[microlearning] failed {card_id}: {e}', flush=True)
        import traceback; traceback.print_exc()
        try:
            conn = get_connection()
            conn.execute(
                "UPDATE microlearning_cards SET status='failed' WHERE id=?",
                (card_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass


# ── Stats ──────────────────────────────────────────────────────────────────────

def get_review_stats(conn) -> dict:
    now = int(time.time() * 1000)
    end_today = now + 24 * 60 * 60 * 1000
    end_week = now + 7 * 24 * 60 * 60 * 1000

    # Core nodes from knowledge_items
    ki_due_today = conn.execute(
        'SELECT COUNT(*) FROM knowledge_items WHERE due_at <= ?', (end_today,)
    ).fetchone()[0]
    ki_due_week = conn.execute(
        'SELECT COUNT(*) FROM knowledge_items WHERE due_at <= ?', (end_week,)
    ).fetchone()[0]
    ki_total = conn.execute('SELECT COUNT(*) FROM knowledge_items').fetchone()[0]

    # Exploration / voice items from review_items
    ri_due_today = conn.execute(
        "SELECT COUNT(*) FROM review_items WHERE due_at <= ? AND item_type != 'book_chapter'", (end_today,)
    ).fetchone()[0]
    ri_due_week = conn.execute(
        "SELECT COUNT(*) FROM review_items WHERE due_at <= ? AND item_type != 'book_chapter'", (end_week,)
    ).fetchone()[0]
    ri_total = conn.execute(
        "SELECT COUNT(*) FROM review_items WHERE item_type != 'book_chapter'"
    ).fetchone()[0]

    # Per-book breakdown: iterate knowledge_items sources arrays
    by_book: dict = {}
    ki_rows = conn.execute(
        'SELECT sources FROM knowledge_items WHERE due_at <= ?', (end_today,)
    ).fetchall()
    for r in ki_rows:
        try:
            sources = json.loads(r['sources'] or '[]')
            book_sources = [s for s in sources if s.get('book_id')]
            if book_sources:
                bid = book_sources[-1]['book_id']
                by_book[bid] = by_book.get(bid, 0) + 1
        except Exception:
            pass

    return {
        'due_today': ki_due_today + ri_due_today,
        'due_this_week': ki_due_week + ri_due_week,
        'total': ki_total + ri_total,
        'knowledge_items_total': ki_total,
        'by_source': by_book,
    }


# ── Exploration items ──────────────────────────────────────────────────────────

def _load_item_for_child(item_id: str, conn) -> dict | None:
    """Load parent item from knowledge_items or review_items, normalising field names."""
    row = conn.execute('SELECT * FROM knowledge_items WHERE id=?', (item_id,)).fetchone()
    if row:
        item = dict(row)
        # Derive flat fields from sources array for use in child items
        try:
            sources = json.loads(item.get('sources') or '[]')
            best = _best_source_for_question(sources)
        except Exception:
            best = {}
        item['source_book_id'] = best.get('book_id')
        item['source_chapter_number'] = best.get('chapter_number')
        item['source_chapter_title'] = best.get('chapter_title', '')
        item['source_text'] = best.get('source_text', '')
        # Resolve curriculum_node_title from curriculum
        domain = item.get('curriculum_domain', '')
        curriculum = load_curriculum(domain)
        node_id = item.get('curriculum_node_id', '')
        if curriculum:
            node = next((n for n in curriculum.get('nodes', []) if n['id'] == node_id), None)
            item['curriculum_node_title'] = node['title'] if node else node_id
        else:
            item['curriculum_node_title'] = node_id
        return item

    row = conn.execute('SELECT * FROM review_items WHERE id=?', (item_id,)).fetchone()
    return dict(row) if row else None


def create_exploration_items(item_id: str, conn) -> list:
    item = _load_item_for_child(item_id, conn)
    if not item:
        return []

    # Don't create duplicates if unexpired exploration items already exist for this parent
    now = int(time.time() * 1000)
    existing = conn.execute(
        "SELECT count(*) FROM review_items WHERE parent_item_id=? AND item_type='exploration' AND due_at > ?",
        (item_id, now - 7 * 24 * 60 * 60 * 1000)  # within last week
    ).fetchone()[0]
    if existing > 0:
        return []

    prompt = EXPLORE_PROMPT.format(
        node_title=item.get('curriculum_node_title', ''),
        source_text=item.get('source_text', '')[:400],
        score=item.get('last_score', 'partly'),
    )

    questions = call_claude_json(prompt, timeout=120)
    if not isinstance(questions, list):
        return []

    tomorrow = now + 24 * 60 * 60 * 1000
    created = []

    for i, q in enumerate(questions[:3]):
        child_id = f'{item_id}_explore_{i}_{now}'
        conn.execute("""
            INSERT INTO review_items
              (id, item_type, curriculum_domain, curriculum_node_id, curriculum_node_title,
               source_book_id, source_chapter_number, source_chapter_title,
               source_text, lens, parent_item_id, stability_days, due_at, review_count, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            child_id, 'exploration',
            item.get('curriculum_domain'), item.get('curriculum_node_id'), item.get('curriculum_node_title'),
            item.get('source_book_id'), item.get('source_chapter_number'), item.get('source_chapter_title'),
            q.get('question', ''), q.get('lens', 'SIGNIFICANCE'),
            item_id, 1.0, tomorrow, 0, now,
        ))
        created.append({'id': child_id, 'question': q.get('question', ''), 'lens': q.get('lens', ''),
                        'suggested_source': q.get('suggested_source', '')})

    conn.commit()
    return created


# ── Entity exploration ────────────────────────────────────────────────────────

ENTITY_EXPLORE_PROMPTS = {
    'place': """A learner tapped "Tell me more" on this place during a knowledge review session.

Entity: {name}
Description: {description}
Type: Place

Generate 3 research questions to deepen understanding of this place. Vary lenses:
1. Geographic/founding: Why was it located here? What strategic or economic factors?
2. Comparative: How does it compare to other places in the region or period?
3. Legacy: What remains today? What's its modern significance?

Output JSON only:
[{{"question":"...","lens":"...","suggested_source":"brief hint where to find the answer"}}]""",

    'person': """A learner tapped "Tell me more" on this person during a knowledge review session.

Entity: {name}
Description: {description}
Type: Person

Generate 3 research questions to deepen understanding of this person. Vary lenses:
1. Formative: What shaped their worldview or actions?
2. Impact: How did they change the course of events?
3. Legacy: How are they remembered? What's their modern significance?

Output JSON only:
[{{"question":"...","lens":"...","suggested_source":"brief hint where to find the answer"}}]""",

    'event': """A learner tapped "Tell me more" on this event during a knowledge review session.

Entity: {name}
Description: {description}
Type: Event

Generate 3 research questions to deepen understanding of this event. Vary lenses:
1. Causal: What chain of events led to this?
2. Consequences: What were the long-term effects?
3. Parallels: What similar events happened elsewhere or in other periods?

Output JSON only:
[{{"question":"...","lens":"...","suggested_source":"brief hint where to find the answer"}}]""",

    'default': """A learner tapped "Tell me more" on this entity during a knowledge review session.

Entity: {name}
Description: {description}

Generate 3 research questions to deepen understanding. Vary lenses:
1. Causal depth (why/how)
2. Comparative (relation to other periods/places/concepts)
3. Significance (consequences or modern relevance)

Output JSON only:
[{{"question":"...","lens":"...","suggested_source":"brief hint where to find the answer"}}]""",
}


def create_entity_exploration_items(entity: dict, domain_id: str, node_id: str, conn) -> list:
    """Generate 3 AI exploration prompts scoped to an entity and queue as review items."""
    entity_id = entity['entity_id']
    entity_type = entity.get('entity_type', '')
    now = int(time.time() * 1000)

    # Don't create duplicates — check for recent entity exploration items
    existing = conn.execute(
        """SELECT count(*) FROM review_items
           WHERE parent_item_id = ? AND item_type = 'exploration' AND due_at > ?""",
        (f'entity:{entity_id}', now - 7 * 24 * 60 * 60 * 1000)
    ).fetchone()[0]
    if existing > 0:
        return []

    prompt_template = ENTITY_EXPLORE_PROMPTS.get(entity_type, ENTITY_EXPLORE_PROMPTS['default'])
    prompt = prompt_template.format(
        name=entity.get('name', ''),
        description=entity.get('description', '')[:400],
    )

    questions = call_claude_json(prompt, timeout=120)
    if not isinstance(questions, list):
        return []

    # Look up node title for the review items
    node = conn.execute(
        'SELECT title FROM curriculum_nodes WHERE id = ? AND domain_id = ?',
        (node_id, domain_id)
    ).fetchone()
    node_title = node['title'] if node else entity.get('name', '')

    tomorrow = now + 24 * 60 * 60 * 1000
    created = []

    for i, q in enumerate(questions[:3]):
        child_id = f'entity:{entity_id}_explore_{i}_{now}'
        conn.execute("""
            INSERT INTO review_items
              (id, item_type, curriculum_domain, curriculum_node_id, curriculum_node_title,
               source_book_id, source_chapter_number, source_chapter_title,
               source_text, lens, parent_item_id, stability_days, due_at, review_count, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            child_id, 'exploration',
            domain_id, node_id, f'{node_title} — {entity.get("name", "")}',
            None, None, f'Entity exploration: {entity.get("name", "")}',
            q.get('question', ''), q.get('lens', 'SIGNIFICANCE'),
            f'entity:{entity_id}', 1.0, tomorrow, 0, now,
        ))
        created.append({
            'id': child_id,
            'question': q.get('question', ''),
            'lens': q.get('lens', ''),
            'suggested_source': q.get('suggested_source', ''),
        })

    conn.commit()
    return created


# ── Voice memo ────────────────────────────────────────────────────────────────

def process_voice_memo(item_id: str, audio_path: Path, conn, transcribe_fn) -> dict:
    """transcribe_fn: callable(Path) -> str  (e.g. transcribe_on_server)"""
    item = _load_item_for_child(item_id, conn)
    if not item:
        return {}

    transcript = transcribe_fn(audio_path)
    if not transcript:
        return {'error': 'Transcription failed'}

    prompt = VOICE_EXTRACT_PROMPT.format(
        node_title=item.get('curriculum_node_title', ''),
        transcript=transcript,
    )

    extracted = call_claude_json(prompt, timeout=120)
    if not isinstance(extracted, dict):
        extracted = {}

    score = extracted.get('suggested_score', 'partly')
    now = int(time.time() * 1000)
    soon = now + 2 * 60 * 60 * 1000  # 2h: high priority
    follow_ups = []

    for i, question in enumerate(extracted.get('questions', [])[:3]):
        child_id = f'{item_id}_voice_{i}_{now}'
        conn.execute("""
            INSERT INTO review_items
              (id, item_type, curriculum_domain, curriculum_node_id, curriculum_node_title,
               source_book_id, source_chapter_number, source_chapter_title,
               source_text, lens, parent_item_id, stability_days, due_at, review_count, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            child_id, 'voice_followup',
            item.get('curriculum_domain'), item.get('curriculum_node_id'), item.get('curriculum_node_title'),
            item.get('source_book_id'), item.get('source_chapter_number'), item.get('source_chapter_title'),
            question, 'SIGNIFICANCE', item_id, 1.0, soon, 0, now,
        ))
        follow_ups.append({'id': child_id, 'question': question})

    conn.commit()

    # Trigger microlearning for research-worthy questions
    ml_triggered = []
    for question in extracted.get('questions', [])[:2]:
        try:
            card_id = create_microlearning_request(
                query=question,
                source_item_id=item_id,
                source_node_id=item.get('curriculum_node_id'),
                source_domain=item.get('curriculum_domain'),
                source_type='voice_wondering',
            )
            ml_triggered.append({'id': card_id, 'query': question})
            print(f'[voice→ml] memo question → {card_id}: {question[:60]}', flush=True)
        except Exception as e:
            print(f'[voice→ml] memo trigger failed: {e}', flush=True)

    result = {
        'transcript': transcript,
        'remembered': extracted.get('remembered', ''),
        'suggested_score': score,
        'connections': extracted.get('connections', []),
        'follow_ups_created': follow_ups,
        'microlearning_triggered': ml_triggered,
    }

    _log_voice_transcript(
        source='review_memo', node_id=item.get('curriculum_node_id', ''),
        domain_id=item.get('curriculum_domain', ''),
        node_title=item.get('curriculum_node_title', ''),
        transcript=transcript,
        audio_bytes=audio_path.stat().st_size if audio_path.exists() else 0,
        llm_result=extracted, ml_triggered=ml_triggered,
    )

    return result


# ── Knowledge profile: transcript chunking & learner context ──────────────

def _extract_entities_from_text(text: str) -> list[str]:
    """Extract likely entity names from text using capitalized multi-word phrases.

    Simple NER fallback when llm_result doesn't include entities_mentioned.
    Looks for sequences of capitalized words (2+ words) that likely represent
    people, places, or events.
    """
    entities = set()
    # Match sequences of 2+ capitalized words (e.g., "Alexander the Great", "Philip II")
    for match in re.finditer(r'\b([A-Z][a-z]+(?:\s+(?:the|of|de|di|von|van|al-|el-|ibn|and|in)\s+)?(?:[A-Z][a-z]+(?:\s+[IVX]+)?)+)', text):
        name = match.group(0).strip()
        # Filter out common sentence starters and short matches
        if len(name) > 4 and name not in ('The', 'This', 'That', 'These', 'Those', 'What', 'When', 'Where', 'Which', 'There'):
            entities.add(name)
    return sorted(entities)


def create_transcript_chunks(transcript_id: str, node_id: str, domain_id: str,
                              transcript: str, llm_result: dict, conn) -> int:
    """Create embedded chunks from a voice transcript and link to nodes/entities.

    Handles both elicitation (captured/missed/interesting/wonderings/feedback_summary)
    and capture (facts/wonderings/entities_mentioned/overall_summary) llm_result formats.

    Returns the number of chunks created.
    """
    import uuid
    import numpy as np
    from limbic.amygdala import EmbeddingModel

    # Check idempotency: skip if chunks already exist for this transcript
    existing = conn.execute(
        'SELECT COUNT(*) FROM transcript_chunks WHERE transcript_id = ?',
        (transcript_id,)
    ).fetchone()
    if existing[0] > 0:
        return 0

    if not llm_result:
        llm_result = {}

    # Collect all chunks as (text, type) tuples
    chunks = []

    # Elicitation format: captured, interesting, wonderings, feedback_summary
    for fact in llm_result.get('captured', []):
        if isinstance(fact, str) and fact.strip():
            chunks.append((fact.strip(), 'captured_fact'))

    for item in llm_result.get('interesting', []):
        if isinstance(item, str) and item.strip():
            chunks.append((item.strip(), 'interesting'))

    # Capture format: facts[].fact
    for fact_obj in llm_result.get('facts', []):
        fact_text = fact_obj.get('fact', '') if isinstance(fact_obj, dict) else str(fact_obj)
        if fact_text.strip():
            chunks.append((fact_text.strip(), 'captured_fact'))

    # Wonderings (same key in both formats)
    for w in llm_result.get('wonderings', []):
        if isinstance(w, str) and w.strip():
            chunks.append((w.strip(), 'wondering'))

    # Research questions (elicitation format)
    for q in llm_result.get('research_questions', []):
        text = q.get('question', '') if isinstance(q, dict) else str(q)
        if text.strip():
            chunks.append((text.strip(), 'wondering'))

    # Feedback summary (elicitation) or overall_summary (capture)
    feedback = llm_result.get('feedback_summary', '') or llm_result.get('overall_summary', '')
    if feedback and feedback.strip():
        chunks.append((feedback.strip(), 'feedback'))

    # Raw speech: split transcript into paragraphs or sentence groups
    if transcript:
        paragraphs = [p.strip() for p in transcript.split('\n') if p.strip()]
        if len(paragraphs) <= 1 and transcript.strip():
            # Single block — split by sentences into ~100-word groups
            words = transcript.split()
            for i in range(0, len(words), 80):
                segment = ' '.join(words[i:i + 80])
                if segment.strip():
                    chunks.append((segment.strip(), 'raw_speech'))
        else:
            for p in paragraphs:
                if len(p.split()) >= 5:  # skip tiny fragments
                    chunks.append((p, 'raw_speech'))

    if not chunks:
        return 0

    # Batch embed all chunk texts
    model = EmbeddingModel()
    texts = [c[0] for c in chunks]
    embeddings = model.embed_batch(texts)

    # Insert chunks
    chunk_ids = []
    for i, (text, chunk_type) in enumerate(chunks):
        chunk_id = uuid.uuid4().hex[:12]
        chunk_ids.append(chunk_id)
        embedding_blob = embeddings[i].astype(np.float32).tobytes()
        conn.execute(
            'INSERT OR IGNORE INTO transcript_chunks (id, transcript_id, chunk_text, chunk_type, embedding) VALUES (?,?,?,?,?)',
            (chunk_id, transcript_id, text, chunk_type, embedding_blob)
        )

    # Primary node link for all chunks
    if node_id and domain_id:
        for chunk_id in chunk_ids:
            conn.execute(
                'INSERT OR IGNORE INTO chunk_node_links (chunk_id, node_id, domain_id, relevance) VALUES (?,?,?,?)',
                (chunk_id, node_id, domain_id, 1.0)
            )

    # Extract entities — prefer llm_result, fallback to NER
    entity_names = []
    for e in llm_result.get('entities_mentioned', []):
        name = e if isinstance(e, str) else str(e)
        if name.strip():
            entity_names.append(name.strip())
    if not entity_names:
        entity_names = _extract_entities_from_text(transcript or '')

    # Create entity links and find secondary node links via entity_curriculum_links
    for entity_name in entity_names:
        for chunk_id in chunk_ids:
            conn.execute(
                'INSERT OR IGNORE INTO chunk_entity_links (chunk_id, entity_name, relevance) VALUES (?,?,?)',
                (chunk_id, entity_name, 1.0)
            )

        # Find curriculum nodes linked to this entity for cross-node linking
        # Look up entity_id from shared_entities by name match
        entity_row = conn.execute(
            'SELECT entity_id FROM shared_entities WHERE name = ? OR name LIKE ?',
            (entity_name, f'%{entity_name}%')
        ).fetchone()
        if entity_row:
            linked_nodes = conn.execute(
                'SELECT domain_id, node_id FROM entity_curriculum_links WHERE entity_id = ?',
                (entity_row['entity_id'],)
            ).fetchall()
            for link in linked_nodes:
                # Skip the primary node (already linked above)
                if link['node_id'] == node_id and link['domain_id'] == domain_id:
                    continue
                for chunk_id in chunk_ids:
                    conn.execute(
                        'INSERT OR IGNORE INTO chunk_node_links (chunk_id, node_id, domain_id, relevance) VALUES (?,?,?,?)',
                        (chunk_id, link['node_id'], link['domain_id'], 0.7)
                    )

    # Node assessments from capture format — add direct links for assessed nodes
    for assessment in llm_result.get('node_assessments', []):
        assessed_node = assessment.get('node_id', '')
        if not assessed_node or (assessed_node == node_id):
            continue
        # Try to find the domain for this node
        node_row = conn.execute(
            'SELECT domain_id FROM curriculum_nodes WHERE id = ?', (assessed_node,)
        ).fetchone()
        if node_row:
            for chunk_id in chunk_ids:
                conn.execute(
                    'INSERT OR IGNORE INTO chunk_node_links (chunk_id, node_id, domain_id, relevance) VALUES (?,?,?,?)',
                    (chunk_id, assessed_node, node_row['domain_id'], 0.9)
                )

    conn.commit()
    return len(chunks)


def get_learner_context(node_id: str, domain_id: str, conn) -> str:
    """Retrieve learner's own words about a curriculum node for prompt injection.

    Combines two retrieval strategies:
    1. Relational: chunks directly linked to this node via chunk_node_links
    2. Semantic: top-5 most similar chunks across ALL chunks via cosine similarity
       against the node's description

    Returns a formatted string suitable for injection into LLM prompts, or empty
    string if no relevant chunks exist.
    """
    import numpy as np
    from limbic.amygdala import EmbeddingModel

    seen_ids = set()
    results = []  # (chunk_id, chunk_type, chunk_text, relevance_score)

    # Strategy 1: Relational retrieval — chunks linked to this node
    linked = conn.execute(
        '''SELECT tc.id, tc.chunk_type, tc.chunk_text, cnl.relevance
           FROM transcript_chunks tc
           JOIN chunk_node_links cnl ON tc.id = cnl.chunk_id
           WHERE cnl.node_id = ? AND cnl.domain_id = ?
           ORDER BY cnl.relevance DESC
           LIMIT 20''',
        (node_id, domain_id)
    ).fetchall()

    for row in linked:
        if row['id'] not in seen_ids:
            seen_ids.add(row['id'])
            results.append((row['id'], row['chunk_type'], row['chunk_text'], float(row['relevance'])))

    # Strategy 2: Semantic retrieval — embed node description, find similar chunks
    node_row = conn.execute(
        'SELECT title, description FROM curriculum_nodes WHERE id = ? AND domain_id = ?',
        (node_id, domain_id)
    ).fetchone()

    if node_row:
        node_text = f"{node_row['title']}. {node_row['description'] or ''}"
        try:
            model = EmbeddingModel()
            query_vec = model.embed(node_text)
        except Exception as _embed_err:
            # Embedding model unavailable (e.g. sentence_transformers not installed) —
            # fall back to relational results only
            print(f'[learner-context] Semantic retrieval skipped (embedding unavailable): {_embed_err}', flush=True)
            query_vec = None

        if query_vec is not None:
            # Load all chunks with embeddings (exclude raw_speech for semantic search
            # to prioritize structured knowledge)
            all_chunks = conn.execute(
                '''SELECT id, chunk_type, chunk_text, embedding
                   FROM transcript_chunks
                   WHERE embedding IS NOT NULL AND chunk_type != 'raw_speech'
                   LIMIT 2000'''
            ).fetchall()

            scored = []
            for chunk in all_chunks:
                if chunk['id'] in seen_ids:
                    continue
                chunk_vec = np.frombuffer(chunk['embedding'], dtype=np.float32)
                similarity = float(np.dot(query_vec, chunk_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(chunk_vec) + 1e-9))
                if similarity >= 0.35:
                    scored.append((chunk['id'], chunk['chunk_type'], chunk['chunk_text'], similarity))

            scored.sort(key=lambda x: -x[3])
            for item in scored[:5]:
                if item[0] not in seen_ids:
                    seen_ids.add(item[0])
                    results.append(item)

    if not results:
        return ''

    # Deduplicate by text similarity (skip near-identical chunks)
    unique_results = []
    seen_texts = set()
    for chunk_id, chunk_type, chunk_text, score in results:
        # Simple dedup: skip if first 60 chars match something already included
        text_key = chunk_text[:60].lower().strip()
        if text_key not in seen_texts:
            seen_texts.add(text_key)
            unique_results.append((chunk_id, chunk_type, chunk_text, score))

    if not unique_results:
        return ''

    # Format output — limit to top 10 most relevant chunks
    unique_results.sort(key=lambda x: -x[3])
    lines = []
    for _, chunk_type, chunk_text, _ in unique_results[:10]:
        # Truncate very long chunks
        display_text = chunk_text[:200] + '...' if len(chunk_text) > 200 else chunk_text
        display_text = display_text.replace('\n', ' ')
        lines.append(f'- [{chunk_type}] "{display_text}"')

    # Prepend domain-level portrait if available
    domain_summary = get_domain_summary(domain_id, conn)
    if domain_summary:
        lines.insert(0, f'DOMAIN KNOWLEDGE PORTRAIT:\n{domain_summary[:800]}\n')

    return 'LEARNER CONTEXT (from voice elicitation):\n' + '\n'.join(lines)


def get_domain_summary(domain_id: str, conn) -> str | None:
    """Retrieve the cached domain knowledge portrait, or None if not available."""
    try:
        row = conn.execute(
            'SELECT summary FROM domain_knowledge_summaries WHERE domain_id = ?',
            (domain_id,)
        ).fetchone()
        if row:
            return row['summary']
    except Exception:
        pass  # table might not exist yet
    return None


DOMAIN_SUMMARY_PROMPT = """Synthesize a learner knowledge portrait from their voice transcripts.

DOMAIN: {domain_title}

The learner has discussed these curriculum nodes via voice recall:

{node_sections}

Entities they've mentioned: {entities}

Write a 300-500 word knowledge portrait covering:
1. KNOWLEDGE FRAMEWORK: How does the learner organize this domain? What's their mental model?
   (chronological? biographical? geographic? thematic?)
2. STRONG AREAS: What do they know well? Cite specific facts and connections they made.
3. GAPS AND MISCONCEPTIONS: What's missing or wrong? Be specific about what they got wrong
   and what critical facts they're missing.
4. INTERESTS AND CURIOSITIES: What topics excite them? What wonderings did they express?
5. CONNECTIONS: What cross-domain or unexpected links have they made?
6. RECOMMENDED NEXT STEPS: Based on this profile, what should they read or review next?

Write in second person ("You know...", "Your strongest area..."). Be specific — cite
their actual words and facts, don't generalize. This portrait will be injected into
every LLM prompt in this domain to personalize the learner's experience.

Output JSON:
{{"portrait": "the full text portrait", "framework_type": "chronological|biographical|geographic|thematic|mixed", "strong_nodes": ["node_id_1", "node_id_2"], "weak_nodes": ["node_id_3"], "key_misconceptions": ["misconception 1"], "interests": ["topic 1", "topic 2"], "recommended_nodes": ["node_id to review next"]}}"""


def generate_domain_summary(domain_id: str, conn=None) -> str | None:
    """Generate a synthesized knowledge portrait for a domain from voice transcript chunks.

    Queries all transcript_chunks linked to this domain, groups by node, and calls
    Claude to synthesize a learner knowledge portrait. Stores the result in
    domain_knowledge_summaries (UPSERT with version increment).

    Follows write-lock discipline: reads → close → LLM call → reopen → write.
    If conn is provided, it's used for the initial read only and NOT held during
    the LLM call. A fresh connection is opened for the final write.

    Returns the portrait text, or None if insufficient data.
    """
    import uuid
    from db import get_connection

    # Phase 1: Read all data (fast)
    own_conn = conn is None
    if own_conn:
        conn = get_connection(readonly=True)

    chunk_count = conn.execute(
        'SELECT COUNT(DISTINCT cnl.chunk_id) FROM chunk_node_links cnl WHERE cnl.domain_id = ?',
        (domain_id,)
    ).fetchone()[0]

    if chunk_count < 10:
        if own_conn:
            conn.close()
        return None

    curriculum = load_curriculum(domain_id)
    if not curriculum:
        if own_conn:
            conn.close()
        return None
    domain_title = curriculum.get('title', domain_id)

    rows = conn.execute(
        '''SELECT cn.id as node_id, cn.title as node_title,
                  tc.chunk_type, tc.chunk_text
           FROM chunk_node_links cnl
           JOIN transcript_chunks tc ON cnl.chunk_id = tc.id
           JOIN curriculum_nodes cn ON cnl.node_id = cn.id AND cnl.domain_id = cn.domain_id
           WHERE cnl.domain_id = ?
           ORDER BY cn.title, tc.chunk_type''',
        (domain_id,)
    ).fetchall()

    from collections import defaultdict
    node_chunks = defaultdict(list)
    node_ids = set()
    for row in rows:
        node_chunks[row['node_title']].append((row['chunk_type'], row['chunk_text']))
        node_ids.add(row['node_id'])

    node_sections = []
    for node_title, chunks in node_chunks.items():
        section = f'### {node_title}\n'
        for chunk_type, chunk_text in chunks[:8]:
            display = chunk_text[:300].replace('\n', ' ')
            section += f'- [{chunk_type}] {display}\n'
        node_sections.append(section)

    entity_rows = conn.execute(
        '''SELECT DISTINCT cel.entity_name
           FROM chunk_entity_links cel
           JOIN chunk_node_links cnl ON cel.chunk_id = cnl.chunk_id
           WHERE cnl.domain_id = ?
           ORDER BY cel.entity_name
           LIMIT 50''',
        (domain_id,)
    ).fetchall()
    entities = ', '.join(r['entity_name'] for r in entity_rows)
    entity_count = len(entity_rows)
    node_count = len(node_ids)

    # Check existing version before closing
    existing = conn.execute(
        'SELECT version FROM domain_knowledge_summaries WHERE domain_id = ?',
        (domain_id,)
    ).fetchone()
    new_version = (existing['version'] + 1) if existing else 1

    if own_conn:
        conn.close()

    # Phase 2: LLM call (slow — no DB connection held)
    sections_text = '\n'.join(node_sections)
    if len(sections_text) > 8000:
        sections_text = sections_text[:8000] + '\n...(truncated)'

    prompt = DOMAIN_SUMMARY_PROMPT.format(
        domain_title=domain_title,
        node_sections=sections_text,
        entities=entities or '(none detected)',
    )

    result = call_claude_json(prompt, timeout=120)
    if not result or 'portrait' not in result:
        print(f'[domain-summary] Claude returned no portrait for {domain_id}', flush=True)
        return None

    portrait = result['portrait']

    # Phase 3: Write result (fast — new connection)
    write_conn = get_connection()
    try:
        summary_id = str(uuid.uuid4())[:8]
        write_conn.execute(
            '''INSERT INTO domain_knowledge_summaries
               (id, domain_id, summary, chunk_count, node_count, entity_count, version, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(domain_id) DO UPDATE SET
                   summary = excluded.summary,
                   chunk_count = excluded.chunk_count,
                   node_count = excluded.node_count,
                   entity_count = excluded.entity_count,
                   version = excluded.version,
                   updated_at = excluded.updated_at''',
            (summary_id, domain_id, portrait, chunk_count, node_count, entity_count, new_version)
        )
        write_conn.commit()
    finally:
        write_conn.close()

    print(f'[domain-summary] Generated portrait for {domain_title}: {len(portrait)} chars, v{new_version}', flush=True)
    return portrait


def get_learner_context_for_entity(entity_name: str, conn) -> str:
    """Retrieve learner's own words about a specific entity for prompt injection.

    Queries chunk_entity_links to find chunks where the learner mentioned this entity.
    Returns a formatted string suitable for injection into LLM prompts.
    """
    rows = conn.execute(
        '''SELECT tc.id, tc.chunk_type, tc.chunk_text, cel.relevance
           FROM transcript_chunks tc
           JOIN chunk_entity_links cel ON tc.id = cel.chunk_id
           WHERE cel.entity_name = ?
           ORDER BY cel.relevance DESC
           LIMIT 15''',
        (entity_name,)
    ).fetchall()

    if not rows:
        # Try fuzzy match on entity name
        rows = conn.execute(
            '''SELECT tc.id, tc.chunk_type, tc.chunk_text, cel.relevance
               FROM transcript_chunks tc
               JOIN chunk_entity_links cel ON tc.id = cel.chunk_id
               WHERE cel.entity_name LIKE ?
               ORDER BY cel.relevance DESC
               LIMIT 15''',
            (f'%{entity_name}%',)
        ).fetchall()

    if not rows:
        return ''

    # Deduplicate by text prefix
    seen_texts = set()
    lines = []
    for row in rows:
        text_key = row['chunk_text'][:60].lower().strip()
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)
        display_text = row['chunk_text'][:200] + '...' if len(row['chunk_text']) > 200 else row['chunk_text']
        display_text = display_text.replace('\n', ' ')
        lines.append(f'- [{row["chunk_type"]}] "{display_text}"')

    if not lines:
        return ''

    return f'LEARNER CONTEXT about {entity_name} (from voice elicitation):\n' + '\n'.join(lines[:10])


# ── Voice elicitation (free recall) ─────────────────────────────────────────

def run_voice_elicitation(node_id: str, domain_id: str, audio_path: Path, conn, transcribe_fn) -> dict:
    """Run voice free-recall elicitation for a curriculum node or chapter recall.

    User speaks freely about what they know about a topic.
    System transcribes, compares against node definition + book sources, gives rich feedback.

    conn can be None — the function manages its own connections to avoid holding
    the write lock during slow operations (transcription + LLM).
    """
    from db import get_connection
    if conn is None:
        conn = get_connection()
    # Handle era sweep pseudo-nodes (sweep:{era_id})
    is_era_sweep = node_id.startswith('sweep:')
    if is_era_sweep:
        era_id = node_id.split(':', 1)[1]
        # Transcribe first, then delegate to run_era_sweep
        print(f'[voice-elicit] Era sweep detected: {era_id}, domain={domain_id}', flush=True)
        print(f'[voice-elicit] Transcribing {audio_path} ({audio_path.stat().st_size} bytes)...', flush=True)
        transcript = transcribe_fn(audio_path)
        if not transcript or len(transcript.split()) < 5:
            return {'error': 'too_short', 'feedback_summary': 'Recording was too short for a sweep. Try speaking for at least 30 seconds.'}
        result = run_era_sweep(era_id, domain_id, transcript, conn)
        result['transcript'] = transcript
        # Log to voice_transcripts
        from db import get_connection as _gc2
        vconn = _gc2()
        try:
            vt_id = f'vt_sweep_{int(time.time())}_{hash(transcript) % 10000:04d}'
            _log_voice_transcript(
                source='era_sweep', node_id=era_id, domain_id=domain_id,
                node_title=result.get('era_title', era_id),
                transcript=transcript, audio_bytes=audio_path.stat().st_size,
                llm_result=result, conn=vconn,
            )
            vconn.commit()
        except Exception as e:
            print(f'[voice-elicit] Failed to log era sweep transcript: {e}', flush=True)
        finally:
            vconn.close()
        if conn:
            conn.close()
        return result

    # Handle chapter recall pseudo-nodes (chapter:{book_id}:{chapter_number})
    is_chapter_recall = node_id.startswith('chapter:')
    is_book_recall = node_id.startswith('book:')
    book_id = ''
    chapter_num = ''
    chapter_source_texts = []

    if is_chapter_recall or is_book_recall:
        parts = node_id.split(':')
        book_id = parts[1] if len(parts) > 1 else ''
        chapter_num = parts[2] if len(parts) > 2 and is_chapter_recall else ''

        # Auto-detect domain_id from book if not provided
        if not domain_id and book_id:
            row = conn.execute(
                "SELECT DISTINCT curriculum_domain FROM knowledge_items WHERE sources LIKE ? LIMIT 1",
                (f'%{book_id}%',)
            ).fetchone()
            if row:
                domain_id = row['curriculum_domain']

        # Look up book title and chapter sources
        book_title = ''
        chapter_title = ''
        source_query = f'%{book_id}%'
        domain_clause = "AND curriculum_domain = ?" if domain_id else ""
        domain_params = (source_query, domain_id) if domain_id else (source_query,)
        rows = conn.execute(
            f"SELECT sources FROM knowledge_items WHERE sources LIKE ? {domain_clause}",
            domain_params
        ).fetchall()
        for r in rows:
            try:
                sources = json.loads(r['sources'])
                for s in sources:
                    if s.get('book_id') != book_id:
                        continue
                    book_title = book_title or s.get('book_title', book_id)
                    if is_chapter_recall:
                        if str(s.get('chapter_number', '')) == str(chapter_num):
                            chapter_title = chapter_title or s.get('chapter_title', '')
                            if s.get('source_text'):
                                chapter_source_texts.append(s['source_text'])
                    else:
                        # Book recall — gather all source texts
                        if s.get('source_text'):
                            chapter_source_texts.append(s['source_text'])
            except Exception:
                pass

        # Fall back to book title from physical_books table
        if not book_title:
            bt_row = conn.execute('SELECT title FROM physical_books WHERE id = ?', (book_id,)).fetchone()
            if bt_row:
                book_title = bt_row['title']

        if is_chapter_recall:
            node = {
                'id': node_id,
                'title': f'Chapter {chapter_num}: {chapter_title}' if chapter_title else f'Chapter {chapter_num}',
                'description': f'What do you remember from Chapter {chapter_num} of {book_title}? Key ideas, people, events, and arguments.',
            }
        else:
            node = {
                'id': node_id,
                'title': book_title or book_id,
                'description': f'What do you remember from {book_title}? Speak freely about key ideas, people, events, themes, and anything that stuck with you.',
            }
    else:
        # Standard curriculum node
        if not domain_id:
            return {'error': 'Missing domain_id for curriculum node'}
        curriculum = load_curriculum(domain_id)
        if not curriculum:
            return {'error': f'Curriculum {domain_id} not found'}

        node = None
        for n in curriculum.get('nodes', []):
            if n['id'] == node_id:
                node = n
                break
        if not node:
            return {'error': f'Node {node_id} not found'}

    # Gather sources BEFORE closing connection
    if (is_chapter_recall or is_book_recall) and chapter_source_texts:
        sources_text = '\n'.join(chapter_source_texts[:8])
    else:
        sources_text = _gather_node_sources(node_id, domain_id, conn) if domain_id else ''

    # Dedup: if this exact audio was already processed for this node, return cached result
    audio_size = audio_path.stat().st_size if audio_path.exists() else 0
    if audio_size > 0:
        existing = conn.execute(
            "SELECT llm_result FROM voice_transcripts WHERE node_id = ? AND audio_bytes = ? AND source = 'elicitation' LIMIT 1",
            (node_id, audio_size)
        ).fetchone()
        if existing and existing['llm_result']:
            try:
                cached = json.loads(existing['llm_result'])
                # Only return if the cached result has actual analysis content
                if cached.get('captured') or cached.get('missed') or cached.get('feedback_summary'):
                    cached['from_cache'] = True
                    print(f'[voice-elicit] Dedup hit: node={node_id}, audio={audio_size} bytes — returning cached result', flush=True)
                    conn.close()
                    return cached
                else:
                    print(f'[voice-elicit] Dedup match for {node_id} has empty analysis, re-processing', flush=True)
            except (json.JSONDecodeError, TypeError):
                pass

    # Close connection before slow work (transcription + LLM) to avoid write lock
    conn.close()

    # Transcribe
    print(f'[voice-elicit] Transcribing {audio_path} ({audio_path.stat().st_size} bytes)...', flush=True)
    transcript = transcribe_fn(audio_path)
    print(f'[voice-elicit] Transcript: {repr(transcript[:200]) if transcript else "EMPTY"}', flush=True)
    if not transcript:
        return {'error': 'Transcription failed'}

    word_count = len(transcript.split())
    print(f'[voice-elicit] Transcript: {word_count} words. Sources: {len(sources_text)} chars', flush=True)

    # Build available nodes list for adjacent_nodes_covered detection
    available_nodes_text = ''
    if domain_id:
        curriculum = load_curriculum(domain_id)
        if curriculum:
            available_nodes_text = '\n'.join(
                f'- {n["id"]}: {n["title"]}'
                for n in curriculum.get('nodes', [])
                if n.get('level', 0) >= 2 and n['id'] != node_id
            )[:2000]  # cap at 2000 chars

    # Run LLM analysis
    prompt = VOICE_ELICITATION_PROMPT.format(
        node_title=node['title'],
        node_description=node['description'],
        sources_text=sources_text or 'No specific book sources available.',
        available_nodes=available_nodes_text or 'Not available',
        transcript=transcript,
    )

    result = call_claude_json(prompt, timeout=180)
    print(f'[voice-elicit] LLM result type={type(result).__name__}, keys={list(result.keys()) if isinstance(result, dict) else "N/A"}', flush=True)
    if not isinstance(result, dict):
        print(f'[voice-elicit] LLM returned non-dict: {repr(str(result)[:200])}', flush=True)
        result = {}

    # Populate result metadata (no DB needed)
    result['node_title'] = node['title']
    result['node_description'] = node['description']
    result['transcript'] = transcript

    # Generate stable transcript ID for both chunk creation and voice_transcripts logging
    vt_id = f'vt_{int(time.time())}_{hash(transcript) % 10000:04d}'

    # DB writes with retry — the expensive work (transcription + LLM) is done,
    # so we retry only the cheap write portion if the DB is locked.
    import sqlite3
    research_triggers = []
    max_write_attempts = 3
    for attempt in range(max_write_attempts):
        try:
            conn = get_connection()
            conn.execute('PRAGMA busy_timeout = 60000')  # 60s wait for lock

            # Generate temporal hook (skip for chapter recall)
            temporal_hook = '' if (is_chapter_recall or is_book_recall) else _generate_temporal_hook(node, domain_id, conn)
            result['temporal_hook'] = temporal_hook

            # Process "wonderings" — create research triggers (with dedup)
            wonderings = result.get('wonderings', [])
            research_triggers = []
            for w in wonderings[:5]:
                # Skip if this exact wondering already exists for this node
                existing_q = conn.execute(
                    "SELECT id FROM review_items WHERE item_type = 'voice_followup' AND curriculum_node_id = ? AND source_text = ?",
                    (node_id, w)
                ).fetchone()
                if existing_q:
                    research_triggers.append({'id': existing_q['id'], 'question': w, 'existing': True})
                    continue
                trigger_id = f'wonder_{node_id}_{int(time.time() * 1000)}'
                try:
                    # Initialize with FSRS card state
                    _new_card = FsrsCard()
                    _card_json = json.dumps(_new_card.to_dict())
                    _initial_due = int(_new_card.due.timestamp() * 1000)
                    conn.execute("""
                        INSERT INTO review_items
                          (id, item_type, curriculum_domain, curriculum_node_id, curriculum_node_title,
                           source_text, lens, stability_days, due_at, review_count, created_at, fsrs_card_json)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        trigger_id, 'voice_followup',
                        domain_id, node_id, node['title'],
                        w, 'SIGNIFICANCE', 1.0,
                        _initial_due,
                        0, int(time.time() * 1000), _card_json,
                    ))
                    research_triggers.append({'id': trigger_id, 'question': w})
                except Exception:
                    pass

            # Update knowledge state based on coverage
            coverage = result.get('coverage_pct', 50)
            score = result.get('suggested_score', 'partly')
            knowledge_level = 'anchored' if score == 'knew' else 'engaged' if score == 'partly' else 'mentioned'
            confidence = coverage / 100.0

            if is_chapter_recall or is_book_recall:
                if book_id and domain_id:
                    if is_chapter_recall and chapter_num:
                        source_filter = f'%"chapter_number": {chapter_num}%'
                    else:
                        source_filter = f'%{book_id}%'
                    ki_rows = conn.execute(
                        "SELECT id, curriculum_node_id FROM knowledge_items WHERE curriculum_domain = ? AND sources LIKE ?",
                        (domain_id, source_filter)
                    ).fetchall()
                    source_tag = f'voice_chapter_recall:{book_id}:{chapter_num}' if is_chapter_recall else f'voice_book_recall:{book_id}'
                    for ki in ki_rows:
                        update_knowledge(domain_id, ki['curriculum_node_id'],
                                         knowledge=knowledge_level, confidence=confidence,
                                         source=source_tag, conn=conn)
            else:
                update_knowledge(domain_id, node_id, knowledge=knowledge_level,
                                 confidence=confidence, source='voice_elicitation', conn=conn)

            # Reschedule matched knowledge_items via FSRS
            if is_chapter_recall or is_book_recall:
                if book_id and domain_id:
                    if is_chapter_recall and chapter_num:
                        source_filter = f'%"chapter_number": {chapter_num}%'
                    else:
                        source_filter = f'%{book_id}%'
                    ki_ids = [r['id'] for r in conn.execute(
                        "SELECT id FROM knowledge_items WHERE curriculum_domain = ? AND sources LIKE ?",
                        (domain_id, source_filter)).fetchall()]
                    for kid in ki_ids:
                        _fsrs_reschedule(kid, score, conn)
            else:
                ki_ids = [r['id'] for r in conn.execute(
                    "SELECT id FROM knowledge_items WHERE curriculum_node_id = ? AND curriculum_domain = ?",
                    (node_id, domain_id)).fetchall()]
                for kid in ki_ids:
                    _fsrs_reschedule(kid, score, conn)

            # Create transcript chunks for knowledge profile
            try:
                chunks_created = create_transcript_chunks(
                    transcript_id=vt_id,
                    node_id=node_id,
                    domain_id=domain_id,
                    transcript=transcript,
                    llm_result=result,
                    conn=conn,
                )
                if chunks_created > 0:
                    print(f'[voice-elicit] Created {chunks_created} transcript chunks for knowledge profile', flush=True)
            except Exception as e:
                print(f'[voice-elicit] Failed to create transcript chunks: {e}', flush=True)

            conn.commit()
            conn.close()
            break  # success
        except sqlite3.OperationalError as e:
            if 'locked' in str(e) and attempt < max_write_attempts - 1:
                print(f'[voice-elicit] DB locked on write attempt {attempt + 1}, retrying in {5 * (attempt + 1)}s...', flush=True)
                try:
                    conn.close()
                except Exception:
                    pass
                time.sleep(5 * (attempt + 1))
            else:
                print(f'[voice-elicit] DB write failed after {attempt + 1} attempts: {e}', flush=True)
                try:
                    conn.close()
                except Exception:
                    pass
                # Don't raise — return the LLM result even if writes failed
                break

    result['research_triggers'] = research_triggers

    # --- Create knowledge_items for elicitation-discovered facts ---
    # When the learner demonstrates knowledge about a node during elicitation,
    # create a knowledge_item so quiz questions can be generated for retention.
    if not (is_chapter_recall or is_book_recall):
        captured = result.get('captured', [])
        if captured and node_id and domain_id:
            item_id = f'{domain_id}:{node_id}'
            eli_conn = None
            try:
                eli_conn = get_connection()
                existing = eli_conn.execute(
                    'SELECT id, sources FROM knowledge_items WHERE id = ?', (item_id,)
                ).fetchone()
                if not existing:
                    captured_texts = []
                    for c in captured:
                        if isinstance(c, dict):
                            captured_texts.append(c.get('fact', c.get('text', str(c))))
                        else:
                            captured_texts.append(str(c))
                    source_text = '; '.join(captured_texts[:8])

                    # Use higher initial stability for elicitation — this is long-term memory
                    elicitation_initial_stability = 14.0  # 2 weeks (vs 1 day for new items)
                    now_ms = int(time.time() * 1000)
                    due_at = now_ms + int(elicitation_initial_stability * 86400 * 1000)

                    new_source = {
                        'source': 'voice_elicitation',
                        'source_text': source_text[:400],
                        'fact_count': len(captured),
                        'added_at': now_ms,
                    }
                    _new_card = FsrsCard()
                    _card_json = json.dumps(_new_card.to_dict())
                    eli_conn.execute('''
                        INSERT INTO knowledge_items
                        (id, curriculum_node_id, curriculum_domain, stability_days, due_at,
                         sources, question_history, created_at, fsrs_card_json)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    ''', (
                        item_id, node_id, domain_id,
                        elicitation_initial_stability, due_at,
                        json.dumps([new_source]), '[]', now_ms,
                        _card_json,
                    ))
                    eli_conn.commit()
                    print(f'[voice-elicit] Created knowledge_item {item_id} with {len(captured)} facts, '
                          f'stability={elicitation_initial_stability}d', flush=True)

                    # Pre-generate a quiz question in background
                    def _pregen_elicitation_question(iid):
                        c = None
                        try:
                            from db import get_connection as _gc
                            c = _gc()
                            q = generate_question(iid, c)
                            c.execute('UPDATE knowledge_items SET cached_question = ? WHERE id = ?',
                                      (json.dumps(q), iid))
                            c.commit()
                            print(f'[voice-elicit] Pre-generated question for {iid}', flush=True)
                        except Exception as e:
                            print(f'[voice-elicit] Question pre-gen failed for {iid}: {e}', flush=True)
                        finally:
                            if c:
                                c.close()
                    threading.Thread(target=_pregen_elicitation_question,
                                     args=(item_id,), daemon=True).start()
            except Exception as e:
                print(f'[voice-elicit] knowledge_item creation failed: {e}', flush=True)
            finally:
                if eli_conn:
                    eli_conn.close()

    # --- Create correction quizzes for confidently-stated wrong facts ---
    confidence_tagged = result.get('confidence_tagged', [])
    wrong_facts = [ct for ct in confidence_tagged
                   if isinstance(ct, dict) and ct.get('confidence') == 'wrong']
    corrections_triggered = []
    for wf in wrong_facts[:3]:
        fact_text = wf.get('fact', '')
        if not fact_text:
            continue
        q = f'Correction needed: The learner believes "{fact_text}" — what is actually true?'
        try:
            card_id = create_microlearning_request(
                query=q, source_node_id=node_id, source_domain=domain_id,
                source_type='correction',
            )
            corrections_triggered.append({'id': card_id, 'wrong_fact': fact_text})
            print(f'[voice→ml] correction → {card_id}: {fact_text[:60]}', flush=True)
        except Exception as e:
            print(f'[voice→ml] correction trigger failed: {e}', flush=True)
    result['corrections_triggered'] = corrections_triggered

    # Trigger microlearning for wonderings only (not missed facts)
    ml_triggered = []
    # Wonderings → microlearning (purest signal — user literally said "I wonder...")
    for w in wonderings[:3]:
        try:
            card_id = create_microlearning_request(
                query=w, source_node_id=node_id, source_domain=domain_id,
                source_type='voice_wondering',
            )
            ml_triggered.append({'id': card_id, 'query': w})
            print(f'[voice→ml] wondering → {card_id}: {w[:60]}', flush=True)
        except Exception as e:
            print(f'[voice→ml] wondering trigger failed: {e}', flush=True)

    # Research questions from LLM extraction (derived from wonderings)
    for q in result.get('research_questions', [])[:3]:
        if isinstance(q, dict):
            q = q.get('question', '') or q.get('query', '')
        q = str(q).strip()
        if q and q not in [m['query'] for m in ml_triggered]:
            try:
                card_id = create_microlearning_request(
                    query=q, source_node_id=node_id, source_domain=domain_id,
                    source_type='voice_wondering',
                )
                ml_triggered.append({'id': card_id, 'query': q})
                print(f'[voice→ml] research question → {card_id}: {q[:60]}', flush=True)
            except Exception as e:
                print(f'[voice→ml] research question failed: {e}', flush=True)

    # NOTE: Missed facts are NOT turned into ML cards — the user prefers
    # to fill knowledge gaps through reading, not quizzing on unread content.
    # Missed facts remain visible in the elicitation results UI.

    result['microlearning_triggered'] = ml_triggered

    # Persist transcript for later analysis
    _log_voice_transcript(
        source='elicitation', node_id=node_id, domain_id=domain_id,
        node_title=node['title'], transcript=transcript,
        audio_bytes=audio_path.stat().st_size if audio_path.exists() else 0,
        llm_result=result, ml_triggered=ml_triggered,
        vt_id=vt_id,
    )

    return result


def process_voice_capture(transcript: str, entity_id: str = None,
                          entity_name: str = None, mode: str = 'general',
                          sync: bool = False, capture_type: str = 'analyze',
                          input_mode: str = 'audio') -> dict:
    """Process a voice capture for knowledge graph ingestion.

    Unlike run_voice_elicitation (which tests recall of a specific node),
    this ingests new knowledge: extracting facts, mapping to curriculum nodes,
    updating knowledge states, adding sources to knowledge_items, and
    triggering question generation + microlearning from wonderings.

    capture_type='insight' short-circuits after node detection: saves the
    transcript linked to curriculum nodes but skips LLM analysis, knowledge
    updates, and microlearning generation. For unverified theories/hypotheses
    the user wants to revisit later.

    Returns dict with: transcript, facts, node_assessments, wonderings,
    knowledge_updates, microlearning_triggered, questions_queued.
    """
    from db import get_connection
    import sqlite3

    if not transcript or len(transcript.split()) < 5:
        return {'error': 'Transcript too short for analysis', 'transcript': transcript}

    # Dedup: skip if this exact transcript was already processed
    import hashlib
    transcript_hash = hashlib.sha256(transcript.encode()).hexdigest()[:16]
    dedup_conn = get_connection(readonly=True)
    existing_vt = dedup_conn.execute(
        "SELECT id FROM voice_transcripts WHERE id LIKE '%' || ? || '%' OR transcript = ?",
        (transcript_hash, transcript)
    ).fetchone()
    if not existing_vt:
        # Also check by exact text match (covers older entries without hash in id)
        existing_vt = dedup_conn.execute(
            "SELECT id FROM voice_transcripts WHERE transcript = ? LIMIT 1",
            (transcript,)
        ).fetchone()
    dedup_conn.close()
    if existing_vt:
        print(f'[voice-capture] Skipping duplicate transcript (matches {existing_vt["id"]})', flush=True)
        return {'error': 'Duplicate transcript already processed', 'existing_id': existing_vt['id']}

    conn = get_connection(readonly=True)

    # --- Find candidate curriculum nodes ---
    # Strategy: start with directly-linked nodes (high confidence), then expand
    # with relevant sibling nodes from the same domains. Keep it focused to avoid
    # bloating the LLM prompt with irrelevant nodes.
    directly_linked_node_ids = set()  # highest priority
    candidate_domains = set()
    detected_entity_ids = []

    # Helper: check if entity name matches transcript via word overlap
    transcript_lower = transcript.lower()
    transcript_words = set(w.lower() for w in re.split(r'\W+', transcript) if len(w) > 3)

    # Generic words that appear in many entity names — too common to be informative
    # as the sole evidence of a match. "Ancient Skepticism" matching only on
    # "ancient" is a false positive when the transcript is about Frederick II.
    # An entity matching only on these words is rejected; "Greek Dark Ages"
    # matching only "greek" + "ages" both stops gives no distinctive match.
    _STOP_WORDS_FOR_MATCHING = {
        # Period descriptors
        'ancient', 'modern', 'medieval', 'classical', 'late', 'early', 'middle', 'old',
        'great', 'high', 'first', 'second', 'third', 'fourth',
        # Demonyms — common in entity names ("German Idealism", "Greek Tragedy"),
        # weak as sole match (a podcast that says "Greek philosophers" once
        # shouldn't match every entity starting with "Greek")
        'german', 'italian', 'french', 'spanish', 'english', 'greek', 'roman',
        'persian', 'arab', 'arabic', 'byzantine', 'norman',
        # Cardinal directions and zones
        'eastern', 'western', 'northern', 'southern',
        # Generic period/scope nouns
        'history', 'historical', 'period', 'era', 'ages', 'world', 'century',
        # Religious/cultural categories
        'church', 'churches', 'christian', 'christianity', 'religious',
        # Polity / governance types
        'empire', 'kingdom', 'state', 'civilization', 'culture', 'cultural',
        # Discipline names
        'literature', 'philosophy', 'theology', 'language', 'languages',
        'tradition', 'movement', 'movements', 'school', 'schools', 'theory',
    }

    def _entity_matches_transcript(name: str) -> bool:
        """Match multi-word entity names by checking word overlap with transcript."""
        if len(name) < 4:
            return False
        name_lower = name.lower()
        # Direct substring match with word boundary check for short names
        if name_lower in transcript_lower:
            # For short names (< 8 chars), verify word boundary to avoid false positives
            if len(name) < 8:
                import re as _re
                if not _re.search(r'\b' + _re.escape(name_lower) + r'\b', transcript_lower):
                    return False
            return True
        # Word overlap with prefix matching (handles plurals: "Umayyad" ↔ "Umayyads")
        name_words = set(w.lower() for w in re.split(r'\W+', name) if len(w) > 3)
        if not name_words:
            return False
        # Exact matches first
        matching = name_words & transcript_words
        # Prefix matching for words >= 5 chars (avoids "Rome"/"Romeo" false positives)
        for nw in name_words - matching:
            if len(nw) >= 5:
                for tw in transcript_words:
                    if len(tw) >= 5 and (nw.startswith(tw) or tw.startswith(nw)):
                        matching.add(nw)
                        break
        overlap = len(matching) / len(name_words)
        # Distinctive matches = matched words that aren't generic period/type descriptors
        distinctive = matching - _STOP_WORDS_FOR_MATCHING
        if len(name_words) == 1:
            return overlap >= 1.0  # single-word entities must match exactly
        # For 2-word entities (e.g. "Rashidun Caliphate"), accept 1/2 match
        # if the matching word is distinctive (>= 6 chars and not a stop word)
        if len(name_words) == 2 and len(matching) == 1:
            matched_word = next(iter(matching))
            return len(matched_word) >= 6 and matched_word not in _STOP_WORDS_FOR_MATCHING
        # For 3+ word entities, require 60%+ match AND at least one distinctive
        # (non-generic) word — prevents "Early Christian Basilicas" matching just
        # because transcript has "early Normans" and "heretic Christians"
        return overlap >= 0.6 and len(matching) >= 2 and len(distinctive) >= 1

    if entity_id:
        # Entity mode: get all curriculum links for this entity
        detected_entity_ids = [entity_id]
        links = conn.execute(
            'SELECT domain_id, node_id FROM entity_curriculum_links WHERE entity_id = ?',
            (entity_id,)
        ).fetchall()
        for link in links:
            directly_linked_node_ids.add(link['node_id'])
            candidate_domains.add(link['domain_id'])

    # For general mode or as fallback: detect entities from transcript
    if not entity_id or not candidate_domains:
        entity_rows = conn.execute(
            'SELECT entity_id, name FROM shared_entities'
        ).fetchall()
        for row in entity_rows:
            if _entity_matches_transcript(row['name']):
                detected_entity_ids.append(row['entity_id'])
                if not entity_name:
                    entity_name = row['name']

        if detected_entity_ids:
            links = conn.execute(
                'SELECT DISTINCT domain_id, node_id, entity_id FROM entity_curriculum_links WHERE entity_id IN ({})'.format(
                    ','.join('?' * len(detected_entity_ids))),
                detected_entity_ids
            ).fetchall()
            for link in links:
                directly_linked_node_ids.add(link['node_id'])
                candidate_domains.add(link['domain_id'])

    print(f'[voice-capture] Detected entities: {detected_entity_ids[:10]}, '
          f'directly linked nodes: {len(directly_linked_node_ids)}, '
          f'domains: {candidate_domains}', flush=True)

    # --- Domain routing: when entity matching finds few nodes, use Gemini Flash
    # to identify the most relevant curriculum domains from the transcript ---
    routed_domain_ids: list[str] = []
    if len(directly_linked_node_ids) < 5:
        try:
            from gemini_llm import call_llm as _gemini_call
            all_domains = conn.execute(
                "SELECT DISTINCT domain_id FROM curriculum_nodes ORDER BY domain_id"
            ).fetchall()
            domain_info = []
            for d in all_domains:
                title_row = conn.execute(
                    "SELECT title FROM curriculum_nodes WHERE domain_id = ? AND level = 1 LIMIT 1",
                    (d['domain_id'],)
                ).fetchone()
                domain_info.append(f"- {d['domain_id']}: {title_row['title'] if title_row else '?'}")
            domain_list = '\n'.join(domain_info)
            route_prompt = (
                f"Which 3 curriculum domains are most relevant to this voice transcript?\n\n"
                f"Domains:\n{domain_list}\n\n"
                f"Transcript (excerpt):\n{transcript[:1500]}\n\n"
                f'Return JSON: {{"domains": ["domain_id_1", "domain_id_2", "domain_id_3"]}}'
            )
            route_raw = _gemini_call(route_prompt, max_tokens=200,
                                     response_mime_type="application/json")
            if route_raw:
                routed = json.loads(route_raw).get("domains", [])[:3]
                valid_ids = {d['domain_id'] for d in all_domains}
                routed_domain_ids = [d for d in routed if d in valid_ids]
                for rid in routed_domain_ids:
                    candidate_domains.add(rid)
                print(f'[voice-capture] Domain routing: {routed_domain_ids}', flush=True)
        except Exception as e:
            print(f'[voice-capture] Domain routing failed (non-fatal): {e}', flush=True)

    # Build candidate nodes: start with directly-linked, then add relevant siblings
    candidate_nodes = []
    seen_node_ids = set()

    # Phase 1: Directly linked nodes (always included)
    if directly_linked_node_ids:
        placeholders = ','.join('?' * len(directly_linked_node_ids))
        nodes = conn.execute(
            f'SELECT id, domain_id, title, description FROM curriculum_nodes WHERE id IN ({placeholders})',
            list(directly_linked_node_ids)
        ).fetchall()
        for n in nodes:
            candidate_nodes.append({
                'node_id': n['id'],
                'domain_id': n['domain_id'],
                'title': n['title'],
                'description': (n['description'] or '')[:200],
                'priority': 'direct',
            })
            seen_node_ids.add(n['id'])

    # Phase 2: Sibling nodes from the same domains that have title word overlap with transcript
    for domain_id in candidate_domains:
        nodes = conn.execute(
            'SELECT id, title, description FROM curriculum_nodes WHERE domain_id = ? AND level >= 2',
            (domain_id,)
        ).fetchall()
        for n in nodes:
            if n['id'] in seen_node_ids:
                continue
            title_words = set(w.lower() for w in re.split(r'\W+', n['title']) if len(w) > 3)
            overlap = len(title_words & transcript_words)
            if overlap > 0:
                candidate_nodes.append({
                    'node_id': n['id'],
                    'domain_id': domain_id,
                    'title': n['title'],
                    'description': (n['description'] or '')[:200],
                    'priority': 'sibling',
                    'overlap': overlap,
                })
                seen_node_ids.add(n['id'])

    # Phase 2b: Nodes from LLM-routed domains (when entity matching was sparse)
    if routed_domain_ids:
        routed_placeholders = ','.join('?' * len(routed_domain_ids))
        routed_nodes = conn.execute(
            f"SELECT id, domain_id, title, description FROM curriculum_nodes "
            f"WHERE domain_id IN ({routed_placeholders}) AND level >= 2",
            routed_domain_ids,
        ).fetchall()
        for n in routed_nodes:
            if n['id'] in seen_node_ids:
                continue
            candidate_nodes.append({
                'node_id': n['id'],
                'domain_id': n['domain_id'],
                'title': n['title'],
                'description': (n['description'] or '')[:200],
                'priority': 'routed',
            })
            seen_node_ids.add(n['id'])

    # Phase 3: If still very few nodes, expand only the primary domain
    # (the one with the most direct links — avoids dumping 70 Ancient Greece
    # nodes when the transcript is about medieval Sicily)
    if len(candidate_nodes) < 10 and directly_linked_node_ids:
        # Find which domain has the most direct links
        domain_counts = {}
        for n in candidate_nodes:
            if n.get('priority') == 'direct':
                domain_counts[n['domain_id']] = domain_counts.get(n['domain_id'], 0) + 1
        if domain_counts:
            primary_domain = max(domain_counts, key=domain_counts.get)
            nodes = conn.execute(
                'SELECT id, title, description FROM curriculum_nodes WHERE domain_id = ? AND level >= 2',
                (primary_domain,)
            ).fetchall()
            for n in nodes:
                if n['id'] not in seen_node_ids:
                    candidate_nodes.append({
                        'node_id': n['id'],
                        'domain_id': primary_domain,
                        'title': n['title'],
                        'description': (n['description'] or '')[:200],
                        'priority': 'domain',
                    })
                    seen_node_ids.add(n['id'])

    # Phase 4: Last resort — scan all nodes for title keyword matches
    if not candidate_nodes:
        all_nodes = conn.execute(
            'SELECT id, domain_id, title, description FROM curriculum_nodes WHERE level >= 2'
        ).fetchall()
        for n in all_nodes:
            title_words = set(w.lower() for w in re.split(r'\W+', n['title']) if len(w) > 3)
            if title_words & transcript_words:
                candidate_nodes.append({
                    'node_id': n['id'],
                    'domain_id': n['domain_id'],
                    'title': n['title'],
                    'description': (n['description'] or '')[:200],
                    'priority': 'keyword',
                })
                candidate_domains.add(n['domain_id'])

    conn.close()

    if not candidate_nodes:
        print(f'[voice-capture] No candidate nodes — routing to entity path', flush=True)
        return _process_voice_capture_entity_path(
            transcript=transcript,
            entity_id=entity_id,
            entity_name=entity_name,
            detected_entity_ids=detected_entity_ids,
            sync=sync,
            input_mode=input_mode,
        )

    # Sort: direct links first, then siblings by overlap, then domain fillers
    priority_order = {'direct': 0, 'sibling': 1, 'routed': 2, 'domain': 3, 'keyword': 4}
    candidate_nodes.sort(key=lambda n: (priority_order.get(n.get('priority', 'keyword'), 3),
                                         -n.get('overlap', 0)))

    by_priority = {}
    for n in candidate_nodes:
        p = n.get('priority', '?')
        by_priority[p] = by_priority.get(p, 0) + 1
    print(f'[voice-capture] Found {len(candidate_nodes)} candidate nodes across {len(candidate_domains)} domains '
          f'(breakdown: {by_priority})', flush=True)

    # --- Insight mode: save transcript + node links, skip all LLM/processing ---
    if capture_type == 'insight':
        # Build entity_id → name lookup for matched entities (for title matching below)
        matched_entity_names: dict[str, str] = {}
        if detected_entity_ids:
            scoring_conn = get_connection(readonly=True)
            unique_eids = list(set(detected_entity_ids))
            placeholders = ','.join('?' * len(unique_eids))
            ent_rows = scoring_conn.execute(
                f'SELECT entity_id, name FROM shared_entities WHERE entity_id IN ({placeholders})',
                unique_eids
            ).fetchall()
            matched_entity_names = {r['entity_id']: r['name'] for r in ent_rows}
            # Get link counts and per-entity links
            link_rows = scoring_conn.execute(
                f'SELECT entity_id, node_id FROM entity_curriculum_links WHERE entity_id IN ({placeholders})',
                unique_eids
            ).fetchall()
            scoring_conn.close()
        else:
            link_rows = []

        # Score 1: TF-IDF specificity, scaled by entity name length.
        # - 1/N down-weights generic entities (Latin → 50 nodes vs Frederick II → 2 nodes)
        # - Length-scaling distinguishes "Latin" (5 chars, often mentioned in passing)
        #   from proper-noun entities like "Frederick II" (12 chars, usually a topic word).
        # Both factors needed: Latin (5 chars, 1 link) shouldn't outrank Frederick II
        # (12 chars, 2 links) just because Latin happens to link to only 1 node.
        entity_total_links: dict[str, int] = {}
        for r in link_rows:
            entity_total_links[r['entity_id']] = entity_total_links.get(r['entity_id'], 0) + 1

        def _entity_weight(eid: str) -> float:
            ename = matched_entity_names.get(eid, '')
            length_factor = max(0.5, min(2.0, len(ename) / 10.0))  # 5-char → 0.5, 20-char → 2.0
            return (1.0 / max(1, entity_total_links.get(eid, 1))) * length_factor

        node_specificity: dict[str, float] = {}
        node_linked_entities: dict[str, list[str]] = {}
        for r in link_rows:
            node_specificity[r['node_id']] = node_specificity.get(r['node_id'], 0.0) + _entity_weight(r['entity_id'])
            node_linked_entities.setdefault(r['node_id'], []).append(r['entity_id'])

        # Score 2: title-entity match — node title contains a matched entity name.
        # Boost scales with entity specificity: "Frederick II Stupor Mundi" containing
        # "Frederick II" (rare entity) > "Latin and the Romance Languages" containing
        # "Latin" (common short word).
        def _title_entity_boost(title: str) -> float:
            title_lower = title.lower()
            boost = 0.0
            for eid, ename in matched_entity_names.items():
                if len(ename) >= 5 and ename.lower() in title_lower:
                    boost += (2.0 + len(ename) * 0.05) * _entity_weight(eid)
            return boost

        # Score 3: position bonus — entities mentioned in the first sentence/200 chars
        # are most likely the topic of the recording. "I listened to a podcast about
        # Frederick II" puts Frederick II at position 0, while "personally Christian"
        # appears 800 chars in. The opening positioning of an entity is a strong topic
        # signal that distinguishes "central topic" from "mentioned in passing".
        head = transcript_lower[:200]

        def _entity_position_bonus(eid: str) -> float:
            ename = matched_entity_names.get(eid, '').lower()
            if not ename:
                return 0.0
            # Full entity name in head → strong signal
            if len(ename) >= 5 and ename in head:
                return 4.0
            # Or any distinctive (non-stop, ≥5 char) word from the entity name in head
            for w in re.split(r'\W+', ename):
                if len(w) >= 5 and w not in _STOP_WORDS_FOR_MATCHING and w in head:
                    return 3.0
            return 0.0

        # Cache per-entity position bonus
        entity_pos_bonus: dict[str, float] = {
            eid: _entity_position_bonus(eid) for eid in matched_entity_names
        }

        def _composite_score(node) -> float:
            base = node_specificity.get(node['node_id'], 0.0)
            title = _title_entity_boost(node['title'])
            # Position bonus: max over entities linking to this node
            pos = max(
                (entity_pos_bonus.get(eid, 0.0)
                 for eid in node_linked_entities.get(node['node_id'], [])),
                default=0.0,
            )
            return base + title + pos

        # Sort direct-priority nodes by composite score
        direct_candidates = [n for n in candidate_nodes if n.get('priority') == 'direct']
        direct_candidates.sort(key=lambda n: -_composite_score(n))
        non_direct = [n for n in candidate_nodes if n.get('priority') != 'direct']
        ordered_candidates = direct_candidates + non_direct

        nodes_linked = [
            {'node_id': n['node_id'], 'domain_id': n['domain_id'],
             'title': n['title'], 'priority': n.get('priority', 'keyword'),
             'score': round(_composite_score(n), 3)}
            for n in ordered_candidates[:20]
        ]

        primary_node_obj = ordered_candidates[0] if ordered_candidates else None
        primary_node = primary_node_obj['node_id'] if primary_node_obj else None
        primary_domain = primary_node_obj['domain_id'] if primary_node_obj else None
        primary_title = primary_node_obj['title'] if primary_node_obj else (entity_name or 'general')

        entity_names = list({n['title'] for n in ordered_candidates[:5]
                             if n.get('priority') == 'direct'})

        _log_voice_transcript(
            source='insight',
            node_id=primary_node or entity_id or 'general',
            domain_id=primary_domain or '',
            node_title=primary_title,
            transcript=transcript,
            audio_bytes=0,
            llm_result={'nodes_linked': nodes_linked, 'capture_type': 'insight'},
            ml_triggered=[],
            input_mode=input_mode,
        )

        top_scored = [(n['node_id'], round(_composite_score(n), 2)) for n in direct_candidates[:5]]
        print(f'[voice-capture] Insight saved: primary={primary_node} ({primary_title}), '
              f'{len(nodes_linked)} nodes linked, top_scored={top_scored}', flush=True)
        return {
            'status': 'completed',
            'capture_type': 'insight',
            'transcript': transcript,
            'nodes_linked': nodes_linked,
            'entities_mentioned': entity_names or list(set(e for e in detected_entity_ids[:5])),
            'notes_saved': 1,
            'research_triggered': [],
            'microlearning_triggered': [],
        }

    # --- Build context section for prompt ---
    if entity_id and entity_name:
        context_section = f'CONTEXT: The learner is speaking about {entity_name}.'
    elif entity_name:
        context_section = f'CONTEXT: The learner appears to be discussing topics related to {entity_name}.'
    else:
        context_section = 'CONTEXT: The learner is sharing knowledge from a recent podcast, book, or personal study.'

    # Build nodes list (limit to 40 most relevant to avoid prompt bloat)
    nodes_for_prompt = candidate_nodes[:40]
    nodes_list = '\n'.join(
        f'- {n["node_id"]}: {n["title"]} — {n["description"]}'
        for n in nodes_for_prompt
    )

    # --- Run Claude analysis (slow — no DB lock held) ---
    prompt = VOICE_CAPTURE_ANALYSIS_PROMPT.format(
        context_section=context_section,
        nodes_list=nodes_list,
        transcript=transcript,
    )

    analysis = call_claude_json(prompt, timeout=180)
    if not isinstance(analysis, dict):
        print(f'[voice-capture] LLM returned non-dict: {repr(str(analysis)[:200])}', flush=True)
        analysis = {}

    facts = analysis.get('facts', [])
    node_assessments = analysis.get('node_assessments', [])
    wonderings = analysis.get('wonderings', [])
    entities_mentioned = analysis.get('entities_mentioned', [])

    print(f'[voice-capture] Analysis: {len(facts)} facts, {len(node_assessments)} nodes assessed, '
          f'{len(wonderings)} wonderings', flush=True)

    # --- DB writes: upsert knowledge_items, update knowledge states ---
    now_ms = int(time.time() * 1000)
    knowledge_updates = []
    items_created = 0
    items_updated = 0
    questions_queued = []

    # Build a lookup from node_id to domain_id
    node_domain_map = {n['node_id']: n['domain_id'] for n in candidate_nodes}

    max_write_attempts = 3
    for attempt in range(max_write_attempts):
        try:
            conn = get_connection()
            conn.execute('PRAGMA busy_timeout = 60000')

            for assessment in node_assessments:
                nid = assessment.get('node_id', '')
                did = node_domain_map.get(nid)
                if not nid or not did:
                    continue

                knowledge_level = assessment.get('knowledge_level', 'engaged')
                if knowledge_level not in ('mentioned', 'engaged', 'anchored'):
                    knowledge_level = 'engaged'

                confidence = min(1.0, (assessment.get('fact_count', 1) / 5.0) + 0.3)
                item_id = f'{did}:{nid}'

                # Gather facts for this node as source text
                node_facts = [f['fact'] for f in facts if nid in f.get('node_ids', [])]
                source_text = '; '.join(node_facts[:5]) if node_facts else assessment.get('summary', '')

                new_source = {
                    'source': 'voice_capture',
                    'entity_id': entity_id,
                    'entity_name': entity_name,
                    'source_text': source_text[:400],
                    'fact_count': len(node_facts),
                    'added_at': now_ms,
                }

                existing = conn.execute(
                    'SELECT id, sources FROM knowledge_items WHERE id = ?', (item_id,)
                ).fetchone()

                if existing:
                    try:
                        sources = json.loads(existing['sources'] or '[]')
                    except Exception:
                        sources = []
                    sources.append(new_source)
                    conn.execute(
                        'UPDATE knowledge_items SET sources = ?, cached_question = NULL WHERE id = ?',
                        (json.dumps(sources), item_id)
                    )
                    items_updated += 1
                else:
                    conn.execute('''
                        INSERT INTO knowledge_items
                        (id, curriculum_node_id, curriculum_domain, stability_days, due_at,
                         sources, question_history, created_at)
                        VALUES (?,?,?,?,?,?,?,?)
                    ''', (
                        item_id, nid, did,
                        INITIAL_STABILITY_DAYS, now_ms,
                        json.dumps([new_source]), '[]', now_ms,
                    ))
                    items_created += 1

                # Update knowledge state (only upgrades, per system rules)
                update_knowledge(did, nid, knowledge=knowledge_level,
                                 confidence=confidence, source='voice_capture', conn=conn)

                # Reschedule via FSRS (maps knowledge_level to score for FSRS rating)
                fsrs_score = {'anchored': 'knew', 'engaged': 'partly', 'mentioned': 'missed'}.get(knowledge_level, 'partly')
                _fsrs_reschedule(item_id, fsrs_score, conn)

                questions_queued.append(item_id)
                knowledge_updates.append({
                    'node_id': nid,
                    'domain_id': did,
                    'knowledge_level': knowledge_level,
                    'facts_captured': len(node_facts),
                })

            # Save entity notes (preserve existing behavior)
            if entity_id and facts:
                note_text = '\n'.join(f'• {f["fact"]}' for f in facts[:15])
                conn.execute(
                    'INSERT INTO entity_notes (entity_id, note, created_at) VALUES (?, ?, ?)',
                    (entity_id, note_text, now_ms))

            conn.commit()
            conn.close()
            break  # success
        except sqlite3.OperationalError as e:
            if 'locked' in str(e) and attempt < max_write_attempts - 1:
                print(f'[voice-capture] DB locked on write attempt {attempt + 1}, retrying...', flush=True)
                try:
                    conn.close()
                except Exception:
                    pass
                time.sleep(5 * (attempt + 1))
            else:
                print(f'[voice-capture] DB write failed: {e}', flush=True)
                try:
                    conn.close()
                except Exception:
                    pass
                break

    print(f'[voice-capture] Knowledge updates: {items_created} created, {items_updated} updated, '
          f'{len(knowledge_updates)} nodes touched', flush=True)

    # --- Pre-generate questions ---
    if questions_queued:
        def _pregen_questions():
            from db import get_connection as _gc
            c = _gc()
            generated = 0
            for iid in questions_queued:
                try:
                    row = c.execute('SELECT cached_question FROM knowledge_items WHERE id = ?', (iid,)).fetchone()
                    if row and not row['cached_question']:
                        q = generate_question(iid, c)
                        c.execute('UPDATE knowledge_items SET cached_question = ? WHERE id = ?',
                                  (json.dumps(q), iid))
                        c.commit()
                        generated += 1
                except Exception as e:
                    print(f'[voice-capture] pre-gen failed {iid}: {e}', flush=True)
            c.close()
            print(f'[voice-capture] Pre-generated {generated}/{len(questions_queued)} questions', flush=True)
        if sync:
            _pregen_questions()
        else:
            threading.Thread(target=_pregen_questions, daemon=True).start()

    # --- Trigger microlearning from wonderings ---
    ml_triggered = []
    primary_domain = next(iter(candidate_domains)) if candidate_domains else None
    primary_node = node_assessments[0]['node_id'] if node_assessments else None

    for w in _rank_wonderings(wonderings, top_k=5):
        try:
            card_id = create_microlearning_request(
                query=w,
                source_node_id=primary_node,
                source_domain=primary_domain,
            )
            ml_triggered.append({'id': card_id, 'query': w})
            print(f'[voice-capture→ml] wondering → {card_id}: {w[:60]}', flush=True)
        except Exception as e:
            print(f'[voice-capture→ml] failed: {e}', flush=True)

    # --- Fallback: when no nodes matched but the capture has real content,
    # route to the entity path. The curriculum LLM pass found no real match
    # (Gemini domain routing / keyword matching produced candidate nodes, but
    # the analysis LLM correctly rejected them). Entity path runs its own LLM
    # call with VOICE_CAPTURE_ENTITY_PROMPT to produce properly structured
    # question/answer facts grouped by entity. See entity-first architecture.
    entity_path_triggered = False
    if not node_assessments and (facts or entities_mentioned):
        print(f'[voice-capture] No node assessments despite {len(facts)} facts — '
              f'routing to entity path', flush=True)
        entity_result = _process_voice_capture_entity_path(
            transcript=transcript,
            entity_id=entity_id,
            entity_name=entity_name,
            detected_entity_ids=detected_entity_ids,
            sync=sync,
            input_mode=input_mode,
        )
        entity_path_triggered = True
        # Surface the entity-path outcome in the curriculum-path response
        # so the client sees entity items were created.
        result_addendum = {
            'entity_path_triggered': True,
            'entity_items_created': entity_result.get('entity_items_created', 0),
            'entity_items_updated': entity_result.get('entity_items_updated', 0),
            'knowledge_entities': entity_result.get('knowledge_entities', []),
        }
        ml_triggered.extend(entity_result.get('microlearning_triggered', []))

    # --- Log transcript ---
    vt_row = _log_voice_transcript(
        source='voice_capture',
        node_id=primary_node or entity_id or 'general',
        domain_id=primary_domain or '',
        node_title=entity_name or 'general',
        transcript=transcript,
        audio_bytes=0,
        llm_result={**analysis, 'knowledge_updates': knowledge_updates},
        ml_triggered=ml_triggered,
        input_mode=input_mode,
    )

    # --- Background: resolve entities to Wikidata QIDs ---
    # Skip when the entity path already fired its own resolution thread,
    # otherwise every mention is resolved twice (doubling API/LLM cost
    # and producing racing INSERTs on shared_entities). See
    # research/session-77-observations.md Bug 1.
    if entities_mentioned and not entity_path_triggered:
        capture_id = vt_row if isinstance(vt_row, str) else 'unknown'
        # Only pass assessed nodes for linking (not the full candidate list)
        assessed_node_map = {na.get('node_id', ''): node_domain_map.get(na.get('node_id', ''), '')
                             for na in node_assessments if na.get('node_id') in node_domain_map}
        threading.Thread(
            target=_resolve_voice_entities_background,
            args=(entities_mentioned, transcript, capture_id, assessed_node_map),
            daemon=True,
        ).start()

    result = {
        'status': 'completed',
        'transcript': transcript,
        'facts_extracted': len(facts),
        'nodes_assessed': len(node_assessments),
        'node_assessments': node_assessments,
        'knowledge_updates': knowledge_updates,
        'items_created': items_created,
        'items_updated': items_updated,
        'questions_queued': len(questions_queued),
        'wonderings': wonderings,
        'entities_mentioned': entities_mentioned,
        'microlearning_triggered': ml_triggered,
        'overall_summary': analysis.get('overall_summary', ''),
    }
    # Merge entity-path addendum if the fallback routed there
    try:
        result.update(result_addendum)
    except NameError:
        pass  # result_addendum only set when entity path was triggered

    # Check if multiple nodes from same era were touched with uncertain dates → timeline card
    if len(node_assessments) >= 2 and primary_domain:
        try:
            _curriculum = load_curriculum(primary_domain)
            if _curriculum:
                # Group assessed nodes by their L1 parent
                node_parents = {}
                for n in _curriculum['nodes']:
                    if n.get('level') == 2:
                        node_parents[n['id']] = n.get('parent_id', '')
                era_groups: dict[str, list] = {}
                for na in node_assessments:
                    parent = node_parents.get(na.get('node_id', ''), '')
                    if parent:
                        era_groups.setdefault(parent, []).append(na)
                # If 2+ nodes in same era, and any uncertain facts → timeline card
                uncertain = [ct for ct in analysis.get('confidence_tagged', [])
                             if isinstance(ct, dict) and ct.get('confidence') == 'uncertain']
                for era_id, era_nodes in era_groups.items():
                    if len(era_nodes) >= 2 and uncertain:
                        era_node = next((n for n in _curriculum['nodes'] if n['id'] == era_id), None)
                        if not era_node:
                            continue
                        children = [n for n in _curriculum['nodes']
                                    if n.get('parent_id') == era_id and n.get('level') == 2]
                        date_facts = []
                        _tconn = get_connection(readonly=True)
                        for ch in children:
                            kf_row = _tconn.execute(
                                'SELECT key_facts FROM curriculum_nodes WHERE id = ? AND domain_id = ?',
                                (ch['id'], primary_domain)
                            ).fetchone()
                            if kf_row and kf_row['key_facts']:
                                for f in json.loads(kf_row['key_facts']):
                                    if f.get('type') in ('date', 'event'):
                                        date_facts.append(f"{f['question']} -> {f['answer']}")
                        _tconn.close()
                        if date_facts:
                            tq = (
                                f"Timeline review for {era_node['title']}: Build the chronological scaffold. "
                                f"Key dates and events to sequence:\n" +
                                '\n'.join(f'- {df}' for df in date_facts[:8])
                            )
                            try:
                                create_microlearning_request(
                                    query=tq, source_node_id=era_id, source_domain=primary_domain,
                                    source_type='sweep_timeline',
                                )
                                print(f'[voice-capture] Created timeline ML for {era_node["title"]}', flush=True)
                            except Exception:
                                pass
                        break  # one timeline card per capture is enough
        except Exception as e:
            print(f'[voice-capture] Timeline card check failed: {e}', flush=True)

    print(f'[voice-capture] Done: {len(facts)} facts → {len(knowledge_updates)} nodes, '
          f'{len(ml_triggered)} ML cards', flush=True)
    return result


def _process_voice_capture_entity_path(
    transcript: str,
    entity_id: str | None,
    entity_name: str | None,
    detected_entity_ids: list,
    sync: bool = False,
    input_mode: str = 'audio',
) -> dict:
    """Process a voice capture via the entity-keyed path (no curriculum required).

    Called from process_voice_capture() when no curriculum nodes match. Creates/
    updates knowledge_entities rows with facts extracted from the transcript,
    schedules them via FSRS, triggers ML cards from wonderings, and fires the
    existing background Wikidata resolution thread.

    See research/entity-first-architecture.md.
    """
    from db import get_connection

    # Gather context for known entities (if any were detected by name matching)
    conn = get_connection(readonly=True)
    entity_context_lines = []
    known_entities = {}  # name → shared_entities row
    for eid in detected_entity_ids[:8]:
        row = conn.execute(
            '''SELECT entity_id, name, description, entity_type,
                      date_start, date_end, wikidata_qid
               FROM shared_entities WHERE entity_id=?''',
            (eid,)
        ).fetchone()
        if not row:
            continue
        known_entities[row['name']] = dict(row)
        desc = (row['description'] or '')[:150]
        dates = ''
        if row['date_start'] is not None:
            end = row['date_end'] if row['date_end'] is not None else row['date_start']
            dates = f" ({row['date_start']}–{end})"
        entity_context_lines.append(
            f"- {row['name']}{dates} [{row['entity_type'] or 'entity'}]: {desc}"
        )
    conn.close()

    if entity_id and entity_name:
        context_section = f'CONTEXT: The learner is speaking about {entity_name}.'
    elif entity_name:
        context_section = f'CONTEXT: The learner appears to be discussing {entity_name}.'
    else:
        context_section = 'CONTEXT: The learner is sharing knowledge from a podcast, book, or personal study. No curriculum structure exists yet for this topic.'

    entity_info = (
        'KNOWN ENTITIES (already in the knowledge base — use these names verbatim if they appear):\n'
        + '\n'.join(entity_context_lines)
    ) if entity_context_lines else 'KNOWN ENTITIES: (none yet — this is a new topic)'

    prompt = VOICE_CAPTURE_ENTITY_PROMPT.format(
        context_section=context_section,
        entity_info=entity_info,
        transcript=transcript,
    )

    analysis = call_claude_json(prompt, timeout=180)
    if not isinstance(analysis, dict):
        print(f'[voice-capture-entity] LLM returned non-dict: {repr(str(analysis)[:200])}', flush=True)
        analysis = {}

    entity_facts = analysis.get('entity_facts', {}) or {}
    entity_types = analysis.get('entity_types', {}) or {}
    wonderings = analysis.get('wonderings', []) or []
    entities_mentioned = analysis.get('entities_mentioned', []) or []
    confidence_tagged = analysis.get('confidence_tagged', []) or []
    overall_summary = analysis.get('overall_summary', '')

    print(
        f'[voice-capture-entity] Analysis: {sum(len(v) for v in entity_facts.values())} facts '
        f'across {len(entity_facts)} entities, {len(wonderings)} wonderings',
        flush=True,
    )

    # --- DB writes: create/update knowledge_entities rows ---
    now_ms = int(time.time() * 1000)
    vt_id = f'vt_{int(time.time())}_{hash(transcript) % 10000:04d}'
    items_created = 0
    items_updated = 0
    ke_ids_created: list[str] = []

    def _slugify(name: str) -> str:
        s = re.sub(r'\W+', '_', name.lower()).strip('_')
        return s or 'entity'

    max_write_attempts = 3
    for attempt in range(max_write_attempts):
        try:
            conn = get_connection()
            conn.execute('PRAGMA busy_timeout = 60000')

            for ent_name, facts in entity_facts.items():
                if not ent_name or not facts:
                    continue
                ent_name = ent_name.strip()
                slug = _slugify(ent_name)
                ke_id = f'ent:{slug}'

                # Normalize incoming facts to the key_facts schema
                normalized_facts = []
                for i, f in enumerate(facts):
                    if not isinstance(f, dict):
                        continue
                    q = (f.get('question') or '').strip()
                    a = (f.get('answer') or '').strip()
                    if not q or not a:
                        continue
                    normalized_facts.append({
                        'id': f.get('id') or f'vc_{int(time.time())}_{i}',
                        'question': q,
                        'answer': a,
                        'type': f.get('type') or 'event',
                        'source_excerpt': f.get('source_excerpt') or '',
                    })
                if not normalized_facts:
                    continue

                # Link to shared_entities if already known
                se = known_entities.get(ent_name)
                linked_entity_id = se.get('entity_id') if se else None
                linked_qid = se.get('wikidata_qid') if se else None
                # Prefer an already-known type from shared_entities; fall back
                # to the LLM's classification; last resort is the generic
                # 'entity' sentinel. See research/session-77-observations.md Gap B.
                ent_type = (
                    (se.get('entity_type') if se else None)
                    or entity_types.get(ent_name)
                    or 'entity'
                )

                new_source = {
                    'source': 'voice_capture',
                    'capture_id': vt_id,
                    'source_text': overall_summary[:400],
                    'added_at': now_ms,
                }

                existing = conn.execute(
                    'SELECT key_facts, sources FROM knowledge_entities WHERE id=?',
                    (ke_id,)
                ).fetchone()
                if existing:
                    try:
                        prior_facts = json.loads(existing['key_facts'] or '[]')
                    except (json.JSONDecodeError, TypeError):
                        prior_facts = []
                    try:
                        prior_sources = json.loads(existing['sources'] or '[]')
                    except (json.JSONDecodeError, TypeError):
                        prior_sources = []

                    # Dedup by question text (case-insensitive)
                    existing_qs = {
                        (pf.get('question') or '').lower().strip() for pf in prior_facts
                    }
                    merged_facts = list(prior_facts)
                    for nf in normalized_facts:
                        if nf['question'].lower().strip() not in existing_qs:
                            merged_facts.append(nf)
                            existing_qs.add(nf['question'].lower().strip())

                    conn.execute(
                        '''UPDATE knowledge_entities
                           SET key_facts=?, sources=?, cached_question=NULL
                           WHERE id=?''',
                        (
                            json.dumps(merged_facts),
                            json.dumps(prior_sources + [new_source]),
                            ke_id,
                        ),
                    )
                    items_updated += 1
                    ke_ids_created.append(ke_id)
                else:
                    conn.execute(
                        '''INSERT INTO knowledge_entities
                           (id, entity_id, entity_name, entity_type, wikidata_qid,
                            key_facts, sources, stability_days, due_at, review_count,
                            created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 1.0, ?, 0, ?)''',
                        (
                            ke_id, linked_entity_id, ent_name, ent_type, linked_qid,
                            json.dumps(normalized_facts),
                            json.dumps([new_source]),
                            now_ms, now_ms,
                        ),
                    )
                    items_created += 1
                    ke_ids_created.append(ke_id)

            conn.commit()
            conn.close()
            break
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < max_write_attempts - 1:
                wait = 5 * (attempt + 1)
                print(f'[voice-capture-entity] DB locked, retry in {wait}s', flush=True)
                time.sleep(wait)
                continue
            raise

    # --- Pre-generate cached questions in the background ---
    # Follows the CLAUDE.md write-lock discipline: read → close → slow Claude
    # work → open → write. Never hold a connection during the LLM call, and
    # never share a conn across entities (ML research threads are also writing).
    if ke_ids_created:
        def _pregen_entity_questions():
            from db import get_connection as _gc

            def _try_one(kid: str) -> str:
                # Returns 'ok' on success, 'skip' if already cached, 'empty' if
                # LLM returned nothing (retriable — 429s and transient failures
                # land here), 'error' on exception (also retriable).
                try:
                    c = _gc(readonly=True)
                    row = c.execute(
                        'SELECT cached_question FROM knowledge_entities WHERE id=?',
                        (kid,),
                    ).fetchone()
                    c.close()
                    if not row or row['cached_question']:
                        return 'skip'

                    rc = _gc(readonly=True)
                    try:
                        q = generate_entity_question(kid, rc)
                    finally:
                        rc.close()
                    if not q:
                        return 'empty'

                    wc = _gc()
                    try:
                        wc.execute(
                            'UPDATE knowledge_entities SET cached_question=? WHERE id=?',
                            (json.dumps(q), kid),
                        )
                        wc.commit()
                    finally:
                        wc.close()
                    return 'ok'
                except Exception as e:
                    print(f'[voice-capture-entity] pre-gen failed {kid}: {e}', flush=True)
                    return 'error'

            generated = 0
            failed_kids: list[str] = []
            for kid in ke_ids_created:
                outcome = _try_one(kid)
                if outcome == 'ok':
                    generated += 1
                elif outcome == 'empty':
                    print(
                        f'[voice-capture-entity] pre-gen empty for {kid} — '
                        f'LLM returned None, queuing retry', flush=True)
                    failed_kids.append(kid)
                elif outcome == 'error':
                    failed_kids.append(kid)

            # Retry once after a 60s cooldown. The prior Iran Revolution capture
            # (Session 87) had Khomeini stuck at cached_question=NULL because a
            # Gemini 429 at 15:01:43 silently dropped the entity; waiting out
            # the per-minute quota window almost always recovers.
            if failed_kids:
                print(
                    f'[voice-capture-entity] sleeping 60s before retrying '
                    f'{len(failed_kids)} failed kid(s)', flush=True)
                time.sleep(60)
                recovered = 0
                for kid in failed_kids:
                    if _try_one(kid) == 'ok':
                        generated += 1
                        recovered += 1
                        print(f'[voice-capture-entity] retry recovered {kid}', flush=True)
                    else:
                        print(f'[voice-capture-entity] retry still failing {kid}', flush=True)
                print(
                    f'[voice-capture-entity] retry: {recovered}/{len(failed_kids)} recovered',
                    flush=True)

            print(
                f'[voice-capture-entity] Pre-generated {generated}/{len(ke_ids_created)} questions',
                flush=True,
            )

        if sync:
            _pregen_entity_questions()
        else:
            threading.Thread(target=_pregen_entity_questions, daemon=True).start()

    # --- Trigger ML cards from wonderings (entity-tagged, no curriculum domain) ---
    ml_triggered = []
    primary_entity_slug = ke_ids_created[0].split(':', 1)[1] if ke_ids_created else None
    for w in _rank_wonderings(wonderings, top_k=5):
        try:
            card_id = create_microlearning_request(
                query=w,
                source_node_id=primary_entity_slug,
                source_domain=None,
                source_type='voice_wondering',
            )
            ml_triggered.append({'id': card_id, 'query': w})
            print(f'[voice-capture-entity→ml] wondering → {card_id}: {w[:60]}', flush=True)
        except Exception as e:
            print(f'[voice-capture-entity→ml] failed: {e}', flush=True)

    # --- Log the transcript ---
    llm_result = {
        'entity_facts': entity_facts,
        'entity_types': entity_types,
        'wonderings': wonderings,
        'entities_mentioned': entities_mentioned,
        'confidence_tagged': confidence_tagged,
        'overall_summary': overall_summary,
        'knowledge_entities_created': items_created,
        'knowledge_entities_updated': items_updated,
    }
    # Prefer the LLM's primary entity over whatever loose name match the
    # curriculum-path carried in — otherwise the transcript row shows
    # unrelated curriculum titles (e.g. "1693 Earthquake" for a Karl XII
    # capture). See research/session-77-observations.md Bug 2.
    primary_entity_name = next(iter(entity_facts.keys()), None) if entity_facts else None
    _log_voice_transcript(
        source='voice_capture_entity',
        node_id=primary_entity_slug or 'entity',
        domain_id='',
        node_title=primary_entity_name or entity_name or 'voice capture',
        transcript=transcript,
        audio_bytes=0,
        llm_result=llm_result,
        ml_triggered=ml_triggered,
        vt_id=vt_id,
        input_mode=input_mode,
    )

    # --- Background Wikidata resolution for mentioned entities ---
    if entities_mentioned:
        threading.Thread(
            target=_resolve_voice_entities_background,
            args=(entities_mentioned, transcript, vt_id, {}),
            daemon=True,
        ).start()

    return {
        'status': 'completed',
        'transcript': transcript,
        'path': 'entity',
        'entity_items_created': items_created,
        'entity_items_updated': items_updated,
        'knowledge_entities': ke_ids_created,
        'wonderings': wonderings,
        'entities_mentioned': entities_mentioned,
        'microlearning_triggered': ml_triggered,
        'overall_summary': overall_summary,
    }


def _resolve_voice_entities_background(entities_mentioned: list, transcript: str,
                                       capture_id: str, node_domain_map: dict) -> None:
    """Background: resolve entity mentions to Wikidata QIDs and backfill shared_entities.

    Runs in a daemon thread after the main voice capture response is sent.
    Creates/updates shared_entities rows and writes entity_resolutions audit trail.
    """
    from db import get_connection
    if not entities_mentioned:
        return

    try:
        from gemini_llm import call_llm
        from limbic.amygdala.embed import EmbeddingModel
        from limbic.amygdala.temporal import DateRange
        from limbic.amygdala.wikidata import WikidataClient
        from limbic.hippocampus.wikidata_resolve import WikidataResolver, validate_chosen_qid
    except ImportError as e:
        print(f'[voice-entity-resolve] limbic not available: {e}', flush=True)
        return

    print(f'[voice-entity-resolve] Starting resolution for {len(entities_mentioned)} entities', flush=True)

    # Step 1: Extract structured mentions with type/date hints via Gemini
    entity_list = ', '.join(str(e) for e in entities_mentioned[:25])
    extract_prompt = (
        f"For each entity, provide the type and approximate date range.\n\n"
        f"Entities: {entity_list}\n\n"
        f"Transcript context:\n{transcript[:2000]}\n\n"
        f'Return JSON: {{"mentions": [{{"mention": "...", "type": "person|place|event|work|concept|other", '
        f'"date_start": year_or_null, "date_end": year_or_null}}]}}'
    )
    raw = call_llm(extract_prompt, max_tokens=2000, response_mime_type="application/json")
    if not raw:
        print('[voice-entity-resolve] Gemini extraction returned empty', flush=True)
        return
    try:
        mentions_data = json.loads(raw).get("mentions", [])
    except (json.JSONDecodeError, AttributeError):
        print('[voice-entity-resolve] Bad JSON from extraction', flush=True)
        return

    # Deduplicate and normalize
    seen = set()
    mentions = []
    for m in mentions_data:
        name = (m.get("mention") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        mentions.append(m)

    if not mentions:
        return

    # Step 2: Deterministic resolution with anchors
    client = WikidataClient(user_agent="Petrarca/0.1 (mailto:stian@haklev.com)")
    embedder = EmbeddingModel()
    resolver = WikidataResolver(client=client, embedder=embedder)

    # Load already-resolved QIDs as anchors
    conn = get_connection(readonly=True)
    existing_anchors = {}
    for row in conn.execute("SELECT entity_id, wikidata_qid FROM shared_entities WHERE wikidata_qid IS NOT NULL"):
        existing_anchors[row['entity_id']] = row['wikidata_qid']
    conn.close()

    anchors = dict(existing_anchors)
    resolutions: list[tuple[dict, object]] = []

    def _coerce_year(v) -> int | None:
        """Gemini occasionally returns years as strings ("1682") despite the
        prompt asking for raw integers. Coerce to int; None on anything that
        doesn't parse. Preserves negative years (BCE)."""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
            try:
                return int(float(v))
            except ValueError:
                return None
        return None

    for m in mentions:
        name = m.get("mention", "")
        s = _coerce_year(m.get("date_start"))
        e = _coerce_year(m.get("date_end"))
        date_hint = None
        if s is not None or e is not None:
            if s is None: s = e
            if e is None: e = s
            date_hint = DateRange(start=min(s, e), end=max(s, e))
        try:
            res = resolver.resolve(
                name,
                context_text=transcript[:800],
                type_hint=m.get("type"),
                date_hint=date_hint,
                already_resolved=anchors,
            )
        except Exception as exc:
            print(f'[voice-entity-resolve] resolve failed for {name!r}: {exc}', flush=True)
            resolutions.append((m, None))
            continue
        if res.status == "resolved":
            anchors[name] = res.chosen_qid
        resolutions.append((m, res))

    # Step 3: LLM disambiguation for ambiguous
    disambig_prompt_tpl = (
        "Disambiguate this entity mention to the correct Wikidata entity.\n\n"
        "MENTION: {mention}\nTYPE: {type_hint}\nDATE HINT: {date_hint}\n"
        "CONTEXT:\n{context}\n\nCANDIDATES:\n{candidates}\n\n"
        "Pick the QID that best matches. If none fit, return null.\n"
        'Return JSON: {{"chosen_qid": "Q123" or null, "confidence": 0.0-1.0, "reasoning": "brief"}}'
    )
    for i, (m, res) in enumerate(resolutions):
        if res is None or res.status != "ambiguous":
            continue
        candidates = res.candidates[:5]
        if not candidates:
            continue
        cand_block = "\n".join(
            f"{j+1}. {c.qid}: {c.label} — {(c.description or '')[:200]} [score {c.total:.2f}]"
            for j, c in enumerate(candidates)
        )
        prompt = disambig_prompt_tpl.format(
            mention=m.get("mention", ""),
            type_hint=m.get("type") or "(unknown)",
            date_hint=f"{m.get('date_start')}..{m.get('date_end')}"
            if (m.get("date_start") or m.get("date_end")) else "(none)",
            context=transcript[:500],
            candidates=cand_block,
        )
        answer_raw = call_llm(prompt, max_tokens=400, response_mime_type="application/json")
        if not answer_raw:
            continue
        try:
            answer = json.loads(answer_raw)
        except json.JSONDecodeError:
            continue
        chosen = answer.get("chosen_qid")
        if not chosen or not validate_chosen_qid(candidates, chosen):
            if chosen:
                print(f'[voice-entity-resolve] Hallucination guard: {m.get("mention")} → {chosen} rejected', flush=True)
            continue
        res.status = "resolved"
        res.chosen_qid = chosen
        res.confidence = float(answer.get("confidence") or 0.7)
        res.reasoning = f"LLM disambiguation: {answer.get('reasoning', '')}"
        anchors[m.get("mention", "")] = chosen

    # Step 4: Write results — audit trail + backfill shared_entities
    resolved_count = 0
    created_count = 0
    conn = get_connection()
    conn.execute('PRAGMA busy_timeout = 60000')

    for m, res in resolutions:
        if res is None:
            continue
        mention = m.get("mention", "")

        # Write audit row
        rid = f"er_{uuid.uuid4().hex[:12]}"
        cand_payload = [
            {"qid": c.qid, "label": c.label, "description": c.description,
             "total": c.total, "scores": c.scores, "rank": c.rank}
            for c in (res.candidates or [])[:10]
        ]
        conn.execute(
            """INSERT INTO entity_resolutions (
                id, entity_id, capture_id, mention_text, context_excerpt,
                type_hint, date_hint_start, date_hint_end, candidate_qids,
                chosen_qid, confidence, status, resolver_model, reasoning,
                cost_usd, created_at
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rid, f"voice:{capture_id}", mention,
                transcript[:500],
                m.get("type"),
                m.get("date_start"), m.get("date_end"),
                json.dumps(cand_payload),
                res.chosen_qid, res.confidence, res.status,
                "voice+gemini", res.reasoning or "", 0.0,
                int(time.time()),
            ),
        )

        if res.status != "resolved" or not res.chosen_qid:
            continue
        resolved_count += 1

        # Helper: after resolving/creating a shared_entities row, backfill
        # any matching knowledge_entities row (created by the entity capture
        # path before Wikidata resolution ran). This links entity items to
        # their canonical QID + entity_id for cross-capture merging.
        def _link_ke(resolved_entity_id: str, qid: str, mention_text: str):
            try:
                ke_slug = re.sub(r'\W+', '_', mention_text.lower()).strip('_')
                ke_id_candidate = f'ent:{ke_slug}'
                # Match by our slug OR by entity_name exact match
                conn.execute(
                    """UPDATE knowledge_entities
                       SET entity_id = COALESCE(entity_id, ?),
                           wikidata_qid = COALESCE(wikidata_qid, ?)
                       WHERE id = ? OR entity_name = ?""",
                    (resolved_entity_id, qid, ke_id_candidate, mention_text),
                )
            except Exception as _e:
                print(f'[voice-entity-resolve] KE link failed for {mention_text}: {_e}', flush=True)

        # Check if QID already exists in shared_entities
        existing = conn.execute(
            "SELECT entity_id FROM shared_entities WHERE wikidata_qid = ?",
            (res.chosen_qid,)
        ).fetchone()
        if existing:
            # Update audit row with the existing entity_id
            conn.execute("UPDATE entity_resolutions SET entity_id = ? WHERE id = ?",
                         (existing['entity_id'], rid))
            _link_ke(existing['entity_id'], res.chosen_qid, mention)
            continue

        # Check if there's an entity with same name but no QID
        name_slug = re.sub(r'\W+', '_', mention.lower()).strip('_')
        existing_by_name = conn.execute(
            "SELECT entity_id FROM shared_entities WHERE entity_id = ? AND wikidata_qid IS NULL",
            (name_slug,)
        ).fetchone()
        if existing_by_name:
            # Assign the QID to the existing entity
            conn.execute("UPDATE shared_entities SET wikidata_qid = ? WHERE entity_id = ?",
                         (res.chosen_qid, existing_by_name['entity_id']))
            conn.execute("UPDATE entity_resolutions SET entity_id = ? WHERE id = ?",
                         (existing_by_name['entity_id'], rid))
            print(f'[voice-entity-resolve] Assigned {res.chosen_qid} to existing entity {name_slug}', flush=True)
            _link_ke(existing_by_name['entity_id'], res.chosen_qid, mention)
            continue

        # Create new shared_entity
        chosen_cand = next((c for c in res.candidates if c.qid == res.chosen_qid), None)
        label = chosen_cand.label if chosen_cand else mention
        desc = (chosen_cand.description or "")[:500] if chosen_cand else ""
        entity_type = m.get("type") or "other"
        date_start = m.get("date_start")
        date_end = m.get("date_end")

        conn.execute(
            """INSERT OR IGNORE INTO shared_entities
            (entity_id, name, description, entity_type, date_start, date_end, wikidata_qid, nexus_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (name_slug, label, desc, entity_type, date_start, date_end, res.chosen_qid),
        )
        conn.execute("UPDATE entity_resolutions SET entity_id = ? WHERE id = ?",
                     (name_slug, rid))

        # Auto-link to curriculum nodes from the voice capture's node assessments
        for node_id, domain_id in node_domain_map.items():
            conn.execute(
                "INSERT OR IGNORE INTO entity_curriculum_links (entity_id, domain_id, node_id) VALUES (?, ?, ?)",
                (name_slug, domain_id, node_id),
            )
        _link_ke(name_slug, res.chosen_qid, mention)
        created_count += 1

    conn.commit()
    conn.close()
    print(f'[voice-entity-resolve] Done: {resolved_count} resolved, {created_count} new entities created '
          f'(of {len(mentions)} mentions)', flush=True)


def _gather_node_sources(node_id: str, domain_id: str, conn) -> str:
    """Gather all book source texts for a curriculum node."""
    rows = conn.execute("""
        SELECT sources FROM knowledge_items
        WHERE curriculum_node_id = ? AND curriculum_domain = ?
    """, (node_id, domain_id)).fetchall()

    parts = []
    for row in rows:
        try:
            sources = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            if isinstance(sources, list):
                for s in sources:
                    if isinstance(s, dict):
                        book_title = s.get('book_title', s.get('book_id', 'Unknown book'))
                        chapter = s.get('chapter_title', '')
                        text = s.get('source_text', '')
                        if text:
                            parts.append(f"From {book_title}" + (f", {chapter}" if chapter else "") + f": {text}")
        except (json.JSONDecodeError, TypeError):
            pass

    return '\n'.join(parts) if parts else ''


def _generate_temporal_hook(node: dict, domain_id: str, conn) -> str:
    """Generate a temporal hook by finding overlapping nodes in other curricula."""
    date_start = node.get('date_start')
    date_end = node.get('date_end')
    if date_start is None:
        return ''

    if date_end is None:
        date_end = date_start

    # Find nodes in OTHER curricula with overlapping dates where user has knowledge
    try:
        rows = conn.execute("""
            SELECT cn.title, cn.date_start, cn.date_end, cd.title as domain_title,
                   ks.knowledge, ks.confidence
            FROM curriculum_nodes cn
            JOIN curriculum_domains cd ON cn.domain_id = cd.id
            LEFT JOIN knowledge_states ks ON ks.node_id = cn.id AND ks.domain_id = cn.domain_id
            WHERE cn.domain_id != ?
              AND cn.date_start IS NOT NULL
              AND cn.date_start <= ? AND COALESCE(cn.date_end, cn.date_start) >= ?
              AND (ks.knowledge IN ('engaged', 'anchored') OR ks.confidence > 0.5)
            ORDER BY ks.confidence DESC
            LIMIT 3
        """, (domain_id, date_end + 50, date_start - 50)).fetchall()

        if rows:
            best = rows[0]
            return f"Contemporaneous with {best[0]} ({best[3]})"
    except Exception:
        pass

    return ''


def _elicitation_candidates_for_domain(domain_id: str, conn) -> list[dict]:
    """Get elicitation candidates for a single domain (internal helper).

    Excludes nodes with direct elicitations (voice_transcripts) and penalises
    nodes partially covered by cross-node transcript links (chunk_node_links)
    so that topics already discussed during adjacent elicitations are deprioritised.
    """
    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return []

    # Get domain title
    row = conn.execute('SELECT title FROM curriculum_domains WHERE id = ?', (domain_id,)).fetchone()
    domain_title = row['title'] if row else domain_id.replace('_', ' ').title()

    rows = conn.execute("""
        SELECT node_id, knowledge, confidence
        FROM knowledge_states
        WHERE domain_id = ?
    """, (domain_id,)).fetchall()

    states = {r[0]: {'knowledge': r[1], 'confidence': r[2]} for r in rows}

    # Exclude nodes that already have a voice transcript (elicitation is mapping, not drilling)
    recent_nodes = set()
    try:
        recent_rows = conn.execute(
            "SELECT node_id FROM voice_transcripts WHERE domain_id = ? AND source = 'elicitation'",
            (domain_id,)
        ).fetchall()
        recent_nodes = {r[0] for r in recent_rows}
    except Exception:
        pass  # table might not exist yet

    # Nodes partially covered by cross-node transcript links (spoke about in other elicitations)
    covered_nodes = set()
    try:
        covered_rows = conn.execute(
            "SELECT DISTINCT node_id FROM chunk_node_links WHERE domain_id = ?",
            (domain_id,)
        ).fetchall()
        covered_nodes = {r[0] for r in covered_rows} - recent_nodes  # exclude already-excluded
    except Exception:
        pass  # table might not exist yet

    candidates = []
    for node in curriculum.get('nodes', []):
        if node['level'] < 2:
            continue  # skip Area-level nodes
        state = states.get(node['id'], {})
        knowledge = state.get('knowledge', 'unknown')
        confidence = state.get('confidence', 0.0)

        if knowledge == 'unknown':
            continue  # nothing to recall
        if node['id'] in recent_nodes:
            continue  # already recalled recently

        # Score: prefer medium confidence (peak at 0.5)
        score = 1.0 - abs(confidence - 0.5) * 2  # peaks at 0.5
        if node['id'] in covered_nodes:
            score -= 0.5  # already partially covered by other elicitations
        if knowledge == 'engaged':
            score += 0.3  # bonus for engaged (most to gain)
        elif knowledge == 'mentioned':
            score += 0.1

        candidates.append({
            'node_id': node['id'],
            'node_title': node['title'],
            'node_description': node['description'],
            'domain_id': domain_id,
            'domain_title': domain_title,
            'knowledge': knowledge,
            'confidence': confidence,
            'elicitation_score': round(score, 2),
        })

    return candidates


def _era_sweep_candidates(conn, limit: int = 1) -> list[dict]:
    """Find eras due for a sweep — periodic broader recall tests.

    Picks eras that haven't been swept recently (>14 days) or never swept,
    from domains where the user has knowledge.
    """
    # Get domains with known nodes
    domain_rows = conn.execute("""
        SELECT DISTINCT domain_id FROM knowledge_states
        WHERE knowledge IN ('engaged', 'anchored')
    """).fetchall()

    candidates = []
    now = int(time.time())
    fourteen_days = 14 * 86400

    for dr in domain_rows:
        did = dr[0]
        curriculum = load_curriculum(did)
        if not curriculum:
            continue
        row = conn.execute('SELECT title FROM curriculum_domains WHERE id = ?', (did,)).fetchone()
        domain_title = row['title'] if row else did

        for node in curriculum['nodes']:
            if node.get('level') != 1:
                continue
            children = [n for n in curriculum['nodes']
                        if n.get('parent_id') == node['id'] and n.get('level') == 2]
            if not children:
                continue

            # Check if any children have knowledge (don't sweep unknown eras)
            has_knowledge = False
            for ch in children:
                ks = conn.execute(
                    'SELECT knowledge FROM knowledge_states WHERE domain_id = ? AND node_id = ?',
                    (did, ch['id'])
                ).fetchone()
                if ks and ks['knowledge'] in ('engaged', 'anchored', 'mentioned'):
                    has_knowledge = True
                    break
            if not has_knowledge:
                continue

            # Check last sweep for this era
            last_sweep = conn.execute(
                "SELECT created_at FROM knowledge_sweeps WHERE domain_id = ? AND "
                "(scoring_result LIKE ? OR id LIKE ?) ORDER BY created_at DESC LIMIT 1",
                (did, f'%{node["id"]}%', f'%{node["id"]}%')
            ).fetchone()

            if last_sweep and (now - last_sweep['created_at']) < fourteen_days:
                continue  # swept recently

            age_days = (now - last_sweep['created_at']) / 86400 if last_sweep else 999
            candidates.append({
                'type': 'era_sweep',
                'node_id': f'sweep:{node["id"]}',
                'node_title': f'Sweep: {node["title"]}',
                'node_description': f'What do you remember about {node["title"]}? Key events, people, and turning points.',
                'domain_id': did,
                'domain_title': domain_title,
                'knowledge': 'engaged',
                'confidence': 0.5,
                'elicitation_score': min(2.0, age_days / 14),  # higher = more overdue
                'era_id': node['id'],
                'child_count': len(children),
            })

    # Sort by most overdue first
    candidates.sort(key=lambda c: c['elicitation_score'], reverse=True)
    return candidates[:limit]


def get_elicitation_candidates(domain_id: str | None = None, limit: int = 8, conn=None) -> list[dict]:
    """Get curriculum nodes suitable for voice elicitation.

    Prioritizes: medium-confidence nodes (engaged, 0.3-0.7) where voice recall
    would be most informative. Avoids unknown (nothing to recall) and anchored
    (already well-known).

    If domain_id is None, returns candidates from ALL domains where the user
    has engaged/anchored nodes, merged and sorted by elicitation_score.
    """
    own = conn is None
    if own:
        from db import get_connection
        conn = get_connection(readonly=True)

    try:
        if domain_id:
            candidates = _elicitation_candidates_for_domain(domain_id, conn)
        else:
            # Find all domains with engaged/anchored nodes
            domain_rows = conn.execute("""
                SELECT DISTINCT domain_id FROM knowledge_states
                WHERE knowledge IN ('engaged', 'anchored', 'mentioned')
            """).fetchall()
            candidates = []
            for row in domain_rows:
                candidates.extend(_elicitation_candidates_for_domain(row[0], conn))

        # Add era sweep candidates — periodic broader recall tests
        era_sweeps = _era_sweep_candidates(conn, limit=1)

        # Add chapter recall candidates — "What do you remember from Chapter X?"
        chapter_recalls = _chapter_recall_candidates(conn, limit=2)

        # Interleave domains for variety (don't let one domain dominate)
        from collections import defaultdict
        domain_groups: dict[str, list] = defaultdict(list)
        for c in candidates:
            domain_groups[c['domain_id']].append(c)
        for g in domain_groups.values():
            g.sort(key=lambda c: c['elicitation_score'], reverse=True)

        interleaved = []
        sorted_domains = sorted(domain_groups.keys(),
                                key=lambda d: len(domain_groups[d]), reverse=True)
        idx = 0
        while len(interleaved) < len(candidates):
            added = False
            for d in sorted_domains:
                if idx < len(domain_groups[d]):
                    interleaved.append(domain_groups[d][idx])
                    added = True
            if not added:
                break
            idx += 1

        # Mix in chapter recalls (max 2, interspersed) and era sweeps
        result = []
        # Put era sweep early (position 2) so it appears but not first
        if era_sweeps:
            result.append(era_sweeps[0])
        ch_idx = 0
        for i, c in enumerate(interleaved):
            if i > 0 and i % 3 == 0 and ch_idx < len(chapter_recalls):
                result.append(chapter_recalls[ch_idx])
                ch_idx += 1
            result.append(c)
        while ch_idx < len(chapter_recalls):
            result.append(chapter_recalls[ch_idx])
            ch_idx += 1

        return result[:limit]
    finally:
        if own:
            conn.close()


def _chapter_recall_candidates(conn, limit: int = 2) -> list[dict]:
    """Generate chapter-specific recall prompts from knowledge_items sources.

    Finds recent book chapters that have curriculum mappings and creates
    prompts like "What do you remember from Chapter 5: The Founding of Syracuse?"
    """
    # Find distinct book+chapter combos from knowledge_items sources
    # Note: don't use json_extract in JOINs — unreliable with varying JSON structures.
    # Look up book titles in Python instead (same pattern as get_review_queue).
    rows = conn.execute("""
        SELECT ki.curriculum_domain, ki.sources
        FROM knowledge_items ki
        WHERE ki.sources LIKE '%chapter_number%'
          AND ki.review_count <= 1
        ORDER BY ki.created_at DESC
        LIMIT 50
    """).fetchall()

    # Build book title cache
    book_titles: dict[str, str] = {}
    for r in rows:
        try:
            for s in json.loads(r['sources'] or '[]'):
                bid = s.get('book_id', '')
                if bid and bid not in book_titles:
                    bt_row = conn.execute('SELECT title FROM physical_books WHERE id = ?', (bid,)).fetchone()
                    book_titles[bid] = bt_row['title'] if bt_row else ''
        except Exception:
            pass

    # Exclude chapters already elicited
    already_elicited = set()
    try:
        elicited_rows = conn.execute(
            "SELECT node_id FROM voice_transcripts WHERE source = 'elicitation' AND node_id LIKE 'chapter:%'"
        ).fetchall()
        already_elicited = {r[0] for r in elicited_rows}
    except Exception:
        pass

    seen_chapters = set()
    candidates = []
    for r in rows:
        try:
            sources = json.loads(r['sources'])
        except Exception:
            continue
        for s in sources:
            ch_num = s.get('chapter_number')
            ch_title = s.get('chapter_title', '')
            book_id = s.get('book_id', '')
            if not ch_num or not ch_title:
                continue
            node_id = f'chapter:{book_id}:{ch_num}'
            key = f'{book_id}:{ch_num}'
            if key in seen_chapters or node_id in already_elicited:
                continue
            seen_chapters.add(key)

            book_title = book_titles.get(book_id, '') or book_id
            candidates.append({
                'type': 'chapter_recall',
                'node_id': f'chapter:{book_id}:{ch_num}',
                'node_title': f'Chapter {ch_num}: {ch_title}',
                'node_description': f'What do you remember from Chapter {ch_num} of {book_title}? '
                                   f'Speak freely about the key ideas, people, and events.',
                'domain_id': r['curriculum_domain'],
                'knowledge': 'engaged',
                'confidence': 0.5,
                'elicitation_score': 1.5,  # slightly above curriculum nodes
                'book_id': book_id,
                'book_title': book_title,
                'chapter_number': ch_num,
                'chapter_title': ch_title,
            })

            if len(candidates) >= limit:
                break
        if len(candidates) >= limit:
            break

    return candidates


# ── Article-read curriculum updates ──────────────────────────────────────────

def notify_article_read_curriculum(article_id: str, conn) -> dict:
    """When an article is read, update curriculum knowledge states for mapped nodes.

    Returns node_details with titles and domain info for client display.
    """
    rows = conn.execute("""
        SELECT acn.node_id, acn.domain_id, acn.node_title, acn.claim_count, acn.avg_similarity,
               cd.title AS domain_title
        FROM article_curriculum_nodes acn
        LEFT JOIN curriculum_domains cd ON cd.id = acn.domain_id
        WHERE acn.article_id = ?
    """, (article_id,)).fetchall()

    if not rows:
        return {'nodes_updated': 0, 'node_details': []}

    updated = 0
    nodes = []
    node_details = []
    for row in rows:
        node_id, domain_id = row['node_id'], row['domain_id']
        claim_count, avg_sim = row['claim_count'], row['avg_similarity']
        # Only update if the mapping is strong enough
        if claim_count >= 2 or avg_sim >= 0.70:
            current = conn.execute(
                "SELECT knowledge, confidence FROM knowledge_states WHERE node_id = ? AND domain_id = ?",
                (node_id, domain_id)
            ).fetchone()

            if current is None or current['knowledge'] == 'unknown':
                update_knowledge(domain_id, node_id, knowledge='mentioned',
                                 confidence=0.2, source=f'article:{article_id}')
                updated += 1
                nodes.append(node_id)
                node_details.append({
                    'node_id': node_id,
                    'node_title': row['node_title'] or node_id.replace('_', ' ').title(),
                    'domain_id': domain_id,
                    'domain_title': row['domain_title'] or domain_id,
                })
            elif current['knowledge'] == 'mentioned':
                # Bump confidence slightly for additional article encounters
                new_conf = min(0.5, (current['confidence'] or 0.2) + 0.05)
                update_knowledge(domain_id, node_id, knowledge='mentioned',
                                 confidence=new_conf, source=f'article:{article_id}')
                updated += 1
                nodes.append(node_id)
                node_details.append({
                    'node_id': node_id,
                    'node_title': row['node_title'] or node_id.replace('_', ' ').title(),
                    'domain_id': domain_id,
                    'domain_title': row['domain_title'] or domain_id,
                })

    return {'nodes_updated': updated, 'nodes': nodes, 'node_details': node_details}


# ── Hamarquizen sessions ─────────────────────────────────────────────────────

def generate_hamarquizen_session(book_id: str, limit: int = 5, conn=None) -> list[dict]:
    """Generate Hamarquizen PRIME->READ->TEST cards for a finished book."""
    own = conn is None
    if own:
        from db import get_connection
        conn = get_connection(readonly=True)

    try:
        row = conn.execute(
            'SELECT title, author, topics FROM physical_books WHERE id=?', (book_id,)
        ).fetchone()
        if not row:
            return []

        book_title = row['title']
        book_author = row['author'] or ''

        # Find knowledge_items linked to this book, ordered by lowest confidence first
        items = conn.execute("""
            SELECT ki.id, ki.curriculum_node_id, ki.curriculum_domain,
                   ki.sources, ki.review_count, ki.stability_days,
                   ks.knowledge, ks.confidence
            FROM knowledge_items ki
            LEFT JOIN knowledge_states ks
              ON ks.node_id = ki.curriculum_node_id AND ks.domain_id = ki.curriculum_domain
            WHERE ki.sources LIKE ?
            ORDER BY COALESCE(ks.confidence, 0.5) ASC, ki.review_count ASC
            LIMIT ?
        """, (f'%{book_id}%', limit * 3)).fetchall()

        if not items:
            return []

        cards = []
        curriculum_cache: dict = {}

        for item_row in items:
            if len(cards) >= limit:
                break

            item_id = item_row['id']
            node_id = item_row['curriculum_node_id']
            domain_id = item_row['curriculum_domain']
            sources_raw = item_row['sources']
            knowledge = item_row['knowledge'] or 'unknown'
            confidence = item_row['confidence'] or 0.0

            # Get source text for this node from this book
            source_text = ''
            try:
                sources = json.loads(sources_raw) if isinstance(sources_raw, str) else sources_raw
                if isinstance(sources, list):
                    for s in sources:
                        if isinstance(s, dict) and s.get('book_id') == book_id:
                            source_text = s.get('source_text', '')
                            break
            except (json.JSONDecodeError, TypeError):
                pass

            # Load curriculum and find node description
            if domain_id not in curriculum_cache:
                curriculum_cache[domain_id] = load_curriculum(domain_id)
            curriculum = curriculum_cache[domain_id]

            node_title = node_id
            node_desc = ''
            if curriculum:
                for n in curriculum.get('nodes', []):
                    if n['id'] == node_id:
                        node_title = n.get('title', node_id)
                        node_desc = n.get('description', '')
                        break

            prompt = HAMARQUIZEN_PROMPT.format(
                book_title=book_title,
                book_author=book_author or 'Unknown',
                node_title=node_title,
                node_description=node_desc,
                source_text=source_text or 'No specific source text available',
                knowledge_level=knowledge,
                confidence=confidence,
            )

            card_data = call_claude_json(prompt, timeout=120)
            if not isinstance(card_data, dict):
                card_data = {}

            if card_data.get('test'):
                cards.append({
                    'item_id': item_id,
                    'node_id': node_id,
                    'domain_id': domain_id,
                    'node_title': node_title,
                    'book_id': book_id,
                    'book_title': book_title,
                    'prime': card_data.get('prime', ''),
                    'read': card_data.get('read', ''),
                    'test': card_data.get('test', ''),
                    'answer': card_data.get('answer', ''),
                    'temporal_hook': card_data.get('temporal_hook', ''),
                    'knowledge': knowledge,
                    'confidence': confidence,
                })

        return cards
    finally:
        if own:
            conn.close()


CROSS_BOOK_HAMARQUIZEN_PROMPT = """Generate a cross-book comparison micro-lesson.

Two books cover the same historical topic from different angles:

Topic: {node_title}
Definition: {node_description}

Book A: "{book_a_title}" — {source_a}
Book B: "{book_b_title}" — {source_b}

Create a PRIME->READ->TEST sequence that COMPARES the two perspectives:

1. PRIME: "What do you remember about [topic] from your reading?" (8-15 words)

2. READ: 3-4 sentences that juxtapose the two books' treatments. What does Book A emphasize that Book B doesn't? What's the same event seen from two angles? Include specific names, dates, details from both. Make the comparison vivid — this is not a summary, it's a dialogue between two authors.

3. TEST: A question (6-12 words) that requires understanding BOTH perspectives. "Why might [Author A] and [Author B] emphasize different aspects of [event]?" or "What does the contrast between [X] and [Y] reveal about [topic]?"

4. ANSWER: 2 sentences explaining the comparative insight.

5. TEMPORAL_HOOK: One cross-period anchor.

Output JSON:
{{"prime":"...","read":"...","test":"...","answer":"...","temporal_hook":"..."}}"""


def generate_cross_book_hamarquizen(limit: int = 5, conn=None) -> list[dict]:
    """Generate cross-book comparison Hamarquizen cards for curriculum nodes covered by 2+ books."""
    own = conn is None
    if own:
        from db import get_connection
        conn = get_connection(readonly=True)

    try:
        # Find curriculum nodes with knowledge_items sourced from 2+ different books
        rows = conn.execute("""
            SELECT ki.curriculum_node_id, ki.curriculum_domain, ki.sources, ki.id AS item_id
            FROM knowledge_items ki
            WHERE ki.sources IS NOT NULL AND ki.sources != '[]'
        """).fetchall()

        # Group by node, collect distinct book sources
        from collections import defaultdict
        node_books: dict[tuple[str, str], list[dict]] = defaultdict(list)
        node_item_ids: dict[tuple[str, str], str] = {}

        for row in rows:
            node_id = row['curriculum_node_id']
            domain_id = row['curriculum_domain']
            item_id = row['item_id']
            key = (domain_id, node_id)
            node_item_ids[key] = item_id
            try:
                sources = json.loads(row['sources']) if isinstance(row['sources'], str) else row['sources']
                if isinstance(sources, list):
                    for s in sources:
                        if isinstance(s, dict) and s.get('book_id'):
                            node_books[key].append(s)
            except (json.JSONDecodeError, TypeError):
                pass

        # Filter to nodes with 2+ distinct books
        multi_book_nodes = []
        for key, sources in node_books.items():
            book_ids = list({s['book_id'] for s in sources})
            if len(book_ids) >= 2:
                multi_book_nodes.append((key, sources, book_ids))

        if not multi_book_nodes:
            return []

        # Load book titles
        all_book_ids = set()
        for _, _, bids in multi_book_nodes:
            all_book_ids.update(bids)

        book_titles = {}
        for bid in all_book_ids:
            brow = conn.execute('SELECT title FROM physical_books WHERE id=?', (bid,)).fetchone()
            if brow:
                book_titles[bid] = brow['title']

        # Build cards (limit * 3 attempts, stop at limit)
        cards = []
        curriculum_cache: dict = {}

        for (domain_id, node_id), sources, book_ids in multi_book_nodes[:limit * 3]:
            if len(cards) >= limit:
                break

            # Get node metadata
            if domain_id not in curriculum_cache:
                curriculum_cache[domain_id] = load_curriculum(domain_id)
            curriculum = curriculum_cache[domain_id]

            node_title = node_id
            node_desc = ''
            if curriculum:
                for n in curriculum.get('nodes', []):
                    if n['id'] == node_id:
                        node_title = n.get('title', node_id)
                        node_desc = n.get('description', '')
                        break

            # Pick first two distinct books
            book_a_id, book_b_id = book_ids[0], book_ids[1]
            source_a = ''
            source_b = ''
            for s in sources:
                if s.get('book_id') == book_a_id and not source_a:
                    source_a = s.get('source_text', '')
                elif s.get('book_id') == book_b_id and not source_b:
                    source_b = s.get('source_text', '')

            book_a_title = book_titles.get(book_a_id, book_a_id)
            book_b_title = book_titles.get(book_b_id, book_b_id)

            prompt = CROSS_BOOK_HAMARQUIZEN_PROMPT.format(
                node_title=node_title,
                node_description=node_desc,
                book_a_title=book_a_title,
                source_a=source_a or 'No specific source text available',
                book_b_title=book_b_title,
                source_b=source_b or 'No specific source text available',
            )

            card_data = call_claude_json(prompt, timeout=120)
            if not isinstance(card_data, dict):
                card_data = {}

            if card_data.get('test'):
                item_id = node_item_ids.get((domain_id, node_id), f'{domain_id}:{node_id}')
                cards.append({
                    'item_id': item_id,
                    'node_id': node_id,
                    'domain_id': domain_id,
                    'node_title': node_title,
                    'book_id': book_a_id,
                    'book_title': book_a_title,
                    'book_b_id': book_b_id,
                    'book_b_title': book_b_title,
                    'prime': card_data.get('prime', ''),
                    'read': card_data.get('read', ''),
                    'test': card_data.get('test', ''),
                    'answer': card_data.get('answer', ''),
                    'temporal_hook': card_data.get('temporal_hook', ''),
                    'knowledge': 'engaged',
                    'confidence': 0.5,
                })

        return cards
    finally:
        if own:
            conn.close()


# ── Knowledge Sweeps ─────────────────────────────────────────────────────────

SWEEP_SCORING_PROMPT = """Score a knowledge sweep — a learner's free recall across an entire curriculum domain.

DOMAIN: {domain_title}

The learner was asked to recall what they know about each era/topic in this domain.
Below is their transcript (may cover multiple eras recorded sequentially).

TRANSCRIPT:
{transcript}

CURRICULUM NODES (Level 1 and 2 — the expected coverage for a sweep):
{nodes_with_facts}

For EACH Level 1/2 node in the curriculum:
1. Was it mentioned at all? (yes/no)
2. What specific facts were stated about it? For each fact:
   - The claim (brief)
   - Correct or incorrect?
   - Match to a key_fact ID if possible
   - Excerpt from transcript
3. What depth was demonstrated?
   - "surface": just named or referenced in passing
   - "textbase": recalled specific facts (dates, names, events)
   - "situation_model": showed causal reasoning, connections to other nodes, perspective-taking

For CONNECTIONS between nodes:
- List every pair of nodes the learner explicitly connected
- Type: causal ("X led to Y"), temporal ("at the same time as"), comparative ("unlike X, Y..."), cross_domain

For ORGANIZATION:
- Did the learner proceed chronologically? Thematically? Randomly?
- Count causal language ("because", "led to", "as a result", "which caused")
- Count perspective-taking and counterfactual statements

IMPORTANT scoring rules:
- Be generous with matching: paraphrases count, approximate dates count (±20 years for ancient, ±5 for modern)
- A vague reference ("the Greeks colonized Sicily") counts as surface mention of the relevant node
- Only mark "incorrect" for clear factual errors (wrong century, wrong attribution, events that didn't happen)
- If the learner conflates two nodes, credit both as mentioned

Output JSON:
{{
  "nodes": [
    {{
      "node_id": "exact_id",
      "node_title": "...",
      "mentioned": true,
      "depth": "surface|textbase|situation_model",
      "facts": [
        {{"claim": "...", "correct": true, "key_fact_id": "id_or_null", "excerpt": "..."}}
      ]
    }}
  ],
  "connections": [
    {{"from_node": "node_id", "to_node": "node_id", "type": "causal|temporal|comparative|cross_domain", "excerpt": "..."}}
  ],
  "organization": {{
    "pattern": "chronological|thematic|random|mixed",
    "causal_count": 5,
    "perspective_count": 1,
    "counterfactual_count": 0
  }},
  "errors": [
    {{"claim": "incorrect statement", "correction": "what actually happened", "node_id": "relevant_node"}}
  ],
  "strongest_area": "The era/topic where the learner showed deepest knowledge",
  "biggest_gap": "The most important era/topic the learner barely mentioned or missed entirely",
  "summary": "2-3 sentence assessment of the learner's overall knowledge structure"
}}"""


ERA_SWEEP_SCORING_PROMPT = """Score a learner's free recall about one era/topic of a curriculum.

ERA: {era_title}
DOMAIN: {domain_title}

The learner was asked to recall everything they know about this era.

TRANSCRIPT:
{transcript}

NODES UNDER THIS ERA (the expected coverage):
{nodes_with_facts}

For EACH node:
1. Was it mentioned? (yes/no)
2. Facts stated — for each: brief claim, correct or not, key_fact_id if matchable
3. Depth: surface | textbase | situation_model

CONNECTIONS between nodes:
- List node pairs the learner explicitly connected
- Type: causal | temporal | comparative | cross_domain

ERRORS: List factual mistakes with corrections.

Scoring rules: be generous — paraphrases count, approximate dates count. Only mark "incorrect" for clear errors.

Output JSON:
{{
  "nodes": [
    {{"node_id": "...", "node_title": "...", "mentioned": true, "depth": "surface|textbase|situation_model",
      "facts": [{{"claim": "...", "correct": true, "key_fact_id": null, "excerpt": "..."}}]}}
  ],
  "connections": [{{"from_node": "...", "to_node": "...", "type": "causal|temporal|comparative|cross_domain", "excerpt": "..."}}],
  "errors": [{{"claim": "...", "correction": "...", "node_id": "..."}}],
  "coverage_pct": 65,
  "suggested_score": "knew|partly|missed",
  "summary": "2-3 sentence assessment",
  "strongest_node": "node_id of the best-recalled topic",
  "biggest_gap": "most important thing the learner missed"
}}"""


def run_era_sweep(era_id: str, domain_id: str, transcript: str, conn=None) -> dict:
    """Score an era-level sweep and feed results back into the knowledge system.

    Returns a dict compatible with voice elicitation results (feedback_summary, etc.)
    so it slots into the existing UI flow.
    """
    from db import get_connection
    if conn is None:
        conn = get_connection(readonly=True)

    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return {'error': f'Curriculum {domain_id} not found'}

    # Find the era node and its L2 children
    era_node = None
    children = []
    for n in curriculum['nodes']:
        if n['id'] == era_id:
            era_node = n
        elif n.get('parent_id') == era_id and n.get('level') == 2:
            children.append(n)
    if not era_node:
        return {'error': f'Era {era_id} not found in curriculum'}

    # Build nodes+facts reference
    nodes_with_facts = []
    for node in children:
        kf_row = conn.execute(
            'SELECT key_facts FROM curriculum_nodes WHERE id = ? AND domain_id = ?',
            (node['id'], domain_id)
        ).fetchone()
        key_facts = []
        if kf_row and kf_row['key_facts']:
            try:
                key_facts = json.loads(kf_row['key_facts'])
            except Exception:
                pass
        facts_str = ''
        if key_facts:
            facts_list = [f"    - [{f['type']}] {f['id']}: {f['question']} → {f['answer']}"
                          for f in key_facts[:6]]
            facts_str = '\n'.join(facts_list)
        entry = f"- {node['id']}: {node['title']} [L{node.get('level', 2)}]\n  {node.get('description', '')}"
        if facts_str:
            entry += f"\n  Key facts:\n{facts_str}"
        nodes_with_facts.append(entry)

    conn.close()

    # ── LLM scoring (slow — no DB lock) ──
    prompt = ERA_SWEEP_SCORING_PROMPT.format(
        era_title=era_node['title'],
        domain_title=curriculum['title'],
        transcript=transcript,
        nodes_with_facts='\n'.join(nodes_with_facts),
    )
    print(f'[era-sweep] Scoring {era_id} ({len(transcript)} chars, {len(children)} nodes)...', flush=True)
    raw = _call_claude(prompt, timeout=180)
    if not raw:
        return {'error': 'LLM scoring failed'}
    result = _parse_json(raw)
    if not result:
        return {'error': 'LLM scoring failed — bad JSON', 'raw': raw[:300]}

    # ── Map results back to elicitation format for UI compatibility ──
    scored_nodes = result.get('nodes', [])
    mentioned = [n for n in scored_nodes if n.get('mentioned')]
    missed = [n for n in scored_nodes if not n.get('mentioned')]
    all_facts = []
    for n in scored_nodes:
        all_facts.extend(n.get('facts', []))

    coverage_pct = result.get('coverage_pct', int(100 * len(mentioned) / len(children)) if children else 0)
    score = result.get('suggested_score', 'partly')

    # Build captured/missed lists for UI compatibility
    captured = []
    for n in mentioned:
        for f in n.get('facts', []):
            if f.get('correct'):
                captured.append(f.get('claim', ''))
    missed_facts = []
    for n in missed:
        missed_facts.append(n.get('node_title', ''))

    elicit_result = {
        'coverage_pct': coverage_pct,
        'suggested_score': score,
        'captured': captured,
        'missed': missed_facts,
        'interesting': [],
        'wonderings': [],
        'research_questions': [],
        'entities_mentioned': [],
        'confidence_tagged': [
            {'fact': e.get('claim', ''), 'confidence': 'wrong'}
            for e in result.get('errors', [])
        ],
        'organizing_framework': result.get('connections', [{}])[0].get('type', 'chronological') if result.get('connections') else 'chronological',
        'adjacent_nodes_covered': [n['node_id'] for n in mentioned],
        'feedback_summary': result.get('summary', ''),
        'era_sweep_detail': result,  # full scoring detail for longitudinal tracking
        'is_era_sweep': True,
        'era_id': era_id,
        'era_title': era_node['title'],
        'nodes_mentioned': len(mentioned),
        'nodes_total': len(children),
    }

    # ── Feed back into knowledge system (write phase) ──
    wconn = get_connection()
    try:
        # Update knowledge states for mentioned nodes
        for n in mentioned:
            depth = n.get('depth', 'surface')
            level = 'anchored' if depth == 'situation_model' else 'engaged' if depth == 'textbase' else 'mentioned'
            fact_count = len([f for f in n.get('facts', []) if f.get('correct')])
            confidence = min(1.0, fact_count * 0.25) if fact_count else 0.3
            update_knowledge(domain_id, n['node_id'], knowledge=level,
                             confidence=confidence, source='era_sweep', conn=wconn)

        # Create correction ML cards for errors
        for err in result.get('errors', [])[:3]:
            claim = err.get('claim', '')
            correction = err.get('correction', '')
            node_id_for_err = err.get('node_id', era_id)
            if claim and correction:
                q = f'Correction: You said "{claim}" — what is actually true about this?'
                try:
                    create_microlearning_request(
                        query=q, source_node_id=node_id_for_err, source_domain=domain_id,
                        source_type='correction',
                    )
                    print(f'[era-sweep] Created correction ML for: {claim[:50]}', flush=True)
                except Exception as e:
                    print(f'[era-sweep] Correction ML failed: {e}', flush=True)

        # Generate timeline card if the sweep showed chronological gaps
        # Collect date-type key_facts from all children to build a sequencing card
        org_pattern = result.get('connections', [])
        has_date_errors = any(
            e.get('node_id', '') in [n['id'] for n in children]
            for e in result.get('errors', [])
        )
        # Generate if: mixed up dates, low coverage, or mentioned but at surface level
        surface_nodes = [n for n in mentioned if n.get('depth') == 'surface']
        if has_date_errors or len(surface_nodes) >= 2 or coverage_pct < 60:
            date_facts = []
            for ch in children:
                kf_row = wconn.execute(
                    'SELECT key_facts FROM curriculum_nodes WHERE id = ? AND domain_id = ?',
                    (ch['id'], domain_id)
                ).fetchone()
                if kf_row and kf_row['key_facts']:
                    try:
                        for f in json.loads(kf_row['key_facts']):
                            if f.get('type') == 'date' or f.get('type') == 'event':
                                date_facts.append(f"{f['question']} → {f['answer']}")
                    except Exception:
                        pass
            if date_facts:
                timeline_q = (
                    f"Timeline review for {era_node['title']}: Build the chronological scaffold. "
                    f"Key dates and events to sequence:\n" +
                    '\n'.join(f'- {df}' for df in date_facts[:8])
                )
                try:
                    create_microlearning_request(
                        query=timeline_q, source_node_id=era_id, source_domain=domain_id,
                        source_type='sweep_timeline',
                    )
                    print(f'[era-sweep] Created timeline ML for {era_node["title"]}', flush=True)
                except Exception as e:
                    print(f'[era-sweep] Timeline ML failed: {e}', flush=True)

        # Store era sweep score for longitudinal tracking
        sweep_row_id = f'era_sweep_{era_id}_{int(time.time())}'
        wconn.execute(
            'INSERT INTO knowledge_sweeps (id, domain_id, sweep_type, phase1_transcript, '
            'total_nodes_mentioned, nodes_total, total_coverage, total_accuracy, composite_score, '
            'scoring_result, system_coverage, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                sweep_row_id, domain_id, 'era',
                transcript,
                len(mentioned), len(children),
                round(len(mentioned) / len(children), 3) if children else 0,
                round(sum(1 for f in all_facts if f.get('correct')) / len(all_facts), 3) if all_facts else 0,
                coverage_pct / 100.0,
                json.dumps(result),
                0,  # system_coverage computed later if needed
                int(time.time()),
            )
        )
        wconn.commit()
        print(f'[era-sweep] Saved {sweep_row_id}: {len(mentioned)}/{len(children)} nodes', flush=True)
    except Exception as e:
        print(f'[era-sweep] Write phase error: {e}', flush=True)
    finally:
        wconn.close()

    return elicit_result


def get_sweep_plan(domain_id: str) -> dict | None:
    """Return the sweep plan for a domain: eras with prompts and metadata."""
    from db import get_connection
    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return None

    conn = get_connection(readonly=True)
    try:
        states = load_knowledge_states(domain_id, conn)
        l2_nodes = [n for n in curriculum['nodes'] if n.get('level', 1) <= 2]
        known = sum(1 for n in l2_nodes if states.get(n['id'], {}).get('knowledge', 'unknown') != 'unknown')
        system_coverage = known / len(l2_nodes) if l2_nodes else 0

        eras = []
        for node in curriculum['nodes']:
            if node.get('level') != 1:
                continue
            children = [n for n in curriculum['nodes']
                        if n.get('parent_id') == node['id'] and n.get('level') == 2]
            eras.append({
                'era_id': node['id'],
                'title': node['title'],
                'prompt': f"{node['title']}. What key events, people, and turning points do you remember from this period? Just the highlights.",
                'children': [{'id': c['id'], 'title': c['title']} for c in children],
                'child_count': len(children),
            })

        return {
            'domain_id': domain_id,
            'domain_title': curriculum['title'],
            'system_coverage': round(system_coverage, 3),
            'eras': eras,
            'total_l2_nodes': len(l2_nodes),
            'sweep_type': 'guided',
        }
    finally:
        conn.close()


def score_sweep(domain_id: str, phase1_eras: list[dict],
                phase2_transcript: str | None = None) -> dict:
    """Score a completed sweep against the curriculum.

    phase1_eras: [{era_id, transcript, duration_s}]
    phase2_transcript: optional gap-probing transcript

    Returns full sweep result dict ready for DB insertion.
    """
    from db import get_connection

    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return {'error': f'Curriculum {domain_id} not found'}

    conn = get_connection(readonly=True)
    try:
        states = load_knowledge_states(domain_id, conn)

        l2_nodes = [n for n in curriculum['nodes'] if n.get('level', 1) <= 2]
        nodes_with_facts = []
        for node in l2_nodes:
            kf_row = conn.execute(
                'SELECT key_facts FROM curriculum_nodes WHERE id = ? AND domain_id = ?',
                (node['id'], domain_id)
            ).fetchone()
            key_facts = []
            if kf_row and kf_row['key_facts']:
                try:
                    key_facts = json.loads(kf_row['key_facts'])
                except Exception:
                    pass

            facts_str = ''
            if key_facts:
                facts_list = [f"    - [{f['type']}] {f['id']}: {f['question']} → {f['answer']}"
                              for f in key_facts[:6]]
                facts_str = '\n'.join(facts_list)

            parent = next((n for n in curriculum['nodes'] if n['id'] == node.get('parent_id')), None)
            era_label = f" (under {parent['title']})" if parent else ''
            entry = f"- {node['id']}: {node['title']}{era_label} [L{node.get('level', 1)}]\n  {node.get('description', '')}"
            if facts_str:
                entry += f"\n  Key facts:\n{facts_str}"
            nodes_with_facts.append(entry)

        p1_combined = '\n\n'.join(
            f"[Era: {era.get('era_id', 'unknown')}]\n{era['transcript']}"
            for era in phase1_eras if era.get('transcript', '').strip()
        )

        full_transcript = p1_combined
        if phase2_transcript and phase2_transcript.strip():
            full_transcript += f"\n\n[Gap probing follow-up]\n{phase2_transcript}"

        if not full_transcript.strip():
            return {'error': 'No transcript content to score'}

        known = sum(1 for n in l2_nodes if states.get(n['id'], {}).get('knowledge', 'unknown') != 'unknown')
        system_coverage = known / len(l2_nodes) if l2_nodes else 0

        l2_ids = {n['id'] for n in l2_nodes}
        connections_possible = 0
        for node in l2_nodes:
            for prereq in node.get('prerequisites', []):
                if prereq in l2_ids:
                    connections_possible += 1

        prev = conn.execute(
            'SELECT id, total_coverage, composite_score FROM knowledge_sweeps '
            'WHERE domain_id = ? ORDER BY created_at DESC LIMIT 1',
            (domain_id,)
        ).fetchone()
    finally:
        conn.close()

    # ── LLM scoring (slow — no DB lock held) ──
    prompt = SWEEP_SCORING_PROMPT.format(
        domain_title=curriculum['title'],
        transcript=full_transcript,
        nodes_with_facts='\n'.join(nodes_with_facts),
    )
    print(f'[sweep] Scoring sweep for {domain_id} ({len(full_transcript)} chars transcript)...', flush=True)
    raw = _call_claude(prompt, timeout=300)
    if not raw:
        return {'error': 'LLM scoring failed — no response'}

    result = _parse_json(raw)
    if not result:
        return {'error': 'LLM scoring failed — could not parse JSON', 'raw': raw[:500]}

    # ── Compute metrics ──
    scored_nodes = result.get('nodes', [])
    mentioned_nodes = [n for n in scored_nodes if n.get('mentioned')]
    all_facts = []
    for n in scored_nodes:
        all_facts.extend(n.get('facts', []))
    facts_correct = sum(1 for f in all_facts if f.get('correct'))
    connections = result.get('connections', [])

    total_nodes = len(l2_nodes)
    org = result.get('organization', {})
    org_score = min(1.0, (org.get('causal_count', 0) * 0.1 +
                          org.get('perspective_count', 0) * 0.15 +
                          (0.3 if org.get('pattern') == 'chronological' else 0.1)))

    coverage = len(mentioned_nodes) / total_nodes if total_nodes else 0
    accuracy = facts_correct / len(all_facts) if all_facts else 0
    connectivity = len(connections) / connections_possible if connections_possible else 0
    composite = (coverage * 0.4 + accuracy * 0.3 + connectivity * 0.2 + org_score * 0.1)

    sweep_id = f'sweep_{domain_id}_{int(time.time())}'

    sweep_result = {
        'id': sweep_id,
        'domain_id': domain_id,
        'sweep_type': 'guided',
        'phase1_transcript': p1_combined,
        'phase2_transcript': phase2_transcript,
        'phase1_eras': json.dumps(phase1_eras),
        'p1_nodes_mentioned': len(mentioned_nodes),
        'p1_facts_correct': facts_correct,
        'p1_facts_stated': len(all_facts),
        'p1_connections': len(connections),
        'total_nodes_mentioned': len(mentioned_nodes),
        'total_facts_correct': facts_correct,
        'total_facts_stated': len(all_facts),
        'total_connections': len(connections),
        'nodes_total': total_nodes,
        'connections_possible': connections_possible,
        'p1_coverage': round(coverage, 3),
        'p1_accuracy': round(accuracy, 3),
        'total_coverage': round(coverage, 3),
        'total_accuracy': round(accuracy, 3),
        'connectivity_score': round(connectivity, 3),
        'organization_score': round(org_score, 3),
        'composite_score': round(composite, 3),
        'scoring_result': json.dumps(result),
        'previous_sweep_id': prev['id'] if prev else None,
        'delta_coverage': round(coverage - prev['total_coverage'], 3) if prev else None,
        'delta_composite': round(composite - prev['composite_score'], 3) if prev else None,
        'system_coverage': round(system_coverage, 3),
    }

    # ── Write to DB ──
    from db import get_connection as _gc
    wconn = _gc()
    try:
        cols = ', '.join(sweep_result.keys())
        placeholders = ', '.join('?' * len(sweep_result))
        wconn.execute(
            f'INSERT INTO knowledge_sweeps ({cols}) VALUES ({placeholders})',
            list(sweep_result.values())
        )
        wconn.commit()
        print(f'[sweep] Saved sweep {sweep_id}: coverage={coverage:.1%}, accuracy={accuracy:.1%}, '
              f'composite={composite:.2f}', flush=True)
    finally:
        wconn.close()

    sweep_result['scoring_detail'] = result
    sweep_result['domain_title'] = curriculum['title']
    return sweep_result


def get_sweep_gaps(scoring_result: dict, domain_id: str) -> list[dict]:
    """Given a scored sweep, identify gaps for Phase 2 probing."""
    curriculum = load_curriculum(domain_id)
    if not curriculum:
        return []

    scored_nodes = scoring_result.get('nodes', [])
    mentioned_ids = {n['node_id'] for n in scored_nodes if n.get('mentioned')}

    l1_nodes = {n['id']: n for n in curriculum['nodes'] if n.get('level') == 1}
    missed_by_era: dict[str, list] = {}
    for node in curriculum['nodes']:
        if node.get('level') != 2:
            continue
        if node['id'] not in mentioned_ids:
            parent_id = node.get('parent_id', '')
            missed_by_era.setdefault(parent_id, []).append(node)

    gap_prompts = []
    for era_id, missed_nodes in missed_by_era.items():
        era = l1_nodes.get(era_id)
        if not era or len(missed_nodes) < 1:
            continue
        node_names = ', '.join(n['title'] for n in missed_nodes[:3])
        prompt = (f"You didn't mention much about: {node_names}. "
                  f"What do you know about these aspects of {era['title']}?")
        gap_prompts.append({
            'era_id': era_id,
            'era_title': era['title'],
            'prompt': prompt,
            'missed_nodes': [{'id': n['id'], 'title': n['title']} for n in missed_nodes],
        })

    return gap_prompts


def get_sweep_history(domain_id: str, limit: int = 10) -> list[dict]:
    """Get past sweeps for a domain, most recent first."""
    from db import get_connection
    conn = get_connection(readonly=True)
    try:
        rows = conn.execute(
            'SELECT id, domain_id, sweep_type, p1_coverage, total_coverage, '
            'total_accuracy, connectivity_score, organization_score, composite_score, '
            'system_coverage, delta_coverage, delta_composite, '
            'total_nodes_mentioned, nodes_total, created_at '
            'FROM knowledge_sweeps WHERE domain_id = ? '
            'ORDER BY created_at DESC LIMIT ?',
            (domain_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
