#!/usr/bin/env python3
"""Build a nonce-bound, exactly two-role real CertificateManager regression HAP.

Uses only the actual API26 SDK and a fresh self-signed test PKCS12. No native
libraries, permissions shims, user certificates or unsigned runtime acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from run_root_probe import digest
from sign_certificate_probe import BUNDLE, PERMISSIONS

TEMPLATE = Path(__file__).with_name('certificate_probe.ets')
DECLARATION = '@ohos.security.certManager.d.ts'


def page(run_id, role, data):
    if (re.fullmatch('[0-9a-f]{32}', run_id) is None or role not in ('normal', 'system') or
            not isinstance(data, bytes) or not 0 < len(data) <= 20480):
        raise ValueError('fresh nonce, explicit role and valid bounded test PKCS12 required')
    return (TEMPLATE.read_text().replace('__CERTIFICATE_RUN_ID__', run_id)
            .replace('__CERTIFICATE_ROLE__', role).replace('__CERTIFICATE_BYTES__', json.dumps(list(data))))


def module(role, compiled=False):
    permissions = [{'name': name} for name in PERMISSIONS] if role == 'system' else []
    if role not in ('normal', 'system'):
        raise ValueError('explicit certificate role required')
    value = {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility', 'deviceTypes': ['phone', '2in1'],
        'deliveryWithInstall': True, 'installationFree': False, 'pages': '$profile:main_pages',
        'requestPermissions': permissions, 'abilities': [{'name': 'EntryAbility',
            'srcEntry': './ets/entryability/EntryAbility.ets', 'exported': True,
            'label': '$string:app_name', 'icon': '$media:icon', 'startWindowIcon': '$media:icon',
            'startWindowBackground': '$color:background'}]}
    return {'app': {'bundleName': BUNDLE}, 'module': value} if compiled else {'module': value}


def build(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    run_id = args.run_id or uuid.uuid4().hex
    sdk = args.sdk.resolve()
    for name in ('ets', 'native'):
        metadata = json.loads((sdk / name / 'oh-uni-package.json').read_text())
        if (metadata.get('apiVersion') != '26' or metadata.get('releaseType') != 'Release' or
                metadata.get('platformVersion') != '26.0.0'):
            raise ValueError('real API26 Release SDK required')
    fixture = root / 'test-credential'; fixture.mkdir()
    key, pem, p12 = (fixture / name for name in ('key.pem', 'certificate.pem', 'credential.p12'))
    subprocess.run([args.openssl, 'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-x509', '-days', '2',
        '-subj', '/CN=QEMU-test-' + run_id, '-keyout', key, '-out', pem], check=True)
    subprocess.run([args.openssl, 'pkcs12', '-export', '-inkey', key, '-in', pem,
        '-name', 'qemu_' + run_id[:16], '-passout', 'pass:qemu_test_only', '-out', p12], check=True)
    data = p12.read_bytes()

    def write(name, value):
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')

    write('AppScope/app.json5', {'app': {'bundleName': BUNDLE, 'vendor': 'harmony-contrib',
        'versionCode': 1, 'versionName': '1.0.0', 'icon': '$media:icon', 'label': '$string:app_name'}})
    write('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'Certificate regression'}]})
    write('AppScope/resources/base/media/icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" fill="#365c88"/></svg>')
    write('build-profile.json5', {'app': {'products': [{'name': 'default', 'targetSdkVersion': '7.0.0(26)',
        'compatibleSdkVersion': '7.0.0(26)', 'runtimeOS': 'HarmonyOS'}],
        'buildModeSet': [{'name': 'debug'}, {'name': 'release'}]},
        'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    for name in ('oh-package.json5', 'entry/oh-package.json5'):
        write(name, {'modelVersion': '6.0.0', 'name': 'certificate-probe', 'version': '1.0.0', 'dependencies': {}})
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
    write('entry/src/main/ets/pages/Index.ets', page(run_id, args.role, data))
    declaration = sdk / 'ets/api' / DECLARATION
    write('certificate-probe-inputs.json', {'schema_version': 1, 'run_id': run_id, 'role': args.role,
        'arch': args.arch, 'scope': 'actual_certificate_empty_populated_cleanup_and_permission_boundaries_only',
        'request_permissions': list(PERMISSIONS) if args.role == 'system' else [],
        'template_sha256': digest(TEMPLATE), 'generated_source': str(generated),
        'generated_source_sha256': digest(generated), 'sdk_declaration': str(declaration),
        'sdk_declaration_sha256': digest(declaration), 'test_pkcs12': str(p12), 'test_pkcs12_sha256': digest(p12)})
    subprocess.run([args.arkdown, 'build', '--project', root, '--target', 'hap', '--mode', 'debug'],
        cwd=root, env=dict(os.environ, OHOS_SDK_HOME=str(sdk)), check=True)
    print(root / 'entry/build/default/outputs/default/entry-default-unsigned.hap')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--role', choices=('normal', 'system'), required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id')
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    parser.add_argument('--openssl', default='openssl')
    build(parser.parse_args())


if __name__ == '__main__':
    main()
