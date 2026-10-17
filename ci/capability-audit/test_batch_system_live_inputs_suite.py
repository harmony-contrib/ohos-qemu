#!/usr/bin/env python3
"""Pure host schemas/control flow only; never guest/SDK/signature evidence."""
import argparse
import ast
import copy
import json
from pathlib import Path
import shlex
import shutil
import struct
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import batch_system_live_inputs_suite as s
from test_batch_runtime_process_snapshots import BOOT, frame, hx, queries

RUN = '1d8d363122285be8460a74f49d0933f2'


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name).resolve()

    def put(self, name, data):
        path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes): path.write_bytes(data)
        elif isinstance(data, str): path.write_text(data)
        else: path.write_text(json.dumps(data))
        return path

    def vectors(self):
        rows = []
        for generation in (1, 2):
            sensor = [{'at_ms': i * 200, 'x': generation / 10 + i / 1000, 'y': 0,
                'z': (9.6 - generation / 10) if i < 10 or i >= 20 else generation} for i in range(30)]
            gnss = [{'at_ms': i * 1000, 'latitude': 30 + generation + i / 100,
                'longitude': 110 + generation + i / 100, 'horizontal_accuracy': 3 + generation} for i in range(3)]
            rows.append({'generation': generation, 'gnss': gnss, 'sensor': sensor})
        return {'schema_version': 1, 'source_id': 'UNIT-controlled-protocol-vectors-NOT-measurements', 'generations': rows}

    def source(self, value=None):
        value = self.vectors() if value is None else value
        path = self.put('vectors.json', value)
        return {'mode': s.CONTROLLED, 'source_id': value['source_id'], 'vectors': s.descriptor(path)}

    def test_explicit_distinct_vectors_validated_without_generating_guest_results(self):
        source = self.source(); values = s.source_vectors(source)
        self.assertEqual(set(values), {1, 2})
        self.assertNotEqual(values[1]['gnss'], values[2]['gnss'])
        self.assertFalse((self.root / 'capture.json').exists())

    def test_duplicate_generation_UTC_nonfinite_and_wrong_phases_rejected(self):
        original = self.vectors(); wrong = []
        row = copy.deepcopy(original); row['generations'][1]['generation'] = 1; wrong.append(row)
        row = copy.deepcopy(original); row['generations'][0]['gnss'][0]['utc_ms'] = 1; wrong.append(row)
        row = copy.deepcopy(original); row['generations'][0]['gnss'][0]['latitude'] = float('nan'); wrong.append(row)
        row = copy.deepcopy(original); row['generations'][0]['sensor'][0]['at_ms'] = -1; wrong.append(row)
        row = copy.deepcopy(original)
        for sample in row['generations'][0]['sensor']: sample['z'] = 9.8
        wrong.append(row)
        row = copy.deepcopy(original); row['generations'][1]['sensor'] = row['generations'][0]['sensor']; wrong.append(row)
        for value in wrong:
            with self.assertRaises((ValueError, OverflowError)): s.source_vectors(self.source(value))

    def test_vector_hash_is_rechecked(self):
        source = self.source(); self.put('vectors.json', self.vectors() | {'extra': 'changed'})
        with self.assertRaisesRegex(ValueError, 'artifact SHA changed'): s.source_vectors(source)

    def test_atomic_publication_never_overwrites_or_leaves_partial_json(self):
        path = self.root / 'published.json'; s.atomic_json(path, {'schema': 'unit'})
        before = path.read_bytes()
        with self.assertRaises(ValueError): s.atomic_json(path, {'schema': 'changed'})
        self.assertEqual(path.read_bytes(), before); self.assertFalse(list(self.root.glob('*.publishing-*')))

    def test_no_ready_publisher_fails_without_guest_result_or_trace(self):
        spec = self.put('artifacts.json', {'input_source': self.source()}); inputs = self.root / 'inputs'; inputs.mkdir()
        result = self.root / 'publisher.json'
        self.assertEqual(s.publish_controlled(spec, self.root / 'capture', inputs, RUN, result, wait=0), 1)
        self.assertEqual(s.read_json(result)['status'], 'fail'); self.assertEqual(list(inputs.iterdir()), [])

    def test_host_publisher_two_constructed_ready_signals_only_claim_publication(self):
        source = self.source(); spec = self.put('artifacts.json', {'input_source': source}); inputs = self.root / 'inputs'; inputs.mkdir()
        for generation in (1, 2): self.put('capture/ready-' + str(generation) + '.json', {'run_id': RUN, 'generation': generation})
        result = self.root / 'publisher.json'
        self.assertEqual(s.publish_controlled(spec, self.root / 'capture', inputs, RUN, result, wait=0), 0)
        value = s.read_json(result); self.assertEqual(value['status'], 'published_NOT_guest_verified')
        self.assertIn('NOT_physical_measurements_or_guest_results', value['scope'])
        for row in value['generations']:
            g = row['generation']; gnss = s.trace(inputs / ('gnss-' + str(g) + '.json'), 'gnss')
            self.assertTrue(all(sample['utc_ms'] == row['host_utc_ms'] + sample['at_ms'] for sample in gnss))
            self.assertEqual(s.read_json(inputs / ('sensor-' + str(g) + '.json')), self.vectors()['generations'][g - 1]['sensor'])
        self.assertFalse((self.root / 'raw-results.jsonl').exists())

    def test_missing_second_ready_preserves_partial_failure(self):
        spec = self.put('artifacts.json', {'input_source': self.source()}); inputs = self.root / 'inputs'; inputs.mkdir()
        self.put('capture/ready-1.json', {'run_id': RUN, 'generation': 1}); result = self.root / 'publisher.json'
        self.assertEqual(s.publish_controlled(spec, self.root / 'capture', inputs, RUN, result, wait=0), 1)
        self.assertTrue((inputs / 'generation1.json').exists()); self.assertFalse((inputs / 'generation2.json').exists())
        self.assertEqual(s.read_json(result)['status'], 'fail')

    def test_stale_ready_identity_does_not_publish(self):
        spec = self.put('artifacts.json', {'input_source': self.source()}); inputs = self.root / 'inputs'; inputs.mkdir()
        self.put('capture/ready-1.json', {'run_id': '0' * 32, 'generation': 1})
        self.assertEqual(s.publish_controlled(spec, self.root / 'capture', inputs, RUN, self.root / 'publisher.json', wait=0), 1)
        self.assertEqual(list(inputs.iterdir()), [])

    def command_row(self, name, text, *, script=None):
        marker = '__LIVE_SUITE_EXIT_' + 'a' * 32 + '__='
        stdout = text if script is None else text + '\n' + marker + '0\n'
        row = {'exit_code': 0, 'stdout': s.descriptor(self.put(name + '-stdout', stdout)),
            'stderr': s.descriptor(self.put(name + '-stderr', '')), 'log': s.descriptor(self.put(name + '-log', stdout)),
            'argv': ['/unit/hdc', '-t', '127.0.0.1:12345', 'fport', 'ls']}
        if script is not None:
            row.update(script=script, marker=marker, guest_exit_code=0, raw=s.descriptor(self.put(name + '-raw', text)))
            row['argv'] = ['/unit/hdc', '-t', '127.0.0.1:12345', 'shell',
                '(' + script + '); task_live_suite_rc=$?; printf "\\n' + marker + '%s\\n" "$task_live_suite_rc"']
        return row

    def cleanup(self):
        # Constructed parser records only; never persisted as runtime evidence.
        rows = [self.command_row('bms', 'com.ohos.systemui\n', script='bm dump -a')]
        for i in (1,2):
            nonce=str(i)*32
            row=self.command_row('process-'+str(i),frame(mode='uid',nonce=nonce,boot=BOOT,uid=20001,bundle=s.BUNDLE),
                script=s.uid_process_scan(20001,nonce=nonce,boot_id=BOOT))
            row['process_scan_nonce']=nonce; rows.append(row)
        rows.append(self.command_row('forwards', ''))
        return {'boot_id':BOOT,'cleanup_complete': True, 'cleanup_errors': [], 'commands': rows, 'cleanup': {
            'ordinary_uid': 20001, 'BMS_after': 0, 'process_scans': [1, 2], 'forwards_after': 3,
            'open_streams': 0, 'owned_forwards': [['tcp:12346', 'localfilesystem:/dev/unix/socket/qemu_gnss/input']],
            'producer': {'owned': True, 'exited': True, 'exit_code': 0}}}

    def test_cleanup_requires_bound_command_stdout_and_guest_exit(self):
        report = self.cleanup(); self.assertEqual(s.verify_cleanup(report, '127.0.0.1:12345')['status'], 'pass')
        for field, value in [('exit_code', 1), ('guest_exit_code', 1), ('script', 'expected-only text')]:
            wrong = copy.deepcopy(report); wrong['commands'][0][field] = value
            with self.assertRaises(ValueError): s.verify_cleanup(wrong, '127.0.0.1:12345')
        with self.assertRaises(ValueError): s.verify_cleanup(report, '127.0.0.1:9999')
        path = Path(report['commands'][0]['stdout']['path']); path.write_text('forged')
        with self.assertRaisesRegex(ValueError, 'SHA changed'): s.verify_cleanup(report, '127.0.0.1:12345')

    def test_app_or_uid_process_or_forward_remaining_rejects_cleanup(self):
        for resource in ('app', 'process', 'forward'):
            report = self.cleanup()
            if resource == 'app': report['commands'][0] = self.command_row('left-bms', s.BUNDLE + '\n', script='bm dump -a')
            if resource == 'process': report['commands'][1] = self.command_row('left-process', 'UID_PROCESS /proc/123\n__LIVE_PROCESS_SCAN_DONE__\n', script=s.uid_process_scan(20001,nonce='1'*32,boot_id=BOOT))
            if resource == 'forward': report['commands'][3] = self.command_row('left-forward', 'tcp:12346 localfilesystem:/dev/unix/socket/qemu_gnss/input\n')
            with self.assertRaises(ValueError): s.verify_cleanup(report, '127.0.0.1:12345')

    def test_done_only_and_failed_queries_do_not_prove_empty(self):
        for raw in ('__LIVE_PROCESS_SCAN_DONE__\n',frame(mode='uid',nonce='1'*32,boot=BOOT,uid=20001,bundle=s.BUNDLE,
                records={1:{**queries(1,mode='uid',ppid=0),'cmdline':(1,hx('od: /proc/1/cmdline: Permission denied'))}})):
            report=self.cleanup(); row=self.command_row('fake-empty',raw,script=s.uid_process_scan(20001,nonce='1'*32,boot_id=BOOT))
            row['process_scan_nonce']='1'*32; report['commands'][1]=row
            with self.assertRaises(ValueError): s.verify_cleanup(report,'127.0.0.1:12345')

    def test_cleanup_flags_or_producer_state_cannot_replace_raw_proof(self):
        for field, value in [('cleanup_complete', False), ('cleanup_errors', ['not cleaned'])]:
            report = self.cleanup(); report[field] = value
            with self.assertRaises(ValueError): s.verify_cleanup(report, '127.0.0.1:12345')
        for field, value in [('open_streams', 1), ('producer', {'owned': True, 'exited': False}), ('process_scans', [1])]:
            report = self.cleanup(); report['cleanup'][field] = value
            with self.assertRaises(ValueError): s.verify_cleanup(report, '127.0.0.1:12345')
        report = self.cleanup(); report['commands'][0]['process_group_cleanup_unconfirmed'] = True
        with self.assertRaisesRegex(ValueError, 'did not quiesce'): s.verify_cleanup(report, '127.0.0.1:12345')
        with self.assertRaises(ValueError): s.verify_cleanup({'cleanup_complete': True, 'cleanup_errors': [], 'cleanup': {}, 'commands': []}, '127.0.0.1:12345')

    def test_only_ordinary_uid_is_allowed_in_process_cleanup_script(self):
        for uid in (0, 1022, 3033, 10000, True, '20001'):
            with self.assertRaises(ValueError): s.uid_process_scan(uid)
        self.assertIn(s.BUNDLE, s.uid_process_scan(None,nonce='1'*32,boot_id=BOOT)); self.assertIn('20001', s.uid_process_scan(20001,nonce='1'*32,boot_id=BOOT))

    def test_native_ELF_parser_requires_real_ARM64_DSO_shape(self):
        data = bytearray(64); data[:7] = b'\x7fELF\x02\x01\x01'; struct.pack_into('<HH', data, 16, 3, 183)
        path = self.put('unit-parser-only-ELF', bytes(data)); self.assertEqual(s.elf64_arm64(path), s.descriptor(path))
        for at, value in [(4, 1), (5, 2), (16, 2), (18, 62)]:
            wrong = data[:]; wrong[at] = value; path.write_bytes(wrong)
            with self.assertRaises(ValueError): s.elf64_arm64(path)

    def test_capture_service_mapping_pattern_includes_real_algo_and_service(self):
        source = s.HERE / 'batch_system_run_live_inputs.py'
        cls = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.ClassDef) and n.name == 'Capture')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'mappings')
        namespace = {'Path': Path, 'shlex': shlex}; exec(compile(ast.Module(body=[method], type_ignores=[]), '<actual-capture-method>', 'exec'), namespace)
        scripts = []; obj = SimpleNamespace(output=self.root, shell=lambda script, name: scripts.append(script) or 'unit OS output')
        namespace['mappings'](obj, 'unit-maps')
        self.assertIn('libdevicestatus_algo.z.so|libdevicestatus_service.z.so', scripts[0])
        self.assertIn('libdevicestatus_mock.z.so', scripts[0])

    def test_private_copy_retains_original_build_proof_without_recompile(self):
        source = self.root / 'source'; source.mkdir()
        self.put('source/live-inputs-contract.json', {'native_packaging': {'relative_library': 'entry/libs/arm64-v8a/libliveinputaudit.so'}})
        native = self.put('source/entry/libs/arm64-v8a/libliveinputaudit.so', b'unit copy bytes only, not ELF')
        hap = self.put('unit.hap', b'unit descriptor only, not compiled HAP')
        manifest = source / 'live-inputs-contract.json'; rows = {'live-inputs-contract.json': s.digest(manifest)}
        spec = {'caller': {'sdk_evidence': {'path': '/unit/sdk-report', 'sha256': 'a' * 64}, 'unsigned_hap': s.descriptor(hap)}}
        result = {'source_project': str(source), 'native_binary': s.descriptor(native),
                  'native_strip': {'scope': 'unit copy metadata ONLY, not an SDK replay'}}
        before = manifest.read_bytes(); destination = s.capture_project(self.root / 'private-copy', spec, result, [], rows)
        self.assertEqual(manifest.read_bytes(), before)
        self.assertIn('NOT_new_compilation', s.read_json(destination / 'live-inputs-build.json')['scope'])
        self.assertFalse((source / 'live-inputs-build.json').exists())
        s.verify_capture_project(destination, spec, result, [], rows)
        receipt = destination / 'live-inputs-build.json'; value = s.read_json(receipt)
        changed = copy.deepcopy(value); changed['native_strip'] = {'status': 'invented'}
        receipt.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'native strip proof differs'):
            s.verify_capture_project(destination, spec, result, [], rows)
        value['commands'] = [{'expected_status': 'pass', 'not_actual_command': True}]; receipt.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'original verified SDK commands'):
            s.verify_capture_project(destination, spec, result, [], rows)

    def test_publisher_changed_source_failure_is_preserved(self):
        source = self.source(); artifacts = self.put('artifacts.json', {'input_source': source})
        self.put('vectors.json', self.vectors() | {'tampered': True}); inputs = self.root / 'inputs'; inputs.mkdir()
        result = self.root / 'publisher.json'
        self.assertEqual(s.publish_controlled(artifacts, self.root / 'capture', inputs, RUN, result, wait=0), 1)
        self.assertIn('SHA changed', s.read_json(result)['error']); self.assertEqual(list(inputs.iterdir()), [])

    def test_installed_bundle_inspection_cannot_be_empty_or_transport_failure(self):
        report = self.cleanup(); report['commands'][0] = self.command_row('empty-bms', '', script='bm dump -a')
        with self.assertRaisesRegex(ValueError, 'system bundle list missing'): s.verify_cleanup(report, '127.0.0.1:12345')
        report = self.cleanup(); report['commands'][3] = self.command_row('failed-forward-list', '[Fail] Device not found or connected\n')
        with self.assertRaisesRegex(ValueError, 'transport failed'): s.verify_cleanup(report, '127.0.0.1:12345')

    def test_post_ready_source_proof_rejects_wire_start_before_publication(self):
        # Constructed host source metadata only; no raw public callbacks/guest.
        source = self.source(); artifacts = self.put('artifacts.json', {'input_source': source})
        inputs = self.root / 'inputs'; inputs.mkdir(); capture = self.root / 'capture'
        for g in (1, 2): self.put('capture/ready-' + str(g) + '.json', {'run_id': RUN, 'generation': g, 'host_utc_ms': time.time_ns() // 1_000_000})
        publisher = self.root / 'publisher.json'; self.assertEqual(s.publish_controlled(artifacts, capture, inputs, RUN, publisher, wait=0), 0)
        receipt = s.read_json(publisher); sessions = []
        for row in receipt['generations']:
            g = row['generation']; base = capture / ('input-' + str(g)); base.mkdir()
            shutil.copyfile(s.checked(row['manifest']), base / 'manifest.json')
            for kind in ('gnss', 'sensor'):
                shutil.copyfile(s.checked(row[kind]), base / (kind + '.json'))
                sessions.append({'generation': g, 'label': 'valid-generation-' + str(g), 'trace_start_monotonic_ns': row['host_monotonic_ns'] + 1})
        raw = self.put('capture/capture.json', {'sessions': sessions})
        report = {'run_id': RUN, 'publisher': s.descriptor(publisher), 'cleanup': {'producer': {'owned': True, 'exit_code': 0}},
            'artifacts': s.descriptor(artifacts), 'publisher_process': {'pid': receipt['pid']}}
        self.assertEqual(s.verify_input_source(report, {'input_source': source}, capture)['mode'], s.CONTROLLED)
        sessions[0]['trace_start_monotonic_ns'] = 0; raw.write_text(json.dumps({'sessions': sessions}))
        with self.assertRaisesRegex(ValueError, 'preceded post-ready'): s.verify_input_source(report, {'input_source': source}, capture)


if __name__ == '__main__': unittest.main()
