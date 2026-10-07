#!/usr/bin/env python3
"""Guard the feature mismatch which failed the first ARM64 phone link."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "patches/lib"))
from network_features import validate


def complete(device):
    return {
        "netmanager_base_enable_feature_sysvpn": True,
        "netmanager_ext_feature_sysvpn": True,
        "netmanager_base_enable_feature_net_firewall": device == "2in1",
        "netmanager_ext_feature_net_firewall": device == "2in1",
    }


class NetworkFeatureTests(unittest.TestCase):
    def test_both_profiles(self):
        for device in ("phone", "2in1"):
            validate(complete(device), device)

    def test_every_missing_or_incorrect_switch_fails(self):
        for device in ("phone", "2in1"):
            for name in complete(device):
                for broken in (None, not complete(device)[name], "true", 1):
                    with self.subTest(device=device, name=name, value=broken):
                        features = complete(device)
                        if broken is None:
                            del features[name]
                        else:
                            features[name] = broken
                        with self.assertRaises(ValueError):
                            validate(features, device)

    def test_unknown_profile_fails(self):
        with self.assertRaises(ValueError):
            validate(complete("phone"), "tablet")


if __name__ == "__main__":
    unittest.main()
