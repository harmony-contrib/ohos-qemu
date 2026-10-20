"""Concrete commands on the parent's original held guest. No resource owner."""
from pathlib import Path
import re
import secrets
import shlex
import time
import zipfile

from capability578_owned_io import reference, require
from guest_ui import command_exit
from guest_process_identity import starttime_shell, uids_shell
from hap_identity_binding import bms_application_identity, strict_json
from batch_network_openvpn_runtime_collect import capture_snapshot
from batch_media_knowledge_suite import assert_bundles_absent
from settings_idle579_project import BUNDLES, source_files

ACTIONS = frozenset(('remember', 'heartbeat', 'stale', 'future', 'parameters', 'current',
    'retain-context', 'old-context-attempt', 'native-ui', 'native-malformed', 'native-foreign'))
ROW_KEYS = {'run', 'boot', 'operation', 'event', 'value', 'code', 'uid', 'pid', 'seq', 'uptimeMs', 'filesDir'}


def load_ref(ref):
    require(type(ref) is dict and set(ref) == {'path', 'sha256'} and reference(ref['path']) == ref,
            'unchanged actual raw artifact required')
    return Path(ref['path']).read_bytes()


def receipt(io, row, script=None):
    require(row['boot_id'] == io.boot_id and type(row['exit_code']) is int and
        row['timed_out'] is False and row['argv'][:3] == [io.hdc, '-t', io.target] and
        load_ref(row['stdout_ref']).decode() == row['stdout'] and
        load_ref(row['stderr_ref']).decode() == row['stderr'], 'actual original IO/raw receipt differs')
    if script is not None:
        require(len(row['argv']) == 5 and row['argv'][3] == 'shell', 'actual guest shell required')
        suffix = row['argv'][4][len(shlex.join(['sh', '-c', script])):]
        match = re.fullmatch(r'; cap578_rc=\$\?; printf "\\n(__CAP578_EXIT_[a-f0-9]{32}__=)%s\\n" "\$cap578_rc"', suffix)
        require(row['argv'][4].startswith(shlex.join(['sh', '-c', script])) and match is not None,
                'source-defined exact shell script/nonce footer differs')
        transport = load_ref(row['transport_stdout_ref']).decode()
        body, status = command_exit(transport, match[1])
        require(body == row['stdout'] and status == row['exit_code'] and row['transport_exit_code'] == 0,
                'actual HDC transport/footer/body/guest status differs')
    return {'receipt': io.ref_receipt(row), 'body': row['stdout_ref'],
            **({'script': script} if script is not None else {})}


