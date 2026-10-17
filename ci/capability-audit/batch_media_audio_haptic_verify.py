#!/usr/bin/env python3
"""Independent raw AudioHaptic/PCM/HDI checks; no guest state changes."""
import argparse
import json
import math
from pathlib import Path
import re
import shlex
import wave

import batch_media_audio_haptic_project as project
import batch_media_audio_capture_challenge as pcm
import batch_system_build_runtime_helpers as product
import batch_media_knowledge_suite as shared
import batch_apps_contact_picker_coordinator as signatures
from enclosing_acceptance_guest import validate_binding
from hap_identity_binding import HAP_IDENTITY_FIELDS, verify_hap_token_identity

HERE, ROLES = project.HERE, project.ROLES
require, checked, record, sha, load = project.require, project.checked, project.record, project.sha, project.load
HEX = re.compile('[a-f0-9]{32}')
FIELDS = {'schema_version', 'run_id', 'boot_id', 'operation_id', 'sequence', 'timestamp_ms', 'uid', 'token_id',
          'player_epoch', 'event', 'api', 'value_json', 'error_code', 'error_message'}


def bms_identity(raw, role):
    bundle, _ = ROLES[role]
    value = json.loads(raw.removeprefix(bundle + ':\n'), object_pairs_hook=signatures.unique)
    app = value['applicationInfo']
    require((app.get('name') or app.get('bundleName')) == bundle and app.get('isSystemApp') is False and
            app.get('appPrivilegeLevel') == 'normal' and type(app.get('uid')) is int and
            app['uid'] // 200000 == 100 and app['uid'] % 200000 >= 10000 and
            type(app.get('accessTokenId')) is int and 0 < app['accessTokenId'] < 2**32, 'actual normal BMS identity differs')
    require(type(value.get('appIndex')) is int and value['appIndex'] == 0 and
            type(app.get('appIndex')) is int and app['appIndex'] == 0 and
            type(value.get('uid')) is int and value['uid'] == app['uid'], 'actual BMS instance/UID differs')
    accounts = [item for item in value.get('userInfo', []) if isinstance(item, dict) and
                item.get('bundleUserInfo', {}).get('userId') == 100]
    require(len(accounts) == 1 and accounts[0].get('bundleName') == bundle and
            type(accounts[0].get('uid')) is int and accounts[0]['uid'] == app['uid'] and
            type(accounts[0].get('accessTokenId')) is int and accounts[0]['accessTokenId'] == app['accessTokenId'],
            'actual account-100 BMS UID/token differs')
    return dict(uid=app['uid'], token_id=app['accessTokenId'], installed_remote=signatures.installed_path(raw, bundle))


def token_identity(raw, role, *, run, boot, identity):
    token = json.loads(raw, object_pairs_hook=signatures.unique)
    require(set(token) == HAP_IDENTITY_FIELDS | {'kind', 'run_id', 'boot_id', 'bundle', 'token_id',
            'VIBRATE', 'before_ns', 'after_ns'}, 'actual token identity fields differ')
    verify_hap_token_identity(token, bundle=ROLES[role][0], uid=identity['uid'], token_id=identity['token_id'])
    require(token['kind'] == 'token' and token['run_id'] == run and token['boot_id'] == boot and
            type(token['VIBRATE']) is int and token['VIBRATE'] == (0 if role == 'normal' else -1) and
            type(token['before_ns']) is int and type(token['after_ns']) is int and
            0 < token['before_ns'] <= token['after_ns'], 'real ordinary VIBRATE token boundary differs')
    return token


def verify_token_binding(binding, raw, *, role, identity, run, boot, observed, command_index):
    require(set(binding) == {'bms_before', 'token', 'bms_after'} and binding['token'] == raw,
            'actual token/BMS binding differs')
    bundle = ROLES[role][0]
    before = bms_identity(observed(binding['bms_before'], 'bm dump -n ' + bundle), role)
    token_raw = observed(raw, project.sampler_script('/data/local/tmp/audio-haptic-' + run,
        'token', run, boot, bundle, identity['uid']))
    after = bms_identity(observed(binding['bms_after'], 'bm dump -n ' + bundle), role)
    require(before == identity == after, 'actual BMS identity changed around token query')
    require(command_index(binding['bms_before']) < command_index(raw) < command_index(binding['bms_after']),
            'raw BMS observations must bracket the actual token command')
    return token_identity(token_raw, role, run=run, boot=boot, identity=identity)


