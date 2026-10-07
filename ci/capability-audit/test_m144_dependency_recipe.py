"""Default cache identity fixtures, not dependency builds or guest evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import shutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from m144_dependency_recipe import REQUIRED, recipe
from m144_core_artifacts import validate_recipe_inputs


class DependencyRecipeTests(unittest.TestCase):
    def test_explicit_core_artifact_requires_actual_complete_builder_helper_recipe(self):
        with tempfile.TemporaryDirectory() as directory:
            frozen = Path(directory)
            actual = recipe(ROOT)
            for name in actual['files_sha256']:
                target = frozen / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
            validate_recipe_inputs(frozen, ROOT)
            for name in (*REQUIRED, 'scripts/package_m144_arkweb_core_in_docker.sh'):
                target = frozen / name; before = target.read_bytes()
                target.write_bytes(before + b'\n# stale dependency input fixture\n')
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'stale fixed dependency'):
                    validate_recipe_inputs(frozen, ROOT)
                target.write_bytes(before)
            (frozen / 'ci/capability-audit').mkdir(parents=True, exist_ok=True)
            (frozen / 'ci/capability-audit/test_unrelated.py').write_text('unrelated fixture')
            validate_recipe_inputs(frozen, ROOT)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in (*REQUIRED, 'scripts/build_m144_v8_in_docker.sh',
                     'patches/common/web/arkweb/m144_core_build/0001-fix.patch',
                     'patches/common/arkcompiler/jsvm/validate_artifacts.py'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('owned input fixture\n')

    def test_recipe_is_deterministic_and_portable_not_repository_path_based(self):
        first = recipe(self.root)
        self.assertEqual(first, recipe(self.root))
        with tempfile.TemporaryDirectory() as other:
            root = Path(other)
            for relative in first['files_sha256']:
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((self.root / relative).read_bytes())
            self.assertEqual(first, recipe(root))
        self.assertEqual(len(first['recipe_sha256']), 64)

    def test_engine_patch_and_builder_or_lock_changes_select_a_fresh_cache(self):
        initial = recipe(self.root)
        for relative in initial['files_sha256']:
            path = self.root / relative
            path.write_text('changed recipe\n')
            self.assertNotEqual(recipe(self.root)['recipe_sha256'], initial['recipe_sha256'])
            path.write_text('owned input fixture\n')

    def test_unrelated_OS_docs_and_runtime_test_edits_do_not_rebuild_Chromium(self):
        initial = recipe(self.root)
        for relative in ('ci/capability-audit/test_new.py', 'scripts/package_standard_qemu.sh',
                         'patches/common/kernel/fix.patch', 'patches/lib/camera_features.py',
                         'patches/common/web/arkweb/m144_core_build/README.md'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('unrelated change\n')
        self.assertEqual(initial, recipe(self.root))

    def test_missing_required_or_aliased_recipe_input_is_rejected(self):
        path = self.root / REQUIRED[0]
        path.unlink()
        with self.assertRaises(ValueError):
            recipe(self.root)
        path.symlink_to(self.root / REQUIRED[1])
        with self.assertRaises(ValueError):
            recipe(self.root)

    def test_all_default_frontends_share_the_repository_recipe_and_keep_explicit_overrides(self):
        for filename in ('run_device_type_matrix_build_docker.sh', 'prepare_qemu_release_dependencies.sh',
                         'run_m144_release_build_docker.sh', 'run_2in1_full_build_docker.sh'):
            source = (ROOT / 'scripts' / filename).read_text()
            self.assertIn('m144_dependency_recipe.py', source)
            self.assertIn('QEMU_ARKWEB_CORE_ARTIFACTS:-', source)
            self.assertIn('arkweb-m144-7.0/${dependency_recipe}', source)
            for destructive in ('rm -rf', 'shutil.rmtree'):
                self.assertNotIn(destructive, source)
        manifest = recipe(ROOT)
        self.assertIn('scripts/docker/m144-build-env.Dockerfile', manifest['files_sha256'])
        self.assertNotIn('ci/capability-audit/test_m144_dependency_recipe.py', manifest['files_sha256'])
        for name in ('scripts/snapshot_build_inputs.py', 'scripts/verify_alsa_config_image.py',
                     'scripts/verify_runtime_elf_contract.py', 'patches/lib/apply_patch.sh',
                     'patches/lib/apply_component_dir.sh', 'patches/lib/avc_artifacts.py'):
            self.assertIn(name, REQUIRED)
            self.assertIn(name, manifest['files_sha256'])


if __name__ == '__main__':
    unittest.main()
