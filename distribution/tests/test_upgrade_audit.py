import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).resolve().parents[1] / 'installer/upgrade-audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ExistingDeviceAudit(unittest.TestCase):
    def test_inspect_secrets_and_commands_do_not_enter_report(self):
        source = {'Name': 'n8n', 'Image': 'sha256:' + 'a' * 64,
                  'Config': {'Env': ['PASSWORD=do-not-export'], 'Labels': None},
                  'HostConfig': {'CreateCommand': ['--password', 'do-not-export']},
                  'State': {'Running': True, 'Health': {'Status': 'healthy', 'Log': ['do-not-export']}}}
        result = audit.container_record(source, {'containers': {'n8n': {'image_id': 'b' * 64}}})
        self.assertNotIn('do-not-export', str(result))
        self.assertEqual(result['review'], 'requires-application-upgrade-review')

    def test_extra_app_is_preserved_even_if_excluded_from_fresh_profile(self):
        result = audit.container_record({'Name': 'immich_server', 'Image': 'a' * 64}, {'containers': {}})
        self.assertEqual(result['review'], 'preserve-outside-release')

    def test_pi_container_is_not_silently_adopted_as_native(self):
        result = audit.container_record({'Name': 'pi-web', 'Image': 'a' * 64}, {'containers': {}})
        self.assertEqual(result['review'], 'requires-container-to-native-migration-review')

    def test_quadlet_inline_credentials_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'app.container'
            p.write_text('[Container]\nImage=example:1\nEnvironment=PASSWORD=private\nExec=app --token private\nPublishPort=18080:80\n')
            result = audit.unit_record(p)
            self.assertNotIn('private', str(result))
            self.assertEqual(result['properties']['PublishPort'], ['18080:80'])


if __name__ == '__main__':
    unittest.main()
