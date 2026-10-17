"""Revoke only our ordinary app's actual MIC token during its live public stream."""
import json
from pathlib import Path
import re
import secrets
import time

from audio_capture_runtime import CaptureRuntime, BUNDLE
from audio_capture_contract import sha
from batch_media_audio_capture_challenge import load_reference, phase_content
from guest_ui import GuestUi, NodeNotReady, LayoutNotReady

PROCESS_IDENTITY_SCRIPT = ('task_mic_app_pid=$(pidof ' + BUNDLE + '); '
    'case "$task_mic_app_pid" in ""|*[!0-9]*) exit 1;; esac; '
    'printf "%s " "$task_mic_app_pid"; '
    'awk \'{printf "%s ", $22}\' /proc/$task_mic_app_pid/stat; '
    'awk \'/^Uid:/{print $2}\' /proc/$task_mic_app_pid/status')


class RevokeRuntime(CaptureRuntime):
    def __init__(self, *args):
        super().__init__(*args)
        self.value.update(kind='active-microphone-revocation', revoke_runner_sha256=sha(Path(__file__)))
        self.control_names = []
        self.save()

    def process_identity(self, label):
        raw = self.actual_shell(PROCESS_IDENTITY_SCRIPT, label)
        fields = raw.split()
        if len(fields) != 3 or any(re.fullmatch('[0-9]+', v) is None for v in fields):
            raise ValueError('one real ordinary stream process required')
        pid, start, uid = map(int, fields)
        if min(pid, start) <= 0 or uid != self.uid:
            raise ValueError('actual microphone process UID differs')
        return {'pid': pid, 'starttime': start, 'uid': uid}, len(self.value['guest_shell_observations']) - 1

    def permission(self):
        ui = GuestUi(self.command, self.args.hdc, self.args.target, self.output / 'start-ui')
        deadline = time.monotonic() + 10
        while True:
            try:
                action = ui.click(BUNDLE, text='Start audio audit', label='start-ordinary-active-revocation')
                break
            except (NodeNotReady, LayoutNotReady):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        action['layout_sha256'] = sha(action['layout'])
        self.value['start_action'] = action
        super().permission()
        app_files = self.parent['ordinary_result_directory']
        prefix = app_files + 'audio-event-' + self.run
        ready_path = prefix + '-revoke-ready.json'
        deadline = time.monotonic() + 10
        while True:
            native_log = prefix + '-mode0-results.log'
            raw = self.actual_shell('if test -f ' + native_log + '; then cat ' + native_log + '; fi',
                                    'actual-live-revoke-readiness-completion')
            rows = []
            for line in raw.splitlines(keepends=True):
                if line.endswith('\n'):
                    rows.append(json.loads(line))
            completed = [r for r in rows if r.get('type') == 'event_ready' and r.get('action') == 'revoke']
            if len(completed) > 1:
                raise ValueError('duplicate live revocation readiness')
            if completed:
                ready = json.loads(self.actual_shell('cat ' + ready_path, 'completed-live-revoke-readiness'))
                if any(ready.get(k) != completed[0].get(k) for k in ('run_id', 'action', 'nonce', 'monotonic_ns')):
                    raise ValueError('native revocation readiness file differs from its completed log')
                break
            if time.monotonic() >= deadline:
                raise ValueError('actual live public microphone did not reach revoke handshake')
            time.sleep(0.05)
        if (ready.get('run_id') != self.run or ready.get('action') != 'revoke' or ready.get('uid') != self.uid or
                re.fullmatch('[0-9a-f]{32}', ready.get('nonce', '')) is None or
                ready.get('state_result') != 0 or ready.get('state') != 2 or ready.get('frames_result') != 0 or
                type(ready.get('frames')) is not int or ready['frames'] <= 0 or
                type(ready.get('copied_bytes')) is not int or ready['copied_bytes'] <= 0):
            raise ValueError('revocation requires an actual RUNNING microphone with captured PCM')
        checkpoint = self.output / 'before-revoke.pcm'
        remote = prefix + '-mode0-baseline.pcm'
        self.command([self.args.hdc, '-t', self.args.target, 'file', 'recv', remote, checkpoint], 'read-real-before-revoke-PCM')
        _, reference = load_reference(self.output / 'challenge/challenge.json', self.output / 'challenge/challenge.pcm', self.run)
        correlation = phase_content(checkpoint.read_bytes()[4800 * 4:-4800 * 4], reference)
        before, before_index = self.process_identity('live-ordinary-process-before-MIC-revoke')
        observation, token_binding = self.token_observation(self.uid, 'live-revoke', operation='revoke')
        if observation.get('result') != 0 or observation.get('before') != 0 or observation.get('after') != -1:
            raise ValueError('actual live MIC permission revocation did not commit')
        after, after_index = self.process_identity('same-live-ordinary-process-after-MIC-revoke')
        if before != after:
            raise ValueError('MIC revoke killed or replaced the actual app process')
        ack = prefix + '-revoke-ack'
        backing = ack + '.publish-' + secrets.token_hex(16)
        self.actual_shell('test ! -e ' + ack + ' && test ! -L ' + ack +
            ' && (set -C; umask 077; printf "%s\\n" ' + ready['nonce'] + ' > ' + backing +
            ') && chown ' + str(self.uid) + ':' + str(self.uid) + ' ' + backing +
            ' && chmod 0600 ' + backing + ' && ln ' + backing + ' ' + ack,
            'acknowledge-only-committed-live-revocation')
        self.control_names = [Path(p).name for p in (ack, backing)]
        self.value['revocation'] = {'ready': ready, 'token': observation, 'token_binding': token_binding,
            'process_before': before, 'process_after': after,
            'process_before_observation': before_index, 'process_after_observation': after_index,
            'checkpoint': {'path': str(checkpoint), 'sha256': sha(checkpoint)}, 'correlation': correlation,
            'ack_nonce': ready['nonce'], 'ack_files': self.control_names}
        self.save()

    def collect(self, app_files):
        private = self.output / 'private'
        private.mkdir(exist_ok=False)
        stem = 'audio-event-' + self.run + '-mode0'
        names = [stem + '-permission.json', stem + '.pcm', stem + '-baseline.pcm', *self.control_names]
        # Completion and cleanup are separate immutable files. Poll only our
        # nonce-scoped sequence, then retain every actual lifecycle record.
        deadline = time.monotonic() + 10
        while True:
            raw = self.actual_shell('find ' + app_files + ' -maxdepth 1 -type f -name "' + stem + '-background-*.json" | sort',
                                    'actual-revocation-foreground-lifecycle-records')
            records = raw.splitlines()
            for remote in records:
                name = remote.removeprefix(app_files)
                if not re.fullmatch(re.escape(stem) + '-background-[0-9]{3}\\.json', name):
                    raise ValueError('unexpected ordinary event lifecycle path')
            values = []
            for index, remote in enumerate(records):
                marker = '__REVOKE_JOURNAL_' + secrets.token_hex(16) + '__'
                text = self.actual_shell('cat ' + remote + ' && printf "%s" ' + marker,
                                         'actual-revocation-lifecycle')
                if not text.endswith(marker):
                    raise ValueError('actual revocation lifecycle transfer incomplete')
                text = text[:-len(marker)]
                try:
                    if not text.endswith('\n'):
                        raise ValueError('lifecycle record is still being written')
                    values.append(json.loads(text))
                except ValueError:
                    if index != len(records) - 1:
                        raise
                    # The newest immutable record can be visible between the
                    # ArkTS create and checked write/close. Its raw HDC read is
                    # retained by command(); only this final record may retry.
                    break
            if any(v.get('event') == 'native_finished' for v in values):
                break
            if time.monotonic() >= deadline:
                raise ValueError('ordinary native worker completion was not observed by its UIAbility')
            time.sleep(0.05)
        names += [r.removeprefix(app_files) for r in records]
        for name in names:
            remote, local = app_files + name, private / name
            raw = self.actual_shell('test -f ' + remote + ' && test ! -L ' + remote + ' && stat -c "%u %a %s" ' + remote,
                                    'actual-active-revoke-private-file-identity')
            uid, mode, size = map(int, raw.split())
            if uid != self.uid or ((name.endswith('.pcm') or name in self.control_names) and mode != 600) or not 0 < size <= 7680000:
                raise ValueError('active-revocation actual private file identity/size invalid')
            self.command([self.args.hdc, '-t', self.args.target, 'file', 'recv', remote, local], 'receive-actual-' + name)
            if local.stat().st_size != size:
                raise ValueError('actual revocation private file transfer truncated')
            self.value['files'][name] = {'path': str(local), 'sha256': sha(local), 'remote': remote,
                                        'uid': uid, 'mode': mode, 'bytes': size}
        if self.token(self.uid, 'after-capture') != -1:
            raise ValueError('ordinary microphone was regranted during active revocation')
        status = self.process.wait(timeout=35)
        self.producer_log.close()
        self.producer_log = None
        self.value['producer'] = {'argv': self.producer_argv, 'host_exit_code': status,
            'log': str(self.output / 'producer.log'), 'log_sha256': sha(self.output / 'producer.log')}
        if status:
            raise ValueError('real independent PCM producer failed during active revocation')
        self.value['status'] = 'captured_NOT_independently_verified'
        return self.save()
