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
    return build_application(args, page(args.run_id, args.role), TEMPLATE,
        'vpn-policy-probe-inputs.json', 'real_policy_persistence_restart_and_permission_NOT_VPN_traffic',
        '@ohos.net.vpnExtension.d.ts')


def build_application(args, generated_page, template, receipt_name, scope, declaration_name,
                      module_factory=None, extra_files=None, strict_mode=None, bundle_name=None,
                      additional_sdk_declarations=None, entry_ability_source=None):
    """Reuse the actual typed three-role app build, never override image policy."""
    root, sdk = prepare_application(args, generated_page, template, receipt_name, scope, declaration_name,
        module_factory, extra_files, strict_mode, bundle_name, additional_sdk_declarations, entry_ability_source)
    subprocess.run([args.arkdown, 'build', '--project', root, '--target', 'hap', '--mode', 'debug'],
                   cwd=root, env=dict(os.environ, OHOS_SDK_HOME=str(sdk)), check=True)


def prepare_application(args, generated_page, template, receipt_name, scope, declaration_name,
                        module_factory=None, extra_files=None, strict_mode=None, bundle_name=None,
                        additional_sdk_declarations=None, entry_ability_source=None):
    """Write exact caller inputs before selecting its real supported compiler."""
    root, sdk = args.output.resolve(), args.sdk.resolve()
    if args.role not in ROLES or re.fullmatch('[0-9a-f]{32}', args.run_id) is None:
        raise ValueError('fresh nonce and explicit bounded VPN role required')
    selected_bundle = BUNDLE if bundle_name is None else bundle_name
    if (not isinstance(selected_bundle, str) or len(selected_bundle) > 127 or
            re.fullmatch('[a-z][a-z0-9]*(?:\\.[a-z][a-z0-9]*)+', selected_bundle) is None):
        raise ValueError('explicit valid probe bundle identity required')
    for name in ('ets', 'native'):
        metadata = json.loads((sdk / name / 'oh-uni-package.json').read_text())
        if any(metadata.get(key) != value for key, value in (
                ('apiVersion', '26'), ('releaseType', 'Release'), ('platformVersion', '26.0.0'))):
            raise ValueError('actual API26 Release SDK required')
    sdk_declarations = {}
    for name in additional_sdk_declarations or ():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('additional SDK declaration must remain inside the SDK')
        path = sdk / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError('actual regular SDK declaration required: ' + name)
        sdk_declarations[name] = digest(path)
    root.mkdir(parents=True, exist_ok=False)
    application_module = (module_factory or module)(args.role)
    requests = application_module['module']['requestPermissions']
    if (not isinstance(requests, list) or any(not isinstance(row, dict) or
            set(row) != {'name'} or not isinstance(row['name'], str) for row in requests) or
            len({row['name'] for row in requests}) != len(requests)):
        raise ValueError('exact distinct application permission requests required')

    def write(name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')

    write('AppScope/app.json5', {'app': {'bundleName': selected_bundle, 'vendor': 'harmony-contrib',
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
        'abiFilters': [{'arm64': 'arm64-v8a', 'armv7a': 'armeabi-v7a', 'x86_64': 'x86_64'}[args.arch]]},
        **({'strictMode': strict_mode} if strict_mode else {})},
        'targets': [{'name': 'default'}]})
    write('entry/src/main/module.json5', application_module)
    write('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'background', 'value': '#ffffff'}]})
    write('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    write('entry/src/main/ets/entryability/EntryAbility.ets', entry_ability_source if entry_ability_source is not None else """import UIAbility from '@ohos.app.ability.UIAbility';
import window from '@ohos.window';
export default class EntryAbility extends UIAbility {
  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }
}
""")
    generated = root / 'entry/src/main/ets/pages/Index.ets'
    write('entry/src/main/ets/pages/Index.ets', generated_page)
    additional_inputs = {}
    if entry_ability_source is not None:
        name = 'entry/src/main/ets/entryability/EntryAbility.ets'
        additional_inputs[name] = digest(root / name)
    for name, value in (extra_files or {}).items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or (root / relative).exists():
            raise ValueError('additional build input must be a new relative project file')
        write(name, value)
        additional_inputs[name] = digest(root / relative)
    declaration = sdk / 'ets/api' / declaration_name
    write(receipt_name, {'schema_version': 1, 'run_id': args.run_id, 'role': args.role,
        'arch': args.arch, 'scope': scope,
        'request_permissions': [row['name'] for row in requests],
        'template_sha256': digest(template), 'generated_source': str(generated),
        'generated_source_sha256': digest(generated), 'sdk_declaration': str(declaration),
        'sdk_declaration_sha256': digest(declaration), 'additional_input_sha256': additional_inputs,
        'strict_mode': strict_mode or {},
        **({'bundle_name': selected_bundle} if bundle_name is not None else {}),
        **({'additional_sdk_declarations': sdk_declarations} if sdk_declarations else {})})
    return root, sdk


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    build(parser.parse_args())
