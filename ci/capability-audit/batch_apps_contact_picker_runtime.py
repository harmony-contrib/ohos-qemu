#!/usr/bin/env python3
"""Prepare an ordinary caller HAP project or independently verify root runtime evidence.

Never builds/signs/installs a HAP, starts QEMU, grants permissions, seeds a DB or
drives UI. Those actions and the shared acceptance gate belong to root.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / 'ci/capability-audit/fixtures/batch_apps/contact_picker_runtime'
CONTRACT = json.loads((FIX / 'project-contract.json').read_text())
MATRIX = {case['id']: case for case in json.loads((FIX / 'case-matrix.json').read_text())['cases']}
BUNDLE = CONTRACT['bundle_name']
TERMINAL = {'resolve', 'reject', 'throw', 'callback'}


class EvidenceError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise EvidenceError(reason)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def document(path):
    return json.loads(Path(path).read_text())


def artifact(descriptor):
    require(isinstance(descriptor, dict), 'artifact descriptor missing')
    path = Path(descriptor.get('path', ''))
    require(path.is_absolute() and path.is_file(), 'artifact must be an actual absolute file')
    require(re.fullmatch('[0-9a-f]{64}', descriptor.get('sha256', '')) is not None, 'artifact SHA missing')
    require(sha(path) == descriptor['sha256'], 'artifact hash mismatch: ' + str(path))
    return path


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def text_values(value, key):
    return [item[key] for item in objects(value) if isinstance(item.get(key), str)]


def raw_json(path):
    text = Path(path).read_text()
    # bm dump may prefix its JSON with a human-readable bundle heading.
    start = text.find('{')
    require(start >= 0, 'no JSON in raw system evidence')
    return json.JSONDecoder().raw_decode(text[start:])[0]


def prepare_project(output):
    output = Path(output).resolve()
    require(output != ROOT and ROOT not in output.parents, 'prepare output must be private scratch outside the repository')
    require(not output.exists(), 'prepare output already exists; preserve prior attempts')
    output.mkdir(parents=True)

    def write(relative, value):
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')

    write('AppScope/app.json5', {'app': {'bundleName': BUNDLE, 'vendor': 'Harmony Contrib',
          'versionCode': 1, 'versionName': '1.0.0', 'icon': '$media:app_icon', 'label': '$string:app_name'}})
    write('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'Contacts public caller'}]})
    write('AppScope/resources/base/media/app_icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" rx="12" fill="#245c9c"/><circle cx="32" cy="23" r="10" fill="white"/><path d="M14 54a18 18 0 0 1 36 0" fill="white"/></svg>\n')
    write('build-profile.json5', {'app': {'products': [{'name': 'default', 'compileSdkVersion': '26.0.0',
          'compatibleSdkVersion': '26.0.0', 'targetSdkVersion': '26.0.0', 'runtimeOS': 'OpenHarmony'}]},
          'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    write('oh-package.json5', {'modelVersion': '6.0.0', 'name': 'contact-picker-caller', 'version': '1.0.0',
          'dependencies': {}, 'devDependencies': {}})
    write('hvigor/hvigor-config.json5', {'modelVersion': '6.0.0', 'dependencies': {},
          'execution': {'daemon': False, 'parallel': False}})
    write('hvigorfile.ts', "import { appTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: appTasks, plugins: [] };\n")
    write('entry/hvigorfile.ts', "import { hapTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: hapTasks, plugins: [] };\n")
    write('entry/build-profile.json5', {'apiType': 'stageMode', 'targets': [{'name': 'default'}]})
    write('entry/oh-package.json5', {'name': 'entry', 'version': '1.0.0', 'dependencies': {}})
    write('entry/src/main/module.json5', {'module': {'name': 'entry', 'type': 'entry',
          'mainElement': 'EntryAbility', 'deviceTypes': ['phone', 'tablet', '2in1'], 'deliveryWithInstall': True,
          'installationFree': False, 'pages': '$profile:main_pages', 'requestPermissions': [],
          'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets',
                         'launchType': 'singleton', 'exported': True, 'label': '$string:app_name',
                         'icon': '$media:app_icon', 'skills': [{'entities': ['entity.system.home'],
                         'actions': ['ohos.want.action.home']}]}]}})
    write('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    mapping = {'EntryAbility.ets': 'entry/src/main/ets/entryability/EntryAbility.ets',
               'Index.ets': 'entry/src/main/ets/pages/Index.ets',
               'PickerCases.ets': 'entry/src/main/ets/model/PickerCases.ets',
               'ResultJournal.ets': 'entry/src/main/ets/model/ResultJournal.ets'}
    for name, target in mapping.items():
        write(target, (FIX / name).read_text())
    manifest = {'schema_version': 1, 'kind': 'ordinary unsigned caller source project; no acceptance',
                'bundle_name': BUNDLE, 'requested_permissions': [], 'apl_required_at_signing': 'normal',
                'system_app_required_at_install': False,
                'source_hashes': {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()},
                'fixture_hashes': {p.name: sha(p) for p in sorted(FIX.iterdir()) if p.is_file()},
                'runtime_acceptance': False}
    write('caller-source-manifest.json', manifest)
    return manifest


def verify_identity(identity, build, run_id):
    require(identity.get('run_id') == run_id, 'identity from a different run')
    hap = artifact(build['caller_hap'])
    require(identity.get('hap_sha256') == sha(hap), 'installed caller HAP does not match compiled caller')
    require(sha(artifact(identity['installed_caller_hap'])) == sha(hap), 'actual installed HAP payload differs')
    with zipfile.ZipFile(hap) as archive:
        manifests = [name for name in archive.namelist() if name == 'module.json' or name.endswith('/module.json')]
        require(len(manifests) == 1, 'built caller HAP manifest ambiguous')
        module = json.loads(archive.read(manifests[0]))
        module = module.get('module', module)
        require(module.get('name') == 'entry' and module.get('requestPermissions', []) == [], 'built HAP requests permissions')
        require(module.get('extensionAbilities', []) == [], 'ordinary caller unexpectedly declares an extension')
    bms = raw_json(artifact(identity['bms_dump']))
    apps = [item for item in objects(bms) if item.get('bundleName') == BUNDLE and 'isSystemApp' in item]
    require(len(apps) == 1, 'raw BMS caller application identity missing or ambiguous')
    app = apps[0]
    require(app['isSystemApp'] is False and app.get('appPrivilegeLevel', app.get('apl')) == 'normal',
            'caller is not a normal non-system application')
    token = app.get('accessTokenId')
    require(type(token) is int and token > 0 and type(app.get('uid')) is int and app['uid'] > 10000,
            'raw BMS UID/token missing')
    probe = raw_json(artifact(identity['permission_probe']))
    require(probe.get('api') in {'abilityAccessCtrl.verifyAccessToken', 'abilityAccessCtrl.verifyAccessTokenSync',
                                'AccessTokenKit::VerifyAccessToken'}, 'permission evidence is not an actual access-token API probe')
    require(probe.get('token_id') == token and probe.get('READ_CONTACTS') == -1 and probe.get('WRITE_CONTACTS') == -1,
            'caller token has broad contacts permission or wrong token was probed')
    profile = raw_json(artifact(identity['decoded_profile']))
    info = profile.get('bundle-info', {})
    require(info.get('bundle-name') == BUNDLE and info.get('apl') == 'normal' and
            info.get('app-feature') != 'hos_system_app', 'signed caller profile is not ordinary')
    require(profile.get('acls', {}).get('allowed-acls', []) == [] and
            profile.get('permissions', {}).get('restricted-permissions', []) == [], 'caller profile grants ACL/restricted permissions')
    signature = raw_json(artifact(identity['signature_verification']))
    require(signature.get('exit_code') == 0 and signature.get('hap_sha256') == sha(hap) and
            signature.get('decoded_profile_sha256') == sha(artifact(identity['decoded_profile'])) and
            'verify-app' in signature.get('command', []), 'independent HAP signature verification missing')
    return {'bundle_name': BUNDLE, 'uid': app['uid'], 'access_token_id': token, 'apl': 'normal',
            'is_system_app': False, 'signature_verified_by': signature['command']}


def verify_seed(seed, cleanup, run_id):
    require(seed.get('run_id') == run_id and cleanup.get('run_id') == run_id, 'seed/cleanup run mismatch')
    require(seed.get('create_api') in {'contact.addContact', 'contact.addContacts'} and
            seed.get('read_api') in {'contact.queryContact', 'contact.queryContacts'}, 'seed must use real public CRUD/read-back')
    records = seed.get('contacts', [])
    require(len(records) >= 205, 'full caller suite needs 205 real read-back contacts')
    ids, keys = set(), set()
    for record in records:
        require(type(record.get('id')) is int and record['id'] > 0 and record['id'] not in ids, 'invalid/duplicate seed ID')
        require(isinstance(record.get('key'), str) and record['key'] and record['key'] not in keys, 'invalid/duplicate seed key')
        require(run_id in record.get('name', {}).get('fullName', '') and record.get('phoneNumbers'),
                'seed nonce/name/phone read-back missing')
        ids.add(record['id']); keys.add(record['key'])
    require(cleanup.get('delete_api') == 'contact.deleteContact' and
            cleanup.get('read_api') in {'contact.queryContact', 'contact.queryContacts'}, 'cleanup must use public delete/read-back')
    require(set(cleanup.get('deleted_keys', [])) == keys and cleanup.get('remaining_contacts') == [], 'seed cleanup incomplete')
    created = raw_json(artifact(seed['raw_create']))
    require(created.get('run_id') == run_id and created.get('api') == seed['create_api'] and
            created.get('error') is None and set(created.get('ids', [])) == ids,
            'seed real public creation result does not match read-back IDs')
    removed = raw_json(artifact(cleanup['raw_delete']))
    require(removed.get('run_id') == run_id and removed.get('api') == 'contact.deleteContact' and
            removed.get('error') is None and set(removed.get('keys', [])) == keys,
            'actual public delete capture does not match seed keys')
    artifact(seed['raw_readback'])
    artifact(cleanup['raw_readback'])
    # Require the independently captured raw read-back to match the ledger.
    raw = raw_json(artifact(seed['raw_readback']))
    require(raw.get('run_id') == run_id and raw.get('api') == seed['read_api'] and raw.get('error') is None and
            raw.get('contacts') == records, 'seed ledger differs from actual public read-back capture')
    after = raw_json(artifact(cleanup['raw_readback']))
    require(after.get('run_id') == run_id and after.get('api') == cleanup['read_api'] and
            after.get('error') is None and after.get('contacts') == [], 'actual cleanup read-back is nonempty or failed')
    return records


def verify_ui(ui, invocation, policy, raw_journal, terminal, expected, records):
    events = [event for event in ui.get('events', []) if event.get('invocation_id') == invocation]
    require(events, 'independent UI evidence missing: ' + invocation)
    starts = [event for event in events if event.get('kind') == 'caller_start']
    require(len(starts) == 1, 'actual caller Start input missing or duplicated')
    start_layout = raw_json(artifact(starts[0]['layout']))
    require(BUNDLE in text_values(start_layout, 'bundleName') and
            'contact_case_start' in text_values(start_layout, 'id'), 'ordinary caller Start UI target missing')
    require(artifact(starts[0]['screenshot']).read_bytes().startswith((b'\x89PNG\r\n\x1a\n', b'P6\n')),
            'caller Start screenshot missing')
    actions = [event for event in events if event.get('kind') in {'done', 'cancel', 'force_stop', 'home', 'deadline_wait'}]
    if policy == 'none':
        require(not any(event.get('kind') in {'picker_visible', 'done', 'cancel'} for event in events),
                'parameter/read-permission case unexpectedly opened a picker')
        return
    if policy == 'provider-launch':
        launches = [event for event in events if event.get('kind') == 'provider_launch']
        require(len(launches) == 1, 'invalid filter must reach the real provider')
        text = artifact(launches[0]['raw_log']).read_text()
        require(CONTRACT['provider_bundle'] in text and CONTRACT['provider_ability'] in text, 'provider launch log wrong target')
        return
    require(any(event.get('kind') == 'picker_visible' for event in events), 'real picker visibility missing')
    action_kind = 'cancel' if 'cancel' in policy else 'force_stop' if 'force-stop' in policy and 'after' not in policy else \
        'home' if policy == 'visible-then-home' else 'deadline_wait' if 'deadline' in policy else 'done'
    actions = [event for event in actions if event.get('kind') == action_kind]
    require(len(actions) == 1, 'exactly one terminal UI action required: ' + invocation)
    action = actions[0]
    screenshot = artifact(action['screenshot']).read_bytes()
    require(screenshot.startswith((b'\x89PNG\r\n\x1a\n', b'P6\n')), 'actual screenshot format missing')
    layout = raw_json(artifact(action['layout']))
    require(CONTRACT['provider_bundle'] in text_values(layout, 'bundleName'), 'layout is not the Contacts provider')
    if action_kind in {'done', 'cancel'}:
        allowed = {'doneButton'} if action_kind == 'done' else {'close_click_btn', 'Settings_close_btn', 'contactList_contacts_back_arrowBack'}
        require(action.get('node_id') in allowed and action['node_id'] in text_values(layout, 'id'), 'actual terminal UI target missing')
    before = artifact(action['journal_before']).read_bytes()
    require(raw_journal.startswith(before), 'UI journal-before snapshot is not a prefix of the final journal')
    prefix = [json.loads(line) for line in before.decode().splitlines() if line]
    require(any(row.get('invocation_id') == invocation and row.get('event') == 'begin' for row in prefix),
            'public invocation was not present before UI action')
    require(not any(row.get('invocation_id') == invocation and row.get('event') in TERMINAL for row in prefix),
            'API returned before real UI completion input')
    absent = [event for event in events if event.get('kind') == 'picker_absent']
    require(len(absent) == 1, 'provider disappearance snapshot missing or ambiguous')
    after = raw_json(artifact(absent[0]['layout']))
    require(CONTRACT['provider_bundle'] not in text_values(after, 'bundleName'), 'provider still visible after completion')
    require(artifact(absent[0]['screenshot']).read_bytes().startswith((b'\x89PNG\r\n\x1a\n', b'P6\n')),
            'provider disappearance screenshot missing')
    if len(expected) == 205:
        counters = [node for node in objects(layout) if node.get('id') == 'selectedText']
        require(counters and any('205' in text for node in counters for text in text_values(node, 'text')),
                '205 selection count not visible before Done')
    if policy == 'change-selection-then-cancel':
        changes = {(event.get('kind'), event.get('contact_id')) for event in events}
        require(('unselect', records[0]['id']) in changes and ('select', records[3]['id']) in changes,
                'cancel-default did not change selection before cancellation')
        for kind, record in [('unselect', records[0]), ('select', records[3])]:
            change = next(event for event in events if event.get('kind') == kind and event.get('contact_id') == record['id'])
            layout = raw_json(artifact(change['layout']))
            require(CONTRACT['provider_bundle'] in text_values(layout, 'bundleName') and
                    record['name']['fullName'] in text_values(layout, 'text'),
                    'changed contact is not visible in the independent layout')


def selected_records(case, slot, records):
    offsets = case.get('selected_offsets', [])
    if offsets == 'first205':
        return records[:205]
    return [records[index] for index in offsets[case['slots'].index(slot)]] if offsets else []


def compare_contacts(actual, expected):
    require(isinstance(actual, list) and len(actual) == len(expected), 'missing/partial/non-array returned contacts')
    require(all(isinstance(item, dict) and type(item.get('id')) is int for item in actual), 'malformed returned Contact')
    ids = [item['id'] for item in actual]
    require(len(ids) == len(set(ids)), 'duplicate returned Contact IDs')
    actual_by_id = {item['id']: item for item in actual}
    require(set(actual_by_id) == {item['id'] for item in expected}, 'wrong/default/cross-session returned Contact IDs')
    for seed in expected:
        observed = actual_by_id[seed['id']]
        for key in ['key', 'name', 'phoneNumbers']:
            require(observed.get(key) == seed.get(key), 'returned Contact ' + key + ' differs from independent read-back')


def verify_process_restart(ui):
    captures = ui['caller_processes']
    ids = {}
    for phase in ['before_exit', 'after_exit', 'after_reopen']:
        raw = raw_json(artifact(captures[phase]))
        require(raw.get('api') == 'appManager.getRunningProcessInformation', 'caller process proof is not AppMgr output')
        matches = [process for process in raw.get('processes', []) if BUNDLE in process.get('bundleNames', [])]
        if phase == 'after_exit':
            require(matches == [], 'ordinary caller remained running after force-stop')
        else:
            require(len(matches) == 1 and type(matches[0].get('pid')) is int and matches[0]['pid'] > 0,
                    'caller PID absent/ambiguous')
            ids[phase] = matches[0]['pid']
    require(ids['before_exit'] != ids['after_reopen'], 'reopen reused the old caller process')


def verify_runtime(journal_path, seed_path, cleanup_path, ui_path, identity_path, build_path, only_case=None):
    raw_journal = Path(journal_path).read_bytes()
    rows = [json.loads(line) for line in raw_journal.decode().splitlines() if line]
    require(rows, 'raw caller journal empty')
    run_id = rows[0].get('run_id')
    require(isinstance(run_id, str) and re.fullmatch('[A-Za-z0-9_-]{1,64}', run_id), 'invalid run id')
    require(all(row.get('schema_version') == 1 and row.get('run_id') == run_id for row in rows), 'mixed/stale caller journal')
    require(all(row.get('case_id') in MATRIX for row in rows), 'journal contains an unknown case')
    build, ui = document(build_path), document(ui_path)
    require(build.get('run_id') == run_id and ui.get('run_id') == run_id, 'build/UI run mismatch')
    package = artifact(build['representative_package'])
    require(build.get('architecture') == 'arm64' and build.get('device_profile') == 'phone' and
            build.get('booted_package_sha256') == sha(package), 'representative fresh ARM64 phone boot identity missing')
    require(build.get('boot_session_id') and ui.get('boot_session_id') == build['boot_session_id'], 'UI from a different boot')
    artifact(build['provider_hap'])
    require(build.get('caller_fixture_hashes') == {p.name: sha(p) for p in sorted(FIX.iterdir()) if p.is_file()},
            'runtime HAP source fixture provenance differs')
    source_manifest = raw_json(artifact(build['caller_source_manifest']))
    require(source_manifest.get('fixture_hashes') == build['caller_fixture_hashes'], 'compiled source manifest provenance missing')
    identity = verify_identity(document(identity_path), build, run_id)
    records = verify_seed(document(seed_path), document(cleanup_path), run_id)
    observed_cases = {row['case_id'] for row in rows}
    cases = [MATRIX[only_case]] if only_case is not None else [case for case in MATRIX.values()
                                                              if case['required'] or case['id'] in observed_cases]
    if any(case['id'] in {'exit-pending', 'reopen'} for case in cases):
        verify_process_restart(ui)
    observations = []
    for case in cases:
        case_rows = [row for row in rows if row.get('case_id') == case['id']]
        launches = {row.get('launch_id') for row in case_rows if row.get('event') == 'begin'}
        require(len(launches) == 1, 'case missing or ambiguously rerun: ' + case['id'])
        launch = next(iter(launches))
        require(isinstance(launch, str) and re.fullmatch('[A-Za-z0-9_-]{1,64}', launch), 'invalid launch identity')
        allowed_invocations = {launch + '/' + slot for slot in case['slots']}
        require(all(row.get('invocation_id') in allowed_invocations for row in case_rows
                    if row.get('event') in TERMINAL | {'begin', 'return', 'observer_watchdog'}),
                'extra or cross-session invocation in raw caller results')
        if case['id'] == 'dual-session':
            starts = [index for index, row in enumerate(case_rows) if row.get('event') == 'begin']
            ends = [index for index, row in enumerate(case_rows) if row.get('event') in TERMINAL]
            require(len(starts) == 2 and ends and max(starts) < min(ends), 'dual requests were not actually overlapping')
        for slot in case['slots']:
            invocation = launch + '/' + slot
            calls = [row for row in case_rows if row.get('invocation_id') == invocation]
            require(sum(row.get('event') == 'begin' for row in calls) == 1, 'duplicate/missing public invocation')
            require(not any(row.get('event') == 'observer_watchdog' for row in calls), 'public API failed to return before observer watchdog')
            terminal = [row for row in calls if row.get('event') in TERMINAL]
            expected = selected_records(case, slot, records)
            if case.get('no_terminal_expected'):
                require(len(terminal) <= 1 and all(row.get('event') in {'reject', 'throw'} and row.get('error_type') == 'object'
                                                and row.get('error_code') == 16700001 and row.get('raw_json') == 'undefined'
                                                for row in terminal), 'exiting caller received success or repeated terminal result')
            else:
                require(len(terminal) == 1, 'missing or repeated public terminal result: ' + invocation)
                result = terminal[0]
                begin = next(row for row in calls if row.get('event') == 'begin')
                elapsed = result.get('timestamp_ms', 0) - begin.get('timestamp_ms', 0)
                require(type(elapsed) is int and elapsed >= 0, 'public result clock/order invalid')
                if case['id'] == 'deadline':
                    require(600000 <= elapsed < 660000, 'native deadline was not actually exercised')
                callbacks = sum(row.get('event') == 'callback' for row in terminal)
                require(all(row.get('callback_count') == (1 if row.get('event') == 'callback' else 0) for row in terminal),
                        'callback count invalid')
                callback_api = 'callback' in case['api'] and (case['id'] != 'dual-session' or slot == 'b')
                returns = [row for row in calls if row.get('event') == 'return']
                if case.get('error_kind') != 'throw':
                    require(len(returns) == 1, 'public return observation missing')
                    require(returns[0].get('raw_json') == ('undefined' if callback_api else 'Promise'), 'callback returned a Promise or Promise API returned undefined')
                if 'error_code' in case:
                    kind = case['error_kind']
                    allowed = {'reject', 'throw'} if kind == 'reject-or-throw' else {kind}
                    require(result.get('event') in allowed and result.get('error_type') == 'object' and
                            result.get('error_code') == case['error_code'] and result.get('raw_json') == 'undefined',
                            'failure is missing/wrong/bare-number BusinessError')
                else:
                    require(result.get('event') == ('callback' if callback_api else 'resolve') and
                            result.get('error_type') == 'undefined', 'selection did not successfully return through its public overload')
                    require(result.get('value_type') == 'object', 'success returned undefined/nonobject')
                    compare_contacts(json.loads(result.get('raw_json', 'null')), expected)
                    require(callbacks == (1 if callback_api else 0), 'public overload result channel mismatch')
            verify_ui(ui, invocation, case['ui'], raw_journal, terminal, expected, records)
            observations.append({'case_id': case['id'], 'invocation_id': invocation, 'terminal_observations': len(terminal)})
    return {'schema_version': 1, 'raw_results_verified': True, 'run_id': run_id, 'identity': identity,
            'scope': 'one_case_only' if only_case else 'required_caller_matrix', 'observations': observations,
            'ledger_closed': False, 'first_artifact_behavior_gate_passed': False,
            'parent_gate_required': 'Root must integrate these raw observations with the full fresh-package suite and optional boundary tests.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--output-dir', type=Path, required=True)
    verify = commands.add_parser('verify')
    for name in ['journal', 'seed', 'cleanup', 'ui', 'identity', 'build', 'output']:
        verify.add_argument('--' + name, type=Path, required=True)
    verify.add_argument('--case', choices=sorted(MATRIX))
    args = parser.parse_args()
    if args.command == 'prepare':
        manifest = prepare_project(args.output_dir)
        print(json.dumps({'project': str(args.output_dir.resolve()), 'source_files': len(manifest['source_hashes']),
                          'signed': False, 'runtime_acceptance': False}))
        return
    try:
        result = verify_runtime(args.journal, args.seed, args.cleanup, args.ui, args.identity, args.build, args.case)
    except (EvidenceError, OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile) as error:
        args.output.write_text(json.dumps({'raw_results_verified': False, 'error': str(error),
                                          'ledger_closed': False, 'first_artifact_behavior_gate_passed': False}, indent=2) + '\n')
        raise SystemExit(str(error))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'raw_results_verified': True, 'scope': result['scope'], 'ledger_closed': False}))


if __name__ == '__main__':
    main()
