"""Whole fixed-release JS and exact source transitions; never guest evidence."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
COMPONENT = ROOT / 'patches/common/foundation/multimedia/media_library/photos_recent_info'
spec = importlib.util.spec_from_file_location('photos_recent_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)

class PhotosRecentInfoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='photos-recent-contract-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'source'
        for relative, before, _ in baseline.FILES:
            original = HERE / 'fixtures/photos_recent_info' / Path(relative).name
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), before)
            target = self.root / baseline.PROJECT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)

    def apply(self, component=COMPONENT):
        return subprocess.run(['bash', str(component/'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def snapshot(self):
        return {relative: (self.root/baseline.PROJECT/relative).read_bytes()
                for relative, _, _ in baseline.FILES}

    def test_actual_whole_wrapper_boundaries_and_resource_lifecycle(self):
        applied = self.apply()
        self.assertEqual(applied.returncode, 0, applied.stderr)
        result = subprocess.run(['node', str(HERE/'photos_recent_info_host.js'),
            str(HERE/'fixtures/photos_recent_info/photoaccesshelperinf.js'),
            str(self.root/baseline.PROJECT/baseline.FILES[0][0])], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"checks":130', result.stdout)

    def test_all_previous_components_and_final_stack_repeat_without_changes(self):
        self.assertEqual(self.apply().returncode, 0)
        original = self.snapshot()
        for component in ('fusion_asset_type', 'api26_photo_enums', 'api26_photo_search_enums', 'photos_recent_info'):
            for _ in range(2):
                result = self.apply(COMPONENT.parent/component)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.snapshot(), original)

    def test_each_unknown_sibling_is_rejected_before_write(self):
        original = self.snapshot()
        for relative in original:
            with self.subTest(relative=relative):
                target = self.root/baseline.PROJECT/relative
                target.write_bytes(original[relative]+b'\n// unknown future change\n')
                before = self.snapshot()
                self.assertNotEqual(self.apply().returncode, 0)
                self.assertEqual(self.snapshot(), before)
                target.write_bytes(original[relative])

    def test_final_stack_with_unknown_native_sibling_is_rejected(self):
        self.assertEqual(self.apply().returncode, 0)
        target = self.root/baseline.PROJECT/baseline.FILES[1][0]
        target.write_bytes(target.read_bytes()+b'\n// unknown\n')
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_symlink_sibling_is_rejected(self):
        target = self.root/baseline.PROJECT/baseline.FILES[0][0]
        preserved = target.with_suffix('.preserved')
        target.rename(preserved)
        target.symlink_to(preserved)
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_preparation_orders_complete_repair_before_source_traversal(self):
        recipe = (ROOT/'scripts/build_standard_qemu_in_docker.sh').read_text()
        marker = 'bash "${PHOTOS_RECENT_INFO_COMPONENT_SCRIPT}"'
        self.assertEqual(recipe.count(marker), 1)
        self.assertLess(recipe.index('bash "${PHOTO_SEARCH_ENUMS_COMPONENT_SCRIPT}"'), recipe.index(marker))
        self.assertLess(recipe.index(marker), recipe.index('  write_source_preparation_metadata\n}'))

if __name__ == '__main__':
    unittest.main()
