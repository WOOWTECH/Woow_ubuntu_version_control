#!/usr/bin/env python3
"""Install a new WOOW appliance. This is not a backup restore or an upgrade tool."""
import argparse
import fcntl
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RELEASE = '2026.11.15-rc1'
LOCK = json.loads((ROOT / 'releases' / RELEASE / 'lock.json').read_text())
MATERIALS = json.loads((ROOT / 'releases' / RELEASE / 'materials.json').read_text())['images']
STATE = Path.home() / '.local/state/woow-release' / RELEASE
SOURCES = STATE / 'sources'
QDIR = Path.home() / '.config/containers/systemd'
_brand_spec = importlib.util.spec_from_file_location('brand_profile', ROOT / 'installer/brand_profile.py')
brands = importlib.util.module_from_spec(_brand_spec)
_brand_spec.loader.exec_module(brands)
APPS = {
    'homeassistant': ('Woow_podman_homeassistant', ['--with-matter', '--with-mcp', '--no-smoke']),
    'emqx': ('Woow_podman_emqx', ['--accept-defaults', '--without-ngrok', '--no-smoke']),
    'litellm': ('Woow_podman_litellm', ['--no-pull', '--yes']),
    'n8n': ('Woow_podman_n8n', ['--no-smoke']),
    'nextcloud': ('Woow_podman_nextcloud', ['--no-smoke']),
    'odoo18': ('Woow_podman_odoo', ['--accept-defaults', '--no-smoke']),
    'hermes': ('Woow_podman_hermes', ['--accept-defaults', '--no-build', '--no-llm', '--no-smoke']),
    'open-design': ('Woow_podman_opendesign', ['--accept-defaults', '--no-build', '--no-smoke']),
    'omnigent': ('Woow_podman_omnigent_package', ['--no-build', '--yes']),
    'headscale': ('Woow_podman_vpn_headscale_package', ['--accept-defaults', '--no-build', '--no-smoke']),
    'woow-code-server': ('Woow_podman_code_server_package', ['--no-build', '--without-tailscale', '--yes']),
    'woow-cf-tunnel': ('Woow_cloudflare_tunnel_webgui', ['--image', LOCK['images'][LOCK['containers']['woow-cf-tunnel']['image_id']]['tags'][0]]),
}

def run(args, **kw):
    kw.setdefault('umask', 0o022)  # Upstream templates must remain readable in unprivileged containers.
    return subprocess.run([str(x) for x in args], check=True, **kw)

def output(args):
    return subprocess.check_output([str(x) for x in args], text=True).strip()

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.chmod(0o600)
    tmp.replace(path)

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def device_address(requested=None):
    """Choose an actual interface address for Cockpit's Pi Web ingress."""
    if requested:
        candidate = requested
    elif (STATE / 'device.json').exists():
        candidate = json.loads((STATE / 'device.json').read_text())['address']
    else:
        route = json.loads(output(['ip', '-j', '-4', 'route', 'get', '1.1.1.1']))
        candidate = route[0].get('prefsrc', '')
    try:
        address = ipaddress.IPv4Address(candidate)
    except ipaddress.AddressValueError:
        raise SystemExit('Use --address with this device\'s LAN IPv4 address.')
    if address.is_loopback or address.is_unspecified or address.is_multicast:
        raise SystemExit('--address must be a reachable interface IPv4 address.')
    return str(address)

def preflight():
    osinfo = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if osinfo.get('ID', '').strip('"') != 'ubuntu' or osinfo.get('VERSION_ID', '').strip('"') != '24.04':
        raise SystemExit('This profile requires Ubuntu 24.04.')
    if platform.machine() != 'x86_64' or os.getuid() == 0:
        raise SystemExit('Run as a normal x86_64 Ubuntu user with sudo, not root.')
    if not (STATE / 'device.json').exists():
        if shutil.disk_usage(Path.home()).free < 85 * 1024**3:
            raise SystemExit('A new full install requires at least 85 GiB free (including first-use UID mapping copies).')
        if QDIR.exists() and list(QDIR.glob('*.container')):
            raise SystemExit('Existing Quadlets found. Use a fresh user/host/VM; this installer does not adopt or replace them.')
        if shutil.which('podman') and output(['podman', 'ps', '-aq']):
            raise SystemExit('Existing containers found. Use a fresh user/host/VM.')
        if (Path.home() / '.local/share/pi-agent').exists():
            raise SystemExit('Existing native Pi installation found. Use a fresh host.')
        occupied = []
        for port in [9090, 8123, 1883, 18083, 15678, 15679, 18080, 18081, 4000, 8000, 7456, 18443, 18000, 30141]:
            with socket.socket() as s:
                if s.connect_ex(('127.0.0.1', port)) == 0:
                    occupied.append(port)
        if occupied:
            raise SystemExit(f'Existing services use profile ports: {occupied}. No changes made.')
    print('Preflight passed: Ubuntu 24.04 x86_64, fresh or managed installation.', flush=True)

