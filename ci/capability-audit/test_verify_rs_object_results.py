"""Synthetic contract checks, not real Binder/guest acceptance evidence."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from verify_rs_object_results import CASES, SCOPE, verify

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from verify_first_artifact_gate import checksum, verified_payload

RUN = 'a' * 32


def fixture(arch='arm64'):
    return [{'type': 'identity', 'run_id': RUN, 'uid': 0,
             'pointer_bits': 32 if arch == 'armv7a' else 64, 'scope': SCOPE},
            *[{'type': 'case', 'run_id': RUN, 'name': name, 'passed': True} for name in CASES],
            {'type': 'summary', 'run_id': RUN, 'cases': len(CASES), 'passed': True,
             'first_artifact_behavior_gate_passed': False}]


def transcript(rows):
    return '\n'.join(json.dumps(row) for row in rows) + '\n'


class RSObjectResultsTests(unittest.TestCase):
    def test_all_architectures_require_all_ordered_boundaries_but_never_attest_full_gate(self):
        self.assertEqual(len(CASES), 18)
        for arch in ('armv7a', 'arm64', 'x86_64'):
            result = verify(transcript(fixture(arch)), arch, RUN, 0)
            self.assertEqual(result['cases'], 18)
            self.assertFalse(result['cross_process_Binder_or_UI_validated'])
            self.assertFalse(result['first_artifact_behavior_gate_passed'])

    def test_stale_incomplete_failed_wrong_abi_or_exaggerated_evidence_rejected(self):
        original = fixture()
        variants = [original[:-1], original + [original[-1]],
                    [original[0], *reversed(original[1:-1]), original[-1]]]
        for index, key, value in ((0, 'run_id', 'b' * 32), (0, 'uid', 10000),
                                  (0, 'uid', False), (0, 'pointer_bits', 32),
                                  (0, 'scope', 'real_cross_process_Binder'),
                                  (1, 'passed', False), (1, 'passed', 1),
                                  (-1, 'cases', 17), (-1, 'passed', False),
                                  (-1, 'first_artifact_behavior_gate_passed', True)):
            changed = copy.deepcopy(original)
            changed[index][key] = value
            variants.append(changed)
        changed = copy.deepcopy(original)
        changed[1]['unexpected'] = True
        variants.append(changed)
        for rows in variants:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                verify(transcript(rows), 'arm64', RUN, 0)
        for arch, nonce, code in (('other', RUN, 0), ('arm64', '', 0),
                                 ('arm64', RUN, False), ('arm64', RUN, 1), ('arm64', RUN, None)):
            with self.subTest(arch=arch, nonce=nonce, code=code), self.assertRaises(ValueError):
                verify(transcript(original), arch, nonce, code)

    def test_gate_rechecks_actual_transcript_and_owned_package_boot_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, path = root / 'stdout.jsonl', root / 'result.json'
            raw.write_text(transcript(fixture()))
            identity = {'sha256': 'b' * 64}
            environment = {'boot_id': '12345678-1234-1234-1234-123456789abc',
                           'target': 'synthetic', 'guest_arch': 'arm64', 'device_type': 'phone'}
            payload = {'status': 'pass', 'kind': 'rs-objects', 'run_id': RUN,
                       'scope': 'isolated_root_probe_only_not_normal_app_or_full_capability_gate',
                       'archive_binding': 'actual_live_owned_boot_and_initial_full_archive_inventory',
                       'arch': 'arm64', 'device': 'phone', 'target': environment['target'],
                       'boot_id': environment['boot_id'], 'archive_sha256': identity['sha256'],
                       'kernel_boot_id_unchanged': True, 'probe_exit_code': 0,
                       'first_artifact_behavior_gate_passed': False, 'log_sha256': checksum(raw),
                       'result': verify(raw.read_text(), 'arm64', RUN, 0)}
            path.write_text(json.dumps(payload))
            verified_payload('rs-objects', path, identity, environment)
            for key, value in (('archive_sha256', 'c' * 64), ('boot_id', 'old'),
                               ('archive_binding', 'caller_selected_archive_not_automatically_boot_attested'),
                               ('arch', 'x86_64'), ('device', '2in1'), ('target', 'other'),
                               ('probe_exit_code', False), ('kernel_boot_id_unchanged', False),
                               ('first_artifact_behavior_gate_passed', True), ('result', {})):
                path.write_text(json.dumps({**payload, key: value}))
                with self.subTest(key=key), self.assertRaises(ValueError):
                    verified_payload('rs-objects', path, identity, environment)
            path.write_text(json.dumps(payload))
            raw.write_text(raw.read_text() + '\n')
            with self.assertRaises(ValueError):
                verified_payload('rs-objects', path, identity, environment)


if __name__ == '__main__':
    unittest.main()
