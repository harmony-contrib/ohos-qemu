"""Two real ordinary audio callers, one owned producer, nonce-gated focus actions.

This collects evidence only. The independently maintained verifier decides pass.
"""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

from audio_capture_runtime import CaptureRuntime
from audio_capture_contract import sha
from audio_capture_permission import decide
from audio_focus_observation import BUNDLES, DIALOG, active_task, notification_node, records
from batch_media_audio_capture_challenge import load_reference, phase_content
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady
from verify_audio_capture_results import token as checked_token

HERE = Path(__file__).resolve().parent
SCOPE = 'ordinary_dual_UID_MIC_VOIP_focus_with_real_BG_ANS_and_independent_PCM'
PRODUCER = dict(rate=48000, channels=2, repeat=60, timeout_ms=90000,
                source_frames=48000, expected_frames=2880000)
NATIVE_LIMIT = 48000 * 4 * 40
JOURNAL_PENDING_SECONDS = 2


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate actual evidence key: ' + key)
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def validate_ready(value, run, action, uid, running=False):
    if (not isinstance(value, dict) or value.get('run_id') != run or value.get('action') != action or
            type(value.get('uid')) is not int or value['uid'] != uid or
            re.fullmatch('[0-9a-f]{32}', value.get('nonce', '')) is None or
            type(value.get('monotonic_ns')) is not int or value['monotonic_ns'] <= 0):
        raise ValueError('native action readiness belongs to another session')
    if running and (any(type(value.get(k)) is not int for k in ('state_result', 'state', 'frames_result')) or
                    value.get('state_result') != 0 or value.get('state') != 2 or
                    value.get('frames_result') != 0 or type(value.get('frames')) is not int or
                    value['frames'] <= 0 or type(value.get('copied_bytes')) is not int or
                    value['copied_bytes'] <= 0):
        raise ValueError('native action readiness has no actual RUNNING microphone PCM')
    return value


def forced_stop(snapshot, interval, stopped):
    event = snapshot.get('last_callback')
    return (snapshot.get('type') == 'event_snapshot' and snapshot.get('state_result') == 0 and
            all(type(snapshot.get(k)) is int for k in ('state_result', 'state', 'invalid', 'before_ns')) and
            snapshot.get('state') == stopped and snapshot.get('invalid') == 0 and
            isinstance(event, dict) and event.get('kind') == 1 and event.get('code') == 0 and
            all(type(event.get(k)) is int for k in ('kind', 'code', 'hint')) and
            event.get('hint') == 3 and type(event.get('monotonic_ns')) is int and
            interval['before_ns'] <= event['monotonic_ns'] <= interval['after_ns'] + 500000000 and
            snapshot.get('before_ns', 0) >= interval['before_ns'])


