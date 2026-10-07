#!/usr/bin/env python3
"""Strictly verify actual two-role CertificateManager lifecycle observations."""
import argparse
import json
from pathlib import Path
import re
import zipfile

from build_certificate_probe import DECLARATION, TEMPLATE, page
from run_normal_hap_probe import BUNDLE, require_normal_identity
from run_root_probe import digest
from sign_certificate_probe import PERMISSIONS, configure_profile

SCOPE = 'actual_certificate_empty_populated_cleanup_and_permission_boundaries_only'


def identity(text, role):
    if role == 'normal':
        return require_normal_identity(text)
    if role != 'system':
        raise ValueError('explicit certificate role required')
    prefix = BUNDLE + ':\n'
    if text.startswith(prefix):
        text = text[len(prefix):]
    value = json.loads(text)['applicationInfo']
    if (value.get('appPrivilegeLevel') != 'system_core' or value.get('isSystemApp') is not True or
            type(value.get('uid')) is not int or value['uid'] // 200000 != 100):
        raise ValueError('actual certificate system test identity must match its bounded profile in account 100')
    return value['uid']


def verify_inputs(value, run_id, arch, role):
    generated, declaration, fixture = (Path(value[name]) for name in
        ('generated_source', 'sdk_declaration', 'test_pkcs12'))
    if (value.get('run_id') != run_id or value.get('arch') != arch or value.get('role') != role or
            value.get('scope') != SCOPE or value.get('template_sha256') != digest(TEMPLATE) or
            value.get('request_permissions') != (list(PERMISSIONS) if role == 'system' else []) or
            declaration.name != DECLARATION or
            any(path.is_symlink() or not path.is_file() or digest(path) != value.get(key)
                for path, key in ((generated, 'generated_source_sha256'),
                    (declaration, 'sdk_declaration_sha256'), (fixture, 'test_pkcs12_sha256'))) or
            generated.read_text() != page(run_id, role, fixture.read_bytes())):
        raise ValueError('certificate caller must match the complete current typed page, PKCS12 and real SDK')


def names(role):
    if role == 'normal':
        return ['denied.promise', 'denied.callback', 'denied.own', 'denied.install', 'summary']
    result = ['empty.promise', 'empty.callback', 'empty.own']
    for generation in range(2):
        result += ['install.' + str(generation)] + ['populated.' + str(generation) + '.' + mode
            for mode in ('promise', 'callback', 'own')] + ['uninstall.' + str(generation)] + [
            'after.' + str(generation) + '.' + mode for mode in ('promise', 'callback', 'own')]
    return result + ['boundary.format', 'boundary.password', 'boundary.alias', 'boundary.uri', 'repeat.empty', 'summary']


def verify(text, run_id, role, identity_text):
    if re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh certificate nonce required')
    identity(identity_text, role)
    rows = [json.loads(line) for line in text.splitlines()]
    expected = names(role)
    if (len(rows) != len(expected) or any(not isinstance(row, dict) for row in rows) or
            [row.get('name') for row in rows] != expected):
        raise ValueError('certificate observations missing, duplicated, reordered or extra')
    uris = {}
    for row in rows:
        name = row['name']; code = row.get('code')
        if (set(row) != {'name', 'runId', 'role', 'code', 'uri', 'credentials', 'values', 'error'} or
                row['runId'] != run_id or row['role'] != role or row['error'] != '' or
                type(code) is not int or not isinstance(row['uri'], str) or
                not isinstance(row['credentials'], list) or not isinstance(row['values'], list) or
                any(type(value) is not int for value in row['values'])):
            raise ValueError('failed/stale/malformed certificate observation: ' + name)
        expected_codes = ({201, 202} if name in ('denied.promise', 'denied.callback') else {201}) if name.startswith('denied.') else {
            'boundary.format': {17500003}, 'boundary.password': {17500003},
            'boundary.alias': {401}, 'boundary.uri': {401}}.get(name, {0})
        if code not in expected_codes:
            raise ValueError('certificate service/permission boundary differs: ' + name)
        if name.startswith('install.'):
            if not row['uri'] or len(row['uri'].encode()) > 256:
                raise ValueError('real import URI missing or oversized')
            uris[int(name[-1])] = row['uri']
        elif name.startswith('uninstall.'):
            if row['uri'] != uris[int(name[-1])]:
                raise ValueError('cleanup must use exactly this generation own import URI')
        elif row['uri'] != '':
            raise ValueError('unexpected certificate URI field: ' + name)
        if name.startswith('populated.'):
            generation = int(name.split('.')[1])
            credentials = row['credentials']
            if len(credentials) != 1:
                raise ValueError('expected one actual fresh imported credential')
            value = credentials[0]
            if (not isinstance(value, dict) or set(value) != {'type', 'alias', 'keyUri'} or
                    not isinstance(value['type'], str) or not 0 < len(value['type'].encode()) <= 8 or
                    value['alias'] != 'qemu_' + run_id[:16] + '_' + str(generation) or
                    value['keyUri'] != uris[generation]):
                raise ValueError('populated credential fields do not match actual own import')
        elif row['credentials'] != []:
            raise ValueError('expected a real empty array: ' + name)
        expected_values = [len(rows) - 1, 0] if name == 'summary' else [64, 0] if name == 'repeat.empty' else []
        if row['values'] != expected_values:
            raise ValueError('certificate repeat/summary/count boundary differs: ' + name)
    return rows


def verify_evidence(document, archive_sha, boot_id):
    if (document.get('status') != 'pass' or document.get('archive_sha256') != archive_sha or
            document.get('boot_id') != boot_id or document.get('failures') != [] or
            document.get('scope') != 'two_real_certificate_HAP_roles_NOT_full_gate' or
            document.get('arch') not in ('arm64', 'armv7a', 'x86_64') or
            re.fullmatch('[0-9a-fA-F]{64}', document.get('udid', '')) is None or
            set(document.get('roles', {})) != {'normal', 'system'}):
        raise ValueError('both actual certificate roles on the same new archive/boot are required')
    challenges = set()
    for role, row in document['roles'].items():
        paths = {}
        for field in ('raw_results', 'result', 'inputs', 'application_identity', 'signed_hap', 'signing_receipt'):
            path = Path(row[field])
            if path.is_symlink() or not path.is_file() or digest(path) != row.get(field + '_sha256'):
                raise ValueError('actual certificate evidence missing/modified: ' + role + ':' + field)
            paths[field] = path
        run_id = row['run_id']; challenges.add(run_id)
        if row.get('status') != 'pass' or row.get('actual_uid') != identity(paths['application_identity'].read_text(), role):
            raise ValueError('actual installed certificate identity differs')
        inputs = json.loads(paths['inputs'].read_text())
        verify_inputs(inputs, run_id, document['arch'], role)
        actual = verify(paths['raw_results'].read_text(), run_id, role, paths['application_identity'].read_text())
        result = json.loads(paths['result'].read_text())
        if (result.get('status') != 'pass' or result.get('scope') != SCOPE or result.get('role') != role or
                result.get('arch') != document['arch'] or result.get('run_id') != run_id or
                result.get('archive_sha256') != archive_sha or result.get('results') != actual or
                result.get('results_sha256') != digest(paths['raw_results']) or
                result.get('inputs_sha256') != digest(paths['inputs']) or
                result.get('application_identity_sha256') != digest(paths['application_identity'])):
            raise ValueError('certificate verification differs from complete actual observations')
        receipt = json.loads(paths['signing_receipt'].read_text())
        profile = receipt.get('verified_profile', {})
        with zipfile.ZipFile(paths['signed_hap']) as hap:
            compiled_module = json.loads(hap.read('module.json'))
        if (receipt.get('status') != 'pass' or receipt.get('role') != role or
                receipt.get('scope') != 'actual_signature_profile_and_codesign_NOT_guest' or
                receipt.get('signed_sha256') != digest(paths['signed_hap']) or
                configure_profile(json.loads(json.dumps(profile)), role, document['udid'], compiled_module) != profile):
            raise ValueError('actual signed HAP permissions and exact verified role profile differ')
    if len(challenges) != 2:
        raise ValueError('each fresh certificate role must have its own host nonce')
    return document['roles']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'application-identity', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--role', choices=('normal', 'system'), required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'run_id': args.run_id, 'arch': args.arch,
        'role': args.role, 'failures': [], 'first_artifact_behavior_gate_passed': False}
    try:
        for path, key in ((args.archive, 'archive_sha256'), (args.results, 'results_sha256'),
                         (args.inputs, 'inputs_sha256'), (args.application_identity, 'application_identity_sha256')):
            if path.is_symlink() or not path.is_file():
                raise ValueError('regular actual certificate evidence required')
            report[key] = digest(path)
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch, args.role)
        report['results'] = verify(args.results.read_text(), args.run_id, args.role, args.application_identity.read_text())
        report['status'] = 'pass'
    except (ValueError, OSError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'role', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
