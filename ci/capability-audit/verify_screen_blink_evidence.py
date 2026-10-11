"""Replay complete role-bound screen-blink behavior, never mere exports."""
import copy
import json
import math
from pathlib import Path
import re
import zipfile

from build_screen_blink_probe import BUNDLE, ROLES, module
from guest_ui import select_node
from run_root_probe import digest
from sign_screen_blink_probe import configure_profile
from verify_screen_blink_results import (identity, rows, verify_inputs, verify_initial,
    verify_frames, verify_committed_stop, verify_background_restored)

CONTRACTS = ['arkts_export:@ohos.accessibility.config:' + name
             for name in ('startBlinking', 'stopBlinking')]
SCOPE = 'three_roles_actual_screen_pixels_NOT_complete_lifecycle_or_full_gate'
SYSTEM_SCOPE = 'actual_calls_pixels_and_caller_exit_NOT_competing_token_or_account_switch_proof'


def checked(path, sha):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or digest(path) != sha:
        raise ValueError('actual screen blink evidence changed/missing: ' + str(path))
    return path


def plan():
    value = [('ready', 'ready', None)]
    def capture(name, mode):
        value.append((name, 'frames', mode))
    def control(name, identifier, values, text=''):
        value.extend(((name + '-control', 'control', identifier),
                      (name, 'results', (values, text))))
    value.append(('baseline-readiness', 'readiness', None))
    capture('disabled-baseline', 'off')
    control('master.enabled', 'blink-enable', [1], '1')
    control('continuous.start', 'blink-start', [0, 0, 1])
    capture('continuous', 'continuous')
    control('continuous.start', 'blink-start', [1, 0, 1])
    control('wrong.stop', 'blink-wrong-stop', [2, 0, 1])
    capture('wrong-stop-retains-owner', 'continuous')
    control('continuous.stop', 'blink-stop', [0, 0, 1])
    capture('stopped', 'bounded-committed-off')
    control('continuous.stop', 'blink-stop', [0, 0, 1])
    control('single.armed', 'blink-single', [1])
    capture('single-auto-clear', 'armed-single')
    value.append(('single.start', 'results', ([0, 0, 1], '')))
    control('continuous.start', 'blink-start', [0, 0, 1])
    control('master.disabled', 'blink-disable', [1], '0')
    capture('disabled-clears', 'off')
    control('continuous.start', 'blink-start', [5, 0, 1])
    control('master.enabled', 'blink-enable', [1], '1')
    control('continuous.start', 'blink-start', [0, 0, 1])
    capture('before-caller-exit', 'continuous')
    value.append(('ready', 'ready', None))
    value.append(('restart-baseline-readiness', 'readiness', None))
    capture('restarted-initial-stop', 'off')
    control('cleanup.master', 'blink-restore', [1], '0')
    capture('cleanup-off', 'off')
    return value


