"""Owned SDK completion fixtures, not an actual SDK compile or guest pass."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_m144_core_sdk as sdk


class M144CoreSdkTests(unittest.TestCase):
    def fixture(self, base):
        source, ohos = base / 'release/src', base / 'ohos'
        private = source.parent / 'qemu-core-sdk-api26'
        records = {}
        for name in sdk.COMPONENTS:
            original = ohos / 'prebuilts/ohos-sdk/linux/26.0.0' / name
            original.mkdir(parents=True)
            (original / 'oh-uni-package.json').write_text(json.dumps(
                {'apiVersion': '26', 'version': '26.0.0.39', 'meta': {'metaVersion': '3.0.2'}}))
            if name == 'previewer':
                continue
            shutil.copytree(original, private / name)
            alias = source / 'ohos_sdk/openharmony' / name
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.symlink_to(private / name, target_is_directory=True)
            records[name] = {'source': str(original), 'metadata_sha256': sdk.sha(original / 'oh-uni-package.json')}
        evidence = private / 'preparation-evidence.json'
        evidence.write_text(json.dumps({'private_sdk': str(private),
            'ohos_source_and_sdk_mounted_readonly': True, 'components': records}))
        return source, ohos, private

    def copy(self, argv, check):
        self.assertEqual(argv[:3], ['cp', '--archive', '--reflink=auto'])
        self.assertTrue(check)
        shutil.copytree(argv[3], argv[4])

    def test_complete_missing_previewer_preserves_original_metadata_prior_evidence_and_repeats(self):
        with tempfile.TemporaryDirectory() as directory:
            source, ohos, private = self.fixture(Path(directory))
            evidence = private / 'preparation-evidence.json'; before = evidence.read_bytes()
            with patch.object(sdk.subprocess, 'run', side_effect=self.copy):
                result = sdk.complete_existing(source, ohos)
            self.assertEqual(set(result['components']), set(sdk.COMPONENTS))
            backups = list(private.glob('preparation-evidence.before-previewer-*.json'))
            self.assertEqual(len(backups), 1); self.assertEqual(backups[0].read_bytes(), before)
            original = ohos / 'prebuilts/ohos-sdk/linux/26.0.0/previewer/oh-uni-package.json'
            self.assertEqual(original.read_bytes(), (private / 'previewer/oh-uni-package.json').read_bytes())
            self.assertEqual(sdk.complete_existing(source, ohos), result)

    def test_unknown_alias_or_component_drift_fails_before_copy(self):
        for kind in ('alias', 'metadata'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                source, ohos, private = self.fixture(Path(directory))
                if kind == 'alias':
                    path = source / 'ohos_sdk/openharmony/native'; path.unlink(); path.symlink_to('/invalid')
                else:
                    (private / 'native/oh-uni-package.json').write_text('{}')
                with patch.object(sdk.subprocess, 'run') as execute, self.assertRaises(ValueError):
                    sdk.complete_existing(source, ohos)
                execute.assert_not_called()
                self.assertFalse((private / 'previewer').exists())

    def test_unknown_previewer_state_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source, ohos, private = self.fixture(Path(directory))
            (private / 'previewer').mkdir()
            with patch.object(sdk.subprocess, 'run') as execute, self.assertRaises(ValueError):
                sdk.complete_existing(source, ohos)
            execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
