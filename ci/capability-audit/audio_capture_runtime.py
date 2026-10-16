"""Owned root producer and real permission UI for the ordinary microphone caller."""
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time

from audio_capture_contract import sha, runtime_identity
from audio_capture_permission import decide
from batch_media_audio_capture_challenge import generate
from guest_ui import GuestUi
from spring_loading_input import binding

HERE = Path(__file__).resolve().parent
BUNDLE = 'org.harmonycontrib.capabilityaudit'


class CaptureRuntime:
    def __init__(self, args, command, shell, report, run, boot_id):
        self.args, self.command, self.shell, self.parent = args, command, shell, report
        self.run, self.boot_id = run, boot_id
        self.denied = getattr(args, 'audio_capture_expect_denied', False)
        self.output = args.output / 'capture'
        self.output.mkdir(exist_ok=False)
        boot = json.loads(Path(args.boot).read_text())
        binding(boot, report['archive_sha256'], boot_id, args.arch, args.device, args.target)
        self.remote = '/data/local/tmp/qemu-mic-' + run
        self.process = None
        self.producer_log = None
        self.started = False
        self.finished = False
        self.value = {'schema_version': 1, 'status': 'fail', 'run_id': run, 'boot_id': boot_id,
            'archive_sha256': report['archive_sha256'], 'arch': args.arch, 'device': args.device,
            'target': args.target, 'expected_denied': self.denied, 'remote_root_directory': self.remote,
            'runner_sha256': sha(Path(__file__)), 'tokens': [], 'files': {},
            'first_artifact_behavior_gate_passed': False}
        saved = self.output / 'acceptance-boot.json'
        saved.write_text(json.dumps(boot, indent=2) + '\n')
        self.value.update(boot=str(saved), boot_sha256=sha(saved))
        self.save()

    def save(self):
        path = self.output / 'runtime.json'
        path.write_text(json.dumps(self.value, indent=2) + '\n')
        return path

    def actual_shell(self, script, label):
        # HDC may return host success for a failed guest command. Preserve an
        # unpredictable remote exit marker for every behavioral operation.
        import secrets
        import re
        marker = '__MIC_EXIT_' + secrets.token_hex(16) + '__='
        text = self.shell(script + '; task_mic_rc=$?; printf "\\n' + marker + '%s\\n" "$task_mic_rc"', label)
        match = re.search(r'(?:^|\n)' + marker + r'(\d+)\s*$', text)
        if not match or match.group(1) != '0':
            raise ValueError('real microphone setup/observation command failed: ' + label)
        return text[:match.start()].rstrip('\n')

    def prepare(self):
        tools = self.output / 'tools'
        self.command(['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
            '--read-only', '--cpus', '2', '--memory', '5g', '--pids-limit', '512',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=512m',
            '--mount', 'type=volume,src=' + self.args.source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=volume,src=' + getattr(self.args, 'out_volume', 'ohos-qemu-7_0-release-out') + ',dst=/ohos/out,readonly',
            '--mount', 'type=bind,src=' + str(HERE.parents[1]) + ',dst=/work,readonly',
            '--mount', 'type=bind,src=' + str(self.args.output.resolve()) + ',dst=/probe',
            self.args.docker_image, 'python3', '/work/ci/capability-audit/build_audio_capture_tools.py',
            '--source-root', '/ohos', '--arch', self.args.arch, '--output', '/probe/capture/tools'],
            'build-current-real-PCM-and-token-tools', timeout=420)
        build = json.loads((tools / 'build.json').read_text())
        if build.get('status') != 'pass' or build.get('arch') != self.args.arch:
            raise ValueError('real microphone orchestration tools did not compile/link')
        for name in ('alsa_inject', 'audio_capture_token'):
            if sha(tools / name) != build['tools'][name]['binary_sha256']:
                raise ValueError('actual microphone tool changed')
        self.value.update(tools=str(tools / 'build.json'), tools_sha256=sha(tools / 'build.json'))
        self.value['guest_libraries'] = {}
        for name, library in (('alsa_inject', 'libasound.so'), ('audio_capture_token', 'libaccesstoken_sdk.z.so')):
            local = self.output / library
            remote = '/system/' + ('lib' if self.args.arch == 'armv7a' else 'lib64') + '/' + library
            self.command([self.args.hdc, '-t', self.args.target, 'file', 'recv', remote, local],
                         'read-actual-package-library-' + name)
            identity = runtime_identity(local.read_bytes(), self.args.arch)
            if identity != build['tools'][name]['linked_library_runtime_sha256']:
                raise ValueError('root tool was linked against another artifact library: ' + library)
            self.value['guest_libraries'][name] = {'remote': remote, 'path': str(local), 'sha256': sha(local),
                                                  'runtime_sha256': identity}
        label_text = self.command(['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
            '--read-only', '--cpus', '1', '--memory', '512m',
            '--mount', 'type=volume,src=' + self.args.source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=bind,src=' + str(HERE.parents[1]) + ',dst=/work,readonly',
            self.args.docker_image, 'python3', '/work/ci/capability-audit/audio_capture_permission.py',
            '--source-root', '/ohos'], 'read-actual-microphone-dialog-resources', timeout=120)
        self.labels = json.loads(label_text)
        label_path = self.output / 'permission-labels.json'
        label_path.write_text(json.dumps(self.labels, ensure_ascii=False, indent=2) + '\n')
        self.value.update(labels=str(label_path), labels_sha256=sha(label_path))
        generate(self.output / 'challenge', self.run)
        self.actual_shell('test ! -e ' + self.remote + ' && mkdir -m 0700 ' + self.remote,
                          'create-owned-root-microphone-directory')
        self.started = True
        for local, name in ((tools / 'alsa_inject', 'alsa_inject'), (tools / 'audio_capture_token', 'audio_capture_token'),
                            (self.output / 'challenge/challenge.pcm', 'challenge.pcm')):
            self.command([self.args.hdc, '-t', self.args.target, 'file', 'send', local, self.remote + '/' + name],
                         'send-root-only-' + name)
            self.actual_shell('chmod ' + ('0600' if name.endswith('.pcm') else '0700') + ' ' + self.remote + '/' + name +
                              ' && test "$(sha256sum ' + self.remote + '/' + name + ' | cut -d " " -f 1)" = ' + sha(local),
                              'verify-root-only-' + name)
        hardware = self.actual_shell('cat /proc/asound/cards && cat /proc/asound/pcm', 'actual-loopback-ALSA-hardware')
        hardware_path = self.output / 'asound.txt'
        hardware_path.write_text(hardware)
        self.value.update(asound=str(hardware_path), asound_sha256=sha(hardware_path))
        self.save()

    def token(self, uid, phase):
        result = json.loads(self.actual_shell(f'{self.remote}/audio_capture_token {self.run} {uid} query',
                                              'independent-MIC-token-' + phase))
        if (result.get('uid') != uid or result.get('run_id') != self.run or result.get('result') != 0 or
                result.get('operation') != 'query' or result.get('before') != result.get('after')):
            raise ValueError('independent actual AccessToken query does not match the ordinary caller')
        self.value['tokens'].append({'phase': phase, 'observation': result})
        self.save()
        return result['after']

    def before_launch(self, uid):
        self.uid = uid
        if self.token(uid, 'before-launch') != -1:
            raise ValueError('fresh ordinary microphone app was unexpectedly pregranted')

    def permission(self):
        # Feed the independent source before allowing the ordinary app to start
        # Capturer. The application cannot traverse this root-only directory.
        if not self.denied:
            wrapper = ('echo "$$" > ' + self.remote + '/producer.pid; '
                'awk \'{print $22}\' /proc/$$/stat > ' + self.remote + '/producer.start; '
                'exec ' + self.remote + '/alsa_inject --input ' + self.remote +
                '/challenge.pcm --rate 48000 --channels 2 --repeat 20 --timeout-ms 30000')
            argv = [str(self.args.hdc), '-t', self.args.target, 'shell', 'sh -c ' + shlex.quote(wrapper)]
            self.producer_log = (self.output / 'producer.log').open('xb')
            self.producer_argv = argv
            self.process = subprocess.Popen(argv, stdout=self.producer_log, stderr=subprocess.STDOUT,
                                            stdin=subprocess.DEVNULL, start_new_session=True)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                # A readable feeding record is emitted only after real exact
                # ALSA format negotiation. No content match is inferred here.
                text = (self.output / 'producer.log').read_text(errors='replace')
                if '"event":"feeding"' in text:
                    break
                if self.process.poll() is not None:
                    raise ValueError('actual root PCM producer exited before microphone capture')
                time.sleep(0.1)
            else:
                raise ValueError('actual ALSA producer did not negotiate the capture cable')
        ui = GuestUi(self.command, self.args.hdc, self.args.target, self.output / 'ui')
        self.value['permission_action'] = decide(ui, self.labels, self.denied, min(self.args.wait_seconds, 120))
        # requestPermissionsFromUser and the independent service query may cross
        # once. Wait only for the actual decision to be committed, never grant.
        deadline = time.monotonic() + 10
        while self.token(self.uid, 'after-dialog') != (-1 if self.denied else 0):
            if time.monotonic() >= deadline:
                raise ValueError('actual AccessToken does not reflect the real microphone dialog decision')
            time.sleep(0.1)
        self.save()

    def collect(self, app_files):
        destination = self.output / 'private'
        destination.mkdir(exist_ok=False)
        names = ['audio-capture-' + self.run + '-permission.json']
        names += [f'audio-capture-{self.run}-cycle{cycle}.pcm' for cycle in (1, 2)]
        for name in names:
            remote = app_files + name
            present = self.actual_shell('if test -e ' + remote + '; then echo PRESENT; else echo ABSENT; fi', 'private-file-existence')
            if present == 'ABSENT' and self.denied and name.endswith('.pcm'):
                self.value['files'][name] = {'absent': True}
                continue
            if present != 'PRESENT':
                raise ValueError('actual private microphone evidence missing: ' + name)
            stat = self.actual_shell('test -f ' + remote + ' && test ! -L ' + remote +
                ' && stat -c "%u %a %s" ' + remote, 'private-file-real-owner-mode-size')
            uid, mode, size = map(int, stat.split())
            # ArkTS permission JSON follows the runtime's default file mode;
            # raw microphone samples must always be private mode 0600.
            if uid != self.uid or (name.endswith('.pcm') and mode != 600) or size < 0 or size > 1536000:
                raise ValueError('actual private microphone file owner/mode/size invalid')
            self.command([self.args.hdc, '-t', self.args.target, 'file', 'recv', remote, destination / name], 'receive-private-' + name)
            if (destination / name).stat().st_size != size:
                raise ValueError('microphone file transfer truncated actual data')
            self.value['files'][name] = {'path': str(destination / name), 'sha256': sha(destination / name),
                'remote': remote, 'uid': uid, 'mode': mode, 'bytes': size}
        if self.token(self.uid, 'after-capture') != (-1 if self.denied else 0):
            raise ValueError('ordinary microphone token changed during the lifecycle test')
        if self.process is not None:
            try:
                status = self.process.wait(timeout=35)
            except subprocess.TimeoutExpired:
                raise ValueError('actual root producer did not complete within its native deadline')
            self.producer_log.close()
            self.producer_log = None
            self.value['producer'] = {'argv': self.producer_argv, 'host_exit_code': status,
                'log': str(self.output / 'producer.log'), 'log_sha256': sha(self.output / 'producer.log')}
            if status != 0:
                raise ValueError('actual root PCM producer failed')
        self.value['status'] = 'captured_NOT_independently_verified'
        self.save()
        return self.output / 'runtime.json'

    def close(self):
        errors = []
        if self.started:
            try:
                # Signal only our current executable and recorded kernel
                # starttime. A reused PID or changed executable is never killed.
                script = ('if test -e ' + self.remote + '/producer.pid; then '
                    'task_mic_pid=$(cat ' + self.remote + '/producer.pid); '
                    'case "$task_mic_pid" in ""|*[!0-9]*) exit 1;; esac; '
                    'if test -d /proc/$task_mic_pid; then '
                    'test "$(readlink /proc/$task_mic_pid/exe)" = ' + self.remote + '/alsa_inject && '
                    'test "$(awk \'{print $22}\' /proc/$task_mic_pid/stat)" = "$(cat ' + self.remote + '/producer.start)" && '
                    'kill -TERM "$task_mic_pid"; fi; fi')
                self.actual_shell(script, 'cleanup-only-owned-PCM-producer')
            except Exception as error:
                errors.append(str(error))
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=3)
                    errors.append('owned producer HDC did not terminate after actual guest cleanup')
        if self.producer_log is not None:
            self.producer_log.close()
            self.producer_log = None
        self.value['cleanup_errors'] = errors
        self.finished = not errors
        self.save()
        if errors:
            raise ValueError('owned microphone producer cleanup failed: ' + '; '.join(errors))
