"""Reject stale/mixed packaging proofs; no fixture claims guest acceptance."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('vpn_image', ROOT / 'scripts/verify_openvpn_backend_image.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class OpenVpnImageTests(unittest.TestCase):
    def fixture(self, directory):
        lock_path = ROOT / 'scripts/openvpn_source_lock.json'
        lock = json.loads(lock_path.read_text())
        main_path = ROOT / 'scripts/openharmony_7_0_release_source_lock.json'
        projects = json.loads(main_path.read_text())['projects']
        commands = []
        for name in M.LOGS:
            (directory / name).write_bytes(b'unit fixture command\n')
            commands.append({'log': name, 'exit_code': 0, 'sha256': M.digest(directory / name)})
        return {'schema_version': 2, 'component': 'fixed source OpenVPN for QEMU OHOS',
                'status': 'pass_source_build_ONLY_NOT_packaged_or_runtime', 'product': 'arm64_virt',
                'recipe': M.recipe_identity(), 'product_build': True,
                'source_lock_sha256': M.digest(lock_path), 'source_archive_sha256': lock['archive_sha256'],
                'source_commit': lock['commit'], 'runtime_gate_passed': False,
                'first_artifact_behavior_gate_passed': False, 'commands': commands,
                'main_source': {'source_lock_sha256': M.digest(main_path), 'checked_projects': len(projects),
                                'projects': [{**p, 'observed_head': p['revision']} for p in projects]}}

    def test_reject_standalone_stale_recipe_and_runtime_claims(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            build = self.fixture(directory)
            path = directory / 'build-evidence.json'
            path.write_text(json.dumps(build))
            self.assertEqual(M.check_build(directory, 'arm64_virt'), build)
            for changes in ({'product_build': False}, {'recipe': {}}, {'product': 'x86_64_virt'},
                            {'source_archive_sha256': '0' * 64}, {'runtime_gate_passed': True},
                            {'first_artifact_behavior_gate_passed': True}):
                path.write_text(json.dumps({**build, **changes}))
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    M.check_build(directory, 'arm64_virt')

    def test_all_commands_and_actual_main_project_heads_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            build = self.fixture(directory)
            path = directory / 'build-evidence.json'
            for mutate in ('missing-command', 'failed-command', 'project-head'):
                changed = copy.deepcopy(build)
                if mutate == 'missing-command':
                    changed['commands'].pop()
                elif mutate == 'failed-command':
                    changed['commands'][4]['exit_code'] = 1
                else:
                    changed['main_source']['projects'][0]['observed_head'] = '0' * 40
                path.write_text(json.dumps(changed))
                with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                    M.check_build(directory, 'arm64_virt')
            path.write_text(json.dumps(build))
            (directory / M.LOGS[3]).write_text('changed configure output')
            with self.assertRaisesRegex(ValueError, 'changed or failed'):
                M.check_build(directory, 'arm64_virt')

    def test_symlink_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            build = self.fixture(directory)
            path = directory / 'build-evidence.json'
            path.write_text(json.dumps(build))
            log = directory / M.LOGS[0]
            log.rename(directory / 'external.log')
            log.symlink_to(directory / 'external.log')
            with self.assertRaisesRegex(ValueError, 'regular'):
                M.check_build(directory, 'arm64_virt')

    def test_inventory_requires_all_programs_configs_licenses_and_source_binary(self):
        inventory = {name: {'sha256': 'a' * 64, 'size': 4096,
                           **({'elf_machine': 183} if name.startswith('bin/') else {})}
                     for name in M.IMAGE_FILES}
        build = {'binary_sha256': 'b' * 64}
        with self.assertRaisesRegex(ValueError, 'actual source build'):
            M.check_inventory(inventory, build, 'arm64_virt', Path('unused'))
        for name in M.IMAGE_FILES:
            missing = dict(inventory)
            del missing[name]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'all three'):
                M.check_inventory(missing, build, 'arm64_virt', Path('unused'))


if __name__ == '__main__':
    unittest.main()
