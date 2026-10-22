"""L22 normal runtime producer on the ORIGINAL APN OwnedIO and peer only.

Root calls run after the original APN whole CRUD join, inside virtual_sim().
No Owner, build-tree mutation, service registry publisher, second AT peer, or
resource launcher exists here. The normal original builder compiles real HAPs.
Every result remains an observation until independent closed-IO replay.
"""
from pathlib import Path
import json
import re
import secrets
import shlex
import sys
import time
import zipfile

from capability578_owned_io import require, reference
from settings_idle579_bindings import receipt, load_ref
from guest_process_identity import identity_shell, starttime_shell
from hap_identity_binding import strict_json, bms_application_identity
from batch_media_knowledge_suite import assert_bundles_absent
from batch_network_openvpn_runtime_collect import capture_snapshot
from telephony579_project import CASE, ROLES, bundle, permissions, source_files
from telephony579_raw import caller_rows, terminal, packet_pair
from telephony579_tun import product_input, handover, service_script, service_observation

CONTROLS = ('l22-on','l22-answer','l22-incoming','l22-carrier-drop','l22-register',
    'l22-sms-error','l22-sms-clear','l22-sms-report','l22-dial-error','l22-dial-timeout','l22-status','l22-off')
NETWORK = 'ip address show; ip route show table all; ip rule show'
REMAINING = (
    'Root policy review of current selected product carrier IMS provider/registration and genuine RTT session/messages; proposal is not approval',
    'Original independent explicit 5A URC/false-reset full contract remains in the communications actor and must be joined',
)


class Unsettled(RuntimeError):
    """Original IO may still own live async/native state: reverse cleanup only."""


class CompletedBusinessFailure(ValueError):
    """An actual completed API boundary differed; no cleanup claim implied."""


