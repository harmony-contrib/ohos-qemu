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
import batch_media_knowledge_suite as shared
import batch_apps_contact_picker_coordinator as signatures
from enclosing_acceptance_guest import validate_binding

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
    return dict(uid=app['uid'], token_id=app['accessTokenId'], installed_remote=signatures.installed_path(raw, bundle))


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


def audio_metrics(capture, expectation, reference):
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
        require((last-first)/48000 >= 8 and rms(tail) > 64, 'actual repeated audio loop stops early')
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
    elif mode == 'loop': require(active and any(r['running'] for r in tail), 'actual VDI loop not running after two audio periods')
    else: require(active, 'actual VDI never ran for unmuted haptics')
    if mode in ('active', 'eos', 'loop'): require(not samples[0]['running'], 'VDI already running before fresh UI start')
    reference = pcm.pcm_values(checked(data['reference']).read_bytes())
    audio = audio_metrics(segment['audio_capture'], expectation, reference)
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
    from batch_media_audio_haptic_runtime import TOOLS, owned_capture_listing
    require(value['tool_sources'] == {name: record(HERE / name) for name in TOOLS}, 'collector or dependent checker source changed')
    commands = value['commands']; shared.verify_commands(commands, value['hdc'], env['target'])
    observations = {}
    for row in value['observations']:
        actual = shared.exact_script(commands[row['command']], row['script'])
        require(actual == checked(row['raw']).read_text(), 'normalized observation differs from actual HDC output')
        observations[(row['raw']['path'], row['raw']['sha256'])] = row
    def observed(raw, script=None):
        key = (raw['path'], raw['sha256'])
        require(key in observations, 'raw result lacks actual guest command')
        row = observations[key]
        if script is not None: require(row['script'] == script, 'claimed actual guest script differs')
        return checked(raw).read_text()
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
        require(proof['soname'] == dso['soname'] and all(line.split()[0] == dso['sha256'] for line in observed(proof['observation'], proof['script']).splitlines()) and
                observed(proof['observation']).strip(), 'same-guest helper DSO link identity differs')
    require(len(value['helper_guest_DSOs']) == len(helper['product_DSOs']), 'missing actual helper dependencies')
    identities = {}; journals = {}; binding_results = {}
    for role, item in value['roles'].items():
        require(role in ROLES, 'unexpected caller role')
        project.project_binding(spec['projects'][role], role, checked(spec['challenge']))
        identity = bms_identity(observed(item['bms'], 'bm dump -n ' + ROLES[role][0]), role)
        identities[role] = identity
        proof = signatures.verify_signed_hap_artifacts(checked(item['signed_hap']), *ROLES[role], env['udid'],
            spec['signer']['dist'], checked(spec['signer']['jar']), Path(path).parent / ('verify-' + role + '-' + __import__('secrets').token_hex(4)), command)
        require(signatures.hap_contents(checked(item['signed_hap']))[1] == signatures.hap_contents(checked(spec['projects'][role]['unsigned_hap']))[1] and
                item['installed_hap']['sha256'] == item['signed_hap']['sha256'] and
                received[(item['installed_hap']['path'], item['installed_hap']['sha256'])] == identity['installed_remote'], 'signed/installed compiled payload differs')
        require(checked(item['journal_before']).read_bytes() == b'' and
                any(j['raw'] == item['journal_before'] for j in value['journals']), 'fresh journal baseline missing')
        journals[role] = parse_journal(checked(item['journal']).read_text(), data['run_id'], env['boot_id'], identity)
        for name, expected in data['files'].items():
            actual = item['inputs'][name]
            require(actual['sha256'] == expected['sha256'] and received[(actual['path'], actual['sha256'])] ==
                    '/data/app/el2/100/base/' + ROLES[role][0] + '/files/' + name, 'private genuine challenge input differs')
        for when in ('initial', 'final'):
            raw = item['token_' + when]; token = json.loads(observed(raw))
            require(token.get('kind') == 'token' and token['run_id'] == data['run_id'] and token['boot_id'] == env['boot_id'] and
                    token['bundle'] == ROLES[role][0] and token['uid'] == identity['uid'] and token['token_id'] == identity['token_id'] and
                    token['VIBRATE'] == (0 if role == 'normal' else -1) and 0 < token['before_ns'] <= token['after_ns'], 'real VIBRATE role/token boundary differs')
        binding_results[role] = dict(identity=identity, signature=proof)
    require(set(identities) == set(ROLES) and len({v['uid'] for v in identities.values()}) == 2 and
            len({v['token_id'] for v in identities.values()}) == 2, 'ordinary/denied installed identities overlap')
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
        staged = [r for r in value['staged'] if r['local'] == captured['request']]
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
    planned = [v for v in project.phases() if v['hold_ms']]
    require([v['phase'] for v in value['segments']] == [v['name'] for v in planned] + ['final-cleanup-quiet'], 'all actual PCM/HDI observation intervals required')
    metrics = []
    final_quiet = dict(name='final-cleanup-quiet', role=None, action=None, options={}, expected='ok', errors=[],
                       hold_ms=1100, audio='quiet', haptic='quiet', eos=False)
    for segment, phase in zip(value['segments'], planned + [final_quiet]):
        require(segment['expected'] == phase and observed(segment['begin_boot']) == env['boot_id'] and observed(segment['end_boot']) == env['boot_id'], 'segment expectation or boot changed')
        require(segment['sampler'] in value['samplers'], 'actual sampler observation missing')
        begin, _ = sampler_rows(segment['sampler'], data['run_id'], env['boot_id'])
        sampler = segment['sampler']; stop_file = remote_root + '/sampler-stop'; marker = sampler['exit_marker']
        expected_script = ('unset LD_LIBRARY_PATH LD_PRELOAD; ' + remote_root + '/sampler sample ' + data['run_id'] + ' ' + env['boot_id'] +
            ' 900000 10 ' + stop_file + '; task_haptic_rc=$?; printf "\\n' + marker + '%s\\n" "$task_haptic_rc"')
        require(sampler['argv'] == [value['hdc'], '-t', env['target'], 'shell', expected_script], 'executed sampler command differs from product helper protocol')
        maps = observed(segment['sampler']['maps'], 'cat /proc/' + str(begin['pid']) + '/maps')
        require(any(line.split()[-1] == remote_root+'/sampler' for line in maps.splitlines() if line.split()), 'actual sampler executable is not mapped')
        for soname in helper['DT_NEEDED']:
            paths = {line.split()[-1] for line in maps.splitlines() if line.split() and line.split()[-1].endswith('/' + soname)}
            require(len(paths) == 1 and any(next(iter(paths)) in observed(p['observation']) for p in value['helper_guest_DSOs'] if p['soname'] == soname),
                    'sampler did not actually map the hashed product DSO: ' + soname)
        metrics.append({'phase': segment['phase'], 'metrics': segment_metrics(segment, data, env['boot_id'])})
    qmp = value['qmp']['requests']
    require(qmp and all(r.get('execute') == 'human-monitor-command' and type(r.get('host_ns')) is int and
            r['host_ns'] <= r.get('completed_ns', 0) and isinstance(r.get('reply'), str) and
            'failure_reply' not in r for r in qmp), 'actual QMP HMP capture commands failed or incomplete')
    require(re.search(r'wavcapture\s+path audiodev', qmp[0]['reply']) and
            qmp[0]['arguments'] == {'command-line': 'help wavcapture'} and
            qmp[1]['arguments'] == {'command-line': 'info capture'} and qmp[1]['reply'] == '', 'actual QEMU capture syntax/initial ownership not established')
    cursor = 2
    for segment in value['segments']:
        rows = qmp[cursor:cursor+6]; cursor += 6
        capture = segment['audio_capture']; wav = checked(capture['wav']); backend = capture['backend']; phase = segment['phase']
        require(len(rows) == 6 and [r['label'] for r in rows] == [phase+'-'+s for s in
            ('before-capture', 'wavcapture', 'capture-owned', 'capture-before-stop', 'stopcapture', 'capture-after-stop')],
            'actual per-segment QMP capture ownership/order differs')
        require([r['arguments']['command-line'] for r in rows] == ['info capture', f'wavcapture {wav} {backend} 48000 16 2',
            'info capture', 'info capture', 'stopcapture 0', 'info capture'] and
            all(rows[i]['reply'] == '' for i in (0, 1, 4, 5)), 'WAV was not captured/stopped by this actual QMP sequence')
        owned_capture_listing(rows[2]['reply'], wav); owned_capture_listing(rows[3]['reply'], wav)
        require(capture['host_begin_ns'] <= rows[1]['host_ns'] <= rows[1]['completed_ns'] < rows[4]['host_ns'] <=
                rows[4]['completed_ns'] <= capture['host_end_ns'], 'actual WAV capture timestamps differ from QMP operations')
    require(cursor == len(qmp), 'unexpected extra capture action')
    cleanup = value['cleanup']
    require(len(cleanup['roles']) == 2, 'both actual owned HAPs must be removed')
    for role in cleanup['roles']:
        require(role['bundle'] in {v[0] for v in ROLES.values()} and
                commands[role['uninstall_command']]['argv'] == [value['hdc'], '-t', env['target'], 'uninstall', role['bundle']] and
                observed(role['absence'], 'test ! -d /data/app/el2/100/base/' + role['bundle'] + ' && test -z "$(pidof ' + role['bundle'] + ')"') == '', 'actual owned process/private data cleanup failed')
    shared.assert_bundles_absent(observed(cleanup['bms_absent'], 'bm dump -a'), [v[0] for v in ROLES.values()])
    shared.assert_ams_absent(observed(cleanup['ams_absent'], 'aa dump -a -u 100'), [v[0] for v in ROLES.values()])
    require(observed(cleanup['final_boot'], 'cat /proc/sys/kernel/random/boot_id') == env['boot_id'], 'cleanup switched guest')
    require(cleanup['private_removal'] and observed(cleanup['private_removal']) == '', 'owned helper/UI cleanup missing')
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
