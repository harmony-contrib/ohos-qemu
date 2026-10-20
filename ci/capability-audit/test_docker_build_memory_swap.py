"""Exercise the real resource argv block with Bash; no Docker is started."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / 'scripts/run_2in1_full_build_docker.sh'


class DockerBuildMemorySwapTests(unittest.TestCase):
    def resource_argv(self, **overrides):
        source = LAUNCHER.read_text()
        start = source.index("# Docker's memory-swap limit includes RAM.")
        end = source.index('  --ulimit nofile=', start)
        program = 'set -euo pipefail\n' + source[start:end] + '  MOCK_IMAGE\n'
        with tempfile.TemporaryDirectory(prefix='memory swap argv ') as directory:
            binary = Path(directory) / 'docker'
            binary.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            binary.chmod(0o755)
            environment = dict(os.environ)
            for key in ('DOCKER_BUILD_MEMORY_SWAP', 'DOCKER_BUILD_MEMORY', 'DOCKER_BUILD_CPUS'):
                environment.pop(key, None)
            environment.update(PATH=directory + os.pathsep + environment['PATH'],
                               DOCKER_PLATFORM='linux/amd64', DEVICE_TYPE='phone', **overrides)
            result = subprocess.run(['/bin/bash', '-c', program], env=environment,
                                    capture_output=True, text=True, check=True)
            return json.loads(result.stdout)

    def test_unset_and_empty_preserve_original_default_resources(self):
        for overrides in ({}, {'DOCKER_BUILD_MEMORY_SWAP': ''}):
            with self.subTest(overrides=overrides):
                args = self.resource_argv(**overrides)
                self.assertNotIn('--memory-swap', args)
                self.assertNotIn('', args)
                self.assertEqual(args[args.index('--memory') + 1], '5g')
                self.assertEqual(args[args.index('--cpus') + 1], '2')

    def test_explicit_total_budget_preserves_ram_and_cpu_arguments(self):
        args = self.resource_argv(DOCKER_BUILD_MEMORY='14g', DOCKER_BUILD_CPUS='4',
                                  DOCKER_BUILD_MEMORY_SWAP='38g')
        self.assertEqual(args.count('--memory-swap'), 1)
        self.assertEqual(args[args.index('--memory-swap') + 1], '38g')
        self.assertEqual(args[args.index('--memory') + 1], '14g')
        self.assertEqual(args[args.index('--cpus') + 1], '4')

    def test_swap_value_stays_one_argument(self):
        args = self.resource_argv(DOCKER_BUILD_MEMORY_SWAP='38g --privileged')
        self.assertEqual(args[args.index('--memory-swap') + 1], '38g --privileged')
        self.assertNotIn('--privileged', args)


if __name__ == '__main__':
    unittest.main()
