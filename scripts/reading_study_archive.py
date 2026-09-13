#!/usr/bin/env python3
"""Immutable private source archive, checksum verification and explicit backup/restore check."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def archive(source, audio, transcript, destination):
    audio=Path(audio);transcript=Path(transcript);root=Path(destination)
    signature=sha(audio)
    if source.get('audio_sha256') and source['audio_sha256']!=signature:
        raise ValueError('Original audio checksum mismatch')
    if not audio.stat().st_size:raise ValueError('Empty audio file')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    out=root/signature
    text=transcript.read_text()
    metadata={k:v for k,v in source.items() if k not in ('audio_url','transcript')}
    metadata.update(audio_sha256=signature,audio_path='original.audio',original_transcript_path='original-transcript.txt')
    if out.exists():
        verified=verify(out)
        existing=json.loads((out/'source.json').read_text())
        if existing!=metadata or sha(out/'original-transcript.txt')!=sha(transcript):
            raise ValueError('Archive identity exists with different metadata/transcript; preserve a separate revision')
        return out,verified
    temporary=Path(tempfile.mkdtemp(prefix='.archiving-',dir=root))
    try:
        shutil.copyfile(audio,temporary/'original.audio')
        (temporary/'original-transcript.txt').write_text(text)
        (temporary/'source.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
        files={p.name:sha(p) for p in temporary.iterdir()}
        (temporary/'checksums.json').write_text(json.dumps(files,indent=2)+'\n')
        for p in temporary.iterdir():os.chmod(p,0o600)
        verify(temporary)
        temporary.rename(out)
        return out,files
    finally:
        if temporary.exists():shutil.rmtree(temporary)


def verify(root):
    root=Path(root);files=json.loads((root/'checksums.json').read_text())
    for name,expected in files.items():
        if Path(name).name!=name or (root/name).is_symlink():raise ValueError('Invalid archive file')
        if sha(root/name)!=expected:raise ValueError('Archive checksum mismatch: '+name)
    return files


def backup(source, destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('Backup must be separate from source')
    files=verify(source)
    if destination.exists():
        if verify(destination)!=files:raise ValueError('Existing backup differs; do not overwrite')
    else:
        destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        shutil.copytree(source,destination)
    verify(destination)
    with tempfile.TemporaryDirectory(prefix='petrarca-restore-') as tmp:
        restored=Path(tmp)/'restored.audio';shutil.copyfile(destination/'original.audio',restored)
        if sha(restored)!=files['original.audio']:raise ValueError('Restore failed')
    return {'files_verified':len(files),'audio_restore_verified':True,
            'different_filesystem':source.stat().st_dev!=destination.stat().st_dev,
            'independent_backup':'Destination ownership/durability must be established separately; a same-disk copy is not independent.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['archive','verify','backup'])
    p.add_argument('--source',required=True);p.add_argument('--audio');p.add_argument('--transcript');p.add_argument('--destination')
    a=p.parse_args()
    if a.action=='archive':
        if not all([a.audio,a.transcript,a.destination]):p.error('archive needs --audio --transcript --destination')
        out,result=archive(json.loads(Path(a.source).read_text()),a.audio,a.transcript,a.destination)
        print(json.dumps({'archive':str(out),'files':result}))
    elif a.action=='verify':print(json.dumps(verify(a.source)))
    else:
        if not a.destination:p.error('backup needs --destination')
        print(json.dumps(backup(a.source,a.destination)))

if __name__=='__main__':main()
