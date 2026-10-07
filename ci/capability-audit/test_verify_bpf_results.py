"""Parser fixtures, not real kernel/BPF acceptance evidence."""
import copy
import json
from pathlib import Path
import unittest
from verify_bpf_results import CASES, verify
from run_root_probe import probe_command, verify_result

RUN = '0abc' * 8


def observations(bits=64):
    rows = [{'type': 'identity', 'run_id': RUN, 'uid': 0, 'pointer_bits': bits}]
    rows += [{'type': 'case', 'run_id': RUN, 'name': name, 'actual': expected,
              'expected': expected, 'passed': True} for name, expected in CASES]
    rows.append({'type': 'summary', 'run_id': RUN, 'cases': len(CASES), 'passed': True})
    return rows


def log(rows):
    return '\n'.join(json.dumps(row) for row in rows)


class BpfResultTests(unittest.TestCase):
    def test_complete_all_architectures_without_network_service_claim(self):
        for arch, bits in (('arm64', 64), ('armv7a', 32), ('x86_64', 64)):
            result = verify(log(observations(bits)), arch, RUN, 0)
            self.assertEqual(result['cases'], 23)
            self.assertFalse(result['netmanager_service_validated'])
            self.assertFalse(result['netfirewall_policy_validated'])

    def test_partial_duplicate_reordered_or_stale_rows_fail(self):
        original = observations()
        for rows in (original[:-1], original + original[-1:],
                     original[:2] + [original[3], original[2]] + original[4:]):
            with self.assertRaises(ValueError): verify(log(rows), 'arm64', RUN, 0)
        for index in range(len(original)):
            broken = copy.deepcopy(original)
            broken[index]['run_id'] = '1234' * 8
            with self.assertRaises(ValueError): verify(log(broken), 'arm64', RUN, 0)

    def test_success_summary_cannot_hide_failed_data_or_boundary(self):
        for index in range(1, 24):
            for key, value in (('actual', 99), ('expected', 99), ('passed', 1), ('actual', False)):
                broken = observations()
                broken[index][key] = value
                with self.assertRaises(ValueError): verify(log(broken), 'arm64', RUN, 0)

    def test_wrong_root_abi_exit_or_unknown_evidence_fields_fail(self):
        for key, value in (('uid', 20010001), ('uid', False), ('pointer_bits', 32)):
            broken = observations()
            broken[0][key] = value
            with self.assertRaises(ValueError): verify(log(broken), 'arm64', RUN, 0)
        for code in (1, None, False, '0'):
            with self.assertRaises(ValueError): verify(log(observations()), 'arm64', RUN, code)
        for index in (0, 1, 24):
            broken = observations()
            broken[index]['ignored_error'] = 'must not ignore'
            with self.assertRaises(ValueError): verify(log(broken), 'arm64', RUN, 0)
        with self.assertRaises(ValueError): verify(log(observations()), 'arm64', '', 0)

    def test_real_runner_passes_challenge_and_independent_process_exit(self):
        command = probe_command('bpf', '/data/local/tmp/fixture', RUN)
        self.assertIn('/probe ' + RUN, command)
        self.assertIn('unset LD_LIBRARY_PATH LD_PRELOAD;', command)
        self.assertEqual(verify_result('bpf', log(observations()), 'arm64', RUN, 0)['cases'], 23)
        with self.assertRaises(ValueError): verify_result('bpf', log(observations()), 'arm64', RUN, 1)

    def test_build_uses_actual_sdk_bpf_header_and_only_loopback_no_policy_mutation(self):
        root = Path(__file__).resolve().parent
        source = (root / 'probes/bpf_syscall.c').read_text()
        self.assertIn('#include <linux/bpf.h>', source)
        self.assertIn('INADDR_LOOPBACK', source)
        self.assertIn('BPF_PROG_LOAD', source)
        self.assertIn('SO_ATTACH_BPF', source)
        self.assertIn('memcmp(payload, challenge, 32)', source)
        self.assertNotIn('BPF_OBJ_PIN', source)
        self.assertIn('bpf_syscall', (root / 'build_access_token_probe.sh').read_text())


if __name__ == '__main__':
    unittest.main()
