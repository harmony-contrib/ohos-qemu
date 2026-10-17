#!/usr/bin/env python3
"""Independently replay two ordinary callers' actual MIC/VOIP focus evidence."""
import argparse
import json
from pathlib import Path
import re
from types import SimpleNamespace

import audio_focus_observation as observation
import media_capture_contract as contract
from audio_capture_permission import select as microphone_node
from batch_media_audio_capture_challenge import load_reference, phase_content
from batch_media_audio_event_challenge import verify as verify_native
from guest_ui import select_node
from run_normal_hap_probe import require_normal_identity
from spring_loading_input import binding
from verify_audio_capture_results import checked_file, sha, token, verify_tools

SCOPE = 'ordinary_dual_UID_MIC_VOIP_focus_with_real_BG_ANS_and_independent_PCM'
HERE = Path(__file__).resolve().parent


def referenced(value, key):
    path = Path(value[key + '_path'])
    if not path.is_absolute() or sha(path) != value.get(key + '_sha256'):
        raise ValueError('actual focus evidence missing or changed: ' + key)
    return path


def interval(value):
    if (not isinstance(value, list) or len(value) != 2 or any(type(v) is not int for v in value) or
            not 0 < value[0] <= value[1]):
        raise ValueError('real guest monotonic operation interval required')
    return value


def completed_native(row, kind, expected):
    log = row['completion_log']
    path = Path(log['path'])
    if not path.is_absolute() or sha(path) != log['sha256']:
        raise ValueError('native focus completion log changed')
    lines = path.read_text().splitlines()
    found = []
    for index, line in enumerate(lines):
        try:
            value = json.loads(line)
        except ValueError:
            if index == len(lines) - 1:
                break  # The live log may already contain the next partial row.
            raise ValueError('malformed middle row in native focus completion log')
        if not isinstance(value, dict) or value.get('run_id') != expected['run_id']:
            raise ValueError('foreign native focus completion log')
        if value.get('type') == kind and value.get('action') == expected['action']:
            found.append(value)
    if found != [expected] or row.get('native_completion') != expected:
        raise ValueError('actual native focus completion missing, duplicated or different')


def actor_tokens(actor, run, capture):
    from hap_identity_binding import bms_application_identity
    from verify_audio_capture_results import verify_token_observation
    uid, bundle = actor['uid'], actor['bundle']
    original_bms = bms_application_identity(referenced(actor, 'identity').read_text(), bundle)
    rows = actor['tokens']
    if not rows:
        raise ValueError('actual ordinary focus permission observations missing')
    token_id, clock, previous_shell, previous_command = None, 0, -1, -1
    microphone, background = [], []
    for row in rows:
        v = row['observation']
        if type(row.get('bms_before_observation')) is not int or row['bms_before_observation'] <= previous_shell:
            raise ValueError('Focus token queries must use fresh ordered original observations')
        if v.get('operation') not in ('query', 'query-background'):
            raise ValueError('Focus only permits its two read-only token operations')
        if verify_token_observation(row, capture, run, uid, bundle=bundle,
                operation=v['operation'], explicit_bundle=True, previous_command=previous_command) != original_bms:
            raise ValueError('Focus token differs from the actual original BMS application identity')
        previous_shell = row['bms_after_observation']
        previous_command = capture['guest_shell_observations'][previous_shell]['command_index']
        state, current = token(v, run, uid, bundle=bundle, operation=v['operation'], allow_transition=True)
        if token_id is None: token_id = current
        if current != token_id or v['before_ns'] < clock:
            raise ValueError('focus actor token identity/clock changed')
        clock = v['after_ns']
        (background if v['operation'] == 'query-background' else microphone).append((row['phase'], state, v))
    if (len(microphone) < 3 or microphone[0][0] != 'before-launch' or microphone[0][1] != -1 or
            microphone[-1][0] != 'final' or microphone[-1][1] != 0 or
            len(background) < 2 or background[0][0] != 'background' or background[-1][0] != 'final-background' or
            any(state != 0 or v['before'] != 0 for _, state, v in background)):
        raise ValueError('focus MIC and normal background permission boundaries missing')
    committed = [r for r in microphone if r[0] == 'after-MIC' and r[1] == 0 and r[2]['before'] == 0]
    if not committed or any(
            state != 0 or v['before'] != 0 for _, state, v in microphone if v['before_ns'] > committed[0][2]['after_ns']):
        raise ValueError('focus caller MIC grant changed or was not actually committed')
    return token_id


