"""Verifier fixtures only; never evidence that the actual kernel works."""
import copy
import json
import unittest

from verify_binder_sender_results import FROZEN_STATE, FROZEN_UPDATES, INITIAL, expected_cases, namespace_setup, verify

RUN = '01' * 16


def fixture():
    rows = [{'type': 'identity', 'run_id': RUN, 'uid': 0, 'pid': 500, 'pointer_bits': 64,
             'context': 'vndbinder', 'scope': 'kernel_sender_only_not_RS_permissions'}]
    def cases(values):
        rows.extend({'type': 'case', 'run_id': RUN, 'name': name, 'actual': value,
                     'expected': value, 'passed': True} for name, value in values)
    cases(INITIAL)
    for test, prefix, one_way, exited in ((1, 'sync', False, False), (2, 'async', True, False),
                                        (3, 'exited_async', True, True)):
        if test == 3:
            cases((('malformed_async_rejected', 0),))
        pid = 500 + test
        rows.append({'type': 'sender', 'run_id': RUN, 'test': test, 'pid': pid,
                     'one_way': one_way, 'exited': exited})
        cases(expected_cases(prefix, pid, one_way))
    cases((('freeze_owned_manager', 0),))
    rows.append({'type': 'sender', 'run_id': RUN, 'test': 5, 'pid': 505, 'one_way': True,
                 'exited': True, 'updates': FROZEN_UPDATES})
    cases(FROZEN_STATE)
    for prefix in ('frozen_first', 'frozen_last'):
        cases(expected_cases(prefix, 505, True)[:-1])
    cases((('frozen_superseded_transactions_not_delivered', -110),))
    for test, prefix, exited in ((7, 'namespace_async', False), (8, 'namespace_exited_async', True)):
        pid = 500 + test
        cases(namespace_setup(prefix, pid, exited))
        rows.append({'type': 'namespace_sender', 'run_id': RUN, 'test': test, 'pid': pid,
                     'namespace_pid': 1, 'proc_pid': pid, 'one_way': True, 'exited': exited})
        cases(expected_cases(prefix, pid, True))
    rows.append({'type': 'summary', 'run_id': RUN, 'cases': 89, 'passed': True,
                 'private_manager_closed': True, 'first_artifact_behavior_gate_passed': False})
    return rows


def text(rows):
    return '\n'.join(json.dumps(row) for row in rows)


class BinderSenderVerifierTests(unittest.TestCase):
    def test_complete_fixture_retains_strict_scope(self):
        result = verify(text(fixture()), 'arm64', RUN, 0)
        self.assertEqual(result['cases'], 89)
        self.assertTrue(result['live_and_exited_private_pid_namespaces_validated'])
        self.assertFalse(result['kernel_pid_reference_release_observed'])
        self.assertFalse(result['rs_token_or_node_ownership_validated'])
        self.assertFalse(result['ordinary_ui_or_vulkan_pixels_validated'])

    def test_zero_stale_forged_wrong_wire_or_namespace_pid_is_rejected(self):
        for name, bad in (('async_kernel_pid', 0), ('exited_async_kernel_pid', 0),
                          ('async_wire_pid', 502), ('sync_kernel_pid', 1),
                          ('sync_forged_pid_ignored', 0), ('async_wire_uid', 4294967295),
                          ('frozen_last_kernel_pid', 0), ('frozen_first_wire_pid', 505),
                          ('frozen_sync_received', 0), ('frozen_sync_received', 1),
                          ('frozen_sync_received', 2), ('frozen_superseded_transactions_not_delivered', 0),
                          ('namespace_async_kernel_pid', 1), ('namespace_exited_async_kernel_pid', 1),
                          ('namespace_async_wire_pid', 507), ('namespace_exited_async_proc_pid', 1),
                          ('namespace_async_namespace_pid', 507), ('namespace_async_wire_uid', 4294967295),
                          ('namespace_exited_async_exit_before_delivery', 1)):
            rows = fixture()
            row = next(row for row in rows if row.get('name') == name)
            row.update(actual=bad, expected=bad, passed=True)
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify(text(rows), 'arm64', RUN, 0)

    def test_namespace_identity_omission_forgery_reuse_and_boolean_fail(self):
        for mutation in ('namespace_bool', 'proc_bool', 'pid_one', 'namespace_host', 'proc_namespace',
                         'duplicate_sender', 'wrong_exit', 'missing_case', 'old_58_case_probe'):
            rows = fixture()
            sender = next(row for row in rows if row.get('type') == 'namespace_sender' and row['test'] == 7)
            if mutation == 'namespace_bool': sender['namespace_pid'] = True
            elif mutation == 'proc_bool': sender['proc_pid'] = True
            elif mutation == 'pid_one': sender['pid'] = 1
            elif mutation == 'namespace_host': sender['namespace_pid'] = 507
            elif mutation == 'proc_namespace': sender['proc_pid'] = 1
            elif mutation == 'duplicate_sender': sender.update(pid=501, proc_pid=501)
            elif mutation == 'wrong_exit': sender['exited'] = True
            elif mutation == 'missing_case':
                rows.remove(next(row for row in rows if row.get('name') == 'namespace_async_ready_delivery'))
            else:
                rows = rows[:63] + [dict(rows[-1], cases=58)]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify(text(rows), 'arm64', RUN, 0)

    def test_frozen_replacement_challenge_order_and_claims_are_strict(self):
        for mutation in ('updates_bool', 'wrong_updates', 'live_sender', 'reorder', 'duplicate_sender',
                         'drop_boundary', 'pid_leak_claim'):
            rows = fixture()
            sender = next(row for row in rows if row.get('type') == 'sender' and row['test'] == 5)
            if mutation == 'updates_bool': sender['updates'] = True
            elif mutation == 'wrong_updates': sender['updates'] = 63
            elif mutation == 'live_sender': sender['exited'] = False
            elif mutation == 'duplicate_sender': sender['pid'] = 501
            elif mutation == 'reorder': rows[-3], rows[-4] = rows[-4], rows[-3]
            elif mutation == 'drop_boundary': rows.pop(-2)
            else: rows[-1]['kernel_pid_reference_release_observed'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify(text(rows), 'arm64', RUN, 0)

    def test_exit_abi_challenge_truncation_cleanup_and_bool_integer_fail(self):
        for arch, challenge, code in (('armv7a', RUN, 0), ('arm64', 'ff' * 16, 0),
                                     ('arm64', RUN, 1), ('arm64', RUN, False)):
            with self.assertRaises(ValueError): verify(text(fixture()), arch, challenge, code)
        for mutation in ('truncated', 'accepted_gate', 'not_closed', 'duplicate_sender', 'bool_pid'):
            rows = copy.deepcopy(fixture())
            if mutation == 'truncated': rows.pop(14)
            elif mutation == 'accepted_gate': rows[-1]['first_artifact_behavior_gate_passed'] = True
            elif mutation == 'not_closed': rows[-1]['private_manager_closed'] = False
            elif mutation == 'duplicate_sender':
                next(row for row in rows if row.get('type') == 'sender' and row['test'] == 2)['pid'] = 501
            else: next(row for row in rows if row.get('type') == 'sender')['pid'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify(text(rows), 'arm64', RUN, 0)


if __name__ == '__main__':
    unittest.main()
