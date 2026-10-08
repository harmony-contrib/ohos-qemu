"""Photos graph/signature boundary regressions, not real provider acceptance."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HAP_COMPONENT = ROOT / 'patches/common/applications/standard/hap/photos_provider'
POLICY_COMPONENT = ROOT / 'patches/common/vendor/ohemu/virt/photos_provider'
ORIGINAL = '9AED2A79925ECA050CD2BB9D2A7F694E49E5E135D28EBDCE53836DE76B5080ED'
SIGNATURE = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'


class PhotosProviderIntegration(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='photos-provider-integration-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.graph = self.root / 'applications/standard/hap/BUILD.gn'
        self.graph.parent.mkdir(parents=True)
        shutil.copy2(Path(__file__).parent / 'fixtures/photos_prebuilt_graph.gn', self.graph)
        self.policy = self.root / 'vendor/ohemu/virt/preinstall-config/install_list_capability.json'
        self.policy.parent.mkdir(parents=True)
        self.document = {'install_list': [
            {'bundleName': 'com.ohos.photos', 'app_signature': [ORIGINAL],
             'allowAppUsePrivilegeExtension': True, 'allowFormVisibleNotify': True},
            {'bundleName': 'com.ohos.unrelated', 'app_signature': ['unchanged'],
             'allowAppDesktopIconHide': False}]}
        self.policy.write_text(json.dumps(self.document))

    def apply(self, component):
        return subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_real_prebuilt_graph_removed_and_idempotent(self):
        result = self.apply(HAP_COMPONENT)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.graph.read_text()
        self.assertNotIn('photos_hap', text)
        self.assertNotIn('Photos.hap', text)
        self.assertIn('ohos_prebuilt_etc("camera_hap")', text)
        before = self.graph.read_bytes()
        self.assertEqual(self.apply(HAP_COMPONENT).returncode, 0)
        self.assertEqual(before, self.graph.read_bytes())

    def test_unknown_prebuilt_block_preserved(self):
        self.graph.write_text(self.graph.read_text().replace('module_install_dir = "app/com.ohos.photos"',
                                                           'module_install_dir = "app/edited.photos"'))
        before = self.graph.read_bytes()
        self.assertNotEqual(self.apply(HAP_COMPONENT).returncode, 0)
        self.assertEqual(before, self.graph.read_bytes())

    def test_partial_prebuilt_graph_preserved(self):
        self.graph.write_text(self.graph.read_text().replace('"//applications/standard/hap:photos_hap",', '', 1))
        before = self.graph.read_bytes()
        self.assertNotEqual(self.apply(HAP_COMPONENT).returncode, 0)
        self.assertEqual(before, self.graph.read_bytes())

    def test_marker_cannot_authorize_a_restored_old_target(self):
        original = self.graph.read_bytes()
        self.assertEqual(self.apply(HAP_COMPONENT).returncode, 0)
        self.graph.write_bytes(original)
        self.assertNotEqual(self.apply(HAP_COMPONENT).returncode, 0)

    def test_exact_photo_certificate_only_and_idempotence(self):
        result = self.apply(POLICY_COMPONENT)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = json.loads(json.dumps(self.document))
        expected['install_list'][0]['app_signature'] = [SIGNATURE]
        self.assertEqual(json.loads(self.policy.read_text()), expected)
        before = self.policy.read_bytes()
        self.assertEqual(self.apply(POLICY_COMPONENT).returncode, 0)
        self.assertEqual(before, self.policy.read_bytes())

    def test_unknown_or_wildcard_policy_preserved(self):
        for signature in ('*', 'unexpected future certificate'):
            with self.subTest(signature=signature):
                edited = json.loads(json.dumps(self.document))
                edited['install_list'][0]['app_signature'] = [signature]
                self.policy.write_text(json.dumps(edited))
                before = self.policy.read_bytes()
                self.assertNotEqual(self.apply(POLICY_COMPONENT).returncode, 0)
                self.assertEqual(before, self.policy.read_bytes())

    def test_privilege_edits_preserved(self):
        edited = json.loads(json.dumps(self.document))
        edited['install_list'][0]['allowAppUsePrivilegeExtension'] = False
        self.policy.write_text(json.dumps(edited))
        before = self.policy.read_bytes()
        self.assertNotEqual(self.apply(POLICY_COMPONENT).returncode, 0)
        self.assertEqual(before, self.policy.read_bytes())

    def test_marker_cannot_authorize_a_restored_old_certificate(self):
        self.assertEqual(self.apply(POLICY_COMPONENT).returncode, 0)
        self.policy.write_text(json.dumps(self.document))
        self.assertNotEqual(self.apply(POLICY_COMPONENT).returncode, 0)

    def test_recipe_prepares_every_piece_before_traversal(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        boundary = recipe.index('  write_source_preparation_metadata\n}')
        for name in ('PHOTOS_SOURCE_PROVIDER', 'PHOTOS_PREBUILT', 'PHOTOS_SIGNING'):
            call = 'bash "${' + name + '_COMPONENT_SCRIPT}"'
            self.assertEqual(recipe.count(call), 1)
            self.assertLess(recipe.index(call), boundary)
        self.assertLess(recipe.index('/photos/source_provider/prepare_dependencies.py"'), boundary)
        profile = (ROOT / 'patches/2in1/product_profile/apply.py').read_text()
        self.assertIn('"applications:photos"', profile)
        self.assertIn('add_component(effective, "applications", "photos")', profile)


if __name__ == '__main__':
    unittest.main()
