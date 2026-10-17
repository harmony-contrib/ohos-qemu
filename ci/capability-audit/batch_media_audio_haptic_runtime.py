#!/usr/bin/env python3
"""Dedicated AudioHaptic suite on one already-owned freshly packaged guest.

No builds, VM boots, permission grants, service kills or shared-runner changes.
Actual signing/UITest transport is reused from the existing audited collectors.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import signal
import subprocess
import sys
import time

import batch_media_audio_haptic_project as project
import batch_media_audio_haptic_build_sampler as sampler_build
import batch_media_knowledge_suite as shared
import batch_apps_contact_picker_coordinator as signatures
from enclosing_acceptance_guest import EnclosingAcceptanceGuest
from guest_ui import GuestUi
from spring_loading_input import OwnedPointer

HERE, FIX, ROLES = project.HERE, project.FIX, project.ROLES
require, record, checked, sha, load = project.require, project.record, project.checked, project.sha, project.load
save = shared.save
SCOPE = 'same_new_archive_ordinary_AudioHaptic_public_lifecycle_independent_QEMU_PCM_read_only_VDI_NOT_full_capability_closure'
TOOLS = ('batch_media_audio_haptic_project.py', 'batch_media_audio_haptic_build_sampler.py',
         'batch_media_audio_haptic_build_callers.py', 'batch_media_audio_haptic_runtime.py', 'batch_media_audio_haptic_verify.py', 'batch_media_audio_capture_challenge.py',
         'batch_media_knowledge_suite.py', 'batch_apps_contact_picker_coordinator.py', 'batch_media_wallpaper_artifacts.py',
         'batch_system_build_runtime_helpers.py', 'enclosing_acceptance_guest.py', 'guest_ui.py', 'spring_loading_input.py')


def owned_capture_listing(text, path):
    require(re.fullmatch(r'\[0\]: Capturing audio\(48000,16,2\) to ' + re.escape(str(path)) + r': [0-9]+ bytes\r?\n', text),
            'actual capture index/path/format is not exclusively ours')


class AudioCapture:
    """Own exactly one new QEMU wavcapture; refuse another client's capture."""
    qmp = OwnedPointer.qmp

    def __init__(self, collector):
        self.collector = collector
        self.env = collector.env
        self.report = collector.value['qmp']
        argv = shlex.split(self.env['qemu_command'])
        backends = [argv[i + 1] for i, word in enumerate(argv[:-1]) if word == '-audiodev']
        ids = [re.search(r'(?:^|,)id=([A-Za-z0-9_-]+)(?:,|$)', word) for word in backends]
        require(len(ids) == 1 and ids[0] is not None, 'one actual QEMU audio backend ID required')
        self.backend = ids[0][1]
        require(any(word.startswith('es1370,') and 'audiodev=' + self.backend in word.split(',') for word in argv),
                'actual ES1370 must use the selected QEMU audio backend')
        self.path = None
        self.owned = False
        help_text = self.hmp('help wavcapture', 'capture-help')
        require(re.search(r'wavcapture\s+path audiodev', help_text), 'actual HMP wavcapture syntax differs from reviewed QEMU primary source')
        require(self.hmp('info capture', 'capture-before') == '', 'another audio capture already exists; refuse to stop or reuse it')

    def hmp(self, command, label):
        self.collector.guest.healthy()
        result = self.qmp('human-monitor-command', label, {'command-line': command})
        self.collector.persist()
        require(isinstance(result, str), 'actual HMP textual reply required')
        return result

    def start(self, phase):
        require(not self.owned and self.hmp('info capture', phase + '-before-capture') == '', 'capture ownership changed')
        self.path = self.collector.args.output / (phase + '-qemu.wav')
        require(not self.path.exists() and re.fullmatch(r'/[A-Za-z0-9_./-]+', str(self.path)),
                'fresh monitor-safe absolute WAV output required (no spaces)')
        self.begin = time.monotonic_ns()
        # Mark ownership before sending; an ambiguous reply still needs cleanup.
        self.owned = True
        reply = self.hmp(f'wavcapture {self.path} {self.backend} 48000 16 2', phase + '-wavcapture')
        require(reply == '', 'QEMU rejected actual WAV capture: ' + reply)
        listing = self.hmp('info capture', phase + '-capture-owned')
        owned_capture_listing(listing, self.path)

    def stop(self, phase):
        require(self.owned and self.path is not None, 'no owned capture')
        listing = self.hmp('info capture', phase + '-capture-before-stop')
        owned_capture_listing(listing, self.path)
        require(self.hmp('stopcapture 0', phase + '-stopcapture') == '', 'actual owned capture stop failed')
        ended = time.monotonic_ns()
        require(self.hmp('info capture', phase + '-capture-after-stop') == '', 'owned capture remains active')
        self.owned = False
        require(self.path.is_file() and not self.path.is_symlink(), 'actual QEMU did not produce a WAV file')
        return {'wav': record(self.path), 'host_begin_ns': self.begin, 'host_end_ns': ended, 'backend': self.backend}


