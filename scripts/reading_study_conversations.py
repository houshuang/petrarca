#!/usr/bin/env python3
"""Snapshot user/assistant text from explicitly registered local study conversations.

Excludes tool payloads, reasoning, system/developer instructions and image bytes.
Produces private research evidence, never Petrarca runtime records.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def messages(data, provider, source_id):
    for number, line in enumerate(data.splitlines(), 1):
        record = json.loads(line)
        if provider == 'codex':
            if record.get('type') != 'response_item':
                continue
            message = record.get('payload', {})
            if message.get('type') != 'message':
                continue
        elif provider == 'claude':
            if record.get('type') not in ('user', 'assistant'):
                continue
            message = record.get('message', {})
        else:
            raise ValueError('Unsupported provider: ' + provider)
        role = message.get('role')
        if role not in ('user', 'assistant') or message.get('channel') == 'analysis':
            continue
        content = message.get('content', [])
        blocks = [{'type': 'text', 'text': content}] if isinstance(content, str) else content
        text = '\n'.join(block.get('text', '') for block in blocks
                         if block.get('type') in ('text', 'input_text', 'output_text'))
        if not text.strip():
            continue
        if text.lstrip().startswith(('# AGENTS.md instructions', '<environment_context>',
                                    '<permissions instructions>', '<skills_instructions>',
                                    '<recommended_plugins>', '<task-notification>',
                                    '[Request interrupted by user')):
            continue
        yield {'id': f'{source_id}-L{number}', 'source': source_id, 'line': number,
               'timestamp': record.get('timestamp'), 'role': role,
               'provider_message_id': message.get('id') or record.get('uuid'),
               'text_sha256': sha(text.encode()), 'text': text,
               'nontext_blocks_omitted': sum(b.get('type') not in
                   ('text', 'input_text', 'output_text') for b in blocks)}


def snapshot(registry_path, output):
    registry = json.loads(registry_path.read_text())
    output.mkdir(parents=True, exist_ok=True)
    sources, all_rows = [], []
    for source in registry['sources']:
        path = Path(source['path'])
        data = path.read_bytes()
        # A running logger can have an unfinished final JSON line. Export only
        # complete lines and record the precise prefix, rather than inventing it.
        if data and not data.endswith(b'\n'):
            try:
                json.loads(data.splitlines()[-1])
            except json.JSONDecodeError:
                data = data[:data.rfind(b'\n') + 1]
        rows = list(messages(data, source['provider'], source['id']))
        sources.append(dict(source, captured_prefix_bytes=len(data),
                            captured_prefix_sha256=sha(data), messages=len(rows)))
        all_rows.extend(rows)
    encoded = json.dumps(all_rows, ensure_ascii=False, sort_keys=True).encode()
    revision = sha(encoded)[:16]
    dest = output / 'snapshots' / revision
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / 'coverage.json').exists():
        coverage = {'exported_at_utc': datetime.now(timezone.utc).isoformat(),
                    'revision': revision, 'sources': sources, 'messages': len(all_rows),
                    'scope': registry['scope'],
                    'exclusions': 'Tool payloads, reasoning, system/developer messages, environment-only packets, image bytes. Not a full raw-log backup.'}
        (dest / 'coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2)+'\n')
        (dest / 'messages.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in all_rows))
        for source in sources:
            lines = [f'# {source["title"]}', '',
                     'Historical conversation evidence. Assistant statements may be wrong or superseded; see the decision/correction ledger.', '']
            for row in [r for r in all_rows if r['source'] == source['id']]:
                lines += [f'<a id="{row["id"]}"></a>',
                          f'## {row["id"]} · {row["timestamp"]} · {row["role"]}', '', row['text'], '']
            (dest / (source['id']+'.md')).write_text('\n'.join(lines))
    (output / 'current.json').write_text(json.dumps({'revision': revision,
        'snapshot': str(dest), 'messages': len(all_rows)}, indent=2)+'\n')
    links = [f'- [{s["title"]}](snapshots/{revision}/{s["id"]}.md): {s["messages"]} messages'
             for s in sources]
    (output / 'README.md').write_text('# Study conversation archive\n\n'+
        '\n'.join(links)+f'\n\n[Coverage and exclusions](snapshots/{revision}/coverage.json) · '
        f'[Searchable message records](snapshots/{revision}/messages.jsonl)\n\n'+
        'Only registered local sessions are included. Snapshots preserve earlier exported text; this is a manually refreshed archive, not an automatic recorder of every future chat.\n')
    return {'revision': revision, 'messages': len(all_rows),
            'sources': [{k:s[k] for k in ('id', 'messages')} for s in sources]}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--registry', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(snapshot(a.registry, a.out), indent=2))
