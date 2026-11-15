#!/usr/bin/env python3
"""Allow measured N100 cold CLI startup time without changing login/host guards."""
import hashlib
import json
import os
from pathlib import Path


def main():
    os.umask(0o077)
    root = Path.home() / '.local/share/pi-agent/plugins/pi-omnigent-plugin'
    version = json.loads((root / 'package.json').read_text())['version']
    if version != '0.3.31':
        raise SystemExit('Unreviewed Omnigent plugin version; startup overlay not applied.')
    target = root / 'src/installer.mjs'
    old = 'const result = await run(command, args, { env, timeoutMs: 5_000 });'
    new = 'const result = await run(command, args, { env, timeoutMs: 30_000 }); // WOOW x86 release: cold CLI probe budget'
    text = target.read_text()
    if new not in text:
        if text.count(old) != 1:
            raise SystemExit('Omnigent dependency probe contract changed.')
        target.write_text(text.replace(old, new))
    report = {'plugin_version': version, 'probe_timeout_ms': 30000, 'installed_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    state = Path.home() / '.local/state/woow-release/2026.11.15-rc1'
    (state / 'native-startup-overlay.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Native dependency probes allow 30 seconds; login and host identity checks retained.')


if __name__ == '__main__':
    main()
