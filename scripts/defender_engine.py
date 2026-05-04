"""Defender mode — prototype.

Pearl 4 (Tibetan monastic debate) from research/srs-humanities/04-tibetan-debate.md:
review through ritualised contradiction. The user asserts a thesis; the system
plays the challenger, surfacing 2-3 objections drawn from their curriculum and
voice corpus. The user defends. The system grades, surfaces a follow-up
objection, and continues until concluded.

This is a text-only v0. Audio is a v1 add — reuse `transcribe_on_server` to
turn audio into a `response_text` and the rest of the pipeline is identical.

Storage: defender_sessions table, one row per session, full conversation as
JSON. No FSRS scheduling — this is metabolisation, not retention.
"""

from __future__ import annotations

import json
import time
from typing import Any

from claude_llm import call_claude_json


# ── knowledge-write helpers ──────────────────────────────────────────────────

def _persist_response_to_knowledge(
    response_text: str, thesis: str, domain_id: str | None,
    node_id: str | None, entity_name: str | None,
    grade: dict, session_id: str, conn,
) -> str | None:
    """Write a defender response into the broader knowledge layer.

    1. Insert a voice_transcripts row with source='defender_response' so the
       response is durable, browseable, and searchable.
    2. Embed the response into transcript_chunks so commonplace-resurfacing
       and the knowledge profile can find it later.
    3. If the session is domain/node-scoped, link the chunks to that node so
       future review-stream context retrieval surfaces this defense.

    Returns the voice_transcripts.id created, or None on failure.
    """
    try:
        from review_engine import _log_voice_transcript, create_transcript_chunks
    except ImportError as e:
        print(f'[defender] could not import review_engine: {e}', flush=True)
        return None

    # Compose a "what was said" record. Frame the thesis + response so future
    # searchers see the full move, not a context-free fragment.
    framed = (
        f"[Defender session {session_id}] Thesis: {thesis.strip()}\n\n"
        f"My defense: {response_text.strip()}"
    )

    # Build a synthetic llm_result so create_transcript_chunks() picks up the
    # response as structured chunks (not just raw_speech).
    synthetic_result = {
        'captured': [response_text.strip()],
        'feedback_summary': grade.get('feedback', '') or '',
        'overall_summary': f"Defense of: {thesis.strip()[:200]}",
    }

    node_title = (
        node_id and f"defender:{node_id}"
        or entity_name and f"defender:entity:{entity_name}"
        or domain_id and f"defender:{domain_id}"
        or 'defender'
    )

    try:
        vt_id = _log_voice_transcript(
            source='defender_response',
            node_id=node_id or '',
            domain_id=domain_id or '',
            node_title=node_title,
            transcript=framed,
            audio_bytes=0,
            llm_result=synthetic_result,
            ml_triggered=[],
            input_mode='text_json',
        )
    except Exception as e:
        print(f'[defender] _log_voice_transcript failed: {e}', flush=True)
        return None

    # Embed and link. node_id may be empty — chunks are still created with
    # embeddings, just without a chunk_node_links row (which is fine — semantic
    # search still finds them).
    try:
        create_transcript_chunks(
            transcript_id=vt_id,
            node_id=node_id or '',
            domain_id=domain_id or '',
            transcript=framed,
            llm_result=synthetic_result,
            conn=conn,
        )
    except Exception as e:
        print(f'[defender] create_transcript_chunks failed (transcript still saved): {e}', flush=True)

    return vt_id


def _knowledge_score_from_grade(grade: dict) -> str | None:
    """Map a defender grade onto an FSRS rating.

    The pearl is explicit that defender mode is metabolisation, not retention,
    so we apply only LIGHT signal — only when the grader saw 'specific evidence'
    do we count it as a partial review. We never downgrade knowledge from
    deflection alone, because deflection in debate is often strategic, not
    ignorance.

    Returns 'knew' | 'partly' | None.
    """
    engagement = (grade or {}).get('engagement', '')
    evidence = (grade or {}).get('evidence', '')
    if engagement == 'engaged' and evidence == 'specific':
        return 'knew'
    if engagement == 'engaged' and evidence == 'general':
        return 'partly'
    return None


