#!/usr/bin/env python3
"""Export immutable images only; never containers, volumes, home directories or secrets."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile


def archive_config(path):
    """Read image JSON, without extracting any archive member to the filesystem."""
    proc = subprocess.Popen(['zstd', '-dc', path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        with tarfile.open(fileobj=proc.stdout, mode='r|') as archive:
            for member in archive:
                if not member.isfile() or member.size > 1024 * 1024:
                    continue
                data = archive.extractfile(member).read()
                try:
                    value = json.loads(data)
                except (ValueError, UnicodeDecodeError):
                    continue
                if isinstance(value, dict) and 'rootfs' in value and 'architecture' in value:
                    return hashlib.sha256(data).hexdigest()
        raise ValueError('No image configuration in archive')
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.terminate()
        proc.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--all', action='store_true', help='Include public images for image-offline installation')
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / '.export.lock').open('w') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock = json.loads(args.lock.read_text())
        index = args.output / 'materials.json'
        previous = json.loads(index.read_text()) if index.exists() else {}
        if previous and previous['release'] != lock['release']:
            raise SystemExit('The output directory belongs to another release.')
        records = previous.get('images', {})
        for ident, record in lock['images'].items():
            if not record['private_material'] and not args.all:
                continue
            raw = subprocess.check_output(['podman', 'image', 'inspect', ident])
            meta = json.loads(raw)[0]
            if meta['Id'].removeprefix('sha256:') != ident:
                raise SystemExit('Image identity mismatch')
            if re.search(rb'gh[pousr]_[A-Za-z0-9]{30,}|sk-or-v1-[a-f0-9]{40,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY', raw):
                raise SystemExit('Credential-like image metadata: ' + ident)
            # Docker-specific configuration (for example Shell/Healthcheck) can
            # disappear during OCI conversion and change the image config ID.
            fmt = record.get('archive_format') or ('docker-archive' if 'docker.distribution' in meta['ManifestType'] else 'oci-archive')
            suffix = 'docker' if fmt == 'docker-archive' else 'oci'
            dest = args.output / f'{ident}.{suffix}.tar.zst'
            if not dest.exists():
                tmp = dest.with_suffix('.partial')
                command = ['podman', 'save', '--format', fmt]
                if fmt == 'oci-archive':
                    command.append('--uncompressed')
                with tmp.open('wb') as stream:
                    save = subprocess.Popen([*command, ident], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    compress = subprocess.Popen(['zstd', '-T2', '-3', '-q'], stdin=save.stdout, stdout=stream)
                    save.stdout.close()
                    rc = compress.wait()
                    error = save.communicate()[1]
                if rc or save.returncode:
                    tmp.unlink(missing_ok=True)
                    raise SystemExit('Export failed: ' + error.decode()[-500:])
                tmp.replace(dest)
            config = archive_config(dest)
            if config != ident:
                raise SystemExit(f'Archive changes image identity: {ident}; not published to index.')
            with dest.open('rb') as stream:
                checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
            records[ident] = {'file': dest.name, 'sha256': checksum, 'bytes': dest.stat().st_size, 'format': fmt, 'config_id': ident}
            temp_index = index.with_suffix('.json.partial')
            temp_index.write_text(json.dumps({'schema_version': 1, 'release': lock['release'], 'images': records}, indent=2) + '\n')
            temp_index.replace(index)
            print(ident[:12], dest.stat().st_size, 'identity and checksum verified', flush=True)


if __name__ == '__main__':
    main()
