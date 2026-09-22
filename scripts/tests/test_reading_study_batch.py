"""Isolated recovery and fail-closed checks for the unified Norway operator."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_study import connect, engine, SEED, curriculum_db
from study_intake import digest, corpus_snapshot, register
from study_readings import import_reviewed
from reading_study_batch import BatchHold, _question_work, _review, discover, run
from limbic.cerebellum.batch import StateStore


SOURCE={'id':'fixture_batch','audio_sha256':'b'*64,'journal_node_id':'batch_node',
        'tana_link':'https://app.tana.inc/?nodeid=batch_node','volume':None,
        'transcript':'I wonder what bog iron looks like before smelting. This is a question from my own reading.'}
QUESTION={'kind':'prompt','topic':'livelihood','title':'Bog iron process','question':'How is bog iron smelted?',
          'answer':'It is reduced in a charcoal furnace.','source_quote':'bog iron looks like',
          'references':[{'title':'Example','url':'https://example.org/iron'}]}


class FakeModel:
    def __init__(self):self.calls=[]
    def call(self,stage,packet,schema,model,**kwargs):
        self.calls.append(stage)
        if stage=='reading':
            body=' '.join(['Bog iron is an iron rich deposit in wet ground.']*14)
            return {'reading':{'title':'Bog iron appearance','text':body,
                    'citations':[{'title':'Museum','url':'https://example.org/museum'}],
                    'targets':[]}}
        if stage=='review-readings':
            return {'decisions':[{'id':packet['candidates'][0]['id'],'verdict':'accept',
                'reason':'Original explicit visual question; distinct from smelting process.',
                'match_ids':[],'relation':'distinct'}],'omissions':[]}
        if stage=='questions':
            return {'questions':[QUESTION],'wonderings':[]}
        if stage=='review-questions':
            return {'decisions':[{'id':packet['candidates'][0]['id'],'verdict':'accept',
                'reason':'Distinct source question.','match_ids':[],'relation':'distinct'}],
                'omissions':[]}
        raise AssertionError(stage)


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.c=connect();engine.install(self.c,SEED)
    def tearDown(self):self.c.close()
    def call(self,action,body):return curriculum_db.study_action(action,body,conn=self.c)

    def test_source_revision_and_corpus_staleness(self):
        register(self.c,SOURCE)
        with self.assertRaisesRegex(ValueError,'changed'):
            register(self.c,{**SOURCE,'transcript':SOURCE['transcript']+' Revised.'})
        snap=corpus_snapshot(self.c)
        self.c.execute('UPDATE study_intake SET source=? WHERE source_id=?',
                       (json.dumps({**SOURCE,'transcript':SOURCE['transcript']+' Revised.'}),SOURCE['id']))
        self.c.commit()
        self.assertNotEqual(snap['corpus_sha256'],corpus_snapshot(self.c)['corpus_sha256'])

    def test_reading_review_cannot_smuggle_unreviewed_target(self):
        seed_path=Path(__file__).resolve().parents[2]/'research/norway-reading-study/readings-seed-v1.json'
        entry=json.loads(seed_path.read_text())['readings'][0]
        snap=corpus_snapshot(self.c)
        candidate_ids=[entry['brief_id']]
        decisions=[{'id':entry['brief_id'],'verdict':'accept','reason':'Reviewed'}]
        packet={'readings_sha256':digest([entry]),'corpus_sha256':snap['corpus_sha256'],
                'candidate_ids':candidate_ids,'decisions':decisions}
        entry={**entry,'review_packet_sha256':digest(packet)}
        with self.assertRaisesRegex(ValueError,'unreviewed'):
            import_reviewed(self.c,{'readings':[entry],
                'expected_corpus_sha256':snap['corpus_sha256'],
                'review_candidate_ids':candidate_ids,'review_decisions':decisions})

    def test_reviewed_selection_rejects_stale_or_incomplete_and_amends(self):
        register(self.c,SOURCE)
        draft={'candidates':[QUESTION,{**QUESTION,'title':'Raw bog iron','question':'What does raw bog iron look like?'}]}
        self.call('intake',{'op':'draft','source_id':SOURCE['id'],'draft':draft})
        snap=corpus_snapshot(self.c)
        decisions=[{'index':0,'verdict':'accept','reason':'Distinct process question'},
                   {'index':1,'verdict':'hold','reason':'Visual reference needs verification'}]
        packet={'draft_sha256':digest(draft),'corpus_sha256':snap['corpus_sha256'],
                'decisions':decisions,'accepted_indices':[0]}
        body={'op':'publish','source_id':SOURCE['id'],'reviewed_sha256':digest(draft),
              'reviewer':'astra','accepted_indices':[0],'review_decisions':decisions,
              'review_packet_sha256':digest(packet),'expected_corpus_sha256':snap['corpus_sha256']}
        with self.assertRaisesRegex(ValueError,'every candidate'):
            self.call('intake',{**body,'review_decisions':decisions[:1]})
        with self.assertRaisesRegex(ValueError,'packet hash'):
            self.call('intake',{**body,'review_packet_sha256':'f'*64})
        self.assertEqual(len(self.call('intake',body)['added']),1)
        self.assertTrue(self.call('intake',body)['duplicate'])  # Lost receipt retry.
        updated=corpus_snapshot(self.c)
        amended=[{'index':0,'verdict':'reject','reason':'Already published'},
                 {'index':1,'verdict':'accept','reason':'Verified visual angle'}]
        amendment={'draft_sha256':digest(draft),'corpus_sha256':updated['corpus_sha256'],
                   'decisions':amended,'accepted_indices':[1]}
        amendment_body={'op':'amend','source_id':SOURCE['id'],'draft':draft,'reviewed_sha256':digest(draft),
                        'reviewer':'astra','accepted_indices':[1],'review_decisions':amended,
                        'review_packet_sha256':digest(amendment),'expected_corpus_sha256':updated['corpus_sha256']}
        self.assertEqual(len(self.call('intake',amendment_body)['added']),1)
        self.assertTrue(self.call('intake',amendment_body)['duplicate'])
        stale_decisions=[{'index':0,'verdict':'reject','reason':'old'},
                         {'index':1,'verdict':'reject','reason':'old'}]
        stale_packet={'draft_sha256':digest(draft),'corpus_sha256':updated['corpus_sha256'],
                      'decisions':stale_decisions,'accepted_indices':[]}
        with self.assertRaisesRegex(ValueError,'changed since review'):
            self.call('intake',{**amendment_body,'accepted_indices':[],
                'review_decisions':stale_decisions,'review_packet_sha256':digest(stale_packet)})

    def test_discovery_saturation_holds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'discovery.json'
            path.write_text(json.dumps({'workspace_id':'VSazTvUjtQ','tag_id':'0VhmSsp1En',
                                        'limit':2,'saturated':True,
                                        'nodes':[{'id':'one'},{'id':'two'}]}))
            with self.assertRaisesRegex(BatchHold,'saturated'):
                discover(None,snapshot=path)

    def test_review_accepts_position_match_but_rejects_forged_or_missing(self):
        corpus=corpus_snapshot(self.c)
        position=corpus['items'][0]['positions'][0]['position_id']
        candidate=[{'id':'candidate-a','candidate':QUESTION}]
        class Answer:
            def __init__(self,match):self.match=match
            def call(self,*args,**kwargs):
                return {'decisions':[{'id':'candidate-a','verdict':'reject','reason':'Same retrieval aspect',
                    'relation':'duplicate','match_ids':[self.match]}],'omissions':[]}
        decisions,_,audit=_review(Answer(position),'questions',candidate,corpus,'sourcehash',{})
        self.assertEqual(decisions[0]['match_ids'],[position])
        self.assertEqual(audit['coverage']['returned'],1)
        with self.assertRaisesRegex(BatchHold,'forged'):
            _review(Answer('forged-position'),'questions',candidate,corpus,'sourcehash',{})
        self.assertEqual(_review(None,'questions',[],corpus,'sourcehash',{})[2]['zero_candidates'],True)
        class Missing:
            def call(self,*args,**kwargs):return {'decisions':[],'omissions':[]}
        with self.assertRaisesRegex(BatchHold,'incomplete'):
            _review(Missing(),'questions',candidate,corpus,'sourcehash',{})

    def test_reading_backlog_with_zero_new_sources_and_resume(self):
        # Same published original is available to the batch, but no source intake is needed.
        self.c.execute('INSERT INTO study_sources VALUES(?,?,?)',
                       (SOURCE['id'],engine.STUDY_ID,json.dumps({k:v for k,v in SOURCE.items() if k!='transcript'})))
        self.c.commit();register(self.c,SOURCE)
        initial_positions=self.c.execute('SELECT COUNT(*) FROM study_positions').fetchone()[0]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            discovery=root/'discovery.json';discovery.write_text(json.dumps({
                'workspace_id':'VSazTvUjtQ','tag_id':'0VhmSsp1En','limit':100,'saturated':False,
                'nodes':[{'id':'batch_node','name':'Norway study','created':'2026-09-22T00:00:00Z'}]}))
            wondering=root/'wonderings.json';wondering.write_text(json.dumps({'entries':[
                {'source_id':SOURCE['id'],'source_quote':'I wonder what bog iron looks like before smelting.',
                 'topic':'What does raw bog iron look like?'}]}))
            model=FakeModel()
            first=run(root/'work',discovery_snapshot=discovery,wonderings_file=wondering,
                      call=self.call,model=model)
            self.assertFalse(first['failures'],first)
            self.assertEqual(first['sources'][0]['state'],'already_published')
            self.assertEqual(first['readings'][0]['state'],'published')
            self.assertEqual(self.c.execute('SELECT COUNT(*) FROM study_reading_selections').fetchone()[0],0)
            self.assertEqual(self.c.execute('SELECT COUNT(*) FROM study_positions').fetchone()[0],initial_positions)
            second=run(root/'work',discovery_snapshot=discovery,wonderings_file=wondering,
                       call=self.call,model=model)
            self.assertEqual(second['readings'][0]['state'],'already_processed')
            self.assertEqual(model.calls,['reading','review-readings'])

    def test_lost_publication_response_reconciles_without_model_repeat(self):
        register(self.c,SOURCE)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);state=StateStore(root/'work'/'state.db');model=FakeModel()
            self.addCleanup(state._conn.close)
            report={'questions':[]}
            lost=[False]
            def call_with_lost_receipt(action,body):
                result=self.call(action,body)
                if action=='intake' and body.get('op')=='publish' and not lost[0]:
                    lost[0]=True
                    raise ConnectionError('receipt lost after commit')
                return result
            with self.assertRaises(ConnectionError):
                _question_work(SOURCE['id'],SOURCE,model,call_with_lost_receipt,report,state)
            self.assertTrue(lost[0])
            self.assertEqual(self.c.execute('SELECT count(*) FROM study_items WHERE version=?',('intake-v1',)).fetchone()[0],1)
            discovery=root/'discovery.json';discovery.write_text(json.dumps({
                'workspace_id':'VSazTvUjtQ','tag_id':'0VhmSsp1En','limit':100,'saturated':False,
                'nodes':[{'id':'batch_node','name':'Norway study','created':'2026-09-22T00:00:00Z'}]}))
            wondering=root/'wonderings.json';wondering.write_text('{"entries":[]}')
            resumed=run(root/'work',discovery_snapshot=discovery,wonderings_file=wondering,
                        call=self.call,model=model)
            self.assertEqual(resumed['questions'][0]['state'],'reconciled_lost_receipt')
            self.assertEqual(self.c.execute('SELECT count(*) FROM study_items WHERE version=?',('intake-v1',)).fetchone()[0],1)
            self.assertEqual(model.calls,['questions','review-questions'])

    def test_lost_reading_receipt_and_deferred_backlog_progress(self):
        source={**SOURCE,'transcript':SOURCE['transcript']+' I wonder where the Hittites lived.'}
        self.c.execute('INSERT INTO study_sources VALUES(?,?,?)',
                       (source['id'],engine.STUDY_ID,json.dumps({k:v for k,v in source.items() if k!='transcript'})))
        self.c.commit();register(self.c,source)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            discovery=root/'discovery.json';discovery.write_text(json.dumps({
                'workspace_id':'VSazTvUjtQ','tag_id':'0VhmSsp1En','limit':100,'saturated':False,
                'nodes':[{'id':'batch_node','name':'Norway study','created':'2026-09-22T00:00:00Z'}]}))
            wondering=root/'wonderings.json';wondering.write_text(json.dumps({'entries':[
                {'source_id':source['id'],'source_quote':'I wonder what bog iron looks like before smelting.',
                 'topic':'What does raw bog iron look like?'},
                {'source_id':source['id'],'source_quote':'I wonder where the Hittites lived.',
                 'topic':'Where did the Hittites live?'}]}))
            model=FakeModel();lost=[False]
            def lost_receipt(action,body):
                result=self.call(action,body)
                if action=='readings-import' and not lost[0]:
                    lost[0]=True;raise ConnectionError('reading receipt lost')
                return result
            with patch('reading_study_batch.MAX_READINGS',1):
                first=run(root/'work',discovery_snapshot=discovery,wonderings_file=wondering,
                          call=lost_receipt,model=model)
                self.assertEqual(first['failures'][0]['stage'],'reading')
                self.assertEqual(len(first['omissions'][0]['deferred']),1)
                second=run(root/'work',discovery_snapshot=discovery,wonderings_file=wondering,
                           call=self.call,model=model)
            self.assertTrue(any(r['state']=='already_processed' for r in second['readings']))
            self.assertTrue(any(r['state']=='published' for r in second['readings']))
            self.assertEqual(self.c.execute('SELECT COUNT(*) FROM study_reading_briefs').fetchone()[0],2)
            self.assertEqual(model.calls.count('reading'),2)

    def test_unavailable_original_is_reported_without_registration(self):
        class MissingAudio:
            def source(self,node):raise BatchHold('original audio unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            discovery=root/'discovery.json';discovery.write_text(json.dumps({
                'workspace_id':'VSazTvUjtQ','tag_id':'0VhmSsp1En','limit':100,'saturated':False,
                'nodes':[{'id':'new_node','name':'Possible reading','created':'2026-09-22T00:00:00Z'}]}))
            wondering=root/'wonderings.json';wondering.write_text('{"entries":[]}')
            before=self.c.execute('SELECT COUNT(*) FROM study_intake').fetchone()[0]
            report=run(root/'work',discovery_snapshot=discovery,wonderings_file=wondering,
                       call=self.call,model=FakeModel(),outliner=MissingAudio())
            self.assertEqual(report['failures'][0]['stage'],'source')
            self.assertIn('audio unavailable',report['failures'][0]['reason'])
            self.assertEqual(self.c.execute('SELECT COUNT(*) FROM study_intake').fetchone()[0],before)


if __name__=='__main__':unittest.main()
