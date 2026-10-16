"""Owned external PCM and challenged Surface input for a real ordinary Recorder."""
import json
from pathlib import Path

from audio_capture_runtime import CaptureRuntime
from audio_capture_contract import sha
from batch_media_recorder_challenge import generate


class RecorderRuntime(CaptureRuntime):
    def __init__(self, *args):
        super().__init__(*args)
        self.denied = getattr(self.args, 'media_recorder_expect_denied', False)
        self.value.update(expected_denied=self.denied, kind='recorder', recorder_runner_sha256=sha(Path(__file__)))
        self.save()

    def generate_challenge(self):
        generate(self.output / 'challenge', self.run)

    def before_launch(self, uid):
        super().before_launch(uid)
        app_files = self.parent['ordinary_result_directory']
        if app_files != '/data/app/el2/100/base/org.harmonycontrib.capabilityaudit/files/':
            raise ValueError('exact ordinary Recorder private directory required')
        self.actual_shell('mkdir -p ' + app_files + ' && chown ' + str(uid) + ':' + str(uid) + ' ' + app_files +
                          ' && chmod 0700 ' + app_files, 'prepare-ordinary-Recorder-video-input-directory')
        name = 'recorder-' + self.run + '-video.bin'
        local, remote = self.output / 'challenge' / name, app_files + name
        self.actual_shell('test ! -e ' + remote, 'fresh-Recorder-video-input-absent')
        self.command([self.args.hdc, '-t', self.args.target, 'file', 'send', local, remote], 'send-Recorder-Surface-input')
        self.actual_shell('chown ' + str(uid) + ':' + str(uid) + ' ' + remote + ' && chmod 0600 ' + remote +
                          ' && test "$(sha256sum ' + remote + ' | cut -d " " -f 1)" = ' + sha(local),
                          'verify-private-Recorder-Surface-input')
        self.value['video_input'] = {'path': str(local), 'sha256': sha(local), 'remote': remote, 'uid': uid, 'mode': 600}
        self.save()

    def collect(self, app_files):
        private = self.output / 'private'
        private.mkdir(exist_ok=False)
        names = ['recorder-' + self.run + '-permission.json'] + [
            'recorder-' + self.run + '-cycle' + str(cycle) + '.mp4' for cycle in (1, 2)]
        for name in names:
            remote = app_files + name
            raw = self.actual_shell('test -f ' + remote + ' && test ! -L ' + remote +
                                    ' && stat -c "%u %a %s" ' + remote, 'Recorder-private-file-owner-mode-size')
            uid, mode, size = map(int, raw.split())
            if uid != self.uid or (name.endswith('.mp4') and mode != 600) or not 0 <= size <= 16 * 1024 * 1024:
                raise ValueError('actual private Recorder file identity/size invalid')
            local = private / name
            self.command([self.args.hdc, '-t', self.args.target, 'file', 'recv', remote, local], 'receive-private-' + name)
            if local.stat().st_size != size: raise ValueError('Recorder file transfer truncated')
            self.value['files'][name] = {'path': str(local), 'sha256': sha(local), 'remote': remote,
                                         'uid': uid, 'mode': mode, 'bytes': size}
        if self.token(self.uid, 'after-capture') != (-1 if self.denied else 0):
            raise ValueError('actual Recorder MIC permission changed during lifecycle')
        if self.process is not None:
            status = self.process.wait(timeout=35)
            self.producer_log.close()
            self.producer_log = None
            self.value['producer'] = {'argv': self.producer_argv, 'host_exit_code': status,
                'log': str(self.output / 'producer.log'), 'log_sha256': sha(self.output / 'producer.log')}
            if status: raise ValueError('actual Recorder independent PCM producer failed')
        self.value['status'] = 'captured_NOT_independently_verified'
        self.save()
        return self.output / 'runtime.json'
