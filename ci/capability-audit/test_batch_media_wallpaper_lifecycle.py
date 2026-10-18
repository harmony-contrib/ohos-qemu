"""Exact installer and real proposed C++ controller with explicit host doubles.

Root executes in its batch. These tests neither boot QEMU nor prove API effects.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/base/theme/wallpaper_mgr/qemu_renderer'
FIXTURE = ROOT / 'ci/capability-audit/fixtures/batch_media/wallpaper_lifecycle'
PROJECT = 'base/theme/wallpaper_mgr'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


class RendererLifecycle(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='qemu-renderer-host-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.apply = module('wallpaper_component_apply', COMPONENT / 'apply.py')
        self.guard = self.apply.guard
        shutil.copytree(COMPONENT / 'lifecycle/preimage', self.root / PROJECT)

    def inventory(self):
        return {p.relative_to(self.root).as_posix(): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
                for p in self.root.rglob('*') if p.is_file()}

    def pristine(self):
        old = ROOT / 'ci/capability-audit/fixtures/batch_media/wallpaper_settings/before' / PROJECT
        for name in ('services/BUILD.gn', 'services/src/wallpaper_service.cpp'):
            shutil.copy2(old / name, self.root / PROJECT / name)

    def test_exact_E_and_pristine_upgrade_are_complete_and_idempotent(self):
        for pristine in (False, True):
            with self.subTest(pristine=pristine):
                shutil.rmtree(self.root / PROJECT)
                shutil.copytree(COMPONENT / 'lifecycle/preimage', self.root / PROJECT)
                if pristine: self.pristine()
                self.assertEqual('pristine' if pristine else 'E', self.guard.state(self.root))
                self.apply.apply(self.root)
                self.assertEqual('F', self.guard.state(self.root, require_patched=True))
                before = self.inventory(); self.apply.apply(self.root); self.assertEqual(before, self.inventory())

    def test_unknown_partial_and_alias_states_preserve_every_file(self):
        target = self.root / PROJECT / 'services/src/wallpaper_service.cpp'
        original = target.read_bytes()
        for kind in ('unknown', 'mixed', 'symlink', 'hardlink'):
            with self.subTest(kind=kind):
                target.unlink(missing_ok=True); target.write_bytes(original)
                if kind == 'unknown': target.write_bytes(original + b'// external\n')
                elif kind == 'mixed':
                    target.write_bytes((ROOT / 'ci/capability-audit/fixtures/batch_media/wallpaper_settings/before' /
                                       PROJECT / 'services/src/wallpaper_service.cpp').read_bytes())
                else:
                    other = self.root / ('outside-' + kind); other.write_bytes(original); target.unlink()
                    if kind == 'symlink': target.symlink_to(other)
                    else: os.link(other, target)
                before = target.read_bytes()
                with self.assertRaises(ValueError): self.apply.apply(self.root)
                self.assertEqual(before, target.read_bytes())

    def test_second_write_failure_rolls_back_only_transaction_bytes_and_modes(self):
        target = self.root / PROJECT / 'services/src/wallpaper_service.cpp'; target.chmod(0o640)
        before = self.inventory(); original = self.apply.atomic; writes = []
        def fail(path, data, mode):
            writes.append(path)
            if len(writes) == 2: raise OSError('injected second write failure')
            original(path, data, mode)
        with patch.object(self.apply, 'atomic', fail), self.assertRaisesRegex(OSError, 'second write'):
            self.apply.apply(self.root)
        self.assertEqual(before, self.inventory())

    def test_preflight_chmod_or_same_bytes_alias_is_not_overwritten(self):
        for kind in ('chmod', 'hardlink', 'symlink'):
            with self.subTest(kind=kind):
                shutil.rmtree(self.root / PROJECT); shutil.copytree(COMPONENT / 'lifecycle/preimage', self.root / PROJECT)
                target = self.root / PROJECT / 'services/src/wallpaper_service.cpp'
                original = self.apply.snapshot; changed = False
                def race(root, names):
                    nonlocal changed
                    result = original(root, names)
                    if not changed:
                        changed = True
                        if kind == 'chmod': target.chmod(0o600)
                        else:
                            outside = self.root / ('preflight-' + kind); outside.write_bytes(target.read_bytes()); target.unlink()
                            if kind == 'hardlink': os.link(outside, target)
                            else: target.symlink_to(outside)
                    return result
                with patch.object(self.apply, 'snapshot', race), self.assertRaises(ValueError): self.apply.apply(self.root)
                if kind == 'chmod': self.assertEqual(0o600, stat.S_IMODE(target.stat().st_mode))
                elif kind == 'symlink': self.assertTrue(target.is_symlink())
                else: self.assertEqual(2, target.stat().st_nlink)

    def test_unwritten_external_edit_is_preserved_after_own_write_rollback(self):
        target = self.root / PROJECT / 'services/src/wallpaper_service.cpp'
        first = self.root / PROJECT / 'services/BUILD.gn'; before = first.read_bytes()
        original = self.apply.atomic; raced = False
        def race(path, data, mode):
            nonlocal raced
            original(path, data, mode)
            if not raced:
                raced = True; target.write_bytes(b'external replacement after first write\n'); target.chmod(0o600)
        with patch.object(self.apply, 'atomic', race), self.assertRaises(ValueError): self.apply.apply(self.root)
        self.assertEqual(before, first.read_bytes())
        self.assertEqual(b'external replacement after first write\n', target.read_bytes())
        self.assertEqual(0o600, stat.S_IMODE(target.stat().st_mode))

    def test_product_recovery_only_after_real_desktop_persistence(self):
        source = (COMPONENT / 'lifecycle/postimage/services/src/wallpaper_service.cpp').read_text()
        start = source.index('bool WallpaperService::SendWallpaperChangeEvent(')
        guard = source.index('if (wallpaperType == WALLPAPER_SYSTEM &&', start)
        request = source.index('RequestQemuRenderer(userId);', guard)
        self.assertLess(source.index('GetWallpaperSafeLocked(userId, wallpaperType', start), guard)
        self.assertIn('wallpaperData.resourceType == PICTURE || wallpaperData.resourceType == DEFAULT', source[guard:request])
        self.assertNotIn('RequestQemuRenderer', source[source.index('ErrCode WallpaperService::SetWallpaper('):
                                                       source.index('ErrorCode WallpaperService::SetWallpaperBackupData(')])

    def test_actual_controller_native_with_controlled_adapters(self):
        include = self.root / 'host-include'; include.mkdir()
        for name in ('ability_connect_callback_stub.h', 'ability_manager_client.h', 'hilog_wrapper.h',
                     'iremote_object.h', 'os_account_manager.h', 'event_handler.h'):
            (include / name).write_text('#include "host_deps.h"\n')
        shutil.copy2(FIXTURE / 'host_deps.h', include / 'host_deps.h')
        binary = self.root / 'controller-host'
        command = [os.environ.get('OHOS_QA_CXX', 'clang++'), '-std=c++17', '-pthread', '-Wall', '-Wextra', '-Werror',
                   '-fsanitize=address,undefined', '-I' + str(include), '-I' + str(COMPONENT / 'lifecycle'),
                   str(COMPONENT / 'lifecycle/qemu_wallpaper_renderer.cpp'), str(FIXTURE / 'controller_test.cpp'),
                   '-o', str(binary)]
        subprocess.run(command, check=True, timeout=45)
        subprocess.run([str(binary)], check=True, timeout=15,
                       env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1' if os.uname().sysname == 'Linux' else 'detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))


if __name__ == '__main__': unittest.main()
