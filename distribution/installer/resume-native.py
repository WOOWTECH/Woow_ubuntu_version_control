#!/usr/bin/env python3
"""Resume an already-authorized local host after cold boot; never log in."""
import json
from pathlib import Path
import subprocess
import time
import urllib.request


def main():
    root = Path.home() / '.local/share/pi-agent'
    receipt = root / 'data/omnigent-plugin/connection.json'
    if not receipt.is_file():
        print('No recorded connection; waiting for explicit setup.')
        return
    proof = json.loads(receipt.read_text())
    if proof.get('server') != 'http://127.0.0.1:8000':
        print('User selected a different server; local bootstrap skipped.')
        return
    deadline = time.monotonic() + 780
    attempts = 0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=10) as response:
                if response.status != 200:
                    raise ValueError('Local server is starting.')
            # The supported boot command validates login consent, installation
            # and host identity itself. It does not perform a model conversation.
            attempts += 1
            boot = subprocess.run([root / 'bin/pi-omnigent', 'boot'], capture_output=True, text=True, timeout=180)
            data = json.loads(boot.stdout) if boot.returncode == 0 else {}
            resumed = data.get('resumption', {})
            if resumed.get('resumed') and resumed.get('host', {}).get('id') == proof['host']['id']:
                print('Authorized local Omnigent host resumed; attempts=' + str(attempts))
                return
            reason = resumed.get('reason') or resumed.get('error', {}).get('code')
            if reason in ('fresh-login-required', 'NEEDS_LOGIN', 'UNAUTHORIZED', 'HTTP_401', 'CONNECTION_IDENTITY_MISMATCH', 'inactive', 'superseded'):
                print('Connection needs user setup; no credentials or identity changed.')
                return
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        time.sleep(10)
    raise SystemExit('Local host did not resume within the cold-start budget.')


if __name__ == '__main__':
    main()
