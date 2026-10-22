"""Finite business adapter on the real original Network OwnedIO.

No IO/Owner/Runner/lease/process/socket constructor. All operations use the
already held canonical IO and its existing normal SDK/signing dispatcher.
"""
from pathlib import Path
import sys
for _name in ('network_whole579_records', 'network_whole579_sources', 'network_whole579_project', 'network_whole579_session', 'network_whole579_hook', 'network_whole579_p2p', 'network_whole579_replay', 'network_whole579_options_replay'):
    _old=sys.modules.get(_name)
    if _old is not None and Path(_old.__file__).resolve()!=Path(__file__).resolve().with_name(_name+'.py'):
        raise ValueError('foreign cached whole Network source '+_name)
import json
import re
import secrets
import shlex
import time
from network_whole579_records import need, raw, doc, ref, save
import network_whole579_project as project


class Session:
    def __init__(self, io, profile, peer_run, original_config):
        need(not io._closed and io.owner.vm is io.guest, 'real original Network IO only')
        self.io = io
        self.original_config = original_config
        self.output = Path(io.output) / 'network-whole579'
        self.output.mkdir(mode=0o700, exist_ok=False)
        self.serial = 0
        self.prefix = {}
        self.peer_deadline = None
        self.cleaning = False
        self.value = dict(schema='network-whole579-systemvpn/v1', run_id=io.run_id,
            archive_sha256=io.archive_sha256, boot_id=io.boot_id, udid=io.udid,
            parameters=dict(profile=io.guest.report['test_environment']['device_type'], udid=io.udid,
                            peer_profile=profile, peer_run=peer_run),
            prepared=None, installed=[], identities={}, operations=[], cleanup=[], failures=[],
            phases=[], account=None, closed=False, kernel_helper=None, kernel_staged=False, kernel_safe_to_remove=True, original_owner_finish_still_required=True,
            runtime_pass=False, first_artifact_behavior_gate_passed=False)
        self.persist()
        io.network_whole579_state = self
        io.register_cleanup(self.cleanup)

    def persist(self):
        target = self.output / 'attempt.json'
        target.write_text(json.dumps(self.value, indent=2, allow_nan=False) + '\n')

    def shell(self, script, label, timeout=60, allow_failure=False):
        need(re.fullmatch('[a-z0-9_-]+', label), 'finite actual Guest shell label')
        if self.peer_deadline is not None and not self.cleaning:
            left = self.peer_deadline - time.time() - 15
            need(left > 0, 'original peer 240s exhausted; retain failure and original cleanup')
            timeout = min(timeout, max(1, int(left)))
        return self.io.shell(script, 'network_whole579_' + label,
                             timeout=timeout, allow_failure=allow_failure)

    def prepare(self):
        self.value['prepared'] = self.io.prepare_callers('network_whole579', 'systemvpn', self.io.run_id,
            project.ROLES, self.value['parameters'])
        self.persist()
        for role in project.ROLES:
            self.install(role, 100)
        from api26_connected579_sources import load
        original = load().steps
        adapter = original.load_adapter(self.original_config['qa_root'])
        helper = self.original_config['kernel_helper']
        proof = adapter.helper_inputs(Path(self.original_config['qa_root'])/'ci/capability-audit',
            Path(helper['root']), helper['evidence']['sha256'], self.original_config['commit'], self.original_config)
        self.value['kernel_helper'] = proof; self.persist()
        from batch_system_build_runtime_helpers import runtime_guest_script, verify_guest_runtime_raw
        for n, entry in enumerate(proof['dsos']):
            row=self.shell(runtime_guest_script(proof['binding'],entry['soname']),'kernel_dso_'+str(n))
            verify_guest_runtime_raw(proof['binding'],entry['soname'],row['stdout'],archive_sha256=self.io.archive_sha256)
            self.value['operations'].append(dict(kind='kernel-runtime',soname=entry['soname'],command=self.io.ref_receipt(row)));self.persist()
        remote='/data/local/tmp/network_whole579_'+self.io.run_id
        self.value['kernel_remote']=remote;self.persist()
        q=shlex.quote(remote)
        self.shell('test ! -e '+q+' && test ! -L '+q+' && umask 077 && mkdir '+q,'kernel_create')
        self.value['kernel_staged']=True;self.persist()
        self.io.send(proof['binary']['path'],remote+'/netlink_snapshot','network_whole579_kernel_send')
        self.shell('test ! -L '+q+'/netlink_snapshot && chmod 700 '+q+'/netlink_snapshot','kernel_mode')
        actual=self.shell('stat -c %u:%a:%h '+q+'/netlink_snapshot && sha256sum '+q+'/netlink_snapshot','kernel_hash')
        need(actual['stdout'].splitlines()==['0:700:1',proof['binary']['sha256']+'  '+remote+'/netlink_snapshot'],'actual original kernel helper bytes/uid/mode')
        self.value['operations'].append(dict(kind='kernel-installed',command=self.io.ref_receipt(actual)));self.persist()

    def install(self, role, user):
        need(role in project.ROLES and type(user) is int and user >= 100 and
             not any(r['role'] == role and r['user'] == user for r in self.value['installed']), 'one real install per role/account')
        caller = self.value['prepared']['callers'][role]
        name = project.bundle('systemvpn', role)
        before = self.shell('bm dump -a', 'fresh_' + role + '_' + str(user))
        # Same signed bundle may already be installed in account100. Account
        # creation is public, fresh and nonce-owned; never replace an old user.
        if user == 100:
            need(not re.search(r'(?<![A-Za-z0-9_.])' + re.escape(name) + r'(?![A-Za-z0-9_.])', before['stdout']), 'refuse foreign baseline bundle')
        else:
            need(self.value['account'] is not None and user == self.value['account']['localId'] and role == 'b', 'only owned public guest-account B install')
        remote = '/data/local/tmp/network_whole579_' + self.io.run_id + '_' + role + '_' + str(user) + '.hap'
        self.io.send(caller['signed']['path'], remote, 'network_whole579_send_' + role + '_' + str(user))
        result = self.shell(shlex.join(['bm', 'install', '-r', '-p', remote, '-u', str(user)]),
                            'install_' + role + '_' + str(user), timeout=600)
        need('install bundle successfully.' in result['stdout'], 'actual SystemVpn caller install failed')
        item = dict(role=role, user=user, remote=remote, signed=caller['signed'])
        self.value['installed'].append(item); self.persist()
        bms = self.shell('bm dump -n ' + name + ' -u ' + str(user), 'bms_' + role + '_' + str(user))
        from apps_providers579_bindings import bms_json, objects
        value = bms_json(bms['stdout'])
        apps = [o for o in objects(value) if o.get('bundleName') == name and type(o.get('uid')) is int]
        need(apps and len({o['uid'] for o in apps}) == 1 and apps[0]['uid'] // 200000 == user,
             'actual BMS account-derived UID required')
        app = apps[0]
        need(app['isSystemApp'] is (role != 'normal') and app['fingerprint'] == caller['identity']['fingerprint'], 'actual system role/signer differs')
        paths = {o['hapPath'] for o in objects(value) if o.get('hapPath')}
        need(len(paths) == 1, 'one actually installed HAP')
        guest_hap = next(iter(paths))
        hashed = self.shell('sha256sum ' + shlex.quote(guest_hap), 'hap_' + role + '_' + str(user))
        need(hashed['stdout'].split() == [caller['signed']['sha256'], guest_hap], 'actual installed signed HAP bytes differ')
        identity = dict(uid=app['uid'], role=role, user=user, bundle=name, application=app,
            bms=self.io.ref_receipt(bms), installed_hash=self.io.ref_receipt(hashed), guest_hap=guest_hap,
            install=self.io.ref_receipt(result), baseline=self.io.ref_receipt(before))
        self.value['identities'][role + ':' + str(user)] = identity
        self.persist()

    def call(self, role, action, payload=None, user=100):
        need(role + ':' + str(user) in self.value['identities'], 'actual installed caller identity')
        need(action in {'identity', 'watch', 'off', 'setup', 'option', 'state', 'destroy', 'traffic4', 'traffic6', 'dns',
            'cleanup', 'exit', 'failure-setup', 'reconfigure', 'restore-peer', 'dns-outside', 'dns-bad-cert', 'accounts', 'account-create', 'account-activate', 'account-restore', 'account-remove'}, 'literal compiled action')
        payload = payload or {}
        need(payload == {} or action == 'option' and set(payload) == {'option'} and payload['option'] in
            tuple(project.OPTIONS), 'finite profile option data')
        self.serial += 1
        request = dict(run_id=self.io.run_id, request_id='whole579_' + str(self.serial) + '_' + action.replace('-', '_'),
                       action=action, payload=payload)
        at = len(self.io.receipts)
        boot = self.shell('cat /proc/sys/kernel/random/boot_id', 'boot_' + str(self.serial))
        need(boot['stdout'].strip() == self.io.boot_id, 'same actual held guest boot')
        name = project.bundle('systemvpn', role)
        argv = ['aa', 'start', '-b', name, '-a', 'EntryAbility', '-m', 'entry', '-u', str(user)]
        for key in ('run_id', 'request_id', 'action'):
            argv += ['--ps', key, request[key]]
        argv += ['--ps', 'payload', json.dumps(payload, separators=(',', ':'))]
        started = self.shell(shlex.join(argv), 'start_' + str(self.serial))
        need('start ability successfully' in started['stdout'].lower(), 'actual AMS start failed')
        directory = '/data/app/el2/' + str(user) + '/base/' + name + '/files'
        deadline = time.monotonic() + 35
        began = time.time()
        if self.peer_deadline is not None and not self.cleaning:
            deadline = min(deadline, time.monotonic() + max(0, self.peer_deadline - began - 15))
        records = []
        poll_serial = 0
        while True:
            poll_serial += 1
            listing = self.shell('ls ' + directory + '/apps579-' + self.io.run_id + '-*.jsonl',
                                 'journals_' + str(self.serial), allow_failure=True)
            files = []; records = []
            if listing['exit_code'] == 0:
                for remote in sorted(listing['stdout'].splitlines()):
                    need(re.fullmatch(re.escape(directory + '/apps579-' + self.io.run_id + '-') + r'[1-9][0-9]*\.jsonl', remote), 'literal own private journal')
                    local = self.output / ('journal_' + str(self.serial) + '_' + str(poll_serial) + '_' + str(len(files)) + '.jsonl')
                    received = self.io.receive(remote, local, 'network_whole579_recv_' + str(self.serial) + '_' + str(len(files)))
                    data = local.read_bytes()
                    need(data.startswith(self.prefix.get(remote, b'')), 'actual append-only process journal')
                    if not data.endswith(b'\n'):
                        files = []; break
                    self.prefix[remote] = data
                    values = [json.loads(line) for line in data.splitlines()]
                    identity = self.value['identities'][role + ':' + str(user)]
                    need(values and all(v['seq'] == n and v['run_id'] == self.io.run_id and v['kind'] == 'systemvpn' and
                        v['role'] == role and v['uid'] == identity['uid'] and v['bundle'] == name and
                        remote.endswith('-' + str(v['pid']) + '.jsonl') for n, v in enumerate(values)), 'actual journal PID/UID/nonce/account/sequence')
                    files.append(dict(remote=remote, raw=ref(local), receive=self.io.ref_receipt(received)))
                    records.extend(values)
            selected = [r for r in records if r['request_id'] == request['request_id']]
            if files and any(r['event'] in ('done', 'error', 'request-error', 'page-error') for r in selected):
                break
            need(time.monotonic() < deadline, 'real typed request did not terminate')
            time.sleep(.1)
        operation = dict(kind='call', role=role, user=user, request=request, started_epoch=began, finished_epoch=time.time(),
            peer_deadline_epoch=self.peer_deadline, during_cleanup=self.cleaning, start=self.io.ref_receipt(started),
            journals=files, commands=[self.io.ref_receipt(r) for r in self.io.receipts[at:]])
        self.value['operations'].append(operation); self.persist()
        need(sum(r['event'] == 'request' for r in selected) == 1 and sum(r['event'] == 'done' for r in selected) == 1 and
             not any(r['event'] in ('error', 'request-error', 'page-error') for r in selected), 'generic caller error, not native boundary')
        for event in selected:
            if event['event'].endswith('-error'):
                detail=json.loads(event['value'])
                need(event['event'] in ('setup-error','dns-error') and type(event['code']) is int and event['code']>0 and
                    detail['codeType']=='number' and detail['rawCode']==event['code'], 'actual native BusinessError only; no TypeError/socket/destroy failure')
        return selected

    def native(self, label):
        from batch_network_openvpn_runtime_collect import snapshot_script, parse_snapshot, SnapshotRace
        for attempt in range(3):
            nonce = secrets.token_hex(16)
            script = snapshot_script(nonce, self.io.boot_id)
            row = self.shell(script, 'native_' + label + '_' + str(attempt), timeout=90)
            item = dict(kind='native', label=label, nonce=nonce, command=self.io.ref_receipt(row))
            self.value['operations'].append(item); self.persist()
            try:
                parsed=parse_snapshot(row['stdout'],nonce,self.io.boot_id)
                item['snapshot_race']=None;self.persist();return parsed
            except SnapshotRace as error:
                item['snapshot_race']=str(error);self.persist()
                if attempt==2:raise

    def kernel(self,label):
        from batch_network_kernel_snapshot import parse_snapshot
        nonce=secrets.token_hex(16)
        command=self.value['kernel_remote']+'/netlink_snapshot --run-id '+nonce+' --timeout-ms '+str(self.original_config['kernel_helper']['timeout_ms'])
        self.value['kernel_safe_to_remove']=False;self.persist()
        row=self.shell(command,'kernel_'+label,timeout=60)
        self.value['kernel_safe_to_remove']=True;self.persist()
        item=dict(kind='kernel',label=label,run_id=nonce,command=self.io.ref_receipt(row))
        self.value['operations'].append(item);self.persist()
        return parse_snapshot(row['stdout'],run_id=nonce,boot_id=self.io.boot_id)

    def dns_wire(self,label,claim):
        remote=claim['directory']+'/dns-wire.jsonl'
        checked=self.shell('test ! -L '+shlex.quote(remote)+' && stat -c %u:%a:%h '+shlex.quote(remote),
            'dns_wire_stat_'+label)
        need(checked['stdout'].strip()=='1098:600:1','actual native DNS journal uid/mode/link')
        target=self.output/('dns-wire-'+str(len(self.value['operations']))+'-'+label+'.jsonl')
        received=self.io.receive(remote,target,'network_whole579_dns_wire_'+label)
        item=dict(kind='dns-wire',label=label,claim=claim,remote=remote,raw=ref(target),
            stat=self.io.ref_receipt(checked),receive=self.io.ref_receipt(received))
        self.value['operations'].append(item);self.persist();return item

    def platform(self, label):
        rows = {}
        for name, script in {'ipv4': 'cat /proc/net/route', 'ipv6': 'cat /proc/net/ipv6_route',
            'addr6': 'cat /proc/net/if_inet6', 'netsys': 'hidumper -s 1151', 'hilog': 'hilog -x',
            'account': 'hidumper -s AccountMgr -a "-os_account_infos"'}.items():
            rows[name] = self.io.ref_receipt(self.shell(script, label + '_' + name, allow_failure=True))
        self.value['operations'].append(dict(kind='platform', label=label, rows=rows)); self.persist()

    def cleanup(self):
        if self.value['closed']: return
        errors = []
        self.value['cleanup_started_epoch']=time.time();self.persist()
        self.cleaning = True
        for role in ('a', 'b'):
            if role + ':100' in self.value['identities']:
                try: self.call(role, 'cleanup')
                except Exception as error: errors.append('public cleanup ' + role + ': ' + str(error))
        if self.value['account'] is not None:
            try: self.call('account', 'account-restore')
            except Exception as error: errors.append('public account restore: ' + str(error))
        from batch_network_openvpn_runtime_collect import snapshot_script, parse_snapshot
        def remove(items):
            rows=[]
            for item in items:
                identity=self.value['identities'].get(item['role']+':'+str(item['user']))
                name=project.bundle('systemvpn',item['role'])
                stop=self.shell('aa force-stop '+name+' -u '+str(item['user']),
                    'stop_'+item['role']+'_'+str(item['user']),allow_failure=True)
                removed=self.shell('bm uninstall -n '+name+' -u '+str(item['user']),
                    'remove_'+item['role']+'_'+str(item['user']),allow_failure=True)
                row=dict(identity=identity,stop=self.io.ref_receipt(stop),uninstall=self.io.ref_receipt(removed),cuts=[])
                rows.append(row);self.value['cleanup'].append(row);self.persist()
                need('uninstall bundle successfully' in removed['stdout'].lower(),'actual per-account HAP uninstall failed')
            for item in rows:
                identity=item['identity'];need(identity is not None,'partial install has no actual BMS identity')
                for at in range(2):
                    nonce=secrets.token_hex(16)
                    row=self.shell(snapshot_script(nonce,self.io.boot_id,mode='uid',uid=identity['uid'],bundle=identity['bundle']),
                        'absence_'+identity['role']+'_'+str(identity['user'])+'_'+str(at),timeout=90)
                    scan=parse_snapshot(row['stdout'],nonce,self.io.boot_id,mode='uid',uid=identity['uid'],bundle=identity['bundle'])
                    ams=self.shell('aa dump -a -u '+str(identity['user']),'ams_absent_'+identity['role']+'_'+str(identity['user'])+'_'+str(at))
                    bms=self.shell('bm dump -a','bms_absent_'+identity['role']+'_'+str(identity['user'])+'_'+str(at))
                    exact=r'(?<![A-Za-z0-9_.])'+re.escape(identity['bundle'])+r'(?![A-Za-z0-9_.])'
                    need(not scan['processes'] and not re.search(exact,ams['stdout']) and not re.search(exact,bms['stdout']),
                        'actual two-cut UID/AMS/BMS absence required')
                    item['cuts'].append(dict(nonce=nonce,process=self.io.ref_receipt(row),ams=self.io.ref_receipt(ams),bms=self.io.ref_receipt(bms)))
            for item in items:self.shell('rm '+shlex.quote(item['remote']),'release_'+item['role']+'_'+str(item['user']))
        # Remove both B copies before the global BMS scanner, while account101
        # still exists. Keep the public account controller until removal ends.
        try: remove([i for i in self.value['installed'] if i['role']!='account'])
        except Exception as error: errors.append('actual non-controller HAP cleanup: '+str(error))
        if self.value['account'] is not None:
            try:
                self.call('account','account-remove');self.value['account_removed']=True
            except Exception as error: errors.append('public owned account removal: '+str(error))
        try: remove([i for i in self.value['installed'] if i['role']=='account'])
        except Exception as error: errors.append('actual controller HAP cleanup: '+str(error))
        if self.value['kernel_staged']:
            try:
                need(self.value['kernel_safe_to_remove'],'actual native helper transport unresolved; preserve staged input for original VM disposal')
                remote=self.value['kernel_remote'];q=shlex.quote(remote)
                row=self.shell('test ! -L '+q+' && test "$(stat -c %u:%a '+q+')" = 0:700 && ls -a1 '+q,'kernel_cleanup_list')
                need(set(row['stdout'].splitlines())=={'.','..','netlink_snapshot'},'unknown helper staging entry must be preserved')
                row=self.shell('test ! -L '+q+'/netlink_snapshot && test "$(stat -c %u:%a:%h '+q+'/netlink_snapshot)" = 0:700:1 && '+
                    'test "$(sha256sum '+q+'/netlink_snapshot)" = '+shlex.quote(self.value['kernel_helper']['binary']['sha256']+'  '+remote+'/netlink_snapshot')+
                    ' && rm '+q+'/netlink_snapshot && rmdir '+q,'kernel_cleanup')
                self.value['kernel_cleanup']=self.io.ref_receipt(row);self.value['kernel_staged']=False
            except Exception as error:errors.append('actual kernel helper staging cleanup: '+str(error))
        self.value['cleanup_errors']=errors;self.value['closed']=not errors;self.value['cleanup_finished_epoch']=time.time();self.persist()
        need(not errors,'actual SystemVpn/account cleanup failed: '+'; '.join(errors))