def _reinforce_scoped_knowledge(
    domain_id: str | None, node_id: str | None,
    entity_name: str | None, score: str, conn,
) -> dict:
    """When a response is well-defended on a scoped session, give a SMALL
    stability boost to the relevant knowledge_items / knowledge_entities.

    This deliberately does NOT call the full FSRS reschedule — that would
    pull cards out of their normal review schedule. Instead, we just bump
    `last_reviewed_at` so the recency-boost picks them up, and append to
    `question_history` so we know the touch came from defender mode.

    Returns: {touched_items: int, touched_entities: int}
    """
    import time
    touched_items = 0
    touched_entities = 0
    now_ms = int(time.time() * 1000)
    note = json.dumps({'source': 'defender', 'score': score, 'ts': now_ms})

    try:
        if domain_id and node_id:
            row = conn.execute(
                "SELECT id, question_history FROM knowledge_items "
                "WHERE curriculum_domain=? AND curriculum_node_id=?",
                (domain_id, node_id),
            ).fetchone()
            if row:
                history = []
                try:
                    history = json.loads(row['question_history'] or '[]')
                except Exception:
                    history = []
                history.append(note)
                conn.execute(
                    "UPDATE knowledge_items SET last_reviewed_at=?, "
                    "question_history=? WHERE id=?",
                    (now_ms, json.dumps(history[-30:]), row['id']),
                )
                touched_items = 1

        if entity_name:
            slug = entity_name.lower().replace(' ', '_')
            row = conn.execute(
                "SELECT id, question_history FROM knowledge_entities "
                "WHERE id=? OR entity_name=?",
                (f'ent:{slug}', entity_name),
            ).fetchone()
            if row:
                history = []
                try:
                    history = json.loads(row['question_history'] or '[]')
                except Exception:
                    history = []
                history.append(note)
                conn.execute(
                    "UPDATE knowledge_entities SET last_reviewed_at=?, "
                    "question_history=? WHERE id=?",
                    (now_ms, json.dumps(history[-30:]), row['id']),
                )
                touched_entities = 1
        conn.commit()
    except Exception as e:
        print(f'[defender] reinforce failed: {e}', flush=True)

    return {'touched_items': touched_items, 'touched_entities': touched_entities}


# ── prompts ──────────────────────────────────────────────────────────────────

DEFENDER_OBJECTION_PROMPT = """You are a sharp, well-read challenger in a structured intellectual debate. The defender has just asserted a thesis. Your job is to surface 2-3 of the strongest objections a competent peer would raise — not strawmen, not pedantic nitpicks. The defender will then respond to one of them.

THESIS: {thesis}

CONTEXT THE DEFENDER HAS STUDIED (their curriculum + voice captures):
{context}

Generate 2-3 distinct objections. Each must come from a DIFFERENT angle — vary across these axes:
- empirical: "the historical record contradicts this — X happened, not Y"
- methodological: "this conflates two scales / time horizons / units of analysis"
- contextual: "in the period you're describing, the alternative wasn't available"
- contrarian: "the conventional view runs the opposite direction — here's why"
- counterfactual: "what would actually have happened if the opposite were true?"

Each objection must:
- be ONE focused claim, not a bundle
- cite SPECIFIC evidence (date, person, event) the defender would recognise from the context above where possible — not vague gestures
- be genuinely defensible: a smart historian could mount this objection in good faith
- be 1-3 sentences max — the defender needs to engage it, not parse it

Avoid: rhetorical questions, "but isn't it possible that...", and objections that just restate the thesis as a question.

Output JSON only:
{{"objections": [{{"angle": "empirical|methodological|contextual|contrarian|counterfactual", "text": "the objection itself", "evidence_hint": "the specific fact/source the defender should know to engage this"}}, ...]}}"""


