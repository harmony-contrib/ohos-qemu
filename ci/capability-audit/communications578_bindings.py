"""Concrete communications stage on root's existing held-resource primitives.

No Owner/Runner/lease/Popen. bind(root_io) creates closures only. All commands,
SDK/signing, long-lived stdin, guest UI and cleanup registration belong to root.
"""
import hashlib
import json
from pathlib import Path
import re
import secrets
import shlex
import time
import communications578_project as project
from communications578_raw import decode, require
from guest_process_identity import identity_shell, starttime_shell, uids_shell
from hap_identity_binding import bms_application_identity
import batch_network_openvpn_runtime_collect as process_scan

SAFE = re.compile('[A-Za-z0-9_-]+')


def bind(root_io):
    io = root_io
    require(re.fullmatch('[a-f0-9-]{36}', io.boot_id) and re.fullmatch('[a-f0-9]{64}', io.archive_sha256), 'Actual held boot/package required')
    state = {'apps': {}, 'installed': set(), 'helpers': {}, 'receipts': [], 'peer': None,
             'remote': None, 'at_path': None, 'at_link': None, 'finished': False, 'label_serial': 0}

    def next_label(name):
        require(SAFE.fullmatch(name), 'Literal safe label required')
        state['label_serial'] += 1
        return name + '-' + str(state['label_serial']).zfill(5)

    def shell(script, label, *, allow_failure=False, timeout=60):
        require(SAFE.fullmatch(label), 'Literal safe label required')
        row = io.shell(script, next_label(label), timeout=timeout, allow_failure=allow_failure)
        require(type(row) is dict and row.get('boot_id') == io.boot_id and type(row.get('stdout')) is str and
                type(row.get('stderr')) is str and type(row.get('exit_code')) is int and not row.get('timed_out'), 'Actual root raw shell receipt missing')
        state['receipts'].append(row)
        if not allow_failure: require(row['exit_code'] == 0, 'Actual guest command failed')
        return row['stdout']

    def command(argv, label):
        require(SAFE.fullmatch(label), 'Safe command label required')
        row = io.command(argv, next_label(label), timeout=90, allow_failure=False)
        require(type(row) is dict and row.get('argv') == argv and row.get('boot_id') == io.boot_id and
                row.get('exit_code') == 0 and type(row.get('stdout')) is str, 'Actual command/exit/raw missing')
        state['receipts'].append(row); return row['stdout']

    def result(mark, **fields):
        rows = state['receipts'][mark:]
        require(rows, 'Actual callback performed no observable command')
        return dict(receipts=rows, **fields)

    def boot(label):
        require(shell('cat /proc/sys/kernel/random/boot_id', label).strip() == io.boot_id, 'Held boot changed')

    def artifact(ref):
        require(type(ref) is dict and set(ref) >= {'path', 'sha256'} and re.fullmatch('[a-f0-9]{64}', ref['sha256']), 'Actual prepared artifact descriptor missing')
        p = Path(ref['path']); require(p.is_absolute() and p.is_file() and not p.is_symlink() and
            hashlib.sha256(p.read_bytes()).hexdigest() == ref['sha256'], 'Actual prepared artifact changed')
        return p

    def bms(role, label):
        app = state['apps'][role]; raw = shell('bm dump -n ' + app['bundle'], label)
        start = raw.find('{'); require(start >= 0, 'Actual BMS JSON absent')
        text = raw[start:]; doc = decode(text)
        identity = bms_application_identity(raw, app['bundle'])
        require(doc['applicationInfo']['isSystemApp'] is (role != 'ordinary'), 'Actual installed role differs')
        if 'uid' in app: require(app['uid'] == identity['uid'], 'Installed UID changed')
        app['uid'] = identity['uid']; app['token'] = doc['applicationInfo']['accessTokenId']
        require(type(app['token']) is int and app['token'] > 0, 'Actual installed access token missing')
        app['bms_raw'] = text; return text

    def caller_identity(role, label):
        app = state['apps'][role]
        raw = shell(identity_shell(app['bundle']), label)
        fields = raw.strip().split()
        require(len(fields) == 6 and all(re.fullmatch('[0-9]+', s) for s in fields), 'Actual complete caller generation missing')
        pid, ticks, *uids = map(int, fields)
        require(pid > 0 and ticks > 0 and uids == [app['uid']] * 4, 'Caller actual PID/UID/start differs')
        if 'pid' in app: require((app['pid'], app['start_ticks']) == (pid, ticks), 'Caller generation replaced')
        app.update(pid=pid, start_ticks=ticks); return raw

    def native(which, label):
        # The root supplies observed package metadata, never alternate code.
        # Its config must exist on this image and define exactly this service.
        config = io.environment['communications578_services'][which]
        require(set(config) == {'name', 'init_path', 'process_name', 'libraries'} and
                all(re.fullmatch('[A-Za-z0-9_-]{1,64}', config[k]) for k in ('name', 'process_name')) and
                re.fullmatch('/(?:system|vendor)/etc/init/[A-Za-z0-9_.-]+\\.cfg', config['init_path']) and
                type(config['libraries']) is list and config['libraries'] and
                all(re.fullmatch('lib[A-Za-z0-9_.-]+\\.so', n) for n in config['libraries']), 'Exact actual packaged service metadata required')
        raw_cfg = shell('cat ' + shlex.quote(config['init_path']), label + '-cfg')
        cfg = decode(raw_cfg); matches = [s for s in cfg['services'] if s['name'] == config['name']]
        require(len(matches) == 1 and type(matches[0].get('path')) is list and matches[0]['path'], 'Actual init service differs')
        service = matches[0]
        require(service['path'][0] in ('/system/bin/sa_main', '/vendor/bin/hdf_devhost') and
                re.fullmatch('u:r:[A-Za-z0-9_]+:s0', service.get('secon', '')), 'Actual executable/domain configuration missing')
        if which == 'ril':
            require(service['name'] == 'riladapter_host' and service['uid'] == 'radio' and
                    service['secon'] == 'u:r:riladapter_host:s0' and service['path'][0] == '/vendor/bin/hdf_devhost' and
                    service['path'][-2:] == ['-n', 'riladapter_host'] and
                    set(config['libraries']) >= {'libril_driver.z.so', 'libril_service_1.5.z.so', 'libhril_hdf.z.so', 'libhril.z.so', 'libril_vendor.z.so'},
                    'Actual reference RIL host/provider configuration differs')
        else:
            require(service['name'] == 'bluetooth_service' and service['uid'] == 'bluetooth' and
                    service['secon'] == 'u:r:bluetooth_service:s0' and
                    service['path'] == ['/system/bin/sa_main', '/system/profile/bluetooth_service.json'], 'Actual Bluetooth service configuration differs')
        # An empty transient observation during restart is retained as empty;
        # it never supplies a made-up PID or successful service generation.
        raw_pid = shell('task_comm_pid=$(pidof ' + config['process_name'] + '); task_comm_rc=$?; '
            'test "$task_comm_rc" -le 1 || exit "$task_comm_rc"; printf "%s\\n" "$task_comm_pid"', label + '-pid').strip()
        require(re.fullmatch('[1-9][0-9]*', raw_pid), 'Unique actual native process missing')
        pid = int(raw_pid); ticks = shell(starttime_shell(str(pid)), label + '-start').strip()
        require(re.fullmatch('[1-9][0-9]*', ticks), 'Native generation absent')
        raw_uids = shell(uids_shell(str(pid)), label + '-uids').strip().split()
        require(len(raw_uids) == 4 and len(set(raw_uids)) == 1 and all(re.fullmatch('[0-9]+', n) for n in raw_uids), 'Native process UID inconsistent')
        maps = shell('cat /proc/' + str(pid) + '/maps', label + '-maps')
        require(all(any(line.rstrip().endswith('/' + lib) for line in maps.splitlines()) for lib in config['libraries']), 'Actual packaged native mappings missing')
        executable = shell('readlink /proc/' + str(pid) + '/exe', label + '-exe').strip()
        domain = shell('cat /proc/' + str(pid) + '/attr/current', label + '-domain').strip().rstrip('\x00')
        cmdline = shell('od -An -v -tx1 /proc/' + str(pid) + '/cmdline', label + '-cmdline')
        require(executable == service['path'][0] and domain == service['secon'], 'Actual native executable/SELinux domain differs')
        after_ticks = shell(starttime_shell(str(pid)), label + '-final-generation').strip()
        require(after_ticks == ticks, 'Actual native generation changed during collection')
        return dict(pid=pid, start_ticks=int(ticks), boot_id=io.boot_id, uid=int(raw_uids[0]), config=config,
                    maps=maps, init=raw_cfg, executable=executable, domain=domain, cmdline_hex=cmdline)

    def restart(which, label):
        before = native(which, label + '-before'); name = before['config']['name']
        shell('service_control stop ' + name, label + '-stop')
        shell('service_control start ' + name, label + '-start')
        deadline = time.monotonic() + 30; last = None
        while time.monotonic() < deadline:
            try:
                after = native(which, label + '-after')
                if (after['pid'], after['start_ticks']) != (before['pid'], before['start_ticks']):
                    state[which] = after; return before, after
            except ValueError as error: last = str(error)
            time.sleep(.25)
        raise ValueError('Actual service generation never changed: ' + str(last))

    def prepare_callers(guest, case, run, roles):
        mark = len(state['receipts']); require(guest is io.guest and case == 'communications578', 'Original held guest/case required')
        require(not state['installed'] and state['peer'] is None and re.fullmatch('[a-f0-9]{32}', run), 'Prior resources must be clean and run fresh')
        state.update(run=run, case='lifecycle' if 'system_peer' in roles else 'public', finished=False)
        params = {'native_sources': project.native_sources(), 'archive_sha256': io.archive_sha256, 'boot_id': io.boot_id}
        prepared = io.prepare_callers('communications578', state['case'], run, roles, params)
        require(type(prepared) is dict and set(prepared) >= {'applications', 'native_helpers', 'receipts'}, 'Real original builder/signature/helper artifacts required')
        require(set(prepared['applications']) == set(roles), 'Actual fixed roles differ')
        state['receipts'].extend(prepared['receipts']); state['apps'] = {}
        for role, value in prepared['applications'].items():
            signed = artifact(value['signed']); unsigned = artifact(value['unsigned'])
            # Original root builder/signing verifier is still mandatory; bind
            # every exact source input here in addition to its signature proof.
            actual_project = Path(value['project'])
            for name, content in project.source_files(state['case'], run, role).items():
                require((actual_project / name).read_bytes() == content.encode(), 'Actual caller project bytes differ')
            state['apps'][role] = dict(bundle=project.bundle(state['case'], role), signed=signed, unsigned=unsigned)
        require(set(prepared['native_helpers']) == {'at_peer', 'permission_controller'}, 'Fixed actual helper pair required')
        state['helpers'] = {name: artifact(ref) for name, ref in prepared['native_helpers'].items()}
        state['remote'] = '/data/local/tmp/communications578-' + run
        shell('test ! -e ' + state['remote'] + ' && test ! -L ' + state['remote'] + ' && mkdir -m 700 ' + state['remote'], 'comm578-create-private')
        for name, path in state['helpers'].items():
            row = io.send(str(path), state['remote'] + '/' + name, next_label('comm578-send-' + name))
            state['receipts'].append(row)
            shell('chmod 700 ' + state['remote'] + '/' + name, 'comm578-mode-' + name)
            raw_hash = shell('sha256sum ' + state['remote'] + '/' + name, 'comm578-hash-' + name)
            require(raw_hash.split()[0] == hashlib.sha256(path.read_bytes()).hexdigest(), 'Guest helper bytes changed')
        boot('comm578-prepared-boot'); return result(mark, prepared=prepared)

    def install(guest, role):
        mark = len(state['receipts']); require(guest is io.guest and role in state['apps'], 'Fixed actual role required')
        app = state['apps'][role]
        all_bms = shell('bm dump -a', 'comm578-before-install')
        require(not re.search(r'(?<![A-Za-z0-9_.])' + re.escape(app['bundle']) + r'(?![A-Za-z0-9_.])', all_bms), 'Preserve pre-existing bundle')
        state['installed'].add(role)  # cleanup intent precedes installation
        raw = command([io.hdc, '-t', io.target, 'install', str(app['signed'])], 'comm578-install-' + role)
        require('install bundle successfully' in raw.lower(), 'Actual HDC/BMS install did not succeed')
        bms(role, 'comm578-installed-bms-' + role)
        app['remote'] = '/data/app/el2/100/base/' + app['bundle'] + '/haps/entry/files/communications578-' + state['run'] + '.jsonl'
        shell('test ! -e ' + shlex.quote(app['remote']) + ' && test ! -L ' + shlex.quote(app['remote']), 'comm578-fresh-journal-' + role)
        return result(mark, bms_raw=app['bms_raw'])

    def start(guest, role, action, request):
        mark = len(state['receipts']); require(guest is io.guest and role in state['installed'] and action == 'EntryAbility', 'Installed exact public caller required')
        require(request['run_id'] == state['run'] and request['boot_id'] == io.boot_id, 'Request belongs to another boot/run')
        script = shlex.join(['aa', 'start', '-b', state['apps'][role]['bundle'], '-a', 'EntryAbility', '--ps', 'request', json.dumps(request, separators=(',', ':'), allow_nan=False)])
        state['apps'][role]['started'] = True
        shell(script, 'comm578-start-' + role); return result(mark)

    def collect(guest, role, request_id):
        mark = len(state['receipts']); require(guest is io.guest and role in state['installed'], 'Live installed caller required')
        app = state['apps'][role]
        raw = shell('if test -f ' + shlex.quote(app['remote']) + '; then cat ' + shlex.quote(app['remote']) + '; fi', 'comm578-journal-' + role)
        if not raw: return result(mark, raw='')
        first = decode(raw.splitlines()[0]); bms(role, 'comm578-collect-bms-' + role)
        process_raw = caller_identity(role, 'comm578-collect-process-' + role)
        require(first['pid'] == app['pid'] and first['uid'] == app['uid'], 'Journal writer is not actual BMS process')
        files = first['files_dir']; require(type(files) is str and files.startswith('/data/storage/') and
            files.endswith('/haps/entry/files') and '..' not in Path(files).parts and str(Path(files)) == files, 'Actual module filesDir invalid')
        sandbox = '/proc/' + str(app['pid']) + '/root' + files + '/' + Path(app['remote']).name
        stat = shell('stat -c ' + shlex.quote('%d:%i:%u:%F') + ' ' + shlex.quote(app['remote']) + ' ' + shlex.quote(sandbox), 'comm578-journal-inode-' + role)
        lines = stat.splitlines(); require(len(lines) == 2 and lines[0] == lines[1] and
            re.fullmatch('[0-9]+:[1-9][0-9]*:' + str(app['uid']) + ':regular file', lines[0]), 'Actual app/root/proc journal inode/UID differs')
        return result(mark, raw=raw, bms_raw=app['bms_raw'], process_identity_raw=process_raw, module_files_raw=stat)

    def uid_absence(role):
        app = state['apps'][role]; require(type(app.get('uid')) is int, 'Installed UID was never established')
        captures = []
        for i in range(2):
            nonce = secrets.token_hex(16)
            raw = shell(process_scan.snapshot_script(nonce, io.boot_id, mode='uid', uid=app['uid'], bundle=app['bundle']), 'comm578-uid-absence-' + role + '-' + str(i))
            snapshot = process_scan.parse_snapshot(raw, nonce, io.boot_id, mode='uid', uid=app['uid'], bundle=app['bundle'])
            require(snapshot['processes'] == {}, 'Caller UID/bundle process remains after uninstall')
            captures.append(raw)
            if i == 0: time.sleep(.5)
        return '\n'.join(captures)

    def exit_caller(role):
        app = state['apps'][role]
        shell('aa force-stop ' + app['bundle'], 'comm578-stop-' + role)
        raw = shell('bm uninstall -n ' + app['bundle'], 'comm578-uninstall-' + role)
        require('uninstall bundle successfully' in raw.lower(), 'Actual bundle uninstall failed')
        remaining = shell('bm dump -a', 'comm578-final-bms-' + role)
        require(not re.search(r'(?<![A-Za-z0-9_.])' + re.escape(app['bundle']) + r'(?![A-Za-z0-9_.])', remaining), 'Bundle remains installed')
        absence = uid_absence(role); state['installed'].remove(role); return raw + '\n' + absence

    def public_cleanup(role):
        app = state['apps'][role]
        if not app.get('started'): return ''
        before = collect(io.guest, role, 'cleanup-observation')['raw']
        op = secrets.token_hex(16)
        request = {'run_id': state['run'], 'boot_id': io.boot_id, 'operation_id': op,
                   'case_id': 'owner-cleanup', 'action': 'cleanup', 'api': '', 'form': 'callback',
                   'slot': 0, 'listener': 'owner-cleanup', 'call_id': 2147483000,
                   'enabled': False, 'address': '12:34:56:78:9A:BC', 'wait_ms': 2500}
        start(io.guest, role, 'EntryAbility', request)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            raw = collect(io.guest, role, op)['raw']
            require(raw.startswith(before), 'Cleanup journal prefix changed')
            tail = [decode(line) for line in raw[len(before):].splitlines()]
            own = [r for r in tail if r['operation_id'] == op]
            if any(r['kind'] == 'end' for r in own):
                require(len([r for r in own if r['kind'] == 'begin' and r['value'] == request]) == 1 and
                        len([r for r in own if r['kind'] == 'return' and r['code'] == 0]) == 1 and
                        len([r for r in own if r['kind'] == 'end']) == 1 and
                        all(r['code'] == 0 and r['kind'] in ('begin', 'return', 'end', 'cleanup-step') for r in own) and
                        not [r for r in tail if r['kind'] in ('callback', 'bt-callback', 'sms-send', 'sms-delivery')],
                        'Real public cleanup failed or a late callback escaped the final quiet window')
                return raw
            time.sleep(.2)
        raise ValueError('Actual public cleanup did not complete before process exit')

    def input_action(guest, action, selector):
        mark = len(state['receipts']); require(guest is io.guest, 'Held guest required')
        if action == 'communications-permission-consent':
            before = len(io.receipts)
            ui = io.ui.click('com.ohos.permissionmanager', text=io.environment['permission_allow_text'], label=next_label('comm578-actual-consent'))
            state['receipts'].extend(io.receipts[before:])
            # Root GuestUi's raw hierarchy/click proof is preserved verbatim.
            shell('cat /proc/sys/kernel/random/boot_id', 'comm578-consent-boot')
            return result(mark, ui=ui)
        if action == 'communications-revoke-network-info':
            role = selector['role']; app = state['apps'][role]
            caller_identity(role, 'comm578-revoke-before-process'); bms(role, 'comm578-revoke-before-bms')
            op = secrets.token_hex(16)
            argv = [state['remote'] + '/permission_controller', state['run'], io.boot_id, op,
                    str(app['token']), app['bundle'], str(app['pid'])]
            raw = shell(shlex.join(argv), 'comm578-fixed-permission-attempt')
            doc = decode(raw)
            require(doc['kind'] == 'fixed-permission-revoke-attempt' and doc['run_id'] == state['run'] and
                    doc['boot_id'] == io.boot_id and doc['operation_id'] == op and doc['target_pid'] == app['pid'] and
                    doc['target_token'] == app['token'] and doc['bundle'] == app['bundle'] and
                    doc['permission'] == 'ohos.permission.GET_NETWORK_INFO' and doc['kill_process'] is False and
                    doc['target_start_ticks_before'] == doc['target_start_ticks_after'] == app['start_ticks'] and
                    doc['flag_before'] & 4 and doc['status_before'] == 0 and doc['revoke_result'] != 0 and
                    doc['flag_result_before'] == doc['flag_result_after'] == doc['flag_result_final'] == 0 and
                    doc['flag_before'] == doc['flag_after'] == doc['flag_final'] and
                    doc['status_before'] == doc['status_after'] == doc['status_final'] and doc['restore_result'] == 0,
                    'Real SYSTEM_FIXED rejection/state/process boundary differs')
            caller_identity(role, 'comm578-revoke-after-process')
            return result(mark, raw=raw, permission_boundary='SYSTEM_FIXED_live_revoke_unsupported')
        raise ValueError('Unlisted actual input action')

    def network(guest, action, parameters):
        mark = len(state['receipts']); require(guest is io.guest, 'Held guest required')
        if action == 'communications-bluetooth-native-restart':
            before, after = restart('bluetooth', 'comm578-bt-restart')
            return result(mark, raw=json.dumps({'before': before, 'after': after}),
                before={k: before[k] for k in ('pid', 'start_ticks', 'boot_id')}, after={k: after[k] for k in ('pid', 'start_ticks', 'boot_id')})
        if action == 'communications-caller-exit':
            return result(mark, raw=exit_caller(parameters['role']))
        if action == 'communications-at-open':
            require(state['peer'] is None and parameters == {'run_id': state['run'], 'boot_id': io.boot_id}, 'Fresh same-boot AT peer required')
            require(shell('getenforce', 'comm578-actual-enforcing').strip() == 'Enforcing', 'Actual SELinux enforcing required')
            shell('dmesg', 'comm578-before-at-kernel-log')
            vendor = shell('param get const.sys.radio.vendorlib.path', 'comm578-vendor-param').strip()
            require(vendor == 'libril_vendor.z.so', 'Fixed QEMU reference vendor SONAME differs')
            current = native('ril', 'comm578-ril-before')
            mapped = set(line.split()[-1] for line in current['maps'].splitlines()
                         if line.split() and line.split()[-1].endswith('/libril_vendor.z.so'))
            require(len(mapped) == 1 and next(iter(mapped)) in ('/vendor/lib/libril_vendor.z.so', '/vendor/lib64/libril_vendor.z.so'),
                    'Actual mapped packaged reference vendor missing')
            vendor_path = next(iter(mapped))
            shell('test -f ' + vendor_path + ' && sha256sum ' + vendor_path, 'comm578-vendor-file')
            path = shell('param get const.telephony.ril.attty.path', 'comm578-at-param').strip() or '/dev/ttyUSB0'
            require(re.fullmatch('/dev/[A-Za-z0-9_/-]+', path) and '..' not in Path(path).parts, 'Configured real AT path invalid')
            shell('test ! -e ' + path + ' && test ! -L ' + path, 'comm578-at-original-absent')
            state['at_path'] = path
            peer_file = state['remote'] + '/peer.jsonl'; state['peer_file'] = peer_file
            script = 'umask 077; set -C; exec ' + state['remote'] + '/at_peer ' + state['run'] + ' ' + io.boot_id + ' > ' + peer_file + ' 2> ' + state['remote'] + '/peer.stderr'
            state['peer'] = io.spawn_guest(script, next_label('comm578-at-peer'))
            deadline = time.monotonic() + 15; ready = None
            while time.monotonic() < deadline:
                raw = shell('if test -f ' + peer_file + '; then cat ' + peer_file + '; fi', 'comm578-peer-ready')
                if raw:
                    ready = decode(raw.splitlines()[0]); break
                time.sleep(.1)
            require(ready is not None and ready['kind'] == 'ready' and ready['boot_id'] == io.boot_id and ready['run_id'] == state['run'], 'Actual peer PTY ready missing')
            require(type(ready['pid']) is int and ready['pid'] > 0 and ready['uid'] == 0 and ready['seq'] == 1,
                    'Actual owned peer process identity missing')
            peer_pid = str(ready['pid'])
            peer_start = shell(starttime_shell(peer_pid), 'comm578-peer-start').strip()
            require(re.fullmatch('[1-9][0-9]*', peer_start), 'Actual peer start ticks missing')
            require(shell(uids_shell(peer_pid), 'comm578-peer-uids').strip() == '0 0 0 0' and
                    shell('readlink /proc/' + peer_pid + '/exe', 'comm578-peer-exe').strip() == state['remote'] + '/at_peer',
                    'Actual peer root/executable differs')
            peer_args = shell('od -An -v -tx1 /proc/' + peer_pid + '/cmdline', 'comm578-peer-argv')
            peer_hex = ''.join(peer_args.split())
            require(re.fullmatch('(?:[a-f0-9]{2})+', peer_hex) and bytes.fromhex(peer_hex).split(b'\x00') ==
                    [str(state['remote'] + '/at_peer').encode(), state['run'].encode(), io.boot_id.encode(), b''],
                    'Actual fixed peer argv/run/boot differs')
            require(shell(starttime_shell(peer_pid), 'comm578-peer-start-again').strip() == peer_start,
                    'Actual peer generation changed during binding')
            state['peer_pid'] = ready['pid']; state['peer_start_ticks'] = int(peer_start)
            target = bytes.fromhex(ready['hex']).decode('ascii'); require(re.fullmatch('/dev/pts/[0-9]+', target), 'Actual fresh PTY required')
            labels = shell('ls -Zd /dev/pts ' + target, 'comm578-actual-pty-labels')
            require('u:object_r:dev_pts_file:s0' in labels and 'u:object_r:devpts:s0' in labels,
                    'Actual PTY directory/slave SELinux labels differ from packaged policy')
            shell('chown ' + str(current['uid']) + ':' + str(current['uid']) + ' ' + target + ' && chmod 600 ' + target, 'comm578-pty-access')
            owner = shell('stat -c ' + shlex.quote('%d:%i:%u:%g:%a:%F') + ' ' + target, 'comm578-pty-inode-mode').strip()
            require(re.fullmatch('[0-9]+:[1-9][0-9]*:' + str(current['uid']) + ':' + str(current['uid']) + ':600:character special file', owner),
                    'Actual owned radio PTY inode/DAC differs')
            state['pty_stat'] = owner
            shell('test ! -e ' + path + ' && test ! -L ' + path + ' && ln -s ' + target + ' ' + path, 'comm578-at-bind')
            state['at_link'] = target
            link_label = shell('ls -Zd ' + path, 'comm578-actual-at-link-label')
            require('u:object_r:dev_file:s0' in link_label, 'Actual owned AT symlink label differs')
            state['at_link_stat'] = shell('stat -c ' + shlex.quote('%d:%i:%u:%F') + ' ' + path, 'comm578-at-link-identity').strip()
            before, after = restart('ril', 'comm578-ril-restart')
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                raw = shell('cat ' + peer_file, 'comm578-modem-init-wire')
                rows = [decode(line) for line in raw.splitlines()]
                received = b''.join(bytes.fromhex(r['hex']) for r in rows if r['kind'] == 'rx')
                if b'ATE0Q0V1\r' in received and b'AT+CFUN=1,0\r' in received: break
                time.sleep(.25)
            else: raise ValueError('Actual RIL read loop/ModemInit never reached peer')
            return result(mark, peer_raw=raw, native=after)
        if action == 'communications-at-write':
            require(state['peer'] is not None and parameters['kind'] in ('one', 'zero', 'invalid') and re.fullmatch('[a-f0-9]{32}', parameters['operation_id']), 'Finite fresh AT write required')
            io.write_stdin(state['peer'], (parameters['operation_id'] + '\t' + parameters['kind'] + '\n').encode())
            raw = shell('cat ' + state['peer_file'], 'comm578-at-write-observation')
            return result(mark, peer_raw=raw)
        if action == 'communications-at-evidence':
            require(state['peer'] is not None, 'Held AT peer missing')
            raw = shell('cat ' + state['peer_file'], 'comm578-at-final-wire')
            target = state['at_link']; pid = state['ril']['pid']
            script = 'readlink -f ' + state['at_path'] + '; task_comm_fd_count=0; for task_comm_fd in /proc/' + str(pid) + '/fd/*; do task_comm_target=$(readlink -f "$task_comm_fd") || exit 1; if test "$task_comm_target" = ' + target + '; then printf "%s\\n" "$task_comm_target"; task_comm_fd_count=$((task_comm_fd_count + 1)); fi; done; test "$task_comm_fd_count" = 1'
            binding = shell(script, 'comm578-at-reader-fd')
            require(binding.splitlines() == [target, target], 'Actual AT path/reader fd differs')
            require(shell('stat -c ' + shlex.quote('%d:%i:%u:%g:%a:%F') + ' ' + target, 'comm578-pty-final-inode').strip() == state['pty_stat'],
                    'Actual reader PTY inode/ownership/mode changed')
            native('ril', 'comm578-ril-final')
            shell('dmesg', 'comm578-after-at-kernel-log')
            return result(mark, peer_raw=raw, binding_raw=binding)
        if action in ('communications-queue-native-begin', 'communications-queue-native-end'):
            role = parameters['role']; app = state['apps'][role]; caller_identity(role, 'comm578-queue-process')
            # Capture an increasing complete dump for this exact live PID;
            # preserve the prefix and require an append-only native window.
            raw = shell('hilog -x -P ' + str(app['pid']), 'comm578-queue-native-dump')
            if action.endswith('begin'):
                state['queue_native_prefix'] = raw; return result(mark, pid=app['pid'], raw=raw)
            prefix = state.pop('queue_native_prefix'); require(raw.startswith(prefix), 'Native log truncated/reordered during queued-off challenge')
            return result(mark, pid=app['pid'], raw=raw[len(prefix):])
        raise ValueError('Unlisted network action: ' + action)

    def cleanup(guest=None):
        mark = len(state['receipts']); failures = []; raw_parts = []
        if state['finished']:
            boot('comm578-cleanup-repeat-boot'); return result(mark, raw='Original communications cleanup already completed\n')
        for role in tuple(state['installed']):
            try: raw_parts.append(public_cleanup(role))
            except Exception as error: failures.append(role + ' public cleanup: ' + str(error))
            try: raw_parts.append(exit_caller(role))
            except Exception as error: failures.append(role + ': ' + str(error))
        if state['peer'] is not None:
            try:
                zero_op = secrets.token_hex(16); stop_op = secrets.token_hex(16)
                io.write_stdin(state['peer'], (zero_op + '\tzero\n').encode())
                time.sleep(.3)
                io.write_stdin(state['peer'], (stop_op + '\tstop\n').encode())
                observed = io.wait(state['peer'], 10)
                require(type(observed) is dict and observed.get('exit_code') == 0 and observed.get('boot_id') == io.boot_id and
                        type(observed.get('argv')) is list and type(observed.get('stdout')) is str and
                        type(observed.get('stderr')) is str and not observed.get('timed_out'), 'Actual held peer did not exit zero with raw receipt')
                state['receipts'].append(observed)
                final_peer = shell('cat ' + state['peer_file'], 'comm578-preserve-final-peer')
                raw_parts.append(final_peer)
                final_rows = [decode(line) for line in final_peer.splitlines()]
                zeros = [r for r in final_rows if r['kind'] == 'tx' and r['operation_id'] == zero_op]
                closed = [r for r in final_rows if r['kind'] == 'closed' and r['operation_id'] == stop_op]
                require(len(zeros) == len(closed) == 1 and zeros[0]['hex'] == b'\r\n+OHOS5A: 0\r\n'.hex() and
                        zeros[0]['seq'] < closed[0]['seq'] and closed[0] == final_rows[-1] and
                        all(r['boot_id'] == io.boot_id and r['run_id'] == state['run'] for r in final_rows),
                        'Actual final zero/closed peer journal missing')
                if 'peer_pid' in state:
                    shell('test ! -d /proc/' + str(state['peer_pid']), 'comm578-peer-process-absence')
                state['peer'] = None
            except Exception as error: failures.append('peer: ' + str(error))
        if state['at_link'] is not None:
            try:
                current = shell('stat -c ' + shlex.quote('%d:%i:%u:%F') + ' ' + state['at_path'] + ' && readlink ' + state['at_path'], 'comm578-at-owned-link')
                require(current.splitlines() == [state['at_link_stat'], state['at_link']], 'AT link ownership changed; preserved')
                shell('rm ' + state['at_path'] + ' && test ! -e ' + state['at_path'] + ' && test ! -L ' + state['at_path'], 'comm578-at-unbind')
                state['at_link'] = None
                restart('ril', 'comm578-ril-original-no-device')
            except Exception as error: failures.append('AT binding/restore: ' + str(error))
        if state['remote'] is not None and state['peer'] is None and state['at_link'] is None:
            try:
                # Exact finite owned files only; unknown files prevent rmdir.
                paths = [state['remote'] + '/' + n for n in ('at_peer', 'permission_controller', 'peer.jsonl', 'peer.stderr')]
                shell('test -d ' + state['remote'] + ' && test ! -L ' + state['remote'] + ' && test "$(stat -c ' + shlex.quote('%u:%a') + ' ' + state['remote'] + ')" = 0:700 && rm -f ' + ' '.join(paths) + ' && rmdir ' + state['remote'], 'comm578-owned-private-release')
                state['remote'] = None
            except Exception as error: failures.append('private files: ' + str(error))
        shell('dmesg', 'comm578-cleanup-kernel-log')
        boot('comm578-cleanup-final-boot')
        require(not failures, 'Actual communications cleanup failed: ' + '; '.join(failures))
        state['finished'] = True
        return result(mark, raw='\n'.join(raw_parts) or 'No installed callers or AT peer remained; actual boot/private absence commands retained\n')

    io.register_cleanup(cleanup)
    return {'prepare_callers': prepare_callers, 'install': install, 'start': start,
            'input': input_action, 'collect': collect, 'network': network, 'cleanup': cleanup}
