#!/usr/bin/env python3
"""Apply the reviewed rootless config-backup fix to this release's source."""
from pathlib import Path
import subprocess
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: patch-nextcloud-backup.py NEXTCLOUD_SOURCE')
    source = Path(sys.argv[1]).resolve()
    patch = Path(__file__).resolve().parents[1] / 'overlays/nextcloud-rootless-backup.patch'
    reverse = subprocess.run(['git', '-C', source, 'apply', '--reverse', '--check', patch], capture_output=True)
    if reverse.returncode == 0:
        return
    check = subprocess.run(['git', '-C', source, 'apply', '--check', patch], capture_output=True)
    if check.returncode:
        raise SystemExit('Nextcloud backup source differs; no files changed')
    subprocess.run(['git', '-C', source, 'apply', patch], check=True)


if __name__ == '__main__':
    main()
