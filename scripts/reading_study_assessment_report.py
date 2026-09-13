#!/usr/bin/env python3
"""Compare assessment transcripts from an immutable study export; no inferred scores."""
import argparse
import json
from pathlib import Path


def rows(root, name):
    return [json.loads(line) for line in (root/(name+'.jsonl')).read_text().splitlines()]


def report(root):
    runs = {r['id']:r for r in rows(root,'study_runs') if r['mode']=='assessment'}
    events = rows(root,'study_events')
    audio = rows(root,'study_audio')
    lines = ['# Recorded understanding over time','',
             'Private: verbatim responses; no automatic scores. Missing audio/transcripts are not zero knowledge.','']
    if not runs:
        return '\n'.join(lines+['No formal assessment recordings in this export.',''])
    grouped={}
    for run in runs.values():
        snapshot=json.loads(run['snapshot']);context=snapshot['assessment']
        for item in snapshot['items']:
            grouped.setdefault((context['volume'],item['id']),[]).append((run,snapshot,item))
    for (volume,item_id),encounters in sorted(grouped.items()):
        lines.extend([f'## Bind {volume} · {encounters[0][2]["title"]}',''])
        for run,snapshot,item in sorted(encounters,key=lambda x:x[0]['created_at']):
            context=snapshot['assessment']
            lines += [f'### {context["occasion"]} · {run["created_at"]} ms UTC',
                f'Run `{run["id"]}` · {context["coverage"]} · {context["help_state"]} · {snapshot["protocol"]["version"]}',
                '',item['text'],'']
            observed=[e for e in events if e['run_id']==run['id'] and e['item_id']==item_id]
            for e in observed:
                detail=json.loads(e['payload']).get('detail',{})
                if e['event']=='assessment_advance': lines += [f'Outcome: {detail.get("outcome")}', '']
                if detail.get('dimension')=='assessment_confidence':lines += [f'Pre-response confidence: {detail.get("value")}', '']
            clips=[a for a in audio if a['run_id']==run['id'] and a['item_id']==item_id]
            if not clips:lines += ['No saved audio for this prompt.','']
            for a in clips:
                lines += [f'Audio `{a["id"]}` · SHA-256 `{a["sha256"]}` · ASR {a["transcription_status"]}',
                    '',a['transcript'] or '[Transcript unavailable; inspect original audio.]','']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--export',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    with args.out.open('x') as f:f.write(report(args.export))
    args.out.chmod(0o600)

if __name__=='__main__':main()
