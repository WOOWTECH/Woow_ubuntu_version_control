#!/usr/bin/env python3
"""Stage pinned Cockpit source for an optional ingress to this host's existing services."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RELEASE = '2026.11.15-rc1'
# Keep source staging separate from the primary installation's brand.json.
STATE = Path.home() / '.local/state/woow-release' / RELEASE / 'parallel-ingress'
_spec = importlib.util.spec_from_file_location('parallel_ingress_brands', ROOT / 'installer/brand_profile.py')
brands = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brands)


def select_source():
    selection = brands.select('apporo', RELEASE, ROOT / 'releases' / RELEASE / 'lock.json', STATE)
    if selection['mode'] != 'production' or not selection['ready'] or not selection['release_eligible']:
        raise ValueError('Parallel ingress requires a committed production Cockpit material lock')
    return selection


def delegate(action, selection, config=None, instance=None):
    """The pinned root CLI owns config, backend parity, transactions and verification."""
    if os.getuid() == 0:
        raise ValueError('Run the distribution wrapper as the deployment owner; it invokes sudo for Cockpit')
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE / 'source.lock').open('w') as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another parallel ingress command is running') from None
        repo = brands.prepare_source(STATE, selection)
        manager = repo / 'parallel-ingress/manage.py'
        if not manager.is_file() or manager.is_symlink():
            raise ValueError('Pinned Cockpit source has no parallel ingress installer; a reviewed material update is required')
        args = ['--config', str(config)] if action == 'install' else ['--instance', instance]
        return subprocess.run(['sudo', 'env', 'PYTHONDONTWRITEBYTECODE=1', 'python3',
                               str(manager), action, *args], check=False).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest='action', required=True)
    actions.add_parser('plan', help='Read-only source selection; does not validate an instance or contact the host')
    install = actions.add_parser('install', help='Stage verified source and delegate to the Cockpit root installer')
    install.add_argument('--config', type=Path, required=True, help='Absolute path to the root-owned instance JSON')
    for action in ('verify', 'rollback'):
        command = actions.add_parser(action)
        command.add_argument('--instance', required=True, help='Instance name understood by the Cockpit root CLI')
    args = parser.parse_args()
    if args.action == 'install' and not args.config.is_absolute():
        parser.error('--config must be an absolute path to the root-owned instance JSON')
    try:
        selection = select_source()
        if args.action == 'plan':
            print(json.dumps({'release': RELEASE, 'scope': 'source-selection',
                              'source': selection, 'instance_validated': False,
                              'runtime_verified': False}, indent=2))
            return 0
        return delegate(args.action, selection, getattr(args, 'config', None), getattr(args, 'instance', None))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    raise SystemExit(main())
