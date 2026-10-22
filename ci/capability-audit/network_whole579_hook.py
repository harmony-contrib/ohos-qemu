"""Two literal phases inside peer15; no resource/actor/Owner replacement."""
from pathlib import Path
import sys
for _name in ('network_whole579_records', 'network_whole579_sources', 'network_whole579_project', 'network_whole579_session', 'network_whole579_hook', 'network_whole579_p2p', 'network_whole579_replay', 'network_whole579_options_replay'):
    _old=sys.modules.get(_name)
    if _old is not None and Path(_old.__file__).resolve()!=Path(__file__).resolve().with_name(_name+'.py'):
        raise ValueError('foreign cached whole Network source '+_name)
import time
from network_whole579_records import need, raw, doc, ref, save
from network_whole579_session import Session


def one(rows, name):
    selected = [r for r in rows if r['event'] == name]
    need(len(selected) == 1, 'one actual ' + name)
    from network_whole579_records import loads
    return loads(selected[0]['value'])


def bind(io, envelope):
    """Root supplies the REAL IO, not the legacy ParentGuest read-only view.

    Called by the admitted Network BoundRun before any peer/normal SDK work.
    The existing connected hook still receives its own unchanged view.
    """
    need(io.owner.vm is io.guest and not io._closed and not hasattr(io, 'network_whole579_state'), 'one original held Network business hook')
    from api26_connected579_sources import load
    original = load().steps.C
    config, runtime_envelope, _ = original.runtime_envelope(envelope)
    challenge = doc(ref(Path(config['sdk']['output']) / 'projects/challenge.json'))
    need(challenge['run_id'] == config['peer']['run_id'] and challenge['config'] == config and
        challenge['profile']['path'] == str(Path(config['sdk']['output']) / 'projects/client.ovpn'), 'actual normal original peer profile/challenge')
    raw(challenge['profile'])
    state = None
    phases = []

    def phase(name):
        nonlocal state
        need((phases, name) in (([], 'prepare'), (['prepare'], 'run')), 'literal prepare/run order only')
        if name == 'prepare':
            state = Session(io, challenge['profile'], challenge['run_id'], config)
        start = time.monotonic_ns()
        state.value['phases'].append(dict(name=name, started_monotonic_ns=start, finished_monotonic_ns=None,
            boot_id=io.boot_id, archive_sha256=io.archive_sha256, original_runtime_envelope=envelope,
            original_challenge=ref(Path(config['sdk']['output']) / 'projects/challenge.json')))
        state.persist()
        try:
            if name == 'prepare':
                state.prepare()
            else:
                ready = Path(config['peer']['case']) / 'runtime/live/ready.json'
                live = Path(config['peer']['case']) / 'runtime/live/peer-evidence.json'
                actual = doc(ref(live))
                need(doc(ref(ready))['run_id'] == challenge['run_id'] and actual['run_id'] == challenge['run_id'] and
                    actual['failures'] == [] and actual.get('owned_child_reaped') is not True, 'same original peer still held before finally-stop')
                state.value['peer_live_at_start'] = ref(live)
                # The mutable file gets a separate immutable byte copy, never
                # a Ref that will silently point at a later peer state.
                copied = state.output / 'peer-before-whole.json'; copied.write_bytes(raw(state.value['peer_live_at_start']))
                state.value['peer_live_at_start'] = ref(copied)
                state.value['peer_started_epoch'] = actual['started_epoch']
                state.value['peer_seconds_budget'] = 240
                state.value['host_started_epoch'] = time.time()
                state.peer_deadline = actual['started_epoch'] + 240
                state.value['peer_deadline_epoch'] = state.peer_deadline
                need(state.peer_deadline-time.time()>15,'original peer has no real business/cleanup budget left')
                run(state)
        except BaseException as error:
            state.value['failures'].append(dict(phase=name, type=type(error).__name__, error=str(error)))
            raise
        finally:
            state.value['phases'][-1]['finished_monotonic_ns'] = time.monotonic_ns()
            if name=='run':state.value['host_finished_epoch']=time.time()
            state.persist()
            if name == 'run':
                try:
                    state.cleanup()
                    need(state.value['cleanup_finished_epoch']<state.peer_deadline,'real whole business/restoration exhausted the original peer window')
                except BaseException as error:
                    state.value['failures'].append(dict(phase='run-cleanup',type=type(error).__name__,error=str(error)))
                    raise
                finally: state.persist()
        phases.append(name)
    return phase


