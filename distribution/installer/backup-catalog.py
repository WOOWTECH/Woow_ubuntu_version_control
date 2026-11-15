#!/usr/bin/env python3
"""Enroll this release's Quadlet applications in Cockpit's trusted backup catalog."""
import json
from pathlib import Path
import subprocess

HELPER = '/usr/local/libexec/woowtech-cockpit-backup'
STATE = Path.home() / '.local/state/woow-release/2026.11.15-rc1'

def call(command, data=None):
    result = subprocess.run(['sudo', HELPER, command], input=json.dumps(data or {}).encode() if data is not None else None, capture_output=True)
    response = json.loads(result.stdout)
    if result.returncode or not response.get('ok'):
        raise RuntimeError(f'{command}: {response.get("error", {}).get("code", "failed")}')
    return response

def main():
    owner = subprocess.check_output(['id', '-un'], text=True).strip()
    draft = call('catalog-suggest', {'owner': owner})
    records = []
    for app in draft['apps']:
        if app.get('installed'):
            records.append({'id': app['id'], 'result': 'kept'})
            continue
        if not app['valid']:
            records.append({'id': app['id'], 'result': 'invalid', 'field': app.get('field')})
            continue
        entry = app['entry']
        # Keep the default cold snapshot: no inference about a database role's
        # permissions, active writers or logical-restore semantics.
        preview = call('catalog-install', {'entry': entry})
        call('catalog-install', {'entry': entry, 'confirm': True, 'expected_sha256': None})
        records.append({'id': app['id'], 'result': 'installed', 'skipped': app['skipped'], 'warnings': app['warnings']})
    dest = STATE / 'backup-catalog.json'
    dest.write_text(json.dumps(records, indent=2, ensure_ascii=False) + '\n')
    dest.chmod(0o600)
    print(json.dumps([{'id': r['id'], 'result': r['result']} for r in records]))
    if any(r['result'] == 'invalid' for r in records):
        raise SystemExit('Some backup entries need review; see private backup-catalog.json')

if __name__ == '__main__':
    main()
