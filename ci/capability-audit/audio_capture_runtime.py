"""Owned root producer and real permission UI for the ordinary microphone caller."""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import secrets
import subprocess
import time

from audio_capture_contract import sha, runtime_identity
from audio_capture_permission import decide
from batch_media_audio_capture_challenge import generate
from guest_ui import GuestUi
import batch_system_build_runtime_helpers as product
from build_audio_capture_tools import verify_installed_tools
from spring_loading_input import binding
from hap_identity_binding import bms_application_identity, strict_json, verify_hap_token_identity
from guest_process_identity import producer_shell, producer_exit_code, cleanup_producer_shell

HERE = Path(__file__).resolve().parent
BUNDLE = 'org.harmonycontrib.capabilityaudit'
BOOT_SCRIPT = 'cat /proc/sys/kernel/random/boot_id'


class CleanupBootError(ValueError):
    """Original guest identity was lost; cleanup must not recover by re-querying."""


def cleanup_boot_prefix(boot_id):
    if re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', boot_id or '') is None:
        raise ValueError('original kernel boot ID is required for guest cleanup')
    return ('task_mic_cleanup_boot=$(' + BOOT_SCRIPT + ') && '
        'test "$task_mic_cleanup_boot" = ' + shlex.quote(boot_id) + ' || exit 1; ')


