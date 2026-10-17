"""Actual pinned contexts grammar and exact previous component migrations."""
import ast
from collections import defaultdict
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_qemu_sensor_runtime as SENSOR
import prepare_qemu_gnss_runtime as GNSS

PREVIOUS = {
    SENSOR: '# SPDX-License-Identifier: Apache-2.0\n'
        '/dev/unix/socket/qemu_sensor          -d u:object_r:qemu_sensor_input_dir:s0\n'
        '/dev/unix/socket/qemu_sensor/input    -s u:object_r:qemu_sensor_input_socket:s0\n',
    GNSS: '# SPDX-License-Identifier: Apache-2.0\n'
        '/dev/unix/socket/qemu_gnss          -d u:object_r:qemu_gnss_input_dir:s0\n'
        '/dev/unix/socket/qemu_gnss/input    -s u:object_r:qemu_gnss_input_socket:s0\n',
}
FIX = ROOT / 'ci/capability-audit/fixtures/selinux_contexts_compatibility'
PINNED_CHECKER_SHA256 = '17d9b8aca5860338759434dbc04bb62c8be27fcc736f0c2a2a3a72a0b423b018'
VPN = ROOT / 'patches/common/foundation/communication/netmanager_ext/openvpn_backend/files/qemu_openvpn_file_contexts'


def contexts_key(module):
    return next(name for name in module.FILES if name.endswith('/file_contexts'))


def snapshot(root):
    return {str(p.relative_to(root)): ('alias', str(p.readlink())) if p.is_symlink()
            else ('file', p.read_bytes()) for p in root.rglob('*') if p.is_symlink() or p.is_file()}


