"""Actual UI regression phases for an installed, identity-verified blink caller.

The owning packaged-guest runner supplies logged shell/UI operations. This
module never signs callers, grants permissions, modifies an image or closes an
audit gap by itself. Caller death requires the optional pre-launch background;
competing tokens and account/service lifecycle still require additional evidence.
"""
import json
from pathlib import Path
import shlex
import time

from build_screen_blink_probe import BUNDLE
from guest_ui import select_node
from run_root_probe import digest
from verify_screen_blink_results import classify_pixels, rows, verify_background_restored, verify_frames, verify_initial


def exercise(ui, shell, remote, output, nonce, role, identity_text, wait_seconds=90, *, background=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status='fail', role=role, run_id=nonce, phases=[], failures=[],
                  scope='actual_calls_and_pixels_NOT_caller_death_or_competing_token_proof',
                  first_artifact_behavior_gate_passed=False)
    ready = False
    cleaned = role != 'system'
    observed = []
    process_stopped = False

    def observe(name, expected=None, text=''):
        nonlocal observed
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            raw = shell('cat ' + shlex.quote(remote), 'blink-results')
            actual = rows(raw, nonce, role)
            if actual[:len(observed)] != observed:
                raise ValueError('blink observations were replaced or truncated')
            if len(actual) > len(observed) and actual[-1]['name'] == name:
                if observed and len(actual) - len(observed) != (2 if name == 'cleanup.master' else 1):
                    raise ValueError('unexpected extra blink control observations')
                path = output / (str(len(report['phases'])).zfill(3) + '-results.log')
                path.write_text(raw)
                report['phases'].append(dict(name=name, results=str(path), sha256=digest(path)))
                if expected is not None and (actual[-1]['values'] != expected or actual[-1]['text'] != text):
                    raise ValueError('blink observed wrong result: ' + name)
                observed = actual
                return raw
            time.sleep(.1)
        raise ValueError('blink observation timed out: ' + name)

    def click(identifier, name, values, text=''):
        selected = ui.click(BUNDLE, identifier=identifier, label=name)
        report['phases'].append(dict(name=name + '-control', selection=selected))
        return observe(name, values, text)

    def capture(name, rect, mode, seconds=5):
        frames = []
        deadline = time.monotonic() + seconds
        while len(frames) < 3 or time.monotonic() < deadline:
            before = time.monotonic()
            path = ui.screenshot(label=name)
            after = time.monotonic()
            frames.append(dict(path=str(path), sha256=digest(path), before=before, after=after))
            if after > deadline + 10:
                raise ValueError('screen capture too slow to establish blink sequence')
            time.sleep(.08)
        record = dict(name=name, rect=rect, mode=mode, frames=frames)
        report['phases'].append(record)
        record['observed'] = verify_frames(frames, rect, mode)

    try:
        initial = observe('ready', [1])
        verify_initial(initial, nonce, role, identity_text)
        ready = True
        if role == 'system':
            layout, path = ui.layout(bundle=BUNDLE, label='blink-baseline')
            rect = select_node(layout, BUNDLE, identifier='blink-pixel-surface')['rect']
            report['surface'] = dict(layout=str(path), sha256=digest(path), rect=rect)
            # ArkUI publishes its tree before the starting window disappears.
            # Establish the real baseline before testing any blink operation;
            # retain every precondition frame, including the starting window.
            readiness = dict(name='baseline-readiness', frames=[])
            report['phases'].append(readiness)
            deadline = time.monotonic() + wait_seconds
            consecutive = []
            while time.monotonic() < deadline:
                before = time.monotonic()
                path = ui.screenshot(label='baseline-readiness')
                frame = dict(path=str(path), sha256=digest(path), before=before, after=time.monotonic())
                readiness['frames'].append(frame)
                try:
                    kind = classify_pixels(path, rect)
                except ValueError as error:
                    kind = 'not-baseline'
                    frame['precondition_error'] = str(error)
                frame['kind'] = kind
                consecutive = (consecutive + [frame]) if kind == 'off' else []
                if len(consecutive) == 3:
                    verify_frames(consecutive, rect, 'off')
                    break
                time.sleep(.1)
            else:
                raise ValueError('actual baseline never became stable before blink actions')
            capture('disabled-baseline', rect, 'off', 1)
            click('blink-enable', 'master.enabled', [1], '1')
            # Public settings notification is asynchronous; do not reinterpret
            # a disabled return as a successful start.
            time.sleep(1)
            click('blink-start', 'continuous.start', [0, 0, 1])
            capture('continuous', rect, 'continuous')
            click('blink-start', 'continuous.start', [1, 0, 1])
            click('blink-wrong-stop', 'wrong.stop', [2, 0, 1])
            capture('wrong-stop-retains-owner', rect, 'continuous')
            click('blink-stop', 'continuous.stop', [0, 0, 1])
            capture('stopped', rect, 'off', 1)
            click('blink-stop', 'continuous.stop', [0, 0, 1])
            # Capture immediately after the public single start. A missed pulse
            # is a failed test, not grounds to accept only a return code.
            click('blink-single', 'single.start', [0, 0, 1])
            capture('single-auto-clear', rect, 'single', 3)
            click('blink-start', 'continuous.start', [0, 0, 1])
            click('blink-disable', 'master.disabled', [1], '0')
            time.sleep(1)
            capture('disabled-clears', rect, 'off', 1)
            click('blink-start', 'continuous.start', [5, 0, 1])
            if background is not None:
                original_pid = rows(initial, nonce, role)[0]['values'][2]
                click('blink-enable', 'master.enabled', [1], '1')
                time.sleep(1)
                click('blink-start', 'continuous.start', [0, 0, 1])
                capture('before-caller-exit', rect, 'continuous')
                process_stopped = True  # Cleanup also retries a lost stop reply.
                shell('aa force-stop ' + BUNDLE, 'blink-stop-own-process-with-active-window')
                deadline = time.monotonic() + wait_seconds
                while time.monotonic() < deadline:
                    if shell('if test -d /proc/' + str(original_pid) +
                             '; then echo PRESENT; else echo ABSENT; fi', 'blink-owner-exit').strip() == 'ABSENT':
                        break
                    time.sleep(.1)
                else:
                    raise ValueError('owned blink caller did not actually exit')
                time.sleep(2)
                frames = []
                for index in range(3):
                    before = time.monotonic()
                    path = ui.screenshot(label='caller-exit-' + str(index))
                    frames.append(dict(path=str(path), sha256=digest(path), before=before, after=time.monotonic()))
                    time.sleep(.8)
                report['caller_exit'] = dict(pid=original_pid, baseline=background, frames=frames)
                verify_background_restored(background, frames)
                if 'start ability successfully' not in shell('aa start -a EntryAbility -b ' + BUNDLE,
                                                            'blink-restart-owned-caller').lower():
                    raise ValueError('owned blink caller did not restart')
                # Only this explicit process-generation boundary permits the
                # nonce-scoped HAP to replace its previous observation file.
                observed = []
                time.sleep(1)
                restarted = observe('ready', [1])
                restart_rows = verify_initial(restarted, nonce, role, identity_text, restarted=True)
                process_stopped = False
                new_pid = restart_rows[0]['values'][2]
                if new_pid == original_pid:
                    raise ValueError('caller restart did not produce a new process identity')
                report['caller_exit']['restarted_pid'] = new_pid
                report['scope'] = 'actual_calls_pixels_and_caller_exit_NOT_competing_token_or_account_switch_proof'
                capture('restarted-initial-stop', rect, 'off', 1)
        report['status'] = 'pass'
    except (ValueError, OSError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    finally:
        if role == 'system' and ready:
            try:
                if process_stopped:
                    if 'start ability successfully' not in shell('aa start -a EntryAbility -b ' + BUNDLE,
                                                                'blink-cleanup-restart').lower():
                        raise ValueError('cannot restart owned caller for policy restoration')
                    time.sleep(1)
                    observed = []
                    verify_initial(observe('ready', [1]), nonce, role, identity_text, restarted=True)
                raw = click('blink-restore', 'cleanup.master', [1], '0')
                actual = rows(raw, nonce, role)
                if (len(actual) < 2 or actual[-2]['name'] != 'cleanup.stop' or
                        actual[-2]['values'] != [0, 0, 1]):
                    raise ValueError('owned screen controller did not stop during cleanup')
                capture('cleanup-off', report['surface']['rect'], 'off', 1)
                cleaned = True
            except (ValueError, OSError, KeyError, TypeError) as error:
                report['failures'].append('cleanup: ' + str(error))
        report['cleanup_verified'] = cleaned
        if not cleaned or report['failures']:
            report['status'] = 'fail'
        (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
