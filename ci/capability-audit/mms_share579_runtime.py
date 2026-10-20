"""New MMS/Share boundaries on one original held guest, after old Share8+MMS1.

No Owner, VM, compiler, signer, transport or permission constructor. The root
adds this fixed family to its existing caller builder and invokes run with its
actual deferred MMS facts Ref. All observations still require raw replay.
"""
from pathlib import Path
import json
import secrets
import time

from capability578_owned_io import reference, require
from guest_ui import NodeNotReady, LayoutNotReady, select_node
from hap_identity_binding import strict_json
from mms_share579_project import BUNDLES, CASES
from mms_share579_bindings import bind, MMS, CACHE
from mms_share579_verify import verify_observations


def value(row):
    return strict_json(row['value'])


def event(binding, role, request, name):
    rows = binding.wait(role, request['operation'], name)
    selected = [row for row in rows if row['event'] == name]
    require(len(selected) == 1, 'exact actual ordinary event required')
    return selected[0]


def request(binding, case, role, action, object_id, **kwargs):
    r = binding.request(role, action, case['case'], object_id, **kwargs)
    case['operations'].append({'role': role, 'request': r})
    return r


def read_owner(binding, case):
    r = request(binding, case, 'owner', 'owner-read', case['object'])
    actual = value(event(binding, 'owner', r, 'owner.file'))
    require(actual == case['source'], 'original source content/inode/URI changed before release observation')
    return r


def probe(binding, case, role, readable=False):
    r = request(binding, case, role, 'probe', case['object'], uri=case['source']['uri'])
    read = event(binding, role, r, 'file.read'); write = event(binding, role, r, 'file.write')
    if readable:
        require(read['code'] == 0 and value(read) == {'uri': case['source']['uri'], 'content': case['source']['content']},
            'live selected target lost its actual grant when only grantor exited')
    else:
        require(read['code'] == 13900012 and value(read).get('codeType') == 'number' and value(read).get('message'),
            'fresh ordinary receiver must actually receive FileIO permission denied, not ENOENT/generic failure')
    require(write['code'] == 13900012 and value(write).get('codeType') == 'number' and value(write).get('message'),
        'READ-only route must deny a fresh WRITE open')
    event(binding, role, r, 'done')
    case['probes'].append({'role': role, 'operation': r['operation'], 'readable': readable})
    return r


def choose(binding):
    deadline = time.monotonic() + 45
    while True:
        try:
            tree = binding.layout('com.ohos.settings')
            select_node(tree, 'com.ohos.settings', identifier='system-share-title')
            # There are exactly two real ordinary MIME targets. No synthetic
            # target or private provider shortcut can satisfy the picker.
            for role in ('receiver', 'foreign'):
                select_node(tree, 'com.ohos.settings', identifier='system-share-target-' + BUNDLES[role] + '/entry/EntryAbility', clickable=True)
            binding.click('com.ohos.settings', 'system-share-target-' + BUNDLES['receiver'] + '/entry/EntryAbility')
            return
        except (NodeNotReady, LayoutNotReady):
            require(time.monotonic() < deadline, 'actual Share picker targets not available')
            time.sleep(.2)


