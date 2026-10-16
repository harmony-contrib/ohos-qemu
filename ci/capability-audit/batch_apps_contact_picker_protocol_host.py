#!/usr/bin/env python3
"""Lease-required host ASan/UBSan challenge, never a HAP or guest acceptance."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / 'ci/capability-audit/fixtures/batch_apps/contact_picker_protocol'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--json-include', required=True, type=Path, help='read-only fixed-source nlohmann include export')
parser.add_argument('--output-dir', required=True, type=Path, help='private scratch; must not already exist')
args = parser.parse_args()
out = args.output_dir.resolve()
out.mkdir(parents=True, exist_ok=False)
spec = importlib.util.spec_from_file_location('protocol_tests', ROOT / 'ci/capability-audit/test_batch_apps_contact_picker_protocol.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
source = out / 'source'
tests.prepare(source)
applied = tests.apply(source)
(out / 'apply.log').write_text(applied.stdout + applied.stderr)
assert applied.returncode == 0
actual = (source / tests.PROJECT / 'contacts/src/contacts_napi_utils.cpp').read_text()
start = actual.index('namespace {\nstruct SelectionRequest {')
end = actual.index('\nModalUICallback::ModalUICallback(', start)
(out / 'actual_selection_impl.inc').write_text(actual[start:end])
for name in ['protocol_test.cpp', 'native_lifecycle_test.cpp']:
    shutil.copy2(FIX / name, out / name)
command = ['clang++', '-std=c++17', '-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
           '-pthread', '-I' + str(args.json_include.resolve()), '-I' + str(source / tests.PROJECT / 'contacts/include'),
           str(out / 'native_lifecycle_test.cpp'), '-o', str(out / 'native_lifecycle_test')]
env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C',
           ASAN_OPTIONS='detect_leaks=' + ('0' if sys.platform == 'darwin' else '1'), UBSAN_OPTIONS='halt_on_error=1')
report = {'kind': 'host adapters + exact native header/selection implementation; no runtime capability closure',
          'source_hashes': json.loads((FIX / 'candidate-hashes.json').read_text()),
          'fixture_sha256': hashlib.sha256((FIX / 'inspection.json').read_bytes()).hexdigest(),
          'dependency_header_hashes': {str(p.relative_to(args.json_include)): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in sorted(args.json_include.rglob('*.hpp'))},
          'compiler': subprocess.check_output(['clang++', '--version'], text=True).splitlines()[0],
          'environment': {key: env[key] for key in ['LC_ALL', 'LC_CTYPE', 'LANG', 'ASAN_OPTIONS', 'UBSAN_OPTIONS']},
          'LSan_supported': sys.platform != 'darwin',
          'commands': [], 'runtime_gate_passed': False}
for name, cmd in [('compile', command), ('run', [str(out / 'native_lifecycle_test')])]:
    before = time.monotonic()
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    (out / (name + '.log')).write_text(result.stdout + result.stderr)
    report['commands'].append({'name': name, 'argv': cmd, 'exit_code': result.returncode,
                               'seconds': time.monotonic() - before, 'stdout': result.stdout, 'stderr': result.stderr})
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(name + ' exit=' + str(result.returncode), flush=True)
    if result.returncode != 0: raise SystemExit(result.returncode)
report['binary_sha256'] = hashlib.sha256((out / 'native_lifecycle_test').read_bytes()).hexdigest()
(out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(report['commands'][-1]['stdout'], end='')
