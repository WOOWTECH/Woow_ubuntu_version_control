#!/usr/bin/env python3
"""Claim only an unconfigured n8n with a new device-local owner account."""
import json
import os
from pathlib import Path
import secrets
import time
import urllib.request

STATE = Path.home() / '.local/state/woow-release/2026.11.15-rc1'
BASE = 'http://127.0.0.1:15678'


def main():
    os.umask(0o077)
    for _ in range(90):
        try:
            with urllib.request.urlopen(BASE + '/rest/settings', timeout=10) as response:
                settings = json.load(response)['data']['userManagement']
            break
        except (OSError, ValueError):
            time.sleep(3)
    else:
        raise SystemExit('n8n settings endpoint did not become ready.')
    if not settings.get('showSetupOnFirstLoad'):
        print('Existing n8n ownership preserved.')
        return
    path = STATE / 'n8n-account.json'
    if not path.exists():
        path.write_text(json.dumps({'email': 'admin@example.invalid', 'password': 'Aa1!' + secrets.token_urlsafe(30), 'firstName': 'WOOW', 'lastName': 'Administrator'}) + '\n')
        path.chmod(0o600)
    request = urllib.request.Request(BASE + '/rest/owner/setup', data=path.read_bytes(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise SystemExit('n8n owner setup did not succeed.')
    print('New n8n owner created; credential kept in private device state.')


if __name__ == '__main__':
    main()