def platform_install():
    run(['sudo', 'install', '-D', '-m', '0644', ROOT / 'overlays/needrestart-woow-release.conf', '/etc/needrestart/conf.d/woow-release.conf'])
    run(['sudo', 'install', '-D', '-m', '0644', ROOT / 'overlays/user-manager.conf', f'/etc/systemd/system/user@{os.getuid()}.service.d/woow-release.conf'])
    run(['sudo', 'systemctl', 'daemon-reload'])
    run(['sudo', 'apt-get', 'update'])
    packages = ['podman', 'uidmap', 'slirp4netns', 'fuse-overlayfs', 'dbus-user-session', 'git', 'curl', 'jq', 'openssl', 'zstd', 'age', 'rsync', 'python3', 'python3-venv', 'nodejs', 'npm', 'build-essential', 'tmux', 'xz-utils', 'unzip', 'iproute2']
    run(['sudo', 'apt-get', 'install', '-y', *packages])
    run(['sudo', 'apt-get', 'install', '-y', *[k + '=' + v for k, v in LOCK['platform_packages'].items()]])
    run(['sudo', 'apt-mark', 'hold', *LOCK['platform_packages']])
    run(['sudo', 'loginctl', 'enable-linger', output(['id', '-un'])])
    run(['systemctl', '--user', 'start', 'podman.socket'])
    run(['systemctl', '--user', 'enable', 'podman.socket'])
    run(['sudo', 'bash', ROOT / 'installer/ensure-swap.sh'])
    (STATE / 'packages.txt').write_text(output(['dpkg-query', '-W', '-f=${Package}\t${Version}\n']) + '\n')

def fetch_sources(materials):
    SOURCES.mkdir(parents=True, exist_ok=True)
    for repo, commit in LOCK['sources'].items():
        dest = SOURCES / repo
        if dest.exists():
            if output(['git', '-C', dest, 'rev-parse', 'HEAD']) != commit:
                raise SystemExit(f'Source mismatch: {repo}')
            continue
        cached = materials.parent / 'sources' / repo
        if (cached / '.git').exists() and output(['git', '-C', cached, 'rev-parse', 'HEAD']) == commit:
            run(['git', 'clone', '--no-hardlinks', cached, dest])
            run(['git', '-C', dest, 'remote', 'set-url', 'origin', f'https://github.com/WOOWTECH/{repo}.git'])
        else:
            run(['git', 'init', dest])
            run(['git', '-C', dest, 'remote', 'add', 'origin', f'https://github.com/WOOWTECH/{repo}.git'])
            run(['git', '-C', dest, 'fetch', '--depth=1', 'origin', commit])
            run(['git', '-C', dest, 'checkout', '--detach', 'FETCH_HEAD'])
        if output(['git', '-C', dest, 'rev-parse', 'HEAD']) != commit:
            raise SystemExit(f'Commit verification failed: {repo}')

def source_modes():
    # Git checkout under a restrictive caller umask can turn public 0644
    # configuration templates into 0600. Restore only Git-tracked file modes;
    # generated device credentials outside these source trees remain private.
    for repo in LOCK['sources']:
        dest = SOURCES / repo
        for entry in output(['git', '-C', dest, 'ls-files', '-s']).splitlines():
            metadata, name = entry.split('\t', 1)
            mode = metadata.split()[0]
            path = dest / name
            if mode in ('100644', '100755') and path.is_file() and not path.is_symlink():
                path.chmod(0o644 if mode == '100644' else 0o755)

def image_exists(ref):
    return subprocess.run(['podman', 'image', 'exists', ref]).returncode == 0

def import_images(materials, selected=None):
    manifest = json.loads((materials / 'materials.json').read_text())
    if manifest['release'] != RELEASE:
        raise SystemExit('Wrong materials release.')
    wanted = set(LOCK['images'])
    if selected:
        wanted = set()
        for app in selected:
            for path in (SOURCES / APPS[app][0] / 'quadlet').rglob('*.container'):
                match = re.search(r'^ContainerName=(.+)$', path.read_text(), re.M)
                if match and match[1] in LOCK['containers']:
                    wanted.add(LOCK['containers'][match[1]]['image_id'])
    for ident, rec in LOCK['images'].items():
        if ident not in wanted:
            continue
        if not image_exists(ident):
            if rec['private_material'] or ident in manifest['images']:
                entry = manifest['images'][ident]
                archive = materials / entry['file']
                if archive.name != entry['file'] or entry != MATERIALS.get(ident) or digest(archive) != entry['sha256']:
                    raise SystemExit(f'Archive checksum/path failure: {ident}')
                # zstd output goes directly to Podman: no untrusted filesystem extraction.
                unzip = subprocess.Popen(['zstd', '-dc', archive], stdout=subprocess.PIPE)
                loaded = subprocess.run(['podman', 'load'], stdin=unzip.stdout)
                unzip.stdout.close()
                if unzip.wait() or loaded.returncode:
                    raise SystemExit(f'Image import failed: {ident}')
            else:
                run(['podman', 'pull', '--arch=amd64', rec['reference']])
        actual = output(['podman', 'image', 'inspect', '--format', '{{.Id}}', ident]).removeprefix('sha256:')
        if actual != ident:
            raise SystemExit(f'Image content identity mismatch: {ident}')
        run(['podman', 'tag', ident, rec['deployment_reference']])
        for tag in rec['tags']:
            if '@' not in tag:
                run(['podman', 'tag', ident, tag])
    # The upstream code-server installer verifies its local build tag before rendering.
    code_version = (SOURCES / 'Woow_podman_code_server_package/VERSION').read_text().strip()
    if image_exists(LOCK['containers']['code-server']['image_id']):
        run(['podman', 'tag', LOCK['containers']['code-server']['image_id'], f'localhost/woow-code-server:{code_version}'])

