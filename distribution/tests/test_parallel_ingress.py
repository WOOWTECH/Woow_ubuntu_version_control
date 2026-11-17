import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('parallel_ingress', ROOT / 'installer/parallel-ingress.py')
ingress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingress)


class ParallelIngressBoundary(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.release_state = self.root / 'release'
        self.release_state.mkdir()
        self.state = self.release_state / 'parallel-ingress'
        # A malformed primary receipt deliberately proves this flow never reads it.
        self.primary = self.release_state / 'brand.json'
        self.primary.write_bytes(b'primary receipt belongs to the global brand installer\n')
        self.original = self.primary.read_bytes()
        self.repo = self.root / 'staged-cockpit'
        self.manager = self.repo / 'parallel-ingress/manage.py'
        self.manager.parent.mkdir(parents=True)
        self.manager.write_text('# fixture; never executed\n')
        for target, value in ((ingress, ('STATE', self.state)), (ingress.os, ('getuid', lambda: 1000))):
            patcher = patch.object(target, *value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cli(self, *args):
        with patch('sys.argv', ['parallel-ingress.py', *args]):
            return ingress.main()

    def test_plan_reads_only_committed_material_and_never_creates_state(self):
        real_run = subprocess.run
        profile = ingress.brands.profile('apporo')

        def read_only(args, **kwargs):
            self.assertEqual(args, ['git', '-C', str(ROOT.parent), 'show',
                                    'HEAD:distribution/brand-materials/' + profile['material_lock']])
            return real_run(args, **kwargs)

        out = io.StringIO()
        with patch.object(ingress.subprocess, 'run', side_effect=read_only) as command, \
                patch.object(ingress.brands, 'prepare_source') as stage, contextlib.redirect_stdout(out):
            self.assertEqual(self.run_cli('plan'), 0)
        plan = json.loads(out.getvalue())
        self.assertEqual(plan['scope'], 'source-selection')
        self.assertEqual(plan['release'], ingress.RELEASE)
        self.assertEqual(plan['source']['mode'], 'production')
        self.assertEqual(plan['source']['material_lock'], profile['material_lock'])
        self.assertFalse(plan['instance_validated'])
        self.assertFalse(plan['runtime_verified'])
        self.assertFalse(self.state.exists())
        self.assertEqual(self.primary.read_bytes(), self.original)
        self.assertEqual(command.call_count, 1)
        stage.assert_not_called()

    def test_install_verify_and_rollback_only_delegate_to_the_verified_source(self):
        selection = ingress.select_source()
        for action, extra in (('install', ['--config', '/etc/cockpit/parallel-ingress-config/apporo.json']),
                              ('verify', ['--instance', 'apporo']), ('rollback', ['--instance', 'apporo'])):
            with self.subTest(action=action), \
                    patch.object(ingress, 'select_source', return_value=selection), \
                    patch.object(ingress.brands, 'prepare_source', return_value=self.repo) as stage, \
                    patch.object(ingress.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as command:
                self.assertEqual(self.run_cli(action, *extra), 0)
                stage.assert_called_once_with(self.state, selection)
                command.assert_called_once_with(['sudo', 'env', 'PYTHONDONTWRITEBYTECODE=1', 'python3',
                                                 str(self.manager), action, *extra], check=False)
            self.assertEqual(self.primary.read_bytes(), self.original)
            self.assertFalse((self.state / 'brand.json').exists())
            self.assertFalse((self.release_state / 'device.json').exists())

    def test_config_is_passed_as_a_path_without_loading_or_rewriting_it(self):
        config = self.root / 'root-owned instance.json'
        config.write_bytes(b'upstream owns the schema and validation, even for invalid JSON\n')
        original = config.read_bytes()
        selection = ingress.select_source()
        with patch.object(ingress, 'select_source', return_value=selection), \
                patch.object(ingress.brands, 'prepare_source', return_value=self.repo), \
                patch.object(ingress.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2)) as command:
            self.assertEqual(self.run_cli('install', '--config', str(config)), 2)
        self.assertEqual(command.call_args.args[0][-2:], ['--config', str(config)])
        self.assertEqual(config.read_bytes(), original)
        self.assertEqual(self.primary.read_bytes(), self.original)

    def test_invalid_arguments_stop_before_source_selection_and_staging(self):
        for args in (('install',), ('install', '--config', 'relative.json'), ('verify',), ('rollback',),
                     ('plan', '--config', '/etc/instance.json'), ('brand', '--brand', 'apporo'),
                     ('install', '--config', '/etc/instance.json', '--development')):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), \
                    patch.object(ingress, 'select_source') as select, \
                    patch.object(ingress.brands, 'prepare_source') as stage, self.assertRaises(SystemExit):
                self.run_cli(*args)
            select.assert_not_called()
            stage.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_nonproduction_selection_is_rejected(self):
        for mode, ready, eligible in (('development', True, False), ('pending', False, False),
                                      ('legacy', True, True), ('production', False, True)):
            with self.subTest(mode=mode), patch.object(ingress.brands, 'select',
                    return_value={'mode': mode, 'ready': ready, 'release_eligible': eligible}), \
                    self.assertRaisesRegex(ValueError, 'production Cockpit material lock'):
                ingress.select_source()
        self.assertFalse(self.state.exists())

    def test_missing_or_symlink_manager_never_runs_sudo(self):
        selection = ingress.select_source()
        self.manager.unlink()
        for symlink in (False, True):
            if symlink:
                external = self.root / 'unverified.py'
                external.write_text('unverified source')
                self.manager.symlink_to(external)
            with self.subTest(symlink=symlink), \
                    patch.object(ingress.brands, 'prepare_source', return_value=self.repo), \
                    patch.object(ingress.subprocess, 'run') as command, \
                    self.assertRaisesRegex(ValueError, 'reviewed material update'):
                ingress.delegate('install', selection, Path('/etc/instance.json'))
            command.assert_not_called()

    def test_source_drift_stops_before_root_installer(self):
        selection = ingress.select_source()
        with patch.object(ingress.brands, 'prepare_source', side_effect=ValueError('Unexpected Cockpit source drift')), \
                patch.object(ingress.subprocess, 'run') as command, self.assertRaisesRegex(ValueError, 'source drift'):
            ingress.delegate('install', selection, Path('/etc/instance.json'))
        command.assert_not_called()
        self.assertEqual(self.primary.read_bytes(), self.original)

    def test_root_wrapper_and_concurrent_commands_stop_before_staging(self):
        selection = ingress.select_source()
        with patch.object(ingress.os, 'getuid', return_value=0), \
                patch.object(ingress.brands, 'prepare_source') as stage, self.assertRaisesRegex(ValueError, 'deployment owner'):
            ingress.delegate('verify', selection, instance='apporo')
        stage.assert_not_called()
        self.assertFalse(self.state.exists())
        with patch.object(ingress.fcntl, 'flock', side_effect=BlockingIOError), \
                patch.object(ingress.brands, 'prepare_source') as stage, self.assertRaisesRegex(ValueError, 'Another parallel'):
            ingress.delegate('verify', selection, instance='apporo')
        stage.assert_not_called()

    def test_source_lock_symlink_cannot_truncate_primary_receipt(self):
        selection = ingress.select_source()
        self.state.mkdir()
        (self.state / 'source.lock').symlink_to(self.primary)
        with patch.object(ingress.brands, 'prepare_source', return_value=self.repo) as stage, \
                patch.object(ingress.subprocess, 'run') as command, self.assertRaises(OSError):
            ingress.delegate('verify', selection, instance='apporo')
        stage.assert_not_called()
        command.assert_not_called()
        self.assertEqual(self.primary.read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()
