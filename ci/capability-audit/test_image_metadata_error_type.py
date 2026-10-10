"""Only the approved ByType parameter error opts in to existing BusinessError encoding."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/image_framework/metadata_error_type'
RELATIVE = 'foundation/multimedia/image_framework/frameworks/kits/js/common/image_source_napi.cpp'
ORIGINAL = '''    napi_get_undefined(env, &result);
    napi_status status;
    std::unique_ptr<ImageSourceAsyncContext> asyncContext = UnwrapContextForReadImageMetadataByType(env, info);
    if (asyncContext == nullptr) {
        return ImageNapiUtils::ThrowExceptionError(env, IMAGE_SOURCE_INVALID_PARAMETER, "async context unwrap failed");
    }

    if (asyncContext->callbackRef == nullptr) {
'''


class ImageMetadataErrorTypeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='qemu-image-error-type-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / RELATIVE
        self.target.parent.mkdir(parents=True)
        self.target.write_text(ORIGINAL)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_only_bytype_opt_in_and_idempotence(self):
        legacy = ORIGINAL.replace('UnwrapContextForReadImageMetadataByType', 'UnwrapContextForReadImageMetadata')
        self.target.write_text(legacy + ORIGINAL)
        expected = ORIGINAL.replace('IMAGE_SOURCE_INVALID_PARAMETER, "async context unwrap failed");',
            'IMAGE_SOURCE_INVALID_PARAMETER,\n            "async context unwrap failed", true);')
        for _ in range(2):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.target.read_text(), legacy + expected)

    def test_drift_rejected_even_after_previous_application(self):
        self.assertEqual(self.apply().returncode, 0)
        self.target.write_text(self.target.read_text().replace('failed", true', 'failed", false'))
        self.assertNotEqual(self.apply().returncode, 0)

    def test_compiled_call_preserves_code_message_and_selects_numeric_encoding(self):
        self.assertEqual(self.apply().returncode, 0)
        branch = self.target.read_text().split('    if (asyncContext == nullptr) {', 1)[1].split('\n    }', 1)[0]
        source = self.root / 'error.cpp'
        source.write_text('''#include <cassert>
#include <cstdint>
#include <string>
constexpr int32_t IMAGE_SOURCE_INVALID_PARAMETER = 7700204;
struct ImageNapiUtils {
    static int ThrowExceptionError(int, int32_t code, const std::string& message, bool number = false) {
        assert(code == 7700204 && message == "async context unwrap failed");
        return number ? 1 : 0;
    }
};
int parameterError(int env) {
''' + branch + '''
}
int main() {
    assert(parameterError(0) == 1);
    assert(ImageNapiUtils::ThrowExceptionError(0, 7700204, "async context unwrap failed") == 0);
}
''')
        binary = self.root / 'error'
        subprocess.run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)],
                       check=True, capture_output=True, text=True)
        subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_shared_build_and_real_runtime_boundary_tests(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('image_framework/metadata_error_type/apply.sh', recipe)
        self.assertIn('bash "${IMAGE_METADATA_ERROR_SCRIPT}" --source-root "${OHOS_ROOT}"', recipe)
        probe = (ROOT / 'ci/capability-audit/image_metadata_probe.ets').read_text()
        for name in ('dng.selected', 'dng.negative', 'dng.after-invalid', 'tiff.end', 'avis.end', 'avis.after-invalid'):
            self.assertIn(name, probe)
        self.assertNotIn('Number((error as BusinessError).code)', probe)