def patch_images():
    records = {}
    for repo in LOCK['sources']:
        if repo == 'Woow_podman__mcp_server':
            # Its own provenance gate validates a clean checkout and renders
            # the reviewed image ID directly; no image-template overlay needed.
            continue
        for path in (SOURCES / repo).rglob('*.container'):
            if '.git' in path.parts:
                continue
            text = path.read_text()
            match = re.search(r'^ContainerName=(.+)$', text, re.M)
            if not match or match[1] not in LOCK['containers']:
                continue
            name = match[1]
            # Odoo still needs its image placeholders for the installer's account probe.
            if name not in ('odoo18-web', 'odoo18-db'):
                text = re.sub(r'^Image=.*$', 'Image=' + LOCK['containers'][name]['image'], text, flags=re.M)
            text = re.sub(r'^Pull=.*\n?', '', text, flags=re.M)
            text = re.sub(r'^(Image=.*)$', r'\1\nPull=never', text, flags=re.M)
            if name == 'litellm':
                # The upstream installer actively invokes health checks. A retry
                # count is therefore not a wall-clock startup budget: 40 attempts
                # can kill Prisma before its first migration finishes. Keep the
                # 900-second installer deadline and normal liveness restarts.
                text = re.sub(r'^HealthStartupRetries=.*$', 'HealthStartupRetries=0', text, flags=re.M)
            path.write_text(text)
            records[str(path.relative_to(SOURCES))] = digest(path)
    save_json(STATE / 'source-overlays.json', records)

def patch_first_boot():
    run(['python3', ROOT / 'installer/patch-nextcloud-backup.py', SOURCES / 'Woow_podman_nextcloud'])
    # keep-id performs a full first-use image ownership copy on Podman 4.9.
    # On N100 storage it can outlast the upstream five-minute start timeout.
    for repo in ('Woow_podman_opendesign', 'Woow_podman_code_server_package', 'Woow_podman_omnigent_package'):
        for unit in (SOURCES / repo / 'quadlet').glob('*.container'):
            text = unit.read_text()
            if 'UserNS=keep-id' in text:
                unit.write_text(re.sub(r'^TimeoutStartSec=(180|300)$', 'TimeoutStartSec=900', text, flags=re.M))
    # A reboot can leave stopped namespace joiners in Podman's database. The
    # owner's --replace then refuses to remove it while those dependents exist.
    # BindsTo/After already stop these exact application units before the owner;
    # remove their old containers before replacing the owner, never their volumes.
    owner = SOURCES / 'Woow_podman_opendesign/quadlet/open-design.container'
    cleanup = 'ExecStartPre=/usr/bin/podman rm --ignore --force open-design-nginx open-design-terminal open-design-mcp\n'
    text = owner.read_text()
    if cleanup not in text:
        owner.write_text(text.replace('[Service]\n', '[Service]\n' + cleanup, 1))
    # Odoo separately probes this constant even after the Quadlet is pinned.
    common = SOURCES / 'Woow_podman_odoo/scripts/common.sh'
    common.write_text(re.sub(r'^REPO_GATEWAY_IMAGE=.*$', 'REPO_GATEWAY_IMAGE=' + LOCK['containers']['odoo18-gateway']['image'], common.read_text(), flags=re.M))
    helpers = SOURCES / 'Woow_podman_odoo/scripts/odoo-helpers.sh'
    text = helpers.read_text()
    old = '  [[ $initialized == t ]] || odoo_tenant_init_base "$db"'
    new = '  if [[ $initialized != t ]]; then\n    odoo_tenant_init_base "$db"\n    ODOO_TENANT_FRESH=1\n  fi'
    if old in text:
        helpers.write_text(text.replace(old, new, 1))
    # HA discovery uses a shared namespace outside the regular woow/# topics.
    # Grant only this named local integration account; keep default deny and
    # isolation from other users' application topics.
    acl = SOURCES / 'Woow_podman_emqx/config/acl.conf'
    rule = '{allow, {username, "woow"}, all, ["homeassistant/#"]}.\n'
    if rule not in acl.read_text():
        acl.write_text(rule + acl.read_text())
    # Starting a second Erlang VM for every `emqx ctl status` probe exceeded
    # its 10s budget during a full cold boot, even after printing "is started".
    # Use the same local node-status endpoint as the existing entrance probe.
    # Functional MQTT authorization/read/write is checked separately.
    broker = SOURCES / 'Woow_podman_emqx/quadlet/emqx.container'
    text = broker.read_text()
    text = text.replace('HealthCmd=emqx ctl status', 'HealthCmd=curl -fsS --max-time 8 -o /dev/null http://127.0.0.1:18093/status')
    broker.write_text(text)
    # All application stacks share an N100. The Hermes gateway took >300s
    # during cold boot; provisioning must wait for it instead of failing once.
    provision = SOURCES / 'Woow_podman_hermes/systemd/hermes-provision.service'
    text = provision.read_text().replace('woow-provision --wait 300', 'woow-provision --wait 900')
    text = text.replace('TimeoutStartSec=420', 'TimeoutStartSec=1020')
    provision.write_text(text)
    # A running Nextcloud container may still be copying cron.php and creating
    # its database. Skip the timer until installation finishes, rather than
    # failing the entire initial install because the file is not there yet.
    cron = SOURCES / 'Woow_podman_nextcloud/systemd/nextcloud-cron.service'
    text = cron.read_text()
    condition = 'ExecCondition=/usr/bin/podman exec -u www-data nextcloud-app php -r "@include \'/var/www/html/config/config.php\'; exit((get_defined_vars()[\'CONFIG\'][\'installed\'] ?? false) ? 0 : 1);"\n'
    if condition not in text:
        text = text.replace('ExecStart=', condition + 'ExecStart=', 1)
        cron.write_text(text)

def set_config(app, overrides):
    repo = APPS[app][0]
    example = SOURCES / repo / 'config' / f'{app}.env.example'
    dest = Path.home() / '.config' / app / f'{app}.env'
    if dest.exists():
        return  # Device-local changes are never overwritten on resume.
    text = example.read_text()
    for k, v in overrides.items():
        if re.search('^' + re.escape(k) + '=', text, re.M):
            text = re.sub('^' + re.escape(k) + '=.*$', k + '=' + str(v), text, flags=re.M)
        else:
            text += f'\n{k}={v}\n'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.parent.chmod(0o755)
    dest.write_text(text)
    dest.chmod(0o600)