def verify_runtime(document, nonce, role, identity_text, commands):
    if (document.get('status') != 'pass' or document.get('role') != role or
            document.get('run_id') != nonce or document.get('failures') != [] or
            document.get('cleanup_verified') is not True or
            document.get('first_artifact_behavior_gate_passed') is not False or
            document.get('scope') != (SYSTEM_SCOPE if role == 'system' else
                'actual_calls_and_pixels_NOT_caller_death_or_competing_token_proof')):
        raise ValueError('complete screen blink runtime/cleanup required')
    expected = plan() if role == 'system' else [('ready', 'ready', None)]
    phases = document.get('phases')
    if (not isinstance(phases, list) or len(phases) != len(expected) or
            any(not isinstance(row, dict) for row in phases)):
        raise ValueError('complete ordered screen blink phases required')
    rect = marker = None
    if role == 'system':
        surface = document.get('surface', {})
        layout = json.loads(checked(surface.get('layout', ''), surface.get('sha256')).read_text())
        rect = select_node(layout, BUNDLE, identifier='blink-pixel-surface')['rect']
        marker = select_node(layout, BUNDLE, identifier='blink-frame-marker')['rect']
        if rect != surface.get('rect') or marker != document.get('optical_marker'):
            raise ValueError('blink surface/marker differs from actual visible native nodes')
    previous = []
    pids = []
    input_cursor = 0
    for row, (name, kind, argument) in zip(phases, expected):
        if row.get('name') != name or row.get('failure'):
            raise ValueError('missing/reordered/failed actual screen blink phase: ' + name)
        if kind in ('ready', 'results'):
            raw = checked(row.get('results', ''), row.get('sha256')).read_text()
            if not raw.endswith('\n'):
                raise ValueError('complete appended screen blink native observations required')
            actual = rows(raw, nonce, role)
            if kind == 'ready':
                previous = verify_initial(raw, nonce, role, identity_text, restarted=bool(pids))
                pids.append(previous[0]['values'][2])
            else:
                extra = 2 if name == 'cleanup.master' else 1
                if (actual[:len(previous)] != previous or len(actual) != len(previous) + extra or
                        actual[-1]['name'] != name or actual[-1]['values'] != argument[0] or
                        actual[-1]['text'] != argument[1] or (extra == 2 and
                        (actual[-2]['name'] != 'cleanup.stop' or actual[-2]['values'] != [0, 0, 1] or
                         actual[-2]['text'] != ''))):
                    raise ValueError('blink native control/order/result differs: ' + name)
                previous = actual
        elif kind == 'control':
            selection = row.get('selection', {})
            layout_path = checked(selection.get('layout', ''), selection.get('layout_sha256'))
            selected = select_node(json.loads(layout_path.read_text()), BUNDLE,
                                   identifier=argument, clickable=True)
            if selected != selection.get('selected_node'):
                raise ValueError('actual screen blink action selected another/hidden node')
            x, y, width, height = selected['rect']
            prefix = 'uitest uiInput click ' + str(x + width // 2) + ' ' + str(y + height // 2) + '; '
            candidates = [index for index in range(input_cursor, len(commands))
                if len(commands[index]['argv']) == 5 and commands[index]['argv'][3] == 'shell' and
                commands[index]['argv'][4].startswith(prefix) and commands[index]['exit_code'] == 0 and re.search(
                    r'__UITEST_EXIT_[0-9a-f]{32}__=0\s*$', commands[index]['output'])]
            if not candidates:
                raise ValueError('actual screen blink native input command/reply is missing')
            input_cursor = candidates[0] + 1
        elif kind == 'readiness':
            frames = row.get('frames', [])
            if not isinstance(frames, list) or len(frames) < 3:
                raise ValueError('blink baseline readiness lacks actual captures')
            # Early startup images are preconditions, not blink failures.
            # Preserve/check all bytes and timing; require the final three off.
            previous_after = -1
            seen = set()
            for frame in frames:
                path = checked(frame.get('path', ''), frame.get('sha256'))
                before, after = frame.get('before'), frame.get('after')
                if (str(path) in seen or type(before) not in (int, float) or type(after) not in (int, float) or
                        not math.isfinite(before) or not math.isfinite(after) or
                        before < previous_after or after < before or after - before > 3):
                    raise ValueError('invalid readiness capture timing/identity')
                seen.add(str(path)); previous_after = after
            verify_frames(frames[-3:], rect, 'off')
        else:
            if row.get('rect') != rect or row.get('mode') != argument:
                raise ValueError('actual screen blink frame surface/mode differs')
            if argument == 'bounded-committed-off':
                if row.get('marker') != marker or row.get('expected_sequence') != len(previous) % 256:
                    raise ValueError('native stop optical marker/serial differs')
                result = verify_committed_stop(row.get('frames'), rect, marker,
                                               row['expected_sequence'], row.get('started'))
                if result != row.get('commit') or result['observed'] != row.get('observed'):
                    raise ValueError('bounded compositor stop summary differs from real frames')
            elif verify_frames(row.get('frames'), rect, argument) != row.get('observed'):
                raise ValueError('actual screen blink pixel sequence summary differs')
    if role == 'system':
        exit_ = document.get('caller_exit', {})
        if (len(pids) != 2 or pids[0] == pids[1] or exit_.get('pid') != pids[0] or
                exit_.get('restarted_pid') != pids[1]):
            raise ValueError('actual screen blink caller death/new PID required')
        verify_background_restored(exit_.get('baseline', {}), exit_.get('frames', []))
    return pids


def verify_evidence(document, archive_sha, boot_id, arch, device, target):
    if (document.get('status') != 'pass' or document.get('scope') != SCOPE or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('device') != device or document.get('target') != target or
            document.get('failures') != [] or document.get('cleanup_verified') is not True or
            document.get('first_artifact_behavior_gate_passed') is not False or
            set(document.get('roles', {})) != set(ROLES) or
            re.fullmatch('[0-9a-fA-F]{64}', document.get('udid', '')) is None):
        raise ValueError('exact packaged screen blink roles/identity/cleanup required')
    cleanup = document.get('caller_cleanup', {})
    if (cleanup.get('bundle') != BUNDLE or cleanup.get('kernel_process_absent') is not True or
            cleanup.get('ability_process_records_absent') is not True or
            type(cleanup.get('consecutive_absent_observations')) is not int or
            cleanup['consecutive_absent_observations'] < 2):
        raise ValueError('actual owned blink caller cleanup is unproven')
    commands = []
    for command in document.get('commands', []):
        argv = command.get('argv')
        if not isinstance(argv, list) or not argv or any(type(value) is not str for value in argv):
            raise ValueError('actual screen blink command identity required')
        output = checked(command.get('log', ''), command.get('sha256')).read_text()
        if type(command.get('exit_code')) is not int or command.get('timed_out'):
            raise ValueError('screen blink command lacks terminal exit status')
        if Path(argv[0]).name == 'hdc' and (len(argv) < 4 or argv[1:3] != ['-t', target]):
            raise ValueError('screen blink command escaped its packaged guest')
        commands.append(dict(argv=argv, output=output, exit_code=command['exit_code'], log=command['log']))
    if not commands:
        raise ValueError('screen blink actual commands required')
    builds = [index for index, command in enumerate(commands)
              if any(Path(arg).name == 'build_screen_blink_probe.py' for arg in command['argv'])]
    if len(builds) != 3:
        raise ValueError('each screen blink role requires its actual typed build command')
    nonces = set()
    for role_index, role in enumerate(ROLES):
        record = document['roles'][role]
        nonce = record.get('run_id'); nonces.add(nonce)
        paths = {field: checked(record.get(field, ''), record.get(field + '_sha256')) for field in
                 ('inputs', 'application_identity', 'signed_hap', 'unsigned_hap', 'signing_receipt', 'runtime')}
        if (record.get('status') != 'pass' or record.get('cleanup_verified') is not True or
                type(record.get('uid')) is not int or identity(paths['application_identity'].read_text(), role) != record['uid']):
            raise ValueError('actual installed screen blink role differs')
        verify_inputs(json.loads(paths['inputs'].read_text()), nonce, arch, role)
        build = commands[builds[role_index]]
        for flag, value in (('--role', role), ('--arch', arch), ('--run-id', nonce),
                            ('--output', str(paths['inputs'].parent))):
            argv = build['argv']
            if argv.count(flag) != 1 or argv.index(flag) + 1 == len(argv) or argv[argv.index(flag) + 1] != value:
                raise ValueError('screen blink typed build command belongs to another caller/role')
        if build['exit_code'] != 0:
            raise ValueError('actual screen blink typed HAP build failed')
        role_commands = commands[builds[role_index]:builds[role_index + 1] if role_index + 1 < 3 else len(commands)]
        receipt = json.loads(paths['signing_receipt'].read_text())
        profile = receipt.get('verified_profile', {})
        with zipfile.ZipFile(paths['signed_hap']) as hap:
            compiled = json.loads(hap.read('module.json'))
        if (receipt.get('status') != 'pass' or receipt.get('role') != role or
                receipt.get('scope') != 'actual_signature_profile_and_codesign_NOT_guest' or
                receipt.get('signed_sha256') != digest(paths['signed_hap']) or
                receipt.get('unsigned_sha256') != digest(paths['unsigned_hap']) or
                compiled['module']['requestPermissions'] != module(role)['module']['requestPermissions'] or
                configure_profile(copy.deepcopy(profile), role, document['udid'], compiled) != profile):
            raise ValueError('actual signed screen blink permission profile differs')
        verify_runtime(json.loads(paths['runtime'].read_text()), nonce, role,
                       paths['application_identity'].read_text(), role_commands)
    if len(nonces) != 3:
        raise ValueError('screen blink roles must have separate fresh nonces')
    return CONTRACTS
