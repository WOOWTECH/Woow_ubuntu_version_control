#!/usr/bin/env python3
"""Compatibility overlay for the RC1 Cockpit pin on version-held devices."""
import argparse
from pathlib import Path


def patch(repo):
    path = repo / 'scripts/manage.py'
    old = "fields.get('Status') == 'install ok installed'"
    new = "fields.get('Status') in ('install ok installed', 'hold ok installed')"
    text = path.read_text()
    if new in text:
        return
    if text.count(old) != 1:
        raise ValueError('Unexpected Cockpit installer; refusing an unreviewed patch')
    path.write_text(text.replace(old, new, 1))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', type=Path)
    patch(parser.parse_args().repo)
