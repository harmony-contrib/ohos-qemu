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
          'mainElement': 'EntryAbility', 'deviceTypes': ['default', 'tablet', '2in1'], 'deliveryWithInstall': True,
          'installationFree': False, 'pages': '$profile:main_pages', 'requestPermissions': [],
          'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets',
                         'launchType': 'singleton', 'exported': True, 'label': '$string:app_name',
                         'icon': '$media:app_icon', 'startWindowIcon': '$media:app_icon',
                         'startWindowBackground': '$color:start_window_background', 'skills': [{'entities': ['entity.system.home'],
                         'actions': ['ohos.want.action.home']}]}]}})
    write('entry/src/main/resources/base/element/color.json', {'color': [
          {'name': 'start_window_background', 'value': '#FFFFFF'}]})
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


def provider_uid(ui):
    raw = raw_json(artifact(ui['provider_bms']))
    matches = [row for row in objects(raw) if row.get('bundleName') == CONTRACT['provider_bundle'] and 'isSystemApp' in row]
    require(len(matches) == 1 and matches[0].get('isSystemApp') is True,
            'actual system Contacts provider BMS identity required')
    value = matches[0].get('uid')
    require(type(value) is int and value // 200000 == 100, 'current-user Contacts provider UID required')
    return value


class AmsNotReady(EvidenceError):
    pass


def ams_sessions(dump, contacts_uid, caller_uid):
    """Parse real aa dump records. No ArkUI ID is assumed equal to an AMS ID."""
    require(type(contacts_uid) is int and type(caller_uid) is int and contacts_uid != caller_uid and
            contacts_uid // 200000 == caller_uid // 200000 == 100, 'distinct current-user provider/host UIDs required')
    require(len(re.findall(r'^  ExtensionRecords:$', dump, re.M)) == 1 and
            len(re.findall(r'^  AppRunningRecords:$', dump, re.M)) == 1, 'complete actual AMS extension/process dump required')
    processes = {}
    for block in re.split(r'(?=^    AppRunningRecord ID #)', dump, flags=re.M)[1:]:
        identity = re.findall(r'^      pid #([1-9][0-9]*)  uid #([1-9][0-9]*)$', block, re.M)
        require(len(identity) == 1, 'malformed AMS process identity')
        pid, uid = map(int, identity[0])
        require(pid not in processes, 'duplicate AMS process PID')
        processes[pid] = (uid, block)
    require(processes, 'actual AMS process records missing')
    hosts = [(pid, block) for pid, (uid, block) in processes.items() if uid == caller_uid and
             re.search(r'^      process name \[' + re.escape(BUNDLE) + r'\]$', block, re.M)]
    entries = re.split(r'(?=^    uri \[)', dump, flags=re.M)[1:]
    sessions = {}
    for block in entries:
        block = re.split(r'^  [A-Za-z].*:$', block, flags=re.M)[0]
        if not ('ability type [UIEXTENSION]' in block and
                f'root host bundle name [{BUNDLE}]' in block and
                re.search(r'AbilityRecord ID #[1-9][0-9]*\s+state #(FOREGROUND|ACTIVE)\b', block) and
                'app state #FOREGROUND' in block):
            continue
        # A second live provider for this ordinary host prevents proving which
        # remote tree is Contacts. Do not accept a real Contacts connection plus
        # a different extension containing a fake preview.
        require(f'bundle name [{CONTRACT["provider_bundle"]}]' in block and
                f'main name [{CONTRACT["provider_ability"]}]' in block,
                'foreign live UIExtension for Contacts host')
        uri = re.findall(r'^    uri \[(' + re.escape('/' + CONTRACT['provider_bundle'] + '/entry/' +
                         CONTRACT['provider_ability']) + r'[1-9][0-9]*)\]$', block, re.M)
        record = re.findall(r'AbilityRecord ID #([1-9][0-9]*)\s+state #(?:FOREGROUND|ACTIVE)\b', block)
        pid = re.findall(r'^      pid: ([1-9][0-9]*)$', block, re.M)
        require(len(uri) == len(record) == len(pid) == 1 and
                'root host module name [entry]' in block and 'root host ability name [EntryAbility]' in block,
                'actual Contacts UIExtension URI/record/host ability required')
        provider_pid = int(pid[0])
        if provider_pid not in processes or not hosts:
            raise AmsNotReady('AMS closing session still references a process no longer present')
        require(processes[provider_pid][0] == contacts_uid and
                len(hosts) == 1 and hosts[0][0] != provider_pid, 'AMS provider/host PID and BMS UID mismatch')
        provider = processes[provider_pid][1]
        host_pid, host = hosts[0]
        name = re.escape(CONTRACT['provider_bundle'])
        ability = re.escape(CONTRACT['provider_ability'])
        require(re.search(r'^      process name \[' + name + r'(?::' + ability + r'(?::[1-9][0-9]*)?)?\]$', provider, re.M),
                'wrong Contacts provider process')
        if 'state #FOREGROUND' not in provider:
            continue  # A closing record may remain cached after its process backgrounds.
        if 'state #FOREGROUND' not in host:
            raise AmsNotReady('AMS host is transitioning out of foreground')
        require(re.search(r'^      uiextension provider #[0-9]+\n        pid #' + str(provider_pid) + r'$', host, re.M) and
                re.search(r'^      root caller #[0-9]+\n        pid #' + str(host_pid) + r'$', provider, re.M),
                'reciprocal live AMS provider/host connection required')
        key = uri[0] + '#' + record[0]
        require(key not in sessions, 'duplicate live AMS Contacts session')
        sessions[key] = {'record_id': int(record[0]), 'uri': uri[0], 'provider_pid': provider_pid,
                         'provider_uid': contacts_uid, 'host_pid': host_pid, 'host_uid': caller_uid}
    return sessions


def closed_session(action, contacts_uid, caller_uid):
    before = ams_sessions(artifact(action['ams_before']).read_text(), contacts_uid, caller_uid)
    after = ams_sessions(artifact(action['ams_after']).read_text(), contacts_uid, caller_uid)
    removed = set(before) - set(after)
    require(len(removed) == 1 and set(after) <= set(before), 'one actual AMS Contacts session must close for this input')
    require(all(after[key] == before[key] for key in after), 'other live AMS session changed identity')
    return before[next(iter(removed))]


class PickerNotReady(EvidenceError):
    pass


def picker_view(layout):
    """Unique real controls, with host-owned nodes confined to a remote subtree."""
    roots = layout if isinstance(layout, list) else [layout]
    pending = [(row, '', []) for row in roots]
    rows = []
    while pending:
        node, owner, ancestors = pending.pop()
        require(isinstance(node, dict) and len(rows) < 100000 and len(ancestors) < 256, 'malformed picker hierarchy')
        attrs, children = node.get('attributes'), node.get('children', [])
        require(isinstance(attrs, dict) and isinstance(children, list), 'actual UITest attributes/children required')
        owner = attrs.get('bundleName') or owner
        rows.append((node, owner, ancestors))
        pending.extend((child, owner, ancestors + [node]) for child in children)
    def identified(identifier):
        return [row for row in rows if row[0]['attributes'].get('id') == identifier and
                row[0]['attributes'].get('visible') == 'true']
    counters, dones = identified('selectedText'), identified('doneButton')
    if not counters or not dones: raise PickerNotReady('actual Contacts picker controls not ready')
    require(len(counters) == len(dones) == 1, 'duplicate visible Contacts picker IDs')
    counter, owner, ancestry = counters[0]
    require(owner in (BUNDLE, CONTRACT['provider_bundle']) and dones[0][1] == owner, 'picker controls have mixed/foreign owners')
    if owner == CONTRACT['provider_bundle']:
        return {'owner': owner, 'tree': layout, 'host_owned': False, 'window_id': None, 'extension_id': None}
    extensions = [node for node, bundle, _ in rows if bundle == BUNDLE and
                  node['attributes'].get('type') == 'UIExtensionComponent' and node['attributes'].get('visible') == 'true']
    require(len(extensions) == 1, 'one actual visible host UIExtension subtree required')
    extension = extensions[0]
    require(extension in ancestry and extension in dones[0][2], 'caller preview is outside remote UIExtension subtree')
    window = extension['attributes'].get('hostWindowId', '')
    extension_id = extension['attributes'].get('accessibilityId', '')
    require(re.fullmatch('[1-9][0-9]*', window) and re.fullmatch('[1-9][0-9]*', extension_id),
            'actual host window and UIExtension identity required')
    for row in (counters[0], dones[0]):
        attrs = row[0]['attributes']
        require(attrs.get('hostWindowId') == window and re.fullmatch('[1-9][0-9]*', attrs.get('accessibilityId', '')) and
                int(attrs['accessibilityId']) >= 100000000000 and int(attrs['accessibilityId']) > int(extension_id),
                'picker child window/remote accessibility identity mismatch')
    require(counter['attributes']['accessibilityId'] != dones[0][0]['attributes']['accessibilityId'],
            'picker controls alias the same remote node')
    return {'owner': owner, 'tree': extension, 'host_owned': True, 'window_id': window, 'extension_id': extension_id}


def verify_ui(ui, invocation, policy, raw_journal, terminal, expected, records, caller_uid):
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
    view = picker_view(layout)
    uid = provider_uid(ui)
    binding = closed_session(action, uid, caller_uid)
    start_sessions = ams_sessions(artifact(starts[0]['ams']).read_text(), uid, caller_uid)
    require(not start_sessions, 'Contacts session already existed before caller Start')
    baseline = ams_sessions(artifact(action['ams_before']).read_text(), uid, caller_uid)
    require(binding['host_uid'] == caller_uid and baseline and
            (len(baseline) in (1, 2) if policy == 'two-done' else len(baseline) == 1),
            'actual Contacts provider binding or session count invalid')
    if view['host_owned']:
        post = raw_json(artifact(action['layout_after']))
        require(not any(row.get('type') == 'UIExtensionComponent' and row.get('visible') == 'true' and
                        row.get('accessibilityId') == view['extension_id'] and row.get('hostWindowId') == view['window_id']
                        for row in objects(post)), 'selected host UIExtension session remains visible after input')
    require(not any(row.get('ams_session') == binding for row in ui.setdefault('_verified_sessions', [])),
            'one AMS session was reused for multiple public invocations')
    ui['_verified_sessions'].append({'invocation_id': invocation, 'ams_session': binding})
    if action_kind in {'done', 'cancel'}:
        allowed = {'doneButton'} if action_kind == 'done' else {'close_click_btn', 'Settings_close_btn', 'contactList_contacts_back_arrowBack'}
        require(action.get('node_id') in allowed and action['node_id'] in text_values(view['tree'], 'id'), 'actual terminal UI target missing')
        targets = [row for row in objects(layout) if row.get('id') == action['node_id'] and row.get('visible') == 'true']
        require(len(targets) == 1 and targets[0].get('enabled') == 'true' and targets[0].get('clickable') == 'true',
                'terminal picker ID is not unique, visible and clickable')
        if view['host_owned']:
            require(targets[0].get('hostWindowId') == view['window_id'] and
                    re.fullmatch('[1-9][0-9]*', targets[0].get('accessibilityId', '')) and
                    int(targets[0]['accessibilityId']) >= 100000000000,
                    'terminal control belongs to a different host window or local preview')
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
    try:
        picker_view(after)
    except PickerNotReady:
        pass
    else:
        raise EvidenceError('picker controls still visible after completion')
    require(artifact(absent[0]['screenshot']).read_bytes().startswith((b'\x89PNG\r\n\x1a\n', b'P6\n')),
            'provider disappearance screenshot missing')
    if len(expected) == 205:
        counters = [row for row in objects(view['tree']) if row.get('id') == 'selectedText']
        counts = [pair for row in counters for text in text_values(row, 'text')
                  for pair in re.findall(r'(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)', text)]
        require(counts == [('205', '205')], '205 actual selection count/limit not visible before Done')
    if policy == 'change-selection-then-cancel':
        changes = {(event.get('kind'), event.get('contact_id')) for event in events}
        require(('unselect', records[0]['id']) in changes and ('select', records[3]['id']) in changes,
                'cancel-default did not change selection before cancellation')
        for kind, record in [('unselect', records[0]), ('select', records[3])]:
            change = next(event for event in events if event.get('kind') == kind and event.get('contact_id') == record['id'])
            layout = raw_json(artifact(change['layout']))
            changed = picker_view(layout)
            require(changed['owner'] == view['owner'] and changed['window_id'] == view['window_id'] and
                    changed['extension_id'] == view['extension_id'] and
                    record['name']['fullName'] in text_values(changed['tree'], 'text'),
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
        require(raw.get('api') in {'appManager.getRunningProcessInformation', 'AppMgrClient::GetAllRunningProcesses'},
                'caller process proof is not AppMgr output')
        if raw['api'] == 'AppMgrClient::GetAllRunningProcesses':
            require(raw.get('error_code') == 0, 'native AppMgr process query failed')
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
            verify_ui(ui, invocation, case['ui'], raw_journal, terminal, expected, records, identity['uid'])
            observations.append({'case_id': case['id'], 'invocation_id': invocation, 'terminal_observations': len(terminal)})
        if case['id'] in {'exit-pending', 'reopen'}:
            phase = 'before_exit' if case['id'] == 'exit-pending' else 'after_reopen'
            measured = raw_json(artifact(ui['caller_processes'][phase]))
            pid = next(row['pid'] for row in measured['processes'] if BUNDLE in row.get('bundleNames', []))
            bindings = [row['ams_session'] for row in ui['_verified_sessions'] if row['invocation_id'] in allowed_invocations]
            require(len(bindings) == 1 and bindings[0]['host_pid'] == pid, 'AMS host differs from actual AppMgr caller process')
        if case['id'] == 'dual-session':
            actions = [row for row in ui['events'] if row.get('invocation_id') in allowed_invocations and row.get('kind') == 'done']
            uid = provider_uid(ui)
            require(len(actions) == 2, 'two actual dual-session inputs required')
            first = ams_sessions(artifact(actions[0]['ams_before']).read_text(), uid, identity['uid'])
            middle = ams_sessions(artifact(actions[0]['ams_after']).read_text(), uid, identity['uid'])
            second = ams_sessions(artifact(actions[1]['ams_before']).read_text(), uid, identity['uid'])
            last = ams_sessions(artifact(actions[1]['ams_after']).read_text(), uid, identity['uid'])
            require(len(first) == 2 and len(middle) == 1 and middle == second and not last,
                    'dual AMS session lifecycle is not two to one to zero')
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
