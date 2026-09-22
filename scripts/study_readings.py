"""Reviewed, source-bound Norway readings and deliberate quiz publication."""
import hashlib
import json
import re

from study_engine import STUDY_ID, EXECUTION_COMMIT, active_focus, encoded, now_ms
from study_selection import TOPICS, validate_seed

ID = re.compile(r'[A-Za-z0-9_-]{3,100}\Z')
BRIEF_FIELDS = {'intent_id','source_id','source_quote','question','basis','brief_id',
                'title','text','citations','reviewer','targets'}
TARGET_FIELDS = {'id','topic','question','answer','supporting_claim','citation_url'}


def _hash(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError('A stable reading ID is required')
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} is required')
    return value.strip()


def _https(url):
    if not isinstance(url, str) or not url.startswith('https://') or len(url) > 2000:
        raise ValueError('A verified HTTPS citation is required')
    return url


def _validate(conn, data):
    if not isinstance(data, dict) or not BRIEF_FIELDS <= set(data) or set(data) - BRIEF_FIELDS - {'illustration'}:
        raise ValueError('Reading fields must match the reviewed source-bound contract; parent and depth are server-owned')
    illustration=data.get('illustration')
    if illustration is not None and illustration != 'karveskurd-diagram-v1':
        raise ValueError('Unknown reviewed illustration')
    intent_id, brief_id = _id(data['intent_id']), _id(data['brief_id'])
    source_id = _id(data['source_id'])
    if data['basis'] != 'explicit':
        raise ValueError('The first pilot requires an explicit original wondering')
    source_row = conn.execute('SELECT source,audio_sha256 FROM study_intake WHERE source_id=?', (source_id,)).fetchone()
    if not source_row:
        raise ValueError('Reading source must be an archived original recording')
    source = json.loads(source_row['source'])
    transcript = source.get('transcript', '')
    quote = _text(data['source_quote'], 'Original quote')
    start = transcript.find(quote)
    if start < 0:
        raise ValueError('Original quote must match the archived transcript exactly')
    if transcript.find(quote, start + 1) >= 0:
        raise ValueError('Original quote is ambiguous; use a longer exact span')
    question = _text(data['question'], 'Bounded question')
    title = _text(data['title'], 'Title')
    body = _text(data['text'], 'Reading text')
    if not 100 <= len(body.split()) <= 350:
        raise ValueError('Reading must stay near the 150–300 word pilot range')
    reviewer = _text(data['reviewer'], 'Reviewer')
    citations = data['citations']
    if not isinstance(citations, list) or not 1 <= len(citations) <= 8:
        raise ValueError('Reading needs checked citations')
    for citation in citations:
        if not isinstance(citation, dict) or set(citation) != {'title','url'}:
            raise ValueError('Citation needs only title and URL')
        _text(citation['title'], 'Citation title'); _https(citation['url'])
    targets = data['targets']
    if not isinstance(targets, list) or len(targets) > 3:
        raise ValueError('At most three optional quiz targets per reading')
    if len({_id(t.get('id')) for t in targets if isinstance(t, dict)}) != len(targets):
        raise ValueError('Duplicate quiz target')
    urls = {citation['url'] for citation in citations}
    for target in targets:
        if not isinstance(target, dict) or set(target) != TARGET_FIELDS:
            raise ValueError('Quiz target fields must match the reviewed contract')
        if target['topic'] not in TOPICS or target['topic'] == 'all':
            raise ValueError('Quiz target has unknown topic')
        for field in ('question','answer','supporting_claim'):
            _text(target[field], field)
        if target['supporting_claim'] not in body:
            raise ValueError('Quiz target must quote an exact supporting claim from the brief')
        if _https(target['citation_url']) not in urls:
            raise ValueError('Quiz target citation must belong to its brief')
    intent = {'id':intent_id,'study_id':STUDY_ID,'source_id':source_id,
              'audio_sha256':source_row['audio_sha256'],
              'transcript_sha256':hashlib.sha256(transcript.encode()).hexdigest(),
              'source_quote':quote,
              'source_start':start,'source_end':start+len(quote),'question':question,'basis':'explicit'}
    brief = {'id':brief_id,'intent_id':intent_id,'title':title,'text':body,
             'citations':citations,'reviewer':reviewer,'source_id':source_id,
             'question':question,'targets':[t['id'] for t in targets],
             'content_origin':'reviewed_explanation','depth':1,
             'illustration':illustration}
    return intent, brief, targets


