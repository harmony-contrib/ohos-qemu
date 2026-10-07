"""Strict real Binder identity evidence, not RS authorization or new-package proof."""
import json
import re

INITIAL = (('open_private_context', 0), ('acquire_unused_private_manager', 0),
           ('initial_sender_info_ioctl', 0), ('initial_no_sender_pid', 0),
           ('sender_ioctl_null_rejected', -14), ('enter_owned_looper', 0))
FROZEN_UPDATES = 64
FROZEN_STATE = (('frozen_updates_and_sync_rejection_client_exit', 0), ('frozen_info_ioctl', 0),
                ('frozen_async_received', 1), ('frozen_sync_received', 3), ('unfreeze_owned_manager', 0))


def expected_cases(prefix, pid, one_way):
    rows = [(prefix + '_delivery', 0), (prefix + '_wire_pid', 0 if one_way else pid),
            (prefix + '_wire_uid', 0), (prefix + '_sender_ioctl', 0),
            (prefix + '_kernel_pid', pid), (prefix + '_forged_pid_ignored', 1),
            (prefix + '_payload_and_protocol', 1)]
    if not one_way:
        rows.append(('sync_reply', 0))
    return rows + [(prefix + '_free_buffer', 0), (prefix + '_client_exit', 0)]


def namespace_setup(prefix, pid, exited):
    rows = [(prefix + '_pipe_setup', 0), (prefix + '_clone_private_pid_namespace', 1),
            (prefix + '_ready_delivery', 0), (prefix + '_child_open_and_send', 0),
            (prefix + '_namespace_pid', 1), (prefix + '_proc_pid', pid)]
    if exited:
        rows.append((prefix + '_exit_before_delivery', 0))
    return rows


def verify(text, arch, run_id, code):
    if type(code) is not int or code != 0 or re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('Binder identity requires an actual successful exit and fresh challenge')
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if len(rows) != 97 or any(not isinstance(row, dict) or row.get('run_id') != run_id for row in rows):
        raise ValueError('incomplete or stale Binder sender results')
    identity = rows[0]
    bits = {'armv7a': 32, 'arm64': 64, 'x86_64': 64}.get(arch)
    if (set(identity) != {'type', 'run_id', 'uid', 'pid', 'pointer_bits', 'context', 'scope'} or
            identity.get('type') != 'identity' or type(identity.get('uid')) is not int or identity['uid'] != 0 or
            type(identity.get('pid')) is not int or identity['pid'] <= 0 or
            type(identity.get('pointer_bits')) is not int or identity['pointer_bits'] != bits or bits is None or
            identity.get('context') != 'vndbinder' or identity.get('scope') != 'kernel_sender_only_not_RS_permissions'):
        raise ValueError('Binder root/ABI/context identity mismatch')
    offset = 1

    def check_cases(expected):
        nonlocal offset
        for name, value in expected:
            row = rows[offset]
            offset += 1
            if (set(row) != {'type', 'run_id', 'name', 'actual', 'expected', 'passed'} or
                    row.get('type') != 'case' or row.get('name') != name or row.get('passed') is not True or
                    type(row.get('actual')) is not int or row['actual'] != value or
                    type(row.get('expected')) is not int or row['expected'] != value):
                raise ValueError('failed/reordered Binder identity boundary: ' + name)

    check_cases(INITIAL)
    senders = []
    for test, prefix, one_way, exited in ((1, 'sync', False, False), (2, 'async', True, False),
                                        (3, 'exited_async', True, True)):
        if test == 3:
            check_cases((('malformed_async_rejected', 0),))
        sender = rows[offset]
        offset += 1
        if (set(sender) != {'type', 'run_id', 'test', 'pid', 'one_way', 'exited'} or sender.get('type') != 'sender' or
                type(sender.get('test')) is not int or sender['test'] != test or
                type(sender.get('pid')) is not int or sender['pid'] <= 0 or sender['pid'] == identity['pid'] or
                sender['pid'] == 2147483630 or sender.get('one_way') is not one_way or sender.get('exited') is not exited):
            raise ValueError('invalid actual forked sender identity')
        senders.append(sender['pid'])
        check_cases(expected_cases(prefix, sender['pid'], one_way))
    check_cases((('freeze_owned_manager', 0),))
    sender = rows[offset]
    offset += 1
    if (set(sender) != {'type', 'run_id', 'test', 'pid', 'one_way', 'exited', 'updates'} or
            sender.get('type') != 'sender' or type(sender.get('test')) is not int or sender['test'] != 5 or
            type(sender.get('pid')) is not int or sender['pid'] <= 0 or sender['pid'] in (identity['pid'], 2147483630) or
            sender.get('one_way') is not True or sender.get('exited') is not True or
            type(sender.get('updates')) is not int or sender['updates'] != FROZEN_UPDATES):
        raise ValueError('invalid actual frozen-update sender identity')
    senders.append(sender['pid'])
    check_cases(FROZEN_STATE)
    for prefix in ('frozen_first', 'frozen_last'):
        check_cases(expected_cases(prefix, sender['pid'], True)[:-1])
    check_cases((('frozen_superseded_transactions_not_delivered', -110),))
    for test, prefix, exited in ((7, 'namespace_async', False), (8, 'namespace_exited_async', True)):
        sender_index = offset + len(namespace_setup(prefix, 0, exited))
        sender = rows[sender_index]
        if (set(sender) != {'type', 'run_id', 'test', 'pid', 'namespace_pid', 'proc_pid', 'one_way', 'exited'} or
                sender.get('type') != 'namespace_sender' or type(sender.get('test')) is not int or
                sender['test'] != test or type(sender.get('pid')) is not int or sender['pid'] <= 1 or
                sender['pid'] in (identity['pid'], 2147483630) or
                type(sender.get('namespace_pid')) is not int or sender['namespace_pid'] != 1 or
                type(sender.get('proc_pid')) is not int or sender['proc_pid'] != sender['pid'] or
                sender.get('one_way') is not True or sender.get('exited') is not exited):
            raise ValueError('invalid actual private PID-namespace sender identity')
        check_cases(namespace_setup(prefix, sender['pid'], exited))
        offset += 1
        check_cases(expected_cases(prefix, sender['pid'], True))
        senders.append(sender['pid'])
    if len(set(senders)) != 6:
        raise ValueError('six actual distinct sending processes required')
    summary = rows[offset]
    if (offset != len(rows) - 1 or set(summary) != {'type', 'run_id', 'cases', 'passed',
            'private_manager_closed', 'first_artifact_behavior_gate_passed'} or summary.get('type') != 'summary' or
            type(summary.get('cases')) is not int or summary['cases'] != 89 or summary.get('passed') is not True or
            summary.get('private_manager_closed') is not True or summary.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('failed/incomplete Binder cleanup or incorrectly claimed package acceptance')
    return {'cases': 89, 'scope': 'real sync/async/exit trusted kernel TGID, forged wire PID/UID, malformed/null rejection, owned frozen updates, sync rejection and live/exited private PID namespaces',
            'live_and_exited_private_pid_namespaces_validated': True,
            'kernel_pid_reference_release_observed': False,
            'rs_token_or_node_ownership_validated': False, 'ordinary_ui_or_vulkan_pixels_validated': False,
            'results': rows}
