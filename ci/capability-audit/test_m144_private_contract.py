from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages
from check_m144_private_contract import cross_flags, virtuals

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/web/arkweb/m144_private_contract'
PATCHES = tuple(sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch')))


class PrivateContractTests(unittest.TestCase):
    def test_only_existing_private_source_no_generated_or_public_headers(self):
        changed = set().union(*(patch_sections(patch) for patch in PATCHES))
        self.assertEqual(len(changed), 9)
        self.assertTrue(all(name.startswith(('src/arkweb/ohos_adapter_ndk/',
                                            'src/arkweb/chromium_ext/ui/gl/ohos/frame_available_listener_impl.',
                                            'src/arkweb/chromium_ext/media/base/ohos/buffer_request_config_adapter_impl.'))
                            for name in changed))
        self.assertTrue(all('/glue/' not in name and '/third_party/' not in name for name in changed))

    def test_pristine_repeat_and_unknown_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            write_preimages(source, PATCHES)
            command = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(source)]
            for _ in range(2):
                subprocess.run(command, capture_output=True, check=True)
            graphic = source / 'src/arkweb/ohos_adapter_ndk/interfaces/graphic_adapter.h'
            graphic.write_text(graphic.read_text().replace('virtual void* GetContext() = 0;', 'virtual void* GetContext() const = 0;'))
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_nonvirtual_extension_does_not_add_release_slot(self):
        self.assertEqual(virtuals('class Example {\nvirtual void Start() = 0;\nvoid Extra();\nvirtual void Finish() = 0;\n};', 'Example'),
                         ['virtual void Start() = 0;', 'virtual void Finish() = 0;'])

    def test_cross_flags_do_not_keep_aarch64_only_options(self):
        flags = ['--target=aarch64-linux-ohos', '-mbranch-protection=pac-ret+b-key', '-mno-outline', '-flto=thin']
        actual = cross_flags(flags, 'arm-linux-ohos', Path('/tmp/owned'))
        self.assertIn('--target=arm-linux-ohos', actual)
        self.assertIn('-march=armv7-a', actual)
        self.assertIn('-flto=thin', actual)
        self.assertFalse(any(flag.startswith('-mbranch-protection') for flag in actual))

    def test_native_and_hap_both_use_and_freeze_component(self):
        self.assertIn('m144_private_contract/apply.sh', (ROOT / 'patches/common/web/arkweb/m144_window_contract/apply_with_core_build.sh').read_text())
        self.assertIn('m144_private_contract', (ROOT / 'scripts/package_m144_arkweb_core_in_docker.sh').read_text())

    def test_request_timestamp_is_concrete_helper_and_flush_remains_authoritative(self):
        patch = (COMPONENT / '0004-keep-request-timestamp-helper-out-of-release-vtable.patch').read_text()
        self.assertIn('-  int64_t GetTimestamp() override;', patch)
        self.assertIn('+  int64_t GetTimestamp();', patch)
        self.assertNotIn('+  virtual', patch)
        graphics = (COMPONENT / '0001-sync-release-graphics-private-contract.patch').read_text()
        self.assertIn('SET_UI_TIMESTAMP, flushConfigAdapter->GetTimestamp()', graphics)

    def test_actual_chromium_listener_callback_context_and_boundaries(self):
        # Actual patched class/body, with only Chromium's closure dependency
        # replaced by a host seam. This is not a GPU or guest acceptance test.
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            write_preimages(source, (PATCHES[2],))
            subprocess.run(['git', '-C', str(source), 'apply', str(PATCHES[2])], check=True)
            gl = source / 'src/arkweb/chromium_ext/ui/gl/ohos'
            header = (gl / 'frame_available_listener_impl.h').read_text()
            body = (gl / 'frame_available_listener_impl.cc').read_text()
            header = '\n'.join(line for line in header.splitlines() if not line.startswith('#include'))
            body = '\n'.join(line for line in body.splitlines() if not line.startswith('#include'))
            prelude = '''#include <cassert>
#include <functional>
#include <memory>
#include <thread>
#include <utility>
namespace base { class RepeatingClosure {
  std::function<void()> callback;
public:
  RepeatingClosure() = default;
  RepeatingClosure(std::function<void()> cb) : callback(std::move(cb)) {}
  explicit operator bool() const { return bool(callback); }
  void Run() { callback(); }
}; }
namespace OHOS::NWeb {
using OnFrameAvailableCb = void (*)(void*);
class FrameAvailableListener {
public:
  virtual ~FrameAvailableListener() = default;
  virtual void* GetContext() = 0;
  virtual OnFrameAvailableCb GetOnFrameAvailableCb() = 0;
}; }
'''
            main = '''int main() {
  using namespace OHOS::NWeb;
  unsigned count = 0;
  const auto thread = std::this_thread::get_id();
  auto listener = std::make_shared<FrameAvailableListenerImpl>(
    base::RepeatingClosure([&] { assert(std::this_thread::get_id() == thread); ++count; }));
  std::shared_ptr<FrameAvailableListener> registry = listener;
  assert(registry->GetContext() == listener.get());
  auto cb = registry->GetOnFrameAvailableCb();
  assert(cb != nullptr && cb == registry->GetOnFrameAvailableCb());
  cb(nullptr);
  assert(count == 0);
  cb(registry->GetContext());
  assert(count == 1);
  std::weak_ptr<FrameAvailableListener> weak = registry;
  listener.reset();
  auto dispatch = registry;
  registry.reset();
  cb(dispatch->GetContext());
  assert(count == 2 && !weak.expired());
  dispatch.reset();
  assert(weak.expired());
  FrameAvailableListenerImpl empty(base::RepeatingClosure{});
  empty.GetOnFrameAvailableCb()(empty.GetContext());
  assert(count == 2);
}
'''
            compile_run(prelude + header + '\n' + body + '\n' + main, language='c++')


if __name__ == '__main__':
    unittest.main()
