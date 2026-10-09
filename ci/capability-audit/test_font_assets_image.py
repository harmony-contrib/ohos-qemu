"""Font container validation fixtures, not glyph rendering proof."""
import importlib.util
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('font_assets_image', ROOT / 'scripts/verify_font_assets_image.py')
font = importlib.util.module_from_spec(spec)
spec.loader.exec_module(font)


def sfnt():
    data = bytearray(128)
    data[:4] = b'\x00\x01\x00\x00'
    struct.pack_into('>H', data, 4, 3)
    for index, (tag, offset, size) in enumerate(((b'head', 60, 54), (b'cmap', 114, 4), (b'maxp', 118, 6))):
        struct.pack_into('>4sIII', data, 12 + index * 16, tag, 0, offset, size)
    data[72:76] = b'\x5f\x0f\x3c\xf5'
    return data


class PackagedFontTests(unittest.TestCase):
    def test_manifest_pins_both_observed_missing_objects(self):
        locked = font.locked_fonts()
        self.assertEqual(locked['HarmonyOS_Sans_SC.ttf'], {'size': 20617156,
            'sha256': '8978e05044e7089ad6a9de38c505c8148305607983487435a916d2610700a7ca'})
        self.assertEqual(locked['HMOSColorEmojiCompat.ttf'], {'size': 16819640,
            'sha256': 'a01627a733f1ff723a4eba9f0c4a2ca47e111ea91f2b56eceed1ef50846639cc'})

    def test_real_directory_shape_and_unsafe_entries(self):
        self.assertEqual(font.font_entries('/31/040755/0/0/.//\n/32/100644/0/0/A.ttf/128/\n'), {'A.ttf': 128})
        for text in ('/32/120777/0/0/A.ttf/128/', '/32/100644/0/0/A.ttf/0/',
                     '/32/100644/0/0/A.ttf/128/\n/33/100644/0/0/A.ttf/128/', 'not a listing',
                     '/32/100644/0/0/a/../B.ttf/128/'):
            with self.assertRaises(ValueError): font.font_entries(text)

    def test_valid_minimal_face_structure(self):
        self.assertEqual(font.inspect_sfnt(sfnt()), 1)

    def test_lfs_placeholder_is_not_a_font(self):
        data = (b'# This file was originally tracked by Git LFS but LFS tracking has been removed\n'
                b'version https://git-lfs.github.com/spec/v1\noid sha256:' + b'a' * 64 + b'\nsize 20617156\n')
        with self.assertRaises(ValueError): font.inspect_sfnt(data)
        with self.assertRaises(ValueError): font.inspect_asset('HarmonyOS_Sans_SC.ttf', data, font.locked_fonts())

    def test_table_bounds_duplicate_missing_and_magic_rejected(self):
        for mutation in ('offset', 'size', 'count', 'duplicate', 'missing', 'magic', 'short'):
            data = sfnt()
            if mutation == 'offset': struct.pack_into('>I', data, 20, 0xffffffff)
            elif mutation == 'size': struct.pack_into('>I', data, 24, 0xffffffff)
            elif mutation == 'count': struct.pack_into('>H', data, 4, 4097)
            elif mutation == 'duplicate': data[28:32] = b'head'
            elif mutation == 'missing': data[28:32] = b'fake'
            elif mutation == 'magic': data[72:76] = b'bad!'
            else: struct.pack_into('>I', data, 24, 0)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): font.inspect_sfnt(data)

    def test_collection_count_and_face_offset_rejected(self):
        for count, offset in ((0, 0), (65, 0), (1, 100000)):
            data = bytearray(16)
            struct.pack_into('>4sIII', data, 0, b'ttcf', 0x10000, count, offset)
            with self.assertRaises(ValueError): font.inspect_sfnt(data)

    def test_font_configuration_cannot_be_a_stub(self):
        font.inspect_asset('hm_symbol_config.json', b'{"symbols":[]}', {})
        for data in (b'# LFS removed', b'"placeholder"'):
            with self.assertRaises(ValueError): font.inspect_asset('hm_symbol_config.json', data, {})

    def test_packager_requires_actual_image_font_check(self):
        recipe = (ROOT / 'scripts/package_standard_qemu.sh').read_text()
        marker = 'python3 "${SCRIPT_DIR}/verify_font_assets_image.py"'
        self.assertEqual(recipe.count(marker), 1)
        self.assertIn('--system-image "${IMAGES_OUT}/system.img" --output "${PACKAGE_DIR}/font-assets-evidence.json"', recipe)

    def test_restored_cached_asset_invalidates_old_output_but_repeat_does_not(self):
        with tempfile.TemporaryDirectory(prefix='font-lfs-timestamp-') as directory:
            root = Path(directory)
            data = bytes(sfnt())
            sha = hashlib.sha256(data).hexdigest()
            cache = root / 'cache' / sha[:2] / sha
            cache.parent.mkdir(parents=True)
            cache.write_bytes(data)
            os.utime(cache, (1000000000, 1000000000))
            target = root / 'source/base/global/system_resources/fonts/fixture.ttf'
            target.parent.mkdir(parents=True)
            target.write_text('# This file was originally tracked by Git LFS but LFS tracking has been removed\n'
                              'version https://git-lfs.github.com/spec/v1\noid sha256:' + sha + '\nsize 128\n')
            os.utime(target, (1000000010, 1000000010))
            manifest = root / 'assets.tsv'
            manifest.write_text('base/global/system_resources\tfonts/fixture.ttf\t'
                'https://gitcode.com/openharmony/global_system_resources\t' + sha + '\t128\n')
            argv = ['bash', str(ROOT / 'patches/common/build/github_lfs_assets/apply.sh'),
                    '--source-root', str(root / 'source'), '--asset-root', str(root / 'cache'),
                    '--asset-map', str(manifest)]
            result = subprocess.run(argv, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), data)
            fresh_time = target.stat().st_mtime_ns
            self.assertGreater(fresh_time, 1000000010 * 1000000000)
            result = subprocess.run(argv, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.stat().st_mtime_ns, fresh_time)


if __name__ == '__main__':
    unittest.main()
