"""Finite URI lifetime IO on the original Owner, without resource constructors."""
from pathlib import Path
import json
import re
import secrets
import shlex
import time
import zipfile
from collections import Counter

from capability578_owned_io import reference, require
from settings_idle579_bindings import receipt, load_ref
from mms_share579_project import (ACTIONS, BUNDLES, CASES, MIME, ROLES, configure_profile,
    module_fields, source_files)
from capability578_callers import compiled_fields_match
from hap_identity_binding import bms_application_identity, strict_json
from guest_process_identity import starttime_shell, uids_shell
from guest_ui import NodeNotReady, LayoutNotReady, select_node
from batch_network_openvpn_runtime_collect import capture_snapshot
from batch_media_knowledge_suite import assert_bundles_absent

MMS = 'com.ohos.mms'
CACHE = '/data/app/el2/100/base/' + MMS + '/cache'


class Bindings:
    def __init__(self, io):
        self.io, self.run = io, io.run_id
        self.output = io.output / 'mms-share579'
        self.output.mkdir(exist_ok=False)
        self.roles, self.commands, self.reads, self.writers = {}, [], [], {}
        self.rows, self.prefixes, self.scans, self.actions = {}, {}, [], []
        self.installs, self.objects, self.requests = [], {}, []
        self.cleaned = False
        self.mms = None
        self.current_case = None
        self.native_windows = []
        self.mms_touched = False
        self.mms_imports = set()
        self.mms_cleanup = None
        io.register_cleanup(self.cleanup)  # before prepare/install/any command

    def shell(self, script, label, allow_failure=False):
        row = self.io.shell(script, 'uri579_' + label, allow_failure=True)
        self.commands.append(receipt(self.io, row, script))
        require(allow_failure or row['exit_code'] == 0, 'actual URI fixture guest command failed: ' + label)
        return row['stdout']

    def boot(self):
        self.io.owner.held_binding(self.io.guest)
        require(self.shell('cat /proc/sys/kernel/random/boot_id', 'boot').strip() == self.io.boot_id,
            'actual original held boot changed')

    def prepare(self):
        self.boot()
        value = self.io.prepare_callers('mms_share579', 'boundaries', self.run, ROLES, {})
        require(value['case'] == 'boundaries' and value['run_id'] == self.run and
            value['boot_id'] == self.io.boot_id and set(value['callers']) == set(ROLES), 'actual fixed caller build required')
        for role, caller in value['callers'].items():
            require(caller['bundle'] == BUNDLES[role] and all(caller[k] for k in
                ('build_commands', 'sign_commands', 'verify_commands')), 'actual ordinary caller build/sign/verify missing')
            for rel, text in source_files('boundaries', self.run, role, {}).items():
                require((Path(caller['project']) / rel).read_text() == text, 'compiled fixture source changed')
            for key in ('unsigned', 'signed'):
                with zipfile.ZipFile(Path(caller[key]['path'])) as hap:
                    require(reference(caller[key]['path']) == caller[key] and hap.read('ets/modules.abc'), 'real complete HAP required')
                    metadata = strict_json(hap.read('module.json').decode())
                    require(metadata['app']['bundleName'] == BUNDLES[role] and
                        compiled_fields_match(metadata['module'], module_fields('boundaries', role, {})),
                        'compiled permissions/skills differ; ordinary fixture cannot gain privileges')
            profile = strict_json(load_ref(caller['verified_profile']).decode())
            require(configure_profile('boundaries')(json.loads(json.dumps(profile)), role, self.io.udid, metadata) == profile,
                'actual verified ordinary profile/UDID differs')
            self.roles[role] = {'prepared': caller}

    def install(self, role):
        name = BUNDLES[role]
        assert_bundles_absent(self.shell('bm dump -a', 'fresh_' + role), [name])
        self.installs.append(role)  # intent before actual install
        row = self.io.command([self.io.hdc, '-t', self.io.target, 'install', self.roles[role]['prepared']['signed']['path']],
            'uri579_install_' + role)
        self.commands.append(receipt(self.io, row))
        text = self.shell('bm dump -n ' + name, 'bms_' + role)
        identity = bms_application_identity(text, name)
        doc = strict_json(text[text.index('{'):])
        require(doc['applicationInfo']['isSystemApp'] is False and
            doc['applicationInfo']['appPrivilegeLevel'] == 'normal' and not doc['reqPermissions'],
            'URI boundary actors must remain ordinary and permission-free')
        modules = doc['hapModuleInfos']
        require(len(modules) == 1 and modules[0]['moduleName'] == 'entry' and modules[0]['hapPath'].startswith('/data/app/'),
            'one actual ordinary installed HAP required')
        checksum = self.shell('sha256sum ' + shlex.quote(modules[0]['hapPath']), 'hash_' + role)
        require(checksum.strip() == self.roles[role]['prepared']['signed']['sha256'] + '  ' + modules[0]['hapPath'],
            'actual installed signed HAP differs')
        self.roles[role].update(identity=identity, remote='/data/app/el2/100/base/' + name + '/files',
            bms_command=len(self.commands)-2, hash_command=len(self.commands)-1)
        require(len({r['identity']['uid'] for r in self.roles.values() if 'identity' in r}) == len(self.installs),
            'ordinary roles must have distinct actual UIDs')

    def request(self, role, action, case, object_id, uri='', delivery=None):
        require(role in ROLES and action in ACTIONS and case in CASES and
            re.fullmatch('[a-f0-9]{32}', object_id), 'finite source-defined operation required')
        request = {'run': self.run, 'boot': self.io.boot_id, 'archive': self.io.archive_sha256,
            'operation': secrets.token_hex(16), 'object': object_id, 'caseId': case,
            'action': action, 'uri': uri, 'delivery': delivery or secrets.token_hex(16)}
        argv = ['aa', 'start', '-b', BUNDLES[role], '-a', 'EntryAbility', '-m', 'entry', '-u', '100',
            '--ps', 'request', json.dumps(request, separators=(',', ':'))]
        self.requests.append({'role': role, 'request': request, 'command': len(self.commands)})
        body = self.shell(shlex.join(argv), 'request_' + role + '_' + action.replace('-', '_'))
        require('start ability successfully' in body.lower(), 'actual AMS rejected ordinary fixture')
        return request

    def _writer(self, role, remote, row):
        key = role, remote
        require(row['uid'] == self.roles[role]['identity']['uid'] and type(row['pid']) is int and row['pid'] > 1 and
            re.fullmatch('uri579-' + self.run + '-' + str(row['pid']) + r'-[a-f0-9]{32}\.jsonl', Path(remote).name) and
            row['filesDir'] == '/data/storage/el2/base/files',
            'actual ordinary application filesDir/UID/PID differs')
        if key in self.writers:
            require(self.writers[key]['filesDir'] == row['filesDir'], 'actual writer sandbox path changed')
            return
        first_command = len(self.commands)
        pid = str(row['pid']); start = self.shell(starttime_shell(pid), 'writer_start_' + role).strip()
        require(re.fullmatch('[1-9][0-9]*', start) and
            self.shell(uids_shell(pid), 'writer_uid_' + role).split() == [str(row['uid'])] * 4,
            'actual journal writer process birth/all UIDs differ')
        sandbox = '/proc/' + pid + '/root' + row['filesDir'] + '/' + Path(remote).name
        value = self.shell('test ! -L ' + shlex.quote(remote) + ' && stat -c ' + shlex.quote('%d:%i:%u:%F') +
            ' ' + shlex.quote(remote) + ' ' + shlex.quote(sandbox), 'writer_inode_' + role).splitlines()
        require(len(value) == 2 and value[0] == value[1] and re.fullmatch('[0-9]+:[1-9][0-9]*:' +
            str(row['uid']) + ':regular file', value[0]) and
            self.shell(starttime_shell(pid), 'writer_end_' + role).strip() == start, 'actual journal sandbox/inode changed')
        self.writers[key] = {'role': role, 'path': remote, 'pid': row['pid'], 'uid': row['uid'],
            'start': start, 'inode': value[0], 'filesDir': row['filesDir'],
            'commands': list(range(first_command, len(self.commands))), 'commands_end': len(self.commands)}

    def collect(self, role):
        base = self.roles[role]['remote']; marker = '__URI579_' + secrets.token_hex(16) + '__'
        pattern = base + '/uri579-' + self.run + '-*.jsonl'
        script = ('for uri579_file in ' + pattern + '; do test -f "$uri579_file" || continue; '
            'test ! -L "$uri579_file" || exit 1; printf "' + marker + 'BEGIN:%s\\n" "$uri579_file"; '
            'cat "$uri579_file" || exit 1; printf "\\n' + marker + 'END\\n"; done')
        body = self.shell(script, 'journal_' + role)
        self.reads.append({'role': role, 'marker': marker, 'command': len(self.commands)-1})
        parts = body.split(marker + 'BEGIN:'); require(parts[0] == '', 'unframed raw journal bytes')
        for part in parts[1:]:
            path, rest = part.split('\n', 1)
            require(re.fullmatch(re.escape(base + '/uri579-' + self.run + '-') + r'[1-9][0-9]*-[a-f0-9]{32}\.jsonl', path) and
                rest.endswith('\n' + marker + 'END\n'), 'actual complete journal path/frame differs')
            text = rest[:-len('\n' + marker + 'END\n')]
            require(len(text.encode()) <= 16*1024*1024 and text.startswith(self.prefixes.get(path, '')), 'journal prefix changed')
            if not text.endswith('\n'):
                continue
            values = [strict_json(line) for line in text.splitlines()]
            previous_time = -1
            for number, row in enumerate(values, 1):
                require(row['run'] == self.run and row['boot'] == self.io.boot_id and row['archive'] == self.io.archive_sha256 and
                    row['bundle'] == BUNDLES[role] and row['role'] == role and row['seq'] == number and
                    type(row['activeMs']) is int and row['activeMs'] >= previous_time and
                    type(row['code']) is int and re.fullmatch('[a-f0-9]{32}', row['operation']),
                    'actual ordinary journal nonce/sequence/identity differs')
                previous_time = row['activeMs']
                self._writer(role, path, row)
            self.prefixes[path], self.rows[path] = text, values
        return [row for path, values in self.rows.items() if '/' + BUNDLES[role] + '/' in path for row in values]

    def wait(self, role, operation, event='done', timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = [row for row in self.collect(role) if row['operation'] == operation]
            require(not any(row['event'] == 'fixture.error' for row in rows), 'actual fixture operation failed')
            selected = [row for row in rows if row['event'] == event]
            if selected:
                require(len(selected) == 1, 'one complete actual event required')
                return rows
            time.sleep(.2)
        raise ValueError('actual URI fixture deadline: ' + role + '/' + event)

    def click(self, name, identifier):
        at = len(self.io.receipts)
        observed = self.io.ui.click(name, identifier=identifier, label='uri579_action_' + str(len(self.actions)))
        self.actions.append({'bundle': name, 'identifier': identifier, 'layout': reference(observed['layout']),
            'selected_node': observed['selected_node'], 'original_io_indices': list(range(at, len(self.io.receipts)))})
        return self.actions[-1]

    def layout(self, name=None):
        at = len(self.io.receipts)
        value, path = self.io.ui.layout(bundle=name, label='uri579_layout_' + str(len(self.actions)))
        self.actions.append({'bundle': name, 'layout': reference(path),
            'original_io_indices': list(range(at, len(self.io.receipts)))})
        return value

    def ready_invoke(self, role, request):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                layout = self.layout(BUNDLES[role])
                node = select_node(layout, BUNDLES[role], identifier='uri579-ready')
                if node['attributes']['text'] != self.run + '/' + request['operation'] + '/' + request['action']:
                    raise NodeNotReady('prior request still visible')
                self.click(BUNDLES[role], 'uri579-run')
                return
            except (NodeNotReady, LayoutNotReady):
                time.sleep(.2)
        raise ValueError('actual ordinary caller UI not ready')

    def scan(self, role, label):
        identity = self.roles[role]['identity'] if role in ROLES else self.mms['identity']
        raw, parsed = capture_snapshot(lambda script, sub: self.shell(script, re.sub('[^A-Za-z0-9_-]', '_', sub)),
            'uri579_' + label, self.io.boot_id, mode='uid', uid=identity['uid'], bundle=identity['bundle'])
        self.scans.append({'role': role, 'label': label, 'snapshot': parsed, 'commands_end': len(self.commands)})
        return parsed

    def stop(self, role):
        name = BUNDLES[role] if role in ROLES else MMS
        before = self.scan(role, 'before_stop_' + role)
        require(before['processes'], 'actual process generation required before death')
        self.shell('aa force-stop ' + name, 'stop_' + role)
        for n in range(2):
            deadline = time.monotonic() + 30
            while True:
                after = self.scan(role, 'stopped_' + role + '_' + str(n))
                if not after['processes']:
                    break
                require(time.monotonic() < deadline, 'actual UID not gone after force-stop')
                time.sleep(.2)
        return before

    def mms_cache(self):
        body = self.shell('if test -d ' + CACHE + '; then ls -1 ' + CACHE + '; else printf "__URI579_NO_CACHE__\\n"; fi', 'mms_cache')
        names = [] if body == '__URI579_NO_CACHE__\n' else body.splitlines()
        owned = [name for name in names if name.startswith('senddata-import-')]
        require(len(owned) == len(set(owned)) and all(re.fullmatch('senddata-import-[a-f0-9-]{36}', name) for name in owned),
            'unknown MMS staging name preserved')
        return owned

    def prepare_mms(self, facts):
        value = strict_json(load_ref(facts).decode())
        require(value['schema'] == 'actual-owned-capability579-mms-facts/v1' and
            value['boot_id'] == self.io.boot_id and value['package']['archive']['sha256'] == self.io.archive_sha256 and
            value['status'] == 'actual_system_hap_facts_exported_NOT_runtime_pass' and
            value['runtime_pass'] is False and set(value['modules']) == {'entry'},
            'actual same-package/boot selected MMS export required; no source/out HAP fallback')
        text = self.shell('bm dump -n ' + MMS, 'mms_bms')
        identity = bms_application_identity(text, MMS)
        doc = strict_json(text[text.index('{'):])
        require(identity == value['identity'] and doc['applicationInfo'] == value['actual_applicationInfo'] and
            doc.get('signatureInfo') == value['actual_signatureInfo'] and doc['reqPermissions'] == value['actual_reqPermissions'] and
            doc['applicationInfo']['isSystemApp'] is True and doc['applicationInfo']['appPrivilegeLevel'] == 'normal',
            'actual installed MMS identity/signature/permissions differ from selected package HAP')
        modules = doc['hapModuleInfos']
        require(len(modules) == 1 and modules[0]['moduleName'] == 'entry' and
            modules[0]['hapPath'] == value['actual_module_paths']['entry'] and
            modules[0]['hapPath'].startswith(('/system/', '/sys_prod/', '/system_ext/', '/app/')),
            'MMS must be selected by the real system package, not a data-updated test HAP')
        hap = value['modules']['entry']['hap']; load_ref(hap)
        with zipfile.ZipFile(hap['path']) as archive:
            require(len(archive.namelist()) == len(set(archive.namelist())) and archive.read('ets/modules.abc') and
                strict_json(archive.read('module.json').decode())['app']['bundleName'] == MMS,
                'actual complete selected MMS HAP required')
        actual = self.shell('sha256sum ' + shlex.quote(modules[0]['hapPath']), 'mms_hap_hash')
        require(actual == hap['sha256'] + '  ' + modules[0]['hapPath'] + '\n', 'held guest MMS bytes differ')
        self.mms = {'identity': identity, 'facts': facts, 'bms_command': len(self.commands)-2,
            'hash_command': len(self.commands)-1, 'hap_path': modules[0]['hapPath']}
        require(identity['uid'] not in {role['identity']['uid'] for role in self.roles.values()}, 'MMS shares an audit actor UID')
        require(not self.mms_cache(), 'preserve preexisting MMS import; fresh stage required')
        self.mms['initial_processes'] = self.scan('mms', 'mms_initial')['processes']

    def restart_mms(self):
        self.mms_touched = True
        text = self.shell('aa start -b com.ohos.mms -a com.ohos.mms.MainAbility -m entry -u 100', 'mms_public_recreate')
        require('start ability successfully' in text.lower(), 'actual public MMS recreation rejected')
        deadline = time.monotonic() + 30
        while True:
            seen = self.scan('mms', 'mms_recreated')
            if seen['processes']:
                return seen
            require(time.monotonic() < deadline, 'actual MMS process not recreated')
            time.sleep(.2)

    def wait_mms_empty(self, ui=False):
        observations = []
        deadline = time.monotonic() + 40
        while len(observations) < 2:
            names = self.mms_cache()
            require(set(names) <= self.mms_imports, 'unknown MMS import preserved; cannot cancel/recover somebody else\'s draft')
            if not names:
                at = len(self.commands)-1
                if ui:
                    tree = self.layout(MMS)
                    # A foreign/empty hierarchy is not proof of MMS UI state.
                    stack = [(node, '') for node in (tree if isinstance(tree,list) else [tree])]
                    visible = False
                    while stack:
                        node, parent = stack.pop(); attrs = node['attributes']; bundle = attrs.get('bundleName') or parent
                        visible = visible or (bundle == MMS and attrs.get('visible') == 'true')
                        stack.extend((child,bundle) for child in node.get('children',[]))
                    require(visible, 'actual visible MMS window required for no-attachment UI observation')
                    try:
                        select_node(tree, MMS, identifier='mms-senddata-attachment')
                    except NodeNotReady:
                        pass
                    else:
                        require(time.monotonic() < deadline, 'actual MMS attachment UI remains')
                        time.sleep(.2)
                        continue
                observations.append(at)
            else:
                observations = []
            require(time.monotonic() < deadline, 'actual MMS staged payload remains')
            time.sleep(.2)
        return observations

    def wait_import(self, content, source_name):
        deadline = time.monotonic() + 45
        while True:
            names = self.mms_cache()
            require(len(names) <= 1, 'unexpected additional MMS attachment preserved')
            if names:
                path = CACHE + '/' + names[0] + '/source.vcf'
                raw = self.shell('od -An -v -tx1 ' + path, 'mms_actual_vcard')
                require(re.fullmatch('[0-9a-fA-F \n]+', raw) and len(raw) <= 32768 and
                    bytes.fromhex(raw) == content.encode(), 'MMS must independently read and copy complete original nonce bytes')
                self.mms_imports.add(names[0])
                imported = {'name': names[0], 'cache_command': len(self.commands)-2, 'bytes_command': len(self.commands)-1}
                try:
                    tree = self.layout(MMS)
                    node = select_node(tree, MMS, identifier='mms-senddata-attachment')
                    require(node['attributes']['text'] == source_name + '\n' + str(len(content.encode())) + ' B',
                        'MMS recipient attachment name/size differs')
                    imported['ui_action'] = len(self.actions)-1
                    return imported
                except (NodeNotReady, LayoutNotReady):
                    pass
            require(time.monotonic() < deadline, 'MMS actual import/UI deadline')
            time.sleep(.2)

    def hilog(self):
        return self.shell('hilog -x', 'hilog')

    def service(self):
        begin = len(self.commands)
        pid = self.shell('pidof foundation', 'upms_foundation_pid').strip()
        require(re.fullmatch('[1-9][0-9]*', pid), 'one actual fixed-profile foundation process required')
        birth = self.shell(starttime_shell(pid), 'upms_foundation_birth').strip()
        uids = self.shell(uids_shell(pid), 'upms_foundation_uids').split()
        maps = self.shell('cat /proc/' + pid + '/maps', 'upms_foundation_maps')
        require(re.fullmatch('[1-9][0-9]*', birth) and uids == ['5523'] * 4 and
            re.search(r'/(?:[A-Za-z0-9_.-]+/)*libupms\.z\.so(?:\n|\s|$)', maps),
            'actual URI service process/UID/mapped production library missing')
        require(self.shell(starttime_shell(pid), 'upms_foundation_birth_after').strip() == birth,
            'actual URI service generation changed')
        return {'pid': int(pid), 'birth': birth, 'uids': uids, 'commands': list(range(begin, len(self.commands)))}

    def begin_native(self, role):
        service = self.service()
        self.hilog()
        value = {'role': role, 'token': self.roles[role]['identity']['token_id'] if role in ROLES else self.mms['identity']['token_id'],
            'before': len(self.commands)-1, 'service_before': service}
        self.native_windows.append(value)
        return len(self.native_windows)-1

    def finish_native(self, index):
        value = self.native_windows[index]
        before = load_ref(self.commands[value['before']]['body']).decode()
        deadline = time.monotonic() + 30
        pattern = r'URI579_REVOKE token:' + str(value['token']) + r' sandbox:1 unset_result:0 erased:1 remaining:0 policy_cutoff_ns:([1-9][0-9]*)\b'
        while True:
            after = self.hilog()
            fresh = list((Counter(after.splitlines()) - Counter(before.splitlines())).elements())
            matches = [line for line in fresh if re.search(pattern, line)]
            require(len(matches) <= 1, 'ambiguous target URI cleanup window')
            if matches:
                line = matches[0]
                stamp = re.match(r'^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+([1-9][0-9]*)\s+[1-9][0-9]*\s+I\b', line)
                require(stamp and int(stamp[1]) == value['service_before']['pid'], 'native erase record has a different actual process')
                value.update(after=len(self.commands)-1, line=line, service_after=self.service())
                require({k: value['service_before'][k] for k in ('pid','birth','uids')} ==
                    {k: value['service_after'][k] for k in ('pid','birth','uids')}, 'actual URI manager restarted')
                return value
            require(time.monotonic() < deadline, 'actual successful target URI policy removal/erase not observed')
            time.sleep(.2)

    def cleanup(self):
        if self.cleaned:
            return
        failures = []
        if self.mms_touched:
            try:
                require(set(self.mms_cache()) <= self.mms_imports, 'preserve unknown MMS import during cleanup')
                # Only the real app's original startup recovery removes its
                # own staging files. Never delete its cache as root.
                self.shell('aa force-stop com.ohos.mms', 'cleanup_mms_stop', allow_failure=True)
                self.restart_mms()
                empty = self.wait_mms_empty()
                self.mms_cleanup = {'empty_commands': empty, 'restored_running': bool(self.mms['initial_processes'])}
                if not self.mms['initial_processes']:
                    self.stop('mms')
                self.mms_cleanup['processes'] = self.scan('mms', 'mms_cleanup_restored')['processes']
            except Exception as error:
                failures.append('actual MMS recovery: ' + str(error))
        # Do not make grant evidence disappear by uninstalling. Runtime first
        # performs fresh same-UID FileIO/native queries while each source exists.
        for object_id, request in list(self.objects.items()):
            try:
                require(not failures, 'preserve source until failed MMS recovery is resolved by original Owner')
                r = self.request('owner', 'cleanup', request['caseId'], object_id)
                self.wait('owner', r['operation'], 'owner.deleted')
                del self.objects[object_id]
            except Exception as error:
                failures.append('owned payload: ' + str(error))
        for role in reversed(self.installs):
            try:
                self.shell('aa force-stop ' + BUNDLES[role], 'cleanup_stop_' + role, allow_failure=True)
                row = self.io.command([self.io.hdc, '-t', self.io.target, 'uninstall', BUNDLES[role]], 'uri579_uninstall_' + role)
                self.commands.append(receipt(self.io, row))
                assert_bundles_absent(self.shell('bm dump -a', 'cleanup_absent_' + role), [BUNDLES[role]])
                for n in range(2):
                    require(not self.scan(role, 'cleanup_' + role + '_' + str(n))['processes'], 'actual fixture UID remains')
            except Exception as error:
                failures.append(role + ': ' + str(error))
        self.boot()
        require(not failures, 'actual URI fixture cleanup failed: ' + '; '.join(failures))
        self.cleaned = True


def bind(root_io):
    return Bindings(root_io)