def import_reviewed(conn, body):
    """Private operator path: transactionally import immutable reviewed content."""
    entries = body.get('readings') if isinstance(body, dict) else None
    if not isinstance(entries, list) or not 1 <= len(entries) <= 20:
        raise ValueError('Import requires a bounded readings list')
    conn.execute('BEGIN IMMEDIATE')
    try:
        added = []
        for data in entries:
            intent, brief, targets = _validate(conn, data)
            old_intent = conn.execute('SELECT * FROM study_reading_intents WHERE id=?', (intent['id'],)).fetchone()
            if old_intent:
                if any(old_intent[k] != v for k,v in intent.items()):
                    raise ValueError('Original intent identity changed')
            else:
                conn.execute('''INSERT INTO study_reading_intents VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                             (*intent.values(),now_ms()))
            old_brief = conn.execute('SELECT payload,content_sha256 FROM study_reading_briefs WHERE id=?',(brief['id'],)).fetchone()
            brief_hash = _hash(brief)
            if old_brief:
                if old_brief['content_sha256'] != brief_hash:
                    raise ValueError('Brief ID changed content; publish a new version ID')
            else:
                conn.execute('UPDATE study_reading_briefs SET active=0 WHERE intent_id=?',(intent['id'],))
                conn.execute('INSERT INTO study_reading_briefs VALUES(?,?,?,?,1,?)',
                             (brief['id'],intent['id'],encoded(brief),brief_hash,now_ms()))
                added.append(brief['id'])
            for target in targets:
                target_hash = _hash(target)
                prior = conn.execute('SELECT content_sha256 FROM study_reading_targets WHERE id=?',(target['id'],)).fetchone()
                if prior and prior['content_sha256'] != target_hash:
                    raise ValueError('Target ID changed content; use a new target ID')
                conn.execute('INSERT OR IGNORE INTO study_reading_targets VALUES(?,?,?)',
                             (target['id'],encoded(target),target_hash))
                conn.execute('INSERT OR IGNORE INTO study_reading_brief_targets VALUES(?,?)',
                             (brief['id'],target['id']))
        conn.commit()
        return {'added':added,'duplicate':not added}
    except Exception:
        conn.rollback(); raise


def catalogue(conn):
    if not active_focus(conn):
        raise ValueError('Study focus is not active')
    result=[]
    for row in conn.execute('''SELECT b.payload,b.content_sha256,i.source_quote,i.source_id,i.transcript_sha256,
                       i.source_start,i.source_end,s.source
        FROM study_reading_briefs b JOIN study_reading_intents i ON i.id=b.intent_id
        JOIN study_intake s ON s.source_id=i.source_id
        WHERE b.active=1 AND i.study_id=? ORDER BY b.created_at,b.rowid''',(STUDY_ID,)):
        brief=json.loads(row['payload'])
        source=json.loads(row['source'])
        targets=[]
        for target_row in conn.execute('''SELECT t.payload,sel.item_id FROM study_reading_brief_targets bt
            JOIN study_reading_targets t ON t.id=bt.target_id
            LEFT JOIN study_reading_selections sel ON sel.target_id=t.id
            WHERE bt.brief_id=? ORDER BY bt.rowid''',(brief['id'],)):
            target=json.loads(target_row['payload'])
            target['selected']=target_row['item_id'] is not None
            targets.append(target)
        result.append({**brief,'content_sha256':row['content_sha256'],
            'source_quote':row['source_quote'],'source_id':row['source_id'],
            'source_node_id':source.get('journal_node_id'),
            'source_url':source.get('tana_link'),
            'source_title':source.get('title') or source.get('journal_title'),
            'source_date':source.get('tana_created_at') or source.get('recorded_at') or source.get('date'),
            'targets':targets})
    return {'readings':result}


def select(conn, body):
    if not active_focus(conn):
        raise ValueError('Study focus is not active')
    if not isinstance(body, dict) or set(body) != {'brief_id','target_ids'}:
        raise ValueError('Select only targets from a reviewed brief')
    brief_id = _id(body['brief_id'])
    ids = body['target_ids']
    if not isinstance(ids,list) or not ids or len(ids)>3 or len(set(ids))!=len(ids):
        raise ValueError('Select one to three distinct targets')
    conn.execute('BEGIN IMMEDIATE')
    try:
        brief_row=conn.execute('SELECT * FROM study_reading_briefs WHERE id=? AND active=1',(brief_id,)).fetchone()
        if not brief_row:
            raise ValueError('Unknown or superseded reading')
        allowed={r[0] for r in conn.execute('SELECT target_id FROM study_reading_brief_targets WHERE brief_id=?',(brief_id,))}
        if not set(ids)<=allowed:
            raise ValueError('Target does not belong to this reading')
        added=[]; selected=[]
        intent=conn.execute('SELECT * FROM study_reading_intents WHERE id=?',(brief_row['intent_id'],)).fetchone()
        source=json.loads(conn.execute('SELECT source FROM study_intake WHERE source_id=?',(intent['source_id'],)).fetchone()[0])
        if hashlib.sha256(source.get('transcript','').encode()).hexdigest() != intent['transcript_sha256']:
            raise ValueError('Original transcript revision changed; review this reading before selection')
        ordinal=conn.execute('SELECT coalesce(max(ordinal),-1)+1 FROM study_items').fetchone()[0]
        for target_id in ids:
            prior=conn.execute('SELECT item_id FROM study_reading_selections WHERE target_id=?',(target_id,)).fetchone()
            if prior:
                selected.append(prior['item_id']);continue
            target=json.loads(conn.execute('SELECT payload FROM study_reading_targets WHERE id=?',(target_id,)).fetchone()[0])
            item_id='no-reading-'+target_id
            pos_id=item_id+'-p0'
            item={'id':item_id,'kind':'prompt','title':target['question'],'ordinal':ordinal+len(added),
                  'family_id':target_id,'topic':target['topic'],'intended_depth':'independent_main_idea',
                  'sources':[{'recording':intent['source_id'],'source_id':intent['source_id'],
                      'tana_link':source['tana_link'],'source_quote':intent['source_quote'],
                      'authorship':'explicit_wondering','evidence_type':'question_only'}],
                  'references':[{'title':c['title'],'url':c['url']} for c in json.loads(brief_row['payload'])['citations']],
                  'positions':[{'position_id':pos_id,'question_text':target['question'],
                      'answer_text':target['answer'],'testable':True}],
                  'reading_brief_id':brief_id,'target_id':target_id,
                  'content_authorship':'reviewed_explanation','reviewer':json.loads(brief_row['payload'])['reviewer']}
            # Full current catalogue remains valid and old snapshots stay frozen.
            conn.execute('INSERT INTO study_items(id,study_id,version,kind,payload,ordinal) VALUES(?,?,?,?,?,?)',
                         (item_id,STUDY_ID,'reading-quiz-v1','prompt',encoded(item),item['ordinal']))
            conn.execute('INSERT INTO study_positions(id,item_id,testable) VALUES(?,?,1)',(pos_id,item_id))
            conn.execute('INSERT INTO study_reading_selections VALUES(?,?,?)',(target_id,item_id,now_ms()))
            added.append(item_id);selected.append(item_id)
        # Validate the resulting item graph before committing.
        all_items=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM study_items WHERE study_id=? AND suspended=0',(STUDY_ID,))]
        validate_seed({'items':all_items})
        conn.commit()
        return {'added':added,'selected':selected,'already_selected':len(ids)-len(added)}
    except Exception:
        conn.rollback();raise
