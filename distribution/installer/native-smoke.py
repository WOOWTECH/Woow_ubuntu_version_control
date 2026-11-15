#!/usr/bin/env python3
"""Verify the native host remains connected and all three CLIs are detected."""
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    os.umask(0o077)
    root = Path.home() / '.local/share/pi-agent'
    state = Path.home() / '.local/state/woow-release/2026.11.15-rc1'
    proof = json.loads((root / 'data/omnigent-plugin/connection.json').read_text())
    deadline = time.monotonic() + 240
    while True:
        result = subprocess.run([root / 'bin/pi-omnigent', 'status'], text=True, capture_output=True, timeout=90)
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        host = data.get('host', {})
        engines = data.get('engines', {})
        report = {
            'host_connected': host.get('connected') is True,
            'host_identity_preserved': host.get('id') == proof['host']['id'],
            'engines_detected': {name: engines.get(name, {}).get('available') is True for name in ('pi', 'claude', 'codex')},
            'external_model_called': False,
        }
        passed = report['host_connected'] and report['host_identity_preserved'] and all(report['engines_detected'].values())
        if passed or time.monotonic() >= deadline:
            report['passed'] = passed
            (state / 'native-smoke.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report))
            if not passed:
                raise SystemExit(1)
            return
        time.sleep(5)


if __name__ == '__main__':
    main()
