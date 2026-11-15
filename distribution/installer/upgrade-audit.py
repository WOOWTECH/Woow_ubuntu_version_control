#!/usr/bin/env python3
"""Read-only inventory for an EXISTING device; never adopts, stops or upgrades services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def query(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode:
        # Do not echo raw diagnostics, command contents or inspect data.
        raise RuntimeError(f'{args[0]} read failed (exit {result.returncode})')
    return result.stdout


def container_record(item, lock):
    name = item['Name'].lstrip('/')
    current = item['Image'].removeprefix('sha256:')
    target = lock['containers'].get(name)
    config = item.get('Config') or {}
    host = item.get('HostConfig') or {}
    state = item.get('State') or {}
    if target:
        action = 'same-image-review-settings' if current == target['image_id'] else 'requires-application-upgrade-review'
    elif name == 'pi-web':
        action = 'requires-container-to-native-migration-review'
    elif name == 'matter-server':
        action = 'preserve-existing-matter-fabric-review'
    else:
        action = 'preserve-outside-release'
    return {
        'name': name, 'running': bool(state.get('Running')),
        'health': (state.get('Health') or {}).get('Status', 'not-declared'),
        'image_id': current, 'image_reference': item.get('ImageName'),
        'target_image_id': target['image_id'] if target else None,
        'review': action,
        'unit': (config.get('Labels') or {}).get('PODMAN_SYSTEMD_UNIT'),
        'network_mode': host.get('NetworkMode'),
        'port_bindings': host.get('PortBindings') or {},
        'mounts': [{k: m.get(k) for k in ('Type', 'Name', 'Source', 'Destination', 'RW')}
                   for m in item.get('Mounts', [])],
        # NEVER include Config.Env, CreateCommand, health output or arbitrary labels.
    }


def unit_record(path):
    allowed = {'Image', 'ContainerName', 'Volume', 'PublishPort', 'Network',
               'EnvironmentFile', 'Requires', 'After', 'Wants', 'TimeoutStopSec'}
    props = {}
    for line in path.read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and key in allowed:
            props.setdefault(key, []).append(value)
    return {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'symlink': path.is_symlink(), 'properties': props}


def audit(lock):
    if os.getuid() == 0:
        raise RuntimeError('Run as the existing rootless deployment owner, not root.')
    ids = query(['podman', 'ps', '-aq']).splitlines()
    items = json.loads(query(['podman', 'inspect', *ids])) if ids else []
    if len(items) != len(ids):
        raise RuntimeError('Incomplete inventory; no upgrade may use this result.')
    containers = [container_record(c, lock) for c in items]
    qdir = Path.home() / '.config/containers/systemd'
    units = [unit_record(p) for p in sorted(qdir.rglob('*.container'))] if qdir.exists() else []
    systemd = json.loads(query(['systemctl', '--user', 'list-units', '--type=service',
                                '--all', '--output=json', '--no-pager']))
    return {
        'schema': 1, 'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'release': lock['release'], 'mode': 'read-only', 'upgrade_authorized_by_report': False,
        'uid': os.getuid(), 'architecture': platform.machine(),
        'free_home_bytes': shutil.disk_usage(Path.home()).free,
        'containers': containers, 'quadlets': units,
        'user_services': [{k: u.get(k) for k in ('unit', 'active', 'sub')} for u in systemd],
        'native_pi_present': (Path.home() / '.local/share/pi-agent').exists(),
        'missing_release_containers': sorted(set(lock['containers']) - {c['name'] for c in containers}),
        'required_before_cutover': [
            'Confirm exact applications and acceptable interruption.',
            'Review existing ports, accounts, mounts, secrets, cloud routes and device identities.',
            'Check application upgrade path, plugins, database schema and available disk.',
            'Prepare and verify a complete consistent backup and rollback on an isolated copy.',
            'Drain writers; coordinate matching app/worker/runner versions.',
            'Validate existing data, login, integrations and URLs before reopening traffic.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=ROOT / 'releases/2026.11.15-rc1/lock.json')
    parser.add_argument('--output', type=Path, required=True,
                        help='New private report file (existing paths are refused).')
    args = parser.parse_args()
    os.umask(0o077)
    lock = json.loads(args.lock.read_text())
    report = audit(lock)
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # O_EXCL also prevents following an existing symlink or overwriting an earlier inventory.
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'report_written': True, 'containers': len(report['containers']),
                      'running': sum(c['running'] for c in report['containers']),
                      'mode': 'read-only', 'services_changed': False}))


if __name__ == '__main__':
    main()
