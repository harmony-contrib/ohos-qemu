"""Exact installation/source-contract checks only; native runner is a separate explicit gate."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/player_framework/audio_haptic_lifecycle'
FIXTURE = Path(__file__).parent / 'fixtures/batch_media/audio_haptic_generation'
BASELINE = json.loads((FIXTURE / 'source_states.json').read_text())
spec = importlib.util.spec_from_file_location('audio_haptic_generation_install', COMPONENT / 'install.py')
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


def source_state(state):
    result = {}
    for name, entry in BASELINE['states'][state].items():
        data = gzip.decompress(base64.b64decode(entry['gzip_base64'])) if entry['gzip_base64'] is not None else None
        if install.digest(data) != entry['sha256']:
            raise ValueError('source fixture hash mismatch: ' + name)
        result[name] = data
    return result


def populate(root, state='upstream'):
    for name, data in source_state(state).items():
        target = root / BASELINE['project'] / name
        if data is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        elif target.exists():
            target.unlink()


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


class ExactComponent(unittest.TestCase):
    def test_all_complete_preimages_upgrade_and_repeat(self):
        for prior in ('upstream', 'b4', 'incarnation_v1', 'incarnation_race_v2', 'incarnation_e'):
            with self.subTest(prior=prior), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                populate(root, prior)
                self.assertEqual(install.state(root), prior)
                self.assertEqual(install.install(root), 'incarnation')
                self.assertEqual(install.snapshot(root), source_state('incarnation'))
                self.assertEqual(install.install(root), 'incarnation')
                self.assertEqual(install.snapshot(root), source_state('incarnation'))

    def test_all_five_partial_failures_roll_back_all_preimages(self):
        for prior in ('upstream', 'b4', 'incarnation_v1', 'incarnation_race_v2', 'incarnation_e'):
            for count in range(1, len(BASELINE['states']['incarnation']) + 1):
                with self.subTest(prior=prior, count=count), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    populate(root, prior)
                    def fail(name, actual):
                        if actual == count:
                            raise OSError('controlled host write failure')
                    with self.assertRaisesRegex(OSError, 'controlled'):
                        install.install(root, after_write=fail)
                    self.assertEqual(install.state(root), prior)
                    self.assertEqual(install.snapshot(root), source_state(prior))
                    self.assertFalse(list(root.rglob('.audio-haptic-*')))

    def test_foreign_edit_is_retained_and_incomplete_rollback_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); populate(root, 'b4')
            changed = []
            def interfere(name, count):
                target = root / BASELINE['project'] / name
                target.write_bytes(b'// independent writer\n')
                changed.append(target)
                raise OSError('controlled interference')
            with self.assertRaisesRegex(RuntimeError, 'incomplete rollback'):
                install.install(root, after_write=interfere)
            self.assertEqual(changed[0].read_bytes(), b'// independent writer\n')

    def test_no_mutation_on_unknown_mixed_missing_or_symlink(self):
        for variant in ('unknown','mixed_b4','mixed_candidate','missing','file_symlink','parent_symlink','unexpected_header'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); populate(root)
                names=list(BASELINE['states']['upstream']); name=names[0]
                target=root / BASELINE['project'] / name
                if variant=='unknown': target.write_bytes(target.read_bytes()+b'// foreign\n')
                elif variant=='mixed_b4': target.write_bytes(source_state('b4')[name])
                elif variant=='mixed_candidate': target.write_bytes(source_state('incarnation')[name])
                elif variant=='missing': target.unlink()
                elif variant=='file_symlink':
                    saved=root/'saved'; target.rename(saved); target.symlink_to(saved)
                elif variant=='parent_symlink':
                    parent=target.parent; saved=root/'saved'; parent.rename(saved); parent.symlink_to(saved)
                elif variant=='unexpected_header':
                    (target.parent/'audio_haptic_playback_session.h').write_bytes(b'// foreign\n')
                before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                with self.assertRaises(ValueError): install.install(root)
                after={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(before,after)
                self.assertFalse((root/'.ohos-qemu-patches').exists())

    def test_preexisting_mode_preserved_and_new_header_644(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);populate(root,'b4')
            for name,data in source_state('b4').items():
                if data is not None: (root/BASELINE['project']/name).chmod(0o640)
            install.install(root)
            for name,data in source_state('b4').items():
                self.assertEqual((root/BASELINE['project']/name).stat().st_mode&0o777,0o640 if data is not None else 0o644)

    def test_require_patched_rejects_both_preimages(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for prior in ('upstream','b4','incarnation_v1','incarnation_race_v2','incarnation_e'):
                populate(root,prior)
                with self.assertRaises(ValueError): install.state(root,True)


class SourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source={Path(name).name:data.decode() for name,data in source_state('incarnation').items()}

    def test_real_dependency_headers_and_full_cpp_harness_are_hash_bound(self):
        provenance=json.loads((FIXTURE/'provenance.json').read_text())
        for entry in provenance['real_headers']:
            self.assertEqual(hashlib.sha256((FIXTURE/entry['fixture']).read_bytes()).hexdigest(),entry['sha256'])
        harness=(FIXTURE/'native_harness.cpp').read_text()
        self.assertNotIn('class AudioHapticPlayerImpl {',harness)
        self.assertNotIn('class AudioHapticSoundNormalImpl {',harness)
        self.assertIn('#include "audio_haptic_player_impl.h"',harness)
        self.assertIn('#include "audio_haptic_sound_normal_impl.h"',harness)
        runner=(Path(__file__).parent/'batch_media_audio_haptic_generation_native.py').read_text()
        for name in ('audio_haptic_sound_normal_impl.cpp','audio_haptic_player_impl.cpp','-fno-rtti'):
            self.assertIn(name,runner)
        self.assertNotIn('ACTUAL_FUNCTIONS',runner)

    def test_no_reset_of_fresh_idle_and_callback_bound_once_at_creation(self):
        normal=self.source['audio_haptic_sound_normal_impl.cpp']
        self.assertNotIn('->Reset(',normal)
        load=function(normal,'int32_t AudioHapticSoundNormalImpl::LoadAVPlayer()')
        self.assertIn('PlayerFactory::CreatePlayer()',load)
        self.assertIn('AudioHapticPlaybackSession>(backend)',load)
        self.assertIn('AHSoundNormalCallback>(shared_from_this(), session)',load)
        self.assertEqual(normal.count('->SetPlayerCallback('),1)
        callback=self.source['audio_haptic_sound_normal_impl.h']
        self.assertIn('const std::shared_ptr<AudioHapticPlaybackSession> session_;',callback)
        for event in ('NotifyErrorEvent(session_,','NotifyFirstFrameEvent(session_,','NotifyInterruptEvent(session_,','NotifyEndOfStreamEvent(session_,'):
            self.assertIn(event,normal)

    def test_state_callback_uses_only_immutable_initial_and_per_event_local(self):
        header=self.source['audio_haptic_sound_normal_impl.h']
        self.assertIn('std::atomic<AudioHapticPlayerState> playerState_',header)
        self.assertIn('const AudioHapticPlayerState playerState_',header)
        body=function(self.source['audio_haptic_sound_normal_impl.cpp'], 'void AHSoundNormalCallback::HandleStateChangeEvent(')
        self.assertIn('AudioHapticPlayerState eventState = playerState_',body)
        self.assertNotIn('playerState_ =',body)
        self.assertIn('SetAVPlayerState(session_, eventState)',body)
        self.assertIn('default:\n            return;',body)

    def test_player_state_and_haptics_mode_cross_thread_reads_are_atomic(self):
        header=self.source['audio_haptic_player_impl.h']
        self.assertIn('std::atomic<AudioHapticPlayerState> playerState_',header)
        self.assertIn('std::atomic<HapticsMode> hapticsMode_',header)
        self.assertNotIn('    AudioHapticPlayerState playerState_',header)
        self.assertNotIn('    HapticsMode hapticsMode_',header)

    def test_source_derived_old_callback_interleave_counterexample(self):
        previous=source_state('incarnation_v1')['frameworks/native/audio_haptic/audio_haptic_sound_normal_impl.cpp'].decode()
        old=function(previous,'void AHSoundNormalCallback::HandleStateChangeEvent(')
        current=function(self.source['audio_haptic_sound_normal_impl.cpp'],'void AHSoundNormalCallback::HandleStateChangeEvent(')
        self.assertIn('playerState_ = AudioHapticPlayerState::STATE_PREPARED',old)
        self.assertIn('playerState_ = AudioHapticPlayerState::STATE_RUNNING',old)
        self.assertIn('SetAVPlayerState(session_, playerState_)',old)
        self.assertIn('eventState = AudioHapticPlayerState::STATE_PREPARED',current)
        self.assertIn('eventState = AudioHapticPlayerState::STATE_RUNNING',current)
        # Source-derived A maps PREPARED, B maps RUNNING, A forwards: old shared state changes A's result.
        shared='STATE_PREPARED'; event_a='STATE_PREPARED'
        shared='STATE_RUNNING'; event_b='STATE_RUNNING'
        self.assertEqual(shared,event_b)
        self.assertNotEqual(shared,event_a)
        self.assertEqual(event_a,'STATE_PREPARED')
        # This is a lightweight source/schedule counterexample, not execution of production C++.

    def test_sound_publication_writes_pair_with_lock_free_of_api_time_snapshot(self):
        source=self.source['audio_haptic_player_impl.cpp']
        time=function(source,'int32_t AudioHapticPlayerImpl::GetAudioCurrentTime()')
        self.assertIn('std::atomic_load(&audioHapticSound_)',time)
        self.assertNotIn('lock(audioHapticPlayerLock_)',time)
        self.assertIn('return sound->GetAudioCurrentTime()',time)
        load=function(source,'void AudioHapticPlayerImpl::LoadPlayer()')
        self.assertIn('lock(audioHapticPlayerLock_)',load)
        self.assertIn('previousSound = std::atomic_exchange(&audioHapticSound_, sound)',load)
        self.assertIn('previousSound.reset()',load)
        release=function(source,'void AudioHapticPlayerImpl::ReleaseSound()')
        self.assertLess(release.index('std::atomic_exchange'),release.index('sound->ReleaseSound()'))
        self.assertEqual(source.count('std::atomic_exchange(&audioHapticSound_,'),2)
        self.assertNotRegex(source,r'\baudioHapticSound_\s*=(?!=)')

    def test_sound_plain_read_functions_hold_the_shared_writer_api_mutex(self):
        source=self.source['audio_haptic_player_impl.cpp']
        for name in ('Prepare','Start','Stop','Release','SetVolume','SetLoop'):
            body=function(source,'int32_t AudioHapticPlayerImpl::'+name+'(')
            self.assertIn('lock(audioHapticPlayerLock_)',body)
            self.assertLess(body.index('lock(audioHapticPlayerLock_)'),body.index('audioHapticSound_'))
        load=function(source,'void AudioHapticPlayerImpl::LoadPlayer()')
        self.assertNotIn('audioHapticSound_->',load)

    def test_no_rtti_or_delivery_time_generation(self):
        joined='\n'.join(self.source.values())
        for forbidden in ('dynamic_pointer_cast','dynamic_cast<','currentEpoch','currentGeneration'):
            self.assertNotIn(forbidden,joined)
        self.assertIn('const std::weak_ptr<Player> backend;',self.source['audio_haptic_playback_session.h'])

    def test_rearm_after_prepare_and_identity_rechecked_under_wait_lock(self):
        player=self.source['audio_haptic_player_impl.cpp']
        start=function(player,'int32_t AudioHapticPlayerImpl::Start()')
        self.assertLess(start.index('PrepareForStart()'),start.index('ResetVibrateState()'))
        first=function(player,'void AudioHapticPlayerImpl::PlaybackFirstFrame(')
        self.assertLess(first.index('lockWait(waitStartVibrateMutex_)'),first.index('normalPlaybackSession_ == session'))
        self.assertIn('session->playConfirmed.load()',first)
        self.assertIn('!isVibrationStopped_.load()',first)
        for suffix in ('EndOfStream','Interrupt'):
            worker=function(player,'void AudioHapticPlayerImpl::HandlePlayback'+suffix+'(')
            self.assertIn('normalPlaybackSession_ == session',worker)
            self.assertIn('session->end.load()',worker)
        self.assertIn('[player = weak_from_this(), session, isLoop]',player)
        self.assertIn('[player = weak_from_this(), session, event]',player)

    def test_source_fd_pinned_and_close_is_final(self):
        normal=self.source['audio_haptic_sound_normal_impl.cpp']
        opening=function(normal,'int32_t AudioHapticSoundNormalImpl::OpenAudioSource()')
        self.assertIn('audioSource_ != pinnedAudioSource_',opening)
        self.assertIn('pinnedAudioSource_ = audioSource_',opening)
        self.assertIn('SetSource(fileDes_, pinnedAudioSource_.offset, pinnedAudioSource_.length)',normal)
        backend=function(normal,'void AudioHapticSoundNormalImpl::ReleaseBackend(')
        self.assertNotIn('close(',backend)
        self.assertIn('close(fileDes_)',function(normal,'void AudioHapticSoundNormalImpl::ReleaseAVPlayer()'))

    def test_retirement_no_source_event_can_resurrect_explicit_stop(self):
        normal=self.source['audio_haptic_sound_normal_impl.cpp']
        for suffix in ('ErrorEvent','InterruptEvent','EndOfStreamEvent'):
            event=function(normal,'void AudioHapticSoundNormalImpl::Notify'+suffix+'(const std::shared_ptr<')
            self.assertIn('compare_exchange_strong',event)
            self.assertNotIn('end.store(',event)
        err=function(normal,'void AudioHapticSoundNormalImpl::NotifyErrorEvent(const std::shared_ptr<')
        self.assertIn('Explicit retirement won before error admission',err)
        eos=function(normal,'void AudioHapticSoundNormalImpl::NotifyEndOfStreamEvent(const std::shared_ptr<')
        self.assertLess(eos.index('if (!isLoop)'),eos.index('AudioHapticSessionEnd::ENDED'))

    def test_time_query_uses_backend_snapshot_without_wait_api_inversion(self):
        body=function(self.source['audio_haptic_sound_normal_impl.cpp'], 'int32_t AudioHapticSoundNormalImpl::GetAudioCurrentTime()')
        self.assertIn('playbackSession_->backend.lock()',body)
        self.assertNotIn('lock(audioHapticPlayerLock_)',body)
        self.assertIn('backend->GetCurrentTime(currentTime)',body)

    def test_fd_lifetime_counterexample_uses_real_os_dup_unlink(self):
        # A real OS prerequisite check, not a C++ execution or decoder acceptance claim.
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'owned-source';path.write_bytes(b'0123456789')
            original=os.open(path,os.O_RDONLY);pinned=os.dup(original)
            try:
                os.close(original);path.unlink()
                for unused in range(3):
                    backend_fd=os.dup(pinned)
                    try: self.assertEqual(os.pread(backend_fd,4,2),b'2345')
                    finally: os.close(backend_fd)
            finally: os.close(pinned)


if __name__=='__main__':
    unittest.main(verbosity=2)
