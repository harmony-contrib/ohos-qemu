#!/usr/bin/env python3
"""Collect real AudioHaptic observations on an enclosing guest; never boot/build.

The frozen public API supplies no output-onset clock. This implementation
collects and independently checks playback/TIME/focus observations, but rejects
synchronization acceptance until an independently implemented onset anchor is
available. Host action timestamps and start Promises are never that anchor.
"""
import argparse
from array import array
import importlib
import json
from pathlib import Path
import re
import secrets
import shlex
import socket
import stat
import subprocess
import sys
import time
import wave

import batch_media_audio_haptic as base
import batch_media375_protocol as protocol
from batch_media_audio_capture_challenge import match_window, pcm_values, WINDOW
from enclosing_acceptance_guest import EnclosingAcceptanceGuest, validate_binding
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady, select_node
from hdc_transport import failed
from run_normal_hap_probe import require_normal_identity

HERE = Path(__file__).resolve().parent
SELF = Path(__file__).resolve()
ROLES = ('owner', 'contender', 'denied')
BUNDLES = {role: 'org.harmonycontrib.audiohaptic' + ('' if role == 'owner' else role) for role in ROLES}
PERMISSIONS = {'owner': ['ohos.permission.VIBRATE', 'ohos.permission.KEEP_BACKGROUND_RUNNING'],
               'contender': [], 'denied': []}
SCOPE = 'public_AudioHaptic_virtual_TIME_audio_dual_UID_observations_ONLY_sync_UNPROVEN'
OWNER_MODULE = HERE.parents[1]/'.tmp/parallel-capability-20261016/root_runtime_owner12.py'
MAP = HERE.parents[1] / 'docs/capability-audit/parallel/network/audio-observation-20261016.json'
LABEL = 'Haptic audit'

# These are new derived caller sources, not edits to the delivered foreground
# page. They use the real SDK105 array overload and ordinary audioPlayback mode.
BACKGROUND_IMPORTS = """import backgroundTaskManager from '@ohos.resourceschedule.backgroundTaskManager';
import wantAgent from '@ohos.wantAgent';
import notificationManager from '@ohos.notificationManager';
"""
BACKGROUND_MEMBERS = r"""
  private controlTimer: number = -1;
  private backgroundActive: boolean = false;
  private backgroundSubscribed: boolean = false;
  private taskId: number = -1;
  private notificationId: number = -1;
  private backgroundEvents: string[] = [];
  private backgroundOverflow: number = 0;
  private backgroundCleaning: boolean = false;

  private backgroundEvent(kind: string, detail: string): void {
    if (this.backgroundEvents.length >= 32) { this.backgroundOverflow++; return; }
    this.backgroundEvents.push(JSON.stringify({ kind: kind, monotonic_ns: this.now(), detail_json: detail,
      cleaning: this.backgroundCleaning }));
  }

  private readonly onBackgroundCancel = (info: backgroundTaskManager.ContinuousTaskCancelInfo): void => {
    this.backgroundEvent('cancel', JSON.stringify(info));
    if (!this.backgroundCleaning && this.player !== undefined) {
      this.player.stop().catch((error: BusinessError): void => {
        this.backgroundEvent('cancel_stop_error', JSON.stringify({ code: error.code, message: error.message }));
      });
    }
  };

  private readonly onBackgroundSuspend = (info: backgroundTaskManager.ContinuousTaskSuspendInfo): void => {
    this.backgroundEvent('suspend', JSON.stringify(info));
    if (info.suspendState && !this.backgroundCleaning && this.player !== undefined) {
      this.player.stop().catch((error: BusinessError): void => {
        this.backgroundEvent('suspend_stop_error', JSON.stringify({ code: error.code, message: error.message }));
      });
    }
  };

  private pollControl(): void {
    if (this.busy) { return; }
    try {
      const context = getContext(this) as common.UIAbilityContext;
      const path = context.filesDir + '/audio-haptic-request.json';
      if (fs.statSync(path).size > 8192) { return; }
      const raw = fs.readTextSync(path);
      if (!raw.endsWith('\n')) { return; }
      const request = JSON.parse(raw) as Request;
      if (request.run_id === this.run && !this.used.includes(request.operation_id)) { this.execute(); }
    } catch (error) {
      // Missing/incomplete request is never an ACK. The host's bounded wait fails.
      this.note = 'Waiting for a complete fresh owned request';
    }
  }

  private async background(request: Request): Promise<void> {
    const context = getContext(this) as common.UIAbilityContext;
    const began = this.now();
    if (request.action === 'authorize') {
      const initial = await notificationManager.isNotificationEnabled();
      this.append(request, 'return', 'notificationManager.initial', began, JSON.stringify({ enabled: initial }));
      if (!initial) { await notificationManager.requestEnableNotification(context); }
      const actual = await notificationManager.isNotificationEnabled();
      this.append(request, 'return', 'notificationManager.authorized', began, JSON.stringify({ enabled: actual }));
      if (!actual) { throw new Error('Actual notification authorization denied'); }
    } else if (request.action === 'background-start') {
      if (this.backgroundActive || this.backgroundSubscribed) { throw new Error('Existing background task'); }
      if (!await notificationManager.isNotificationEnabled()) { throw new Error('No real notification authorization'); }
      backgroundTaskManager.on('continuousTaskCancel', this.onBackgroundCancel);
      this.backgroundSubscribed = true;
      backgroundTaskManager.on('continuousTaskSuspend', this.onBackgroundSuspend);
      const target = await wantAgent.getWantAgent({ wants: [{ bundleName: context.abilityInfo.bundleName,
        abilityName: context.abilityInfo.name, moduleName: context.abilityInfo.moduleName }],
        operationType: wantAgent.OperationType.START_ABILITY, requestCode: 22,
        wantAgentFlags: [wantAgent.WantAgentFlags.CONSTANT_FLAG] });
      const actual = await backgroundTaskManager.startBackgroundRunning(context, ['audioPlayback'], target);
      this.backgroundActive = true;
      this.taskId = actual.continuousTaskId === undefined ? -1 : actual.continuousTaskId;
      this.notificationId = actual.notificationId;
      this.append(request, 'return', 'backgroundTaskManager.startBackgroundRunning', began, JSON.stringify(actual));
      if (this.taskId < 0) { throw new Error('Actual continuous task ID missing'); }
    } else if (request.action === 'background-stop') {
      this.backgroundCleaning = true;
      try {
        if (this.backgroundActive) {
          await backgroundTaskManager.stopBackgroundRunning(context);
          this.backgroundActive = false;
          this.append(request, 'return', 'backgroundTaskManager.stopBackgroundRunning', began, '{}');
        }
      } finally {
        if (this.backgroundSubscribed) {
          backgroundTaskManager.off('continuousTaskCancel', this.onBackgroundCancel);
          backgroundTaskManager.off('continuousTaskSuspend', this.onBackgroundSuspend);
          this.backgroundSubscribed = false;
        }
      }
    } else if (request.action === 'control-close') {
      if (this.backgroundActive || this.id >= 0 || (this.player !== undefined && !this.released)) {
        throw new Error('Release real player/resource/background task before closing control');
      }
      if (this.controlTimer >= 0) { clearInterval(this.controlTimer); this.controlTimer = -1; }
    } else if (request.action === 'arm') {
      if (this.controlTimer >= 0) { throw new Error('Already armed'); }
      this.controlTimer = setInterval((): void => { this.pollControl(); }, 50);
    }
    this.append(request, 'getters', 'backgroundTaskManager.observations', began,
      JSON.stringify({ active: this.backgroundActive, task_id: this.taskId, notification_id: this.notificationId,
        events: this.backgroundEvents, overflow: this.backgroundOverflow }));
  }
"""

TOKEN_SOURCE = protocol.TOKEN_SOURCE


def require(value, message):
    if not value: raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate evidence key: ' + key)
        result[key] = value
    return result


def loads(raw):
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def checked(value):
    path = Path(value['path'])
    require(path.is_absolute() and base.record(path)['sha256'] == value['sha256'], 'evidence bytes changed')
    return path


def descriptor(path):
    return base.record(path)


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    return descriptor(path)


def derived_page(run, role):
    require(role in ROLES and re.fullmatch('[a-f0-9]{32}', run), 'fixed role/fresh run required')
    source = base.PAGE.read_text().replace('__AUDIO_HAPTIC_RUN__', run)
    require(source.count('  private now(): number {') == 1, 'frozen base source insertion changed')
    source = BACKGROUND_IMPORTS + source.replace('  private now(): number {', BACKGROUND_MEMBERS+'\n  private now(): number {')
    source = source.replace("'stop', 'release', 'start-after-release']", "'stop', 'release', 'start-after-release', 'authorize', 'background-start', 'background-stop', 'arm', 'control-close']")
    source = source.replace("      if (request.action === 'init') {", "      if (['authorize', 'background-start', 'background-stop', 'arm', 'control-close'].includes(request.action)) {\n        await this.background(request);\n      } else if (request.action === 'init') {")
    source = source.replace('    // No state/getTime API exists.', "    this.append(request, 'getters', 'backgroundTaskManager.observations', this.now(),\n      JSON.stringify({ active: this.backgroundActive, task_id: this.taskId, notification_id: this.notificationId,\n        events: this.backgroundEvents, overflow: this.backgroundOverflow }));\n    // No state/getTime API exists.")
    if role == 'contender':
        source = source.replace('audio.StreamUsage.STREAM_USAGE_MEDIA', 'audio.StreamUsage.STREAM_USAGE_VOICE_COMMUNICATION')
    return source


