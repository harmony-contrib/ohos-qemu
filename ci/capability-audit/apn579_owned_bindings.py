"""Finite virtual-SIM context on the original held OwnedIO, without resources.

All transports, builds, signatures, stdin and teardown remain original IO calls.
Only the real AT peer models a card. Public native APIs and the real packaged
CallSetting UI establish the account/default/preference consumed by Apps APN.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import re
import secrets
import shlex
import time

from capability578_owned_io import require, reference
from settings_idle579_bindings import receipt, load_ref
from hap_identity_binding import strict_json, bms_application_identity
from guest_process_identity import starttime_shell, uids_shell
from batch_network_openvpn_runtime_collect import capture_snapshot
from batch_media_knowledge_suite import assert_bundles_absent
from guest_ui import select_node, NodeNotReady, LayoutNotReady
from apn579_project import BUNDLE, PERMISSIONS, source_files
from apn579_protocol import peer_rows, readiness, public_state

ROW_KEYS = {'run','boot','operation','event','value','code','uid','pid','seq','uptimeMs','filesDir'}
ACTIONS = {'inspect','select-default','apn-read','apn-remember','open-apn',
           'restore-preference','restore-default','deactivate'}
PROVIDER = 'com.ohos.callsetting'
RIL_LIBS = {'libril_driver.z.so','libril_service_1.5.z.so','libhril_hdf.z.so',
            'libhril.z.so','libril_vendor.z.so'}


def canonical(value):
    result = dict(value)
    result['apns'] = sorted(value['apns'], key=lambda r: json.dumps(r, sort_keys=True))
    return result


def helper_admission(helper):
    require(type(helper) is dict and set(helper) == {'binary','build'} and
        load_ref(helper['binary'])[:4] == b'\x7fELF', 'actual platform C helper ELF descriptor required')
    proof = strict_json(load_ref(helper['build']).decode())
    actual = proof['helpers']['apn579_modem_peer']
    source_sha = hashlib.sha256(Path(__file__).with_name('apn579_modem_peer.c').read_bytes()).hexdigest()
    require(proof['status'] == actual['status'] == 'pass_compile_link_ONLY' and proof['plan_only'] is False and
        proof['changed_inputs'] == [] and actual['language'] == 'c' and actual['CFI_preserved'] is True and
        actual['runtime_validated'] is False and actual['binary_sha256'] == helper['binary']['sha256'] and
        actual['source']['sha256'] == actual['private_source_sha256'] == source_sha and
        actual['compile_command'] and actual['link_command'] and actual['actual_compiler_dependencies'] and
        'libc.so' in actual['actual_link_input_sonames'].values() and
        'libc.so' in actual['DT_NEEDED'], 'actual original platform C build/source/ELF/CFI proof differs')
    return proof


class VirtualSim:
    def __init__(self, io):
        require(re.fullmatch('[a-f0-9]{32}', io.run_id) and
            re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', io.boot_id) and
            re.fullmatch('[a-f0-9]{64}', io.archive_sha256), 'original run/boot/new package required')
        self.io, self.run = io, io.run_id
        self.output = Path(io.output) / 'apn579-owned'
        self.output.mkdir(exist_ok=False)
        self.commands, self.reads, self.ui, self.controls, self.requests = [], [], [], [], []
        self.rows, self.prefixes, self.writers = {}, {}, {}
        self.peer, self.peer_pid, self.peer_start = None, None, None
        self.remote, self.link, self.target, self.link_stat = None, None, None, None
        self.installed, self.uid, self.token = False, None, None
        self.card_present, self.activation_intent, self.restore_intent = False, False, False
        self.ril_stopped, self.ril_touched, self.cleaned = False, False, False
        self.peer_prefix, self.peer_reads, self.services = '', [], []
        self.baseline, self.original_apn, self.ready_apn = None, None, None
        self.apps, self.error, self.cleanup_errors = None, None, []
        self.modal_open = False
        self.report = {'schema':'actual-owned-virtual-sim579/v1','run':self.run,
            'boot_id':io.boot_id,'archive_sha256':io.archive_sha256,
            'scope':'owned virtual classic SIM prerequisite plus original Apps APN; no RF/PDP/IMS support claim',
            'commands':self.commands,'journal_reads':self.reads,'writers':[], 'ui':self.ui,
            'peer_controls':self.controls,'peer_reads':self.peer_reads,'services':self.services,'requests':self.requests,
            'failures':[],'cleanup_complete':False,'apps_joined':False,'runtime_pass':False}
        io.register_cleanup(self.cleanup)
        self.save()

    def save(self):
        self.report['writers'] = list(self.writers.values())
        (self.output / 'evidence.json').write_text(json.dumps(self.report, indent=2) + '\n')

    def shell(self, script, label, allow_failure=False, timeout=60):
        require(re.fullmatch('[A-Za-z0-9_-]+', label), 'safe literal command label required')
        row = self.io.shell(script, 'apn579_' + label, timeout=timeout, allow_failure=True)
        self.commands.append(receipt(self.io, row, script))
        self.save()
        if not allow_failure: require(row['exit_code'] == 0, 'actual guest command failed: ' + label)
        return row['stdout']

    def command(self, argv, label):
        row = self.io.command(argv, 'apn579_' + label, timeout=90, allow_failure=True)
        self.commands.append(receipt(self.io, row))
        self.save()
        require(row['argv'] == argv and row['exit_code'] == 0, 'actual original HDC operation failed')
        return row['stdout']

    def boot(self):
        require(self.shell('cat /proc/sys/kernel/random/boot_id', 'boot').strip() == self.io.boot_id,
                'original held boot changed')

    def prepare(self):
        self.boot()
        native = self.io.apn579_native_helper
        require(type(native) is dict and set(native) == {'modem_peer'}, 'one explicitly selected APN C helper required')
        helper = native['modem_peer']
        helper_admission(helper)
        self.helper = helper
        self.report['native_helper'] = helper
        prepared = self.io.prepare_callers('apn579','virtual-sim',self.run,('control',),{})
        require(prepared['case'] == 'virtual-sim' and prepared['run_id'] == self.run and
            prepared['boot_id'] == self.io.boot_id and set(prepared['callers']) == {'control'},
            'actual fixed original caller builder result differs')
        self.prepared = prepared['callers']['control']
        require(self.prepared['bundle'] == BUNDLE and all(self.prepared[k] for k in
            ('build_commands','sign_commands','verify_commands')), 'actual compile/sign/verification required')
        for key in ('unsigned','signed','signing','verified_profile'): load_ref(self.prepared[key])
        for name, text in source_files('virtual-sim',self.run,'control',{}).items():
            require((Path(self.prepared['project']) / name).read_bytes() == text.encode(),
                    'actual compiled public controller sources differ')
        self.report['prepared'] = self.prepared
        assert_bundles_absent(self.shell('bm dump -a','before_install'),[BUNDLE])
        self.installed = True  # intent precedes even a partial installation
        raw = self.command([self.io.hdc,'-t',self.io.target,'install',self.prepared['signed']['path']], 'install')
        require('install bundle successfully' in raw.lower(), 'actual BMS installation did not succeed')
        raw = self.shell('bm dump -n ' + BUNDLE,'controller_bms')
        identity = bms_application_identity(raw,BUNDLE)
        doc = strict_json(raw[raw.index('{'):])
        require(doc['applicationInfo']['isSystemApp'] is True and
            doc['applicationInfo']['appPrivilegeLevel'] == 'system_basic' and
            set(doc['reqPermissions']) == set(PERMISSIONS), 'actual controller APL/permission vector differs')
        self.uid = identity['uid']; self.token = doc['applicationInfo']['accessTokenId']
        require(type(self.uid) is int and self.uid > 10000 and type(self.token) is int and self.token > 0,
                'actual BMS UID/token absent')
        self.report['identity'] = identity
        self.app_remote = '/data/app/el2/100/base/' + BUNDLE + '/haps/entry/files'
        self.remote = '/data/local/tmp/apn579-' + self.run
        self.shell('test ! -e ' + self.remote + ' && test ! -L ' + self.remote +
            ' && mkdir -m 700 ' + self.remote,'create_private')
        self.helper_remote = self.remote + '/modem_peer'
        row = self.io.send(helper['binary']['path'],self.helper_remote,'apn579_send_peer')
        self.commands.append(receipt(self.io,row))
        require(row['exit_code'] == 0, 'actual helper transfer failed')
        self.shell('chmod 700 ' + self.helper_remote,'peer_mode')
        require(self.shell('sha256sum ' + self.helper_remote,'peer_hash').split() ==
            [helper['binary']['sha256'],self.helper_remote], 'actual guest/helper bytes differ')

    def request(self, action):
        require(action in ACTIONS and self.installed, 'finite installed public controller action required')
        op = secrets.token_hex(16)
        argv = ['aa','start','-b',BUNDLE,'-a','EntryAbility','--ps','run',self.run,
                '--ps','boot',self.io.boot_id,'--ps','operation',op,'--ps','action',action]
        self.shell(shlex.join(argv),'request_' + action.replace('-','_'))
        self.requests.append({'action':action,'operation':op,'command':len(self.commands)-1})
        self.save()
        return op

    def writer(self, path, row):
        pid = row['pid']
        require(type(pid) is int and pid > 1 and row['uid'] == self.uid and
            re.fullmatch('apn-sim579-' + self.run + '-' + str(pid) + r'-[a-f0-9]{32}\.jsonl',Path(path).name) and
            row['filesDir'] in ('/data/storage/el2/base/haps/entry/files',self.app_remote),
            'actual per-PID controller sandbox/UID differs')
        if path in self.writers:
            require(self.writers[path]['pid'] == pid and self.writers[path]['filesDir'] == row['filesDir'],
                    'original journal writer changed')
            return
        start = self.shell(starttime_shell(str(pid)),'writer_start').strip()
        require(re.fullmatch('[1-9][0-9]*',start), 'actual caller start ticks absent')
        require(self.shell(uids_shell(str(pid)),'writer_uids').split() == [str(self.uid)] * 4,
                'all four actual caller UIDs differ')
        sandbox = '/proc/' + str(pid) + '/root' + row['filesDir'] + '/' + Path(path).name
        raw = self.shell('test ! -L ' + shlex.quote(path) + ' && stat -c ' + shlex.quote('%d:%i:%u:%F') +
            ' ' + shlex.quote(path) + ' ' + shlex.quote(sandbox),'writer_inode')
        lines = raw.splitlines()
        require(len(lines) == 2 and lines[0] == lines[1] and
            re.fullmatch('[0-9]+:[1-9][0-9]*:' + str(self.uid) + ':regular file',lines[0]),
            'actual root/sandbox journal inode/UID differs')
        require(self.shell(starttime_shell(str(pid)),'writer_start_after').strip() == start,
                'actual writer generation changed during binding')
        require(not self.writers, 'controller must retain the generation remembering original APN state')
        self.writers[path] = {'pid':pid,'start_ticks':int(start),'uid':self.uid,'path':path,
                             'filesDir':row['filesDir'],'inode':lines[0]}

    def collect(self):
        marker = '__APN579_' + secrets.token_hex(16) + '__'
        script = ('for apn579_file in ' + self.app_remote + '/apn-sim579-' + self.run + '-*.jsonl; do '
            'test -f "$apn579_file" || continue; test ! -L "$apn579_file" || exit 1; '
            'printf "' + marker + 'BEGIN:%s\\n" "$apn579_file"; cat "$apn579_file" || exit 1; '
            'printf "\\n' + marker + 'END\\n"; done')
        raw = self.shell(script,'controller_journal')
        self.reads.append({'command':len(self.commands)-1,'marker':marker})
        pieces = raw.split(marker + 'BEGIN:')
        require(pieces[0] == '', 'unexpected actual journal prefix')
        for piece in pieces[1:]:
            path, tail = piece.split('\n',1)
            require(re.fullmatch(re.escape(self.app_remote + '/apn-sim579-' + self.run + '-') +
                r'[1-9][0-9]*-[a-f0-9]{32}\.jsonl',path) and tail.endswith('\n' + marker + 'END\n'),
                'complete fixed sandbox journal frame required')
            body = tail[:-len('\n' + marker + 'END\n')]
            require(len(body.encode()) < 16*1024*1024 and body.startswith(self.prefixes.get(path,'')),
                    'actual append-only caller journal changed/truncated')
            if not body.endswith('\n'): continue
            rows = [strict_json(line) for line in body.splitlines()]
            require(rows, 'empty journal proves no actual operation')
            previous = -1
            for seq,row in enumerate(rows,1):
                require(type(row) is dict and set(row) == ROW_KEYS and row['run'] == self.run and
                    row['boot'] == self.io.boot_id and type(row['seq']) is int and row['seq'] == seq and
                    re.fullmatch('[a-f0-9]{32}',row['operation']) and type(row['uptimeMs']) is int and
                    row['uptimeMs'] >= previous and type(row['code']) is int and type(row['value']) is str and
                    type(row['event']) is str, 'actual typed journal nonce/boot/sequence/raw fields differ')
                previous = row['uptimeMs']; self.writer(path,row)
            self.prefixes[path] = body; self.rows[path] = rows
        self.save()
        return [row for values in self.rows.values() for row in values]

    def completed(self, op, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = [r for r in self.collect() if r['operation'] == op]
            ends = [r for r in rows if r['event'] in ('done','error')]
            if ends:
                require(len(ends) == 1 and len([r for r in rows if r['event'] == 'begin']) == 1 and
                    rows[0]['event'] == 'begin' and rows[-1] == ends[0], 'one completed real public request required')
                return rows
            time.sleep(.2)
        raise ValueError('actual public request did not complete before deadline')

    def call(self, action, event, timeout=45):
        rows = self.completed(self.request(action),timeout)
        require(rows[-1]['event'] == 'done' and all(r['code'] == 0 for r in rows),
                'actual public action failed: ' + action + ': ' + json.dumps(rows))
        found = [r for r in rows if r['event'] == event]
        require(len(found) == 1, 'actual requested public result absent/duplicated')
        return found[0]

    def snapshot(self, active):
        row = self.call('inspect','snapshot')
        if active: return public_state(row,True)
        value = strict_json(row['value'])
        require(value['hasSim'] is False and value['active'] is False and value['state'] in (0,1) and
            value['accounts'] == [] and value['dataState'] in (-1,0), 'real no-card/account/data baseline required')
        return value

    def absent(self):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            rows = self.completed(self.request('inspect'))
            snapshots = [r for r in rows if r['event'] == 'snapshot']
            if rows[-1]['event'] == 'done' and len(snapshots) == 1:
                value = strict_json(snapshots[0]['value'])
                if value['hasSim'] is False and value['active'] is False and value['state'] == 1 and not value['accounts']:
                    public_state(snapshots[0],False)
                    require(value['defaultSlot'] == self.baseline['defaultSlot'] and value['dataState'] in (-1,0),
                            'public no-SIM default slot/data boundary changed')
                    return value
            time.sleep(.25)
        raise ValueError('actual removal never reached public SIM/account absent state')

    def no_sim_rejection(self):
        rows = self.completed(self.request('open-apn'))
        require(rows[-1]['event'] == 'error' and rows[-1]['code'] == -1 and rows[-1]['value'] == 'null' and
            not any(r['event'] in ('open.return','done') for r in rows),
            'actual no-SIM public APN call must reject for the real SIM/backend boundary')
        self.report.setdefault('no_sim_public_errors',[]).append(rows[-1])

    def native(self):
        cfg = self.io.environment['communications578_services']['ril']
        require(type(cfg) is dict and set(cfg) == {'name','init_path','process_name','libraries'} and
            cfg['name'] == 'riladapter_host' and re.fullmatch('[A-Za-z0-9_-]{1,64}',cfg['process_name']) and
            re.fullmatch(r'/(?:system|vendor)/etc/init/[A-Za-z0-9_.-]+\.cfg',cfg['init_path']) and
            type(cfg['libraries']) is list and set(cfg['libraries']) >= RIL_LIBS and
            all(re.fullmatch(r'lib[A-Za-z0-9_.-]+\.so',name) for name in cfg['libraries']),
            'exact packaged original RIL descriptor required')
        raw = self.shell('cat ' + shlex.quote(cfg['init_path']),'ril_init')
        rows = [r for r in strict_json(raw)['services'] if r['name'] == cfg['name']]
        require(len(rows) == 1 and rows[0]['uid'] == 'radio' and rows[0]['secon'] == 'u:r:riladapter_host:s0' and
            rows[0]['path'][0] == '/vendor/bin/hdf_devhost' and rows[0]['path'][-2:] == ['-n','riladapter_host'],
            'actual RIL init path/UID/domain differs')
        pid = self.shell('apn579_pid=$(pidof ' + cfg['process_name'] + '); apn579_rc=$?; '
            'test "$apn579_rc" -le 1 || exit "$apn579_rc"; printf "%s\\n" "$apn579_pid"','ril_pid').strip()
        require(re.fullmatch('[1-9][0-9]*',pid), 'one real RIL PID required')
        start = self.shell(starttime_shell(pid),'ril_start').strip()
        uids = self.shell(uids_shell(pid),'ril_uids').split()
        require(re.fullmatch('[1-9][0-9]*',start) and len(uids) == 4 and len(set(uids)) == 1 and
            re.fullmatch('[0-9]+',uids[0]), 'actual native RIL generation/UID absent')
        maps = self.shell('cat /proc/' + pid + '/maps','ril_maps')
        require(all(any(line.rstrip().endswith('/' + lib) for line in maps.splitlines()) for lib in cfg['libraries']),
                'actual reference RIL library mappings absent')
        cmdline = self.shell('od -An -v -tx1 /proc/' + pid + '/cmdline','ril_actual_argv')
        require(re.fullmatch('(?:[a-f0-9]{2})+',''.join(cmdline.split())), 'actual RIL command line bytes absent')
        require(self.shell('readlink /proc/' + pid + '/exe','ril_exe').strip() == '/vendor/bin/hdf_devhost' and
            self.shell('cat /proc/' + pid + '/attr/current','ril_domain').strip().rstrip('\x00') == rows[0]['secon'] and
            self.shell(starttime_shell(pid),'ril_start_after').strip() == start,
            'actual RIL executable/domain/generation differs')
        result = {'pid':int(pid),'start_ticks':int(start),'uid':int(uids[0]),'config':cfg,
                  'maps':maps,'init':raw,'cmdline_hex':cmdline,'boot_id':self.io.boot_id}
        self.services.append(result); self.save()
        return result

    def start_ril(self, before):
        self.shell('service_control start riladapter_host','ril_service_start')
        self.ril_stopped = False
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                after = self.native()
                if (after['pid'],after['start_ticks']) != (before['pid'],before['start_ticks']): return after
            except ValueError: pass  # raw failed transient observations remain in commands
            time.sleep(.25)
        raise ValueError('actual new RIL generation never appeared')

    def stop_ril(self):
        # Use the last actually observed generation, also on retry after a
        # stop/start command partially succeeded. Requiring a fresh live PID
        # before issuing the owned init stop would strand an already stopped
        # service and prevent cleanup from restoring it.
        before = getattr(self,'ril',self.original_ril)
        self.ril_touched = True
        self.shell('service_control stop riladapter_host','ril_service_stop')
        deadline = time.monotonic() + 20
        consecutive = 0
        while time.monotonic() < deadline:
            name = before['config']['process_name']
            raw = self.shell('apn579_pid=$(pidof ' + name + '); apn579_rc=$?; '
                'test "$apn579_rc" -le 1 || exit "$apn579_rc"; '
                'if test -z "$apn579_pid"; then echo ABSENT; else printf "%s\\n" "$apn579_pid"; fi',
                'ril_stopped_process_name').strip()
            try:
                gone = self.shell('if test -d /proc/' + str(before['pid']) + '; then ' +
                    starttime_shell(str(before['pid'])) + '; else echo ABSENT; fi','ril_stopped_generation').strip()
            except ValueError:
                time.sleep(.05)
                continue  # a disappearing proc file is retained and retried
            require(gone == 'ABSENT' or re.fullmatch('[1-9][0-9]*',gone), 'actual stopped PID generation malformed')
            absent = raw == 'ABSENT' and gone != str(before['start_ticks'])
            consecutive = consecutive + 1 if absent else 0
            if consecutive == 2:
                self.ril_stopped = True
                self.report.setdefault('stopped_ril_generations',[]).append(before)
                return
            time.sleep(.2)
        raise ValueError('actual RIL process/generation did not stop before transport release')

    def read_peer(self):
        raw = self.shell('cat ' + self.remote + '/peer.jsonl','peer_journal')
        require(raw.startswith(self.peer_prefix), 'actual peer raw prefix changed/truncated')
        if not raw.endswith('\n'): raise ValueError('peer journal row incomplete')
        rows = peer_rows(raw,self.run,self.io.boot_id,self.peer_pid,0)
        self.peer_prefix = raw
        self.peer_reads.append({'command':len(self.commands)-1,'rows':len(rows)})
        self.save()
        return rows

    def control(self, action):
        require(self.peer is not None and action in ('insert','remove','status','stop'), 'finite live peer control required')
        operation = secrets.token_hex(16)
        payload = (operation + '\t' + action + '\n').encode()
        observed = self.io.write_stdin(self.peer,payload)
        require(observed['key'] == self.peer and observed['boot_id'] == self.io.boot_id and
            load_ref(observed['raw']) == payload, 'actual held peer stdin receipt differs')
        self.controls.append({'action':action,'operation':operation,'receipt':observed})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            rows = [r for r in self.read_peer() if r['operation_id'] == operation]
            controls = [r for r in rows if r['kind'] == 'control']
            target = 'backend' if action == 'status' else 'closed' if action == 'stop' else 'tx'
            effects = [r for r in rows if r['kind'] == target]
            if controls and effects:
                require(len(controls) == len(effects) == 1 and bytes.fromhex(controls[0]['hex']) == action.encode() and
                    controls[0]['seq'] < effects[0]['seq'], 'real finite backend action/ordering differs')
                if action in ('insert','remove'):
                    expected = b'\r\n^SIMST: ' + (b'1' if action == 'insert' else b'0') + b'\r\n'
                    require(bytes.fromhex(effects[0]['hex']) == expected, 'actual SIM URC bytes differ')
                return effects[0]
            time.sleep(.1)
        raise ValueError('actual owned peer did not observe control/effect')

    def open_peer(self):
        require(self.shell('getenforce','enforcing').strip() == 'Enforcing', 'actual global SELinux enforcing required')
        self.shell('dmesg','kernel_before')
        require(self.shell('param get const.sys.radio.vendorlib.path','vendor_param').strip() == 'libril_vendor.z.so',
                'actual finite reference vendor SONAME differs')
        path = self.shell('param get const.telephony.ril.attty.path','at_path_param').strip()
        require(path == '/dev/ttyUSB0', 'actual QEMU product AT-path parameter must be present and fixed')
        self.shell('test ! -e ' + path + ' && test ! -L ' + path,'original_at_absent')
        before = self.native(); self.original_ril = before
        self.report['original_ril'] = before
        # Start absent. The only later insertion is the owned peer's real URC.
        script = ('umask 077; set -C; exec ' + self.helper_remote + ' ' + self.run + ' ' + self.io.boot_id +
                  ' > ' + self.remote + '/peer.jsonl 2> ' + self.remote + '/peer.stderr')
        self.peer = self.io.spawn_guest(script,'apn579_peer_transport')
        deadline = time.monotonic() + 15
        ready = None
        while time.monotonic() < deadline:
            raw = self.shell('if test -f ' + self.remote + '/peer.jsonl; then cat ' + self.remote + '/peer.jsonl; fi','peer_ready')
            if raw.endswith('\n') and raw:
                ready = strict_json(raw.splitlines()[0]); break
            time.sleep(.1)
        require(ready is not None and ready['kind'] == 'ready' and type(ready['pid']) is int and
            ready['pid'] > 1 and ready['uid'] == 0, 'actual created peer PTY readiness absent')
        self.peer_pid = ready['pid']; pid = str(self.peer_pid)
        self.peer_start = self.shell(starttime_shell(pid),'peer_start').strip()
        require(re.fullmatch('[1-9][0-9]*',self.peer_start) and
            self.shell(uids_shell(pid),'peer_uids').split() == ['0'] * 4 and
            self.shell('readlink /proc/' + pid + '/exe','peer_exe').strip() == self.helper_remote,
            'actual root peer executable/UID/start differs')
        raw = self.shell('od -An -v -tx1 /proc/' + pid + '/cmdline','peer_argv')
        encoded = ''.join(raw.split())
        require(re.fullmatch('(?:[a-f0-9]{2})+',encoded) and bytes.fromhex(encoded).split(b'\0') ==
            [self.helper_remote.encode(),self.run.encode(),self.io.boot_id.encode(),b''], 'actual peer argv/run/boot differs')
        self.target = bytes.fromhex(self.read_peer()[0]['hex']).decode('ascii')
        self.report['peer_identity'] = {'pid':self.peer_pid,'start_ticks':int(self.peer_start),'uid':0,'pty':self.target}
        labels = self.shell('ls -Zd /dev/pts ' + self.target,'pty_labels')
        require('u:object_r:dev_pts_file:s0' in labels and 'u:object_r:devpts:s0' in labels,
                'actual PTY directory/device policy types differ')
        self.shell('chown ' + str(before['uid']) + ':' + str(before['uid']) + ' ' + self.target +
            ' && chmod 600 ' + self.target,'pty_radio_dac')
        self.pty_stat = self.shell('stat -c ' + shlex.quote('%d:%i:%u:%g:%a:%F') + ' ' + self.target,'pty_inode').strip()
        require(re.fullmatch('[0-9]+:[1-9][0-9]*:' + str(before['uid']) + ':' + str(before['uid']) +
            ':600:character special file',self.pty_stat), 'actual radio PTY inode/DAC differs')
        # Keep the reader stopped while changing the sole owned transport path.
        self.stop_ril()
        self.link = path
        self.shell('test ! -e ' + path + ' && test ! -L ' + path + ' && ln -s ' + self.target + ' ' + path,'bind_at_path')
        self.link_stat = self.shell('stat -c ' + shlex.quote('%d:%i:%u:%F') + ' ' + path,'owned_link_inode').strip()
        require(re.fullmatch('[0-9]+:[1-9][0-9]*:0:symbolic link',self.link_stat), 'actual owned AT symlink required')
        require('u:object_r:dev_file:s0' in self.shell('ls -Zd ' + path,'at_link_label'), 'actual AT symlink policy type differs')
        self.ril = self.start_ril(before)
        self.fd_binding()
        self.report['bound_absent'] = self.absent()

    def fd_binding(self):
        deadline = time.monotonic() + 30
        last = None
        while time.monotonic() < deadline:
            try: return self._fd_binding_once()
            except ValueError as error: last = str(error)
            time.sleep(.2)
        raise ValueError('actual owned RIL PTY reader never stabilized: ' + str(last))

    def _fd_binding_once(self):
        current = self.native()
        require((current['pid'],current['start_ticks']) == (self.ril['pid'],self.ril['start_ticks']),
                'actual RIL reader generation changed')
        pid = str(current['pid'])
        script = ('readlink -f ' + self.link + '; apn579_count=0; for apn579_fd in /proc/' + pid + '/fd/*; do '
            'apn579_target=$(readlink -f "$apn579_fd") || exit 1; if test "$apn579_target" = ' + self.target + '; then '
            'printf "%s\\n" "$apn579_target"; apn579_count=$((apn579_count + 1)); fi; done; test "$apn579_count" = 1')
        require(self.shell(script,'ril_real_reader_fd').splitlines() == [self.target,self.target],
                'actual RIL fd is not the one owned PTY slave')
        require(self.shell('stat -c ' + shlex.quote('%d:%i:%u:%g:%a:%F') + ' ' + self.target,'pty_inode_after').strip() == self.pty_stat and
            self.shell(starttime_shell(str(self.peer_pid)),'peer_generation_after').strip() == self.peer_start,
            'actual PTY inode/DAC or held peer generation changed')

    def activate(self):
        self.card_present = True  # insertion intent retained before stdin can fail
        self.control('insert')
        self.activation_intent = True
        deadline = time.monotonic() + 90
        last = []
        while time.monotonic() < deadline:
            last = self.completed(self.request('select-default'))
            snapshots = [r for r in last if r['event'] == 'snapshot']
            if last[-1]['event'] == 'done' and len(snapshots) == 1:
                try:
                    actual = public_state(snapshots[0],True)
                    self.report['active_public'] = actual
                    self.report['wire_initialization'] = readiness(self.read_peer())
                    self.fd_binding(); return
                except ValueError: pass  # not a pass; every real incomplete attempt remains journalled
            time.sleep(.5)
        raise ValueError('real RIL/SIMManager/account/default-slot initialization incomplete: ' + json.dumps(last))

    def layout(self, label):
        before = len(self.io.receipts)
        tree,path = self.io.ui.layout(bundle=PROVIDER,label='apn579_' + label)
        self.ui.append({'kind':'layout','layout':reference(path),'original_commands':
                        [self.io.ref_receipt(r) for r in self.io.receipts[before:]]})
        self.save(); return tree

    def select_existing(self, profile):
        require(type(profile) is int and profile >= 0, 'actual existing profile id required')
        self.modal_open = True
        self.call('open-apn','open.return')
        deadline = time.monotonic() + 30
        scrolls = 0
        while time.monotonic() < deadline:
            try:
                tree = self.layout('existing_profile')
                node = select_node(tree,PROVIDER,identifier='system-apn-select-' + str(profile),clickable=True)
                require(node['attributes'].get('enabled') == 'true', 'actual existing APN control disabled')
                x,y,w,h = node['rect']
                self.shell('uitest uiInput click ' + str(x+w//2) + ' ' + str(y+h//2),'select_packaged_cmnet')
                self.ui.append({'kind':'existing_profile_selection','profile':profile,'node':node,
                                'layout':self.ui[-1]['layout'],'command':len(self.commands)-1})
                return
            except (LayoutNotReady,NodeNotReady):
                if scrolls < 12:
                    try:
                        listing = select_node(self.layout('list_geometry'),PROVIDER,identifier='system-apn-list')
                        x,y,w,h = listing['rect']; require(h >= 80, 'actual APN list geometry too small')
                        self.shell('uitest uiInput swipe ' + ' '.join(map(str,[x+w//2,y+h*3//4,x+w//2,y+h//4])) + ' 500','scroll_packaged_apn')
                        self.ui.append({'kind':'scroll','node':listing,'command':len(self.commands)-1}); scrolls += 1
                    except (LayoutNotReady,NodeNotReady): pass
                time.sleep(.2)
        raise ValueError('actual CallSetting existing default APN control never appeared')

    def close_modal(self):
        # Killing only this audit caller releases its real UI extension session.
        # The public controller retaining the preference must stay alive, so
        # use the packaged modal's normal Back path instead.
        self.shell('uitest uiInput keyEvent Back','close_apn_modal')
        deadline = time.monotonic() + 20
        consecutive = 0
        while time.monotonic() < deadline:
            visible = True
            try:
                tree = self.layout('modal_after_back')
                select_node(tree,PROVIDER,identifier='system-apn-settings-navigation')
            except (LayoutNotReady,NodeNotReady): visible = False
            ams = self.shell('aa dump -a -u 100','modal_ams_after_back')
            require(re.search(r'^User ID #100\s*$',ams,re.M) and 'AppRunningRecords:' in ams,
                    'actual complete account100 AMS dump required')
            absent = not re.search(r'(?<![A-Za-z0-9_])GeneralCallSettingDialogAbility(?![A-Za-z0-9_])',ams)
            consecutive = consecutive + 1 if not visible and absent else 0
            if consecutive == 2:
                self.modal_open = False; return
            time.sleep(.2)
        raise ValueError('actual APN modal remains after Back')

    def preferred_baseline(self):
        # Observe the actual installed default resource, not only host source.
        raw = self.shell('cat /system/etc/telephony/pdp_profile.json','packaged_apn_resource')
        resource = strict_json(raw)
        defaults = [r for r in resource['operator_infos'] if r.get('mcc') == '460' and r.get('mnc') == '00' and
                    r.get('apn') == 'cmnet' and 'default' in r.get('apn_types','').split(',')]
        require(len(defaults) == 1, 'actual packaged 460/00 default cmnet resource missing/ambiguous')
        self.report['packaged_apn_resource'] = {'command':len(self.commands)-1,'selected':defaults[0]}
        self.original_apn = canonical(strict_json(self.call('apn-remember','apn')['value']))
        self.restore_intent = True
        require(self.original_apn['active'] is True and self.original_apn['numeric'] == '46000' and
            self.original_apn['slot'] == 0 and self.original_apn['simId'] ==
            self.report['active_public']['accounts'][0]['simId'], 'actual active APN account differs from public SIM chain')
        candidates = [r for r in self.original_apn['rows'] if r['mcc'] == '460' and r['mnc'] == '00' and
            r['apn'] == 'cmnet' and r['name'] == defaults[0]['operator_name'] and 'default' in r['types'].split(',')]
        require(len(candidates) == 1 and type(candidates[0]['id']) is int and candidates[0]['id'] >= 0,
                'real service did not load one packaged default CMNET row; no direct insert fallback')
        if self.original_apn['preferred'] >= 0:
            require(any(r['id'] == self.original_apn['preferred'] for r in self.original_apn['rows']),
                    'original selected APN id is not restorable')
            self.ready_apn = self.original_apn
        else:
            require(self.original_apn['preferred'] == -1, 'unrecognized preferred APN state')
            self.select_existing(candidates[0]['id'])
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                current = canonical(strict_json(self.call('apn-read','apn')['value']))
                expected = dict(self.original_apn,preferred=candidates[0]['id'])
                if current == expected: self.ready_apn = current; break
                time.sleep(.2)
            require(self.ready_apn is not None, 'actual CallSetting selection did not establish the preferred APN')
            self.close_modal()
        self.report.update(original_apn=self.original_apn,apps_precondition=self.ready_apn)
        self.save()

    def enter(self):
        self.prepare()
        self.baseline = self.snapshot(False)
        self.report['original_no_sim'] = self.baseline
        # Only slot0 has a finite physical virtual modem; changing an unrelated
        # or absent slot cannot be reversed with this public data API.
        require(self.baseline['defaultSlot'] == 0, 'original public default slot must be0 before any card mutation')
        self.no_sim_rejection()
        self.open_peer()
        self.activate()
        self.preferred_baseline()
        self.boot(); return self

    def join_apps(self, result, path):
        actual = strict_json(load_ref(reference(path)).decode())
        require(actual == result and actual['schema'] == 'actual-apps578-runtime/v1' and
            actual['case'] == 'apn' and actual['boot_id'] == self.io.boot_id and
            actual['archive_sha256'] == self.io.archive_sha256, 'original immutable Apps APN result differs')
        self.apps = result
        self.report['apps'] = reference(path)
        if actual.get('apn',{}).get('baseline') is not None:
            require(canonical(actual['apn']['baseline']) == self.ready_apn,
                    'Apps did not consume the genuine activated/default/preferred APN baseline')
        require(actual['status'] == 'observed' and actual['failures'] == [] and actual['cleanup_verified'] is True and
            actual['apn']['positive_completed'] is True, 'original Apps APN CRUD/cleanup did not complete')
        current = canonical(strict_json(self.call('apn-read','apn')['value']))
        require(current == self.ready_apn, 'original Apps UI cleanup left APN mutations')
        self.report['apps_joined'] = True; self.save()

    def cleanup(self):
        if self.cleaned: return reference(self.output / 'evidence.json')
        failures = []
        def step(name, action):
            try: action()
            except Exception as error: failures.append(name + ': ' + str(error))

        if self.modal_open: step('owned APN modal Back/release',self.close_modal)
        if self.restore_intent:
            def restore():
                rows = self.completed(self.request('restore-preference'))
                require(rows[-1]['event'] == 'done' and not any(r['event'] == 'error' for r in rows),
                        'original public preferred APN restoration failed')
                values = [r for r in rows if r['event'] == 'apn']
                returned = [r for r in rows if r['event'] == 'restore.return']
                require(len(values) == len(returned) == 1 and strict_json(returned[0]['value']) is True and
                    canonical(strict_json(values[0]['value'])) == self.original_apn,
                    'real preference/catalog did not return to pre-UI account baseline')
                self.report['restored_apn'] = canonical(strict_json(values[0]['value']))
                self.restore_intent = False
            step('public APN restore',restore)
        if self.activation_intent and self.card_present:
            def restore_default():
                public_state(self.call('restore-default','snapshot'),True)
                self.report['default_restored'] = True
            step('public default slot restore',restore_default)
            step('public deactivate',lambda: self.call('deactivate','deactivate.return'))
        if self.peer is not None:
            def remove():
                self.control('remove')
                self.report['removed_public'] = self.absent()
                self.no_sim_rejection()
                self.card_present = False
            step('real card removal/public no-SIM',remove)
            # Stop the reader before closing its PTY. Even failed public
            # cleanup cannot leave an active original reader on a dead peer.
            if self.ril_touched and not self.ril_stopped: step('stop RIL reader',self.stop_ril)
            def stop_peer():
                # If public observation failed, remove still must precede stop;
                # its failure stays a failure, never becomes a passing boundary.
                if self.card_present: self.control('remove')
                closed = self.control('stop')
                row = self.io.wait(self.peer,10)
                require(row['boot_id'] == self.io.boot_id and row['exit_code'] == 0 and
                    row.get('transport_exit_code') == 0 and row.get('timed_out') is False and
                    load_ref(row['stdout_ref']).decode() == row['stdout'] and
                    load_ref(row['stderr_ref']).decode() == row['stderr'], 'actual owned peer did not exit zero')
                self.report['peer_wait'] = {'argv':row['argv'],'exit_code':row['exit_code'],
                    'transport_exit_code':row['transport_exit_code'],'stdout':row['stdout_ref'],
                    'stderr':row['stderr_ref'],'transport_stdout':row['transport_stdout_ref'],'boot_id':row['boot_id']}
                rows = self.read_peer()
                require(rows[-1] == closed and bytes.fromhex(closed['hex']).decode() == self.target,
                        'actual closed peer row/PTY differs')
                # The original held HDC child is WNOWAIT-owned. The exited
                # guest helper itself must no longer have a /proc generation.
                self.shell('test ! -d /proc/' + str(self.peer_pid),'peer_absent')
                self.peer = None
            step('held peer stop',stop_peer)
        if self.link is not None:
            def unbind():
                require(self.link_stat is not None, 'link creation identity was not established; preserve unknown path')
                raw = self.shell('stat -c ' + shlex.quote('%d:%i:%u:%F') + ' ' + self.link +
                    ' && readlink ' + self.link,'owned_link_before_remove')
                require(raw.splitlines() == [self.link_stat,self.target], 'AT path ownership changed; preserved')
                self.shell('rm ' + self.link + ' && test ! -e ' + self.link + ' && test ! -L ' + self.link,'unbind_at_path')
                self.link = None
            step('owned AT symlink release',unbind)
        if self.ril_touched and self.link is None:
            def restore_ril():
                if not self.ril_stopped: self.stop_ril()
                prior = getattr(self,'ril',self.original_ril)
                self.report['restored_ril'] = self.start_ril(prior)
                self.ril_touched = False
            step('original RIL restart',restore_ril)
        if self.baseline is not None and self.installed and self.peer is None and self.link is None:
            def restored_no_sim():
                value = self.snapshot(False)
                require(value['defaultSlot'] == self.baseline['defaultSlot'], 'original no-SIM public slot changed')
                self.report['final_no_sim'] = value
                self.no_sim_rejection()
            step('original public no-SIM boundary',restored_no_sim)
        if self.installed:
            def uninstall():
                self.shell('aa force-stop ' + BUNDLE,'controller_stop',allow_failure=True)
                raw = self.shell('bm uninstall -n ' + BUNDLE,'controller_uninstall')
                require('uninstall bundle successfully' in raw.lower(), 'actual controller uninstall did not succeed')
                assert_bundles_absent(self.shell('bm dump -a','controller_bms_absent'),[BUNDLE])
                require(self.uid is not None, 'partially installed controller UID unknown; cannot claim full cleanup')
                for index in range(2):
                    raw, observed = capture_snapshot(self.shell,'controller_uid_absent_' + str(index),
                        self.io.boot_id,mode='uid',uid=self.uid,bundle=BUNDLE)
                    require(observed['processes'] == {}, 'actual controller UID/bundle processes remain')
                    if index == 0: time.sleep(.25)
                self.installed = False
            step('public controller uninstall/complete UID absence',uninstall)
        if self.remote is not None:
            def preserve_peer_stderr():
                self.shell('if test -f ' + self.remote + '/peer.stderr; then cat ' + self.remote + '/peer.stderr; fi',
                           'peer_native_stderr')
                self.report['peer_native_stderr_command'] = len(self.commands)-1
            step('native peer diagnostic stderr',preserve_peer_stderr)
        if self.remote is not None and self.peer is None and self.link is None:
            def remove_private():
                require(self.shell('stat -c ' + shlex.quote('%u:%a:%F') + ' ' + self.remote,'owned_private_mode').strip() ==
                    '0:700:directory', 'owned private directory metadata changed')
                self.shell('test ! -L ' + self.remote + ' && rm -f ' + ' '.join(self.remote + '/' + name
                    for name in ('modem_peer','peer.jsonl','peer.stderr')) + ' && rmdir ' + self.remote,'private_release')
                self.remote = None
            step('finite private files release',remove_private)
        step('final kernel AVC log',lambda: self.shell('dmesg','kernel_after'))
        step('original held boot',self.boot)
        self.cleanup_errors = failures
        self.report['failures'] = ([self.error] if self.error else []) + failures
        self.cleaned = not failures and not self.installed and self.peer is None and self.link is None and self.remote is None and not self.ril_touched
        self.report['cleanup_complete'] = self.cleaned
        self.report['runtime_pass'] = self.cleaned and self.report['apps_joined'] and not self.report['failures']
        self.save()
        require(self.cleaned, 'actual virtual SIM cleanup failed: ' + '; '.join(failures))
        return reference(self.output / 'evidence.json')


@contextmanager
def virtual_sim(root_io):
    """Fixed context: original no-SIM -> real modem/public/UI -> reverse cleanup."""
    fixture = VirtualSim(root_io)
    try:
        fixture.enter()
        yield fixture
    except Exception as error:
        fixture.error = str(error)
        raise
    finally:
        fixture.cleanup()
