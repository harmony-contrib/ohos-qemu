"""Execute the actual export accessor; not a drag backend or guest proof."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/arkui/ace_engine/spring_loading_context'
PATCH = COMPONENT / '0001-export-the-real-frontend-spring-context.patch'


class SpringLoadingContextTests(unittest.TestCase):
    def test_real_identity_late_binding_environment_isolation_and_failures(self):
        sections = patch_sections(PATCH)
        text = '\n'.join('\n'.join(after) for hunks in sections.values() for _, _, after in hunks)
        function = text.split('static napi_value GetSpringLoadingContext', 1)[1].split(
            '\nstatic napi_value DragControllerExport', 1)[0]
        function = 'static napi_value GetSpringLoadingContext' + function
        compile_run(r'''
#include <cassert>
#include <cstring>
enum napi_status { napi_ok, napi_generic_failure };
enum napi_valuetype { napi_undefined, napi_function, napi_object };
struct Value { napi_valuetype type; };
struct Env { Value global{napi_object}; Value absent{napi_undefined}; Value* ctor=&absent;
    int calls=0, fail=0, errors=0; };
using napi_env=Env*; using napi_value=Value*; using napi_callback_info=void*;
#define NAPI_CALL(env, call) do { if ((call) != napi_ok) return nullptr; } while (0)
napi_status Step(Env* e) { return ++e->calls==e->fail ? napi_generic_failure : napi_ok; }
napi_status napi_get_global(Env* e, Value** out) {
    auto s=Step(e); if(s==napi_ok) *out=&e->global; return s; }
napi_status napi_get_named_property(Env* e, Value* value, const char* key, Value** out) {
    assert(value==&e->global && std::strcmp(key,"SpringLoadingContext")==0);
    auto s=Step(e); if(s==napi_ok) *out=e->ctor; return s; }
napi_status napi_typeof(Env* e, Value* value, napi_valuetype* out) {
    auto s=Step(e); if(s==napi_ok) *out=value->type; return s; }
napi_status napi_throw_type_error(Env* e, const char*, const char*) { ++e->errors; return napi_ok; }
''' + function + r'''
int main() {
    Env a,b; Value first{napi_function}, second{napi_function}, bad{napi_object};
    assert(GetSpringLoadingContext(&a,nullptr)==&a.absent);
    a.ctor=&first; b.ctor=&second;
    for(int i=0;i<128;++i) {
        assert(GetSpringLoadingContext(&a,nullptr)==&first);
        assert(GetSpringLoadingContext(&b,nullptr)==&second);
    }
    // Never return or retain a constructor belonging to the other env.
    a.ctor=&a.absent;
    assert(GetSpringLoadingContext(&a,nullptr)==&a.absent);
    assert(GetSpringLoadingContext(&b,nullptr)==&second);
    a.ctor=&bad;
    assert(GetSpringLoadingContext(&a,nullptr)==nullptr && a.errors==1);
    a.ctor=&first;
    assert(GetSpringLoadingContext(&a,nullptr)==&first);
    for(int failure=1;failure<=3;++failure) {
        a.calls=0; a.fail=failure;
        assert(GetSpringLoadingContext(&a,nullptr)==nullptr && a.calls==failure);
        a.calls=0; a.fail=0;
        assert(GetSpringLoadingContext(&a,nullptr)==&first && a.calls==3);
    }
}
''', language='c++')

    def test_read_only_export_shared_build_and_no_replacement_class(self):
        text = PATCH.read_text()
        self.assertIn('{ "SpringLoadingContext", nullptr, nullptr, GetSpringLoadingContext, nullptr, nullptr,', text)
        self.assertIn('napi_enumerable, nullptr }', text)
        for forbidden in ('napi_define_class', 'napi_new_instance', 'napi_create_reference',
                          'SetContext', 'SetSpringLoadingAborted', 'SetDragSpringLoadingConfiguration'):
            self.assertNotIn(forbidden, text)
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(script.count('bash "${SPRING_LOADING_CONTEXT_COMPONENT_SCRIPT}" --source-root'), 1)

    def test_unknown_source_is_preserved_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'foundation/arkui/ace_engine/interfaces/napi/kits/drag_controller/js_drag_controller.cpp'
            source.parent.mkdir(parents=True)
            original = b'// user-owned unknown source\n'
            source.write_bytes(original)
            result = subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', directory],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unknown/incomplete component edit', result.stderr)
            self.assertEqual(source.read_bytes(), original)


if __name__ == '__main__': unittest.main()