def noise_wav(path, seconds):
    """Independent NRZ chips; known input, never claimed as captured output."""
    require(type(seconds) is int and 1 <= seconds <= 60, 'bounded input duration required')
    samples = array('h')
    for _ in range(48000*seconds//8):
        a, b = secrets.randbits(1), secrets.randbits(1)
        samples.extend([8192 if a else -8192, 8192 if b else -8192]*8)
    if sys.byteorder != 'little': samples.byteswap()
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed')); stream.writeframes(samples.tobytes())


def prepare(output, sdk, source_export, *, seconds=60):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    require(type(seconds) is int and 1 <= seconds <= 60, 'bounded preparation duration')
    source = base.verify_export(source_export); sdk_proof = base.check_sdk(sdk)
    bg = Path(sdk)/'ets/api/@ohos.resourceschedule.backgroundTaskManager.d.ts'
    require('AUDIO_PLAYBACK = 2' in bg.read_text() and 'bgModes: string[], wantAgent: WantAgent): Promise<ContinuousTaskNotification>' in bg.read_text(), 'real SDK105 audioPlayback overload required')
    run = secrets.token_hex(16); roles = {}
    # The public JSON contract limits EACH event to 5000ms. Adjacent events
    # have no pulse gaps; only aggregate TIME activity is claimed.
    for role in ROLES:
        directory = output/role; directory.mkdir()
        page = directory/'Index.ets'; page.write_text(base.PAGE.read_text().replace('__AUDIO_HAPTIC_RUN__', run))
        challenge_path = directory/'base-project-input.json'
        challenge = {'run_id': run, 'page': descriptor(page), 'template': descriptor(base.PAGE)}
        save_json(challenge_path, challenge)
        manifest_path = base.project(directory/'project', challenge_path, sdk, denied=role != 'owner')
        project = manifest_path.parent
        (project/'entry/src/main/ets/pages/Index.ets').write_text(derived_page(run, role))
        app_path = project/'AppScope/app.json5'; app = loads(app_path.read_text()); app['app']['bundleName'] = BUNDLES[role]; save_json(app_path, app)
        save_json(project/'AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': LABEL}]})
        module_path = project/'entry/src/main/module.json5'; module = loads(module_path.read_text())
        module['module']['requestPermissions'] = [{'name': p} for p in PERMISSIONS[role]]
        if role == 'owner': module['module']['abilities'][0]['backgroundModes'] = ['audioPlayback']
        save_json(module_path, module)
        # Keep SDK source inventory small: no copied SDK, binary, build or input WAV.
        manifest_path.unlink()
        manifest = {'schema_version': 1, 'scope': 'derived_public_AudioHaptic_source_ONLY_NOT_compiled', 'role': role,
            'bundle': BUNDLES[role], 'run_id': run, 'permissions': PERMISSIONS[role], 'sdk': sdk_proof,
            'base_page': descriptor(base.PAGE), 'coordinator': descriptor(SELF), 'source_hashes': {
                str(p.relative_to(project)): descriptor(p)['sha256'] for p in sorted(project.rglob('*')) if p.is_file()},
            'runtime_validated': False, 'ledger_closed': False}
        save_json(manifest_path, manifest)
        audio = directory/(run+'-stop.wav'); noise_wav(audio, seconds)
        pattern = []
        for start in range(0, seconds*1000, 5000):
            event = base.haptic(min(5000, seconds*1000-start))['Channels'][0]['Pattern'][0]
            event['Event']['StartTime'] = start; pattern.append(event)
        haptic = directory/(run+'-stop.json'); data = base.haptic(1000); data['Channels'][0]['Pattern'] = pattern; save_json(haptic, data)
        roles[role] = {'bundle': BUNDLES[role], 'project': str(project), 'manifest': descriptor(manifest_path),
            'audio': descriptor(audio), 'haptic': descriptor(haptic), 'duration_ms': seconds*1000,
            'permissions': PERMISSIONS[role]}
    token = output/'audio_haptic_token_observer.cpp'; token.write_text(TOKEN_SOURCE)
    observer = output/'audio_haptic375_time_observer.cpp'; observer.write_text(protocol.PASSIVE_SOURCE)
    value = {'schema_version': 1, 'scope': SCOPE, 'run_id': run, 'sdk': sdk_proof, 'fixed_source': source,
        'coordinator': descriptor(SELF), 'base_generator': descriptor(Path(base.__file__)), 'base_page': descriptor(base.PAGE),
        'protocol': descriptor(Path(protocol.__file__)), 'observer_source': descriptor(observer), 'token_source': descriptor(token), 'sdk_background': descriptor(bg),
        'notification_source_map': descriptor(MAP), 'roles': roles, 'runtime_validated': False, 'ledger_closed': False}
    save_json(output/'preparation.json', value)
    return output/'preparation.json'


def validate_preparation(path):
    value = loads(Path(path).read_text())
    require(value['scope'] == SCOPE and re.fullmatch('[a-f0-9]{32}', value['run_id']), 'fresh preparation required')
    for key in ('coordinator', 'protocol', 'base_generator', 'base_page', 'observer_source', 'token_source', 'notification_source_map'):
        checked(value[key])
    require(value['coordinator']['sha256'] == descriptor(SELF)['sha256'] and
            value['protocol'] == descriptor(Path(protocol.__file__)) and
            checked(value['token_source']).read_text() == TOKEN_SOURCE and
            checked(value['observer_source']).read_text() == protocol.PASSIVE_SOURCE, 'candidate source drift')
    base.verify_export(checked(value['fixed_source']['export']))
    for role in ROLES:
        entry = value['roles'][role]; manifest = loads(checked(entry['manifest']).read_text())
        require(entry['bundle'] == BUNDLES[role] and entry['permissions'] == PERMISSIONS[role] and
                manifest['role'] == role and manifest['run_id'] == value['run_id'], 'prepared role changed')
        project = Path(entry['project']); page = project/'entry/src/main/ets/pages/Index.ets'
        require(page.read_text() == derived_page(value['run_id'], role), 'derived actual page differs')
        for name, expected in manifest['source_hashes'].items():
            require(not Path(name).is_absolute() and '..' not in Path(name).parts and
                    descriptor(project/name)['sha256'] == expected, 'prepared project source changed')
        for key in ('audio', 'haptic'): checked(entry[key])
    return value


def actual_token(raw, run, role, identity, permission, expected, boot):
    return protocol.actual_token(raw, run=run, boot=boot, bundle=BUNDLES[role], identity=identity,
        permission=permission, expected=expected)


def root_admission(args):
    # The parent creates the lease and retains the locked open description. We
    # only verify its live nonce/config/parent/HDC handshake; never acquire one.
    require(all(getattr(args, name, None) for name in ('root_lease', 'root_lease_nonce', 'root_config', 'root_output')),
        'explicit same-parent live root lease/config required')
    require(OWNER_MODULE.is_file() and not OWNER_MODULE.is_symlink(), 'frozen root owner12 module required')
    sys.path.insert(0, str(OWNER_MODULE.parent))
    try:
        owner = importlib.import_module('root_runtime_owner12')
        require(Path(owner.__file__).resolve() == OWNER_MODULE.resolve(), 'root owner module path differs')
        proof = owner.verify(descriptor(args.root_lease), args.root_lease_nonce,
            descriptor(args.root_config), args.root_output.resolve(), args.hdc)
    finally:
        sys.path.pop(0)
    return {'owner_module': descriptor(OWNER_MODULE), 'lease': descriptor(args.root_lease),
        'config': descriptor(args.root_config), 'proof': proof}


def audio_values(path):
    with wave.open(str(path)) as stream:
        require((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) ==
                (2, 2, 48000, 'NONE'), 'actual WAV must be stereo48k/16bit PCM')
        require(0 < stream.getnframes() <= 48000*120, 'empty/header-only or unbounded actual audio')
        return pcm_values(stream.readframes(stream.getnframes()))