def share(binding, case):
    r = request(binding, case, 'owner', 'share', case['object'])
    binding.ready_invoke('owner', r)
    event(binding, 'owner', r, 'share.opened')
    choose(binding)
    delivered = dict(r, action='consume', operation=r['delivery'], uri=case['source']['uri'])
    case['delivery'] = delivered
    incoming = value(event(binding, 'receiver', delivered, 'receiver.incoming'))
    require(incoming['uri'] == case['source']['uri'] and incoming['flags'] == 1, 'actual Share delivery must be READ-only')
    read = event(binding, 'receiver', delivered, 'file.read')
    write = event(binding, 'receiver', delivered, 'file.write')
    require(read['code'] == 0 and value(read) == {'uri': case['source']['uri'], 'content': case['source']['content']} and
        write['code'] == 13900012 and value(write)['message'], 'independent selected receiver must read exact bytes and deny WRITE')
    event(binding, 'receiver', delivered, 'done')
    result = value(event(binding, 'owner', r, 'share.result'))
    require(result['resultCode'] == 0 and result['want']['parameters'] == {'outcome': 'launched',
        'selectedBundleName': BUNDLES['receiver'], 'selectedModuleName': 'entry', 'selectedAbilityName': 'EntryAbility'},
        'real chooser callback/selected component differs')
    native = binding.begin_native('receiver')
    case['native_window'] = native
    if case['case'] == 'share-owner-death':
        case['owner_death'] = binding.stop('owner')
        # Permission is target-scoped. Grantor death alone is not a revoke.
        probe(binding, case, 'receiver', readable=True)
        case['receiver_death'] = binding.stop('receiver')
    elif case['case'] == 'share-receiver-death':
        case['receiver_death'] = binding.stop('receiver')
    else:
        binding.click(BUNDLES['receiver'], 'uri579-close')
        event(binding, 'receiver', delivered, 'ability.destroyed')
        after_close = binding.scan('receiver', 'after_receiver_ui_close')
        case['after_ui_close'] = after_close
        # The real AppMgr can cache a process after its last ability closes.
        # UI closure is observed separately; policy release is required only
        # after the target actually exits, not inferred from window absence.
        if after_close['processes']:
            case['receiver_death'] = binding.stop('receiver')
    binding.finish_native(native)
    # Same installed UID, no URI field/flags, new FD; original file is present.
    probe(binding, case, 'receiver')
    probe(binding, case, 'foreign')
    read_owner(binding, case)


def mms(binding, case):
    require(not binding.mms_cache(), 'previous MMS staging must already be absent')
    baseline = binding.restart_mms()
    case['mms_baseline'] = baseline
    case['negative_service'] = binding.service()
    case['before_log'] = len(binding.commands)
    binding.hilog()
    role = 'foreign' if case['case'] == 'mms-forged-owner' else 'owner'
    r = request(binding, case, role, 'mms', case['object'], uri=case['source']['uri'] if role == 'foreign' else '')
    binding.ready_invoke(role, r)
    event(binding, role, r, 'done')
    # A true API error is retained and fails this expected handler-delivery
    # path. No arbitrary unknown error is relabeled permission rejection.
    event(binding, role, r, 'mms.opened')
    if case['case'] in ('mms-no-grant', 'mms-forged-owner'):
        case['absent'] = binding.wait_mms_empty(ui=True)
        binding.hilog(); case['after_log'] = len(binding.commands)-1
        case['mms_after_attempt'] = binding.scan('mms', 'negative_mms_alive')
        require(case['mms_after_attempt']['processes'], 'actual MMS receiver must remain observable')
        read_owner(binding, case)
        probe(binding, case, 'foreign')
        # Rejection semantics are checked from the actual native/handler log
        # window by the raw verifier. Cache absence alone is insufficient.
        return
    imported = binding.wait_import(case['source']['content'], Path(case['source']['path']).name)
    case['imported'] = imported
    native = binding.begin_native('mms'); case['native_window'] = native
    if case['case'] == 'mms-owner-death':
        case['owner_death'] = binding.stop('owner')
        copied = binding.shell('od -An -v -tx1 ' + CACHE + '/' + imported['name'] + '/source.vcf', 'mms_after_owner_death')
        case['copy_after_owner_death'] = len(binding.commands)-1
        require(bytes.fromhex(copied) == case['source']['content'].encode() and
            binding.scan('mms', 'mms_survives_owner')['processes'], 'MMS-owned draft lost original bytes when grantor exited')
    if case['case'] != 'mms-receiver-death':
        binding.click(MMS, 'mms-senddata-cancel')
        case['cancel_absent'] = binding.wait_mms_empty(ui=True)
    case['mms_death'] = binding.stop('mms')
    binding.finish_native(native)
    # Force-stop may omit onDestroy; startup's actual recovery is authoritative.
    # Only our freshly observed import UUID can be present before recovery.
    require(set(binding.mms_cache()) <= {imported['name']}, 'unknown MMS staging preserved')
    case['mms_recreated'] = binding.restart_mms()
    case['recreate_absent'] = binding.wait_mms_empty(ui=True)
    require(set(case['mms_death']['processes']).isdisjoint(case['mms_recreated']['processes']) or
        all(case['mms_death']['processes'].get(pid, {}).get('start') != item.get('start')
            for pid, item in case['mms_recreated']['processes'].items()), 'actual MMS process birth did not change')
    read_owner(binding, case)
    probe(binding, case, 'foreign')


