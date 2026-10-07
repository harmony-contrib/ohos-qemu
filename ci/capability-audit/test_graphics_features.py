import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'patches/lib'))
from graphics_features import validate

GOOD = {'window_manager_use_sceneboard': True,
        'graphic_2d_feature_rs_enable_uni_render': True,
        'graphic_2d_feature_enable_opengl': True,
        'graphic_2d_feature_enable_vulkan': False}


class GraphicsFeatureTests(unittest.TestCase):
    def test_both_real_profiles(self):
        for device in ('phone', '2in1'):
            validate(dict(GOOD), device)

    def test_missing_wrong_or_non_boolean_values_fail(self):
        for device in ('phone', '2in1'):
            for name, expected in GOOD.items():
                for value in (None, not expected, 1 if expected else 0, str(expected)):
                    broken = dict(GOOD)
                    if value is None: del broken[name]
                    else: broken[name] = value
                    with self.subTest(device=device, name=name, value=value), self.assertRaises(ValueError):
                        validate(broken, device)

    def test_unknown_profile_fails(self):
        with self.assertRaises(ValueError): validate(GOOD, 'tablet')


if __name__ == '__main__': unittest.main()
