#!/usr/bin/env python3
"""Run fixed-source child lifecycle boundaries; this is not package validation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/ability/ability_runtime/native_child_process'
FIXTURE = ROOT / 'ci/capability-audit/fixtures/batch_system/native_child_lifecycle'
BASE = Path('foundation/ability/ability_runtime/frameworks/native/child_process')
PATCH = COMPONENT / '0004-complete-start-callback-lifecycle.patch'
HERE = Path(__file__).resolve().parent
SCENARIOS = [
    'null_child', 'proxy_failure', 'error_then_success', 'success_then_error',
    'callback_reentry', 'drop_last_owner', 'drop_last_owner_error',
    'concurrent_terminal', 'exit_callbacks',
] + [f'create_{mode}{suffix}' for suffix in ('', '_configs')
     for mode in ('early_success', 'early_error', 'reject', 'delayed')]
BASELINE_FAILURES = ['null_child', 'proxy_failure', 'callback_reentry',
                     'create_early_success', 'create_early_error',
                     'create_early_success_configs', 'create_early_error_configs']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_fixture():
    provenance = json.loads((FIXTURE / 'provenance.json').read_text())
    for row in provenance['files']:
        if digest(FIXTURE / row['path']) != row['sha256']:
            raise ValueError('fixed source fixture changed: ' + row['path'])
    return provenance


def prepare(destination, pristine=False):
    provenance = verify_fixture()
    fixture_root = FIXTURE / 'pristine' if pristine else FIXTURE
    for row in provenance['pristine_files' if pristine else 'files']:
        if digest(fixture_root / row['path']) != row['sha256']:
            raise ValueError('fixed pristine source fixture changed: ' + row['path'])
        target = destination / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture_root / row['path'], target)
    return provenance


def compile_sources(directory, cxx):
    source = directory / BASE
    shims = directory / 'shims'
    shims.mkdir()
    for name in ('native_child_notify_stub.h', 'native_child_process.h', 'iremote_stub.h',
                 'nocopyable.h', 'hilog_tag_wrapper.h', 'ipc_inner_object.h',
                 'child_process_manager_error_utils.h'):
        (shims / name).write_text('// ABI declarations supplied by forced support header.\n')
    text = (source / 'src/native_child_process.cpp').read_text()
    start = text.index('int OH_Ability_CreateNativeChildProcess(')
    end = text.index('Ability_NativeChildProcess_ErrCode ConvertNativeChildProcessArgs', start)
    extracted = directory / 'actual_create_entrypoints.cpp'
    extracted.write_text('#include "native_child_callback.h"\n'
                         'using namespace OHOS;\nusing namespace OHOS::AbilityRuntime;\n' + text[start:end])
    binary = directory / 'child_lifecycle'
    argv = [cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g',
            '-include', str(HERE / 'batch_system_child_lifecycle_support.h'),
            '-I' + str(shims), '-I' + str(source / 'include'),
            str(source / 'src/native_child_callback.cpp'),
            str(source / 'src/child_callback_manager.cpp'), str(extracted),
            str(HERE / 'batch_system_child_lifecycle_harness.cpp'), '-o', str(binary)]
    compiled = subprocess.run(argv, capture_output=True, text=True)
    (directory / 'compile.log').write_text(compiled.stdout + compiled.stderr)
    if compiled.returncode:
        raise RuntimeError('host compile failed: ' + str(directory / 'compile.log'))
    return binary, argv, digest(extracted)


def run(output, cxx='c++'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = output / 'before'
    after = output / 'after'
    provenance = prepare(before)
    prepare(after)
    applied = subprocess.run(['git', '-C', str(after), 'apply', '--check', str(PATCH)],
                             capture_output=True, text=True, check=True)
    subprocess.run(['git', '-C', str(after), 'apply', str(PATCH)], check=True)
    (output / 'apply.log').write_text(applied.stdout + applied.stderr)
    rows = []
    # Apple clang ASan rejects detect_leaks=1 before entering main. The actual
    # manager's retained references are checked by intrusive live/ref counters.
    leak_sanitizer = platform.system() != 'Darwin'
    env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C',
               ASAN_OPTIONS=f'detect_leaks={int(leak_sanitizer)}:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1')
    builds = []
    for state, directory, scenarios in (
        ('before', before, BASELINE_FAILURES), ('after', after, SCENARIOS)
    ):
        binary, argv, extracted_hash = compile_sources(directory, cxx)
        builds.append(dict(state=state, argv=argv, binary_sha256=digest(binary),
                           extracted_entrypoints_sha256=extracted_hash))
        for scenario in scenarios:
            proc = subprocess.run([str(binary), scenario], capture_output=True, text=True,
                                  env=env, timeout=20)
            (directory / (scenario + '.log')).write_text(proc.stdout + proc.stderr)
            rows.append(dict(state=state, scenario=scenario, exit_code=proc.returncode))
            if state == 'before' and proc.returncode == 0:
                raise ValueError('fixed baseline did not reproduce ' + scenario)
            if state == 'before' and not proc.stderr.startswith(scenario + ': '):
                raise ValueError('baseline did not reach its boundary assertion: ' + scenario)
            if state == 'after' and proc.returncode:
                raise ValueError('patched boundary failed: ' + scenario)
    # Exercise the winning callback under multiple independent 32-thread schedules.
    binary = after / 'child_lifecycle'
    for repeat in range(20):
        proc = subprocess.run([str(binary), 'concurrent_terminal'], capture_output=True,
                              text=True, env=env, timeout=20)
        if proc.returncode:
            raise ValueError('concurrent terminal repeat failed: ' + proc.stderr)
    evidence = dict(
        status='pass_host_fixed_source_lifecycle_boundaries', runtime_tested=False,
        first_artifact_behavior_gate_passed=False, requirements_closed=0,
        limitations='Host ABI shims and local dispatch control only; no AppMgr/AppSpawn service, '
                    'kernel identity, SDK cross compilation or guest execution is validated.',
        environment=dict(platform=platform.platform(), locale='C',
                         address_sanitizer=True, undefined_behavior_sanitizer=True,
                         leak_sanitizer=leak_sanitizer,
                         compiler=subprocess.check_output([cxx, '--version'], text=True).splitlines()[0]),
        fixture_provenance=provenance, patch_sha256=digest(PATCH),
        builds=builds, scenarios=rows, concurrent_repeats=20,
    )
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cxx', default='c++')
    args = parser.parse_args()
    result = run(args.output, args.cxx)
    print(json.dumps(dict(status=result['status'], cases=len(result['scenarios']),
                          concurrent_repeats=result['concurrent_repeats'])))