def configure(address):
    if not re.fullmatch(r'[A-Za-z0-9.-]+', address):
        raise SystemExit('Use a hostname or IPv4 address, without a scheme/path/port.')
    def imported_digest(name):
        return output(['podman', 'image', 'inspect', '--format', '{{.Digest}}', LOCK['containers'][name]['image_id']])
    overrides = {
        'homeassistant': {'HA_TZ': 'Asia/Taipei', 'HA_PRIVILEGED': 'false', 'HA_MCP': 'true', 'HA_MATTER': 'true'},
        'emqx': {'WOOW_EMQX_BIND': '0.0.0.0'},
        # The source's Paseo bridge requires its own approved HTTPS origin.
        # Never reuse the source device's domain or invent a trusted origin.
        'open-design': {'WOOW_OD_PASEO': 'off'},
        'n8n': {'HOST_BIND': '0.0.0.0', 'N8N_SECURE_COOKIE': 'false', 'EXECUTIONS_MODE': 'queue', 'N8N_QUEUE_WEBHOOK_PROCESSOR': 'true'},
        'nextcloud': {'HOST_PORT': 18082, 'NEXTCLOUD_TRUSTED_DOMAINS': f'localhost 127.0.0.1 nextcloud-gateway {address}'},
    }
    for app in APPS:
        if app == 'woow-cf-tunnel':
            # Upstream's first run only creates settings and exits successfully.
            # Prepare the reviewed fresh-volume settings before invoking it.
            set_config(app, {})
        if app != 'woow-cf-tunnel':
            if app == 'odoo18':
                if not image_exists(LOCK['containers']['odoo18-web']['image_id']):
                    continue
                overrides[app] = {'WOOW_ODOO_TENANT_CLOUD': 'True', 'WOOW_ODOO_DEFAULT_DB': 'odoo', 'WOOW_ODOO_ADMIN_LOGIN': 'admin@example.invalid', 'WOOW_ODOO_GATEWAY_ENABLED': 'True', 'WOOW_ODOO_IMAGE': 'localhost/woow-release/odoo18-web@' + imported_digest('odoo18-web'), 'WOOW_ODOO_DB_IMAGE': 'localhost/woow-release/odoo18-db@' + imported_digest('odoo18-db')}
            set_config(app, overrides.get(app, {}))

def install_apps(selected):
    for app in selected:
        repo, args = APPS[app]
        print('Installing ' + app, flush=True)
        with (STATE / (app + '.log')).open('a') as log:
            if app == 'homeassistant' and subprocess.run(['podman', 'secret', 'exists', 'homeassistant-mcp-token']).returncode != 0:
                run(['bash', SOURCES / repo / 'scripts/install.sh', '--with-matter', '--without-mcp', '--no-smoke'], stdout=log, stderr=subprocess.STDOUT)
                run(['python3', ROOT / 'installer/bootstrap-ha.py'], stdout=log, stderr=subprocess.STDOUT)
            result = subprocess.run(['bash', str(SOURCES / repo / 'scripts/install.sh'), *args], stdout=log, stderr=subprocess.STDOUT, umask=0o022)
        if result.returncode:
            raise SystemExit(f'{app} failed; inspect the private log: {STATE / (app + ".log")}. Resume after correcting the cause.')
        if app == 'n8n':
            run(['python3', ROOT / 'installer/bootstrap-n8n.py'])
        if app == 'nextcloud':
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                try:
                    with urllib.request.urlopen('http://127.0.0.1:18082/status.php', timeout=10) as response:
                        status = json.load(response)
                    if status.get('installed') and not status.get('maintenance') and not status.get('needsDbUpgrade'):
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(5)
            else:
                raise SystemExit('Nextcloud initialization did not complete.')
            with (STATE / (app + '.log')).open('a') as log:
                for command in [['podman', 'exec', '-u', 'www-data', 'nextcloud-app', 'php', 'occ', 'background:cron'],
                                ['podman', 'exec', 'nextcloud-db', 'psql', '-U', 'nextcloud', '-d', 'nextcloud', '-c', 'CREATE EXTENSION IF NOT EXISTS vector'],
                                ['podman', 'exec', '-u', 'www-data', 'nextcloud-app', 'php', 'occ', 'db:add-missing-indices']]:
                    run(command, stdout=log, stderr=subprocess.STDOUT)
        print(app + ' installer passed', flush=True)

def office(address):
    secret = 'nextcloud-office-password'
    if subprocess.run(['podman', 'secret', 'exists', secret]).returncode != 0:
        import secrets
        run(['podman', 'secret', 'create', secret, '-'], input=secrets.token_urlsafe(32).encode(), stdout=subprocess.DEVNULL)
    for name in ['nextcloud-office', 'nextcloud-gateway']:
        text = (ROOT / 'overlays' / (name + '.container')).read_text().replace('@@NEXTCLOUD_AUTHORITY@@', address + ':18081')
        text = re.sub(r'^Image=.*$', 'Image=' + LOCK['containers'][name]['image'] + '\nPull=never', text, flags=re.M)
        (QDIR / (name + '.container')).write_text(text)
    shutil.copyfile(ROOT / 'overlays/nextcloud-gateway.conf', Path.home() / '.config/nextcloud/gateway.conf')
    (Path.home() / '.config/nextcloud/gateway.conf').chmod(0o644)
    run(['systemctl', '--user', 'daemon-reload'])
    run(['systemctl', '--user', 'start', 'nextcloud-office.service', 'nextcloud-gateway.service'])
    run(['python3', ROOT / 'installer/nextcloud-office-app.py'])
    run(['podman', 'exec', '--user', 'www-data', 'nextcloud-app', 'php', 'occ', 'config:app:set', 'richdocuments', 'wopi_url', '--value=http://' + address + ':18081'])
    run(['podman', 'exec', '--user', 'www-data', 'nextcloud-app', 'php', 'occ', 'config:app:set', 'richdocuments', 'public_wopi_url', '--value=http://' + address + ':18081'])

