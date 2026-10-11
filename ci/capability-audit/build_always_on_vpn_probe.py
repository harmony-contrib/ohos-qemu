#!/usr/bin/env python3
"""Build three explicit VPN policy caller roles using the actual API26 SDK."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('always_on_vpn_probe.ets')
BUNDLE = 'org.harmonycontrib.capabilityaudit'
ROLES = ('normal', 'system-denied', 'system')
PERMISSION = 'ohos.permission.MANAGE_VPN'


def page(run_id, role):
    if re.fullmatch('[0-9a-f]{32}', run_id) is None or role not in ROLES:
        raise ValueError('fresh nonce and explicit VPN caller role required')
    return TEMPLATE.read_text().replace('__VPN_RUN__', run_id).replace('__VPN_ROLE__', role)


def module(role, compiled=False):
    if role not in ROLES:
        raise ValueError('explicit VPN caller role required')
    value = {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility', 'deviceTypes': ['phone', '2in1'],
        'deliveryWithInstall': True, 'installationFree': False, 'pages': '$profile:main_pages',
        'requestPermissions': [{'name': PERMISSION}] if role == 'system' else [],
        'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets', 'exported': True,
            'label': '$string:app_name', 'icon': '$media:icon', 'startWindowIcon': '$media:icon',
            'startWindowBackground': '$color:background'}]}
    return {'app': {'bundleName': BUNDLE}, 'module': value} if compiled else {'module': value}


def build(args):
    root, sdk = args.output.resolve(), args.sdk.resolve()
    generated_page = page(args.run_id, args.role)
    for name in ('ets', 'native'):
        metadata = json.loads((sdk / name / 'oh-uni-package.json').read_text())
        if any(metadata.get(key) != value for key, value in (
                ('apiVersion', '26'), ('releaseType', 'Release'), ('platformVersion', '26.0.0'))):
            raise ValueError('actual API26 Release SDK required')
    root.mkdir(parents=True, exist_ok=False)

    def write(name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')

    write('AppScope/app.json5', {'app': {'bundleName': BUNDLE, 'vendor': 'harmony-contrib',
        'versionCode': 1, 'versionName': '1.0.0', 'icon': '$media:icon', 'label': '$string:app_name'}})
    write('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'VPN policy regression'}]})
    write('AppScope/resources/base/media/icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" fill="#365c88"/></svg>')
    write('build-profile.json5', {'app': {'products': [{'name': 'default', 'targetSdkVersion': '7.0.0(26)',
        'compatibleSdkVersion': '7.0.0(26)', 'runtimeOS': 'HarmonyOS'}],
        'buildModeSet': [{'name': 'debug'}, {'name': 'release'}]},
        'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    for name in ('oh-package.json5', 'entry/oh-package.json5'):
        write(name, {'modelVersion': '6.0.0', 'name': 'vpn-policy-probe', 'version': '1.0.0', 'dependencies': {}})
    write('entry/build-profile.json5', {'apiType': 'stageMode', 'buildOption': {'externalNativeOptions': {
        'abiFilters': [{'arm64': 'arm64-v8a', 'armv7a': 'armeabi-v7a', 'x86_64': 'x86_64'}[args.arch]]}},
        'targets': [{'name': 'default'}]})
    write('entry/src/main/module.json5', module(args.role))
    write('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'background', 'value': '#ffffff'}]})
    write('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    write('entry/src/main/ets/entryability/EntryAbility.ets', """import UIAbility from '@ohos.app.ability.UIAbility';
import window from '@ohos.window';
export default class EntryAbility extends UIAbility {
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
""")
    generated = root / 'entry/src/main/ets/pages/Index.ets'
    write('entry/src/main/ets/pages/Index.ets', generated_page)
    declaration = sdk / 'ets/api/@ohos.net.vpnExtension.d.ts'
    write('vpn-policy-probe-inputs.json', {'schema_version': 1, 'run_id': args.run_id, 'role': args.role,
        'arch': args.arch, 'scope': 'real_policy_persistence_restart_and_permission_NOT_VPN_traffic',
        'request_permissions': [PERMISSION] if args.role == 'system' else [],
        'template_sha256': digest(TEMPLATE), 'generated_source': str(generated),
        'generated_source_sha256': digest(generated), 'sdk_declaration': str(declaration),
        'sdk_declaration_sha256': digest(declaration)})
    subprocess.run([args.arkdown, 'build', '--project', root, '--target', 'hap', '--mode', 'debug'],
                   cwd=root, env=dict(os.environ, OHOS_SDK_HOME=str(sdk)), check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    build(parser.parse_args())
