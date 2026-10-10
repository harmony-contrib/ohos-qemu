"""Synthetic DRM parser boundaries, not kernel/guest success evidence."""
import unittest
from verify_kernel_screen_mode import verify

STATE = '''crtc[33]: crtc-0
\tenable=1
\tactive=1
\tmode: "1920x1080": 75 217140 1920 2400 2457 2592 1080 1085 1090 1117 0x48 0xa
connector[34]: Virtual-1
\tcrtc=crtc-0
'''
MODE = dict(width=1920, height=1080, refreshRate=75)


class KernelScreenModeTests(unittest.TestCase):
    def test_exact_real_format_keeps_scope_narrow(self):
        result = verify(STATE, MODE)
        self.assertEqual(result['pixel_clock_khz'], 217140)
        self.assertEqual(result['closed'], [])

    def test_stale_service_mode_or_resolution_rejected(self):
        for key, value in (('width', 1280), ('height', 800), ('refreshRate', 50)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                verify(STATE, dict(MODE, **{key: value}))

    def test_disabled_duplicate_unbound_or_malformed_kernel_records_rejected(self):
        for text in ('', STATE * 2, STATE.replace('enable=1', 'enable=0'),
                     STATE.replace('active=1', 'active=0'), STATE.replace('217140', '0'),
                     STATE.replace('2400', '100'), STATE.replace('crtc=crtc-0', 'crtc=(null)'),
                     STATE.replace('0x48 0xa', ''), STATE.replace('mode:', 'unknown:'),
                     STATE + 'connector[35]: Virtual-2\n\tcrtc=crtc-0\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                verify(text, MODE)


if __name__ == '__main__':
    unittest.main()
