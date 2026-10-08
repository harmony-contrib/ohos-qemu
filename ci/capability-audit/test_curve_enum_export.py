"""Actual registration logic with mock JS allocation; no interpolation/guest claim."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run, patch_sections, write_preimages

ROOT=Path(__file__).resolve().parents[2]
COMPONENT=ROOT/'patches/common/foundation/arkui/ace_engine/api26_curve_enum'
PATCH=COMPONENT/'0001-export-existing-curve-string-contract.patch'
NAMES=["Linear","Ease","EaseIn","EaseOut","EaseInOut","FastOutSlowIn","LinearOutSlowIn","FastOutLinearIn","ExtremeDeceleration","Sharp","Rhythm","Smooth","Friction"]
VALUES=['linear','ease','ease-in','ease-out','ease-in-out','fast-out-slow-in',
        'linear-out-slow-in','fast-out-linear-in','extreme-deceleration','sharp','rhythm','smooth','friction']
CONSTANTS=["LINEAR","EASE","EASE_IN","EASE_OUT","EASE_IN_OUT","FAST_OUT_SLOW_IN","LINEAR_OUT_SLOW_IN","FAST_OUT_LINEAR_IN","EXTREME_DECELERATION","SHARP","RHYTHM","SMOOTH","FRICTION"]


class CurveExportTests(unittest.TestCase):
    def test_actual_helper_all_members_every_failure_and_no_retained_objects(self):
        functions=[]
        for hunks in patch_sections(PATCH).values():
            for _,_,lines in hunks:
                for index,line in enumerate(lines):
                    if line.startswith('static bool RegisterPublicCurveEnum('):
                        functions.append('\n'.join(lines[index:lines.index('}',index)+1]))
        self.assertEqual(len(functions),1)
        constants='\n'.join('const char DOM_ANIMATION_TIMING_FUNCTION_'+name+'[]="'+value+'";'
                            for name,value in zip(CONSTANTS,VALUES))
        declarations=r"""
#include <cassert>
#include <map>
#include <memory>
#include <string>
#include <vector>
using std::shared_ptr;
struct JsRuntime;
int calls=0,failure=0;
bool wrapped=false;
struct JsValue {
 static int alive;
 std::string kind,value;
 std::map<std::string,shared_ptr<JsValue>> own;
 explicit JsValue(std::string k):kind(k){++alive;}
 ~JsValue(){--alive;}
 bool IsObject(shared_ptr<JsRuntime>){return kind=="object";}
 bool IsString(shared_ptr<JsRuntime>){return kind=="string";}
 bool SetProperty(shared_ptr<JsRuntime>,const std::string& key,const shared_ptr<JsValue>& item){
  if(++calls==failure)return false;
  assert(own.emplace(key,item).second);return true;
 }
};
int JsValue::alive=0;
struct JsRuntime {
 shared_ptr<JsValue> Allocate(const std::string& kind){
  if(++calls==failure)return wrapped?std::make_shared<JsValue>("exception"):nullptr;
  return std::make_shared<JsValue>(kind);
 }
 shared_ptr<JsValue> NewObject(){return Allocate("object");}
 shared_ptr<JsValue> NewString(const std::string& text){
  auto item=Allocate("string");if(item)item->value=text;return item;
 }
};
"""
        main=r"""
int main(){
 const std::vector<std::string> names={__NAMES__};
 const std::vector<std::string> values={__VALUES__};
 auto runtime=std::make_shared<JsRuntime>();
 for(unsigned repeat=0;repeat<128;++repeat)for(int type=0;type<2;++type){
  wrapped=type;
  for(failure=0;failure<=28;++failure){
   calls=0;{
    auto exports=std::make_shared<JsValue>("object");
    auto sentinel=std::make_shared<JsValue>("function");
    exports->own.emplace("initCurve",sentinel);
    const bool success=RegisterPublicCurveEnum(runtime,exports);
    if(failure){
     assert(!success && calls==failure && exports->own.size()==1 && !exports->own.count("Curve"));
    }else{
     assert(success && calls==28 && exports->own.size()==2);
     const auto object=exports->own.at("Curve");
     assert(object->own.size()==13);
     for(size_t i=0;i<13;++i){
      assert(object->own.at(names[i])->kind=="string" && object->own.at(names[i])->value==values[i]);
     }
    }
    assert(exports->own.at("initCurve")==sentinel);
   }assert(JsValue::alive==0);
  }
 }
}
""".replace('__NAMES__',','.join('"'+value+'"' for value in NAMES)).replace(
    '__VALUES__',','.join('"'+value+'"' for value in VALUES))
        compile_run(declarations+constants+functions[0]+main,language='c++')

    def test_component_twice_reverse_and_failed_initializer_returns_null(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);write_preimages(root,PATCH)
            for _ in range(2):
                result=subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(root)],
                                      capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            subprocess.run(['git','-C',str(root),'apply','--check','--reverse',str(PATCH)],check=True)
        text=PATCH.read_text()
        self.assertIn('if (!RegisterPublicCurveEnum(runtime, moduleObj)) {\n'
                      '+        moduleObj = runtime->NewNull();\n+        return;',text)
        self.assertNotIn('GetGlobal',text)
        self.assertNotIn('NewNumber',text)
        self.assertNotIn('NewInt32',text)


if __name__=='__main__':unittest.main()

