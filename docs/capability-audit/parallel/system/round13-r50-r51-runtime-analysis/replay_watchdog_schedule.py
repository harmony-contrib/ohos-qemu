#!/usr/bin/env python3
"""Arithmetic examples of the frozen source; no native/guest execution or pass claim."""
import hashlib
import json
from pathlib import Path


def replay(enabled, now, due, slow=False):
    """Pending checker only: FetchNextTask -> Run -> ReInsertTaskIfNeed."""
    steps = []
    while due <= now:
        threshold = 5000 if enabled else 10000
        if now - due > threshold:
            steps.append({'now_ms': now, 'old_due_ms': due, 'action': 'reset_due_without_checker_evaluation'})
            due = now
        else:
            steps.append({'now_ms': now, 'old_due_ms': due,
                          'action': 'full_report_then_recovery' if slow else 'half_warning'})
            slow = True
            if steps[-1]['action'] == 'full_report_then_recovery':
                # Production next invokes KillPeerBinderProcess; the model stops here.
                return steps, due, slow
        due += 5000
    return steps, due, slow


def sleep_delta(boot_delta, monotonic_delta):
    # IsInSleep also requires initialized baselines, !IsInAppspwan and non-kick task.
    return abs(boot_delta - monotonic_delta) >= 2000


def main():
    snapshot = Path(__file__).with_name('source-review.json')
    source = json.loads(snapshot.read_text())
    records = {r['path']: r for r in source['records']}
    def text(suffix):
        rows = [r for p, r in records.items() if p.endswith(suffix)]
        assert len(rows) == 1
        return '\n'.join(line for section in rows[0]['excerpts'] for line in section['lines'])
    task = text('/watchdog_task.cpp')
    inner = text('/watchdog_inner.cpp')
    checker = text('/handler_checker.cpp')
    assert 'blockThresholdMs = 5000;' in task
    assert 'blockThresholdMs = resetRatio * checkInterval;' in task
    assert 'now - nextTickTime > (blockThresholdMs)' in task
    assert 'nextTickTime = now;' in task
    assert 'task.nextTickTime = task.nextTickTime + task.checkInterval;' in inner
    assert 'taskSlow_ = true;' in checker and 'return CheckStatus::WAITING;' in checker
    assert 'DEFAULT_SLEEP_TIME = 2 * 1000;' in inner
    assert 'WatchdogInner::KillPeerBinderProcess(description);' in task
    assert 'DelayBeforeExit(10);' in inner and '_exit(0);' in inner
    old = replay(False, 28000, 20000)
    new = replay(True, 28000, 20000)
    awake_half = replay(True, 20000, 20000)
    awake_full = replay(True, 25000, awake_half[1], awake_half[2])
    assert [s['action'] for s in old[0]] == ['half_warning', 'full_report_then_recovery']
    assert [s['action'] for s in new[0]] == ['reset_due_without_checker_evaluation']
    assert new[1] == 33000
    assert awake_half[0][0]['action'] == 'half_warning'
    assert awake_full[0][0]['action'] == 'full_report_then_recovery'
    assert sleep_delta(8000, 0) and not sleep_delta(8000, 8000)
    result = {
        'scope': 'Python_source_arithmetic_examples_NOT_extracted_native_function_test_NOT_runtime_fix',
        'source_snapshot_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        'historical_now_and_nextTickTime_not_captured': True,
        'example_only_interval_ms': 5000,
        'example_only_overdue_ms': 8000,
        'default_macro_absent': old[0],
        'macro_present_same_lateness': new[0],
        'awake_pending_checker_half_then_full': awake_half[0] + awake_full[0],
        'sleep_comparison_examples_initialized_non_appspawn_non_kick_task': {
            'boot_8000_mono_0_skip': sleep_delta(8000, 0),
            'boot_8000_mono_8000_skip': sleep_delta(8000, 8000)},
        'first_artifact_behavior_gate_passed': False,
    }
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
