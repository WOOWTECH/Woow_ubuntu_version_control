import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', ROOT / 'installer/woow-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseSafety(unittest.TestCase):
    def test_lock_has_immutable_sources_and_images(self):
        for commit in release.LOCK['sources'].values():
            self.assertRegex(commit, r'^[a-f0-9]{40}$')
        for ident, image in release.LOCK['images'].items():
            self.assertRegex(ident, r'^[a-f0-9]{64}$')
            self.assertEqual('sha256:' + ident, image['id'])
            if not image['private_material']:
                self.assertRegex(image['reference'], r'@sha256:[a-f0-9]{64}$')
        for name in release.LOCK['containers']:
            self.assertNotRegex(name, r'immich|soak|test|rollback')
            container = release.LOCK['containers'][name]
            image = release.LOCK['images'][container['image_id']]
            self.assertEqual(container['image'], image['deployment_reference'])

    def test_existing_quadlets_are_never_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp) / 'quadlet'
            q.mkdir()
            (q / 'important.container').write_text('keep this')
            with patch.object(release, 'STATE', Path(tmp) / 'state'), patch.object(release, 'QDIR', q), patch.object(release.shutil, 'disk_usage') as space, patch.object(release.os, 'getuid', return_value=1000):
                space.return_value.free = 100 * 1024**3
                with self.assertRaisesRegex(SystemExit, 'Existing Quadlets'):
                    release.preflight()
            self.assertEqual((q / 'important.container').read_text(), 'keep this')

    def test_resume_keeps_device_settings_and_passwords(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = home / '.config/n8n/n8n.env'
            env.parent.mkdir(parents=True)
            env.write_text('HOST_PORT=12345\n')
            with patch.object(release.Path, 'home', return_value=home):
                release.set_config('n8n', {'HOST_PORT': 15678})
            self.assertEqual(env.read_text(), 'HOST_PORT=12345\n')

    def test_private_material_path_cannot_escape(self):
        ident = 'a' * 64
        with tempfile.TemporaryDirectory() as tmp:
            material = Path(tmp)
            (material / 'materials.json').write_text(json.dumps({'release': release.RELEASE, 'images': {ident: {'file': '../outside', 'sha256': 'bad'}}}))
            lock = {'images': {ident: {'private_material': True}}}
            with patch.object(release, 'LOCK', lock), patch.object(release, 'image_exists', return_value=False), patch.object(release, 'run') as command:
                with self.assertRaisesRegex(SystemExit, 'checksum/path'):
                    release.import_images(material)
                command.assert_not_called()

    def test_credentials_are_written_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'device.json'
            release.save_json(dest, {'device_id': 'new'})
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)

    def test_ingress_rejects_loopback_and_url(self):
        for address in ['localhost', '127.0.0.1', '0.0.0.0', 'https://192.0.2.1']:
            with self.subTest(address=address), self.assertRaises(SystemExit):
                release.device_address(address)
        self.assertEqual(release.device_address('192.0.2.10'), '192.0.2.10')


if __name__ == '__main__':
    unittest.main()
