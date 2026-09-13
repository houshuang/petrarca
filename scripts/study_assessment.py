"""Frozen, unaided-first observations. No answer keys, grades or memory writes."""
import hashlib
import json
from pathlib import Path

PROTOCOL_PATH = Path(__file__).resolve().parents[1]/'research/norway-reading-study/assessment-v1.json'
TYPES = ('current', 'before_volume', 'volume_end', 'delayed', 'project_end')
CONFIDENCE = ('sure', 'unsure', 'unknown')
OUTCOMES = ('recorded', 'unknown', 'skipped', 'interrupted')


def protocol():
    return json.loads(PROTOCOL_PATH.read_text())


def start(conn, body):
    from study_engine import STUDY_ID, EXECUTION_COMMIT, encoded, now_ms, active_focus
    if not active_focus(conn):
        raise ValueError('Study focus is not active')
    config = body.get('assessment', {})
    volume = config.get('volume')
    if type(volume) is not int or not 1 <= volume <= 12:
        raise ValueError('Choose a volume from 1 to 12')
    if config.get('occasion') not in TYPES or config.get('help_state') not in ('closed', 'supported'):
        raise ValueError('Declare assessment occasion and help state')
    if not isinstance(config.get('coverage'), str) or not 1 <= len(config['coverage'].strip()) <= 200:
        raise ValueError('Describe pages or chapters covered')
    run_id = body['request_id']
    prior = conn.execute('SELECT * FROM study_runs WHERE id=?', (run_id,)).fetchone()
    if prior:
        snapshot = json.loads(prior['snapshot'])
        if prior['mode'] != 'assessment' or snapshot['assessment'] != config:
            raise ValueError('Assessment retry changed context')
        return snapshot
    frozen = protocol()
    prompts = list(frozen['core'])
    if config['occasion'] in ('volume_end', 'project_end'):
        sentinel = json.loads((PROTOCOL_PATH.parent/'sentinel-questions-v1.json').read_text())
        # Rotate a bounded pair, preserving the exact selected prompts in the run.
        start_index = ((volume-1)*2) % len(sentinel['questions'])
        for offset in range(2):
            q = sentinel['questions'][(start_index+offset) % len(sentinel['questions'])]
            prompts.append({'id': q['id'], 'title': q['label'], 'text':
                q['prompt_no']+' Har svaret ditt endret seg? Hva endret det?',
                'max_seconds': 60, 'confidence': False, 'source': q})
    items = [{**p, 'id': 'assessment-'+p['id'], 'kind': 'voice'} for p in prompts]
    result = {'run_id':run_id, 'items':items, 'assessment':config, 'protocol':frozen,
              'protocol_sha256':hashlib.sha256(encoded(frozen).encode()).hexdigest(),
              'rubric':json.loads((PROTOCOL_PATH.parent/'rubric-v1.json').read_text()),
              'execution_commit':EXECUTION_COMMIT, 'client_context':body.get('client_context',{})}
    conn.execute('INSERT INTO study_runs VALUES(?,?,?,?,?)',
                 (run_id,STUDY_ID,now_ms(),'assessment',encoded(result)))
    conn.execute('INSERT INTO study_assessments VALUES(?,?,?,?,?,?,?)',
                 (run_id,config['occasion'],volume,config['coverage'],config['help_state'],frozen['version'],now_ms()))
    return result


def completed(conn, run_id):
    return [r[0] for r in conn.execute("SELECT item_id FROM study_events WHERE run_id=? AND event='assessment_advance' ORDER BY rowid", (run_id,))]


def current_item(conn, run_id, snapshot):
    done = set(completed(conn, run_id))
    return next((p for p in snapshot['items'] if p['id'] not in done), None)


def handle_event(conn, body, item, snapshot):
    from study_engine import EXECUTION_COMMIT
    action = body['event']
    allowed = ('shown','feedback','recording_started','recording_stopped','recording_failed',
               'audio_uploaded','audio_upload_failed','audio_played','backgrounded','foregrounded',
               'session_left','assessment_advance')
    if action not in allowed or body.get('results'):
        raise ValueError('Assessments have no answer reveal or grades')
    detail = body.get('detail', {})
    if action == 'assessment_advance':
        current = current_item(conn,body['run_id'],snapshot)
        if not current or item['id'] != current['id']:
            raise ValueError('Answer the unaided account before the fixed cues')
        outcome = detail.get('outcome')
        if outcome not in OUTCOMES:
            raise ValueError('Declare recorded, unknown, skipped or interrupted')
        if outcome == 'recorded' and not conn.execute(
                "SELECT 1 FROM study_audio WHERE run_id=? AND item_id=? AND response_kind='recall'",
                (body['run_id'],item['id'])).fetchone():
            raise ValueError('Save the recording before continuing')
        if item.get('confidence') and outcome == 'recorded':
            validate_confidence(conn,body['run_id'],item['id'])
    if action == 'feedback' and detail.get('dimension') == 'assessment_confidence':
        if detail.get('value') not in CONFIDENCE:
            raise ValueError('Invalid confidence')
        if conn.execute("SELECT 1 FROM study_audio WHERE run_id=? AND item_id=?",(body['run_id'],item['id'])).fetchone():
            raise ValueError('Confidence must precede the recording upload')
    return {'saved':True,'scheduled':False,'execution_commit':EXECUTION_COMMIT,
            'scheduling_policy':'assessment-no-fsrs-v1','protocol_version':snapshot['protocol']['version']}


def validate_confidence(conn, run_id, item_id):
    rows = conn.execute("SELECT payload FROM study_events WHERE run_id=? AND item_id=? AND event='feedback'",(run_id,item_id))
    if not any(json.loads(r[0]).get('detail',{}).get('dimension')=='assessment_confidence' and
               json.loads(r[0]).get('detail',{}).get('value') in CONFIDENCE for r in rows):
        raise ValueError('Record confidence before this response')


def validate_audio(conn, run_id, item, snapshot):
    current = current_item(conn,run_id,snapshot)
    if not current or item['id'] != current['id']:
        raise ValueError('This assessment prompt is not current')
    if item.get('confidence'):
        validate_confidence(conn,run_id,item['id'])