def journal(actor, run, mode):
    files = actor['files']
    names = actor['background_journal']
    prefix = 'audio-event-' + run + '-mode' + str(mode) + '-background-'
    if names != [prefix + str(i).zfill(3) + '.json' for i in range(len(names))]:
        raise ValueError('ordinary focus lifecycle sequence incomplete or replayed')
    rows = [json.loads(checked_file(files[name]).read_text()) for name in names]
    if any(r.get('run_id') != run or r.get('mode') != mode for r in rows):
        raise ValueError('focus lifecycle belongs to another actor/run')
    expected = ['notification_initial', 'notification_authorized', 'native_start_requested', 'native_microphone_ready',
                'background_started', 'native_finished', 'background_stopped',
                'background_cancel_observer_removed', 'background_suspend_observer_removed']
    actual = [r.get('event') for r in rows if r.get('event') not in ('continuous_task_cancel', 'continuous_task_suspend')]
    if actual != expected:
        raise ValueError('focus ordinary native/task/notification/subscription lifecycle failed')
    by_event = {r['event']: r for r in rows}
    if (json.loads(by_event['notification_initial']['detail']) != {'enabled': actor['notification_initial']} or
            json.loads(by_event['notification_authorized']['detail']) != {'enabled': True} or
            json.loads(by_event['native_start_requested']['detail']) != {'needs_background': True} or
            json.loads(by_event['native_finished']['detail']) !=
            {'native_status': 1, 'native_still_running': False, 'background_failed': False}):
        raise ValueError('actual background notification/native completion disagrees with UIAbility')
    for row in rows:
        if row['event'] == 'continuous_task_suspend' and json.loads(row['detail']).get('suspendState') is not False:
            raise ValueError('ordinary focus audio task was suspended')
        if row['event'] == 'continuous_task_cancel' and json.loads(row['detail']).get('expected_stop') is not True:
            raise ValueError('ordinary focus task canceled before cleanup')
    return json.loads(by_event['background_started']['detail'])


def permission(actor, run, mode, mic_labels, notification_contract):
    action = actor['mic_action']
    path = Path(action['layout'])
    if (sha(path) != action['layout_sha256'] or action.get('decision') != 'ALLOW' or
            microphone_node(json.loads(path.read_text()), mic_labels, False) != action.get('selected_node')):
        raise ValueError('actual focus MIC authorization UI differs')
    value = json.loads(checked_file(actor['files']['audio-event-' + run + '-mode' + str(mode) + '-permission.json']).read_text())
    if (value.get('run_id') != run or value.get('mode') != mode or
            value.get('permissions') != ['ohos.permission.MICROPHONE'] or
            value.get('auth_results') != [0] or type(value['auth_results'][0]) is not int or
            value.get('dialog_shown_results') != [True] or type(value['dialog_shown_results'][0]) is not bool):
        raise ValueError('actual focus public permission request differs from token/UI')
    if type(actor.get('notification_initial')) is not bool:
        raise ValueError('actual initial notification enabled state missing')
    action = actor['notification_action']
    if actor['notification_initial']:
        if action is not None: raise ValueError('unexpected notification authorization action')
    else:
        path = Path(action['layout'])
        if (sha(path) != action['layout_sha256'] or observation.notification_node(
                json.loads(path.read_text()), notification_contract) != action['selected_node']):
            raise ValueError('actual focus notification authorization dialog differs')


