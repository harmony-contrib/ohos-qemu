#!/usr/bin/env python3
"""Reach the fresh guest's real home screen using at most one ordinary swipe.

This is test setup after default suspend/wake acceptance, not a security or
power-policy repair. Never clear another client's override or bypass a PIN.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from boot_package import FATAL
from guest_ui import GuestUi, bounds, select_node
from run_root_probe import digest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from power_test_policy import power_timeout

BUNDLE = 'com.ohos.sceneboard'
LOCK = 'ScreenLockRootComponent'
LOCK_HOME = 'MainPageView_Screen_Lock_Home'
DESKTOP = 'SCBDesktop_Flex_Desktop'
SCOPE = 'fresh_packaged_actual_system_home_setup_NOT_capability_acceptance'


def system_screen(layout):
    roots = layout if isinstance(layout, list) else [layout]
    pending = []
    for root in roots:
        if not isinstance(root, dict) or not isinstance(root.get('attributes'), dict):
            raise ValueError('actual system screen requires a well-formed viewport')
        pending.append((root, '', bounds(root['attributes'].get('bounds')), 0))
    found, count = {}, 0
    while pending:
        node, inherited_bundle, viewport, depth = pending.pop()
        count += 1
        if count > 100000 or depth > 256 or not isinstance(node, dict):
            raise ValueError('malformed or excessive system UI hierarchy')
        attributes, children = node.get('attributes'), node.get('children', [])
        if not isinstance(attributes, dict) or not isinstance(children, list):
            raise ValueError('malformed system UI node')
        bundle = attributes.get('bundleName') or inherited_bundle
        identifier = attributes.get('id')
        if bundle == BUNDLE and identifier in (LOCK, LOCK_HOME, DESKTOP):
            if identifier in found or attributes.get('visible') != 'true' or attributes.get('enabled') != 'true':
                raise ValueError('system home/lock target is duplicate, hidden or disabled')
            selected = select_node(layout, bundle, identifier=identifier)
            x, y, w, h = selected['rect']
            vx, vy, vw, vh = viewport
            if min(w, h) < 32 or x < vx or y < vy or x + w > vx + vw or y + h > vy + vh:
                raise ValueError('system home/lock node is outside its actual viewport')
            found[identifier] = selected
        pending.extend((child, bundle, viewport, depth + 1) for child in children)
    if set(found) == {LOCK, LOCK_HOME}:
        lock, home = found[LOCK]['rect'], found[LOCK_HOME]['rect']
        if lock != home:
            raise ValueError('unrecognized lock home geometry; no credential fallback')
        return 'locked', found[LOCK]
    if set(found) == {DESKTOP}:
        return 'home', found[DESKTOP]
    raise ValueError('unknown/credential/app screen; require the real default lock home or desktop')


def service_pids(text):
    rows = text.strip().splitlines()
    if len(rows) != 2 or any(re.fullmatch('[1-9][0-9]*', row) is None for row in rows):
        raise ValueError('require actual unique RenderService and Foundation processes')
    return rows


def prepare(ui, report, *, clock=time.monotonic, sleep=time.sleep):
    def identity(label):
        if ui.shell('cat /proc/sys/kernel/random/boot_id', label).strip() != report['boot_id']:
            raise ValueError('kernel changed during actual system home setup')
    identity('home-boot-before')
    report['service_pids_before'] = service_pids(ui.shell('pidof render_service; pidof foundation', 'home-services-before'))
    report['policy_before'] = power_timeout(ui.shell('hidumper -s 3301 -a "-a"', 'home-policy-before'))
    layout, path = ui.layout(label='home-before')
    state, selected = system_screen(layout)
    report.update(before_screen=state, before_layout=str(path), before_layout_sha256=digest(path), swipe_count=0)
    if report['policy_before']['override_ms'] not in ((None, 10000) if state == 'locked' else (None,)):
        raise ValueError('unknown existing power override; no gesture or restore may replace it')
    if state == 'locked':
        left, top, width, height = selected['rect']
        start = [left + width // 2, top + height * 85 // 100]
        end = [start[0], top + height * 20 // 100]
        report.update(swipe_count=1, swipe={'selected_node': selected, 'start': start, 'end': end})
        ui.shell('uitest uiInput swipe ' + ' '.join(map(str, (*start, *end))), 'ordinary-lock-home-swipe')
        deadline = clock() + 20
        while True:
            if clock() >= deadline:
                raise ValueError('ordinary gesture did not reach home; no privileged unlock fallback')
            sleep(1)
            layout, path = ui.layout(label='home-after-swipe')
            state, selected = system_screen(layout)
            if state == 'home':
                if clock() > deadline:
                    raise ValueError('home appeared only after the finite deadline')
                break
    report.update(after_screen=state, after_layout=str(path), after_layout_sha256=digest(path),
                  home_node=selected)
    report['policy_after'] = power_timeout(ui.shell('hidumper -s 3301 -a "-a"', 'home-policy-after'))
    if (report['policy_after']['base_ms'] != report['policy_before']['base_ms'] or
            report['policy_after']['override_ms'] is not None):
        raise ValueError('system did not restore its own original policy; refuse to clear/replace another override')
    report['screenshot'] = str(ui.screenshot(label='actual-system-home'))
    report['screenshot_sha256'] = digest(Path(report['screenshot']))
    identity('home-boot-after')
    report['service_pids_after'] = service_pids(ui.shell('pidof render_service; pidof foundation', 'home-services-after'))
    if report['service_pids_after'] != report['service_pids_before']:
        raise ValueError('critical services restarted during ordinary home gesture')
    report['status'] = 'pass'


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    boot = json.loads(args.boot.read_text())
    environment = boot['test_environment']
    report = {'schema_version': 1, 'scope': SCOPE, 'status': 'fail',
              'archive_sha256': boot['archive_sha256'], 'boot_id': environment['boot_id'],
              'commands': [], 'failures': [], 'privileged_unlock': False, 'power_override_cleared': False,
              'first_artifact_behavior_gate_passed': False}
    def command(argv, label):
        argv = list(map(str, argv))
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        log = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        log.write_text(result.stdout + result.stderr)
        report['commands'].append({'argv': argv, 'exit_code': result.returncode, 'log': str(log), 'sha256': digest(log)})
        if result.returncode or '[Fail]' in result.stdout or 'Device not found or connected' in result.stdout:
            raise ValueError('actual owned home setup command failed: ' + label)
        return result.stdout.replace('\r', '')
    try:
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or boot.get('candidate_kernel') or
                environment.get('external_keepalive') is not False or
                digest(Path(boot['archive'])) != boot['archive_sha256']):
            raise ValueError('successful actual new-package acceptance boot required')
        if command(['ps', '-p', environment['qemu_pid'], '-o', 'command='], 'owned-QEMU').strip() != environment['qemu_command']:
            raise ValueError('owned QEMU process identity changed')
        if FATAL.search((args.boot.parent / 'qemu.log').read_text(errors='replace')):
            raise ValueError('kernel or critical service failed before home setup')
        ui = GuestUi(command, args.hdc, environment['target'], args.output / 'ui')
        prepare(ui, report)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hdc', required=True)
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'scope': result['scope'], 'failures': result['failures']}))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
