"""Check exact previous/current Settings source migration without a checkout reset."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / 'ci/capability-audit/fixtures/batch_apps'
COMP = ROOT / 'patches/common/applications/standard/settings'
spec = importlib.util.spec_from_file_location('lifetime_upgrade', Path(__file__).with_name('batch_apps_upgrade_settings_lifetimes.py'))
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


class SettingsLifetimeUpgradeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='batch-apps-lifetime-migration-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        provenance = json.loads((FIX / 'share_provider/provenance.json').read_text())
        for path, record in provenance['files'].items():
            if not path.startswith('applications/standard/settings/'):
                continue
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(gzip.decompress(base64.b64decode(record['gzip_base64'])))
        module = upgrade.load_component('accessibility_service_completion')
        target = self.root / module.PROJECT / module.FILES[0][0]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((FIX / 'accessibility_service/IgnoreRepeatClickService.before.ets').read_bytes())

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in (self.root / 'applications').rglob('*') if p.is_file()}

    def previous(self):
        for name in upgrade.COMPONENTS:
            patch = next((COMP / name).glob('0001-*.patch'))
            subprocess.run(['git', '-C', str(self.root), 'apply', str(patch)], check=True, capture_output=True)

    def current(self):
        for name in upgrade.COMPONENTS:
            result = subprocess.run(['bash', str(COMP / name / 'apply.sh'), '--source-root', str(self.root)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_previous_preimages_are_the_complete_first_patch_output(self):
        self.previous()
        for path, digest in json.loads(upgrade.PREVIOUS.read_text())['sha256'].items():
            data = gzip.decompress(base64.b64decode((FIX / 'settings_lifetime_previous' / (Path(path).name + '.gz.b64')).read_bytes()))
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
            self.assertEqual((self.root / path).read_bytes(), data)

    def test_original_current_and_upgrade_replay(self):
        original = self.snapshot()
        report = upgrade.upgrade(self.root)
        self.assertEqual(set(report['states_before'].values()), {'original'})
        self.assertEqual(report['upgraded_files'], [])
        self.assertEqual(self.snapshot(), original)
        self.previous()
        report = upgrade.upgrade(self.root)
        self.assertEqual(set(report['states_before'].values()), {'previous'})
        self.assertEqual(len(report['upgraded_files']), 3)
        self.current()
        current = self.snapshot()
        for _ in range(2):
            report = upgrade.upgrade(self.root)
            self.assertEqual(set(report['states_before'].values()), {'current'})
            self.assertEqual(report['upgraded_files'], [])
            self.current()
            self.assertEqual(self.snapshot(), current)

    def test_new_full_stack_applies_from_original(self):
        self.current()
        current = self.snapshot()
        self.current()
        self.assertEqual(self.snapshot(), current)
        self.assertEqual(upgrade.upgrade(self.root)['upgraded_files'], [])

    def test_unknown_edit_in_either_component_preserves_both(self):
        self.previous()
        for path in json.loads(upgrade.PREVIOUS.read_text())['sha256']:
            target = self.root / path
            clean = target.read_bytes()
            target.write_bytes(clean + b'\n// user edit retained\n')
            before = self.snapshot()
            with self.assertRaises(ValueError):
                upgrade.upgrade(self.root)
            self.assertEqual(self.snapshot(), before)
            target.write_bytes(clean)

    def test_partial_old_new_share_component_is_rejected_before_service_change(self):
        self.previous()
        path = ('applications/standard/settings/product/phone/src/main/ets/Setting/'
                'SharePicker/SharePickerController.ets')
        (self.root / path).write_bytes((FIX / 'share_provider/candidate/SharePickerController.ets').read_bytes())
        before = self.snapshot()
        with self.assertRaises(ValueError):
            upgrade.upgrade(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_symlink_input_is_rejected_before_any_source_write(self):
        self.previous()
        path = next(iter(json.loads(upgrade.PREVIOUS.read_text())['sha256']))
        target = self.root / path
        saved = target.with_suffix('.saved')
        target.rename(saved)
        target.symlink_to(saved)
        before = self.snapshot()
        with self.assertRaises(ValueError):
            upgrade.upgrade(self.root)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(target.is_symlink())

    def test_complete_wallpaper_successor_is_preserved_and_missing_companion_rejected(self):
        self.previous()
        project = self.root / 'applications/standard/settings'
        before = ROOT / 'ci/capability-audit/fixtures/batch_media/wallpaper_settings/before/applications/standard/settings/feature'
        shutil.copytree(before, project / 'feature')
        result = subprocess.run(['bash', str(COMP / 'wallpaper_settings/apply.sh'), '--source-root', str(self.root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        companion = project / 'feature/theme/src/main/ets/utils/WallpaperSelectionController.ets'
        saved = companion.read_bytes()
        companion.unlink()
        incomplete = self.snapshot()
        with self.assertRaises(ValueError):
            upgrade.upgrade(self.root)
        self.assertEqual(self.snapshot(), incomplete)
        companion.write_bytes(saved)
        before = self.snapshot()
        report = upgrade.upgrade(self.root)
        self.assertEqual(len(report['upgraded_files']), 3)
        after = self.snapshot()
        for path, data in before.items():
            if path not in report['upgraded_files']:
                self.assertEqual(after[path], data)
        self.current()
        self.assertEqual(after, self.snapshot())

    def test_share_generator_preserves_the_two_patch_stack_and_successor_guard(self):
        with tempfile.TemporaryDirectory(prefix='batch-apps-share-generator-') as temporary:
            staged = Path(temporary)
            paths = (
                'ci/capability-audit/batch_apps_prepare_share_candidate.py',
                'ci/capability-audit/fixtures/batch_apps/share_provider',
                'ci/capability-audit/fixtures/batch_apps/settings_lifetime_previous',
                'patches/common/applications/standard/settings/share_picker',
                'patches/common/applications/standard/mms/send_data_text',
            )
            for relative in paths:
                source = ROOT / relative
                target = staged / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)
            before = {str(path.relative_to(staged)): path.read_bytes()
                      for path in staged.rglob('*') if path.is_file() and '__pycache__' not in path.parts}
            result = subprocess.run(['python3', str(staged / paths[0])], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for relative, data in before.items():
                self.assertEqual((staged / relative).read_bytes(), data, relative)


if __name__ == '__main__':
    unittest.main()
