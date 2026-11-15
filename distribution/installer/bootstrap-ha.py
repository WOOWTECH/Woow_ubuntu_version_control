#!/usr/bin/env python3
"""Create a new device's HA account and its local MCP credential via HA APIs."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'http://127.0.0.1:8123'
CLIENT = BASE + '/'
STATE = Path.home() / '.local/state/woow-release/2026.11.15-rc1'

def request(path, data=None, token=None, form=False):
    headers = {}
    if data is not None:
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        data = (urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=headers), timeout=60) as r:
        return json.load(r)

def main():
    os.umask(0o077)
    if subprocess.run(['podman', 'secret', 'exists', 'homeassistant-mcp-token']).returncode == 0:
        print('HA MCP credential already provisioned; kept.')
        return
    for attempt in range(90):
        try:
            steps = request('/api/onboarding')
            break
        except (OSError, ValueError):
            time.sleep(4)
    else:
        raise SystemExit('HA did not become ready for onboarding.')
    account_file = STATE / 'ha-account.json'
    if not account_file.exists():
        if next((s['done'] for s in steps if s['step'] == 'user'), True):
            raise SystemExit('HA already has an owner; refusing to replace it.')
        account_file.write_text(json.dumps({'username': 'admin', 'password': secrets.token_urlsafe(32)}))
        account_file.chmod(0o600)
    account = json.loads(account_file.read_text())
    if not next(s['done'] for s in steps if s['step'] == 'user'):
        code = request('/api/onboarding/users', {'client_id': CLIENT, 'name': 'Administrator', **account, 'language': 'zh-Hant'})['auth_code']
    else:
        flow = request('/auth/login_flow', {'client_id': CLIENT, 'handler': ['homeassistant', None], 'redirect_uri': CLIENT})
        response = request('/auth/login_flow/' + flow['flow_id'], {'client_id': CLIENT, **account})
        code = response['result']
    token = request('/auth/token', {'grant_type': 'authorization_code', 'code': code, 'client_id': CLIENT}, form=True)['access_token']
    for step in ('core_config', 'analytics', 'integration'):
        if not next((s['done'] for s in steps if s['step'] == step), True):
            data = {'client_id': CLIENT, 'redirect_uri': CLIENT} if step == 'integration' else {}
            request('/api/onboarding/' + step, data, token)
    code = '''import asyncio,aiohttp,json,sys
async def main():
 token=json.load(sys.stdin)['token']
 async with aiohttp.ClientSession() as s:
  async with s.ws_connect('http://127.0.0.1:8123/api/websocket') as ws:
   await ws.receive_json()
   await ws.send_json({'type':'auth','access_token':token})
   auth=await ws.receive_json()
   if auth.get('type')!='auth_ok':raise RuntimeError('HA websocket authentication failed')
   await ws.send_json({'id':1,'type':'auth/long_lived_access_token','client_name':'WOOW local HA MCP','lifespan':3650})
   r=await ws.receive_json()
   if not r.get('success'):raise RuntimeError('HA MCP token creation failed')
   print(r['result'])
asyncio.run(main())
'''
    value = subprocess.check_output(['podman', 'exec', '-i', 'homeassistant', 'python', '-c', code], input=json.dumps({'token': token}).encode()).strip()
    subprocess.run(['podman', 'secret', 'create', 'homeassistant-mcp-token', '-'], input=value, check=True, stdout=subprocess.DEVNULL)
    print('New HA account and device-local MCP credential created. Credentials remain in the private device state.')

if __name__ == '__main__':
    main()
