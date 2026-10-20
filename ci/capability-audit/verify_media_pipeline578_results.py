#!/usr/bin/env python3
"""Replay original Owner/HAP/UI/token custody, then independently consume media.

No synthesized success, old image, caller-only callback, create/release result,
or summary JSON can satisfy this case. Aggregate broad-media closure stays open.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile
import math
from types import SimpleNamespace

from media_pipeline578 import (sha, parse_journal, event, verify_files, palette, tile_samples,
                               DECODE_W, DECODE_H, SCENARIOS, decode, content, audio_content, strict_json)
import media_pipeline578_contract as contract
from media_pipeline578_runtime import ui_plan, APP_FILES
from audio_capture_runtime import BUNDLE
from audio_capture_permission import select as select_mic
from verify_audio_capture_results import (checked_file, microphone_shell_body, verify_token_observation,
                                         token, verify_tools)
from run_normal_hap_probe import require_normal_identity, previous_probe_absent
from guest_process_identity import identity_shell, producer_rows
from guest_ui import select_node, command_exit, swipe_down_points
from spring_loading_input import binding
from hap_identity_binding import bms_application_identity

PERSONA = 'media-pipeline578'
SCOPE = 'ordinary_public_screen_capture_transcode_independent_AV_bytes_and_owned_boundaries578'
BATCH = ('screen-transcode', 'screen-deny', 'screen-transcode', 'screen-revoke', 'screen-transcode',
         'screen-death', 'screen-transcode', 'transcode-cancel', 'screen-transcode', 'transcode-death', 'screen-transcode')


def shell_body(runtime, index, script):
    return microphone_shell_body(runtime, index, script)[0]


def ui_body(runtime, index):
    command = runtime['orchestration_commands'][index]
    argv = command['argv']
    if (command.get('exit_code') != 0 or command.get('timed_out') or len(argv) != 5 or
            argv[:4] != [runtime['hdc']['argv0'], '-t', runtime['target'], 'shell']):
        raise ValueError('original successful owned UITest command required')
    match = re.fullmatch(r'(.*); task_ui_rc=\$\?; printf "\\n(__UITEST_EXIT_[0-9a-f]{32}__=)%s\\n" "\$task_ui_rc"', argv[4])
    if match is None:
        raise ValueError('exact original UITest command footer required')
    raw = checked_file({'path': command['log'], 'sha256': command['sha256']}).read_text()
    body, code = command_exit(raw, match[2])
    if code != 0 or '[Fail]' in body:
        raise ValueError('actual UITest operation failed')
    return match[1], body


def layout_replay(runtime, indexes, layout, bundle):
    if len(indexes) != 2 or indexes[1] != indexes[0]+1:
        raise ValueError('original ordered UITest dump/read commands required')
    dump, _ = ui_body(runtime, indexes[0]); read, raw = ui_body(runtime, indexes[1])
    match = re.fullmatch(r'test ! -e (/data/local/tmp/qemu-capability-ui-[0-9a-f]{32}-[0-9]+\.json) && uitest dumpLayout -p \1' + (' -b ' + re.escape(bundle) if bundle else ''), dump)
    if match is None or read != 'cat '+match[1]:
        raise ValueError('actual hierarchy is not the original target-bundle dump')
    value = json.loads(raw)
    if value != json.loads(Path(layout).read_text()):
        raise ValueError('saved UI hierarchy differs from original guest stdout')
    return value


def action_replay(runtime, row, expected):
    if row['selector'] != expected or sha(row['layout']) != row['layout_sha256']:
        raise ValueError('actual screen decision/continue selector changed')
    indexes = row['ui_commands']
    if len(indexes) != 3 or indexes[2] != indexes[1]+1:
        raise ValueError('actual click command missing')
    layout = layout_replay(runtime, indexes[:2], row['layout'], None if 'swipe_to' in expected else expected['bundle'])
    if 'swipe_to' in expected:
        node = select_node(layout, expected['bundle'], identifier=expected['identifier'])
        destination = select_node(layout, **expected['swipe_to'])
        points = swipe_down_points(node, destination)
        if (node != row['selected_node'] or destination != row['destination_node'] or points != row['swipe_points']):
            raise ValueError('recorded drawer gesture differs from the actual two visible nodes')
        script, _ = ui_body(runtime, indexes[2])
        if script != 'uitest uiInput swipe ' + ' '.join(map(str, points)):
            raise ValueError('original drawer gesture was not derived from actual node bounds')
        return indexes[2]
    node = select_node(layout, **expected, clickable=True)
    if node != row['selected_node']:
        raise ValueError('recorded screen control differs from actual visible node')
    x, y, w, h = node['rect']
    script, _ = ui_body(runtime, indexes[2])
    if script != f'uitest uiInput click {x+w//2} {y+h//2}':
        raise ValueError('original click was not the actual enabled node center')
    return indexes[2]


def canvas_replay(runtime, row, run):
    if sha(row['layout']) != row['layout_sha256'] or sha(row['screenshot']) != row['screenshot_sha256']:
        raise ValueError('actual compositor/Canvas observation changed')
    indexes = row['ui_commands']
    if len(indexes) != 4 or indexes != list(range(indexes[0], indexes[0]+4)):
        raise ValueError('actual compositor dump/capture/transfer commands missing')
    layout = layout_replay(runtime, indexes[:2], row['layout'], BUNDLE)
    node = select_node(layout, BUNDLE, identifier='media578-canvas')
    if node != row['node']:
        raise ValueError('actual visible screen Canvas differs')
    script, _ = ui_body(runtime, indexes[2])
    match = re.fullmatch(r'test ! -e (/data/local/tmp/qemu-capability-ui-[0-9a-f]{32}-[0-9]+\.png) && uitest screenCap -p \1', script)
    transfer = runtime['orchestration_commands'][indexes[3]]
    if (match is None or transfer.get('exit_code') != 0 or transfer.get('timed_out') or
            transfer['argv'] != [runtime['hdc']['argv0'], '-t', runtime['target'], 'file', 'recv', match[1], row['screenshot']]):
        raise ValueError('actual compositor PNG was not transferred from this owned guest')
    from PIL import Image
    with Image.open(row['screenshot']) as image:
        if image.format != 'PNG' or list(image.size) != row['display']:
            raise ValueError('actual compositor display dimensions differ')
        small = image.convert('RGB').resize((DECODE_W, DECODE_H), Image.Resampling.BOX).tobytes()
    x, y, w, h = node['rect']; width, height = row['display']
    roi = [x/width, y/height, w/width, h/height]
    if roi != row['roi']:
        raise ValueError('recorded media ROI is not the actual compositor Canvas')
    samples = tile_samples(small, roi)
    errors = [abs(channel-value) for pixel, value in zip(samples[:56], palette(run, row['cycle'])[0]) for channel in pixel]
    if max(errors) > 20 or sum(errors)/len(errors) > 8:
        raise ValueError('actual compositor did not render this cycle fresh nonce texture')
    return roi


def producer_replay(runtime):
    producer = runtime['producer']
    raw = checked_file({'path': producer['log'], 'sha256': producer['log_sha256']}).read_text()
    if len(producer['argv']) != 5 or producer['argv'][:4] != [runtime['hdc']['argv0'], '-t', runtime['target'], 'shell']:
        raise ValueError('actual PCM source used another HDC transport/guest')
    rows = producer_rows(raw, producer, remote=runtime['remote_root_directory'], repeat=60, timeout_ms=90000)
    if (rows[0] != {'event': 'feeding', 'device': 'hw:CARD=QemuCapture,DEV=1,SUBDEV=0', 'rate': 48000, 'channels': 2, 'bytes': 192000} or
            rows[-1] != {'event': 'played', 'frames': 2880000, 'rate': 48000, 'channels': 2, 'repeats': 60, 'source_bytes': 192000}):
        raise ValueError('actual root PCM source is not the existing independent 60-repeat producer')
    middle = rows[1:-1]
    if not middle or len(middle) > 2:
        raise ValueError('actual ALSA drain completion missing')
    terminal = middle[-1]
    if (set(terminal) != {'event', 'alsa_rc', 'status_rc', 'state', 'delay_frames', 'written_frames'} or
            terminal['event'] != 'drained' or terminal['alsa_rc'] not in (0, -11, -4) or
            any(type(terminal.get(k)) is not int for k in ('alsa_rc', 'status_rc', 'state', 'delay_frames', 'written_frames')) or
            (terminal['status_rc'], terminal['state'], terminal['delay_frames'], terminal['written_frames']) != (0, 1, 0, 2880000)):
        raise ValueError('actual independent producer did not drain its accepted frames')
    if terminal['alsa_rc'] != 0 and len(middle) != 2:
        raise ValueError('missing actual ALSA recovery observation')
    if len(middle) == 2:
        pending = middle[0]
        if (set(pending) != {'event', 'alsa_rc', 'state'} or pending['event'] != 'drain_pending' or
                type(pending['alsa_rc']) is not int or pending['alsa_rc'] not in (-11, -4) or
                type(pending['state']) is not int or pending['state'] not in (1, 2, 3, 5)):
            raise ValueError('invalid actual ALSA drain recovery')


def stable_replay(runtime, name, descriptor):
    records = [r for r in runtime['stable_outputs'] if r['name'] == name]
    if len(records) != 1 or len(records[0]['observations']) != 2:
        raise ValueError('original stable terminal output observations required')
    path = APP_FILES+name
    script = 'test -f ' + path + ' && test ! -L ' + path + ' && stat -c "%u %a %s" ' + path + ' && sha256sum ' + path + ' && cat /proc/uptime'
    bodies = []
    for row in records[0]['observations']:
        raw = shell_body(runtime, row['shell_observation'], script)
        if row['script'] != script or row['raw'] != raw:
            raise ValueError('output stability row differs from actual command')
        stat, digest, uptime = raw.splitlines()
        uid, mode, size = stat.split()
        if (int(uid) != descriptor['uid'] or int(mode, 8) != descriptor['mode'] or int(size) != descriptor['bytes'] or
                digest.split() != [descriptor['sha256'], path]):
            raise ValueError('terminal media bytes differ from original guest stat/SHA')
        bodies.append((stat, digest, float(uptime.split()[0]), row['shell_observation']))
    if (not all(math.isfinite(v[2]) for v in bodies) or bodies[0][:2] != bodies[1][:2] or
            bodies[1][2]-bodies[0][2] < 1 or bodies[1][3] <= bodies[0][3]):
        raise ValueError('actual media bytes/time did not remain stable across two distinct guest observations')


def death_replay(runtime, rows):
    death = runtime['death']
    script = identity_shell(BUNDLE, all_uids=False)
    before = shell_body(runtime, death['before_observation'], script)
    if before != death['before'] or int(before.split()[0]) != rows[0]['pid']:
        raise ValueError('owned death targeted another process generation')
    indexes = death['stop_shells']
    if len(indexes) < 5 or (len(indexes)-1) % 2 or indexes != list(range(indexes[0], indexes[0]+len(indexes))):
        raise ValueError('complete original controlled own-app stop observations required')
    if shell_body(runtime, indexes[0], 'aa force-stop '+BUNDLE).strip() != 'force stop process successfully.':
        raise ValueError('actual owner did not stop this ordinary application')
    pid_script = ('task_probe_pids=$(pidof ' + BUNDLE + '); if test -n "$task_probe_pids"; then printf "%s\\n" "$task_probe_pids"; else echo ABSENT; fi')
    absent = []
    for a, b in zip(indexes[1::2], indexes[2::2]):
        absent.append(previous_probe_absent(shell_body(runtime, a, pid_script), shell_body(runtime, b, 'aa dump -a -u 100')))
    if absent[-2:] != [True, True]:
        raise ValueError('own-app kernel/AA death was not independently observed twice')
    # No in-app summary or fabricated callback substitutes for process death.
    return {'pid': int(before.split()[0]), 'starttime': int(before.split()[1]), 'controlled_own_app_stop': True}


def verify(args):
    runtime = json.loads(args.runtime.read_text())
    scenario, run = runtime['scenario'], args.run_id
    if (scenario not in SCENARIOS or runtime.get('kind') != 'screen-transcode578' or runtime.get('parent_persona') != PERSONA or
            runtime.get('status') != 'captured_NOT_independently_verified' or runtime.get('archive_sha256') != sha(args.archive) or
            runtime.get('run_id') != run or runtime.get('boot_id') != args.boot_id or runtime.get('arch') != args.arch or
            runtime.get('cleanup_errors') != [] or runtime.get('cleanup_complete') is not True or
            runtime.get('owned_remote_directory_removed') is not True or runtime.get('expected_denied') is not False or
            runtime.get('runner_sha256') != sha(Path(__file__).with_name('audio_capture_runtime.py')) or
            runtime.get('process_identity_helper_sha256') != sha(Path(__file__).with_name('guest_process_identity.py')) or
            runtime.get('media578_runner_sha256') != sha(Path(__file__).with_name('media_pipeline578_runtime.py'))):
        raise ValueError('new actual artifact/boot/ABI/owned cleanup media evidence required')
    boot = checked_file({'path': runtime['boot'], 'sha256': runtime['boot_sha256']})
    binding(json.loads(boot.read_text()), sha(args.archive), args.boot_id, args.arch, runtime['device'], runtime['target'])
    inputs = json.loads(args.inputs.read_text()); contract.verify_inputs(inputs); contract.verify_hap(args.hap, inputs)
    if (inputs['run_id'], inputs['scenario'], inputs['arch']) != (run, scenario, args.arch):
        raise ValueError('actual media HAP/source/run differs')
    uid = require_normal_identity(args.application_identity.read_text())
    identity = bms_application_identity(args.application_identity.read_text(), BUNDLE)
    rows = parse_journal(args.results.read_text(), run, scenario, incomplete=scenario.endswith('-death'))
    if rows[0]['uid'] != uid:
        raise ValueError('ordinary caller journal UID differs from real BMS')
    actual_process = runtime['caller_process']
    raw = shell_body(runtime, actual_process['shell_observation'], identity_shell(BUNDLE, all_uids=False))
    if raw != actual_process['raw'] or [int(v) for v in raw.split()][::2] != [rows[0]['pid'], uid]:
        raise ValueError('actual kernel caller generation differs from journal')
    observations = runtime['tokens']
    if len(observations) < 3 or observations[0]['phase'] != 'before-launch' or observations[-1]['phase'] != 'after-capture':
        raise ValueError('actual independent token observations do not span capture')
    previous = -1
    for i, row in enumerate(observations):
        if verify_token_observation(row, runtime, run, uid, previous_command=previous) != identity:
            raise ValueError('actual ordinary BMS/token identity changed')
        state, _ = token(row['observation'], run, uid, allow_transition=0 < i < len(observations)-1)
        if (i == 0 and state != -1) or (i > 0 and state != 0):
            raise ValueError('real microphone grant was missing/revoked/pregranted')
        previous = runtime['guest_shell_observations'][row['bms_after_observation']]['command_index']
    labels = json.loads(checked_file({'path': runtime['labels'], 'sha256': runtime['labels_sha256']}).read_text())
    action = runtime['permission_action']
    layout = checked_file({'path': action['layout'], 'sha256': action['layout_sha256']})
    if select_mic(json.loads(layout.read_text()), labels, False) != action['selected_node'] or action['decision'] != 'ALLOW':
        raise ValueError('real MIC authorization UI differs')
    authorization = json.loads(event(rows, 'microphone.authorization')['detail'])
    if (any(type(v) is not int for v in authorization.get('auth_results', [])) or
            any(type(v) is not bool for v in authorization.get('dialog_shown_results', []))):
        raise ValueError('actual permission result types differ')
    if authorization != {'permissions': ['ohos.permission.MICROPHONE'], 'auth_results': [0], 'dialog_shown_results': [True]}:
        raise ValueError('actual ordinary MIC request disagrees with real token/UI')
    # Parent adds PERSONA to the original helper's finite protocol allowlist;
    # no weakening/relabeling of another persona is permitted.
    verify_tools(runtime, args.arch, parent_persona=PERSONA)
    producer_replay(runtime)
    plan = ui_plan(checked_file(runtime['screen_ui_plan']))
    actions = runtime['screen_actions']; expected = []
    count = 2 if scenario == 'screen-transcode' else 1
    for cycle in range(1, count+1):
        choice = 'deny' if scenario == 'screen-deny' else 'allow'
        expected.extend((choice, cycle, selector) for selector in plan[choice])
        if scenario == 'screen-revoke': expected.extend(('revoke', cycle, selector) for selector in plan['revoke'])
        elif scenario not in ('screen-deny', 'screen-death'):
            expected.append(('continue', cycle, {'bundle': BUNDLE, 'identifier': 'media578-continue'}))
    if len(actions) != len(expected): raise ValueError('complete actual screen UI choreography required')
    last = -1
    for row, (name, cycle, selector) in zip(actions, expected):
        if (row['action'], row['cycle']) != (name, cycle): raise ValueError('actual UI case order differs')
        index = action_replay(runtime, row, selector)
        if index <= last: raise ValueError('actual UI command reused or reordered')
        last = index
    rois = [canvas_replay(runtime, row, run) for row in runtime['canvas_observations']]
    if scenario != 'screen-deny' and (len(rois) != count or any(r != rois[0] for r in rois)):
        raise ValueError('actual Canvas/display geometry changed between recreation cycles')
    files = runtime['files']
    expected_names = {f'media578-{run}-results.log'}
    for cycle in range(1, count+1):
        expected_names.add(f'media578-{run}-{cycle}-capture.mp4')
        if scenario in ('screen-transcode', 'transcode-cancel', 'transcode-death'):
            expected_names.add(f'media578-{run}-{cycle}-transcoded.mp4')
    if set(files) != expected_names:
        raise ValueError('complete exact this-run media output set required')
    for name, descriptor in files.items():
        path = checked_file(descriptor)
        if (path.parent != args.runtime.parent/'private' or descriptor['remote'] != APP_FILES+name or
                path.name != name or descriptor['uid'] != uid or descriptor['mode'] & 0o007 or path.stat().st_size != descriptor['bytes']):
            raise ValueError('actual media private output custody differs')
        stat_script = 'test -f ' + APP_FILES+name + ' && test ! -L ' + APP_FILES+name + ' && stat -c "%u %a %s" ' + APP_FILES+name
        raw = shell_body(runtime, descriptor['stat_observation'], stat_script)
        a, b, c = raw.split()
        if (int(a), int(b, 8), int(c)) != (uid, descriptor['mode'], descriptor['bytes']):
            raise ValueError('actual original media private file stat differs')
        if name.endswith('.mp4'): stable_replay(runtime, name, descriptor)
    journal_name = f'media578-{run}-results.log'
    if sha(args.results) != files[journal_name]['sha256']:
        raise ValueError('actual media journal differs from owned private file')
    if scenario.endswith('-death'):
        result = death_replay(runtime, rows)
        if scenario == 'transcode-death':
            from batch_media_recorder_challenge import load_reference
            _, reference, _ = load_reference(args.runtime.parent/'challenge', run)
            capture = args.runtime.parent/'private'/f'media578-{run}-1-capture.mp4'
            _, pts, _, rgb, audio, _ = decode(args.ffmpeg, args.ffprobe, capture, (640, 480), args.decode_evidence/'death-source')
            result['input_pixels'] = content(rgb, pts, run, rois[0], privacy=True)
            result['input_audio'] = audio_content(audio, reference)
    else:
        result = verify_files(args.results, args.runtime.parent/'private', args.runtime.parent/'challenge', run, scenario,
                              rois[0] if rois else [0, 0, 1, .8], args.ffmpeg, args.ffprobe, args.decode_evidence)
    return {'status': 'pass', 'scope': SCOPE, 'scenario': scenario, 'run_id': run, 'arch': args.arch,
            'archive_sha256': sha(args.archive), 'boot_id': args.boot_id, 'process_generation': raw_process(runtime),
            'result': result, 'decoders': {name: {'path': str(Path(getattr(args, name)).resolve()),
                'sha256': sha(Path(getattr(args, name)).resolve())} for name in ('ffmpeg', 'ffprobe')},
            'closed_requirements': [], 'first_artifact_behavior_gate_passed': False,
            'same_artifact_negative_and_fresh_recovery_batch_required': True}


def raw_process(runtime):
    pid, start, uid = map(int, runtime['caller_process']['raw'].split())
    return {'pid': pid, 'starttime': start, 'uid': uid}


def evidence_arguments(document, archive, boot_id, arch, decode_evidence):
    """Bind original ordinary runner outputs; actual verify() still replays all raw inputs."""
    if (document.get('status') != 'pass' or document.get('persona') != PERSONA or document.get('failures') != [] or
            document.get('archive_sha256') != sha(archive) or document.get('boot_id') != boot_id or document.get('arch') != arch):
        raise ValueError('same new artifact original ordinary media runner evidence required')
    result_path = Path(document['result'])
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('original media verifier result missing')
    root = result_path.parent
    paths = {'result': result_path, 'raw_results': root/'results.log', 'ordinary_identity': root/'application-identity.json',
             'hap': root/'ordinary-probe-signed.hap', 'compiled_contract_inputs': root/'project/media-pipeline578-probe-inputs.json',
             'capture_runtime': root/'capture/runtime.json'}
    if any(sha(path) != document.get(name+'_sha256') for name, path in paths.items()):
        raise ValueError('original media runner output changed')
    saved = json.loads(result_path.read_text())
    args = SimpleNamespace(archive=Path(archive), boot_id=boot_id, arch=arch, run_id=document['run_id'],
        results=paths['raw_results'], inputs=paths['compiled_contract_inputs'], runtime=paths['capture_runtime'],
        hap=paths['hap'], application_identity=paths['ordinary_identity'], decode_evidence=Path(decode_evidence),
        ffmpeg=Path(saved['decoders']['ffmpeg']['path']), ffprobe=Path(saved['decoders']['ffprobe']['path']))
    return args, saved


def verify_evidence(document, archive, boot_id, arch, decode_evidence):
    args, saved = evidence_arguments(document, archive, boot_id, arch, decode_evidence)
    actual = verify(args)
    if actual != saved:
        raise ValueError('saved media result differs from fresh raw replay and independent decode')
    return actual


def verify_batch(arguments):
    """Always replay raw evidence/real decoders; a list of pass summaries is invalid."""
    if len(arguments) != len(BATCH) or any(isinstance(a, dict) for a in arguments):
        raise ValueError('original per-case verifier arguments required, not result summaries')
    cases = [verify(a) for a in arguments]
    return _verified_case_sequence(cases)


def _verified_case_sequence(cases):
    if len(cases) != len(BATCH) or tuple(c['scenario'] for c in cases) != BATCH:
        raise ValueError('positive / each negative / fresh positive recovery ordering required')
    if len({c['run_id'] for c in cases}) != len(cases): raise ValueError('media caller nonce reused')
    if len({(c['archive_sha256'], c['boot_id'], c['arch']) for c in cases}) != 1:
        raise ValueError('media boundaries/recovery must use this same new artifact/boot/ABI')
    for i in (5, 9):
        if cases[i]['process_generation'] == cases[i+1]['process_generation']:
            raise ValueError('death recovery did not start a new kernel process generation')
    return {'status': 'pass', 'scope': SCOPE+'_boundaries_and_fresh_recovery', 'cases': len(cases),
            'closed_requirements': [], 'first_artifact_behavior_gate_passed': False}


PACKAGE_BATCH_SCOPE = SCOPE + '_package_batch_raw_replay'


def media_suite_inputs(environment):
    """Resolve actual mandatory UI/decoder inputs, without resource fallback."""
    configured = environment.get('QEMU_TEST_MEDIA_SCREEN_UI')
    if not isinstance(configured, str) or not configured:
        raise ValueError('actual QEMU_TEST_MEDIA_SCREEN_UI is required; media check cannot be skipped')
    path = Path(configured)
    if (not path.is_absolute() or path.resolve() != path or
            any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError('canonical actual packaged screen UI input required')
    ui_plan(path)
    tools = {}
    for name in ('ffmpeg', 'ffprobe'):
        actual = shutil.which(name, path=environment.get('PATH', ''))
        if actual is None or not Path(actual).is_file():
            raise ValueError('actual admitted independent decoder is missing: ' + name)
        # Preserve the literal tool path. The original377 policy verifies its
        # complete actual descriptor/symlink chain; do not replace argv0 with a
        # different alias or infer admission from a common resolved executable.
        tools[name] = str(Path(actual).absolute())
    return {'screen_ui_plan': {'path': str(path), 'sha256': sha(path)}, **tools}


def _package_case_documents(batch, archive, boot_id, arch):
    """Only parse actual evidence descriptors here; each case still needs replay."""
    keys = {'schema_version', 'status', 'scope', 'archive_sha256', 'boot_id', 'arch',
            'screen_ui_plan', 'cases', 'closed_requirements', 'first_artifact_behavior_gate_passed'}
    if (type(batch) is not dict or set(batch) != keys or batch['schema_version'] != 1 or
            type(batch['schema_version']) is not int or batch['status'] != 'pass' or batch['scope'] != PACKAGE_BATCH_SCOPE or
            batch['archive_sha256'] != sha(archive) or batch['boot_id'] != boot_id or batch['arch'] != arch or
            batch['closed_requirements'] != [] or batch['first_artifact_behavior_gate_passed'] is not False or
            type(batch['cases']) is not list or len(batch['cases']) != len(BATCH)):
        raise ValueError('complete same-artifact media package batch required; broad closure is not inferred')
    plan = batch['screen_ui_plan']
    if type(plan) is not dict or set(plan) != {'path', 'sha256'}:
        raise ValueError('actual packaged screen UI descriptor required')
    plan_path = checked_file(plan)
    if (not plan_path.is_absolute() or plan_path.resolve() != plan_path or
            any(p.is_symlink() for p in (plan_path, *plan_path.parents))):
        raise ValueError('canonical actual packaged screen UI input required')
    ui_plan(plan_path)
    documents, seen = [], set()
    for descriptor, scenario in zip(batch['cases'], BATCH):
        if (type(descriptor) is not dict or set(descriptor) != {'scenario', 'evidence', 'sha256'} or
                descriptor['scenario'] != scenario):
            raise ValueError('all eleven actual media boundaries and fresh recoveries are required in order')
        path = Path(descriptor['evidence'])
        if (not path.is_absolute() or path.resolve() != path or path.name != 'evidence.json' or
                any(p.is_symlink() for p in (path, *path.parents)) or path in seen or
                not path.is_file() or path.stat().st_size > 8*1024*1024 or sha(path) != descriptor['sha256']):
            raise ValueError('unique unchanged actual ordinary-HAP case evidence required')
        seen.add(path)
        document = strict_json(path.read_text())
        runtime_path = path.parent/'capture/runtime.json'
        if sha(runtime_path) != document.get('capture_runtime_sha256'):
            raise ValueError('actual original media runtime descriptor changed')
        runtime = strict_json(runtime_path.read_text())
        if runtime.get('screen_ui_plan') != plan or runtime.get('scenario') != scenario:
            raise ValueError('case did not use this actual screen UI input/scenario')
        documents.append(document)
    return documents


def verify_package_batch(batch, archive, boot_id, arch, *, replay_parent=None):
    """Gate entry: load every actual case and re-run original raw + real decoders.

    TemporaryDirectory uses the enclosing Owner's private TMPDIR and existing
    constructor broker. A caller may pass a dedicated private parent for an
    isolated replay. No prior pass summary or serialized case list is accepted
    as the result of verify_evidence().
    """
    documents = _package_case_documents(batch, archive, boot_id, arch)
    with tempfile.TemporaryDirectory(prefix='qemu-media578-package-replay-', dir=replay_parent) as directory:
        cases = [verify_evidence(document, archive, boot_id, arch, Path(directory)/('case-'+str(i)))
                 for i, document in enumerate(documents)]
    result = _verified_case_sequence(cases)
    if tuple(case['scenario'] for case in cases) != BATCH:
        raise ValueError('actual media case results differ from their descriptors')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'runtime', 'inputs', 'hap', 'application-identity', 'results', 'ffmpeg', 'ffprobe', 'decode-evidence', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--run-id', required=True); p.add_argument('--boot-id', required=True)
    p.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    a = p.parse_args()
    value = verify(a)
    with a.output.open('x') as output: output.write(json.dumps(value, indent=2)+'\n')
    print(json.dumps(value))


if __name__ == '__main__': main()