DEFENDER_GRADE_PROMPT = """You are a debate moderator and intellectual sparring partner. The defender has asserted a thesis and is now responding to one of your objections. Grade their response and decide whether to push further.

ORIGINAL THESIS: {thesis}

THE OBJECTION YOU RAISED: {objection}

THE DEFENDER'S RESPONSE: {response}

CONTEXT THEY HAVE STUDIED:
{context}

Evaluate:

1. ENGAGEMENT: Did they actually address THIS objection, or did they pivot to a different point?
   - "engaged": directly contended with the objection's specific claim
   - "deflected": acknowledged it but moved to safer ground
   - "ignored": responded to a different objection or restated the thesis

2. EVIDENCE: Did they bring specific facts/sources to bear, or stay at the level of generality?
   - "specific": named a date, person, source, mechanism
   - "general": correct gesture without anchoring evidence
   - "absent": no evidence offered

3. CONCESSION: Did they cede any ground, refine the thesis, or hold the line?
   - This is GOOD signal — concessions suggest real thinking. Hold-the-line responses can be either rigorous or stubborn; flag which.

4. FOLLOW-UP: Generate ONE next move. Either:
   - "follow_up_objection": a sharper objection that specifically targets a weak point in their response. Should escalate, not repeat. Cite something specific from their response.
   - "concede_and_pivot": acknowledge they handled this objection well, surface a NEW objection from a different angle.
   - "conclude": the defender has now defended the thesis well from multiple angles (only after 3+ rounds), or the thesis has been refined into a stronger form. Provide a 2-3 sentence summary of what they established.

Be intellectually honest. If the response was bad, say so in `feedback`. If it was excellent, say so. Don't flatter.

Output JSON only:
{{"engagement": "engaged|deflected|ignored", "evidence": "specific|general|absent", "concession": "ceded ground/refined thesis/held line", "feedback": "1-2 sentences honest assessment of the response — what worked and what didn't", "next_move": "follow_up_objection|concede_and_pivot|conclude", "follow_up_objection": {{"angle": "...", "text": "...", "evidence_hint": "..."}} | null, "conclusion_summary": "..." | null}}"""


# ── context loading ──────────────────────────────────────────────────────────

