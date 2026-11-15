#!/usr/bin/env python3
"""Run pinned projects' operational checks; never call an external model provider."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

spec = importlib.util.spec_from_file_location('release', Path(__file__).with_name('woow-release.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apps', nargs='+', choices=r.APPS, default=list(r.APPS))
    args = parser.parse_args()
    os.umask(0o077)
    results = {}
    previous_path = r.STATE / 'smoke-results.json'
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    for app in args.apps:
        source = r.SOURCES / r.APPS[app][0]
        script = source / 'tests/smoke.sh'
        flags = []
        if app == 'homeassistant':
            token = r.output(['podman', 'secret', 'inspect', '--showsecret', '--format', '{{.SecretData}}', 'homeassistant-mcp-token'])
            header = Path.home() / '.config/homeassistant/smoke.header'
            header.write_text('Authorization: Bearer ' + token + '\n')
            header.chmod(0o600)
            flags = ['--wait', '180', '--settle', '10']
        elif app in ('n8n', 'nextcloud'):
            flags = ['--timeout', '180']
        elif app == 'woow-code-server':
            flags = ['--quick']
        text = script.read_text()
        # These upstream assertions parse a tag as a semantic version. Release
        # aliases identify immutable content; retain the version assertion using
        # the actual runtime version represented by this lock instead.
        replacements = {
            'n8n': ('want=$(app_tag "$(app_installed_image n8n.container)")', 'want=2.43.6'),
            'nextcloud': ('want=$(app_image_version "$(app_installed_image nextcloud-app.container)")', 'want=35.0.1'),
        }
        if app in replacements:
            old, new = replacements[app]
            if text.count(old) != 1:
                raise SystemExit('Upstream smoke contract changed: ' + app)
            text = text.replace(old, new)
        fd, name = tempfile.mkstemp(prefix='.woow-release-smoke-', suffix='.sh', dir=script.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(text)
            log = r.STATE / ('smoke-' + app + '.log')
            with log.open('w') as stream:
                try:
                    process = subprocess.run(['bash', name, *flags], stdout=stream, stderr=subprocess.STDOUT, timeout=1200, umask=0o022)
                    results[app] = {'exit_code': process.returncode}
                except subprocess.TimeoutExpired:
                    results[app] = {'exit_code': 124}
            print(app, results[app], flush=True)
            r.save_json(r.STATE / 'smoke-results.json', {**previous, **results})
        finally:
            Path(name).unlink(missing_ok=True)
    raise SystemExit(0 if all(x['exit_code'] == 0 for x in results.values()) else 1)


if __name__ == '__main__':
    main()
