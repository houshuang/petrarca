"""Source preservation and publication failure cases against isolated canonical SQLite."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_study import connect, engine, SEED, curriculum_db
from study_intake import digest
from reading_study_archive import archive, verify, backup
from reading_study_intake import draft
from unittest.mock import Mock

SOURCE={'id':'fixture_source','audio_sha256':'a'*64,'journal_node_id':'fixture_journal',
        'tana_link':'https://app.tana.inc/?nodeid=fixture_journal','volume':1,
        'transcript':'The original fixture says soil moves downhill. Do not infer authorship.'}
DRAFT={'candidates':[{'kind':'term','topic':'livelihood','title':'Fixture term','question':'Fixture question?',
    'answer':'Fixture explanation.','source_quote':'soil moves downhill',
    'references':[{'title':'Fixture only','url':'https://example.org/source'}]}]}

class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.c=connect();engine.install(self.c,SEED)
    def tearDown(self):self.c.close()
    def call(self,op,**kw):return curriculum_db.study_action('intake',dict(op=op,**kw),conn=self.c)
    def prepare(self):
        self.call('register',source=SOURCE)
        return self.call('draft',source_id=SOURCE['id'],draft=DRAFT)
    def test_registration_deduplicates_audio_and_rejects_replaced_original(self):
        self.call('register',source=SOURCE)
        duplicate={**SOURCE,'id':'other_source'}
        self.assertTrue(self.call('register',source=duplicate)['duplicate'])
        with self.assertRaises(ValueError):self.call('register',source={**SOURCE,'audio_sha256':'b'*64})
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_intake').fetchone()[0],1)
    def test_draft_cannot_invent_source_span_or_change_published_content(self):
        self.call('register',source=SOURCE)
        changed=copy.deepcopy(DRAFT);changed['candidates'][0]['source_quote']='invented'
        with self.assertRaises(ValueError):self.call('draft',source_id=SOURCE['id'],draft=changed)
        self.assertEqual(self.call('status')[0]['state'],'archived')
        self.call('draft',source_id=SOURCE['id'],draft=DRAFT)
        self.call('publish',source_id=SOURCE['id'],reviewed_sha256=digest(DRAFT),reviewer='fixture reviewer')
        with self.assertRaises(ValueError):self.call('draft',source_id=SOURCE['id'],draft=DRAFT)
    def test_review_binds_exact_draft_and_append_preserves_schedules(self):
        before=[tuple(r) for r in self.c.execute('SELECT * FROM study_positions')]
        old_items=[tuple(r) for r in self.c.execute('SELECT * FROM study_items')]
        old_run=engine.session(self.c,{'request_id':'intake_previous_run_12345'})
        result=self.prepare()
        with self.assertRaises(ValueError):self.call('publish',source_id=SOURCE['id'],reviewed_sha256='wrong',reviewer='fixture')
        published=self.call('publish',source_id=SOURCE['id'],reviewed_sha256=result['draft_sha256'],reviewer='fixture')
        self.assertEqual(len(published['added']),1)
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT * FROM study_positions')][:len(before)],before)
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT * FROM study_items')][:len(old_items)],old_items)
        self.assertEqual(engine.session(self.c,{'request_id':old_run['run_id']})['items'],old_run['items'])
        self.assertTrue(self.call('publish',source_id=SOURCE['id'],reviewed_sha256=result['draft_sha256'],reviewer='fixture')['duplicate'])
    def test_empty_draft_is_valid_and_failed_processing_is_visible(self):
        self.call('register',source=SOURCE)
        self.call('failed',source_id=SOURCE['id'],error='TimeoutExpired')
        self.assertEqual(self.call('status')[0]['state'],'failed')
        self.call('draft',source_id=SOURCE['id'],draft={'candidates':[]})
        self.assertEqual(self.call('status')[0]['state'],'drafted')
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_items').fetchone()[0],13)
    def test_monthly_waits_then_freezes_sample_without_touching_memory(self):
        empty=curriculum_db.study_action('monthly',{},conn=self.c)
        self.assertEqual(empty['status'],'waiting_for_completed_volume')
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_monthly_samples').fetchone()[0],0)
        run=engine.session(self.c,{'request_id':'monthly_assessment_12345','mode':'assessment','assessment':{
            'volume':1,'coverage':'Volume finished, fixture','occasion':'volume_end','help_state':'closed'}})
        for n,item in enumerate(run['items']):
            engine.event(self.c,{'request_id':f'monthly_fixture_{n:05}','run_id':run['run_id'],'item_id':item['id'],
                'event':'assessment_advance','detail':{'outcome':'unknown'}})
        result=curriculum_db.study_action('monthly',{'seed':12},conn=self.c)
        self.assertEqual(result['eligible_volumes'],[1]);self.assertEqual(len(result['volumes']),1)
        self.assertEqual(result,curriculum_db.study_action('monthly',{'seed':99},conn=self.c))
        self.assertEqual(self.c.execute('SELECT sum(review_count) FROM study_positions').fetchone()[0],0)
    def test_archive_restore_and_corruption_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);audio=root/'input';audio.write_bytes(b'fixture audio')
            transcript=root/'transcript';transcript.write_text('fixture transcript')
            source={k:v for k,v in SOURCE.items() if k not in ('audio_sha256','transcript')}
            out,files=archive(source,audio,transcript,root/'archive')
            self.assertEqual(archive(source,audio,transcript,root/'archive')[0],out)
            self.assertTrue(backup(out,root/'separate-copy')['audio_restore_verified'])
            (out/'original.audio').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):verify(out)
    def test_codex_timeout_preserves_evidence_and_does_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fail(command,**kwargs):
                self.assertEqual(command[:5],['codex','exec','--sandbox','read-only','--ephemeral'])
                return Mock(returncode=1)
            with self.assertRaises(RuntimeError):draft(SOURCE,Path(tmp)/'attempt',run=fail)
            self.assertTrue((Path(tmp)/'attempt/prompt.txt').exists())
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_items').fetchone()[0],13)

if __name__=='__main__':unittest.main()
