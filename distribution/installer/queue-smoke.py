#!/usr/bin/env python3
"""Create, execute and remove a temporary n8n production webhook workflow."""
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid

STATE = Path.home() / '.local/state/woow-release/2026.11.15-rc1'


def main():
    os.umask(0o077)
    # HTTP health is available before the external task launcher registers.
    # Wait for actual runner registration before submitting a workflow; never
    # hide a failed execution by retrying the same production webhook.
    deadline = time.monotonic() + 600
    while True:
        proc = subprocess.run(['podman', 'logs', 'n8n-worker'], capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and 'Registered runner "launcher-javascript"' in proc.stdout + proc.stderr:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('n8n worker JavaScript launcher did not register')
        time.sleep(5)
    account = json.loads((STATE / 'n8n-account.json').read_text())
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def request(path, data=None, method=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request('http://127.0.0.1:15678/rest' + path, data=body, method=method, headers={'Content-Type': 'application/json'})
        with client.open(req, timeout=60) as response:
            return json.load(response)
    request('/login', {'emailOrLdapLoginId': account['email'], 'password': account['password']})
    marker = 'woow-release-' + uuid.uuid4().hex
    workflow = {'name': marker, 'settings': {'executionOrder': 'v1'}, 'nodes': [
        {'parameters': {'httpMethod': 'POST', 'path': marker, 'responseMode': 'lastNode', 'options': {}}, 'id': 'hook', 'name': 'Webhook', 'type': 'n8n-nodes-base.webhook', 'typeVersion': 2, 'position': [240, 300], 'webhookId': marker},
        {'parameters': {'jsCode': 'return [{json:{probe:"' + marker + '"}}];'}, 'id': 'code', 'name': 'Code', 'type': 'n8n-nodes-base.code', 'typeVersion': 2, 'position': [460, 300]},
    ], 'connections': {'Webhook': {'main': [[{'node': 'Code', 'type': 'main', 'index': 0}]]}}}
    created = request('/workflows', workflow)['data']
    ident = created['id']
    try:
        request('/workflows/' + ident + '/activate', {'versionId': created['versionId']})
        time.sleep(5)
        req = urllib.request.Request('http://127.0.0.1:15679/webhook/' + marker, data=b'{}', headers={'Content-Type': 'application/json'})
        with client.open(req, timeout=120) as response:
            reply = json.load(response)
        assert reply == {'probe': marker} or reply == [{'probe': marker}], 'Code runner result mismatch'
        report = {'owner_login': True, 'worker_launcher_registered_before_execution': True, 'production_webhook_processor': True, 'queued_worker_and_javascript_runner': True, 'returned_unique_code_result': True}
    finally:
        request('/workflows/' + ident + '/deactivate', {})
        request('/workflows/' + ident + '/archive', {})
        request('/workflows/' + ident, method='DELETE')
    report['temporary_workflow_removed'] = True
    (STATE / 'queue-smoke.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
