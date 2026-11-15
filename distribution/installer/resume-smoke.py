#!/usr/bin/env python3
"""Re-run application installation and verify that device credentials are preserved."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

spec = importlib.util.spec_from_file_location('release', Path(__file__).with_name('woow-release.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def fingerprint():
    names = r.output(['podman', 'secret', 'ls', '--format', '{{.Name}}']).splitlines()
    records = json.loads(r.output(['podman', 'secret', 'inspect', '--showsecret', *names]))
    values = {'secret:' + item['Spec']['Name']: hashlib.sha256(item['SecretData'].encode()).hexdigest() for item in records}
    for name in ['ha-account.json', 'n8n-account.json', 'piweb-password', 'device.json']:
        values['file:' + name] = r.digest(r.STATE / name)
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apps', nargs='+', choices=r.APPS, default=list(r.APPS))
    args = parser.parse_args()
    os.umask(0o077)
    before = fingerprint()
    with (r.STATE / 'resume-smoke.log').open('w') as log:
        result = subprocess.run(['python3', str(Path(__file__).with_name('woow-release.py')), 'apps', '--apps', *args.apps], stdout=log, stderr=subprocess.STDOUT, timeout=1800)
    after = fingerprint()
    report = {'applications': args.apps, 'installer_exit_code': result.returncode, 'credential_records_checked': len(before), 'credentials_preserved': all(after.get(k) == v for k, v in before.items()), 'new_secret_count': len(set(after) - set(before))}
    r.save_json(r.STATE / 'resume-smoke.json', report)
    print(json.dumps(report))
    if result.returncode or not report['credentials_preserved']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
