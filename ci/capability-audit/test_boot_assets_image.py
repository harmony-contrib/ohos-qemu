"""Boot resource packaging guards, not boot playback proof."""
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_boot_assets_image as boot


def identity(data):
    return {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}


class BootAssetsTests(unittest.TestCase):
    def test_locked_release_objects(self):
        assets = boot.locked_assets()
        self.assertEqual(assets['bootpic.zip']['size'], 1363678)
        self.assertEqual(assets['bootvideo.mp4']['sha256'],
                         'e17936c58519250cb114e8735a05fe2c0bb50d4954a20a0b67b9e652ef276114')

    def test_rejects_both_pointer_formats_even_large(self):
        for marker in boot.MARKERS:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'vendor').mkdir()
                (root / 'vendor/bad').write_bytes(marker + b'\n' + b'x' * 4096)
                with self.assertRaisesRegex(ValueError, 'vendor/bad'):
                    boot.scan_staging(root)

    def test_skips_guest_symlinks_and_accepts_regular_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').write_bytes(b'actual resource')
            (root / 'link').symlink_to('/nonexistent-guest-path')
            self.assertEqual(boot.scan_staging(root)['regular_files_checked'], 1)

    def test_empty_staging_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'empty'):
                boot.scan_staging(Path(directory))

    def test_wrong_identity_fails_before_format(self):
        with self.assertRaisesRegex(ValueError, 'fixed-release'):
            boot.inspect_asset('bootpic.zip', b'pointer', boot.locked_assets()['bootpic.zip'])

    def test_zip_crc_and_header(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('frame.png', b'fixture frame')
        data = stream.getvalue()
        self.assertEqual(boot.inspect_asset('bootpic.zip', data, identity(data)), identity(data))
        with self.assertRaises(zipfile.BadZipFile):
            boot.inspect_asset('bootpic.zip', b'broken', identity(b'broken'))

    def test_video_header(self):
        data = b'\x00\x00\x00\x18ftypisom' + bytes(12)
        self.assertEqual(boot.inspect_asset('bootvideo.mp4', data, identity(data)), identity(data))
        with self.assertRaisesRegex(ValueError, 'video header'):
            boot.inspect_asset('bootvideo.mp4', b'broken', identity(b'broken'))

    def test_packaging_invokes_actual_image_and_all_staging_gate(self):
        script = (ROOT / 'scripts/package_standard_qemu.sh').read_text()
        self.assertIn('verify_boot_assets_image.py', script)
        self.assertIn('--staging-root "$(dirname "${IMAGE_DIR}")"', script)


if __name__ == '__main__':
    unittest.main()
