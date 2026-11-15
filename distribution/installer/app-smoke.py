#!/usr/bin/env python3
"""Authenticated Nextcloud file round trip and Odoo tenant login on a new device."""
import base64
import json
import os
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET

STATE = Path.home() / '.local/state/woow-release/2026.11.15-rc1'


def secret(name):
    return subprocess.check_output(['podman', 'secret', 'inspect', '--showsecret', '--format', '{{.SecretData}}', name], text=True).strip()


def main():
    os.umask(0o077)
    env = dict(line.split('=', 1) for line in (Path.home() / '.config/nextcloud/nextcloud.env').read_text().splitlines() if line and not line.startswith('#') and '=' in line)
    user = env['NEXTCLOUD_ADMIN_USER']
    auth = 'Basic ' + base64.b64encode((user + ':' + secret('nextcloud-admin-password')).encode()).decode()
    url = 'http://127.0.0.1:18081/remote.php/dav/files/' + urllib.parse.quote(user, safe='') + '/woow-release-' + uuid.uuid4().hex + '.txt'
    payload = b'WOOW fresh device WebDAV acceptance\n'
    def dav(method, data=None):
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers={'Authorization': auth}), timeout=60) as response:
            return response.status, response.read()
    try:
        assert dav('PUT', payload)[0] in (201, 204)
        assert dav('GET')[1] == payload
    finally:
        dav('DELETE')
    with urllib.request.urlopen('http://127.0.0.1:18081/hosting/discovery', timeout=30) as response:
        document = ET.fromstring(response.read())
    assert document.tag == 'wopi-discovery' and document.findall('.//action')
    data = {'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': {'db': 'odoo', 'login': 'admin@example.invalid', 'password': secret('odoo18-odoo-admin-password')}}
    request = urllib.request.Request('http://127.0.0.1:18080/web/session/authenticate', data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=60) as response:
        authenticated = json.load(response)
    assert authenticated.get('result', {}).get('uid'), 'Odoo administrator login failed'
    report = {'nextcloud_webdav_write_read_delete': True, 'collabora_discovery': True, 'odoo_tenant_admin_login': True, 'office_editing_tested': False}
    (STATE / 'app-smoke.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
