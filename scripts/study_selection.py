"""Selection for deliberate Norway practice; dependencies represent exposure, not mastery."""
import json

TOPICS = {'all':'Alle temaer','chronology':'Perioder og tidslinjer','landscape':'Landskap og bosetning',
          'livelihood':'Levemåter og jordbruk','networks':'Materialer og forbindelser',
          'concepts':'Begreper og kulturer','evidence':'Språk, identitet og spor','connections':'Sammenhenger'}
V2 = 'norway-intensive-v2'
POLICY_V2 = {'selection':'six-at-a-time; due then new; one family per batch; exposed prerequisites',
             'introduction':'exposure only; never a knowledge grade',
             'scheduling':'study-consolidation-v2: Good/Again, 10m/20m/1d learning, 0.9 retention',
             'extra_practice':'explicit opt-in; 60-second cooldown; no FSRS updates',
             'assignment':'observational, not randomized','source_attribution':'unresolved unless supported'}


def validate_seed(seed):
    items = seed['items']; ids = [i['id'] for i in items]
    if len(set(ids)) != len(ids): raise ValueError('Duplicate item ID')
    graph = {i['id']:i.get('prerequisites',[]) for i in items}
    positions=[]
    for i in items:
        if i.get('topic','all') not in TOPICS: raise ValueError('Unknown topic')
        if not set(graph[i['id']]) <= set(ids): raise ValueError('Missing prerequisite')
        if not i.get('sources') or not i.get('references'): raise ValueError('Sources and references required')
        if any(not s.get('tana_link','').startswith('https://') for s in i['sources']):
            raise ValueError('Source links required for the phone reader')
        positions.extend(p['position_id'] for p in i['positions'])
    if len(set(positions)) != len(positions): raise ValueError('Position IDs must be unique')
    visited=set(); visiting=set()
    def visit(key):
        if key in visiting: raise ValueError('Prerequisite cycle')
        if key in visited: return
        visiting.add(key)
        for dep in graph[key]: visit(dep)
        visiting.remove(key);visited.add(key)
    for key in graph:visit(key)


def choose(conn, rows, mode, practice, topic, now):
    seen = {r[0] for r in conn.execute("SELECT DISTINCT item_id FROM study_events WHERE event IN ('introduced','position_revealed','revealed','complete')")}
    payloads = {r['id']:json.loads(r['payload']) for r in rows}
    completed = {r[0]:r[1] for r in conn.execute("SELECT item_id, MAX(created_at) FROM study_events WHERE event IN ('complete','introduced','skip') GROUP BY item_id")}
    matching=[r for r in rows if (r['kind']=='voice') == (mode=='voice')]
    if topic!='all': matching=[r for r in matching if payloads[r['id']].get('topic','concepts')==topic]
    # Include supporting cards for a selected topic; do not strand it behind a hidden prerequisite.
    wanted={r['id'] for r in matching}
    def add_support(key):
        for dep in payloads[key].get('prerequisites',[]):
            if dep not in seen and dep not in wanted:
                wanted.add(dep);add_support(dep)
    for key in list(wanted):add_support(key)
    matching=[r for r in rows if r['id'] in wanted]
    unlocked=[r for r in matching if set(payloads[r['id']].get('prerequisites',[])) <= seen]
    due=[r for r in unlocked if r['reviews'] and r['next_due']<=now]
    fresh=[r for r in unlocked if not r['reviews']]
    cooldown=60000 if practice=='extra' else 10*60000
    eligible=[r for r in unlocked if (practice=='extra' or not r['reviews'] or r['next_due']<=now)
              and completed.get(r['id'],0)<=now-cooldown]
    if practice=='extra':eligible.sort(key=lambda r:(completed.get(r['id'],0),r['ordinal']))
    else:eligible.sort(key=lambda r:(0 if r['reviews'] else 1,r['next_due'],r['ordinal']))
    chosen=[];families=set()
    for r in eligible:
        family=payloads[r['id']].get('family_id',r['id'])
        if family in families:continue
        families.add(family);chosen.append(r)
        if len(chosen)==6:break
    future=[r['next_due'] for r in unlocked if r['reviews'] and r['next_due']>now]
    return chosen, {'due':len(due),'new':len(fresh),'total':len(matching),
                    'next_due_at':min(future) if future else None,
                    'waiting_for_foundation':len(matching)-len(unlocked),
                    'practice':practice,'topic':topic}