class Transactions:
    def __init__(self, io, modem):
        require(modem.io is io and modem.peer is not None and modem.report['apps_joined'] is True and
            not modem.cleaned and modem.card_present and modem.ready_apn is not None,
            'original successful whole Apps APN context and its held peer required')
        self.io, self.modem = io, modem
        self.output = Path(io.output) / 'telephony579-whole'
        self.output.mkdir(exist_ok=False)
        self.roles, self.installed, self.writers, self.prefixes, self.rows = {}, [], {}, {}, {}
        self.commands, self.reads, self.requests, self.controls, self.steps = [], [], [], [], []
        self.business_intent = False; self.data_baseline = None; self.cleaned = False
        self.report = {'schema':'actual-telephony579-transactions/v1', 'run_id':io.run_id,
            'boot_id':io.boot_id,'archive_sha256':io.archive_sha256,
            'original_apn_output':str(modem.output / 'evidence.json'),
            'peer_key':modem.peer,'peer_identity':dict(modem.report['peer_identity']),
            'native_helper':modem.helper,'commands':self.commands,'reads':self.reads,
            'requests':self.requests,'controls':self.controls,'steps':self.steps,
            'roles':self.roles,'writers':self.writers,'cleanup':[], 'cleanup_complete':False,
            'failures':[],'remaining':list(REMAINING),'whole_L22_pass':False,
            'new_package_acceptance':False,'source_candidate_only':False}
        io.register_cleanup(self.cleanup)
        self.save()

    def save(self):
        (self.output / 'evidence.json').write_text(json.dumps(self.report,indent=2) + '\n')

    def shell(self, script, label, *, allow_failure=False):
        row = self.io.shell(script,'l22_' + label,allow_failure=True)
        self.commands.append(receipt(self.io,row,script)); self.save()
        if not allow_failure: require(row['exit_code'] == 0,'actual L22 guest command failed: ' + label)
        return row['stdout']

    def command(self, argv, label):
        row = self.io.command(argv,'l22_' + label,timeout=90,allow_failure=True)
        self.commands.append(receipt(self.io,row)); self.save()
        require(row['exit_code'] == 0,'actual L22 HDC command failed: ' + label)
        return row['stdout']

    def prepare(self):
        require(self.shell('cat /proc/sys/kernel/random/boot_id','boot').strip() == self.io.boot_id,
            'original boot changed')
        self.modem.fd_binding()
        native,guest,digest = product_input({'telephony579':self.io.telephony579_product},self.io.archive_sha256,
            self.io.guest.report['test_environment']['product'])
        self.report['native_product_export'] = self.io.telephony579_product['product_export']
        self.report['native_library_path'] = guest
        self.report['native_library_sha256'] = digest
        self.save()
        self.report['network_before_command'] = len(self.commands)
        self.report['network_before'] = self.shell(NETWORK,'network_before')
        self.shell('test ! -e /sys/class/net/usb0 && test ! -L /sys/class/net/usb0','usb0_absent')
        value = self.io.prepare_callers('telephony579',CASE,self.io.run_id,ROLES,{})
        require(value['case'] == CASE and value['run_id'] == self.io.run_id and
            value['boot_id'] == self.io.boot_id and set(value['callers']) == set(ROLES),
            'actual original serialized builder returned another caller set')
        for role in ROLES:
            item = value['callers'][role]
            require(item['bundle'] == bundle(CASE,role) and item['build_commands'] and
                item['sign_commands'] and item['verify_commands'], 'actual compile/sign/verify missing')
            for key in ('unsigned','signed','signing','verified_profile'): load_ref(item[key])
            for path,text in source_files(CASE,self.io.run_id,role,{}).items():
                require((Path(item['project']) / path).read_bytes() == text.encode(),
                    'actual compiled fixture source differs')
            profile = strict_json(load_ref(item['verified_profile']).decode())
            require(profile['bundle-info']['bundle-name'] == item['bundle'] and
                profile['bundle-info']['apl'] == ('normal' if role == 'ordinary' else 'system_core') and
                profile['bundle-info']['app-feature'] == ('hos_normal_app' if role == 'ordinary' else 'hos_system_app') and
                profile['debug-info']['device-ids'] == [self.io.udid] and
                profile['acls']['allowed-acls'] == permissions(CASE,role) and
                profile['permissions']['restricted-permissions'] == permissions(CASE,role),
                'verified actual role authority differs; never elevate normal caller')
            with zipfile.ZipFile(item['unsigned']['path']) as before, zipfile.ZipFile(item['signed']['path']) as after:
                names = before.namelist()
                require(len(names) == len(set(names)) and len(after.namelist()) == len(set(after.namelist())) and
                    set(after.namelist()) == set(names) | {'.pages.info'} and before.read('ets/modules.abc') and
                    all(before.read(n) == after.read(n) for n in names), 'actual signer changed fixture payload')
            self.roles[role] = {'prepared':item,'identities':[],'generations':[]}
        self.save()
        for role in ROLES: self.install(role)
        require(len({r['identity']['uid'] for r in self.roles.values()}) == len(ROLES) and
            len({r['identity']['token_id'] for r in self.roles.values()}) == len(ROLES),
            'three actual independent HAP UID/token roles required')
        for role in ROLES: self.request(role,'identity')
        state = self.state()
        self.data_baseline = state['isCellularDataEnabled']
        require(type(self.data_baseline) is bool and state['getCallState'] == 0 and
            state['getCellularDataState'] in (-1,0), 'actual pre-transaction idle/disconnected baseline required')
        self.report['data_baseline'] = self.data_baseline; self.save()

    def bms(self, role):
        entry = self.roles[role]; name = entry['prepared']['bundle']
        index = len(self.commands); raw = self.shell('bm dump -n ' + name,'bms_' + role)
        identity = bms_application_identity(raw,name); doc = strict_json(raw[raw.index('{'):])
        require(doc['applicationInfo']['isSystemApp'] is (role != 'ordinary') and
            doc['applicationInfo']['appPrivilegeLevel'] == ('normal' if role == 'ordinary' else 'system_core') and
            set(doc['reqPermissions']) == set(permissions(CASE,role)), 'actual BMS role/permissions differ')
        require('identity' not in entry or entry['identity'] == identity,'actual BMS UID/token changed')
        entry['identity'] = identity; entry['identities'].append({'command':index,'identity':identity})
        return doc

    def install(self, role):
        entry = self.roles[role]; name = entry['prepared']['bundle']
        assert_bundles_absent(self.shell('bm dump -a','before_install_' + role),[name])
        self.installed.append(role); self.save()  # partial installation already has cleanup intent
        raw = self.command([self.io.hdc,'-t',self.io.target,'install',entry['prepared']['signed']['path']], 'install_' + role)
        require('install bundle successfully' in raw.lower(),'actual caller installation failed')
        doc = self.bms(role)
        paths = [m['hapPath'] for m in doc['hapModuleInfos'] if m.get('hapPath')]
        require(len(paths) == 1 and paths[0].startswith('/data/app/'),'one actual installed HAP path required')
        entry['installed_hash_command'] = len(self.commands)
        require(self.shell('sha256sum ' + shlex.quote(paths[0]),'hap_bytes_' + role).split() ==
            [entry['prepared']['signed']['sha256'],paths[0]], 'actual installed signed HAP bytes differ')
        entry['remote'] = '/data/app/el2/100/base/' + name + '/haps/entry/files'
        self.shell('for l22_file in ' + entry['remote'] + '/telephony579-' + self.io.run_id + '-*.jsonl; do '
            'test ! -e "$l22_file" && test ! -L "$l22_file" || exit 1; done','fresh_journals_' + role)
        self.save()

    def collect(self, role):
        entry = self.roles[role]; self.bms(role)
        marker = '__L22_' + secrets.token_hex(16) + '__'
        script = ('for l22_file in ' + entry['remote'] + '/telephony579-' + self.io.run_id + '-*.jsonl; do '
            'test -f "$l22_file" || continue; test ! -L "$l22_file" || exit 1; '
            'printf "' + marker + 'BEGIN:%s\\n" "$l22_file"; cat "$l22_file" || exit 1; '
            'printf "\\n' + marker + 'END\\n"; done')
        index = len(self.commands); raw = self.shell(script,'journal_' + role)
        self.reads.append({'role':role,'command':index,'marker':marker}); self.save()
        parts = raw.split(marker + 'BEGIN:'); require(parts[0] == '','unexpected actual raw frame prefix')
        for part in parts[1:]:
            path,tail = part.split('\n',1)
            match = re.fullmatch(re.escape(entry['remote'] + '/telephony579-' + self.io.run_id + '-') + r'([1-9][0-9]*)\.jsonl',path)
            require(match is not None and tail.endswith('\n' + marker + 'END\n'),'actual complete per-PID journal frame required')
            text = tail[:-len('\n' + marker + 'END\n')]
            require(text.startswith(self.prefixes.get(path,'')),'actual caller raw prefix changed')
            if not text.endswith('\n'): continue
            parsed = caller_rows(text,self.io.run_id,self.io.boot_id,role,entry['identity']['uid'],int(match[1]))
            if path not in self.writers:
                self.bind_writer(role,path,parsed[0])
            else:
                writer = self.writers[path]
                if not writer.get('exited'):
                    require(self.shell(starttime_shell(str(writer['pid'])),'live_writer_' + role).strip() == str(writer['start_ticks']),
                        'actual current journal generation disappeared or PID reused')
                elif writer.get('sealing'):
                    writer['seal_inode_command'] = len(self.commands)
                    require(self.shell('test ! -L ' + shlex.quote(path) + ' && stat -c ' + shlex.quote('%d:%i:%u:%F') +
                        ' ' + shlex.quote(path),'sealed_inode_' + role).strip() == writer['inode'],
                        'exited original journal inode/UID changed before final raw sealing')
                    writer['sealing'] = False
                elif text != self.prefixes[path]: raise ValueError('sealed exited original journal was appended')
            self.prefixes[path] = text; self.rows[path] = parsed
        self.save()
        return [row for path,rows in self.rows.items() if path.startswith(entry['remote'] + '/') for row in rows]

    def bind_writer(self, role, path, row):
        entry = self.roles[role]; index = len(self.commands)
        raw = self.shell(identity_shell(entry['prepared']['bundle']),'writer_' + role)
        fields = raw.split(); require(len(fields) == 6 and all(re.fullmatch('[0-9]+',n) for n in fields),
            'actual complete process identity required')
        pid,ticks,*uids = map(int,fields)
        require(pid == row['pid'] and ticks > 0 and uids == [entry['identity']['uid']]*4,
            'actual caller PID/four UIDs/start differs')
        sandbox = '/proc/' + str(pid) + '/root' + row['files_dir'] + '/' + Path(path).name
        inode_index = len(self.commands)
        stat = self.shell('test ! -L ' + shlex.quote(path) + ' && stat -c ' + shlex.quote('%d:%i:%u:%F') +
            ' ' + shlex.quote(path) + ' ' + shlex.quote(sandbox),'journal_inode_' + role)
        lines = stat.splitlines()
        require(len(lines) == 2 and lines[0] == lines[1] and re.fullmatch('[0-9]+:[1-9][0-9]*:' + str(uids[0]) + ':regular file',lines[0]),
            'actual sandbox/root path is not the same inode and UID')
        final_index = len(self.commands)
        require(self.shell(starttime_shell(str(pid)),'writer_after_' + role).strip() == str(ticks), 'caller generation changed during journal bind')
        self.writers[path] = {'role':role,'path':path,'pid':pid,'start_ticks':ticks,'uid':uids[0],
            'identity_command':index,'inode_command':inode_index,'after_command':final_index,'inode':lines[0],'exited':False}
        entry['generations'].append(path)

    def issue(self, role, action, **parameters):
        require(role in self.installed and action in ('identity','state','observe','unobserve','dial','answer','hangup',
            'sms','data-on','data-off','udp','quiet','restore','invalid-dial','invalid-sms','invalid-data'), 'fixed installed actual caller/action required')
        request = {'run_id':self.io.run_id,'boot_id':self.io.boot_id,'operation_id':secrets.token_hex(16),'action':action,**parameters}
        script = shlex.join(['aa','start','-b',self.roles[role]['prepared']['bundle'],'-a','EntryAbility',
            '--ps','request',json.dumps(request,separators=(',',':'),allow_nan=False)])
        index = len(self.commands); self.shell(script,'request_' + role + '_' + action.replace('-','_'))
        self.requests.append({'role':role,'request':request,'command':index}); self.save()
        return request

    def wait(self, role, request, timeout=45):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            rows = self.collect(role)
            selected = [r for r in rows if r['operation_id'] == request['operation_id']]
            if any(r['kind'] == 'end' for r in selected): return terminal(rows,request)
            time.sleep(.2)
        raise Unsettled('actual public request has no terminal completion: ' + role + '/' + request['action'])

    def request(self, role, action, expect=0, **parameters):
        rows = self.wait(role,self.issue(role,action,**parameters))
        errors = [r for r in rows if r['kind'] == 'error']
        if any(r['kind'] in ('cleanup-error','listener-off-error') for r in rows) or any(
            r['kind'] == 'sms-completion' and r['value'].get('timeout') is True for r in rows):
            raise Unsettled('actual listener/socket/restore/SMS async cleanup is not settled: ' + role + '/' + action)
        if action in ('observe','unobserve','restore') and errors:
            raise Unsettled('actual owned listener/restore operation failed: ' + action)
        okay = ((expect == 0 and not errors and len([r for r in rows if r['kind'] == 'return']) == 1) or
            (expect != 0 and len(errors) == 1 and errors[0]['code'] == expect and not any(r['kind'] == 'return' for r in rows)))
        if not okay:
            raise CompletedBusinessFailure('completed actual public role boundary differs: ' + role + '/' + action + '/' + str(expect))

        return rows

    def state(self):
        rows = self.request('system','state')
        result = next(r['value'] for r in rows if r['kind'] == 'return')
        require(type(result['getCallState']) is int and type(result['getCellularDataState']) is int and
            type(result['isCellularDataEnabled']) is bool,'actual public state errors are not success')
        return result

    def await_state(self, predicate, label, timeout=45):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = self.state()
            if predicate(value): return value
            time.sleep(.25)
        raise ValueError('actual framework convergence deadline: ' + label)

    def control(self, action):
        require(action in CONTROLS and self.modem.peer == self.report['peer_key'],'same original held peer required')
        op = secrets.token_hex(16); payload = (op + '\t' + action + '\n').encode()
        actual = self.io.write_stdin(self.modem.peer,payload)
        require(actual['key'] == self.modem.peer and actual['boot_id'] == self.io.boot_id and
            load_ref(actual['raw']) == payload,'actual original peer stdin receipt differs')
        self.controls.append({'action':action,'operation':op,'receipt':actual}); self.save()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            rows = [r for r in self.modem.read_peer() if r['operation_id'] == op]
            effects = [r for r in rows if r['kind'] in ('tx','backend')]
            if rows and effects:
                if action == 'l22-on':
                    try:
                        handover(rows,run=self.io.run_id,boot=self.io.boot_id,operation=op,peer_pid=self.modem.peer_pid)
                    except ValueError:
                        time.sleep(.1)
                        continue
                    if not any(r['kind'] == 'tx' for r in rows):
                        time.sleep(.1)
                        continue
                require(rows[0]['kind'] == 'control' and bytes.fromhex(rows[0]['hex']) == action.encode() and
                    all(r['seq'] > rows[0]['seq'] for r in effects),'actual endpoint action/effect ordering differs')
                return rows
            time.sleep(.1)
        raise ValueError('actual original peer action effect deadline: ' + action)

    def settled_boundary_failure(self):
        # Only the fixed argument/role negative steps may continue, and only
        # after independent real endpoint + public/native observations agree.
        observed = self.control('l22-status')
        state = [bytes.fromhex(r['hex']).decode() for r in observed if r['kind'] == 'backend']
        require(state == ['registered=1 call=-1 pdp=0 sms_pending=0'],
            'negative operation left actual lower-layer call/PDP/SMS pending')
        actual = self.state()
        require(actual['getCallState'] == 0 and actual['getCellularDataState'] in (-1,0) and
            actual['isCellularDataEnabled'] is False,'negative operation changed actual call/data policy')
        self.modem.fd_binding()

    def attempt(self, name, function):
        entry = {'name':name,'status':'started','request_start':len(self.requests),'control_start':len(self.controls)}
        self.steps.append(entry); self.save()
        try:
            function(); entry['status'] = 'observed'
        except CompletedBusinessFailure as error:
            entry.update(status='failed',error=str(error)); self.report['failures'].append(name + ': ' + str(error))
            if name not in ('actual-malformed-parameters','actual-role-rejections'):
                self.report['business_reuse_stopped'] = True
                raise Unsettled('completed positive/lifecycle failure requires reverse cleanup: ' + name) from error
            try: self.settled_boundary_failure()
            except Exception as cleanup_error:
                self.report['business_reuse_stopped'] = True
                raise Unsettled('negative business boundary failed actual settle proof: ' + name) from cleanup_error
            entry['continued_only_after_actual_settle_proof'] = True
        except Exception as error:
            # No generic error-code whitelist. Unknown semantic/IO/identity,
            # partial listener/socket teardown, pending request and RIL
            # generation errors are quarantined before another business step.
            entry.update(status='unsettled',error=str(error)); self.report['failures'].append(name + ': ' + str(error))
            self.report['business_reuse_stopped'] = True
            raise Unsettled('stop reusing original IO; reverse cleanup only: ' + name) from error
        finally:
            entry.update(request_end=len(self.requests),control_end=len(self.controls)); self.save()

    def caller_restart(self):
        role = 'system'; entry = self.roles[role]
        self.collect(role)
        prior = [self.writers[p] for p in entry['generations'] if not self.writers[p]['exited']]
        require(len(prior) == 1,'one live system caller generation required')
        self.shell('aa force-stop ' + entry['prepared']['bundle'],'restart_stop_system')
        self.prove_absent(role,'generation_exit')
        prior[0]['exited'] = True; prior[0]['sealing'] = True
        prior[0]['exit_command'] = len(self.commands)-1
        self.collect(role)
        self.request(role,'identity')
        after = [self.writers[p] for p in entry['generations'] if not self.writers[p]['exited']]
        require(len(after) == 1 and (after[0]['pid'],after[0]['start_ticks']) != (prior[0]['pid'],prior[0]['start_ticks']),
            'real new system caller generation required')
        self.request(role,'observe'); self.save()

    def prove_absent(self, role, label):
        entry = self.roles[role]; identity = entry['identity']
        for index in range(2):
            raw, observed = capture_snapshot(lambda script,name:self.shell(script,re.sub('[^A-Za-z0-9_-]','_',name)),
                'l22_' + label + '_' + role + '_' + str(index),self.io.boot_id,
                mode='uid',uid=identity['uid'],bundle=entry['prepared']['bundle'])
            require(not observed['processes'],'owned HAP UID/generation remains')
            self.report['cleanup'].append({'role':role,'kind':label,'command':len(self.commands)-1})
            if index == 0: time.sleep(.25)

    def endpoint_binding(self):
        pid = str(self.modem.peer_pid)
        self.modem.fd_binding()
        self.report['tun_binding_command'] = len(self.commands)
        raw = self.shell('test -d /sys/class/net/usb0 && cat /sys/class/net/usb0/ifindex && '
            'l22_tun_count=0; for l22_fd in /proc/' + pid + '/fd/*; do '
            'l22_target=$(readlink "$l22_fd") || exit 1; if test "$l22_target" = /dev/tun; then '
            'printf "TUNFD=%s\\n" "$l22_fd"; cat /proc/' + pid + '/fdinfo/${l22_fd##*/} || exit 1; '
            'l22_tun_count=$((l22_tun_count + 1)); fi; done; test "$l22_tun_count" = 1', 'actual_tun_owner')
        require(re.search(r'^iff:\s+usb0$',raw,re.M),'actual peer TUN fdinfo must bind usb0')
        controls = [r for r in self.controls if r['action'] == 'l22-on']
        require(len(controls) == 1,'one original peer native endpoint acquisition')
        facts = handover(self.modem.read_peer(),run=self.io.run_id,boot=self.io.boot_id,
            operation=controls[0]['operation'],peer_pid=self.modem.peer_pid)
        require(raw.splitlines()[0] == str(facts['ifindex']),'SCM handover ifindex must equal independently observed kernel usb0')
        self.report['native_handover'] = facts
        self.report['native_service_command'] = len(self.commands)
        observed = self.shell(service_script(facts['pid'],self.report['native_library_path'],
            self.report['native_library_sha256'],self.io.boot_id),'native_tun_service')
        self.report['native_service_observation'] = service_observation(observed,facts,
            self.report['native_library_path'],self.report['native_library_sha256'])
        self.save()
        require(self.shell(starttime_shell(pid),'tun_owner_generation').strip() == self.modem.peer_start,
            'actual TUN owner generation changed')

    def peer_after(self, seq, needle, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = [r for r in self.modem.read_peer() if r['seq'] > seq and r['kind'] == 'tx' and
                needle in bytes.fromhex(r['hex'])]
            if found: return found[-1]
            time.sleep(.1)
        raise ValueError('actual lower-layer transaction did not arrive: ' + repr(needle))

    def call_transactions(self):
        mark = self.modem.read_peer()[-1]['seq']
        self.request('system','dial')
        self.peer_after(mark,b'^CCALLSTATE: 1,2,0')
        self.await_state(lambda s:s['getCallState'] == 2,'outgoing offhook')
        self.await_detail(2)
        self.control('l22-answer')
        self.await_detail(0)
        self.report.setdefault('call_active_frames',[]).append(self.io.frame('l22_active_call'))
        mark = self.modem.read_peer()[-1]['seq']
        hanging = self.request('system','hangup')
        self.peer_after(mark,b'^CCALLSTATE: 1,6,0')
        self.await_detail(6,since=hanging[0]['monotonic_ms'])
        self.await_state(lambda s:s['getCallState'] == 0,'outgoing release')
        self.control('l22-incoming')
        self.await_state(lambda s:s['getCallState'] == 1,'incoming ring')
        self.await_detail(4)
        mark = self.modem.read_peer()[-1]['seq']
        self.request('system','answer')
        self.peer_after(mark,b'^CCALLSTATE: 1,0,0')
        self.await_detail(0)
        mark = self.modem.read_peer()[-1]['seq']
        hanging = self.request('system','hangup')
        self.peer_after(mark,b'^CCALLSTATE: 1,6,0')
        self.await_detail(6,since=hanging[0]['monotonic_ms'])
        self.await_state(lambda s:s['getCallState'] == 0,'incoming release')

    def await_detail(self, state, since=0, timeout=30):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            rows = self.collect('system')
            callbacks = [r for r in rows if r['kind'] == 'callback' and r['value']['type'] == 'callDetailsChange' and r['monotonic_ms'] >= since]
            if callbacks and callbacks[-1]['value']['value'].get('callState') == state:
                require(type(callbacks[-1]['value']['value'].get('callId')) is int,'actual native call ID required')
                return callbacks[-1]
            time.sleep(.2)
        raise ValueError('actual latest callDetailsChange state absent: ' + str(state))

    def call_negative(self):
        self.control('l22-dial-error')
        request = self.issue('system','dial')
        rows = self.wait('system',request)
        errors = [r for r in rows if r['kind'] == 'error']
        # Some native versions settle DialCall before the modem response.
        # Either native rejection or the later real disconnected callback is
        # retained; the raw replay still requires ATD -> NO CARRIER -> idle.
        if not errors:
            self.await_detail(6,since=rows[0]['monotonic_ms'])
        self.await_state(lambda s:s['getCallState'] == 0,'real dial NO CARRIER')

    def call_timeout(self):
        self.control('l22-dial-timeout')
        request = self.issue('system','dial')
        rows = self.wait('system',request,timeout=95)
        # No response is injected. The actual product at_support.c waits its
        # unchanged DEFAULT_LONG_TIMEOUT=50000 before reporting native failure.
        if not any(r['kind'] == 'error' for r in rows):
            self.await_detail(6,since=rows[0]['monotonic_ms'],timeout=95)
        self.await_state(lambda s:s['getCallState'] == 0,'real native AT timeout')
        self.report['native_timeout_log_command'] = len(self.commands)
        self.shell('hilog -x','native_timeout_logs'); self.save()

    def device_reset(self):
        # Reuse original controlled service generation operations and its
        # reader/FD/init/DSO guards. The endpoint and Owner remain unchanged.
        self.request('system','data-off')
        self.await_state(lambda s:s['getCellularDataState'] in (-1,0),'pre-reset idle PDP')
        before = self.modem.ril
        self.report['ril_reset'] = {'before':dict(before),'stop_command_start':len(self.modem.commands)}
        self.save()
        self.modem.stop_ril()
        self.control('l22-carrier-drop')
        after = self.modem.start_ril(before)
        self.modem.ril = after
        self.modem.fd_binding()
        self.report['ril_reset'].update(after=dict(after),command_end=len(self.modem.commands))
        self.control('l22-register')
        self.await_state(lambda s:type(s['getNetworkState']) is dict and s['getNetworkState'].get('regState') == 1,
            'actual RIL rebuilt service re-registration')
        self.endpoint_binding(); self.save()

    def sms_positive(self):
        nonce = secrets.token_hex(16); rows = self.request('system','sms',nonce=nonce)
        result = next(r['value'] for r in rows if r['kind'] == 'sms-completion')
        require(result == {'code':0,'result':{'result':0}},'actual SMS sendCallback must report SEND_SMS_SUCCESS')
        self.control('l22-sms-report')
        request = next(r for r in rows if r['kind'] == 'begin')['value']
        end = time.monotonic() + 20
        while time.monotonic() < end:
            actual = [r for r in self.collect('system') if r['operation_id'] == request['operation_id'] and r['kind'] == 'sms-delivery-callback']
            if actual:
                require(len(actual) == 1 and actual[0]['code'] == 0 and type(actual[0]['value']['result']['pdu']) is list,
                    'actual independent SMS delivery callback absent or errored')
                return
            time.sleep(.2)
        raise ValueError('real +CDS delivery did not reach original SMS NAPI callback')

    def sms_negative(self):
        self.control('l22-sms-error')
        try:
            rows = self.request('system','sms',nonce=secrets.token_hex(16))
            completed = next(r['value'] for r in rows if r['kind'] == 'sms-completion')
            require(completed.get('timeout') is not True and completed['result']['result'] != 0,
                'actual CMS error must reach a non-success sendCallback, not local completion/timeout')
        finally: self.control('l22-sms-clear')

    def permission_transactions(self):
        baseline = self.state()
        for role in ('ordinary','denied'):
            expect = 202 if role == 'ordinary' else 201
            for action in ('dial','data-on','data-off'): self.request(role,action,expect=expect)
            # SMS SendMessage checks SEND_MESSAGES directly, before any
            # system-app-only IMS API; both ungranted roles require actual201.
            self.request(role,'sms',expect=201,nonce=secrets.token_hex(16))
            self.request('system','quiet',wait_ms=5000)
            actual = self.state()
            require(actual['getCallState'] == baseline['getCallState'] and
                actual['getCellularDataState'] == baseline['getCellularDataState'] and
                actual['isCellularDataEnabled'] == baseline['isCellularDataEnabled'],
                'denied caller changed actual call/data state')

    def data_transactions(self):
        self.request('system','data-on')
        self.await_state(lambda s:s['getCellularDataState'] == 2 and s['isCellularDataEnabled'] is True,
            'real registered PDP and network')
        for role in ('system','ordinary'):
            rows = self.request(role,'udp',nonce=secrets.token_hex(16))
            actual = next(r['value'] for r in rows if r['kind'] == 'return')
            packet_pair(self.modem.read_peer(),actual['payload'])
        self.report['network_connected_command'] = len(self.commands)
        self.shell(NETWORK,'network_connected')
        self.control('l22-carrier-drop')
        self.await_state(lambda s:s['getCellularDataState'] in (-1,0),'actual carrier disconnect')
        self.control('l22-register')
        self.await_state(lambda s:s['getCellularDataState'] == 2,'actual carrier reattach')
        self.request('ordinary','udp',nonce=secrets.token_hex(16))
        self.request('system','data-off')
        self.await_state(lambda s:s['getCellularDataState'] in (-1,0) and s['isCellularDataEnabled'] is False,'actual PDP teardown')

    def exercise(self):
        self.prepare()
        self.request('system','observe')
        self.request('system','data-off')
        self.await_state(lambda s:s['getCellularDataState'] in (-1,0) and s['isCellularDataEnabled'] is False,'controlled disconnected policy')
        self.business_intent = True; self.save()
        self.control('l22-on'); self.endpoint_binding()
        self.await_state(lambda s:type(s['getNetworkState']) is dict and s['getNetworkState'].get('regState') == 1,
            'actual registered virtual network')
        self.attempt('actual-malformed-parameters',lambda:[self.request('system',name,expect=401)
            for name in ('invalid-dial','invalid-sms','invalid-data')])
        self.attempt('actual-role-rejections',self.permission_transactions)
        self.attempt('cs-outgoing-and-incoming',self.call_transactions)
        self.attempt('cs-real-no-carrier',self.call_negative)
        self.attempt('sms-submit-and-delivery',self.sms_positive)
        self.attempt('sms-actual-modem-error',self.sms_negative)
        self.attempt('cellular-two-uid-independent-packets-and-carrier-recovery',self.data_transactions)
        self.attempt('cs-real-native-at-timeout',self.call_timeout)
        self.attempt('ril-device-reset-and-rebind',self.device_reset)
        # API state must be idle/disconnected before a fresh caller generation.
        self.attempt('idle-caller-generation-rebuild',self.caller_restart)
        self.attempt('cs-after-caller-rebuild',self.call_transactions)
        self.attempt('sms-after-caller-rebuild',self.sms_positive)
        self.attempt('cellular-after-caller-rebuild',self.data_transactions)

    def cleanup(self):
        if self.cleaned: return
        errors = []
        def step(name, action):
            try: action()
            except Exception as error: errors.append(name + ': ' + str(error))
        if self.business_intent:
            # Actual lower-layer disconnect permits reverse cleanup even after
            # a failed API operation. It remains explicit non-success evidence.
            step('disconnect finite endpoint',lambda:self.control('l22-carrier-drop'))
        if 'system' in self.installed and self.data_baseline is not None:
            step('actual public state restoration',lambda:self.request('system','restore',data_baseline=self.data_baseline))
            step('real data/call disconnected',lambda:self.await_state(lambda s:s['getCellularDataState'] in (-1,0) and
                s['getCallState'] == 0 and s['isCellularDataEnabled'] == self.data_baseline,'cleanup'))
        if self.business_intent:
            def off():
                self.control('l22-off'); self.business_intent = False
            step('close same peer nonpersistent TUN',off)
        for role in tuple(reversed(self.installed)):
            entry = self.roles[role]; name = entry['prepared']['bundle']
            def uninstall(role=role,entry=entry,name=name):
                # Preserve complete live raw caller state before its sandbox
                # disappears; after stop its prior generation is immutable.
                if entry.get('generations'): self.collect(role)
                self.shell('aa force-stop ' + name,'final_stop_' + role,allow_failure=True)
                if entry.get('generations'):
                    self.prove_absent(role,'before-uninstall')
                    for path in entry['generations']:
                        if not self.writers[path]['exited']:
                            self.writers[path].update(exited=True,sealing=True)
                    self.collect(role)
                raw = self.command([self.io.hdc,'-t',self.io.target,'uninstall',name],'uninstall_' + role)
                require('uninstall bundle successfully' in raw.lower(),'actual L22 uninstall did not succeed')
                assert_bundles_absent(self.shell('bm dump -a','bundle_absent_' + role),[name])
                require('identity' in entry,'partial installation requires actual BMS UID recovery')
                self.prove_absent(role,'uninstalled')
                for path in entry['generations']: self.writers[path]['exited'] = True
                self.installed.remove(role)
            step('caller uninstall/UID absence ' + role,uninstall)
        step('owned usb0 absence',lambda:self.shell('test ! -e /sys/class/net/usb0 && test ! -L /sys/class/net/usb0','tun_absent'))
        def network_restored():
            self.report['network_after_command'] = len(self.commands)
            actual = self.shell(NETWORK,'network_after')
            require(actual == self.report['network_before'],'actual original addresses/routes/rules differ after transaction cleanup')
        step('original kernel network restoration',network_restored)
        step('original held boot',lambda:require(self.shell('cat /proc/sys/kernel/random/boot_id','final_boot').strip() == self.io.boot_id,
            'held boot changed during cleanup'))
        self.report['cleanup_errors'] = errors
        self.cleaned = not errors and not self.installed and not self.business_intent
        self.report['cleanup_complete'] = self.cleaned
        self.report['transaction_matrix_observed'] = self.cleaned and not self.report['failures'] and bool(self.steps) and all(
            s['status'] == 'observed' for s in self.steps)
        self.save()
        require(self.cleaned,'actual L22 reverse cleanup failed: ' + '; '.join(errors))


def run(io, modem):
    producer = Transactions(io,modem)
    try: producer.exercise()
    except Exception as error:
        producer.report['failures'].append('transaction setup/production: ' + str(error)); producer.save()
    finally:
        pending = sys.exc_info()[0]
        try: producer.cleanup()
        except Exception as cleanup_error:
            if pending is None or issubclass(pending,Exception): raise
            # Preserve KeyboardInterrupt/SystemExit without catching them.
            # Original OwnedIO retains its registered reverse cleanup retry.
            producer.report.setdefault('interrupted_cleanup_errors',[]).append(str(cleanup_error)); producer.save()
    return reference(producer.output / 'evidence.json')