def verify_capture_requests(qmp, segments):
    """Replay raw command-specific capture replies; never a collector status flag."""
    from batch_media_audio_haptic_runtime import capture_list_empty, owned_capture_listing
    require(isinstance(qmp, list) and len(qmp) >= 2 and all(isinstance(r, dict) and
            r.get('execute') == 'human-monitor-command' and type(r.get('host_ns')) is int and
            type(r.get('completed_ns')) is int and 0 < r['host_ns'] <= r['completed_ns'] and
            isinstance(r.get('reply'), str) and 'failure_reply' not in r for r in qmp),
            'actual QMP HMP capture commands failed or incomplete')
    require(qmp[0].get('label') == 'capture-help' and qmp[1].get('label') == 'capture-before' and
            re.search(r'wavcapture\s+path audiodev', qmp[0]['reply']) and
            qmp[0].get('arguments') == {'command-line': 'help wavcapture'} and
            qmp[1].get('arguments') == {'command-line': 'info capture'} and
            capture_list_empty(qmp[1]['reply']), 'actual QEMU capture syntax/initial ownership not established')
    require(all(left['completed_ns'] <= right['host_ns'] for left, right in zip(qmp, qmp[1:])),
            'actual QMP capture intervals overlap or were reordered')
    cursor = 2
    for segment in segments:
        rows = qmp[cursor:cursor+6]; cursor += 6
        capture = segment['audio_capture']; wav = checked(capture['wav']); backend = capture['backend']; phase = segment['phase']
        require(len(rows) == 6 and [r.get('label') for r in rows] == [phase+'-'+s for s in
            ('before-capture', 'wavcapture', 'capture-owned', 'capture-before-stop', 'stopcapture', 'capture-after-stop')],
            'actual per-segment QMP capture ownership/order differs')
        require([r.get('arguments') for r in rows] == [{'command-line': script} for script in
            ('info capture', f'wavcapture {wav} {backend} 48000 16 2', 'info capture', 'info capture', 'stopcapture 0', 'info capture')] and
            capture_list_empty(rows[0]['reply']) and capture_list_empty(rows[5]['reply']) and
            rows[1]['reply'] == '' and rows[4]['reply'] == '',
            'WAV was not captured/stopped by this actual QMP sequence')
        owned_capture_listing(rows[2]['reply'], wav); owned_capture_listing(rows[3]['reply'], wav)
        require(capture['host_begin_ns'] <= rows[1]['host_ns'] <= rows[1]['completed_ns'] < rows[4]['host_ns'] <=
                rows[4]['completed_ns'] <= capture['host_end_ns'], 'actual WAV capture timestamps differ from QMP operations')
    require(cursor == len(qmp), 'unexpected extra capture action')


def parse_journal(raw, run, boot, identity):
    require(isinstance(raw, str) and 0 < len(raw) <= 16 * 1024**2 and raw.endswith('\n'), 'complete nonempty raw journal required')
    rows = []
    for line in raw.splitlines():
        row = json.loads(line, object_pairs_hook=signatures.unique)
        require(set(row) == FIELDS and type(row['schema_version']) is int and row['schema_version'] == 1 and row['run_id'] == run and row['boot_id'] == boot and
                HEX.fullmatch(row['operation_id']) and type(row['sequence']) is int and row['sequence'] == len(rows) + 1 and
                type(row['timestamp_ms']) is int and row['timestamp_ms'] > 0 and
                type(row['player_epoch']) is int and row['player_epoch'] >= 0 and
                row['uid'] == identity['uid'] and row['token_id'] == identity['token_id'] and
                type(row['error_code']) is int and isinstance(row['error_message'], str), 'stale/reordered/foreign raw caller record')
        if rows: require(row['timestamp_ms'] >= rows[-1]['timestamp_ms'], 'caller realtime moved backward')
        row['value'] = json.loads(row['value_json'], object_pairs_hook=signatures.unique)
        if row['event'] != 'error': require(row['error_code'] == 0 and row['error_message'] == '', 'nonerror row carries a hidden failure')
        if row['event'] == 'callback': require(row['api'] in ('AudioHapticPlayer.endOfStream', 'AudioHapticPlayer.audioInterrupt'), 'nonpublic callback invented')
        rows.append(row)
    return rows


def one(rows, event, api=None):
    found = [r for r in rows if r['event'] == event and (api is None or r['api'] == api)]
    require(len(found) == 1, 'exactly one actual event required: ' + event + '/' + str(api))
    return found[0]


def operation(rows, envelope, expectation, *, role, previous_epoch, source_id):
    request = envelope['request']; group = [r for r in rows if r['operation_id'] == request['operation_id']]
    begin = one(group, 'begin')
    require(begin['value'] == request and begin['api'] == request['action'] and begin['sequence'] == min(r['sequence'] for r in group),
            'actual operation does not begin with exact fresh request')
    require(all(r['event'] in ('begin', 'return', 'callback', 'complete', 'error') for r in group), 'invented raw event')
    if expectation['expected'] == 'error':
        error = one(group, 'error')
        require(error['api'] == request['action'] and error['error_code'] in expectation['errors'] and
                not any(r['event'] == 'complete' for r in group) and
                not any(r['api'] == 'AudioHapticManager.createPlayer' and r['event'] == 'return' for r in group),
                'required genuine public error missing/changed or false success present')
        if request['action'] == 'start': require(not any(r['api'] == 'AudioHapticPlayer.start' and r['event'] == 'return' for r in group), 'failed start contains success return')
        return previous_epoch, source_id
    require(not any(r['event'] == 'error' for r in group), 'actual public operation failed')
    complete = one(group, 'complete')
    require(complete['api'] == request['action'], 'terminal action differs')
    action = request['action']
    apis = {'access': 'abilityAccessCtrl.checkAccessTokenSync', 'register': 'AudioHapticManager.registerSource',
        'start': 'AudioHapticPlayer.start', 'stop': 'AudioHapticPlayer.stop', 'release': 'AudioHapticPlayer.release',
        'loop': 'AudioHapticPlayer.setLoop', 'volume': 'AudioHapticPlayer.setVolume', 'unregister': 'AudioHapticManager.unregisterSource'}
    if action == 'create':
        epoch = one(group, 'return', 'AudioHapticManager.createPlayer')['player_epoch']
        require(epoch == previous_epoch + 1, 'created player epoch was reused/skipped')
        require(one(group, 'return', 'AudioHapticManager.setAudioLatencyMode')['value'] == 0 and
                one(group, 'return', 'AudioHapticManager.setStreamUsage')['value'] == 1 and
                one(group, 'return', 'AudioHapticPlayer.isMuted.audio')['value'] is request['mute_audio'] and
                one(group, 'return', 'AudioHapticPlayer.isMuted.haptic')['value'] is request['mute_haptics'], 'actual player options differ')
        return epoch, source_id
    returned = one(group, 'return', apis[action])
    require(returned['player_epoch'] == previous_epoch, 'operation changed retained player instance')
    if action == 'register':
        require(type(returned['value']) is int and returned['value'] >= 0, 'resource registration failed')
        source_id = returned['value']
    elif action == 'unregister': require(returned['value'] == source_id, 'different resource unregistered')
    elif action == 'access': require(type(returned['value']) is int and returned['value'] == (0 if role == 'normal' else -1), 'self VIBRATE result differs')
    elif action in ('loop', 'volume'): require(returned['value'] == request[action], 'actual setter argument differs')
    else: require(returned['value'] == {}, 'unexpected return value for public void Promise')
    if expectation.get('eos'):
        callbacks = [r for r in group if r['event'] == 'callback' and r['api'] == 'AudioHapticPlayer.endOfStream' and r['player_epoch'] == previous_epoch]
        require(callbacks and callbacks[0]['timestamp_ms'] >= returned['timestamp_ms'], 'actual EOS callback missing on this retained player/run')
    return previous_epoch, source_id