def run(io, *, mms_facts):
    binding = bind(io)
    document = {'schema': 'actual-mms-share579-boundaries/v1', 'run': io.run_id, 'boot_id': io.boot_id,
        'archive_sha256': io.archive_sha256, 'mms_facts': mms_facts, 'cases': [], 'failures': [],
        'cleanup_complete': False, 'runtime_pass': False, 'whole_id_closure': False,
        'formally_closed': [], 'first_artifact_behavior_gate_passed': False}
    path = binding.output / 'evidence.json'

    def save():
        document.update(roles=binding.roles, mms=binding.mms, commands=binding.commands,
            journal_reads=binding.reads, writers=list(binding.writers.values()), requests=binding.requests,
            actions=binding.actions, native_windows=binding.native_windows, process_scans=binding.scans,
            mms_cleanup=binding.mms_cleanup,
            original_io=[io.ref_receipt(row) for row in io.receipts])
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')

    save()
    try:
        binding.prepare()
        for role in BUNDLES:
            binding.install(role)
        binding.prepare_mms(mms_facts)
        for name in CASES:
            case = {'case': name, 'object': secrets.token_hex(16), 'operations': [], 'probes': [],
                'command_start': len(binding.commands), 'action_start': len(binding.actions), 'status': 'running'}
            document['cases'].append(case)
            # A no-grant probe is itself a real standard ability instance.
            # Finish prior instances before testing last-target exit again.
            for role in ('receiver', 'foreign'):
                if binding.scan(role, 'before_case_' + role)['processes']:
                    binding.stop(role)
            binding.objects[case['object']] = {'caseId': name}  # before create
            r = request(binding, case, 'owner', 'create', case['object'])
            case['source'] = value(event(binding, 'owner', r, 'owner.file'))
            probe(binding, case, 'foreign')
            if name.startswith('share-'):
                share(binding, case)
            else:
                mms(binding, case)
            # All release checks and owner re-reads precede deletion/uninstall.
            read_owner(binding, case)
            r = request(binding, case, 'owner', 'cleanup', case['object'])
            event(binding, 'owner', r, 'owner.deleted')
            del binding.objects[case['object']]
            case.update(command_end=len(binding.commands), action_end=len(binding.actions), status='raw_observed_pending_replay')
            save()
    except Exception as error:
        document['failures'].append(type(error).__name__ + ': ' + str(error))
        raise
    finally:
        try:
            binding.cleanup(); document['cleanup_complete'] = True
        except Exception as error:
            document['failures'].append('cleanup: ' + type(error).__name__ + ': ' + str(error))
            raise
        finally:
            save()
    try:
        replay = verify_observations(document, io)
    except Exception as error:
        document['failures'].append('raw replay: ' + type(error).__name__ + ': ' + str(error))
        save()
        raise
    result = binding.output / 'verification.json'; result.write_text(json.dumps(replay, indent=2) + '\n')
    return {'evidence': reference(path), 'verification': reference(result), 'whole_id_closure': False,
        'formally_closed': [], 'first_artifact_behavior_gate_passed': False}
