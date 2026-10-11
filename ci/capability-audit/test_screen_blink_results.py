"""Synthetic verifier rejection tests, not device rendering evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from run_root_probe import digest
from verify_screen_blink_results import optical_sequence, rows, verify_background_restored, verify_frames, verify_initial


class BlinkResultTests(unittest.TestCase):
    nonce = 'a' * 32

    def observations(self, role='system', restarted=False):
        values = [('identity', [20000001, 20000001, 123], '')]
        denied = 202 if role == 'normal' else 201
        if role == 'system':
            values += [('initial.master', [], '1' if restarted else '0')]
        values += [('initial.start', [0 if restarted else 5, 0, 1] if role == 'system' else [-1, denied, 1], ''),
                   ('initial.stop', [0, 0, 1] if role == 'system' else [-1, denied, 1], '')]
        for field, invalid in (('mode', (0, 3, -1)), ('scenario', (0, 5, -1))):
            values += [(f'invalid.{field}.{number}', [-1, 401 if role == 'system' else denied, 1], '')
                       for number in invalid]
        values += [('ready', [1], '')]
        return [dict(runId=self.nonce, role=role, name=name, values=value, text=text)
                for name, value, text in values]

    @staticmethod
    def encode(value):
        return ''.join(json.dumps(row) + '\n' for row in value)

    def test_system_initial_restart_and_strict_rejections(self):
        identity = json.dumps({'applicationInfo': dict(appPrivilegeLevel='system_core',
                              isSystemApp=True, uid=20000001)})
        for restart in (False, True):
            actual = self.observations(restarted=restart)
            verify_initial(self.encode(actual), self.nonce, 'system', identity, restarted=restart)
            bad = copy.deepcopy(actual)
            bad[0]['values'][0] += 1
            with self.assertRaises(ValueError):
                verify_initial(self.encode(bad), self.nonce, 'system', identity, restarted=restart)
            for mutate in ('nonce', 'boolean', 'result', 'extra', 'missing'):
                bad = copy.deepcopy(actual)
                if mutate == 'nonce': bad[0]['runId'] = 'b' * 32
                elif mutate == 'boolean': bad[-1]['values'] = [True]
                elif mutate == 'result': bad[2]['values'] = [1, 0, 1]
                elif mutate == 'extra': bad.append(bad[-1])
                else: bad.pop()
                with self.assertRaises(ValueError):
                    verify_initial(self.encode(bad), self.nonce, 'system', identity, restarted=restart)
        denied = self.observations('system-denied')
        verify_initial(self.encode(denied), self.nonce, 'system-denied', identity)
        denied[1]['values'] = [-1, 202, 1]
        with self.assertRaises(ValueError):
            verify_initial(self.encode(denied), self.nonce, 'system-denied', identity)
        with self.assertRaises(ValueError):
            rows(self.encode(self.observations()), 'stale', 'system')

    def test_normal_role_requires_normal_identity_and_exact_202(self):
        identity = json.dumps({'applicationInfo': dict(appPrivilegeLevel='normal',
                              isSystemApp=False, uid=20010001)})
        actual = self.observations('normal')
        actual[0]['values'] = [20010001, 20010001, 123]
        verify_initial(self.encode(actual), self.nonce, 'normal', identity)
        actual[1]['values'] = [-1, 201, 1]
        with self.assertRaises(ValueError):
            verify_initial(self.encode(actual), self.nonce, 'normal', identity)

    def test_actual_pixels_order_integrity_and_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            frames = []
            for index, color in enumerate(((130, 140, 36), (32, 48, 64)) * 3):
                path = Path(directory) / f'{index}.png'
                Image.new('RGB', (200, 200), color).save(path)
                frames.append(dict(path=str(path), sha256=digest(path), before=index, after=index + .1))
            rect = [0, 0, 200, 200]
            self.assertEqual(verify_frames(frames, rect, 'continuous'), ['on', 'off'] * 3)
            verify_frames([frames[0], frames[1], frames[3]], rect, 'single')
            verify_frames(frames[1::2], rect, 'off')
            self.assertEqual(verify_frames([frames[1], frames[2], frames[3], frames[5]], rect, 'armed-single'),
                             ['off', 'on', 'off', 'off'])
            for invalid in (frames[1::2], frames, frames[:3], frames[1:5]):
                with self.assertRaises(ValueError):
                    verify_frames(invalid, rect, 'armed-single')
            baseline = dict(path=frames[1]['path'], sha256=frames[1]['sha256'])
            extra = Path(directory) / 'last-off.png'
            Image.new('RGB', (200, 200), (32, 48, 64)).save(extra)
            restored = [frames[3], frames[5], dict(path=str(extra), sha256=digest(extra), before=6, after=6.1)]
            verify_background_restored(baseline, restored)
            with self.assertRaises(ValueError): verify_background_restored(baseline, frames[::2])
            with self.assertRaises(ValueError): verify_background_restored(baseline, frames[1::2])
            for mutate in ('hash', 'duplicate', 'nan', 'infinity', 'overlap', 'slow', 'unknown'):
                bad = copy.deepcopy(frames)
                if mutate == 'hash': bad[0]['sha256'] = '0' * 64
                elif mutate == 'duplicate': bad[1] = bad[0]
                elif mutate == 'nan': bad[0]['before'] = float('nan')
                elif mutate == 'infinity': bad[-1]['after'] = float('inf')
                elif mutate == 'overlap': bad[1]['before'] = 0
                elif mutate == 'slow': bad[-1]['after'] = 100
                else:
                    path = Path(directory) / 'wrong.png'
                    Image.new('RGB', (200, 200), 'white').save(path)
                    bad[0].update(path=str(path), sha256=digest(path))
                with self.assertRaises(ValueError):
                    verify_frames(bad, rect, 'continuous')
            for mode in ('off', 'single'):
                with self.assertRaises(ValueError): verify_frames(frames, rect, mode)
            for bad_rect in ([0, 0, 79, 200], [-1, 0, 200, 200], [0, 0, 201, 200]):
                with self.assertRaises(ValueError): verify_frames(frames, bad_rect, 'continuous')

    def test_diagnostic_sequence_under_real_overlay_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'marker.png'
            for zero, one in (((0, 0, 0), (255, 255, 255)), ((112, 112, 0), (255, 255, 143))):
                for value in (0, 1, 2, 37, 128, 254, 255):
                    image = Image.new('RGB', (160, 20))
                    for bit in range(8):
                        image.paste(one if value & (1 << bit) else zero, (bit * 20, 0, (bit + 1) * 20, 20))
                    image.save(path)
                    self.assertEqual(optical_sequence(path, [0, 0, 160, 20]), value)
            Image.new('RGB', (160, 20), (200, 200, 200)).save(path)
            self.assertIsNone(optical_sequence(path, [0, 0, 160, 20]))
            for rect in ([-1, 0, 160, 20], [0, 0, 200, 20], [0, 0, 8, 20]):
                with self.assertRaises(ValueError):
                    optical_sequence(path, rect)


if __name__ == '__main__':
    unittest.main()