def services(actor, started):
    active, cleanup = [], []
    for row in actor['service_snapshots']:
        clock = interval(row['actual_clock_interval'])
        uid_text = referenced(row, 'uid_dump').read_text()
        all_text = referenced(row, 'all_dump').read_text()
        ans_text = referenced(row, 'ans_dump').read_text()
        if row['phase'] == 'cleanup':
            own = [v for v in observation.records(uid_text) if observation.integer(v, 'uid') == actor['uid']]
            full = [v for v in observation.records(all_text) if observation.integer(v, 'uid') == actor['uid']]
            if own or full: raise ValueError('ordinary focus task remained after public cleanup')
            if 'notification list:\n' in ans_text:
                notifications = observation.records(ans_text, notification=True)
                if any(observation.integer(v, 'OwnerUid') == actor['uid'] and
                       observation.integer(v, 'Id') == started['notificationId'] for v in notifications):
                    raise ValueError('owned focus background notification remained after public cleanup')
            elif not ans_text.strip().endswith('no notification') or any(
                    text in ans_text.lower() for text in ('error', 'denied', 'invalid')):
                raise ValueError('actual notification cleanup observation failed')
            # The empty-list observation is paired with the earlier actual
            # active join, public stop completion and both task absence dumps;
            # an isolated empty ANS dump cannot satisfy this verifier.
            cleanup.append(clock)
        else:
            actual = observation.active_task(uid_text, all_text, ans_text, actor['uid'], actor['pid'], actor['bundle'],
                                            started['continuousTaskId'], started['notificationId'])
            if actual != row['observation']:
                raise ValueError('focus service summary differs from actual raw service records')
            active.append(clock)
    if not active or len(cleanup) != 1 or cleanup[0][0] < max(c[1] for c in active):
        raise ValueError('actual focus active and cleanup service observations missing')
    return active, cleanup[0]


def verify_capture_boot(capture, value, boot):
    if capture.get('target') != value['target'] or capture.get('device') != value['device']:
        raise ValueError('focus producer target/device differs from enclosing run')
    capture_boot = Path(capture['boot'])
    if sha(capture_boot) != capture['boot_sha256'] or json.loads(capture_boot.read_text()) != boot:
        raise ValueError('focus producer has another enclosing boot receipt')


