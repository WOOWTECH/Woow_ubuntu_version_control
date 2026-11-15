#!/usr/bin/env python3
"""Connect new device-local services, without importing another device's identity."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

STATE = Path.home() / '.local/state/woow-release/2026.11.15-rc1'


def secret(name):
    return subprocess.check_output(['podman', 'secret', 'inspect', '--showsecret', '--format', '{{.SecretData}}', name], text=True).strip()


def request(path, token, data=None):
    headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
    body = json.dumps(data).encode() if data is not None else None
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8123' + path, data=body, headers=headers), timeout=45) as response:
        return json.load(response)


def main():
    os.umask(0o077)
    token = secret('homeassistant-mcp-token')
    entries = request('/api/config/config_entries/entry', token)
    mqtt = [entry for entry in entries if entry['domain'] == 'mqtt']
    if not mqtt:
        flow = request('/api/config/config_entries/flow', token, {'handler': 'mqtt', 'show_advanced_options': False})
        if flow.get('step_id') != 'broker':
            raise SystemExit('Unexpected HA MQTT onboarding step; no settings changed.')
        result = request('/api/config/config_entries/flow/' + flow['flow_id'], token, {
            'broker': '127.0.0.1', 'port': 1883, 'username': 'woow',
            'password': secret('woow-emqx-mqtt-password'), 'protocol': '5',
            'other_settings': {'transport': 'tcp', 'set_ca_cert': 'off', 'set_client_cert': False},
        })
        if result.get('type') != 'create_entry':
            raise SystemExit('HA MQTT onboarding failed; credentials were not logged.')
    # Resume never replaces an existing MQTT entry or user-edited agent servers.
    for _ in range(30):
        mqtt = [entry for entry in request('/api/config/config_entries/entry', token) if entry['domain'] == 'mqtt']
        if mqtt and mqtt[0].get('state') == 'loaded':
            break
        time.sleep(2)
    else:
        raise SystemExit('HA MQTT entry is not loaded.')

    root = Path.home() / '.local/share/pi-agent'
    manifest = root / 'data/mcp.json'
    data = json.loads(manifest.read_text()) if manifest.exists() else {'mcpServers': {}}
    changed = 'woow-local-ha' not in data['mcpServers']
    if changed:
        data['mcpServers']['woow-local-ha'] = {'url': 'http://127.0.0.1:9584/mcp'}
        manifest.write_text(json.dumps(data, indent=2) + '\n')
        manifest.chmod(0o600)
        # The installed launcher scopes and synchronizes Pi/Claude/Codex state.
        subprocess.run(['systemctl', '--user', 'restart', 'pi-web.service'], check=True)
    connected = STATE / 'native-omnigent.json'
    connection = root / 'data/omnigent-plugin/connection.json'
    if not connected.exists() and not connection.exists():
        # The supported CLI uses the same lifecycle as Pi Web's settings form.
        # Only this new device's non-admin operator password is sent on stdin.
        result = subprocess.run([root / 'bin/pi-omnigent', 'connect', '--server', 'http://127.0.0.1:8000', '--username', 'operator', '--password-stdin'], input=secret('omnigent-runner-password'), capture_output=True, text=True, timeout=360)
        if result.returncode:
            raise SystemExit('Native Pi Omnigent connection failed; no credential output was emitted.')
        reply = json.loads(result.stdout)
        if not reply.get('ok') or not reply.get('host', {}).get('connected'):
            raise SystemExit('Native Pi host is not connected to local Omnigent.')
        connected.write_text(json.dumps({'connected': True, 'server': 'http://127.0.0.1:8000', 'host_id': reply['host']['id']}) + '\n')
        # Move host ownership to the persistent Pi Web service. A host spawned
        # by this installation job would otherwise die with its systemd cgroup.
        subprocess.run(['systemctl', '--user', 'restart', 'pi-web.service'], check=True)
    report = {'ha_mqtt': 'loaded', 'shared_agent_mcp': 'woow-local-ha', 'native_omnigent_connection_preserved': connection.exists() or connected.exists(), 'external_credentials_copied': False}
    (STATE / 'local-links.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