def run(s):
    """Independent public SystemVpn business under the original held TLS peer."""
    from batch_network_openvpn_runtime_collect import claimed
    def call(role, action, **kw): return s.call(role, action, **kw)
    def state(role='a'): return one(call(role, 'state'), 'connected-config')
    def connected(role,variant='normal'):
        deadline = time.monotonic() + 25
        while True:
            v = state(role)
            if v['defined'] and v['vpnId'] == s.io.run_id + '-' + role:
                snap = s.native('connected_' + role)
                import hashlib
                expected_hash=hashlib.sha256(__import__('network_whole579_project').profile_variant(s.value['parameters'],variant).encode()).hexdigest()
                claim = claimed(snap, expected_hash)
                hashed=s.shell('test ! -L '+__import__('shlex').quote(claim['config'])+' && sha256sum '+
                    __import__('shlex').quote(claim['config']),'profile_hash_'+role)
                need(hashed['stdout'].split()==[expected_hash,claim['config']],
                    'actual native worker must consume this exact normally generated original TLS profile')
                s.value['operations'].append(dict(kind='claim',role=role,variant=variant,claim=claim,profile_hash=s.io.ref_receipt(hashed)));s.persist()
                return v,claim
            need(time.monotonic() < deadline, 'real negotiated SystemVpn connected state missing')
            time.sleep(.1)
    def empty(label):
        deadline = time.monotonic() + 20
        while True:
            v = state()
            if label == 'invalid' or label == 'failed_worker':
                need(not v['defined'], 'current source-gap probe/TLS identity failure unexpectedly reached CONNECTED without the required independent positive policy oracle')
            snap = s.native(label)
            if not v['defined'] and all(p['exe'] == '/system/bin/qemu_openvpn_service' and p['ppid'] == 1
                for p in snap['processes'].values()) and all(e.startswith('backend.lock|') for e in snap['entries']):
                return
            need(time.monotonic() < deadline, 'old real worker/group/session/connected config did not recover')
            time.sleep(.1)
    def setup(role):
        events = call(role, 'setup')
        need(sum(r['event'] == 'setup-returned' for r in events) == 1 and not any(r['event'] == 'setup-error' for r in events), 'native SystemVpn setup refused')
        return connected(role)
    def traffic(role):
        for family in (4, 6):
            events = call(role, 'traffic' + str(family))
            result = one(events, 'nonce-result')
            need(result['actual'].startswith('VPN3 ') and not any(r['event'] == 'socket-error' for r in events), 'actual independent dual-stack peer challenge failed')
        call(role, 'dns'); s.platform('dual_stack_' + role)
    call('a', 'identity'); call('b', 'identity')
    need(s.value['identities']['a:100']['uid'] != s.value['identities']['b:100']['uid'], 'two distinct real SystemVpn owners required')
    empty('baseline')
    for role, code in (('normal', 202), ('denied', 201)):
        events = call(role, 'setup')
        rejected = [r for r in events if r['event'] == 'setup-error']
        need(len(rejected) == 1 and rejected[0]['code'] == code and not any(r['event'] == 'setup-returned' for r in events), 'actual native ordinary/system-without-permission boundary')
        empty('role_' + role)
    call('a', 'watch'); call('b', 'watch')
    config_a, first = setup('a'); traffic('a')
    # B is another true SystemVpn UI context/UID; no VpnExtension is present.
    conflict = call('b', 'setup')
    need(sum(r['event'] == 'setup-error' and r['code'] == 2203002 for r in conflict) == 1 and
        not any(r['event'] == 'setup-returned' for r in conflict), 'second SystemVpn single-slot contention must reject')
    call('b', 'destroy')
    preserved, still = connected('a')
    need(preserved['vpnId'] == config_a['vpnId'] and still['generation'] == first['generation'] and
        still['client']['pid'] == first['client']['pid'] and still['client']['start'] == first['client']['start'], 'B destroy touched A real session')
    call('a', 'destroy'); empty('handover_a')
    _, second = setup('b'); traffic('b')
    need(second['generation'] != first['generation'], 'actual owner handover must create a fresh native generation')
    call('b', 'destroy'); empty('handover_b')
    # Positive native configuration/route/resolver paths. The final reader
    # reconstructs their real kernel and independent peer transactions; no
    # errno/current rejection can substitute for these outcomes.
    for option in ('metric', 'dnsport', 'splitdns', 'dot', 'doh', 'badcert'):
        before=s.kernel('before_'+option)
        values=call('a','option',payload={'option':option})
        need(sum(r['event']=='setup-returned' for r in values)==1 and not any(r['event']=='setup-error' for r in values),'required positive normal backend option failed')
        _,claim=connected('a',option)
        s.kernel('connected_'+option)
        if option=='badcert':
            rows=call('a','dns-bad-cert')
            need(any(r['event']=='dns-error' for r in rows) and not any(r['event']=='dns-answer' for r in rows),'real wrong-DNS-certificate resolution must reject')
        else:
            traffic('a')
            if option=='splitdns':call('a','dns-outside')
        if option in ('dnsport','splitdns','dot','doh','badcert'):s.dns_wire(option,claim)
        s.platform('option_'+option)
        call('a','destroy');empty('option_destroy_'+option);s.kernel('after_'+option)
    rejected=call('a','option',payload={'option':'invalid'})
    need(any(r['event']=='setup-error' for r in rejected) and not any(r['event']=='setup-returned' for r in rejected),'real forbidden executable option must reject')
    empty('invalid');call('a','destroy')
    # The real existing server receives a nonce-bound administrative request,
    # changes its nonce-owned CCD and asks its existing authenticated client to
    # reconnect. No replacement peer, fake callback or guest PID signal.
    values=call('a','option',payload={'option':'persist'})
    need(any(r['event']=='setup-returned' for r in values) and not any(r['event']=='setup-error' for r in values),'actual persist-tun setup failed')
    _,persistent=connected('a','persist');s.kernel('persist_before');traffic('a')
    call('a','reconfigure')
    deadline=time.monotonic()+30
    while True:
        current=state('a')
        if current['defined'] and current['dnsAddresses']==['10.73.0.254']:break
        need(time.monotonic()<deadline,'real persistent renegotiation did not replace its public DNS/routes');time.sleep(.1)
    _,reconfigured=connected('a','persist');s.kernel('persist_after');traffic('a');s.platform('persist_reconfigured')
    need(reconfigured['generation']==persistent['generation'] and reconfigured['client']['pid']==persistent['client']['pid'] and
        reconfigured['client']['start']==persistent['client']['start'],'persistent reconnect replaced the original native session/client')
    call('a','restore-peer')
    deadline=time.monotonic()+30
    while True:
        current=state('a')
        if current['defined'] and current['dnsAddresses']==['10.73.0.1']:break
        need(time.monotonic()<deadline,'original CCD/DNS did not recover on the same peer/session');time.sleep(.1)
    connected('a','persist');s.kernel('persist_restored');traffic('a')
    call('a','destroy');empty('persist_destroy');s.kernel('persist_destroyed')
    failed = call('a', 'failure-setup')
    # Public setUp may acknowledge worker ownership before real TLS failure.
    # A returned fd alone is not CONNECTED; native and peer error raw are joined
    # by the final reader. Never signal a PID or fabricate worker completion.
    s.platform('tls_identity_failure')
    empty('failed_worker')
    _, recovered = setup('a'); traffic('a')
    need(recovered['generation'] not in (first['generation'], second['generation']), 'true worker failure recovery generation missing')
    call('a', 'destroy'); empty('recovered_destroy')
    call('a', 'off'); call('b', 'off')
    # Real public guest account; account100 config/userId data cannot substitute
    # a different process UID. GUEST is an explicit CheckCurrentAccountType
    # rejection even while actually activated. No account database edits.
    call('account', 'accounts')
    made = one(call('account', 'account-create'), 'account-created')
    need(made['localId'] >= 101 and made['localName'] == 'whole579_' + s.io.run_id, 'actual nonce-owned guest account')
    s.value['account'] = made; s.persist(); s.install('b', made['localId'])
    call('account', 'account-activate')
    foreign = call('b', 'setup', user=made['localId'])
    need(sum(r['event'] == 'setup-error' and r['code'] == 2203001 for r in foreign) == 1 and
        not any(r['event'] == 'setup-returned' for r in foreign), 'actual guest-account native type denial')
    call('account', 'account-restore'); call('account', 'accounts')
    empty('account_recovered')
    # Explicit on/off/re-entry and whole process restart recovery. Old callback
    # request IDs must remain quiet; actual PID change is checked in replay.
    s.value['quiet_start'] = call('a', 'state')[-1]['active_ms']
    setup('a'); call('a', 'destroy'); empty('off_stream')
    while True:
        values = call('a', 'state')
        if values[-1]['active_ms'] - s.value['quiet_start'] >= 5000: break
        time.sleep(.25)
    call('a', 'watch'); setup('a'); traffic('a'); call('a', 'destroy'); empty('last')
    call('a', 'off'); call('b', 'off')
    _,death_session=setup('a');traffic('a')
    old=call('a','identity');old_pid=old[-1]['pid']
    stopped=s.shell('aa force-stop org.ohos.qemu.networkwhole579.a -u 100','owner_a_real_process_death')
    s.value['operations'].append(dict(kind='owner-process-death',old_pid=old_pid,active_claim=death_session,command=s.io.ref_receipt(stopped)));s.persist()
    fresh=call('a','identity');need(fresh[-1]['pid']!=old_pid,'actual new caller process PID required')
    empty('process_recreated');call('a','watch');setup('a');traffic('a');call('a','destroy');empty('recreated_destroy');call('a','off')
    s.platform('final')


def retain_closed(io):
    """After original io.close; whole Owner finish remains a separate obligation."""
    s = getattr(io, 'network_whole579_state', None)
    need(s is not None and io._closed, 'original IO must really close before whole retention')
    actual = ref(io.output / 'io.json')
    need(doc(actual)['commands'] == io.receipts, 'closed original IO raw command order')
    return save(s.output / 'closed.json', dict(schema='network-whole579-closed-io/v1', io=actual,
        report=ref(s.output / 'attempt.json'), archive_sha256=io.archive_sha256,
        boot_id=io.boot_id, run_id=io.run_id, original_owner_finish_still_required=True))
