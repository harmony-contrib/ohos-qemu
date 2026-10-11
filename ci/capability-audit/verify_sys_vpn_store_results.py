"""Strict real VPN store observations; never connected/tunnel acceptance."""
import json
from pathlib import Path
import re
import uuid
import zipfile

from build_sys_vpn_store_probe import PERMISSION, ROLES, TEMPLATE, SCOPE, page
from run_root_probe import digest
from verify_always_on_vpn_results import identity, verify_restart
from sign_always_on_vpn_probe import configure_profile

EVIDENCE_SCOPE = 'three_real_VPN_store_roles_and_caller_restart_NOT_tunnel_or_full_gate'
METHODS = ('addSysVpnConfig', 'getSysVpnConfig', 'getSysVpnConfigList', 'deleteSysVpnConfig')


def expected_config(run_id, index, revision, account=100):
    if (re.fullmatch('[a-f0-9]{32}', run_id or '') is None or type(index) is not int or
            index not in range(3) or type(revision) is not int or revision not in (0, 1)):
        raise ValueError('exact fresh VPN config variant/revision required')
    def address(ip, family):
        return dict(address=ip, family=family, port=0)
    def link(ip, family, prefix):
        return dict(address=address(ip, family), prefixLength=prefix)
    value = dict(vpnId=str(uuid.UUID(run_id[:31] + str(index))),
        vpnName='audit-' + run_id + '-' + str(revision), vpnType=(9, 2, 4)[index],
        userName='audit-' + run_id, password='synthetic-' + run_id, saveLogin=True, userId=account,
        forwardingRoutes='198.18.0.0/24',
        addresses=[link('198.18.0.2', 1, 24), link('2001:db8::2', 2, 64)],
        localAddresses=[link('198.18.0.6', 1, 28), link('2001:db8::6', 2, 96)],
        remoteAddresses=['198.19.0.1', '2001:db8:1::1'],
        dnsAddresses=['198.18.0.53', '2001:db8::53'],
        searchDomains=['a.' + run_id + '.invalid', 'b.' + run_id + '.invalid'],
        mtu=1400 + revision, isIPv4Accepted=True, isIPv6Accepted=True, isLegacy=False, isBlocking=True,
        trustedApplications=['org.harmonycontrib.capabilityaudit', 'org.harmonycontrib.other'] if revision == 0 else [],
        blockedApplications=['org.harmonycontrib.blocked', 'org.harmonycontrib.blocked2'] if revision == 1 else [],
        routes=[dict(interface='vpn-tun', destination=link('198.18.1.0', 1, 24),
            gateway=address('198.18.0.1', 1), hasGateway=True, isDefaultRoute=False, isExcludedRoute=False),
            dict(interface='vpn-tun', destination=link('2001:db8:2::', 2, 64),
            gateway=address('2001:db8::1', 2), hasGateway=False, isDefaultRoute=False, isExcludedRoute=True)])
    if index == 0:
        value.update(ovpnPort='1194', ovpnProtocol=0, ovpnAuthType=0,
                     ovpnConfig='audit-config-' + run_id, askpass='synthetic-askpass-' + run_id)
    else:
        value.update(ipsecPreSharedKey='synthetic-psk-' + run_id, ipsecIdentifier='audit-identifier')
        if index == 2:
            value['l2tpSharedKey'] = 'synthetic-l2tp-' + run_id
    return value


