"""Light host counterexamples only. No guest, SDK/native build or signing."""
from array import array
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import batch_media_audio_haptic_coordinator as c

RUN = 'a'*32
UID = 20010001
PID = 523
SDK = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')
EXPORT = Path('/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-audio-haptic-source-inputs-01/evidence.json')


def token():
    return {'schema_version': 1, 'run_id': RUN, 'user_id': 100, 'uid': UID, 'bundle': c.BUNDLES['owner'],
            'token_id': 123456, 'permission': 'ohos.permission.VIBRATE', 'before': 0, 'after': 0, 'before_ns': 100, 'after_ns': 101}


def task_text(mode='2,', suspended='false', pid=PID, uid=UID, bundle=None):
    bundle = bundle or c.BUNDLES['owner']
    return ('No.1\n\tuid: '+str(uid)+'\n\tpid: '+str(pid)+'\n\tcontinuousTaskId: 4\n\tnotificationId: 9\n'
            '\tabilityName: EntryAbility\n\tbundleName: '+bundle+'\n\tbackgroundModes: '+mode+'\n'
            '\tsuspendState: '+suspended+'\n\twantAgentBundleName: '+bundle+'\n'
            '\tisCombinedTaskNotification: false\n\tnotificationLabel: actual-label\n')


ANS = 'notification list:\nNo.1\nOwnerUid: '+str(UID)+'\nId: 9\nLabel: actual-label\n'


def process_raw(uid=UID, pid=PID, start=900):
    # Kernel fields3..22; field22 is starttime, not an invented wall clock.
    fields = ['S']+['0']*18+[str(start)]
    return 'Name:\tactual-app\nUid:\t'+('\t'.join([str(uid)]*4))+'\n\nQEMU_PROCESS_STAT\n'+str(pid)+' (app has spaces) '+' '.join(fields)+'\n'


