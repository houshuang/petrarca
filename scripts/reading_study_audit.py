#!/usr/bin/env python3
"""Audit an immutable study export; never connect to or modify production."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path


def audit(root):
    root = Path(root)
    manifest = json.loads((root/'manifest.json').read_text())
    tables = {}
    for name, expected in manifest['files'].items():
        data = (root/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise ValueError('Export checksum mismatch: '+name)
        tables[name.removesuffix('.jsonl')] = [json.loads(line) for line in data.splitlines()]
    events = tables['study_events']
    runs = {r['id']: json.loads(r['snapshot']) for r in tables['study_runs']}
    items = {r['id']: json.loads(r['payload']) for r in tables['study_items']}
    expected_counts = Counter()
    latest = {}
    seen_terminals = set()
    revealed = set()
    errors = []
    scores = Counter()
    item_results = {}
    for e in events:
        body, result = json.loads(e['payload']), json.loads(e['result'])
        key = (e['run_id'],e['item_id'])
        snapshot = runs[e['run_id']]
        item = next((i for i in snapshot['items'] if i['id']==e['item_id']),None)
        if not item:
            errors.append('Event item outside frozen run: '+e['id'])
            continue
        if e['event']=='position_revealed':
            revealed.add((*key,body.get('detail',{}).get('position_id')))
        if e['event'] in ('introduced','complete'):
            terminal=(*key,e['event'])
            if terminal in seen_terminals:errors.append('Duplicate terminal: '+e['id'])
            seen_terminals.add(terminal)
        if e['event']!='complete':continue
        grades=body.get('results',[])
        should_schedule=(body.get('detail',{}).get('book_state')=='closed' and
                         snapshot.get('practice')!='extra' and item.get('scheduling_eligible',True))
        if bool(result.get('scheduled'))!=should_schedule:errors.append('Scheduling eligibility mismatch: '+e['id'])
        if item.get('needs_introduction'):errors.append('Introduction graded: '+e['id'])
        allowed={p['position_id'] for p in item['positions'] if p.get('testable',True)}
        for g in grades:
            pos=g['position_id'];scores[g['score']]+=1
            if pos not in allowed:errors.append('Anchor or foreign position graded: '+e['id'])
            if (*key,pos) not in revealed:errors.append('Grade without earlier reveal: '+e['id'])
            if result.get('scheduled'):
                expected_counts[pos]+=1;latest[pos]=(g['score'],e['created_at'])
        item_results[e['item_id']]={'title':item['title'],'scores':[g['score'] for g in grades],
                                    'at':body.get('client_time',e['created_at']),'evidence':'self_report'}
    for p in tables['study_positions']:
        if p['review_count']!=expected_counts[p['id']]:errors.append('Review count mismatch: '+p['id'])
        if p['id'] not in latest:continue
        score,time=latest[p['id']]
        if p['last_score']!=score:errors.append('Latest grade mismatch: '+p['id'])
        if abs(p['last_reviewed_at']-time)>1000:errors.append('Latest review time mismatch: '+p['id'])
        card=json.loads(p['fsrs_card_json'])
        due=int(datetime.fromisoformat(card['due']).timestamp()*1000)
        if abs(due-p['due_at'])>1:errors.append('FSRS due mismatch: '+p['id'])
        if abs((card['stability'] or 1)-p['stability_days'])>1e-6:errors.append('FSRS stability mismatch: '+p['id'])
    familiarity=[]
    for e in events:
        body=json.loads(e['payload']);d=body.get('detail',{})
        if e['event']=='feedback' and d.get('dimension')=='term_recognition' and d.get('phase')=='before_introduction':
            familiarity.append({'title':items[e['item_id']]['title'],'value':d['value']})
    counts=Counter(e['event'] for e in events)
    return {'exported_at_ms':manifest['created_at_ms'],'integrity_errors':errors,
            'events':dict(counts),'runs':len(runs),'completed_cards':counts['complete'],
            'distinct_completed_cards':len(item_results),'graded_parts':dict(scores),
            'scheduled_parts':sum(expected_counts.values()),'introduced':counts['introduced'],
            'audio_recordings':len(tables['study_audio']),'assessments':len(tables['study_assessments']),
            'latest_self_reports':list(item_results.values()),'pre_introduction_familiarity':familiarity,
            'exposure_warnings':{'shown_while_context_unknown':sum(e['event'] in ('shown','introduction_shown') and
                json.loads(e['payload']).get('detail',{}).get('book_state')=='unknown' for e in events),
                'interpretation':'Old shown events can occur behind setup; old introduction_shown can precede definition. Do not count these as confirmed reading or comprehension.'},
            'knowledge_interpretation':'Self-reported main ideas and word familiarity; not independently scored accuracy, retention or connected understanding.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--export',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();result=audit(a.export)
    with open(a.output,'x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    Path(a.output).chmod(0o600)
    print(json.dumps({k:result[k] for k in ('integrity_errors','completed_cards','distinct_completed_cards','graded_parts','scheduled_parts','introduced','audio_recordings','assessments')}))

if __name__=='__main__':main()
