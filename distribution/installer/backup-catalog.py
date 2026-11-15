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
        if app['id'] == 'emqx':
            # /readyz is intentionally private to the container namespace.
            # A host probe sees Podman's translated address and is denied.
            # Use the host-reachable entrance check; the release drill also
            # verifies an authenticated MQTT read after actual data restore.
            for check in entry.get('health', []):
                if check.get('url') == 'http://127.0.0.1:18083/readyz':
                    check['url'] = 'http://127.0.0.1:18083/healthz'
        if app['id'] == 'homeassistant':
            for check in entry.get('health', []):
                if check.get('url') == 'http://127.0.0.1:9584/mcp':
                    # Streamable HTTP MCP accepts POST, not a health-check GET.
                    # 405 is its expected GET response; local-smoke.py tests
                    # actual initialize/tools/list separately.
                    check['expect_status'] = 405
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