def verify_application_cleanup(value, capture):
    """Replay real lifecycle cleanup after retained public focus observations."""
    from audio_capture_runtime import BOOT_SCRIPT, cleanup_boot_prefix
    from hdc_transport import failed
    bundles = list(contract.BUNDLES); cleanup = value.get('owned_application_cleanup', {})
    if (cleanup.get('complete') is not True or cleanup.get('errors') != [] or capture.get('cleanup_boot_failure') or
            cleanup.get('boot_id') != value['boot_id'] or
            cleanup.get('bundles') != bundles or cleanup.get('confirmed_installed') != bundles or
            cleanup.get('scope') != 'owned_Focus_HAP_lifecycle_cleanup_NOT_public_Stop_Release_evidence' or
            len(cleanup.get('roles', [])) != 2 or len(cleanup.get('uninstalls', [])) != 2):
        raise ValueError('complete real owned Focus application cleanup required')
    commands = capture['orchestration_commands']; used = set()
    def output(index, argv):
        if type(index) is not int or index in used or not 0 <= index < len(commands):
            raise ValueError('missing/reused Focus cleanup command')
        used.add(index); command = commands[index]
        if command['argv'] != argv or command.get('exit_code') != 0 or command.get('timed_out'):
            raise ValueError('actual Focus cleanup command failed or differs')
        streams = []
        for name in ('stdout', 'stderr'):
            path = Path(command[name + '_path'])
            if sha(path) != command[name + '_sha256']: raise ValueError('Focus cleanup transport log changed')
            streams.append(path.read_text().replace('\r', ''))
        if streams[1] or failed(*streams): raise ValueError('actual Focus cleanup transport failed')
        return streams[0]
    rows = cleanup.get('observations', []); indices = [r['command_index'] for r in rows]
    if not rows or indices != sorted(set(indices)): raise ValueError('ordered unique Focus cleanup observations required')
    for row in rows:
        index = row['command_index']
        if type(index) is not int or not 0 <= index < len(commands): raise ValueError('Focus observation command missing')
        argv = commands[index]['argv']
        if (len(argv) != 5 or argv[:4] != [capture['hdc']['argv0'], '-t', value['target'], 'shell']):
            raise ValueError('Focus cleanup belongs to another transport/target')
        suffix = re.fullmatch(re.escape(row['script']) +
            r'; focus_rc=\$\?; printf "\\n(__FOCUS_EXIT_[a-f0-9]{32}__=)%s\\n" "\$focus_rc"', argv[4])
        if suffix is None: raise ValueError('exact Focus cleanup shell/exit wrapper required')
        text = output(index, argv)
        footer = re.search(r'(?:^|\n)' + re.escape(suffix[1]) + r'0\n$', text)
        if footer is None or text[:footer.start()].rstrip('\n') != row['raw']:
            raise ValueError('Focus cleanup guest exit/raw observation differs')
    def one(label, script=None):
        matches = [r for r in rows if r['label'] == label]
        if len(matches) != 1 or script is not None and matches[0]['script'] != script:
            raise ValueError('required actual Focus cleanup observation missing: ' + label)
        return matches[0]
    boot = value['boot_id']
    for row in rows:
        if row['script'] == BOOT_SCRIPT and row['raw'].strip() != boot:
            raise ValueError('Focus cleanup observed another kernel')
    one('focus-application-cleanup-boot-before', BOOT_SCRIPT)
    one('focus-application-cleanup-boot-after', BOOT_SCRIPT)
    for bundle, role, uninstall in zip(bundles, cleanup['roles'], cleanup['uninstalls']):
        if role.get('bundle') != bundle or role.get('kernel_and_ability_absent') is not True:
            raise ValueError('Focus cleanup role is foreign/incomplete')
        before = one('focus-stop-boot-before-' + bundle, BOOT_SCRIPT)
        stopped = one('stop-owned-' + bundle, cleanup_boot_prefix(boot) + 'aa force-stop ' + bundle)
        after = one('focus-stop-boot-after-' + bundle, BOOT_SCRIPT)
        ready = one('focus-uninstall-boot-before-' + bundle, BOOT_SCRIPT)
        if stopped['raw'].strip() != 'force stop process successfully.': raise ValueError('Focus stop did not succeed')
        drain = [r for r in rows if stopped['command_index'] < r['command_index'] < after['command_index']]
        if len(drain) < 4 or [r['label'] for r in drain[-4:]] != ['owned-process-drain', 'owned-ability-drain'] * 2:
            raise ValueError('two actual Focus kernel/AA absence rounds required')
        for pids, aa in zip(drain[-4::2], drain[-3::2]):
            expected = ('focus_pids=$(pidof ' + bundle + '); if test -n "$focus_pids"; '
                        'then printf "%s\\n" "$focus_pids"; else echo ABSENT; fi')
            if (pids['script'] != expected or pids['raw'].strip() != 'ABSENT' or aa['script'] != 'aa dump -a -u 100' or
                    not re.search(r'^User ID #100\s*$', aa['raw'], re.M) or 'AppRunningRecords:' not in aa['raw'] or
                    re.search(r'(?<![A-Za-z0-9_.])' + re.escape(bundle) + r'(?![A-Za-z0-9_.])', aa['raw'])):
                raise ValueError('Focus kernel/AA cleanup does not prove absence')
        argv = [capture['hdc']['argv0'], '-t', value['target'], 'uninstall', bundle]
        raw = output(uninstall['command_index'], argv)
        if (uninstall['bundle'] != bundle or uninstall['argv'] != argv or uninstall['raw'] != raw or
                uninstall.get('already_absent_after_failed_install') is not False or
                not re.search('uninstall bundle successfully', raw, re.I) or re.search(r'\[Fail\]|failed', raw, re.I) or
                not before['command_index'] < stopped['command_index'] < after['command_index'] < ready['command_index'] < uninstall['command_index']):
            raise ValueError('actual owned Focus uninstall missing or out of order')
        absence = one('focus-uninstalled-data-and-process-absent-' + bundle,
            'test ! -d /data/app/el2/100/base/' + bundle + ' && test -z "$(pidof ' + bundle + ')"')
        if absence['command_index'] <= uninstall['command_index']: raise ValueError('Focus absence predates uninstall')
    bms = one('focus-cleanup-full-BMS-list', 'bm dump -a')
    aa = one('focus-cleanup-full-AA-list', 'aa dump -a -u 100')
    if ('com.ohos.' not in bms['raw'] or not re.search(r'^User ID #100\s*$', aa['raw'], re.M) or
            'AppRunningRecords:' not in aa['raw'] or any(re.search(r'(?<![A-Za-z0-9_.])' + re.escape(b) +
            r'(?![A-Za-z0-9_.])', bms['raw'] + '\n' + aa['raw']) for b in bundles) or
            not max(r['command_index'] for r in cleanup['uninstalls']) < bms['command_index'] < aa['command_index'] <
                one('focus-application-cleanup-boot-after')['command_index']):
        raise ValueError('final Focus BMS/AA/boot cleanup proof incomplete')


