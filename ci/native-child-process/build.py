#!/usr/bin/env python3
"""Build a minimal SDK C API regression HAP; requires arkdown and hap-sign."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--arch', choices=['arm64', 'armv7a', 'x86_64'], default='arm64')
p.add_argument('--sdk', type=Path, default=Path('/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony'))
p.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
p.add_argument('--hap-sign', default=os.environ.get('HAP_SIGN', 'hap-sign'))
p.add_argument('--udid', required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--single-case', choices=['150KiB-ascii', 'empty', 'core'])
p.add_argument('--foreground-probe', action='store_true',
               help='start Native regression only from the UI foreground callback')
a = p.parse_args()
root = a.output.resolve()
root.mkdir(parents=True, exist_ok=True)
triple, abi = {'arm64': ('aarch64-linux-ohos', 'arm64-v8a'), 'armv7a': ('arm-linux-ohos', 'armeabi-v7a'), 'x86_64': ('x86_64-linux-ohos', 'x86_64')}[a.arch]
bundle = 'org.harmonycontrib.childprocessregression'
def write(name, data):
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) if not isinstance(data, str) else data)
write('AppScope/app.json5', {'app': {'bundleName': bundle, 'vendor': 'harmony-contrib', 'versionCode': 1, 'versionName': '1.0.0', 'icon': '$media:icon', 'label': '$string:app_name'}})
write('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'Child process regression'}]})
write('AppScope/resources/base/media/icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" fill="#2355aa"/></svg>')
write('build-profile.json5', {'app': {'products': [{'name': 'default', 'targetSdkVersion': '5.0.5(17)', 'compatibleSdkVersion': '5.0.5(17)', 'runtimeOS': 'HarmonyOS'}], 'buildModeSet': [{'name': 'debug'}, {'name': 'release'}]}, 'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
write('oh-package.json5', {'modelVersion': '6.0.0', 'name': 'native-child-process-regression', 'version': '1.0.0', 'dependencies': {}})
write('entry/oh-package.json5', {'modelVersion': '6.0.0', 'name': 'entry', 'version': '1.0.0', 'dependencies': {}})
write('entry/build-profile.json5', {'apiType': 'stageMode', 'buildOption': {'externalNativeOptions': {'abiFilters': [abi]}}, 'targets': [{'name': 'default'}]})
module = {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility',
          'deviceTypes': ['phone', '2in1'], 'deliveryWithInstall': True,
          'installationFree': False, 'pages': '$profile:main_pages',
          'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets',
                         'exported': True, 'label': '$string:app_name', 'icon': '$media:icon',
                         'startWindowIcon': '$media:icon', 'startWindowBackground': '$color:background'}]}
write('entry/src/main/module.json5', {'module': module})
write('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'background', 'value': '#ffffff'}]})
write('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
if a.foreground_probe:
    write('entry/src/main/ets/entryability/EntryAbility.ets', '''import { UIAbility, Want } from '@kit.AbilityKit';
import window from '@ohos.window';
import probe from 'libprobe.so';
export default class EntryAbility extends UIAbility {
  private caseIndex: number = -1;
  private launched: boolean = false;
  onCreate(want: Want): void {
    const value = want.parameters?.['regressionCase'];
    if (typeof value === 'number') { this.caseIndex = value; }
  }
  onWindowStageCreate(stage: window.WindowStage): void {
    stage.loadContent('pages/Index');
  }
  onForeground(): void {
    if (this.launched) { return; }
    this.launched = true;
    if (this.caseIndex >= 0) { probe.runCase(this.caseIndex); }
    else { probe.run(); }
  }
}
''')
else:
    write('entry/src/main/ets/entryability/EntryAbility.ets', '''import { UIAbility, Want } from '@kit.AbilityKit';
import window from '@ohos.window';
import probe from 'libprobe.so';
export default class EntryAbility extends UIAbility {
  private caseIndex: number = -1;
  onCreate(want: Want): void {
    const value = want.parameters?.['regressionCase'];
    if (typeof value === 'number') { this.caseIndex = value; }
  }
  onWindowStageCreate(stage: window.WindowStage): void {
    stage.loadContent('pages/Index');
    if (this.caseIndex >= 0) { probe.runCase(this.caseIndex); }
    else { probe.run(); }
  }
}
''')
write('entry/src/main/ets/pages/Index.ets', '@Entry\n@Component\nstruct Index { build() { Column() { Text("Native child process regression") } } }\n')
libs = root / 'entry/libs' / abi
libs.mkdir(parents=True, exist_ok=True)
native = a.sdk / 'native'
cmd = [str(native / 'llvm/bin/clang++'), '--target=' + triple, '--sysroot=' + str(native / 'sysroot'), '-std=c++17', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror', str(Path(__file__).with_name('probe.cpp').resolve()), '-lchild_process', '-lace_napi.z', '-lhilog_ndk.z', '-o', str(libs / 'libprobe.so')]
if a.single_case:
    cmd.insert(1, '-DNATIVE_CHILD_SINGLE_CASE=' +
               {'150KiB-ascii': '1', 'empty': '2', 'core': '3'}[a.single_case])
if a.arch == 'armv7a':
    cmd[1:1] = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon']
subprocess.run(cmd, check=True)
shutil.copy2(native / 'llvm/lib' / triple / 'libc++_shared.so', libs / 'libc++_shared.so')
env = dict(os.environ, OHOS_SDK_HOME=str(a.sdk))
subprocess.run([a.arkdown, 'build', '--project', str(root), '--target', 'hap', '--mode', 'debug'], cwd=root, env=env, check=True)
out = root / 'entry/build/default/outputs/default'
subprocess.run([a.hap_sign, 'sign', str(out / 'entry-default-unsigned.hap'), '--bundle-name', bundle, '--compatible-version', '17', '--device-id', a.udid, '--output', str(out / 'entry-default-signed.hap'), '--force'], check=True)
print(out / 'entry-default-signed.hap')
