#!/usr/bin/env python3
"""Exercise local HA/MQTT/MCP and shared agent configuration; no model calls."""
import importlib.util
import json
import os
from pathlib import Path
import time
import tomllib
import urllib.request
import uuid

spec = importlib.util.spec_from_file_location('links', Path(__file__).with_name('local-links.py'))
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)


def main():
    os.umask(0o077)
    token = links.secret('homeassistant-mcp-token')
    ident = 'woow_release_' + uuid.uuid4().hex[:12]
    discovery = 'homeassistant/sensor/' + ident + '/config'
    topic = 'woow/release-test/' + ident + '/state'
    def publish(target, payload):
        links.request('/api/services/mqtt/publish', token, {'topic': target, 'payload': payload, 'qos': 1, 'retain': True})
    try:
        publish(discovery, json.dumps({'name': ident, 'unique_id': ident, 'state_topic': topic}))
        publish(topic, '23.75')
        for _ in range(30):
            states = links.request('/api/states', token)
            if any(s['entity_id'] == 'sensor.' + ident and s['state'] == '23.75' for s in states):
                break
            time.sleep(2)
        else:
            raise SystemExit('HA MQTT discovery/state round trip failed.')
    finally:
        publish(discovery, '')
        publish(topic, '')

    headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
    def mcp(method, params=None, ident=1):
        body = {'jsonrpc': '2.0', 'id': ident, 'method': method}
        if params is not None:
            body['params'] = params
        req = urllib.request.Request('http://127.0.0.1:9584/mcp', data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            session = response.headers.get('mcp-session-id')
            if session:
                headers['Mcp-Session-Id'] = session
            if 'text/event-stream' in response.headers.get('Content-Type', ''):
                for line in response:
                    if line.startswith(b'data: '):
                        return json.loads(line[6:])
            return json.load(response)
    initialized = mcp('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {}, 'clientInfo': {'name': 'woow-release-smoke', 'version': '1'}})
    if 'result' not in initialized:
        raise SystemExit('HA MCP initialization failed.')
    tools = mcp('tools/list', ident=2).get('result', {}).get('tools', [])
    if not tools:
        raise SystemExit('HA MCP returned no tools.')
    root = Path.home() / '.local/share/pi-agent'
    shared = json.loads((root / 'data/mcp.json').read_text())['mcpServers']['woow-local-ha']['url']
    claude = json.loads((root / 'home/.claude.json').read_text())['mcpServers']['woow-local-ha']['url']
    codex = tomllib.loads((root / 'home/.codex/config.toml').read_text())['mcp_servers']['woow-local-ha']['url']
    if shared != claude or shared != codex:
        raise SystemExit('Agent MCP settings differ.')
    report = {'ha_mqtt_discovery_and_state': True, 'ha_mcp_tool_count': len(tools), 'pi_claude_codex_share_ha_mcp': True, 'external_model_called': False}
    (links.STATE / 'local-smoke.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
