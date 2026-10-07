from pathlib import Path
import subprocess
import tempfile
import unittest
import importlib.util
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "patches/common/web/arkweb/m144_window_contract"
spec = importlib.util.spec_from_file_location('window_release_check', COMPONENT / 'check.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class M144WindowContractTests(unittest.TestCase):
    def test_obsolete_master_patch_is_not_applied_to_unified_release(self):
        self.assertFalse(list(COMPONENT.glob('*.patch')))
        self.assertIn('check.py', (COMPONENT / 'apply.sh').read_text())

    def test_pristine_repeat_and_unknown_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            path = source / 'src/arkweb/ohos_adapter_ndk/interfaces/graphic_adapter.h'
            path.parent.mkdir(parents=True)
            body = ('class WindowAdapter {\n'
                    '    virtual void SetWindowNodeIdAndRSHandle(void* native_window, uint64_t node_id, uint64_t handle) {}\n};\n')
            path.write_text(body)
            with patch.object(checker.subprocess, 'check_output', return_value=checker.REVISION + '\n'):
                for _ in range(2):
                    checker.check(source)
                self.assertEqual(path.read_text(), body)
                path.write_text(body.replace('SetWindowNodeIdAndRSHandle', 'MissingSlot'))
                with self.assertRaises(ValueError):
                    checker.check(source)
            with patch.object(checker.subprocess, 'check_output', return_value='master\n'), self.assertRaises(ValueError):
                checker.check(source)

    def test_both_native_and_hap_paths_reapply_after_official_prepare(self):
        native = (ROOT / 'scripts/build_m144_arkweb_core_in_docker.sh').read_text()
        package = (ROOT / 'patches/common/web/arkweb/m144_core_package/apply_core_and_package.sh').read_text()
        self.assertIn('m144_window_contract/apply_with_core_build.sh', native)
        self.assertIn('m144_window_contract/apply_with_core_build.sh', package)
        self.assertIn('-without-nweb-ex', native)
        bootstrap = (COMPONENT / 'apply_with_core_build.sh').read_text()
        self.assertLess(bootstrap.index('m144_v8_shared/apply.sh'), bootstrap.index('m144_core_build/apply.sh'))


if __name__ == '__main__':
    unittest.main()
