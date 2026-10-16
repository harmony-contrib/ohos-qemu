"""Real source/function regressions with controlled dependencies, never guest proof."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / 'ci/capability-audit/fixtures/batch_media/wallpaper_settings'
SDK = Path(os.environ.get('BATCH_MEDIA_WALLPAPER_SDK', '/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0'))
TS = SDK / 'ets/build-tools/ets-loader/node_modules/typescript'
CONTROLLER = 'applications/standard/settings/feature/theme/src/main/ets/utils/WallpaperSelectionController.ets'
COMPONENTS = ('patches/common/applications/standard/settings/wallpaper_settings',
              'patches/common/base/theme/wallpaper_mgr/qemu_renderer')


def load(path):
    spec = importlib.util.spec_from_file_location('wallpaper_source_guard', path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def function(text, signature):
    start = text.index(signature);brace = text.index('{', start);depth = 1;end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}');end += 1
    return text[start:end]


class WallpaperSettings(unittest.TestCase):
    def test_whole_components_replay_twice_and_reject_every_target_drift(self):
        # /ohos is not inside this repository. Match that layout so git apply
        # does not inherit the parent checkout and skip subdirectory patch paths.
        with tempfile.TemporaryDirectory(prefix='wallpaper-exact-') as temporary:
            root = Path(temporary);shutil.copytree(FIX / 'before', root, dirs_exist_ok=True)
            for component in COMPONENTS:
                guard = load(ROOT / component / 'verify_source.py')
                self.assertFalse(guard.validate(root))
                for _ in range(2):
                    subprocess.run(['bash', str(ROOT / component / 'apply.sh'), '--source-root', str(root)], check=True)
                self.assertTrue(guard.validate(root, require_patched=True))
                for relative, _, expected in guard.FILES:
                    target = root / guard.PROJECT / relative;raw = target.read_bytes()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
                    target.write_bytes(raw + b'\n// unknown external edit\n')
                    with self.assertRaises(ValueError): guard.validate(root, require_patched=True)
                    target.write_bytes(raw)
            self.assertEqual(len(json.loads((FIX / 'targets.json').read_text())), 8)

    def test_existing_manifest_only_requests_the_real_set_permission_and_preserves_source_resources(self):
        name = 'applications/standard/settings/product/phone/src/main/module.json5'
        old, new = (FIX / 'before' / name).read_bytes(), (FIX / 'after' / name).read_bytes()
        added = b'\n      {\n        "name": "ohos.permission.SET_WALLPAPER"\n      },'
        self.assertEqual(new.replace(added, b'', 1), old)
        self.assertNotIn(b'ohos.permission.GET_WALLPAPER', new)
        self.assertNotIn(b'ohos.permission.READ_IMAGEVIDEO', new)
        for locale in ('base', 'zh_CN'):
            name = 'applications/standard/settings/feature/theme/src/main/resources/' + locale + '/element/string.json'
            old = json.loads((FIX / 'before' / name).read_text(encoding='utf-8-sig'))
            new = json.loads((FIX / 'after' / name).read_text())
            self.assertEqual(new['string'][:len(old['string'])], old['string'])
            self.assertEqual(len({r['name'] for r in new['string']}), len(new['string']))
        native = (FIX / 'after/base/theme/wallpaper_mgr/services/BUILD.gn').read_text()
        self.assertEqual(native.count('defines += [ "QEMU_WALLPAPER_RENDERER" ]'), 2)
        for name in ('armv7a_virt', 'arm64_virt', 'x86_64_virt'):
            self.assertIn('product_name == "' + name + '"', native)
            self.assertIn('product_name == "' + name + '"', (ROOT / 'scripts/prepare_qemu_openvpn_backend.py').read_text())
        self.assertEqual(native.count('if (!theme_service &&'), 2)

    def test_official_API26_declarations_without_replacing_SDK_types(self):
        with tempfile.TemporaryDirectory(prefix='wallpaper-types-', dir=FIX) as temporary:
            subprocess.run(['node', str(FIX / 'sdk-types.cjs'), str(FIX / 'after' / CONTROLLER), str(TS),
                            temporary, str(SDK / 'ets/api')], check=True, timeout=30)

    def test_actual_controller_with_cancellation_permission_error_and_resource_boundaries(self):
        subprocess.run(['node', str(FIX / 'controller-tests.cjs'), str(FIX / 'after' / CONTROLLER), str(TS)], check=True, timeout=20)

    def test_actual_native_connect_and_retry_functions_under_sanitizers(self):
        source = (FIX / 'after/base/theme/wallpaper_mgr/services/src/wallpaper_service.cpp').read_text()
        start = source.index('#ifdef QEMU_WALLPAPER_RENDERER')
        constants = source[start:source.index('#endif', start)+len('#endif')]
        actual = function(source, 'bool WallpaperService::ConnectExtensionAbility()') + '\n' + function(source, 'void WallpaperService::StartExtensionAbility(int32_t times)')
        harness = r'''
#include <cassert>
#include <cstdint>
#include <functional>
#include <memory>
#include <queue>
#include <string>
#define HILOG_DEBUG(...) do {} while (0)
#define HILOG_ERROR(...) do {} while (0)
#define HILOG_INFO(...) do {} while (0)
using ErrCode=int;
constexpr int ERR_OK=0,DEFAULT_VALUE=-1,CONNECT_EXTENSION_INTERVAL=100;
struct MemoryGuard {MemoryGuard(){}~MemoryGuard(){}};
struct EventHandler {std::queue<std::function<void()>> tasks;void PostTask(std::function<void()> f,int ms){assert(ms==100);tasks.push(f);}};
class WallpaperService;
struct WallpaperExtensionAbilityConnection {explicit WallpaperExtensionAbilityConnection(WallpaperService&) {}};
namespace AAFwk {
struct Want {std::string bundle,ability;void SetElementName(const char*b,const char*a){bundle=b;ability=a;}};
struct AbilityManagerClient {int connect=0,result=0,calls=0,extensionCalls=0;std::string last;
static std::shared_ptr<AbilityManagerClient> GetInstance(){static auto p=std::make_shared<AbilityManagerClient>();return p;}
int Connect(){++calls;return connect;}int ConnectExtensionAbility(const Want&w,WallpaperExtensionAbilityConnection*,int user){assert(user==-1);last=w.bundle;assert(w.ability=="WallpaperExtAbility");++extensionCalls;return result;}};
}
class WallpaperService {public:WallpaperExtensionAbilityConnection*connection_=nullptr;EventHandler*serviceHandler_=nullptr;~WallpaperService(){delete connection_;}bool ConnectExtensionAbility();void StartExtensionAbility(int32_t);};
'''
        harness += constants + '\n' + actual + r'''
int main(){auto client=AAFwk::AbilityManagerClient::GetInstance();
for(int fault=0;fault<3;++fault){client->connect=fault==1?-17:0;client->result=fault==2?-42:0;client->calls=client->extensionCalls=0;
EventHandler handler;WallpaperService service;service.serviceHandler_=&handler;service.StartExtensionAbility(3);
int retries=0;while(!handler.tasks.empty()){assert(++retries<=2);auto f=handler.tasks.front();handler.tasks.pop();f();}
assert(client->calls==(fault==0?1:3));assert(client->extensionCalls==(fault==1?0:client->calls));
if(fault!=1){
#ifdef QEMU_WALLPAPER_RENDERER
assert(client->last=="com.ohos.wallpaper");
#else
assert(client->last=="com.ohos.launcher");
#endif
}
}
}
'''
        with tempfile.TemporaryDirectory(prefix='wallpaper-native-', dir=FIX) as temporary:
            path=Path(temporary)/'actual-functions.cpp';path.write_text(harness)
            for qemu in (False, True):
                exe=Path(temporary)/('qemu' if qemu else 'stock')
                flags=['clang++','-std=c++17','-Wall','-Wextra','-Werror','-fsanitize=address,undefined']
                subprocess.run(flags+(['-DQEMU_WALLPAPER_RENDERER'] if qemu else [])+[str(path),'-o',str(exe)],check=True,timeout=30)
                subprocess.run([str(exe)],check=True,timeout=10,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))


if __name__ == '__main__':
    unittest.main()
