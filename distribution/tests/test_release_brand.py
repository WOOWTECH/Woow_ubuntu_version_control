import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_brands', ROOT / 'installer/woow-release.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def unconfigured_profile(brand):
    """An explicit legacy/pending fixture; never depends on production pins."""
    return {'schema_version': 1, 'id': brand, 'display_name': brand,
            'feature_profile': 'openclaw-x86_64', 'material_lock': None}


class BrandIntegration(unittest.TestCase):
    def test_unconfigured_brand_plans_preserve_runtime_and_do_not_run_commands(self):
        plans = []
        with tempfile.TemporaryDirectory() as tmp, patch.object(r, 'STATE', Path(tmp) / 'state'), \
                patch.object(r.brands, 'profile', side_effect=unconfigured_profile), \
                patch.object(r.subprocess, 'run', side_effect=AssertionError('plan must not run commands')):
            for brand in ('woowtech', 'apporo'):
                out = io.StringIO()
                with patch('sys.argv', ['woow-release.py', 'plan', '--brand', brand]), contextlib.redirect_stdout(out):
                    r.main()
                plans.append(json.loads(out.getvalue()))
            self.assertFalse(r.STATE.exists())
        for key in ('release', 'applications', 'containers', 'pending_authorizations'):
            self.assertEqual(plans[0][key], plans[1][key])
        self.assertEqual(plans[0]['containers'], 47)
        self.assertTrue(plans[0]['branding']['ready'])
        self.assertFalse(plans[1]['branding']['ready'])

    def test_repository_brand_plans_share_material_and_only_read_committed_git(self):
        # Production plans must really validate the committed lock. Only the
        # exact read-only git show is permitted; sudo/network/deployment fail.
        profiles = [r.brands.profile(brand) for brand in r.brands.BRANDS]
        lock_name = profiles[0]['material_lock']
        self.assertEqual(lock_name, profiles[1]['material_lock'])
        real_run = subprocess.run

        def read_only(args, **kwargs):
            self.assertIsNotNone(lock_name)
            self.assertEqual(args, ['git', '-C', str(ROOT.parent), 'show',
                                    'HEAD:distribution/brand-materials/' + lock_name])
            return real_run(args, **kwargs)

        plans = []
        with tempfile.TemporaryDirectory() as tmp, patch.object(r, 'STATE', Path(tmp) / 'state'), \
                patch.object(r.subprocess, 'run', side_effect=read_only) as command:
            for args in ([], ['--brand', 'woowtech'], ['--brand', 'apporo']):
                out = io.StringIO()
                with patch('sys.argv', ['woow-release.py', 'plan', *args]), contextlib.redirect_stdout(out):
                    r.main()
                plans.append(json.loads(out.getvalue()))
            self.assertFalse(r.STATE.exists())
        self.assertEqual(plans[0], plans[1], 'new hosts still default to woowtech')
        for key in ('release', 'applications', 'containers', 'pending_authorizations'):
            self.assertEqual(plans[1][key], plans[2][key], key)
        if lock_name is not None:
            self.assertEqual(command.call_count, 3)
            for plan in plans:
                self.assertEqual(plan['branding']['mode'], 'production')
                self.assertTrue(plan['branding']['ready'])
            for key in ('material_lock', 'material_lock_sha256', 'commit', 'tree', 'main_commit'):
                self.assertEqual(plans[1]['branding'][key], plans[2]['branding'][key], key)
        else:
            command.assert_not_called()  # Preparation branch before the reviewed pin arrives.

    def test_pending_apporo_apply_and_unmanaged_brand_action_stop_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r, 'STATE', Path(tmp) / 'state'), \
                patch.object(r.brands, 'profile', side_effect=unconfigured_profile), \
                patch.object(r, 'device_address') as address, patch.object(r, 'run') as command:
            for args in (['apply', '--brand', 'apporo'], ['brand'],
                         ['apply', '--development', '--cockpit-source', '/unused']):
                with self.subTest(args=args), patch('sys.argv', ['woow-release.py', *args]), \
                        contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    r.main()
            address.assert_not_called()
            command.assert_not_called()
            self.assertFalse(r.STATE.exists())

    def test_cockpit_passes_brand_to_shared_installers_without_changing_service_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / 'Woow_cockpit'
            (repo / 'pi-web-integration').mkdir(parents=True)
            service = repo / 'pi-web-integration/woowtech-piweb-gateway.service'
            service.write_text('ExecStart=/usr/bin/node gateway.mjs\n')
            (repo / 'pwa-gateway').mkdir()
            pwa_unit = repo / 'pwa-gateway/woow-cockpit-pwa.container'
            pwa_unit.write_text('[Container]\nContainerName=woow-cockpit-pwa\nImage=nginx:latest\nPull=always\n')
            selection = {'brand': 'apporo', 'mode': 'development'}
            with patch.object(r.brands, 'prepare_source', return_value=repo), \
                    patch.object(r.brands, 'receipt_for', side_effect=lambda s, p, status: {'status': status}), \
                    patch.object(r, 'verify_presentation'), patch.object(r, 'save_json') as save, patch.object(r, 'run') as command, \
                    patch.object(r, 'output', side_effect=lambda a: '--brand' if '--help' in a else 'operator'):
                r.cockpit('192.0.2.20', selection)
            calls = command.call_args_list
            install = next(c for c in calls if 'install' in c.args[0] and any(str(a).endswith('scripts/manage.py') for a in c.args[0]))
            self.assertIn('--brand', install.args[0])
            self.assertIn('apporo', install.args[0])
            self.assertIn('--service-owner', install.args[0])
            self.assertIn('operator', install.args[0])
            pwa = next(c for c in calls if any(str(a).endswith('pwa-gateway/install.sh') for a in c.args[0]))
            pi = next(c for c in calls if any(str(a).endswith('pi-web-integration/install.sh') for a in c.args[0]))
            self.assertEqual(pwa.kwargs['env']['BRAND'], 'apporo')
            self.assertIn('BRAND=apporo', pi.args[0])
            self.assertEqual(pi.args[0][-2:], ['192.0.2.20', '19094'])
            self.assertEqual([c.args[1]['status'] for c in save.call_args_list], ['installing', 'applied'])
            self.assertNotIn('apporo', service.read_text())
            self.assertIn('Image=' + r.LOCK['containers']['woow-cockpit-pwa']['image'], pwa_unit.read_text())
            self.assertIn('Pull=never', pwa_unit.read_text())
            self.assertNotIn('latest', pwa_unit.read_text())
            self.assertFalse(any('podman' in c.args[0] for c in calls))

    def test_brand_only_preserves_pi_network_config_and_restarts_only_active_gateways(self):
        units = ('woowtech-piweb-gateway.service', 'woowtech-piweb-gateway-vpn.service',
                 'woowtech-piweb-gateway-public.service')
        copies = {
            '/usr/local/libexec/woowtech-piweb-gateway.mjs': ('gateway.mjs', '0755'),
            '/usr/local/share/cockpit/woowpiweb/index.html': ('package/index.html', '0644'),
            '/usr/local/share/cockpit/woowpiweb/style.css': ('package/style.css', '0644'),
        }
        for active_units in (units, units[:1], ()):
            with self.subTest(active=active_units), tempfile.TemporaryDirectory() as tmp:
                repo, host = Path(tmp) / 'repo', Path(tmp) / 'host'
                pi = repo / 'pi-web-integration'
                (pi / 'package').mkdir(parents=True)
                (pi / units[0]).write_text('ExecStart=/usr/bin/node gateway.mjs\n')
                (repo / 'pwa-gateway').mkdir()
                (repo / 'pwa-gateway/woow-cockpit-pwa.container').write_text(
                    '[Container]\nContainerName=woow-cockpit-pwa\nImage=nginx:latest\n')
                for destination, (source, _) in copies.items():
                    (pi / source).write_text('new presentation: ' + source)
                    installed = host / destination.lstrip('/')
                    installed.parent.mkdir(parents=True, exist_ok=True)
                    installed.write_text('old presentation')
                preserved = {
                    'usr/local/share/cockpit/woowpiweb/app.js':
                        'const vpn="http://100.64.0.8:19094", publicOrigin="https://pi.example.test";',
                    'usr/local/share/cockpit/woowpiweb/manifest.json':
                        '{"content-security-policy":"frame-src http://100.64.0.8:19094 https://pi.example.test"}',
                    'usr/local/lib/woow-node/node': 'existing pinned node',
                    'etc/cockpit/cockpit.conf': '[WebService]\nOrigins=https://cockpit.example.test\n',
                }
                for unit, bind in zip(units, ('192.0.2.20', '100.64.0.8', '127.0.0.1')):
                    preserved['etc/systemd/system/' + unit] = '[Service]\nEnvironment=PI_GATEWAY_BIND=' + bind
                    preserved['etc/systemd/system/' + unit + '.d/network.conf'] = (
                        '[Service]\nEnvironment=PI_GATEWAY_PUBLIC_ORIGIN=https://pi.example.test\n')
                for name, content in preserved.items():
                    path = host / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content)
                before = {name: (host / name).read_bytes() for name in preserved}
                writes, restarts = [], []

                def command(args, **kwargs):
                    args = [str(a) for a in args]
                    self.assertFalse(any(a.endswith('pi-web-integration/install.sh') for a in args))
                    if args[:2] == ['sudo', 'install']:
                        target = args[-1]
                        self.assertIn(target, copies)
                        source, mode = copies[target]
                        self.assertEqual(args, ['sudo', 'install', '-o', 'root', '-g', 'root',
                                                '-m', mode, str(pi / source), target])
                        (host / target.lstrip('/')).write_bytes(Path(args[-2]).read_bytes())
                        writes.append(target)
                    elif args[:2] == ['sudo', 'systemctl']:
                        if args[2] == 'is-active':
                            self.assertEqual(args[3], '--quiet')
                            self.assertFalse(kwargs['check'])
                            return subprocess.CompletedProcess(args, 0 if args[-1] in active_units else 3)
                        self.assertEqual(args[2], 'try-restart')
                        self.assertIn(args[-1], active_units)
                        restarts.append(args[-1])
                    return subprocess.CompletedProcess(args, 0)

                selection = {'brand': 'apporo', 'mode': 'development'}
                with patch.object(r.brands, 'prepare_source', return_value=repo), \
                        patch.object(r.brands, 'receipt_for', return_value={}), \
                        patch.object(r, 'verify_presentation') as verify, patch.object(r, 'save_json'), \
                        patch.object(r, 'run', side_effect=command) as commands, \
                        patch.object(r, 'output', return_value='--brand'):
                    r.cockpit('192.0.2.99', selection, presentation_only=True)
                self.assertCountEqual(writes, copies)
                self.assertEqual(restarts, list(active_units))
                for name, data in before.items():
                    self.assertEqual((host / name).read_bytes(), data, name)
                for destination, (source, _) in copies.items():
                    self.assertEqual((host / destination.lstrip('/')).read_bytes(), (pi / source).read_bytes())
                calls = [[str(a) for a in c.args[0]] for c in commands.call_args_list]
                self.assertFalse(any('--service-owner' in c or '/etc/cockpit/cockpit.conf' in c for c in calls))
                self.assertCountEqual([c[-1] for c in calls if c[:3] == ['sudo', 'systemctl', 'is-active']], units)
                verify.assert_called_once_with(repo, selection)

    def test_legacy_cockpit_retains_original_source_and_default_brand(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources = Path(tmp)
            repo = sources / 'Woow_cockpit'
            (repo / 'pi-web-integration').mkdir(parents=True)
            (repo / 'pi-web-integration/woowtech-piweb-gateway.service').write_text('ExecStart=/usr/bin/node gateway.mjs\n')
            with patch.object(r, 'SOURCES', sources), patch.object(r.brands, 'prepare_source') as staging, \
                    patch.object(r, 'run') as command, patch.object(r, 'output', return_value='operator'), \
                    patch.object(r, 'save_json') as receipt, patch.dict(r.os.environ, {'BRAND': 'apporo'}):
                r.cockpit('192.0.2.20', {'mode': 'legacy', 'brand': 'woowtech'})
            staging.assert_not_called()
            receipt.assert_not_called()
            self.assertFalse(any('--brand' in c.args[0] for c in command.call_args_list))
            pwa = next(c for c in command.call_args_list if any(str(a).endswith('pwa-gateway/install.sh') for a in c.args[0]))
            self.assertEqual(pwa.kwargs['env']['BRAND'], 'woowtech')

    def test_presentation_checks_reject_gateway_pwa_unit_and_brand_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, system, home, state, qdir = [root / name for name in ('repo', 'system', 'home', 'state', 'quadlet')]
            state.mkdir()
            qdir.mkdir()
            marker = system / 'etc/cockpit/branding/brand.json'
            marker.parent.mkdir(parents=True)
            marker.write_text('{"id":"apporo"}')
            copies = {'usr/local/libexec/woowtech-piweb-gateway.mjs': 'pi-web-integration/gateway.mjs',
                      'usr/local/share/cockpit/woowpiweb/index.html': 'pi-web-integration/package/index.html',
                      'usr/local/share/cockpit/woowpiweb/style.css': 'pi-web-integration/package/style.css'}
            for installed, source in copies.items():
                for p in (system / installed, repo / source):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text('locked public presentation')
            (repo / 'pwa-gateway').mkdir()
            unit = qdir / 'woow-cockpit-pwa.container'
            unit.write_text('locked unit')
            (repo / 'pwa-gateway/woow-cockpit-pwa.container').write_bytes(unit.read_bytes())
            expected = {'nginx.conf': 'locked routes', 'assets/manifest.webmanifest': 'apporo',
                        'assets/icon-192.png': 'image192', 'assets/icon-512.png': 'image512'}
            script = 'import pathlib,sys\nroot=pathlib.Path(sys.argv[-1])\n'
            script += 'for name, data in ' + repr(expected) + '.items():\n p=root/name\n p.parent.mkdir(parents=True,exist_ok=True)\n p.write_text(data)\n'
            (repo / 'pwa-gateway/render.py').write_text(script)
            pwa = home / '.local/share/woowtech-cockpit-pwa'
            for name, data in expected.items():
                p = pwa / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(data)
            with patch.object(r, 'STATE', state), patch.object(r, 'QDIR', qdir):
                r.verify_presentation(repo, {'brand': 'apporo'}, system, home)
                for path in (marker, unit, system / 'usr/local/libexec/woowtech-piweb-gateway.mjs', pwa / 'assets/icon-192.png'):
                    old = path.read_bytes()
                    path.write_text('{"id":"woowtech"}' if path == marker else 'drift')
                    with self.subTest(path=path), self.assertRaises(ValueError):
                        r.verify_presentation(repo, {'brand': 'apporo'}, system, home)
                    path.write_bytes(old)

    def test_brand_action_runs_full_runtime_verification_and_propagates_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'device.json').write_text('{}')
            selection = {'brand': 'apporo', 'mode': 'development', 'ready': True}
            with patch.object(r, 'STATE', state), patch.object(r.brands, 'select', return_value=selection), \
                    patch.object(r.brands, 'prepare_source'), patch.object(r, 'device_address', return_value='192.0.2.20'), \
                    patch.object(r, 'preflight'), patch.object(r.os, 'umask'), \
                    patch.object(r, 'cockpit') as cockpit, patch.object(r, 'verify', return_value=False) as verify, \
                    patch.object(r, 'install_apps') as apps, \
                    patch('sys.argv', ['woow-release.py', 'brand', '--brand', 'apporo', '--development', '--cockpit-source', str(state)]):
                with self.assertRaises(SystemExit) as error:
                    r.main()
            self.assertEqual(error.exception.code, 1)
            cockpit.assert_called_once_with('192.0.2.20', selection, presentation_only=True)
            verify.assert_called_once_with(selection, allow_development=True)
            apps.assert_not_called()

    def test_base_apps_resume_is_not_disabled_by_a_development_brand_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'device.json').write_text('{}')
            selection = {'brand': 'apporo', 'mode': 'pending', 'ready': False, 'reason': 'development receipt'}
            with patch.object(r, 'STATE', state), patch.object(r.brands, 'select', return_value=selection), \
                    patch.object(r, 'device_address', return_value='192.0.2.20'), \
                    patch.object(r, 'preflight'), patch.object(r.os, 'umask'), \
                    patch.object(r, 'patch_first_boot'), patch.object(r, 'configure'), \
                    patch.object(r, 'install_apps') as apps, patch.object(r, 'cockpit') as cockpit, \
                    patch('sys.argv', ['woow-release.py', 'apps']):
                r.main()
            apps.assert_called_once_with(list(r.APPS))
            cockpit.assert_not_called()

    def test_installed_brand_or_source_mismatch_cannot_pass_verification(self):
        installed = {'brand': 'woowtech', 'mode': 'production', 'commit': 'a' * 40, 'tree': 'b' * 40}
        selected = {**installed, 'brand': 'apporo'}
        with patch.object(r.brands, 'verify_receipt', return_value=(installed, Path('/unused'))), \
                patch.object(r.subprocess, 'run') as command:
            result = r.verify_brand(selected)
        self.assertFalse(result['passed'])
        command.assert_not_called()

    def test_missing_production_receipt_is_not_accepted_as_legacy_woow(self):
        with patch.object(r.brands, 'verify_receipt', return_value=(None, None)), \
                patch.object(r.subprocess, 'run') as command:
            for brand in ('woowtech', 'apporo'):
                result = r.verify_brand({'brand': brand, 'mode': 'production'})
                self.assertFalse(result['passed'])
                self.assertFalse(result['release_eligible'])
        command.assert_not_called()

    def test_runtime_failures_are_never_hidden_and_development_is_not_release_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            state = home / 'state'
            state.mkdir()
            sources = state / 'sources'
            pins = sources / 'Woow_native_os_pi_agent/lib/pins.sh'
            pins.parent.mkdir(parents=True)
            pins.write_text('PIN_NODE_VERSION=1.2.3\nPIN_CLAUDE_VERSION=1.2.3\nPIN_CODEX_VERSION=1.2.3\n')
            (state / 'native-startup-overlay.json').write_text(json.dumps({'probe_timeout_ms': 30000, 'installed_sha256': 'digest'}))
            lock = {'sources': {'Woow_native_os_pi_agent': 'a' * 40}, 'native_pi_version': '1.2.3',
                    'platform_packages': {'podman': '1'}, 'containers': {'app': {'image_id': 'b' * 64}},
                    'external_authorizations': []}
            response = Mock()
            response.__enter__ = Mock(return_value=Mock(status=200))
            response.__exit__ = Mock(return_value=False)
            for mode, correct_image, allow_dev, expected in [('production', True, False, True),
                    ('production', False, False, False), ('development', True, False, False),
                    ('development', True, True, True), ('development', False, True, False)]:
                def command(args, **kw):
                    if str(args[0]) == 'git':
                        stdout = 'a' * 40 if 'rev-parse' in args else ''
                    elif '--version' in args:
                        stdout = '1.2.3'
                    elif args[0] == 'dpkg-query':
                        stdout = '1'
                    elif args[0] == 'apt-mark':
                        stdout = 'podman'
                    elif args[0] == 'systemctl':
                        stdout = '180s' if 'show' in args else 'active'
                    elif args[0] == 'podman':
                        stdout = json.dumps([{'Name': 'app', 'Image': ('b' if correct_image else 'c') * 64,
                                              'State': {'Running': True, 'Health': {'Status': 'healthy'}}}])
                    else:
                        raise AssertionError(args)
                    return subprocess.CompletedProcess(args, 0, stdout, '')
                with self.subTest(mode=mode, image=correct_image, allow=allow_dev), \
                        patch.object(r, 'LOCK', lock), patch.object(r, 'STATE', state), patch.object(r, 'SOURCES', sources), \
                        patch.object(r.Path, 'home', return_value=home), patch.object(r.Path, 'is_file', return_value=True), \
                        patch.object(r, 'digest', return_value='digest'), patch.object(r.subprocess, 'run', side_effect=command), \
                        patch.object(r.urllib.request, 'urlopen', return_value=response), patch.object(r, 'save_json') as save, \
                        patch.object(r, 'verify_brand', return_value={'passed': True, 'mode': mode, 'release_eligible': mode == 'production'}), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(r.verify(allow_development=allow_dev), expected)
                    report = save.call_args.args[1]
                    self.assertEqual(report['runtime_passed'], correct_image)
                    self.assertEqual(report['passed'], correct_image and mode == 'production')


if __name__ == '__main__':
    unittest.main()
