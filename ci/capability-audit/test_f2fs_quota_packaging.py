"""Synthetic format/launcher tests; no fixture establishes actual quota use."""
import importlib.util
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/vendor/ohemu/f2fs_quota'
spec = importlib.util.spec_from_file_location('quota_format_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
ORIGINAL = ('/data\n2147483648\n--fs_type=f2fs\n'
            '--dac_config ../../build/ohos/images/mkimage/dac.txt\n'
            '--file_context obj/base/security/selinux/file_contexts.bin\n')


class QuotaPackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='quota-format-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / baseline.PROJECT / baseline.FILES[0][0]
        self.config.parent.mkdir(parents=True)
        self.config.write_text(ORIGINAL)
        self.packager = (ROOT / 'scripts/package_standard_qemu.sh').read_text()

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_exact_idempotent_format_has_real_project_quota_option(self):
        self.assertFalse(baseline.validate(self.root))
        for _ in range(2):
            applied = self.apply()
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertTrue(baseline.validate(self.root, require_patched=True))
        self.assertEqual(self.config.read_text(), ORIGINAL + '--prjquota\n')

    def test_unknown_edit_and_missing_f2fs_prerequisite_rejected_unchanged(self):
        for text in (ORIGINAL + '# user edit\n', ORIGINAL.replace('f2fs', 'ext4')):
            self.config.write_text(text)
            self.assertNotEqual(self.apply().returncode, 0)
            self.assertEqual(self.config.read_text(), text)

    def test_existing_shared_vpn_patch_still_detects_its_applied_state(self):
        self.assertEqual(self.apply().returncode, 0)
        source = (ROOT / 'patches/common/standard_vpn/components/vendor_product/'
                  '0001-configure-qemu-vpn-images-and-graphics.patch').read_text()
        first = 'diff --git' + source.split('diff --git')[1]
        patch = self.root / 'existing-format.patch'
        patch.write_text(first)
        result = subprocess.run(['git', '-C', str(self.root), 'apply', '--reverse', '--check', str(patch)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(baseline.validate(self.root, require_patched=True))

    def test_actual_packager_checks_each_real_required_superblock_bit(self):
        match = re.search(r'(?ms)^require_f2fs_verity\(\) \{\n.*?^\}', self.packager)
        self.assertIsNotNone(match)
        function = match.group()
        image = self.root / 'synthetic-header.img'
        for magic, mask, accepted in ((0xf2f52010, 0x498, True), (0, 0x498, False),
                                      (0xf2f52010, 0x400, False),
                                      *((0xf2f52010, 0x498 & ~bit, False) for bit in (8, 16, 128, 1024))):
            header = bytearray(4096)
            struct.pack_into('<I', header, 1024, magic)
            struct.pack_into('<I', header, 3204, mask)
            image.write_bytes(header)
            result = subprocess.run(['bash', '-c', function + '\nrequire_f2fs_verity "$1" fixture',
                'fixture', str(image)], capture_output=True, text=True)
            with self.subTest(magic=magic, mask=mask):
                self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_actual_mount_rewrite_preserves_security_and_quote_is_idempotent(self):
        match = re.search(r"sed_in_place_extended '(s#.*#g)'", self.packager)
        self.assertIsNotNone(match)
        expression = match.group(1)
        for device in ('vda', 'vdf', 'vdc'):
            for kind in ('ext4', 'f2fs'):
                original = ('-append \\"ohos.required_mount.data=/dev/block/' + device +
                            '@/data@' + kind + '@nosuid,nodev,noatime@wait,required\\"\n')
                expected = original.replace('@' + kind + '@nosuid,nodev,noatime@wait,required',
                    '@f2fs@nosuid,nodev,noatime,usrquota,grpquota,prjquota@wait,required,reservedsize=104857600')
                result = subprocess.run(['sed', '-E', expression], input=original, capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout, expected)
                repeated = subprocess.run(['sed', '-E', expression], input=result.stdout,
                                          capture_output=True, text=True, check=True)
                self.assertEqual(repeated.stdout, expected)
        windows = next(line for line in self.packager.splitlines() if line.startswith('\\$KernelBootArgs = '))
        self.assertIn('@f2fs@nosuid,nodev,noatime,usrquota,grpquota,prjquota@', windows)

    def test_shared_build_order_and_kernel_format_are_explicit(self):
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertLess(builder.index('  apply_standard_vpn_component\n'),
                        builder.index('  bash "${F2FS_QUOTA_COMPONENT_SCRIPT}"'))
        self.assertIn('    CONFIG_QFMT_V2 \\\n', self.packager)


if __name__ == '__main__':
    unittest.main()