def require_cleanup_boot(shell, boot_id, label):
    try:
        cleanup_boot_prefix(boot_id)
        actual = shell(BOOT_SCRIPT, label).strip()
    except Exception as error:
        raise CleanupBootError('owned audio cleanup cannot confirm original guest kernel: ' + str(error)) from error
    if actual != boot_id:
        raise CleanupBootError('owned audio cleanup refused a different guest kernel')
    return actual


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
        self.producer_exit_marker = None
        self.started = False
        self.finished = False
        hdc_argv0 = str(args.hdc)
        hdc_path = shutil.which(hdc_argv0)
        if hdc_path is None: raise ValueError('actual configured HDC executable is missing')
        hdc_path = Path(hdc_path).resolve()
        if not hdc_path.is_file(): raise ValueError('actual HDC canonical file is missing')
        self.value = {'schema_version': 1, 'status': 'fail', 'run_id': run, 'boot_id': boot_id,
            'parent_persona': report['persona'],
            'archive_sha256': report['archive_sha256'], 'arch': args.arch, 'device': args.device,
            'target': args.target, 'expected_denied': self.denied, 'remote_root_directory': self.remote,
            'runner_sha256': sha(Path(__file__)),
            'process_identity_helper_sha256': sha(HERE / 'guest_process_identity.py'), 'tokens': [], 'files': {},
            'first_artifact_behavior_gate_passed': False,
            'hdc': {'path': str(hdc_path), 'sha256': sha(hdc_path), 'argv0': hdc_argv0}}
        saved = self.output / 'acceptance-boot.json'
        saved.write_text(json.dumps(boot, indent=2) + '\n')
        self.value.update(boot=str(saved), boot_sha256=sha(saved))
        self.save()

    def save(self):
        if hasattr(self, 'parent'):
            self.value['orchestration_commands'] = self.parent['commands']
        path = self.output / 'runtime.json'
        path.write_text(json.dumps(self.value, indent=2) + '\n')
        return path

    def actual_shell(self, script, label):
        # HDC may return host success for a failed guest command. Preserve an
        # unpredictable remote exit marker for every behavioral operation.
        import secrets
        import re
        marker = '__MIC_EXIT_' + secrets.token_hex(16) + '__='
        command_index = len(self.parent['commands']) if hasattr(self, 'parent') else None
        text = self.shell(script + '; task_mic_rc=$?; printf "\\n' + marker + '%s\\n" "$task_mic_rc"', label)
        match = re.search(r'(?:^|\n)' + marker + r'(\d+)\s*$', text)
        if hasattr(self, 'value'):
            self.value.setdefault('guest_shell_observations', []).append(dict(script=script, label=label,
                exit_marker=marker, command_index=command_index, raw=text,
                guest_exit_code=int(match.group(1)) if match else None))
            self.save()
        if not match or match.group(1) != '0':
            raise ValueError('real microphone setup/observation command failed: ' + label)
        return text[:match.start()].rstrip('\n')

    def generate_challenge(self):
        generate(self.output / 'challenge', self.run)

    def reuse_tools(self, tools, profile_value):
        """Copy a verified actual build without rewriting its historical receipt."""
        source = os.environ.get('OHOS_QA_MIC_TOOLS_BUILD')
        digest = os.environ.get('OHOS_QA_MIC_TOOLS_BUILD_SHA256')
        if source is None and digest is None: return False
        if not source or not re.fullmatch(r'[0-9a-f]{64}', digest or ''):
            raise ValueError('both explicit MIC tools build receipt and SHA256 required; no compile fallback')
        path = Path(source)
        if (not path.is_absolute() or path.name != 'build.json' or path.is_symlink() or
                not path.is_file() or path.resolve() != path or sha(path) != digest):
            raise ValueError('canonical regular actual MIC tools build receipt/SHA256 differs')
        if tools.resolve().is_relative_to(path.parent) or path.parent.is_relative_to(tools.resolve()):
            raise ValueError('actual MIC tools source and case output must be separate directories')
        build = verify_installed_tools(path, self.args.arch)
        if any(row['installed_runtime_profile']['profile'] != profile_value for row in build['tools'].values()):
            raise ValueError('prebuilt actual MIC tools installed runtime profile differs from current profile')
        for entry in path.parent.rglob('*'):
            if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
                raise ValueError('actual MIC tools directory contains a symlink or nonregular entry')
        shutil.copytree(path.parent, tools)
        copied = tools / 'build.json'
        if sha(path) != digest or sha(copied) != digest:
            raise ValueError('actual MIC tools build receipt changed during copy')
        if verify_installed_tools(copied, self.args.arch) != build:
            raise ValueError('copied actual MIC tools replay differs from original')
        self.value['prebuilt_tools_build_input'] = {'path': str(path), 'sha256': digest}
        self.save()
        return True

    def prepare(self):
        tools = self.output / 'tools'
        profile = getattr(self.args, 'runtime_profile', None) or os.environ.get('OHOS_QA_RUNTIME_PROFILE')
        digest = getattr(self.args, 'runtime_profile_sha256', None) or os.environ.get('OHOS_QA_RUNTIME_PROFILE_SHA256')
        if profile is None or not re.fullmatch(r'[0-9a-f]{64}', digest or ''):
            raise ValueError('explicit actual installed runtime profile and SHA256 required; no SDK helper fallback')
        profile = Path(profile).absolute()
        if profile.is_symlink() or not profile.is_file() or sha(profile) != digest:
            raise ValueError('actual installed runtime profile file/SHA256 differs')
        profile_value = json.loads(profile.read_text())
        product.validate_installed_profile(profile_value, archive_sha256=self.parent['archive_sha256'])
        self.value['installed_runtime_profile_input'] = {'path': str(profile), 'sha256': digest}
        self.save()
        if not self.reuse_tools(tools, profile_value):
            self.command(['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
            '--read-only', '--cpus', '2', '--memory', '5g', '--pids-limit', '512',
            '--tmpfs', '/tmp:rw,nosuid,nodev,size=512m',
            '--mount', 'type=volume,src=' + self.args.source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=volume,src=' + getattr(self.args, 'out_volume', 'ohos-qemu-7_0-release-out') + ',dst=/ohos/out,readonly',
            '--mount', 'type=bind,src=' + str(HERE.parents[1]) + ',dst=/work,readonly',
            '--mount', 'type=bind,src=' + str(self.args.output.resolve()) + ',dst=/probe',
            '--mount', 'type=bind,src=' + str(profile.parent) + ',dst=/runtime-profile,readonly',
            self.args.docker_image, 'python3', '/work/ci/capability-audit/build_audio_capture_tools.py',
            '--source-root', '/ohos', '--arch', self.args.arch, '--output', '/probe/capture/tools',
            '--runtime-profile', '/runtime-profile/' + profile.name, '--runtime-profile-sha256', digest],
                'build-current-real-PCM-and-token-tools', timeout=1200)
        build = verify_installed_tools(tools / 'build.json', self.args.arch)
        if build.get('status') != 'pass' or build.get('arch') != self.args.arch:
            raise ValueError('real microphone orchestration tools did not compile/link')
        if any(row['installed_runtime_profile']['profile'] != profile_value for row in build['tools'].values()):
            raise ValueError('actual MIC tools installed runtime profile differs from current profile')
        for name in ('alsa_inject', 'audio_capture_token'):
            if sha(tools / name) != build['tools'][name]['binary_sha256']:
                raise ValueError('actual microphone tool changed')
        self.value.update(tools=str(tools / 'build.json'), tools_sha256=sha(tools / 'build.json'))
        self.value['guest_libraries'] = {}
        for name, library in (('alsa_inject', 'libasound.so'), ('audio_capture_token', 'libaccesstoken_sdk.z.so')):
            local = self.output / library
            directory = 'vendor/' if name == 'alsa_inject' else 'system/'
            directory += 'lib' if self.args.arch == 'armv7a' else 'lib64'
            if name == 'audio_capture_token':
                directory += '/platformsdk'
            remote = '/' + directory + '/' + library
            self.command([self.args.hdc, '-t', self.args.target, 'file', 'recv', remote, local],
                         'read-actual-package-library-' + name)
            identity = runtime_identity(local.read_bytes(), self.args.arch)
            if identity != build['tools'][name]['linked_library_runtime_sha256']:
                raise ValueError('root tool was linked against another artifact library: ' + library)
            self.value['guest_libraries'][name] = {'remote': remote, 'path': str(local), 'sha256': sha(local),
                                                  'runtime_sha256': identity}
        self.value['guest_runtime_DSOs'] = []
        for tool, row in build['tools'].items():
            for soname in row['DT_NEEDED']:
                script = product.runtime_guest_script(row, soname)
                raw = self.actual_shell(script, 'actual-installed-' + tool + '-' + soname)
                observed = product.verify_guest_runtime_raw(row, soname, raw,
                    archive_sha256=self.parent['archive_sha256'])
                self.value['guest_runtime_DSOs'].append(dict(tool=tool, script=script, raw=raw, observation=observed))
                self.value['guest_runtime_DSOs'][-1].update(shell_observation=len(self.value['guest_shell_observations']) - 1,
                    command_index=self.value['guest_shell_observations'][-1]['command_index'])
        self.save()
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
        self.generate_challenge()
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

    def token_observation(self, uid, phase, *, bundle=BUNDLE, operation='query', explicit_bundle=False):
        # The UID is read from BMS, not HapTokenInfo's non-serialized UID field.
        from run_normal_hap_probe import require_normal_identity
        bms_script = shlex.join(['bm', 'dump', '-n', bundle])
        def identity(suffix):
            raw = self.actual_shell(bms_script, 'token-BMS-' + phase + '-' + suffix)
            index = len(self.value['guest_shell_observations']) - 1
            if require_normal_identity(raw, bundle) != uid:
                raise ValueError('actual normal BMS caller UID changed around native token query')
            return bms_application_identity(raw, bundle), index
        before, before_index = identity('before')
        script = ('unset LD_LIBRARY_PATH LD_PRELOAD; ' + self.remote + '/audio_capture_token ' +
                  self.run + ' ' + str(uid) + ' ' + operation + (' ' + bundle if explicit_bundle else ''))
        result = strict_json(self.actual_shell(script, 'independent-MIC-token-' + phase))
        query_index = len(self.value['guest_shell_observations']) - 1
        after, after_index = identity('after')
        if before != after:
            raise ValueError('actual BMS UID/accessTokenId changed during native token query')
        verify_hap_token_identity(result, bundle=bundle, uid=before['uid'], token_id=before['token_id'])
        row = dict(phase=phase, observation=result, bms_before_observation=before_index,
                   token_observation=query_index, bms_after_observation=after_index)
        return result, row

    def token(self, uid, phase):
        result, row = self.token_observation(uid, phase)
        if (result.get('run_id') != self.run or result.get('result') != 0 or
                result.get('operation') != 'query' or type(result.get('before')) is not int or
                result.get('before') not in (-1, 0) or type(result.get('after')) is not int or result.get('after') not in (-1, 0)):
            raise ValueError('independent actual AccessToken query does not match the ordinary caller')
        self.last_token = result
        self.value['tokens'].append(row)
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
            self.producer_exit_marker = '__PCM_CHILD_EXIT_' + secrets.token_hex(16) + '__='
            wrapper = producer_shell(self.remote, self.producer_exit_marker)
            argv = [str(self.args.hdc), '-t', self.args.target, 'shell', wrapper]
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
        while (self.token(self.uid, 'after-dialog') != (-1 if self.denied else 0) or
               self.last_token['before'] != (-1 if self.denied else 0)):
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
            self.value['producer'] = self.producer_receipt(status)
            self.save()
            if status != 0 or self.value['producer']['guest_exit_code'] != 0:
                raise ValueError('actual root PCM producer failed')
        self.value['status'] = 'captured_NOT_independently_verified'
        self.save()
        return self.output / 'runtime.json'

    def producer_receipt(self, status, *, require_complete=True):
        path = self.output / 'producer.log'
        value = dict(argv=self.producer_argv, host_exit_code=status,
            guest_exit_marker=self.producer_exit_marker, log=str(path.resolve()), log_sha256=sha(path))
        try:
            value['guest_exit_code'] = producer_exit_code(path.read_text(), self.producer_exit_marker)
        except ValueError:
            if require_complete: raise
            value['guest_exit_code'] = None
        return value

    def require_cleanup_boot(self, label):
        if self.value.get('cleanup_boot_failure'):
            raise CleanupBootError(self.value['cleanup_boot_failure'])
        try:
            return require_cleanup_boot(self.actual_shell, self.boot_id, label)
        except CleanupBootError as error:
            self.value['cleanup_boot_failure'] = str(error)
            raise

    def close(self, *, host_only_reason=None):
        errors = [host_only_reason] if host_only_reason else []
        if self.started and not errors:
            try:
                self.require_cleanup_boot('PCM-cleanup-boot-before-stop')
                # Signal only our current executable and recorded kernel
                # starttime. A reused PID or changed executable is never killed.
                script = cleanup_producer_shell(self.remote)
                self.actual_shell(cleanup_boot_prefix(self.boot_id) + script, 'cleanup-only-owned-PCM-producer')
            except Exception as error:
                errors.append(str(error))
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                errors.append('owned producer HDC remained active after guest cleanup; preserve unknown guest state')
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
        if self.started and not errors:
            try:
                self.require_cleanup_boot('PCM-cleanup-boot-before-private-removal')
                if not re.fullmatch(r'/data/local/tmp/qemu-mic-[0-9a-f]{32}', self.remote):
                    raise ValueError('owned microphone directory identity differs')
                names = ('alsa_inject', 'audio_capture_token', 'challenge.pcm', 'producer.pid', 'producer.start')
                permitted = ' '.join('! -name ' + shlex.quote(name) for name in names)
                script = ('test -d ' + self.remote + ' && test ! -L ' + self.remote +
                    ' && test "$(stat -c \'%u %a\' ' + self.remote + ')" = "0 700" && '
                    'task_mic_unknown=$(find ' + self.remote + ' -mindepth 1 -maxdepth 1 ' + permitted + ') && '
                    'test -z "$task_mic_unknown"')
                for name in names:
                    path = self.remote + '/' + name
                    script += (' && if test -e ' + path + ' || test -L ' + path + '; then '
                        'test -f ' + path + ' && test ! -L ' + path +
                        ' && test "$(stat -c %u ' + path + ')" = 0; fi')
                script += (' && rm -f -- ' + ' '.join(self.remote + '/' + name for name in names) +
                    ' && rmdir ' + self.remote + ' && test ! -e ' + self.remote + ' && test ! -L ' + self.remote)
                self.actual_shell(cleanup_boot_prefix(self.boot_id) + script, 'cleanup-only-owned-microphone-files-and-directory')
                self.value['owned_remote_directory_removed'] = True
                self.started = False
            except Exception as error:
                errors.append(str(error))
        self.value['cleanup_errors'] = errors
        self.value['cleanup_complete'] = not errors
        self.finished = not errors
        self.save()
        if errors:
            raise ValueError('owned microphone producer cleanup failed: ' + '; '.join(errors))
