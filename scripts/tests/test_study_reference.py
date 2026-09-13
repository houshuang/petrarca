import json
import unittest
from test_study import connect,engine,SEED
class ReferenceTests(unittest.TestCase):
    def test_exposure_is_versioned_without_changing_practice(self):
        c=connect();engine.install(c,SEED)
        prior=list(c.execute('SELECT payload FROM study_items'))
        run=engine.session(c,{'request_id':'reference_fixture_12345','mode':'reference','aid':'ard'})
        self.assertIn('assets',run['reference'])
        result=engine.event(c,{'request_id':'reference_event_12345','run_id':run['run_id'],'item_id':run['items'][0]['id'],'event':'shown','detail':{'phase':'explanation'}})
        self.assertFalse(result['scheduled'])
        for event in ('complete','introduced'):
            with self.assertRaises(ValueError):engine.event(c,{'request_id':'reference_invalid_'+event,'run_id':run['run_id'],'item_id':run['items'][0]['id'],'event':event})
        self.assertEqual(prior,list(c.execute('SELECT payload FROM study_items')))
        self.assertEqual(c.execute('SELECT sum(review_count) FROM study_positions').fetchone()[0],0)
        c.close()
