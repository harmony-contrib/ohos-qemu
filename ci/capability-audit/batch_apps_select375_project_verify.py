#!/usr/bin/env python3
"""Independently replay raw select375 observations. No pass flag is an input.

This verifies one ordinary caller/target API join. It does not prove native
session destruction, code-sign cryptography, screenshot/UI choice, or full gate.
Root must separately run the shared real Java/CMS signer verifier and UI/native
lifecycle acceptance. The source/SDK/HAP/BMS and same-boot bindings here remain
mandatory; those separate gates may not be inferred from this report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import zipfile

from batch_apps_select375_project import (BOOT, CONTRACT, FIX, HEX, ROLES, checked, load_challenge,
    prepared, regular, require, sha, source_tools)
from batch_apps_select375_project_build import SCOPE, sdk_commands
from guest_ui import command_exit
from hap_identity_binding import bms_application_identity

KEYS = {'schema_version', 'run_id', 'boot_id', 'archive_sha256', 'operation_id', 'case_id', 'phase', 'kind',
        'role', 'uid', 'token_id', 'pid', 'sequence', 'timestamp_ms', 'event', 'api', 'value_json', 'error_code', 'error_message'}
EVENTS = {'begin', 'incoming', 'owned', 'owner_before', 'owner_after', 'probe_call', 'probe_result', 'select_call',
          'select_result', 'deleted', 'private_call', 'private_resolve', 'private_reject', 'read', 'write', 'return',
          'complete', 'error', 'failed'}


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate JSON key'); out[key] = value
    return out


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def payload(req, suffix):
    return 'SELECT375/' + req['run_id'] + '/' + req['operation_id'] + '/' + req['case_id'] + '/' + suffix


def phase(req, kind, stage):
    return dict(req, kind=kind, phase=stage)


def request_shape(req):
    require(isinstance(req, dict) and set(req) == {'schema_version', 'run_id', 'boot_id', 'archive_sha256',
            'operation_id', 'case_id', 'phase', 'kind'} and type(req['schema_version']) is int and req['schema_version'] == 1 and
            re.fullmatch('[a-f0-9]{32}', req['run_id']) and re.fullmatch('[a-f0-9]{32}', req['operation_id']) and
            BOOT.fullmatch(req['boot_id']) and HEX.fullmatch(req['archive_sha256']) and req['case_id'] in CONTRACT['cases'] and
            req['phase'] == 'run' and req['kind'] == 'caller', 'exact original caller request required')


def parse(raw, req, role, identity):
    if raw == '': return []
    require(type(raw) is str and len(raw.encode()) <= 4194304 and raw.endswith('\n') and '\r' not in raw,
            'complete bounded original JSONL required')
    rows, last = [], 0
    for line in raw.splitlines():
        row = decode(line)
        require(isinstance(row, dict) and set(row) == KEYS and type(row['schema_version']) is int and row['schema_version'] == 1,
                'unknown/stripped journal fields')
        require(all(row[k] == req[k] for k in ('run_id', 'boot_id', 'archive_sha256')) and
                row['role'] == role and re.fullmatch('[a-f0-9]{32}', row['operation_id']) and
                row['case_id'] in CONTRACT['cases'] and row['event'] in EVENTS and
                row['kind'] in ('caller', 'select', 'probe') and row['phase'] in ('run', 'choose', 'before', 'after'),
                'foreign journal identity/event')
        require(type(row['sequence']) is int and row['sequence'] == len(rows) + 1 and
                type(row['timestamp_ms']) is int and row['timestamp_ms'] >= last > -1 and row['timestamp_ms'] > 0,
                'reordered journal sequence/clock')
        require(type(row['uid']) is int and row['uid'] == identity['uid'] and row['uid'] // 200000 == 100 and
                type(row['token_id']) is int and row['token_id'] == identity['token_id'] and
                type(row['pid']) is int and 0 < row['pid'] < 2**31 and type(row['error_code']) is int and
                isinstance(row['error_message'], str) and isinstance(row['api'], str) and isinstance(row['value_json'], str),
                'actual installed identity/raw outcome differs')
        decode(row['value_json']); rows.append(row); last = row['timestamp_ms']
    return rows


def value(row): return decode(row['value_json'])


def success(row, event, api=None):
    require(row['event'] == event and row['error_code'] == 0 and row['error_message'] == '' and
            (api is None or row['api'] == api), 'unexpected API event/error: ' + event)
    return value(row)


def result(req, role, stage):
    return {'resultCode': CONTRACT['result_codes'][role], 'want': {'parameters': {
        'run_id': req['run_id'], 'operation_id': req['operation_id'], 'case_id': req['case_id'],
        'phase': stage, 'role': role, 'receipt': payload(req, 'result-' + role + '-' + stage)}}}


def returned_result(actual, expected):
    """N-API may materialize known empty Want fields; never strip metadata."""
    require(isinstance(actual, dict) and set(actual) <= {'resultCode', 'want'} and
            type(actual.get('resultCode')) is int and actual['resultCode'] == expected['resultCode'], 'actual result code differs')
    want = actual.get('want')
    if want is None:
        require('want' not in expected, 'actual target result Want absent'); return
    require(isinstance(want, dict), 'actual result Want must be an object')
    defaults = {'deviceId': '', 'bundleName': '', 'moduleName': '', 'abilityName': '', 'uri': '', 'type': '',
                'action': '', 'flags': 0, 'entities': []}
    require(set(want) <= set(defaults) | {'parameters'} and all(
            type(want[k]) is type(v) and want[k] == v for k, v in defaults.items() if k in want),
            'result retained a foreign component/URI/flag or unknown metadata')
    require(want.get('parameters', {}) == expected.get('want', {}).get('parameters', {}), 'result payload/nonce differs')


def target(rows, req, role, kind, stage, uri):
    expected_req = phase(req, kind, stage)
    require(len(rows) == 6 and [r['event'] for r in rows] == ['begin', 'incoming', 'read', 'write', 'return', 'complete'] and
            all(all(r[k] == expected_req[k] for k in expected_req) for r in rows), 'exact sole target invocation required')
    require(success(rows[0], 'begin', 'request') == expected_req, 'target substituted request')
    incoming = success(rows[1], 'incoming', 'UIAbility.Want')
    require(isinstance(incoming, dict) and isinstance(incoming.get('parameters'), dict) and
            decode(incoming['parameters'].get('request', '')) == expected_req and
            incoming.get('bundleName') == ROLES[role]['bundle'] and incoming.get('abilityName') == 'EntryAbility' and
            incoming.get('moduleName') == 'entry', 'actual target Want/component differs')
    if kind == 'probe':
        require(incoming.get('flags', 0) == 0 and 'uri' not in incoming and incoming['parameters'].get('probe_uri') == uri,
                'foreign probe received a grant/URI field')
    else:
        flags = CONTRACT['cases'][req['case_id']]['flags']
        require(incoming.get('uri') == uri and incoming.get('action', '') == '' and
                incoming.get('type') == CONTRACT['mime'] and incoming.get('entities') == [CONTRACT['entity']] and
                type(incoming.get('flags')) is int and incoming['flags'] & 3 == flags, 'selected original Want/URI flags differ')
    for i, event in [(2, 'read'), (3, 'write')]:
        row = rows[i]
        require(row['event'] == event and row['api'] == ('fileIo.openSync/readSync' if event == 'read' else 'fileIo.openSync/writeSync'),
                'actual FileIO invocation missing')
        granted = kind == 'select' and (CONTRACT['cases'][req['case_id']]['flags'] & (1 if event == 'read' else 2)) != 0
        if granted:
            observed = success(row, event)
            require(observed == payload(req, 'original' if event == 'read' else 'modified'), 'actual payload bytes differ')
        else:
            require(row['error_code'] == CONTRACT['permission_denied_file_code'] and row['error_message'] and value(row) is None,
                    'real permission-denied required; missing file/parse/transport error is not denial')
    require(success(rows[4], 'return', 'UIAbilityContext.terminateSelfWithResult') == result(req, role, stage) and
            success(rows[5], 'complete', '') is None, 'actual target returned another nonce/result')
    return result(req, role, stage)


def verify_operation(req, before, after, identities):
    """Pure raw API join; callers must first bind bytes to real guest commands."""
    request_shape(req); require(set(before) == set(after) == set(identities) == set(ROLES), 'three complete role snapshots required')
    additions = {}
    for role in ROLES:
        old, new = parse(before[role], req, role, identities[role]), parse(after[role], req, role, identities[role])
        require(new[:len(old)] == old and not any(r['operation_id'] == req['operation_id'] for r in old), 'journal rewritten or reused nonce')
        additions[role] = new[len(old):]
        require(all(r['operation_id'] == req['operation_id'] and r['case_id'] == req['case_id'] for r in additions[role]),
                'unconsumed additional operation in collection window')
    caller = additions['caller']; case = req['case_id']
    require(caller and all(r['kind'] == 'caller' and r['phase'] == 'run' for r in caller), 'caller scope differs')
    require(success(caller[0], 'begin', 'request') == req, 'caller request substitution')
    incoming = success(caller[1], 'incoming', 'UIAbility.Want')
    require(decode(incoming.get('parameters', {}).get('request', '')) == req, 'caller launch request differs')
    if case in ('private-start', 'forged-sid'):
        require(len(caller) == 5 and not additions['target_a'] and not additions['target_b'], 'private-start caused target or extra operation')
        want = {'bundleName': 'com.ohos.settings', 'abilityName': 'PickerDialog'}
        if case == 'forged-sid': want['parameters'] = {'dialogSessionId': 'legacy_picker_' + req['operation_id']}
        require(success(caller[2], 'private_call', 'UIAbilityContext.startAbility') == want and
                caller[3]['event'] == 'private_reject' and caller[3]['api'] == 'UIAbilityContext.startAbility' and
                caller[3]['error_code'] in CONTRACT['private_start_denied_codes'] and caller[3]['error_message'] and
                value(caller[3]) is None and success(caller[4], 'complete', '') is None, 'explicit private start did not actually reject')
        return {'case_id': case, 'operation_id': req['operation_id'], 'observed_private_start_error': caller[3]['error_code']}
    expected_events = ['begin', 'incoming', 'owned', 'owner_before']
    if case != 'cancel': expected_events += ['probe_call', 'probe_result']
    expected_events += ['select_call', 'select_result', 'owner_after']
    if case != 'cancel': expected_events += ['probe_call', 'probe_result']
    expected_events += ['deleted', 'complete']
    require([r['event'] for r in caller] == expected_events, 'missing/extra/reordered caller action')
    uri = success(caller[2], 'owned', 'fileUri.getUriFromPath')
    suffix = '/select375-' + req['run_id'] + '-' + req['operation_id'] + '.txt'
    require(isinstance(uri, str) and uri == 'file://' + ROLES['caller']['bundle'] + '/data/storage/el2/base/files' + suffix,
            'exact owned app-root URI required; module filesDir/foreign/alias URI refused')
    require(success(caller[3], 'owner_before', 'fileIo.openSync/readSync') == payload(req, 'original'), 'owner did not read true original payload')
    offset = 4 if case == 'cancel' else 6
    want = {'action': CONTRACT['action'], 'uri': uri, 'type': CONTRACT['mime'], 'entities': [CONTRACT['entity']],
            'flags': CONTRACT['cases'][case]['flags'], 'parameters': {'request': json.dumps(phase(req, 'select', 'choose'), separators=(',', ':'))}}
    actual = success(caller[offset], 'select_call', 'UIAbilityContext.startAbilityForResult')
    require(set(actual) == set(want) and all(actual[k] == want[k] for k in want if k != 'parameters') and
            set(actual['parameters']) == {'request'} and decode(actual['parameters']['request']) == phase(req, 'select', 'choose'),
            'actual select call is explicit/substituted or has different URI authorization')
    returned = success(caller[offset + 1], 'select_result', 'UIAbilityContext.startAbilityForResult')
    if case == 'cancel':
        require(not additions['target_a'] and not additions['target_b'], 'cancellation invoked a target')
        returned_result(returned, {'resultCode': -1})
    else:
        role = CONTRACT['cases'][case]['target']; other = 'target_b' if role == 'target_a' else 'target_a'
        expected = target(additions[role], req, role, 'select', 'choose', uri)
        returned_result(returned, expected)
        require(len(additions[other]) == 12, 'both actual foreign probes required')
        for index, stage, call_at in [(0, 'before', 4), (6, 'after', 9)]:
            expected = target(additions[other][index:index + 6], req, other, 'probe', stage, uri)
            probe_want = success(caller[call_at], 'probe_call', 'UIAbilityContext.startAbilityForResult')
            require(set(probe_want) == {'bundleName', 'moduleName', 'abilityName', 'flags', 'parameters'} and
                    probe_want['bundleName'] == ROLES[other]['bundle'] and probe_want['moduleName'] == 'entry' and
                    probe_want['abilityName'] == 'EntryAbility' and probe_want['flags'] == 0 and
                    set(probe_want['parameters']) == {'request', 'probe_uri'} and probe_want['parameters']['probe_uri'] == uri and
                    decode(probe_want['parameters']['request']) == phase(req, 'probe', stage), 'probe grant or identity changed')
            returned_result(success(caller[call_at + 1], 'probe_result', 'UIAbilityContext.startAbilityForResult'), expected)
            t = additions[other][index:index + 6]
            require(caller[call_at]['timestamp_ms'] <= t[0]['timestamp_ms'] <= t[-1]['timestamp_ms'] <= caller[call_at + 1]['timestamp_ms'],
                    'probe/caller invocation ordering differs')
        chosen = additions[role]
        require(caller[offset]['timestamp_ms'] <= chosen[0]['timestamp_ms'] <= chosen[-1]['timestamp_ms'] <= caller[offset + 1]['timestamp_ms'],
                'target was invoked outside the select pending interval')
    require(success(caller[offset + 2], 'owner_after', 'fileIo.openSync/readSync') == payload(req, 'modified' if case == 'write-a' else 'original'),
            'real owner readback differs from requested URI write boundary')
    require(success(caller[-2], 'deleted', 'fileIo.unlinkSync/accessSync') ==
            {'path': '/data/storage/el2/base/files' + suffix, 'exists_after': False} and
            success(caller[-1], 'complete', '') is None, 'owned public file cleanup not observed')
    return {'case_id': case, 'operation_id': req['operation_id'], 'selected_target': CONTRACT['cases'][case]['target'], 'uri': uri}


def sdk_binding(spec, role, challenge_path):
    project = Path(spec['source_project']); manifest, rows = prepared(project, role, challenge_path)
    report = decode(checked(spec['sdk_evidence']).read_text())
    require(report.get('schema_version') == 1 and report.get('scope') == SCOPE and
            type(report.get('exit_code')) is int and report['exit_code'] == 0 and report.get('failures') == [] and
            report.get('source_commit') == manifest['source_commit'] and report.get('source_tools') == source_tools() and
            report.get('sdk') == manifest['sdk'] and report.get('node_version') == 'v18.20.1' and
            set(report.get('source_files', {})) == set(ROLES) and report['source_files'][role] == rows and
            len(report.get('haps', [])) == 3 and {r.get('project') for r in report['haps']} == set(ROLES), 'actual exact SDK105 three-role provenance required')
    require(sha(checked(report['tools']['cpu_cap'])) == sha(FIX / 'cpu-cap.cjs'), 'bounded SDK preload differs')
    commands = report.get('commands', []); expected = sdk_commands(report['tools'])
    version = report.get('node_version_command', {})
    require(version.get('argv') == [str(checked(report['tools']['node'])), '--version'] and
            version.get('project') == 'tools' and version.get('label') == 'node-version' and
            version.get('actual_observation_received') is True and
            type(version.get('exit_code')) is int and version['exit_code'] == 0 and
            type(version.get('started_ns')) is int and type(version.get('finished_ns')) is int and
            0 < version['started_ns'] <= version['finished_ns'] and
            not version.get('timed_out', False) and checked(version['log']).read_text().strip() == 'v18.20.1',
            'actual root-runner Node version command missing')
    require(len(commands) == 6 and [r.get('project') for r in commands] == [r for role in ROLES for r in [role, role]], 'serial three-role SDK commands required')
    for row, (label, argv) in zip([r for r in commands if r['project'] == role], expected):
        require(row.get('label') == label and row.get('argv') == argv and row.get('cwd') == str(project) and
                row.get('actual_observation_received') is True and type(row.get('exit_code')) is int and
                row['exit_code'] == 0 and not row.get('timed_out', False), 'actual SDK argv/cwd/exit differs')
        require(type(row.get('started_ns')) is int and type(row.get('finished_ns')) is int and
                0 < row['started_ns'] <= row['finished_ns'], 'actual SDK command times absent')
        text = checked(row['log']).read_text(errors='replace')
        if label == 'compile': require('BUILD SUCCESSFUL' in text, 'real compiler success absent')
    hap = checked(spec['unsigned_hap']); built = next(v for v in report['haps'] if v['project'] == role)
    require(hap == project / 'entry/build/default/outputs/default/entry-default-unsigned.hap' and
            built['path'] == str(hap) and built['sha256'] == sha(hap) and built['bytes'] == hap.stat().st_size, 'actual compiled role HAP differs')
    return hap


def wrapped(script, operation):
    marker = '__SELECT375_EXIT_' + operation + '__='
    return script + '; select375_rc=$?; printf "\\n' + marker + '%s\\n" "$select375_rc"', marker


def command(row, script, request, hdc, endpoint):
    shell, marker = wrapped(script, request['operation_id'])
    require(set(row) == {'argv', 'host_exit_code', 'raw', 'started_ns', 'finished_ns'} and
            row['argv'] == [str(hdc), '-t', endpoint, 'shell', shell] and
            type(row['host_exit_code']) is int and row['host_exit_code'] == 0 and
            type(row['started_ns']) is int and type(row['finished_ns']) is int and 0 < row['started_ns'] <= row['finished_ns'],
            'exact trusted HDC command and actual host exit/time required')
    raw = checked(row['raw']).read_text()
    require(not any(x in raw for x in ('[Fail]', 'HDCFail', 'Connect server failed', 'device not found')), 'HDC transport failure')
    body, code = command_exit(raw, marker)
    require(code == 0, 'actual guest command failed')
    return body


def journal_script(req, role):
    path = '/data/app/el2/100/base/' + ROLES[role]['bundle'] + '/files/select375-' + req['run_id'] + '-' + req['boot_id'] + '.jsonl'
    absent = '__SELECT375_ABSENT_' + req['operation_id'] + '__'
    q = shlex.quote(path)
    return 'if test -e ' + q + '; then cat ' + q + '; else printf "%s\\n" ' + shlex.quote(absent) + '; fi', absent


def identity(body, role):
    out = bms_application_identity(body, ROLES[role]['bundle'])
    start = body.index('{'); app = decode(body[start:])
    require(app['applicationInfo'].get('isSystemApp') is False and app['applicationInfo'].get('appPrivilegeLevel') == 'normal' and
            app.get('reqPermissions') == [], 'all three installed roles must remain ordinary and permission-free')
    paths = {x['hapPath'] for x in walk_objects(app) if isinstance(x.get('hapPath'), str) and x['hapPath'].endswith('.hap')}
    require(len(paths) == 1, 'unique actual installed HAP path required')
    path = paths.pop()
    require(path.startswith('/data/app/') and not any(x in path.split('/')[1:] for x in ('', '.', '..')) and '//' not in path,
            'canonical installed data-app HAP path required')
    out['hap_path'] = path
    return out


def walk_objects(v):
    if isinstance(v, dict):
        yield v
        for child in v.values(): yield from walk_objects(child)
    elif isinstance(v, list):
        for child in v: yield from walk_objects(child)


def verify_runtime(spec, challenge_path, expected_request, hdc, endpoint, archive_sha):
    """Read-only root entry. Caller supplies trusted current request/endpoint/HDC.

    ``commands`` contains before then after snapshots, each boot + BMS/journal/
    installed-hash for caller/A/B. Actual UI and launch commands are separately
    preserved by root; this API does not label their broader gate as passed.
    """
    req = decode(regular(expected_request).read_text()); request_shape(req)
    data = load_challenge(challenge_path)
    require(req['run_id'] == data['run_id'] and req['archive_sha256'] == archive_sha and HEX.fullmatch(archive_sha), 'actual root challenge/archive differs')
    hdc = regular(hdc); require(isinstance(endpoint, str) and re.fullmatch('[A-Za-z0-9_.:-]{1,128}', endpoint), 'explicit trusted endpoint required')
    require(set(spec) == {'schema_version', 'request', 'applications', 'commands'} and spec['schema_version'] == 1 and
            checked(spec['request']) == Path(expected_request) and set(spec['applications']) == set(ROLES) and len(spec['commands']) == 20,
            'complete original runtime artifact/command set required')
    previous = 0
    for row in spec['commands']:
        require(type(row.get('started_ns')) is int and row['started_ns'] >= previous and type(row.get('finished_ns')) is int,
                'commands overlap or are reordered'); previous = row['finished_ns']
    identities, snapshots = {}, {'before': {}, 'after': {}}
    signed = {}
    from batch_apps_contact_picker_coordinator import verify_signed_payload, ordinary_hap, verify_profile
    for role in ROLES:
        app = spec['applications'][role]; unsigned = sdk_binding(app, role, challenge_path)
        signed[role] = checked(app['signed_hap']); verify_signed_payload(unsigned, signed[role]); ordinary_hap(signed[role], ROLES[role]['bundle'], [])
        profile = decode(checked(app['decoded_profile']).read_text())
        verify_profile(profile, ROLES[role]['bundle'], [], app['actual_guest_udid'])
        require(sha(checked(app['installed_hap'])) == sha(signed[role]), 'pulled actual installed HAP differs')
    for snap, offset in [('before', 0), ('after', 10)]:
        commands = spec['commands'][offset:offset + 10]
        boot = command(commands[0], 'cat /proc/sys/kernel/random/boot_id', req, hdc, endpoint).strip()
        require(boot == req['boot_id'], 'actual guest reboot/foreign boot')
        for i, role in enumerate(ROLES):
            n = 1 + 3 * i
            current = identity(command(commands[n], 'bm dump -n ' + ROLES[role]['bundle'], req, hdc, endpoint), role)
            if snap == 'before': identities[role] = current
            else: require(identities[role] == current, 'installed identity changed during operation')
            script, absent = journal_script(req, role)
            body = command(commands[n + 1], script, req, hdc, endpoint)
            snapshots[snap][role] = '' if body == absent + '\n' else body
            path = current['hap_path']
            hashes = command(commands[n + 2], 'sha256sum ' + shlex.quote(path), req, hdc, endpoint)
            require(hashes == sha(signed[role]) + '  ' + path + '\n', 'actual installed guest HAP hash differs')
    require(len({v['uid'] for v in identities.values()}) == 3 and len({v['token_id'] for v in identities.values()}) == 3,
            'roles must have distinct actual installed UID/token owners')
    result = verify_operation(req, snapshots['before'], snapshots['after'], identities)
    return {'scope': 'raw_select375_single_operation_source_SDK_HAP_BMS_boot_API_join_ONLY', **result,
        'archive_sha256': archive_sha, 'boot_id': req['boot_id'], 'identity_roles': identities,
        'signature_cryptography_verified_here': False, 'UI_choice_verified_here': False,
        'native_owner_release_verified_here': False, 'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('evidence', 'challenge', 'request', 'hdc'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--endpoint', required=True); parser.add_argument('--archive-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(verify_runtime(decode(args.evidence.read_text()), args.challenge, args.request, args.hdc, args.endpoint, args.archive_sha), indent=2))


if __name__ == '__main__': main()
