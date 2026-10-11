"""Execute patched cache/constructor code with NAPI lifecycle failure fixtures."""
from pathlib import Path
import unittest

from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/image_framework/tiff_dng_class_exports'

STUB = r"""
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <new>
#include <string>
#include <vector>
struct Env;
struct Value;
struct CallbackInfo { Value* target = nullptr; Value* self = nullptr; };
using napi_env = Env*;
using napi_value = Value*;
using napi_callback_info = CallbackInfo*;
using Callback = Value* (*)(Env*, CallbackInfo*);
struct Value {
    std::string name;
    Callback callback = nullptr;
    Value* prototype = nullptr;
    std::map<std::string, Value*> fields;
};
struct Ref { Env* owner; Value* value; bool deleted = false; };
using napi_ref = Ref*;
enum napi_status { napi_ok, napi_generic_failure };
struct Env {
    bool failHook = false, failDefine = false, failReference = false, failInstance = false;
    int hookCount = 0, deletes = 0, typeErrors = 0;
    std::vector<std::unique_ptr<Value>> values;
    std::vector<std::unique_ptr<Ref>> refs;
    std::vector<std::pair<void (*)(void*), void*>> hooks;
    Value* make() { values.emplace_back(new Value); return values.back().get(); }
    void close() { auto pending = std::move(hooks); for (auto h : pending) h.first(h.second); }
};
constexpr size_t NAPI_AUTO_LENGTH = static_cast<size_t>(-1);
#define IMAGE_LOGE(...) ((void)0)
napi_status napi_add_env_cleanup_hook(Env* e, void (*hook)(void*), void* context) {
    if (e->failHook) return napi_generic_failure;
    ++e->hookCount; e->hooks.emplace_back(hook, context); return napi_ok;
}
napi_status napi_delete_reference(Env* e, Ref* r) {
    assert(r && r->owner == e && !r->deleted);
    r->deleted = true; ++e->deletes; return napi_ok;
}
napi_status napi_get_reference_value(Env* e, Ref* r, Value** out) {
    assert(r && r->owner == e && !r->deleted); *out = r->value; return napi_ok;
}
napi_status napi_get_new_target(Env*, CallbackInfo* i, Value** out) {
    *out = i->target; return napi_ok;
}
napi_status napi_get_cb_info(Env*, CallbackInfo* i, size_t*, Value**, Value** self, void**) {
    *self = i->self; return napi_ok;
}
napi_status napi_throw_type_error(Env* e, const char*, const char*) {
    ++e->typeErrors; return napi_ok;
}
napi_status napi_define_class(Env* e, const char* name, size_t, Callback cb,
    void*, size_t count, const void* props, Value** out) {
    assert(count == 0 && !props);
    if (e->failDefine) return napi_generic_failure;
    auto value = e->make(); value->name = name; value->callback = cb; *out = value; return napi_ok;
}
napi_status napi_create_reference(Env* e, Value* value, int count, Ref** out) {
    assert(count == 1);
    if (e->failReference) return napi_generic_failure;
    e->refs.emplace_back(new Ref{e, value}); *out = e->refs.back().get(); return napi_ok;
}
napi_status napi_set_named_property(Env*, Value* object, const char* name, Value* value) {
    object->fields[name] = value; return napi_ok;
}
napi_status napi_new_instance(Env* e, Value* ctor, size_t count, Value** args, Value** out) {
    assert(count == 0 && !args);
    if (e->failInstance) return napi_generic_failure;
    auto value = e->make(); value->prototype = ctor;
    CallbackInfo info{ctor, value}; *out = ctor->callback(e, &info); return napi_ok;
}
napi_status napi_get_undefined(Env*, Value** out) { *out = nullptr; return napi_ok; }
struct MetadataNapi { static Value* InitRecordMetadata(Env*, Value*); };
"""

MAIN = r"""
int main() {
    Env first, second;
    auto a = first.make(); auto b = second.make();
    MetadataNapi::InitRecordMetadata(&first, a);
    MetadataNapi::InitRecordMetadata(&second, b);
    assert(a->fields.size() == 2 && b->fields.size() == 2);
    assert(a->fields["DngMetadata"] != b->fields["DngMetadata"]);
    auto dng = CreateRecordMetadata(&first, true);
    auto tiff = CreateRecordMetadata(&first, false);
    assert(dng && tiff && dng != tiff);
    assert(dng->prototype == a->fields["DngMetadata"] && dng->fields.empty());
    assert(tiff->prototype == a->fields["TiffMetadata"] && tiff->fields.empty());
    auto another = CreateRecordMetadata(&first, true);
    assert(another != dng && another->prototype == dng->prototype);
    MetadataNapi::InitRecordMetadata(&first, a);
    assert(first.hookCount == 1 && first.refs.size() == 2);
    CallbackInfo call{nullptr, a};
    assert(RecordMetadataConstructor(&first, &call) == nullptr && first.typeErrors == 1);
    first.close();
    assert(first.deletes == 2 && recordConstructors.count(&first) == 0);
    assert(CreateRecordMetadata(&second, true)->prototype == b->fields["DngMetadata"]);
    // Reuse the same address to model a new worker environment on one thread.
    auto rebound = first.make();
    MetadataNapi::InitRecordMetadata(&first, rebound);
    assert(rebound->fields["DngMetadata"] != a->fields["DngMetadata"]);
    assert(first.hookCount == 2 && first.refs.size() == 4);
    first.close(); second.close();
    assert(first.deletes == 4 && second.deletes == 2 && recordConstructors.empty());
    for (int failure = 0; failure < 4; ++failure) {
        Env e;
        e.failHook = failure == 0; e.failDefine = failure == 1;
        e.failReference = failure == 2; e.failInstance = failure == 3;
        assert(CreateRecordMetadata(&e, true) == nullptr);
        e.failHook = e.failDefine = e.failReference = e.failInstance = false;
        auto exports = e.make();
        MetadataNapi::InitRecordMetadata(&e, exports);
        assert(CreateRecordMetadata(&e, true)->prototype == exports->fields["DngMetadata"]);
        e.close();
        assert(e.deletes == 2 && recordConstructors.empty());
    }
}
"""


class TiffDngClassTests(unittest.TestCase):
    def test_actual_code_environment_isolation_cleanup_reuse_and_napi_failures(self):
        sections = patch_sections(COMPONENT / '0001-register-environment-owned-metadata-record-classes.patch')
        target = next(name for name in sections if name.endswith('/metadata_napi.cpp'))
        added = '\n'.join('\n'.join(after) for _, _, after in sections[target])
        actual = added.split('namespace {\nstruct RecordMetadataConstructors', 1)[1]
        actual = 'namespace {\nstruct RecordMetadataConstructors' + actual.split(
            'napi_value MetadataNapi::CreateDngMetadata', 1)[0]
        compile_run(STUB + actual + MAIN, language='c++')

    def test_shared_build_and_actual_parsed_instance_proof(self):
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(script.count('bash "${IMAGE_RECORD_CLASSES_SCRIPT}" --source-root'), 1)
        probe = (ROOT / 'ci/capability-audit/image_metadata_probe.ets').read_text()
        for name in ('DngMetadata', 'TiffMetadata'):
            self.assertEqual(probe.count('new image.' + name + '()'), 3)
            self.assertIn('value instanceof image.' + name, probe)


if __name__ == '__main__':
    unittest.main()
