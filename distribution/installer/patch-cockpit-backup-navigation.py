#!/usr/bin/env python3
"""Apply Woow_cockpit PR #15 navigation to the historical rc1 source pin."""
import argparse
import json
from pathlib import Path


def patch(repo):
    path = repo / 'backup/manifest.json'
    manifest = json.loads(path.read_text())
    if 'menu' not in manifest and manifest.get('tools', {}).get('index', {}).get('label') == '備份與還原' and manifest['tools']['index'].get('order') == 41:
        return
    if 'tools' in manifest or set(manifest.get('menu', {})) != {'index'}:
        raise ValueError('Unexpected backup navigation; no changes applied')
    entry = manifest['menu']['index']
    if entry.get('label') != '備份與還原' or entry.get('order') != 46:
        raise ValueError('Unexpected backup menu entry; no changes applied')
    entry['order'] = 41
    manifest['tools'] = manifest.pop('menu')
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', type=Path)
    patch(parser.parse_args().repo)
