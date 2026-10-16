#!/usr/bin/env python3
"""Host-only verifier/contract boundary tests. Test data is not guest evidence."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from batch_system_live_inputs import nonce, load_rows, read_json, trace, f32
from batch_system_verify_live_inputs import compare_location, compare_sensor, compare_still, verify_msdp_inventory, sessions, window, mapped_processes
from batch_system_gnss_controller import encode_sample

RUN = 'f' * 32


def row(seq, kind, values, generation=1):
    return dict(schema=1, run_id=RUN, seq=seq, kind=kind, generation=generation,
                boot_ns=str(10_000_000_000 + seq * 1000000), values=values, text='')


class ContractTests(unittest.TestCase):
    def file(self, value):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'input.json'; path.write_text(json.dumps(value)); return path

    def generated_project(self):
        # Metadata lookup seam only; no SDK/API implementation is supplied here.
        import batch_system_build_live_hap as build
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        project = Path(temp.name) / 'project'
        with patch('batch_system_build_live_hap.sdk_contract', return_value={'unit': 'metadata only'}), \
             patch('batch_system_live_inputs.sdk_contract', return_value={'unit': 'metadata only'}):
            build.generate(project, Path(temp.name), 'arm64', RUN)
        return project

    def test_actual_linux_sdk39_project_schema(self):
        project = self.generated_project()
        product = read_json(project / 'build-profile.json5')['app']['products']
        self.assertEqual(product, [{'name': 'default', 'compileSdkVersion': '26.0.0',
            'compatibleSdkVersion': '26.0.0', 'targetSdkVersion': '26.0.0', 'runtimeOS': 'OpenHarmony'}])
        self.assertEqual(read_json(project / 'hvigor/hvigor-config.json5'),
            {'modelVersion': '6.0.0', 'dependencies': {}, 'execution': {'daemon': False, 'parallel': False}})
        for name, task in [('hvigorfile.ts', 'appTasks'), ('entry/hvigorfile.ts', 'hapTasks')]:
            self.assertEqual((project / name).read_text(), "import { " + task +
                " } from '@ohos/hvigor-ohos-plugin';\nexport default { system: " + task + ", plugins: [] };\n")
        self.assertFalse((project / 'live-inputs-build.json').exists())

    def test_schema_tamper_cannot_be_hidden_by_refreshing_file_hashes(self):
        from batch_system_live_inputs import project_files, verify_project
        for mutation in ('runtime', 'compile_version', 'app_task', 'hap_task', 'parallel'):
            project = self.generated_project()
            if mutation in ('runtime', 'compile_version'):
                path = project / 'build-profile.json5'; value = read_json(path)
                if mutation == 'runtime': value['app']['products'][0]['runtimeOS'] = 'HarmonyOS'
                else: del value['app']['products'][0]['compileSdkVersion']
                path.write_text(json.dumps(value))
            elif mutation == 'parallel':
                path = project / 'hvigor/hvigor-config.json5'; value = read_json(path)
                value['execution']['parallel'] = True; path.write_text(json.dumps(value))
            else:
                (project / ('hvigorfile.ts' if mutation == 'app_task' else 'entry/hvigorfile.ts')).write_text('export default {};\n')
            contract = project / 'live-inputs-contract.json'; value = read_json(contract)
            value['source_files'] = project_files(project); contract.write_text(json.dumps(value))
            with patch('batch_system_live_inputs.sdk_contract', return_value={'unit': 'metadata only'}):
                with self.assertRaisesRegex(ValueError, 'OpenHarmony API26/Hvigor6'):
                    verify_project(project, Path('/unused'), RUN, 'arm64')

    def test_missing_hvigor_wiring_fails_closed(self):
        from batch_system_live_inputs import verify_project
        project = self.generated_project(); (project / 'entry/hvigorfile.ts').unlink()
        with patch('batch_system_live_inputs.sdk_contract', return_value={'unit': 'metadata only'}):
            with self.assertRaises(FileNotFoundError): verify_project(project, Path('/unused'), RUN, 'arm64')

    def test_nonce_rejects_stale_shape(self):
        for value in ['', 'x' * 32, 'F' * 32, '0' * 32, 1, None]:
            with self.assertRaises(ValueError): nonce(value)

    def test_duplicate_json_keys_rejected(self):
        path = self.file({}); path.write_text('{"run_id":1,"run_id":2}')
        with self.assertRaises(ValueError): read_json(path)

    def test_nan_trace_rejected(self):
        path = self.file([dict(at_ms=0, x=float('nan'), y=0, z=9)])
        with self.assertRaises(ValueError): trace(path, 'sensor')

    def test_no_builtin_fixed_trace(self):
        path = self.file([dict(at_ms=i * 200, x=0, y=0, z=9) for i in range(30)])
        with self.assertRaises(ValueError): trace(path, 'sensor')

    def test_empty_location_result_does_not_pass(self):
        with self.assertRaises(ValueError): compare_location([], [dict(utc_ms=1)], 1)

    def test_location_raw_challenge_match_and_mutations(self):
        source = [dict(utc_ms=1700000000000 + i * 1000, latitude=30 + i / 1000,
            longitude=120 - i / 1000, horizontal_accuracy=3.125) for i in range(3)]
        values = [row(i + 1, 'location', [1, s['latitude'], s['longitude'], 0, 3.125, 0,
            s['utc_ms'], 9_000_000_000 + i * 1000000, 0, 1, 1]) for i, s in enumerate(source)]
        self.assertEqual(compare_location(values, source, 1)['callbacks'], 3)
        for index, value in [(0, 0), (1, 0), (6, 1700000000000), (7, -1), (8, 1), (9, 0), (10, 2)]:
            wrong = deepcopy(values); wrong[1]['values'][index] = value
            with self.assertRaises(ValueError): compare_location(wrong, source, 1)
        with self.assertRaises(ValueError): compare_location(values[:2], source, 1)

    def test_sensor_float32_units_and_order(self):
        source = [dict(x=.1 + i / 10, y=1.2, z=9.21) for i in range(3)]
        values = [row(i + 1, 'sensor', [1, f32(s['x']), f32(s['y']), f32(s['z']),
            9_000_000_000 + i * 1000000]) for i, s in enumerate(source)]
        self.assertEqual(compare_sensor(values, source, 1)['matched_samples'], 3)
        for change in ['old_generation', 'axis', 'unit', 'timestamp']:
            wrong = deepcopy(values)
            if change == 'old_generation': wrong[1]['values'][0] = 0
            if change == 'axis': wrong[1]['values'][1:3] = wrong[1]['values'][2:0:-1]
            if change == 'unit': wrong[1]['values'][3] /= 9.8
            if change == 'timestamp': wrong[1]['values'][4] = wrong[0]['values'][4]
            with self.assertRaises(ValueError): compare_sensor(wrong, source, 1)

    def test_still_requires_real_transition_callbacks_and_input_timing(self):
        # Constructed host validator data only, never executable guest evidence.
        samples = []
        for phase, z in enumerate([9.2, 15.0, 9.4]):
            samples.extend(dict(at_ms=(phase * 10 + i) * 200, x=.1 + i / 100, y=.2, z=z) for i in range(10))
        events = []
        for i, sample in enumerate(samples):
            stamp = 20_000_000_000 + i * 200_000_000
            value = row(i + 1, 'sensor', [1, f32(sample['x']), f32(sample['y']), f32(sample['z']), stamp])
            value['boot_ns'] = str(stamp + 1_000_000); events.append(value)
        for i, (index, state) in enumerate([(4, 1), (10, 2), (24, 1)]):
            value = row(31 + i, 'still', [1, state])
            value['boot_ns'] = str(20_000_000_000 + index * 200_000_000 + 10_000_000)
            events.append(value)
        self.assertEqual(compare_still(events, samples, 1)['states'], [1, 2, 1])
        for mutation in ['missing', 'state', 'early', 'old_generation', 'extra']:
            wrong = deepcopy(events)
            if mutation == 'missing': wrong.pop()
            elif mutation == 'state': wrong[-2]['values'][1] = 1
            elif mutation == 'early': wrong[-3]['boot_ns'] = '20000000000'
            elif mutation == 'old_generation': wrong[-1]['values'][0] = 0
            else: wrong.append(wrong[-1])
            with self.assertRaises(ValueError): compare_still(wrong, samples, 1)
        with self.assertRaises(ValueError): compare_still(events[:30], samples, 1)

    def test_missing_msdp_package_evidence_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError): verify_msdp_inventory(directory)
            (Path(directory) / 'inventory.json').write_text('{"status":"pass"}')
            with self.assertRaises(ValueError): verify_msdp_inventory(directory)

    def test_raw_rows_cannot_be_a_summary(self):
        path = self.file({}); path.write_text('{"status":"pass","callbacks":100}\n')
        with self.assertRaises((ValueError, KeyError)): load_rows(path, RUN)
        path.write_text(json.dumps(row(1, 'ready', [])) + '\n')
        self.assertEqual(len(load_rows(path, RUN)), 1)
        with self.assertRaises(ValueError): load_rows(path, '0' * 32)
        path.write_text(json.dumps(row(1, 'ready', [])).replace('{', '{\"seq\":2,', 1) + '\n')
        with self.assertRaises(ValueError): load_rows(path, RUN)
        value = row(1, 'sensor', [float('nan')]); path.write_text(json.dumps(value) + '\n')
        with self.assertRaises(ValueError): load_rows(path, RUN)

    def test_quiet_interval_requires_clock_markers(self):
        a = row(1, 'quiet_marker', []); b = row(2, 'quiet_marker', []); b['boot_ns'] = '15000000000'
        self.assertGreater(window([a, b], [1, 2])[1], 4)
        with self.assertRaises(ValueError): window([a, b], [0, 2])
        a['kind'] = 'expected_quiet';
        with self.assertRaises(ValueError): window([a, b], [1, 2])

    def test_mappings_require_real_uid_and_no_replaced_library(self):
        text = 'PROCESS /proc/1\nUid:\t1022\t1022\t1022\t1022\nu:r:location_host:s0\n/vendor/lib64/vendorGnssAdapter.so\n'
        self.assertEqual(mapped_processes(text)[0][0], 1022)
        for bad in [text.replace('Uid:', 'ExpectedUid:'), text + ' (deleted)', 'status:pass']:
            with self.assertRaises(ValueError): mapped_processes(bad)

    def test_wire_evidence_needs_real_all_sessions(self):
        with self.assertRaises(ValueError): sessions({'sessions': []}, {})

    def test_wire_bytes_rejection_and_retired_nonce(self):
        # Codec/validator test only: constructed transcript must never be reported
        # as device execution or new-package proof.
        values = []; inputs = {}; old = {}; counter = 0
        for generation in (1, 2):
            source = dict(at_ms=0, utc_ms=1700000000000, latitude=30.1234,
                longitude=120.4321, horizontal_accuracy=2.5, x=1.1, y=2.2, z=9.3)
            inputs[generation] = {k: [source] for k in ('gnss', 'sensor')}
            for kind in ('gnss', 'sensor'):
                labels = ['wrong_nonce', 'zero_sequence', 'wrong_version', 'nonfinite']
                if generation == 2: labels.append('old_generation_nonce')
                labels.append('valid-generation-' + str(generation))
                for label in labels:
                    counter += 1; challenge = counter.to_bytes(16, 'little')
                    hello = struct.pack('<4sI16sII', b'QGN1' if kind == 'gnss' else b'QSN1', 1, challenge, 88 if kind == 'gnss' else 1, 0)
                    packet = bytearray(encode_sample(challenge, 1, {k:v for k,v in source.items() if k not in ('x','y','z')}) if kind == 'gnss' else
                        struct.pack('<4sI16sQfff', b'QSF1', 1, challenge, 1, source['x'], source['y'], source['z']))
                    if label == 'wrong_nonce': packet[8] ^= 128
                    elif label == 'zero_sequence': packet[24:32] = bytes(8)
                    elif label == 'wrong_version': packet[4:8] = struct.pack('<I', 0xffffffff)
                    elif label == 'nonfinite':
                        if kind == 'gnss': packet[40:48] = struct.pack('<d', float('nan'))
                        else: packet[32:36] = struct.pack('<f', float('nan'))
                    elif label == 'old_generation_nonce': packet[8:24] = old[kind]
                    else: old[kind] = challenge
                    values.append(dict(kind=kind, generation=generation, label=label, hello_hex=hello.hex(),
                        connected_monotonic_ns=1, trace_start_monotonic_ns=1, frames=[dict(hex=bytes(packet).hex(), host_monotonic_ns=2)],
                        eof_monotonic_ns=3, disconnect='EOF', stop_disconnect='EOF'))
        # Strip sensor-only source keys for the actual GNSS contract.
        for generation in inputs:
            inputs[generation]['gnss'] = [{k:v for k,v in inputs[generation]['gnss'][0].items() if k not in ('x','y','z')}]
        self.assertEqual(sessions({'sessions': values}, inputs)['unique_provider_nonces'], 22)
        for field, replacement in [('disconnect', None), ('hello_hex', values[0]['hello_hex']), ('frames', [])]:
            wrong = deepcopy(values); wrong[1][field] = replacement
            with self.assertRaises(ValueError): sessions({'sessions': wrong}, inputs)


if __name__ == '__main__': unittest.main()
