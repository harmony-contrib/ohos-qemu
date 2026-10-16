#!/usr/bin/env python3
"""Actual fixed MSDP input functions and opt-in mock boundary; supplemental only."""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURE = HERE / 'fixtures/batch_system/msdp_input'
COMPONENT = ROOT / 'patches/common/base/msdp/device_status/sensor_input'
CALLBACK = 'base/msdp/device_status/libs/src/datahub/sensor_data_callback.cpp'
CLIENT = 'base/msdp/device_status/services/native/src/devicestatus_msdp_client_impl.cpp'
BEFORE_CASES = ['nan', 'wrong_type', 'short_event', 'bounded_queue', 'batch_rollback', 'activate_rollback', 'no_mock']
AFTER_CASES = BEFORE_CASES + ['valid_unaligned_event', 'invalid_envelopes', 'subscribe_failure', 'valid_register']


def prepare(root):
    meta = json.loads((FIXTURE / 'provenance.json').read_text())
    for row in meta['files']:
        data = gzip.decompress(base64.b64decode((FIXTURE / row['fixture']).read_bytes()))
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('fixed MSDP source changed')
        target = root / row['path']; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    return meta


def section(text, begin, end):
    start = text.index(begin)
    return text[start:text.index(end, start + len(begin))]


def run(output, cxx='c++'):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C',
               ASAN_OPTIONS=f'detect_leaks={int(platform.system() != "Darwin")}:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1')
    rows = []
    builds = []
    for state, cases in [('before', BEFORE_CASES), ('after', AFTER_CASES)]:
        root = output / state; meta = prepare(root)
        if state == 'after':
            subprocess.run(['python3', str(COMPONENT / 'apply.py'), '--source-root', str(root)],
                           capture_output=True, check=True)
        source = (root / CALLBACK).read_text(); client = (root / CLIENT).read_text()
        actual = root / 'actual_msdp_functions.inc'
        actual.write_text(section(source, 'bool SensorDataCallback::PushData(', 'bool SensorDataCallback::PopData(') +
                          section(source, 'static void SensorDataCallbackImpl(', 'bool SensorDataCallback::UnregisterCallbackSensor(') +
                          section(client, 'ErrCode DeviceStatusMsdpClientImpl::InitMsdpImpl(', 'ErrCode DeviceStatusMsdpClientImpl::MockHandle('))
        flags = [cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread', '-g',
                 '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-DDEVICE_STATUS_SENSOR_ENABLE',
                 '-I' + str(root), str(HERE / 'batch_system_msdp_input_harness.cpp')]
        binary = root / 'actual_msdp'; argv = flags + ['-DDEVICE_STATUS_DISABLE_MOCK_FALLBACK', '-o', str(binary)]
        compiled = subprocess.run(argv, capture_output=True, text=True)
        (root / 'compile.log').write_text(compiled.stdout + compiled.stderr)
        if compiled.returncode: raise ValueError('actual MSDP function compile failed')
        builds.append(dict(state=state, argv=argv, extracted_sha256=hashlib.sha256(actual.read_bytes()).hexdigest(),
                           binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()))
        for case in cases:
            proc = subprocess.run([str(binary), case], capture_output=True, text=True, env=env, timeout=10)
            (root / (case + '.log')).write_text(proc.stdout + proc.stderr)
            rows.append(dict(state=state, scenario=case, exit_code=proc.returncode))
            if state == 'before' and (proc.returncode == 0 or not proc.stderr.startswith(case + ': ')):
                raise ValueError('original defect not reproduced: ' + case)
            if state == 'after' and proc.returncode: raise ValueError('repaired MSDP boundary failed: ' + case)
        if state == 'after':
            binary = root / 'default_msdp'; argv = flags + ['-o', str(binary)]
            compiled = subprocess.run(argv, capture_output=True, text=True)
            (root / 'default-compile.log').write_text(compiled.stdout + compiled.stderr)
            if compiled.returncode: raise ValueError('default feature compilation failed')
            builds.append(dict(state='default', argv=argv,
                               binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest()))
            proc = subprocess.run([str(binary), 'default_fallback'], capture_output=True, text=True, env=env)
            (root / 'default_fallback.log').write_text(proc.stdout + proc.stderr)
            if proc.returncode: raise ValueError('non-opt-in fallback behavior changed')
            rows.append(dict(state=state, scenario='default_fallback', exit_code=proc.returncode))
    result = dict(status='pass_fixed_msdp_input_boundaries', fixture_provenance=meta, cases=rows,
                  builds=builds, platform=platform.platform(),
                  compiler=subprocess.check_output([cxx, '--version'], text=True).splitlines()[0],
                  patch_sha256=hashlib.sha256(next(COMPONENT.glob('*.patch')).read_bytes()).hexdigest(),
                  harness_sha256=hashlib.sha256((HERE / 'batch_system_msdp_input_harness.cpp').read_bytes()).hexdigest(),
                  runtime_tested=False, requirements_closed=0, first_artifact_behavior_gate_passed=False,
                  limitations='Actual extracted functions with test SensorAgent call fault injection and '
                              'semaphore counter shim only; OS semaphore/thread lifecycle, algorithm outcomes '
                              'and real SensorService/MSDP IPC remain unvalidated.')
    (output / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--cxx', default='c++')
    args = parser.parse_args(); result = run(args.output, args.cxx)
    print(json.dumps(dict(status=result['status'], cases=len(result['cases']))))
