#!/usr/bin/env python3
"""Private stdin-JSON operator interface; never exposed as a public HTTP route."""
import json
import sys
from curriculum_db import study_action
from db import init_db

if __name__ == '__main__':
    init_db()
    request = json.load(sys.stdin)
    if request.get('action') not in ('intake', 'monthly'):
        raise ValueError('Only intake and monthly operator actions are allowed')
    print(json.dumps(study_action(request['action'], request.get('body', {})), ensure_ascii=False))