def validate_fresh(reply, ready, uid, request_interval, constants):
    expected = dict(type='event_fresh_reply', run_id=ready['run_id'], action=ready['action'],
        ready_nonce=ready['nonce'], request_nonce=ready['nonce'], uid=uid, euid=uid,
        phase=1 if ready['action'] == 'focus_begin' else 0, state_result=0, state=2,
        frames_result=0, timestamp_result=0, source_result=0, source_type=constants['MIC'],
        rate_result=0, rate=48000, channels_result=0, channels=2, format_result=0,
        format=constants['S16LE'], bytes=96000, persisted=True)
    if any(reply.get(key) != value or type(reply.get(key)) is not type(value)
           for key, value in expected.items()):
        raise ValueError('fresh reply has wrong owner/nonce/state/format/length')
    numbers = ('request_seen_ns', 'requested_offset', 'request_frames', 'request_position',
        'request_timestamp_ns', 'request_query_before_ns', 'request_query_after_ns', 'frames',
        'position', 'timestamp_ns', 'query_before_ns', 'query_after_ns', 'copy_before_ns',
        'copy_after_ns', 'first_callback_ns', 'last_callback_ns', 'callback_count', 'offset',
        'end_offset', 'reply_prepared_ns')
    if any(type(reply.get(key)) is not int or reply[key] < 0 for key in numbers):
        raise ValueError('fresh reply counters/clocks invalid')
    q = reply
    if (not ready['monotonic_ns'] <= request_interval[0] <= q['request_seen_ns'] < q['first_callback_ns'] <=
            q['last_callback_ns'] <= q['copy_before_ns'] <= q['copy_after_ns'] <= q['query_before_ns'] <=
            q['query_after_ns'] <= q['reply_prepared_ns'] < ready['monotonic_ns'] + 15000000000 or
            not q['request_seen_ns'] <= q['request_query_before_ns'] <= q['request_query_after_ns'] <= q['copy_before_ns'] or
            q['query_after_ns'] - q['last_callback_ns'] > 250000000 or
            q['requested_offset'] > q['offset'] or q['offset'] % 4 or
            q['end_offset'] != q['offset'] + q['bytes'] or q['callback_count'] <= 0 or
            q['frames'] <= q['request_frames'] or q['position'] <= q['request_position'] or
            q['timestamp_ns'] <= q['request_timestamp_ns'] or q['frames'] + 4800 < q['end_offset'] // 4):
        raise ValueError('fresh PCM predates request, lacks progress, or has invalid callback coverage')
    name = 'audio-event-' + ready['run_id'] + '-' + ready['action'] + '-snapshot-' + ready['nonce'] + '.pcm'
    if q.get('pcm_basename') != name:
        raise ValueError('fresh PCM basename is not this action nonce')
    return reply


class AudioFocusRuntime:
    def __init__(self, args, command, shell, parent, run, boot_id, actors):
        self.args, self.command, self.shell, self.parent = args, command, shell, parent
        self.run, self.boot_id = run, boot_id
        self.output = args.output / 'focus'
        self.output.mkdir(exist_ok=False)
        self.capture = CaptureRuntime(args, command, shell, parent, run, boot_id)
        self.serial = 0
        self.complete = False
        self.closed = False
        self.value = dict(schema_version=1, scope=SCOPE, status='fail', run_id=run,
            boot_id=boot_id, archive_sha256=parent['archive_sha256'], arch=args.arch,
            device=args.device, target=args.target, runner_sha256=sha(Path(__file__)),
            sources_sha256={name: sha(HERE / name) for name in
                ('audio_focus_runtime.py', 'run_audio_focus_probe.py', 'audio_focus_observation.py')},
            common={'producer_configuration': dict(PRODUCER)}, actors=actors,
            timeline=[], failures=[], first_artifact_behavior_gate_passed=False)
        for role, actor in actors.items():
            if (role not in ('owner', 'contender') or actor['bundle'] != BUNDLES[role == 'contender'] or
                    actor['mode'] != (2 if role == 'contender' else 1)):
                raise ValueError('actual fixed owner/contender roles required')
            actor.update(files={}, tokens=[], ready_json=[], fresh_snapshots=[], acks=[],
                         background_journal=[], service_snapshots=[], notification_action=None)
            actor['app_files'] = '/data/app/el2/100/base/' + actor['bundle'] + '/files/'
            (args.output / role / 'private').mkdir(exist_ok=False)
            (args.output / role / 'live').mkdir(exist_ok=False)
        if actors['owner']['uid'] == actors['contender']['uid']:
            raise ValueError('focus requires two distinct ordinary UIDs')
        self.save()

    def save(self):
        self.capture.save()
        common = self.value['common']
        paths = {'capture_runtime': self.capture.output / 'runtime.json',
                 'boot': self.args.output / 'acceptance-boot.json',
                 'challenge_manifest': self.capture.output / 'challenge/challenge.json',
                 'challenge_pcm': self.capture.output / 'challenge/challenge.pcm',
                 'notification_contract': self.output / 'notification-contract.json'}
        for name, path in paths.items():
            if path.is_file():
                common[name + '_path'], common[name + '_sha256'] = str(path.resolve()), sha(path)
        path = self.output / 'runtime.json'
        path.write_text(json.dumps(self.value, ensure_ascii=False, indent=2) + '\n')
        return path

    def note(self, phase, **detail):
        self.value['timeline'].append(dict(phase=phase, host_wall_ns=time.time_ns(),
            host_monotonic_ns=time.monotonic_ns(), **detail))
        self.save()

    def actual(self, script, label):
        return self.capture.actual_shell(script, label)

    def token(self, actor, phase, operation='query', expected=0, transition=False):
        text = self.actual('unset LD_LIBRARY_PATH LD_PRELOAD; ' + self.capture.remote +
            '/audio_capture_token ' + self.run + ' ' + str(actor['uid']) + ' ' + operation +
            ' ' + actor['bundle'], 'focus-token-' + phase)
        value = strict_json(text)
        state, token_id = checked_token(value, self.run, actor['uid'], allow_transition=transition,
                                       bundle=actor['bundle'], operation=operation)
        if state != expected or (actor.get('token_id') is not None and actor['token_id'] != token_id):
            raise ValueError('actual focus permission/token identity changed: ' + phase)
        actor['token_id'] = token_id
        row = dict(phase=phase, observation=value)
        actor['tokens'].append(row)
        self.capture.value['tokens'].append(row)
        self.save()
        return value

    def bracket(self, actor, label, operation):
        before = self.token(actor, 'clock-before-' + label)
        result = operation()
        after = self.token(actor, 'clock-after-' + label)
        interval = [before['after_ns'], after['before_ns']]
        if interval[1] < interval[0]:
            raise ValueError('guest CLOCK_MONOTONIC moved backwards')
        return result, interval

    def process(self, actor, label):
        bundle = actor['bundle']
        raw = self.actual('focus_pid=$(pidof ' + bundle + '); '
            'case "$focus_pid" in ""|*[!0-9]*) exit 1;; esac; '
            'printf "%s " "$focus_pid"; awk \'{printf "%s ", $22}\' /proc/$focus_pid/stat; '
            'awk \'/^Uid:/{print $2, $3, $4, $5}\' /proc/$focus_pid/status', label)
        values = raw.split()
        if len(values) != 6 or any(re.fullmatch('[0-9]+', v) is None for v in values):
            raise ValueError('one actual ordinary focus process required')
        pid, start, *uids = map(int, values)
        if pid <= 0 or start <= 0 or uids != [actor['uid']] * 4:
            raise ValueError('actual focus process owner differs')
        identity = dict(pid=pid, starttime=start, uid=actor['uid'])
        if actor.get('process_before') is not None and identity != actor['process_before']:
            raise ValueError('focus actor process exited or was replaced')
        return identity

    def paths(self, actor, action):
        return actor['app_files'] + 'audio-event-' + self.run + '-' + action

    def present(self, path, label):
        value = self.actual('if test -e ' + shlex.quote(path) + '; then echo PRESENT; '
                            'else echo ABSENT; fi', label)
        if value not in ('PRESENT', 'ABSENT'):
            raise ValueError('invalid actual private-file existence observation')
        return value == 'PRESENT'

    def collect_file(self, actor, remote, *, native=True):
        name = remote.removeprefix(actor['app_files'])
        if not re.fullmatch('audio-event-' + self.run + r'-[A-Za-z0-9_.-]+', name):
            raise ValueError('private focus evidence path escapes this run')
        text = self.actual('test -f ' + shlex.quote(remote) + ' && test ! -L ' + shlex.quote(remote) +
            ' && stat -c "%u %a %s" ' + shlex.quote(remote) + ' && sha256sum ' + shlex.quote(remote),
            'focus-private-stat-and-content')
        lines = text.splitlines()
        if (len(lines) != 2 or re.fullmatch(r'[0-9]+ [0-7]+ [0-9]+', lines[0]) is None or
                re.fullmatch('[0-9a-f]{64}  ' + re.escape(remote), lines[1]) is None):
            raise ValueError('actual private focus stat invalid')
        uid, mode, size = map(int, lines[0].split())
        remote_sha = lines[1].split()[0]
        if uid != actor['uid'] or native and mode != 600 or not 0 < size <= NATIVE_LIMIT * 3:
            raise ValueError('actual focus evidence owner/mode/size invalid: ' + name)
        local = self.args.output / ('owner' if actor['mode'] == 1 else 'contender') / 'private' / name
        if local.exists():
            previous = actor['files'].get(name)
            if (previous is None or previous['bytes'] != size or sha(local) != previous['sha256'] or
                    remote_sha != previous['sha256'] or previous['uid'] != uid or previous['mode'] != mode):
                raise ValueError('immutable focus evidence changed: ' + name)
            return previous
        self.command([self.args.hdc, '-t', self.args.target, 'file', 'recv', remote, local], 'focus-private-receive')
        if local.stat().st_size != size or sha(local) != remote_sha:
            raise ValueError('actual focus transfer truncated')
        value = dict(path=str(local.resolve()), sha256=sha(local), remote=remote,
                     uid=uid, mode=mode, bytes=size)
        actor['files'][name] = value
        self.save()
        return value

    def journal_record(self, actor, remote, *, pending=False):
        """Keep live bytes separate from the immutable, completed journal set."""
        def stat():
            text = self.actual('test -f ' + shlex.quote(remote) + ' && test ! -L ' + shlex.quote(remote) +
                ' && stat -c "%u %a %s %i %Y %Z" ' + shlex.quote(remote) +
                ' && sha256sum ' + shlex.quote(remote), 'focus-background-journal-stat')
            lines = text.splitlines()
            if (len(lines) != 2 or re.fullmatch(r'[0-9]+ [0-7]+ [0-9]+ [0-9]+ [0-9]+ [0-9]+', lines[0]) is None or
                    re.fullmatch('[0-9a-f]{64}  ' + re.escape(remote), lines[1]) is None):
                raise ValueError('actual background journal stat invalid')
            uid, mode, size, inode, mtime, ctime = map(int, lines[0].split())
            if uid != actor['uid'] or not 0 <= size <= NATIVE_LIMIT * 3 or inode <= 0:
                raise ValueError('actual background journal owner/size/inode invalid')
            return dict(uid=uid, mode=mode, bytes=size, inode=inode, mtime=mtime, ctime=ctime,
                        sha256=lines[1].split()[0])

        before = stat()
        self.serial += 1
        role = 'owner' if actor['mode'] == 1 else 'contender'
        local = self.args.output / role / 'live' / (str(self.serial).zfill(5) + '-journal-read.bin')
        started = time.monotonic_ns()
        self.command([self.args.hdc, '-t', self.args.target, 'file', 'recv', remote, local],
                     'focus-background-journal-receive')
        raw = local.read_bytes()
        read = dict(remote=remote, path=str(local.resolve()), sha256=sha(local), bytes=len(raw),
                    before=before, host_monotonic_interval=[started, time.monotonic_ns()],
                    complete=False)
        actor.setdefault('journal_reads', []).append(read)
        # Save before any subsequent command or parse can fail, including an
        # owner change or disappearance while the app was writing this inode.
        self.save()
        after = stat()
        read['after'] = after
        reason = None
        if before != after or len(raw) != after['bytes'] or read['sha256'] != after['sha256']:
            reason = 'stat-or-content-changed'
        elif not raw:
            reason = 'empty'
        elif not raw.endswith(b'\n'):
            reason = 'missing-final-newline'
        if reason is not None:
            read['pending_reason'] = reason
            self.save()
            if pending:
                return None
            raise ValueError('incomplete or changed background journal: ' + reason)
        try:
            row = strict_json(raw.decode('utf-8'))
            if (not isinstance(row, dict) or row.get('run_id') != self.run or
                    type(row.get('mode')) is not int or row['mode'] != actor['mode']):
                raise ValueError('background journal belongs to another run')
        except (ValueError, UnicodeError) as error:
            read['parse_error'] = str(error)
            self.save()
            # A stable newline-terminated record is complete, so malformed JSON
            # or a wrong session is never hidden as an in-progress tail write.
            raise
        destination = self.args.output / role / 'private' / Path(remote).name
        with destination.open('xb') as output:
            output.write(raw)
        value = dict(path=str(destination.resolve()), sha256=read['sha256'], remote=remote,
                     uid=after['uid'], mode=after['mode'], bytes=len(raw))
        actor['files'][destination.name] = value
        read['complete'] = True
        self.save()
        return value, row

    def journal(self, actor, *, final=False):
        stem = 'audio-event-' + self.run + '-mode' + str(actor['mode'])
        def listed():
            raw = self.actual('find ' + actor['app_files'] + ' -maxdepth 1 -name "' + stem +
                              '-background-*.json" | sort', 'focus-background-journal-list')
            paths = raw.splitlines()
            if len(paths) > 512:
                raise ValueError('unbounded background journal sequence')
            if any(remote != actor['app_files'] + stem + '-background-' + str(index).zfill(3) + '.json'
                   for index, remote in enumerate(paths)):
                raise ValueError('missing, duplicate or foreign background journal sequence')
            return paths
        paths = listed()
        values = []
        for index, remote in enumerate(paths):
            name = Path(remote).name
            # HAP writes these nonce-scoped records with CREATE and refuses
            # overwrites. Recheck remote hashes when collecting the final set,
            # rather than repeating an HDC round-trip per immutable old record.
            value = actor['files'].get(name)
            if value is None:
                if not final and index == len(paths) - 1:
                    def tail():
                        result = self.journal_record(actor, remote, pending=True)
                        if result is None:
                            current = listed()
                            if remote not in current:
                                raise ValueError('pending background journal disappeared')
                            if current[-1] != remote:
                                # A later CREATE proves this record's writer
                                # finished. It must now pass one strict read.
                                return self.journal_record(actor, remote)
                        return result
                    value, row = self.wait('background-journal-tail-completion',
                                           tail, JOURNAL_PENDING_SECONDS)
                else:
                    value, row = self.journal_record(actor, remote)
            else:
                content = Path(value['path']).read_bytes()
                if not content.endswith(b'\n'):
                    raise ValueError('immutable background journal lacks its final newline')
                row = strict_json(content.decode('utf-8'))
            if (not isinstance(row, dict) or row.get('run_id') != self.run or
                    type(row.get('mode')) is not int or row['mode'] != actor['mode']):
                raise ValueError('background journal belongs to another run')
            if name not in actor['background_journal']:
                actor['background_journal'].append(name)
            values.append(row)
        fatal = ('startup_failed', 'cleanup_failed', 'cancel_observer_cleanup_failed',
                 'suspend_observer_cleanup_failed')
        if any(row.get('event') in fatal for row in values):
            raise ValueError('actual HAP background/native lifecycle failed')
        return values

    def wait(self, label, function, seconds=12):
        deadline = time.monotonic() + seconds
        while True:
            result = function()
            if result:
                return result
            if self.capture.process is not None and self.capture.process.poll() is not None:
                raise ValueError('owned actual PCM producer exited during ' + label)
            if time.monotonic() >= deadline:
                raise ValueError('actual focus wait timed out: ' + label)
            time.sleep(0.05)

    def native_rows(self, actor, label):
        remote = actor['app_files'] + 'audio-event-' + self.run + '-mode' + str(actor['mode']) + '-results.log'
        text = self.actual('if test -f ' + remote + '; then cat ' + remote + '; fi', label)
        if len(text) > NATIVE_LIMIT * 3:
            raise ValueError('unbounded actual native focus log')
        self.serial += 1
        local = self.args.output / ('owner' if actor['mode'] == 1 else 'contender') / 'live' / (
            str(self.serial).zfill(5) + '-' + label + '.log')
        local.write_text(text + ('\n' if text else ''))
        rows = []
        for line in text.splitlines():
            try:
                row = strict_json(line)
            except (ValueError, json.JSONDecodeError):
                # A live final line can be mid-write; retain it and poll again.
                if line != text.splitlines()[-1]:
                    raise
                break
            if not isinstance(row, dict) or row.get('run_id') != self.run:
                raise ValueError('mixed native focus run evidence')
            rows.append(row)
        actor['latest_native_log'] = dict(path=str(local.resolve()), sha256=sha(local))
        return rows

    def ready(self, actor, action, running=True):
        remote = self.paths(actor, action) + '-ready.json'
        def completed(rows):
            found = [row for row in rows if row.get('type') == 'event_ready' and row.get('action') == action]
            if len(found) > 1:
                raise ValueError('duplicate native action readiness completion')
            if not found:
                return None
            row = found[0]
            if (row.get('run_id') != self.run or re.fullmatch('[0-9a-f]{32}', row.get('nonce', '')) is None or
                    type(row.get('monotonic_ns')) is not int or row['monotonic_ns'] <= 0):
                raise ValueError('invalid native readiness completion identity')
            return row
        # Native emits this only after WritePrivate succeeds through fsync and
        # close; a newly created ready inode alone can still contain short JSON.
        completion = self.wait_native(actor, 'ready-complete-' + action, completed)
        completion_log = dict(actor['latest_native_log'])
        file, interval = self.bracket(actor, 'ready-' + action, lambda: self.collect_file(actor, remote))
        ready = validate_ready(strict_json(Path(file['path']).read_text()), self.run, action, actor['uid'], running)
        if any(ready[key] != completion[key] for key in ('run_id', 'action', 'nonce', 'monotonic_ns')):
            raise ValueError('native readiness completion and private file differ')
        if ready['nonce'] in [row['observation']['nonce'] for row in actor['ready_json']]:
            raise ValueError('reused native action nonce')
        actor['ready_json'].append(dict(action=action, path=file['path'], sha256=file['sha256'],
            observation=ready, actual_clock_interval=interval, native_completion=completion,
            completion_log=completion_log))
        self.save()
        return ready

    def write_nonce(self, actor, remote, nonce):
        if re.fullmatch('[0-9a-f]{32}', nonce) is None:
            raise ValueError('actual native nonce required')
        # Publish only after the new control inode has its final owner and mode;
        # otherwise native's O_NOFOLLOW/fstat could see the transient root UID.
        temporary = remote + '.publish-' + os.urandom(16).hex()
        self.actual('test ! -e ' + remote + ' && test ! -L ' + remote +
            ' && (set -C; umask 077; printf "%s\\n" ' + nonce + ' > ' + temporary + ') && '
            'chown ' + str(actor['uid']) + ':' + str(actor['uid']) + ' ' + temporary +
            ' && chmod 0600 ' + temporary + ' && ln ' + temporary + ' ' + remote,
            'focus-publish-owned-exclusive-control')
        # Retain the immutable backing hardlink as evidence. Unlinking it here
        # would change ctime during native's fstat-before/read/fstat-after check.
        actor.setdefault('control_backing_files', []).append(temporary)
        return self.collect_file(actor, remote)

    def ack(self, actor, ready):
        remote = self.paths(actor, ready['action']) + '-ack'
        before = self.token(actor, 'clock-before-ack-' + ready['action'])
        if not 0 <= before['after_ns'] - ready['monotonic_ns'] < 14500000000:
            raise ValueError('native ready expired before any ACK mutation')
        file = self.write_nonce(actor, remote, ready['nonce'])
        after = self.token(actor, 'clock-after-ack-' + ready['action'])
        interval = [before['after_ns'], after['before_ns']]
        if interval[0] < ready['monotonic_ns'] or interval[1] - ready['monotonic_ns'] >= 15000000000:
            raise ValueError('native ACK outside its actual bounded ready interval')
        actor['acks'].append(dict(action=ready['action'], nonce=ready['nonce'],
                                 file=Path(file['path']).name, actual_clock_interval=interval))
        self.note('ack-' + ready['action'], uid=actor['uid'], actual_clock_interval=interval)

    def fresh_snapshot(self, actor, ready):
        if ready['action'] not in ('focus_begin', 'contender_start'):
            raise ValueError('fresh snapshot only applies to an actual shared MIC baseline')
        prefix = self.paths(actor, ready['action'])
        before = self.token(actor, 'clock-before-fresh-request-' + ready['action'])
        if not 0 <= before['after_ns'] - ready['monotonic_ns'] < 14000000000:
            raise ValueError('native ready expired before fresh request mutation')
        request = self.write_nonce(actor, prefix + '-snapshot-request', ready['nonce'])
        after = self.token(actor, 'clock-after-fresh-request-' + ready['action'])
        interval = [before['after_ns'], after['before_ns']]
        remote = prefix + '-snapshot-reply.json'
        def completed(rows):
            found = [row for row in rows if row.get('type') == 'event_fresh_reply']
            if len(found) > 1:
                raise ValueError('duplicate native fresh PCM completion')
            if not found:
                return None
            return validate_fresh(found[0], ready, actor['uid'], interval, self.constants)
        # The native completion follows checked fsync/close of both files.
        # Seeing CREATE alone does not prove the reply JSON has been written.
        completion = self.wait_native(actor, 'fresh-reply-native-log', completed)
        completion_log = dict(actor['latest_native_log'])
        reply_file = self.collect_file(actor, remote)
        reply = validate_fresh(strict_json(Path(reply_file['path']).read_text()), ready, actor['uid'],
                               interval, self.constants)
        if reply != completion:
            raise ValueError('native fresh PCM completion and private reply differ')
        pcm_file = self.collect_file(actor, actor['app_files'] + reply['pcm_basename'])
        if pcm_file['bytes'] != reply['bytes']:
            raise ValueError('actual fresh PCM transfer length differs')
        correlation = phase_content(Path(pcm_file['path']).read_bytes(), self.reference)
        actor['fresh_snapshots'].append(dict(action=ready['action'], nonce=ready['nonce'],
            request_file=Path(request['path']).name, reply_file=Path(reply_file['path']).name,
            pcm_file=Path(pcm_file['path']).name, request_clock_interval=interval,
            observation=reply, correlation=correlation, native_completion=completion,
            completion_log=completion_log))
        self.note('actual-fresh-PCM-correlated', uid=actor['uid'], action=ready['action'])
        return reply

    def service_snapshot(self, actor, phase, *, active=True):
        self.serial += 1
        directory = self.output / (str(self.serial).zfill(5) + '-' + phase + '-' + str(actor['mode']))
        directory.mkdir()
        def capture():
            value = {}
            for key, command in [('uid_dump', 'hidumper -s 1903 -a "-C --get ' + str(actor['uid']) + '"'),
                                 ('all_dump', 'hidumper -s 1903 -a "-C --all"'),
                                 ('ans_dump', 'hidumper -s 3203 -a "--active"')]:
                text = self.actual(command, 'focus-' + key)
                path = directory / (key + '.txt');path.write_text(text + '\n')
                value[key + '_path'], value[key + '_sha256'] = str(path.resolve()), sha(path)
            return value
        value, interval = self.bracket(actor, 'service-' + phase, capture)
        value.update(phase=phase, actual_clock_interval=interval, observation=None)
        texts = [Path(value[key + '_path']).read_text() for key in ('uid_dump', 'all_dump', 'ans_dump')]
        if active:
            info = actor['background_started']
            value['observation'] = active_task(*texts, actor['uid'], actor['pid'], actor['bundle'],
                                               info['continuousTaskId'], info['notificationId'])
        else:
            if any(int(row['uid']) == actor['uid'] for row in records(texts[0])):
                return None
            if any(int(row['uid']) == actor['uid'] for row in records(texts[1])):
                return None
            # ANS can legitimately contain no notification once both actors stop.
            if 'no notification\n' not in texts[2]:
                own_id = actor['background_started']['notificationId']
                if any(int(row['OwnerUid']) == actor['uid'] and int(row['Id']) == own_id
                       for row in records(texts[2], notification=True)):
                    return None
        actor['service_snapshots'].append(value)
        self.save()
        return value

    def prepare(self):
        self.capture.prepare()
        output = self.command(['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
            '--read-only', '--cpus', '1', '--memory', '512m', '--pids-limit', '128',
            '--mount', 'type=volume,src=' + self.args.source_volume + ',dst=/ohos,readonly',
            '--mount', 'type=bind,src=' + str(HERE.parents[1]) + ',dst=/work,readonly',
            self.args.docker_image, 'python3', '/work/ci/capability-audit/audio_focus_observation.py',
            '--source-root', '/ohos'], 'focus-read-fixed-notification-contract', timeout=120)
        self.notification_contract = strict_json(output)
        (self.output / 'notification-contract.json').write_text(json.dumps(self.notification_contract, ensure_ascii=False, indent=2) + '\n')
        header = self.args.sdk / 'native/sysroot/usr/include/ohaudio/native_audiostream_base.h'
        self.constants = {}
        for name, constant in [('STOPPED', 'AUDIOSTREAM_STATE_STOPPED'), ('MIC', 'AUDIOSTREAM_SOURCE_TYPE_MIC'),
                               ('S16LE', 'AUDIOSTREAM_SAMPLE_S16LE')]:
            match = re.search(r'\b' + constant + r'\s*=\s*(\d+)', header.read_text())
            if not match:
                raise ValueError('actual public SDK enum definition unavailable: ' + constant)
            self.constants[name] = int(match.group(1))
        self.stopped = self.constants['STOPPED']
        self.value['common']['stopped_state'] = dict(value=self.stopped, header=str(header), sha256=sha(header))
        self.value['common']['sdk_audio_constants'] = self.constants
        _, self.reference = load_reference(self.capture.output / 'challenge/challenge.json',
                                           self.capture.output / 'challenge/challenge.pcm', self.run)
        for actor in self.value['actors'].values():
            self.token(actor, 'before-launch', expected=-1)
        self.save()

    def start_producer(self):
        c = self.capture
        if c.process is not None:
            raise ValueError('only one actual producer may run')
        wrapper = ('echo "$$" > ' + c.remote + '/producer.pid; '
            'awk \'{print $22}\' /proc/$$/stat > ' + c.remote + '/producer.start; '
            'unset LD_LIBRARY_PATH LD_PRELOAD; exec ' + c.remote + '/alsa_inject --input ' + c.remote +
            '/challenge.pcm --rate 48000 --channels 2 --repeat 60 --timeout-ms 90000')
        c.producer_argv = [str(self.args.hdc), '-t', self.args.target, 'shell', 'sh -c ' + shlex.quote(wrapper)]
        c.producer_log = (c.output / 'producer.log').open('xb')
        c.process = subprocess.Popen(c.producer_argv, stdout=c.producer_log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True)
        self.wait('actual-producer-feeding', lambda: '"event":"feeding"' in
                  (c.output / 'producer.log').read_text(errors='replace'), 10)
        c.value['producer_configuration'] = dict(PRODUCER)
        self.note('one-actual-independent-producer-feeding')

    def launch(self, actor):
        reply = self.actual('aa start -a EntryAbility -b ' + actor['bundle'], 'focus-launch-own-ordinary-app')
        if 'start ability successfully' not in reply.lower():
            raise ValueError('ordinary focus app launch failed')
        ui = GuestUi(self.command, self.args.hdc, self.args.target,
                     self.args.output / ('owner' if actor['mode'] == 1 else 'contender') / 'ui')
        def click_start():
            try:
                return ui.click(actor['bundle'], text='Start audio audit', label='focus-start-ordinary-app')
            except (NodeNotReady, LayoutNotReady):
                return None
        actor['start_action'] = self.wait('actual-start-button', click_start)
        actor['start_action']['layout_sha256'] = sha(actor['start_action']['layout'])
        actor['mic_action'] = decide(ui, self.capture.labels, False, 12)
        self.wait('committed-real-MIC-grant', lambda: self._mic_committed(actor))
        actor['process_before'] = self.process(actor, 'focus-process-before')
        actor['pid'] = actor['process_before']['pid']
        def notification_initial():
            rows = self.journal(actor)
            found = [r for r in rows if r.get('event') == 'notification_initial']
            if len(found) > 1:
                raise ValueError('duplicate notification authorization attempt')
            return found[0] if found else None
        initial = strict_json(self.wait('notification-initial', notification_initial)['detail'])
        if type(initial.get('enabled')) is not bool:
            raise ValueError('actual initial notification state missing')
        actor['notification_initial'] = initial['enabled']
        if not initial['enabled']:
            def allow_notification():
                try:
                    layout, path = ui.layout(bundle=DIALOG, label='focus-notification-permission')
                    node = notification_node(layout, self.notification_contract)
                except (NodeNotReady, LayoutNotReady):
                    return None
                left, top, width, height = node['rect']
                ui.shell('uitest uiInput click ' + str(left + width // 2) + ' ' + str(top + height // 2),
                         'focus-real-notification-allow')
                return dict(layout=str(path), layout_sha256=sha(path), selected_node=node,
                            decision='ALLOW', bundle=DIALOG)
            actor['notification_action'] = self.wait('real-notification-authorization', allow_notification)
        def started():
            rows = self.journal(actor)
            authorized = [r for r in rows if r.get('event') == 'notification_authorized']
            if authorized and strict_json(authorized[0]['detail']).get('enabled') is not True:
                raise ValueError('notification authorization did not persist')
            found = [r for r in rows if r.get('event') == 'background_started']
            if len(found) > 1:
                raise ValueError('multiple actual background tasks started')
            return found[0] if authorized and found else None
        info = strict_json(self.wait('real-background-started', started)['detail'])
        if any(type(info.get(k)) is not int or info[k] < 0 for k in ('continuousTaskId', 'notificationId')):
            raise ValueError('actual startBackgroundRunning IDs missing')
        actor['background_started'] = info
        self.token(actor, 'background', operation='query-background')
        self.service_snapshot(actor, 'active')
        self.note('actor-background-started', uid=actor['uid'], mode=actor['mode'])
        return actor

    def _mic_committed(self, actor):
        observation = strict_json(self.actual('unset LD_LIBRARY_PATH LD_PRELOAD; ' + self.capture.remote +
            '/audio_capture_token ' + self.run + ' ' + str(actor['uid']) + ' query ' + actor['bundle'],
            'focus-poll-MIC-commit'))
        state, _ = checked_token(observation, self.run, actor['uid'], allow_transition=True, bundle=actor['bundle'])
        if state != 0 or observation['before'] != 0:
            actor['tokens'].append(dict(phase='MIC-transition', observation=observation))
            self.save()
            return False
        self.token(actor, 'after-MIC')
        return True

    def wait_native(self, actor, label, predicate):
        def poll():
            rows = self.native_rows(actor, label)
            summaries = [r for r in rows if r.get('type') == 'event_summary']
            if summaries and summaries[-1].get('candidate_complete') is not True:
                raise ValueError('actual native focus session failed before ' + label)
            return predicate(rows)
        return self.wait(label, poll)

    def finished(self, actor, collect=True):
        rows = self.wait_native(actor, 'native-complete', lambda rows: rows if any(
            r.get('type') == 'event_summary' and r.get('mode') == actor['mode'] and
            r.get('candidate_complete') is True for r in rows) else None)
        stop = [r for r in rows if r.get('type') == 'event_stop']
        tail = [r for r in rows if r.get('type') == 'event_step' and r.get('name') in ('release', 'destroy')]
        if (len(stop) != 1 or stop[0].get('actual') != 0 or
                [r.get('name') for r in tail] != ['release', 'destroy'] or
                any(r.get('actual') != 0 for r in tail)):
            raise ValueError('actual Capturer Stop/Release/Destroy failed')
        def cleanup_journal():
            values = self.journal(actor)
            names = [r.get('event') for r in values]
            required = ('native_finished', 'background_stopped', 'background_cancel_observer_removed',
                        'background_suspend_observer_removed')
            if not all(name in names for name in required):
                return None
            if any(names.count(name) != 1 for name in required):
                raise ValueError('duplicate actual cleanup journal')
            done = strict_json(next(r['detail'] for r in values if r['event'] == 'native_finished'))
            if done != dict(native_status=1, native_still_running=False, background_failed=False):
                raise ValueError('UIAbility observed native failure or incomplete worker cleanup')
            return values
        self.wait('public-background-and-observer-cleanup', cleanup_journal)
        self.wait('service-task-and-notification-exit', lambda: self.service_snapshot(actor, 'cleanup', active=False))
        self.token(actor, 'final')
        self.token(actor, 'final-background', operation='query-background')
        actor['process_after'] = self.process(actor, 'focus-same-process-after')
        if collect:
            self.collect_actor(actor)
        self.note('actor-native-background-observers-clean', uid=actor['uid'])

    def collect_actor(self, actor, partial=False):
        if not partial:
            self.journal(actor, final=True)
        stem = 'audio-event-' + self.run + '-'
        raw = self.actual('if test -d ' + actor['app_files'] + '; then find ' + actor['app_files'] +
            ' -maxdepth 1 -name "' + stem + '*" | sort; fi', 'focus-all-own-private-evidence')
        paths = raw.splitlines()
        if len(paths) > 512:
            raise ValueError('unbounded focus evidence file set')
        for remote in paths:
            arkts = bool(re.fullmatch(re.escape(stem) + r'mode[12]-(?:permission|background-[0-9]{3})\.json',
                                     Path(remote).name))
            try:
                if arkts and '-background-' in Path(remote).name and Path(remote).name not in actor['files']:
                    value, _ = self.journal_record(actor, remote)
                else:
                    value = self.collect_file(actor, remote, native=not arkts)
                if remote.endswith('-results.log'):
                    actor['native_results_path'] = value['path']
                    actor['native_results_sha256'] = value['sha256']
            except Exception as error:
                if not partial:
                    raise
                actor.setdefault('partial_collection_errors', []).append(str(error))
        self.save()

    def execute(self):
        owner, contender = self.value['actors']['owner'], self.value['actors']['contender']
        self.start_producer()
        self.launch(owner)
        owner_begin = self.ready(owner, 'focus_begin')
        self.launch(contender)
        contender_begin = self.ready(contender, 'contender_start')
        abilities = self.output / 'both-live-ability-and-process-records.txt'
        abilities.write_text(self.actual('aa dump -a -u 100', 'focus-both-live-abilities') + '\n')
        self.value['common']['both_live_abilities'] = dict(path=str(abilities.resolve()), sha256=sha(abilities))
        self.service_snapshot(owner, 'both-background')
        self.service_snapshot(contender, 'both-background')
        self.fresh_snapshot(owner, owner_begin)
        self.fresh_snapshot(contender, contender_begin)
        for actor in (owner, contender):
            self.process(actor, 'focus-same-process-before-VOIP')
        self.ack(contender, contender_begin)
        def started(rows):
            found = [r for r in rows if r.get('type') == 'event_start_interval']
            if len(found) > 1:
                raise ValueError('multiple actual VOIP start intervals')
            if found:
                interval = found[0]
                if (interval.get('actual') != 0 or type(interval.get('before_ns')) is not int or
                        type(interval.get('after_ns')) is not int or
                        not 0 <= interval['after_ns'] - interval['before_ns'] < 2000000000):
                    raise ValueError('actual VOIP Start failed or clock invalid')
                return interval
            return None
        interval = self.wait_native(contender, 'actual-VOIP-Start', started)
        contender['actual_start_interval'] = interval
        stop = self.wait_native(owner, 'actual-forced-STOP-before-ACK', lambda rows: next(
            (r for r in reversed(rows) if forced_stop(r, interval, self.stopped)), None))
        owner['actual_forced_stop'] = stop
        self.note('actual-VOIP-caused-forced-STOP', actual_start_interval=interval, actual_forced_stop=stop)
        self.ack(owner, owner_begin)
        owner_end = self.ready(owner, 'focus_end', running=False)
        contender_end = self.ready(contender, 'contender_stop')
        self.ack(contender, contender_end)
        self.finished(contender, collect=False)
        # Natural public release, observer cleanup and service exit must finish
        # before permitting the owner's real MIC Start after focus release.
        self.ack(owner, owner_end)
        self.finished(owner)
        self.collect_actor(contender)
        process = self.capture.process
        status = process.wait(timeout=95)
        self.capture.producer_log.close();self.capture.producer_log = None
        log = self.capture.output / 'producer.log'
        producer_rows = [strict_json(line) for line in log.read_text().splitlines() if line.startswith('{')]
        played = [r for r in producer_rows if r.get('event') == 'played']
        expected = dict(event='played', frames=PRODUCER['expected_frames'], rate=48000, channels=2,
                        repeats=60, source_bytes=192000)
        if status != 0 or played != [expected]:
            raise ValueError('single real producer failed its exact full playback contract')
        self.capture.value['producer'] = dict(argv=self.capture.producer_argv, host_exit_code=status,
            log=str(log.resolve()), log_sha256=sha(log))
        self.capture.value['status'] = 'captured_NOT_independently_verified'
        self.complete = True
        self.value['status'] = 'captured_NOT_independently_verified'
        self.note('both-real-lifecycles-complete-and-producer-played')
        return self.save()

    def close(self):
        if self.closed:
            return
        self.closed = True
        errors = []
        for actor in self.value['actors'].values():
            try:
                self.native_rows(actor, 'before-owned-app-cleanup')
                self.collect_actor(actor, partial=not self.complete)
            except Exception as error:
                errors.append(str(error))
        try:
            self.capture.close()
        except Exception as error:
            errors.append(str(error))
        if self.capture.process is not None:
            log = self.capture.output / 'producer.log'
            if log.is_file():
                self.capture.value['producer'] = dict(argv=self.capture.producer_argv,
                    host_exit_code=self.capture.process.poll(), log=str(log.resolve()), log_sha256=sha(log))
        self.value['cleanup_errors'] = errors
        if errors:
            self.value['status'] = 'fail'
            self.value['failures'].extend(errors)
        self.save()
