"""Isolated SQLite and HTTP pilot tests; no live ingestion, network LLMs or credentials."""
import copy
import importlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SCRIPTS))
import study_engine as engine
from study_schema import SCHEMA

# Only external storage bootstrap and LLM providers are replaced. The actual
# curriculum boundary, study engine and canonical FSRS implementation run here.
db = types.ModuleType('db')
db.get_connection = lambda **kwargs: None
db.init_db = lambda: None
llm = types.ModuleType('claude_llm')
def no_llm(*args, **kwargs): raise AssertionError('Pilot must not call an LLM to grade')
for name in ['call_claude','call_claude_json','call_claude_or_gemini','call_claude_search']:
    setattr(llm,name,no_llm)
with patch.dict(sys.modules,{'db':db,'claude_llm':llm}):
    import curriculum_db
    import review_engine
    import study_http

SEED = json.loads((SCRIPTS.parent/'research/norway-reading-study/pilot-v1.json').read_text())

def connect(path=':memory:'):
    c=sqlite3.connect(path,timeout=10);c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON');return c

class StudyTests(unittest.TestCase):
    def setUp(self):
        self.modules=patch.dict(sys.modules,{'review_engine':review_engine});self.modules.start();self.addCleanup(self.modules.stop)
        self.c=connect(); self.c.execute('CREATE TABLE knowledge_items (id TEXT, stability_days REAL)')
        self.c.execute("INSERT INTO knowledge_items VALUES('old',42)");self.c.commit()
        engine.install(self.c,SEED,code_commit='test-commit')
        self.run=engine.session(self.c,{'request_id':'fixture_run_12345'})
        self.item=next(x for x in self.run['items'] if x['kind']=='aspect')
    def tearDown(self): self.c.close()
    def event(self,action,item=None,**kw):
        item=item or self.item
        return {'request_id':f'fixture_event_{self.c.execute("SELECT count(*) FROM study_events").fetchone()[0]}_{action}',
            'run_id':self.run['run_id'],'item_id':item['id'],'event':action,**kw}
    def reveal(self,item=None):
        item=item or self.item
        for p in item['positions']:
            if p.get('testable',True):engine.event(self.c,self.event('position_revealed',item,detail={'position_id':p['position_id']}))
    def complete(self,item=None,context='closed'):
        item=item or self.item
        return self.event('complete',item,detail={'book_state':context},results=[{'position_id':p['position_id'],'score':'knew'} for p in item['positions'] if p.get('testable',True)])
    def test_focus_preserves_old_state_and_blocks_legacy_stream(self):
        self.assertEqual(curriculum_db.generate_review_stream(conn=self.c)['items'],[])
        self.assertEqual(self.c.execute('SELECT stability_days FROM knowledge_items').fetchone()[0],42)
        self.assertEqual(engine.status(self.c)['paused_counts'],{'knowledge_items':1})
    def test_intro_is_exposure_only_and_cannot_grade(self):
        item=self.run['items'][0]
        with self.assertRaises(ValueError):engine.event(self.c,self.complete(item))
        engine.event(self.c,self.event('introduced',item))
        self.assertEqual(self.c.execute('SELECT sum(review_count) FROM study_positions').fetchone()[0],0)
    def test_grade_retries_are_exactly_once_and_resume_is_explicit(self):
        self.reveal();b=self.complete();first=engine.event(self.c,b)
        self.assertTrue(first['scheduled']);self.assertEqual(engine.event(self.c,b),first)
        self.assertEqual(self.c.execute('SELECT sum(review_count) FROM study_positions').fetchone()[0],3)
        b['request_id']='different_retry_12345'
        with self.assertRaises(ValueError):engine.event(self.c,b)
        resumed=engine.session(self.c,{'request_id':self.run['run_id']})
        self.assertIn(self.item['id'],resumed['completed_ids'])
    def test_answer_must_have_been_revealed(self):
        with self.assertRaises(ValueError):engine.event(self.c,self.complete())
    def test_open_book_and_unknown_context_do_not_update_memory(self):
        for context in ['open','unknown']:
            self.reveal();b=self.complete(context=context)
            self.assertFalse(engine.event(self.c,b)['scheduled'])
            self.c.execute("DELETE FROM study_events WHERE event='complete'");self.c.commit()
        self.assertEqual(self.c.execute('SELECT sum(review_count) FROM study_positions').fetchone()[0],0)
    def test_invalid_position_cannot_partially_grade(self):
        self.reveal();b=self.complete();b['results'].append({'position_id':'outside','score':'knew'})
        with self.assertRaises(ValueError):engine.event(self.c,b)
        self.assertEqual(self.c.execute('SELECT sum(review_count) FROM study_positions').fetchone()[0],0)
    def test_visible_anchor_cannot_earn_credit(self):
        item=next(x for x in self.run['items'] if x['kind']=='causal');self.reveal(item)
        engine.event(self.c,self.complete(item))
        self.assertEqual(self.c.execute('SELECT review_count FROM study_positions WHERE id=?',(item['positions'][0]['position_id'],)).fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT sum(review_count) FROM study_positions WHERE item_id=?',(item['id'],)).fetchone()[0],2)
    def test_seed_and_run_snapshots_are_immutable(self):
        old=self.c.execute('SELECT snapshot FROM study_runs').fetchone()[0]
        seed=copy.deepcopy(SEED);seed['items'][0]['title']='changed'
        with self.assertRaises(ValueError):engine.install(self.c,seed)
        self.assertEqual(self.c.execute('SELECT snapshot FROM study_runs').fetchone()[0],old)
        self.assertEqual(engine.session(self.c,{'request_id':self.run['run_id']})['items'],self.run['items'])
    def test_superseding_seed_hides_prior_cards_without_deleting(self):
        seed=copy.deepcopy(SEED);seed['items']=seed['items'][:1];engine.install(self.c,seed)
        self.assertEqual(engine.status(self.c)['items'],1)
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_items').fetchone()[0],13)
    def test_voice_durable_bound_purpose_and_idempotent(self):
        run=engine.session(self.c,{'request_id':'fixture_voice_12345','mode':'voice'});item=run['items'][0]
        data=b'\x00\x00\x00\x18ftypM4A '+b'fixture'*50
        with tempfile.TemporaryDirectory() as root:
            a=engine.save_audio(self.c,run['run_id'],item['id'],data,'audio/mp4',root)
            self.assertEqual(a,engine.save_audio(self.c,run['run_id'],item['id'],data,'audio/mp4',root))
            row=self.c.execute('SELECT * FROM study_audio').fetchone()
            self.assertEqual(Path(row['audio_path']).read_bytes(),data)
            self.assertEqual(Path(row['audio_path']).stat().st_mode & 0o777,0o600)
            self.assertIsNone(row['transcript'])
            with self.assertRaises(ValueError):engine.save_audio(self.c,run['run_id'],'not-in-run',data,'audio/mp4',root)
            with self.assertRaises(ValueError):engine.save_audio(self.c,self.run['run_id'],self.item['id'],data,'audio/mp4',root)
            engine.save_audio(self.c,self.run['run_id'],self.item['id'],data,'audio/mp4',root,'wondering')
            self.assertEqual(self.c.execute('SELECT count(*) FROM study_audio').fetchone()[0],2)
    def test_transcription_claim_does_not_create_knowledge(self):
        with tempfile.TemporaryDirectory() as root:
            engine.save_audio(self.c,self.run['run_id'],self.item['id'],b'ftyp'+b'x'*300,'audio/mp4',root,'reflection')
            row=engine.transcription(self.c,{'claim':True});self.assertIsNotNone(row)
            self.assertIsNone(engine.transcription(self.c,{'claim':True}))
            engine.transcription(self.c,{'audio_id':row['id'],'status':'complete','transcript':'Dette er usikkert.'})
            self.assertEqual(self.c.execute('SELECT count(*) FROM knowledge_items').fetchone()[0],1)
    def test_parallel_session_retry_creates_one_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'study.db';c=connect(path);engine.install(c,SEED);c.close();results=[]
            def worker():
                c=connect(path)
                try:results.append(engine.session(c,{'request_id':'concurrent_session_12345'}))
                finally:c.close()
            threads=[threading.Thread(target=worker) for _ in range(3)]
            for t in threads:t.start()
            for t in threads:t.join()
            self.assertEqual(len(results),3);self.assertEqual(results[0],results[1])
            c=connect(path);self.assertEqual(c.execute('SELECT count(*) FROM study_runs').fetchone()[0],1);c.close()
    def test_suspension_http_guard_including_query_string(self):
        class Handler:
            path='/structural/grade?retry=1'
            def _send_private_json_response(self,status,payload):self.status=status;self.payload=payload
        h=Handler()
        with patch.object(study_http,'study_action',return_value={'active':True}):self.assertTrue(study_http.route(h,'POST'))
        self.assertEqual(h.status,409)

if __name__=='__main__':unittest.main()
