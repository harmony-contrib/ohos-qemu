"""Execute the real profile verifier function with mock tools, not guest proof."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / 'scripts/run_device_type_matrix_build_docker.sh'


class MatrixProfileOptionalArrayTests(unittest.TestCase):
    def test_real_profile_function_preserves_empty_and_populated_arguments(self):
        source = FRONTEND.read_text()
        start = source.index('verify_package() {\n')
        end = source.index('\nselect_arch_dependencies() {', start)
        function = source[start:end]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verifier = root / 'mock verifier with spaces.sh'
            verifier.write_text('"' + os.sys.executable + '" -c '
                + "'import json,sys; print(json.dumps(sys.argv[1:]))' \"$@\"\n")
            for profile in ('phone', '2in1'):
                package = str(root / 'package with spaces')
                env = dict(os.environ, TASK_VERIFY=str(verifier), TASK_PACKAGE=package,
                           TASK_PROFILE=profile)
                script = ('set -euo pipefail\nVERIFY="$TASK_VERIFY"\n'
                          'MANIFEST_REVISION=f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549\n'
                          + function + '\nverify_package "$TASK_PROFILE" "$TASK_PACKAGE"\n')
                result = subprocess.run(['/bin/bash', '-c', script], env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = ['--package', package, '--expect-device-type', profile,
                            '--expect-manifest-revision', 'f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549',
                            '--require-full-' + profile]
                if profile == '2in1':
                    expected.append('--require-scene-window')
                self.assertEqual(json.loads(result.stdout), expected)
                self.assertNotIn('', json.loads(result.stdout))


if __name__ == '__main__':
    unittest.main()