class Bindings:
    def __init__(self, io):
        self.io = io
        require(re.fullmatch('[a-f0-9]{32}', io.run_id) and
            re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', io.boot_id),
            'same fresh run and actual guest boot required')
        self.run, self.roles, self.commands, self.reads = io.run_id, {}, [], []
        self.rows, self.prefixes, self.writers = {}, {}, {}
        self.install_intents, self.cleaned = [], False
        io.register_cleanup(self.cleanup)

    def shell(self, script, label, allow_failure=False):
        row = self.io.shell(script, 'idle579_' + label, allow_failure=True)
        self.commands.append(receipt(self.io, row, script))
        if not allow_failure:
            require(row['exit_code'] == 0, 'real guest operation failed: ' + label)
        return row['stdout']

    def command(self, argv, label, allow_failure=False):
        row = self.io.command(argv, 'idle579_' + label, allow_failure=True)
        self.commands.append(receipt(self.io, row))
        if not allow_failure:
            require(row['exit_code'] == 0, 'real HDC operation failed: ' + label)
        return row['stdout']

    def boot(self):
        require(self.shell('cat /proc/sys/kernel/random/boot_id', 'boot').strip() == self.io.boot_id,
                'actual held guest boot changed')

    def prepare(self):
        self.boot()
        native = self.io.package_inputs['native_addons']['settings_idle579']
        require(type(native) is dict and set(native) == {'binary', 'build', 'abi'} and
                native['abi'] == 'arm64-v8a' and load_ref(native['binary'])[:4] == b'\x7fELF' and
                load_ref(native['build']), 'original pre-VM actual platform shared-NAPI build required')
        self.native = native
        value = self.io.prepare_callers('settings_idle579', 'conditional', self.run,
                                       ('system', 'foreign'), {})
        require(value['case'] == 'conditional' and value['run_id'] == self.run and
            value['boot_id'] == self.io.boot_id and set(value['callers']) == set(BUNDLES) and
            value['native_addons'] == {'settings_idle579': native}, 'fixed prepared caller/addon contract differs')
        for role, row in value['callers'].items():
            require(row['bundle'] == BUNDLES[role] and row['build_commands'] and
                    row['sign_commands'] and row['verify_commands'], 'actual compile/sign/verify receipts missing')
            for kind in ('unsigned', 'signed', 'signing', 'verified_profile'):
                load_ref(row[kind])
            project = Path(row['project'])
            for path, expected in source_files('conditional', self.run, role, {}).items():
                require((project / path).is_file() and not (project / path).is_symlink() and
                        (project / path).read_text() == expected, 'actual source overlay differs')
            for kind in ('unsigned', 'signed'):
                with zipfile.ZipFile(row[kind]['path']) as hap:
                    require(len(hap.namelist()) == len(set(hap.namelist())) and
                        hap.read('libs/arm64-v8a/libsettings_idle579.so') == load_ref(native['binary']) and
                        hap.read('ets/modules.abc'), 'actual signed HAP native/Ark bytes differ')
            self.roles[role] = {'prepared': row}
        return value

    def install(self, role):
        require(role in BUNDLES and role not in self.install_intents, 'one finite install role required')
        bundle = BUNDLES[role]
        raw = self.shell('bm dump -a', 'before_' + role)
        assert_bundles_absent(raw, [bundle])
        # Register intent BEFORE a possibly partial/failed real install.
        self.install_intents.append(role)
        signed = self.roles[role]['prepared']['signed']
        self.command([self.io.hdc, '-t', self.io.target, 'install', signed['path']], 'install_' + role)
        raw = self.shell('bm dump -n ' + bundle, 'bms_' + role)
        identity = bms_application_identity(raw, bundle)
        doc = strict_json(raw[raw.index('{'):])
        require(doc['applicationInfo']['isSystemApp'] is True and
            doc['applicationInfo']['appPrivilegeLevel'] == 'system_core' and not doc.get('reqPermissions'),
                'actual system fixture signature/APL/permissions differs')
        paths = [m['hapPath'] for m in doc['hapModuleInfos'] if m.get('hapPath')]
        require(len(paths) == 1 and paths[0].startswith('/data/app/'), 'one installed actual fixture HAP required')
        raw_hash = self.shell('sha256sum ' + shlex.quote(paths[0]), 'installed_hash_' + role)
        require(raw_hash.strip() == signed['sha256'] + '  ' + paths[0], 'installed signed HAP changed')
        self.roles[role].update(identity=identity, bms_command=len(self.commands)-2,
            installed_hash_command=len(self.commands)-1,
            remote='/data/app/el2/100/base/' + bundle + '/haps/entry/files')
        pattern = self.roles[role]['remote'] + '/settings-idle579-' + self.run + '-*.jsonl'
        self.shell('for idle579_file in ' + pattern + '; do test ! -e "$idle579_file" && '
            'test ! -L "$idle579_file" || exit 1; done', 'fresh_journal_' + role)
        require(len({r['identity']['uid'] for r in self.roles.values() if 'identity' in r}) ==
                sum('identity' in r for r in self.roles.values()), 'fixture HAP UIDs must be distinct')
        return identity

    def request(self, role, action):
        require(role in self.roles and action in ACTIONS and 'identity' in self.roles[role],
                'fixed installed role/action required')
        if role == 'foreign':
            require(action in ('remember', 'heartbeat'), 'foreign service only supplies live genuine token')
        operation = secrets.token_hex(16)
        argv = ['aa', 'start', '-b', BUNDLES[role], '-a', 'EntryAbility', '--ps', 'run', self.run,
                '--ps', 'boot', self.io.boot_id, '--ps', 'operation', operation, '--ps', 'action', action]
        self.shell(shlex.join(argv), 'request_' + role + '_' + action.replace('-', '_'))
        return operation

    def _writer(self, role, path, row):
        pid = row['pid']; key = (role, path)
        require(row['uid'] == self.roles[role]['identity']['uid'] and type(pid) is int and pid > 1 and
            re.fullmatch('settings-idle579-' + self.run + '-' + str(pid) + r'-[a-f0-9]{32}\.jsonl', Path(path).name) and type(row['filesDir']) is str and
            row['filesDir'] in ('/data/storage/el2/base/haps/entry/files', self.roles[role]['remote']) and
            '..' not in Path(row['filesDir']).parts and str(Path(row['filesDir'])) == row['filesDir'],
            'actual per-PID UID/filesDir journal binding differs')
        if key in self.writers:
            require(row['filesDir'] == self.writers[key]['filesDir'], 'writer sandbox path changed')
            return
        sandbox = '/proc/' + str(pid) + '/root' + row['filesDir'] + '/' + Path(path).name
        raw = self.shell(starttime_shell(str(pid)), 'writer_start_' + role)
        require(re.fullmatch('[1-9][0-9]*\n?', raw), 'actual writer process start ticks absent')
        start = int(raw.strip())
        uids = self.shell(uids_shell(str(pid)), 'writer_uids_' + role)
        require(uids.split() == [str(row['uid'])] * 4, 'all four actual writer UIDs differ')
        meta = self.shell('test ! -L ' + shlex.quote(path) + ' && stat -c ' + shlex.quote('%d:%i:%u:%F') +
            ' ' + shlex.quote(path) + ' ' + shlex.quote(sandbox), 'writer_inode_' + role)
        lines = meta.splitlines()
        require(len(lines) == 2 and lines[0] == lines[1] and re.fullmatch(
            '[0-9]+:[1-9][0-9]*:' + str(row['uid']) + ':regular file', lines[0]),
                'actual sandbox/root journal inode ownership differs')
        maps = self.shell('cat /proc/' + str(pid) + '/maps', 'writer_maps_' + role)
        require('libsettings_idle579.so' in maps, 'actual platform addon was not mapped by caller')
        require(self.shell(starttime_shell(str(pid)), 'writer_start_after_' + role).strip() == str(start),
                'actual writer process generation changed')
        self.writers[key] = {'start_ticks': start, 'inode': lines[0], 'path': path,
                             'filesDir': row['filesDir'], 'commands_end': len(self.commands)}

    def collect(self, role):
        require(role in self.roles and 'remote' in self.roles[role], 'installed real journal role required')
        remote = self.roles[role]['remote']
        pattern = remote + '/settings-idle579-' + self.run + '-*.jsonl'
        marker = '__IDLE579_' + secrets.token_hex(16) + '__'
        script = ('for idle579_file in ' + pattern + '; do test -f "$idle579_file" || continue; '
            'test ! -L "$idle579_file" || exit 1; printf "' + marker + 'BEGIN:%s\\n" "$idle579_file"; '
            'cat "$idle579_file" || exit 1; printf "\\n' + marker + 'END\\n"; done')
        raw = self.shell(script, 'journal_' + role)
        self.reads.append({'role': role, 'command': len(self.commands)-1, 'marker': marker})
        pieces = raw.split(marker + 'BEGIN:')
        require(pieces[0] == '', 'unexpected journal capture prefix')
        for piece in pieces[1:]:
            path, rest = piece.split('\n', 1)
            require(re.fullmatch(re.escape(remote + '/settings-idle579-' + self.run + '-') +
                r'[1-9][0-9]*-[a-f0-9]{32}\.jsonl', path) and rest.endswith('\n' + marker + 'END\n'),
                    'actual complete finite journal frame differs')
            body = rest[:-len('\n' + marker + 'END\n')]
            require(len(body.encode()) <= 16 * 1024 * 1024 and
                body.startswith(self.prefixes.get(path, '')), 'actual append-only journal prefix changed')
            if not body.endswith('\n'):
                continue  # Retain raw; wait for the writer's complete fsynced row.
            parsed = [strict_json(line) for line in body.splitlines()]
            require(parsed, 'empty file cannot prove an actual request')
            previous_time = -1
            for number, row in enumerate(parsed, 1):
                require(type(row) is dict and set(row) == ROW_KEYS and row['run'] == self.run and
                    row['boot'] == self.io.boot_id and re.fullmatch('[a-f0-9]{32}', row['operation']) and
                    type(row['seq']) is int and row['seq'] == number and type(row['uptimeMs']) is int and
                    row['uptimeMs'] >= previous_time and type(row['code']) is int and
                    type(row['event']) is str and type(row['value']) is str, 'actual raw typed journal differs')
                previous_time = row['uptimeMs']; self._writer(role, path, row)
            self.prefixes[path] = body; self.rows[path] = parsed
        return [r for path, values in self.rows.items() if '/' + BUNDLES[role] + '/' in path for r in values]

    def wait(self, role, operation, event, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = self.collect(role)
            errors = [r for r in rows if r['operation'] == operation and r['event'] in
                      ('work.error', 'native.error', 'driver.start.error', 'stop.error')]
            require(not errors, 'real fixture error: ' + repr(errors))
            selected = [r for r in rows if r['operation'] == operation and r['event'] == event]
            if selected:
                require(len(selected) == 1, 'duplicated real operation event')
                return selected[0]
            time.sleep(.2)
        raise ValueError('actual runtime deadline: ' + role + '/' + event)

    def snapshot(self):
        return self.shell('aa dump -a -u 100', 'ams')

    def logs(self):
        return self.shell('hilog -x', 'hilog')

    def cleanup(self):
        if self.cleaned:
            return
        failures = []
        for role in reversed(self.install_intents):
            bundle = BUNDLES[role]
            try:
                # The only process stop/uninstall here is this stage's two new HAPs.
                self.shell('aa force-stop ' + bundle, 'stop_' + role, allow_failure=True)
                self.command([self.io.hdc, '-t', self.io.target, 'uninstall', bundle], 'uninstall_' + role)
                raw = self.shell('bm dump -a', 'gone_' + role)
                assert_bundles_absent(raw, [bundle])
                identity = self.roles[role].get('identity')
                require(identity is not None, 'failed installation needs actual BMS UID cleanup recovery')
                for scan in range(2):
                    raw, parsed = capture_snapshot(lambda script, label: self.shell(script,
                        re.sub('[^A-Za-z0-9_-]', '_', label)), 'idle579_cleanup_' + role,
                        self.io.boot_id, mode='uid', uid=identity['uid'], bundle=bundle)
                    require(not parsed['processes'], 'owned fixture UID/process remains after uninstall')
            except Exception as error:
                failures.append(role + ': ' + str(error))
        self.boot()
        require(not failures, 'actual cleanup failed: ' + '; '.join(failures))
        self.cleaned = True


def bind(root_io):
    return Bindings(root_io)
