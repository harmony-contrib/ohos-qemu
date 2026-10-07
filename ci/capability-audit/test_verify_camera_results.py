"""Verifier fixtures only; generated photos/records are not Camera execution."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from verify_camera_results import ARKTS_CYCLE, ARKTS_PREFIX, NATIVE_BOUNDARIES, NATIVE_CYCLE, decode_photo, verify

RUN = '8' * 32
UID = 20010036
IDENTITY = json.dumps({'applicationInfo': {'uid': UID, 'appPrivilegeLevel': 'normal', 'isSystemApp': False}})


def render(rows):
    return '\n'.join(json.dumps(row) for row in rows)


def fixture(root):
    from PIL import Image, ImageDraw
    native = [{'run_id': RUN, 'kind': 'native_identity', 'arch': 'arm64', 'uid': UID, 'euid': UID}]
    for name in NATIVE_BOUNDARIES:
        native.append(dict(run_id=RUN, kind='native_case', cycle=0, name=name, value=0, **{'pass': True}))
    for cycle in (1, 2):
        for name in NATIVE_CYCLE:
            if name == '@profile':
                row = dict(kind='native_profile', format=1003, width=320, height=180)
            elif name == '@frames':
                row = dict(kind='native_frames', starts=1, ends=1, errors=0, maximum=90)
            else:
                value = 7400103 if name == 'start_before_config_rejected' else 1 if name == 'real_camera_enumeration' else 90 if name == 'real_frame_completion' else 0
                row = dict(kind='native_case', name=name, value=value, **{'pass': True})
            native.append(dict(run_id=RUN, cycle=cycle, **row))
    native.append(dict(run_id=RUN, kind='native_complete', checks=61, failures=0, exit_code=0,
                       scope='public_NDK_preview_callbacks_not_pixel_or_photo_validation'))
    arkts = [dict(run_id=RUN, kind='arkts_case', name=name, cycle=0, value=0, detail='', **{'pass': True}) for name in ARKTS_PREFIX]
    timestamp = 1000000000
    colors = ((192, 192, 192), (192, 192, 0), (0, 192, 192), (0, 192, 0),
              (192, 0, 192), (192, 0, 0), (0, 0, 192), (0, 0, 0))
    for cycle in (1, 2):
        decoded = None
        for name in ARKTS_CYCLE:
            value, detail = 0, ''
            if name == 'camera_enumeration': value = 1
            if name == 'real_profiles': value, detail = 320, '320'
            if name in ('preview_frame_start', 'preview_frame_end'): value = 1
            if name.startswith('photo_timestamp_'):
                timestamp += 100000000
                value = timestamp
                image = Image.new('RGB', (320, 180))
                draw = ImageDraw.Draw(image)
                for i, color in enumerate(colors): draw.rectangle((i * 40, 0, i * 40 + 39, 179), fill=color)
                photo = root / f'camera-{RUN}-c{cycle}-p{name[-1]}.jpg'
                image.save(photo, quality=95)
                decoded = decode_photo(photo)
            if name.startswith('photo_JPEG_'): value = decoded['bytes']
            if name.startswith('photo_dimensions_'): value, detail = decoded['width'], str(decoded['height'])
            if name.startswith('photo_real_pixels_'):
                value, detail = 8, json.dumps(decoded['samples'])
            arkts.append(dict(run_id=RUN, kind='arkts_case', name=name, cycle=cycle, value=value, detail=detail, **{'pass': True}))
    arkts.append(dict(run_id=RUN, kind='arkts_complete',
                      checks=len(ARKTS_PREFIX) + 2 * len(ARKTS_CYCLE), failures=0, **{'pass': True}))
    return native, arkts


class CameraResultTests(unittest.TestCase):
    def test_exact_order_two_native_and_arkts_cycles_and_four_independent_JPEGs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native, arkts = fixture(root)
            observed = verify(render(native), render(arkts), RUN, 'arm64', IDENTITY, root)
            self.assertEqual((observed['native_records'], observed['arkts_records'], len(observed['photos'])), (67, 45, 4))
            self.assertEqual(observed['uid'], UID)

    def test_partial_reordered_duplicate_stale_wrong_arch_or_privileged_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native, arkts = fixture(root)
            for broken in (native[:-1], native + [native[-1]], native[:2] + native[3:], list(reversed(native))):
                with self.assertRaises(ValueError): verify(render(broken), render(arkts), RUN, 'arm64', IDENTITY, root)
            for broken in (arkts[:-1], arkts + [arkts[-1]], list(reversed(arkts))):
                with self.assertRaises(ValueError): verify(render(native), render(broken), RUN, 'arm64', IDENTITY, root)
            for run, arch, identity in ((RUN, 'armv7a', IDENTITY), ('0' * 32, 'arm64', IDENTITY),
                                        (RUN, 'arm64', IDENTITY.replace('normal', 'system_core'))):
                with self.assertRaises(ValueError): verify(render(native), render(arkts), run, arch, identity, root)

    def test_callbacks_true_flags_do_not_replace_actual_API_values_or_normal_UID(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native, arkts = fixture(root)
            for kind, field, value in (('native_identity', 'uid', 0), ('native_identity', 'euid', True),
                                       ('native_profile', 'format', 2000), ('native_frames', 'starts', 0),
                                       ('native_frames', 'errors', 1), ('native_frames', 'maximum', 7),
                                       ('native_complete', 'checks', True)):
                rows = copy.deepcopy(native)
                next(row for row in rows if row['kind'] == kind)[field] = value
                with self.subTest(kind=kind, field=field), self.assertRaises(ValueError):
                    verify(render(rows), render(arkts), RUN, 'arm64', IDENTITY, root)
            rows = copy.deepcopy(native)
            next(row for row in rows if row.get('name') == 'start_before_config_rejected')['value'] = 0
            with self.assertRaises(ValueError): verify(render(rows), render(arkts), RUN, 'arm64', IDENTITY, root)

    def test_actual_photo_bytes_pixels_timestamp_and_lifecycle_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native, arkts = fixture(root)
            for name, field, value in (('capture_requested_1', 'value', 1),
                                       ('capture_call_returned_1', 'value', -1),
                                       ('photo_timestamp_2', 'value', 1), ('photo_JPEG_1', 'value', 128),
                                       ('photo_dimensions_1', 'detail', '1'), ('photo_real_pixels_1', 'detail', '[0,0,0]'),
                                       ('preview_frame_end', 'value', 0), ('release_cycle', 'pass', False)):
                rows = copy.deepcopy(arkts)
                next(row for row in rows if row.get('name') == name)[field] = value
                with self.subTest(name=name, field=field), self.assertRaises(ValueError):
                    verify(render(native), render(rows), RUN, 'arm64', IDENTITY, root)
            photo = root / f'camera-{RUN}-c1-p1.jpg'
            photo.unlink()
            with self.assertRaises(ValueError): verify(render(native), render(arkts), RUN, 'arm64', IDENTITY, root)

    def test_symlink_and_independently_blank_or_different_photo_fail(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native, arkts = fixture(root)
            photo = root / f'camera-{RUN}-c1-p1.jpg'
            outside = root / 'owned.jpg'
            photo.rename(outside)
            photo.symlink_to(outside)
            with self.assertRaises(ValueError): verify(render(native), render(arkts), RUN, 'arm64', IDENTITY, root)
            photo.unlink()
            Image.new('RGB', (320, 180), (0, 0, 0)).save(photo, quality=95)
            rows = copy.deepcopy(arkts)
            next(row for row in rows if row.get('name') == 'photo_JPEG_1')['value'] = photo.stat().st_size
            with self.assertRaises(ValueError): verify(render(native), render(rows), RUN, 'arm64', IDENTITY, root)

    def test_CLI_binds_archive_and_keeps_gate_false_even_fixture_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native, arkts = fixture(root)
            archive, native_file, arkts_file, identity, output = [root / name for name in ('image.tar.gz', 'native', 'arkts', 'identity', 'evidence.json')]
            archive.write_bytes(b'fixture-not-a-QEMU-image')
            native_file.write_text(render(native))
            arkts_file.write_text(render(arkts))
            identity.write_text(IDENTITY)
            command = [sys.executable, str(Path(__file__).with_name('verify_camera_results.py')), '--archive', str(archive),
                       '--native-results', str(native_file), '--arkts-results', str(arkts_file), '--photo-root', str(root),
                       '--application-identity', str(identity), '--run-id', RUN, '--arch', 'arm64', '--output', str(output)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            result = json.loads(output.read_text())
            self.assertFalse(result['first_artifact_behavior_gate_passed'])
            self.assertFalse(result['visible_preview_validated'])
            self.assertFalse(result['video_or_advanced_camera_validated'])
            native_file.write_text('')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(json.loads(output.read_text())['status'], 'fail')


if __name__ == '__main__': unittest.main()
