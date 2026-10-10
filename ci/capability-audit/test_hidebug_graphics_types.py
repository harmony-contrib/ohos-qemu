"""Private NAPI encoding guards; the actual ordinary HAP remains the runtime gate."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/developtools/profiler/hidebug/graphics_memory_types'
RELATIVE = 'developtools/profiler/hidebug/interfaces/js/kits/napi/napi_hidebug.cpp'
ORIGINAL = '''        napi_create_object(env, &ret);
        napi_value gl = nullptr;
        napi_create_int32(env, static_cast<int32_t>(result_->gl), &gl);
        napi_set_named_property(env, ret, "gl", gl);
        napi_value graph = nullptr;
        napi_create_bigint_uint64(env, static_cast<uint64_t>(result_->graph), &graph);
        napi_set_named_property(env, ret, "graph", graph);
'''


class HiDebugGraphicsTypesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='qemu-hidebug-types-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / RELATIVE
        self.target.parent.mkdir(parents=True)
        self.target.write_text(ORIGINAL)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_only_unsigned_number_encoding_and_idempotence(self):
        expected = ORIGINAL.replace('napi_create_int32(env, static_cast<int32_t>(result_->gl), &gl)',
                                    'napi_create_uint32(env, result_->gl, &gl)').replace(
            'napi_create_bigint_uint64(env, static_cast<uint64_t>(result_->graph), &graph)',
            'napi_create_uint32(env, result_->graph, &graph)')
        for _ in range(2):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.target.read_text(), expected)

    def test_drift_and_stale_marker_rejected(self):
        self.assertEqual(self.apply().returncode, 0)
        self.target.write_text(self.target.read_text().replace('napi_create_uint32', 'napi_create_int32'))
        self.assertNotEqual(self.apply().returncode, 0)

    def test_unsigned_upper_half_does_not_become_signed_or_bigint(self):
        self.assertEqual(self.apply().returncode, 0)
        source = self.root / 'encoding.cpp'
        source.write_text('''#include <cassert>
#include <cstdint>
#include <cstring>
struct Value { uint64_t number = 0, gl = 0, graph = 0; };
using napi_value = Value*;
Value object, field;
int napi_create_object(int, napi_value* out) { object = {}; *out = &object; return 0; }
int napi_create_uint32(int, uint32_t value, napi_value* out) { field.number = value; *out = &field; return 0; }
int napi_set_named_property(int, napi_value out, const char* key, napi_value value) {
    if (!std::strcmp(key, "gl")) out->gl = value->number; else out->graph = value->number;
    return 0;
}
struct Summary { uint32_t gl, graph; };
void encode(Summary* result_) {
    int env = 0; napi_value ret = nullptr;
''' + self.target.read_text() + '''}
int main() {
    uint32_t values[] = {0u, 2147483647u, 2147483648u, UINT32_MAX};
    for (uint32_t value : values) {
        Summary input = {value, value}; encode(&input);
        assert(object.gl == value && object.graph == value);
    }
}
''')
        binary = self.root / 'encoding'
        subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)],
                       check=True, capture_output=True, text=True)
        subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_shared_build_wiring(self):
        text = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('hidebug/graphics_memory_types/apply.sh', text)
        self.assertIn('bash "${HIDEBUG_GRAPHICS_TYPES_SCRIPT}" --source-root "${OHOS_ROOT}"', text)
