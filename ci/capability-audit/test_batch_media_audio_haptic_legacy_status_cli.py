"""Actual recipe readonly verifier against the exact former F bool-parent.

Unexecuted regression source. Reuses existing test helpers without editing the
shared product verifier test file or inheriting/rerunning its unrelated cases.
"""
import unittest
import test_batch_media_audio_haptic_fixes as public_errors
from test_product_component_verifier_cli import ProductVerifierCLI


class AudioHapticLegacyStatusCLI(unittest.TestCase):
    files = ProductVerifierCLI.files
    check = ProductVerifierCLI.check

    def test_readonly_product_verifier_rejects_legacy_parent_until_upgraded(self):
        def populate(root):
            for name, data in public_errors.legacy_postimage().items():
                target = root / 'foundation/multimedia/player_framework' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        self.check(public_errors.COMP, 'AUDIO_HAPTIC_PUBLIC_ERRORS_COMPONENT_SCRIPT',
                   'verify_audio_haptic_public_errors_component', populate)


if __name__ == '__main__':
    unittest.main()
