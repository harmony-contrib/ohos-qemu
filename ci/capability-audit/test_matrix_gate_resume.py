"""Exercise actual first-gate shell block; mocks are never guest evidence."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MatrixGateResumeTests(unittest.TestCase):
    def test_resume_valid_evidence_and_fail_closed_on_invalid_validation(self):
        source = (ROOT / 'scripts/run_device_type_matrix_build_docker.sh').read_text()
        start = source.index('if ! python3 "${SCRIPT_DIR}/verify_first_artifact_gate.py"',
                             source.index('verify_current_inputs "${first_tar}"\n'))
        block = source[start:source.index('\n# Validate each profile', start)]
        for already_valid, validator_passes, validator_exists in (
                (True, True, True), (False, True, True), (False, False, True), (False, True, False)):
            with self.subTest(already_valid=already_valid, validator_passes=validator_passes,
                              validator_exists=validator_exists), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                valid = root / 'valid'; calls = root / 'calls'; validator_calls = root / 'validator-calls'
                if already_valid:
                    valid.touch()
                mock = root / 'python3'
                mock.write_text('#!' + os.sys.executable + '\n' +
                    'import json,os,pathlib,sys\n'
                    'with open(os.environ["TASK_CALLS"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                    'sys.exit(0 if pathlib.Path(os.environ["TASK_VALID"]).exists() else 1)\n')
                mock.chmod(0o755)
                validator = root / 'validator with spaces.sh'
                validator.write_text('set -euo pipefail\n'
                    'touch "$TASK_VALIDATOR_CALLS"\n'
                    'if [ "$TASK_VALIDATOR_PASSES" = 1 ]; then touch "$TASK_VALID"; else exit 1; fi\n')
                environment = dict(os.environ, PATH=str(root) + ':' + os.environ['PATH'],
                    TASK_VALID=str(valid), TASK_CALLS=str(calls), TASK_VALIDATOR_CALLS=str(validator_calls),
                    TASK_VALIDATOR_PASSES=str(int(validator_passes)))
                variables = dict(SCRIPT_DIR=str(root), first_tar=str(root / 'new package.tar.gz'),
                    first_dir=str(root / 'new package'), MATRIX_FIRST_ARTIFACT_EVIDENCE=str(root / 'gate.json'),
                    MATRIX_FIRST_PRODUCT='arm64_virt', MATRIX_FIRST_DEVICE_TYPE='phone',
                    MATRIX_FIRST_VALIDATOR=str(validator) if validator_exists else '')
                script = 'set -euo pipefail\n' + '\n'.join(
                    key + '=' + shlex.quote(value) for key, value in variables.items()) + '\n' + block
                result = subprocess.run(['/bin/bash', '-c', script], env=environment,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode == 0,
                                 already_valid or (validator_exists and validator_passes), result.stderr)
                self.assertEqual(validator_calls.exists(), not already_valid and validator_exists)
                checks = [json.loads(line) for line in calls.read_text().splitlines()]
                self.assertEqual(len(checks), 1 if not already_valid and validator_exists and not validator_passes else 2)
                for argv in checks:
                    self.assertEqual(argv[argv.index('--archive') + 1], variables['first_tar'])
                    self.assertEqual(argv[argv.index('--evidence') + 1], variables['MATRIX_FIRST_ARTIFACT_EVIDENCE'])


if __name__ == '__main__':
    unittest.main()
