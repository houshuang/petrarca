#!/usr/bin/env python3
"""Explicit admin import / focus restoration / immutable, analysis-ready export."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['activate','restore','export','status','retry-transcription'])
    p.add_argument('--seed', default='research/norway-reading-study/intensive-v2.json')
    p.add_argument('--sources', default='research/norway-reading-study/sources-v1.json')
    p.add_argument('--output', help='New private export directory; never overwrite a prior export')
    args = p.parse_args()
    from curriculum_db import study_action
    from db import get_connection
    if args.action == 'activate':
        commit = subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        print(json.dumps(study_action('install', json.loads(Path(args.seed).read_text()),
                         sources=json.loads(Path(args.sources).read_text()),code_commit=commit)))
    elif args.action == 'status':
        print(json.dumps(study_action('status')))
    else:
        conn = get_connection()
        try:
            if args.action == 'restore':
                conn.execute('BEGIN IMMEDIATE')
                conn.execute('UPDATE study_focus SET active=0 WHERE id=1')
                payload = json.dumps({'action':'restore_other_cards','prior_schedules':'untouched'})
                conn.execute('INSERT INTO study_revisions VALUES(?,?,?,?,?,?)',
                  (f'restore-{time.time_ns()}','norway-reading-2026',int(time.time()*1000),
                   subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'focus-disabled',payload))
                conn.commit(); print('Other cards restored; study data and all prior schedules retained.')
            elif args.action == 'retry-transcription':
                cursor = conn.execute("UPDATE study_audio SET transcription_status='pending' WHERE transcription_status='failed'")
                conn.commit(); print(f'Requeued {cursor.rowcount} failed transcriptions; original audio unchanged.')
            else:
                if not args.output: p.error('--output required')
                out = Path(args.output); out.mkdir(parents=True,exist_ok=False,mode=0o700)
                conn.execute('BEGIN')  # All export tables share one consistent SQLite snapshot.
                manifest = {'created_at_ms':int(time.time()*1000),'files':{},'interpretation':
                  'Observational single-reader study. Shown is exposure, grades are self-report; raw speech is not verified understanding. Join events to runs.snapshot to items.sources and study_sources.'}
                for table in ['study_focus','study_sources','study_revisions','study_items','study_positions','study_runs','study_events','study_audio','study_transcriptions','study_audio_attempts','study_assessments','study_intake','study_intake_events','study_monthly_samples']:
                    rows = [dict(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                    content = ''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows)
                    path = out/(table+'.jsonl'); path.write_text(content); os.chmod(path,0o600)
                    manifest['files'][path.name] = {'rows':len(rows),'sha256':hashlib.sha256(content.encode()).hexdigest()}
                conn.rollback()
                (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
                print(json.dumps(manifest,indent=2))
        finally: conn.close()

if __name__ == '__main__': main()
