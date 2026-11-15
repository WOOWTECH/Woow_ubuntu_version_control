#!/usr/bin/env python3
"""Capture/verify an existing rootless host across a reboot. Never restarts services."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def query(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if p.returncode:
        raise RuntimeError(f'{args[0]} read failed (exit {p.returncode})')
    return p.stdout


def record(c, name_by_id):
    config = c.get('Config') or {}
    host = c.get('HostConfig') or {}
    state = c.get('State') or {}
    network = host.get('NetworkMode', '')
    if network.startswith('container:'):
        ref = network.split(':', 1)[1]
        matches = [name for ident, name in name_by_id.items() if ident.startswith(ref) or name == ref]
        if len(matches) != 1:
            raise RuntimeError('Cannot resolve shared network namespace owner')
        network = 'container-name:' + matches[0]
    return {
        'image_id': c['Image'].removeprefix('sha256:'),
        'running': bool(state.get('Running')),
        'health': (state.get('Health') or {}).get('Status', 'not-declared'),
        'network_mode': network,
        'ports': host.get('PortBindings') or {},
        'devices': host.get('Devices') or [],
        'mounts': sorted([{k: m.get(k) for k in ('Type', 'Name', 'Source', 'Destination', 'RW')}
                          for m in c.get('Mounts', []) if m['Type'] in ('bind', 'volume')],
                         key=lambda m: m['Destination']),
        # Hash only; never publish environment values or arbitrary labels.
        'environment_sha256': digest(sorted(v for v in config.get('Env', [])
                                             if not v.startswith('HOSTNAME='))),
        'unit': (config.get('Labels') or {}).get('PODMAN_SYSTEMD_UNIT'),
    }


def snapshot(units, urls):
    if os.getuid() == 0:
        raise RuntimeError('Run as the existing deployment owner, not root')
    ids = query(['podman', 'ps', '-q']).splitlines()
    items = json.loads(query(['podman', 'inspect', *ids])) if ids else []
    name_by_id = {c['Id']: c['Name'].lstrip('/') for c in items}
    services = {}
    for unit in units:
        p = subprocess.run(['systemctl', '--user', 'is-active', unit], capture_output=True, text=True, timeout=20)
        services[unit] = p.returncode == 0 and p.stdout.strip() == 'active'
    http = {}
    for name, url in urls.items():
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
            raise ValueError('Only HTTP(S) URLs without embedded credentials are supported')
        try:
            with urllib.request.urlopen(url, timeout=12) as response:
                http[name] = response.status
        except Exception as e:
            http[name] = type(e).__name__
    return {
        'schema': 1, 'uid': os.getuid(),
        'host_identity_sha256': digest(Path('/etc/machine-id').read_text().strip()),
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'recorded_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'uptime_seconds': float(Path('/proc/uptime').read_text().split()[0]),
        'containers': {c['Name'].lstrip('/'): record(c, name_by_id) for c in items},
        'units': services, 'urls': urls, 'http': http,
    }


def ready(data):
    return (bool(data['containers']) and all(c['running'] and c['health'] in ('healthy', 'not-declared', '')
            for c in data['containers'].values()) and all(data['units'].values())
            and all(v == 200 for v in data['http'].values()))


def compare(before, after):
    keys = ('image_id', 'network_mode', 'ports', 'devices', 'mounts', 'environment_sha256', 'unit')
    missing = sorted(set(before['containers']) - set(after['containers']))
    extra = sorted(set(after['containers']) - set(before['containers']))
    changes = {name: [key for key in keys if old[key] != after['containers'][name][key]]
               for name, old in before['containers'].items() if name in after['containers']}
    changes = {name: fields for name, fields in changes.items() if fields}
    report = {
        'boot_changed': before['boot_id'] != after['boot_id'],
        'same_host_and_owner': before['host_identity_sha256'] == after['host_identity_sha256'] and before['uid'] == after['uid'],
        'expected_containers': len(before['containers']), 'running_containers': len(after['containers']),
        'missing_containers': missing, 'unexpected_containers': extra, 'changed_container_fields': changes,
        'all_expected_services_ready': ready(after),
        'units': after['units'], 'http': after['http'],
        'verified_at_boot_uptime_seconds': round(after['uptime_seconds'], 1),
        'read_only': True, 'services_restarted_by_auditor': False,
    }
    report['passed'] = report['boot_changed'] and report['same_host_and_owner'] and not missing and not extra and not changes and ready(after)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('capture', 'verify'))
    p.add_argument('--baseline', type=Path)
    p.add_argument('--output', type=Path, required=True, help='New private JSON file; existing paths refused')
    p.add_argument('--unit', action='append', default=[])
    p.add_argument('--url', action='append', default=[], help='NAME=http://127.0.0.1:PORT/health')
    a = p.parse_args()
    os.umask(0o077)
    if a.output.exists() or a.output.is_symlink():
        p.error('Output already exists')
    if a.action == 'capture':
        urls = dict(x.split('=', 1) for x in a.url)
        result = snapshot(a.unit, urls)
        if not ready(result):
            raise RuntimeError('Baseline is not ready; no valid reboot baseline saved')
        passed = True
        brief = {'captured': True, 'containers': len(result['containers']), 'read_only': True}
    else:
        if not a.baseline:
            p.error('verify requires --baseline')
        before = json.loads(a.baseline.read_text())
        result = compare(before, snapshot(list(before['units']), before['urls']))
        passed = result['passed']
        brief = result
    a.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(brief))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