def native():
    repo = SOURCES / 'Woow_native_os_pi_agent'
    env = os.environ.copy()
    asset = LOCK['native_assets']['piweb']
    cached = STATE / 'assets' / asset['url'].rsplit('/', 1)[-1]
    cached.parent.mkdir(parents=True, exist_ok=True)
    if not cached.exists():
        partial = cached.with_suffix('.download')
        run(['curl', '-fsSL', '--retry', '3', asset['url'], '-o', partial])
        if digest(partial) != asset['sha256']:
            raise SystemExit('Native Pi artifact checksum mismatch; incomplete file not promoted.')
        partial.replace(cached)
    if digest(cached) != asset['sha256']:
        raise SystemExit('Native Pi artifact checksum mismatch.')
    Path(str(cached) + '.sha256').write_text(asset['sha256'] + '  ' + cached.name + '\n')
    env['PI_AGENT_PIWEB_ARTIFACT'] = str(cached)
    with (STATE / 'native-pi.log').open('a') as log:
        result = subprocess.run(['bash', str(repo / 'install.sh')], env=env, stdout=log, stderr=subprocess.STDOUT, umask=0o022)
    if result.returncode:
        raise SystemExit('Native Pi installer failed; see private native-pi.log')
    run(['python3', ROOT / 'installer/patch-native-startup.py'])
    import secrets
    pwfile = STATE / 'piweb-password'
    if not pwfile.exists():
        pwfile.write_text(secrets.token_urlsafe(32))
        pwfile.chmod(0o600)
    envfile = Path.home() / '.config/woow-release/piweb.env'
    envfile.parent.mkdir(parents=True, exist_ok=True)
    envfile.write_text('PI_WEB_PASSWORD=' + pwfile.read_text() + '\n')
    envfile.chmod(0o600)
    dropin = Path.home() / '.config/systemd/user/pi-web.service.d'
    dropin.mkdir(parents=True, exist_ok=True)
    (dropin / 'release-auth.conf').write_text('[Service]\nEnvironmentFile=%h/.config/woow-release/piweb.env\n')
    run(['systemctl', '--user', 'daemon-reload'])
    run(['systemctl', '--user', 'restart', 'pi-web.service'])

def mcp():
    repo = SOURCES / 'Woow_podman__mcp_server'
    # Pin to the actual deployed build's merged source, not today's arbitrary main.
    if subprocess.run(['git', '-C', repo, 'merge-base', '--is-ancestor', LOCK['sources'][repo.name], 'origin/main']).returncode:
        run(['git', '-C', repo, 'fetch', '--unshallow', 'origin', 'main'])
    for product, port in [('headscale', 18509), ('emqx', 18501), ('hermes', 18502), ('n8n', 18503), ('odoo', 18504), ('litellm', 18505), ('nextcloud', 18506), ('opendesign', 18507), ('k8s', 18508)]:
        extra = []
        if product == 'headscale' and not (Path.home() / '.config/headscale-mcp-admin/headscale-mcp-admin.env').exists():
            extra = ['--origin', 'http://127.0.0.1:' + str(port)]
        with (STATE / (product + '-mcp.log')).open('a') as log:
            # Existing owner-approved unsigned release flow still validates the clean
            # merged commit, image labels and immutable content ID before installation.
            proc = subprocess.run(['bash', str(repo / 'products/deploy/manage.sh'), product, 'install', '--skip-release-signature', '--port', str(port), *extra], stdout=log, stderr=subprocess.STDOUT, umask=0o022)
            if proc.returncode and product == 'k8s':
                # A fresh device deliberately has no cluster credentials. The
                # child can briefly report running before failing auto-detect;
                # repeat the upstream management test after that state settles.
                # Never accept a configured backend failure through this path.
                config = subprocess.run(['podman', 'exec', 'k8s-mcp-admin', 'cat', '/data/config.json'], capture_output=True, text=True)
                connection = json.loads(config.stdout).get('connection', {}) if config.returncode == 0 else None
                if connection is not None and not connection.get('kubeconfig') and str(connection.get('in_cluster', 'false')).lower() != 'true':
                    for _ in range(30):
                        with urllib.request.urlopen('http://127.0.0.1:18508/healthz', timeout=10) as response:
                            health = json.load(response)
                        if health.get('mcp') == 'not_running':
                            proc = subprocess.run(['bash', str(repo / 'products/deploy/manage.sh'), 'k8s', 'smoke'], stdout=log, stderr=subprocess.STDOUT, umask=0o022)
                            if proc.returncode == 0:
                                save_json(STATE / 'k8s-pending.json', {'management_smoke_passed': True, 'cluster_configured': False, 'cluster_tools_tested': False})
                                break
                        time.sleep(2)
        if proc.returncode:
            raise SystemExit(product + ' MCP install failed; inspect its private log.')

