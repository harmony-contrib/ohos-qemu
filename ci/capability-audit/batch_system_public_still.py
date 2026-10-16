#!/usr/bin/env python3
"""Fixed actual source composition and bounded host diagnostics, never guest proof."""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURES = HERE / 'fixtures/batch_system/public_still'
COMPONENT = ROOT / 'patches/common/base/msdp/device_status/public_still'
PREFIX = 'base/msdp/device_status/'


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function(text, signature):
    start = text.index(signature); begin = text.index('{', start); depth = 1; end = begin + 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end] + '\n'


def materialize(root):
    meta = json.loads((FIXTURES / 'provenance.json').read_text())
    from batch_system_msdp_input import prepare as prepare_old, COMPONENT as old
    prepare_old(root)
    for relative, row in {**meta['files'], **meta['support_files']}.items():
        data = gzip.decompress(base64.b64decode((FIXTURES / row['file']).read_bytes()))
        if hashlib.sha256(data).hexdigest() != row['sha256']: raise ValueError('actual fixed source changed')
        target = root / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    subprocess.run([sys.executable, str(old / 'apply.py'), '--source-root', str(root)], check=True, capture_output=True)
    return meta


def prepare(output):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    before = output / 'before'; before.mkdir(); meta = materialize(before)
    after = output / 'after'; shutil.copytree(before, after)
    subprocess.run([sys.executable, str(COMPONENT / 'apply.py'), '--source-root', str(after)], check=True, capture_output=True)
    repeated = subprocess.run([sys.executable, str(COMPONENT / 'apply.py'), '--source-root', str(after)], check=True, capture_output=True, text=True)
    if json.loads(repeated.stdout)['status'] != 'already_applied': raise ValueError('installer not idempotent')
    support = {n: row for n, row in meta['support_files'].items() if n.endswith('.h')}
    include = output / 'include'; include.mkdir()
    for relative in support: shutil.copyfile(after / relative, include / Path(relative).name)
    for relative in meta['files']:
        if relative.endswith('.h'): shutil.copyfile(after / relative, include / Path(relative).name)
    # Pure logging/thread naming adapter only. Sensor/IMsdp DTO and API declarations
    # above are the actual fixed headers, not substitute public interfaces.
    (include / 'fi_log.h').write_text('#pragma once\n#define FI_HILOGE(...) do {} while (0)\n#define FI_HILOGI(...) do {} while (0)\n#define FI_HILOGD(...) do {} while (0)\n#define FI_HILOGW(...) do {} while (0)\n#define CALL_DEBUG_ENTER do {} while (0)\n')
    (include / 'include').mkdir()
    (include / 'include/util.h').write_text('#pragma once\n#include <string>\nnamespace OHOS { namespace Msdp { namespace DeviceStatus { inline void SetThreadName(const std::string&) {} } } }\n')
    source = (after / PREFIX / 'services/native/src/devicestatus_msdp_client_impl.cpp').read_text()
    signatures = ['DeviceStatusMsdpClientImpl::DeviceStatusMsdpClientImpl()',
        'ErrCode DeviceStatusMsdpClientImpl::AlgoHandle(', 'ErrCode DeviceStatusMsdpClientImpl::StartAlgo(',
        'ErrCode DeviceStatusMsdpClientImpl::GetAlgoAbility(', 'ErrCode DeviceStatusMsdpClientImpl::AlgoDisable(',
        'ErrCode DeviceStatusMsdpClientImpl::RegisterAlgo()', 'ErrCode DeviceStatusMsdpClientImpl::RegisterImpl(',
        'void DeviceStatusMsdpClientImpl::OnResult(', 'int32_t DeviceStatusMsdpClientImpl::MsdpCallback(',
        'Data DeviceStatusMsdpClientImpl::SaveObserverData(', 'ErrCode DeviceStatusMsdpClientImpl::ImplCallback(',
        'ErrCode DeviceStatusMsdpClientImpl::LoadAlgoLibrary()', 'ErrCode DeviceStatusMsdpClientImpl::UnloadAlgoLibrary()',
        'void DeviceStatusMsdpClientImpl::RetireAlgo()', 'ErrCode DeviceStatusMsdpClientImpl::UnloadAlgoLibraryLocked()',
        'IMsdp* DeviceStatusMsdpClientImpl::GetAlgoInst(']
    (output / 'actual_client.inc').write_text('\n'.join(function(source, x) for x in signatures))
    source = (after / PREFIX / 'services/native/src/devicestatus_manager.cpp').read_text()
    signatures = ['void DeviceStatusManager::DeviceStatusCallbackDeathRecipient::OnRemoteDied(',
        'int32_t DeviceStatusManager::NotifyDeviceStatusChange(', 'void DeviceStatusManager::Subscribe(Type type,',
        'void DeviceStatusManager::Unsubscribe(Type type,', 'bool DeviceStatusManager::HasObjectLocked(',
        'void DeviceStatusManager::ReconcileType(', 'void DeviceStatusManager::RemoveDeadCallback(',
        'DeviceStatusManager::~DeviceStatusManager()']
    (output / 'actual_manager.inc').write_text('\n'.join(function(source, x) for x in signatures))
    header = (after / PREFIX / 'services/native/include/devicestatus_manager.h').read_text()
    (output / 'actual_manager_death.inc').write_text(function(header, 'class DeviceStatusCallbackDeathRecipient :').rstrip() + ';\n')
    result = {'status': 'pass_source_composition_only', 'scope': 'actual fixed14 source guard/extraction; no compiler or guest',
        'fixture_provenance_sha256': digest(FIXTURES / 'provenance.json'),
        'manifest_sha256': digest(COMPONENT / 'manifest.json'), 'sources_sha256': {n: digest(after / n) for n in meta['files']},
        'actual_client_functions_sha256': digest(output / 'actual_client.inc'),
        'actual_manager_functions_sha256': digest(output / 'actual_manager.inc'),
        'actual_manager_death_declaration_sha256': digest(output / 'actual_manager_death.inc'),
        'compiler_invoked': False, 'requirements_closed': 0, 'first_artifact_behavior_gate_passed': False}
    (output / 'prepare.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def run(output, cxx):
    output = Path(output).resolve(); prepare(output)
    after = output / 'after'; include = output / 'include'
    env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C', ASAN_OPTIONS='detect_leaks=1:halt_on_error=1', UBSAN_OPTIONS='halt_on_error=1')
    common = [cxx, '-std=c++17', '-g', '-O1', '-Wall', '-Wextra', '-Werror', '-pthread',
        '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-gnu-unique', '-DDEVICE_STATUS_SENSOR_ENABLE',
        '-I' + str(include), '-I' + str(output)]
    source_names = ['libs/src/datahub/sensor_data_callback.cpp', 'libs/src/devicestatus_algorithm_manager.cpp',
        'libs/src/algorithm/algo_absolute_still.cpp', 'libs/src/algorithm/algo_horizontal.cpp', 'libs/src/algorithm/algo_vertical.cpp',
        'libs/src/algorithm/algo_base.cpp']
    library = output / 'libactual_msdp.so'; binary = output / 'actual_msdp_host'
    argv = [common + ['-shared', '-fPIC'] + [str(after / PREFIX / n) for n in source_names] +
        [str(HERE / 'batch_system_public_still_harness.cpp'), '-DBATCH_PLUGIN_HELPERS', '-o', str(library)],
        common + [str(HERE / 'batch_system_public_still_harness.cpp'), '-rdynamic', '-ldl', '-o', str(binary)]]
    evidence = {'status': 'fail', 'scope': 'Linux_host_actual_algorithm_DSO_and_extracted_service_retirement_manager_functions_ONLY_NOT_guest',
        'commands': [], 'cases': [], 'first_artifact_behavior_gate_passed': False, 'requirements_closed': 0}
    def save():
        (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    save()
    try:
        for i, command in enumerate(argv):
            log = output / ('compile-' + str(i) + '.log')
            with log.open('wb') as stream:
                try:
                    completed = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=60)
                    code = completed.returncode
                except subprocess.TimeoutExpired:
                    code = 124
            evidence['commands'].append({'argv': command, 'exit_code': code, 'log_sha256': digest(log)})
            save()
        if any(c['exit_code'] for c in evidence['commands']):
            return evidence
        for name in ['public_type_and_shared_input', 'callback_stop', 'restart_reload', 'batch_rollback', 'deactivate_retry',
                     'relative_unsupported', 'owner_required', 'external_callback_quiesce', 'manager_first_last', 'manager_rollback', 'manager_death', 'manager_reentry', 'manager_event_filters']:
            started = time.monotonic(); log = output / (name + '.log')
            with log.open('wb') as stream:
                try:
                    completed = subprocess.run([str(binary), str(library), name], env=env, stdout=stream,
                                               stderr=subprocess.STDOUT, timeout=4)
                    code = completed.returncode
                except subprocess.TimeoutExpired:
                    code = 124
            evidence['cases'].append({'name': name, 'exit_code': code, 'seconds': time.monotonic() - started, 'log_sha256': digest(log)})
            save()
        evidence.update(status='fail' if any(c['exit_code'] for c in evidence['cases']) else 'pass',
                        algorithm_DSO_sha256=digest(library), harness_binary_sha256=digest(binary))
    finally:
        save()
    return evidence


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--compile-and-run', action='store_true'); p.add_argument('--cxx', default='g++')
    a = p.parse_args(); result = run(a.output, a.cxx) if a.compile_and_run else prepare(a.output)
    print(json.dumps({'status': result['status']}))
    if a.compile_and_run and result['status'] != 'pass':
        raise SystemExit(1)
