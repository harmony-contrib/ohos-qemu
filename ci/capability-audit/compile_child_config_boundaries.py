#!/usr/bin/env python3
"""Compile real patched config functions; supplemental, not packaged runtime."""
import argparse
import json
from pathlib import Path
import subprocess
from run_root_probe import digest

ROOT = Path(__file__).resolve().parents[2]
RELATIVE = Path('foundation/ability/ability_runtime/frameworks/native/child_process/src/native_child_process.cpp')
PATCH = ROOT/'patches/common/foundation/ability/ability_runtime/native_child_process/0003-validate-config-boundaries.patch'


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    source = args.source_root/RELATIVE
    original = source.read_text()
    isolated = args.output/'source'/RELATIVE
    isolated.parent.mkdir(parents=True)
    isolated.write_text(original)
    with (args.output/'patch.log').open('xb') as log:
        subprocess.run(['patch', '-p1', '-i', str(PATCH)], cwd=args.output/'source',
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    patched = isolated.read_text()
    start = patched.index('Ability_NativeChildProcess_ErrCode OH_Ability_DestroyChildProcessConfigs')
    end = patched.index('Ability_NativeChildProcess_ErrCode OH_Ability_ChildProcessConfigs_SetProcessName', start)
    unit = args.output/'actual_config_functions.cpp'
    unit.write_text('''#include <cassert>
#include <initializer_list>
#define TAG_LOGE(...) ((void)0)
enum Ability_NativeChildProcess_ErrCode {NCP_NO_ERROR=0,NCP_ERR_INVALID_PARAM=401};
enum NativeChildProcess_IsolationMode {NCP_ISOLATION_MODE_NORMAL=0,NCP_ISOLATION_MODE_ISOLATED=1};
struct Ability_ChildProcessConfigs {NativeChildProcess_IsolationMode isolationMode;};
''' + patched[start:end] + '''
int main() {
    assert(OH_Ability_DestroyChildProcessConfigs(nullptr)==NCP_NO_ERROR);
    auto* config=new Ability_ChildProcessConfigs{NCP_ISOLATION_MODE_ISOLATED};
    assert(OH_Ability_ChildProcessConfigs_SetIsolationMode(nullptr,NCP_ISOLATION_MODE_NORMAL)==NCP_ERR_INVALID_PARAM);
    for(int mode: {-1,2,99}) {
        assert(OH_Ability_ChildProcessConfigs_SetIsolationMode(config,static_cast<NativeChildProcess_IsolationMode>(mode))==NCP_ERR_INVALID_PARAM);
        assert(config->isolationMode==NCP_ISOLATION_MODE_ISOLATED);
    }
    assert(OH_Ability_ChildProcessConfigs_SetIsolationMode(config,NCP_ISOLATION_MODE_NORMAL)==NCP_NO_ERROR);
    assert(config->isolationMode==NCP_ISOLATION_MODE_NORMAL);
    assert(OH_Ability_DestroyChildProcessConfigs(config)==NCP_NO_ERROR);
}
''')
    binary = args.output/'config_functions'
    argv = [args.cxx, '-std=c++17', '-Wall', '-Wextra', '-Werror', str(unit), '-o', str(binary)]
    with (args.output/'compile.log').open('xb') as log:
        subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run([str(binary)], check=True)
    if source.read_text() != original:
        raise ValueError('readonly release source changed during isolated boundary test')
    result = dict(status='pass_compile_supplemental_only', runtime_tested=False,
        first_artifact_behavior_gate_passed=False, source=str(source), source_sha256=digest(source),
        patch_sha256=digest(PATCH), patched_sha256=digest(isolated),
        compile_argv=argv, compiled_unit_sha256=digest(unit), binary_sha256=digest(binary),
        checks=['null destroy succeeds','null mode configs rejects','three invalid modes preserve config',
                'valid mode changes config','nonnull destruction succeeds'])
    (args.output/'evidence.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    run(parser.parse_args())