def verify(args):
    value = json.loads(args.runtime.read_text())
    run, archive_sha = value['run_id'], sha(args.archive)
    if (value.get('status') != 'captured_NOT_independently_verified' or value.get('scope') != SCOPE or
            re.fullmatch('[0-9a-f]{32}', run or '') is None or value.get('archive_sha256') != archive_sha or
            value.get('boot_id') != args.boot_id or value.get('arch') != args.arch or value.get('failures') != [] or
            value.get('first_artifact_behavior_gate_passed') is not False or value.get('cleanup_errors') != [] or
            value.get('runner_sha256') != sha(HERE / 'audio_focus_runtime.py')):
        raise ValueError('two ordinary focus callers must belong to this exact artifact/boot/ABI')
    for name in ('run_audio_focus_probe.py', 'audio_focus_runtime.py', 'audio_focus_observation.py'):
        if value['sources_sha256'].get(name) != sha(HERE / name):
            raise ValueError('ordinary focus orchestration source changed')
    common = value['common']
    boot = json.loads(referenced(common, 'boot').read_text())
    binding(boot, archive_sha, args.boot_id, args.arch, value['device'], value['target'])
    capture = json.loads(referenced(common, 'capture_runtime').read_text())
    if (capture.get('archive_sha256') != archive_sha or capture.get('boot_id') != args.boot_id or
            capture.get('target') != value['target'] or capture.get('device') != value['device'] or
            capture.get('run_id') != run or capture.get('arch') != args.arch or capture.get('cleanup_errors') != [] or
            capture.get('runner_sha256') != sha(HERE / 'audio_capture_runtime.py')):
        raise ValueError('focus independent producer/tools bound to another actual run')
    verify_capture_boot(capture, value, boot)
    verify_tools(capture, args.arch, parent_persona='audio-focus')
    verify_application_cleanup(value, capture)
    configuration = {'rate': 48000, 'channels': 2, 'repeat': 60, 'timeout_ms': 90000,
                     'source_frames': 48000, 'expected_frames': 2880000}
    if common.get('producer_configuration') != configuration:
        raise ValueError('actual focus producer configuration differs')
    producer = capture['producer']
    path = Path(producer['log'])
    if (producer.get('host_exit_code') != 0 or sha(path) != producer['log_sha256'] or
            [json.loads(l) for l in path.read_text().splitlines() if l.strip()] != [
                {'event': 'feeding', 'device': 'hw:CARD=QemuCapture,DEV=1,SUBDEV=0', 'rate': 48000, 'channels': 2, 'bytes': 192000},
                {'event': 'played', 'frames': 2880000, 'rate': 48000, 'channels': 2, 'repeats': 60, 'source_bytes': 192000}]):
        raise ValueError('actual independent focus PCM producer did not finish the exact source')
    _, reference = load_reference(referenced(common, 'challenge_manifest'), referenced(common, 'challenge_pcm'), run)
    labels_path = Path(capture['labels'])
    if sha(labels_path) != capture['labels_sha256']: raise ValueError('trusted MIC resource contract changed')
    mic_labels = json.loads(labels_path.read_text())
    notification_contract = json.loads(referenced(common, 'notification_contract').read_text())
    source_map = json.loads(observation.MAP.read_text())
    if (notification_contract.get('map_sha256') != sha(observation.MAP) or
            notification_contract.get('sources_sha256') != {r['path']: r['sha256'] for r in source_map['sources'].values()} or
            notification_contract.get('translations') != source_map['authorization_dialog']['translations']):
        raise ValueError('focus background/notification source contract changed')
    actors, native, active = value['actors'], {}, {}
    for role, mode, bundle in (('owner', 1, observation.BUNDLES[0]), ('contender', 2, observation.BUNDLES[1])):
        actor = actors[role]
        identity = referenced(actor, 'identity')
        uid = require_normal_identity(identity.read_text(), bundle)
        if actor.get('uid') != uid or actor.get('mode') != mode or actor.get('bundle') != bundle:
            raise ValueError('actual ordinary focus caller identity differs')
        if actor.get('process_before') != actor.get('process_after'):
            raise ValueError('focus caller process was replaced or killed')
        process = actor['process_before']
        if (process.get('uid') != uid or process.get('pid') != actor['pid'] or type(process.get('pid')) is not int or
                process['pid'] <= 0 or type(process.get('starttime')) is not int or process['starttime'] <= 0):
            raise ValueError('actual same-process focus lifecycle missing')
        inputs = json.loads(referenced(actor, 'inputs').read_text())
        if inputs.get('kind') != 'audio-event' or inputs.get('mode') != mode or inputs.get('run_id') != run or inputs.get('bundle') != bundle or inputs.get('arch') != args.arch:
            raise ValueError('actual focus HAP role/source differs')
        contract.verify_inputs(inputs)
        contract.verify_hap(referenced(actor, 'hap'), inputs)
        for name, row in actor['files'].items():
            path = checked_file(row)
            if (path.name != name or row.get('uid') != uid or path.stat().st_size != row.get('bytes') or
                    (not (name.endswith('-permission.json') or '-background-' in name) and row.get('mode') != 600)):
                raise ValueError('actual focus native files wrong owner/mode/size')
        actor_tokens(actor, run, capture)
        permission(actor, run, mode, mic_labels, notification_contract)
        started = journal(actor, run, mode)
        active[role], _ = services(actor, started)
        results = referenced(actor, 'native_results')
        native[role] = verify_native(results, results.parent, referenced(common, 'challenge_manifest'),
                                    referenced(common, 'challenge_pcm'), identity, run, mode)
        # Implemented below from the exact native request/reply contract.
        verify_fresh_snapshot(actor, native[role], reference, run)
    if actors['owner']['uid'] == actors['contender']['uid'] or actors['owner']['pid'] == actors['contender']['pid']:
        raise ValueError('focus requires two independent actual ordinary callers')
    verify_causality(actors, native, active)
    return {'status': 'pass', 'scope': SCOPE, 'run_id': run, 'arch': args.arch, 'boot_id': args.boot_id,
            'archive_sha256': archive_sha, 'actors': native, 'runtime_sha256': sha(args.runtime),
            'verifier_sha256': sha(Path(__file__)), 'closed_requirements': [], 'first_artifact_behavior_gate_passed': False}