def exact(actual, expected):
    """Reject JS bool/int equivalence and malformed nested native objects."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(exact(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def verify_config(text, run_id, index, revision, account):
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('actual VPN config must be an object')
    expected = expected_config(run_id, index, revision, account)
    # Optional empty arrays retain the existing documented omission behavior.
    for key in ('trustedApplications', 'blockedApplications'):
        if not expected[key] and key not in value:
            value[key] = []
    for key, field in expected.items():
        if key not in value or not exact(value[key], field):
            raise ValueError('actual stored VPN field differs: ' + key)
    return value


def expected(role, phase):
    if role not in ROLES or phase not in ('seed', 'restart', 'denial') or (
            (role == 'system') != (phase != 'denial')):
        raise ValueError('incompatible VPN store role/phase')
    rows = [('identity', None, None)]
    def snapshots(name, index, revision):
        rows.extend((name + '.' + method + '.' + str(index), [revision], (index, revision))
                    for method in ('get', 'list'))
    if phase == 'denial':
        rows += [('denied.' + str(index), [1, 202 if role == 'normal' else 201, 1], None)
                 for index in range(4)]
    elif phase == 'seed':
        rows.append(('initial', [0], None))
        for index in range(3):
            snapshots('seed', index, 0)
            snapshots('replace', index, 1)
        rows += [('invalid.prefix', [1, 401, 1], None)] * 6
        snapshots('after-invalid', 0, 1)
    else:
        for index in range(3):
            snapshots('restart', index, 1)
        rows.append(('cleanup', [0], None))
    return rows + [('summary', [1, 1 if phase == 'seed' else 0], None)]


def verify(text, run_id, role, phase, identity_text):
    if re.fullmatch('[a-f0-9]{32}', run_id or '') is None or not text.endswith('\n'):
        raise ValueError('fresh nonce and complete append-only VPN observations required')
    uid = identity(identity_text, role)
    rows = [json.loads(line) for line in text.splitlines()]
    contract = expected(role, phase)
    if len(rows) != len(contract):
        raise ValueError('missing/extra VPN store observations')
    for row, (name, values, config) in zip(rows, contract):
        if (not isinstance(row, dict) or set(row) != {'runId', 'role', 'name', 'values', 'config', 'error'} or
                row['runId'] != run_id or row['role'] != role or row['name'] != name or row['error'] != '' or
                not isinstance(row['values'], list) or any(type(value) is not int for value in row['values']) or
                not isinstance(row['config'], str)):
            raise ValueError('failed/malformed/reordered VPN store observation: ' + name)
        if values is None:
            if len(row['values']) != 3 or row['values'][:2] != [uid, uid] or row['values'][2] <= 1:
                raise ValueError('VPN store caller identity differs')
        elif row['values'] != values:
            raise ValueError('VPN store behavior differs: ' + name)
        if config is None:
            if row['config'] != '':
                raise ValueError('unexpected VPN config payload: ' + name)
        else:
            verify_config(row['config'], run_id, *config, uid // 200000)
    return rows


def verify_inputs(value, run_id, arch, role):
    generated, declaration = (Path(value[key]) for key in ('generated_source', 'sdk_declaration'))
    if (type(value.get('schema_version')) is not int or value['schema_version'] != 1 or
            value.get('run_id') != run_id or value.get('arch') != arch or value.get('role') != role or
            arch not in ('arm64', 'armv7a', 'x86_64') or value.get('scope') != SCOPE or
            value.get('request_permissions') != ([PERMISSION] if role == 'system' else []) or
            value.get('template_sha256') != digest(TEMPLATE) or declaration.name != '@ohos.net.vpn.d.ts' or
            any(path.is_symlink() or not path.is_file() or digest(path) != value.get(key)
                for path, key in ((generated, 'generated_source_sha256'), (declaration, 'sdk_declaration_sha256'))) or
            generated.read_text() != page(run_id, role)):
        raise ValueError('VPN store observations do not match exact current source/SDK/role')


def verify_evidence(document, archive_sha, boot_id, arch, device, target):
    if (document.get('status') != 'pass' or document.get('scope') != EVIDENCE_SCOPE or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('device') != device or document.get('target') != target or
            document.get('failures') != [] or
            document.get('caller_cleanup_verified') is not True or set(document.get('roles', {})) != set(ROLES) or
            re.fullmatch('[0-9a-fA-F]{64}', document.get('udid', '')) is None):
        raise ValueError('exact new-package VPN CRUD/restart and all denied roles required')
    nonces = set()
    for role, record in document['roles'].items():
        paths = {}
        for field in ('inputs', 'application_identity', 'signed_hap', 'signing_receipt'):
            path = Path(record[field])
            if path.is_symlink() or not path.is_file() or digest(path) != record.get(field + '_sha256'):
                raise ValueError('VPN store evidence changed/missing: ' + field)
            paths[field] = path
        nonce = record['run_id']; nonces.add(nonce)
        if record.get('status') != 'pass' or record.get('actual_uid') != identity(paths['application_identity'].read_text(), role):
            raise ValueError('installed VPN store identity differs')
        verify_inputs(json.loads(paths['inputs'].read_text()), nonce, arch, role)
        receipt = json.loads(paths['signing_receipt'].read_text())
        profile = receipt.get('verified_profile', {})
        with zipfile.ZipFile(paths['signed_hap']) as hap:
            compiled = json.loads(hap.read('module.json'))
        if (receipt.get('status') != 'pass' or receipt.get('role') != role or
                receipt.get('scope') != 'actual_signature_profile_and_codesign_NOT_guest' or
                receipt.get('signed_sha256') != digest(paths['signed_hap']) or
                configure_profile(json.loads(json.dumps(profile)), role, document['udid'], compiled) != profile):
            raise ValueError('actual signed VPN store permission contract differs')
        phases = record.get('phases', {})
        if set(phases) != ({'seed', 'restart'} if role == 'system' else {'denial'}):
            raise ValueError('incomplete VPN store phases')
        for phase, row in phases.items():
            raw = Path(row['raw_results'])
            if raw.is_symlink() or not raw.is_file() or digest(raw) != row.get('raw_results_sha256'):
                raise ValueError('VPN store raw observations changed/missing')
            actual = verify(raw.read_text(), nonce, role, phase, paths['application_identity'].read_text())
            if actual != row.get('results'):
                raise ValueError('VPN store summary differs from raw observations')
        if role == 'system':
            verify_restart(phases['seed']['results'], phases['restart']['results'])
    if len(nonces) != len(ROLES):
        raise ValueError('each VPN store caller requires an independent fresh host nonce')
    return ['arkts_export:@ohos.net.vpn:' + method for method in METHODS]
