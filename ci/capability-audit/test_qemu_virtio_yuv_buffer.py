"""Real geometry arithmetic under ASan/UBSan; not a DRM/guest substitute."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/device/qemu/virtio_yuv_buffer'
spec = importlib.util.spec_from_file_location('qemu_yuv_repair_tests', COMPONENT / 'verify_source.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class QemuYuvBufferTests(unittest.TestCase):
    def test_real_geometry_function_under_sanitizers(self):
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler)
        preface = '''#include <cstdint>
#include <climits>
#include <cassert>
#include <cstdio>
constexpr uint32_t HEIGHT_ALIGN=2, WIDTH_ALIGN=8, MAX_PLANES=3;
constexpr uint32_t GBM_BO_USE_SCANOUT=1, GBM_BO_USE_PROTECTED=256;
constexpr uint32_t GBM_BO_USE_SW_READ_OFTEN=512, GBM_BO_USE_SW_READ_RARELY=1024;
constexpr uint32_t GBM_BO_USE_SW_WRITE_OFTEN=2048, GBM_BO_USE_SW_WRITE_RARELY=4096;
struct PlaneLayoutInfo { uint32_t numPlanes; uint32_t radio[3]; };
struct FormatInfo { uint32_t format, bitsPerPixel; const PlaneLayoutInfo *planes; };
struct drm_mode_create_dumb { uint32_t height, width, bpp, flags, handle, pitch; uint64_t size; };
'''
        cases = '''int main() {
  PlaneLayoutInfo p420={3,{4,1,1}}, sp420={2,{4,2,0}}, p422={3,{4,2,2}};
  FormatInfo yuv={1,8,&p420}, nv12={2,8,&sp420}, yuv422={3,8,&p422}, rgba={4,32,nullptr};
  drm_mode_create_dumb d={};
  const uint32_t cpu=GBM_BO_USE_SW_READ_OFTEN|GBM_BO_USE_SW_WRITE_OFTEN;
  assert(PrepareDumbGeometry(64,64,yuv,true,cpu,d));
  assert(d.width==16 && d.height==96 && d.bpp==32 && d.width*4==64);
  assert(PrepareDumbGeometry(64,64,nv12,true,cpu,d));
  assert(d.width==16 && d.height==96 && d.bpp==32);
  assert(PrepareDumbGeometry(70,66,yuv,true,cpu,d));
  assert(d.width==18 && d.height==100 && d.bpp==32 && d.width*4==72);
  assert(PrepareDumbGeometry(64,65,yuv422,true,cpu,d));
  assert(d.width==16 && d.height==130 && d.bpp==32);
  assert(PrepareDumbGeometry(64,64,yuv,false,cpu,d));
  assert(d.width==64 && d.height==96 && d.bpp==8);
  assert(PrepareDumbGeometry(64,64,rgba,true,0,d));
  assert(d.width==64 && d.height==64 && d.bpp==32);
  for (uint32_t denied : {0U,GBM_BO_USE_SCANOUT|cpu,GBM_BO_USE_PROTECTED|cpu})
    assert(!PrepareDumbGeometry(64,64,yuv,true,denied,d));
  assert(!PrepareDumbGeometry(63,64,yuv,true,cpu,d));
  assert(!PrepareDumbGeometry(64,63,nv12,true,cpu,d));
  assert(!PrepareDumbGeometry(0,64,yuv,true,cpu,d));
  assert(!PrepareDumbGeometry(64,0,yuv,true,cpu,d));
  assert(!PrepareDumbGeometry(UINT32_MAX-1,64,yuv,true,cpu,d));
  assert(!PrepareDumbGeometry(64,UINT32_MAX-1,yuv,true,cpu,d));
  assert(!PrepareDumbGeometry(UINT32_MAX,UINT32_MAX,rgba,true,0,d));
  PlaneLayoutInfo bad={4,{4,1,1}}; yuv.planes=&bad;
  assert(!PrepareDumbGeometry(64,64,yuv,true,cpu,d));
  bad.numPlanes=3; bad.radio[0]=0;
  assert(!PrepareDumbGeometry(64,64,yuv,true,cpu,d));
  // Thousands of real dimensions retain enough bytes for all logical planes.
  yuv.planes=&p420;
  for (uint32_t w=2; w<=256; w+=2) for (uint32_t h=2; h<=128; h+=2) {
    assert(PrepareDumbGeometry(w,h,yuv,true,cpu,d));
    const uint64_t pitch=static_cast<uint64_t>(d.width)*4;
    assert(pitch>=w && pitch%8==0 && d.bpp==32);
    assert(pitch*d.height>=pitch*h*3/2);
  }
  std::puts("host_geometry_8192_dimensions_only_not_guest_pixels");
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'geometry.cpp'
            source.write_text(preface.replace('#include <cstdio>', '#include <cstdio>\n#include <initializer_list>') +
                repair.NEW_GEOMETRY.split('static bool IsVirtioGpu', 1)[0] + cases)
            binary = root / 'geometry'
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(source), '-o', str(binary)], check=True, capture_output=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn('8192_dimensions_only_not_guest_pixels', result.stdout)

    def test_fixed_preflight_exact_states_and_foreign_edits_preserved(self):
        original = ''.join(old for old, _ in repair.REPLACEMENTS)
        repaired = repair.repaired_source(original)
        with self.assertRaises(ValueError): repair.repaired_source(original + repair.OLD_GEOMETRY)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'device/qemu' / repair.FILE
            target.parent.mkdir(parents=True)
            target.write_text(original)
            def git(argv, **kwargs):
                return repair.REVISION + '\n' if argv[-2:] == ['rev-parse', 'HEAD'] else original.encode()
            with patch.object(repair.subprocess, 'check_output', side_effect=git):
                self.assertFalse(repair.validate(root))
                with self.assertRaises(ValueError): repair.validate(root, True)
                target.write_text(repaired)
                self.assertTrue(repair.validate(root, True))
                target.write_text(repaired + '// foreign edit\n')
                with self.assertRaises(ValueError): repair.validate(root)
                self.assertTrue(target.read_text().endswith('// foreign edit\n'))
                target.unlink()
                outside = root / 'outside'
                outside.write_text(original)
                target.symlink_to(outside)
                with self.assertRaises(ValueError): repair.validate(root)
                self.assertEqual(outside.read_text(), original)

    def test_component_wired_in_single_plan_before_product_traversal(self):
        builder = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        plan = builder.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\n}\n', 1)[0]
        self.assertEqual(plan.count('bash "${QEMU_VIRTIO_YUV_BUFFER_COMPONENT_SCRIPT}"'), 1)
        self.assertLess(plan.index('QEMU_VIRTIO_YUV_BUFFER_COMPONENT_SCRIPT'), plan.index('configure_qemu_device_profile'))
        source = repair.NEW_GEOMETRY
        self.assertIn('drmGetVersion(gbm->fd)', source)
        self.assertIn('drmFreeVersion(version)', source)
        for forbidden in ('chmod(', 'chown(', '/dev/dma_heap', 'setuid(', 'EMULATOR_ENABLED'):
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
