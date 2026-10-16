#!/usr/bin/env python3
"""Regenerate both full inherited RIL maps and compile the new actual HDI units."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from compile_native_repair_batch import verify_object

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ril_communication_source', ROOT / 'scripts/prepare_ril_communication_callback.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_map(directory):
    result = {}
    for path in sorted(directory.rglob('iril_callback.h')):
        declarations = re.findall(r'\b(CMD_RIL_CALLBACK_[A-Z0-9_]+)\s*=\s*(\d+)', path.read_text())
        if not declarations:
            raise ValueError('actual generated callback command map missing: ' + str(path))
        result[str(path.relative_to(directory))] = {k: int(v) for k, v in declarations}
    if len(result) < 5:
        raise ValueError('all inherited RIL version command maps required')
    return result


def run(root, output):
    root, output = root.resolve(), output.resolve()
    if any(not os.statvfs(p).f_flag & os.ST_RDONLY for p in (root, root / 'out')):
        raise ValueError('source and product output must be read-only')
    if subprocess.check_output(['git', '-C', str(root / source.PROJECT), 'rev-parse', 'HEAD'], text=True).strip() != source.REVISION:
        raise ValueError('fixed RIL interface project revision required')
    output.mkdir(parents=True, exist_ok=False)
    candidate = output / 'candidate'
    interface = candidate / 'drivers/interface'
    interface.mkdir(parents=True)
    shutil.copytree(root / 'drivers/interface/ril', interface / 'ril')
    originals = {str(p.relative_to(root)): sha(p) for p in sorted((root / 'drivers/interface/ril').rglob('*.idl'))}
    tool = root / 'out/arm64_virt/clang_x64/ability/idl_tool/idl'
    cwd = root / 'out/arm64_virt'
    generated = {}
    for name in ('before', 'after'):
        if name == 'after':
            source.apply(candidate)
            source.apply(candidate)
        directory = output / name
        argv = [str(tool), '--intf-type', 'hdi', '--system', 'full', '--mode', 'ipc', '-d', str(directory), '--gen-cpp']
        for filename in ('IRil.idl', 'IRilCallback.idl', 'Types.idl'):
            argv += ['-c', str(interface / 'ril/v1_5' / filename)]
        argv += ['-r', 'ohos.hdi:' + str(interface)]
        with (output / (name + '-generator.log')).open('xb') as log:
            subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        generated[name] = {'argv': argv, 'commands': command_map(directory),
                           'files_sha256': {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}}
    before, after = generated['before']['commands'], generated['after']['commands']
    old = {**after}
    key = 'ril/v1_5/iril_callback.h'
    old[key] = dict(old[key])
    value = old[key].pop('CMD_RIL_CALLBACK_COMMUNICATION_STATE_UPDATED', None)
    if old != before or value != 162 or before[key] != {
            'CMD_RIL_CALLBACK_GET_PRIMARY_SLOT_RESPONSE': 160, 'CMD_RIL_CALLBACK_SET_PRIMARY_SLOT_RESPONSE': 161}:
        raise ValueError('new RIL event moved or changed an existing inherited transaction')
    header = (output / 'after' / key).read_text()
    if not re.search(r'CommunicationStateUpdated\(const OHOS::HDI::Ril::V1_1::RilRadioResponseInfo& responseInfo,\s*bool is5A\) = 0;', header):
        raise ValueError('actual generated RIL callback ABI differs from agreed service implementation')
    proxy = (output / 'after/ril/v1_5/ril_callback_proxy.cpp').read_text()
    if not re.search(r'int32_t RilCallbackProxy::CommunicationStateUpdated\(.*?TF_ASYNC', proxy, re.S):
        raise ValueError('new generated callback is not actually one-way')
    overlay = output / 'generated-headers.json'
    overlay.write_text(json.dumps({'version': 0, 'roots': [
        {'type': 'file', 'name': str(cwd / 'gen/drivers/interface' / relative),
         'external-contents': str(output / 'after' / relative), 'use-external-name': True}
        for relative in generated['after']['files_sha256'] if relative.endswith('.h')]}) + '\n')
    report = {'status': 'fail', 'scope': 'actual_inherited_HDI_maps_and_complete_generated_TUs_ONLY_NOT_modem_runtime',
              'source_inputs_sha256': originals, 'generator_sha256': sha(tool), 'generation': generated,
              'objects': [], 'first_artifact_behavior_gate_passed': False}
    for unit, target_library in (('ril_callback_stub', 'libril_proxy_1.5'), ('ril_callback_proxy', 'libril_stub_1.5')):
        row = {'unit': unit, 'status': 'fail'}
        try:
            target = 'obj/out/arm64_virt/gen/drivers/interface/ril/v1_5/' + target_library + '/' + unit + '.o'
            query = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'), '-w', 'dupbuild=warn',
                '-C', str(cwd), '-t', 'commands', '-s', target], capture_output=True, text=True, check=True, timeout=180)
            (output / (unit + '-query.log')).write_text(query.stdout + query.stderr)
            argv = shlex.split(query.stdout.splitlines()[-1])
            if Path(argv[0]).name == 'ccache':
                argv.pop(0)
            original = cwd / 'gen/drivers/interface/ril/v1_5' / (unit + '.cpp')
            if (Path(argv[0]).name != 'clang++' or '--target=aarch64-linux-ohos' not in argv or
                    (cwd / argv[argv.index('-c') + 1]).resolve() != original):
                raise ValueError('actual complete RIL product TU command required')
            row['original_argv'] = argv[:]
            obj = output / (unit + '.o')
            argv[argv.index('-c') + 1] = str(output / 'after/ril/v1_5' / (unit + '.cpp'))
            argv[argv.index('-o') + 1] = str(obj)
            argv[argv.index('-MF') + 1] = str(output / (unit + '.d'))
            argv += ['-ivfsoverlay', str(overlay), '-iquote', str(original.parent)]
            row['executed_argv'] = argv
            with (output / (unit + '-compile.log')).open('xb') as log:
                status = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=600).returncode
            row['exit_code'] = status
            if status:
                raise ValueError('actual generated RIL callback compilation failed')
            row.update(verify_object(obj, (cwd / argv[0]).resolve().parent / 'llvm-dis', 'aarch64', 183, 2),
                       status='pass', object_sha256=sha(obj))
        except Exception as error:
            row['error'] = type(error).__name__ + ': ' + str(error)
        report['objects'].append(row)
        (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    report['source_inputs_unchanged'] = all(sha(root / p) == v for p, v in originals.items())
    if report['source_inputs_unchanged'] and all(r['status'] == 'pass' for r in report['objects']):
        report['status'] = 'pass'
    (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'new_transaction': value, 'objects': report['objects']}))
    return report['status'] == 'pass'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.source_root, args.output) else 1)