def sampler_rows(item, run, boot):
    require(item['exit_code'] == 0, 'actual sampler process failed')
    text = checked(item['raw']).read_text().replace('\r', '')
    marker = item['exit_marker']
    require(re.fullmatch('__HAPTIC_SAMPLE_EXIT_[a-f0-9]{32}__=', marker) and text.count(marker) == 1 and
            text.endswith('\n' + marker + '0\n'), 'actual guest sampler exit nonce missing')
    lines = text[:text.rfind('\n' + marker)].strip().splitlines()
    rows = [json.loads(line, object_pairs_hook=signatures.unique) for line in lines]
    require(len(rows) >= 27, 'complete sampler observations too short')
    begin, end = rows[0], rows[-1]
    require(begin.get('kind') == 'begin' and (begin['run_id'], begin['boot_id'], begin['uid'], begin['device_id'], begin['vibrator_id'], begin['interval_ms']) ==
            (run, boot, 0, 0, 0, 10) and type(begin['pid']) is int and begin['pid'] > 1 and
            end == dict(kind='complete', run_id=run, boot_id=boot, samples=len(rows)-2, owner_stop=True), 'sampler run/device/exit binding differs')
    samples = rows[1:-1]
    previous = 0
    for index, row in enumerate(samples, 1):
        require(set(row) == {'kind', 'sequence', 'before_ns', 'after_ns', 'realtime_ns', 'result', 'running'} and
                row['kind'] == 'sample' and row['sequence'] == index and type(row['result']) is int and row['result'] == 0 and
                type(row['running']) is bool and all(type(row[k]) is int and row[k] > 0 for k in ('before_ns', 'after_ns', 'realtime_ns')) and
                row['after_ns'] >= row['before_ns'] >= previous, 'actual read-only HDI sample failed/reordered')
        if previous: require(row['before_ns'] - previous <= 200000000, 'HDI sampling gap exceeds 200 ms; cannot certify timing/silence')
        previous = row['after_ns']
    return begin, samples


def clock_bounds(items, run, boot):
    intervals = []
    for item in items:
        value = load(checked(item['raw']))
        require(value.get('kind') == 'clock' and value['run_id'] == run and value['boot_id'] == boot and
                0 < value['before_ns'] <= value['after_ns'] and
                0 < item['host_before_ns'] <= item['host_after_ns'], 'actual guest/host clock bracket invalid')
        intervals.append((item['host_before_ns']-value['after_ns'], item['host_after_ns']-value['before_ns']))
    low, high = max(v[0] for v in intervals), min(v[1] for v in intervals)
    require(low <= high and high-low <= 400000000, 'guest/host monotonic calibration absent, changed or wider than 400 ms')
    return low, high


def wave_values(path):
    with wave.open(str(path), 'rb') as stream:
        require((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) == (2, 2, 48000, 'NONE'),
                'independent QEMU output must be real 48kHz stereo S16LE WAV')
        frames = stream.getnframes()
        require(0 < frames <= 48000 * 120, 'bounded nonempty independent capture required; zero frames do not prove silence')
        return pcm.pcm_values(stream.readframes(frames))