def verify_causality(actors, native, active):
    ready, ack, roots = {}, {}, {}
    for role in ('owner', 'contender'):
        actor, evidence = actors[role], native[role]
        ready[role] = {r['action']: r for r in evidence['signals']}
        ack[role] = {r['action']: r for r in evidence['acks']}
        roots[role] = {}
        if len(actor['ready_json']) != 2 or len(actor['acks']) != 2:
            raise ValueError('each actual focus actor must complete exactly two fresh actions')
        for row in actor['ready_json']:
            path = Path(row['path'])
            if sha(path) != row['sha256'] or json.loads(path.read_text()) != row['observation']:
                raise ValueError('actual native focus readiness file changed')
            v = row['observation']
            signal = ready[role][row['action']]
            completed_native(row, 'event_ready', signal)
            if v.get('run_id') != evidence['run_id']:
                raise ValueError('actual native focus run changed')
            if (v.get('uid') != actor['uid'] or v.get('action') != row['action'] or
                    v.get('nonce') != signal['nonce'] or v.get('monotonic_ns') != signal['monotonic_ns']):
                raise ValueError('actual native focus readiness differs from its native log')
            if interval(row['actual_clock_interval'])[0] < signal['monotonic_ns']:
                raise ValueError('focus readiness collected before its native completion')
        for row in actor['acks']:
            action = row['action']
            low, high = interval(row['actual_clock_interval'])
            actual = ack[role][action]
            data = checked_file(actor['files'][row['file']]).read_bytes()
            if (row.get('nonce') != ready[role][action]['nonce'] or data != (row['nonce'] + '\n').encode() or
                    not low <= actual['monotonic_ns'] <= high + 1000000000):
                raise ValueError('actual root focus ACK missing, replayed or outside its operation interval')
            roots[role][action] = [low, high]
    before_start = roots['contender']['contender_start'][0]
    second_authorized = ready['contender']['contender_start']['monotonic_ns']
    for role in ('owner', 'contender'):
        point = actors[role]['fresh_snapshots'][0]
        requested = interval(point['request_clock_interval'])
        reply = point['observation']
        if (requested[0] < second_authorized or reply['reply_prepared_ns'] > before_start or
                any(not any(second_authorized <= c[0] <= c[1] <= requested[0] for c in active[other])
                    for other in ('owner', 'contender'))):
            raise ValueError('fresh MIC observations must follow both background grants/tasks and precede VOIP Start')
    start = native['contender']['start_interval']
    forced = [v for v in native['owner']['callbacks'] if v.get('kind') == 1 and v.get('code') == 0 and v.get('hint') == 3]
    if (len(forced) != 1 or not start['before_ns'] <= forced[0]['monotonic_ns'] <= start['after_ns'] + 500000000 or
            roots['owner']['focus_begin'][0] < forced[0]['monotonic_ns'] or
            roots['contender']['contender_start'][0] > start['before_ns']):
        raise ValueError('owner actual forced STOP is not caused by the new ordinary VOIP Start')
    contender_rows = [json.loads(l) for l in referenced(actors['contender'], 'native_results').read_text().splitlines() if l.strip()]
    release = [r for r in contender_rows if r.get('type') == 'event_step' and r.get('name') == 'release']
    stop = [r for r in contender_rows if r.get('type') == 'event_stop']
    cleanup = [r for r in actors['contender']['service_snapshots'] if r['phase'] == 'cleanup']
    if (len(release) != 1 or len(stop) != 1 or stop[0].get('actual') != 0 or
            not ack['contender']['contender_stop']['monotonic_ns'] <= stop[0]['monotonic_ns'] <= release[0]['monotonic_ns'] or
            roots['owner']['focus_end'][0] < release[0]['monotonic_ns'] or len(cleanup) != 1 or
            roots['owner']['focus_end'][0] < interval(cleanup[0]['actual_clock_interval'])[1]):
        raise ValueError('owner MIC restarted before actual contender Stop/Release/task cleanup')
    if not any(c[1] < ready['contender']['contender_start']['monotonic_ns'] for c in active['owner']):
        raise ValueError('owner had no verified recording task before contender microphone authorization')


