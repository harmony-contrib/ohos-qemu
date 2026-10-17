#!/usr/bin/env python3
"""Controlled host protocol counterexamples ONLY; never guest success evidence."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import batch_media_audio_haptic_project as project
import batch_media_audio_haptic_verify as verify
from batch_media_audio_haptic_runtime import owned_capture_listing
import batch_media_audio_haptic_runtime as runtime


class HostChecks(unittest.TestCase):
    def test_real_pinned_schema_and_fresh_challenge_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = project.challenge(root / 'first')
            second = project.challenge(root / 'second')
            a, b = project.validate_challenge(first), project.validate_challenge(second)
            self.assertNotEqual(a['run_id'], b['run_id'])
            self.assertNotEqual(a['reference']['sha256'], b['reference']['sha256'])
            self.assertEqual(a['haptic_provenance'], b['haptic_provenance'])
            with self.assertRaises(FileExistsError): project.challenge(root / 'first')
            with self.assertRaises(json.JSONDecodeError): project.load(project.checked(a['files']['bad.json']))
            project.checked(a['files']['haptic.json']).write_text('{}')
            with self.assertRaises(ValueError): project.validate_challenge(first)

    def test_fixed_plan_fresh_request_and_original_class_copy(self):
        phases = project.phases()
        self.assertEqual(len({p['name'] for p in phases}), len(phases))
        self.assertTrue({f'normal-start-{n}' for n in (1, 2, 3)} <= {p['name'] for p in phases})
        self.assertTrue({'eos-start-1', 'eos-start-2', 'loop-start', 'post-release-start', 'recreate-active-release',
                         'mute-audio-start', 'mute-haptics-start', 'mute-both-start', 'denied-create',
                         'bad-wav-retry-start', 'bad-json-retry-start', 'missing-wav-retry-start'} <= {p['name'] for p in phases})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); challenge = project.challenge(root / 'challenge')
            boot = 'a'*8 + '-' + 'b'*4 + '-' + 'c'*4 + '-' + 'd'*4 + '-' + 'e'*12
            a = project.request(challenge, boot, 'normal-start-1')
            b = project.request(challenge, boot, 'normal-start-1')
            self.assertNotEqual(a['request']['operation_id'], b['request']['operation_id'])
            for role in project.ROLES:
                manifest = project.render(root / role, role, challenge, None)
                value = project.load(manifest)
                self.assertEqual(value['apl'], 'normal'); self.assertFalse(value['system_app'])
                self.assertEqual(value['allowed_acls'], [])
                self.assertEqual((root / role / 'entry/src/main/ets/pages/AudioHapticProbe.ets').read_bytes(), project.PROBE.read_bytes())
                page = (root / role / 'entry/src/main/ets/pages/Index.ets').read_text()
                self.assertEqual(page.count('new AudioHapticProbe('), 1)
                self.assertIn('private probe: AudioHapticProbe | undefined', page)
                self.assertNotIn('aboutToAppear', page)

    def test_raw_record_and_error_counterexamples(self):
        run = 'a'*32; boot = 'b'*8+'-'+'b'*4+'-'+'b'*4+'-'+'b'*4+'-'+'b'*12
        identity = dict(uid=20010001, token_id=123)
        request = dict(schema_version=1, run_id=run, boot_id=boot, operation_id='c'*32, action='create')
        def row(sequence, event, value, code=0):
            return dict(schema_version=1, run_id=run, boot_id=boot, operation_id='c'*32, sequence=sequence,
                timestamp_ms=sequence, uid=identity['uid'], token_id=identity['token_id'], player_epoch=0,
                event=event, api='create', value_json=json.dumps(value), error_code=code, error_message='controlled host input' if code else '')
        original = [row(1, 'begin', request), row(2, 'error', {}, 201)]
        encode = lambda rows: ''.join(json.dumps(r)+'\n' for r in rows)
        parsed = verify.parse_journal(encode(original), run, boot, identity)
        expectation = dict(expected='error', errors=[201])
        self.assertEqual(verify.operation(parsed, {'request': request}, expectation, role='denied', previous_epoch=0, source_id=1), (0, 1))
        for mutate in (lambda r: r[1].update(sequence=1), lambda r: r[1].update(uid=20010002),
                       lambda r: r[1].update(token_id=999), lambda r: r[1].update(boot_id=run)):
            rows = copy.deepcopy(original); mutate(rows)
            with self.assertRaises(ValueError): verify.parse_journal(encode(rows), run, boot, identity)
        wrong = copy.deepcopy(parsed); wrong[1]['error_code'] = 5400103
        with self.assertRaises(ValueError): verify.operation(wrong, {'request': request}, expectation, role='denied', previous_epoch=0, source_id=1)

    def test_independent_audio_rejects_wrong_challenge_channels_and_empty_silence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); manifest = project.challenge(root / 'challenge'); data = project.validate_challenge(manifest)
            reference = project.checked(data['reference']).read_bytes()
            def capture(name, raw):
                path = root / (name+'.wav')
                with wave.open(str(path), 'wb') as stream:
                    stream.setparams((2, 2, 48000, 0, 'NONE', 'none')); stream.writeframes(raw)
                return dict(wav=project.record(path), host_begin_ns=1000000000, host_end_ns=6000000000)
            raw = bytes(48000) + reference*4 + bytes(144000)
            good = capture('controlled-signal', raw)
            result = verify.audio_metrics(good, {'audio': 'eos', 'action': 'start'}, project.pcm.pcm_values(reference))
            self.assertEqual(result['frames'], 240000)
            wrong = project.pcm.pcm_values(reference); wrong.reverse()
            with self.assertRaises(ValueError): verify.audio_metrics(good, {'audio': 'eos', 'action': 'start'}, wrong)
            zero = capture('controlled-silence', bytes(240000*4))
            verify.audio_metrics(zero, {'audio': 'quiet', 'action': 'start'}, project.pcm.pcm_values(reference))
            with self.assertRaises(ValueError): verify.audio_metrics(capture('empty', b''), {'audio': 'quiet', 'action': 'start'}, project.pcm.pcm_values(reference))
            with self.assertRaises(ValueError): verify.audio_metrics(good, {'audio': 'quiet', 'action': 'start'}, project.pcm.pcm_values(reference))

    def test_hmp_exact_ownership_and_sampler_read_only_source(self):
        owned_capture_listing('[0]: Capturing audio(48000,16,2) to /tmp/ours.wav: 1234 bytes\n', '/tmp/ours.wav')
        for text in ('[1]: Capturing audio(48000,16,2) to /tmp/ours.wav: 1234 bytes\n',
                     '[0]: Capturing audio(48000,16,2) to /tmp/other.wav: 1234 bytes\n',
                     '[0]: Capturing audio(48000,16,2) to /tmp/ours.wav: 1234 bytes\nextra\n'):
            with self.assertRaises(ValueError): owned_capture_listing(text, '/tmp/ours.wav')
        source = (project.FIX / 'sampler.cpp').read_text()
        self.assertIn('driver->IsVibratorRunning(device, running)', source)
        self.assertNotRegex(source, r'driver->(?:Start|Stop|Enable|Play)\w*\(')
        self.assertNotIn('GrantPermission(', source)
        self.assertNotIn('RevokePermission(', source)

    def test_exact_HMP_notice_does_not_hide_capture_or_other_output(self):
        notice = runtime.INFO_CAPTURE_NOTICE
        own = '[0]: Capturing audio(48000,16,2) to /tmp/ours.wav: 1234 bytes\r\n'
        self.assertTrue(runtime.capture_list_empty(''))
        self.assertTrue(runtime.capture_list_empty(notice))
        owned_capture_listing(notice+own, '/tmp/ours.wav')
        for text in (own, notice+own, notice*2, notice.replace('v10.2', 'v10.3'),
                     notice.replace('info capture', 'stopcapture'), notice.replace('\r\n', '\n'),
                     notice+'Failed to add wave capture\r\n', 'unknown monitor output\n'):
            with self.subTest(text=text): self.assertFalse(runtime.capture_list_empty(text))
        for text in (notice*2+own, notice+own+own, notice+own+'error\n',
                     notice+own.replace('[0]', '[1]'), notice+own.replace('/ours.wav', '/foreign.wav'),
                     notice+own.replace('48000,16,2', '44100,16,2')):
            with self.subTest(text=text), self.assertRaises(ValueError): owned_capture_listing(text, '/tmp/ours.wav')

    def test_capture_refuses_foreign_state_without_any_start_or_stop(self):
        notice = runtime.INFO_CAPTURE_NOTICE
        def collector():
            return SimpleNamespace(env={'qemu_command': 'qemu -audiodev none,id=ohos_audio -device es1370,audiodev=ohos_audio'},
                value={'qmp': {'requests': []}}, guest=SimpleNamespace(healthy=lambda: None), persist=lambda: None)
        for baseline in (notice, notice+'[0]: Capturing audio(48000,16,2) to /tmp/foreign.wav: 40 bytes\r\n', notice*2):
            calls = []
            def qmp(capture, execute, label, arguments):
                calls.append(arguments['command-line'])
                return 'wavcapture path audiodev [frequency [bits [channels]]]\r\n' if label == 'capture-help' else baseline
            with patch.object(runtime.AudioCapture, 'qmp', qmp):
                if baseline == notice:
                    capture = runtime.AudioCapture(collector()); self.assertFalse(capture.owned)
                else:
                    with self.assertRaises(ValueError): runtime.AudioCapture(collector())
            self.assertEqual(calls, ['help wavcapture', 'info capture'])
        capture = runtime.AudioCapture.__new__(runtime.AudioCapture)
        capture.path = Path('/tmp/ours.wav'); capture.owned = True; calls = []
        def foreign(command, label):
            calls.append(command)
            return notice+'[0]: Capturing audio(48000,16,2) to /tmp/foreign.wav: 40 bytes\r\n'
        capture.hmp = foreign
        with self.assertRaises(ValueError): capture.stop('controlled')
        self.assertEqual(calls, ['info capture']); self.assertTrue(capture.owned)

    def test_BMS_UID_and_actual_token_join_with_raw_bracketing(self):
        role = 'normal'; bundle = project.ROLES[role][0]; run = 'a'*32; boot = 'b'*36
        uid = 20010040; token = 537042608
        def bms(uid=uid, token=token):
            return bundle+':\n'+json.dumps(dict(appIndex=0, uid=uid,
                applicationInfo=dict(bundleName=bundle, appIndex=0, isSystemApp=False, appPrivilegeLevel='normal',
                    uid=uid, accessTokenId=token), hapModuleInfos=[dict(hapPath='/data/app/el1/bundle/public/'+bundle+'/entry.hap')],
                userInfo=[dict(bundleName=bundle, uid=uid, accessTokenId=token, bundleUserInfo=dict(userId=100))]))
        raw_bms = bms(); identity = verify.bms_identity(raw_bms, role)
        native = dict(kind='token', run_id=run, boot_id=boot, bundle=bundle, token_id=token, VIBRATE=0,
            before_ns=10, after_ns=11, identity_schema='hap-bms-access-token/v1', expected_uid=uid,
            at_reported_uid=0, at_query_rc=0, at_token_id=token, at_user_id=100, at_inst_index=0, at_bundle=bundle)
        scripts = {'before': 'bm dump -n '+bundle, 'after': 'bm dump -n '+bundle,
            'token': project.sampler_script('/data/local/tmp/audio-haptic-'+run, 'token', run, boot, bundle, uid)}
        data = {'before': raw_bms, 'token': json.dumps(native), 'after': raw_bms}
        refs = {name:dict(path=name, sha256=name) for name in data}; indexes = dict(before=1, token=2, after=3)
        binding = dict(bms_before=refs['before'], token=refs['token'], bms_after=refs['after'])
        def observed(ref, expected):
            self.assertEqual(expected, scripts[ref['path']]); return data[ref['path']]
        def replay():
            return verify.verify_token_binding(binding, refs['token'], role=role, identity=identity, run=run, boot=boot,
                observed=observed, command_index=lambda ref:indexes[ref['path']])
        self.assertEqual(replay()['at_reported_uid'], 0)  # The BMS record, not this unsupported AT field, supplies UID.
        for key, wrong in [('expected_uid', uid+1), ('at_token_id', token+1), ('at_inst_index', 1),
                           ('at_query_rc', -1), ('uid', uid), ('before_ns', True), ('VIBRATE', False)]:
            data['token'] = json.dumps(dict(native, **{key:wrong}))
            with self.subTest(key=key), self.assertRaises(ValueError): replay()
        data['token'] = json.dumps(native)
        for changed in (bms(uid=uid+1), bms(token=token+1)):
            data['after'] = changed
            with self.assertRaisesRegex(ValueError, 'BMS identity changed'): replay()
        data['after'] = raw_bms; indexes['after'] = 1
        with self.assertRaisesRegex(ValueError, 'bracket'): replay()
        wrong = json.loads(raw_bms.removeprefix(bundle+':\n')); wrong['userInfo'][0]['accessTokenId'] += 1
        with self.assertRaises(ValueError): verify.bms_identity(bundle+':\n'+json.dumps(wrong), role)
        wrong['userInfo'][0]['accessTokenId'] -= 1; wrong['applicationInfo']['appIndex'] = 1
        with self.assertRaises(ValueError): verify.bms_identity(bundle+':\n'+json.dumps(wrong), role)


if __name__ == '__main__':
    print('HOST STRUCTURE/CONTROLLED PROTOCOL ONLY: no SDK, product compiler, guest, real PCM or VDI validation')
    unittest.main(verbosity=2)
