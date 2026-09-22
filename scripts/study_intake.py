"""Source-bound intake ledger and append-only publication through the canonical DB."""
import hashlib
import json
import re
from study_engine import STUDY_ID, EXECUTION_COMMIT, encoded, now_ms
from study_selection import V2, POLICY_V2, validate_seed, TOPICS


def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()


def corpus_snapshot(conn):
    """Current publication surface, without learner events or mutable schedules."""
    own_transaction=not conn.in_transaction
    if own_transaction:conn.execute('BEGIN')
    try:
        return _corpus_snapshot_rows(conn)
    finally:
        if own_transaction:conn.rollback()


def _corpus_snapshot_rows(conn):
    items=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM study_items WHERE study_id=? ORDER BY id',(STUDY_ID,))]
    readings=[dict(json.loads(r['payload']),active=bool(r['active']),content_sha256=r['content_sha256'])
              for r in conn.execute('SELECT payload,active,content_sha256 FROM study_reading_briefs ORDER BY id')]
    targets=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM study_reading_targets ORDER BY id')]
    sources=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM study_sources WHERE study_id=? ORDER BY id',(STUDY_ID,))]
    originals=[{'source_id':r['source_id'],'audio_sha256':r['audio_sha256'],
                'source_sha256':digest(json.loads(r['source']))}
               for r in conn.execute('SELECT source_id,audio_sha256,source FROM study_intake ORDER BY source_id')]
    intents=[dict(r) for r in conn.execute('SELECT * FROM study_reading_intents ORDER BY id')]
    payload={'items':items,'readings':readings,'targets':targets,'sources':sources,
             'originals':originals,'intents':intents}
    return {**payload,'corpus_sha256':digest(payload)}


def log(conn,source_id,state,detail):
    conn.execute('INSERT INTO study_intake_events(source_id,state,created_at,payload) VALUES(?,?,?,?)',
                 (source_id,state,now_ms(),encoded(detail)))


def register(conn, source):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',source.get('id','')):raise ValueError('Stable source ID required')
    if not re.fullmatch(r'[a-f0-9]{64}',source.get('audio_sha256','')):raise ValueError('Archive audio before registration')
    if not source.get('journal_node_id') or not source.get('tana_link','').startswith('https://app.tana.inc/'):
        raise ValueError('Original Tana identity required')
    if source.get('volume') is not None and (type(source['volume']) is not int or not 1<=source['volume']<=12):
        raise ValueError('Volume must be 1–12 or unresolved')
    if 'audio_url' in source:raise ValueError('Do not persist signed download URLs in runtime metadata')
    conn.execute('BEGIN IMMEDIATE')
    try:
        prior=conn.execute('SELECT * FROM study_intake WHERE audio_sha256=? OR source_id=?',
                           (source['audio_sha256'],source['id'])).fetchone()
        if prior:
            if prior['audio_sha256']!=source['audio_sha256']:raise ValueError('Source ID changed audio')
            old=json.loads(prior['source'])
            if {k:v for k,v in old.items() if k!='id'}!={k:v for k,v in source.items() if k!='id'}:
                raise ValueError('Existing original metadata or transcript changed; reconcile as a revision')
            conn.rollback();return {'source_id':prior['source_id'],'state':prior['state'],'duplicate':True}
        # Existing published source registrations are recognised without generating duplicate cards.
        existing=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM study_sources WHERE study_id=?',(STUDY_ID,))]
        if any(s.get('id')==source['id'] and s.get('audio_sha256')!=source['audio_sha256'] for s in existing):
            raise ValueError('Published source identity changed audio')
        published=any(s.get('audio_sha256')==source['audio_sha256'] for s in existing)
        state='published' if published else 'archived'
        conn.execute('INSERT INTO study_intake VALUES(?,?,?,?,?,?,?)',
                     (source['id'],source['audio_sha256'],state,encoded(source),None,now_ms(),now_ms()))
        log(conn,source['id'],state,{'basis':'existing published source' if published else 'verified archive','execution_commit':EXECUTION_COMMIT})
        conn.commit();return {'source_id':source['id'],'state':state,'duplicate':published}
    except Exception:conn.rollback();raise


def record_draft(conn, body):
    conn.execute('BEGIN IMMEDIATE')
    try:
        result = _record_draft(conn, body)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def _record_draft(conn, body):
    source_id=body['source_id'];draft=body['draft']
    row=conn.execute('SELECT * FROM study_intake WHERE source_id=?',(source_id,)).fetchone()
    if not row or row['state']=='published':raise ValueError('Source unavailable or already published')
    source=json.loads(row['source'])
    _validate_draft(source,draft)
    signature=digest(draft)
    conn.execute('UPDATE study_intake SET state=?,draft=?,updated_at=? WHERE source_id=?',('drafted',encoded(draft),now_ms(),source_id))
    log(conn,source_id,'drafted',{'draft_sha256':signature,'candidates':len(draft['candidates']),'execution_commit':EXECUTION_COMMIT})
    return {'source_id':source_id,'state':'drafted','draft_sha256':signature}


