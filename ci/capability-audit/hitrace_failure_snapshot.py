"""Preserve a failed caller's actual journal, trace and lifecycle state."""
import re


def capture(shell, remote):
    if re.fullmatch(r'/data/app/el2/100/base/org\.harmonycontrib\.hitraceaudit/files/'
                    r'hitrace-[a-f0-9]{32}-results\.log', remote or '') is None:
        raise ValueError('exact nonce-scoped HiTrace journal required')
    observations = {}
    for label, script in (
            ('caller-journal', 'if test -f ' + remote + '; then cat ' + remote + '; fi'),
            ('kernel-trace', 'cat /sys/kernel/tracing/trace'),
            ('processes', 'ps -ef'),
            ('ability-state', 'aa dump -a -u 100'),
            ('service-waits',
             'for task_snapshot_pid in $(pidof render_service appspawn '
             'org.harmonycontrib.capabilityaudit org.harmonycontrib.hitraceaudit); do '
             'cat /proc/$task_snapshot_pid/status; '
             'for task_snapshot_thread in /proc/$task_snapshot_pid/task/*; do '
             'echo "$task_snapshot_thread"; cat "$task_snapshot_thread/wchan"; '
             'cat "$task_snapshot_thread/stack"; done; done'),
            ('faultlog-inventory', 'ls -l /data/log/eventlog/freeze /data/log/faultlog/faultlogger'),
            ('hilog', 'hilog -x')):
        try:
            shell(script, 'failure-' + label)
            observations[label] = {'captured': True}
        except Exception as error:
            # A failed capture must not suppress later independent observations.
            observations[label] = {'capture_error': type(error).__name__ + ': ' + str(error)}
    return {'scope': 'readonly_failed_HiTrace_diagnostics_NOT_behavior_pass',
            'observations': observations}
