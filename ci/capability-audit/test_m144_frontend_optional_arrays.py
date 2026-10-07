"""Execute the real host frontend with mock external tools, never guest proof.

macOS /bin/bash 3.2 treats an empty array as unset under nounset. The fixture
executes every stage with both empty and populated optional arrays. Mock tools
record exact argument boundaries; no Docker/network/build is performed here.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / 'scripts/run_m144_release_build_docker.sh'


class M144OptionalArrayTests(unittest.TestCase):
    def fixture(self, root, source=None):
        scripts = root / 'fixture repository/scripts'
        scripts.mkdir(parents=True)
        (scripts / FRONTEND.name).write_text(source or FRONTEND.read_text())
        (scripts / 'm144_dependency_recipe.py').write_text('print("' + '1' * 64 + '")\n')
        (scripts / 'snapshot_build_inputs.py').write_text(
            'import argparse,shutil\nfrom pathlib import Path\n'
            'p=argparse.ArgumentParser();p.add_argument("--source");p.add_argument("--destination");a=p.parse_args()\n'
            'shutil.copytree(Path(a.source)/"scripts",Path(a.destination)/"scripts")\n')
        preparer = (
            'import json,os,sys\nfrom pathlib import Path\n'
            'with open(os.environ["TASK_TRACE"],"a") as f:f.write(json.dumps([Path(__file__).name,*sys.argv[1:]])+"\\n")\n'
            'if Path(__file__).name=="prepare_m144_release_hap_cache.py":\n'
            ' print(str(Path(os.environ["CACHE_ROOT"])/"paired tools fixture"))\n')
        for name in ('prepare_m144_release_cache.py', 'prepare_m144_release_lfs.py',
                     'prepare_m144_tool_sources.py', 'prepare_m144_release_hap_cache.py'):
            (scripts / name).write_text(preparer)
        binaries = root / 'mock binaries'
        binaries.mkdir()
        docker = binaries / 'docker'
        docker.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
            'with open(os.environ["TASK_TRACE"],"a") as f:f.write(json.dumps(["docker",*sys.argv[1:]])+"\\n")\n')
        docker.chmod(0o755)
        environment = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ['PATH'],
                           CACHE_ROOT=str(root / 'cache with spaces'), TASK_TRACE=str(root / 'trace.jsonl'),
                           DOCKER_IMAGE='MOCK_NO_ACTUAL_IMAGE')
        return scripts / FRONTEND.name, environment

    def execute(self, frontend, environment, mode, skip_fetch):
        environment = dict(environment, M144_SKIP_FETCH=str(skip_fetch))
        result = subprocess.run(['/bin/bash', str(frontend), mode, 'arm64'],
                                env=environment, text=True, capture_output=True)
        trace = Path(environment['TASK_TRACE'])
        rows = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
        return result, rows

    def test_all_six_stages_empty_nonempty_options_preserve_exact_argv(self):
        for mode in ('prepare', 'native', 'hap', 'v8', 'swiftshader', 'avc'):
            for skip_fetch in (0, 1):
                with self.subTest(mode=mode, skip_fetch=skip_fetch), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    frontend, environment = self.fixture(root)
                    result, rows = self.execute(frontend, environment, mode, skip_fetch)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    run = [row for row in rows if row[:2] == ['docker', 'run']]
                    self.assertEqual(len(run), 1)
                    self.assertNotIn('', run[0])
                    mounts = [run[0][i + 1] for i, arg in enumerate(run[0]) if arg == '--mount']
                    self.assertEqual(len(mounts), 7 if mode in ('native', 'hap') else 6)
                    paired = 'type=bind,src=' + environment['CACHE_ROOT'] + '/paired tools fixture,dst=/m144-hap-tools,readonly'
                    self.assertEqual(paired in mounts, mode in ('native', 'hap'))
                    for name in ('prepare_m144_release_lfs.py', 'prepare_m144_tool_sources.py'):
                        commands = [row for row in rows if row[0] == name]
                        self.assertEqual(len(commands), 1)
                        self.assertEqual(commands[0].count('--no-fetch'), skip_fetch)
                        self.assertNotIn('', commands[0])
                    tools = next(row for row in rows if row[0] == 'prepare_m144_tool_sources.py')
                    self.assertEqual(tools[-2:], ['gn', 'sdk-llvm15'])
                    fetch = [row for row in rows if row[0] == 'prepare_m144_release_cache.py']
                    self.assertEqual(len(fetch), 1 - skip_fetch)

    def test_guarded_empty_array_is_zero_arguments_and_nonempty_keeps_spaces(self):
        guards = [line.strip().rstrip('\\').strip() for line in FRONTEND.read_text().splitlines()
                  if line.strip().startswith('${hap_tool_mounts[@]+')]
        self.assertEqual(len(guards), 1)
        script = 'set -eu\nhap_tool_mounts=()\nset -- ' + guards[0] + '\n[ "$#" = 0 ]\n'
        script += 'hap_tool_mounts=(--mount "one argument with spaces")\nset -- ' + guards[0] + '\n'
        script += '[ "$#" = 2 ] && [ "$1" = --mount ] && [ "$2" = "one argument with spaces" ]\n'
        subprocess.run(['/bin/bash', '-c', script], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
