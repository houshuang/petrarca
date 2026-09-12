"""Evidence integrity checks, with no network or production database calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reading_study as study
from reading_study_review import apply_review


class ReadingStudyTests(unittest.TestCase):
    def test_uncertain_dates_and_language_switches_survive_segmentation(self):
        tokens = [{'text': 'Kanskje 3008–3007 f.Kr.?', 'start_ms': 0, 'end_ms': 1500, 'confidence': .4},
                  {'text': ' No, I am not sure.', 'start_ms': 5000, 'end_ms': 7000, 'confidence': .9}]
        rows = study.segments(tokens)
        self.assertEqual([r['text'] for r in rows], ['Kanskje 3008–3007 f.Kr.?', 'No, I am not sure.'])
        self.assertEqual(rows[1]['start_ms'], 5000)
        self.assertIn('3008–3007', study.render({'title': 'Test'}, rows))

    def test_rerun_uses_evidence_and_rejects_changed_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'original.mp3').write_bytes(b'fixture audio')
            record = {'id': 'sample', 'title': 'Test', 'audio_path': 'original.mp3',
                      'capture_mode': 'continuous_book_open_reading'}
            dest = root / 'recordings/sample/v1'
            dest.mkdir(parents=True)
            raw = {'text': 'Kanskje 4000.', 'tokens': [
                {'text': 'Kanskje 4000.', 'start_ms': 5, 'end_ms': 1500, 'confidence': .6}]}
            study.write_json(dest / 'raw.json', raw)
            study.write_json(dest / 'binding.json', {'audio_sha256': study.digest(root / 'original.mp3'),
                'config': {'model': 'stt-async-v5', 'language_hints': ['no', 'en'],
                           'enable_language_identification': True, 'context': {}}, 'source': record})
            with patch.object(study, 'api', side_effect=AssertionError('Must not call API')), \
                 patch.object(study.subprocess, 'check_output', return_value='{"format":{"duration":"20"}}'):
                study.transcribe(record, root, {}, 'v1')
                study.transcribe(record, root, {}, 'v1')
                metrics = json.loads((dest / 'metrics.json').read_text())
                self.assertEqual(metrics['recorded_reading_session_ms'], 20000)
                self.assertIsNone(metrics['active_reading_ms'])
                self.assertEqual(json.loads((dest / 'raw.json').read_text()), raw)
                (root / 'original.mp3').write_bytes(b'different audio')
                with self.assertRaisesRegex(ValueError, 'Inputs changed'):
                    study.transcribe(record, root, {}, 'v1')

    def test_unaligned_result_does_not_become_a_clean_transcript(self):
        self.assertEqual(study.segments([{'text': 'No timing.'}]), [])

    def test_editorial_layer_keeps_raw_unchanged_and_rejects_stale_edits(self):
        rows = [{'id': 's001', 'text': 'Regnvakt. Kanskje 3008–3007?', 'start_ms': 10}]
        review = {'edits': [{'segment': 's001', 'original': 'Regnvakt',
                            'edited': '[trolig reinjakt]'}], 'flags': {'s001': 'Date unresolved'}}
        edited = apply_review(rows, review)
        self.assertTrue(rows[0]['text'].startswith('Regnvakt'))
        self.assertIn('Kanskje 3008–3007?', edited[0]['text'])
        self.assertEqual(edited[0]['review_note'], 'Date unresolved')
        with self.assertRaisesRegex(ValueError, 'preimage'):
            apply_review(edited, review)


if __name__ == '__main__':
    unittest.main()
