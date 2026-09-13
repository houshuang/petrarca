"""Exercise intensive selection, exposure dependencies and canonical consolidation on isolated DBs."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from test_study import engine, connect, review_engine, SEED
from study_selection import choose, validate_seed

V2_SEED=json.loads((Path(__file__).resolve().parents[2]/'research/norway-reading-study/intensive-v2.json').read_text())

class IntensiveTests(unittest.TestCase):
    def setUp(self):
        self.c=connect();engine.install(self.c,V2_SEED,code_commit='v2-fixture')
        self.modules=patch.dict('sys.modules',{'review_engine':review_engine});self.modules.start();self.addCleanup(self.modules.stop)
    def tearDown(self):self.c.close()
    def run_for(self,key='v2_fixture_session',**kw):return engine.session(self.c,{'request_id':key,**kw})
    def send(self,run,item,action,**kw):
        return engine.event(self.c,{'request_id':'v2_event_'+str(self.c.execute('SELECT count(*) FROM study_events').fetchone()[0])+'_'+action,
            'run_id':run['run_id'],'item_id':item['id'],'event':action,**kw})
    def grade(self,run,item,score='knew',context='closed'):
        p=item['positions'][0]
        self.send(run,item,'position_revealed',detail={'position_id':p['position_id']})
        return self.send(run,item,'complete',detail={'book_state':context},results=[{'position_id':p['position_id'],'score':score}])
    def test_all_content_reachable_and_old_items_exact(self):
        validate_seed(V2_SEED)
        self.assertGreaterEqual(len(V2_SEED['items']),70)
        byid={i['id']:i for i in V2_SEED['items']}
        for i in SEED['items']:self.assertEqual(i,byid[i['id']])
        known=set()
        while True:
            more={i['id'] for i in V2_SEED['items'] if set(i.get('prerequisites',[]))<=known}
            if more<=known:break
            known|=more
        self.assertEqual(known,set(byid))
    def test_dependency_cycles_rejected(self):
        seed=copy.deepcopy(V2_SEED);seed['items'][0]['prerequisites']=[seed['items'][0]['id']]
        with self.assertRaises(ValueError):engine.install(self.c,seed)
    def test_only_exposed_dependencies_and_unique_families(self):
        run=self.run_for(topic='connections')
        self.assertTrue(run['items'])
        for item in run['items']:self.assertFalse(item.get('prerequisites'))
        families=[i.get('family_id',i['id']) for i in run['items']]
        self.assertEqual(len(families),len(set(families)))
    def test_topic_includes_foundations_from_other_topics(self):
        run=self.run_for(topic='connections')
        self.assertTrue(any(i.get('topic')!='connections' for i in run['items']))
        self.assertGreater(run['availability']['waiting_for_foundation'],0)
    def test_consolidation_correct_20_minutes_miss_10_minutes(self):
        run=self.run_for(topic='chronology')
        items=[i for i in run['items'] if i['kind']=='prompt']
        for item,score,minutes in zip(items,['knew','missed'],[20,10]):
            before=engine.now_ms();result=self.grade(run,item,score)
            due=self.c.execute('SELECT due_at FROM study_positions WHERE item_id=?',(item['id'],)).fetchone()[0]
            self.assertTrue(result['scheduled']);self.assertAlmostEqual((due-before)/60000,minutes,delta=0.1)
            self.assertEqual(result['scheduling_policy'],'study-consolidation-v2')
    def test_extra_never_changes_schedule_and_can_select_not_due(self):
        run=self.run_for(topic='chronology');item=next(i for i in run['items'] if i['kind']=='prompt')
        self.grade(run,item)
        before=self.c.execute('SELECT * FROM study_positions WHERE item_id=?',(item['id'],)).fetchone()
        with patch.object(engine,'now_ms',return_value=engine.now_ms()+61000):
            extra=self.run_for('v2_extra_session',practice='extra',topic='chronology')
            # Select may prefer unvisited items; exhaust last_seen ordering deterministically.
            for i in extra['items']:
                if i['kind']=='prompt' and not i['needs_introduction']:
                    prior=tuple(self.c.execute('SELECT * FROM study_positions WHERE item_id=?',(i['id'],)).fetchone())
                    result=self.grade(extra,i)
                    self.assertFalse(result['scheduled']);self.assertEqual(result['practice'],'extra')
                    self.assertEqual(prior,tuple(self.c.execute('SELECT * FROM study_positions WHERE item_id=?',(i['id'],)).fetchone()))
        self.assertEqual(tuple(before),tuple(self.c.execute('SELECT * FROM study_positions WHERE item_id=?',(item['id'],)).fetchone()))
    def test_extra_replay_rejects_changed_mode_or_topic(self):
        self.run_for(practice='extra',topic='chronology')
        with self.assertRaises(ValueError):self.run_for(practice='scheduled',topic='chronology')
        with self.assertRaises(ValueError):self.run_for(practice='extra',topic='evidence')
    def test_extra_selects_future_review_while_scheduled_does_not(self):
        run=self.run_for(topic='chronology');item=next(i for i in run['items'] if i['kind']=='prompt')
        self.grade(run,item)
        rows=self.c.execute('SELECT i.*, p.due_at AS next_due, p.review_count AS reviews FROM study_items i JOIN study_positions p ON p.item_id=i.id WHERE i.id=?',(item['id'],)).fetchall()
        now=engine.now_ms()+61000
        self.assertEqual(choose(self.c,rows,'review','scheduled','all',now)[0],[])
        self.assertEqual([r['id'] for r in choose(self.c,rows,'review','extra','all',now)[0]],[item['id']])
    def test_open_reflection_cannot_change_schedule(self):
        # Same exclusion used by the personal-connection voice item, isolated from microphone IO.
        seed=copy.deepcopy(V2_SEED);item=next(i for i in seed['items'] if i['id']=='no-v2-time-old')
        item['id']='reflection_fixture';item['scheduling_eligible']=False
        item['positions'][0]['position_id']='reflection_fixture_position';seed['items']=[item]
        engine.install(self.c,seed)
        run=self.run_for();self.assertFalse(self.grade(run,run['items'][0])['scheduled'])
        self.assertEqual(self.c.execute('SELECT review_count FROM study_positions WHERE item_id=?',(item['id'],)).fetchone()[0],0)
    def test_old_runs_keep_old_policy_after_activation(self):
        c=connect();engine.install(c,SEED,code_commit='old')
        run=engine.session(c,{'request_id':'v1_pending_session'});item=next(i for i in run['items'] if i['kind']=='aspect')
        snapshot=c.execute('SELECT snapshot FROM study_runs').fetchone()[0]
        engine.install(c,V2_SEED,code_commit='new')
        self.assertEqual(snapshot,c.execute('SELECT snapshot FROM study_runs').fetchone()[0])
        for n,p in enumerate(item['positions']):
            engine.event(c,{'request_id':f'v1_reveal_event_{n}','run_id':run['run_id'],'item_id':item['id'],'event':'position_revealed','detail':{'position_id':p['position_id']}})
        out=engine.event(c,{'request_id':'v1_completion_event','run_id':run['run_id'],'item_id':item['id'],'event':'complete','detail':{'book_state':'closed'},'results':[{'position_id':p['position_id'],'score':'knew'} for p in item['positions']]})
        self.assertEqual(out['scheduling_policy'],'legacy-fsrs')
        self.assertGreater(c.execute('SELECT min(due_at) FROM study_positions WHERE item_id=?',(item['id'],)).fetchone()[0]-engine.now_ms(),20*86400000)
        c.close()
    def test_scheduled_new_run_does_not_immediately_repeat(self):
        run=self.run_for(topic='chronology');item=next(i for i in run['items'] if i['kind']=='prompt');self.grade(run,item)
        next_run=self.run_for('v2_next_session',topic='chronology')
        self.assertNotIn(item['id'],[i['id'] for i in next_run['items']])

if __name__=='__main__':unittest.main()