def verify_fresh_snapshot(actor, native, reference, run):
    action, phase = ('focus_begin', 1) if actor['mode'] == 1 else ('contender_start', 0)
    points = actor['fresh_snapshots']
    if len(points) != 1 or points[0].get('action') != action:
        raise ValueError('one requested fresh microphone PCM observation per actor required')
    point = points[0]
    request, reply, pcm = [checked_file(actor['files'][point[k + '_file']]) for k in ('request', 'reply', 'pcm')]
    value = json.loads(reply.read_text())
    signal = next(r for r in native['signals'] if r['action'] == action)
    nonce = signal['nonce']
    if (point.get('nonce') != nonce or request.read_bytes() != (nonce + '\n').encode() or
            value != point['observation'] or value.get('type') != 'event_fresh_reply' or
            value.get('run_id') != run or value.get('action') != action or value.get('ready_nonce') != nonce or
            value.get('request_nonce') != nonce or value.get('uid') != actor['uid'] or value.get('euid') != actor['uid'] or
            value.get('phase') != phase or value.get('persisted') is not True or value.get('pcm_basename') != pcm.name):
        raise ValueError('fresh focus PCM nonce, source actor or persisted reply differs')
    rows = [json.loads(l) for l in referenced(actor, 'native_results').read_text().splitlines() if l.strip()]
    replies = [r for r in rows if r.get('type') == 'event_fresh_reply']
    if replies != [value] or any(r.get('type') == 'event_fresh_error' for r in rows):
        raise ValueError('fresh PCM reply differs from actual native completion/error log')
    completed_native(point, 'event_fresh_reply', value)
    for key in ('state_result', 'frames_result', 'timestamp_result', 'source_result', 'rate_result', 'channels_result', 'format_result'):
        if type(value.get(key)) is not int or value[key] != 0:
            raise ValueError('fresh MIC public getter failed: ' + key)
    # These numeric enums are from the exact native_audiostream_base.h whose
    # bytes are bound by the actual API26 HAP native/SDK input contract.
    for key, expected in {'state': 2, 'source_type': 0, 'rate': 48000, 'channels': 2, 'format': 1, 'bytes': 96000}.items():
        if type(value.get(key)) is not int or value[key] != expected:
            raise ValueError('fresh MIC actual state/format/size differs: ' + key)
    keys = ('request_seen_ns', 'requested_offset', 'request_frames', 'request_position', 'request_timestamp_ns',
            'request_query_before_ns', 'request_query_after_ns', 'frames', 'position', 'timestamp_ns', 'query_before_ns',
            'query_after_ns', 'copy_before_ns', 'copy_after_ns', 'first_callback_ns', 'last_callback_ns',
            'callback_count', 'offset', 'end_offset', 'reply_prepared_ns')
    if any(type(value.get(k)) is not int or value[k] < 0 for k in keys):
        raise ValueError('fresh MIC actual callback/clock bounds invalid')
    for prefix in ('request_', ''):
        before, after, stamp = (value[prefix + name] for name in ('query_before_ns', 'query_after_ns', 'timestamp_ns'))
        if not 0 <= after - before <= 200000000 or not before - 1000000000 <= stamp <= after + 100000000:
            raise ValueError('fresh MIC timestamp clock domain/query interval invalid')
    low, high = interval(point['request_clock_interval'])
    if (not max(low, signal['monotonic_ns']) <= value['request_seen_ns'] <= high + 1000000000 or
            not value['request_seen_ns'] <= value['request_query_before_ns'] <= value['request_query_after_ns'] <= value['query_before_ns'] or
            not value['request_seen_ns'] < value['first_callback_ns'] <= value['last_callback_ns'] <=
            value['copy_before_ns'] <= value['copy_after_ns'] <= value['query_before_ns'] <= value['query_after_ns'] <= value['reply_prepared_ns'] or
            value['query_after_ns'] - value['last_callback_ns'] > 250000000 or
            value['frames'] <= value['request_frames'] or value['position'] <= value['request_position'] or
            value['timestamp_ns'] <= value['request_timestamp_ns'] or value['offset'] < value['requested_offset'] or
            value['end_offset'] - value['offset'] != 96000 or value['offset'] % 4 or value['callback_count'] <= 0):
        raise ValueError('fresh MIC bytes were not delivered after this actual request while RUNNING')
    name = 'audio-event-' + run + '-mode' + str(actor['mode']) + ('-primer-full.pcm' if phase == 0 else '.pcm')
    data = checked_file(actor['files'][name]).read_bytes()
    fresh = pcm.read_bytes()
    if len(fresh) != 96000 or data[value['offset']:value['end_offset']] != fresh:
        raise ValueError('fresh requested PCM differs from actual full native callback data')
    kind = 'event_primer_chunk' if phase == 0 else 'event_chunk'
    chunks = [r for r in rows if r.get('type') == kind and r['offset'] < value['end_offset'] and
              r['offset'] + r['bytes'] > value['offset']]
    covered = value['offset']
    for row in chunks:
        if max(row['offset'], value['offset']) != covered or row['phase'] != phase:
            raise ValueError('fresh requested PCM actual callback coverage invalid')
        covered = min(value['end_offset'], row['offset'] + row['bytes'])
    if (covered != value['end_offset'] or len(chunks) != value['callback_count'] or
            chunks[0]['monotonic_ns'] != value['first_callback_ns'] or chunks[-1]['monotonic_ns'] != value['last_callback_ns']):
        raise ValueError('fresh PCM actual callback count/range differs from the reply')
    actual = phase_content(fresh, reference)
    if actual != point['correlation']:
        raise ValueError('fresh PCM summary differs from independently replayed correlation')
    return value


