"""Actual complete snapshot scheduling function with explicit GPU test doubles."""
import base64
import gzip
import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/graphic/graphic_2d/color_picker_gl_sampling'
spec = importlib.util.spec_from_file_location('gl_sampling_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec); spec.loader.exec_module(baseline)

DOUBLES = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <thread>
using NodeId = uint64_t;
#define RS_ENABLE_GL
#define RS_ENABLE_GPU
#define RS_LOGE(...) ((void)0)
#define RS_OPTIONAL_TRACE_NAME(...) ((void)0)
namespace Drawing {
using ColorQuad = uint32_t;
struct Rect {}; struct RectI {}; enum class ClipOp {INTERSECT};
struct GPUContext {};
struct Image {ColorQuad color = 0;};
struct Surface {
 std::shared_ptr<Image> image;
 std::shared_ptr<Image> GetImageSnapshot(RectI, bool) {return image;}
};
}
struct IColorPickerManager {
 int calls=0;Drawing::ColorQuad color=0;std::thread::id owner;
 void HandleColorUpdate(Drawing::ColorQuad value){++calls;color=value;owner=std::this_thread::get_id();}
};
struct RSPaintFilterCanvas {
 std::shared_ptr<Drawing::Surface> surface;std::shared_ptr<Drawing::GPUContext> gpu;
 int saves=0,restores=0;
 void Save(){++saves;}void Restore(){++restores;}void ClipRect(const Drawing::Rect&,Drawing::ClipOp,bool){}
 Drawing::RectI GetRoundInDeviceClipBounds(){return {};}
 auto GetSurface(){return surface;}auto GetGPUContext(){return gpu;}
};
struct RSTagTracker {static constexpr int TAG_COLOR_PICKER_SNAPSHOT=0;
 RSTagTracker(std::shared_ptr<Drawing::GPUContext>,int){};};
static bool hetero=false,vulkan=false,pickOK=true;static int picked=0,scheduled=0;
struct HveFilter {
 static HveFilter& GetHveFilter(){static HveFilter filter;return filter;}
 bool HasValidFilterNode(RSPaintFilterCanvas&,NodeId){return false;}
 std::shared_ptr<Drawing::Image> SampleLayer(RSPaintFilterCanvas&,Drawing::RectI,NodeId){assert(false);return {};}
};
struct RSHeteroColorPicker {
 static RSHeteroColorPicker& Instance(){static RSHeteroColorPicker picker;return picker;}
 template<class Callback>bool GetColor(Callback callback,RSPaintFilterCanvas&,std::shared_ptr<Drawing::Image> image){
  if(hetero)callback(image->color);return hetero;}
};
struct RSSystemProperties {static bool IsUseVulkan(){return vulkan;}};
struct RSPropertyDrawableUtils {
 static bool PickColor(std::shared_ptr<Drawing::GPUContext> gpu,std::shared_ptr<Drawing::Image> image,
                      Drawing::ColorQuad& result){assert(gpu&&image);++picked;result=image->color;return pickOK;}
};
struct Info{};
static auto CreateColorPickerInfo(std::shared_ptr<Drawing::Surface>,std::shared_ptr<Drawing::Image>,
                                 std::weak_ptr<IColorPickerManager>){return std::make_unique<Info>();}
static void ScheduleColorPickWithSemaphore(Drawing::Surface&,std::weak_ptr<IColorPickerManager>,
                                           std::unique_ptr<Info>,Drawing::GPUContext&){++scheduled;}
'''


class GlSamplingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative, before, _ in baseline.FILES:
            fixture = Path(__file__).with_name('fixtures') / (Path(relative).name + '.gz.b64')
            data = gzip.decompress(base64.b64decode(fixture.read_bytes()))
            self.assertEqual(hashlib.sha256(data).hexdigest(), before)
            target = self.root / baseline.PROJECT / relative
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def function(self):
        source = (self.root / baseline.PROJECT / baseline.FILES[0][0]).read_text()
        match = re.search(r'bool ExtractSnapshotAndScheduleColorPick\([\s\S]*?^}', source, re.M)
        self.assertIsNotNone(match)
        return match.group()

    def test_original_GL_reports_scheduling_success_without_any_callback(self):
        compile_run(DOUBLES + self.function() + r'''
int main(){RSPaintFilterCanvas canvas;canvas.gpu=std::make_shared<Drawing::GPUContext>();
 canvas.surface=std::make_shared<Drawing::Surface>();canvas.surface->image=std::make_shared<Drawing::Image>();
 auto manager=std::make_shared<IColorPickerManager>();Drawing::Rect rect;
 assert(ExtractSnapshotAndScheduleColorPick(canvas,&rect,manager,1));
 assert(scheduled==1&&picked==0&&manager->calls==0);}
''', language='c++')

    def test_repaired_GL_snapshot_color_owning_thread_failures_and_VK_path(self):
        applied = self.apply(); self.assertEqual(applied.returncode, 0, applied.stderr)
        compile_run(DOUBLES + self.function() + r'''
int main(){RSPaintFilterCanvas canvas;canvas.gpu=std::make_shared<Drawing::GPUContext>();
 canvas.surface=std::make_shared<Drawing::Surface>();canvas.surface->image=std::make_shared<Drawing::Image>();
 auto manager=std::make_shared<IColorPickerManager>();Drawing::Rect rect;
 for(uint32_t color:{0xff000000u,0xffffffffu,0xff136ab9u}){
  manager->calls=picked=scheduled=0;canvas.surface->image->color=color;
  assert(ExtractSnapshotAndScheduleColorPick(canvas,&rect,manager,1));
  assert(picked==1&&scheduled==0&&manager->calls==1&&manager->color==color);
  assert(manager->owner==std::this_thread::get_id());}
 manager->calls=picked=scheduled=0;pickOK=false;
 assert(!ExtractSnapshotAndScheduleColorPick(canvas,&rect,manager,1));
 assert(picked==1&&scheduled==0&&manager->calls==0);pickOK=true;
 picked=scheduled=0;vulkan=true;
 assert(ExtractSnapshotAndScheduleColorPick(canvas,&rect,manager,1));
 assert(picked==0&&scheduled==1&&manager->calls==0);vulkan=false;
 hetero=true;picked=scheduled=0;
 assert(ExtractSnapshotAndScheduleColorPick(canvas,&rect,manager,1));
 assert(picked==0&&scheduled==0&&manager->calls==1);hetero=false;
 manager->calls=0;
 assert(!ExtractSnapshotAndScheduleColorPick(canvas,nullptr,manager,1));
 auto surface=canvas.surface;canvas.surface=nullptr;
 assert(!ExtractSnapshotAndScheduleColorPick(canvas,&rect,manager,1));canvas.surface=surface;
 auto image=surface->image;surface->image=nullptr;
 assert(!ExtractSnapshotAndScheduleColorPick(canvas,&rect,manager,1));surface->image=image;
 canvas.gpu=nullptr;assert(!ExtractSnapshotAndScheduleColorPick(canvas,&rect,manager,1));
 assert(manager->calls==0&&canvas.saves==canvas.restores);}
''', language='c++')

    def test_exact_two_file_stack_repeat_partial_and_unknown_rejected(self):
        self.assertEqual(self.apply().returncode, 0)
        final = {(self.root / baseline.PROJECT / row[0]):
                 (self.root / baseline.PROJECT / row[0]).read_bytes() for row in baseline.FILES}
        self.assertEqual(self.apply().returncode, 0)
        for target, data in final.items():
            self.assertEqual(target.read_bytes(), data)
        target = next(iter(final)); target.write_bytes(final[target] + b'\n// unknown\n')
        unknown = {path: path.read_bytes() for path in final}
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual({path: path.read_bytes() for path in final}, unknown)


if __name__ == '__main__':
    unittest.main()