def sign_ordinary_hap(unsigned, bundle, permissions, udid, signer_dist, signer_jar, output, command):
    # The shared comparator is integrated by root. Avoid the legacy whole-ZIP
    # equality in sign_normal_hap; retain all real signature/profile checks.
    unsigned = checked(record(unsigned)); signatures.ordinary_hap(unsigned, bundle, permissions)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    dist, jar, _ = signatures.signer_inputs(signer_dist, signer_jar)
    signed = output / 'signed.hap'
    command([sys.executable, str(HERE / 'sign_web_probe.py'), '--signer-dist', str(dist), '--jar', str(jar),
        '--unsigned', str(unsigned), '--output', str(signed), '--bundle-name', bundle, '--udid', udid, '--sign-code', '1'], 'sign-normal-HAP')
    signatures.verify_signed_payload(unsigned, signed)
    proof = signatures.verify_signed_hap_artifacts(signed, bundle, permissions, udid, dist, jar, output / 'verification', command)
    proof['unsigned_hap'] = record(unsigned)
    return proof


def cleanup_player_actions(invoke, envelope, read_rows, errors, role):
    # A failed Stop must never prevent attempting Release of our own player.
    for action in ('stop', 'release'):
        try:
            current = json.loads(json.dumps(envelope)); current['role'] = role
            current['phase'] = 'cleanup-' + role + '-' + action
            current['request'].update(action=action, operation_id=secrets.token_hex(16))
            operation = invoke(current, cleanup=True)
            group = [row for row in read_rows(operation) if row['operation_id'] == current['request']['operation_id']]
            require(any(row['event'] == 'complete' for row in group) and not any(row['event'] == 'error' for row in group),
                    'real owned public cleanup failed')
        except Exception as error: errors.append('owned ' + role + ' ' + action + ' cleanup: ' + str(error))


