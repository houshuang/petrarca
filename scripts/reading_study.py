#!/usr/bin/env python3
"""Versioned research transcription artifacts; never writes Petrarca runtime data.

Input manifest: {recordings: [{id, audio_path, original_transcript_path, ...}]}.
Paths are relative to the manifest. Requires ffprobe and SONIOX_API_KEY.
Raw audio, ASR tokens and source metadata remain separate from interpretations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def stamp(ms):
    seconds = int(ms / 1000)
    return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'


def segments(tokens):
    """Group source tokens without rewriting numbers, hesitations or uncertainty."""
    output, current = [], []
    for token in tokens:
        if token.get('is_audio_event') or token.get('translation_status') == 'translation':
            continue
        if token.get('start_ms') is None or token.get('end_ms') is None:
            continue
        if current:
            text = ''.join(t['text'] for t in current)
            gap = token['start_ms'] - current[-1]['end_ms']
            if gap > 2500 or (len(text) > 500 and text.rstrip().endswith(('.', '?', '!'))):
                output.append(current)
                current = []
        current.append(token)
    if current:
        output.append(current)
    return [{'id': f's{i + 1:03}', 'start_ms': row[0]['start_ms'],
             'end_ms': row[-1]['end_ms'],
             'text': ''.join(t['text'] for t in row).strip(),
             'min_token_confidence': min((t.get('confidence', 1) for t in row), default=1)}
            for i, row in enumerate(output)]


def render(record, rows):
    lines = [f"# {record['title']}", '',
             'New ASR transcription; not an audio-verified or historically corrected reference.',
             'Timestamps are offsets in the original audio. Keep the original Tana version.', '']
    for row in rows:
        lines += [f"## {stamp(row['start_ms'])}–{stamp(row['end_ms'])} · {row['id']}", '', row['text'], '']
    return '\n'.join(lines)


def api(method, path, payload=None, content_type='application/json'):
    key = os.environ.get('SONIOX_API_KEY')
    if not key:
        raise RuntimeError('Set SONIOX_API_KEY in the process environment.')
    body = json.dumps(payload).encode() if isinstance(payload, dict) else payload
    request = urllib.request.Request('https://api.soniox.com/v1' + path, data=body,
        method=method, headers={'Authorization': 'Bearer ' + key, 'Content-Type': content_type})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read()
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as exc:
        # Never log request headers or signed audio URLs.
        raise RuntimeError(f'Soniox {method} {path.split("/")[1]} returned HTTP {exc.code}') from None


def cleanup(job):
    for field, endpoint in [('transcription_id', '/transcriptions/'), ('file_id', '/files/')]:
        if job.get(field):
            try:
                api('DELETE', endpoint + job[field])
            except RuntimeError:
                return False
    return True


def transcribe(record, root, context, version):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', record['id']) or not re.fullmatch(r'[A-Za-z0-9_-]+', version):
        raise ValueError('Recording id and version must be safe directory names.')
    audio = (root / record['audio_path']).resolve()
    audio_hash = digest(audio)
    if record.get('audio_sha256') and record['audio_sha256'] != audio_hash:
        raise ValueError('Audio no longer matches the archived manifest hash.')
    destination = root / 'recordings' / record['id'] / version
    destination.mkdir(parents=True, exist_ok=True)
    config = {'model': 'stt-async-v5', 'language_hints': record.get('languages', ['no', 'en']),
              'enable_language_identification': True, 'context': context}
    binding = {'audio_sha256': audio_hash, 'config': config, 'source': record}
    binding_path = destination / 'binding.json'
    if (destination / 'raw.json').exists() and not binding_path.exists():
        raise ValueError('Existing raw ASR has no input binding; do not adopt unbound evidence.')
    if binding_path.exists() and json.loads(binding_path.read_text()) != binding:
        raise ValueError('Inputs changed: choose a new version; never overwrite prior evidence.')
    write_json(binding_path, binding)
    raw_path, job_path = destination / 'raw.json', destination / 'job.json'
    job = json.loads(job_path.read_text()) if job_path.exists() else {}
    if not raw_path.exists():
        if not job.get('file_id'):
            boundary = 'study' + uuid.uuid4().hex
            body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                    f'filename="audio.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n').encode()
            body += audio.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
            job['file_id'] = api('POST', '/files', body, 'multipart/form-data; boundary=' + boundary)['id']
            write_json(job_path, job)
        if not job.get('transcription_id'):
            job['transcription_id'] = api('POST', '/transcriptions', dict(config, file_id=job['file_id']))['id']
            write_json(job_path, job)
        print(record['id'], 'processing', flush=True)
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            status = api('GET', '/transcriptions/' + job['transcription_id'])
            if status['status'] == 'completed':
                break
            if status['status'] == 'error':
                raise RuntimeError('ASR job failed; saved job metadata allows investigation.')
            time.sleep(3)
        else:
            raise RuntimeError('ASR still pending; rerun the same version to resume.')
        raw = api('GET', '/transcriptions/' + job['transcription_id'] + '/transcript')
        if not raw.get('tokens'):
            raise ValueError('Empty ASR result; preserve job and do not mark complete.')
        write_json(raw_path, raw)
    raw = json.loads(raw_path.read_text())
    rows = segments(raw['tokens'])
    if not rows:
        raise ValueError('No timestamped speech segments; manual inspection required.')
    write_json(destination / 'segments.json', rows)
    (destination / 'transcript.md').write_text(render(record, rows))
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'quiet', '-show_format',
                                               '-of', 'json', str(audio)], text=True))
    duration = round(float(probe['format']['duration']) * 1000)
    reading_mode = record.get('capture_mode') == 'continuous_book_open_reading'
    metrics = {'audio_duration_ms': duration,
               'recorded_reading_session_ms': duration if reading_mode else None,
               'asr_words': len(raw['text'].split()), 'segments': len(rows),
               'active_reading_ms': None, 'unaided_recall_ms': None,
               'measurement_note': 'Continuous recording measures reading + notes + any unmarked breaks. It does not isolate active reading or demonstrate unaided recall.'}
    write_json(destination / 'metrics.json', metrics)
    candidates = [dict(row, reasons=[reason for reason, yes in [
        ('contains_number', bool(re.search(r'\d', row['text']))),
        ('low_ASR_confidence', row['min_token_confidence'] < 0.65),
        ('reader_uncertainty', bool(re.search(r'\b(kanskje|usikker|vet ikke|lurer|tror|maybe|not sure)\b', row['text'], re.I)))] if yes])
        for row in rows]
    write_json(destination / 'review-candidates.json', [r for r in candidates if r['reasons']])
    if job and not job.get('remote_cleaned'):
        job['remote_cleaned'] = cleanup(job)
        write_json(job_path, job)
    print(record['id'], 'complete', metrics['audio_duration_ms'], 'ms', flush=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--recording', help='Transcribe one recording ID; default all marked for retranscription.')
    args = parser.parse_args()
    records = json.loads(args.manifest.read_text())['recordings']
    context = json.loads(args.context.read_text())
    chosen = [r for r in records if (r['id'] == args.recording if args.recording else r.get('retranscribe'))]
    if not chosen:
        parser.error('No matching recordings.')
    for record in chosen:
        transcribe(record, args.manifest.parent, context, args.version)


if __name__ == '__main__':
    main()
