import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('brands', ROOT / 'installer/brand_profile.py')
brands = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brands)


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.DEVNULL, text=True).strip()


def commit(repo):
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=Distribution test', '-c', 'user.email=test@example.invalid',
        'commit', '-qm', 'fixture')
    return git(repo, 'rev-parse', 'HEAD')


class BrandMaterialSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'distribution-repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        self.dist = self.repo / 'distribution'
        (self.dist / 'brands').mkdir(parents=True)
        (self.dist / 'brand-materials').mkdir()
        for brand in brands.BRANDS:
            (self.dist / 'brands' / (brand + '.json')).write_bytes((ROOT / 'brands' / (brand + '.json')).read_bytes())
        self.base = self.dist / 'base.json'
        self.base.write_text('{"release":"test"}\n')
        self.state = self.root / 'state'
        self.source = self.root / 'cockpit'
        self.source.mkdir()
        git(self.source, 'init', '-q')
        for file in ('scripts/manage.py', 'scripts/brand_profile.py', 'pwa-gateway/install.sh',
                     'pwa-gateway/render.py', 'pwa-gateway/woow-cockpit-pwa.container',
                     'pi-web-integration/install.sh', 'brands/woowtech/brand.json', 'brands/apporo/brand.json'):
            p = self.source / file
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('# fixture\n')
        self.source_commit = commit(self.source)
        self.tree = git(self.source, 'rev-parse', 'HEAD^{tree}')
        self.lock = self.dist / 'brand-materials/test.json'
        self.material = {'schema_version': 1, 'base_release': 'test', 'base_lock_sha256': brands.sha256(self.base),
                         'brands': list(brands.BRANDS), 'cockpit': {'repository': brands.COCKPIT_REPOSITORY,
                         'commit': self.source_commit, 'tree': self.tree, 'main_commit': self.source_commit,
                         'interface_version': 1}}
        self.lock.write_text(json.dumps(self.material))
        commit(self.repo)
        self.patcher = patch.object(brands, 'ROOT', self.dist)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def select(self, brand=None, **kw):
        return brands.select(brand, 'test', self.base, self.state, **kw)

    def test_default_woow_and_blocked_apporo_have_the_same_feature_profile(self):
        woow, apporo = self.select(), self.select('apporo')
        self.assertEqual(woow['mode'], 'legacy')
        self.assertTrue(woow['ready'])
        self.assertFalse(apporo['ready'])
        self.assertFalse(apporo['release_eligible'])
        self.assertEqual(woow['feature_profile'], apporo['feature_profile'])
        self.assertEqual(woow['base_lock_sha256'], apporo['base_lock_sha256'])
        self.assertFalse(self.state.exists())

    def test_unknown_brand_and_function_overrides_are_rejected(self):
        with self.assertRaises(ValueError):
            self.select('../apporo')
        profile = self.dist / 'brands/apporo.json'
        data = json.loads(profile.read_text())
        data['applications'] = []
        profile.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'profile fields'):
            self.select('apporo')

    def test_production_requires_committed_shared_lock_bound_to_base(self):
        for brand in brands.BRANDS:
            selected = self.select(brand, material_lock=self.lock)
            self.assertEqual(selected['commit'], self.source_commit)
            self.assertTrue(selected['release_eligible'])
        self.lock.write_text(self.lock.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'committed and unchanged'):
            self.select('apporo', material_lock=self.lock)

    def test_lock_rejects_wrong_base_repository_tree_and_brand_subset(self):
        changes = [({'base_release': 'other'}, None), ({'base_lock_sha256': '0' * 64}, None),
                   ({'brands': ['apporo']}, None), ({}, {'repository': 'https://example.invalid/repo.git'}),
                   ({}, {'commit': 'main'}), ({}, {'tree': 'latest'}), ({'applications': []}, None)]
        for top, source in changes:
            with self.subTest(top=top, source=source):
                value = copy.deepcopy(self.material)
                value.update(top)
                value['cockpit'].update(source or {})
                self.lock.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    self.select('apporo', material_lock=self.lock)

    def test_external_and_symlink_material_locks_are_rejected(self):
        external = self.root / 'outside.json'
        external.write_bytes(self.lock.read_bytes())
        link = self.dist / 'brand-materials/link.json'
        link.symlink_to(self.lock)
        for path in (external, link):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.select('apporo', material_lock=path)

    def test_local_source_requires_explicit_development_and_clean_commit(self):
        for kw in ({'local_source': self.source}, {'development': True},
                   {'local_source': self.source, 'development': True, 'material_lock': self.lock}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.select('apporo', **kw)
        selected = self.select('apporo', local_source=self.source, development=True)
        self.assertFalse(selected['release_eligible'])
        (self.source / 'uncommitted.txt').write_text('change')
        with self.assertRaisesRegex(ValueError, 'committed and clean'):
            self.select('apporo', local_source=self.source, development=True)

    def test_development_stages_a_separate_clone_and_records_exact_overlays(self):
        selected = self.select('apporo', local_source=self.source, development=True)
        staged = brands.prepare_source(self.state, selected)
        self.assertNotEqual(staged, self.source)
        original = (self.source / 'scripts/manage.py').read_bytes()
        (staged / 'scripts/manage.py').write_text('# reviewed overlay\n')
        receipt = brands.receipt_for(selected, staged, 'applied')
        self.assertEqual((self.source / 'scripts/manage.py').read_bytes(), original)
        self.assertEqual(git(self.source, 'status', '--porcelain'), '')
        (self.state / 'brand.json').write_text(json.dumps(receipt))
        verified, path = brands.verify_receipt(self.state, 'test', self.base)
        self.assertEqual(verified['mode'], 'development')
        self.assertEqual(path, staged)
        self.assertEqual(self.select()['brand'], 'apporo')
        self.assertFalse(self.select()['ready'])
        (staged / 'scripts/manage.py').write_text('# drift\n')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            brands.verify_receipt(self.state, 'test', self.base)

    def test_unapproved_source_changes_and_incomplete_receipts_fail(self):
        selected = self.select('apporo', local_source=self.source, development=True)
        staged = brands.prepare_source(self.state, selected)
        receipt = brands.receipt_for(selected, staged, 'installing')
        (self.state / 'brand.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            brands.verify_receipt(self.state, 'test', self.base)
        (staged / 'pwa-gateway/install.sh').write_text('# unreviewed\n')
        with self.assertRaisesRegex(ValueError, 'Unapproved'):
            brands.receipt_for(selected, staged, 'applied')

    def test_production_provenance_rejects_unmerged_commit_and_wrong_origin(self):
        selected = self.select('apporo', material_lock=self.lock)
        git(self.source, 'remote', 'add', 'origin', brands.COCKPIT_REPOSITORY)
        git(self.source, 'update-ref', 'refs/remotes/origin/main', self.source_commit)
        brands.source_check(self.source, selected)
        (self.source / 'new.txt').write_text('unmerged')
        unmerged = commit(self.source)
        bad = {**selected, 'commit': unmerged, 'tree': git(self.source, 'rev-parse', 'HEAD^{tree}')}
        with self.assertRaisesRegex(ValueError, 'provenance'):
            brands.source_check(self.source, bad)
        git(self.source, 'checkout', '--detach', self.source_commit)
        git(self.source, 'remote', 'set-url', 'origin', 'https://example.invalid/repo.git')
        with self.assertRaisesRegex(ValueError, 'origin'):
            brands.source_check(self.source, selected)

    def test_bad_receipt_fails_closed(self):
        self.state.mkdir()
        (self.state / 'brand.json').write_text('{"brand":"apporo"}')
        with self.assertRaises(ValueError):
            self.select()


if __name__ == '__main__':
    unittest.main()