def _validate_draft(source,draft):
    transcript=source.get('transcript','')
    for candidate in draft.get('candidates',[]):
        if candidate.get('kind') not in ('term','prompt','voice'):raise ValueError('Unsupported draft kind')
        if candidate.get('topic') not in TOPICS:raise ValueError('Unknown topic')
        quote=candidate.get('source_quote','')
        if not quote or quote not in transcript:raise ValueError('Candidate must cite an exact source span')
        if not all(isinstance(candidate.get(k),str) and candidate[k].strip() for k in ('title','question','answer')):
            raise ValueError('Candidate missing content')
        if not candidate.get('references') or any(not r.get('url','').startswith('https://') for r in candidate['references']):
            raise ValueError('External reference required for review')
    if 'candidates' not in draft or len(draft['candidates'])>20:raise ValueError('Expected bounded candidate list')


def publish(conn, body):
    conn.execute('BEGIN IMMEDIATE')
    try:
        row=conn.execute('SELECT * FROM study_intake WHERE source_id=?',(body['source_id'],)).fetchone()
        amend=body.get('amend') is True
        if not row or (not amend and not row['draft']):raise ValueError('No draft to publish')
        if amend and row['state']!='published':raise ValueError('Only a published source can be amended')
        draft=body.get('draft') if amend else json.loads(row['draft'])
        if amend:_validate_draft(json.loads(row['source']),draft)
        if digest(draft)!=body.get('reviewed_sha256') or not body.get('reviewer'):
            raise ValueError('Exact reviewed draft hash and reviewer required')
        if not amend and row['state'] not in ('drafted','published'):
            raise ValueError('Resolve failed processing before publishing')
        if amend and 'accepted_indices' not in body:
            raise ValueError('Amendment requires explicit reviewed candidate selection')
        candidates=draft['candidates']
        if 'accepted_indices' in body:
            accepted=body['accepted_indices']
            if not isinstance(accepted,list) or any(type(i) is not int or i<0 or i>=len(candidates) for i in accepted) or len(set(accepted))!=len(accepted):
                raise ValueError('Invalid reviewed candidate selection')
            decisions=body.get('review_decisions')
            if not isinstance(decisions,list) or len(decisions)!=len(candidates):
                raise ValueError('Independent review must cover every candidate')
            by_index={d.get('index'):d for d in decisions if isinstance(d,dict) and type(d.get('index')) is int}
            if set(by_index)!=set(range(len(candidates))) or len(by_index)!=len(decisions):
                raise ValueError('Missing or duplicated review verdict')
            for i,decision in by_index.items():
                if decision.get('verdict') not in ('accept','reject','hold') or not isinstance(decision.get('reason'),str) or not decision['reason'].strip():
                    raise ValueError('Unknown or unexplained review verdict')
                if (i in accepted)!=(decision['verdict']=='accept'):
                    raise ValueError('Accepted selection disagrees with review')
            if not body.get('review_packet_sha256') or not body.get('expected_corpus_sha256'):
                raise ValueError('Reviewed packet and corpus binding required')
            packet={'draft_sha256':digest(draft),'corpus_sha256':body['expected_corpus_sha256'],
                    'decisions':decisions,'accepted_indices':accepted}
            if body['review_packet_sha256']!=digest(packet):
                raise ValueError('Review packet hash does not match verdicts')
        else:
            accepted=list(range(len(candidates)))  # Legacy exact-hash operator remains compatible.
        if row['state']=='published' and not amend:
            if 'accepted_indices' in body:
                receipt=action(conn,{'op':'receipt','source_id':body['source_id'],
                                     'review_packet_sha256':body['review_packet_sha256']})
                if not receipt['found']:raise ValueError('Published source has a different review packet')
            conn.rollback();return {'state':'published','duplicate':True}
        if amend:
            receipt=action(conn,{'op':'receipt','source_id':body['source_id'],
                                 'review_packet_sha256':body['review_packet_sha256']})
            if receipt['found']:
                conn.rollback();return {'state':'published','duplicate':True,'added':[]}
        if 'expected_corpus_sha256' in body and body['expected_corpus_sha256']!=corpus_snapshot(conn)['corpus_sha256']:
            raise ValueError('Canonical corpus changed since review')
        source=json.loads(row['source'])
        prior=[json.loads(r[0]) for r in conn.execute('SELECT payload FROM study_items WHERE study_id=? AND suspended=0 ORDER BY ordinal',(STUDY_ID,))]
        ordinal=conn.execute('SELECT coalesce(max(ordinal),-1)+1 FROM study_items').fetchone()[0]
        existing={(i['title'].casefold(),p.get('question_text','').casefold()) for i in prior for p in i['positions']}
        added=[]
        for n in accepted:
            c=candidates[n]
            key=(c['title'].casefold(),c['question'].casefold())
            if key in existing:continue
            existing.add(key);item_id='no-intake-'+digest(draft)[:12]+'-'+str(n)
            added.append({'id':item_id,'kind':c['kind'],'title':c['title'],'ordinal':ordinal+len(added),
              'family_id':item_id,'topic':c['topic'],'intended_depth':'recognition_and_rough_meaning' if c['kind']=='term' else 'main_idea',
              'introduction':c['answer'] if c['kind']=='term' else '',
              'sources':[{'recording':source['id'],'source_id':source['id'],'tana_link':source['tana_link'],
                          'source_quote':c['source_quote'],'authorship':'unresolved_book_or_reader','evidence_type':'exposure_only'}],
              'references':c['references'],'positions':[{'position_id':item_id+'-p0','question_text':c['question'],'answer_text':c['answer'],'testable':True}],
              'content_authorship':'codex_draft_source_checked','reviewer':body['reviewer'],'draft_sha256':digest(draft)})
        seed={'study_id':STUDY_ID,'version':'intensive-v2','items':prior+added};validate_seed(seed)
        for item in added:
            conn.execute('INSERT INTO study_items(id,study_id,version,kind,payload,ordinal) VALUES(?,?,?,?,?,?)',
                         (item['id'],STUDY_ID,'intake-v1',item['kind'],encoded(item),item['ordinal']))
            conn.execute('INSERT INTO study_positions(id,item_id,testable) VALUES(?,?,1)',(item['positions'][0]['position_id'],item['id']))
        saved_source={k:v for k,v in source.items() if k!='transcript'}
        conn.execute('INSERT OR IGNORE INTO study_sources VALUES(?,?,?)',(source['id'],STUDY_ID,encoded(saved_source)))
        revision={'seed':seed,'policy':POLICY_V2,'intake_source':source['id'],'reviewed_sha256':digest(draft),'reviewer':body['reviewer']}
        if amend:revision['amendment']=True
        if 'accepted_indices' in body:
            revision.update(accepted_indices=accepted,review_packet_sha256=body['review_packet_sha256'],
                            prior_corpus_sha256=body['expected_corpus_sha256'],review_decisions=body['review_decisions'])
        conn.execute('INSERT OR IGNORE INTO study_revisions VALUES(?,?,?,?,?,?)',
                     (digest(revision),STUDY_ID,now_ms(),EXECUTION_COMMIT,V2,encoded(revision)))
        if not amend:
            conn.execute('UPDATE study_intake SET state=?,updated_at=? WHERE source_id=?',('published',now_ms(),source['id']))
        log(conn,source['id'],'amended' if amend else 'published',{'items':[i['id'] for i in added],'reviewer':body['reviewer'],'draft_sha256':digest(draft),
                                          'review_packet_sha256':body.get('review_packet_sha256')})
        conn.commit();return {'state':'published','added':[i['id'] for i in added]}
    except Exception:conn.rollback();raise


