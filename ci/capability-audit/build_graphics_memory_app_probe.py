#!/usr/bin/env python3
"""Build public C++/ArkTS graphics-memory callers; only real real allocation accounting can pass them."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from build_serial_hap_probe import ARCHITECTURES
from run_root_probe import digest

BUNDLE = 'org.harmonycontrib.graphicsmemoryaudit'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--arch', choices=ARCHITECTURES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    args = parser.parse_args()
    if re.fullmatch('[0-9a-f]{32}', args.run_id) is None:
        parser.error('fresh 32-digit hexadecimal run-id required')
    root, sdk = args.output.resolve(), args.sdk.resolve()
    metadata = json.loads((sdk / 'ets/oh-uni-package.json').read_text())
    if str(metadata.get('apiVersion')) != '26' or metadata.get('releaseType') != 'Release':
        raise ValueError('actual API26 Release SDK required')
    root.mkdir(parents=True, exist_ok=False)
    triple, abi = ARCHITECTURES[args.arch]
    directory = Path(__file__).resolve().parent
    source = directory / 'graphics_memory_app_probe.cpp'
    template = directory / 'graphics_memory_app_probe.ets'
    report = dict(status='fail', scope='unsigned_public_graphicsmemory_callers_build_NOT_buffer_accounting',
        arch=args.arch, run_id=args.run_id, bundle=BUNDLE, request_permissions=[],
        source_sha256=digest(source), template_sha256=digest(template), builder_sha256=digest(Path(__file__)),
        sdk=str(sdk), closed=[], first_artifact_behavior_gate_passed=False, commands=[])

    def write(name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')

    try:
        write('AppScope/app.json5', {'app': {'bundleName': BUNDLE, 'vendor': 'harmony-contrib',
            'versionCode': 1, 'versionName': '1.0.0', 'icon': '$media:icon', 'label': '$string:app_name'}})
        write('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'HiDebug audit'}]})
        write('AppScope/resources/base/media/icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" fill="#336699"/></svg>')
        write('build-profile.json5', {'app': {'products': [{'name': 'default', 'targetSdkVersion': '7.0.0(26)',
            'compatibleSdkVersion': '7.0.0(26)', 'runtimeOS': 'HarmonyOS'}],
            'buildModeSet': [{'name': 'debug'}, {'name': 'release'}]},
            'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
        for relative in ('oh-package.json5', 'entry/oh-package.json5'):
            write(relative, {'modelVersion': '6.0.0', 'name': 'graphicsmemory-audit', 'version': '1.0.0', 'dependencies': {}})
        write('entry/build-profile.json5', {'apiType': 'stageMode',
            'buildOption': {'externalNativeOptions': {'abiFilters': [abi]}}, 'targets': [{'name': 'default'}]})
        write('entry/src/main/module.json5', {'module': {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility',
            'deviceTypes': ['phone', '2in1'], 'deliveryWithInstall': True, 'installationFree': False,
            'pages': '$profile:main_pages', 'requestPermissions': [],
            'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets', 'exported': True,
                'label': '$string:app_name', 'icon': '$media:icon', 'startWindowIcon': '$media:icon',
                'startWindowBackground': '$color:background'}]}})
        write('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'background', 'value': '#ffffff'}]})
        write('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
        write('entry/src/main/ets/entryability/EntryAbility.ets',
            "import UIAbility from '@ohos.app.ability.UIAbility';\nimport window from '@ohos.window';\n"
            "export default class EntryAbility extends UIAbility {\n"
            "  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }\n}\n")
        write('entry/src/main/ets/pages/Index.ets', template.read_text().replace('__RUN__', args.run_id))
        write('entry/src/main/cpp/types/libgraphicsmemoryprobe/index.d.ts',
            'interface Probe { action: (phase: number) => number; snapshot: () => number[]; }\ndeclare const probe: Probe;\nexport default probe;\n')
        libraries = root / 'entry/libs' / abi
        libraries.mkdir(parents=True)
        native = sdk / 'native'
        flags = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon'] if args.arch == 'armv7a' else []
        command = [str(native / 'llvm/bin/clang++'), '--target=' + triple, '--sysroot=' + str(native / 'sysroot'),
            *flags, '-std=c++17', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
            '-fno-exceptions', '-fno-rtti', '-nostdlib++', str(source), '-lace_napi.z', '-lohhidebug', '-lnative_buffer',
            '-o', str(libraries / 'libgraphicsmemoryprobe.so')]
        for label, argv in (('native-sdk', command), ('arkts-sdk',
                [args.arkdown, 'build', '--project', str(root), '--target', 'hap', '--mode', 'debug'])):
            log = root / (label + '-build.log')
            with log.open('x') as stream:
                result = subprocess.run(argv, cwd=root, env=dict(os.environ, OHOS_SDK_HOME=str(sdk)),
                    stdout=stream, stderr=subprocess.STDOUT)
            report['commands'].append(dict(argv=argv, exit_code=result.returncode, log_sha256=digest(log)))
            if result.returncode:
                raise ValueError('actual SDK build failed: ' + label)
        hap = root / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
        if digest(source) != report['source_sha256'] or digest(template) != report['template_sha256']:
            raise ValueError('graphics-memory caller changed during actual compilation')
        report.update(status='pass', unsigned_hap=str(hap), hap_sha256=digest(hap),
            generated_source_sha256=digest(root / 'entry/src/main/ets/pages/Index.ets'),
            native_library_sha256=digest(libraries / 'libgraphicsmemoryprobe.so'),
            module_sha256=digest(root / 'entry/src/main/module.json5'),
            declarations_sha256={name: digest(sdk / relative) for name, relative in
                [('cxx', 'native/sysroot/usr/include/hidebug/hidebug.h'), ('arkts', 'ets/api/@ohos.hidebug.d.ts')]})
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    write('graphicsmemory-probe-inputs.json', report)
    print(json.dumps(dict(status=report['status'], error=report.get('error'))))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
