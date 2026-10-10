"""QEMU shortcut configuration boundaries; not keyboard/guest acceptance."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimodalinput/input/shortkey_profile'
RELATIVE = 'foundation/multimodalinput/input/etc/ability_launch_config.json'
ORIGINAL = '''{
  "Shortkeys": [
  ],
  "Sequences": [
  ],
  "RepeatKeys": [
    {
      "keyCode": 18,
      "times": 5,
      "delay": 500,
      "statusConfig": "",
      "ability": {
        "bundleName": "com.ohos.emergencycommunication",
        "abilityName": "com.ohos.emergencycommunication.SOSEmergencyCallAbility"
      }
    }
  ]
}'''


class ShortkeyProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='qemu-shortkey-fixture-')
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name)
        self.path = self.source / RELATIVE
        self.path.parent.mkdir(parents=True)
        self.path.write_text(ORIGINAL)
        self.reserved = self.path.with_name('system_keys_config.json')
        self.reserved.write_text('''{
    "SystemKeys": [
        {
            "preKeys": [ 2076 ],
            "finalKey": -1
        }
    ]
}
''')

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.source)],
                              text=True, capture_output=True)

    def test_apply_idempotence_and_preserved_other_inputs(self):
        for _ in range(2):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(self.path.read_text())
        original = json.loads(ORIGINAL)
        self.assertEqual(actual['RepeatKeys'], original['RepeatKeys'])
        self.assertEqual(actual['Sequences'], original['Sequences'])
        self.assertEqual(len(actual['Shortkeys']), 1)
        key = actual['Shortkeys'][0]
        self.assertEqual(key['businessId'], 'qemu.settings')
        self.assertEqual((key['preKey'], key['finalKey']), ([2076], 2025))
        self.assertEqual((key['trigger'], key['keyDownDuration']), ('key_down', 500))
        self.assertEqual(key['ability'], dict(bundleName='com.ohos.settings',
                                            abilityName='com.ohos.settings.MainAbility'))
        self.assertEqual(json.loads(self.reserved.read_text())['SystemKeys'],
                         [dict(preKeys=[2076], finalKey=2025), dict(preKeys=[2076], finalKey=-1)])

    def test_stale_marker_rechecks_system_reservation(self):
        self.assertEqual(self.apply().returncode, 0)
        self.reserved.write_text(self.reserved.read_text().replace('2025', '2026'))
        self.assertNotEqual(self.apply().returncode, 0)

    def test_existing_unknown_profile_is_not_overwritten(self):
        self.path.write_text(ORIGINAL.replace('"Shortkeys": [\n', '"Shortkeys": [{"businessId":"user"}\n'))
        before = self.path.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_stale_marker_does_not_hide_changed_target(self):
        self.assertEqual(self.apply().returncode, 0)
        self.path.write_text(self.path.read_text().replace('qemu.settings', 'wrong'))
        self.assertNotEqual(self.apply().returncode, 0)

    def test_shared_build_applies_before_build_entry(self):
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('common/foundation/multimodalinput/input/shortkey_profile/apply.sh', script)
        self.assertIn('bash "${QEMU_SHORTKEY_PROFILE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"', script)


if __name__ == '__main__':
    unittest.main()
