#!/usr/bin/env python3
"""Exercise the actual patch's ABI mapping, not the missing DSP algorithms."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "patches/common/foundation/multimedia/audio_framework/audio_suite_library_path"
PATCH = COMPONENT / "0001-use-native-abi-plugin-directory.patch"
CANONICAL_PATCH = COMPONENT / "0002-accept-qemu-canonical-read-only-library-root.patch"


def sections():
    result = {}
    for section in PATCH.read_text().split("diff --git ")[1:]:
        name = section.split("+++ b/", 1)[1].splitlines()[0]
        hunk = section.split("@@", 2)[2].splitlines()[1:]
        result[name] = hunk
    return result


def canonical_hunks():
    return [section.splitlines()[1:] for section in CANONICAL_PATCH.read_text().split("@@")[2::2]]


class AudioSuiteAbiTests(unittest.TestCase):
    def run_abi(self, lp64):
        hunks = list(sections().values())
        canonical = canonical_hunks()
        common = "\n".join(line[1:] for line in canonical[0] if line.startswith(("+", " ")))
        prefix = common[common.index("#if defined(__LP64__)"):common.index("#endif") + len("#endif")]
        mapping = "\n".join(line[1:] for line in hunks[1] if line.startswith("+"))
        validator = "\n".join(line[1:] for line in canonical[1] if line.startswith(("+", " ")))
        validator = validator.replace("AudioSuiteLibraryManager::IsValidPath", "IsValidPath")
        expected = "/system/lib64/" if lp64 else "/system/lib/"
        expected_canonical = "/usr/system/lib64/" if lp64 else "/usr/system/lib/"
        wrong = "/system/lib/" if lp64 else "/system/lib64/"
        wrong_canonical = "/usr/system/lib/" if lp64 else "/usr/system/lib64/"
        program = f'''#include <cassert>
#include <string>
#include <cstring>
// Simulate only the two ABI branches; this is not a cross-architecture guest.
#undef __LP64__
{("#define __LP64__ 1" if lp64 else "")}
{prefix}
#define CHECK_AND_RETURN_RET_LOG(condition, value, message) do {{ if (!(condition)) return value; }} while (0)
{validator}
std::string map(const std::string &path) {{
    struct {{ std::string soPath; }} nodeParameter {{ path }};
{mapping}
    return nodeParameter.soPath;
}}
int main() {{
    assert(std::string(PREFIX) == "{expected}");
    assert(std::string(QEMU_PREFIX) == "{expected_canonical}");
    assert(IsValidPath("{expected}libplugin.so"));
    assert(IsValidPath("{expected_canonical}libplugin.so"));
    assert(!IsValidPath(nullptr));
    assert(!IsValidPath("{wrong}libplugin.so"));
    assert(!IsValidPath("{wrong_canonical}libplugin.so"));
    assert(!IsValidPath("/system/lib64evil/libplugin.so"));
    assert(!IsValidPath("/usr/system/lib64evil/libplugin.so"));
    assert(!IsValidPath("/data/libplugin.so"));
    // LoadLibrary passes realpath's output: an escaped symlink/traversal
    // resolves outside both read-only library roots and must be rejected.
    assert(!IsValidPath("/usr/data/libplugin.so"));
    assert(map("/system/lib64/") == "{expected}");
    assert(map("/system/lib/") == "/system/lib/");
    assert(map("").empty()); // built-in mixer has no plug-in library
    // Do not rewrite custom or unsafe paths into a trusted prefix.
    assert(map("/data/lib64/") == "/data/lib64/");
    assert(map("/system/lib64evil/") == "/system/lib64evil/");
    assert(map("/system/lib64/../other/") == "/system/lib64/../other/");
}}
'''
        compiler = shutil.which("clang++") or shutil.which("g++")
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory() as temp:
            source, binary = Path(temp) / "abi.cpp", Path(temp) / "abi"
            source.write_text(program)
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=address,undefined", str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_lp64_keeps_existing_paths(self):
        self.run_abi(True)

    def test_arm32_maps_only_default_xml_path(self):
        self.run_abi(False)

    def test_patch_apply_and_reverse_check_are_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, hunk in sections().items():
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                preimage = "\n".join(line[1:] for line in hunk if line.startswith(("-", " ")))
                if name.endswith("audio_suite_common.cpp"):
                    validator = canonical_hunks()[1]
                    preimage += "\n}\n" + "\n".join(line[1:] for line in validator if line.startswith(("-", " ")))
                file.write_text(preimage + "\n// More source follows these hunks.\n")
            command = ["bash", str(COMPONENT / "apply.sh"), "--source-root", str(root)]
            subprocess.run(command, check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "apply", "--check", "--reverse", str(CANONICAL_PATCH)], check=True)
            postimages = {name: (root / name).read_text() for name in sections()}
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(postimages, {name: (root / name).read_text() for name in sections()})
            # Reverse-check each patch in dependency order. 0001's hunk has
            # changed after 0002, so check it after reversing 0002 in scratch.
            subprocess.run(["git", "-C", str(root), "apply", "--reverse", str(CANONICAL_PATCH)], check=True)
            subprocess.run(["git", "-C", str(root), "apply", "--check", "--reverse", str(PATCH)], check=True)


if __name__ == "__main__":
    unittest.main()
