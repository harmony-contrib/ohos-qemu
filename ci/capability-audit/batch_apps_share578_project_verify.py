#!/usr/bin/env python3
"""Independently replay raw share578 observations. No pass flag is an input.

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

from batch_apps_share578_project import (BOOT, CONTRACT, FIX, HEX, ROLES, checked, load_challenge,
    prepared, regular, require, sha, source_tools)
from batch_apps_share578_project_build import SCOPE, sdk_commands
from guest_ui import command_exit
from hap_identity_binding import bms_application_identity

KEYS = {'schema_version', 'run_id', 'boot_id', 'archive_sha256', 'operation_id', 'case_id', 'phase', 'kind',
        'role', 'uid', 'token_id', 'pid', 'sequence', 'timestamp_ms', 'event', 'api', 'value_json', 'error_code', 'error_message'}
EVENTS = {'begin', 'incoming', 'owned', 'owner_before', 'owner_after', 'probe_call', 'probe_result', 'select_call',
          'select_result', 'deleted', 'private_call', 'private_resolve', 'private_reject', 'read', 'write', 'return',
          'complete', 'error', 'failed', 'text', 'share_call', 'share_opened', 'share_result',
          'share_callback_error', 'duplicate_callback', 'cleanup_ready', 'cleanup_confirmed', 'mms_call', 'mms_opened'}


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'duplicate JSON key'); out[key] = value
    return out


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def payload(req, suffix):
    return 'SHARE578/' + req['run_id'] + '/' + req['operation_id'] + '/' + req['case_id'] + '/' + suffix


def phase(req, kind, stage):
    return dict(req, kind=kind, phase=stage)


def request_shape(req):
    require(isinstance(req, dict) and set(req) == {'schema_version', 'run_id', 'boot_id', 'archive_sha256',
            'operation_id', 'case_id', 'phase', 'kind'} and type(req['schema_version']) is int and req['schema_version'] == 1 and
            re.fullmatch('[a-f0-9]{32}', req['run_id']) and re.fullmatch('[a-f0-9]{32}', req['operation_id']) and
            BOOT.fullmatch(req['boot_id']) and HEX.fullmatch(req['archive_sha256']) and req['case_id'] in list(CONTRACT['cases']) + list(CONTRACT['mms_cases']) and
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
                row['case_id'] in list(CONTRACT['cases']) + list(CONTRACT['mms_cases']) and row['event'] in EVENTS and
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


def additions(req, before, after, identities):
    request_shape(req)
    require(set(before) == set(after) == set(identities) == set(ROLES), 'three complete snapshots required')
    out = {}
    for role in ROLES:
        old, new = parse(before[role], req, role, identities[role]), parse(after[role], req, role, identities[role])
        require(new[:len(old)] == old and not any(r['operation_id'] == req['operation_id'] for r in old), 'rewritten/reused journal')
        out[role] = new[len(old):]
        require(all(r['operation_id'] == req['operation_id'] and r['case_id'] == req['case_id'] for r in out[role]), 'foreign operation in raw window')
    return out


def owned(req, caller):
    require(len(caller) >= 4 and all(r['kind'] == 'caller' and r['phase'] == 'run' for r in caller), 'caller scope differs')
    require(success(caller[0], 'begin', 'request') == req and decode(success(caller[1], 'incoming', 'UIAbility.Want').get('parameters', {}).get('request', '')) == req, 'caller substituted request')
    suffix = '/share578-' + req['run_id'] + '-' + req['operation_id'] + '.txt'
    uri = success(caller[2], 'owned', 'fileUri.getUriFromPath')
    require(uri == 'file://' + ROLES['caller']['bundle'] + '/data/storage/el2/base/files' + suffix, 'exact owned app-root URI required')
    require(success(caller[3], 'owner_before', 'fileIo.openSync/readSync') == payload(req, 'original'), 'owner original bytes differ')
    return uri, suffix


def shared_call(req, row, uri):
    params = {'type': CONTRACT['mime'], 'uri': uri, 'ability.params.stream': [uri],
        'ability.subject': json.dumps(phase(req, 'select', 'choose'), separators=(',', ':')),
        'ability.want.params.uriPermissionFlag': CONTRACT['cases'][req['case_id']]['flags']}
    if req['case_id'] == 'text-a':
        params = {'type': 'text/plain', 'ability.params.stream': payload(req, 'original'), 'ability.subject': params['ability.subject']}
    actual = success(row, 'share_call', 'UIAbilityContext.startAbilityByType')
    require(isinstance(actual, dict) and set(actual) == {'type', 'parameters'} and actual['type'] == 'share' and
        set(actual['parameters']) == set(params) and all(actual['parameters'][k] == v for k, v in params.items() if k != 'ability.subject') and
        decode(actual['parameters']['ability.subject']) == phase(req, 'select', 'choose'), 'actual public modal API/URI/flags/subject differ')


def target(rows, req, role, kind, stage, uri):
    expect_req = phase(req, kind, stage)
    text = req['case_id'] == 'text-a' and kind == 'select'
    require([r['event'] for r in rows] == (['begin', 'incoming', 'text', 'return', 'complete'] if text else
        ['begin', 'incoming', 'read', 'write', 'return', 'complete']) and
        all(all(r[k] == v for k, v in expect_req.items()) for r in rows), 'exact real target invocation required')
    require(success(rows[0], 'begin', 'request') == expect_req, 'receiver nonce differs')
    want = success(rows[1], 'incoming', 'UIAbility.Want'); params = want.get('parameters', {})
    require(want.get('bundleName') == ROLES[role]['bundle'] and want.get('moduleName') == 'entry' and want.get('abilityName') == 'EntryAbility', 'actual delivered component differs')
    if kind == 'probe':
        require(decode(params.get('request', '')) == expect_req and params.get('probe_uri') == uri and
            want.get('flags', 0) == 0 and 'uri' not in want, 'text-only probe acquired grant')
    else:
        require('request' not in params and decode(params.get('ability.subject', '')) == expect_req and
            want.get('action') == CONTRACT['action'], 'modal receiver did not consume actual filtered sendData Want')
        if text:
            require(want.get('type') == 'text/plain' and want.get('uri', '') == '' and
                params.get('ability.params.stream') == payload(req, 'original') and
                success(rows[2], 'text', 'UIAbility.Want.parameters') == payload(req, 'original'), 'actual shared text differs')
        else:
            require(want.get('type') == CONTRACT['mime'] and want.get('uri') == uri and params.get('ability.params.stream') == [uri] and
                type(want.get('flags')) is int and want['flags'] & 3 == 1, 'Share must forward READ only, including caller flags=3')
    if not text:
        for i, event in [(2, 'read'), (3, 'write')]:
            row = rows[i]; api = 'fileIo.openSync/readSync' if event == 'read' else 'fileIo.openSync/writeSync'
            require(row['event'] == event and row['api'] == api, 'actual receiver IO missing')
            if kind == 'select' and event == 'read':
                require(success(row, event, api) == payload(req, 'original'), 'receiver did not read original nonce bytes')
            else:
                require(row['error_code'] == CONTRACT['permission_denied_file_code'] and row['error_message'] and value(row) is None,
                    'real URI authorization denial required; ENOENT/empty/model outcome is not denial')
    returned = rows[-2]
    if kind == 'probe':
        require(success(returned, 'return', 'UIAbilityContext.terminateSelfWithResult') == result(req, role, stage), 'probe returned foreign nonce')
    else:
        require(success(returned, 'return', 'UIAbilityContext.terminateSelf') is None, 'modal target exit differs')
    require(success(rows[-1], 'complete', '') is None, 'receiver not complete')
    return result(req, role, stage)


def verify_operation(req, before, after, identities):
    delta = additions(req, before, after, identities); caller = delta['caller']; case = req['case_id']
    require(case != 'death', 'death requires native raw process and UI lifetime verifier')
    uri, suffix = owned(req, caller)
    probes = case not in ('text-a', 'cancel'); offset = 6 if probes else 4
    expected = ['begin', 'incoming', 'owned', 'owner_before'] + (['probe_call', 'probe_result'] if probes else [])
    expected += ['share_call']
    require([r['event'] for r in caller[:offset+1]] == expected, 'caller invocation prefix differs')
    shared_call(req, caller[offset], uri)
    callbacks = caller[offset+1:offset+3]
    require(sorted(r['event'] for r in callbacks) == ['share_opened', 'share_result'], 'exact one real modal start and callback required')
    opened = next(r for r in callbacks if r['event'] == 'share_opened')
    require(success(opened, 'share_opened', 'UIAbilityContext.startAbilityByType') is None, 'public start failed')
    returned = success(next(r for r in callbacks if r['event'] == 'share_result'), 'share_result', 'AbilityStartCallback.onResult')
    tail = caller[offset+3:]
    require([r['event'] for r in tail] == ['cleanup_ready', 'cleanup_confirmed', 'owner_after'] +
        (['probe_call', 'probe_result'] if probes else []) + ['deleted', 'complete'], 'caller cleanup action missing/reordered')
    require(success(tail[0], 'cleanup_ready', '') is None and success(tail[1], 'cleanup_confirmed', 'UI.onClick') is None, 'root must explicitly release payload only after receiver IO')
    target_role = CONTRACT['cases'][case]['target']
    if case == 'no-grant-a':
        require(returned.get('resultCode') == 401 and returned.get('want', {}).get('parameters', {}).get('outcome') == 'invalid' and
            isinstance(returned.get('want', {}).get('parameters', {}).get('message'), str) and returned['want']['parameters']['message'], 'missing READ must really fail validation')
    else:
        returned_result(returned, {'resultCode': 1 if case == 'cancel' else 0, 'want': {'parameters': {
            'outcome': 'cancelled' if case == 'cancel' else 'launched',
            'selectedBundleName': ROLES[target_role]['bundle'] if target_role else '',
            'selectedModuleName': 'entry' if target_role else '', 'selectedAbilityName': 'EntryAbility' if target_role else ''}}})
    for role in ('target_a', 'target_b'):
        if role == target_role:
            target(delta[role], req, role, 'select', 'choose', uri)
            require(caller[offset]['timestamp_ms'] <= delta[role][0]['timestamp_ms'] <= delta[role][-1]['timestamp_ms'] <= tail[1]['timestamp_ms'], 'payload cleanup preceded receiver real IO')
        elif probes and role == ('target_b' if case not in ('read-b',) else 'target_a'):
            require(len(delta[role]) == 12, 'both actual unselected URI probes required')
            for at, stage, call in [(0, 'before', caller[4]), (6, 'after', tail[3])]:
                chosen = delta[role][at:at+6]; expected_result = target(chosen, req, role, 'probe', stage, uri)
                want = success(call, 'probe_call', 'UIAbilityContext.startAbilityForResult')
                require(want == {'bundleName': ROLES[role]['bundle'], 'moduleName':'entry','abilityName':'EntryAbility','flags':0,
                    'parameters':{'request': json.dumps(phase(req,'probe',stage), separators=(',',':')), 'probe_uri':uri}}, 'probe added authorization/foreign request')
                reply = caller[5] if stage == 'before' else tail[4]
                returned_result(success(reply, 'probe_result', 'UIAbilityContext.startAbilityForResult'), expected_result)
                require(call['timestamp_ms'] <= chosen[0]['timestamp_ms'] <= chosen[-1]['timestamp_ms'] <= reply['timestamp_ms'], 'probe not within actual caller call')
        else:
            require(not delta[role], 'cancel/deny/unselected target invoked')
    require(success(tail[2], 'owner_after', 'fileIo.openSync/readSync') == payload(req,'original') and
        success(tail[-2], 'deleted', 'fileIo.unlinkSync/accessSync') == {'path':'/data/storage/el2/base/files'+suffix,'exists_after':False} and
        success(tail[-1], 'complete','') is None, 'real owner readback/unlink not observed')
    return {'case_id':case,'operation_id':req['operation_id'],'selected_target':target_role,'uri':uri}


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
    marker = '__SHARE578_EXIT_' + operation + '__='
    return script + '; share578_rc=$?; printf "\\n' + marker + '%s\\n" "$share578_rc"', marker


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
    prefix = 'mms578' if req['case_id'] in CONTRACT['mms_cases'] else 'share578'
    path = '/data/app/el2/100/base/' + ROLES[role]['bundle'] + '/files/' + prefix + '-' + req['run_id'] + '-' + req['boot_id'] + '.jsonl'
    absent = '__SHARE578_ABSENT_' + req['operation_id'] + '__'
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


def bind_runtime(spec, challenge_path, expected_request, hdc, endpoint, archive_sha):
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
    return req, snapshots, identities


def verify_runtime(spec, challenge_path, expected_request, hdc, endpoint, archive_sha):
    req, snapshots, identities = bind_runtime(spec, challenge_path, expected_request, hdc, endpoint, archive_sha)
    result = verify_operation(req, snapshots['before'], snapshots['after'], identities)
    return {'scope': 'raw_modal_Share578_single_operation_source_SDK_HAP_BMS_boot_API_join_ONLY', **result,
        'archive_sha256': archive_sha, 'boot_id': req['boot_id'], 'identity_roles': identities,
        'signature_cryptography_verified_here': False, 'UI_choice_verified_here': False,
        'native_owner_release_verified_here': False, 'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('evidence', 'challenge', 'request', 'hdc'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--endpoint', required=True); parser.add_argument('--archive-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(verify_case(decode(args.evidence.read_text()), args.challenge, args.request, args.hdc, args.endpoint, args.archive_sha), indent=2))




def ui_command(row, hdc, endpoint):
    require(set(row) == {'argv','host_exit_code','raw','started_ns','finished_ns'} and row['argv'][:4] == [str(hdc),'-t',endpoint,'shell'] and
        len(row['argv']) == 5 and type(row['host_exit_code']) is int and row['host_exit_code'] == 0 and
        type(row['started_ns']) is int and type(row['finished_ns']) is int and 0 < row['started_ns'] <= row['finished_ns'], 'actual UITest root command required')
    match = re.fullmatch(r'(.+); task_ui_rc=\$\?; printf "\\n(__UITEST_EXIT_[a-f0-9]{32}__=)%s\\n" "\$task_ui_rc"', row['argv'][4])
    require(match is not None, 'exact packaged UITest wrapper required')
    raw = checked(row['raw']).read_text(); body, code = command_exit(raw, match[2])
    require(code == 0 and not any(x in raw for x in ('[Fail]','HDCFail','Connect server failed','device not found')), 'UITest guest/transport failed')
    return match[1], body


def ui_tree(proof, hdc, endpoint, bundle=None):
    require(set(proof) == {'tree','dump','read'}, 'exact raw hierarchy proof required')
    script, raw = ui_command(proof['read'], hdc, endpoint)
    require(re.fullmatch(r'cat /data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[0-9]+[.]json', script), 'fresh UITest hierarchy path required')
    remote = script[4:]; dumped, _ = ui_command(proof['dump'], hdc, endpoint)
    require(dumped == 'test ! -e '+remote+' && uitest dumpLayout -p '+remote+(' -b '+bundle if bundle else '') and
        proof['dump']['finished_ns'] <= proof['read']['started_ns'], 'hierarchy is not bound to actual fresh UITest dump/read')
    layout = decode(checked(proof['tree']).read_text())
    require(layout == decode(raw), 'hierarchy artifact differs from original guest bytes')
    # Traverse even an absence proof: malformed/duplicate/off-screen trees may
    # never turn into successful disappearance.
    from guest_ui import select_node, NodeNotReady
    try: select_node(layout, 'com.ohos.settings', identifier='system-share-title')
    except NodeNotReady: pass
    return layout


def chooser_nodes(layout, req):
    from guest_ui import select_node, NodeNotReady
    settings = 'com.ohos.settings'; select_node(layout, settings, identifier='system-share-title')
    for id_ in ('system-share-error', 'system-share-empty'):
        try: select_node(layout, settings, identifier=id_)
        except NodeNotReady: pass
        else: raise ValueError('actual modal share provider reports an error/empty state')
    ids = {'system-share-target-'+ROLES[r]['bundle']+'/entry/EntryAbility' for r in ('target_a','target_b')}
    # Custom MIME cases must expose exactly our genuine installed receivers.
    # text/plain may expose MMS and other real receivers too; we still require
    # both ordinary audit receivers and click exactly the requested component.
    observed=[]; pending=[(x,'') for x in (layout if isinstance(layout,list) else [layout])]
    while pending:
        node,inherited=pending.pop(); a=node['attributes']; bundle=a.get('bundleName') or inherited
        ident=a.get('id','')
        if bundle==settings and isinstance(ident,str) and ident.startswith('system-share-target-'): observed.append(ident)
        pending.extend((x,bundle) for x in node.get('children',[]))
    require(len(observed)==len(set(observed)), 'duplicate actual share target identity')
    if req['case_id'] != 'text-a': require(set(observed)==ids, 'custom MIME candidates changed or missing')
    else: require(ids <= set(observed), 'both ordinary text receivers required')
    candidates={r:select_node(layout,settings,identifier='system-share-target-'+ROLES[r]['bundle']+'/entry/EntryAbility',clickable=True) for r in ('target_a','target_b')}
    if req['case_id'] in ('cancel','death'): button=select_node(layout,settings,identifier='system-share-cancel',clickable=True)
    else: button=candidates[CONTRACT['cases'][req['case_id']]['target']]
    return {'button':button,'candidates':candidates}


def verify_click(action, req, hdc, endpoint, kind):
    from guest_ui import select_node
    require(set(action)=={'hierarchy','click'}, 'exact hierarchy/click raw proof required')
    bundle='com.ohos.settings' if kind=='chooser' else ROLES['caller']['bundle']
    layout=ui_tree(action['hierarchy'],hdc,endpoint,bundle)
    if kind=='chooser': node=chooser_nodes(layout,req)['button']
    else:
        ready=select_node(layout,bundle,identifier='share578-ready')
        require(ready['attributes'].get('text')=='/'.join([req['run_id'],req['operation_id'],req['case_id'],'run']), 'caller node has foreign nonce')
        node=select_node(layout,bundle,identifier='share578-cleanup' if kind=='cleanup' else 'share578-run',clickable=True)
    left,top,width,height=node['rect']; script,_=ui_command(action['click'],hdc,endpoint)
    require(script=='uitest uiInput click '+str(left+width//2)+' '+str(top+height//2) and
        action['hierarchy']['read']['finished_ns'] <= action['click']['started_ns'], 'click not dispatched on current actual node center')


def process_proof(proof, req, hdc, endpoint, identity):
    from batch_network_openvpn_runtime_collect import snapshot_script, parse_snapshot
    require(set(proof)=={'nonce','command'} and re.fullmatch('[a-f0-9]{32}',proof['nonce']), 'fresh raw kernel scan required')
    bundle=ROLES['caller']['bundle']
    script=snapshot_script(proof['nonce'],req['boot_id'],mode='uid',uid=identity['uid'],bundle=bundle)
    return parse_snapshot(command(proof['command'],script,req,hdc,endpoint),proof['nonce'],req['boot_id'],mode='uid',uid=identity['uid'],bundle=bundle)


def verify_case(spec, challenge_path, expected_request, hdc, endpoint, archive_sha):
    require(set(spec)=={'schema_version','api','actions','launch','death','recovery'} and spec['schema_version']==1, 'complete Share578 raw case envelope required')
    req,snaps,identities=bind_runtime(spec['api'],challenge_path,expected_request,hdc,endpoint,archive_sha)
    require(req['case_id'] in CONTRACT['cases'], 'MMS has a separate narrow raw verifier')
    launch=shlex.join(['aa','start','-b',ROLES['caller']['bundle'],'-a','EntryAbility','--ps','request',json.dumps(req,separators=(',',':'))])
    command(spec['launch'],launch,req,hdc,endpoint)
    require(spec['api']['commands'][9]['finished_ns'] <= spec['launch']['started_ns'], 'caller launch preceded before snapshot')
    require(spec['launch']['finished_ns'] <= spec['actions']['caller']['hierarchy']['dump']['started_ns'], 'caller action preceded current launch')
    start=spec['api']['commands'][9]['finished_ns'];end=spec['api']['commands'][10]['started_ns']
    for name,action in spec['actions'].items():
        proof=action if name=='pending_chooser' else action['hierarchy']
        require(start <= proof['dump']['started_ns'] <= proof['read']['finished_ns'] <= end,'UI proof outside current raw operation window')
        if name!='pending_chooser': require(proof['read']['finished_ns'] <= action['click']['started_ns'] <= action['click']['finished_ns'] <= end,'click outside current raw operation window')
    verify_click(spec['actions']['caller'],req,hdc,endpoint,'caller')
    if req['case_id']=='death':
        require(spec['recovery'] is None,'death cannot borrow recovery')
        require(set(spec['actions'])=={'caller','pending_chooser'} and isinstance(spec['death'],dict), 'death must stay pending until caller force-stop')
        chooser_nodes(ui_tree(spec['actions']['pending_chooser'],hdc,endpoint,'com.ohos.settings'),req)
        delta=additions(req,snaps['before'],snaps['after'],identities); caller=delta['caller'];uri,_=owned(req,caller)
        require([r['event'] for r in caller]==['begin','incoming','owned','owner_before','share_call','share_opened'] and not delta['target_a'] and not delta['target_b'], 'dead caller received stale callback/target or did not reach pending modal')
        shared_call(req,caller[4],uri); require(success(caller[5],'share_opened','UIAbilityContext.startAbilityByType') is None,'share not opened')
        d=spec['death'];require(set(d)=={'before','stop','absent','gone_chooser'} and len(d['absent'])==len(d['gone_chooser'])==2,'two complete post-death observations required')
        before=process_proof(d['before'],req,hdc,endpoint,identities['caller']);pid=caller[-1]['pid'];birth=before['processes'].get(pid)
        require(birth is not None and birth['uid']==identities['caller']['uid'], 'pending caller PID and kernel birth not observed')
        require(spec['actions']['pending_chooser']['read']['finished_ns'] <= d['before']['command']['started_ns'] <= d['before']['command']['finished_ns'] <= d['stop']['started_ns'], 'caller death not after pending real chooser/birth observation')
        command(d['stop'],'aa force-stop '+ROLES['caller']['bundle'],req,hdc,endpoint)
        last=d['stop']['finished_ns']
        for scan,tree in zip(d['absent'],d['gone_chooser']):
            require(scan['command']['started_ns'] >= last,'post-death snapshots reordered')
            require(not process_proof(scan,req,hdc,endpoint,identities['caller'])['processes'],'caller UID/bundle process remains after force-stop')
            layout=ui_tree(tree,hdc,endpoint)
            from guest_ui import select_node,NodeNotReady
            try: select_node(layout,'com.ohos.settings',identifier='system-share-title')
            except NodeNotReady: pass
            else: raise ValueError('modal chooser remains after original caller death')
            require(scan['command']['finished_ns'] <= tree['dump']['started_ns'],'chooser absence preceded process absence')
            last=tree['read']['finished_ns']
        require(last <= spec['api']['commands'][10]['started_ns'],'final journal capture preceded death checks')
        return {'scope':'actual_pending_modal_caller_death_raw_slice_ONLY','case_id':'death','dead_pid':pid,'dead_start':birth['start'],
            'boot_id':req['boot_id'],'archive_sha256':archive_sha,'ledger_closed':False,'first_artifact_behavior_gate_passed':False}
    require(spec['death'] is None and set(spec['actions'])==({'caller','cleanup'} if req['case_id']=='no-grant-a' else {'caller','chooser','cleanup'}), 'normal case action set differs')
    if req['case_id']!='no-grant-a':
        verify_click(spec['actions']['chooser'],req,hdc,endpoint,'chooser')
        require(spec['actions']['caller']['click']['finished_ns'] <= spec['actions']['chooser']['hierarchy']['dump']['started_ns'] <= spec['actions']['chooser']['click']['finished_ns'] <= spec['actions']['cleanup']['hierarchy']['dump']['started_ns'],'modal/caller cleanup action order differs')
    verify_click(spec['actions']['cleanup'],req,hdc,endpoint,'cleanup')
    require(spec['actions']['cleanup']['click']['finished_ns'] <= spec['api']['commands'][10]['started_ns'],'after snapshot preceded explicit cleanup')
    if req['case_id']=='recovery-a':
        recovery=spec['recovery'];require(isinstance(recovery,dict) and set(recovery)=={'process','death'},'recovery requires exact prior death and current kernel birth')
        prior=decode(checked(recovery['death']).read_text())
        require(prior['api']['request'] != spec['api']['request'] and prior['api']['applications']==spec['api']['applications'],'recovery must use fresh nonce and same installed ordinary roles')
        dead_req=checked(prior['api']['request'])
        dead=verify_case(prior,challenge_path,dead_req,hdc,endpoint,archive_sha)
        require(dead.get('case_id')=='death' and prior['api']['commands'][-1]['finished_ns'] <= spec['api']['commands'][0]['started_ns'],'recovery not after independently verified death')
        current=process_proof(recovery['process'],req,hdc,endpoint,identities['caller'])
        rows=additions(req,snaps['before'],snaps['after'],identities)['caller'];pid=rows[-1]['pid'];birth=current['processes'].get(pid)
        require(birth is not None and (pid,birth['start']) != (dead['dead_pid'],dead['dead_start']) and
            spec['actions']['cleanup']['click']['finished_ns'] <= recovery['process']['command']['started_ns'] <= recovery['process']['command']['finished_ns'] <= spec['api']['commands'][10]['started_ns'], 'recovery reused dead process or lacks current complete kernel birth')
    else: require(spec['recovery'] is None,'unexpected recovery claim')
    result=verify_operation(req,snaps['before'],snaps['after'],identities)
    return {'scope':'actual_modal_Share578_API_URI_UI_raw_slice_ONLY',**result,'boot_id':req['boot_id'],'archive_sha256':archive_sha,
        'signature_cryptography_verified_here':False,'native_owner_release_verified_here':False,'ledger_closed':False,'first_artifact_behavior_gate_passed':False}


if __name__ == '__main__': main()
