"""Exact-source guard and EOS-branch host model tests, not media API acceptance."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/foundation/multimedia/av_codec/avc_eos'
spec = importlib.util.spec_from_file_location('avc_eos_source', COMPONENT / 'verify_source.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def fixture_source():
    return '\n'.join(old for old, _ in source.REPLACEMENTS + source.INPUT_REPLACEMENTS)


class AvcEosTests(unittest.TestCase):
    def test_exact_transform_requires_each_unique_original_structure(self):
        original = fixture_source()
        fixed = source.repaired_source(original)
        for old, new in source.REPLACEMENTS + source.INPUT_REPLACEMENTS:
            self.assertIn(new, fixed)
            with self.assertRaises(ValueError): source.repaired_source(original.replace(old, 'unknown'))
            with self.assertRaises(ValueError): source.repaired_source(original + old)
        self.assertIn('state_ != State::ERROR', fixed)

    def test_guard_accepts_only_exact_original_or_known_patch(self):
        original = fixture_source()
        fixed = source.repaired_source(original)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'foundation/multimedia/av_codec' / source.FILE
            target.parent.mkdir(parents=True)
            for current, accepted, patched in ((original, True, False),
                                               (source.repaired_source(original, False), True, False),
                                               (fixed, True, True),
                                               (fixed + '// unknown edit', False, False)):
                target.write_text(current)
                with patch.object(source.subprocess, 'check_output', side_effect=[source.REVISION + '\n', original.encode()]):
                    if accepted: self.assertEqual(source.validate(root), patched)
                    else:
                        with self.assertRaises(ValueError): source.validate(root)
                self.assertEqual(target.read_text(), current)
            target.write_text(original)
            with patch.object(source.subprocess, 'check_output', side_effect=[source.REVISION + '\n', original.encode()]):
                with self.assertRaises(ValueError): source.validate(root, True)

    def test_other_revision_is_rejected_before_source_read(self):
        with patch.object(source.subprocess, 'check_output', return_value='master\n'):
            with self.assertRaises(ValueError): source.validate(Path('/fixture'))

    def test_partial_input_changes_and_linked_source_preserve_input(self):
        original = fixture_source()
        eos = source.repaired_source(original, False)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'foundation/multimedia/av_codec' / source.FILE
            target.parent.mkdir(parents=True)
            for old, new in source.INPUT_REPLACEMENTS:
                partial = eos.replace(old, new)
                target.write_text(partial)
                with patch.object(source.subprocess, 'check_output', side_effect=[source.REVISION + '\n', original.encode()]):
                    with self.assertRaises(ValueError): source.validate(root)
                self.assertEqual(target.read_text(), partial)
            other = root / 'linked-input.cpp'
            other.write_text(source.repaired_source(original))
            target.unlink()
            target.symlink_to(other)
            with patch.object(source.subprocess, 'check_output', side_effect=[source.REVISION + '\n', original.encode()]):
                with self.assertRaises(ValueError): source.validate(root)
            self.assertTrue(target.is_symlink())

    def test_real_input_size_and_stride_branches_with_sanitizers(self):
        compiler = shutil.which('clang++')
        if compiler is None: self.skipTest('clang++ required for actual branch sanitizer test')
        functions = []
        for name, index in (('Legacy', 0), ('Fixed', 1)):
            check = source.INPUT_REPLACEMENTS[0][index].replace('AvcEncoder::CheckBufferSize', name)
            conversion = source.INPUT_REPLACEMENTS[1][index]
            input_stride = source.INPUT_REPLACEMENTS[2][index]
            functions += [check, 'int ' + name + 'ConversionStride(int incoming, bool surface) {\n'
                          'int marker = 1; int *inputSurface_ = surface ? &marker : nullptr;\n'
                          '(void)inputSurface_; Frame inFrame{incoming};\n' + conversion + 'return stride;\n}\n',
                          'int ' + name + 'InputStride(VideoPixelFormat srcPixelFmt_, int encWidth_) {\n'
                          '(void)srcPixelFmt_; Frame inFrame{};\n' + input_stride + 'return inFrame.stride;\n}\n']
        code = '''#include <cassert>
#include <cstdint>
#include <climits>
#define AVCODEC_LOGE(...) ((void)0)
constexpr int AVCS_ERR_OK = 0;
constexpr int AVCS_ERR_UNSUPPORT_SOURCE = -11;
constexpr int EVEN_NUMBER_DIVISOR = 2;
constexpr int RGBA_COLINC = 4;
enum class VideoPixelFormat { RGBA, YUVI420, NV12, NV21, UNKNOWN };
struct Frame { int stride; };
''' + ''.join(functions) + '''int main() {
using P = VideoPixelFormat;
const int rgbStride = FixedInputStride(P::RGBA, 64);
assert(rgbStride == 256 && LegacyInputStride(P::RGBA, 64) == 64);
// The real original byte-mode path accepts less than a complete RGBA frame.
assert(Legacy(16383, LegacyInputStride(P::RGBA, 64), 64, P::RGBA) == 0);
assert(Fixed(16383, rgbStride, 64, P::RGBA) == -11);
assert(Fixed(16384, rgbStride, 64, P::RGBA) == 0);
assert(FixedConversionStride(rgbStride, false) == 64);
assert(FixedConversionStride(rgbStride, true) == 64);
assert(LegacyConversionStride(64, false) == 64);
assert(LegacyConversionStride(256, true) == 64);
for (P p : {P::YUVI420, P::NV12, P::NV21}) {
    assert(FixedInputStride(p, 64) == 64);
    assert(Fixed(6144, 64, 64, p) == 0);
    assert(Fixed(6143, 64, 64, p) == -11);
    assert(Fixed(INT_MAX, INT_MAX - 1, INT_MAX - 1, p) == -11);
    assert(Fixed(INT_MAX, 65, 64, p) == -11);
}
for (P p : {P::RGBA, P::YUVI420, P::NV12, P::NV21}) {
    assert(Fixed(0, 64, 64, p) == -11);
    assert(Fixed(-1, 64, 64, p) == -11);
    assert(Fixed(INT_MAX, 0, 64, p) == -11);
    assert(Fixed(INT_MAX, -1, 64, p) == -11);
    assert(Fixed(INT_MAX, 64, 0, p) == -11);
    assert(Fixed(INT_MAX, 64, -1, p) == -11);
    assert(Fixed(INT_MAX, 64, 63, p) == -11);
}
assert(Fixed(INT_MAX, INT_MAX - 3, INT_MAX - 1, P::RGBA) == -11);
assert(Fixed(INT_MAX, 254, 64, P::RGBA) == -11);
assert(Fixed(8, 4, 2, P::RGBA) == 0);
assert(Fixed(7, 4, 2, P::RGBA) == -11);
assert(Fixed(INT_MAX, 64, 64, P::UNKNOWN) == -11);
}
'''
        code = '#include <initializer_list>\n' + code
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / 'actual-input-branches.cpp'
            candidate.write_text(code)
            binary = root / 'actual-input-branches'
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(candidate), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)

    def test_eos_precedes_backend_and_both_precede_traversal(self):
        builder = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        eos = builder.index('bash "${AVC_EOS_COMPONENT_SCRIPT}"')
        backend = builder.index('bash "${SOFTWARE_AVC_COMPONENT_SCRIPT}"')
        metadata = builder.index('  write_source_preparation_metadata')
        self.assertLess(eos, backend)
        self.assertLess(backend, metadata)
        backend_script = (COMPONENT.parent / 'software_avc/apply.sh').read_text()
        self.assertIn('avc_eos/verify_source.py', backend_script)
        self.assertIn('--require-patched', backend_script)

    def test_actual_replacement_branch_resets_size_pts_and_rejects_failure(self):
        compiler = shutil.which('clang++')
        if compiler is None: self.skipTest('clang++ required for host branch sanitizer test')
        functions = []
        for name, branch in (('Legacy', source.REPLACEMENTS[0][0]), ('Fixed', source.REPLACEMENTS[0][1])):
            functions.append('int ' + name + '(bool isSendEos_, int ret, Args outArgs, Buffer *outputAVBuffer) {\n'
                             '(void)ret;(void)outArgs;\n' + branch + '}\nreturn 0;\n}\n')
        code = '''#include <cassert>
#include <cstdint>
#define AVCS_ERR_VID_ENC_FAILED (-7)
#define AVCODEC_BUFFER_FLAG_EOS 1
#define CHECK_AND_RETURN_RET_LOG(condition, error, ...) do { if (!(condition)) return error; } while (0)
struct Memory { unsigned size = 55; void SetSize(unsigned next) { size = next; } };
struct Buffer { Memory *memory_; int64_t pts_ = 69; int flag_ = 0; };
struct Args { unsigned bytes; uint64_t timestamp; };
''' + ''.join(functions) + '''int main() {
Memory memory; Buffer buffer{&memory}; Args eos{0, 0};
assert(Legacy(true, 0, eos, &buffer) == 0 && memory.size == 55 && buffer.pts_ == 69);
buffer.flag_ = 0;
assert(Legacy(true, 1, eos, &buffer) == 0 && buffer.flag_ == 1);
buffer.flag_ = 0;
assert(Fixed(true, 1, eos, &buffer) == -7 && buffer.flag_ == 0 && memory.size == 55 && buffer.pts_ == 69);
assert(Fixed(true, 0, eos, &buffer) == 0 && buffer.flag_ == 1 && memory.size == 0 && buffer.pts_ == 0);
Args delayed{128, 123456789};
assert(Fixed(true, 0, delayed, &buffer) == 0 && memory.size == 128 && buffer.pts_ == 123456789);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / 'eos-model.cpp'
            candidate.write_text(code)
            binary = root / 'eos-model'
            subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(candidate), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
