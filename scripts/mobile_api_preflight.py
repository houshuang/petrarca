#!/usr/bin/env python3
"""Check the private URL without exposing it in command output or errors."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request


def private_url() -> str:
    path = Path(os.environ.get('PETRARCA_MOBILE_CAPABILITY_FILE',
                               '~/.config/petrarca/mobile-api-capability')).expanduser()
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Mobile API capability must be a private regular file (mode 0600)')
    capability = path.read_text().strip()
    if not re.fullmatch(r'petrarca-mobile-[0-9a-f]{64}', capability):
        raise ValueError('Invalid mobile API capability')
    return f'https://alifstian.duckdns.org/{capability}'


def main() -> None:
    try:
        url = private_url()
        with urllib.request.urlopen(url + '/health', timeout=10) as response:
            if json.load(response).get('status') != 'ok':
                raise ValueError('Mobile API health check failed')
        env = dict(os.environ, PETRARCA_API_URL=url)
        if sys.argv[1:] == ['--check']:
            result = subprocess.run(['npx', 'expo', 'config', '--json'], env=env,
                                    capture_output=True, text=True, check=True)
            if json.loads(result.stdout)['extra'].get('researchServerUrl') != url:
                raise ValueError('Expo config does not contain the private API URL')
            print('Private HTTPS API and Expo release configuration verified.')
        else:
            # Credentials enter the child environment, never argv or stdout.
            sys.exit(subprocess.run(sys.argv[1:], env=env).returncode)
    except Exception:
        raise SystemExit('Private mobile API preflight failed. Check the capability file and HTTPS gateway.') from None


if __name__ == '__main__':
    main()
