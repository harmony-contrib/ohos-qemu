"""Host-only protocol/math counterexamples, never HDI/audio/guest proof."""
import json
from pathlib import Path
import re
import tempfile
import unittest
import wave

import batch_media_audio_haptic as probe

RUN = 'a'*32
BOOT = '12345678-1234-4567-8abc-123456789abc'
SDK = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')
EXPORT = Path('/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-audio-haptic-source-inputs-01/evidence.json')


def samples():
    return [{'schema_version': 1, 'kind': 'sample', 'run_id': RUN, 'boot_id': BOOT, 'sequence': i+1,
             'before_ns': 1000000+i*20000000, 'after_ns': 1100000+i*20000000, 'result': 0, 'running': state}
            for i, state in enumerate([False, False, True, True, False, False])]


def stream(values=None):
    values = values or samples()
    rows = [{'schema_version': 1, 'kind': 'begin', 'run_id': RUN, 'boot_id': BOOT, 'uid': 0, 'device_id': 0,
        'vibrator_id': 0, 'before_ns': 1, 'after_ns': 2, 'result': 0, 'time_delay': True,
        'hd_haptic': False, 'preset_mapping': False, 'duration_ms': 100, 'period_ms': 20}, *values,
        {'schema_version': 1, 'kind': 'complete', 'run_id': RUN, 'boot_id': BOOT, 'samples': len(values)}]
    return rows


def encode(rows):
    return ''.join(json.dumps(row)+'\n' for row in rows)


