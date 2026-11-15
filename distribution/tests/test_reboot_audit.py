import copy
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('reboot', Path(__file__).resolve().parents[1] / 'installer/reboot-audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class RebootAcceptance(unittest.TestCase):
    def setUp(self):
        self.container = {'Image': 'sha256:' + 'a' * 64,
                          'State': {'Running': True, 'Health': {'Status': 'healthy'}},
                          'Config': {'Env': ['PASSWORD=private'], 'Labels': {'PODMAN_SYSTEMD_UNIT': 'app.service'}},
                          'HostConfig': {'NetworkMode': 'bridge', 'PortBindings': {'80/tcp': [{'HostPort': '8080'}]}},
                          'Mounts': [{'Type': 'volume', 'Name': 'data', 'Source': '/private/data', 'Destination': '/data', 'RW': True}]}
        self.before = {'boot_id': 'before', 'host_identity_sha256': 'host', 'uid': 1000,
                       'containers': {'app': audit.record(self.container, {})},
                       'units': {'native.service': True}, 'http': {'app': 200}, 'uptime_seconds': 100}
        self.after = copy.deepcopy(self.before)
        self.after['boot_id'] = 'after'

    def test_pass_requires_real_reboot_on_same_host_and_owner(self):
        self.assertTrue(audit.compare(self.before, self.after)['passed'])
        for key, value in [('boot_id', 'before'), ('host_identity_sha256', 'different'), ('uid', 2000)]:
            bad = copy.deepcopy(self.after)
            bad[key] = value
            with self.subTest(key=key):
                self.assertFalse(audit.compare(self.before, bad)['passed'])

    def test_missing_or_extra_container_cannot_pass(self):
        for containers in [{}, {**self.after['containers'], 'other': self.after['containers']['app']}]:
            after = {**self.after, 'containers': containers}
            self.assertFalse(audit.compare(self.before, after)['passed'])

    def test_healthy_container_with_changed_persistent_configuration_fails(self):
        for key in ['image_id', 'network_mode', 'ports', 'devices', 'mounts', 'environment_sha256', 'unit']:
            after = copy.deepcopy(self.after)
            after['containers']['app'][key] = 'different'
            with self.subTest(key=key):
                result = audit.compare(self.before, after)
                self.assertFalse(result['passed'])
                self.assertEqual(result['changed_container_fields'], {'app': [key]})

    def test_native_units_http_and_health_are_independent_readiness_gates(self):
        for status in ['starting', 'unhealthy', 'unknown', None]:
            after = copy.deepcopy(self.after)
            after['containers']['app']['health'] = status
            self.assertFalse(audit.compare(self.before, after)['passed'])
        for key, value in [('units', {'native.service': False}), ('http', {'app': 503})]:
            after = {**self.after, key: value}
            self.assertFalse(audit.compare(self.before, after)['passed'])

    def test_recreated_namespace_owner_and_hostname_do_not_fake_configuration_drift(self):
        old = copy.deepcopy(self.container)
        new = copy.deepcopy(self.container)
        old['HostConfig']['NetworkMode'] = 'container:old-id'
        new['HostConfig']['NetworkMode'] = 'container:new-id'
        old['Config']['Env'].append('HOSTNAME=old-id')
        new['Config']['Env'].append('HOSTNAME=new-id')
        self.assertEqual(audit.record(old, {'old-id': 'gateway'}), audit.record(new, {'new-id': 'gateway'}))
        with self.assertRaises(RuntimeError):
            audit.record(new, {})

    def test_secret_values_and_commands_are_not_in_record(self):
        self.container['Config']['Cmd'] = ['--token', 'do-not-export']
        self.container['State']['Health']['Log'] = ['do-not-export']
        result = json.dumps(audit.record(self.container, {}))
        self.assertNotIn('PASSWORD', result)
        self.assertNotIn('do-not-export', result)
        self.assertEqual(len(audit.record(self.container, {})['environment_sha256']), 64)


if __name__ == '__main__':
    unittest.main()
