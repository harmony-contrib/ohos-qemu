"""Patch/installer boundaries only; actual Linux ABI tests run separately."""
import contextlib
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/drivers/peripheral/camera/vivid_capture'
KERNEL_CONFIG = REPO / 'patches/common/device/qemu/vivid_capture'
KERNEL_DEFAULTS = REPO / 'patches/common/kernel/linux/linux_6_6/vivid_capture'


def load(path):
    spec = importlib.util.spec_from_file_location('camera_vivid_' + path.parent.name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load(COMPONENT / 'apply.py')
configuration = load(KERNEL_CONFIG / 'check.py')
defaults = load(KERNEL_DEFAULTS / 'check.py')


class VividCaptureTests(unittest.TestCase):
    def run_installer(self, root, head=installer.REVISION, check_only=False):
        argv = ['apply.py', '--source-root', str(root)] + (['--check-only'] if check_only else [])
        def git(command, **kwargs):
            if command[-2:] == ['rev-parse', 'HEAD']: return head + '\n'
            pairs = installer.transforms()[command[-1].removeprefix('HEAD:')]
            return b'\n'.join(old for old, _ in pairs)
        with patch.object(sys, 'argv', argv), patch.object(installer.subprocess, 'check_output', side_effect=git), contextlib.redirect_stdout(io.StringIO()):
            installer.main()

    def fixture(self, root):
        source = root / 'drivers/peripheral'
        for name, pairs in installer.transforms().items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(installer.repaired(b'\n'.join(old for old, _ in pairs), pairs))
        return source

    def test_strict_revision_unknown_source_and_header_are_preserved(self):
        for failure in ('revision', 'source', 'header'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                source = self.fixture(root)
                header = source / installer.HEADER
                if failure == 'source': (source / 'camera/camera.gni').write_bytes(b'unknown edit')
                if failure == 'header': header.write_bytes(b'unknown header')
                before = {p: p.read_bytes() for p in source.rglob('*') if p.is_file()}
                with self.assertRaises(SystemExit):
                    self.run_installer(root, head='master' if failure == 'revision' else installer.REVISION)
                self.assertEqual(before, {p: p.read_bytes() for p in source.rglob('*') if p.is_file()})

    def test_check_only_and_repeated_install_do_not_forge_kernel_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = self.fixture(root)
            header = source / installer.HEADER
            self.run_installer(root, check_only=True)
            self.assertFalse(header.exists())
            for _ in range(2):
                self.run_installer(root)
                self.assertEqual(header.read_bytes(), (COMPONENT / 'files/qemu_v4l2_capture.h').read_bytes())
            changes = installer.transforms()['camera/vdi_base/usb_camera/adapter/platform/v4l2/src/driver_adapter/src/v4l2_uvc.cpp']
            self.assertTrue(all(b'UsbDeviceFilter' not in old + new for old, new in changes))
            self.assertTrue(all(b'GetCameraDevNameByCap' not in old + new for old, new in changes))

    def test_symlink_rejected_before_patch_or_header_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = self.fixture(root)
            path = source / 'camera/camera.gni'
            outside = root / 'owned'
            path.rename(outside)
            path.symlink_to(outside)
            original = outside.read_bytes()
            with self.assertRaises(SystemExit): self.run_installer(root, check_only=True)
            self.assertEqual(outside.read_bytes(), original)
            self.assertFalse((source / installer.HEADER).exists())

    def test_kernel_settings_reject_partial_duplicate_and_unknown_configs(self):
        for name, selections in configuration.PRE.items():
            before = '\n'.join('# ' + key + ' is not set' if value == 'n' else key + '=' + value
                               for key, value in selections.items()) + '\n'
            configuration.validate(name, before)
            after = '\n'.join(key + '=' + value for key, value in configuration.POST.items()) + '\nCONFIG_FB=y\nCONFIG_HAS_DMA=y\n'
            configuration.validate(name, after, patched=True)
            for wrong in (after.replace('CONFIG_VIDEO_VIVID=y', 'CONFIG_VIDEO_VIVID=m'),
                          after + 'CONFIG_VIDEO_VIVID=y\n',
                          after.replace('CONFIG_HAS_DMA=y', '# CONFIG_HAS_DMA is not set')):
                with self.assertRaises(ValueError): configuration.validate(name, wrong, patched=True)

    def test_real_default_changes_leave_error_injection_and_frame_generation_untouched(self):
        before = (b'static unsigned int node_types[VIVID_MAX_DEVS] = {\n'
                  b'\t[0 ... (VIVID_MAX_DEVS - 1)] = 0xe1d3d\n};\n'
                  b'static unsigned num_inputs[VIVID_MAX_DEVS] = { [0 ... (VIVID_MAX_DEVS - 1)] = 4 };\n')
        after = defaults.repaired(before)
        self.assertIn(b'= 0x1\n', after)
        self.assertIn(b'= 1 };\n', after)
        self.assertNotIn(b'= 0xe1d3d', after)
        with self.assertRaises(ValueError): defaults.repaired(after)

    def test_kernel_patch_has_production_context_and_is_reversible(self):
        patch_file = KERNEL_CONFIG / '0001-build-real-v4l2-capture-driver-in-three-kernels.patch'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            originals = {}
            for section in patch_file.read_text().split('diff --git ')[1:]:
                name = section.split('+++ b/')[1].splitlines()[0]
                hunks = list(re.finditer(r'^@@ -(\d+),(\d+) \+\d+,\d+ @@\n(.*?)(?=^@@|\Z)', section, re.M | re.S))
                lines = ['# isolated patch fixture\n'] * max(int(h[1]) + int(h[2]) for h in hunks)
                for h in hunks:
                    old = [line[1:] + '\n' for line in h[3].splitlines() if line.startswith((' ', '-'))]
                    self.assertEqual(len(old), int(h[2]))
                    start = int(h[1]) - 1
                    lines[start:start + len(old)] = old
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(''.join(lines))
                originals[path] = path.read_bytes()
            command = ['git', '-C', str(root), 'apply', '--whitespace=nowarn', str(patch_file)]
            subprocess.run(command, check=True, capture_output=True)
            subprocess.run(command + ['--reverse'], check=True, capture_output=True)
            self.assertTrue(all(path.read_bytes() == data for path, data in originals.items()))

    def test_opt_in_precedes_profile_and_kernel_fingerprint_traversal(self):
        builder = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        position = builder.index('bash "${QEMU_CAMERA_VIVID_COMPONENT_SCRIPT}"')
        self.assertLess(position, builder.index('  configure_qemu_device_profile\n', position))
        self.assertLess(builder.index('bash "${VIVID_CAPTURE_DEFAULTS_COMPONENT_SCRIPT}"'),
                        builder.index('  configure_qemu_device_profile\n', position))


if __name__ == '__main__': unittest.main()
