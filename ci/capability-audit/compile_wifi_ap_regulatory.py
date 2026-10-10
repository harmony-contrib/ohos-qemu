#!/usr/bin/env python3
"""Compile full candidate AP HAL TUs against read-only real product commands.

Does not regenerate GN, link a service, prove service permissions or close WLAN.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/wifi/software_ap_regulatory'
PREFIX = 'foundation/communication/wifi/wifi/services/wifi_standard/wifi_framework/wifi_manage/wifi_native/'
SOURCE = PREFIX + 'wifi_hal_interface/wifi_ap_hal_interface.cpp'
HEADER = PREFIX + 'wifi_hal_interface/wifi_software_regulatory.h'
TARGET = 'obj/' + PREFIX + 'wifi_hal_interface/wifi_native/wifi_ap_hal_interface.o'
PRODUCTS = {'arm64_virt': 'aarch64-linux-ohos', 'armv7a_virt': 'arm-linux-ohos',
            'x86_64_virt': 'x86_64-linux-ohos'}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def run(args):
    source_root = args.source_root.resolve()
    if not os.statvfs(source_root).f_flag & os.ST_RDONLY:
        raise ValueError('source and product inputs must be mounted read-only')
    args.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('ap_regulatory_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if baseline.validate(source_root):
        raise ValueError('isolated check requires pristine component source')
    paths = [Path(baseline.PROJECT) / row[0] for row in baseline.FILES]
    original = {str(p): digest(source_root / p) if (source_root / p).exists() else None for p in paths}
    inputs = [Path(__file__), *COMPONENT.glob('*.patch'), COMPONENT / 'apply.sh', COMPONENT / 'verify_source.py',
              ROOT / 'patches/lib/apply_exact_component.py', ROOT / 'patches/lib/exact_source_states.py']
    before = {str(p): digest(p) for p in inputs}
    report = dict(status='fail', scope='full_candidate_TU_compilation_NOT_link_GN_or_guest_acceptance',
        closed=[], first_artifact_behavior_gate_passed=False, commands=[], original_sha256=original,
        component_inputs_sha256=before, candidate_GN_feature_selection_verified=False)
    try:
        with tempfile.TemporaryDirectory(prefix='wifi-ap-regulatory-full-tu-') as temporary:
            staged = Path(temporary)
            for p in paths:
                if (source_root / p).exists():
                    (staged / p).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_root / p, staged / p)
            for attempt in (1, 2):
                with (args.output / ('apply-' + str(attempt) + '.log')).open('x') as log:
                    subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(staged)],
                                   stdout=log, stderr=subprocess.STDOUT, check=True)
            baseline.validate(staged, require_patched=True)
            report['patched_sha256'] = {str(p): digest(staged / p) for p in paths}
            for product, triple in PRODUCTS.items():
                cwd = source_root / 'out' / product
                query = subprocess.run([str(source_root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                    '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', TARGET],
                    capture_output=True, text=True, check=True)
                (args.output / (product + '-query.log')).write_text(query.stdout + query.stderr)
                argv = shlex.split(query.stdout.splitlines()[-1])
                if Path(argv[0]).name == 'ccache':
                    argv.pop(0)
                if (Path(argv[0]).name != 'clang++' or '--target=' + triple not in argv or
                    any(x in argv for x in ('&&', ';', '|')) or any(argv.count(x) != 1 for x in ('-c', '-o', '-MF')) or
                    (cwd / argv[argv.index('-c') + 1]).resolve() != source_root / SOURCE or
                    '-DHDI_CHIP_INTERFACE_SUPPORT' in argv or '-DHDI_WPA_INTERFACE_SUPPORT' not in argv):
                    raise ValueError('unexpected actual non-chip WPA product compile command: ' + product)
                actual = argv[:]
                argv[1:1] = ['-DWIFI_SOFTWARE_AP_REGULATORY_BACKEND',
                             '-I' + str(source_root / 'third_party/libnl/libnl/include')]
                obj = args.output / (product + '.o')
                dependencies = args.output / (product + '.d')
                argv[argv.index('-c') + 1] = str(staged / SOURCE)
                argv[argv.index('-o') + 1] = str(obj)
                argv[argv.index('-MF') + 1] = str(dependencies)
                log = args.output / (product + '-compile.log')
                with log.open('x') as stream:
                    result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                            env=dict(os.environ, CCACHE_DISABLE='1'))
                row = dict(product=product, original_argv=actual, candidate_argv=argv,
                           exit_code=result.returncode, log_sha256=digest(log))
                report['commands'].append(row)
                if result.returncode:
                    raise ValueError('full candidate TU compile failed: ' + product)
                if str(staged / HEADER) not in dependencies.read_text():
                    raise ValueError('compiler did not consume exact candidate regulatory header')
                row.update(object_sha256=digest(obj), dependencies_sha256=digest(dependencies))
            if original != {str(p): digest(source_root / p) if (source_root / p).exists() else None for p in paths}:
                raise ValueError('read-only source changed during candidate compilation')
            if before != {str(p): digest(p) for p in inputs}:
                raise ValueError('component inputs changed during candidate compilation')
            report['status'] = 'pass'
    except Exception as error:
        report['error'] = str(error)
    (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))