def _load_context(domain_id: str | None, node_id: str | None,
                  entity_name: str | None, conn) -> dict:
    """Pull the context that gets fed to both objection-generation and grading.

    Returns: {key_facts: [...], voice_excerpts: [...], related_entities: [...],
              source_label: str}
    Empty fields are fine — Claude handles thin context gracefully.
    """
    key_facts: list[str] = []
    voice_excerpts: list[str] = []
    related_entities: list[dict] = []
    source_label = "general history"

    if domain_id:
        row = conn.execute(
            "SELECT title FROM curriculum_domains WHERE id=?", (domain_id,)
        ).fetchone()
        if row:
            source_label = row['title']

    # Curriculum-node-anchored: pull node key_facts + sibling node titles
    if domain_id and node_id:
        node = conn.execute(
            "SELECT title, description, key_facts FROM curriculum_nodes "
            "WHERE domain_id=? AND id=?", (domain_id, node_id)
        ).fetchone()
        if node:
            source_label = f"{source_label} → {node['title']}"
            try:
                facts = json.loads(node['key_facts'] or '[]')
                for f in facts[:25]:
                    if isinstance(f, dict):
                        if f.get('claim'):
                            key_facts.append(f['claim'])
                        elif f.get('fact'):
                            key_facts.append(f['fact'])
                    elif isinstance(f, str):
                        key_facts.append(f)
            except Exception:
                pass

    # Entity-anchored: pull entity key_facts + Wikidata neighbors
    if entity_name:
        slug = entity_name.lower().replace(' ', '_')
        ent = conn.execute(
            "SELECT id, key_facts, wikidata_qid FROM knowledge_entities "
            "WHERE id=? OR entity_name=?",
            (f'ent:{slug}', entity_name)
        ).fetchone()
        if ent:
            source_label = f"entity: {entity_name}"
            try:
                facts = json.loads(ent['key_facts'] or '[]')
                for f in facts[:25]:
                    if isinstance(f, dict) and f.get('fact'):
                        key_facts.append(f['fact'])
                    elif isinstance(f, dict) and f.get('claim'):
                        key_facts.append(f['claim'])
            except Exception:
                pass

    # Voice excerpts: any transcript that mentions the entity or domain in the last 365d
    voice_filter = entity_name or (domain_id or '')
    if voice_filter:
        cutoff = int((time.time() - 365 * 86400) * 1000)
        rows = conn.execute(
            "SELECT transcript, source FROM voice_transcripts "
            "WHERE created_at > ? AND (transcript LIKE ? OR domain_id = ?) "
            "ORDER BY created_at DESC LIMIT 5",
            (cutoff, f'%{voice_filter}%', domain_id or '')
        ).fetchall()
        for r in rows:
            t = r['transcript'][:600]
            if t:
                voice_excerpts.append(f"[{r['source']}] {t}")

    # Related entities — anything in shared_entities matching the domain by curriculum link
    if domain_id:
        rows = conn.execute(
            "SELECT DISTINCT e.name, e.entity_type, e.dates, e.description "
            "FROM shared_entities e "
            "JOIN entity_curriculum_links l ON l.entity_id = e.entity_id "
            "WHERE l.domain_id = ? LIMIT 20",
            (domain_id,)
        ).fetchall()
        for r in rows:
            related_entities.append({
                'name': r['name'],
                'type': r['entity_type'] or '',
                'dates': r['dates'] or '',
                'desc': (r['description'] or '')[:200],
            })

    return {
        'source_label': source_label,
        'key_facts': key_facts,
        'voice_excerpts': voice_excerpts,
        'related_entities': related_entities,
    }


def _format_context(ctx: dict) -> str:
    """Render the context dict into a string for prompt injection."""
    parts = [f"SOURCE: {ctx['source_label']}", ""]
    if ctx['key_facts']:
        parts.append("KEY FACTS THE DEFENDER HAS STUDIED:")
        for f in ctx['key_facts']:
            parts.append(f"  - {f}")
        parts.append("")
    if ctx['voice_excerpts']:
        parts.append("VOICE CAPTURES (the defender's own words on this topic):")
        for ex in ctx['voice_excerpts']:
            parts.append(f"  - {ex}")
        parts.append("")
    if ctx['related_entities']:
        parts.append("RELATED ENTITIES (people/places/events in this domain):")
        for e in ctx['related_entities']:
            line = f"  - {e['name']}"
            if e['type']:
                line += f" ({e['type']}"
                if e['dates']:
                    line += f", {e['dates']}"
                line += ")"
            elif e['dates']:
                line += f" ({e['dates']})"
            if e['desc']:
                line += f": {e['desc']}"
            parts.append(line)
        parts.append("")
    return "\n".join(parts) if len(parts) > 2 else "(no specific context — reason from general historical knowledge)"


# ── public API ───────────────────────────────────────────────────────────────

