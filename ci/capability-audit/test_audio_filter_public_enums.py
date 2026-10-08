"""Exact registration/failure fixtures; not DSP or rendering acceptance."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = (
    ROOT / 'patches/common/foundation/multimedia/audio_framework/api26_public_enums',
    ROOT / 'patches/common/foundation/graphic/graphic_2d/ui_effect/api26_public_modes',
)


class AudioFilterPublicEnumTests(unittest.TestCase):
    def test_exact_native_values_protocol_values_and_every_registration_error(self):
        functions = []
        for component, name in zip(COMPONENTS, ('RegisterPublicAudioEnums', 'RegisterPublicFilterModes')):
            patch = next(component.glob('*.patch'))
            sections = patch_sections(patch)
            lines = [line for hunks in sections.values() for hunk in hunks for line in hunk[2]]
            start = next(i for i, line in enumerate(lines) if line.startswith('static napi_status ' + name))
            functions.append('\n'.join(lines[start:lines.index('}', start) + 1]))
        source = r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
enum { SELECT_STRATEGY_DEFAULT=0, SELECT_STRATEGY_INDEPENDENT=1, SELECT_STRATEGY_STREAM=2 };
enum { SPATIAL_AUDIO_SOURCE_TYPE_STEREO=0, SPATIAL_AUDIO_SOURCE_TYPE_AUDIO_VIVID=1,
       SPATIAL_AUDIO_SOURCE_TYPE_MULTI_CHANNEL=2, FLAG_SHOW_SYSTEM_UI=1 };
struct Value { int32_t number=0; std::map<std::string,Value*> own; };
using napi_env=void*; using napi_value=Value*;
enum napi_status { napi_ok=0, napi_generic_failure=9 };
int calls=0, failure=0;
std::vector<std::unique_ptr<Value>> storage;
Value* Make() { storage.push_back(std::make_unique<Value>()); return storage.back().get(); }
napi_status Step() { return ++calls==failure ? napi_generic_failure : napi_ok; }
napi_status napi_create_object(napi_env, Value** value) {
    auto status=Step(); if(status==napi_ok) *value=Make(); return status; }
napi_status napi_create_int32(napi_env,int32_t number,Value** value) {
    auto status=Step(); if(status==napi_ok) { *value=Make(); (*value)->number=number; } return status; }
napi_status napi_set_named_property(napi_env,Value* object,const char* name,Value* value) {
    auto status=Step(); if(status==napi_ok) assert(object->own.emplace(name,value).second); return status; }
'''
        main = r'''
int main() {
  for(unsigned repeat=0;repeat<128;++repeat) {
    for(int kind=0;kind<2;++kind) {
      int steps=kind==0 ? 18 : 16;
      for(failure=0;failure<=steps;++failure) {
        auto exports=Make(); calls=0;
        auto status=kind==0 ? RegisterPublicAudioEnums(nullptr,exports) : RegisterPublicFilterModes(nullptr,exports);
        if(failure) { assert(status==napi_generic_failure && calls==failure); continue; }
        assert(status==napi_ok && calls==steps);
        if(kind==0) {
          assert(exports->own.size()==3);
          auto select=exports->own.at("AudioDevcieSelectStrategy"); assert(select->own.size()==2);
          assert(select->own.at("SELECT_STRATEGY_DEFAULT")->number==0);
          assert(select->own.at("SELECT_STRATEGY_INDEPENDENT")->number==1);
          assert(!select->own.count("SELECT_STRATEGY_STREAM"));
          auto spatial=exports->own.at("SpatialAudioSourceType"); assert(spatial->own.size()==3);
          assert(spatial->own.at("SPATIAL_AUDIO_SOURCE_TYPE_STEREO")->number==0);
          assert(spatial->own.at("SPATIAL_AUDIO_SOURCE_TYPE_AUDIO_VIVID")->number==1);
          assert(spatial->own.at("SPATIAL_AUDIO_SOURCE_TYPE_MULTI_CHANNEL")->number==2);
          auto volume=exports->own.at("VolumeFlag"); assert(volume->own.size()==1);
          assert(volume->own.at("FLAG_SHOW_SYSTEM_UI")->number==1);
        } else {
          assert(exports->own.size()==2);
          auto fly=exports->own.at("FlyMode"); assert(fly->own.size()==2);
          assert(fly->own.at("BOTTOM")->number==0 && fly->own.at("TOP")->number==1);
          auto ripple=exports->own.at("WaterRippleMode"); assert(ripple->own.size()==4);
          assert(ripple->own.at("SMALL2MEDIUM_RECV")->number==0);
          assert(ripple->own.at("SMALL2MEDIUM_SEND")->number==1);
          assert(ripple->own.at("SMALL2SMALL")->number==2 && ripple->own.at("MINI_RECV")->number==3);
        }
      }
    }
  }
}
'''
        compile_run(source + '\n'.join(functions) + main, language='c++')

    def test_each_component_applies_twice_and_propagates_new_failure(self):
        for component, name in zip(COMPONENTS, ('RegisterPublicAudioEnums', 'RegisterPublicFilterModes')):
            patch = next(component.glob('*.patch'))
            with self.subTest(component=component), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                write_preimages(root, patch)
                command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
                for _ in range(2):
                    subprocess.run(command, check=True, capture_output=True)
                subprocess.run(['git', '-C', str(root), 'apply', '--check', '--reverse', str(patch)], check=True)
            self.assertIn('if (' + name + '(env, exports) != napi_ok) {\n+        return nullptr;', patch.read_text())


if __name__ == '__main__':
    unittest.main()
