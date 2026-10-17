#!/usr/bin/env python3
"""Controlled host protocol counterexamples ONLY; never guest success evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave

import batch_media_audio_haptic_project as project
import batch_media_audio_haptic_verify as verify
from batch_media_audio_haptic_runtime import owned_capture_listing


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


if __name__ == '__main__':
    print('HOST STRUCTURE/CONTROLLED PROTOCOL ONLY: no SDK, product compiler, guest, real PCM or VDI validation')
    unittest.main(verbosity=2)
