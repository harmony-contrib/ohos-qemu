"""Compile the actual patched parser body with ASan/UBSan; not guest accounting proof."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/base/hiviewdfx/hiview/dmabuf_parser'
RELATIVE = 'base/hiviewdfx/hiview/framework/native/unified_collection/graphic_memory/graphic_memory.cpp'
ORIGINAL = "#include <v1_0/imemory_tracker_interface.h>\nvoid CreateDmaInfo(const std::string &line, std::map<uint64_t, DmaInfo> &dmaInfoMap)\n{\n    DmaInfo dmaInfo;\n    char name[256] = {0}; // 256: max size of name\n    if (sscanf_s(line.c_str(), \"%255s %llu %*llu %llu %llu %*n %*s %*s %*s\",\n                 name, sizeof(name), &dmaInfo.pid, &dmaInfo.size, &dmaInfo.ino) == 0) {\n        return;\n    }\n    dmaInfo.name = name;\n    dmaInfo.size /= BYTE_PER_KB;\n    auto it = dmaInfoMap.find(dmaInfo.ino);\n    if (it == dmaInfoMap.end()) {\n        dmaInfoMap.insert(std::pair<uint64_t, DmaInfo>(dmaInfo.ino, dmaInfo));\n    } else if ((dmaInfo.name != \"composer_host\" && dmaInfo.name != \"render_service\") ||\n               (dmaInfo.name == \"render_service\" && it->second.name == \"composer_host\")) {\n        it->second.pid = dmaInfo.pid;\n    }\n}\n"
PREAMBLE = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <string>
struct DmaInfo {
    uint64_t size = 0;
    uint64_t ino = 0;
    uint32_t pid = 0;
    std::string name;
};
const int BYTE_PER_KB = 1024;
'''
CASES = r'''
#include <algorithm>
int main() {
    std::map<uint64_t, DmaInfo> rows;
    CreateDmaInfo("ordinary.hap 20010038 7 8388608 4294967301 22 allocator NULL heap", rows);
    assert(rows.size() == 1);
    const auto &row = rows.at(4294967301ULL);
    assert(row.pid == 20010038 && row.size == 8192 && row.name == "ordinary.hap");
    const char *invalid[] = {
        "", "Dma-buf objects usage of processes:", "Process pid fd size_bytes ino exp_pid",
        "Total dmabuf size of ordinary.hap: 8388608 bytes",
        "a", "a 12", "a 12 7", "a 12 7 4096", "a 12 7 4096 nonsense",
        "a -1 7 4096 8", "a +1 7 4096 8", "a 4294967296 7 4096 8",
        "a 1 -7 4096 8", "a 1 4294967296 4096 8", "a 1 7 -4096 8",
        "a 1 7 18446744073709551616 8", "a 1 7 4096 -8",
        "a 1 7 4096 18446744073709551616", "a 12z 7 4096 8",
        "a 1 7 4096 8x", "a 0 7 4096 8", "a 1 7 0 8", "a 1 7 4096 0"
    };
    for (const auto *line : invalid) {
        CreateDmaInfo(line, rows);
        assert(rows.size() == 1 && rows.at(4294967301ULL).pid == 20010038);
    }
    CreateDmaInfo(std::string(256, 'a') + " 1 7 4096 8", rows);
    assert(rows.size() == 1);
    CreateDmaInfo("composer_host 20 3 4096 9", rows);
    CreateDmaInfo("render_service 21 3 4096 9", rows);
    assert(rows.at(9).pid == 21);
    CreateDmaInfo("app 22 3 4096 9", rows);
    CreateDmaInfo("composer_host 20 3 4096 9", rows);
    CreateDmaInfo("render_service 21 3 4096 9", rows);
    assert(rows.at(9).pid == 22 && rows.at(9).size == 4 && rows.at(9).name == "app");
    CreateDmaInfo("app 22 4 4096 9", rows);
    assert(rows.size() == 2);
    CreateDmaInfo("huge 4294967295 4294967295 18446744073709551615 18446744073709551615", rows);
    assert(rows.at(UINT64_MAX).pid == UINT32_MAX && rows.at(UINT64_MAX).size == UINT64_MAX / 1024);
    const char *shared[] = {"composer_host 20 3 4096 9", "render_service 21 3 4096 9", "app 22 3 4096 9"};
    int order[] = {0, 1, 2};
    do {
        std::map<uint64_t, DmaInfo> owners;
        for (int i : order) CreateDmaInfo(shared[i], owners);
        assert(owners.size() == 1 && owners.at(9).pid == 22 && owners.at(9).name == "app");
    } while (std::next_permutation(order, order + 3));
}
'''


class DmaBufParserTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='qemu-dmabuf-parser-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / RELATIVE
        self.target.parent.mkdir(parents=True)
        self.target.write_text(ORIGINAL)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def test_real_patched_body_boundaries_with_sanitizers(self):
        for _ in range(2):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
        source = self.root / 'parser-test.cpp'
        source.write_text(PREAMBLE + self.target.read_text().replace(
            '#include <v1_0/imemory_tracker_interface.h>', '') + CASES)
        compiler = shutil.which('clang++')
        self.assertIsNotNone(compiler, 'actual Clang sanitizer compiler required')
        binary = self.root / 'parser-test'
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
            str(source), '-o', str(binary)], check=True, capture_output=True, text=True)
        execution = subprocess.run([str(binary)], capture_output=True, text=True)
        self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)

    def test_unknown_source_refused(self):
        self.target.write_text(ORIGINAL.replace('    DmaInfo dmaInfo;', '    DmaInfo renamed;'))
        before = self.target.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.target.read_bytes(), before)

    def test_marker_does_not_hide_drift(self):
        self.assertEqual(self.apply().returncode, 0)
        self.target.write_text(self.target.read_text().replace('std::from_chars', 'incorrect_parse'))
        self.assertNotEqual(self.apply().returncode, 0)

    def test_shared_six_profile_build_wiring(self):
        build = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('hiview/dmabuf_parser/apply.sh', build)
        self.assertIn('bash "${HIVIEW_DMABUF_PARSER_SCRIPT}" --source-root "${OHOS_ROOT}"', build)