def audio_metrics(capture, expectation, reference, *, followed_by_boundary=False):
    values = wave_values(checked(capture['wav'])); frames = len(values)//2
    elapsed = (capture['host_end_ns']-capture['host_begin_ns'])/1e9
    require(0 < elapsed <= 120 and abs(frames/48000-elapsed) <= .25,
            'QEMU capture lacks a continuous host-timed silence clock (gap, drift or inactivity); cannot infer synchronization')
    rms = lambda data: math.sqrt(sum(v*v for v in data)/len(data)) if data else 0
    tail = values[-int(.4*48000)*2:]
    result = dict(frames=frames, duration_seconds=frames/48000, elapsed_seconds=elapsed, tail_rms=rms(tail))
    mode = expectation['audio']
    if mode == 'quiet':
        require(result['tail_rms'] <= 8, 'actual QEMU output is not silent at required boundary')
        if expectation['action'] in ('start', 'create', None):
            require(rms(values) <= 8, 'mute/denied/post-release/final interval contains unexpected audio')
        return result
    active = [i for i in range(frames) if max(abs(values[2*i]), abs(values[2*i+1])) > 64]
    require(len(active) >= 2*pcm.WINDOW, 'actual independent fresh stereo PCM missing')
    first, last = active[0], active[-1]
    # Fade-in/out may change sample amplitudes. Full independent windows in the
    # interior must still match both random channels, their timing and order.
    start = first + 1024; finish = last - pcm.WINDOW - 1024
    require(finish > start+pcm.WINDOW, 'actual fresh audio interval too short')
    matches = []
    for pos in (start, finish):
        match = pcm.match_window(values[pos*2:(pos+pcm.WINDOW)*2], reference)
        match['capture_frame'] = pos; matches.append(match)
    period = len(reference)//2
    displacement = (matches[1]['source_frame']-matches[0]['source_frame']-(finish-start)) % period
    require(min(displacement, period-displacement) <= 1, 'independent PCM rate/order/drop/replay discontinuity')
    result.update(first_active_frame=first, last_active_frame=last, matches=matches)
    if mode == 'eos':
        require(result['tail_rms'] <= 8 and 3.5 <= (last-first)/48000 <= 4.4, 'actual 4-second WAV EOS/trailing silence differs')
    elif mode == 'loop':
        require((last-first)/48000 >= 8 and (followed_by_boundary or rms(tail) > 64), 'actual repeated audio loop stops early')
    return result


