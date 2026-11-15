#!/usr/bin/env python3
"""Opt-in EMQX backup/restore drill on the new, isolated acceptance device.

Stops/restarts the whole EMQX application and restores its data to the snapshot.
Never run while users are changing broker settings or publishing production data.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

spec = importlib.util.spec_from_file_location('catalog', Path(__file__).with_name('backup-catalog.py'))
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)
CLIENT = 'docker.io/library/eclipse-mosquitto:2.0.22@sha256:212f89e1eaeb2c322d6441b64396e3346026674db8fa9c27beac293405c32b3c'


def job(command, data):
    started = catalog.call(command, dict(data, request_id=str(uuid.uuid4())))
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        result = catalog.call('job-status', {'job_id': started['job_id']})['job']
        if result['state'] not in ('queued', 'running'):
            if result['state'] != 'succeeded':
                raise RuntimeError(command + ': ' + json.dumps(result.get('error')))
            return result['result']
        time.sleep(3)
    raise TimeoutError(command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-isolated-device', action='store_true', required=True)
    parser.parse_args()
    os.umask(0o077)
    status = catalog.call('status')
    apps = [a['id'] for a in status['apps'] if any(u['name'] == 'emqx.service' for u in a['units'])]
    if len(apps) != 1:
        raise SystemExit('Need exactly one enrolled EMQX application.')
    catalog.call('key-init')
    password = subprocess.check_output(['podman', 'secret', 'inspect', '--showsecret', '--format', '{{.SecretData}}', 'woow-emqx-mqtt-password'], text=True).strip()
    topic = 'woow/release-backup/' + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='woow-backup-smoke-') as directory:
        for tool in ('mosquitto_pub', 'mosquitto_sub'):
            Path(directory, tool).write_text('-u woow\n-P ' + password + '\n')
        def mqtt(tool, *args):
            # The entrance can serve HTTP before EMQX opens its MQTT listener.
            # Require a real broker response after the cold restart, within a
            # bounded startup budget. Repeated retained writes are idempotent.
            deadline = time.monotonic() + 120
            while True:
                result = subprocess.run(['podman', 'run', '--rm', '--pull=never', '--network=host', '-e', 'XDG_CONFIG_HOME=/cfg', '-v', directory + ':/cfg:ro', CLIENT, tool, '-V', 'mqttv5', '-h', '127.0.0.1', '-t', topic, *args], timeout=60, text=True, capture_output=True)
                # Mosquitto 2.0.22 can exit zero after a rejected PUBACK or
                # SUBACK. MQTT 5 exposes that rejection on stderr. Never
                # mistake a successful process exit for a successful write.
                if result.returncode == 0 and not result.stderr.strip():
                    return result.stdout.strip()
                if time.monotonic() >= deadline:
                    raise RuntimeError('MQTT operation failed after the restart deadline; exit code ' + str(result.returncode))
                time.sleep(3)
        def expect(value):
            deadline = time.monotonic() + 30
            while True:
                actual = mqtt('mosquitto_sub', '-C', '1', '-W', '20')
                if actual == value:
                    return
                if time.monotonic() >= deadline:
                    raise AssertionError('Retained test message did not match ' + value)
                time.sleep(2)
        try:
            mqtt('mosquitto_pub', '-q', '1', '-r', '-m', 'before-backup')
            expect('before-backup')
            backup = job('backup-start', {'apps': apps, 'include_images': False, 'note': 'Isolated release acceptance drill', 'encrypt': True})
            backup_id = backup['backup_id']
            verified = job('verify-start', {'backup_id': backup_id})
            download = catalog.call('download-info', {'backup_id': backup_id})
            # Read the exact downloadable bytes, not merely the listing metadata.
            expected = next(b['sha256'] for b in catalog.call('list')['backups'] if b['id'] == backup_id)
            actual = subprocess.check_output(['sudo', 'sha256sum', download['path']], text=True).split()[0]
            assert actual == expected
            mqtt('mosquitto_pub', '-q', '1', '-r', '-m', 'after-backup')
            expect('after-backup')
            restored = job('restore-start', {'backup_id': backup_id, 'apps': apps, 'confirm': True})
            expect('before-backup')
            report = {'backup_id': backup_id, 'encrypted': True, 'deep_verify_succeeded': True, 'download_checksum_matches': True, 'download_bytes': download['size'], 'retained_message_restored': True, 'safety_backup_id': restored.get('safety_backup_id'), 'restored': restored}
            (catalog.STATE / 'backup-smoke.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps({k: v for k, v in report.items() if k != 'restored'}))
        finally:
            mqtt('mosquitto_pub', '-q', '1', '-r', '-n')


if __name__ == '__main__':
    main()