class Collector(shared.Collector):
    """Reuse generic actual commands/UITest observations; no Knowledge operations."""
    def __init__(self, args, value):
        self.args, self.value = args, value
        self.guest = EnclosingAcceptanceGuest(args.boot, args.archive, args.hdc, args.output / 'guest').start()
        self.env = self.guest.env
        require((self.env['guest_arch'], self.env['device_type']) == ('arm64', 'phone'), 'current representative ARM64 phone only')
        self.data = project.validate_challenge(checked(value['artifacts_data']['challenge']))
        self.ui = GuestUi(self.command, args.hdc, self.guest.target, args.output / 'ui')
        self.remote = '/data/local/tmp/audio-haptic-' + self.data['run_id']
        self.roles = value['roles']; self.identities = {}; self.pids = {}
        self.installed = []; self.remote_created = False
        self.process = None; self.sampler_stream = None; self.sampler_row = None; self.sampler_pid = None
        self.capture = None

    def files(self, role):
        return '/data/app/el2/100/base/' + ROLES[role][0] + '/files'

    def stage(self, local, remote, uid, *, replace=False, executable=False):
        local = checked(local)
        temp = remote + '.' + secrets.token_hex(8) + '.tmp' if replace else remote
        require(not replace or remote.endswith('/audio-haptic-request.json'), 'only owned request may be replaced')
        self.shell('test ! -e ' + shlex.quote(temp) + ' && test ! -L ' + shlex.quote(temp), 'fresh-stage-target')
        self.command([self.args.hdc, '-t', self.guest.target, 'file', 'send', local, temp], 'send-owned-file')
        sent = len(self.value['commands']) - 1
        mode = '700' if executable else '600'
        self.shell('chown ' + str(uid) + ':' + str(uid) + ' ' + shlex.quote(temp) + ' && chmod ' + mode + ' ' + shlex.quote(temp), 'owned-stage-mode')
        if replace: self.shell('test ! -L ' + shlex.quote(remote) + ' && mv ' + shlex.quote(temp) + ' ' + shlex.quote(remote), 'publish-owned-request')
        observed = self.observe('sha256sum ' + shlex.quote(remote), 'actual-staged-sha')
        require(checked(observed).read_text().split() == [sha(local), remote], 'staged bytes differ')
        self.value['staged'].append(dict(local=record(local), remote=remote, sent_remote=temp, uid=uid, mode=mode, command=sent, guest_hash=observed))
        self.persist()

    def journal(self, role, name):
        remote = self.files(role) + '/audio-haptic-' + self.data['run_id'] + '.jsonl'
        marker = '__HAPTIC_EOF_' + secrets.token_hex(16) + '__'
        observation = self.observe('if test -f ' + shlex.quote(remote) + '; then cat ' + shlex.quote(remote) +
            ' || exit 1; fi && printf ' + shlex.quote('\n' + marker + '\n'), name)
        raw = checked(observation).read_text()
        require(raw.endswith('\n' + marker) and raw.count(marker) == 1, 'whole journal EOF missing')
        path = self.args.output / (name + '-' + secrets.token_hex(4) + '.jsonl')
        with path.open('x') as stream: stream.write(raw[:-len(marker)-1])
        result = record(path)
        self.value['journals'].append(dict(role=role, raw=result, observation=observation, sentinel=marker, remote=remote))
        return result

    def pid(self, role, phase):
        bundle = ROLES[role][0]
        raw = self.observe('pidof ' + bundle, phase + '-' + role + '-pid')
        text = checked(raw).read_text()
        require(re.fullmatch('[1-9][0-9]*', text), 'one actual persistent ordinary caller PID required')
        identity = self.observe('cat /proc/' + text + '/stat', phase + '-' + role + '-stat')
        stat = checked(identity).read_text()
        fields = stat[stat.rfind(')') + 2:].split()
        require(len(fields) >= 20 and fields[19].isdigit(), 'actual process starttime missing')
        current = (int(text), int(fields[19]))
        require(role not in self.pids or self.pids[role] == current, 'same caller instance was lost across lifecycle operations')
        self.pids[role] = current
        return dict(pid=raw, stat=identity)

    def token(self, role, when):
        bundle, _ = ROLES[role]
        raw = self.observe(project.sampler_script(self.remote, 'token', self.data['run_id'], self.env['boot_id'],
            bundle, self.identities[role]['uid']), role + '-token-' + when)
        value = load(checked(raw))
        require(value.get('kind') == 'token' and value['run_id'] == self.data['run_id'] and value['boot_id'] == self.env['boot_id'] and
                value['bundle'] == bundle and value['uid'] == self.identities[role]['uid'] and value['token_id'] == self.identities[role]['token_id'] and
                value['VIBRATE'] == (0 if role == 'normal' else -1), 'real ordinary VIBRATE token differs')
        self.roles[role]['token_' + when] = raw

    def install(self, role):
        artifacts = self.value['artifacts_data']; spec = artifacts['projects'][role]
        bundle, permissions = ROLES[role]
        proof = sign_ordinary_hap(checked(spec['unsigned_hap']), bundle, permissions, self.env['udid'],
            artifacts['signer']['dist'], checked(artifacts['signer']['jar']), self.args.output / (role + '-signing'), self.command)
        self.installed.append(bundle)
        reply = self.command([self.args.hdc, '-t', self.guest.target, 'install', checked(proof['signed_hap'])], 'install-' + role)
        require(re.search(r'\bsuccess', reply, re.I) and not re.search(r'\bfail', reply, re.I), 'actual install failed')
        bms = self.observe('bm dump -n ' + bundle, role + '-BMS')
        from batch_media_audio_haptic_verify import bms_identity
        identity = bms_identity(checked(bms).read_text(), role)
        self.identities[role] = identity
        self.roles[role] = dict(sdk=spec, signed_hap=proof['signed_hap'], signature=proof, bms=bms,
            installed_remote=identity['installed_remote'], installed_hap=self.receive(identity['installed_remote'], role + '-installed-HAP'), inputs={})
        self.token(role, 'initial')
        self.shell('aa start -b ' + bundle + ' -a EntryAbility', 'open-' + role)
        self.wait_control(bundle, {'identifier': 'audio_haptic_run'}, 'ready', role)
        self.roles[role]['journal_before'] = self.journal(role, role + '-before')
        require(checked(self.roles[role]['journal_before']).read_bytes() == b'', 'fresh lazy caller journal already exists')
        for name, item in self.data['files'].items():
            self.stage(item, self.files(role) + '/' + name, identity['uid'])
            self.roles[role]['inputs'][name] = self.receive(self.files(role) + '/' + name, role + '-readback-' + name)
            require(self.roles[role]['inputs'][name]['sha256'] == item['sha256'], 'caller private challenge readback differs')

    def clock(self, label):
        before = time.monotonic_ns()
        raw = self.observe(project.sampler_script(self.remote, 'clock', self.data['run_id'], self.env['boot_id']), label)
        after = time.monotonic_ns()
        row = dict(raw=raw, host_before_ns=before, host_after_ns=after)
        self.value['clocks'].append(row)
        return row

    def sampler_start(self, phase):
        require(self.process is None, 'only one read-only sampler may be active')
        marker = '__HAPTIC_SAMPLE_EXIT_' + secrets.token_hex(16) + '__='
        stop = self.remote + '/sampler-stop'
        self.shell('test ! -e ' + stop + ' && test ! -L ' + stop, 'sampler-stop-fresh')
        script = 'unset LD_LIBRARY_PATH LD_PRELOAD; ' + self.remote + '/sampler sample ' + self.data['run_id'] + ' ' + self.env['boot_id']
        script += ' 900000 10 ' + stop + '; task_haptic_rc=$?; printf "\\n' + marker + '%s\\n" "$task_haptic_rc"'
        path = self.args.output / (phase + '-sampler.jsonl')
        argv = [self.args.hdc, '-t', self.guest.target, 'shell', script]
        self.sampler_stream = path.open('xb')
        self.process = subprocess.Popen(argv, stdout=self.sampler_stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        self.sampler_row = dict(argv=argv, phase=phase, exit_marker=marker, path=str(path), host_begin_ns=time.monotonic_ns())
        self.value['samplers'].append(self.sampler_row)
        deadline = time.monotonic() + 15
        while True:
            lines = path.read_text(errors='replace').replace('\r', '').splitlines()
            if lines:
                begin = json.loads(lines[0]); require(begin.get('kind') == 'begin', 'actual sampler did not connect to HDI')
                self.sampler_pid = begin['pid']; break
            require(self.process.poll() is None and time.monotonic() < deadline, 'actual sampler failed to start')
            time.sleep(.1)
        pid = str(self.sampler_pid)
        self.sampler_row['process'] = self.observe('test "$(readlink /proc/' + pid + '/exe)" = ' + self.remote +
            '/sampler && cat /proc/' + pid + '/stat', phase + '-sampler-process')
        self.sampler_row['maps'] = self.observe('cat /proc/' + pid + '/maps', phase + '-sampler-maps')
        self.persist()

    def sampler_stop(self):
        require(self.process is not None, 'no owned sampler')
        stop = self.remote + '/sampler-stop'
        self.shell('test ! -e ' + stop + ' && test ! -L ' + stop + ' && (umask 077; : > ' + stop + ')', 'stop-only-owned-sampler-by-file')
        try:
            code = self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.value['cleanup_errors'].append('owned read-only sampler did not exit after stop file')
            raise ValueError('sampler termination unproved; preserve owned guest for root investigation')
        self.sampler_stream.close(); self.sampler_stream = None
        path = Path(self.sampler_row['path'])
        self.sampler_row.update(raw=record(path), exit_code=code, host_end_ns=time.monotonic_ns())
        marker = self.sampler_row['exit_marker']
        text = path.read_text().replace('\r', '')
        require(code == 0 and text.endswith('\n' + marker + '0\n') and text.count(marker) == 1, 'actual guest sampler failed')
        self.shell('test ! -d /proc/' + str(self.sampler_pid) + ' && rm -- ' + stop + ' && test ! -e ' + stop, 'owned-sampler-exited-and-stop-file-removed')
        result = self.sampler_row
        self.process = None; self.sampler_row = None; self.sampler_pid = None
        return result

    def abort_owned_sampler(self):
        """Only our proven PID/starttime/executable; never touches an effect."""
        if self.process is not None and self.process.poll() is not None and self.sampler_row is not None:
            path = Path(self.sampler_row['path']); marker = self.sampler_row['exit_marker']
            text = path.read_text(errors='replace').replace('\r', '')
            if re.search(r'\n' + re.escape(marker) + r'[0-9]+\n$', text) and text.count(marker) == 1:
                if self.sampler_stream is not None: self.sampler_stream.close()
                self.sampler_row.update(raw=record(path), exit_code=self.process.returncode,
                    host_end_ns=time.monotonic_ns(), failed_native_command_returned=True)
                self.process = None; self.sampler_stream = None; self.sampler_row = None; self.sampler_pid = None
                self.shell('rm -f -- ' + self.remote + '/sampler-stop', 'failed-owned-observer-stop-file-removed')
                return
        require(self.process is not None and self.sampler_row is not None and self.sampler_pid is not None,
                'no independently identified owned sampler to terminate')
        raw = checked(self.sampler_row['process']).read_text()
        fields = raw[raw.rfind(')')+2:].split()
        require(len(fields) >= 20 and fields[19].isdigit(), 'owned observer kernel starttime missing')
        pid = str(self.sampler_pid)
        script = ('if test -d /proc/' + pid + '; then test "$(readlink /proc/' + pid + '/exe)" = ' + self.remote +
            '/sampler && test "$(awk \'{print $22}\' /proc/' + pid + '/stat)" = ' + fields[19] + ' && kill -TERM ' + pid + '; fi')
        self.observe(script, 'terminate-only-owned-stalled-read-only-sampler')
        self.process.wait(timeout=5)
        self.sampler_stream.close(); self.sampler_stream = None
        self.sampler_row.update(raw=record(Path(self.sampler_row['path'])), exit_code=self.process.returncode,
                                host_end_ns=time.monotonic_ns(), aborted_owned_observer=True)
        self.shell('test ! -d /proc/' + pid + ' && rm -f -- ' + self.remote + '/sampler-stop', 'aborted-owned-observer-absent')
        self.process = None; self.sampler_row = None; self.sampler_pid = None

    def invoke(self, envelope, *, cleanup=False, following=None, delay_ms=None):
        role, phase = envelope['role'], envelope['phase']; bundle = ROLES[role][0]
        envelopes = [envelope] if following is None else [envelope, following]
        rows = []
        begin = self.identity('request-' + envelope['request']['operation_id'] + '-boot-before')
        for item in envelopes:
            path = self.args.output / ('request-' + item['request']['operation_id'] + '.json')
            project.write(path, item)
            row = dict(phase=item['phase'], role=role, request=record(path), begin_boot=begin, complete=False)
            self.value['cleanup_operations' if cleanup else 'phases'].append(row); rows.append(row)
        transport = rows[0]['request']
        if following is not None:
            path = self.args.output / ('pair-' + envelope['request']['operation_id'] + '.json')
            project.write(path, project.paired_request(envelope, following, delay_ms)); transport = record(path)
        self.shell('aa start -b ' + bundle + ' -a EntryAbility', 'foreground-' + role)
        self.wait_control(bundle, {'identifier': 'audio_haptic_run'}, 'ready', phase)
        before = self.pid(role, phase + '-before')
        self.stage(transport, self.files(role) + '/audio-haptic-request.json', self.identities[role]['uid'], replace=True)
        # One real click executes only this explicit pair in the persistent UI
        # instance. No HDC, screenshot, journal or sampler restart between calls.
        click = self.click(bundle, {'identifier': 'audio_haptic_run'}, 'run', phase)
        for row in rows: row.update(transport_request=transport, click=click, pid_before=before)
        deadline = time.monotonic() + 45
        while True:
            journal = self.journal(role, 'request-' + envelope['request']['operation_id'] + '-poll')
            text = checked(journal).read_text()
            if text.endswith('\n'):
                records = list(map(json.loads, text.splitlines()))
                if all(any(r['operation_id'] == item['request']['operation_id'] and r['event'] in ('complete', 'error')
                           for r in records) for item in envelopes): break
                # A real failed first call prevents the UI from running its
                # following operation. Preserve that failure without 45s delay.
                first = [r for r in records if r['operation_id'] == envelope['request']['operation_id']]
                require(not any(r['event'] == 'error' for r in first) or following is None, 'paired public Start failed')
            require(time.monotonic() < deadline, 'real public operation timed out: ' + phase); time.sleep(.2)
        ended = self.identity('request-' + envelope['request']['operation_id'] + '-boot-after')
        after = self.pid(role, phase + '-after')
        for row in rows: row.update(journal=journal, end_boot=ended, pid_after=after, complete=True)
        self.roles[role]['journal'] = journal; self.persist()
        return rows if following is not None else rows[0]

    def segment(self, phase, envelope=None, *, following=None, boundary=None):
        block = [phase] if boundary is None else [phase, boundary]
        name = project.capture_name(block)
        self.capture.start(name)
        row = dict(phase=name, expected=phase, begin_boot=self.identity(name + '-segment-before'))
        if boundary is not None: row['boundary_expected'] = boundary
        self.value['segments'].append(row)
        try:
            row['clock_before'] = self.clock(name + '-clock-before'); self.sampler_start(name)
            if envelope is not None:
                operations = self.invoke(envelope, following=following, delay_ms=phase['hold_ms'])
                if following is None: row['operation'] = operations
                else: row['operation'], row['boundary_operation'] = operations
            time.sleep((phase if boundary is None else boundary)['hold_ms'] / 1000)
            if envelope is not None:
                role = envelope['role']; row['journal_after'] = self.journal(role, name + '-after-hold')
                self.roles[role]['journal'] = row['journal_after']
                if envelope['request']['action'] == 'start': row['native_log'] = self.observe('hilog -x', name + '-native-log')
            row['sampler'] = self.sampler_stop(); row['clock_after'] = self.clock(name + '-clock-after')
        finally:
            if self.process is not None:
                try: row['sampler'] = self.sampler_stop()
                except Exception as error: self.value['cleanup_errors'].append(str(error))
            if self.capture.owned: row['audio_capture'] = self.capture.stop(name)
            row['end_boot'] = self.identity(name + '-segment-after'); self.persist()

    def cleanup(self):
        errors = self.value['cleanup_errors']; cleanup = self.value.setdefault('cleanup', {})
        if self.process is not None:
            try: self.sampler_stop()
            except Exception as error:
                errors.append('owned sampler cleanup: ' + str(error))
                try: self.abort_owned_sampler()
                except Exception as abort_error: errors.append('owned sampler termination: ' + str(abort_error))
        if self.capture is not None and self.capture.owned:
            try: cleanup['owned_capture_stop'] = self.capture.stop('emergency')
            except Exception as error: errors.append('owned QEMU capture cleanup: ' + str(error))
        # Stop/release only a successfully created, not-yet-released owned player.
        for role in self.roles:
            try:
                journal = self.journal(role, role + '-cleanup-before')
                rows = [json.loads(line) for line in checked(journal).read_text().splitlines()]
                created = [r['sequence'] for r in rows if r['event'] == 'return' and r['api'] == 'AudioHapticManager.createPlayer']
                released = [r['sequence'] for r in rows if r['event'] == 'return' and r['api'] == 'AudioHapticPlayer.release']
                if created and max(created) > max(released, default=0):
                    base = project.request(checked(self.value['artifacts_data']['challenge']), self.env['boot_id'], 'normal-stop-1')
                    cleanup_player_actions(self.invoke, base,
                        lambda operation: map(json.loads, checked(operation['journal']).read_text().splitlines()), errors, role)
                self.roles[role]['journal'] = self.journal(role, role + '-final')
                self.token(role, 'final')
            except Exception as error: errors.append('owned public player cleanup: ' + role + ': ' + str(error))
        cleanup['roles'] = []
        for bundle in reversed(self.installed):
            try:
                reply = self.command([self.args.hdc, '-t', self.guest.target, 'uninstall', bundle], 'uninstall-owned-role')
                require(re.search(r'\bsuccess', reply, re.I), 'owned uninstall failed')
                index = len(self.value['commands']) - 1
                absent = self.observe('test ! -d /data/app/el2/100/base/' + bundle +
                    ' && test -z "$(pidof ' + bundle + ')"', 'owned-data-and-process-absent')
                cleanup['roles'].append(dict(bundle=bundle, uninstall_command=index, absence=absent))
            except Exception as error: errors.append('owned bundle cleanup: ' + str(error))
        try:
            bms = self.observe('bm dump -a', 'owned-BMS-absent')
            shared.assert_bundles_absent(checked(bms).read_text(), self.installed)
            cleanup['bms_absent'] = bms
            ams = self.observe('aa dump -a -u 100', 'owned-AMS-absent')
            shared.assert_ams_absent(checked(ams).read_text(), self.installed)
            cleanup['ams_absent'] = ams
            if self.capture is not None and self.process is None:
                self.segment(dict(name='final-cleanup-quiet', role=None, action=None, options={}, expected='ok', errors=[],
                    hold_ms=1100, audio='quiet', haptic='quiet', eos=False, active_before=None))
        except Exception as error: errors.append('owned cleanup observations: ' + str(error))
        try:
            ui_paths = sorted({p for row in self.value['commands'] if len(row['argv']) == 5 and row['argv'][3] == 'shell'
                for p in re.findall(r'/data/local/tmp/qemu-capability-ui-' + self.ui.challenge + r'-[1-9][0-9]*\.(?:json|png)', row['argv'][4])})
            require(self.process is None, 'preserve private observer files while owned process exit is unproved')
            paths = ([self.remote + '/sampler'] if self.remote_created else []) + ui_paths
            if paths:
                if self.remote_created: paths, script = project.private_cleanup_script(self.remote, ui_paths)
                else:
                    script = 'rm -f -- ' + ' '.join(map(shlex.quote, paths)) + ' && ' + ' && '.join(
                        'test ! -e ' + shlex.quote(p) + ' && test ! -L ' + shlex.quote(p) for p in paths)
                cleanup['private_removal'] = self.observe(script, 'only-owned-helper-and-UI-files-absent')
            cleanup['ui_challenge'] = self.ui.challenge
            cleanup['private_paths'] = paths
            cleanup['final_boot'] = self.identity('final-same-boot')
        except Exception as error: errors.append('owned private cleanup: ' + str(error))
        self.value['guest_commands'] = self.guest.report['commands']
        self.value['cleanup_complete'] = not errors
        self.persist()


def artifact_spec(path):
    value = load(path)
    require(set(value) == {'schema_version', 'challenge', 'projects', 'signer', 'helper'} and value['schema_version'] == 1 and
            set(value['projects']) == set(ROLES), 'exact two-role precompiled artifact manifest required')
    challenge = checked(value['challenge']); project.validate_challenge(challenge)
    for role, spec in value['projects'].items(): project.project_binding(spec, role, challenge)
    signatures.signer_inputs(value['signer']['dist'], checked(value['signer']['jar']))
    sampler_build.helper_binding(value['helper'])
    return value


def run(args):
    args.output = args.output.resolve(); args.output.mkdir(parents=True, exist_ok=False)
    require(re.fullmatch(r'/[A-Za-z0-9_./-]+', str(args.output)), 'HMP WAV output needs an absolute path without spaces')
    value = dict(schema_version=1, status='fail', scope=SCOPE, archive=record(args.archive), archive_sha256=sha(args.archive),
        boot=record(args.boot), artifacts=record(args.artifacts), hdc=str(Path(args.hdc).resolve()), commands=[], observations=[], received=[],
        staged=[], journals=[], phases=[], cleanup_operations=[], ui_actions=[], segments=[], samplers=[], clocks=[], roles={},
        failures=[], cleanup_errors=[], cleanup_complete=False, qmp={'requests': []}, signature_reverification_commands=[],
        tool_sources={name: record(HERE / name) for name in TOOLS},
        first_frame_trace_freshness_independently_verified=False, cross_generation_callback_gap_closed=False,
        first_artifact_behavior_gate_passed=False, ledger_closed=False)
    collector = None; lease = None
    try:
        spec = artifact_spec(args.artifacts); value['artifacts_data'] = spec
        collector = Collector(args, value); value.update(run_id=collector.data['run_id'], boot_id=collector.env['boot_id'], test_environment=collector.env)
        # A root scheduler still excludes active external producers. This lock
        # prevents simultaneous instances of this dedicated tool on this guest.
        lease = (Path(args.boot).resolve().parent / 'audio-vibrator-QA.lock').open('a')
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        value['exclusive_workload_acknowledged'] = args.exclusive_audio_vibrator
        require(args.exclusive_audio_vibrator, 'root must allocate the guest audio/vibrator producer exclusively')
        collector.observe('test -z "$(pidof vibrator_hdi)"', 'active-vibrator-HDI-probe-absent')
        listing = collector.observe('bm dump -a', 'no-preexisting-owned-roles')
        shared.assert_bundles_absent(checked(listing).read_text(), [row[0] for row in ROLES.values()])
        value['helper'] = sampler_build.helper_binding(spec['helper'])
        collector.shell('test ! -e ' + collector.remote + ' && test ! -L ' + collector.remote, 'fresh-helper-directory')
        collector.remote_created = True
        collector.shell('mkdir -m 700 ' + collector.remote, 'create-owned-helper-directory')
        collector.stage(value['helper']['binary'], collector.remote + '/sampler', 0, executable=True)
        value['helper_guest_DSOs'] = []
        for dso in value['helper']['product_DSOs']:
            name = dso['soname']
            candidates = ['/system/lib64/' + name, '/system/lib64/platformsdk/' + name, '/vendor/lib64/' + name, '/lib/' + name]
            script = 'for task_dso in ' + ' '.join(map(shlex.quote, candidates)) + '; do if test -f "$task_dso"; then sha256sum "$task_dso" || exit 1; fi; done'
            raw = collector.observe(script, 'actual-helper-DSO-' + name)
            require(checked(raw).read_text().splitlines() and all(v.split()[0] == dso['sha256'] for v in checked(raw).read_text().splitlines()),
                    'same-new-guest product DSO differs from actual helper link: ' + name)
            value['helper_guest_DSOs'].append(dict(soname=name, observation=raw, script=script))
        collector.capture = AudioCapture(collector)
        for role in ROLES: collector.install(role)
        require(len({row['uid'] for row in collector.identities.values()}) == 2 and
                len({row['token_id'] for row in collector.identities.values()}) == 2, 'normal/denied identities overlap')
        for block in project.execution_plan():
            phase = block[0]
            envelope = project.request(checked(spec['challenge']), collector.env['boot_id'], phase['name'])
            if len(block) == 2:
                following = project.request(checked(spec['challenge']), collector.env['boot_id'], block[1]['name'])
                collector.segment(phase, envelope, following=following, boundary=block[1])
            elif phase['hold_ms']: collector.segment(phase, envelope)
            else: collector.invoke(envelope)
    except Exception as error:
        value['failures'].append(type(error).__name__ + ': ' + str(error))
    finally:
        if collector is not None:
            try: collector.cleanup()
            except Exception as error: value['cleanup_errors'].append(type(error).__name__ + ': ' + str(error))
        else: value['cleanup_complete'] = True; value['cleanup'] = {'no_guest_resources_created': True}
        if lease is not None: lease.close()
        save(args.output / 'evidence.json', value)
    if not value['failures'] and not value['cleanup_errors'] and value['cleanup_complete']:
        try:
            from batch_media_audio_haptic_verify import verify_evidence
            value['independent_result'] = verify_evidence(args.output / 'evidence.json', args.archive, args.boot,
                command=signatures.Commands(args.output / 'reverification', value['signature_reverification_commands']))
            value['status'] = 'pass_scoped_runtime_NOT_full_capability_closure'
        except Exception as error: value['failures'].append('independent verification: ' + type(error).__name__ + ': ' + str(error))
        save(args.output / 'evidence.json', value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'boot', 'artifacts', 'output'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--hdc', required=True)
    parser.add_argument('--exclusive-audio-vibrator', action='store_true', help='root scheduler has excluded all other audio/vibrator producers')
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({'status': result['status'], 'failures': result['failures'], 'cleanup_errors': result['cleanup_errors']}, indent=2))
    raise SystemExit(result['status'] != 'pass_scoped_runtime_NOT_full_capability_closure')


if __name__ == '__main__': main()
