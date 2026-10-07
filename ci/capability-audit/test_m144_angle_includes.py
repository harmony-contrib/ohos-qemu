"""Include-path and patch fixtures, not a complete ArkWeb build/guest pass."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_access_token_kernel import write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/web/arkweb/m144_angle_includes'
PATCH = next(COMPONENT.glob('*.patch'))


class AngleReleaseIncludesTests(unittest.TestCase):
    def test_pristine_repeat_and_unknown_source_edit_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            write_preimages(source, PATCH)
            arguments = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(source)]
            for _ in range(2):
                subprocess.run(arguments, check=True, capture_output=True)
            path = source / 'src/arkweb/chromium_ext/third_party/angle/src/common/ohos_util.cpp'
            self.assertIn('#include "common/platform.h"', path.read_text())
            path.write_text(path.read_text().replace('"common/platform.h"', '"user-edited.h"'))
            edited = path.read_bytes()
            self.assertNotEqual(subprocess.run(arguments, capture_output=True).returncode, 0)
            self.assertEqual(path.read_bytes(), edited)

    def test_each_added_include_resolves_in_the_real_release_directory_topology(self):
        name = None
        resolved = []
        for line in PATCH.read_text().splitlines():
            if line.startswith('+++ b/'):
                name = Path('/workspace/release') / line[6:]
            match = re.fullmatch(r'\+#include "([^"]+)"', line)
            if match:
                header = match[1]
                if header.startswith('../'):
                    target = (name.parent / header).resolve()
                else:
                    target = Path('/workspace/release/src/third_party/angle/src') / header
                resolved.append(target)
        expected = [
            'third_party/angle/src/common/platform.h',
            'third_party/ohos_ndk/includes/ohos_adapter/hilog_adapter.h',
            'third_party/ohos_ndk/includes/ohos_adapter/ohos_adapter_helper.h',
            'third_party/angle/src/libANGLE/Display.h',
            'third_party/angle/src/libANGLE/renderer/gl/egl/DisplayEGL.h',
            'third_party/ohos_ndk/includes/ohos_adapter/hilog_adapter.h',
            'third_party/angle/src/libANGLE/renderer/gl/egl/ExternalImageSiblingEGL.h',
        ]
        self.assertEqual(resolved, [Path('/workspace/release/src') / path for path in expected])

    def test_only_existing_extension_includes_change_and_both_stages_use_hook(self):
        source = PATCH.read_text()
        changes = [line for line in source.splitlines() if line[:1] in ('+', '-') and
                   not line.startswith(('+++', '---'))]
        self.assertEqual(len(changes), 14)
        self.assertTrue(all(line[1:].startswith('#include "') for line in changes))
        self.assertEqual(source.count('diff --git '), 5)
        self.assertNotIn('new file mode', source)
        hook = (ROOT / 'patches/common/web/arkweb/m144_window_contract/apply_with_core_build.sh').read_text()
        self.assertIn('m144_angle_includes/apply.sh', hook)
        native = (ROOT / 'scripts/build_m144_arkweb_core_in_docker.sh').read_text()
        package = (ROOT / 'patches/common/web/arkweb/m144_core_package/apply_core_and_package.sh').read_text()
        for stage in (native, package):
            self.assertIn('m144_window_contract/apply_with_core_build.sh', stage)
        self.assertIn('m144_angle_includes', (ROOT / 'scripts/m144_core_artifacts.py').read_text())


if __name__ == '__main__':
    unittest.main()