def action(conn, body):
    op=body['op']
    if op=='register':return register(conn,body['source'])
    if op=='draft':return record_draft(conn,body)
    if op=='publish':return publish(conn,body)
    if op=='amend':return publish(conn,{**body,'amend':True})
    if op=='source':
        row=conn.execute('SELECT source,draft FROM study_intake WHERE source_id=?',(body['source_id'],)).fetchone()
        if not row:raise ValueError('Unknown source')
        return {'source':json.loads(row['source']),'draft':json.loads(row['draft']) if row['draft'] else None}
    if op=='status':return [dict(r) for r in conn.execute('''SELECT source_id,state,created_at,updated_at,
        (SELECT payload FROM study_intake_events e WHERE e.source_id=study_intake.source_id ORDER BY e.id DESC LIMIT 1) AS last_event
        FROM study_intake ORDER BY created_at''' )]
    if op=='snapshot':return corpus_snapshot(conn)
    if op=='receipt':
        source_id=body['source_id'];packet_sha=body['review_packet_sha256']
        for row in conn.execute("SELECT state,payload FROM study_intake_events WHERE source_id=? AND state IN ('published','amended') ORDER BY id DESC",(source_id,)):
            detail=json.loads(row['payload'])
            if detail.get('review_packet_sha256')==packet_sha:
                return {'found':True,'state':row['state'],'detail':detail}
        return {'found':False}
    if op=='failed':
        row=conn.execute('SELECT state FROM study_intake WHERE source_id=?',(body['source_id'],)).fetchone()
        if not row:raise ValueError('Unknown source')
        if row['state']=='published':return {'state':'published'}
        log(conn,body['source_id'],'failed',{'error':body.get('error','processing_failed')})
        conn.execute("UPDATE study_intake SET state='failed',updated_at=? WHERE source_id=? AND state!='published'",(now_ms(),body['source_id']))
        conn.commit();return {'state':'failed'}
    raise ValueError('Unknown intake operation')