def active_boundary_metrics(segment, data, boot, journal, clock_interval):
    expectation = segment['boundary_expected']; required = expectation['active_before']
    require(required is not None, 'explicit active boundary expectation required')
    start_request = load(checked(segment['operation']['request']))['request']
    boundary_request = load(checked(segment['boundary_operation']['request']))['request']
    start_group = [row for row in journal if row['operation_id'] == start_request['operation_id']]
    boundary_group = [row for row in journal if row['operation_id'] == boundary_request['operation_id']]
    began = one(boundary_group, 'begin'); start_return = one(start_group, 'return', 'AudioHapticPlayer.start')
    require(began['player_epoch'] == start_return['player_epoch'] and began['sequence'] > start_return['sequence'] and
            not any(row['event'] == 'callback' and row['api'] == 'AudioHapticPlayer.endOfStream' and
                    row['sequence'] < began['sequence'] for row in start_group),
            'EOS preceded the purported active Stop/Release; boundary remains unproved')
    _, samples = sampler_rows(segment['sampler'], data['run_id'], boot)
    instant = began['timestamp_ms'] * 1000000
    preceding = [row for row in samples if row['realtime_ns'] <= instant and instant-row['realtime_ns'] <= 100000000]
    require(len(preceding) >= 3 and instant-preceding[-1]['realtime_ns'] <= 30000000,
            'no dense genuine VDI observations immediately before Stop/Release')
    if required['haptic']:
        require(all(row['running'] for row in preceding), 'VDI had already expired before active Stop/Release')
    else:
        require(all(not row['running'] for row in preceding), 'muted haptics unexpectedly active before Stop')
    anchor = preceding[-1]
    delta = instant-anchor['realtime_ns']
    low, high = clock_interval
    action_low = anchor['before_ns'] + delta + low - 1000000
    action_high = anchor['after_ns'] + delta + high + 1000000
    require(action_high-action_low <= 100000000, 'active boundary clock uncertainty exceeds 100ms; keep boundary gap')
    result = dict(action_host_interval_ns=[action_low, action_high], preceding_VDI_samples=len(preceding),
                  maximum_VDI_pre_action_age_ns=instant-anchor['realtime_ns'], required=required)
    if required['audio']:
        capture = segment['audio_capture']; values = wave_values(checked(capture['wav'])); origin = capture['host_begin_ns']
        reference = pcm.pcm_values(checked(data['reference']).read_bytes())
        # Use the declared +/-250ms capture-origin bound conservatively. The
        # matched source must exist before the call; its last active frame must
        # reach the call within 50ms under the worst allowed clock/origin bound.
        end_frame = (action_low-origin-250000000)*48000//1000000000
        start_frame = end_frame-2*pcm.WINDOW
        require(start_frame >= 0 and end_frame <= len(values)//2, 'no genuine pre-action PCM window')
        matches = [pcm.match_window(values[pos*2:(pos+pcm.WINDOW)*2], reference)
                   for pos in (start_frame, start_frame+pcm.WINDOW)]
        active = [i for i in range(len(values)//2) if max(abs(values[2*i]), abs(values[2*i+1])) > 64]
        require(active and origin+active[-1]*1000000000//48000-250000000 >= action_high-50000000,
                'PCM may have ended before Stop/Release under measured uncertainty; active boundary unproved')
        result['pre_action_PCM_matches'] = matches
    result['scope'] = 'conservative_continuous_PCM_and_read_only_VDI_boundary_NOT_physical_motor_or_late_callback_closure'
    return result


def segment_metrics(segment, data, boot):
    expectation = segment['expected']
    _, samples = sampler_rows(segment['sampler'], data['run_id'], boot)
    low, high = clock_bounds([segment['clock_before'], segment['clock_after']], data['run_id'], boot)
    mode = expectation['haptic']
    latest = samples[-1]['after_ns']
    tail = [r for r in samples if r['before_ns'] >= latest-400000000]
    require(len(tail) >= 10, 'actual HDI silence/active tail too sparse')
    active = [r for r in samples if r['running']]
    if mode == 'quiet':
        require(all(not r['running'] for r in tail), 'actual VDI still running at silent boundary')
        if expectation['action'] in ('start', 'create', None): require(not active, 'muted/denied/post-release/final interval unexpectedly vibrated')
    elif mode == 'eos': require(active and all(not r['running'] for r in tail), 'actual VDI did not run and expire at EOS')
    elif mode == 'loop':
        require(active and (segment.get('boundary_expected') is not None or any(r['running'] for r in tail)),
                'actual VDI loop not running after two audio periods')
        require(active[-1]['realtime_ns']-active[0]['realtime_ns'] >= 8000000000, 'VDI loop did not span two real audio periods')
    else: require(active, 'actual VDI never ran for unmuted haptics')
    if mode in ('active', 'eos', 'loop'): require(not samples[0]['running'], 'VDI already running before fresh UI start')
    reference = pcm.pcm_values(checked(data['reference']).read_bytes())
    audio = audio_metrics(segment['audio_capture'], expectation, reference,
        followed_by_boundary=segment.get('boundary_expected') is not None)
    result = dict(audio=audio, HDI_samples=len(samples), HDI_running_samples=len(active), clock_offset_ns=[low, high],
                  QEMU_audio_frame_origin_uncertainty_ns=250000000)
    if mode in ('active', 'eos', 'loop') and expectation['audio'] in ('active', 'eos', 'loop'):
        origin = segment['audio_capture']['host_begin_ns']
        audio_ns = origin + audio['first_active_frame']*1000000000//48000
        vib_min = active[0]['before_ns']+low
        vib_max = active[0]['after_ns']+high
        minimum, maximum = vib_min-audio_ns-250000000, vib_max-audio_ns+250000000
        require(minimum <= 200000000 and maximum >= -200000000, 'observed audio/vibration onsets are outside declared 200ms plus measured uncertainty')
        result['vibration_minus_audio_onset_ns'] = dict(minimum=minimum, maximum=maximum,
            scope='bounded_QEMU_wave_capture_and_read_only_VDI_state_NOT_physical_motor_or_DSP_precision')
    return result


def verify_evidence(path, archive, boot, *, command):
    value = load(path); data = project.validate_challenge(checked(value['artifacts_data']['challenge']))
    env = validate_binding(load(boot), sha(archive)); spec = value['artifacts_data']
    require(value['archive'] == record(archive) and value['boot'] == record(boot) and value['archive_sha256'] == sha(archive) and
            value['boot_id'] == env['boot_id'] and value['run_id'] == data['run_id'] and value['failures'] == [] and
            value['cleanup_errors'] == [] and value['cleanup_complete'] is True and
            value['first_artifact_behavior_gate_passed'] is False and value['ledger_closed'] is False, 'failed/unbound/incomplete owned guest evidence')
    require(load(checked(value['artifacts'])) == spec, 'original artifact input changed')
    from batch_media_audio_haptic_runtime import TOOLS
    require(value['tool_sources'] == {name: record(HERE / name) for name in TOOLS}, 'collector or dependent checker source changed')
    commands = value['commands']; shared.verify_commands(commands, value['hdc'], env['target'])
    observations = {}
    observation_commands = set()
    for row in value['observations']:
        actual = shared.exact_script(commands[row['command']], row['script'])
        require(actual == checked(row['raw']).read_text(), 'normalized observation differs from actual HDC output')
        key = (row['raw']['path'], row['raw']['sha256'])
        require(key not in observations and type(row['command']) is int and row['command'] not in observation_commands,
                'duplicate actual observation file/command binding')
        observations[key] = row; observation_commands.add(row['command'])
    def observed(raw, script=None):
        key = (raw['path'], raw['sha256'])
        require(key in observations, 'raw result lacks actual guest command')
        row = observations[key]
        if script is not None: require(row['script'] == script, 'claimed actual guest script differs')
        return checked(raw).read_text()
    def command_index(raw):
        key = (raw['path'], raw['sha256'])
        require(key in observations, 'raw result lacks actual guest command')
        return observations[key]['command']
    for row in value['journals']:
        marker = row['sentinel']; remote = '/data/app/el2/100/base/' + ROLES[row['role']][0] + '/files/audio-haptic-' + data['run_id'] + '.jsonl'
        require(row['remote'] == remote and re.fullmatch('__HAPTIC_EOF_[a-f0-9]{32}__', marker), 'wrong actual private journal')
        text = observed(row['observation'], 'if test -f ' + shlex.quote(remote) + '; then cat ' + shlex.quote(remote) +
            ' || exit 1; fi && printf ' + shlex.quote('\n' + marker + '\n'))
        require(text.endswith('\n'+marker) and text.count(marker) == 1 and checked(row['raw']).read_text() == text[:-len(marker)-1], 'actual complete journal transfer differs')
    received = {}
    for row in value['received']:
        local = checked(row['raw']); remote = row['remote']
        require(commands[row['command']]['argv'] == [value['hdc'], '-t', env['target'], 'file', 'recv', remote, str(local)] and
                observed(row['guest_hash'], 'test -f ' + shlex.quote(remote) + ' && test ! -L ' + shlex.quote(remote) +
                ' && sha256sum ' + shlex.quote(remote)).split() == [sha(local), remote], 'actual file receive binding differs')
        received[(row['raw']['path'], row['raw']['sha256'])] = remote
    from batch_media_audio_haptic_build_sampler import helper_binding
    helper = helper_binding(spec['helper'])
    require(value['helper'] == helper, 'actual compiled sampler/helper receipts differ')
    for dso, proof in zip(helper['product_DSOs'], value['helper_guest_DSOs']):
        require(proof['soname'] == dso['soname'], 'same-guest helper DSO SONAME differs')
        expected_script = product.runtime_guest_script(helper, dso['soname'])
        require(proof['script'] == expected_script, 'collector supplied another DSO observation command')
        product.verify_guest_runtime_raw(helper, dso['soname'], observed(proof['observation'], expected_script),
                                         archive_sha256=value['archive_sha256'])
    require(len(value['helper_guest_DSOs']) == len(helper['product_DSOs']), 'missing actual helper dependencies')
    identities = {}; journals = {}; binding_results = {}
    for role, item in value['roles'].items():
        require(role in ROLES, 'unexpected caller role')
        project.project_binding(spec['projects'][role], role, checked(spec['challenge']))
        identity = bms_identity(observed(item['bms'], 'bm dump -n ' + ROLES[role][0]), role)
        identities[role] = identity
        proof = signatures.verify_signed_hap_artifacts(checked(item['signed_hap']), *ROLES[role], env['udid'],
            spec['signer']['dist'], checked(spec['signer']['jar']), Path(path).parent / ('verify-' + role + '-' + __import__('secrets').token_hex(4)), command)
        signatures.verify_signed_payload(checked(spec['projects'][role]['unsigned_hap']), checked(item['signed_hap']))
        require(item['installed_hap']['sha256'] == item['signed_hap']['sha256'] and
                received[(item['installed_hap']['path'], item['installed_hap']['sha256'])] == identity['installed_remote'], 'signed/installed compiled payload differs')
        require(checked(item['journal_before']).read_bytes() == b'' and
                any(j['raw'] == item['journal_before'] for j in value['journals']), 'fresh journal baseline missing')
        journals[role] = parse_journal(checked(item['journal']).read_text(), data['run_id'], env['boot_id'], identity)
        for name, expected in data['files'].items():
            actual = item['inputs'][name]
            require(actual['sha256'] == expected['sha256'] and received[(actual['path'], actual['sha256'])] ==
                    '/data/app/el2/100/base/' + ROLES[role][0] + '/files/' + name, 'private genuine challenge input differs')
        for when in ('initial', 'final'):
            require(set(item.get('token_bindings', {})) == {'initial', 'final'}, 'initial/final BMS token bindings missing')
            verify_token_binding(item['token_bindings'][when], item['token_' + when], role=role, identity=identity,
                run=data['run_id'], boot=env['boot_id'], observed=observed, command_index=command_index)
        binding_results[role] = dict(identity=identity, signature=proof)
    require(set(identities) == set(ROLES) and len({v['uid'] for v in identities.values()}) == 2 and
            len({v['token_id'] for v in identities.values()}) == 2, 'ordinary/denied installed identities overlap')
    phase_records = {row['phase']: row for row in value['phases']}
    require(len(phase_records) == len(value['phases']), 'duplicate phase evidence')
    transports = {}
    for block in project.execution_plan():
        first = phase_records[block[0]['name']]
        expected = load(checked(first['request']))
        if len(block) == 2:
            second = phase_records[block[1]['name']]
            expected = project.paired_request(expected, load(checked(second['request'])), block[0]['hold_ms'])
            require(first['transport_request'] == second['transport_request'] and first['click'] == second['click'], 'paired calls require one explicit real UI click')
        require(load(checked(first['transport_request'])) == expected, 'real UI transport differs from fixed explicit operation plan')
        for phase in block: transports[phase['name']] = first['transport_request']
    epochs = {role: 0 for role in ROLES}; source_ids = {role: -1 for role in ROLES}; pids = {role: [] for role in ROLES}; nonces = set()
    require(len(value['phases']) == len(project.phases()), 'fixed lifecycle/negative/mute coverage incomplete')
    for captured, phase in zip(value['phases'], project.phases()):
        envelope = load(checked(captured['request'])); role = phase['role']; nonce = envelope['request']['operation_id']
        require(nonce not in nonces and envelope == project.request(checked(spec['challenge']), env['boot_id'], phase['name'], nonce) and
                captured['phase'] == phase['name'] and captured['role'] == role and captured['complete'] is True, 'actual ordered fresh UI operation changed')
        nonces.add(nonce)
        require(observed(captured['begin_boot'], 'cat /proc/sys/kernel/random/boot_id') == env['boot_id'] and
                observed(captured['end_boot'], 'cat /proc/sys/kernel/random/boot_id') == env['boot_id'], 'operation boot differs')
        epochs[role], source_ids[role] = operation(journals[role], envelope, phase, role=role, previous_epoch=epochs[role], source_id=source_ids[role])
        for key in ('pid_before', 'pid_after'):
            pid = observed(captured[key]['pid'], 'pidof ' + ROLES[role][0])
            require(re.fullmatch('[1-9][0-9]*', pid), 'one actual caller PID required')
            raw = observed(captured[key]['stat'], 'cat /proc/' + pid + '/stat')
            fields = raw[raw.rfind(')')+2:].split(); require(len(fields) >= 20 and fields[19].isdigit(), 'actual starttime missing')
            pids[role].append((pid, fields[19]))
        click = captured['click']; require(click in value['ui_actions'] and click['bundle'] == ROLES[role][0] and click['selector'] == {'identifier': 'audio_haptic_run'}, 'wrong real UI host control')
        shared.verify_click(click, commands, value['hdc'], env['target'], observed)
        staged = [r for r in value['staged'] if r['local'] == transports[phase['name']]]
        require(len(staged) == 1 and staged[0]['remote'] == '/data/app/el2/100/base/' + ROLES[role][0] + '/files/audio-haptic-request.json', 'clicked operation lacks exact staged request')
        begin_index = observations[(captured['begin_boot']['path'], captured['begin_boot']['sha256'])]['command']
        end_index = observations[(captured['end_boot']['path'], captured['end_boot']['sha256'])]['command']
        require(begin_index < staged[0]['command'] < click['command'] < end_index, 'fresh request/click/boot transport ordering differs')
        require(any(j['raw'] == captured['journal'] and j['role'] == role for j in value['journals']), 'phase terminal journal is not an actual guest capture')
    require(all(len(set(v)) == 1 for v in pids.values()), 'native class instance was lost across stop/restart/EOS/recreate')
    allowed_stages = {('/data/app/el2/100/base/' + ROLES[role][0] + '/files/' + name): (identity['uid'], '600')
                      for role, identity in identities.items() for name in list(data['files']) + ['audio-haptic-request.json']}
    remote_root = '/data/local/tmp/audio-haptic-' + data['run_id']
    allowed_stages[remote_root + '/sampler'] = (0, '700')
    for item in value['staged']:
        local = checked(item['local']); remote = item['remote']; sent = item['command']
        require(remote in allowed_stages and (item['uid'], item['mode']) == allowed_stages[remote], 'stage escaped the exact owned private path/UID surface')
        require(commands[sent]['argv'] == [value['hdc'], '-t', env['target'], 'file', 'send', str(local), item['sent_remote']] and
                observed(item['guest_hash'], 'sha256sum ' + shlex.quote(remote)).split() == [sha(local), remote], 'actual stage input bytes differ')
        shared.exact_script(commands[sent+1], 'chown ' + str(item['uid']) + ':' + str(item['uid']) + ' ' + shlex.quote(item['sent_remote']) + ' && chmod ' + item['mode'] + ' ' + shlex.quote(item['sent_remote']))
        if remote != item['sent_remote']:
            require(remote.endswith('/audio-haptic-request.json') and re.fullmatch(re.escape(remote)+r'\.[a-f0-9]{16}\.tmp', item['sent_remote']), 'only exact owned requests may be replaced')
            shared.exact_script(commands[sent+2], 'test ! -L ' + shlex.quote(remote) + ' && mv ' + shlex.quote(item['sent_remote']) + ' ' + shlex.quote(remote))
        if remote.endswith('/sampler'): require(item['local'] == helper['binary'] and item['uid'] == 0 and item['mode'] == '700', 'another observer was executed')
        else: require(item['mode'] == '600' and item['uid'] in {v['uid'] for v in identities.values()}, 'ordinary private input owner/mode differs')
    planned = project.capture_plan()
    require([v['phase'] for v in value['segments']] == [project.capture_name(block) for block in planned] + ['final-cleanup-quiet'], 'all continuous PCM/HDI observation intervals required')
    metrics = []
    final_quiet = dict(name='final-cleanup-quiet', role=None, action=None, options={}, expected='ok', errors=[],
                       hold_ms=1100, audio='quiet', haptic='quiet', eos=False, active_before=None)
    used_clocks = []
    for segment, block in zip(value['segments'], planned + [[final_quiet]]):
        phase = block[0]
        require(segment['expected'] == phase and observed(segment['begin_boot'], 'cat /proc/sys/kernel/random/boot_id') == env['boot_id'] and
                observed(segment['end_boot'], 'cat /proc/sys/kernel/random/boot_id') == env['boot_id'], 'segment expectation or boot changed')
        expected_boundary = block[1] if len(block) == 2 else None
        require(segment.get('boundary_expected') == expected_boundary, 'fixed active boundary changed')
        if phase['name'] != 'final-cleanup-quiet':
            require(segment['operation'] == phase_records[phase['name']], 'segment Start/single operation differs')
        if expected_boundary is not None:
            require(segment['boundary_operation'] == phase_records[expected_boundary['name']], 'same-window boundary operation differs')
        clock_indexes = []
        for key in ('clock_before', 'clock_after'):
            clock = segment[key]; require(clock in value['clocks'] and clock not in used_clocks, 'unbound/reused clock bracket')
            used_clocks.append(clock)
            observed(clock['raw'], project.sampler_script(remote_root, 'clock', data['run_id'], env['boot_id']))
            clock_indexes.append(observations[(clock['raw']['path'], clock['raw']['sha256'])]['command'])
        require(clock_indexes[0] < clock_indexes[1], 'actual calibration order differs')
        begin_index = observations[(segment['begin_boot']['path'], segment['begin_boot']['sha256'])]['command']
        end_index = observations[(segment['end_boot']['path'], segment['end_boot']['sha256'])]['command']
        require(begin_index < clock_indexes[0] < clock_indexes[1] < end_index, 'clock bracket escaped continuous segment')
        if phase['name'] != 'final-cleanup-quiet':
            require(clock_indexes[0] < segment['operation']['click']['command'] < clock_indexes[1], 'calibration does not bracket real operation click')
        require(segment['sampler'] in value['samplers'], 'actual sampler observation missing')
        begin, _ = sampler_rows(segment['sampler'], data['run_id'], env['boot_id'])
        sampler = segment['sampler']; stop_file = remote_root + '/sampler-stop'; marker = sampler['exit_marker']
        expected_script = ('unset LD_LIBRARY_PATH LD_PRELOAD; ' + remote_root + '/sampler sample ' + data['run_id'] + ' ' + env['boot_id'] +
            ' 900000 10 ' + stop_file + '; task_haptic_rc=$?; printf "\\n' + marker + '%s\\n" "$task_haptic_rc"')
        require(sampler['argv'] == [value['hdc'], '-t', env['target'], 'shell', expected_script], 'executed sampler command differs from product helper protocol')
        maps = observed(segment['sampler']['maps'], 'cat /proc/' + str(begin['pid']) + '/maps')
        require(any(line.split()[-1] == remote_root+'/sampler' for line in maps.splitlines() if line.split()), 'actual sampler executable is not mapped')
        for soname in helper['DT_NEEDED']:
            expected_paths = set(product.runtime_guest_paths(helper, soname))
            paths = {line.split()[-1] for line in maps.splitlines() if line.split() and
                (line.split()[-1] in expected_paths or line.split()[-1].endswith('/' + soname) or
                 soname == 'libc.so' and line.split()[-1].endswith('/ld-musl-aarch64.so.1'))}
            require(paths == expected_paths and any(next(iter(paths)) in observed(p['observation']) for p in value['helper_guest_DSOs'] if p['soname'] == soname),
                    'sampler did not actually map the hashed product DSO: ' + soname)
        result = {'phase': segment['phase'], 'metrics': segment_metrics(segment, data, env['boot_id'])}
        if expected_boundary is not None:
            interval = clock_bounds([segment['clock_before'], segment['clock_after']], data['run_id'], env['boot_id'])
            result['boundary'] = active_boundary_metrics(segment, data, env['boot_id'], journals[phase['role']], interval)
            _, samples = sampler_rows(segment['sampler'], data['run_id'], env['boot_id'])
            require(all(not sample['running'] for sample in samples if sample['before_ns'] >= samples[-1]['after_ns']-400000000),
                    'VDI still active after real Stop/Release')
            result['boundary']['quiet_audio'] = audio_metrics(segment['audio_capture'], expected_boundary,
                pcm.pcm_values(checked(data['reference']).read_bytes()))
        metrics.append(result)
    require(len(used_clocks) == len(value['clocks']), 'unrelated clock calibrations in evidence')
    for role, item in value['roles'].items():
        initial = item['token_bindings']['initial']; final = item['token_bindings']['final']
        calls = [row for row in value['phases'] + value['cleanup_operations'] if row['role'] == role]
        require(command_index(item['bms']) < command_index(initial['bms_before']) and
                command_index(initial['bms_after']) < min(row['click']['command'] for row in calls) and
                command_index(final['bms_before']) > max(command_index(row['end_boot']) for row in calls),
                'actual initial/final BMS-token observations do not bracket role operations')
    verify_capture_requests(value['qmp']['requests'], value['segments'])
    cleanup = value['cleanup']
    require(len(cleanup['roles']) == 2, 'both actual owned HAPs must be removed')
    for role in cleanup['roles']:
        require(role['bundle'] in {v[0] for v in ROLES.values()} and
                commands[role['uninstall_command']]['argv'] == [value['hdc'], '-t', env['target'], 'uninstall', role['bundle']] and
                observed(role['absence'], 'test ! -d /data/app/el2/100/base/' + role['bundle'] + ' && test -z "$(pidof ' + role['bundle'] + ')"') == '', 'actual owned process/private data cleanup failed')
    shared.assert_bundles_absent(observed(cleanup['bms_absent'], 'bm dump -a'), [v[0] for v in ROLES.values()])
    shared.assert_ams_absent(observed(cleanup['ams_absent'], 'aa dump -a -u 100'), [v[0] for v in ROLES.values()])
    require(observed(cleanup['final_boot'], 'cat /proc/sys/kernel/random/boot_id') == env['boot_id'], 'cleanup switched guest')
    ui_challenge = cleanup['ui_challenge']; require(re.fullmatch('[a-f0-9]{32}', ui_challenge), 'actual UI nonce missing')
    ui_paths = sorted({p for row in commands if len(row['argv']) == 5 and row['argv'][3] == 'shell'
        for p in re.findall(r'/data/local/tmp/qemu-capability-ui-' + ui_challenge + r'-[1-9][0-9]*\.(?:json|png)', row['argv'][4])})
    all_ui_paths = {p for row in commands if len(row['argv']) == 5 and row['argv'][3] == 'shell'
        for p in re.findall(r'/data/local/tmp/qemu-capability-ui-[a-f0-9]{32}-[1-9][0-9]*\.(?:json|png)', row['argv'][4])}
    require(ui_paths and set(ui_paths) == all_ui_paths, 'actual complete UI-owned nonce/path set differs')
    paths, script = project.private_cleanup_script(remote_root, ui_paths)
    require(cleanup['private_paths'] == paths and observed(cleanup['private_removal'], script) == '',
            'exact owned helper/UI deletion and absence command missing')
    return dict(scope='bound_ordinary_public_calls_fresh_independent_PCM_and_read_only_time_VDI_only',
        archive_sha256=sha(archive), boot_id=env['boot_id'], run_id=data['run_id'], roles=binding_results, phases=len(project.phases()),
        segments=metrics, first_frame_native_log_freshness_verified=False, physical_motor_or_HD_haptics_verified=False,
        cross_generation_callback_gap_closed=False, first_artifact_behavior_gate_passed=False, ledger_closed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('evidence', 'archive', 'boot', 'output'): parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    commands = []
    result = verify_evidence(args.evidence, args.archive, args.boot, command=signatures.Commands(args.output / 'commands', commands))
    project.write(args.output / 'result.json', result)
    project.write(args.output / 'commands.json', commands)
    print(json.dumps({'scope': result['scope'], 'phases': result['phases'], 'ledger_closed': False}))


if __name__ == '__main__': main()