def audio_progress(reference_path, capture_path, *, minimum_frames=24000, allow_prefix=False):
    """Validate two disjoint real data windows and source progression, not time."""
    reference, capture = audio_values(reference_path), audio_values(capture_path)
    nonzero = [i//2 for i in range(0, len(capture), 2) if abs(capture[i]) > 256 or abs(capture[i+1]) > 256]
    require(nonzero and nonzero[-1]-nonzero[0]+1 >= max(minimum_frames, 2*WINDOW), 'fresh non-silent playback too short')
    first, last = nonzero[0], nonzero[-1]+1
    # Mixer ramps may affect the edge. Keep the same bounded 128frame trim at
    # both ends; require full real correlation, not a timer or a signal level.
    first += 128; last -= 128
    if allow_prefix:
        # The focus capture begins while owner is playing. Check only its final
        # independent half-second as contender audio; retain all earlier data.
        first = max(first, last-minimum_frames)
    require(last-first >= max(minimum_frames, 2*WINDOW), 'actual playback lacks independent disjoint windows')
    head = match_window(capture[first*2:(first+WINDOW)*2], reference)
    tail = match_window(capture[(last-WINDOW)*2:last*2], reference)
    require(min(head['minimum_correlation'], tail['minimum_correlation']) >= .99999,
            'fresh actual PCM is mixed/distorted beyond the declared correlation bound')
    advance = last-first-WINDOW
    require(tail['source_frame']-head['source_frame'] == advance, 'old audio replay/discontinuity/sample rate mismatch')
    return {'first_capture_frame': first, 'last_capture_frame_exclusive': last,
            'first_window': head, 'last_window': tail, 'source_advance_frames': advance,
            'output_onset_monotonic_ns': None, 'synchronization_verified': False}


def background_join(uid_text, all_text, ans_text, uid, pid, bundle, task, notification):
    from audio_focus_observation import records, integer
    own = [r for r in records(uid_text) if integer(r, 'uid') == uid]
    all_own = [r for r in records(all_text) if integer(r, 'uid') == uid]
    require(len(own) == len(all_own) == 1, 'one real owner background task required')
    row = all_own[0]
    for entry in (own[0], row):
        require(integer(entry, 'pid', 1) == pid and integer(entry, 'continuousTaskId') == task and
                integer(entry, 'notificationId') == notification and entry.get('abilityName') == 'EntryAbility', 'task PID/UID/ID join failed')
    require(row.get('bundleName') == bundle and row.get('backgroundModes') == '2,' and row.get('suspendState') == 'false' and
            row.get('wantAgentBundleName') == bundle and row.get('isCombinedTaskNotification') == 'false',
            'real ordinary audioPlayback task missing/suspended/wrong mode')
    notifications = [r for r in records(ans_text, notification=True) if integer(r, 'OwnerUid') == uid and
                     integer(r, 'Id') == notification and r.get('Label') == row.get('notificationLabel')]
    require(len(notifications) == 1, 'actual owned active notification missing')
    return {'task': row, 'notification': notifications[0]}


def background_absent(uid_text, all_text, ans_text, uid, notification):
    from audio_focus_observation import records, integer
    require(not any(integer(row, 'uid') == uid for text in (uid_text, all_text) for row in records(text)),
            'owned audioPlayback task remained after public cleanup')
    if ans_text.strip().endswith('no notification'):
        require(not re.search('denied|invalid|error', ans_text, re.I), 'notification cleanup dump failed')
    else:
        require(not any(integer(row, 'OwnerUid') == uid and integer(row, 'Id') == notification for row in records(ans_text, notification=True)),
                'actual owner background notification remained')


def no_onset_anchor(receipt=None):
    # There is deliberately no adapter which trusts a declared timestamp, a
    # Promise, a log's wall time or the first observed file byte. Such an adapter
    # would silently replace the missing independent clock implementation.
    if receipt is not None:
        raise ValueError('No supported independent AudioHaptic output-onset anchor; supplied claims are not accepted')
    return {'synchronization_verified': False, 'accepted': False,
            'reason': 'Public AudioHaptic API and frozen first-frame latency log do not establish a stream-bound MONOTONIC output onset'}


def background_callbacks(rows):
    count = 0
    for row in rows:
        if row['api'] != 'backgroundTaskManager.observations': continue
        value = row['value']
        require(type(value['overflow']) is int and value['overflow'] == 0 and isinstance(value['events'], list) and len(value['events']) <= 32,
                'background observer overflow/truncation')
        for raw in value['events']:
            event = loads(raw); require(type(event['monotonic_ns']) is int and 0 < event['monotonic_ns'] <= row['after_ns'] and
                type(event['cleaning']) is bool and event['kind'] in ('cancel', 'suspend', 'cancel_stop_error', 'suspend_stop_error'),
                'invalid actual background callback')
            detail = loads(event['detail_json'])
            require(event['kind'] not in ('cancel_stop_error', 'suspend_stop_error'), 'real cancellation failed to stop player')
            if not event['cleaning']:
                require(event['kind'] != 'cancel' and (event['kind'] != 'suspend' or detail.get('suspendState') is False),
                        'background cancellation/suspension cannot satisfy renderer focus')
            count += 1
    return count


def mapped(path, path_map):
    """Explicit Linux bind aliases only; preserve original receipt/argv bytes."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and isinstance(path_map, list) and len(path_map) <= 2, 'bounded explicit helper path aliases required')
    matches = []
    for row in path_map:
        require(set(row) == {'from', 'to'}, 'exact helper path alias fields required')
        old, new = Path(row['from']), Path(row['to'])
        require(old.is_absolute() and new.is_absolute() and old != Path('/') and new != Path('/') and
                '..' not in old.parts and '..' not in new.parts, 'unsafe helper path alias')
        if path.is_relative_to(old): matches.append(new/path.relative_to(old))
    require(len(matches) <= 1, 'ambiguous helper path aliases')
    return matches[0] if matches else path


def verify_helper(spec, source, arch):
    from avc_media_contract import verify_elf, runtime_identity
    binary = checked(spec['binary']); receipt = checked(spec['build']); value = loads(receipt.read_text())
    aliases = spec.get('path_map', [])
    def artifact(row): return {'path': str(mapped(row['path'], aliases)), 'sha256': row['sha256']}
    require(value.get('scope') == 'compile_link_ONLY_NOT_guest' and value.get('arch') == arch and
            artifact(value['source']) == source and checked(artifact(value['source'])) == checked(source) and
            artifact(value['binary']) == spec['binary'],
            'actual helper source/ABI/build receipt required')
    verify_elf(binary.read_bytes(), arch)
    commands = value.get('commands', [])
    require(commands and any(str(checked(source)) in [str(mapped(arg, aliases)) if isinstance(arg, str) and arg.startswith('/') else arg
                for arg in row.get('argv', [])] for row in commands), 'actual helper compilation command absent')
    for row in commands:
        require(type(row.get('exit_code')) is int and row['exit_code'] == 0 and checked(artifact(row['log'])).is_file(),
                'actual helper build command/log failed')
    require(value.get('libraries'), 'actual product-linked helper DSOs required')
    for row in value['libraries']:
        require(re.fullmatch('/(?:system|vendor)/lib(?:64)?/[A-Za-z0-9_./-]+', row['guest_path']) and
                '..' not in Path(row['guest_path']).parts, 'fixed actual guest DSO path required')
        require(runtime_identity(checked(artifact(row['file'])).read_bytes(), arch) == row['runtime_sha256'], 'actual linked DSO runtime bytes changed')
    return {**value, 'original_build_receipt': descriptor(receipt), 'path_map': aliases,
            'libraries': [{**row, 'original_file': row['file'], 'file': artifact(row['file'])} for row in value['libraries']]}


def process_identity(raw, pid, uid):
    require(type(pid) is int and pid > 1 and type(uid) is int and uid//200000 == 100, 'real ordinary process identity required')
    require(raw.count('\nQEMU_PROCESS_STAT\n') == 1, 'actual status/stat boundary missing')
    status, process_stat = raw.split('\nQEMU_PROCESS_STAT\n')
    match = re.search(r'(?m)^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$', status)
    require(match and all(int(v) == uid for v in match.groups()), 'kernel process UID differs from BMS')
    require(process_stat.startswith(str(pid)+' (') and ') ' in process_stat, 'actual kernel PID mismatch')
    fields = process_stat.strip().rsplit(') ', 1)[1].split()
    require(len(fields) >= 20 and fields[19].isdigit() and int(fields[19]) > 0, 'actual process start generation absent')
    return {'pid': pid, 'uid': uid, 'start_ticks': int(fields[19])}


def mapped_haptic(raw):
    matches = []
    for line in raw.splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or Path(fields[5]).name != 'libaudio_haptic.z.so': continue
        require(re.fullmatch('[0-9a-f]+-[0-9a-f]+', fields[0]) and re.fullmatch('[rwxps-]{4}', fields[1]) and
                re.fullmatch('[0-9a-f]+', fields[2]) and re.fullmatch('[0-9a-f]+:[0-9a-f]+', fields[3]) and
                fields[4].isdigit() and int(fields[4]) > 0 and
                re.fullmatch('/system/lib(?:64)?/[A-Za-z0-9_./-]+', fields[5]) and '..' not in Path(fields[5]).parts,
                'actual AudioHaptic mapping is deleted/anonymous/malformed')
        matches.append((fields[5], int(fields[4])))
    require(matches and len(set(matches)) == 1, 'one actual mapped AudioHaptic product DSO required')
    return {'guest_path': matches[0][0], 'inode': matches[0][1]}


def verify_callers(inputs, preparation, env, output, command):
    from batch_apps_contact_picker_coordinator import verify_sdk_project, verify_signed_hap_artifacts, hap_contents, source_rows
    results = {}
    for role in ROLES:
        spec = inputs['actors'][role]
        require(Path(spec['source_project']).resolve() == Path(preparation['roles'][role]['project']).resolve(),
                'SDK compiled another prepared caller source project')
        sdk = verify_sdk_project(spec)
        manifest = loads(checked(preparation['roles'][role]['manifest']).read_text())
        compiled = source_rows(loads(checked(spec['sdk_evidence']).read_text()), spec['sdk_project'])
        require(all(compiled.get(name) == expected for name, expected in manifest['source_hashes'].items()),
                'SDK receipt did not compile every prepared caller source byte')
        signature = verify_signed_hap_artifacts(checked(spec['signed_hap']), BUNDLES[role], PERMISSIONS[role], env['udid'],
            inputs['signer_dist'], inputs.get('signer_jar'), Path(output)/role, command)
        require(hap_contents(checked(spec['unsigned_hap']))[1] == hap_contents(checked(spec['signed_hap']))[1],
                'actual signed and SDK-compiled caller payload differ')
        results[role] = {'sdk': sdk, 'signature': signature}
    return results


class Coordinator:
    def __init__(self, args):
        self.admission = root_admission(args)
        self.args = args; self.output = args.output.resolve(); self.output.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.preparation = validate_preparation(args.preparation); self.run = self.preparation['run_id']
        self.inputs = loads(args.inputs.read_text()); self.guest = EnclosingAcceptanceGuest(args.boot, args.archive, args.hdc, self.output/'guest')
        self.boot = self.guest.env['boot_id']; self.remote = '/data/local/tmp/audio-haptic-'+self.run
        self.value = {'schema_version': 1, 'scope': SCOPE, 'status': 'collecting', 'run_id': self.run, 'boot_id': self.boot,
            'archive': descriptor(args.archive), 'boot': descriptor(args.boot), 'preparation': descriptor(args.preparation),
            'inputs': descriptor(args.inputs), 'coordinator': descriptor(SELF), 'root_admission': self.admission,
            'commands': [], 'observations': [], 'actions': [], 'qmp': [],
            'actors': {}, 'foregrounds': [], 'captures': {}, 'service_snapshots': [], 'tokens': [], 'guest_libraries': {}, 'errors': [], 'cleanup_errors': [],
            'cleanup_complete': False, 'synchronization_verified': False, 'first_artifact_behavior_gate_passed': False,
            'ledger_closed': False}
        self.ui = GuestUi(self.command, args.hdc, self.guest.target, self.output/'ui')
        self.capture = None; self.pending_capture = None; self.observer = None; self.observer_log = None; self.armed = set()
        self.helpers = {}; self.token_ids = {}; self.save()

    def save(self):
        self.value['enclosing_guest_commands'] = self.guest.report['commands']
        return save_json(self.output/'evidence.json', self.value)

    def text(self, raw, label):
        path = self.output/('raw-'+secrets.token_hex(8)+'-'+label+'.txt')
        with path.open('x') as stream: stream.write(raw)
        return descriptor(path)

    def command(self, argv, label):
        root_admission(self.args)
        self.guest.healthy(); argv = list(map(str, argv))
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        log = self.text(result.stdout+result.stderr, 'transport')
        self.value['commands'].append({'argv': argv, 'label': label, 'exit_code': result.returncode, 'log': log}); self.save()
        require(result.returncode == 0 and not failed(result.stdout, result.stderr), 'actual transport failed: '+label)
        return result.stdout.replace('\r', '')

    def shell(self, script, label):
        root_admission(self.args)
        raw = self.guest.shell(script, label); self.save(); return raw

    def observe(self, script, label):
        raw = self.shell(script, label); ref = self.text(raw, label)
        self.value['observations'].append({'raw': ref, 'script': script,
            'command': len(self.guest.report['commands'])-1})
        self.save(); return ref

    def receive(self, remote, label, uid=None):
        quote = shlex.quote(remote)
        before = self.shell('test -f '+quote+' && test ! -L '+quote+" && stat -c '%u %a %s %i' "+quote+' && sha256sum '+quote, label+'-stat')
        lines = before.splitlines(); require(len(lines) == 2, 'actual owned file stat required')
        owner, mode, size, inode = map(int, lines[0].split()); expected_sha = lines[1].split()[0]
        require(0 < size <= 64*1024*1024 and re.fullmatch('[0-9a-f]{64}', expected_sha), 'bounded real file required')
        if uid is not None: require(owner == uid and mode == 600, 'caller private raw evidence must be UID-owned0600')
        path = self.output/(secrets.token_hex(4)+'-'+label)
        self.command([self.args.hdc, '-t', self.guest.target, 'file', 'recv', remote, path], label+'-recv')
        after = self.shell('test -f '+quote+' && test ! -L '+quote+" && stat -c '%u %a %s %i' "+quote+' && sha256sum '+quote, label+'-stat-after')
        require(before == after and descriptor(path)['sha256'] == expected_sha and path.stat().st_size == size, 'file changed during transfer')
        return {'file': descriptor(path), 'remote': remote, 'uid': owner, 'mode': mode, 'inode': inode, 'stat': self.text(before, label+'-metadata')}

    def publish(self, path, remote, uid, *, replace=False):
        staging = self.remote+'/stage-'+secrets.token_hex(8)
        self.command([self.args.hdc, '-t', self.guest.target, 'file', 'send', path, staging], 'stage-owned-input')
        guard = '' if replace else 'test ! -e '+shlex.quote(remote)+' && test ! -L '+shlex.quote(remote)+' && '
        self.shell('chmod 0600 '+staging+' && chown '+str(uid)+':'+str(uid)+' '+staging+
                   ' && test "$(sha256sum '+staging+' | cut -d " " -f 1)" = '+descriptor(path)['sha256']+
                   ' && '+guard+'mv '+staging+' '+shlex.quote(remote), 'commit-owned-input')

    def actor(self, role): return self.value['actors'][role]

    def token(self, role, permission='ohos.permission.VIBRATE'):
        actor = self.actor(role); expect = 0 if permission in PERMISSIONS[role] else -1
        before = self.observe('bm dump -n '+BUNDLES[role], 'BMS-before-token-'+role)
        require(protocol.bms_identity(checked(before).read_text(), BUNDLES[role]) == actor['identity'], 'BMS identity changed before token query')
        raw = self.observe(protocol.token_script(self.remote, self.run, self.boot, BUNDLES[role], actor['uid'], permission), 'token-'+role)
        after = self.observe('bm dump -n '+BUNDLES[role], 'BMS-after-token-'+role)
        require(protocol.bms_identity(checked(after).read_text(), BUNDLES[role]) == actor['identity'], 'BMS identity changed after token query')
        row = actual_token(checked(raw).read_text(), self.run, role, actor['identity'], permission, expect, self.boot)
        if role in self.token_ids: require(row['token_id'] == self.token_ids[role], 'actual caller token replaced')
        self.token_ids[role] = row['token_id']; item = {'role': role, 'permission': permission,
            'bms_before': before, 'raw': raw, 'bms_after': after, 'value': row}
        self.value['tokens'].append(item); self.save(); return row

    def foreground(self, role):
        self.shell('aa start -b '+BUNDLES[role]+' -a EntryAbility -m entry -u 100', 'foreground-'+role)
        end = time.monotonic()+15
        while time.monotonic() < end:
            try:
                layout, path = self.ui.layout(bundle=BUNDLES[role], label='foreground-'+role)
                select_node(layout, BUNDLES[role], identifier='audio_haptic_run', clickable=True)
                self.actor(role)['foreground_layout'] = descriptor(path)
                self.process(role)
                self.value['foregrounds'].append({'role': role, 'layout': descriptor(path), 'host_monotonic_ns': time.monotonic_ns()})
                self.save(); return
            except (NodeNotReady, LayoutNotReady): time.sleep(.1)
        raise ValueError('actual AudioHaptic UI did not become visible')

    def process(self, role):
        actor = self.actor(role)
        raw = self.shell('pidof '+BUNDLES[role], 'actual-pid-'+role)
        require(re.fullmatch('[1-9][0-9]*', raw.strip()), 'one actual caller process required')
        pid = int(raw.strip())
        if 'pid' in actor: require(pid == actor['pid'], 'caller restarted during observation')
        raw = self.shell('cat /proc/'+str(pid)+'/status; echo QEMU_PROCESS_STAT; cat /proc/'+str(pid)+'/stat', 'actual-process-'+role)
        value = process_identity(raw, pid, actor['uid'])
        if 'process_start' in actor: require(value == actor['process_start'], 'actual process generation changed')
        actor['pid'] = pid; actor['process_start'] = value
        actor.setdefault('process_records', []).append(self.text(raw, 'process-'+role)); self.save()

    def journal(self, role):
        item = self.receive(self.actor(role)['files']+'audio-haptic-'+self.run+'.jsonl', 'journal-'+role, self.actor(role)['uid'])
        self.actor(role)['journal'] = item
        rows = base.parse_hap(checked(item['file']).read_text(), self.run, self.boot, self.actor(role)['uid'])
        self.save(); return rows

    def notification(self):
        mapping = loads(MAP.read_text()); contract = mapping['authorization_dialog']['translations']
        layout, path = self.ui.layout(label='real-notification-dialog')
        for translation in contract.values():
            try:
                select_node(layout, 'com.ohos.notificationdialog', text=translation['group_label_notification'].replace('%s', LABEL))
                node = select_node(layout, 'com.ohos.notificationdialog', text=translation['ALLOW'], clickable=True)
                x, y, w, h = node['rect']; self.shell('uitest uiInput click '+str(x+w//2)+' '+str(y+h//2), 'allow-real-owner-notification')
                self.value['notification_action'] = {'layout': descriptor(path), 'node': node, 'source_map': descriptor(MAP)}
                return
            except NodeNotReady: continue
        raise NodeNotReady('actual current owner notification dialog not yet visible')

    def action(self, role, action, *, expected_error=None):
        operation = secrets.token_hex(16)
        request = {'schema_version': 1, 'run_id': self.run, 'boot_id': self.boot, 'operation_id': operation,
            'action': action, 'case_id': 'stop', 'mute_audio': False, 'mute_haptics': role == 'contender', 'fast': False}
        path = self.output/('request-'+operation+'.json'); save_json(path, request)
        before = self.token(role); self.publish(path, self.actor(role)['files']+'audio-haptic-request.json', self.actor(role)['uid'], replace=True)
        if role not in self.armed:
            self.ui.click(BUNDLES[role], identifier='audio_haptic_run', label='actual-arm-'+role)
        deadline = time.monotonic()+15; handled_dialog = False
        while time.monotonic() < deadline:
            if action == 'authorize' and not handled_dialog:
                try: self.notification(); handled_dialog = True
                except (NodeNotReady, LayoutNotReady): pass
            remote = self.actor(role)['files']+'audio-haptic-'+self.run+'.jsonl'
            if self.shell('if test -f '+remote+'; then tail -c 1 '+remote+' | od -An -tu1; fi', 'journal-newline').strip() == '10':
                raw = self.shell('cat '+remote, 'read-control-journal')
                # A control operation can still be in progress; do not feed a
                # partial operation to the final strict parser.
                rows = [loads(line) for line in raw.splitlines()]
                terminal = [r for r in rows if r.get('operation_id') == operation and r.get('event') in ('complete', 'error')]
                if len(terminal) == 1:
                    actual = terminal[0]
                    require((expected_error is None and actual['event'] == 'complete') or
                            (expected_error is not None and actual['event'] == 'error' and actual['error_code'] == expected_error), 'actual public call failed/unexpectedly succeeded: '+action)
                    after = self.token(role)
                    item = {'role': role, 'action': action, 'operation': operation, 'request': descriptor(path),
                        'terminal': actual, 'control_interval_ns': [before['before_ns'], after['after_ns']], 'expected_error': expected_error}
                    self.value['actions'].append(item)
                    if action == 'arm': self.armed.add(role)
                    if action == 'control-close': self.armed.discard(role)
                    self.save(); return item
            time.sleep(.05)
        raise ValueError('actual request exceeded original15s deadline: '+role+'/'+action)

    def qmp(self, command):
        root_admission(self.args)
        self.guest.healthy(); path = Path(self.guest.env['qmp_socket'])
        require(stat.S_ISSOCK(path.stat().st_mode), 'actual owned enclosing QMP socket required')
        records = []
        item = {'command': command, 'records': records, 'host_monotonic_ns': time.monotonic_ns()}
        self.value['qmp'].append(item); self.save()
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(10); connection.connect(str(path))
            with connection.makefile('rb') as stream:
                greeting = loads(stream.readline()); require('QMP' in greeting, 'actual QMP greeting absent'); records.append(greeting)
                for label, execute, arguments in [('capabilities', 'qmp_capabilities', None), ('request', 'human-monitor-command', {'command-line': command})]:
                    nonce = secrets.token_hex(16); request = {'execute': execute, 'id': nonce}
                    if arguments is not None: request['arguments'] = arguments
                    connection.sendall(json.dumps(request).encode()+b'\n'); records.append({'sent': request})
                    while True:
                        raw = stream.readline(); require(raw, 'actual QMP disconnected'); reply = loads(raw); records.append(reply)
                        if reply.get('id') == nonce:
                            require('error' not in reply and 'return' in reply, 'actual QMP failed')
                            break
        item['finished_host_ns'] = time.monotonic_ns(); self.save()
        value = reply['return']; require(isinstance(value, str), 'actual HMP text required')
        return value

    def start_capture(self, phase):
        require(self.capture is None and self.pending_capture is None, 'only this coordinator owned capture can be stopped')
        existing = strip_hmp(self.qmp('info capture')); require(not existing.strip(), 'another owner already has QEMU audio capture')
        path = self.output/(self.run+'-'+phase+'.wav'); require(not path.exists(), 'fresh capture path required')
        require(not re.search(r'[\s\x00-\x1f]', str(path)), 'HMP path cannot contain whitespace')
        # Mark the intent before the call: a lost QMP reply must not leave an
        # untracked capture and then claim the guest is safe to reuse.
        self.pending_capture = (phase, path)
        self.value.setdefault('capture_intervals', {})[phase] = {'start_host_ns': time.monotonic_ns(), 'start_reply_observed': False}
        require(not strip_hmp(self.qmp('wavcapture '+str(path)+' ohos_audio 48000 16 2')).strip(), 'actual wavcapture failed')
        info = strip_hmp(self.qmp('info capture'))
        match = re.fullmatch(r'\[(\d+)\]: Capturing audio\(48000,16,2\) to '+re.escape(str(path))+r': \d+ bytes\n?', info)
        require(match, 'actual owned capture identity/format differs')
        self.capture = (phase, path, int(match.group(1))); self.pending_capture = None
        self.value['capture_intervals'][phase].update(start_host_ns=time.monotonic_ns(), start_reply_observed=True)

    def stop_capture(self):
        if self.capture is None and self.pending_capture is not None:
            phase, path = self.pending_capture
            info = strip_hmp(self.qmp('info capture'))
            if not info.strip(): self.pending_capture = None; return
            match = re.fullmatch(r'\[(\d+)\]: Capturing audio\(48000,16,2\) to '+re.escape(str(path))+r': \d+ bytes\n?', info)
            require(match, 'cannot safely identify capture after lost start acknowledgement')
            self.capture = (phase, path, int(match.group(1))); self.pending_capture = None
        if self.capture is None: return
        phase, path, index = self.capture
        require(not strip_hmp(self.qmp('stopcapture '+str(index))).strip(), 'actual stopcapture failed')
        require(not strip_hmp(self.qmp('info capture')).strip(), 'owned capture still active')
        self.capture = None; require(path.is_file() and not path.is_symlink(), 'actual WAV file absent')
        path.chmod(0o600); self.value['captures'][phase] = descriptor(path); self.save()
        self.value['capture_intervals'][phase]['stop_host_ns'] = time.monotonic_ns(); self.save()

    def service(self, phase, *, cleanup=False):
        actor = self.actor('owner'); texts = {}
        before = self.token('owner')
        for key, script in [('uid', 'hidumper -s 1903 -a "-C --get '+str(actor['uid'])+'"'),
                            ('all', 'hidumper -s 1903 -a "-C --all"'), ('ans', 'hidumper -s 3203 -a "--active"')]:
            texts[key] = self.text(self.shell(script, phase+'-'+key), 'service-'+key)
        after = self.token('owner'); row = {'phase': phase, 'raw': texts, 'interval_ns': [before['before_ns'], after['after_ns']]}
        if not cleanup:
            info = self.background_info(); row['join'] = background_join(*(checked(texts[k]).read_text() for k in ('uid', 'all', 'ans')),
                actor['uid'], actor['pid'], BUNDLES['owner'], info['continuousTaskId'], info['notificationId'])
        else:
            info = self.background_info()
            background_absent(*(checked(texts[k]).read_text() for k in ('uid', 'all', 'ans')), actor['uid'], info['notificationId'])
        self.value['service_snapshots'].append(row); self.save()

    def background_info(self):
        rows = self.journal('owner')
        infos = [r['value'] for r in rows if r['event'] == 'return' and r['api'] == 'backgroundTaskManager.startBackgroundRunning']
        require(len(infos) == 1 and type(infos[0].get('continuousTaskId')) is int and type(infos[0].get('notificationId')) is int,
                'actual background task/notification IDs absent')
        return infos[0]

    def setup(self):
        self.guest.start()
        self.account('before')
        self.shell('test ! -e '+self.remote+' && mkdir -m 0700 '+self.remote, 'owned-root-directory')
        from avc_media_contract import runtime_identity
        for name, source in [('passive', self.preparation['observer_source']), ('token', self.preparation['token_source'])]:
            spec = self.inputs['helpers'][name]; receipt = verify_helper(spec, source, self.guest.env['guest_arch']); self.helpers[name] = receipt
            remote_name = 'passive' if name == 'passive' else 'token'; binary = checked(spec['binary'])
            self.command([self.args.hdc, '-t', self.guest.target, 'file', 'send', binary, self.remote+'/'+remote_name], 'deploy-real-'+name)
            self.shell('chmod 0700 '+self.remote+'/'+remote_name+' && test "$(sha256sum '+self.remote+'/'+remote_name+' | cut -d " " -f 1)" = '+descriptor(binary)['sha256'], 'verify-real-'+name)
            self.value['guest_libraries'][name] = []
            for lib in receipt['libraries']:
                actual = self.receive(lib['guest_path'], 'product-DSO')
                require(runtime_identity(checked(actual['file']).read_bytes(), self.guest.env['guest_arch']) == lib['runtime_sha256'], 'helper linked to different actual package DSO')
                self.value['guest_libraries'][name].append(actual)
        verified = verify_callers(self.inputs, self.preparation, self.guest.env, self.output/'signatures', self.command)
        for role in ROLES:
            spec = self.inputs['actors'][role]
            # Installation belongs to the enclosing suite; never grant, alter
            # profiles, replace an installed app or silently reuse another HAP.
            bms_ref = self.observe('bm dump -n '+BUNDLES[role], 'BMS-'+role); raw = checked(bms_ref).read_text()
            identity = protocol.bms_identity(raw, BUNDLES[role]); uid = identity['uid']
            bms = loads(raw.removeprefix(BUNDLES[role]+':\n')); paths = set()
            def visit(item):
                if isinstance(item, dict):
                    for key, child in item.items():
                        if key == 'hapPath' and isinstance(child, str): paths.add(child)
                        else: visit(child)
                elif isinstance(item, list):
                    for child in item: visit(child)
            visit(bms); require(len(paths) == 1, 'one actual installed entry HAP path required')
            installed = self.receive(next(iter(paths)), 'installed-'+role)
            require(installed['file']['sha256'] == spec['signed_hap']['sha256'], 'actual BMS installed HAP differs')
            files = '/data/app/el2/100/base/'+BUNDLES[role]+'/haps/entry/files/'
            self.value['actors'][role] = {'bundle': BUNDLES[role], 'uid': uid, 'identity': identity, 'BMS': bms_ref,
                'installed_hap': installed, 'sdk': verified[role]['sdk'], 'signature': verified[role]['signature'], 'files': files}
            self.token(role)
        require(len({self.actor(r)['uid'] for r in ROLES}) == 3 and
            len({self.actor(r)['identity']['token_id'] for r in ROLES}) == 3, 'three distinct normal UIDs and tokens required')
        # Foreground all callers once, before creating observer/capture. Root's
        # actual UI installation/permission setup is not replaced by a timer.
        for role in ROLES:
            self.foreground(role)
            self.shell('test -d '+self.actor(role)['files']+' && test ! -L '+self.actor(role)['files']+
                ' && test "$(stat -c %u '+self.actor(role)['files']+')" = '+str(self.actor(role)['uid']), 'actual-private-directory')
            empty = self.output/('empty-private-journal-'+role); empty.write_bytes(b'')
            self.publish(empty, self.actor(role)['files']+'audio-haptic-'+self.run+'.jsonl', self.actor(role)['uid'])
            for key, suffix in [('audio', '.wav'), ('haptic', '.json')]:
                self.publish(checked(self.preparation['roles'][role][key]), self.actor(role)['files']+self.run+'-stop'+suffix, self.actor(role)['uid'])
            self.action(role, 'arm')
        self.foreground('owner'); self.action('owner', 'authorize'); self.token('owner', 'ohos.permission.KEEP_BACKGROUND_RUNNING')
        self.foreground('denied'); self.action('denied', 'init', expected_error=201)
        self.foreground('contender'); self.action('contender', 'init')
        self.foreground('owner'); self.action('owner', 'init')
        from avc_media_contract import runtime_identity
        for role in ('owner', 'contender'):
            self.process(role)
            raw = self.shell('cat /proc/'+str(self.actor(role)['pid'])+'/maps', 'actual-AudioHaptic-maps-'+role)
            mapping = mapped_haptic(raw); actual = self.receive(mapping['guest_path'], 'actual-AudioHaptic-DSO-'+role)
            require(actual['inode'] == mapping['inode'], 'mapped AudioHaptic inode changed before read')
            self.actor(role)['haptic_mapping'] = {'maps': self.text(raw, 'haptic-maps'), 'mapping': mapping, 'actual_DSO': actual,
                'runtime_sha256': runtime_identity(checked(actual['file']).read_bytes(), self.guest.env['guest_arch'])}
        self.value['dsp_parameter'] = self.text(self.shell('param get const.multimedia.audio.support_hadware_audio_haptic_sync', 'actual-DSP-parameter'), 'actual-DSP-parameter')
        self.save()

    def account(self, phase):
        from account_state import parse_snapshot
        raw = self.shell('echo "bootevent.account.ready=$(param get bootevent.account.ready)"; '
            'hidumper -s AccountMgr -a "-os_account_infos"', 'actual-account-'+phase)
        require(all(parse_snapshot(raw).values()), 'actual active foreground account100 required')
        self.value.setdefault('accounts', {})[phase] = self.text(raw, 'account-'+phase); self.save()

    def start_observer(self):
        log = self.output/'passive-HDI.jsonl'; self.observer_log = log.open('xb')
        root_admission(self.args)
        marker = '__HAPTIC375_EXIT_'+secrets.token_hex(16)+'__='
        wrapped = protocol.observer_script(self.remote, self.run, self.boot, marker)
        argv = [str(self.args.hdc), '-t', self.guest.target, 'shell', wrapped]
        self.observer = subprocess.Popen(argv, stdout=self.observer_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        self.value['observer'] = {'argv': argv, 'marker': marker, 'raw': descriptor(log), 'exit_code': None}
        end = time.monotonic()+5
        while time.monotonic() < end:
            text = log.read_text()
            if '"kind":"sample"' in text:
                rows = [loads(line) for line in text.splitlines() if line.endswith('}')]
                require(rows[0].get('protocol') == protocol.PROTOCOL and rows[0].get('run_id') == self.run and
                    rows[0].get('boot_id') == self.boot and rows[0].get('time_delay') is True and
                    rows[-1].get('running') is False, 'real idle current TIME capacity required before public playback')
                return
            require(self.observer.poll() is None, 'actual passive observer exited'); time.sleep(.05)
        raise ValueError('actual passive observer startup timed out')

    def collect(self):
        self.setup(); self.start_observer()
        self.foreground('owner'); self.action('owner', 'start'); self.action('owner', 'background-start')
        self.foreground('contender')
        # This WAV starts after the second UI is already visible. It must
        # contain fresh advancing owner PCM, not a pre-background checkpoint.
        self.start_capture('owner-after-contender-foreground'); time.sleep(.8); self.stop_capture()
        self.service('before-contender-start')
        self.process('owner'); self.process('contender')
        self.action('owner', 'snapshot')
        self.start_capture('focus'); self.action('contender', 'start'); time.sleep(1.0)
        self.action('owner', 'snapshot'); self.action('contender', 'snapshot'); self.stop_capture()
        self.service('after-contender-start')
        for role in ROLES: self.journal(role)
        self.value['status'] = 'captured_NOT_full_runtime_gate'; self.save()

    def close(self):
        errors = self.value['cleanup_errors']
        try: self.stop_capture()
        except Exception as error: errors.append('owned capture: '+str(error))
        for role in ROLES:
            if role not in self.armed: continue
            try: self.foreground(role)
            except Exception as error: errors.append(role+'/cleanup foreground: '+str(error))
            for action in (('background-stop', 'release', 'control-close') if role == 'owner' else ('release', 'control-close')):
                try: self.action(role, action)
                except Exception as error: errors.append(role+'/'+action+': '+str(error))
            try: self.journal(role)
            except Exception as error: errors.append(role+'/journal: '+str(error))
        if self.actor_or_none('owner'):
            try: self.service('cleanup', cleanup=True)
            except Exception as error: errors.append('background service cleanup: '+str(error))
        if self.observer is not None:
            try:
                self.shell('umask 077; set -C; : > '+self.remote+'/sampler-stop', 'stop-only-owned-passive-observer')
                self.observer.wait(timeout=10)
                self.observer_log.close()
                self.value['observer'].update(raw=descriptor(self.output/'passive-HDI.jsonl'), exit_code=self.observer.returncode)
                final = protocol.parse_time_transport((self.output/'passive-HDI.jsonl').read_text(), self.run,
                    self.boot, self.observer.returncode, self.value['observer']['marker'])
                require(final[-1]['running'] is False, 'actual TIME backend remained active after public cleanup')
                # It is only our executable; no vibrator mutation is needed.
                self.shell('test ! -e /proc/$(cat '+self.remote+'/observer.pid)', 'observer-exited')
            except Exception as error:
                errors.append('observer completion: '+str(error))
                try:
                    self.shell('task_haptic_pid=$(cat '+self.remote+'/observer.pid) && '
                        'test "$(readlink /proc/$task_haptic_pid/exe)" = '+self.remote+'/passive && '
                        'test "$(awk \'{print $22}\' /proc/$task_haptic_pid/stat)" = "$(cat '+self.remote+'/observer.start)" && '
                        'kill -KILL "$task_haptic_pid"', 'cancel-only-owned-observer')
                    self.observer.wait(timeout=5)
                except Exception as cleanup_error: errors.append('observer cancellation: '+str(cleanup_error))
                finally:
                    self.observer_log.close()
                    self.value['observer'].update(raw=descriptor(self.output/'passive-HDI.jsonl'), exit_code=self.observer.poll())
        for role in self.value['actors']:
            try:
                self.shell('aa force-stop '+BUNDLES[role]+' && if pidof '+BUNDLES[role]+'; then exit 1; fi', 'owned-caller-stop-'+role)
            except Exception as error: errors.append(role+'/process cleanup: '+str(error))
        # Apps and signed HAP installation remain suite-owned. Remove only our
        # source inputs and requests, never all private files or arbitrary paths.
        for role in self.value['actors']:
            paths = [self.actor(role)['files']+self.run+'-stop'+s for s in ('.wav', '.json')]
            paths.append(self.actor(role)['files']+'audio-haptic-request.json')
            try: self.shell('rm -f '+' '.join(map(shlex.quote, paths))+' && test ! -e '+shlex.quote(paths[0])+' && test ! -e '+shlex.quote(paths[1]), 'owned-input-cleanup-'+role)
            except Exception as error: errors.append(role+'/input cleanup: '+str(error))
        if not errors:
            try: self.shell('rm -rf '+self.remote+' && test ! -e '+self.remote, 'owned-root-cleanup')
            except Exception as error: errors.append('root cleanup: '+str(error))
        try:
            require(self.shell('cat /proc/sys/kernel/random/boot_id', 'boot-after').strip() == self.boot, 'actual boot changed')
            self.account('after')
            self.guest.healthy()
        except Exception as error: errors.append('final guest health: '+str(error))
        self.value['cleanup_complete'] = not errors; self.save()

    def actor_or_none(self, role): return self.value['actors'].get(role)


def strip_hmp(raw):
    require(isinstance(raw, str), 'actual HMP text required')
    raw = raw.replace('\r\n', '\n')
    return re.sub(r"^warning: '(?:wavcapture|info capture|stopcapture)' is deprecated since v10\.2, to be removed\n", '', raw)


def verify_qmp(value):
    """Re-read exact command/reply bindings, not a supplied capture-success flag."""
    opened = []; stopped = []
    for item in value['qmp']:
        records = item['records']; require(records and 'QMP' in records[0], 'actual enclosing QMP greeting missing')
        sent = [row['sent'] for row in records if 'sent' in row]
        require(len(sent) == 2 and sent[0]['execute'] == 'qmp_capabilities' and
                sent[1]['execute'] == 'human-monitor-command' and sent[1]['arguments'] == {'command-line': item['command']},
                'actual QMP argv changed')
        replies = []
        for request in sent:
            require(re.fullmatch('[a-f0-9]{32}', request['id']), 'fresh QMP request nonce absent')
            matches = [r for r in records if r.get('id') == request['id']]
            require(len(matches) == 1 and 'error' not in matches[0] and 'return' in matches[0], 'actual QMP request failed/reordered')
            replies.append(matches[0]['return'])
        reply = strip_hmp(replies[-1]); command = item['command']
        if command.startswith('wavcapture '):
            require(not reply.strip(), 'wavcapture reported an actual error')
            opened.append(command)
        elif command.startswith('stopcapture '):
            require(re.fullmatch('stopcapture [0-9]+', command) and not reply.strip(), 'actual stopcapture failed')
            stopped.append(command)
        else:
            require(command == 'info capture' and (not reply.strip() or re.fullmatch(r'\[\d+\]: Capturing audio\(48000,16,2\) to /[^\n]+: \d+ bytes\n?', reply)),
                    'unexpected/failed HMP operation')
    require(len(opened) == len(stopped) == 2, 'two independently owned actual QEMU captures required')
    for phase, command in zip(('owner-after-contender-foreground', 'focus'), opened):
        file = checked(value['captures'][phase]); require(command == 'wavcapture '+str(file)+' ohos_audio 48000 16 2', 'QMP output path differs from actual recorded WAV')
        interval = value['capture_intervals'][phase]
        require(type(interval['start_host_ns']) is int and type(interval['stop_host_ns']) is int and
                interval['start_host_ns'] < interval['stop_host_ns'], 'actual capture command order missing')


def verify_observations(path, archive, boot, *, signature_output=None, signature_command=None):
    """Independent raw recheck. A successful observation is NOT sync acceptance."""
    value = loads(Path(path).read_text()); env = validate_binding(loads(Path(boot).read_text()), descriptor(archive)['sha256'])
    require(value['scope'] == SCOPE and value['archive'] == descriptor(archive) and value['boot'] == descriptor(boot) and
            value['boot_id'] == env['boot_id'] and value['coordinator'] == descriptor(SELF) and value['status'] == 'captured_NOT_full_runtime_gate',
            'actual same fresh archive/boot/candidate collection required')
    prep = validate_preparation(checked(value['preparation'])); run = prep['run_id']
    require(value['run_id'] == run and value['cleanup_complete'] is True and value['cleanup_errors'] == [] and value['errors'] == [],
            'failed/incomplete actual collection or cleanup')
    # Transport logs are independently re-read. Summary status or copied JSON
    # fields alone cannot authorize acceptance.
    for command in value['enclosing_guest_commands']:
        log = Path(command['log']); require(descriptor(log)['sha256'] == command['sha256'] and command['exit_code'] == 0 and
            command['argv'][1:4] == ['-t', env['target'], 'shell'], 'actual enclosing guest transport changed')
        raw = log.read_text().replace('\r', '')
        marker = re.search(r'__QEMU_CHILD_EXIT_[a-f0-9]{32}__=', command['argv'][-1])
        require(marker and raw.endswith('\n'+marker.group()+'0\n') and raw.count(marker.group()) == 1 and not failed(raw), 'guest exit failure hidden by HDC')
    def observation(ref):
        matches = [row for row in value['observations'] if row['raw'] == ref]
        require(len(matches) == 1, 'one original observation command required')
        return matches[0]
    def command_index(ref):
        index = observation(ref)['command']
        require(type(index) is int and 0 <= index < len(value['enclosing_guest_commands']), 'actual observation command index invalid')
        return index
    def observed(ref, script):
        from guest_ui import command_exit
        row = observation(ref); command = value['enclosing_guest_commands'][command_index(ref)]
        require(row['script'] == script and command['argv'][-1].startswith('('+script+'); task_child_rc=$?; '),
            'original observation command differs from the exact expected script')
        original = Path(command['log']).read_text().replace('\r', '')
        marker = re.search(r'__QEMU_CHILD_EXIT_[a-f0-9]{32}__=', command['argv'][-1])
        body, code = command_exit(original, marker.group())
        require(code == 0 and body == checked(ref).read_text(), 'copied observation differs from original successful command stdout')
        return body
    admission = value['root_admission']
    require(admission['owner_module'] == descriptor(OWNER_MODULE), 'root owner implementation changed since collection')
    for key in ('lease', 'config'): checked(admission[key])
    lease = loads(checked(admission['lease']).read_text())
    require(lease['config'] == admission['config'] and
        admission['proof']['parent_pid'] == lease['parent_pid'] and
        admission['proof']['inherited_resource_inode'] == lease['lock'], 'root admission receipt differs from original lease')
    inputs = loads(checked(value['inputs']).read_text())
    from account_state import parse_snapshot
    require(set(value['accounts']) == {'before', 'after'} and
            all(all(parse_snapshot(checked(value['accounts'][phase]).read_text()).values()) for phase in ('before', 'after')),
            'actual before/after foreground account100 observation absent')
    verify_qmp(value)
    require(signature_output is not None and signature_command is not None,
            'independent actual SDK/signature re-verification is required; receipt pass flags are insufficient')
    verify_callers(inputs, prep, env, signature_output, signature_command)
    from avc_media_contract import runtime_identity
    for name, source in [('passive', prep['observer_source']), ('token', prep['token_source'])]:
        build = verify_helper(inputs['helpers'][name], source, env['guest_arch'])
        actual = value['guest_libraries'][name]
        require(len(actual) == len(build['libraries']), 'actual linked guest library inventory incomplete')
        for captured, linked in zip(actual, build['libraries']):
            require(captured['remote'] == linked['guest_path'] and
                    runtime_identity(checked(captured['file']).read_bytes(), env['guest_arch']) == linked['runtime_sha256'],
                    'actual linked helper product DSO bytes differ')
    actors = value['actors']; rows = {}
    for role in ROLES:
        actor = actors[role]; require(actor['bundle'] == BUNDLES[role], 'mixed caller role')
        identity = protocol.bms_identity(observed(actor['BMS'], 'bm dump -n '+BUNDLES[role]), BUNDLES[role])
        uid = identity['uid']; require(uid == actor['uid'] and identity == actor['identity'], 'BMS UID/token drift')
        require(actor['installed_hap']['file']['sha256'] == inputs['actors'][role]['signed_hap']['sha256'], 'actual installed signed caller differs')
        checked(actor['installed_hap']['file'])
        rows[role] = base.parse_hap(checked(actor['journal']['file']).read_text(), run, env['boot_id'], uid)
        require(actor['journal']['uid'] == uid and actor['journal']['mode'] == 600, 'caller raw ownership missing')
        if role != 'denied':
            mapped_dso = actor['haptic_mapping']; mapping = mapped_haptic(checked(mapped_dso['maps']).read_text())
            actual = mapped_dso['actual_DSO']; stat_lines = checked(actual['stat']).read_text().splitlines()
            require(len(stat_lines) == 2 and len(stat_lines[0].split()) == 4 and
                    mapping == mapped_dso['mapping'] and actual['remote'] == mapping['guest_path'] and
                    int(stat_lines[0].split()[3]) == actual['inode'] == mapping['inode'] and
                    stat_lines[1].split()[0] == actual['file']['sha256'], 'actual mapped AudioHaptic DSO/inode/raw file differs')
            require(runtime_identity(checked(actual['file']).read_bytes(), env['guest_arch']) == mapped_dso['runtime_sha256'], 'mapped AudioHaptic runtime bytes changed')
        require(actor.get('process_records'), 'actual kernel process identity absent')
        identities = [process_identity(checked(v).read_text(), actor['pid'], uid) for v in actor['process_records']]
        require(all(v == actor['process_start'] for v in identities), 'actual caller PID generation changed')
        # Actual self-token rows must agree with the independent AccessToken
        # observer; they cannot stand in for it.
        tokens = [protocol.verify_token_binding(item, run=run, boot=env['boot_id'], role=role,
            bundle=BUNDLES[role], identity=identity, permission=item['permission'],
            expected=0 if item['permission'] in PERMISSIONS[role] else -1, observed=observed,
            command_index=command_index) for item in value['tokens'] if item['role'] == role]
        require(len(tokens) >= 3 and len({v['token_id'] for v in tokens}) == 1, 'actual stable independent token observations missing')
        require(all(r['value']['token_id'] == tokens[0]['token_id'] for r in rows[role] if r['event'] == 'token'), 'self and independent token identity differ')
        for action in [v for v in value['actions'] if v['role'] == role]:
            request = loads(checked(action['request']).read_text())
            require(request['run_id'] == run and request['boot_id'] == env['boot_id'] and request['operation_id'] == action['operation'] and
                    request['action'] == action['action'] and request['mute_haptics'] is (role == 'contender'), 'stale/relabelled control request')
            terminal = [r for r in rows[role] if r['operation_id'] == action['operation'] and r['event'] in ('complete', 'error')]
            require(len(terminal) == 1 and {k: v for k, v in terminal[0].items() if k != 'value'} == action['terminal'], 'actual app terminal row differs')
            lo, hi = action['control_interval_ns']
            require(0 < lo <= terminal[0]['before_ns'] <= terminal[0]['after_ns'] <= hi, 'app ACTIVE clock does not lie inside actual MONOTONIC control bracket')
        background_callbacks(rows[role])
    require(any(r['event'] == 'error' and r['error_code'] == 201 for r in rows['denied']), 'actual zero-permission public rejection missing')
    require(not any(r['api'] == 'AudioHapticPlayer.start' and r['event'] == 'return' for r in rows['denied']), 'denied caller unexpectedly started')
    require(len({actors[r]['uid'] for r in ROLES}) == 3 and len({actors[r]['identity']['token_id'] for r in ROLES}) == 3,
        'focus did not use different ordinary UIDs/tokens')
    passive = value['observer']
    require(passive['argv'] == [value['enclosing_guest_commands'][0]['argv'][0], '-t', env['target'], 'shell',
        protocol.observer_script('/data/local/tmp/audio-haptic-'+run, run, env['boot_id'], passive['marker'])],
        'actual passive helper command/run/boot/stop path differs')
    observations = protocol.parse_time_transport(checked(passive['raw']).read_text(),
        run, env['boot_id'], passive['exit_code'], passive['marker'])
    episodes = base.time_episodes(observations); require(len(episodes) == 1, 'exactly one public owner TIME episode required')
    captures = value['captures']; owner_audio = audio_progress(checked(prep['roles']['owner']['audio']), checked(captures['owner-after-contender-foreground']))
    contender_audio = audio_progress(checked(prep['roles']['contender']['audio']), checked(captures['focus']), allow_prefix=True)
    foregrounds = [row for row in value['foregrounds'] if row['role'] == 'contender' and
                   row['host_monotonic_ns'] < value['capture_intervals']['owner-after-contender-foreground']['start_host_ns']]
    require(foregrounds, 'second actual UI was not shown before the fresh owner data window')
    layout = loads(checked(foregrounds[-1]['layout']).read_text()); select_node(layout, BUNDLES['contender'], identifier='audio_haptic_run', clickable=True)
    before = [r for r in value['service_snapshots'] if r['phase'] == 'before-contender-start']
    require(len(before) == 1, 'actual pre-contender service join missing')
    starts = [r for r in rows['owner'] if r['api'] == 'backgroundTaskManager.startBackgroundRunning' and r['event'] == 'return']
    require(len(starts) == 1, 'actual public audioPlayback startup missing'); info = starts[0]['value']
    join = background_join(*(checked(before[0]['raw'][k]).read_text() for k in ('uid', 'all', 'ans')),
        actors['owner']['uid'], actors['owner']['pid'], BUNDLES['owner'], info['continuousTaskId'], info['notificationId'])
    require(join == before[0]['join'], 'background summary differs from actual service records')
    cleanup = [r for r in value['service_snapshots'] if r['phase'] == 'cleanup']
    require(len(cleanup) == 1, 'actual background/notification cleanup dump missing')
    background_absent(*(checked(cleanup[0]['raw'][k]).read_text() for k in ('uid', 'all', 'ans')), actors['owner']['uid'], info['notificationId'])
    start = [r for r in value['actions'] if r['role'] == 'contender' and r['action'] == 'start']
    require(len(start) == 1, 'one actual contender Start required')
    operation = [r for r in rows['contender'] if r['operation_id'] == start[0]['operation'] and r['api'] == 'AudioHapticPlayer.start' and r['event'] == 'return']
    require(len(operation) == 1, 'actual contender public Start return absent')
    lo, hi = operation[0]['before_ns'], operation[0]['after_ns']
    callbacks = [e for r in rows['owner'] if r['event'] == 'callbacks' for e in r['value']['events'] if e['kind'] == 'audioInterrupt']
    forced = {json.dumps(e, sort_keys=True): e for e in callbacks if e['event_type'] == 1 and e['force_type'] == 0 and e['hint_type'] in (2, 3) and lo <= e['monotonic_ns'] <= hi+1000000000}
    require(len(forced) == 1, 'actual forced renderer PAUSE/STOP callback bound to contender Start absent')
    event = next(iter(forced.values())); require(episodes[0]['end_ns'][1] <= event['monotonic_ns']+1000000000,
        'real TIME backend did not stop after renderer interruption')
    require(episodes[0]['end_ns'][1] >= event['monotonic_ns']-250000000, 'TIME was already stopped before renderer interruption')
    require(any(r['running'] and lo-500000000 <= r['before_ns'] <= r['after_ns'] <= event['monotonic_ns'] for r in observations),
            'owner TIME was already stopped before actual contender Start')
    # No arbitrary declared anchor can turn these observations into a gate.
    return {'scope': SCOPE, 'archive_sha256': descriptor(archive)['sha256'], 'boot_id': env['boot_id'], 'run_id': run,
            'owner_audio': owner_audio, 'contender_audio': contender_audio, 'TIME_episodes': episodes,
            'forced_interrupt': event, 'background': join, 'anchor': no_onset_anchor(value.get('onset_anchor')),
            'native_pipeline_source_image_witness_verified': False,
            'accepted': False, 'ledger_closed': False, 'first_artifact_behavior_gate_passed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='mode', required=True)
    create = sub.add_parser('prepare')
    for name in ('output', 'sdk', 'source-export'): create.add_argument('--'+name, type=Path, required=True)
    execute = sub.add_parser('run')
    for name in ('output', 'boot', 'archive', 'hdc', 'preparation', 'inputs'): execute.add_argument('--'+name, type=Path, required=True)
    for name in ('root-lease', 'root-config', 'root-output'): execute.add_argument('--'+name, type=Path, required=True)
    execute.add_argument('--root-lease-nonce', required=True)
    verify = sub.add_parser('verify')
    for name in ('evidence', 'archive', 'boot', 'output'): verify.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare': print(prepare(args.output, args.sdk, args.source_export)); return 0
    if args.mode == 'verify':
        require(not args.output.exists(), 'fresh verification output required')
        output = args.output.parent/(args.output.name+'-raw-recheck'); output.mkdir(mode=0o700, exist_ok=False)
        counter = [0]
        def actual_command(argv, label):
            result = subprocess.run(list(map(str, argv)), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
            counter[0] += 1; log = output/(str(counter[0]).zfill(4)+'-'+label+'.log'); log.write_text(result.stdout+result.stderr)
            save_json(output/(str(counter[0]).zfill(4)+'-'+label+'.json'), {'argv': list(map(str, argv)), 'exit_code': result.returncode, 'log': descriptor(log)})
            require(result.returncode == 0, 'independent signature tool failed'); return result.stdout+result.stderr
        result = verify_observations(args.evidence, args.archive, args.boot, signature_output=output/'signatures', signature_command=actual_command)
        save_json(args.output, result); print(json.dumps(result)); return 1  # Unproven synchronization is never accepted.
    coordinator = Coordinator(args)
    try: coordinator.collect()
    except Exception as error: coordinator.value['errors'].append(str(error))
    finally: coordinator.close()
    # A clean collection still needs the independent raw verifier and onset
    # implementation. There is no successful full-gate exit in this candidate.
    print(coordinator.output/'evidence.json'); return 1


if __name__ == '__main__':
    raise SystemExit(main())
