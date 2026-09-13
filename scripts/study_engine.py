"""Study operations; invoked through curriculum_db, with no generated knowledge claims."""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from study_schema import SCHEMA

STUDY_ID = 'norway-reading-2026'
DESIGN_VERSION = 'norway-phone-pilot-v1'
POLICY = {'selection':'due-first, curated-order, six-at-a-time, ten-minute encounter cooldown',
          'introduction':'exposure only; next encounter may test rough meaning',
          'grading':'self-report; FSRS only when book declared closed; no anchor credit',
          'assignment':'observational, not randomized',
          'source_attribution':'open-book origin unresolved; never assumed synthesis',
          'capture_kinds':['recall','wondering','correction','reflection']}


def now_ms():
    return int(time.time() * 1000)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def active_focus(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='study_focus'").fetchone():
        return None
    row = conn.execute('SELECT * FROM study_focus WHERE id=1 AND active=1').fetchone()
    return dict(row) if row else None


def status(conn):
    focus = active_focus(conn)
    if not focus:
        return {'active': False}
    return {'active': True, 'study_id': focus['study_id'], 'title': 'Norgeshistorie',
            'subtitle': 'Bind 1 · det du har lest', 'other_cards_suspended': True,
            'paused_counts': json.loads(focus['prior_counts']),
            'items': conn.execute('SELECT count(*) FROM study_items WHERE study_id=? AND suspended=0',
                                  (focus['study_id'],)).fetchone()[0]}


def install(conn, seed, sources=None, code_commit='unknown'):
    """Idempotent, explicit administrative import. Does not change prior schedules."""
    conn.executescript(SCHEMA)
    if seed['study_id'] != STUDY_ID:
        raise ValueError('Unexpected study')
    conn.execute('BEGIN IMMEDIATE')
    try:
        for item in seed['items']:
            payload = encoded(item)
            prior = conn.execute('SELECT payload FROM study_items WHERE id=?', (item['id'],)).fetchone()
            if prior and prior['payload'] != payload:
                raise ValueError('Study content is immutable; use a new item/version')
            conn.execute('INSERT OR IGNORE INTO study_items(id,study_id,version,kind,payload,ordinal) VALUES(?,?,?,?,?,?)',
                         (item['id'], STUDY_ID, seed['version'], item['kind'], payload, item['ordinal']))
            for pos in item['positions']:
                conn.execute('INSERT OR IGNORE INTO study_positions(id,item_id,testable) VALUES(?,?,?)',
                             (pos['position_id'], item['id'], int(pos.get('testable', True))))
        ids = [i['id'] for i in seed['items']]
        conn.execute('UPDATE study_items SET suspended=1 WHERE study_id=?', (STUDY_ID,))
        conn.executemany('UPDATE study_items SET suspended=0 WHERE id=?', [(i,) for i in ids])
        for source in sources or []:
            payload = encoded(source)
            prior = conn.execute('SELECT payload FROM study_sources WHERE id=?', (source['id'],)).fetchone()
            if prior and prior['payload'] != payload:
                raise ValueError('Source version changed')
            conn.execute('INSERT OR IGNORE INTO study_sources VALUES(?,?,?)', (source['id'], STUDY_ID, payload))
        counts = {}
        for table in ['knowledge_items', 'knowledge_entities', 'structural_cards',
                      'microlearning_cards', 'microlearning_quizzes', 'review_items']:
            if conn.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                counts[table] = conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
        conn.execute('INSERT OR IGNORE INTO study_focus VALUES(1,?,1,?,?)',
                     (STUDY_ID, now_ms(), encoded(counts)))
        conn.execute('UPDATE study_focus SET active=1,study_id=? WHERE id=1', (STUDY_ID,))
        revision = {'seed':seed,'policy':POLICY,'source_ids':[s['id'] for s in sources or []]}
        revision_id = hashlib.sha256((code_commit+encoded(revision)).encode()).hexdigest()
        conn.execute('INSERT OR IGNORE INTO study_revisions VALUES(?,?,?,?,?,?)',
                     (revision_id,STUDY_ID,now_ms(),code_commit,DESIGN_VERSION,encoded(revision)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return status(conn)


def session(conn, body):
    conn.execute('BEGIN IMMEDIATE')
    try:
        result = _session(conn, body)
        conn.commit()
        result['completed_ids'] = [r[0] for r in conn.execute("SELECT DISTINCT item_id FROM study_events WHERE run_id=? AND event IN ('complete','introduced','skip')", (result['run_id'],))]
        result['audio_item_ids'] = [r[0] for r in conn.execute("SELECT DISTINCT item_id FROM study_audio WHERE run_id=? AND response_kind='recall'", (result['run_id'],))]
        return result
    except Exception:
        conn.rollback()
        raise


def _session(conn, body):
    focus = active_focus(conn)
    if not focus:
        raise ValueError('Study focus is not active')
    run_id = body.get('request_id', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,100}', run_id):
        raise ValueError('A stable session request_id is required')
    mode = body.get('mode', 'review')
    if mode not in ('review', 'voice'):
        raise ValueError('Unknown mode')
    prior = conn.execute('SELECT * FROM study_runs WHERE id=?', (run_id,)).fetchone()
    if prior:
        if prior['mode'] != mode or prior['study_id'] != focus['study_id']:
            raise ValueError('Session retry changed input')
        return json.loads(prior['snapshot'])
    now = now_ms()
    rows = conn.execute('''SELECT i.*, COALESCE(MIN(p.due_at),0) AS next_due,
        COALESCE(SUM(p.review_count),0) AS reviews,
        (SELECT MAX(e.created_at) FROM study_events e WHERE e.item_id=i.id
         AND e.event IN ('complete','skip','introduced')) AS last_seen
        FROM study_items i LEFT JOIN study_positions p ON p.item_id=i.id AND p.testable=1
        WHERE i.study_id=? AND i.suspended=0 GROUP BY i.id ORDER BY i.ordinal''',
        (focus['study_id'],)).fetchall()
    eligible = [r for r in rows if (r['kind'] == 'voice') == (mode == 'voice')
                and (not r['last_seen'] or r['last_seen'] < now - 10 * 60 * 1000)
                and (r['reviews'] == 0 or r['next_due'] <= now)]
    # Curated ordinal interleaves formats; due reviewed items take precedence.
    eligible.sort(key=lambda r: (0 if r['reviews'] else 1, r['next_due'], r['ordinal']))
    chosen = []
    for r in eligible[:6]:
        item = json.loads(r['payload'])
        item['version'] = r['version']
        item['needs_introduction'] = bool(item.get('introduction') and not r['introduced_at'])
        stats = {p['id']: dict(p) for p in conn.execute('SELECT * FROM study_positions WHERE item_id=?', (r['id'],))}
        for pos in item['positions']:
            pos.update({k: stats[pos['position_id']][k] for k in
                        ['stability_days','due_at','review_count','last_score']})
        chosen.append(item)
    revision = conn.execute('SELECT id,code_commit,design_version FROM study_revisions WHERE study_id=? ORDER BY created_at DESC LIMIT 1',
                            (focus['study_id'],)).fetchone()
    result = {'run_id': run_id, 'items': chosen, 'study': status(conn),
              'experiment':dict(revision) if revision else {'design_version':DESIGN_VERSION},
              'policy':POLICY, 'client_context':body.get('client_context',{})}
    conn.execute('INSERT INTO study_runs VALUES(?,?,?,?,?)',
                 (run_id, focus['study_id'], now, mode, encoded(result)))
    conn.commit()
    return result


def bound_item(conn, run_id, item_id):
    run = conn.execute('SELECT * FROM study_runs WHERE id=?', (run_id,)).fetchone()
    focus = active_focus(conn)
    if not run or not focus or run['study_id'] != focus['study_id']:
        raise ValueError('Session is not part of the active study')
    item = next((x for x in json.loads(run['snapshot'])['items'] if x['id'] == item_id), None)
    if not item:
        raise ValueError('Item is not part of this session')
    return item


def event(conn, body):
    event_id = body.get('request_id', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{12,140}', event_id):
        raise ValueError('Stable event request_id required')
    serialized = encoded(body)
    conn.execute('BEGIN IMMEDIATE')
    try:
        prior = conn.execute('SELECT payload,result FROM study_events WHERE id=?', (event_id,)).fetchone()
        if prior:
            if prior['payload'] != serialized:
                raise ValueError('Event retry changed input')
            conn.rollback()
            return json.loads(prior['result'])
        item = bound_item(conn, body.get('run_id'), body.get('item_id'))
        action = body.get('event')
        if action not in ('shown','revealed','introduced','skip','complete','position_revealed',
                          'position_graded','source_opened','feedback','recording_started',
                          'recording_stopped','recording_cancelled','audio_uploaded','audio_played',
                          'backgrounded','foregrounded','session_left','introduction_shown','scroll','session_finished','audio_upload_failed','recording_failed'):
            raise ValueError('Unknown study event')
        # At most one completion per run/item even if a caller changes its retry ID.
        if action in ('complete','introduced') and conn.execute(
                'SELECT 1 FROM study_events WHERE run_id=? AND item_id=? AND event=?',
                (body['run_id'],item['id'],action)).fetchone():
            raise ValueError('This item was already completed in this session')
        result = {'saved': True, 'scheduled': False}
        if action == 'introduced':
            if not item['needs_introduction']:
                raise ValueError('This encounter is not an introduction')
            conn.execute('UPDATE study_items SET introduced_at=COALESCE(introduced_at,?) WHERE id=?', (now_ms(),item['id']))
        if action == 'complete':
            results = body.get('results', [])
            allowed = {p['position_id'] for p in item['positions'] if p.get('testable', True)}
            ids = [r.get('position_id') for r in results]
            if not results or len(ids) != len(set(ids)) or not set(ids) <= allowed:
                raise ValueError('Invalid position selection')
            if any(r.get('score') not in ('knew','missed') for r in results):
                raise ValueError('Invalid grade')
            if item['needs_introduction']:
                raise ValueError('First introduction is exposure, not a graded test')
            if item['kind'] == 'voice' and not conn.execute(
                    "SELECT 1 FROM study_audio WHERE run_id=? AND item_id=? AND response_kind='recall'",
                    (body['run_id'],item['id'])).fetchone():
                raise ValueError('Save the spoken response before grading')
            observed = conn.execute("SELECT payload FROM study_events WHERE run_id=? AND item_id=? AND event='position_revealed'", (body['run_id'],item['id'])).fetchall()
            revealed = {json.loads(r['payload']).get('detail',{}).get('position_id') for r in observed}
            if not set(ids) <= revealed:
                raise ValueError('Reveal each tested answer before self-assessment')
            from review_engine import _fsrs_reschedule
            if body.get('detail', {}).get('book_state') == 'closed':
                for r in results:
                    _fsrs_reschedule(r['position_id'],r['score'],conn,table='study_positions')
                result['scheduled'] = True
            # Visible anchors and open-book/unknown-context responses get no memory credit.
        conn.execute('INSERT INTO study_events VALUES(?,?,?,?,?,?,?)',
                     (event_id,body['run_id'],item['id'],action,now_ms(),serialized,encoded(result)))
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def save_audio(conn, run_id, item_id, data, mime, audio_root, response_kind='recall'):
    item = bound_item(conn,run_id,item_id)
    if response_kind not in POLICY['capture_kinds']:
        raise ValueError('Unknown recording purpose')
    if (response_kind=='recall' and item['kind']!='voice') or not data or len(data)>25*1024*1024:
        raise ValueError('Invalid voice response')
    suffix = '.webm' if mime.startswith('audio/webm') else '.m4a'
    if not (b'ftyp' in data[:64] or data.startswith(b'\x1aE\xdf\xa3')):
        raise ValueError('Unsupported audio container')
    digest = hashlib.sha256(data).hexdigest()
    audio_id = 'study_audio_' + hashlib.sha256((run_id+item_id+response_kind+digest).encode()).hexdigest()
    audio_root = Path(audio_root)
    audio_root.mkdir(parents=True,exist_ok=True,mode=0o700)
    path = audio_root/(audio_id+suffix)
    if not path.exists():
        temporary = audio_root/(uuid.uuid4().hex+'.tmp')
        with temporary.open('xb') as f:
            os.chmod(temporary,0o600)
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
        directory = os.open(audio_root,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    conn.execute('INSERT OR IGNORE INTO study_audio(id,run_id,item_id,audio_path,sha256,created_at,response_kind) VALUES(?,?,?,?,?,?,?)',
                 (audio_id,run_id,item_id,str(path),digest,now_ms(),response_kind))
    conn.commit()
    return {'saved': True,'audio_id':audio_id,'bytes':len(data)}


def transcription(conn, body):
    """Worker bookkeeping only; transcripts never become automatic grades."""
    if body.get('claim'):
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("SELECT id,audio_path FROM study_audio WHERE transcription_status='pending' OR (transcription_status='processing' AND transcription_updated_at<?) ORDER BY created_at LIMIT 1",
                           (now_ms()-600000,)).fetchone()
        if row:
            conn.execute("UPDATE study_audio SET transcription_status='processing',transcription_updated_at=? WHERE id=?", (now_ms(),row['id']))
        conn.commit()
        return dict(row) if row else None
    conn.execute('INSERT INTO study_transcriptions VALUES(?,?,?,?,?,?)',
                 (uuid.uuid4().hex,body['audio_id'],now_ms(),encoded(body.get('metadata',{})),body.get('transcript'),body['status']))
    conn.execute('UPDATE study_audio SET transcript=?,transcription_status=?,transcription_updated_at=? WHERE id=?',
                 (body.get('transcript'),body['status'],now_ms(),body['audio_id']))
    conn.commit()
    return {'saved':True}


def summary(conn):
    """Observed study activity, without a mastery score or inferred reading time."""
    focus = status(conn)
    if not focus['active']:
        return {**focus,'events':{},'audio':[],'reading_recordings':0,'recorded_reading_seconds':0}
    study_id = focus['study_id']
    counts = {r['event']:r['n'] for r in conn.execute(
        'SELECT e.event,count(*) n FROM study_events e JOIN study_runs r ON r.id=e.run_id WHERE r.study_id=? GROUP BY e.event', (study_id,))}
    audio = [dict(r) for r in conn.execute(
        'SELECT a.response_kind,a.transcription_status,count(*) count FROM study_audio a JOIN study_runs r ON r.id=a.run_id WHERE r.study_id=? GROUP BY a.response_kind,a.transcription_status', (study_id,))]
    sources = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM study_sources WHERE study_id=?',(study_id,))]
    revision = conn.execute('SELECT id,design_version,created_at FROM study_revisions WHERE study_id=? ORDER BY created_at DESC LIMIT 1',(study_id,)).fetchone()
    return {**focus, 'events':counts,'audio':audio,
        'reading_recordings':sum(s.get('capture_mode')=='continuous_book_open_reading' for s in sources),
        'recorded_reading_seconds':sum(s.get('duration_seconds',0) for s in sources if s.get('capture_mode')=='continuous_book_open_reading'),
        'revision':dict(revision) if revision else None}
