#!/usr/bin/env python3
"""Replay explicit editorial decisions and build a local audio/transcript reader."""
import argparse
import html
import json
from pathlib import Path
import re

from reading_study import digest, render, stamp, write_json


def apply_review(rows, review):
    rows = json.loads(json.dumps(rows))
    by_id = {r['id']: r for r in rows}
    for edit in review['edits']:
        row = by_id[edit['segment']]
        if row['text'].count(edit['original']) != 1:
            raise ValueError('Editorial preimage must occur exactly once: ' + edit['segment'])
        row['text'] = row['text'].replace(edit['original'], edit['edited'], 1)
    for row in rows:
        row['review_note'] = review['flags'].get(row['id'])
        row['evidence_kind'] = 'open_book_reading_capture'
    return rows


def build(manifest_path, asr_version, editorial_version):
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text())
    records = manifest['recordings']
    e = html.escape
    sections = []
    durations = 0
    for record in records:
        if not record.get('retranscribe'):
            continue
        rid = record['id']
        source = root / 'recordings' / rid / asr_version
        review = json.loads((source / 'review.json').read_text())
        if review['raw_sha256'] != digest(source / 'raw.json'):
            raise ValueError('ASR evidence changed; review must be performed again.')
        rows = json.loads((source / 'segments.json').read_text())
        edited = apply_review(rows, review)
        dest = root / 'recordings' / rid / editorial_version
        dest.mkdir(parents=True, exist_ok=True)
        binding = dict(review, asr_version=asr_version)
        if (dest / 'binding.json').exists() and json.loads((dest / 'binding.json').read_text()) != binding:
            raise ValueError('Editorial decisions changed; choose a new editorial version.')
        write_json(dest / 'binding.json', binding)
        write_json(dest / 'segments.json', edited)
        text = render(record, edited).replace('New ASR transcription;', 'Annotated ASR transcription;')
        text += '\n\n## Explicit review notes\n\n'
        text += '\n'.join(f"- {r['id']} ({stamp(r['start_ms'])}): {r['review_note']}"
                          for r in edited if r['review_note'])
        (dest / 'transcript.md').write_text(text + '\n')
        metrics = json.loads((source / 'metrics.json').read_text())
        durations += metrics['audio_duration_ms']
        sections.append(f'<section id="{e(rid)}"><h2>{e(record["title"])}</h2>'
                        f'<p>{stamp(metrics["audio_duration_ms"])} · '
                        f'page checkpoints {record["page_checkpoint_start"]}–{record["page_checkpoint_end"]}'
                        f' · <a href="{e(record["tana_link"])}">Original in Tana</a></p>'
                        f'<audio id="audio-{e(rid)}" controls preload="none" src="{e(record["audio_path"])}"></audio>')
        original_by_id = {r['id']: r['text'] for r in rows}
        for row in edited:
            if not re.search(r'\w', row['text']):
                continue
            flag = f'<p class="flag">Review: {e(row["review_note"])}</p>' if row['review_note'] else ''
            raw = original_by_id[row['id']]
            alternative = f'<details><summary>Unedited ASR</summary>{e(raw)}</details>' if raw != row['text'] else ''
            sections.append(f'<article><button data-audio="{e(rid)}" data-start="{row["start_ms"] / 1000}">'
                            f'{stamp(row["start_ms"])} · {e(row["id"])}</button>'
                            f'<p>{e(row["text"])}</p>{flag}{alternative}</article>')
        sections.append('</section>')
    target_path = root / manifest.get('learning_targets_file', 'learning-targets-v1.json')
    targets = json.loads(target_path.read_text()) if target_path.exists() else []
    target_html = []
    for target in targets:
        refs = ' '.join(f'<button data-audio="{e(s["recording"])}" data-start="{s["start_ms"] / 1000}">'
                        f'{e(s["recording"])} {stamp(s["start_ms"])}</button>' for s in target['sources'])
        target_html.append(f'<article><h3>{e(target["title"])}</h3><p>{e(target["candidate_prompt"])}</p>'
                           f'<p>{e(target["selection_reason"])}</p>{refs}</article>')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Norway reading study · BATCH</title><style>
body{max-width:960px;margin:40px auto;padding:0 24px;background:#faf7f0;color:#282923;font:17px/1.6 system-ui}
h1,h2,h3{font-family:Georgia,serif}section{margin:48px 0}article{padding:16px 0;border-bottom:1px solid #d9d4c9}
audio{width:100%;position:sticky;top:0;background:#faf7f0;padding:8px 0}button,input{font:inherit;padding:6px 10px;border:1px solid #a5a598;border-radius:4px;background:white}
button{cursor:pointer;color:#315943;font-size:14px;margin:3px}.flag{border-left:3px solid #af7033;padding-left:12px;color:#76430e}
input{width:100%;box-sizing:border-box}a{color:#315943}summary{cursor:pointer}header p{max-width:800px}
</style><header><h1>Norway reading study</h1><p>BATCH · Recorded reading + spoken notes: DURATION.
Open-book captures, not recall scores. Original audio and ASR versions are preserved. Brackets and amber notes identify unresolved readings.
Tap a timestamp to play the original audio there. These annotations have not all been independently verified by listening.</p>
BASELINES
<input id="search" type="search" placeholder="Search transcripts and selected targets" aria-label="Search transcripts and selected targets"></header>
<details><summary>TARGET_COUNT selected learning targets — proposals, not scheduled questions</summary>TARGETS</details>
SECTIONS<script>
document.querySelectorAll('button[data-audio]').forEach(b=>b.addEventListener('click',()=>{
 const audio=document.getElementById('audio-'+b.dataset.audio);
 document.querySelectorAll('audio').forEach(a=>{if(a!==audio)a.pause()});
 audio.currentTime=Number(b.dataset.start);audio.play().catch(()=>{});
 audio.scrollIntoView({behavior:'smooth',block:'center'});
}));
document.getElementById('search').addEventListener('input',e=>{
 const q=e.target.value.toLocaleLowerCase();
 document.querySelectorAll('article').forEach(a=>a.hidden=!a.textContent.toLocaleLowerCase().includes(q));
});</script></html>'''
    baselines = ''.join(f'<p>{e(r["title"])}: <a href="{e(r["audio_path"])}">Baseline audio</a> · '
                        f'<a href="{e(r["original_transcript_path"])}">Original transcript</a></p>'
                        for r in records if r.get('capture_mode') == 'pre_reading_baseline')
    replacements = {'BATCH': e(str(manifest.get('batch', root.name))),
                    'DURATION': stamp(durations), 'BASELINES': baselines,
                    'TARGET_COUNT': str(len(targets)), 'TARGETS': ''.join(target_html),
                    'SECTIONS': ''.join(sections)}
    document = re.sub('|'.join(replacements), lambda m: replacements[m[0]], document)
    (root / 'index.html').write_text(document)
    return root / 'index.html'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--asr-version', required=True)
    p.add_argument('--editorial-version', required=True)
    a = p.parse_args()
    for value in [a.asr_version, a.editorial_version]:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
            p.error('Version must be a safe directory name.')
    print(build(a.manifest, a.asr_version, a.editorial_version))
