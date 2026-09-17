#!/usr/bin/env python3
"""Run the C API regression against an already booted, enabled private guest."""
import argparse
import json
from pathlib import Path
import subprocess
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--target', required=True)
p.add_argument('--hap', type=Path, required=True)
p.add_argument('--evidence', type=Path, required=True)
p.add_argument('--timeout', type=int, default=900)
p.add_argument('--device-type', choices=('2in1', 'phone'), default='2in1')
p.add_argument('--expected-cases', type=int, default=21)
p.add_argument('--isolated-cases', action='store_true',
               help='run each case in a new ARMv7a app process')
a = p.parse_args()
if a.isolated_cases and a.expected_cases != 21:
    p.error('--isolated-cases requires the complete 21-case HAP')
a.evidence.mkdir(parents=True, exist_ok=True)
bundle = 'org.harmonycontrib.childprocessregression'
hdc = ['hdc', '-t', a.target]
def run(*args, check=True):
    result = subprocess.run(hdc + list(args), capture_output=True, text=True, timeout=60)
    if check and result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout + result.stderr
info = run('shell', 'param get const.ohos.fullname; param get const.product.devicetype; param get const.max_native_child_process; param get persist.sys.abilityms.multi_process_model')
(a.evidence / 'environment.txt').write_text(info)
if a.device_type not in (line.strip() for line in info.splitlines()):
    raise SystemExit(f'Native child regression requires a private {a.device_type} guest')
installed = run('install', '-r', str(a.hap.resolve()))
(a.evidence / 'install.txt').write_text(installed)
if 'successfully' not in installed.lower():
    raise SystemExit(installed)
# Delete only the previous test result in this dedicated test bundle.
path = f'/data/app/el2/100/base/{bundle}/files/native-child-process-results.log'
run('shell', f'rm -f {path}', check=False)
# A slow TCG guest can report the foreground account ready before the lock
# screen finishes its post-reboot transition. Retry only that specific error;
# waking and swiping the private 800x500 test display is safe here.
attempts = []
def start(index=None):
    run('shell', f'aa force-stop {bundle}', check=False)
    if a.isolated_cases:
        # The first Native launch can cold-start nativespawn. On ARMv7a/2in1
        # under TCG, force-stop returns before that process and its sandbox
        # cleanup settle; a launch two seconds later has exited mid-case.
        # Twenty seconds let the preceding app and child leave before restart.
        time.sleep(20)
    command = f'aa start -a EntryAbility -b {bundle}'
    if index is not None:
        command += f' --pi regressionCase {index}'
    for attempt in range(60):
        started = run('shell', command, check=False)
        attempts.append(f'case={index} attempt={attempt}: {started}')
        if 'start ability successfully' in started.lower():
            return
        if '10106101' in started or 'another ability is being started' in started.lower():
            time.sleep(2)
            continue
        if '10106102' not in started and 'screen is locked' not in started.lower():
            break
        run('shell', 'power-shell wakeup', check=False)
        run('shell', 'uitest uiInput swipe 400 450 400 100 600', check=False)
        time.sleep(2)
    raise RuntimeError(f'case {index} did not start: {started}')

deadline = time.monotonic() + a.timeout
text = ''
if a.isolated_cases:
    completed = 0
    for index in range(21):
        start(index)
        marker = f'CASE_DONE index={index} pass=1'
        while time.monotonic() < deadline:
            text = run('shell', f'cat {path}', check=False)
            if marker in text:
                completed += 1
                print(marker, flush=True)
                break
            if f'CASE_DONE index={index} pass=0' in text:
                raise RuntimeError(f'case {index} failed:\n{text}')
            time.sleep(1)
        else:
            raise RuntimeError(f'case {index} timed out after {completed} passes:\n{text}')
    if any(f'CASE_DONE index={index} pass=1' not in text for index in range(21)):
        raise RuntimeError('results log lost one or more isolated case markers')
    text += '\nSUMMARY total=21 failures=0 (isolated app launches)\n'
else:
    start()
    while time.monotonic() < deadline:
        text = run('shell', f'cat {path}', check=False)
        if 'SUMMARY ' in text:
            break
        time.sleep(2)
(a.evidence / 'start.txt').write_text('\n--- attempt ---\n'.join(attempts))
(a.evidence / 'results.log').write_text(text)
(a.evidence / 'hilog.txt').write_text(run('shell', 'hilog -x', check=False))
passed = f'SUMMARY total={a.expected_cases} failures=0' in text and not any(line.startswith('FAIL') for line in text.splitlines())
(a.evidence / 'result.json').write_text(json.dumps({'passed': passed, 'target': a.target, 'hap': str(a.hap.resolve()), 'expected_cases': a.expected_cases}, indent=2) + '\n')
print(text)
if not passed:
    raise SystemExit('Native child process regression failed or timed out')
