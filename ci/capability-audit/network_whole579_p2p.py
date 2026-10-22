"""Public P2P group/data/removal before original WiFi cleanup, same 7 callbacks."""
from pathlib import Path
import sys
for _name in ('network_whole579_records', 'network_whole579_sources', 'network_whole579_project', 'network_whole579_session', 'network_whole579_hook', 'network_whole579_p2p', 'network_whole579_replay', 'network_whole579_options_replay'):
    _old=sys.modules.get(_name)
    if _old is not None and Path(_old.__file__).resolve()!=Path(__file__).resolve().with_name(_name+'.py'):
        raise ValueError('foreign cached whole Network source '+_name)
import time
from network_whole579_records import need, save

KEYS = {'prepare_callers', 'install', 'start', 'input', 'collect', 'network', 'cleanup'}


def wrap_callbacks(io, callbacks):
    need(set(callbacks) == KEYS and all(callable(v) for v in callbacks.values()) and
         io.owner.vm is io.guest and not io._closed, 'original held WiFi callbacks only')
    original = callbacks['cleanup']
    attempted = False
    value = None

    def cleanup():
        nonlocal attempted, value
        if attempted:
            return original()
        attempted = True
        out = Path(io.output) / 'network-whole579-p2p'
        out.mkdir(mode=0o700, exist_ok=False)
        result = dict(schema='network-whole579-p2p/v1', run_id=io.run_id, archive_sha256=io.archive_sha256,
            boot_id=io.boot_id, operations=[], failures=[], cleanup=[], runtime_pass=False,
            first_artifact_behavior_gate_passed=False)
        serial = 0
        error = None
        peer_started = False
        watch_started = False
        baseline = None

        def keep(kind, record):
            result['operations'].append(dict(kind=kind, record=record)); return record

        def call(action, payload=None, role='grant', boundary=False):
            nonlocal serial
            from apps_providers579_runtime import rows
            serial += 1
            request = dict(run_id=io.run_id, request_id='wholep2p_' + str(serial) + '_' + action.replace('-', '_'),
                           action=action, payload=payload or {})
            keep('request', dict(role=role, **request))
            keep('start', callbacks['start'](role, action, request))
            data = keep('collect', callbacks['collect'](role, request['request_id']))
            records = rows(data['journal'], io.run_id, role, request['request_id'])
            need(sum(r['event'] == 'request' for r in records) == 1, 'one actual P2P typed dispatch')
            errors = [r for r in records if r['event'] in ('error', 'request-error', 'page-error')]
            if boundary:
                need(len(errors) == 1 and errors[0]['code'] in (201, 202) and not any(r['event'] == 'done' for r in records), 'real no-permission P2P native denial')
            else:
                need(not errors and sum(r['event'] == 'done' for r in records) == 1, 'real P2P public action failed')
            return records

        def one(records, event):
            from network_whole579_records import loads
            found = [r for r in records if r['event'] == event]
            need(len(found) == 1, 'one actual ' + event); return loads(found[0]['value'])

        def network(action, data=None):
            return keep('network_' + action, callbacks['network'](action, data or {}))

        def settled(predicate, message):
            deadline = time.monotonic() + 45
            while True:
                records = call('p2p-state'); state = one(records, 'p2p-state')
                if predicate(state): return records, state
                need(time.monotonic() < deadline, message); time.sleep(.15)

        try:
            for role in ('normal', 'denied'):
                call('p2p-discover', role=role, boundary=True)
            # Original provider body has restored its own initial STA/AP; its
            # real spare wiphy and namespace still belong to original cleanup.
            call('p2p-watch'); watch_started = True
            baseline = one(call('p2p-snapshot'), 'p2p-before')
            need(baseline['linked']['connectState'] == 0, 'refuse unrelated initial P2P group')
            result['baseline'] = baseline
            network('wifi-p2p-peer-start'); peer_started = True
            observed_peer = network('wifi-p2p-peer-collect'); mac = observed_peer['peer_mac']
            call('p2p-discover')
            _, discovered = settled(lambda s: any(p['deviceAddress'].lower() == mac for p in s['peers']),
                                    'actual independent GO not discovered through public P2P service')
            network('wifi-p2p-arm')
            call('p2p-connect', {'peer_mac': mac})
            _, group = settled(lambda s: s['linked']['connectState'] == 1 and not s['linked']['isGroupOwner'] and
                s['group']['ownerInfo']['deviceAddress'].lower() == mac, 'real public P2P group/WPS negotiation failed')
            peer = network('wifi-p2p-peer-collect')
            from network_whole579_records import raw
            need('mode=P2P GO' in raw(peer['status']).decode().splitlines() and
                '[AUTHORIZED]' in raw(peer['station']).decode(), 'independent stock P2P GO must authorize actual OS client')
            exchange = network('wifi-p2p-data', {'interface': group['group']['interface']})
            from apps_providers579_wifi_runtime import verify_exchange
            verify_exchange(exchange, io.run_id)
            network('wifi-ip-collect')
            call('p2p-remove')
            settled(lambda s: s['linked']['connectState'] == 0, 'public P2P removal did not disconnect')
            network('wifi-peer-stop'); peer_started = False
            # Exercise the other public group path, independently of a client
            # connect request. No private registry or synthesized callback.
            call('p2p-create')
            _, go = settled(lambda s: s['linked']['connectState'] == 1 and s['linked']['isGroupOwner'] and
                s['group']['groupName'] == 'DIRECT-whole579_' + io.run_id[:8], 'real public createGroup did not create the owned GO')
            network('wifi-ip-collect'); call('p2p-remove')
            settled(lambda s: s['linked']['connectState'] == 0, 'owned GO removal did not settle')
            off = call('p2p-off'); watch_started = False
            start_active = off[-1]['active_ms']
            # A real active-time interval, not a producer quiet boolean.
            while True:
                rows = call('p2p-state')
                if rows[-1]['active_ms'] - start_active >= 5000: break
                time.sleep(.25)
            call('p2p-restore')
            final = one(call('p2p-state'), 'p2p-state')
            need(final['linked']['connectState'] == 0 and final['groups'] == baseline['groups'], 'public initial persistent P2P group vector not restored')
            result['final'] = final
        except BaseException as caught:
            error = caught
            result['failures'].append(dict(type=type(caught).__name__, error=str(caught)))
        finally:
            # Continue every independent restoration attempt and then call the
            # entire original networking44/STA/AP/portal/idle cleanup unchanged.
            for name, function in (
                ('p2p-off', lambda: call('p2p-off') if watch_started else None),
                ('p2p-restore', lambda: call('p2p-restore') if baseline is not None else None),
                ('peer-stop', lambda: network('wifi-peer-stop') if peer_started else None)):
                try: result['cleanup'].append(dict(action=name, result=function(), error=None))
                except BaseException as caught:
                    result['cleanup'].append(dict(action=name, error=type(caught).__name__ + ': ' + str(caught)))
                    if error is None: error = caught
            try:
                value = original()
                result['original_cleanup'] = value
            except BaseException as caught:
                result['original_cleanup_error'] = type(caught).__name__ + ': ' + str(caught)
                if error is None: error = caught
            io.network_whole579_p2p_ref = save(out / 'attempt.json', result)
        if error is not None: raise error
        return value
    return dict(callbacks, cleanup=cleanup)
