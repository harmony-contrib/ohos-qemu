"""Exercise the real packager checksum function against the boot verifier."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from boot_package import verify_extracted_files

ROOT = Path(__file__).resolve().parents[2]


class PackageChecksumCoverageTests(unittest.TestCase):
    def fixture(self, root):
        names = ('manifest.json', 'build-inputs.json', 'images/system.img',
                 'launch/linux.sh', 'launch/macos.command', 'tools/sign-hap.sh',
                 'wallpaper-native/build-theme-service-args.txt',
                 'wallpaper-native/theme-service-query.json',
                 'contacts-native/execution-log.txt',
                 'arkweb-source-core/frozen-build-inputs/nested/source.json',
                 'native-frozen-inputs/scripts/recipe.py',
                 'nested/SHA256SUMS')
        for name in names:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('checksum coverage fixture ' + name)
        return set(names)

    def refresh(self, root):
        source = (ROOT / 'scripts/package_standard_qemu.sh').read_text()
        function = 'refresh_package_checksums() {' + source.split(
            'refresh_package_checksums() {', 1)[1].split('\njson_string_field()', 1)[0]
        subprocess.run(['bash', '-euo', 'pipefail', '-c',
                        function + '\nrefresh_package_checksums "$1"',
                        'checksum-test', str(root)], check=True, capture_output=True,
                       env=dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C'))

    def test_all_nested_witnesses_tools_and_nested_checksum_files_are_covered_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = self.fixture(root)
            self.refresh(root)
            self.assertEqual(set(verify_extracted_files(root)), names)
            initial = (root / 'SHA256SUMS').read_bytes()
            self.refresh(root)
            self.assertEqual((root / 'SHA256SUMS').read_bytes(), initial)
            self.assertEqual(len(initial.splitlines()), len(names))

    def test_boot_verifier_rejects_modified_or_missing_nested_raw_evidence(self):
        for damage in ('modified', 'removed'):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.fixture(root)
                self.refresh(root)
                raw = root / 'wallpaper-native/build-theme-service-args.txt'
                if damage == 'modified':
                    raw.write_bytes(b'changed after packaging')
                else:
                    raw.unlink()
                with self.assertRaises(ValueError):
                    verify_extracted_files(root)


if __name__ == '__main__':
    unittest.main()
