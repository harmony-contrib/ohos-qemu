#!/usr/bin/env python3
"""Exercise installed ordinary Contacts apps in the suite-owned acceptance guest.

No boot/build/sign/install/grant/DB commands. Public CRUD happens in the independent
system_basic seed HAP after UITest clicks the actual permission dialog. Root supplies
signed artifacts and a product-built read-only AppMgr/AccessToken observer.
"""
import argparse
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import subprocess
import sys
import time
import zipfile

from enclosing_acceptance_guest import EnclosingAcceptanceGuest
from run_root_probe import validate_elf
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady, bounds, select_node
import batch_apps_contact_picker_runtime as verifier

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(__file__).with_name('fixtures') / 'batch_apps/contact_picker_seed'
SEED = 'com.ohos.qemu.contactpickerseed'
CALLER = verifier.BUNDLE
PROVIDER = verifier.CONTRACT['provider_bundle']
PERMISSIONS = ['ohos.permission.READ_CONTACTS', 'ohos.permission.WRITE_CONTACTS']


def descriptor(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': verifier.sha(path)}


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return descriptor(path)


def prepare_seed(output):
    output = Path(output).resolve()
    verifier.require(output != ROOT and ROOT not in output.parents and not output.exists(),
                     'new private seed project outside repository required')
    output.mkdir(parents=True)
    def write(name, value):
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')
    write('AppScope/app.json5', {'app': {'bundleName': SEED, 'vendor': 'Harmony Contrib',
          'versionCode': 1, 'versionName': '1.0.0', 'icon': '$media:app_icon', 'label': '$string:app_name'}})
    write('AppScope/resources/base/media/app_icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#276238"/></svg>\n')
    write('AppScope/resources/base/element/string.json', {'string': [
        {'name': 'app_name', 'value': 'Contacts public CRUD seed'},
        {'name': 'contacts_reason', 'value': 'Create, read and remove temporary Contacts test records with your permission'}]})
    write('build-profile.json5', {'app': {'products': [{'name': 'default', 'compileSdkVersion': '26.0.0',
          'compatibleSdkVersion': '26.0.0', 'targetSdkVersion': '26.0.0', 'runtimeOS': 'OpenHarmony'}]},
          'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    write('oh-package.json5', {'modelVersion': '6.0.0', 'name': 'contact-picker-seed', 'version': '1.0.0',
          'dependencies': {}, 'devDependencies': {}})
    write('hvigor/hvigor-config.json5', {'modelVersion': '6.0.0', 'dependencies': {},
          'execution': {'daemon': False, 'parallel': False}})
    write('hvigorfile.ts', "import { appTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: appTasks, plugins: [] };\n")
    write('entry/hvigorfile.ts', "import { hapTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: hapTasks, plugins: [] };\n")
    write('entry/build-profile.json5', {'apiType': 'stageMode', 'targets': [{'name': 'default'}]})
    write('entry/oh-package.json5', {'name': 'entry', 'version': '1.0.0', 'dependencies': {}})
    write('entry/src/main/module.json5', {'module': {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility',
          'deviceTypes': ['default', 'tablet', '2in1'], 'deliveryWithInstall': True, 'installationFree': False,
          'pages': '$profile:main_pages', 'requestPermissions': [{'name': permission, 'reason': '$string:contacts_reason',
          'usedScene': {'abilities': ['EntryAbility'], 'when': 'inuse'}} for permission in PERMISSIONS],
          'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets', 'launchType': 'singleton',
          'exported': True, 'label': '$string:app_name', 'icon': '$media:app_icon', 'startWindowIcon': '$media:app_icon',
          'startWindowBackground': '$color:start_window_background',
          'skills': [{'entities': ['entity.system.home'], 'actions': ['ohos.want.action.home']}]}]}})
    write('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'start_window_background', 'value': '#FFFFFF'}]})
    write('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    for source, target in [('EntryAbility.ets', 'entryability/EntryAbility.ets'), ('Index.ets', 'pages/Index.ets'),
                           ('SeedStore.ets', 'model/SeedStore.ets')]:
        write('entry/src/main/ets/' + target, (FIX / source).read_text())
    manifest = {'schema_version': 1, 'bundle_name': SEED, 'requested_permissions': PERMISSIONS,
                'apl_required_at_signing': 'system_basic', 'system_app_required_at_install': True,
                'fixture_hashes': {p.name: verifier.sha(p) for p in sorted(FIX.iterdir()) if p.is_file()},
                'source_hashes': {str(p.relative_to(output)): verifier.sha(p) for p in sorted(output.rglob('*')) if p.is_file()},
                'signed': False, 'runtime_acceptance': False}
    write('seed-source-manifest.json', manifest)
    return manifest


def application_info(text, bundle):
    start = text.find('{')
    verifier.require(start >= 0, 'actual BMS JSON missing')
    raw = json.loads(text[start:])
    apps = [item for item in verifier.objects(raw) if item.get('bundleName') == bundle and 'isSystemApp' in item]
    verifier.require(len(apps) == 1, 'BMS app identity missing or ambiguous')
    app = apps[0]
    verifier.require(bundle in (CALLER, SEED), 'only exact caller/seed audit identities allowed')
    system_seed = bundle == SEED
    verifier.require(app['isSystemApp'] is system_seed and
        app.get('appPrivilegeLevel', app.get('apl')) == ('system_basic' if system_seed else 'normal') and
        type(app.get('uid')) is int and app['uid'] // 200000 == 100 and type(app.get('accessTokenId')) is int and
        0 < app['accessTokenId'] < 2**32, 'exact caller-normal/seed-system_basic BMS UID/token required')
    return app


def parse_journal(text, run_id):
    verifier.require(not text or text.endswith('\n'), 'incomplete journal frame')
    rows = [json.loads(line) for line in text.splitlines() if line]
    verifier.require(all(row.get('schema_version') == 1 and row.get('run_id') == run_id for row in rows),
                     'foreign or malformed raw journal')
    return rows


def operation_rows(rows, operation_id):
    own = [row for row in rows if row.get('operation_id') == operation_id]
    if not any(row.get('event') == 'complete' for row in own):
        return None
    verifier.require(sum(row.get('event') == 'begin' for row in own) == 1 and
                     sum(row.get('event') == 'complete' for row in own) == 1, 'duplicate seed operation')
    errors = [row for row in own if row.get('event') == 'error']
    verifier.require(not errors, 'public seed operation failed: ' + json.dumps(errors))
    return own


def seed_receipt(rows, run_id, mode, output, journal):
    """Derive the frozen verifier envelope solely from preserved public API rows."""
    reads = [row for row in rows if row.get('event') == 'readback' and row.get('api') == 'contact.queryContacts']
    verifier.require(len(reads) == 1, 'one actual public readback required')
    contacts = json.loads(reads[0]['raw_json'])
    verifier.require(isinstance(contacts, list), 'public readback is not an array')
    read_art = write_json(output / (mode + '-raw-readback.json'), {'run_id': run_id, 'api': 'contact.queryContacts',
        'contacts': contacts, 'raw_journal': descriptor(journal), 'operation_id': reads[0]['operation_id']})
    result = {'run_id': run_id, 'read_api': 'contact.queryContacts', 'raw_readback': read_art}
    if mode == 'create':
        added = [json.loads(row['raw_json']) for row in rows if row.get('event') == 'created' and row.get('api') == 'contact.addContact']
        verifier.require(len(added) == 205 and len(set(added)) == 205 and len(contacts) == 205,
                         '205 independent add/read results required')
        by_id = {record['id']: record for record in contacts}
        verifier.require(set(by_id) == set(added), 'created IDs differ from public readback')
        # Preserve the public readback order in both envelope and raw_readback.
        result.update(create_api='contact.addContact', contacts=contacts,
            raw_create=write_json(output / 'create-raw-add.json', {'run_id': run_id, 'api': 'contact.addContact',
                'ids': added, 'raw_journal': descriptor(journal), 'operation_id': reads[0]['operation_id']}))
        queries = [json.loads(row['raw_json']) for row in rows if row.get('event') == 'query_after']
        verifier.require(len(queries) == 1 and len(queries[0]) == 205,
                         'select-all205 requires a guest with exactly the 205 public seed records')
    else:
        removed = [json.loads(row['raw_json']) for row in rows if row.get('event') == 'deleted' and row.get('api') == 'contact.deleteContact']
        result.update(delete_api='contact.deleteContact', deleted_keys=removed, remaining_contacts=contacts,
            raw_delete=write_json(output / 'cleanup-raw-delete.json', {'run_id': run_id, 'api': 'contact.deleteContact',
                'keys': removed, 'raw_journal': descriptor(journal), 'operation_id': reads[0]['operation_id']}))
    return result


def walk(layout):
    roots = layout if isinstance(layout, list) else [layout]
    pending = [(node, '', []) for node in roots]
    count = 0
    while pending:
        node, inherited, ancestors = pending.pop()
        count += 1
        verifier.require(count <= 100000 and len(ancestors) <= 256 and isinstance(node, dict), 'invalid UITest tree')
        attrs, children = node.get('attributes'), node.get('children', [])
        verifier.require(isinstance(attrs, dict) and isinstance(children, list), 'invalid UITest hierarchy')
        bundle = attrs.get('bundleName') or inherited
        yield node, bundle, ancestors
        pending.extend((child, bundle, ancestors + [node]) for child in children)


def clickable_for_text(layout, bundle, text):
    matches = [(node, ancestors) for node, actual, ancestors in walk(layout)
               if actual == bundle and node['attributes'].get('text') == text and node['attributes'].get('visible') == 'true']
    if not matches:
        raise NodeNotReady('contact name not in actual visible UITest tree')
    verifier.require(len(matches) == 1, 'duplicate visible contact name')
    node, ancestors = matches[0]
    for target in [node, *reversed(ancestors)]:
        attrs = target['attributes']
        if attrs.get('enabled') == 'true' and attrs.get('clickable') == 'true' and attrs.get('visible') == 'true':
            return {'attributes': attrs, 'rect': list(bounds(attrs.get('bounds'))), 'bundle': bundle}
    raise ValueError('actual contact row has no enabled clickable ancestor')


def scoped_layout(view):
    tree = view['tree']
    return {'attributes': {'bundleName': view['owner']}, 'children': tree if isinstance(tree, list) else [tree]}


def selected_count(layout):
    view = verifier.picker_view(layout)
    layout = scoped_layout(view)
    owner = view['owner']
    nodes = [node for node, bundle, _ in walk(layout) if bundle == owner and
             node['attributes'].get('id') == 'selectedText' and node['attributes'].get('visible') == 'true']
    if not nodes:
        raise NodeNotReady('visible Contacts selection counter missing')
    verifier.require(len(nodes) == 1, 'multiple visible picker counters; session ambiguous')
    text = ' '.join(value for node in verifier.objects(nodes[0]) if isinstance(node.get('text'), str) for value in [node['text']])
    ratios = re.findall(r'(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)', text)
    verifier.require(len(ratios) == 1, 'ambiguous actual selection count/limit: ' + text)
    count, limit = map(int, ratios[0])
    verifier.require(0 <= count <= limit <= 10000, 'invalid actual selection count/limit')
    return count


def fresh_lines(before, after):
    """Keep only actual newly observed hilog lines; never manufacture launch text."""
    old = Counter(before.splitlines())
    new = []
    for line in after.splitlines():
        if old[line]: old[line] -= 1
        else: new.append(line)
    return '\n'.join(new) + '\n'


class Driver:
    def __init__(self, guest, ui, output, run_id, observer, *, permission_bundle='com.ohos.permissionmanager',
                 allow_texts=('允许', 'Allow'), clock=time.monotonic, sleep=time.sleep):
        self.guest, self.ui, self.output = guest, ui, Path(output)
        self.run_id, self.observer = run_id, observer
        self.permission_bundle, self.allow_texts = permission_bundle, tuple(allow_texts)
        self.clock, self.sleep = clock, sleep
        self.evidence = {'run_id': run_id, 'boot_session_id': guest.env['boot_id'], 'events': [], 'caller_processes': {}}
        self.last_journal = ''
        self.permission_bms_bindings = []
        self.serial = 0
        self.caller_uid = None
        self.provider_bms = None

    def label(self, stem):
        self.serial += 1
        return str(self.serial).zfill(4) + '-' + stem

    def raw(self, script, stem):
        label = self.label(stem)
        text = self.guest.shell(script, label)
        path = self.output / (label + '.log')
        path.write_text(text)
        return text, descriptor(path)

    def event(self, kind, invocation, **data):
        row = {'kind': kind, 'invocation_id': invocation, **data}
        self.evidence['events'].append(row)
        return row

    def wait(self, action, seconds=60):
        deadline = self.clock() + seconds
        last = ''
        while self.clock() < deadline:
            try:
                result = action()
                if result is not None and result is not False: return result
            except (LayoutNotReady, NodeNotReady, verifier.PickerNotReady, verifier.AmsNotReady) as error:
                last = str(error)
            self.sleep(0.3)
        raise ValueError('bounded runtime wait expired: ' + last)

    def layout(self, stem):
        return self.ui.layout(label=self.label(stem))

    def screen(self, stem):
        return descriptor(self.ui.screenshot(label=self.label(stem)))

    def failure_diagnostics(self, stem):
        """Read-only failure observations; never substitute a journal or pass."""
        result = {'scope': 'same_boot_failure_UI_ONLY_NOT_runtime_or_cleanup_proof', 'errors': []}
        try:
            raw, result['boot_before'] = self.raw('cat /proc/sys/kernel/random/boot_id', stem + '-boot-before')
            verifier.require(raw.strip() == self.guest.env['boot_id'], 'failure capture left enclosing boot')
        except Exception as error:
            result['errors'].append({'observation': 'boot_before', 'error': str(error)})
            return result
        # A failed hierarchy dump must not prevent a real PNG from showing an
        # application error such as a missing staged file or journal exception.
        for name, capture in [
                ('layout', lambda: descriptor(self.layout(stem + '-layout')[1])),
                ('screenshot', lambda: self.screen(stem + '-pixels')),
                ('ams', lambda: self.raw('aa dump -a -u 100', stem + '-AMS')[1]),
                ('hilog', lambda: self.raw('hilog -x', stem + '-hilog')[1])]:
            try:
                result[name] = capture()
            except Exception as error:
                result['errors'].append({'observation': name, 'error': str(error)})
        try:
            raw, result['boot_after'] = self.raw('cat /proc/sys/kernel/random/boot_id', stem + '-boot-after')
            verifier.require(raw.strip() == self.guest.env['boot_id'], 'failure capture guest rebooted')
            result['same_boot_verified'] = True
        except Exception as error:
            result['errors'].append({'observation': 'boot_after', 'error': str(error)})
        return result

    def launch(self, bundle, **parameters):
        argv = ['aa', 'start', '-b', bundle, '-a', 'EntryAbility']
        for name, value in parameters.items(): argv.extend(['--ps', name, str(value)])
        return self.raw(shlex.join(argv), 'launch-' + ('seed' if bundle == SEED else 'caller'))

    def journal(self, bundle, stem):
        name = ('contact-seed-' if bundle == SEED else 'contact-picker-') + self.run_id + '.jsonl'
        remote = '/data/app/el2/100/base/' + bundle + '/files/' + name
        text, art = self.raw('if test -f ' + shlex.quote(remote) + '; then cat ' + shlex.quote(remote) + '; fi', stem)
        rows = parse_journal(text, self.run_id)
        if bundle == CALLER:
            verifier.require(text.startswith(self.last_journal), 'caller journal was replaced or truncated')
            self.last_journal = text
        return rows, art

    def snapshot(self, stem, predicate=lambda layout: True):
        def capture():
            layout, path = self.layout(stem)
            return (layout, path) if predicate(layout) else None
        layout, path = self.wait(capture)
        return {'layout': descriptor(path), 'screenshot': self.screen(stem)}

    def actual_click(self, node, stem):
        x, y, w, h = node['rect']
        self.ui.shell('uitest uiInput click ' + str(x + w // 2) + ' ' + str(y + h // 2), self.label(stem))

    def node_click(self, bundle, *, identifier=None, text=None, stem='click'):
        def click():
            layout, path = self.layout(stem)
            node = select_node(layout, bundle, identifier=identifier, text=text, clickable=True)
            evidence = {'layout': descriptor(path), 'screenshot': self.screen(stem), 'selected_node': node}
            self.actual_click(node, stem)
            return evidence
        return self.wait(click)

    def request_click(self, bundle, status_id, expected, button_id, stem):
        """Recheck the current nonce and enabled button in the SAME input tree."""
        def click():
            layout, path = self.layout(stem)
            status = select_node(layout, bundle, identifier=status_id)['attributes'].get('text', '')
            if status.startswith(('Launch rejected:', 'Operation failed:')):
                raise ValueError('actual app rejected the current request: ' + status)
            if status != expected:
                return None
            button = select_node(layout, bundle, identifier=button_id, clickable=True)
            evidence = {'layout': descriptor(path), 'screenshot': self.screen(stem),
                        'selected_node': button, 'ready_identity': expected, 'ready_status_id': status_id}
            self.actual_click(button, stem)
            return evidence
        return self.wait(click)

    def permissions(self, bundle, token, stem):
        before_raw, before = self.raw('bm dump -n ' + bundle, stem + '-BMS-before')
        app = application_info(before_raw, bundle)
        verifier.require(type(token) is int and token == app['accessTokenId'], 'observer token must come from current BMS')
        raw, art = self.raw(shlex.join([self.observer, 'permissions', bundle, str(token)]), stem)
        value = json.loads(raw)
        verifier.require(value.get('api') == 'AccessTokenKit::VerifyAccessToken' and
                         type(value.get('token_id')) is int and value['token_id'] == token and value.get('bundle_name') == bundle and
                         all(type(value.get(k)) is int and value[k] in (-1, 0) for k in ('READ_CONTACTS', 'WRITE_CONTACTS')),
                         'observer token/API/grant mismatch')
        after_raw, after = self.raw('bm dump -n ' + bundle, stem + '-BMS-after')
        again = application_info(after_raw, bundle)
        verifier.require(all(again[k] == app[k] for k in ('uid', 'accessTokenId')), 'BMS UID/token changed around observer query')
        self.permission_bms_bindings.append({'bundle': bundle, 'token': art, 'before': before, 'after': after})
        return value, art

    def processes(self, phase, expect):
        def capture():
            text, art = self.raw(shlex.join([self.observer, 'processes', CALLER]), 'process-' + phase)
            data = json.loads(text)
            verifier.require(data.get('api') == 'AppMgrClient::GetAllRunningProcesses' and data.get('error_code') == 0,
                             'real AppMgr observer failed')
            matches = [p for p in data['processes'] if CALLER in p.get('bundleNames', [])]
            if len(matches) != expect: return None
            self.evidence['caller_processes'][phase] = art
            return data
        return self.wait(capture, 30)

    def seed_operation(self, mode):
        operation = mode + '_' + secrets.token_hex(8)
        # Cancel any previous JS operation before recovery; its partial public
        # records are recovered by the next public query, never by DB writes.
        self.raw('aa force-stop ' + SEED, 'stop-seed-before-' + mode)
        self.launch(SEED, runId=self.run_id, operationId=operation, mode=mode)
        clicked = self.request_click(SEED, 'contact_seed_status',
            'Ready: ' + self.run_id + '/' + operation + '/' + mode, 'contact_seed_start', 'seed-start-' + mode)
        self.evidence.setdefault('seed_launch_inputs', []).append({'operation_id': operation, 'mode': mode, **clicked})
        def complete():
            rows, art = self.journal(SEED, 'seed-journal-' + mode)
            own = operation_rows(rows, operation)
            if own is not None: return own, art
            try:
                layout, path = self.layout('normal-permission-dialog')
                matches = []
                for text in self.allow_texts:
                    try:
                        matches.append(clickable_for_text(layout, self.permission_bundle, text))
                    except NodeNotReady:
                        pass
                verifier.require(len(matches) <= 1, 'ambiguous user permission Allow controls')
                if matches:
                    self.evidence.setdefault('seed_user_permission_inputs', []).append({
                        'layout': descriptor(path), 'screenshot': self.screen('normal-permission-dialog'),
                        'selected_node': matches[0]})
                    self.actual_click(matches[0], 'user-allow-contacts')
            except LayoutNotReady:
                pass
            return None
        own, journal = self.wait(complete, 900)
        return seed_receipt(own, self.run_id, mode, self.output, Path(journal['path']))

    def caller_ready(self, case_id, launch_id, seed):
        self.launch(CALLER, runId=self.run_id, launchId=launch_id, caseId=case_id,
                    seedIds=json.dumps([r['id'] for r in seed['contacts']], separators=(',', ':')),
                    queryKey=seed['contacts'][0]['key'])
        if case_id == 'reopen': self.processes('after_reopen', 1)
        _, start_ams = self.raw('aa dump -a -u 100', 'AMS-before-caller-Start')
        clicked = self.request_click(CALLER, 'contact_case_status',
            'Ready: ' + self.run_id + '/' + launch_id + '/' + case_id, 'contact_case_start', 'caller-start-' + case_id)
        for slot in verifier.MATRIX[case_id]['slots']:
            self.event('caller_start', launch_id + '/' + slot, ams=start_ams, **clicked)

    def wait_terminals(self, invocations, seconds=90):
        def complete():
            rows, _ = self.journal(CALLER, 'caller-observe')
            return rows if all(any(row.get('invocation_id') == inv and row.get('event') in verifier.TERMINAL
                                          for row in rows) for inv in invocations) else None
        return self.wait(complete, seconds)

    def wait_count(self, count):
        def ready():
            layout, path = self.layout('picker-count-' + str(count))
            return (layout, path) if selected_count(layout) == count else None
        return self.wait(ready)

    def contact_click(self, record, kind, invocation):
        def visible():
            layout, path = self.layout('contact-' + kind)
            try:
                view = verifier.picker_view(layout)
                scoped = scoped_layout(view)
                node = clickable_for_text(scoped, view['owner'], record['name']['fullName'])
            except NodeNotReady:
                # Scroll only inside the actual provider's single visible List.
                lists = [n['attributes'] for n, b, _ in walk(scoped) if b == view['owner'] and
                         n['attributes'].get('scrollable') == 'true' and n['attributes'].get('visible') == 'true']
                if not lists: return None  # Provider can still be loading its public query.
                verifier.require(len(lists) == 1, 'contact is off-screen without one actual scrollable list')
                x, y, w, h = bounds(lists[0].get('bounds'))
                self.ui.shell('uitest uiInput swipe ' + ' '.join(map(str,
                    [x + w // 2, y + h * 3 // 4, x + w // 2, y + h // 4, 400])), self.label('scroll-actual-contact-list'))
                return None
            self.event(kind, invocation, contact_id=record['id'], layout=descriptor(path),
                       screenshot=self.screen('contact-' + kind), selected_node=node)
            self.live_ams()
            self.actual_click(node, 'contact-' + kind)
            return True
        return self.wait(visible, 60)

    def terminal_input(self, invocation, kind):
        def pending_snapshot():
            rows, art = self.journal(CALLER, 'journal-before-' + kind)
            own = [row for row in rows if row.get('invocation_id') == invocation]
            verifier.require(any(row.get('event') == 'begin' for row in own) and
                             not any(row.get('event') in verifier.TERMINAL for row in own),
                             'public invocation is not pending immediately before real input')
            return art
        if kind in ('done', 'cancel'):
            identifiers = ['doneButton'] if kind == 'done' else ['close_click_btn', 'Settings_close_btn', 'contactList_contacts_back_arrowBack']
            def action():
                layout, path = self.layout('picker-' + kind)
                view = verifier.picker_view(layout)
                matches = []
                for identifier in identifiers:
                    try:
                        matches.append((identifier, select_node(scoped_layout(view), view['owner'], identifier=identifier, clickable=True)))
                    except NodeNotReady:
                        pass
                if not matches: return None
                verifier.require(len(matches) == 1, 'ambiguous terminal picker controls')
                identifier, node = matches[0]
                screenshot = self.screen('picker-' + kind)
                before = pending_snapshot()
                ams = self.live_ams()
                row = self.event(kind, invocation, node_id=identifier, layout=descriptor(path), ams_before=ams,
                                 screenshot=screenshot, journal_before=before, selected_node=node)
                self.actual_click(node, 'picker-' + kind)
                return row
            return self.wait(action)
        else:
            snap = self.snapshot('picker-before-' + kind, self.has_picker)
            before = pending_snapshot()
            ams = self.live_ams()
            row = self.event(kind, invocation, journal_before=before, ams_before=ams, **snap)
            if kind == 'force_stop': self.raw('aa force-stop ' + CALLER, 'force-stop-owned-caller')
            elif kind == 'home': self.ui.shell('uitest uiInput keyEvent Home', self.label('actual-home'))
            return row

    @staticmethod
    def has_picker(layout):
        try: verifier.picker_view(layout)
        except verifier.PickerNotReady: return False
        return True

    def live_ams(self):
        raw, proof = self.raw('aa dump -a -u 100', 'bound-live-provider-AMS')
        verifier.require(verifier.ams_sessions(raw, self.provider_bms, self.caller_uid),
                         'actual live Contacts provider must exist before picker input')
        return proof

    def picker_click(self, identifier, stem):
        def click():
            layout, path = self.layout(stem)
            view = verifier.picker_view(layout)
            node = select_node(scoped_layout(view),
                               view['owner'], identifier=identifier, clickable=True)
            self.live_ams()
            self.actual_click(node, stem)
            return True
        return self.wait(click)

    def session_closed(self, action):
        before = verifier.ams_sessions(Path(action['ams_before']['path']).read_text(), self.provider_bms, self.caller_uid)
        def closed():
            text, proof = self.raw('aa dump -a -u 100', 'AMS-after-input')
            after = verifier.ams_sessions(text, self.provider_bms, self.caller_uid)
            if len(set(before) - set(after)) != 1 or not set(after) <= set(before): return None
            layout, path = self.layout('immediate-after-input')
            old_view = verifier.picker_view(json.loads(Path(action['layout']['path']).read_text()))
            if old_view['host_owned'] and any(row.get('type') == 'UIExtensionComponent' and
                    row.get('visible') == 'true' and row.get('accessibilityId') == old_view['extension_id'] and
                    row.get('hostWindowId') == old_view['window_id'] for row in verifier.objects(layout)):
                return None
            action['ams_after'] = proof
            action['layout_after'] = descriptor(path)
            verifier.closed_session(action, self.provider_bms, self.caller_uid)
            return True
        self.wait(closed)

    def absent(self, invocations):
        snap = self.snapshot('picker-absent', lambda layout: not self.has_picker(layout) and PROVIDER not in verifier.text_values(layout, 'bundleName'))
        for invocation in invocations: self.event('picker_absent', invocation, **snap)

    def case(self, case_id, seed):
        case = verifier.MATRIX[case_id]
        launch = case_id.replace('-', '_') + '_' + secrets.token_hex(5)
        invocations = [launch + '/' + slot for slot in case['slots']]
        before_hilog = self.raw('hilog -x', 'hilog-before-' + case_id)[0] if case['ui'] == 'provider-launch' else ''
        self.caller_ready(case_id, launch, seed)
        if case['ui'] in ('none', 'provider-launch'):
            self.wait_terminals(invocations)
            if case['ui'] == 'provider-launch':
                def launch_proof():
                    after = self.raw('hilog -x', 'hilog-after-' + case_id)[0]
                    fresh = fresh_lines(before_hilog, after)
                    if PROVIDER not in fresh or verifier.CONTRACT['provider_ability'] not in fresh: return None
                    path = self.output / (self.label('new-provider-launch') + '.log')
                    path.write_text(fresh)
                    return descriptor(path)
                self.event('provider_launch', invocations[0], raw_log=self.wait(launch_proof, 30))
            self.snapshot('no-provider-after-' + case_id, lambda layout: not self.has_picker(layout) and PROVIDER not in verifier.text_values(layout, 'bundleName'))
            return
        self.snapshot('picker-visible', self.has_picker)
        _, ams = self.raw('aa dump -a -u 100', 'actual-provider-AMS-' + case_id)
        for invocation in invocations:
            self.event('picker_visible', invocation)
            self.event('provider_ams', invocation, raw_log=ams)
        records = seed['contacts']
        if case_id == 'dual-session':
            # Both begins must predate either terminal. Use the real visible count
            # to identify the session, never returned data or a guessed stack order.
            rows, _ = self.journal(CALLER, 'dual-begins')
            verifier.require(all(sum(r.get('event') == 'begin' and r.get('invocation_id') == inv for r in rows) == 1
                                 for inv in invocations), 'dual public calls did not both begin')
            pending = {1: invocations[0], 2: invocations[1]}
            while pending:
                def current():
                    layout, _ = self.layout('dual-current-count')
                    count = selected_count(layout)
                    return count if count in pending else None
                count = self.wait(current)
                invocation = pending.pop(count)
                action = self.terminal_input(invocation, 'done')
                self.wait_terminals([invocation])
                self.session_closed(action)
            self.absent(invocations)
            return
        invocation = invocations[0]
        if case_id in ('select-promise', 'select-callback', 'legacy-promise', 'legacy-callback'):
            self.contact_click(records[case['selected_offsets'][0][0]], 'select', invocation)
        elif case_id == 'cancel-default':
            self.wait_count(3)
            self.contact_click(records[0], 'unselect', invocation)
            self.wait_count(2)
            self.contact_click(records[3], 'select', invocation)
            self.wait_count(3)
        elif '205' in case_id:
            self.wait_count(205)
            self.picker_click('all_select_message', 'clear-all205')
            self.wait_count(0)
            self.picker_click('all_select_message', 'select-all205')
            self.wait_count(205)
        kind = 'cancel' if 'cancel' in case['ui'] else 'force_stop' if case_id == 'exit-pending' else \
               'home' if case_id == 'navigation-dismiss' else 'deadline_wait' if case_id == 'deadline' else 'done'
        if kind == 'force_stop': self.processes('before_exit', 1)
        action = self.terminal_input(invocation, kind)
        if kind == 'force_stop': self.processes('after_exit', 0)
        else: self.wait_terminals(invocations, 660 if kind == 'deadline_wait' else 90)
        self.session_closed(action)
        self.absent(invocations)

    def execute(self, seed_token, cases):
        seed = None
        errors = []
        try:
            before, proof = self.permissions(SEED, seed_token, 'seed-permissions-before-user')
            self.evidence['seed_permission_before'] = proof
            verifier.require(all(before[p] == -1 for p in ('READ_CONTACTS', 'WRITE_CONTACTS')),
                             'fresh seed install must require actual user grant')
            seed = self.seed_operation('create')
            write_json(self.output / 'seed.json', seed)
            after, proof = self.permissions(SEED, seed_token, 'seed-permissions-after-user')
            self.evidence['seed_permission_after'] = proof
            verifier.require(self.evidence.get('seed_user_permission_inputs') and
                             all(after[p] == 0 for p in ('READ_CONTACTS', 'WRITE_CONTACTS')),
                             'actual user Contacts permission grant missing')
            for case_id in cases:
                try:
                    self.case(case_id, seed)
                except Exception as error:
                    failure = {'case_id': case_id, 'error': str(error),
                               'diagnostics': self.failure_diagnostics('failure-' + case_id)}
                    errors.append(failure)
                    self.raw('aa force-stop ' + CALLER, 'recover-owned-caller-after-failure')
        except Exception as error:
            errors.append({'phase': 'seed-or-run', 'error': str(error),
                           'diagnostics': self.failure_diagnostics('failure-seed-or-run')})
        finally:
            try:
                self.raw('aa force-stop ' + CALLER, 'finally-stop-owned-caller')
            except Exception as error:
                errors.append({'phase': 'caller-stop', 'error': str(error)})
            try:
                cleanup = self.seed_operation('cleanup')
                write_json(self.output / 'cleanup.json', cleanup)
                verifier.require(cleanup['remaining_contacts'] == [], 'public CRUD cleanup left nonce records')
            except Exception as error:
                errors.append({'phase': 'public-CRUD-cleanup', 'error': str(error)})
            try:
                self.journal(CALLER, 'final-caller-journal')
                (self.output / 'journal.jsonl').write_text(self.last_journal)
            except Exception as error:
                errors.append({'phase': 'final-journal', 'error': str(error)})
            write_json(self.output / 'ui.json', self.evidence)
        return errors


def verify_normal_signed_input(identity, hap, bundle, permissions):
    with zipfile.ZipFile(hap) as archive:
        names = [n for n in archive.namelist() if n == 'module.json' or n.endswith('/module.json')]
        verifier.require(len(names) == 1, 'one real compiled HAP module required')
        module = json.loads(archive.read(names[0]))
        module = module.get('module', module)
        actual = module.get('requestPermissions', [])
        verifier.require(sorted(p['name'] for p in actual) == sorted(permissions) and
                         module.get('extensionAbilities', []) == [], 'ordinary HAP permissions/extensions differ')
    profile_path = verifier.artifact(identity['decoded_profile'])
    profile = verifier.raw_json(profile_path)
    info = profile.get('bundle-info', {})
    verifier.require(bundle in (CALLER, SEED) and permissions == ([] if bundle == CALLER else PERMISSIONS), 'exact Contacts profile role required')
    system_seed = bundle == SEED
    verifier.require(info.get('bundle-name') == bundle and info.get('apl') == ('system_basic' if system_seed else 'normal') and
                     info.get('app-feature') == ('hos_system_app' if system_seed else 'hos_normal_app') and
                     profile.get('acls', {}).get('allowed-acls', []) == [] and
                     profile.get('permissions', {}).get('restricted-permissions', []) == [],
                     'exact role profile with no ACL/restricted grants required')
    signature = verifier.raw_json(verifier.artifact(identity['signature_verification']))
    verifier.require(signature.get('exit_code') == 0 and signature.get('hap_sha256') == verifier.sha(hap) and
                     signature.get('decoded_profile_sha256') == verifier.sha(profile_path) and
                     'verify-app' in signature.get('command', []), 'real independent signature verification missing')
    remote = identity['installed_remote_hap']
    parts = PurePosixPath(remote).parts
    verifier.require(remote.startswith('/data/app/el1/bundle/public/') and bundle in parts and
                     '..' not in parts and remote.endswith('.hap'), 'exact BMS-installed ordinary HAP path required')


def run(args):
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    run_id = args.run_id or ('cp_' + secrets.token_hex(12))
    verifier.require(re.fullmatch('[A-Za-z0-9_-]{1,64}', run_id), 'bounded nonce required')
    report = {'schema_version': 1, 'run_id': run_id, 'status': 'fail', 'commands': [], 'failures': [],
              'scope': 'ordinary_contact_picker_runtime_NOT_full_behavior_gate', 'ledger_closed': False,
              'first_artifact_behavior_gate_passed': False}
    guest = None
    try:
        guest = EnclosingAcceptanceGuest(args.boot, args.archive, args.hdc, args.output / 'guest-commands').start()
        from batch_system_build_runtime_helpers import target_spec
        verifier.require(target_spec(guest.env['product'])['arch'] == guest.env['guest_arch'] and
                         guest.env['device_type'] in ('phone','2in1'), 'actual product/profile enclosing acceptance guest required')
        build = verifier.document(args.build)
        verifier.require(verifier.sha(verifier.artifact(build['representative_package'])) == verifier.sha(args.archive) and
                         build['booted_package_sha256'] == verifier.sha(args.archive), 'root build/package binding mismatch')
        build.update(run_id=run_id, boot_session_id=guest.env['boot_id'], architecture=guest.env['guest_arch'], device_profile=guest.env['device_type'])
        write_json(args.output / 'build.json', build)
        cases = [case['id'] for case in verifier.MATRIX.values() if case['required']] + list(args.optional_case)
        verifier.require(len(cases) == len(set(cases)), 'duplicate requested cases')
        def command(argv, label):
            guest.healthy()
            result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=30)
            path = args.output / ('transport-' + str(len(report['commands'])).zfill(4) + '-' + label + '.log')
            path.write_text(result.stdout + result.stderr)
            report['commands'].append({'argv': list(map(str, argv)), 'exit_code': result.returncode, **descriptor(path)})
            verifier.require(result.returncode == 0 and '[Fail]' not in result.stdout + result.stderr, 'actual guest transport failed: ' + label)
            guest.healthy()
            return result.stdout.replace('\r', '')
        ui = GuestUi(command, args.hdc, guest.target, args.output / 'ui-artifacts')
        driver = Driver(guest, ui, args.output, run_id, args.observer,
                        permission_bundle=args.permission_bundle, allow_texts=args.allow_text or ['允许', 'Allow'])
        verifier.require(PurePosixPath(args.observer).is_absolute() and '..' not in PurePosixPath(args.observer).parts,
                         'absolute installed observer path required')
        remote_hash = driver.raw('sha256sum ' + shlex.quote(args.observer), 'actual-readonly-observer-hash')[0].split()[0]
        verifier.require(remote_hash == verifier.sha(args.observer_local), 'guest observer differs from product-built artifact')
        validate_elf(args.observer_local, guest.env['guest_arch'])
        report['observer'] = descriptor(args.observer_local)
        report['observer_remote'] = args.observer
        seed_manifest = verifier.raw_json(verifier.artifact(build['seed_source_manifest']))
        verifier.require(seed_manifest.get('fixture_hashes') == {p.name: verifier.sha(p) for p in sorted(FIX.iterdir()) if p.is_file()},
                         'compiled seed source fixture provenance differs')
        report['seed_source_manifest'] = build['seed_source_manifest']
        identities = {}
        for bundle, key, input_path in [(CALLER, 'caller', args.identity), (SEED, 'seed', args.seed_identity)]:
            signed = verifier.document(input_path)
            hap = verifier.artifact(build[key + '_hap'])
            verify_normal_signed_input(signed, hap, bundle, [] if key == 'caller' else PERMISSIONS)
            text, bms = driver.raw('bm dump -n ' + bundle, key + '-actual-BMS-UID-token')
            app = application_info(text, bundle)
            installed = args.output / (key + '-actual-installed.hap')
            command([args.hdc, '-t', guest.target, 'file', 'recv', signed['installed_remote_hap'], installed], key + '-pull-installed-HAP')
            verifier.require(verifier.sha(installed) == verifier.sha(hap), 'actual installed HAP differs from signed input')
            _, token_proof = driver.permissions(bundle, app['accessTokenId'], key + '-actual-token-permissions')
            identity = {**signed, 'run_id': run_id, 'hap_sha256': verifier.sha(hap), 'bms_dump': bms,
                        'installed_caller_hap': descriptor(installed), 'permission_probe': token_proof}
            write_json(args.output / (key + '-identity.json'), identity)
            identities[key] = app
        provider_raw, provider_bms = driver.raw('bm dump -n ' + PROVIDER, 'Contacts-provider-BMS-UID')
        driver.evidence['provider_bms'] = provider_bms
        verifier.provider_uid(driver.evidence)
        driver.provider_bms = provider_bms
        driver.caller_uid = identities['caller']['uid']
        # Zero-permission caller is checked before it can trigger any UI.
        verifier.verify_identity(verifier.document(args.output / 'caller-identity.json'), build, run_id)
        driver.raw('aa dump -a -u 100', 'AMS-before')
        report['failures'].extend(driver.execute(identities['seed']['accessTokenId'], cases))
        report['identity_after'] = {}
        for bundle, key in [(CALLER, 'caller'), (SEED, 'seed')]:
            try:
                text, proof = driver.raw('bm dump -n ' + bundle, key + '-BMS-UID-token-after')
                app = application_info(text, bundle)
                verifier.require(all(app[name] == identities[key][name] for name in ('uid', 'accessTokenId')),
                                 'installed UID/token changed during runtime')
                value, token_proof = driver.permissions(bundle, app['accessTokenId'], key + '-token-after')
                wanted = -1 if key == 'caller' else 0
                verifier.require(all(value[name] == wanted for name in ('READ_CONTACTS', 'WRITE_CONTACTS')),
                                 'unexpected Contacts permission state after runtime')
                report['identity_after'][key] = {'bms_dump': proof, 'permission_probe': token_proof}
            except Exception as error:
                report['failures'].append({'phase': key + '-identity-after', 'error': str(error)})
        for script, label in [('aa dump -a -u 100', 'AMS-after'), ('hilog -x', 'final-hilog'),
                              ('cat /proc/sys/kernel/random/boot_id', 'actual-currentboot-after')]:
            try:
                raw, _ = driver.raw(script, label)
                if label == 'actual-currentboot-after':
                    verifier.require(raw.strip() == guest.env['boot_id'], 'guest rebooted during runtime cases')
            except Exception as error:
                report['failures'].append({'phase': label, 'error': str(error)})
        # Invoke the independent verifier even when a case failed; preserve both
        # failure collections and public cleanup evidence in the same batch.
        try:
            result = verifier.verify_runtime(args.output / 'journal.jsonl', args.output / 'seed.json',
                args.output / 'cleanup.json', args.output / 'ui.json', args.output / 'caller-identity.json', args.output / 'build.json')
            write_json(args.output / 'independent-verifier.json', result)
        except Exception as error:
            report['failures'].append({'phase': 'independent-verifier', 'error': str(error)})
            write_json(args.output / 'independent-verifier.json', {'raw_results_verified': False, 'error': str(error),
                       'ledger_closed': False, 'first_artifact_behavior_gate_passed': False})
        if not report['failures']: report['status'] = 'pass'
    except Exception as error:
        failure = {'phase': 'setup-or-runtime', 'error': str(error)}
        if 'driver' in locals():
            failure['diagnostics'] = driver.failure_diagnostics('failure-setup-or-runtime')
        report['failures'].append(failure)
    finally:
        if guest:
            report['test_environment'] = guest.env
            report['guest_commands'] = guest.report['commands']
            if 'driver' in locals(): report['permission_bms_bindings'] = driver.permission_bms_bindings
            guest.close()
        write_json(args.output / 'driver-report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    prepare = sub.add_parser('prepare-seed')
    prepare.add_argument('--output-dir', type=Path, required=True)
    runtime = sub.add_parser('run')
    for name in ['boot', 'archive', 'build', 'identity', 'seed-identity', 'observer-local', 'output']:
        runtime.add_argument('--' + name, type=Path, required=True)
    runtime.add_argument('--hdc', required=True)
    runtime.add_argument('--observer', required=True)
    runtime.add_argument('--run-id')
    runtime.add_argument('--permission-bundle', default='com.ohos.permissionmanager')
    runtime.add_argument('--allow-text', action='append')
    runtime.add_argument('--optional-case', action='append', default=[], choices=['deadline', 'navigation-dismiss'])
    args = parser.parse_args()
    if args.mode == 'prepare-seed':
        print(json.dumps(prepare_seed(args.output_dir)))
        return 0
    report = run(args)
    print(json.dumps({'status': report['status'], 'run_id': report['run_id'], 'failures': report['failures'],
                      'ledger_closed': False, 'first_artifact_behavior_gate_passed': False}, ensure_ascii=False))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
