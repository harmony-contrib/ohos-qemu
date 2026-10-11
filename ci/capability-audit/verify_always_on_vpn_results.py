"""Strict VPN policy observations; not a standalone packaged acceptance gate."""
import json
from pathlib import Path
import re
import zipfile

from build_always_on_vpn_probe import PERMISSION, ROLES, TEMPLATE, page
from run_root_probe import digest
from verify_certificate_results import identity as certificate_identity
from sign_always_on_vpn_probe import configure_profile

SCOPE = 'real_policy_persistence_restart_and_permission_NOT_VPN_traffic'


def identity(text, role):
    if role not in ROLES:
        raise ValueError('explicit VPN role required')
    return certificate_identity(text, 'normal' if role == 'normal' else 'system')


def verify_inputs(value, run_id, arch, role):
    generated, declaration = (Path(value[key]) for key in ('generated_source', 'sdk_declaration'))
    if (type(value.get('schema_version')) is not int or value['schema_version'] != 1 or
            value.get('run_id') != run_id or value.get('arch') != arch or value.get('role') != role or
            arch not in ('arm64', 'armv7a', 'x86_64') or value.get('scope') != SCOPE or
            value.get('request_permissions') != ([PERMISSION] if role == 'system' else []) or
            value.get('template_sha256') != digest(TEMPLATE) or
            declaration.name != '@ohos.net.vpnExtension.d.ts' or
            any(path.is_symlink() or not path.is_file() or digest(path) != value.get(key)
                for path, key in ((generated, 'generated_source_sha256'), (declaration, 'sdk_declaration_sha256'))) or
            generated.read_text() != page(run_id, role)):
        raise ValueError('VPN observations do not match exact current source/SDK/role')


def expected(role, phase):
    if role not in ROLES or phase not in ('seed', 'restart', 'denial') or (
            (role == 'system') != (phase != 'denial')):
        raise ValueError('incompatible VPN role and phase')
    rows = [('identity', None)] + [('invalid.' + method, [401, 1]) for _ in range(2) for method in ('get', 'set')]
    if phase == 'denial':
        rows += [('denied.' + method, [202 if role == 'normal' else 201, 1]) for method in ('get', 'set')]
    elif phase == 'seed':
        rows += [('initial', [0])]
        for round_ in range(3):
            rows += [(name + '.' + str(round_), value) for name, value in (
                ('enabled', [1]), ('other', [0]), ('disabled', [0]))]
        rows += [('seed.persisted', [1])]
    else:
        rows += [('restart.persisted', [1]), ('restart.other', [0]), ('restart.disabled', [0]), ('cleanup', [0])]
    return rows + [('summary', [1, 1 if phase == 'seed' else 0])]


def verify(text, run_id, role, phase, identity_text):
    if re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh VPN nonce required')
    uid = identity(identity_text, role)
    rows = [json.loads(line) for line in text.splitlines()]
    contract = expected(role, phase)
    if len(rows) != len(contract):
        raise ValueError('missing/extra VPN observations')
    for row, (name, values) in zip(rows, contract):
        if (not isinstance(row, dict) or set(row) != {'runId', 'role', 'name', 'values', 'error'} or
                row['runId'] != run_id or row['role'] != role or row['name'] != name or row['error'] != '' or
                not isinstance(row['values'], list) or any(type(v) is not int for v in row['values'])):
            raise ValueError('failed/malformed/reordered VPN observation: ' + name)
        if values is None:
            if len(row['values']) != 3 or row['values'][:2] != [uid, uid] or row['values'][2] <= 1:
                raise ValueError('VPN HAP identity does not match actual installed caller')
        elif row['values'] != values:
            raise ValueError('VPN behavior differs: ' + name)
    return rows


def verify_restart(seed, restarted):
    if (seed[0]['runId'] != restarted[0]['runId'] or seed[0]['role'] != 'system' or
            restarted[0]['role'] != 'system' or seed[0]['values'][:2] != restarted[0]['values'][:2] or
            seed[0]['values'][2] == restarted[0]['values'][2]):
        raise ValueError('policy must survive an actual different caller process with the same identity')


def verify_evidence(document, archive_sha, boot_id, arch, device):
    if (document.get('status') != 'pass' or document.get('scope') !=
            'three_real_VPN_policy_roles_and_caller_restart_NOT_tunnel_or_full_gate' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('device') != device or
            document.get('failures') != [] or set(document.get('roles', {})) != set(ROLES) or
            re.fullmatch('[0-9a-fA-F]{64}', document.get('udid', '')) is None):
        raise ValueError('all three VPN caller roles on this exact packaged guest are required')
    nonces = set()
    for role, record in document['roles'].items():
        paths = {}
        for field in ('inputs', 'application_identity', 'signed_hap', 'signing_receipt'):
            path = Path(record[field])
            if path.is_symlink() or not path.is_file() or digest(path) != record.get(field + '_sha256'):
                raise ValueError('VPN evidence changed/missing: ' + field)
            paths[field] = path
        nonce = record['run_id']
        nonces.add(nonce)
        if record.get('status') != 'pass' or record.get('actual_uid') != identity(paths['application_identity'].read_text(), role):
            raise ValueError('VPN installed caller identity differs')
        verify_inputs(json.loads(paths['inputs'].read_text()), nonce, arch, role)
        receipt = json.loads(paths['signing_receipt'].read_text())
        profile = receipt.get('verified_profile', {})
        with zipfile.ZipFile(paths['signed_hap']) as hap:
            compiled = json.loads(hap.read('module.json'))
        if (receipt.get('status') != 'pass' or receipt.get('role') != role or
                receipt.get('scope') != 'actual_signature_profile_and_codesign_NOT_guest' or
                receipt.get('signed_sha256') != digest(paths['signed_hap']) or
                configure_profile(json.loads(json.dumps(profile)), role, document['udid'], compiled) != profile):
            raise ValueError('actual signed VPN permission contract differs')
        phases = record.get('phases', {})
        if set(phases) != ({'seed', 'restart'} if role == 'system' else {'denial'}):
            raise ValueError('incomplete VPN phases')
        for phase, row in phases.items():
            raw = Path(row['raw_results'])
            if raw.is_symlink() or not raw.is_file() or digest(raw) != row.get('raw_results_sha256'):
                raise ValueError('VPN raw observations changed/missing')
            actual = verify(raw.read_text(), nonce, role, phase, paths['application_identity'].read_text())
            if actual != row.get('results'):
                raise ValueError('VPN summary differs from raw observations')
        if role == 'system':
            verify_restart(phases['seed']['results'], phases['restart']['results'])
    if len(nonces) != len(ROLES):
        raise ValueError('each fresh VPN caller role needs an independent host nonce')
    return ['arkts_export:@ohos.net.vpnExtension:' + name for name in
            ('isAlwaysOnVpnEnabled', 'setAlwaysOnVpnEnabled')]
