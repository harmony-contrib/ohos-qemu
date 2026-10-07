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
    return '\n'.join(old for old, _ in source.REPLACEMENTS)


class AvcEosTests(unittest.TestCase):
    def test_exact_transform_requires_each_unique_original_structure(self):
        original = fixture_source()
        fixed = source.repaired_source(original)
        for old, new in source.REPLACEMENTS:
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
            for current, accepted, patched in ((original, True, False), (fixed, True, True),
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
