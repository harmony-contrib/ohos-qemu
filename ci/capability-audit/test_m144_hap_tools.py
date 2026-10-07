"""Locked host tool boundary checks, not actual HAP or guest acceptance."""
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_m144_release_hap_cache as cache
import prepare_m144_hap_tools as tools
from test_access_token_kernel import patch_sections, write_preimages


class M144HapToolsTests(unittest.TestCase):
    def test_real_lock_covers_release_archive_paired_tools_and_component_patch(self):
        expected = cache.recipe(ROOT)
        self.assertEqual(len(expected['inputs_sha256']), 1)
        self.assertEqual(expected['lock']['hvigor_version'], '6.0.0-release-patch-rc.2')
        self.assertEqual(expected['lock']['sdkmanager_version'], '2.26.2')
        self.assertEqual(expected['lock']['project_model_version'], '6.0.0')
        self.assertEqual(expected['lock']['archive_sha256'],
                         '83e45209c65662bbeab81d36d691807bf8db56d94d7d15c959600dcc348814c3')

    def test_changed_archive_version_registry_or_missing_component_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'scripts/m144_hap_tools', root / 'scripts/m144_hap_tools')
            lock = root / cache.LOCK
            original = json.loads(lock.read_text())
            for kind in ('hvigor_version', 'sdkmanager_version', 'archive_sha256', 'archive_url', 'project_model_version'):
                document = json.loads(json.dumps(original))
                document[kind] = 'master'
                lock.write_text(json.dumps(document))
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    cache.recipe(root)

    def fixture(self, root):
        expected = cache.recipe(ROOT)
        roles = {'hvigor': expected['lock']['hvigor_version'],
                 'hvigor-ohos-plugin': expected['lock']['hvigor_version'],
                 'hvigor-ohos-plugin/node_modules/@ohos/sdkmanager-common': expected['lock']['sdkmanager_version']}
        for role, version in roles.items():
            target = root / 'hvigor' / role
            target.mkdir(parents=True)
            (target / 'package.json').write_text(json.dumps({'version': version}))
        (root / 'hvigor/fixture.txt').write_text('synthetic cache boundary only')
        record = {'status': 'pass', **cache.recipe(ROOT), 'installed_tree_sha256': cache.tree_digest(root),
                  'official_tool_code_modified': False}
        (root / 'cache-evidence.json').write_text(json.dumps(record))
        return record

    def test_tree_content_mode_and_escaping_alias_are_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'cache'
            self.fixture(root)
            cache.verify(root, cache.recipe(ROOT))
            leaf = root / 'hvigor/fixture.txt'
            leaf.chmod(0o755)
            with self.assertRaisesRegex(ValueError, 'content changed'):
                cache.verify(root, cache.recipe(ROOT))
            leaf.chmod(0o644)
            leaf.write_text('drift')
            with self.assertRaisesRegex(ValueError, 'content changed'):
                cache.verify(root, cache.recipe(ROOT))
            (root / 'hvigor/outside').symlink_to(Path(directory) / 'outside')
            with self.assertRaisesRegex(ValueError, 'escapes'):
                cache.tree_digest(root)

    def test_seed_preserves_home_configuration_and_exact_wrapper_cache_key(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = base / 'cache'; self.fixture(root)
            home = base / 'home'; home.mkdir(); project = base / 'project'; project.mkdir()
            npmrc = home / '.npmrc'; npmrc.write_text('existing private config preserved')
            with patch.object(tools.os, 'statvfs', return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
                result = tools.seed(root, ROOT, project, home)
                self.assertEqual(npmrc.read_text(), 'existing private config preserved')
                self.assertTrue(result['official_wrapper_unchanged'])
                self.assertFalse(result['dependency_network_required'])
                destination = home / '.hvigor/project_caches' / result['project_cache_key'] / 'workspace'
                for role in ('hvigor', 'hvigor-ohos-plugin'):
                    self.assertEqual((destination / 'node_modules/@ohos' / role).resolve(),
                                     (root / 'hvigor' / role).resolve())
                with self.assertRaisesRegex(ValueError, 'overwrite'):
                    tools.seed(root, ROOT, project, home)

    def test_seed_rejects_writable_cache_and_redirected_home_ancestors(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); root = base / 'cache'; self.fixture(root)
            home = base / 'home'; home.mkdir(); project = base / 'project'; project.mkdir()
            with self.assertRaisesRegex(ValueError, 'read-only'):
                tools.seed(root, ROOT, project, home)
            foreign = base / 'foreign'; foreign.mkdir(); (home / '.hvigor').symlink_to(foreign)
            with patch.object(tools.os, 'statvfs', return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
                with self.assertRaisesRegex(ValueError, 'ancestor'):
                    tools.seed(root, ROOT, project, home)
            self.assertEqual(list(foreign.iterdir()), [])

    def test_actual_parser_preflight_requires_every_valid_and_invalid_boundary(self):
        rows = [{'value': value, 'expected': wanted, 'accepted': wanted}
                for value, wanted in tools.VERSION_CASES]
        for kind in ('complete', 'missing', 'unexpected_accept', 'bad_json', 'process_failure'):
            data = json.loads(json.dumps(rows))
            if kind == 'missing':
                data.pop()
            elif kind == 'unexpected_accept':
                data[-1]['accepted'] = True
            result = SimpleNamespace(returncode=9 if kind == 'process_failure' else 0,
                stdout=b'bad json' if kind == 'bad_json' else json.dumps(data).encode(), stderr=b'')
            with self.subTest(kind=kind), patch.object(tools.subprocess, 'run', return_value=result):
                checked = tools.sdk_version_check(Path('/owned/cache'), Path('/pinned/node'))
            self.assertEqual(checked['status'], 'pass' if kind == 'complete' else 'fail')

    def test_hap_environment_retains_proxy_home_and_offline_without_mutating_parent(self):
        component = ROOT / 'patches/common/web/arkweb/m144_core_package'
        source_patch = component / '0004-preserve-host-network-environment-for-hap-tools.patch'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); write_preimages(root, (source_patch,))
            subprocess.run(['git', '-C', str(root), 'apply', str(source_patch)], check=True)
            text = (root / 'src/arkweb/build/hap/build_hap_rk.py').read_text()
            body = text.split('    self.env = os.environ.copy()\n', 1)[1].split('\n  def WriteDepfile', 1)[0]
            body = '\n'.join(line for line in body.splitlines() if not line.startswith('// fixture filler'))
            namespace = {'os': os, 'self': SimpleNamespace(sdk='sdk26', node='full-node')}
            with patch.dict(os.environ, {'HOME': '/same-original-home', 'PATH': '/original-path',
                                        'HTTPS_PROXY': 'fixture-proxy', 'npm_config_offline': 'true'}, clear=True):
                exec('self.env = os.environ.copy()\n' + textwrap.dedent(body), namespace)
                self.assertEqual(namespace['self'].env['HOME'], '/same-original-home')
                self.assertEqual(namespace['self'].env['HTTPS_PROXY'], 'fixture-proxy')
                self.assertEqual(namespace['self'].env['npm_config_offline'], 'true')
                self.assertEqual(os.environ['PATH'], '/original-path')

    def test_build_recipe_requires_preflight_before_native_or_hap_and_does_not_replace_chromium_node(self):
        frontend = (ROOT / 'scripts/run_m144_release_build_docker.sh').read_text()
        self.assertLess(frontend.index('prepare_m144_release_hap_cache.py'), frontend.index('docker run --rm'))
        self.assertLess(frontend.index('prepare_m144_hap_tools.py'), frontend.index('native) bash'))
        self.assertIn('--preflight', frontend)
        self.assertIn('dst=/m144-hap-tools,readonly', frontend)
        gn_patch = ROOT / 'patches/common/web/arkweb/m144_core_package/0005-use-full-release-node-for-hap-and-har-tools.patch'
        self.assertEqual(set(patch_sections(gn_patch)), {'src/arkweb/build/hap/hap.gni'})
        self.assertEqual(gn_patch.read_text().count('+      rebase_path("//ohos_sdk/nodejs/"'), 2)
        self.assertNotIn('export HOME=', (ROOT / 'scripts/prepare_m144_hap_tools.py').read_text())
        paired = ROOT / 'patches/common/web/arkweb/m144_core_package/0007-use-fixed-release-hvigor-without-project-downloaders.patch'
        self.assertNotIn('build-profile.json5', paired.read_text())
        self.assertIn('${OHOS_BASE_SDK_HOME}/hvigor/bin/hvigorw.js', paired.read_text())


if __name__ == '__main__':
    unittest.main()
