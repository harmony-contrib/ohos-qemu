"""Actual adapter-fragment and launcher fixtures, not OS or guest evidence."""
import importlib.util
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/build/host_gn_execution'
GN = '/fixed source/prebuilts/build-tools/linux-x86/bin/gn'


def helpers():
    result = []
    for path in sorted(COMPONENT.glob('000[12]-*.patch')):
        match = re.search(r'^\+def _qemu_host_gn_command\(cmd\):\n(?:\+    .*\n)+',
                          path.read_text(), re.MULTILINE)
        if match is None:
            raise ValueError('actual added host GN helper is missing')
        source = '\n'.join(line[1:] for line in match.group().splitlines())
        namespace = {'os': os, 'platform': platform}
        exec(compile(source, str(path), 'exec'), namespace)
        result.append(namespace['_qemu_host_gn_command'])
    return result


class HostGnExecutionTests(unittest.TestCase):
    def test_native_and_non_gn_commands_preserve_object_and_arguments(self):
        with patch.dict(os.environ, {'QEMU_HOST_GN_QEMU_USER': '0'}):
            for helper in helpers():
                original = [GN, 'format', '/space path/BUILD.gn']
                self.assertIs(helper(original), original)
        with patch.dict(os.environ, {'QEMU_HOST_GN_QEMU_USER': '1'}):
            for helper in helpers():
                for original in (['ninja', '-C', '/space path'], ['gn', 'gen'], [],
                                 'gn gen', ['/bin/qemu-x86_64-static', GN], [None, 'format']):
                    self.assertIs(helper(original), original)

    def test_explicit_cpu_keeps_all_arguments_without_mutating_or_double_wrapping(self):
        with patch.dict(os.environ, {'QEMU_HOST_GN_QEMU_USER': '1'}), \
                patch.object(platform, 'system', return_value='Linux'), \
                patch.object(platform, 'machine', return_value='x86_64'):
            for helper in helpers():
                original = [GN, 'gen', '--args=one="space value"', '$literal.gn']
                expected = ['/usr/bin/qemu-x86_64-static', '-cpu', 'max'] + original
                actual = helper(original)
                self.assertEqual(actual, expected)
                self.assertEqual(original, expected[3:])
                self.assertIs(helper(actual), actual)
                self.assertEqual(helper(tuple(original)), expected)

    def test_invalid_gn_mode_or_wrong_host_is_rejected(self):
        for helper in helpers():
            with patch.dict(os.environ, {'QEMU_HOST_GN_QEMU_USER': '2'}):
                with self.assertRaises(ValueError):
                    helper([GN, 'format'])
            with patch.dict(os.environ, {'QEMU_HOST_GN_QEMU_USER': '1'}), \
                    patch.object(platform, 'system', return_value='Darwin'):
                with self.assertRaises(ValueError):
                    helper([GN, 'format'])

    def test_real_formatter_and_hb_execute_paths_are_both_connected(self):
        first, second = [path.read_text() for path in sorted(COMPONENT.glob('000[12]-*.patch'))]
        self.assertIn('+        subprocess.check_output(_qemu_host_gn_command(cmd))', first)
        self.assertIn('+        cmd = _qemu_host_gn_command(cmd)', second)
        for source in (first, second):
            added = '\n'.join(line[1:] for line in source.splitlines()
                              if line.startswith('+') and not line.startswith('+++'))
            self.assertNotRegex(added, r'\bexcept\b')
            self.assertNotIn('max_try', added)
        build = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('apt_packages+=(qemu-user-static)', build)
        self.assertIn('${QEMU_HOST_GN_EXECUTION_COMPONENT_SCRIPT}', build)
        self.assertLess(build.index('bash "${QEMU_HOST_GN_EXECUTION_COMPONENT_SCRIPT}"'),
                        build.index('build_product "${product}"', build.index('main() {')))

    def test_actual_host_launcher_auto_selection_and_invalid_overrides(self):
        source = (ROOT / 'scripts/run_2in1_full_build_docker.sh').read_text()
        start = source.index('QEMU_HOST_GN_QEMU_USER="${QEMU_HOST_GN_QEMU_USER:-auto}"')
        end = source.index('# Keep generated output', start)
        block = source[start:end]
        for machine, docker_platform, mode, result, status in (
                ('arm64', 'linux/amd64', 'auto', '1', 0),
                ('aarch64', 'linux/amd64', 'auto', '1', 0),
                ('x86_64', 'linux/amd64', 'auto', '0', 0),
                ('arm64', 'linux/arm64', 'auto', '0', 0),
                ('arm64', 'linux/amd64', '0', '0', 0),
                ('arm64', 'linux/arm64', '1', '', 2),
                ('arm64', 'linux/amd64', 'wrong', '', 2)):
            environment = dict(os.environ, GN_FIXTURE_MACHINE=machine,
                DOCKER_PLATFORM=docker_platform, QEMU_HOST_GN_QEMU_USER=mode)
            command = 'uname() { printf "%s\\n" "$GN_FIXTURE_MACHINE"; }\n' + block
            command += '\nprintf "%s" "$QEMU_HOST_GN_QEMU_USER"\n'
            actual = subprocess.run(['/bin/bash', '-eu', '-c', command],
                env=environment, capture_output=True, text=True, check=False)
            self.assertEqual(actual.returncode, status, actual.stderr)
            self.assertEqual(actual.stdout, result)

    def test_complete_state_checker_refuses_partial_or_unknown_python_edits(self):
        spec = importlib.util.spec_from_file_location('host_gn_source_contract', COMPONENT / 'verify_source.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import hashlib
        before, after = b'original fixture', b'repaired fixture'
        entries = tuple((name, hashlib.sha256(before).hexdigest(), hashlib.sha256(after).hexdigest())
                        for name in ('first.py', 'second.py'))
        with tempfile.TemporaryDirectory() as temporary, patch.object(module, 'FILES', entries):
            root = Path(temporary)
            (root / 'build').mkdir()
            for name, _, _ in entries:
                (root / 'build' / name).write_bytes(before)
            self.assertFalse(module.validate(root))
            (root / 'build/first.py').write_bytes(after)
            with self.assertRaises(ValueError):
                module.validate(root)
            (root / 'build/second.py').write_bytes(after)
            self.assertTrue(module.validate(root, require_patched=True))
            (root / 'build/first.py').write_bytes(b'unknown')
            with self.assertRaises(ValueError):
                module.validate(root)


if __name__ == '__main__':
    unittest.main()
