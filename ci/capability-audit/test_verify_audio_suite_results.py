import json
import unittest
from verify_audio_suite_results import SCOPE, verify

GOOD = {"scope": SCOPE, "cycles": 2, "verified_samples": 3840, "input_callbacks": 16,
        "invalid_state_boundary": True, "pass": True}


class AudioSuiteResultsTests(unittest.TestCase):
    def test_narrow_scope_only(self):
        result = verify(json.dumps(GOOD), 0)
        self.assertFalse(result["algorithm_plugins_tested"])
        self.assertFalse(result["realtime_audio_device_tested"])

    def test_empty_duplicate_wrong_types_failed_or_partial_rejected(self):
        for text in ("", "{}", json.dumps(GOOD) + "\n" + json.dumps(GOOD)):
            with self.assertRaises(ValueError): verify(text, 0)
        for key, value in (("cycles", True), ("cycles", 1), ("verified_samples", 0),
                           ("input_callbacks", 0), ("input_callbacks", True),
                           ("invalid_state_boundary", False), ("pass", 1), ("scope", "all audio passes")):
            row = dict(GOOD); row[key] = value
            with self.assertRaises(ValueError): verify(json.dumps(row), 0)
        for key in GOOD:
            row = dict(GOOD); del row[key]
            with self.assertRaises(ValueError): verify(json.dumps(row), 0)

    def test_actual_nonzero_exit_cannot_pass(self):
        for code in (1, 127, False, None):
            with self.assertRaises(ValueError): verify(json.dumps(GOOD), code)


if __name__ == "__main__": unittest.main()
