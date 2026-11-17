"""Additive presentation selection; never changes the appliance runtime lock."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BRANDS = ('woowtech', 'apporo')
COCKPIT_REPOSITORY = 'https://github.com/WOOWTECH/Woow_cockpit.git'
OVERLAYS = frozenset(('scripts/manage.py', 'backup/manifest.json',
                      'pi-web-integration/woowtech-piweb-gateway.service',
                      'pwa-gateway/woow-cockpit-pwa.container'))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(path, *args):
    result = subprocess.run(['git', '-C', str(path), *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Cockpit Git provenance check failed: ' + args[0])
    return result.stdout.strip()


def fields(data, expected, kind):
    if not isinstance(data, dict) or set(data) != set(expected):
        raise ValueError('Unexpected ' + kind + ' fields')


def profile(brand):
    if brand not in BRANDS:
        raise ValueError('Unknown appliance brand')
    data = json.loads((ROOT / 'brands' / (brand + '.json')).read_text())
    fields(data, ('schema_version', 'id', 'display_name', 'feature_profile', 'material_lock'), 'brand profile')
    if data['schema_version'] != 1 or data['id'] != brand or data['feature_profile'] != 'openclaw-x86_64':
        raise ValueError('Unsupported brand profile')
    if not isinstance(data['display_name'], str) or not data['display_name'].strip():
        raise ValueError('Invalid brand display name')
    if data['material_lock'] is not None and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]*\.json', data['material_lock']):
        raise ValueError('Invalid brand material lock filename')
    return data


def load_lock(path, release, base_lock):
    """Only committed locks inside this distribution can authorize production."""
    path = Path(path).absolute()
    directory = ROOT / 'brand-materials'
    if path.is_symlink() or path.parent.resolve() != directory.resolve():
        raise ValueError('Brand lock must be a regular file in distribution/brand-materials')
    data = json.loads(path.read_text())
    fields(data, ('schema_version', 'base_release', 'base_lock_sha256', 'brands', 'cockpit'), 'brand material lock')
    if data['schema_version'] != 1 or data['base_release'] != release or data['base_lock_sha256'] != sha256(base_lock):
        raise ValueError('Brand material lock does not match the immutable base release')
    if data['brands'] != list(BRANDS):
        raise ValueError('A shared Cockpit material lock must support both brands')
    source = data['cockpit']
    fields(source, ('repository', 'commit', 'tree', 'main_commit', 'interface_version'), 'Cockpit source')
    if source['repository'] != COCKPIT_REPOSITORY or source['interface_version'] != 1:
        raise ValueError('Unsupported Cockpit repository or brand interface')
    for key in ('commit', 'tree', 'main_commit'):
        if not isinstance(source[key], str) or not re.fullmatch('[0-9a-f]{40}', source[key]):
            raise ValueError('Cockpit ' + key + ' must be a complete immutable Git object ID')
    relative = path.resolve().relative_to(ROOT.parent.resolve()).as_posix()
    committed = subprocess.run(['git', '-C', str(ROOT.parent), 'show', 'HEAD:' + relative], capture_output=True)
    if committed.returncode or committed.stdout != path.read_bytes():
        raise ValueError('Production brand material lock must be committed and unchanged')
    return data, path.name


def read_receipt(state):
    path = state / 'brand.json'
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError('Brand receipt must not be a symlink')
    data = json.loads(path.read_text())
    fields(data, ('schema_version', 'brand', 'mode', 'base_lock_sha256', 'material_lock',
                  'material_lock_sha256', 'commit', 'tree', 'overlays', 'status'), 'brand receipt')
    if data['schema_version'] != 1 or data['brand'] not in BRANDS or data['mode'] not in ('production', 'development'):
        raise ValueError('Invalid brand receipt')
    if data['status'] not in ('installing', 'applied'):
        raise ValueError('Invalid brand installation status')
    for key in ('commit', 'tree'):
        if not isinstance(data[key], str) or not re.fullmatch('[0-9a-f]{40}', data[key]):
            raise ValueError('Invalid brand receipt Git object')
    return data


def select(brand, release, base_lock, state, material_lock=None, local_source=None, development=False):
    receipt = read_receipt(state)
    brand = brand or (receipt['brand'] if receipt else 'woowtech')
    selected = profile(brand)
    common = {'brand': brand, 'display_name': selected['display_name'],
              'feature_profile': selected['feature_profile'], 'base_lock_sha256': sha256(base_lock)}
    if development or local_source is not None:
        if not development or local_source is None or material_lock is not None:
            raise ValueError('Development requires --development --cockpit-source PATH and no --brand-lock')
        source = Path(local_source).resolve()
        if git(source, 'rev-parse', '--show-toplevel') != str(source):
            raise ValueError('Local Cockpit source must be the Git repository root')
        if git(source, 'status', '--porcelain', '--untracked-files=normal'):
            raise ValueError('Local Cockpit source must be committed and clean; the source checkout is never modified')
        return {**common, 'mode': 'development', 'ready': True, 'release_eligible': False,
                'local_source': str(source), 'commit': git(source, 'rev-parse', 'HEAD'),
                'tree': git(source, 'rev-parse', 'HEAD^{tree}'), 'material_lock': None,
                'material_lock_sha256': None}
    if material_lock is None and selected['material_lock']:
        material_lock = ROOT / 'brand-materials' / selected['material_lock']
    if material_lock is None and receipt and receipt['mode'] == 'production':
        material_lock = ROOT / 'brand-materials' / receipt['material_lock']
    if material_lock is not None:
        lock, name = load_lock(material_lock, release, base_lock)
        return {**common, 'mode': 'production', 'ready': True, 'release_eligible': True,
                'material_lock': name, 'material_lock_sha256': sha256(material_lock), **lock['cockpit']}
    if receipt and receipt['mode'] == 'development':
        return {**common, 'mode': 'pending', 'ready': False, 'release_eligible': False,
                'reason': 'Existing development branding requires an explicit local source or a production brand lock'}
    return {**common, 'mode': 'legacy' if brand == 'woowtech' else 'pending',
            'ready': brand == 'woowtech', 'release_eligible': brand == 'woowtech',
            'reason': None if brand == 'woowtech' else 'A reviewed, committed Cockpit brand material lock is required'}


def source_path(state, selection):
    if selection['mode'] not in ('production', 'development') or not re.fullmatch('[0-9a-f]{40}', selection['commit']):
        raise ValueError('Invalid staged source identity')
    return state / 'branding' / selection['mode'] / selection['commit']


def source_check(path, selection, overlays=None):
    if git(path, 'rev-parse', 'HEAD') != selection['commit'] or git(path, 'rev-parse', 'HEAD^{tree}') != selection['tree']:
        raise ValueError('Cockpit commit/tree does not match the brand material')
    if selection['mode'] == 'production':
        if git(path, 'remote', 'get-url', 'origin') != COCKPIT_REPOSITORY:
            raise ValueError('Cockpit production origin mismatch')
        git(path, 'merge-base', '--is-ancestor', selection['commit'], selection['main_commit'])
        git(path, 'merge-base', '--is-ancestor', selection['main_commit'], 'origin/main')
    overlays = overlays or {}
    if not isinstance(overlays, dict) or not set(overlays).issubset(OVERLAYS):
        raise ValueError('Unapproved Cockpit source overlay')
    changed = set(git(path, 'diff', '--name-only', 'HEAD').splitlines())
    if git(path, 'ls-files', '--others', '--exclude-standard') or changed != set(overlays):
        raise ValueError('Unexpected Cockpit source drift')
    for name, expected in overlays.items():
        if (path / name).is_symlink() or sha256(path / name) != expected:
            raise ValueError('Cockpit source overlay checksum mismatch')


def prepare_source(state, selection):
    path = source_path(state, selection)
    if path.is_symlink() or not path.resolve().is_relative_to(state.resolve()):
        raise ValueError('Cockpit staging must not be a symlink')
    receipt = read_receipt(state)
    existing_overlays = receipt['overlays'] if receipt and all(receipt[k] == selection[k] for k in ('mode', 'commit', 'tree')) else {}
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        source = selection.get('local_source', COCKPIT_REPOSITORY)
        subprocess.run(['git', 'clone', '--no-hardlinks', '--no-checkout', source, str(path)], check=True)
        git(path, 'checkout', '--detach', selection['commit'])
        existing_overlays = {}
    if selection['mode'] == 'production':
        if git(path, 'remote', 'get-url', 'origin') != COCKPIT_REPOSITORY:
            raise ValueError('Cockpit production origin mismatch')
        git(path, 'fetch', '--no-tags', 'origin', 'main:refs/remotes/origin/main')
    source_check(path, selection, existing_overlays)
    for relative in ('scripts/manage.py', 'scripts/brand_profile.py', 'pwa-gateway/install.sh',
                     'pwa-gateway/render.py', 'pwa-gateway/woow-cockpit-pwa.container',
                     'pi-web-integration/install.sh', 'brands/woowtech/brand.json', 'brands/apporo/brand.json'):
        if not (path / relative).is_file() or (path / relative).is_symlink():
            raise ValueError('Cockpit brand source is missing a required installer')
    return path


def receipt_for(selection, path, status):
    changed = set(git(path, 'diff', '--name-only', 'HEAD').splitlines())
    if not changed.issubset(OVERLAYS):
        raise ValueError('Unapproved Cockpit source changes during branding')
    overlays = {name: sha256(path / name) for name in sorted(changed)}
    source_check(path, selection, overlays)
    return {'schema_version': 1, **{key: selection[key] for key in
            ('brand', 'mode', 'base_lock_sha256', 'material_lock', 'material_lock_sha256', 'commit', 'tree')},
            'overlays': overlays, 'status': status}


def verify_receipt(state, release, base_lock):
    receipt = read_receipt(state)
    if not receipt:
        return None, None
    if receipt['status'] != 'applied' or receipt['base_lock_sha256'] != sha256(base_lock):
        raise ValueError('Brand installation is incomplete or uses a different base release')
    selection = dict(receipt)
    if receipt['mode'] == 'production':
        lock_path = ROOT / 'brand-materials' / receipt['material_lock']
        lock, _ = load_lock(lock_path, release, base_lock)
        if sha256(lock_path) != receipt['material_lock_sha256'] or any(receipt[k] != lock['cockpit'][k] for k in ('commit', 'tree')):
            raise ValueError('Brand receipt does not match its material lock')
        selection.update(lock['cockpit'])
    path = source_path(state, selection)
    source_check(path, selection, receipt['overlays'])
    return selection, path
