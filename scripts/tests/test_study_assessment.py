import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_study import connect, engine, SEED

class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.c=connect();engine.install(self.c,SEED)
        self.body={'request_id':'assessment_fixture_12345','mode':'assessment','assessment':{
            'volume':1,'coverage':'13–146; skipped details','occasion':'current','help_state':'closed'}}
        self.run=engine.session(self.c,self.body)
        self.serial=0
    def tearDown(self):self.c.close()
    def event(self,item,action,detail=None,**kwargs):
        self.serial+=1
        return engine.event(self.c,dict(request_id=f'assessment_event_{self.serial:05}',run_id=self.run['run_id'],
            item_id=item['id'],event=action,detail=detail or {},**kwargs))
    def audio(self,item,root,attempt='assessment_attempt_12345',data=None):
        return engine.save_audio(self.c,self.run['run_id'],item['id'],data or b'ftyp'+b'x'*300,'audio/mp4',root,attempt_id=attempt)
    def test_core_has_no_answers_and_cannot_grade_or_reveal(self):
        self.assertEqual(len(self.run['items']),6)
        self.assertNotIn('answer',json.dumps(self.run['items']))
        for action in ('complete','introduced','position_revealed'):
            with self.assertRaises(ValueError):self.event(self.run['items'][0],action)
        self.assertEqual(self.c.execute('SELECT sum(review_count) FROM study_positions').fetchone()[0],0)
    def test_sequence_missingness_and_exact_retry(self):
        a,b=self.run['items'][:2]
        with self.assertRaises(ValueError):self.event(b,'assessment_advance',{'outcome':'unknown'})
        with self.assertRaises(ValueError):self.event(a,'assessment_advance',{'outcome':'recorded'})
        result=self.event(a,'assessment_advance',{'outcome':'unknown'})
        self.assertFalse(result['scheduled'])
        resumed=engine.session(self.c,self.body)
        self.assertEqual(resumed['completed_ids'],[a['id']])
        changed=copy.deepcopy(self.body);changed['assessment']['coverage']='other'
        with self.assertRaises(ValueError):engine.session(self.c,changed)
    def test_audio_attempt_is_stable_and_confidence_precedes_cue_upload(self):
        a,b=self.run['items'][:2]
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):self.audio(b,root)
            receipt=self.audio(a,root)
            self.assertEqual(receipt,self.audio(a,root))
            self.assertEqual(receipt['attempt_id'],'assessment_attempt_12345')
            with self.assertRaises(ValueError):self.audio(a,root,data=b'ftyp'+b'y'*300)
            self.event(a,'assessment_advance',{'outcome':'recorded'})
            with self.assertRaises(ValueError):self.audio(b,root,'assessment_attempt_22222')
            self.event(b,'feedback',{'dimension':'assessment_confidence','value':'unsure'})
            self.audio(b,root,'assessment_attempt_22222')
            self.event(b,'assessment_advance',{'outcome':'recorded'})
            # Retry old upload remains safe even after advancing.
            self.assertEqual(receipt,self.audio(a,root))
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_audio_attempts').fetchone()[0],2)
        self.assertEqual(self.c.execute('SELECT sum(review_count) FROM study_positions').fetchone()[0],0)
    def test_volume_end_adds_only_bounded_original_question_pair(self):
        body=copy.deepcopy(self.body);body['request_id']='assessment_end_12345';body['assessment']['occasion']='volume_end'
        run=engine.session(self.c,body)
        self.assertEqual(len(run['items']),8)
        self.assertTrue(run['items'][-1]['source']['original_excerpt'])
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_items').fetchone()[0],13)

if __name__=='__main__':unittest.main()