def start_session(thesis: str, conn,
                  domain_id: str | None = None,
                  node_id: str | None = None,
                  entity_name: str | None = None) -> dict:
    """Create a new defender session and return the opening objections.

    Returns: {session_id, thesis, objections: [{angle, text, evidence_hint}, ...],
              context_summary: str}
    """
    if not thesis or len(thesis.strip()) < 10:
        return {'error': 'Thesis too short — assert at least one substantive sentence.'}

    ctx = _load_context(domain_id, node_id, entity_name, conn)
    ctx_str = _format_context(ctx)

    prompt = DEFENDER_OBJECTION_PROMPT.format(thesis=thesis.strip(), context=ctx_str)
    result = call_claude_json(prompt, timeout=120)
    if not result or not isinstance(result, dict) or not result.get('objections'):
        return {'error': 'LLM did not return usable objections — try rephrasing the thesis.'}

    objections = result['objections'][:3]
    session_id = f"def_{int(time.time())}_{hash(thesis) % 100000:05d}"
    rounds = [
        {
            'round': 0,
            'role': 'opener',
            'objections': objections,
            'created_at': int(time.time() * 1000),
        }
    ]

    conn.execute(
        """INSERT INTO defender_sessions
           (id, thesis, domain_id, node_id, entity_name, rounds, context_used,
            status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
        (session_id, thesis.strip(), domain_id, node_id, entity_name,
         json.dumps(rounds), json.dumps(ctx),
         int(time.time() * 1000)),
    )
    conn.commit()

    return {
        'session_id': session_id,
        'thesis': thesis.strip(),
        'objections': objections,
        'context_summary': ctx['source_label'],
    }


def respond(session_id: str, response_text: str, objection_index: int, conn) -> dict:
    """Record the defender's response, grade it, return next move.

    `objection_index` selects which of the most-recent objections list the
    defender chose to address (0/1/2). The grader is shown only that objection.

    Returns: {grade: {...}, next_move: str, follow_up: {...} | None,
              conclusion: str | None, status: 'active'|'concluded'}
    """
    if not response_text or len(response_text.strip()) < 5:
        return {'error': 'Response too short.'}

    row = conn.execute(
        "SELECT thesis, rounds, context_used, status FROM defender_sessions WHERE id=?",
        (session_id,)
    ).fetchone()
    if not row:
        return {'error': f'Session {session_id} not found.'}
    if row['status'] == 'concluded':
        return {'error': 'Session already concluded.'}

    thesis = row['thesis']
    try:
        rounds = json.loads(row['rounds'])
    except Exception:
        rounds = []
    try:
        ctx = json.loads(row['context_used'])
    except Exception:
        ctx = {}
    ctx_str = _format_context(ctx) if ctx else "(no context loaded)"

    # Find the objection the defender is responding to.
    last_round = rounds[-1] if rounds else None
    if not last_round:
        return {'error': 'Session has no opening round — re-create the session.'}

    if 'objections' in last_round:
        objs = last_round['objections']
    elif 'objection' in last_round:
        objs = [last_round['objection']]
    else:
        return {'error': 'Last round has no objection to respond to.'}

    if objection_index < 0 or objection_index >= len(objs):
        objection_index = 0
    chosen = objs[objection_index]

    # Grade.
    prompt = DEFENDER_GRADE_PROMPT.format(
        thesis=thesis,
        objection=f"({chosen.get('angle', 'objection')}) {chosen.get('text', '')}",
        response=response_text.strip(),
        context=ctx_str,
    )
    grade = call_claude_json(prompt, timeout=120)
    if not grade or not isinstance(grade, dict):
        return {'error': 'LLM grading failed — try again.'}

    next_move = grade.get('next_move', 'follow_up_objection')
    follow_up = grade.get('follow_up_objection')
    conclusion = grade.get('conclusion_summary')

    new_round = {
        'round': len(rounds),
        'role': 'response',
        'addressed_objection': chosen,
        'response_text': response_text.strip(),
        'grade': {
            'engagement': grade.get('engagement'),
            'evidence': grade.get('evidence'),
            'concession': grade.get('concession'),
            'feedback': grade.get('feedback'),
        },
        'created_at': int(time.time() * 1000),
    }
    rounds.append(new_round)

    # Append the follow-up move so the next /respond call has something to address.
    if next_move == 'conclude':
        rounds.append({
            'round': len(rounds),
            'role': 'conclusion',
            'summary': conclusion or 'Session concluded.',
            'created_at': int(time.time() * 1000),
        })
        new_status = 'concluded'
        concluded_at = int(time.time() * 1000)
    else:
        if follow_up and isinstance(follow_up, dict):
            rounds.append({
                'round': len(rounds),
                'role': 'challenger',
                'objections': [follow_up],
                'created_at': int(time.time() * 1000),
            })
        new_status = 'active'
        concluded_at = None

    conn.execute(
        "UPDATE defender_sessions SET rounds=?, status=?, concluded_at=? WHERE id=?",
        (json.dumps(rounds), new_status, concluded_at, session_id),
    )
    conn.commit()

    # ── Knowledge-write side-effects (Pearl 4 → metabolisation) ────────────
    # 1) Persist the response so commonplace + knowledge profile can find it.
    sess_row = conn.execute(
        "SELECT domain_id, node_id, entity_name FROM defender_sessions WHERE id=?",
        (session_id,)
    ).fetchone()
    domain_id = sess_row['domain_id'] if sess_row else None
    node_id = sess_row['node_id'] if sess_row else None
    entity_name = sess_row['entity_name'] if sess_row else None

    vt_id = _persist_response_to_knowledge(
        response_text=response_text,
        thesis=thesis,
        domain_id=domain_id,
        node_id=node_id,
        entity_name=entity_name,
        grade=new_round['grade'],
        session_id=session_id,
        conn=conn,
    )

    # 2) Light reinforcement signal — only on engaged+specific or engaged+general.
    score = _knowledge_score_from_grade(new_round['grade'])
    reinforce = {'touched_items': 0, 'touched_entities': 0}
    if score:
        reinforce = _reinforce_scoped_knowledge(
            domain_id, node_id, entity_name, score, conn,
        )

    return {
        'session_id': session_id,
        'grade': new_round['grade'],
        'next_move': next_move,
        'follow_up': follow_up if next_move != 'conclude' else None,
        'conclusion': conclusion if next_move == 'conclude' else None,
        'status': new_status,
        'round_count': len([r for r in rounds if r.get('role') == 'response']),
        'knowledge_writes': {
            'transcript_id': vt_id,
            'reinforcement_score': score,
            **reinforce,
        },
    }


def list_sessions(conn, limit: int = 20) -> list[dict]:
    """Return recent sessions for the history view."""
    rows = conn.execute(
        """SELECT id, thesis, domain_id, node_id, entity_name, status,
                  created_at, concluded_at, rounds
           FROM defender_sessions
           ORDER BY created_at DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    out = []
    for r in rows:
        try:
            rounds = json.loads(r['rounds'])
            response_count = len([rd for rd in rounds if rd.get('role') == 'response'])
        except Exception:
            response_count = 0
        out.append({
            'id': r['id'],
            'thesis': r['thesis'],
            'domain_id': r['domain_id'],
            'node_id': r['node_id'],
            'entity_name': r['entity_name'],
            'status': r['status'],
            'created_at': r['created_at'],
            'concluded_at': r['concluded_at'],
            'rounds': response_count,
        })
    return out


def get_session(session_id: str, conn) -> dict | None:
    """Full session detail."""
    row = conn.execute(
        """SELECT id, thesis, domain_id, node_id, entity_name, status,
                  created_at, concluded_at, rounds, context_used
           FROM defender_sessions WHERE id=?""",
        (session_id,)
    ).fetchone()
    if not row:
        return None
    try:
        rounds = json.loads(row['rounds'])
    except Exception:
        rounds = []
    try:
        ctx = json.loads(row['context_used'])
    except Exception:
        ctx = {}
    return {
        'id': row['id'],
        'thesis': row['thesis'],
        'domain_id': row['domain_id'],
        'node_id': row['node_id'],
        'entity_name': row['entity_name'],
        'status': row['status'],
        'created_at': row['created_at'],
        'concluded_at': row['concluded_at'],
        'rounds': rounds,
        'context_summary': ctx.get('source_label', '') if isinstance(ctx, dict) else '',
    }
