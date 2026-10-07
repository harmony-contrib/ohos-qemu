"""Exact component/branch fixtures only, not Camera device or package tests."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/drivers/peripheral/camera/jpeg_capture'


class CameraJpegCaptureTests(unittest.TestCase):
    def test_component_applies_fresh_and_twice_preserves_unknown_and_partial_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            originals, finals = {}, {}
            for patch in sorted(COMPONENT.glob('*.patch')):
                write_preimages(root, patch)
                for name, sections in patch_sections(patch).items():
                    path = root / name
                    originals[name] = path.read_bytes()
                    final = path.read_text()
                    for _, old, new in sections:
                        old, new = '\n'.join(old), '\n'.join(new)
                        self.assertEqual(final.count(old), 1)
                        final = final.replace(old, new)
                    finals[name] = final.encode()
            recipe = root / 'recipe'
            component = recipe / COMPONENT.relative_to(ROOT)
            shutil.copytree(COMPONENT, component)
            shutil.copytree(ROOT / 'patches/lib', recipe / 'patches/lib')
            verifier = component / 'verify_source.py'
            source = verifier.read_text()
            import importlib.util
            spec = importlib.util.spec_from_file_location('camera_jpeg_fixture_baseline', verifier)
            baseline = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(baseline)
            for relative, original, final in baseline.FILES:
                name = baseline.PROJECT + '/' + relative
                source = source.replace(original, hashlib.sha256(originals[name]).hexdigest())
                source = source.replace(final, hashlib.sha256(finals[name]).hexdigest())
            verifier.write_text(source)
            command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
            for _ in (1, 2):
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual({name: (root / name).read_bytes() for name in originals}, finals)
            name = next(iter(originals))
            for changed in (b'unknown user edit\n', originals[name]):
                (root / name).write_bytes(changed)
                before = {name: (root / name).read_bytes() for name in originals}
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
                self.assertEqual({name: (root / name).read_bytes() for name in originals}, before)

    def test_actual_added_profile_filter_does_not_advertise_unbacked_or_non_capture_JPEG(self):
        patch = COMPONENT / '0002-advertise-the-real-YUYV-software-JPEG-profile.patch'
        sections = next(iter(patch_sections(patch).values()))
        added = sections[1][2][3:-3]
        body = '\n'.join(added)
        self.assertIn('#ifdef QEMU_VIVID_CAPTURE_ENABLED', body)
        program = '''
#include <cassert>
constexpr unsigned OHOS_CAMERA_FORMAT_JPEG = 2000, CAPTURE_STREAM = 2;
struct Input { bool isYuv; };
bool Selected(unsigned format, unsigned streamId, bool yuv) {
  (void)OHOS_CAMERA_FORMAT_JPEG;
  (void)CAPTURE_STREAM;
  Input it {yuv};
  (void)it; // The upstream/off branch deliberately has no added filter.
  for (unsigned once = 0; once != 1; ++once) {
FILTER
    return true;
  }
  return false;
}
int main() {
  for (unsigned repeat = 0; repeat != 512; ++repeat) {
    for (unsigned stream = 0; stream != 4; ++stream) {
      for (bool yuv : {false, true}) {
#ifdef QEMU_VIVID_CAPTURE_ENABLED
        assert(Selected(2000, stream, yuv) == (stream == 2 && yuv));
#else
        assert(Selected(2000, stream, yuv));
#endif
        assert(Selected(1003, stream, yuv));
      }
    }
  }
}
'''.replace('#include <cassert>', '#include <cassert>\n#include <initializer_list>').replace('FILTER', body)
        for definition in ('', '#define QEMU_VIVID_CAPTURE_ENABLED\n'):
            compile_run(definition + program, language='c++')

    def test_actual_source_selection_preserves_non_opt_in_behavior_and_real_MJPEG_preference(self):
        patch = COMPONENT / '0004-use-supported-YUYV-for-software-JPEG-capture.patch'
        fragment = next(iter(patch_sections(patch).values()))[0][2][3:-3]
        program = '''
#include <cassert>
constexpr unsigned V4L2_PIX_FMT_YUYV = 1, V4L2_PIX_FMT_MJPEG = 2, CAMERA_FORMAT_BLOB = 3;
unsigned Select(unsigned cameraformat_, bool advertisedMjpeg) {
 unsigned uvcSourcePixformat_ = 0;
SELECT
 if (advertisedMjpeg) uvcSourcePixformat_ = V4L2_PIX_FMT_MJPEG;
 return uvcSourcePixformat_;
}
int main() {
 for (unsigned repeat = 0; repeat != 512; ++repeat) {
  assert(Select(0, false) == V4L2_PIX_FMT_YUYV);
  assert(Select(0, true) == V4L2_PIX_FMT_MJPEG);
  assert(Select(CAMERA_FORMAT_BLOB, true) == V4L2_PIX_FMT_MJPEG);
#ifdef QEMU_VIVID_CAPTURE_ENABLED
  assert(Select(CAMERA_FORMAT_BLOB, false) == V4L2_PIX_FMT_YUYV);
#else
  assert(Select(CAMERA_FORMAT_BLOB, false) == V4L2_PIX_FMT_MJPEG);
#endif
 }
}
'''.replace('SELECT', '\n'.join(fragment))
        for definition in ('', '#define QEMU_VIVID_CAPTURE_ENABLED\n'):
            compile_run(definition + program, language='c++')

    def test_ordered_plan_and_both_real_targets_share_the_opt_in_define(self):
        source = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        applied = source.index('  bash "${QEMU_CAMERA_JPEG_CAPTURE_COMPONENT_SCRIPT}"')
        self.assertLess(source.index('  bash "${QEMU_CAMERA_USB_COMPONENT_SCRIPT}"'), applied)
        self.assertLess(source.index('  bash "${QEMU_CAMERA_VIVID_COMPONENT_SCRIPT}"'), applied)
        self.assertLess(applied, source.index('  configure_qemu_device_profile', applied))
        for name in ('0001-enable-virtual-capture-metadata-selection.patch',
                     '0003-enable-virtual-capture-pipeline-selection.patch'):
            patch = (COMPONENT / name).read_text()
            self.assertIn('if (drivers_peripheral_camera_qemu_vivid_capture)', patch)
            self.assertIn('defines += [ "QEMU_VIVID_CAPTURE_ENABLED" ]', patch)


if __name__ == '__main__':
    unittest.main()
