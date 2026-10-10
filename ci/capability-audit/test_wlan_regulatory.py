"""Recipe boundaries; real assets/signature checks run separately in Docker."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/device/qemu/wlan_regulatory'


class WlanRegulatoryTests(unittest.TestCase):
    def test_packaging_and_load_order_preserve_kernel_enforcement(self):
        patch = (COMPONENT / '0001-package-signed-regulatory-database.patch').read_text()
        self.assertIn('"regulatory.db", "regulatory.db.p7s"', patch)
        self.assertIn('+  install_images = [ "vendor" ]', patch)
        self.assertIn('+  relative_install_dir = "init"', patch)
        self.assertIn('+            "name": "pre-init"', patch)
        self.assertIn('/sys/module/firmware_class/parameters/path /system/lib/firmware', patch)
        self.assertNotIn('CONFIG_CFG80211_REQUIRE_SIGNED_REGDB', patch)
        self.assertNotIn('chmod', patch)

    def test_unknown_or_symlinked_asset_rejected(self):
        spec = importlib.util.spec_from_file_location('regdb_assets_test', COMPONENT / 'verify_assets.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            database = root / next(iter(module.ASSETS))
            database.parent.mkdir(parents=True)
            database.write_bytes(b'not an upstream signed database')
            with self.assertRaisesRegex(ValueError, 'unknown regulatory input'):
                module.verify(root)
            database.unlink()
            database.symlink_to(root / 'missing')
            with self.assertRaisesRegex(ValueError, 'unknown regulatory input'):
                module.verify(root)

    def test_common_build_registers_asset_check_before_patch(self):
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(script.count('bash "${QEMU_WLAN_REGULATORY_COMPONENT_SCRIPT}" --source-root'), 1)
        apply = (COMPONENT / 'apply.sh').read_text()
        self.assertLess(apply.index('verify_assets.py'), apply.index('apply_exact_component.py'))


if __name__ == '__main__':
    unittest.main()