class AudioHapticCoordinatorTests(unittest.TestCase):
    def test_token_keeps_actual_bundle_uid_grant_and_monotonic(self):
        actual = c.actual_token(json.dumps(token()), RUN, 'owner', UID, 'ohos.permission.VIBRATE', 0)
        self.assertEqual(actual['token_id'], 123456)
        for key, value in [('bundle', c.BUNDLES['contender']), ('uid', UID+1), ('before', False), ('after', -1), ('after_ns', 99)]:
            row = token(); row[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                c.actual_token(json.dumps(row), RUN, 'owner', UID, 'ohos.permission.VIBRATE', 0)

    def test_duplicate_raw_keys_rejected(self):
        with self.assertRaises(ValueError): c.loads('{"uid":1,"uid":2}')
        with self.assertRaises(ValueError): c.loads('{"clock":NaN}')

    def test_process_identity_uses_uid_and_kernel_start_generation(self):
        actual = c.process_identity(process_raw(), PID, UID)
        self.assertEqual(actual, {'pid': PID, 'uid': UID, 'start_ticks': 900})
        for raw in (process_raw(uid=0), process_raw(pid=PID+1), process_raw(start=0), 'Uid: 20010001\n'):
            with self.assertRaises(ValueError): c.process_identity(raw, PID, UID)

    def test_loaded_haptic_mapping_requires_unique_actual_file_inode(self):
        line = '7000-9000 r-xp 00000000 00:19 234 /system/lib64/libaudio_haptic.z.so\n'
        self.assertEqual(c.mapped_haptic(line), {'guest_path': '/system/lib64/libaudio_haptic.z.so', 'inode': 234})
        for raw in (line.replace('234 ', '0 '), line.replace('.so', '.so (deleted)'), line+line.replace('234 ', '235 '), ''):
            with self.assertRaises(ValueError): c.mapped_haptic(raw)

    def test_real_audio_playback_mode_two_join(self):
        joined = c.background_join(task_text(), task_text(), ANS, UID, PID, c.BUNDLES['owner'], 4, 9)
        self.assertEqual(joined['task']['backgroundModes'], '2,')

    def test_recording_and_substring_modes_are_not_playback(self):
        for mode in ('3,', '12,', '2,3,'):
            with self.assertRaises(ValueError):
                c.background_join(task_text(), task_text(mode), ANS, UID, PID, c.BUNDLES['owner'], 4, 9)

    def test_suspended_wrong_pid_and_other_notification_rejected(self):
        for own, full, ans in [(task_text(), task_text(suspended='true'), ANS),
                               (task_text(pid=PID+1), task_text(), ANS),
                               (task_text(), task_text(), ANS.replace('actual-label', 'other-label'))]:
            with self.assertRaises(ValueError): c.background_join(own, full, ans, UID, PID, c.BUNDLES['owner'], 4, 9)

    def test_actual_service_cleanup_requires_both_task_and_notification_absence(self):
        empty = 'No running continuous task\n'
        c.background_absent(empty, empty, 'no notification\n', UID, 9)
        for own, all_tasks, ans in [(task_text(), empty, 'no notification\n'), (empty, task_text(), 'no notification\n'), (empty, empty, ANS)]:
            with self.assertRaises(ValueError): c.background_absent(own, all_tasks, ans, UID, 9)
        with self.assertRaises(ValueError): c.background_absent(empty, empty, 'permission denied\nno notification\n', UID, 9)

    def test_background_cancellation_cannot_be_reported_as_focus(self):
        def rows(kind, cleaning, detail):
            event = json.dumps({'kind': kind, 'cleaning': cleaning, 'detail_json': json.dumps(detail), 'monotonic_ns': 10})
            return [{'api': 'backgroundTaskManager.observations', 'after_ns': 20, 'value': {'events': [event], 'overflow': 0}}]
        for value in (rows('cancel', False, {}), rows('suspend', False, {'suspendState': True}), rows('cancel_stop_error', True, {})):
            with self.assertRaises(ValueError): c.background_callbacks(value)
        self.assertEqual(c.background_callbacks(rows('cancel', True, {})), 1)
        self.assertEqual(c.background_callbacks(rows('suspend', False, {'suspendState': False})), 1)

    def test_overflow_cannot_hide_cancel(self):
        with self.assertRaises(ValueError):
            c.background_callbacks([{'api': 'backgroundTaskManager.observations', 'value': {'events': [], 'overflow': 1}}])

    def test_no_declared_or_promise_onset_anchor_can_pass(self):
        actual = c.no_onset_anchor()
        self.assertFalse(actual['accepted']); self.assertFalse(actual['synchronization_verified'])
        for value in ({'timestamp_ns': 1}, {'source': 'startPromise'}, {'source': 'capture_start'}, {'source': 'hilog_wall_clock'}):
            with self.assertRaises(ValueError): c.no_onset_anchor(value)

    def test_only_known_deprecation_warning_is_removed(self):
        warning = "warning: 'wavcapture' is deprecated since v10.2, to be removed\r\n"
        self.assertEqual(c.strip_hmp(warning), '')
        self.assertIn('unknown command', c.strip_hmp('unknown command: wavcapture\r\n'))
        self.assertIn('Error', c.strip_hmp(warning+'Error opening actual WAV\r\n'))

    def test_qmp_recheck_binds_each_capture_path_and_real_return(self):
        def row(command, reply=''):
            return {'command': command, 'records': [{'QMP': {'version': 'host-fixture_ONLY'}},
                {'sent': {'execute': 'qmp_capabilities', 'id': '1'*32}}, {'return': {}, 'id': '1'*32},
                {'sent': {'execute': 'human-monitor-command', 'id': '2'*32, 'arguments': {'command-line': command}}},
                {'return': reply, 'id': '2'*32}]}
        with tempfile.TemporaryDirectory() as temp:
            paths = [Path(temp).resolve()/name for name in ('owner.wav', 'focus.wav')]
            for path in paths: path.write_bytes(b'host-fixture_NOT_guest')
            value = {'qmp': [], 'captures': {}, 'capture_intervals': {}}
            for phase, path in zip(('owner-after-contender-foreground', 'focus'), paths):
                value['qmp'].extend([row('wavcapture '+str(path)+' ohos_audio 48000 16 2'), row('stopcapture 0')])
                value['captures'][phase] = c.descriptor(path)
                value['capture_intervals'][phase] = {'start_host_ns': 1, 'stop_host_ns': 2}
            c.verify_qmp(value)  # QMP envelope-only, not audio or full runtime.
            value['qmp'][0]['records'][-1]['return'] = 'Error opening actual WAV'
            with self.assertRaises(ValueError): c.verify_qmp(value)

    def test_lost_capture_start_reply_does_not_become_unowned_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'owned.wav'; path.write_bytes(b'unit_fixture_NOT_audio')
            coordinator = c.Coordinator.__new__(c.Coordinator)
            coordinator.capture = None; coordinator.pending_capture = ('focus', path)
            coordinator.value = {'captures': {}, 'capture_intervals': {'focus': {'start_host_ns': 1}}}
            coordinator.save = lambda: None
            answers = iter(['[0]: Capturing audio(48000,16,2) to '+str(path)+': 22 bytes\n', '', ''])
            commands = []
            def qmp(command): commands.append(command); return next(answers)
            coordinator.qmp = qmp; coordinator.stop_capture()
            self.assertEqual(commands, ['info capture', 'stopcapture 0', 'info capture'])
            self.assertIsNone(coordinator.capture); self.assertIsNone(coordinator.pending_capture)
            self.assertEqual(coordinator.value['captures']['focus'], c.descriptor(path))

    def test_lost_reply_never_stops_some_other_capture(self):
        coordinator = c.Coordinator.__new__(c.Coordinator)
        coordinator.capture = None; coordinator.pending_capture = ('focus', Path('/owned/focus.wav'))
        coordinator.qmp = lambda command: '[1]: Capturing audio(48000,16,2) to /somebody/else.wav: 22 bytes\n'
        with self.assertRaises(ValueError): coordinator.stop_capture()

    def test_explicit_build_path_map_preserves_original_source(self):
        aliases = [{'from': '/input', 'to': '/host/frozen'}, {'from': '/evidence', 'to': '/host/results'}]
        self.assertEqual(c.mapped('/input/probe.cpp', aliases), Path('/host/frozen/probe.cpp'))
        self.assertEqual(c.mapped('/ohos/compiler', aliases), Path('/ohos/compiler'))
        self.assertEqual(aliases[0]['from'], '/input')
        for invalid in ([{'from': '/', 'to': '/host'}], [{'from': '/input', 'to': '/host'}, {'from': '/input/sub', 'to': '/host2'}]):
            with self.assertRaises(ValueError): c.mapped('/input/sub/file', invalid)

    def test_derived_page_is_legitimate_public_audio_playback(self):
        page = c.derived_page(RUN, 'owner'); contender = c.derived_page(RUN, 'contender')
        self.assertIn("['audioPlayback']", page)
        self.assertNotIn('audioRecording', page)
        self.assertIn('requestEnableNotification(context)', page)
        self.assertIn("raw.endsWith('\\n')", page)
        self.assertIn('this.backgroundOverflow++', page)
        self.assertIn('this.backgroundCleaning = true', page)
        self.assertIn('STREAM_USAGE_VOICE_COMMUNICATION', contender)
        self.assertNotIn('throw error', page)
        self.assertEqual(c.base.PAGE.read_text().count('startBackgroundRunning'), 0)

    def test_token_observer_has_no_permission_mutation_or_general_bundle(self):
        self.assertIn('GetHapTokenInfo', c.TOKEN_SOURCE); self.assertIn('CLOCK_MONOTONIC', c.TOKEN_SOURCE)
        for forbidden in ('GrantPermission', 'RevokePermission', 'UpdatePermission', 'system_clock'):
            self.assertNotIn(forbidden, c.TOKEN_SOURCE)

    def write_wav(self, path, values):
        with wave.open(str(path), 'wb') as stream:
            stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed')); stream.writeframes(values.tobytes())

    def test_pcm_fixture_proves_only_content_progress_not_onset(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp); source = temp/'input.wav'; c.noise_wav(source, 1)
            values = c.audio_values(source); capture = temp/'observed-host-fixture.wav'
            self.write_wav(capture, array('h', [0]*400)+values[:70000]+array('h', [0]*400))
            result = c.audio_progress(source, capture)
            self.assertGreater(result['source_advance_frames'], 0)
            self.assertIsNone(result['output_onset_monotonic_ns']); self.assertFalse(result['synchronization_verified'])

    def test_silence_and_collapsed_channels_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp); source = temp/'input.wav'; c.noise_wav(source, 1); actual = temp/'host-fixture.wav'
            self.write_wav(actual, array('h', [0]*70000))
            with self.assertRaises(ValueError): c.audio_progress(source, actual)
            values = c.audio_values(source)[:70000]
            for i in range(0, len(values), 2): values[i+1] = values[i]
            self.write_wav(actual, values)
            with self.assertRaises(ValueError): c.audio_progress(source, actual)

    def test_focus_capture_retains_old_prefix_without_accepting_it_as_contender(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp); owner = temp/'owner.wav'; contender = temp/'contender.wav'
            c.noise_wav(owner, 1); c.noise_wav(contender, 1); capture = temp/'host-fixture.wav'
            self.write_wav(capture, c.audio_values(owner)[:12000]+c.audio_values(contender)[:70000])
            with self.assertRaises(ValueError): c.audio_progress(contender, capture)
            self.assertGreater(c.audio_progress(contender, capture, allow_prefix=True)['first_capture_frame'], 6000)

    def test_real_sdk_prepare_creates_three_source_only_projects(self):
        if not SDK.is_dir() or not EXPORT.is_file(): self.skipTest('actual SDK/source export absent, never use a fake SDK')
        with tempfile.TemporaryDirectory() as temp:
            path = c.prepare(Path(temp)/'new', SDK, EXPORT, seconds=1)
            value = c.validate_preparation(path)
            self.assertFalse(value['runtime_validated']); self.assertFalse(value['ledger_closed'])
            self.assertEqual(set(value['roles']), set(c.ROLES))
            for role in c.ROLES:
                project = Path(value['roles'][role]['project'])
                module = json.loads((project/'entry/src/main/module.json5').read_text())['module']
                self.assertEqual(module['deviceTypes'], ['default'])
                self.assertEqual([v['name'] for v in module['requestPermissions']], c.PERMISSIONS[role])
                self.assertEqual(module['abilities'][0].get('backgroundModes', []), ['audioPlayback'] if role == 'owner' else [])
                page = project/'entry/src/main/ets/pages/Index.ets'
                self.assertEqual(page.read_text(), c.derived_page(value['run_id'], role))
            page.write_text(page.read_text()+'\n// changed after preparation')
            with self.assertRaises(ValueError): c.validate_preparation(path)

    def test_existing_frozen_candidate_not_modified_by_derivation(self):
        before = c.descriptor(c.base.PAGE)
        c.derived_page(RUN, 'owner'); c.derived_page(RUN, 'denied')
        self.assertEqual(before, c.descriptor(c.base.PAGE))


if __name__ == '__main__': unittest.main()
