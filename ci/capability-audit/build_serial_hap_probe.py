#!/usr/bin/env python3
"""Build an unsigned, permission-free ordinary Serial HAP (SDK check only)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

ARCHITECTURES = {'arm64': ('aarch64-linux-ohos', 'arm64-v8a'),
                 'armv7a': ('arm-linux-ohos', 'armeabi-v7a'), 'x86_64': ('x86_64-linux-ohos', 'x86_64')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, default=Path('/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony'))
    parser.add_argument('--arch', choices=ARCHITECTURES, default='arm64')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    parser.add_argument('--run-id', default=uuid.uuid4().hex)
    parser.add_argument('--port-name', default='ttyUSB0')
    parser.add_argument('--bundle-name', default='org.harmonycontrib.serialaudit')
    parser.add_argument('--scenario', choices=('basic', 'attachment', 'usb-manager'), default='basic')
    parser.add_argument('--usb-actor', choices=('owner', 'peer'), default='owner')
    parser.add_argument('--hvigor-home', type=Path, default=Path(os.environ.get('QEMU_TEST_HVIGOR_HOME',
        '/Applications/DevEco-Studio.app/Contents/tools/hvigor')))
    parser.add_argument('--node-home', type=Path, default=Path(os.environ.get('QEMU_TEST_NODE_HOME',
        '/Applications/DevEco-Studio.app/Contents/tools/node')))
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{32}', args.run_id) or not re.fullmatch('tty(?:USB|ACM)[0-9]+', args.port_name):
        parser.error('run-id needs 32 lowercase hex digits and port-name a dedicated ttyUSB/ttyACM basename')
    if not re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+', args.bundle_name):
        parser.error('invalid normal application bundle name')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError('output project directory must be empty; refusing to overwrite')
    triple, abi = ARCHITECTURES[args.arch]

    def write(relative, content):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if isinstance(content, str) else json.dumps(content, indent=2) + '\n')

    write('AppScope/app.json5', {'app': {'bundleName': args.bundle_name, 'vendor': 'harmony-contrib',
          'versionCode': 1, 'versionName': '1.0.0', 'icon': '$media:icon', 'label': '$string:app_name'}})
    write('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'Serial audit'}]})
    write('AppScope/resources/base/media/icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128">'
          '<rect width="128" height="128" fill="#336699"/></svg>')
    write('build-profile.json5', {'app': {'products': [{'name': 'default', 'targetSdkVersion': '7.0.0(26)',
          'compatibleSdkVersion': '7.0.0(26)', 'runtimeOS': 'HarmonyOS'}],
          'buildModeSet': [{'name': 'debug'}, {'name': 'release'}]},
          'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    for relative in ('oh-package.json5', 'entry/oh-package.json5'):
        write(relative, {'modelVersion': '6.0.0', 'name': 'serial-audit', 'version': '1.0.0', 'dependencies': {}})
    write('entry/build-profile.json5', {'apiType': 'stageMode',
          'buildOption': {'externalNativeOptions': {'abiFilters': [abi]}}, 'targets': [{'name': 'default'}]})
    write('entry/src/main/module.json5', {'module': {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility',
          'deviceTypes': ['2in1'], 'deliveryWithInstall': True, 'installationFree': False,
          'pages': '$profile:main_pages', 'requestPermissions': [],
          'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets', 'exported': True,
                         'label': '$string:app_name', 'icon': '$media:icon', 'startWindowIcon': '$media:icon',
                         'startWindowBackground': '$color:background'}]}})
    if args.scenario == 'usb-manager':
        module_path = root / 'entry/src/main/module.json5'
        module = json.loads(module_path.read_text())
        module['module']['abilities'][0]['launchType'] = 'singleton'
        write('entry/src/main/module.json5', module)
    write('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'background', 'value': '#ffffff'}]})
    write('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    write('entry/src/main/ets/entryability/EntryAbility.ets',
          "import UIAbility from '@ohos.app.ability.UIAbility';\nimport window from '@ohos.window';\n"
          "export default class EntryAbility extends UIAbility {\n"
          "  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }\n}\n")
    directory = Path(__file__).resolve().parent
    template = ('usb_manager_probe.ets' if args.scenario == 'usb-manager' else
                'serial_attachment_probe.ets' if args.scenario == 'attachment' else 'serial_probe.ets')
    page = (directory / template).read_text().replace('__SERIAL_RUN_ID__', args.run_id)
    page = page.replace('__SERIAL_BUNDLE__', args.bundle_name).replace('__SERIAL_PORT_NAME__', args.port_name)
    page = page.replace('__USB_ACTOR__', args.usb_actor)
    write('entry/src/main/ets/pages/Index.ets', page)
    write('entry/src/main/cpp/types/libserialaclprobe/index.d.ts',
          'export const check: (portName: string) => string;\n'
          'export const unauthorizedGrant: () => Promise<void>;\n')
    libraries = root / 'entry/libs' / abi
    libraries.mkdir(parents=True)
    native = args.sdk.resolve() / 'native'
    flags = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon'] if args.arch == 'armv7a' else []
    command = [str(native / 'llvm/bin/clang++'), '--target=' + triple, '--sysroot=' + str(native / 'sysroot'),
               *flags, '-std=c++17', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
               str(directory / 'serial_acl_hap_probe.cpp'), '-lace_napi.z', '-o', str(libraries / 'libserialaclprobe.so')]
    native_log = root / 'native-sdk-build.log'
    with native_log.open('w') as stream:
        subprocess.run(command, check=True, stdout=stream, stderr=subprocess.STDOUT)
    shutil.copy2(native / 'llvm/lib' / triple / 'libc++_shared.so', libraries / 'libc++_shared.so')
    hap_log = root / 'arkts-sdk-build.log'
    with hap_log.open('w') as stream:
        if args.scenario == 'usb-manager':
            # Type-check the new public caller using the actual official API26
            # compiler. The existing Serial personas retain their original path.
            hvigor = args.hvigor_home.resolve()
            node = args.node_home.resolve()
            if not (hvigor / 'bin/hvigorw').is_file() or not (node / 'bin/node').is_file():
                raise ValueError('actual official Hvigor/Node required for USBManager source checking')
            write('build-profile.json5', {'app': {'products': [{'name': 'default',
                'compileSdkVersion': '26.0.0', 'targetSdkVersion': '26.0.0', 'compatibleSdkVersion': '26.0.0',
                'runtimeOS': 'OpenHarmony'}], 'buildModeSet': [{'name': 'debug'}, {'name': 'release'}]},
                'modules': [{'name': 'entry', 'srcPath': './entry',
                    'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
            # The real clang++ invocation above already built the native probe
            # into entry/libs/<abi>. Do not request a second, absent CMake tree.
            write('entry/build-profile.json5', {'apiType': 'stageMode',
                'targets': [{'name': 'default'}]})
            plugin = str(hvigor / 'hvigor-ohos-plugin')
            write('hvigorfile.ts', "import { appTasks } from '" + plugin + "';\nexport default { system: appTasks, plugins: [] };\n")
            write('entry/hvigorfile.ts', "import { hapTasks } from '" + plugin + "';\nexport default { system: hapTasks, plugins: [] };\n")
            write('hvigor/hvigor-config.json5', {'modelVersion': '6.0.0', 'dependencies': {},
                'execution': {'daemon': False, 'parallel': False}, 'logging': {'level': 'info'}})
            write('local.properties', 'sdk.dir=' + str(args.sdk.resolve().parent) + '\n')
            module = json.loads((root / 'entry/src/main/module.json5').read_text())
            module['module']['deviceTypes'] = ['default']
            write('entry/src/main/module.json5', module)
            subprocess.run([str(hvigor / 'bin/hvigorw'), 'assembleHap', '--no-daemon',
                '-p', 'product=default', '-p', 'buildMode=debug'], cwd=root,
                env=dict(os.environ, OHOS_SDK_HOME=str(args.sdk.resolve().parent), NODE_HOME=str(node)),
                check=True, stdout=stream, stderr=subprocess.STDOUT)
        else:
            subprocess.run([args.arkdown, 'build', '--project', str(root), '--target', 'hap', '--mode', 'debug'],
                           cwd=root, env=dict(os.environ, OHOS_SDK_HOME=str(args.sdk.resolve())), check=True,
                           stdout=stream, stderr=subprocess.STDOUT)
    hap = root / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
    inputs = {'scope': 'unsigned_ordinary_hap_sdk_build_only_not_runtime_acceptance', 'run_id': args.run_id,
              'bundle_name': args.bundle_name, 'port_name': args.port_name, 'arch': args.arch,
              'scenario': args.scenario, 'usb_actor': args.usb_actor if args.scenario == 'usb-manager' else None,
              'page_source_sha256': hashlib.sha256((directory / template).read_bytes()).hexdigest(),
              'request_permissions': [], 'native_compile_command': command, 'unsigned_hap': str(hap),
              'hap_sha256': hashlib.sha256(hap.read_bytes()).hexdigest(), 'first_package_gate_passed': False}
    inputs.update(native_sdk_log_sha256=hashlib.sha256(native_log.read_bytes()).hexdigest(),
                  arkts_sdk_log_sha256=hashlib.sha256(hap_log.read_bytes()).hexdigest())
    write('serial-probe-inputs.json', inputs)
    print(json.dumps(inputs, indent=2))


if __name__ == '__main__':
    main()
