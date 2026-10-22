"""Pure raw reconstruction; only the original admitted final actor calls this.

No guest commands, SDK commands, network sockets, subprocesses or resources.
The two whole-ID results require the broader original proof as well as every
new independent operation. Producer booleans never register a finding.
"""
from pathlib import Path
import sys
for _name in ('network_whole579_records', 'network_whole579_sources', 'network_whole579_project', 'network_whole579_session', 'network_whole579_hook', 'network_whole579_p2p', 'network_whole579_replay', 'network_whole579_options_replay'):
    _old=sys.modules.get(_name)
    if _old is not None and Path(_old.__file__).resolve()!=Path(__file__).resolve().with_name(_name+'.py'):
        raise ValueError('foreign cached whole Network source '+_name)
import hashlib
import ipaddress
import re
import shlex
import struct
from network_whole579_records import need, raw, doc, ref, save, loads
from networking579_records import original_owners
from provider579_records import shell_body, script, normalized, zip_members, FIELDS
import network_whole579_project as project


class SystemEvidence:
    def __init__(self, envelope, archive, boot):
        v = doc(envelope); self.value = doc(v['report']); self.io = doc(v['io'])
        r = self.value; self.run = r['run_id']; self.env = doc(boot)['test_environment']
        need(v['schema'] == 'network-whole579-closed-io/v1' and r['schema'] == 'network-whole579-systemvpn/v1' and
            self.io['closed'] is True and r['closed'] is True and r['failures'] == [] and r['cleanup_errors'] == [] and
            v['archive_sha256'] == r['archive_sha256'] == self.io['archive_sha256'] == archive['sha256'] and
            v['boot_id'] == r['boot_id'] == self.io['boot_id'] == self.env['boot_id'] and v['run_id'] == self.run and
            re.fullmatch('[a-f0-9]{32}', self.run), 'failed/foreign/unfinished original SystemVpn IO')
        need([p['name'] for p in r['phases']] == ['prepare', 'run'] and all(
            type(p['started_monotonic_ns']) is int and p['started_monotonic_ns'] <= p['finished_monotonic_ns'] and
            p['boot_id'] == self.env['boot_id'] and p['archive_sha256'] == archive['sha256'] for p in r['phases']) and
            r['phases'][0]['finished_monotonic_ns'] <= r['phases'][1]['started_monotonic_ns'], 'actual two-phase time/boot interval')
        need(r['parameters']['profile'] == self.env['device_type'] and r['parameters']['udid'] == self.env['udid'], 'actual profile/UDID')
        self.rows = self.io['commands']; self.bodies = [shell_body(row) for row in self.rows]
        self.commands = [normalized(row) for row in self.rows]
        need(all(row['boot_id'] == self.env['boot_id'] for row in self.rows) and all(
            p['reaped'] is True and type(p['exit_code']) is int for p in self.io['held_transports'].values()), 'same original IO/settled held transports')
        self.calls = []; self.native = []; self.claims = []; self.claim_scans=[]; self.kernels=[]; self.dns=[]; self.public_net_ids=set(); self.journals = {}; self.all_rows = {}
        self.prepare()
        from batch_network_openvpn_runtime_collect import snapshot_script, parse_snapshot, claimed, SnapshotRace
        latest = None
        for op in r['operations']:
            if op['kind'] == 'call':
                values=self.call(op);self.calls.append((op,values))
                self.public_net_ids.update(loads(v['value'])['netId'] for v in values if v['event']=='vpn-properties')
            elif op['kind'] == 'native':
                row, (body, code) = self.bound(op['command'])
                need(code == row['exit_code'] == 0 and script(row) == snapshot_script(op['nonce'], self.env['boot_id']), 'fixed complete native snapshot program')
                try: latest=parse_snapshot(body,op['nonce'],self.env['boot_id'])
                except SnapshotRace as error:
                    need(op.get('snapshot_race')==str(error),'only actual complete decoder-proven snapshot race may retry')
                    latest=None;continue
                need(op.get('snapshot_race') is None,'complete native snapshot mislabeled racing')
                self.native.append((op,latest))
            elif op['kind'] == 'claim':
                need(latest is not None, 'native claim without raw capture')
                expected_hash=hashlib.sha256(project.profile_variant(r['parameters'],op['variant']).encode()).hexdigest()
                recomputed = claimed(latest, expected_hash)
                need(recomputed == op['claim'], 'claimed native identity differs from complete process source')
                row, (body, code) = self.bound(op['profile_hash'])
                need(code == row['exit_code'] == 0 and body.split() == [expected_hash, recomputed['config']] and
                    script(row) == 'test ! -L ' + shlex.quote(recomputed['config']) + ' && sha256sum ' + shlex.quote(recomputed['config']), 'actual source profile/worker config hash differs')
                self.claims.append((op, recomputed));self.claim_scans.append(latest)
            elif op['kind']=='kernel-runtime':
                from batch_system_build_runtime_helpers import runtime_guest_script,verify_guest_runtime_raw
                row,(body,code)=self.bound(op['command'])
                need(code==row['exit_code']==0 and script(row)==runtime_guest_script(r['kernel_helper']['binding'],op['soname']),'fixed real installed helper DSO observation')
                verify_guest_runtime_raw(r['kernel_helper']['binding'],op['soname'],body,archive_sha256=archive['sha256'])
            elif op['kind']=='kernel-installed':
                row,(body,code)=self.bound(op['command']);remote=r['kernel_remote']+'/netlink_snapshot'
                need(code==row['exit_code']==0 and body.splitlines()==['0:700:1',r['kernel_helper']['binary']['sha256']+'  '+remote] and
                    script(row)=='stat -c %u:%a:%h '+shlex.quote(remote)+' && sha256sum '+shlex.quote(remote),'actual owned GET7 helper bytes/uid/mode/link')
            elif op['kind']=='kernel':
                from batch_network_kernel_snapshot import parse_snapshot as parse_kernel
                row,(body,code)=self.bound(op['command'])
                need(code==row['exit_code']==0 and script(row)==r['kernel_remote']+'/netlink_snapshot --run-id '+op['run_id']+
                    ' --timeout-ms '+str(self.original_config['kernel_helper']['timeout_ms']),'fixed exact read-only kernel helper argv/nonce')
                self.kernels.append((op,parse_kernel(body,run_id=op['run_id'],boot_id=self.env['boot_id'])))
            elif op['kind']=='dns-wire':
                row,(body,code)=self.bound(op['stat'])
                need(code==row['exit_code']==0 and op['remote']==op['claim']['directory']+'/dns-wire.jsonl' and
                    script(row)=='test ! -L '+shlex.quote(op['remote'])+' && stat -c %u:%a:%h '+shlex.quote(op['remote']) and
                    body.strip()=='1098:600:1','actual private native DNS journal custody')
                self.bound(op['receive']);data=raw(op['raw'])
                need(op['receive']['exit_code']==0 and op['receive']['argv'][1:]==['-t',self.env['target'],'file','recv',op['remote'],op['raw']['path']] and
                    data.endswith(b'\n'),'actual same-target complete received native DNS journal')
                self.dns.append((op,[loads(line) for line in data.splitlines()]))
            elif op['kind'] == 'platform':
                need(set(op['rows']) == {'ipv4', 'ipv6', 'addr6', 'netsys', 'hilog', 'account'}, 'complete dual-stack/service/UID context')
                for item in op['rows'].values(): self.bound(item)
            elif op['kind'] == 'owner-process-death':
                row, (body, code) = self.bound(op['command'])
                need(code == row['exit_code'] == 0 and script(row) == 'aa force-stop org.ohos.qemu.networkwhole579.a -u 100', 'actual owned caller process termination')
                need(self.claims and op['active_claim']==self.claims[-1][1] and self.claims[-1][0]['role']=='a' and
                    any(v['pid']==op['old_pid'] and v['role']=='a' for vals in self.all_rows.values() for v in vals),
                    'actual active SystemVpn owner/process identity before death')
            else:
                raise ValueError('unrecognised SystemVpn raw operation')
        self.cleanup()

    def bound(self, row):
        need(row in self.commands, 'observation escaped actual original closed IO')
        i = self.commands.index(row); return self.rows[i], self.bodies[i]

    def prepare(self):
        from capability578_callers import compiled_fields_match
        from apps_providers579_bindings import bms_json, objects
        from api26_connected579_sources import load
        original=load().steps
        self.original_config,_,_=original.C.runtime_envelope(self.value['phases'][0]['original_runtime_envelope'])
        c=self.original_config;helper=c['kernel_helper'];adapter=original.load_adapter(c['qa_root'])
        expected=adapter.helper_inputs(Path(c['qa_root'])/'ci/capability-audit',Path(helper['root']),helper['evidence']['sha256'],c['commit'],c)
        need(expected==self.value['kernel_helper'],'original normal helper/installed-image/link/cleanup proof differs')
        p = self.value['prepared']; need(p['case'] == 'systemvpn' and p['run_id'] == self.run and
            p['boot_id'] == self.env['boot_id'] and set(p['callers']) == set(project.ROLES), 'all normal compiled SystemVpn roles')
        for role, caller in p['callers'].items():
            source = doc(ref(Path(caller['project']) / 'capability578-source-inputs.json'))
            for name, text in project.source_files('systemvpn', self.run, role, self.value['parameters']).items():
                need(name in source and raw(source[name]) == text.encode(), 'source-bound actual normally compiled caller differs')
            unsigned, signed = zip_members(caller['unsigned']), zip_members(caller['signed'])
            try:
                need(set(unsigned.namelist()) == set(signed.namelist()) and all(unsigned.read(n) == signed.read(n)
                    for n in unsigned.namelist()), 'signer changed compiled payload')
                compiled = loads(signed.read('module.json'))
            finally: unsigned.close(); signed.close()
            need(compiled['app']['bundleName'] == project.bundle('systemvpn', role) and compiled_fields_match(
                compiled['module'], project.module_fields('systemvpn', role, self.value['parameters'])), 'real HAP role/module/permissions')
            profile, signing = doc(caller['verified_profile']), doc(caller['signing'])
            need(project.configure_profile('systemvpn')(loads(__import__('json').dumps(profile)), role, self.env['udid'], compiled) == profile and
                signing['verified_profile'] == profile and signing['scope'] == 'actual_signature_profile_and_codesign_NOT_guest' and
                signing['signed_sha256'] == caller['signed']['sha256'] and signing['unsigned_sha256'] == caller['unsigned']['sha256'], 'actual code/profile/UDID/signature proof')
            for key in ('build_commands', 'sign_commands', 'verify_commands'):
                need(caller[key], 'actual original production commands missing')
                for c in caller[key]:
                    self.bound(c); need(c['exit_code'] == 0 and c['timed_out'] is False, 'actual SDK/signer operation failed')
            need(len(caller['build_commands']) == 2 and 'BUILD SUCCESSFUL' in ''.join((raw(c['stdout']) + raw(c['stderr'])).decode()
                for c in caller['build_commands']), 'normal SDK two-stage compile raw')
            app = [c for c in caller['verify_commands'] if 'verify-app' in c['argv']]
            prof = [c for c in caller['verify_commands'] if 'verify-profile' in c['argv']]
            need(len(app) == len(prof) == 1 and app[0]['argv'][app[0]['argv'].index('-inFile') + 1] == caller['signed']['path'], 'actual verify-app signed input')
            text = (raw(app[0]['stdout']) + raw(app[0]['stderr'])).decode()
            need(all(t in text for t in ('verify codesign success', 'Digest verify result: true', 'verify-app success', 'verify permission sign success')) and
                'verify-profile success' in (raw(prof[0]['stdout']) + raw(prof[0]['stderr'])).decode(), 'actual cryptographic/profile verifier raw')
            leaf = re.split(r'certificate #0\b', text, maxsplit=1)
            need(len(leaf) == 2, 'actual application leaf')
            fingerprints = re.findall(r'SHA256:\s*([0-9A-Fa-f:]+)', re.split(r'certificate #1\b', leaf[1], maxsplit=1)[0])
            need(len(fingerprints) == 1 and fingerprints[0].replace(':', '').upper() == caller['identity']['fingerprint'], 'real application certificate fingerprint')
        identities = self.value['identities']
        need(set(identities) == {r + ':100' for r in project.ROLES} | {'b:' + str(self.value['account']['localId'])}, 'two real account UID namespaces')
        for key, identity in identities.items():
            role, user = identity['role'], identity['user']; need(key == role + ':' + str(user) and identity['uid'] // 200000 == user, 'actual caller account-derived UID')
            row, (body, code) = self.bound(identity['bms']); value = bms_json(body)
            need(code == 0 and script(row) == 'bm dump -n ' + project.bundle('systemvpn', role) + ' -u ' + str(user) and
                any(v == identity['application'] for v in objects(value)) and identity['application']['isSystemApp'] is (role != 'normal') and
                identity['application']['fingerprint'] == p['callers'][role]['identity']['fingerprint'], 'actual BMS signer/system/UID identity')
            row, (body, code) = self.bound(identity['installed_hash'])
            need(code == 0 and body.split() == [p['callers'][role]['signed']['sha256'], identity['guest_hap']], 'actual installed signed bytes')
            self.bound(identity['install'])

    def call(self, op):
        request = op['request']; role, user = op['role'], op['user']; identity = self.value['identities'][role + ':' + str(user)]
        need(set(request) == {'run_id', 'request_id', 'action', 'payload'} and request['run_id'] == self.run and
            re.fullmatch('[a-z0-9_-]{1,64}', request['request_id']), 'literal nonce-bound request')
        start, (body, code) = self.bound(op['start'])
        wanted = ['aa', 'start', '-b', identity['bundle'], '-a', 'EntryAbility', '-m', 'entry', '-u', str(user)]
        for key in ('run_id', 'request_id', 'action'): wanted += ['--ps', key, request[key]]
        wanted += ['--ps', 'payload', __import__('json').dumps(request['payload'], separators=(',', ':'))]
        need(code == 0 and script(start) == shlex.join(wanted) and 'start ability successfully' in body.lower(), 'original actual request argv/AMS result')
        rows = []; remotes = []
        for item in op['journals']:
            data = raw(item['raw']); remote = item['remote']; remotes.append(remote)
            self.bound(item['receive'])
            need(item['receive']['argv'][1:] == ['-t', self.env['target'], 'file', 'recv', remote, item['raw']['path']] and
                item['receive']['exit_code'] == 0 and data.endswith(b'\n') and data.startswith(self.journals.get(remote, b'')), 'actual same-target received append-only journal')
            self.journals[remote] = data; values = [loads(line) for line in data.splitlines()]
            previous = -1
            for n, r in enumerate(values):
                need(set(r) == FIELDS and r['run_id'] == self.run and r['kind'] == 'systemvpn' and r['role'] == role and
                    r['bundle'] == identity['bundle'] and r['uid'] == identity['uid'] and type(r['pid']) is int and r['pid'] > 1 and
                    remote == '/data/app/el2/' + str(user) + '/base/' + identity['bundle'] + '/files/apps579-' + self.run + '-' + str(r['pid']) + '.jsonl' and
                    r['seq'] == n and type(r['active_ms']) is int and r['active_ms'] >= previous, 'actual per-process UID/nonce/sequence/active clock')
                previous = r['active_ms']
            rows += values; self.all_rows[(role, user, remote)] = values
        need(remotes == sorted(set(remotes)), 'unique sorted actual process journals')
        selected = [r for r in rows if r['request_id'] == request['request_id']]
        need(sum(r['event'] == 'request' for r in selected) == sum(r['event'] == 'done' for r in selected) == 1 and
            not any(r['event'] in ('error', 'request-error', 'page-error') for r in selected) and len({r['pid'] for r in selected}) == 1 and
            all(r['action'] == request['action'] for r in selected), 'generic error/missing request/false success')
        actual = loads(next(r['value'] for r in selected if r['event'] == 'request'))
        need(all(actual[k] == request[k] for k in ('run_id', 'request_id', 'action')) and loads(actual['payload']) == request['payload'], 'actual OnNewWant request DATA differs')
        for c in op['commands']: self.bound(c)
        for event in selected:
            if event['event'].endswith('-error'):
                detail=loads(event['value'])
                need(event['event'] in ('setup-error','dns-error') and type(event['code']) is int and event['code']>0 and
                    detail['codeType']=='number' and detail['rawCode']==event['code'], 'real native rejection only; no TypeError/socket/destroy error')
        return selected

    def cleanup(self):
        from batch_network_openvpn_runtime_collect import snapshot_script, parse_snapshot
        seen = set()
        for item in self.value['cleanup']:
            identity = item['identity']; key = identity['role'] + ':' + str(identity['user'])
            need(key not in seen and len(item['cuts']) == 2, 'two independent original UID cleanup censuses')
            seen.add(key); self.bound(item['stop']); self.bound(item['uninstall'])
            for cut in item['cuts']:
                row, (body, code) = self.bound(cut['process'])
                need(code == 0 and script(row) == snapshot_script(cut['nonce'], self.env['boot_id'], mode='uid', uid=identity['uid'], bundle=identity['bundle']), 'complete same-account UID scanner')
                state = parse_snapshot(body, cut['nonce'], self.env['boot_id'], mode='uid', uid=identity['uid'], bundle=identity['bundle'])
                need(not state['processes'], 'caller UID still executable')
                exact = r'(?<![A-Za-z0-9_.])' + re.escape(identity['bundle']) + r'(?![A-Za-z0-9_.])'
                for k in ('ams', 'bms'):
                    _, (text, status) = self.bound(cut[k]); need(status == 0 and not re.search(exact, text), 'original AMS/BMS cleanup incomplete')
        need(seen == set(self.value['identities']) and self.value['account_removed'] is True, 'omitted per-account caller/account cleanup')
        need(self.value['kernel_staged'] is False and self.value['kernel_safe_to_remove'] is True,'unsettled native helper retained')
        row,(body,code)=self.bound(self.value['kernel_cleanup']);remote=self.value['kernel_remote'];q=shlex.quote(remote)
        expected='test ! -L '+q+'/netlink_snapshot && test "$(stat -c %u:%a:%h '+q+'/netlink_snapshot)" = 0:700:1 && '+            'test "$(sha256sum '+q+'/netlink_snapshot)" = '+shlex.quote(self.value['kernel_helper']['binary']['sha256']+'  '+remote+'/netlink_snapshot')+            ' && rm '+q+'/netlink_snapshot && rmdir '+q
        need(code==row['exit_code']==0 and script(row)==expected,'exact owned helper cleanup failed')
        need(self.value['peer_seconds_budget']==240 and self.value['peer_deadline_epoch']==self.value['peer_started_epoch']+240 and
            self.value['host_started_epoch']<self.value['host_finished_epoch']<=self.value['cleanup_started_epoch']<=
            self.value['cleanup_finished_epoch']<self.value['peer_deadline_epoch'],
            'new business must finish in the one original held 240s peer window')
        for op,_ in self.calls:
            if op['peer_deadline_epoch'] is not None and not op['during_cleanup']:
                need(op['peer_deadline_epoch']==self.value['peer_deadline_epoch'] and op['started_epoch']<=op['finished_epoch']<op['peer_deadline_epoch']-15,
                    'actual typed request exceeded retained original-peer cleanup reserve')



def events(e, role, action, user=100):
    return [(op, rows) for op, rows in e.calls if op['role'] == role and op['user'] == user and op['request']['action'] == action]


def one(rows, event):
    selected = [r for r in rows if r['event'] == event]
    need(len(selected) == 1, 'one actual ' + event); return loads(selected[0]['value'])


def vpn_join(packet, output, original_vpn):
    # Complete old strict375/482/TLS/TUN/GET7/nonce/connected2/store/always-on/
    # A32 and final independent Owner closure are independently reconstructed.
    base = original_vpn(packet, output)
    owners = original_owners(packet)
    dedicated = doc(packet['independent_owners']['network']['report'])
    descriptor = dedicated['case_result']['network_whole579']
    e = SystemEvidence(descriptor, packet['archive'], packet['api']['network']['boot'])
    r = e.value
    for role, code in (('normal', 202), ('denied', 201)):
        probes = events(e, role, 'setup'); need(len(probes) == 1, 'one actual permission boundary')
        rows = probes[0][1]; rejected = [v for v in rows if v['event'] == 'setup-error']
        need(len(rejected) == 1 and rejected[0]['code'] == code and loads(rejected[0]['value'])['codeType'] == 'number' and
            not any(v['event'] == 'setup-returned' for v in rows), 'real native role rejection, not a TypeError')
    claims = e.claims
    need(len(claims) >= 6 and {c[0]['role'] for c in claims} == {'a', 'b'} and
        r['identities']['a:100']['uid'] != r['identities']['b:100']['uid'], 'two real SystemVpn owners and recovery generations')
    initial = next(c for op, c in claims if op['role'] == 'a')
    b_requests = events(e, 'b', 'setup'); need(len(b_requests) == 2, 'B contention then real handover setup')
    need(sum(v['event'] == 'setup-error' and v['code'] == 2203002 for v in b_requests[0][1]) == 1 and
        not any(v['event'] == 'setup-returned' for v in b_requests[0][1]) and
        sum(v['event'] == 'setup-returned' for v in b_requests[1][1]) == 1, 'true single-slot B rejection/handover')
    preserved = claims[1][1]
    need(preserved['generation'] == initial['generation'] and preserved['client']['pid'] == initial['client']['pid'] and
        preserved['client']['start'] == initial['client']['start'], 'foreign owner destroy changed A')
    need(len({c['generation'] for _, c in claims}) >= 5, 'reconnect/failure/reentry/recreated process must use genuine fresh native generations')
    for op, rows in e.calls:
        if op['request']['action'] == 'state':
            cfg = one(rows, 'connected-config')
            need(one(rows,'actual-account')==op['user'],'actual SDK caller account differs from AMS/BMS UID namespace')
            apps=one(rows,'connected-app')
            need(apps==([project.bundle('systemvpn',cfg['vpnId'].split('-')[-1])] if cfg['defined'] else []),
                'actual connected-app getter must identify the real current SystemVpn owner or genuine absence')
            if cfg['defined']:
                need(cfg['userId'] == op['user'] and any(a['address']['family'] == 1 for a in cfg['addresses']) and
                    any(a['address']['family'] == 2 for a in cfg['addresses']) and cfg['dnsAddresses'] in (['10.73.0.1'],['10.73.0.254']) and
                    any(rt['destination']['address']['family'] == 2 for rt in cfg['routes']), 'actual public negotiated IPv4/IPv6/DNS/route family')
    # All named source gaps now require the actual native positive proof below.
    failure = events(e, 'a', 'failure-setup'); need(len(failure) == 1 and any(v['event'] == 'setup-entered' for v in failure[0][1]), 'actual TLS worker failure request')
    failed_cut = [s for op, s in e.native if op['label'] == 'failed_worker']
    need(failed_cut and all(p['exe'] == '/system/bin/qemu_openvpn_service' and p['ppid'] == 1 for p in failed_cut[-1]['processes'].values()), 'real failed worker did not settle')
    failed_rows=failure[0][1];begin=next(v['active_ms'] for v in failed_rows if v['event']=='setup-entered')
    follow=[rows[0]['active_ms'] for op,rows in events(e,'a','setup') if rows[0]['active_ms']>begin]
    need(follow,'actual post-failure reconnect request')
    end=min(follow)
    late=[v for rows in e.all_rows.values() for v in rows]
    need(any(v['role']=='a' and v['event']=='vpn-connect-multi' and begin<=v['active_ms']<=end and
        loads(v['value']).get('vpnId')==e.run+'-a' and loads(v['value']).get('isConnected') is False for v in late),
        'actual failed TLS worker must dispatch the owned asynchronous disconnect before recovery')
    account = r['account']; need(account['localId'] >= 101 and account['localName'] == 'whole579_' + e.run and account['type'] == 2,
        'actual nonce-owned GUEST account, not userId config spoof')
    foreign = events(e, 'b', 'setup', account['localId']); need(len(foreign) == 1 and
        sum(v['event'] == 'setup-error' and v['code'] == 2203001 for v in foreign[0][1]) == 1 and
        any(v['event'] == 'setup-entered' for v in foreign[0][1]), 'real different account UID must reach native SystemVpn type rejection')
    account_rows = events(e, 'account', 'account-remove'); need(len(account_rows) == 1 and
        all(a['localId'] != account['localId'] for a in one(account_rows[0][1], 'account-remove')['accounts']) and
        one(account_rows[0][1], 'account-remove')['foreground'] == 100, 'actual public account removal/foreground restore')
    owned_ids = {e.run + '-a', e.run + '-b'}
    baselines = [set(one(rows, 'store-baseline')) for _, rows in e.calls if any(v['event'] == 'store-baseline' for v in rows)]
    cleanups = [set(one(rows, 'store-cleanup')) for _, rows in e.calls if any(v['event'] == 'store-cleanup' for v in rows)]
    need(len(baselines) == len(cleanups) == 2, 'both genuine public stored profiles need original IDs and actual cleanup readback')
    foreign_ids = set.union(*baselines) - owned_ids
    need(all((ids - owned_ids) == foreign_ids for ids in baselines + cleanups) and
        all(not any(item == op['request']['run_id'] + '-' + op['role'] for item in one(rows, 'store-cleanup'))
            for op, rows in e.calls if any(v['event'] == 'store-cleanup' for v in rows)),
        'owned cleanup must preserve every original unrelated SystemVpn store identity')
    # All watcher callbacks are read from full late journal snapshots. No
    # summary count or an old process's request may satisfy this contract.
    all_rows = [row for rows in e.all_rows.values() for row in rows]
    for role in ('a', 'b'):
        watched = events(e, role, 'watch'); need(watched, 'real callback registration')
        for op, rows in watched:
            callbacks = [v for v in all_rows if v['role'] == role and v['request_id'] == op['request']['request_id'] and
                v['event'] in ('vpn-connect', 'vpn-connect-multi')]
            need(callbacks and any(loads(v['value'])['isConnected'] is True for v in callbacks) and
                any(loads(v['value'])['isConnected'] is False for v in callbacks), 'actual complete connected/disconnected callback stream')
            off = next((values[-1] for operation, values in e.calls if operation['role'] == role and operation['request']['action'] == 'off' and
                values[-1]['active_ms'] >= rows[0]['active_ms']), None)
            need(off is not None and not any(v['active_ms'] > off['active_ms'] for v in callbacks), 'callback after exact off boundary')
    identities = events(e, 'a', 'identity'); need(len({rows[-1]['pid'] for _, rows in identities}) >= 2, 'actual caller process exit/recreation missing')
    deaths=[op for op in r['operations'] if op['kind']=='owner-process-death']
    death_cleanup=[s for op,s in e.native if op['label']=='process_recreated']
    need(len(deaths)==1 and death_cleanup and all(v['exe']=='/system/bin/qemu_openvpn_service' and v['ppid']==1
        for v in death_cleanup[-1]['processes'].values()),'active owner death must really release its worker/client/bridge before recreation')
    death_index=next(i for i,op in enumerate(r['operations']) if op['kind']=='owner-process-death')
    later=[op for op in r['operations'][death_index+1:] if op['kind']=='claim' and op['role']=='a']
    need(later and all(op['claim']['generation']!=deaths[0]['active_claim']['generation'] for op in later),
        'genuine recreated owner must establish a fresh native session')
    peer_case = Path(doc(doc(r['phases'][0]['original_runtime_envelope'])['intent'])['peer']['case'])
    wire_ref = ref(peer_case / 'runtime/live/whole.jsonl'); wire = [loads(line) for line in raw(wire_ref).splitlines()]
    peer = doc(ref(peer_case / 'runtime/live/peer-evidence.json'))
    need(peer['run_id'] == r['parameters']['peer_run'] and peer['owned_child_reaped'] is True and peer['peer_tun_removed'] is True and
        peer['failures'] == [] and peer['nonce_packets'] == 2 and peer['nonce_completed'] == 1, 'original peer baseline count/custody changed')
    need(wire and all(v['schema'] == 'network-whole579-peer-wire/v1' and v['run_id'] == peer['run_id'] and
        v['ingress_ifindex'] == peer['tun_ifindex'] and v['uid'] == 0 and v['pid']==peer['peer_pid'] and v['proc_stat'].split(')')[-1].split()[19]==peer['peer_proc_stat'].split(')')[-1].split()[19] and type(v['netns']) is int and
        v['boot_id']==peer['kernel_boot_id'] and v['proc_stat'].startswith(str(v['pid'])+' ') and
        type(v['active_ns']) is int for v in wire), 'actual independent original TUN ingress wire identity')
    for op, rows in e.calls:
        action = op['request']['action']
        if action in ('traffic4', 'traffic6', 'reconfigure', 'restore-peer'):
            first = one(rows, 'nonce-tx'); result = one(rows, 'nonce-result'); family = 2 if action == 'traffic6' else 1
            need(first['family'] == result['family'] == family and result['actual'].startswith('VPN3 ') and
                any(v['kind'] == ('ipv4' if family == 1 else 'ipv6') and bytes.fromhex(v['request_hex']).decode() == first['text'] for v in wire) and
                any(bytes.fromhex(v['response_hex']).decode() == result['actual'] and v['complete'] for v in wire), 'independent actual dual-stack server nonce send/receive/reply join')
        if action == 'dns':
            domain = one(rows, 'dns-question'); answers = one(rows, 'dns-answer')
            need(domain == 'n' + e.run + '.' + op['request']['request_id'].replace('_', '-') + '.whole579.invalid' and
                ({'10.73.0.1', 'fd73:579::1'} <= {a['address'] for a in answers} or {'10.73.0.254','fd73:579::fe'} <= {a['address'] for a in answers}), 'OS resolver dual-stack outcome')
            encoded = b''.join(bytes([len(s)]) + s.encode() for s in domain.split('.')) + b'\0'
            from network_whole579_options_replay import question,answer_matches
            matches = [v for v in wire if v['kind'] in ('dns','dns-port','dns-reconfigured','dot','doh') and v['request_hex'] and question(bytes.fromhex(v['request_hex']))[0]==domain]
            need(matches and all(bytes.fromhex(v['request_hex'])[:2] == bytes.fromhex(v['response_hex'])[:2] for v in matches) and
                {question(bytes.fromhex(v['request_hex']))[1] for v in matches} == {1,28}, 'actual OS DNS A+AAAA queries and transaction replies crossed original TUN')
    from network_whole579_options_replay import replay as replay_options
    positive=replay_options(e,wire)
    proof=save(output/'vpn-whole-raw.json',dict(original=base['proof'],new=descriptor,wire=wire_ref,
        original_owner_settlement=owners,normal_source=ref(Path(__file__)),native_options=positive,
        not_claimed=positive['not_claimed']))
    return dict(proof=proof,supported_scope_complete=True,whole_id_runtime_pass=True,remaining=[],
        related_boot_ids=[e.env['boot_id']],not_claimed=positive['not_claimed'])


def p2p_join(e, descriptor, baseline_proof, output):
    from provider579_wifi_replay import Radio
    from apps_providers579_wifi_runtime import verify_exchange, verify_dora
    value = doc(descriptor)
    need(value['schema'] == 'network-whole579-p2p/v1' and value['run_id'] == e.run and value['boot_id'] == e.env['boot_id'] and
        value['archive_sha256'] == e.archive['sha256'] and value['failures'] == [] and
        not any(r.get('error') for r in value['cleanup']) and not value.get('original_cleanup_error'), 'actual P2P cleanup/producer failed')
    radio = Radio(e);radio.network('wifi-radio-prepare',{},e.only('network_wifi-radio-prepare'))
    requests = {}; calls = []; networks = []
    for op in value['operations']:
        kind, record = op['kind'], op['record']
        if kind == 'request':
            need(record['request_id'] not in requests and record['run_id'] == e.run, 'one actual P2P request')
            requests[record['request_id']] = record
        elif kind == 'start':
            cut = e.callback(record); role, action, request = cut['arguments']
            need(requests[request['request_id']] == {'role': role, **request} and doc(record['request']) == request, 'actual started P2P request binding')
        elif kind == 'collect':
            cut = e.callback(record); role, request_id = cut['arguments']; request = requests[request_id]
            rows = [r for r in e.journal(record, role) if r['request_id'] == request_id]
            need(rows and sum(r['event'] == 'request' for r in rows) == 1 and len({r['pid'] for r in rows}) == 1, 'real P2P PID/nonce/request journal')
            errors = [r for r in rows if r['event'] in ('error', 'request-error', 'page-error')]
            if role != 'grant':
                need(len(errors) == 1 and errors[0]['code'] in (201, 202) and not any(r['event'] == 'done' for r in rows), 'actual P2P role denial')
            else: need(not errors and sum(r['event'] == 'done' for r in rows) == 1, 'actual P2P public action failed')
            calls.append((request, rows, record))
        elif kind.startswith('network_'):
            action = kind[len('network_'):]; cut = e.callback(record)
            need(cut['callback'] == 'network' and cut['arguments'][0] == action, 'actual finite network callback')
            radio.journals(record); networks.append((action, record))
            if action == 'wifi-p2p-data':
                need((record['initial_netns'],record['peer_netns'])==radio.namespaces,'same original held radio namespace pair')
                verify_exchange(record, e.run)
        else: raise ValueError('unknown P2P actual operation')
    states = [one(rows, 'p2p-state') for req, rows, _ in calls if req['action'] == 'p2p-state' and req['role'] == 'grant']
    peers = [r for a, r in networks if a == 'wifi-p2p-peer-collect']
    need(peers and states, 'independent actual P2P discovery/state')
    mac = peers[0]['peer_mac']
    need(all(r['peer_mac'] == mac and 'mode=P2P GO' in raw(r['status']).decode().splitlines() for r in peers) and
        any(any(p['deviceAddress'].lower() == mac for p in s['peers']) for s in states), 'real independent P2P GO/public discovery match')
    connected = [s for s in states if s['linked']['connectState'] == 1 and not s['linked']['isGroupOwner'] and
        s['group']['ownerInfo']['deviceAddress'].lower() == mac]
    need(connected and any(s['linked']['connectState'] == 1 and s['linked']['isGroupOwner'] and
        s['group']['groupName'] == 'DIRECT-whole579_' + e.run[:8] for s in states), 'actual public GC and createGroup GO both required')
    exchanges = [r for a, r in networks if a == 'wifi-p2p-data']
    need(len(exchanges) == 1 and exchanges[0]['interface'] in {s['group']['interface'] for s in connected}, 'actual P2P interface carries nonce data')
    station = next(raw(r['station']).decode() for r in reversed(peers) if '[AUTHORIZED]' in raw(r['station']).decode())
    matches = re.findall(r'^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$', station, re.M)
    need(len(matches) == 1, 'real independent authorized P2P client MAC')
    lease = verify_dora(exchanges[0], 'dhcp-server-rx', 'dhcp-server-tx', matches[0])
    need(lease['address'] == '192.0.2.2' and lease['server'] == '192.0.2.1', 'actual P2P DHCP outcome on independent peer')
    watched = [req['request_id'] for req, _, _ in calls if req['action'] == 'p2p-watch']
    need(len(watched) == 1, 'one actual registered P2P callback set')
    full = []
    for _, rows, record in reversed(calls):
        if record is not None:
            full = e.journal(record, 'grant') if rows[0]['role'] == 'grant' else full
            if full: break
    callbacks = [r for r in full if r['request_id'] == watched[0]]
    need(any(r['event'] == 'p2p-peers' and any(p['deviceAddress'].lower() == mac for p in loads(r['value'])) for r in callbacks) and
        any(r['event'] == 'p2p-connection' and loads(r['value'])['connectState'] == 1 for r in callbacks) and
        any(r['event'] == 'p2p-connection' and loads(r['value'])['connectState'] == 0 for r in callbacks), 'real discovery/connected/removal callback stream')
    off = next(rows[-1] for req, rows, _ in calls if req['action'] == 'p2p-off')
    need(not any(r['active_ms'] > off['active_ms'] for r in callbacks) and
        max(rows[-1]['active_ms'] for req, rows, _ in calls if req['action'] == 'p2p-state') - off['active_ms'] >= 5000,
        'actual off callback quiet interval')
    need(value['final']['linked']['connectState'] == 0 and value['final']['groups'] == value['baseline']['groups'], 'real initial group vector restored')
    proof = save(output / 'wifi-whole-raw.json', dict(original_STA_AP_UID_UI_idle=baseline_proof, actual_P2P=descriptor,
        dora=lease, source=ref(Path(__file__))))
    return dict(proof=proof, supported_scope_complete=True, whole_id_runtime_pass=True, remaining=[],
                related_boot_ids=[e.env['boot_id']])