class ContextCompatibilityTests(unittest.TestCase):
    def root(self, temporary, module):
        root = Path(temporary) / module.__name__
        build = root / module.BUILD
        build.parent.mkdir(parents=True)
        fixture = ('gnss_runtime/BUILD.gn' if module is GNSS else 'core/qemu_sensor/BUILD.gn')
        build.write_bytes((ROOT / 'ci/capability-audit/fixtures' / fixture).read_bytes())
        return root

    def previous(self, root, module, format_fixed=False):
        module.apply(root)
        types = root / (module.POLICY + 'public/types.te')
        types.write_text(types.read_text().replace(', system_sock_domain;', ';'))
        if not format_fixed:
            (root / contexts_key(module)).write_text(PREVIOUS[module])
        self.assertEqual({n: hashlib.sha256((root / n).read_bytes()).hexdigest()
                          for n in module.FILES}, module.FORMAT_FIXED_FILES_SHA256
                         if format_fixed else module.LEGACY_FILES_SHA256)

    def checker(self):
        source = (FIX / 'build_contexts.py').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), PINNED_CHECKER_SHA256)
        metadata = json.loads((FIX / 'source.json').read_text())
        self.assertEqual(metadata['source_commit'], 'cfc1d5b31a7438dbc87763f9222f00337221cf21')
        self.assertEqual(metadata['sha256'], PINNED_CHECKER_SHA256)
        node = next(n for n in ast.parse(source).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'check_redefinition')
        namespace = {'re': re, 'defaultdict': defaultdict}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(FIX / 'build_contexts.py'), 'exec'), namespace)
        return namespace['check_redefinition']

    def test_actual_pinned_validator_rejects_old_six_rules_and_accepts_new_payloads(self):
        validate = self.checker()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'file_contexts'
            old_vpn = VPN.read_text().replace('          u:object_r:qemu_openvpn_control_socket',
                '          -s u:object_r:qemu_openvpn_control_socket').replace(
                '    u:object_r:qemu_openvpn_tunfd_socket', '    -s u:object_r:qemu_openvpn_tunfd_socket')
            path.write_text(''.join(PREVIOUS.values()) + old_vpn)
            log = io.StringIO()
            with contextlib.redirect_stdout(log), self.assertRaises(Exception):
                validate(str(path))
            self.assertEqual(log.getvalue().count(' format check fail'), 6)
            path.write_text(''.join(m.FILES[contexts_key(m)] for m in PREVIOUS) + VPN.read_text())
            validate(str(path))

    def test_exact_previous_complete_install_upgrades_and_replays(self):
        for module in PREVIOUS:
            for format_fixed in (False, True):
                with self.subTest(module=module.__name__, format_fixed=format_fixed), tempfile.TemporaryDirectory() as temporary:
                    root = self.root(temporary, module)
                    self.previous(root, module, format_fixed)
                    before = snapshot(root)
                    result = module.apply(root)
                    self.assertTrue(result['upgraded_known_previous'])
                    after = snapshot(root)
                    changed = {module.POLICY + 'public/types.te'}
                    if not format_fixed:
                        changed.add(contexts_key(module))
                    self.assertEqual({n for n in before if before[n] != after[n]}, changed)
                    self.assertFalse(module.apply(root)['upgraded_known_previous'])
                    self.assertEqual(snapshot(root), after)

    def test_each_changed_previous_member_is_preserved_before_any_upgrade(self):
        for module in PREVIOUS:
            for name in module.FILES:
                with self.subTest(module=module.__name__, name=name), tempfile.TemporaryDirectory() as temporary:
                    root = self.root(temporary, module)
                    self.previous(root, module)
                    path = root / name
                    path.write_bytes(path.read_bytes() + b'unknown caller bytes\n')
                    before = snapshot(root)
                    with self.assertRaises(ValueError):
                        module.apply(root)
                    self.assertEqual(snapshot(root), before)

    def test_missing_previous_member_is_not_a_complete_upgrade(self):
        for module in PREVIOUS:
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as temporary:
                root = self.root(temporary, module)
                self.previous(root, module)
                (root / next(iter(module.FILES))).unlink()
                before = snapshot(root)
                with self.assertRaises(ValueError):
                    module.apply(root)
                self.assertEqual(snapshot(root), before)

    def test_previous_context_alias_never_writes_its_target(self):
        for module in PREVIOUS:
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as temporary:
                root = self.root(temporary, module)
                self.previous(root, module)
                path = root / contexts_key(module)
                target = Path(temporary) / 'outside'
                target.write_bytes(path.read_bytes())
                path.unlink()
                path.symlink_to(target)
                before = snapshot(root)
                with self.assertRaises(ValueError):
                    module.apply(root)
                self.assertEqual(snapshot(root), before)
                self.assertEqual(target.read_text(), PREVIOUS[module])

    def test_sensor_previous_upgrade_preserves_complete_shared_knowledge_blocks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.root(temporary, SENSOR)
            self.previous(root, SENSOR)
            build = root / SENSOR.BUILD
            anchor = b'group("product_etc_conf") {\n  deps = [\n'
            value = build.read_bytes()
            for block, dependency in SENSOR.KNOWLEDGE_GN:
                value = value.replace(anchor, block.encode() + anchor + dependency.encode())
            build.write_bytes(value)
            self.assertTrue(SENSOR.apply(root)['upgraded_known_previous'])
            for block, dependency in SENSOR.KNOWLEDGE_GN:
                self.assertEqual(build.read_bytes().count(block.encode()), 1)
                self.assertEqual(build.read_bytes().count(dependency.encode()), 1)
            self.assertFalse(SENSOR.apply(root)['upgraded_known_previous'])

    def test_context_paths_and_labels_remain_identical(self):
        for module in PREVIOUS:
            old = [line.split() for line in PREVIOUS[module].splitlines() if line and not line.startswith('#')]
            new = [line.split() for line in module.FILES[contexts_key(module)].splitlines() if line and not line.startswith('#')]
            self.assertEqual([(r[0], r[-1]) for r in old], [(r[0], r[-1]) for r in new])
            self.assertTrue(all(len(row) == 2 for row in new))


if __name__ == '__main__':
    unittest.main()
