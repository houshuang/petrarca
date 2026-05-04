"""Commonplace-resurfacing — Pearl 8 (Locke + Bjornstad).

Treat voice_transcripts as a digital commonplace book and surface chunks the
user captured long ago that semantically rhyme with what they're thinking
about right now. No SRS scheduling, no review pressure — just associative
pull. Locke's reform: the system holds the storage so the human can forget.

Reuses existing infrastructure end-to-end:
  - transcript_chunks: already populated with float32 embeddings (Session 56)
  - limbic.amygdala.EmbeddingModel: already used elsewhere for cosine search
  - voice_transcripts: source-of-truth for date/source provenance

The only new state is `commonplace_events` — a log of what was resurfaced
when, so we don't keep showing the same echo on every query.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any


# Default age cutoff: only chunks older than this count as "resurfaced".
# Locke's bet is that the gap is what makes the experience valuable; a 2-day
# echo is just memory, not resurfacing. 30 days is the floor for "felt forgotten".
DEFAULT_MIN_AGE_DAYS = 30
DEFAULT_SIM_THRESHOLD = 0.55


def _embed_query(text: str):
    """Return a normalized embedding vector for the query text, or None on error."""
    try:
        import numpy as np
        from limbic.amygdala import EmbeddingModel
        model = EmbeddingModel()
        vec = model.embed(text)
        return vec
    except Exception as e:
        print(f'[commonplace] embedding unavailable: {e}', flush=True)
        return None


def find_resurface(query_text: str, conn,
                   min_age_days: int = DEFAULT_MIN_AGE_DAYS,
                   sim_threshold: float = DEFAULT_SIM_THRESHOLD,
                   max_results: int = 5,
                   exclude_transcript_ids: list[str] | None = None) -> dict:
    """Find old chunks that semantically match the query text.

    Args:
        query_text: what the user is currently thinking/reading/recording about.
        conn: SQLite connection.
        min_age_days: only consider chunks older than this. 0 = no age filter.
        sim_threshold: minimum cosine similarity. Tune empirically.
        max_results: how many echoes to return.
        exclude_transcript_ids: skip chunks from these transcripts (e.g. the
            voice capture the user just made — don't echo themselves).

    Returns: {
        echoes: [{
            chunk_id, chunk_text, chunk_type, similarity,
            transcript_id, transcript_source, transcript_date, days_ago,
            transcript_node_title, transcript_excerpt,
        }, ...],
        query_excerpt: query_text[:200],
        meta: {threshold, min_age_days, candidates_scanned},
    }
    """
    import numpy as np

    if not query_text or len(query_text.strip()) < 8:
        return {'echoes': [], 'query_excerpt': query_text[:200],
                'meta': {'error': 'query too short'}}

    qvec = _embed_query(query_text.strip())
    if qvec is None:
        return {'echoes': [], 'query_excerpt': query_text[:200],
                'meta': {'error': 'embedding unavailable'}}

    qvec = np.asarray(qvec, dtype=np.float32)
    qnorm = float(np.linalg.norm(qvec)) + 1e-9

    cutoff_ms = int((time.time() - min_age_days * 86400) * 1000) if min_age_days > 0 else 0
    excluded = set(exclude_transcript_ids or [])

    # Pull candidate chunks: any with an embedding, joined to their transcript
    # for date/source. Skip raw_speech because it bloats results with noisy
    # near-duplicates of the structured chunk_types.
    rows = conn.execute(
        '''SELECT tc.id AS chunk_id, tc.chunk_text, tc.chunk_type, tc.embedding,
                  tc.transcript_id, vt.created_at AS transcript_created_at,
                  vt.source AS transcript_source, vt.node_title, vt.transcript AS full_transcript
           FROM transcript_chunks tc
           JOIN voice_transcripts vt ON vt.id = tc.transcript_id
           WHERE tc.embedding IS NOT NULL
             AND tc.chunk_type != 'raw_speech'
             AND vt.created_at < ?
           LIMIT 5000''',
        (cutoff_ms if cutoff_ms else int(time.time() * 1000) + 1,)
    ).fetchall()

    scored = []
    for r in rows:
        if r['transcript_id'] in excluded:
            continue
        try:
            cvec = np.frombuffer(r['embedding'], dtype=np.float32)
            cnorm = float(np.linalg.norm(cvec)) + 1e-9
            sim = float(np.dot(qvec, cvec) / (qnorm * cnorm))
        except Exception:
            continue
        if sim < sim_threshold:
            continue
        scored.append((sim, r))

    # Take top max_results, but enforce one-echo-per-transcript so a single
    # long capture doesn't dominate the result set.
    scored.sort(key=lambda t: -t[0])
    seen_transcripts = set()
    echoes = []
    now_ms = int(time.time() * 1000)
    for sim, r in scored:
        if r['transcript_id'] in seen_transcripts:
            continue
        seen_transcripts.add(r['transcript_id'])
        days_ago = max(1, (now_ms - r['transcript_created_at']) // (1000 * 86400))
        full = r['full_transcript'] or ''
        # Surrounding excerpt: ±120 chars around the chunk text in the full transcript
        excerpt = ''
        if full and r['chunk_text']:
            idx = full.find(r['chunk_text'])
            if idx >= 0:
                start = max(0, idx - 120)
                end = min(len(full), idx + len(r['chunk_text']) + 120)
                excerpt = ('…' if start > 0 else '') + full[start:end].strip() + ('…' if end < len(full) else '')
        echoes.append({
            'chunk_id': r['chunk_id'],
            'chunk_text': r['chunk_text'],
            'chunk_type': r['chunk_type'],
            'similarity': round(sim, 3),
            'transcript_id': r['transcript_id'],
            'transcript_source': r['transcript_source'],
            'transcript_date': r['transcript_created_at'],
            'days_ago': int(days_ago),
            'transcript_node_title': r['node_title'] or '',
            'transcript_excerpt': excerpt,
        })
        if len(echoes) >= max_results:
            break

    return {
        'echoes': echoes,
        'query_excerpt': query_text.strip()[:300],
        'meta': {
            'threshold': sim_threshold,
            'min_age_days': min_age_days,
            'candidates_scanned': len(rows),
            'matches_above_threshold': len(scored),
        },
    }


def log_event(query_text: str, echoes: list[dict], conn,
              query_source: str = 'manual',
              audio_bytes: int = 0) -> str:
    """Persist a resurfacing event so we can study what worked."""
    event_id = f'cp_{int(time.time())}_{uuid.uuid4().hex[:6]}'
    conn.execute(
        '''INSERT INTO commonplace_events
           (id, query_text, query_source, audio_bytes, echo_chunk_ids,
            echo_count, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (event_id, (query_text or '')[:2000], query_source, audio_bytes,
         json.dumps([e['chunk_id'] for e in echoes]),
         len(echoes),
         int(time.time() * 1000)),
    )
    conn.commit()
    return event_id


def list_recent_events(conn, limit: int = 30) -> list[dict]:
    """Recent resurfacing events for the history view."""
    rows = conn.execute(
        '''SELECT id, query_text, query_source, echo_count, created_at
           FROM commonplace_events
           ORDER BY created_at DESC LIMIT ?''',
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
