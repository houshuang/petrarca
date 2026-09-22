"""Reviewed readings stay source-bound; selection is the only scheduling entry."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import sys

from test_study import connect, engine, SEED, curriculum_db, review_engine
from study_intake import register
from study_readings import import_reviewed, catalogue, select

SEED_READINGS=json.loads((Path(__file__).resolve().parents[2]/'research/norway-reading-study/readings-seed-v1.json').read_text())


class ReadingTests(unittest.TestCase):
    def setUp(self):
        modules=patch.dict(sys.modules,{'review_engine':review_engine})
        modules.start();self.addCleanup(modules.stop)
        self.c=connect()
        engine.install(self.c,SEED,code_commit='test')
        for index,reading in enumerate(SEED_READINGS['readings']):
            if self.c.execute('SELECT 1 FROM study_intake WHERE source_id=?',(reading['source_id'],)).fetchone():
                continue
            register(self.c,{'id':reading['source_id'],'audio_sha256':str(index+1)*64,
                             'journal_node_id':'original-'+str(index),
                             'tana_link':'https://app.tana.inc/?nodeid=original-'+str(index),
                             'volume':1,'recorded_at':'2026-09-18',
                             'transcript':'Before. '+reading['source_quote']+' After.'})
    def tearDown(self):self.c.close()
    def imported(self):return import_reviewed(self.c,SEED_READINGS)

    def test_exact_original_source_and_server_owned_depth(self):
        original=copy.deepcopy(SEED_READINGS['readings'][0])
        for mutation in [dict(source_quote='Invented'),dict(source_id='no-such-original'),
                         dict(parent_id='no-brief-other'),dict(depth=1),dict(basis='inferred')]:
            changed={**original,**mutation}
            with self.assertRaises(ValueError):import_reviewed(self.c,{'readings':[changed]})
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_reading_intents').fetchone()[0],0)
        self.imported()
        row=self.c.execute('SELECT * FROM study_reading_intents WHERE id=?',(original['intent_id'],)).fetchone()
        self.assertEqual(row['source_quote'],original['source_quote'])
        self.assertEqual(row['source_end']-row['source_start'],len(original['source_quote']))
        self.assertEqual(catalogue(self.c)['readings'][0]['depth'],1)

    def test_import_is_immutable_and_no_view_creates_memory(self):
        before=[tuple(r) for r in self.c.execute('SELECT * FROM study_positions')]
        prior_run=engine.session(self.c,{'request_id':'reading_old_run_12345'})
        self.assertEqual(len(self.imported()['added']),3)
        self.assertTrue(self.imported()['duplicate'])
        changed=copy.deepcopy(SEED_READINGS)
        changed['readings'][0]['text']+=' Different claim.'
        with self.assertRaises(ValueError):import_reviewed(self.c,changed)
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT * FROM study_positions')],before)
        self.assertEqual(engine.session(self.c,{'request_id':prior_run['run_id']})['items'],prior_run['items'])
        self.assertEqual(len(catalogue(self.c)['readings']),3)
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_reading_selections').fetchone()[0],0)

    def test_opt_in_is_idempotent_and_preserves_old_runs(self):
        self.imported()
        prior_run=engine.session(self.c,{'request_id':'reading_frozen_run_12345'})
        before=[tuple(r) for r in self.c.execute('SELECT * FROM study_positions')]
        brief=SEED_READINGS['readings'][0]
        ids=[t['id'] for t in brief['targets']]
        with self.assertRaises(ValueError):select(self.c,{'brief_id':brief['brief_id'],'target_ids':[SEED_READINGS['readings'][1]['targets'][0]['id']]})
        selected=select(self.c,{'brief_id':brief['brief_id'],'target_ids':ids})
        self.assertEqual(len(selected['added']),2)
        self.assertEqual(select(self.c,{'brief_id':brief['brief_id'],'target_ids':ids})['added'],[])
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_reading_selections').fetchone()[0],2)
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT * FROM study_positions')][:len(before)],before)
        self.assertEqual(engine.session(self.c,{'request_id':prior_run['run_id']})['items'],prior_run['items'])
        added=self.c.execute('SELECT * FROM study_positions WHERE item_id=?',(selected['added'][0],)).fetchone()
        self.assertEqual(added['review_count'],0)
        self.assertEqual(added['due_at'],0)
        self.assertTrue(all(t['selected'] for t in catalogue(self.c)['readings'][0]['targets']))

    def test_help_exposure_never_grades_or_schedules_assisted_answer(self):
        self.imported()
        brief=SEED_READINGS['readings'][0]
        item_id=select(self.c,{'brief_id':brief['brief_id'],'target_ids':[brief['targets'][0]['id']]})['added'][0]
        run=engine.session(self.c,{'request_id':'reading_assisted_run_12345'})
        item=next((i for i in run['items'] if i['id']==item_id),None)
        if item is None:
            # New items are ordinal-later; old first-round cards are still frozen.
            for old in run['items']:
                engine.event(self.c,{'request_id':'skip_'+old['id'],'run_id':run['run_id'],'item_id':old['id'],'event':'skip'})
            run=engine.session(self.c,{'request_id':'reading_assisted_next_12345'})
            item=next(i for i in run['items'] if i['id']==item_id)
        position=item['positions'][0]['position_id']
        engine.event(self.c,{'request_id':'reading_help_evt_12345','run_id':run['run_id'],'item_id':item_id,
                             'event':'feedback','detail':{'dimension':'reading_help','brief_id':brief['brief_id']}})
        self.assertEqual(self.c.execute('SELECT review_count FROM study_positions WHERE id=?',(position,)).fetchone()[0],0)
        engine.event(self.c,{'request_id':'reading_reveal_evt_12345','run_id':run['run_id'],'item_id':item_id,
                             'event':'position_revealed','detail':{'position_id':position}})
        result=engine.event(self.c,{'request_id':'reading_grade_evt_12345','run_id':run['run_id'],'item_id':item_id,
                             'event':'complete','detail':{'book_state':'closed'},
                             'results':[{'position_id':position,'score':'knew'}]})
        self.assertTrue(result['reading_help'])
        self.assertFalse(result['scheduled'])
        self.assertEqual(self.c.execute('SELECT review_count FROM study_positions WHERE id=?',(position,)).fetchone()[0],0)

    def test_shared_target_across_two_originals_has_one_receipt(self):
        first=copy.deepcopy(SEED_READINGS['readings'][0]);second=copy.deepcopy(first)
        second.update(intent_id='no-wonder-second-original',brief_id='no-brief-second-original',
                      source_id=SEED_READINGS['readings'][1]['source_id'],
                      source_quote=SEED_READINGS['readings'][1]['source_quote'])
        self.assertEqual(len(import_reviewed(self.c,{'readings':[first,second]})['added']),2)
        target=first['targets'][0]['id']
        self.assertEqual(len(select(self.c,{'brief_id':first['brief_id'],'target_ids':[target]})['added']),1)
        self.assertEqual(select(self.c,{'brief_id':second['brief_id'],'target_ids':[target]})['added'],[])
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_reading_selections').fetchone()[0],1)

    def test_edited_archived_transcript_cannot_publish_target(self):
        self.imported()
        brief=SEED_READINGS['readings'][0]
        row=self.c.execute('SELECT source FROM study_intake WHERE source_id=?',(brief['source_id'],)).fetchone()
        source=json.loads(row['source']);source['transcript']+=' Edited after review.'
        self.c.execute('UPDATE study_intake SET source=? WHERE source_id=?',(json.dumps(source),brief['source_id']))
        self.c.commit()
        with self.assertRaisesRegex(ValueError,'transcript revision changed'):
            select(self.c,{'brief_id':brief['brief_id'],'target_ids':[brief['targets'][0]['id']]})
        self.assertEqual(self.c.execute('SELECT count(*) FROM study_reading_selections').fetchone()[0],0)


if __name__=='__main__':unittest.main()