def cockpit(address, selection=None, presentation_only=False):
    branded = selection is not None and selection['mode'] in ('production', 'development')
    repo = brands.prepare_source(STATE, selection) if branded else SOURCES / 'Woow_cockpit'
    brand_args = ['--brand', selection['brand']] if branded else []
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['BRAND'] = selection['brand'] if branded else 'woowtech'
    if branded:
        # Probe the agreed interface before touching the installed management UI.
        help_text = output(['python3', '-B', repo / 'scripts/manage.py', 'install', '--help'])
        if '--brand' not in help_text:
            raise ValueError('Pinned Cockpit source does not implement install --brand')
        # The separate brand source must retain the same PWA image as rc1.
        pwa_unit = repo / 'pwa-gateway/woow-cockpit-pwa.container'
        text = pwa_unit.read_text()
        if re.findall(r'^ContainerName=(.+)$', text, re.M) != ['woow-cockpit-pwa'] or len(re.findall(r'^Image=', text, re.M)) != 1:
            raise ValueError('Unexpected Cockpit PWA runtime identity')
        text = re.sub(r'^Pull=.*\n?', '', text, flags=re.M)
        text = re.sub(r'^Image=.*$', 'Image=' + LOCK['containers']['woow-cockpit-pwa']['image'] + '\nPull=never', text, flags=re.M)
        pwa_unit.write_text(text)
    run(['python3', ROOT / 'installer/patch-cockpit-held-packages.py', repo])
    run(['python3', ROOT / 'installer/patch-cockpit-backup-navigation.py', repo])
    # Source overlays are applied only to the distribution-owned staging clone.
    service = repo / 'pi-web-integration/woowtech-piweb-gateway.service'
    service.write_text(service.read_text().replace('ExecStart=/usr/bin/node ', 'ExecStart=/usr/local/lib/woow-node/node '))
    if branded:
        save_json(STATE / 'brand.json', brands.receipt_for(selection, repo, 'installing'))
    owners = [] if presentation_only else ['--service-owner', output(['id', '-un'])]
    run(['sudo', 'env', 'PYTHONDONTWRITEBYTECODE=1', 'python3', repo / 'scripts/manage.py', 'install', *brand_args, *owners], env=env)
    # Fresh-host policy chosen by the product owner: HTTP on LAN; HTTPS belongs at an external tunnel.
    conf = '[WebService]\nAllowUnencrypted=true\nLoginTo=false\n\n[Session]\nIdleTimeout=0\n'
    if not presentation_only:
        run(['sudo', 'install', '-d', '-m', '755', '/etc/cockpit'])
        run(['sudo', 'tee', '/etc/cockpit/cockpit.conf'], input=conf.encode(), stdout=subprocess.DEVNULL)
        run(['sudo', 'systemctl', 'enable', '--now', 'cockpit.socket'])
    run(['sudo', 'env', 'PYTHONDONTWRITEBYTECODE=1', 'python3', repo / 'scripts/manage.py', 'verify'], env=env)
    run(['bash', repo / 'pwa-gateway/install.sh'], env=env)
    # Keep the gateway's Node runtime root-owned; do not execute a user's binary as a system service.
    node = Path.home() / '.local/share/pi-agent/node/bin/node'
    run(['sudo', 'install', '-d', '-m', '755', '/usr/local/lib/woow-node'])
    run(['sudo', 'install', '-m', '755', node, '/usr/local/lib/woow-node/node'])
    sudo_env = ['env', 'BRAND=' + selection['brand']] if branded else []
    run(['sudo', *sudo_env, 'bash', repo / 'pi-web-integration/install.sh', address, '19094'], env=env)
    if branded:
        verify_presentation(repo, selection)
        save_json(STATE / 'brand.json', brands.receipt_for(selection, repo, 'applied'))


def verify_presentation(repo, selection, system_root=Path('/'), home=None):
    """Check the installed brand and separately installed PWA/Pi artifacts."""
    home = Path.home() if home is None else home
    marker = system_root / 'etc/cockpit/branding/brand.json'
    if marker.is_symlink() or json.loads(marker.read_text()).get('id') != selection['brand']:
        raise ValueError('Installed Cockpit brand profile mismatch')
    copies = {
        'usr/local/libexec/woowtech-piweb-gateway.mjs': 'pi-web-integration/gateway.mjs',
        'usr/local/share/cockpit/woowpiweb/index.html': 'pi-web-integration/package/index.html',
        'usr/local/share/cockpit/woowpiweb/style.css': 'pi-web-integration/package/style.css',
    }
    for installed, source in copies.items():
        path = system_root / installed
        if path.is_symlink() or digest(path) != digest(repo / source):
            raise ValueError('Installed Pi Web gateway presentation drift')
    if digest(QDIR / 'woow-cockpit-pwa.container') != digest(repo / 'pwa-gateway/woow-cockpit-pwa.container'):
        raise ValueError('Cockpit PWA Quadlet differs from its locked source')
    with tempfile.TemporaryDirectory(prefix='brand-check-', dir=STATE) as temp:
        expected = Path(temp)
        proc = subprocess.run(['python3', '-B', str(repo / 'pwa-gateway/render.py'),
                               '--brand', selection['brand'], '--output', str(expected)], capture_output=True)
        if proc.returncode:
            raise ValueError('Pinned Cockpit PWA renderer failed verification')
        for relative in ('nginx.conf', 'assets/manifest.webmanifest', 'assets/icon-192.png', 'assets/icon-512.png'):
            installed = home / '.local/share/woowtech-cockpit-pwa' / relative
            if installed.is_symlink() or digest(installed) != digest(expected / relative):
                raise ValueError('Installed Cockpit PWA presentation drift: ' + relative)


