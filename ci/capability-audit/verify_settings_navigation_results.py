"""Require public call results plus actual Settings UI/provider/return evidence."""
import argparse
import json
from pathlib import Path
import re

from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest
from settings_navigation_evidence import SETTINGS

SCOPE = 'ordinary_input_Settings_navigation_only_NOT_all_Settings'


def settings_identity(text):
    info = json.loads(text.removeprefix(SETTINGS + ':\n'))['applicationInfo']
    uid = info.get('uid')
    if (info.get('name') != SETTINGS or info.get('isSystemApp') is not True or
            info.get('appPrivilegeLevel') != 'system_basic' or type(uid) is not int or uid // 200000 != 100):
        raise ValueError('actual preinstalled system_basic Settings identity required')
    return uid


def verify_rows(text, run_id, *, startup=False):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh Settings nonce required')
    expected = ['installed-input-methods', 'empty-identity.0', 'empty-identity.1', 'ready']
    if not startup:
        expected += ['input.request-returned', 'detail.request-returned'] * 2
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(expected):
        raise ValueError('complete Settings observation sequence required')
    for index, (row, name) in enumerate(zip(rows, expected)):
        if (not isinstance(row, dict) or set(row) != {'runId', 'sequence', 'name', 'pass', 'value'} or
                row['runId'] != run_id or type(row['sequence']) is not int or row['sequence'] != index + 1 or
                row['name'] != name or row['pass'] is not True or not isinstance(row['value'], str)):
            raise ValueError('failed/stale/reordered Settings observation')
    methods = json.loads(rows[0]['value'])
    if (not isinstance(methods, list) or not methods or any(not isinstance(method, dict) or
            any(not isinstance(method.get(key), str) or not method[key] for key in ('name', 'id')) for method in methods)):
        raise ValueError('real installed input method identity required')
    for row in rows[1:3]:
        error = json.loads(row['value'])
        if not isinstance(error, dict) or type(error.get('code')) is not int or error['code'] != 16900010:
            raise ValueError('public invalid parameter rejection required')
    if not startup:
        for row in (rows[5], rows[7]):
            if json.loads(row['value']) != methods[0]:
                raise ValueError('detail call did not name the actual installed input method')
    return {'observations': len(rows), 'methods': methods, 'closed': [],
            'not_claimed': ['all Settings', 'network/display pages', 'input method enable/switch operations']}


def verify_inputs(path, run_id, arch, sdk):
    inputs = json.loads(path.read_text())
    template = Path(__file__).with_name('settings_navigation_probe.ets')
    page = path.parent / 'entry/src/main/ets/pages/Index.ets'
    module = path.parent / 'entry/src/main/module.json5'
    if (inputs.get('schema_version') != 1 or inputs.get('scope') != 'ordinary_Settings_public_calls_NOT_UI_acceptance' or
            inputs.get('run_id') != run_id or inputs.get('arch') != arch or inputs.get('request_permissions') != [] or
            inputs.get('template_sha256') != digest(template) or inputs.get('generated_source_sha256') != digest(page) or
            inputs.get('module_sha256') != digest(module) or
            page.read_text() != template.read_text().replace('__SETTINGS_RUN__', run_id) or
            json.loads(module.read_text())['module'].get('requestPermissions', []) != []):
        raise ValueError('actual compiled zero-permission Settings caller does not match its contract')
    for name, key in (('settings', 'settings_declarations_sha256'), ('inputMethod', 'input_method_declarations_sha256'),
                      ('screen', 'screen_declarations_sha256')):
        if inputs.get(key) != digest(sdk / 'ets/api' / ('@ohos.' + name + '.d.ts')):
            raise ValueError('Settings caller SDK declarations changed')


def verify_evidence(document, archive_sha, boot_id, arch):
    from settings_navigation_ui import verify_actions
    if (document.get('status') != 'pass' or document.get('persona') != 'settings-navigation' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != [] or
            document.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('Settings evidence must belong to this actual package/boot/architecture')
    result_path = Path(document.get('result', ''))
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('explicit Settings result required')
    root = result_path.parent
    files = {'result': result_path, 'raw_results': root / 'results.log',
             'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
             'compiled_contract_inputs': root / 'project/settings-navigation-probe-inputs.json',
             'settings_navigation_actions': root / 'settings-navigation-actions.json'}
    for key, path in files.items():
        if not path.is_file() or path.is_symlink() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('actual Settings evidence changed: ' + key)
    value = json.loads(result_path.read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('failures') != [] or
            value.get('archive_sha256') != archive_sha or value.get('run_id') != document.get('run_id') or
            value.get('arch') != arch or value.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('Settings verifier summary does not belong to this run')
    for name in ('verify_settings_navigation_results.py', 'settings_navigation_ui.py', 'settings_navigation_evidence.py'):
        if value.get('verifier_hashes', {}).get(name) != digest(Path(__file__).with_name(name)):
            raise ValueError('Settings verification code changed')
    verify_inputs(files['compiled_contract_inputs'], document['run_id'], arch, Path(value['sdk']))
    uid = require_normal_identity(files['ordinary_identity'].read_text())
    actual = verify_rows(files['raw_results'].read_text(), document['run_id'])
    actual['ui'] = verify_actions(json.loads(files['settings_navigation_actions'].read_text()), actual['methods'], uid)
    if actual != value.get('result') or uid != document.get('ordinary_uid'):
        raise ValueError('Settings success differs from actual raw app/UI proof')
    return actual


def main():
    from settings_navigation_ui import verify_actions
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'actions', 'sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'archive_sha256': digest(args.archive), 'arch': args.arch,
              'run_id': args.run_id, 'sdk': str(args.sdk.resolve()), 'failures': [],
              'first_artifact_behavior_gate_passed': False, 'verifier_hashes': {
                  name: digest(Path(__file__).with_name(name)) for name in (
                      'verify_settings_navigation_results.py', 'settings_navigation_ui.py', 'settings_navigation_evidence.py')}}
    try:
        verify_inputs(args.inputs, args.run_id, args.arch, args.sdk)
        uid = require_normal_identity(args.application_identity.read_text())
        result = verify_rows(args.results.read_text(), args.run_id)
        result['ui'] = verify_actions(json.loads(args.actions.read_text()), result['methods'], uid)
        report.update(status='pass', result=result)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
