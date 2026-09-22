#!/usr/bin/env python3
"""Import a reviewed Norway reading JSON file through the private server operator.

Usage: python3 scripts/reading_study_readings.py reviewed-readings.json
The input is reviewed content, not a learner capture. No public ingest endpoint is used.
"""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    args=parser.parse_args()
    payload=json.loads(args.file.read_text())
    if not isinstance(payload,dict) or set(payload)!={'readings'}:
        parser.error('Expected {"readings": [...]}')
    result=subprocess.run(
        ['ssh','alif','cd /opt/petrarca && python3 scripts/reading_study_intake_admin.py'],
        input=json.dumps({'action':'readings-import','body':payload},ensure_ascii=False),
        text=True,capture_output=True,timeout=90)
    if result.returncode:
        raise RuntimeError('Reading import failed; inspect server operator error before retrying')
    print(result.stdout.strip().splitlines()[-1])


if __name__=='__main__':main()
