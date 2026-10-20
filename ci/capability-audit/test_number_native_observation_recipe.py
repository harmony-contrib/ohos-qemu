"""Execute the real source plan and image admission on exact paired sources."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / 'patches'
OLD = PATCHES / 'common/foundation/ability/ability_runtime/number_identity_loader'
A = PATCHES / 'common/foundation/ability/ability_runtime/number_identity_native_trace495'
B = PATCHES / 'common/base/telephony/number_identity/native_observation495'
MAIN = 'foundation/ability/ability_runtime/frameworks/native/appkit/app/main_thread.cpp'


def populate(component, root):
    state = json.loads((component / 'source_states.json').read_text())
    for relative, before, after in state['files']:
        if before is not None:
            target = root / state['project'] / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(component / 'fixtures/original' / state['project'] / relative, target)


class NumberRecipe(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='number-trace-recipe-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.source = self.base / 'source with spaces'
        self.source.mkdir()
        populate(A, self.source)
        populate(B, self.source)
        (self.base / 'cache/logs').mkdir(parents=True)
        (self.source / 'out/arm64_virt').mkdir(parents=True)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(PATCH_ROOT=str(PATCHES), OHOS_ROOT=str(self.source),
                        SOURCE_ROOT=str(self.source), CACHE_ROOT=str(self.base / 'cache'),
                        SCRIPT_DIR=str(ROOT / 'scripts'), PRODUCT='arm64_virt',
                        DEVICE_TYPE_PROFILE='qemu_phone_full_source',
                        GIT_CEILING_DIRECTORIES=str(self.base), GIT_CONFIG_GLOBAL='/dev/null',
                        GIT_CONFIG_NOSYSTEM='1', PYTHONDONTWRITEBYTECODE='1')

    def shell(self, program, **updates):
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', program],
                              env=dict(self.env, **updates), capture_output=True, text=True, timeout=30)

    def plan_function(self):
        text = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        begin = text.index('apply_number_identity_native_observation() {\n')
        end = text.index('apply_qemu_capability_patch_plan() {\n', begin)
        return text[begin:end]

    def apply(self):
        result = self.shell(self.plan_function() + '\napply_number_identity_native_observation\n')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def snapshot(self):
        return {str(p.relative_to(self.source)): p.read_bytes()
                for p in self.source.rglob('*') if p.is_file()
                and 'out' not in p.relative_to(self.source).parts}

    def image_module(self):
        path = ROOT / 'scripts/verify_number_identity_image.py'
        spec = importlib.util.spec_from_file_location('actual_number_image_recipe', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def package_function(self):
        text = (ROOT / 'scripts/package_standard_qemu.sh').read_text()
        begin = text.index('verify_number_native_observation_source() {\n')
        end = text.index('verify_audio_haptic_sync_id_source() {\n', begin)
        return text[begin:end]

    def test_upstream_loader_then_two_components_and_idempotence(self):
        shutil.copy2(OLD / 'fixtures/original' / MAIN, self.source / MAIN)
        self.apply()
        after = self.snapshot()
        self.assertTrue((self.base / 'cache/logs/apply_number_identity_loader.log').exists())
        self.apply()
        self.assertEqual(after, self.snapshot())
        self.image_module().require_number_loader_source(self.source)

    def test_loaded_predecessor_skips_old_apply_then_completes(self):
        self.apply()
        self.assertFalse((self.base / 'cache/logs/apply_number_identity_loader.log').exists())
        self.image_module().require_number_loader_source(self.source)

    def test_unknown_provider_refused_before_any_source_mutation(self):
        path = self.source / 'base/telephony/number_identity/number_location/src/number_location_ability.cpp'
        path.write_bytes(path.read_bytes() + b'\n// unknown input\n')
        before = self.snapshot()
        result = self.shell(self.plan_function() + '\napply_number_identity_native_observation\n')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_image_admits_only_complete_successor_after_legacy_rejection(self):
        # The legacy standalone guard keeps its original predecessor contract.
        module = self.image_module()
        module.require_number_loader_source(self.source)
        result = self.shell('bash "$PATCH_ROOT/common/foundation/ability/ability_runtime/number_identity_native_trace495/apply.sh" --source-root "$OHOS_ROOT"')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with self.assertRaises(ValueError):
            module.require_number_loader_source(self.source)
        self.apply()
        module.require_number_loader_source(self.source)
        path = self.source / MAIN
        path.write_bytes(path.read_bytes() + b'\n// unknown input\n')
        with self.assertRaises(ValueError):
            module.require_number_loader_source(self.source)

    def test_full_phone_packaging_requires_complete_vector(self):
        program = self.package_function() + '\nverify_number_native_observation_source\n'
        result = self.shell(program)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.apply()
        result = self.shell(program)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = json.loads((self.source / 'out/arm64_virt/number-native-observation-source.json').read_text())
        self.assertTrue(receipt['whole_final'])
        self.assertFalse(receipt['compiled'])
        self.assertFalse(receipt['native_callback_proven'])

    def test_selector_requires_exact_legacy_or_complete_successor(self):
        fixture = Path(__file__).resolve().parent / 'fixtures/number_native_observation/source_pins_before'
        shutil.copytree(fixture, self.source, dirs_exist_ok=True)
        path = PATCHES / 'common/vendor/ohemu/virt/number_identity_local/configure.py'
        spec = importlib.util.spec_from_file_location('actual_number_selector_recipe', path)
        selector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(selector)
        self.assertEqual(selector.source_pins(self.source), selector.SOURCE_PINS)
        partial = self.shell('bash "$PATCH_ROOT/common/foundation/ability/ability_runtime/number_identity_native_trace495/apply.sh" --source-root "$OHOS_ROOT"')
        self.assertEqual(partial.returncode, 0, partial.stdout + partial.stderr)
        with self.assertRaises(ValueError):
            selector.source_pins(self.source)
        self.apply()
        final = selector.source_pins(self.source)
        self.assertEqual(len([key for key in final if final[key] != selector.SOURCE_PINS[key]]), 3)
        unrelated = self.source / 'base/telephony/number_identity/frameworks/js/src/napi_number_identity.cpp'
        unrelated.write_bytes(unrelated.read_bytes() + b'\n// unrelated input\n')
        with self.assertRaises(ValueError):
            selector.source_pins(self.source)


if __name__ == '__main__':
    unittest.main()
