"""Collect bounded, read-only diagnostics from the same failed boot."""
import re


COMMANDS = (
    ('processes', 'ps -ef'),
    ('service-waits',
     'for boot_snapshot_pid in $(pidof render_service foundation composer_host allocator_host); do '
     'cat /proc/$boot_snapshot_pid/status; '
     'for boot_snapshot_thread in /proc/$boot_snapshot_pid/task/*; do '
     'echo "$boot_snapshot_thread"; cat "$boot_snapshot_thread/wchan"; '
     'cat "$boot_snapshot_thread/stack"; done; done'),
    ('faultlog-inventory', 'ls -l /data/log/eventlog/freeze /data/log/faultlog/faultlogger'),
    ('power-state', 'hidumper -s 3301 -a "-a"'),
    ('kernel-state', 'cat /proc/uptime; cat /sys/power/state; cat /sys/power/autosleep; dmesg'),
    ('hilog', 'hilog -x'),
)


def capture(shell, boot_id):
    """The caller records command logs and enforces a short per-command timeout."""
    if re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', boot_id or '') is None:
        raise ValueError('actual failed boot identity required')
    result = {'scope': 'readonly_failed_boot_diagnostics_NOT_behavior_pass',
              'expected_boot_id': boot_id, 'observations': {}}
    try:
        actual = shell('cat /proc/sys/kernel/random/boot_id', 'failure-identity').strip()
    except Exception as error:
        result['identity_error'] = type(error).__name__ + ': ' + str(error)
        return result
    result['observed_boot_id'] = actual
    if actual != boot_id:
        result['identity_error'] = 'failed boot is no longer the same kernel; no further commands'
        return result
    for label, script in COMMANDS:
        try:
            shell(script, 'failure-' + label)
            result['observations'][label] = {'captured': True}
        except Exception as error:
            result['observations'][label] = {'capture_error': type(error).__name__ + ': ' + str(error)}
    return result
