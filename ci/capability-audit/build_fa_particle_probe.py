#!/usr/bin/env python3
"""Compile a real FA model caller; compilation alone is not guest evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--sdk', type=Path, required=True)
parser.add_argument('--hvigor-home', type=Path, required=True)
parser.add_argument('--node-home', type=Path, required=True)
args = parser.parse_args()
root, sdk = args.output.resolve(), args.sdk.resolve()
hvigor = args.hvigor_home.resolve()
metadata = json.loads((sdk / 'ets/oh-uni-package.json').read_text())
if str(metadata.get('apiVersion')) != '26' or metadata.get('releaseType') != 'Release':
    raise ValueError('actual API26 Release SDK required')
if not (hvigor / 'bin/hvigorw').is_file() or not (args.node_home / 'bin/node').is_file():
    raise ValueError('official legacy model builder and Node required')
root.mkdir(exist_ok=False, parents=True)
nonce = secrets.token_hex(16)
bundle = 'org.harmonycontrib.qemu.fa.particle'

def write(name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')

write('build-profile.json5', {'app': {'products': [{'name': 'default',
    'compileSdkVersion': '26.0.0', 'targetSdkVersion': '26.0.0', 'compatibleSdkVersion': 8,
    'runtimeOS': 'OpenHarmony'}], 'buildModeSet': [{'name': 'debug'}, {'name': 'release'}]},
    'modules': [{'name': 'entry', 'srcPath': './entry',
                 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
for name in ('oh-package.json5', 'entry/oh-package.json5'):
    write(name, {'modelVersion': '6.0.0', 'name': 'fa-particle-probe', 'version': '1.0.0', 'dependencies': {}})
write('entry/build-profile.json5', {'apiType': 'faMode', 'buildOption': {}, 'targets': [{'name': 'default'}]})
write('entry/src/main/config.json', {
    'app': {'bundleName': bundle, 'vendor': 'harmony-contrib', 'version': {'code': 1, 'name': '1.0'},
            'apiVersion': {'compatible': 8, 'target': 26}}, 'deviceConfig': {},
    'module': {'package': bundle, 'name': '.MyApplication', 'mainAbility': '.MainAbility',
        'deviceType': ['default', 'tablet'],
        'distro': {'deliveryWithInstall': True, 'moduleName': 'entry', 'moduleType': 'entry', 'installationFree': False},
        'abilities': [{'name': '.MainAbility', 'visible': True, 'srcPath': 'MainAbility', 'srcLanguage': 'js',
            'icon': '$media:icon', 'label': '$string:app_name', 'type': 'page', 'launchType': 'singleton',
            'skills': [{'entities': ['entity.system.home'], 'actions': ['action.system.home']}]},
            {'name': '.ParticleService', 'visible': True, 'srcPath': 'ParticleService',
             'srcLanguage': 'js', 'icon': '$media:icon', 'label': '$string:app_name', 'type': 'service'}],
        'js': [{'name': '.MainAbility', 'pages': ['pages/index/index']}]}})
write('entry/src/main/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'FA particle probe'}]})
write('entry/src/main/resources/base/media/icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" fill="#227799"/></svg>')
write('entry/src/main/js/MainAbility/app.js', 'export default { onCreate() {}, onDestroy() {} };\n')
write('entry/src/main/js/MainAbility/pages/index/index.hml', '<div class="page"><text>FA particle registration probe</text></div>\n')
write('entry/src/main/js/MainAbility/pages/index/index.css', '.page { flex-direction: column; align-items: center; justify-content: center; }\n')
source = '''import particleAbility from '@ohos.ability.particleAbility';
const nonce = '__NONCE__';
function report(name, status, value) {
  console.info('QEMU_FA_PARTICLE:' + JSON.stringify({nonce: nonce, name: name, status: status, value: value}));
}
export default {
  async onStart() {
    try {
      const errorCode = particleAbility.ErrorCode;
      const keys = errorCode === undefined ? [] : Object.keys(errorCode);
      report('particle.invalid_parameter', keys.length === 1 && keys[0] === 'INVALID_PARAMETER' &&
        errorCode.INVALID_PARAMETER === -1 ? 'pass' : 'fail', errorCode === undefined ? null : errorCode);
      const context = particleAbility.getContext();
      const info = await particleAbility.getAbilityInfo();
      report('actual.fa.context', context !== null && typeof context === 'object' &&
        info.bundleName === '__BUNDLE__' && info.type === 2 ? 'pass' : 'fail',
        {bundleName: info.bundleName, name: info.name, type: info.type,
         contextPresent: context !== null && typeof context === 'object'});
      const abilityInfo = await new Promise((resolve, reject) => {
        particleAbility.getAbilityInfo((error, value) => error ? reject(error) : resolve(value));
      });
      report('particle.context', abilityInfo.bundleName === info.bundleName && abilityInfo.name === info.name &&
        abilityInfo.type === 2 ? 'pass' : 'fail', abilityInfo);
      const name = await particleAbility.getAbilityName();
      report('particle.ability_name', name.endsWith('ParticleService') ? 'pass' : 'fail', name);
      report('complete', 'pass', 'FA');
    } catch (error) {
      report('exception', 'fail', {code: error.code, message: error.message});
    }
  }
};
'''.replace('__NONCE__', nonce).replace('__BUNDLE__', bundle)
page_source = '''import featureAbility from '@ohos.ability.featureAbility';
export default {
  data: { started: false },
  async onShow() {
    if (this.started) { return; }
    this.started = true;
    try {
      await featureAbility.startAbility({ want: { bundleName: '__BUNDLE__',
        abilityName: '__BUNDLE__.ParticleService' } });
      console.info('QEMU_FA_PAGE:' + JSON.stringify({ nonce: '__NONCE__', status: 'pass' }));
    } catch (error) {
      console.info('QEMU_FA_PAGE:' + JSON.stringify({ nonce: '__NONCE__', status: 'fail',
        code: error.code, message: error.message }));
    }
  }
};
'''.replace('__NONCE__', nonce).replace('__BUNDLE__', bundle)
write('entry/src/main/js/MainAbility/pages/index/index.js', page_source)
write('entry/src/main/js/ParticleService/service.js', source)
write('caller-inputs.json', {'status': 'not_run', 'scope': 'FA_compile_candidate_NOT_guest_evidence',
    'bundle': bundle, 'nonce': nonce, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
    'page_source_sha256': hashlib.sha256(page_source.encode()).hexdigest(),
    'model': 'FA', 'ability_kind': 'service', 'request_permissions': []})
plugin = str(hvigor / 'hvigor-ohos-plugin')
write('hvigorfile.ts', "import { legacyAppTasks } from '" + plugin + "';\nexport default { system: legacyAppTasks, plugins: [] };\n")
write('entry/hvigorfile.ts', "import { legacyHapTasks } from '" + plugin + "';\nexport default { system: legacyHapTasks, plugins: [] };\n")
write('hvigor/hvigor-config.json5', {'modelVersion': '6.0.0', 'dependencies': {},
    'execution': {'daemon': False, 'parallel': False}, 'logging': {'level': 'info'}})
write('local.properties', 'sdk.dir=' + str(sdk.parent) + '\n')
subprocess.run([str(hvigor / 'bin/hvigorw'), 'assembleHap', '--no-daemon', '-p', 'product=default', '-p', 'buildMode=debug'],
               cwd=root, env=dict(os.environ, OHOS_SDK_HOME=str(sdk.parent),
                  NODE_HOME=str(args.node_home.resolve())), check=True)

outputs = list((root / 'entry/build/default/outputs/default').glob('*-unsigned.hap'))
if len(outputs) != 1:
    raise ValueError('exactly one actual unsigned FA HAP required')
with zipfile.ZipFile(outputs[0]) as archive:
    config = json.loads(archive.read('config.json'))
    if 'module.json' in archive.namelist() or config['app']['bundleName'] != bundle:
        raise ValueError('not the expected actual FA package')
    if config['module'].get('reqPermissions', []):
        raise ValueError('ordinary FA probe must not request extra permissions')
    for member in ('assets/js/ParticleService/service.abc',
                   'assets/js/MainAbility/pages/index/index.abc'):
        if not archive.read(member):
            raise ValueError('actual compiled FA page and service are required')
inputs = json.loads((root / 'caller-inputs.json').read_text())
inputs.update(unsigned_hap=str(outputs[0]),
              unsigned_hap_sha256=hashlib.sha256(outputs[0].read_bytes()).hexdigest(),
              sdk_metadata=metadata,
              sdk_metadata_sha256=hashlib.sha256((sdk / 'ets/oh-uni-package.json').read_bytes()).hexdigest(),
              builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              build_status='pass')
write('caller-inputs.json', inputs)
print(outputs[0])