def verify_evidence(document, archive, boot_id, arch):
    archive = Path(archive)
    if (document.get('status') != 'pass' or document.get('persona') != 'audio-focus' or
            document.get('scope') != SCOPE or document.get('archive_sha256') != sha(archive) or
            document.get('boot_id') != boot_id or document.get('arch') != arch or
            document.get('failures') != [] or document.get('runner_sha256') != sha(HERE / 'run_audio_focus_probe.py')):
        raise ValueError('two-UID focus case differs from the actual archive/boot/ABI')
    result_path, runtime_path = Path(document['result']), Path(document['runtime'])
    if (not result_path.is_absolute() or result_path.name != 'verified-result.json' or
            not runtime_path.is_absolute() or runtime_path != result_path.parent / 'focus/runtime.json' or
            sha(result_path) != document.get('result_sha256') or sha(runtime_path) != document.get('runtime_sha256')):
        raise ValueError('actual independently verified focus result/runtime changed')
    actual = verify(SimpleNamespace(runtime=runtime_path, archive=archive, boot_id=boot_id, arch=arch))
    if actual != json.loads(result_path.read_text()):
        raise ValueError('two-UID focus summary differs from independent actual replay')
    return actual


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'runtime', 'output'): p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--boot-id', required=True)
    p.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = p.parse_args()
    try: result = verify(args)
    except (ValueError, OSError, KeyError, TypeError, IndexError) as error:
        result = {'status': 'fail', 'scope': SCOPE, 'error': str(error), 'closed_requirements': [],
                  'first_artifact_behavior_gate_passed': False}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'error': result.get('error')}))
    return result['status'] != 'pass'


if __name__ == '__main__': raise SystemExit(main())