def verify_brand(selection=None):
    """Keep development validation distinct from release acceptance."""
    try:
        installed, repo = brands.verify_receipt(STATE, RELEASE, ROOT / 'releases' / RELEASE / 'lock.json')
        if installed is None:
            if selection and (selection['brand'] != 'woowtech' or selection['mode'] in ('production', 'development')):
                raise ValueError('Requested brand has not been installed')
            if Path('/etc/cockpit/branding/brand.json').exists():
                raise ValueError('Installed brand profile has no distribution receipt')
            return {'brand': 'woowtech', 'mode': 'legacy', 'passed': True, 'release_eligible': True}
        if selection and (installed['brand'] != selection['brand'] or
                          (selection['mode'] in ('production', 'development') and
                           any(installed[k] != selection[k] for k in ('mode', 'commit', 'tree', 'material_lock_sha256')))):
            raise ValueError('Installed branding differs from the requested material')
        # Cockpit verifies its managed-file journal, including renderer output.
        checked = subprocess.run(['sudo', 'env', 'PYTHONDONTWRITEBYTECODE=1', 'python3',
                                  str(repo / 'scripts/manage.py'), 'verify'], capture_output=True, text=True)
        if checked.returncode:
            raise ValueError('Cockpit managed-file verification failed')
        verify_presentation(repo, installed)
        return {'brand': installed['brand'], 'mode': installed['mode'], 'passed': True,
                'commit': installed['commit'], 'tree': installed['tree'],
                'release_eligible': installed['mode'] == 'production'}
    except (ValueError, OSError, KeyError, TypeError) as error:
        # No subprocess stdout, config, or credentials enter the public report.
        return {'passed': False, 'release_eligible': False, 'error': str(error)}

