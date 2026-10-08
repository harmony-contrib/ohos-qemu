"""Exact native enum export fixtures; no interface/device/backend pass claim."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/ethernet_api26'
PATCH = COMPONENT / '0002-register-the-existing-device-connection-type-enum.patch'
CPP = 'foundation/communication/netmanager_ext/frameworks/js/napi/ethernet/ethernet_module.cpp'


class EthernetConnectionTypeTests(unittest.TestCase):
    def test_exact_native_values_are_registered_without_feature_guard(self):
        lines = patch_sections(PATCH)[CPP][1][2]
        begin = lines.index('    napi_value connectionTypes = NapiUtils::CreateObject(env);')
        end = lines.index('    AddCleanupHook(env);')
        body = '\n'.join(lines[begin:end])
        source = r'''
#include <cassert>
#include <cstdint>
#include <initializer_list>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value { int32_t number=0; std::map<std::string, Value*> own; };
using napi_env=void*; using napi_value=Value*;
enum DeviceConnectionType { BUILT_IN=0, EXTERNAL=1 };
struct Property { const char* name; Value* value; };
std::vector<std::unique_ptr<Value>> storage;
struct NapiUtils {
    static Value* CreateObject(napi_env) { storage.push_back(std::make_unique<Value>());
        return storage.back().get(); }
    static Value* CreateInt32(napi_env env,int32_t number) { auto value=CreateObject(env);
        value->number=number; return value; }
    static void DefineProperties(napi_env,Value* object,std::initializer_list<Property> properties) {
        for(const auto& property:properties) assert(object->own.emplace(property.name,property.value).second); }
    static void SetNamedProperty(napi_env,Value* object,const char* name,Value* value) {
        assert(object->own.emplace(name,value).second); }
};
#define DECLARE_NAPI_STATIC_PROPERTY(name,value) Property{name,value}
void Register(napi_env env,Value* exports) {
'''
        main = r'''
}
int main() {
    for(unsigned repeat=0;repeat<256;++repeat) {
        auto exports=NapiUtils::CreateObject(nullptr); Register(nullptr,exports);
        assert(exports->own.size()==1);
        auto types=exports->own.at("DeviceConnectionType"); assert(types->own.size()==2);
        assert(types->own.at("BUILT_IN")->number==BUILT_IN);
        assert(types->own.at("EXTERNAL")->number==EXTERNAL);
    }
}
'''
        compile_run(source + body + main, language='c++')
        self.assertNotIn('#if', body)

    def test_whole_component_fresh_and_repeat_application(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for patch in sorted(COMPONENT.glob('*.patch')):
                write_preimages(root, patch)
            fixture = root / 'fixture-repository'
            component = fixture / COMPONENT.relative_to(ROOT)
            shutil.copytree(COMPONENT, component)
            shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
            command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
            subprocess.run(command, check=True, capture_output=True)
            candidate = (root / CPP).read_text()
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual((root / CPP).read_text(), candidate)
            self.assertIn('DeviceConnectionType::BUILT_IN', candidate)
            self.assertIn('DeviceConnectionType::EXTERNAL', candidate)


if __name__ == '__main__':
    unittest.main()
