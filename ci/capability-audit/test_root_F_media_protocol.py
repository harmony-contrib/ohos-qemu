"""Root protocol regressions; controlled evidence is never device acceptance."""
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from batch_media_audio_haptic_verify import active_boundary_callbacks
from media_recorder_runtime import RecorderRuntime
from guest_process_identity import producer_shell
from audio_capture_contract import sha
from verify_audio_capture_results import verify_producer


class BoundaryCallbacks(unittest.TestCase):
    def test_periodic_loop_eos_is_retained_but_other_epochs_and_nonloop_end_fail(self):
        callback=dict(event='callback',api='AudioHapticPlayer.endOfStream',sequence=3,player_epoch=7)
        began=dict(sequence=8,player_epoch=7);started=dict(sequence=2,player_epoch=7)
        self.assertEqual(active_boundary_callbacks([callback],began,started,looping=True),[callback])
        with self.assertRaisesRegex(ValueError,'EOS preceded'):
            active_boundary_callbacks([callback],began,started,looping=False)
        with self.assertRaisesRegex(ValueError,'another player'):
            active_boundary_callbacks([{**callback,'player_epoch':6}],began,started,looping=True)
        with self.assertRaises(ValueError):
            active_boundary_callbacks([callback],{**began,'sequence':1},started,looping=True)


class RecorderProducerReceipt(unittest.TestCase):
    def test_actual_child_footer_is_recorded_and_nonzero_is_rejected_even_when_hdc_exits_zero(self):
        for guest_code in [0,1]:
            with self.subTest(guest_code=guest_code),tempfile.TemporaryDirectory() as folder:
                runtime=RecorderRuntime.__new__(RecorderRuntime)
                runtime.output=Path(folder);runtime.run='a'*32;runtime.uid=20010001;runtime.denied=False
                runtime.value={'files':{}};runtime.args=SimpleNamespace(hdc='/fixture/hdc',target='127.0.0.1:1')
                runtime.producer_exit_marker='__PCM_CHILD_EXIT_'+'b'*32+'__='
                runtime.producer_argv=['/fixture/hdc','-t',runtime.args.target,'shell',producer_shell('/data/local/tmp/qemu-mic-'+'c'*32,runtime.producer_exit_marker)]
                runtime.process=SimpleNamespace(wait=lambda timeout:0);runtime.producer_log=io.BytesIO()
                (runtime.output/'producer.log').write_text('{"event":"feeding"}\n\n'+runtime.producer_exit_marker+str(guest_code)+'\n')
                runtime.actual_shell=lambda *args:str(runtime.uid)+' 600 0'
                runtime.command=lambda argv,label:Path(argv[-1]).write_bytes(b'')
                runtime.token=lambda *args:0
                saved=[];runtime.save=lambda:saved.append(copy.deepcopy(runtime.value))
                if guest_code:
                    with self.assertRaisesRegex(ValueError,'PCM producer failed'):runtime.collect('/fixture/files/')
                else:
                    runtime.collect('/fixture/files/')
                self.assertEqual(runtime.value['producer']['host_exit_code'],0)
                self.assertEqual(runtime.value['producer']['guest_exit_code'],guest_code)
                self.assertEqual(runtime.value['producer']['guest_exit_marker'],runtime.producer_exit_marker)
                self.assertTrue(any(row.get('producer',{}).get('guest_exit_code')==guest_code for row in saved))


class CompleteProducerDrain(unittest.TestCase):
    def test_all_writes_are_insufficient_without_real_successful_drain_and_child_exit(self):
        remote='/data/local/tmp/qemu-mic-'+'c'*32;marker='__PCM_CHILD_EXIT_'+'d'*32+'__='
        feeding=dict(event='feeding',device='hw:CARD=QemuCapture,DEV=1,SUBDEV=0',rate=48000,channels=2,bytes=192000)
        drained=dict(event='drained',alsa_rc=0,status_rc=0,state=1,delay_frames=0,written_frames=960000)
        played=dict(event='played',frames=960000,rate=48000,channels=2,repeats=20,source_bytes=192000)
        pending=dict(event='drain_pending',alsa_rc=-11,state=5)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'producer.log'
            def check(rows,code=0):
                path.write_text(''.join(json.dumps(r)+'\n' for r in rows)+'\n'+marker+str(code)+'\n')
                verify_producer(dict(remote_root_directory=remote,producer=dict(log=str(path),log_sha256=sha(path),
                    host_exit_code=0,guest_exit_code=code,guest_exit_marker=marker,argv=['hdc','-t','HOST-fixture','shell',producer_shell(remote,marker)])))
            check([feeding,drained,played]);check([feeding,pending,drained,played])
            check([feeding,pending,{**drained,'alsa_rc':-11},played])
            check([feeding,{**pending,'alsa_rc':-4},{**drained,'alsa_rc':-4},played])
            for rows in [[feeding,played],[feeding,{**drained,'alsa_rc':-5},played],
                         [feeding,{**drained,'alsa_rc':-11},played],
                         [feeding,pending,{**drained,'status_rc':-5},played],
                         [feeding,pending,{**drained,'status_rc':False},played],
                         [feeding,pending,{**drained,'delay_frames':1},played],
                         [feeding,pending,{**drained,'state':5},played],
                         [feeding,pending,{**drained,'written_frames':959999},played],
                         [feeding,{**drained,'alsa_rc':False},played],[feeding,{**pending,'state':4},drained,played],
                         [feeding,pending,pending,drained,played],[feeding,dict(event='failed',stage='close'),played]]:
                with self.assertRaises(ValueError):check(rows)
            with self.assertRaises(ValueError):check([feeding,drained,played],1)

if __name__=='__main__':unittest.main()
