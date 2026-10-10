"""Exercise actual registration bodies with explicit host NAPI doubles."""
from pathlib import Path
import unittest

from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/contacts_data/record_classes'
PATCH = COMPONENT / '0001-register-public-contact-record-classes.patch'


class ContactRecordClassesTests(unittest.TestCase):
    def test_real_registration_all_failure_points_and_holder_default(self):
        sections = patch_sections(PATCH)
        header = '\n'.join(next(hunks for name, hunks in sections.items()
                                if name.endswith('contacts_record_classes.h'))[0][2])
        header = header.replace('#include "contacts_napi_utils.h"', '')
        harness = r'''
#include <cassert>
#include <cstddef>
#include <map>
#include <memory>
#include <string>
#include <vector>
struct Value;
using napi_env=void*;
using napi_value=Value*;
using napi_callback_info=void*;
using napi_callback=napi_value(*)(napi_env,napi_callback_info);
enum napi_status {napi_ok=0,napi_generic_failure=9};
constexpr size_t NAPI_AUTO_LENGTH=static_cast<size_t>(-1);
struct Value {std::map<std::string,Value*> fields; std::string text; napi_callback callback=nullptr;};
std::vector<std::unique_ptr<Value>> allocations;
int calls=0, failure=0;
Value* Make(){allocations.push_back(std::make_unique<Value>());return allocations.back().get();}
napi_status Step(napi_env env){assert(env==reinterpret_cast<void*>(1));return ++calls==failure?napi_generic_failure:napi_ok;}
napi_status napi_define_class(napi_env env,const char* name,size_t length,napi_callback callback,void* data,
    size_t count,const void* descriptors,napi_value* result){
    assert(length==NAPI_AUTO_LENGTH && !data && count==0 && !descriptors);
    auto status=Step(env); if(status==napi_ok){*result=Make();(*result)->text=name;(*result)->callback=callback;} return status;
}
napi_status napi_set_named_property(napi_env env,napi_value object,const char* name,napi_value value){
    auto status=Step(env); if(status==napi_ok){assert(value);object->fields[name]=value;}return status;
}
napi_status napi_create_string_utf8(napi_env env,const char* value,size_t length,napi_value* result){
    assert(length==NAPI_AUTO_LENGTH);auto status=Step(env);
    if(status==napi_ok){*result=Make();(*result)->text=value;}return status;
}
namespace OHOS {namespace ContactsApi {
constexpr const char* CONTACT_PACKAGE_NAME="com.ohos.contacts";
struct ContactsNapiUtils {static napi_value CreateClassConstructor(napi_env,napi_callback_info info){
    return static_cast<Value*>(info); // explicit host constructor double
}};
}}
'''
        main = r'''
int main(){
    napi_env env=reinterpret_cast<void*>(1);
    const std::vector<std::string> names{"ContactAttributes","Group","Holder","Name","NickName","Note",
                                          "Organization","Portrait","Website"};
    for(int repeat=0;repeat<64;++repeat){
        for(failure=0;failure<=18;++failure){
            allocations.clear();calls=0;auto exports=Make();auto sentinel=Make();exports->fields["existing"]=sentinel;
            auto status=OHOS::ContactsApi::RegisterPublicContactRecords(env,exports);
            assert(status==(failure?napi_generic_failure:napi_ok));assert(calls==(failure?failure:18));
            assert(exports->fields.at("existing")==sentinel);
            if(failure)continue;
            assert(exports->fields.size()==10);
            for(const auto& name:names){
                auto constructor=exports->fields.at(name);assert(constructor->text==name && constructor->callback);
                auto first=Make();auto second=Make();
                assert(constructor->callback(env,first)==first && constructor->callback(env,second)==second);
                assert(first!=second);
                if(name=="Holder"){
                    assert(first->fields.at("bundleName")->text=="com.ohos.contacts");
                    assert(second->fields.at("bundleName")->text=="com.ohos.contacts");
                    assert(first->fields.at("bundleName")!=second->fields.at("bundleName"));
                }else{assert(first->fields.empty() && second->fields.empty());}
            }
        }
    }
    for(failure=1;failure<=2;++failure){
        calls=0;auto record=Make();assert(OHOS::ContactsApi::CreatePublicHolderRecord(env,record)==nullptr);
        assert(calls==failure);
    }
    calls=0;assert(OHOS::ContactsApi::CreatePublicHolderRecord(env,nullptr)==nullptr);assert(calls==0);
}
'''
        compile_run(harness + header + main, language='c++')

    def test_existing_enum_repair_and_database_paths_are_not_modified(self):
        files = set(patch_sections(PATCH))
        self.assertEqual(files, {
            'applications/standard/contacts_data/contacts/include/contacts_record_classes.h',
            'applications/standard/contacts_data/contacts/src/native_module.cpp'})
        self.assertIn('napi_is_exception_pending', PATCH.read_text())
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(recipe.count('bash "${CONTACT_RECORD_CLASSES_SCRIPT}" --source-root'), 1)
        self.assertIn('ContactsNapiUtils::CreateClassConstructor', PATCH.read_text())


if __name__ == '__main__':
    unittest.main()
