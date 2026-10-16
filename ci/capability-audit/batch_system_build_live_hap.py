#!/usr/bin/env python3
"""Generate one fresh ordinary caller; SDK build only with explicit --build."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from batch_system_live_inputs import (BUNDLE, FIXTURES, PERMISSIONS, digest, nonce,
                                     project_files, sdk_contract, verify_project, write_json,
                                     SDK_PRODUCT, HVIGOR_CONFIG, HVIGOR_APP, HVIGOR_HAP,
                                     ENTRY_PROFILE, NATIVE_TARGETS, native_packaging)


def generate(output, sdk, arch, run_id):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    declarations = sdk_contract(sdk)
    abi, triple = NATIVE_TARGETS[arch]
    def put(name, content):
        p = output / name; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content if isinstance(content, str) else json.dumps(content, indent=2) + '\n')
    put('AppScope/app.json5', {'app': {'bundleName': BUNDLE, 'vendor': 'harmony-contrib',
        'versionCode': 1, 'versionName': '1.0.0', 'icon': '$media:icon', 'label': '$string:app_name'}})
    put('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'Live input audit'}]})
    put('AppScope/resources/base/media/icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#336688"/></svg>')
    put('build-profile.json5', {'app': {'products': [SDK_PRODUCT]},
        'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    put('hvigor/hvigor-config.json5', HVIGOR_CONFIG)
    put('hvigorfile.ts', HVIGOR_APP)
    put('entry/hvigorfile.ts', HVIGOR_HAP)
    put('oh-package.json5', {'modelVersion': '6.0.0', 'name': 'live-input-audit', 'version': '1.0.0', 'dependencies': {}, 'devDependencies': {}})
    put('entry/oh-package.json5', {'modelVersion': '6.0.0', 'name': 'entry', 'version': '1.0.0',
        'dependencies': {'libliveinputaudit.so': 'file:./src/main/cpp/types/libliveinputaudit'}})
    # The SDK compiles the NAPI library into entry/libs/<abi> before Hvigor.
    # externalNativeOptions selects the CMake task even when it only has abiFilters.
    put('entry/build-profile.json5', ENTRY_PROFILE)
    put('entry/src/main/module.json5', {'module': {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility',
        'deviceTypes': ['default'], 'deliveryWithInstall': True, 'installationFree': False, 'pages': '$profile:main_pages',
        'requestPermissions': [{'name': name, 'reason': '$string:permission_reason',
            'usedScene': {'abilities': ['EntryAbility'], 'when': 'inuse'}} for name in PERMISSIONS],
        'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets', 'exported': True,
            'label': '$string:app_name', 'icon': '$media:icon', 'startWindowIcon': '$media:icon', 'startWindowBackground': '$color:background'}]}})
    put('entry/src/main/resources/base/element/string.json', {'string': [{'name': 'permission_reason', 'value': 'Observe externally supplied device input'}]})
    put('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'background', 'value': '#ffffff'}]})
    put('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    put('entry/src/main/ets/entryability/EntryAbility.ets', (FIXTURES / 'EntryAbility.ets').read_text())
    put('entry/src/main/ets/pages/Index.ets', (FIXTURES / 'Index.ets.in').read_text().replace('__LIVE_RUN_ID__', nonce(run_id)))
    put('socket_probe.cpp', (FIXTURES / 'socket_probe.cpp').read_text())
    put('entry/src/main/cpp/types/libliveinputaudit/Index.d.ts',
        'interface Native { clock(): string; denials(): string; }\ndeclare const native: Native;\nexport default native;\n')
    put('entry/src/main/cpp/types/libliveinputaudit/oh-package.json5',
        {'name': 'libliveinputaudit.so', 'version': '1.0.0', 'types': './Index.d.ts'})
    write_json(output / 'live-inputs-contract.json', {'schema_version': 1, 'bundle': BUNDLE, 'role': 'ordinary_app',
        'run_id': run_id, 'arch': arch, 'sdk': declarations, 'source_files': project_files(output),
        'fixture_hashes': {p.name: digest(p) for p in FIXTURES.iterdir() if p.is_file()}, 'triple': triple, 'abi': abi,
        'native_packaging': native_packaging(arch),
        'not_claimed': 'SDK compilation, valid signature, public callback delivery, MSDP backend or package gate'})
    return verify_project(output, sdk, run_id, arch)


def build(project, sdk, arch, run_id, arkdown):
    project = Path(project).resolve(); sdk = Path(sdk).resolve()
    value = verify_project(project, sdk, run_id, arch)
    library = project / value['native_packaging']['relative_library']
    libs = library.parent; libs.mkdir(parents=True)
    commands = [[str(sdk / 'native/llvm/bin/clang++'), '--target=' + value['triple'],
        '--sysroot=' + str(sdk / 'native/sysroot'), '-std=c++17', '-shared', '-fPIC', '-O2',
        '-Wall', '-Wextra', '-Werror', str(project / 'socket_probe.cpp'), '-lace_napi.z',
        '-o', str(library)],
        [arkdown, 'build', '--project', str(project), '--target', 'hap', '--mode', 'debug']]
    report = {'status': 'fail', 'commands': [], 'source_contract_sha256': digest(project / 'live-inputs-contract.json')}
    try:
        for i, argv in enumerate(commands):
            started = time.time()
            p = subprocess.run(argv, cwd=project, env=dict(os.environ, OHOS_SDK_HOME=str(sdk)),
                capture_output=True, timeout=1800)
            log = project / ('build-' + str(i) + '.log'); log.write_bytes(p.stdout + p.stderr)
            report['commands'].append({'argv': argv, 'exit_code': p.returncode, 'started_epoch': started,
                                      'log': str(log), 'sha256': digest(log)})
            if p.returncode: raise ValueError('actual SDK build command failed')
        verify_project(project, sdk, run_id, arch)
        hap = project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
        report.update(status='pass', unsigned_hap=str(hap), unsigned_hap_sha256=digest(hap),
            native_library=str(library), native_sha256=digest(library))
    finally:
        write_json(project / 'live-inputs-build.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--sdk', type=Path, required=True)
    p.add_argument('--run-id', required=True); p.add_argument('--arch', choices=['arm64', 'armv7a', 'x86_64'], default='arm64')
    p.add_argument('--build', action='store_true'); p.add_argument('--arkdown', default='arkdown')
    a = p.parse_args(); generate(a.output, a.sdk, a.arch, nonce(a.run_id))
    if a.build: build(a.output, a.sdk, a.arch, a.run_id, a.arkdown)
    print(a.output / 'live-inputs-contract.json')


if __name__ == '__main__': main()
