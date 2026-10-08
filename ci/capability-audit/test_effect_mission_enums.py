"""Exact native bindings only: no image or peer/image-classification behavior claim."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT=Path(__file__).resolve().parents[2]
PLAN=(
    ('foundation/graphic/graphic_2d/effect_kit/api26_light_degree', '0001-register-existing-public-picture-light-degree.patch', 'RegisterPictureLightDegree'),
    ('foundation/ability/ability_runtime/api26_mission_state', '0001-register-existing-public-mission-state.patch', 'RegisterContinueState'),
)


class EffectMissionEnumTests(unittest.TestCase):
    def test_each_native_value_every_napi_error_and_repeated_initialization(self):
        functions=[]
        for relative,filename,name in PLAN:
            for hunks in patch_sections(ROOT/'patches/common'/relative/filename).values():
                for _,_,lines in hunks:
                    for i,line in enumerate(lines):
                        if line.startswith('static napi_status '+name+'('):
                            functions.append('\n'.join(lines[i:lines.index('}',i)+1]))
        self.assertEqual(len(functions),2)
        source=r"""
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>
enum PictureLightColorDegree { UNKOWN_LIGHT_COLOR_DEGREE_PICTURE=0,
 EXTREMELY_LIGHT_COLOR_PICTURE=1, LIGHT_COLOR_PICTURE=2, DARK_COLOR_PICTURE=3,
 EXTREMELY_DARK_COLOR_PICTURE=4, FLOWERY_PICTURE=5, EXTREMELY_FLOWERY_PICTURE=6 };
enum ContinueState { CONTINUESTATE_UNKNOWN=-1, CONTINUESTATE_ACTIVE=0, CONTINUESTATE_INACTIVE=1, CONTINUESTATE_MAX=2 };
struct Value { int32_t number=0; std::map<std::string,Value*> own; };
using napi_env=void*; using napi_value=Value*;
enum napi_status { napi_ok=0, napi_generic_failure=9 };
int calls=0,failure=0;
std::vector<std::unique_ptr<Value>> storage;
Value* Make(){ storage.push_back(std::make_unique<Value>()); return storage.back().get(); }
napi_status Step(){return ++calls==failure ? napi_generic_failure : napi_ok;}
napi_status napi_create_object(napi_env,Value** value){
 auto status=Step();if(status==napi_ok)*value=Make();return status;}
napi_status napi_create_int32(napi_env,int32_t number,Value** value){
 auto status=Step();if(status==napi_ok){*value=Make();(*value)->number=number;}return status;}
napi_status napi_set_named_property(napi_env,Value* object,const char* name,Value* value){
 auto status=Step();if(status==napi_ok)assert(object->own.emplace(name,value).second);return status;}
"""
        main=r"""
int main(){
 const std::vector<std::string> degree={"UNKNOWN_LIGHT_COLOR_DEGREE_PICTURE",
  "EXTREMELY_LIGHT_COLOR_PICTURE","LIGHT_COLOR_PICTURE","DARK_COLOR_PICTURE",
  "EXTREMELY_DARK_COLOR_PICTURE","FLOWERY_PICTURE","EXTREMELY_FLOWERY_PICTURE"};
 for(unsigned repeat=0;repeat<128;++repeat)for(int kind=0;kind<2;++kind){
  const int steps=kind==0?16:6;
  for(failure=0;failure<=steps;++failure){
   calls=0;auto exports=Make();
   auto status=kind==0?RegisterPictureLightDegree(nullptr,exports):RegisterContinueState(nullptr,exports);
   if(failure){assert(status==napi_generic_failure && calls==failure);continue;}
   assert(status==napi_ok && calls==steps && exports->own.size()==1);
   if(kind==0){
    auto object=exports->own.at("PictureLightDegree");assert(object->own.size()==degree.size());
    for(size_t i=0;i<degree.size();++i)assert(object->own.at(degree[i])->number==static_cast<int32_t>(i));
    assert(!object->own.count("UNKOWN_LIGHT_COLOR_DEGREE_PICTURE"));
   }else{
    auto object=exports->own.at("ContinueState");assert(object->own.size()==2);
    assert(object->own.at("ACTIVE")->number==0 && object->own.at("INACTIVE")->number==1);
    assert(!object->own.count("UNKNOWN") && !object->own.count("MAX"));
   }
  }
 }
}
"""
        compile_run(source+'\n'.join(functions)+main,language='c++')

    def test_every_component_applies_twice_with_real_crlf_and_lf_preimages(self):
        for relative,filename,name in PLAN:
            component=ROOT/'patches/common'/relative
            patch=component/filename
            for crlf in (False,True):
                with self.subTest(relative=relative,crlf=crlf),tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);write_preimages(root,patch)
                    if crlf:
                        for path in root.rglob('*.cpp'):
                            path.write_bytes(path.read_bytes().replace(b'\n',b'\r\n'))
                    for _ in range(2):
                        result=subprocess.run(['bash',str(component/'apply.sh'),'--source-root',str(root)],
                                              capture_output=True,text=True)
                        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    subprocess.run(['git','-C',str(root),'apply','--check','--reverse',
                                    '--ignore-space-change',str(patch)],check=True)
            self.assertIn('if ('+name+'(env, exports) != napi_ok) {\n+        return nullptr;',patch.read_text())


if __name__=='__main__':unittest.main()
