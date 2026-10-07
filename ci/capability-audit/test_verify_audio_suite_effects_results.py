"""Synthetic verifier regressions, not guest DSP acceptance."""
import copy
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest
from verify_audio_suite_effects_results import FREQUENCIES, expected_energy, sequence, verify

RUN = 'af528e3248f3452d82131d0db3852414'
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal', 'isSystemApp': False, 'uid': 20010036}})


def fixture():
    rows = [{'type': 'identity', 'run_id': RUN, 'uid': 20010036, 'euid': 20010036},
            {'type': 'step', 'run_id': RUN, 'cycle': 0, 'test': -1, 'name': 'null_create', 'actual': 1,
             'expected': 1, 'passed': True}]
    phase = (int(RUN[:8], 16) % 10000) / 10000
    for cycle in (1, 2):
        for test in range(18):
            for name, expected in sequence(test):
                row = {'run_id': RUN, 'cycle': cycle, 'test': test, 'passed': True}
                if name != '@signal': row.update(type='step', name=name, actual=expected, expected=expected)
                else:
                    frequency = FREQUENCIES[test] if test < 10 else 1000 if test < 14 else 12000
                    db = 6 if test < 10 else 20 * math.log10((.5, 2.25, 1, 1.75)[test - 10]) if test < 14 else -20
                    energy = expected_energy(phase, frequency)
                    row.update(type='signal', frequency=frequency, phase=phase, input_bytes=384000,
                               consumed_bytes=384000, output_bytes=384000, callbacks=100, bad_callbacks=0,
                               finished=True, left_input_energy=energy, right_input_energy=energy,
                               left_output_energy=energy * 10 ** (db / 10), right_output_energy=energy * 10 ** (db / 10),
                               left_dB=db, right_dB=db)
                rows.append(row)
    rows.append({'type': 'summary', 'run_id': RUN, 'cycles': 2, 'pipelines': 36, 'passed': True,
                 'scope': 'public_AudioSuite_three_DSP_effects_not_AI_or_download'})
    return rows


def text(rows): return '\n'.join(json.dumps(row) for row in rows)


class DspResultTests(unittest.TestCase):
    def test_exact_36_pipelines_complete_order_and_literal_NDK_errors(self):
        rows = fixture()
        self.assertEqual(len(rows), 1323)
        self.assertEqual(len(verify(text(rows), RUN, IDENTITY)), 1323)
        self.assertEqual([row['actual'] for row in rows if row.get('name') == 'render_before_start'], [2] * 36)
        self.assertEqual([row['actual'] for row in rows if row.get('name') == 'eq_invalid_gain'], [1] * 20)

    def test_stale_partial_reordered_missing_destroy_and_privileged_rejected(self):
        original = fixture()
        for changed in (original[:-1], original + [original[-1]], [original[1], original[0]] + original[2:]):
            with self.assertRaises(ValueError): verify(text(changed), RUN, IDENTITY)
        with self.assertRaises(ValueError): verify(text(original), '0' * 32, IDENTITY)
        with self.assertRaises(ValueError): verify(text(original), RUN, IDENTITY.replace('normal', 'system_core'))
        changed = copy.deepcopy(original)
        changed[38]['name'] = 'missing_destroy'
        with self.assertRaises(ValueError): verify(text(changed), RUN, IDENTITY)

    def test_real_metrics_cannot_be_replaced_by_nominal_success(self):
        original = fixture()
        index = next(i for i, row in enumerate(original) if row['type'] == 'signal')
        mutations = {'phase': 0, 'frequency': 42, 'consumed_bytes': 383996, 'output_bytes': 400000,
                     'callbacks': 0, 'finished': False, 'bad_callbacks': 1, 'left_dB': 0,
                     'left_output_energy': 0, 'left_input_energy': 1, 'right_dB': float('nan')}
        for key, value in mutations.items():
            changed = copy.deepcopy(original)
            changed[index][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): verify(text(changed), RUN, IDENTITY)
        changed = copy.deepcopy(original)
        energy = changed[index]['left_input_energy']
        changed[index]['left_output_energy'] = energy
        changed[index]['left_dB'] = 0
        with self.assertRaises(ValueError): verify(text(changed), RUN, IDENTITY)

    def test_boolean_numbers_and_failed_steps_cannot_pass(self):
        for index, key, value in ((1, 'actual', True), (0, 'uid', True), (2, 'actual', False),
                                   (-1, 'pipelines', True), (3, 'passed', False)):
            rows = fixture()
            rows[index][key] = value
            with self.subTest(index=index, key=key), self.assertRaises(ValueError): verify(text(rows), RUN, IDENTITY)

    def test_CLI_retains_failure_and_archive_binding_never_releases_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, results, identity, output = (root / name for name in ('image.tar.gz', 'results', 'identity', 'evidence.json'))
            archive.write_bytes(b'fixture not a QEMU image')
            identity.write_text(IDENTITY)
            results.write_text(text(fixture()))
            command = ['python3', str(Path(__file__).with_name('verify_audio_suite_effects_results.py')), '--archive', str(archive),
                       '--results', str(results), '--application-identity', str(identity), '--run-id', RUN, '--output', str(output)]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertFalse(json.loads(output.read_text())['first_artifact_behavior_gate_passed'])
            results.write_text('')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(json.loads(output.read_text())['status'], 'fail')


if __name__ == '__main__': unittest.main()