class AudioHapticTests(unittest.TestCase):
    def hap_rows(self):
        return [{'schema_version': 1, 'run_id': RUN, 'boot_id': BOOT, 'operation_id': 'b'*32, 'sequence': i+1,
                 'uid': 20010001, 'event': event, 'api': 'snapshot', 'before_ns': 100+i, 'after_ns': 110+i,
                 'value_json': json.dumps(value), 'error_code': 0, 'error_message': ''}
                for i, (event, value) in enumerate([('begin', {}), ('callbacks', {'events': [], 'overflow': 0}), ('complete', {})])]

    def test_hap_parser_does_not_infer_hdi_or_audio_success(self):
        parsed = probe.parse_hap(encode(self.hap_rows()), RUN, BOOT, 20010001)
        self.assertEqual([row['event'] for row in parsed], ['begin', 'callbacks', 'complete'])
        self.assertTrue(all('pass' not in row for row in parsed))

    def test_callback_overflow_and_late_callback_fail(self):
        for value in [{'events': [], 'overflow': 1}, {'overflow': 0, 'events': [{'kind': 'audioInterrupt',
            'generation': 1, 'monotonic_ns': 100, 'event_type': 1, 'force_type': 0, 'hint_type': 3, 'released': True}]}]:
            rows = self.hap_rows(); rows[1]['value_json'] = json.dumps(value)
            with self.assertRaises(ValueError): probe.parse_hap(encode(rows), RUN, BOOT, 20010001)

    def test_real_getter_bounds_are_conservative(self):
        rows = probe.parse_hdi(encode(stream()), RUN, BOOT, 0)
        episode = probe.time_episodes(rows)[0]
        self.assertEqual(episode['start_ns'], [21000000, 41100000])
        self.assertEqual(episode['end_ns'], [61000000, 81100000])
        self.assertEqual(episode['duration_ns'], [19900000, 60100000])

    def test_empty_muted_trace_is_not_a_start(self):
        values = samples()
        for row in values: row['running'] = False
        self.assertEqual(probe.time_episodes(probe.parse_hdi(encode(stream(values)), RUN, BOOT, 0)), [])

    def test_failed_rpc_is_not_false(self):
        rows = stream(); rows[2].update(result=-1, running=None)
        with self.assertRaisesRegex(ValueError, 'actual HDI getter'):
            probe.parse_hdi(encode(rows), RUN, BOOT, 0)

    def test_boolean_numeric_result_rejected(self):
        rows = stream(); rows[2]['result'] = False
        with self.assertRaises(ValueError): probe.parse_hdi(encode(rows), RUN, BOOT, 0)

    def test_truncation_or_nonzero_exit_rejected(self):
        for raw, code in [(encode(stream()).rstrip(), 0), (encode(stream()), 1)]:
            with self.assertRaises(ValueError): probe.parse_hdi(raw, RUN, BOOT, code)

    def test_foreign_boot_and_reordered_samples_rejected(self):
        for key, value in [('boot_id', 'b'*36), ('sequence', 99)]:
            rows = stream(); rows[2][key] = value
            with self.assertRaises(ValueError): probe.parse_hdi(encode(rows), RUN, BOOT, 0)

    def test_missing_complete_rejected(self):
        with self.assertRaises(ValueError): probe.parse_hdi(encode(stream()[:-1]), RUN, BOOT, 0)

    def test_active_final_state_cannot_prove_cleanup(self):
        values = samples(); values[-1]['running'] = True
        with self.assertRaises(ValueError): probe.time_episodes(values)

    def test_no_clock_fallback_or_mutating_driver_calls(self):
        source = probe.OBSERVER.read_text()
        self.assertEqual(set(re.findall(r'driver->(\w+)\(', source)), {'GetHapticCapacity', 'IsVibratorRunning'})
        self.assertIn('CLOCK_MONOTONIC', source)
        self.assertNotIn('system_clock', source)
        self.assertNotIn('driver->Stop', source)
        self.assertNotIn('driver->Start', source)

    def test_public_sdk_does_not_gain_invented_state_getter(self):
        source = probe.PAGE.read_text()
        self.assertNotIn('.getState(', source)
        self.assertNotIn('.getCurrentTime(', source)
        self.assertNotIn('throw error', source)
        self.assertIn('this.player.isMuted(', source)
        self.assertIn('this.player.start()', source)
        self.assertIn('this.callbackOverflow++', source)

    def test_alignment_reports_uncertainty_and_no_gate(self):
        value = probe.alignment_bounds([100, 130], [110, 140])
        self.assertEqual(value['haptic_minus_audio_ns'], [-40, 20])
        self.assertFalse(value['full_runtime_gate'])
        with self.assertRaises(ValueError): probe.alignment_bounds([True, 130], [110, 140])

    def test_real_sdk_export_and_complete_source_projects(self):
        if not SDK.is_dir() or not EXPORT.is_file():
            self.skipTest('actual SDK105/fixed-source export absent; never substitute a fake SDK')
        with tempfile.TemporaryDirectory(prefix='audio-haptic-source-test-') as temp:
            temp = Path(temp)
            challenge = probe.prepare(temp/'challenge', SDK, EXPORT)
            data = json.loads(challenge.read_text())
            self.assertFalse(data['runtime_validated'])
            for case in data['cases'].values():
                with wave.open(case['audio']['path']) as wav:
                    self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (2, 2, 48000))
                    self.assertEqual(wav.getnframes(), case['frames'])
                    self.assertTrue(any(wav.readframes(4096)))
                event = json.loads(Path(case['haptic']['path']).read_text())['Channels'][0]['Pattern'][0]['Event']
                self.assertEqual((event['Type'], event['StartTime']), ('continuous', 0))
                self.assertEqual(event['Duration'], case['haptic_duration_ms'])
            for denied in (False, True):
                manifest = probe.project(temp/str(denied), challenge, SDK, denied=denied)
                result = json.loads(manifest.read_text())
                self.assertEqual(result['requested_permissions'], [] if denied else ['ohos.permission.VIBRATE'])
                self.assertEqual(result['required_apl'], 'normal')
                self.assertFalse(result['required_system_app'])
                self.assertFalse(result['runtime_validated'])


if __name__ == '__main__':
    unittest.main()
