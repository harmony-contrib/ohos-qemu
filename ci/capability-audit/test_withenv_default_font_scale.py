"""Actual bridge helper with pipeline/value doubles; no runtime or package acceptance."""
import base64
import gzip
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_access_token_kernel import compile_run

ROOT=Path(__file__).resolve().parents[2]
COMPONENT=ROOT/'patches/common/foundation/arkui/ace_engine/withenv_default_font_scale'
spec=importlib.util.spec_from_file_location('withenv_font_baseline',COMPONENT/'verify_source.py')
BASELINE=importlib.util.module_from_spec(spec);spec.loader.exec_module(BASELINE)

DOUBLES=r'''
#include <cassert>
#include <memory>
#include <optional>
#include <string>
template<class T>using RefPtr=std::shared_ptr<T>;
template<class T>struct JSRef;
struct JSVal {
 enum Kind { UNDEFINED,NUMBER,STRING };Kind kind=UNDEFINED;double number=0;std::string text;
 static JSRef<JSVal> Undefined();
};
template<class T>struct JSRef {
 RefPtr<T> value;
 static JSRef Make(const T& value) { return {std::make_shared<T>(value)}; }
 const T* operator->() const { return value.get(); }
};
JSRef<JSVal> JSVal::Undefined() { return JSRef<JSVal>::Make(JSVal{}); }
JSVal ToJSValue(double value) { return {JSVal::NUMBER,value,{}}; }
JSVal ToJSValue(const std::string& value) { return {JSVal::STRING,0,value}; }
enum class TextDirection { LTR,RTL,AUTO };
namespace NG {
const std::string ENV_KEY_DIRECTION="system.arkui.layout.direction",ENV_KEY_FONT_SCALE="system.arkui.fontScale";
struct SystemEnvValue {
 std::optional<TextDirection> direction;std::optional<double> number;
 std::optional<TextDirection> GetDirection() const { return direction; }
 std::optional<double> GetDouble() const { return number; }
};
struct Pipeline { double scale=1;double GetFontScale() const { return scale; } };
struct UINode { RefPtr<Pipeline> pipeline;RefPtr<Pipeline> GetContext() const { return pipeline; } };
}
#define CHECK_NULL_RETURN(value,result) do { if(!(value))return result; }while(0)
'''


def helper(text):
    start=text.index('std::optional<JSRef<JSVal>> MakeSystemEnvValue(');body=text.index('{',start);depth=0
    for index in range(body,len(text)):
        if text[index]=='{':depth+=1
        elif text[index]=='}':
            depth-=1
            if depth==0:return text[start:index+1]+'\n'
    raise ValueError('complete original native helper required')


class WithEnvFontTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);relative,original,_=BASELINE.FILES[0]
        raw=gzip.decompress(base64.b64decode((ROOT/'ci/capability-audit/fixtures/js_view_withenv_font.cpp.gz.b64').read_bytes()))
        self.assertEqual(hashlib.sha256(raw).hexdigest(),original)
        self.target=self.root/BASELINE.PROJECT/relative;self.target.parent.mkdir(parents=True);self.target.write_bytes(raw)

    def apply(self):
        return subprocess.run(['bash',str(COMPONENT/'apply.sh'),'--source-root',str(self.root)],capture_output=True,text=True)

    def test_original_unconfigured_font_has_no_public_value(self):
        compile_run(DOUBLES+helper(self.target.read_text())+r'''
int main(){assert(!MakeSystemEnvValue(NG::ENV_KEY_FONT_SCALE,std::nullopt));}
''',language='c++')

    def test_repaired_helper_uses_each_owning_pipeline_and_preserves_override_and_type_boundaries(self):
        self.assertEqual(self.apply().returncode,0)
        compile_run(DOUBLES+helper(self.target.read_text())+r'''
int main(){
 for(double scale:{0.7,1.0,1.5,2.0}){
  auto node=std::make_shared<NG::UINode>();node->pipeline=std::make_shared<NG::Pipeline>();node->pipeline->scale=scale;
  auto actual=MakeSystemEnvValue(NG::ENV_KEY_FONT_SCALE,std::nullopt,node);
  assert(actual&&actual->value->kind==JSVal::NUMBER&&actual->value->number==scale);
  for(double overrideValue:{0.0,0.8,1.0,1.7}){
   NG::SystemEnvValue provided;provided.number=overrideValue;
   auto overrideResult=MakeSystemEnvValue(NG::ENV_KEY_FONT_SCALE,provided,node);
   assert(overrideResult&&overrideResult->value->kind==JSVal::NUMBER&&overrideResult->value->number==overrideValue);
  }
  NG::SystemEnvValue wrongType;wrongType.direction=TextDirection::LTR;
  auto rejected=MakeSystemEnvValue(NG::ENV_KEY_FONT_SCALE,wrongType,node);
  assert(rejected&&rejected->value->kind==JSVal::UNDEFINED);
  for(auto direction:{TextDirection::LTR,TextDirection::RTL,TextDirection::AUTO}){
   NG::SystemEnvValue provided;provided.direction=direction;
   auto result=MakeSystemEnvValue(NG::ENV_KEY_DIRECTION,provided,node);
   assert(result&&result->value->kind==JSVal::STRING);
   assert(result->value->text==(direction==TextDirection::LTR?"Ltr":direction==TextDirection::RTL?"Rtl":"Auto"));
  }
  assert(MakeSystemEnvValue(NG::ENV_KEY_DIRECTION,std::nullopt,node)->value->text=="Auto");
  assert(!MakeSystemEnvValue("unknown.key",std::nullopt,node));
 }
 assert(!MakeSystemEnvValue(NG::ENV_KEY_FONT_SCALE,std::nullopt,nullptr));
 auto detached=std::make_shared<NG::UINode>();assert(!MakeSystemEnvValue(NG::ENV_KEY_FONT_SCALE,std::nullopt,detached));
}
''',language='c++')

    def test_queries_and_override_removal_notifications_bind_the_actual_view_node(self):
        self.assertEqual(self.apply().returncode,0);text=self.target.read_text()
        self.assertEqual(text.count('MakeSystemEnvValue(key, queryValue, node)'),1)
        self.assertEqual(text.count('MakeSystemEnvValue(key, value, AceType::DynamicCast<NG::UINode>(self->GetViewNode()))'),1)
        self.assertEqual(self.apply().returncode,0);expected=self.target.read_bytes()
        self.target.write_bytes(expected+b'unknown mutation\n');self.assertNotEqual(self.apply().returncode,0)
        self.assertEqual(self.target.read_bytes(),expected+b'unknown mutation\n')


if __name__=='__main__':unittest.main()
