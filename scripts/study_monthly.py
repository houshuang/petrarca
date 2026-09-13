"""Once-per-month reproducible sample of completed-volume assessments."""
import datetime
import json
import random
import re
import secrets
from study_engine import encoded, now_ms
from study_assessment import protocol, completed


def sample(conn, body):
    current_month=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m')
    month=body.get('month',current_month)
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',month):raise ValueError('Month must be YYYY-MM')
    conn.execute('BEGIN IMMEDIATE')
    try:
        prior=conn.execute('SELECT payload FROM study_monthly_samples WHERE month=?',(month,)).fetchone()
        if prior:conn.rollback();return json.loads(prior[0])
        if month!=current_month:raise ValueError('Do not backfill missed months or sample future months')
        universe={}
        for row in conn.execute("SELECT a.*,r.snapshot FROM study_assessments a JOIN study_runs r ON r.id=a.run_id WHERE a.occasion='volume_end' ORDER BY a.created_at"):
            snapshot=json.loads(row['snapshot'])
            if len(completed(conn,row['run_id']))==len(snapshot['items']):universe[row['volume']]=dict(row)
        if not universe:conn.rollback();return {'month':month,'status':'waiting_for_completed_volume','volumes':[]}
        seed=body.get('seed',secrets.randbits(52));rng=random.Random(seed)
        chosen=rng.sample(sorted(universe),min(3,len(universe)));cue_pool=protocol()['core'][1:]
        observations=[]
        for volume in chosen:
            source_ids=set();metadata=[]
            for r in conn.execute('SELECT id,payload FROM study_sources'):
                source=json.loads(r['payload'])
                if source.get('volume')==volume:
                    source_ids.add(r['id'])
                    if source.get('tana_created_at'):metadata.append(source['tana_created_at'])
            item_ids=[]
            for r in conn.execute('SELECT id,payload FROM study_items'):
                if any(s.get('source_id',s.get('recording')) in source_ids for s in json.loads(r['payload']).get('sources',[])):item_ids.append(r['id'])
            latest=None
            if item_ids:
                latest=conn.execute("SELECT max(created_at) FROM study_events WHERE item_id IN ("+','.join('?' for _ in item_ids)+") AND event IN ('introduced','position_revealed','complete','shown')",item_ids).fetchone()[0]
            # Current visual references concern volume 1, even when opened outside a card.
            reference_latest=conn.execute("SELECT max(e.created_at) FROM study_events e JOIN study_runs r ON r.id=e.run_id WHERE r.mode='reference' AND e.event IN ('shown','revealed')").fetchone()[0] if volume==1 else None
            observations.append({'volume':volume,'completed_assessment':universe[volume]['run_id'],
                'completion_observed_at':conn.execute("SELECT max(created_at) FROM study_events WHERE run_id=? AND event='assessment_advance'",(universe[volume]['run_id'],)).fetchone()[0],'cue':rng.choice(cue_pool),
                'last_recorded_card_exposure_at':latest,'last_reference_exposure_at':reference_latest,
                'last_reading_source_metadata_at':max(metadata) if metadata else None,
                'outside_exposure':'unknown unless separately reported'})
        result={'month':month,'status':'sampled','seed':seed,'eligible_volumes':sorted(universe),'volumes':observations,
                'sampled_at':now_ms(),'protocol_version':protocol()['version'],
                'instruction':'Up to ten minutes total. Ask the frozen cue for each selected volume without answers. Log actual recording/help state; missed months are not made up. These are observations under maintenance.'}
        conn.execute('INSERT INTO study_monthly_samples VALUES(?,?,?)',(month,now_ms(),encoded(result)))
        conn.commit();return result
    except Exception:conn.rollback();raise