def verify(selection=None, allow_development=False):
    result = {'release': RELEASE, 'containers': {}, 'external_authorizations_pending': LOCK['external_authorizations']}
    result['sources'] = {}
    for repo, expected in LOCK['sources'].items():
        actual = subprocess.run(['git', '-C', SOURCES / repo, 'rev-parse', 'HEAD'], capture_output=True, text=True)
        overlays = subprocess.run(['git', '-C', SOURCES / repo, 'diff', '--name-only'], capture_output=True, text=True)
        result['sources'][repo] = {'commit_matches': actual.returncode == 0 and actual.stdout.strip() == expected, 'local_overlays': overlays.stdout.splitlines()}
    result['native_versions'] = {}
    native_root = Path.home() / '.local/share/pi-agent'
    pins = (SOURCES / 'Woow_native_os_pi_agent/lib/pins.sh').read_text()
    for name, pin, executable in [('node', 'NODE', native_root / 'node/bin/node'), ('claude', 'CLAUDE', native_root / 'bin/claude'), ('codex', 'CODEX', native_root / 'bin/codex'), ('pi', None, native_root / 'bin/pi')]:
        expected = re.search('^PIN_' + pin + r'_VERSION=([0-9.]+)', pins, re.M)[1] if pin else LOCK['native_pi_version']
        try:
            query = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=30)
            match = re.search(r'\d+\.\d+\.\d+', query.stdout)
            result['native_versions'][name] = {'version': match[0] if match else None, 'matches': query.returncode == 0 and bool(match) and match[0] == expected}
        except (OSError, subprocess.TimeoutExpired):
            result['native_versions'][name] = {'matches': False}
    overlay = STATE / 'native-startup-overlay.json'
    plugin_installer = native_root / 'plugins/pi-omnigent-plugin/src/installer.mjs'
    overlay_record = json.loads(overlay.read_text()) if overlay.is_file() else {}
    result['native_startup_overlay_matches'] = plugin_installer.is_file() and overlay_record.get('probe_timeout_ms') == 30000 and overlay_record.get('installed_sha256') == digest(plugin_installer)
    result['platform_packages'] = {}
    for package, expected in LOCK['platform_packages'].items():
        query = subprocess.run(['dpkg-query', '-W', '-f=${Version}', package], capture_output=True, text=True)
        result['platform_packages'][package] = {'version': query.stdout.strip(), 'matches': query.returncode == 0 and query.stdout.strip() == expected}
    holds = subprocess.run(['apt-mark', 'showhold'], capture_output=True, text=True)
    policy = Path('/etc/needrestart/conf.d/woow-release.conf')
    result['maintenance'] = {
        'release_packages_held': holds.returncode == 0 and set(LOCK['platform_packages']).issubset(holds.stdout.splitlines()),
        'backup_restart_policy_matches': policy.is_file() and digest(policy) == digest(ROOT / 'overlays/needrestart-woow-release.conf'),
    }
    stop_budget = subprocess.run(['systemctl', 'show', f'user@{os.getuid()}.service', '-p', 'TimeoutStopUSec', '--value'], capture_output=True, text=True)
    result['maintenance']['user_manager_stop_budget_matches'] = stop_budget.returncode == 0 and stop_budget.stdout.strip() in ('3min', '180s')
    result['native_units'] = {}
    for unit, user in [('pi-web.service', True), ('woow-native-connection.service', True), ('hermes-provision.service', True), ('cockpit.socket', False), ('woowtech-piweb-gateway.service', False)]:
        query = subprocess.run(['systemctl', *(['--user'] if user else []), 'is-active', unit], capture_output=True, text=True)
        result['native_units'][unit] = query.returncode == 0 and query.stdout.strip() == 'active'
    # A single read avoids 47 Podman startup/lock cycles under cold-boot load.
    # Podman may still return records for existing names when another is absent.
    proc = subprocess.run(['podman', 'inspect', *LOCK['containers']], capture_output=True, text=True)
    try:
        inspected = {c['Name'].lstrip('/'): c for c in json.loads(proc.stdout)}
    except (ValueError, TypeError, KeyError):
        inspected = {}
    for name, rec in LOCK['containers'].items():
        c = inspected.get(name)
        if c is None:
            result['containers'][name] = {'status': 'missing'}
            continue
        result['containers'][name] = {'running': c['State']['Running'], 'image_matches': c['Image'].removeprefix('sha256:') == rec['image_id'], 'health': c['State'].get('Health', {}).get('Status', 'not-declared')}
    result['http'] = {}
    for name, url in {'cockpit': 'http://127.0.0.1:9090/ping', 'ha': 'http://127.0.0.1:8123/', 'emqx': 'http://127.0.0.1:18083/', 'n8n': 'http://127.0.0.1:15678/healthz', 'nextcloud': 'http://127.0.0.1:18081/status.php', 'odoo': 'http://127.0.0.1:18080/web/login', 'litellm': 'http://127.0.0.1:4000/health/liveliness', 'pi-web': 'http://127.0.0.1:30141/'}.items():
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                result['http'][name] = response.status
        except Exception as e:
            result['http'][name] = type(e).__name__
    result['passed'] = all(c.get('running') and c.get('image_matches') and c.get('health') not in ('unhealthy', 'starting') for c in result['containers'].values()) and all(v == 200 for v in result['http'].values()) and all(p['matches'] for p in result['platform_packages'].values()) and all(result['native_units'].values())
    result['passed'] = result['passed'] and all(s['commit_matches'] for s in result['sources'].values()) and all(v['matches'] for v in result['native_versions'].values())
    result['passed'] = result['passed'] and all(result['maintenance'].values())
    result['passed'] = result['passed'] and result['native_startup_overlay_matches']
    result['branding'] = verify_brand(selection)
    result['runtime_passed'] = result['passed'] and result['branding']['passed']
    result['release_eligible'] = result['branding']['release_eligible']
    result['passed'] = result['runtime_passed'] and result['release_eligible']
    save_json(STATE / 'verification.json', result)
    print(json.dumps(result, indent=2))
    return result['runtime_passed'] if allow_development else result['passed']

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['plan', 'brand', 'platform', 'sources', 'images', 'apps', 'office', 'native', 'cockpit', 'mcp', 'local-links', 'backup-catalog', 'verify', 'apply'])
    p.add_argument('--materials', type=Path, default=Path('/mnt/materials/images'))
    p.add_argument('--address', help='LAN IPv4 address; detected automatically for a fresh device')
    p.add_argument('--apps', nargs='+', choices=APPS)
    p.add_argument('--brand', choices=brands.BRANDS, help='Presentation only; defaults to installed brand, otherwise woowtech')
    p.add_argument('--brand-lock', type=Path, help='Committed material lock inside distribution/brand-materials')
    p.add_argument('--development', action='store_true', help='Allow a local Cockpit commit for plan/brand only; never release eligible')
    p.add_argument('--cockpit-source', type=Path, help='Explicit clean local Git checkout; requires --development')
    args = p.parse_args()
    if (args.development or args.cockpit_source is not None) and args.action not in ('plan', 'brand'):
        p.error('Local development sources are allowed only for plan and brand')
    try:
        selection = brands.select(args.brand, RELEASE, ROOT / 'releases' / RELEASE / 'lock.json', STATE,
                                  args.brand_lock, args.cockpit_source, args.development)
    except (ValueError, OSError, KeyError, TypeError) as error:
        p.error(str(error))
    if args.action == 'plan':
        print(json.dumps({'release': RELEASE, 'applications': list(APPS), 'containers': len(LOCK['containers']), 'new_device': True, 'requires_authorized_materials': True, 'pending_authorizations': LOCK['external_authorizations'], 'branding': selection}, indent=2))
        return
    if args.action in ('apply', 'cockpit', 'brand') and not selection['ready']:
        p.error(selection['reason'])
    if args.action == 'brand' and not (STATE / 'device.json').is_file():
        p.error('brand requires an existing distribution-managed device; use apply for a new appliance')
    os.umask(0o077)
    args.address = device_address(args.address)
    STATE.mkdir(parents=True, exist_ok=True)
    # Native Pi has no containers/shared image state and may install while images load.
    guard_name = 'native.install.lock' if args.action == 'native' else 'install.lock'
    with (STATE / guard_name).open('w') as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another installer is still running; wait for it before resuming.')
        preflight()
        if not (STATE / 'device.json').exists():
            import uuid
            save_json(STATE / 'device.json', {'device_id': str(uuid.uuid4()), 'release': RELEASE, 'address': args.address})
        if args.action in ('apply', 'cockpit', 'brand') and selection['mode'] in ('production', 'development'):
            # Validate source provenance before any platform/application changes.
            brands.prepare_source(STATE, selection)
        steps = ['platform', 'sources', 'images', 'apps', 'office', 'native', 'cockpit', 'mcp', 'local-links', 'backup-catalog', 'verify'] if args.action == 'apply' else [args.action]
        for step in steps:
            if step == 'platform': platform_install()
            elif step == 'sources': fetch_sources(args.materials); source_modes()
            elif step == 'images': import_images(args.materials, args.apps); patch_images(); patch_first_boot()
            elif step == 'apps': patch_first_boot(); configure(args.address); install_apps(args.apps or list(APPS))
            elif step == 'office': office(args.address)
            elif step == 'native': native()
            elif step in ('cockpit', 'brand'):
                cockpit(args.address, selection, presentation_only=step == 'brand')
                if step == 'brand' and not verify(selection, allow_development=args.development):
                    raise SystemExit(1)
            elif step == 'mcp': mcp()
            elif step == 'local-links': run(['python3', ROOT / 'installer/local-links.py'])
            elif step == 'backup-catalog': run(['python3', ROOT / 'installer/backup-catalog.py'])
            elif step == 'verify' and not verify(selection): raise SystemExit(1)

if __name__ == '__main__':
    main()
