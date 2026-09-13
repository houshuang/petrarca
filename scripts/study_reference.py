"""Immutable, on-demand reference exposures; never changes a practice payload."""
import json
from pathlib import Path

PATH=Path(__file__).resolve().parents[1]/'research/norway-reading-study/learning-aids-v1.json'

def start(conn,body):
    from study_engine import STUDY_ID, EXECUTION_COMMIT, encoded, now_ms
    aid=body.get('aid')
    prior=conn.execute('SELECT mode,snapshot FROM study_runs WHERE id=?',(body['request_id'],)).fetchone()
    if prior:
        snapshot=json.loads(prior['snapshot'])
        if prior['mode']!='reference' or snapshot['aid']!=aid:raise ValueError('Reference retry changed input')
        return snapshot
    content=json.loads(PATH.read_text())
    item=next((i for i in content['items'] if i['id']==aid),None)
    if not item:raise ValueError('Unknown reference')
    item={**item,'id':'reference-'+aid,'positions':[],'needs_introduction':False}
    result={'run_id':body['request_id'],'aid':aid,'items':[item],
            'reference':content,'execution_commit':EXECUTION_COMMIT,'client_context':body.get('client_context',{})}
    conn.execute('INSERT INTO study_runs VALUES(?,?,?,?,?)',(body['request_id'],STUDY_ID,now_ms(),'reference',encoded(result)))
    return result
