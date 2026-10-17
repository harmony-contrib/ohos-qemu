"""POSIX /proc identities and truthful owned PCM child exit receipts.

Guest images need cat/sed/readlink, not awk. A process generation is never an
empty string. Shell fragments stop before a signal on any failed observation.
"""
import json
import re
import shlex


def _pid(value):
    if not re.fullmatch(r'(?:[1-9][0-9]*|\$\$|\$[A-Za-z_][A-Za-z0-9_]*)', value):
        raise ValueError('literal positive PID or a private shell PID variable required')
    return value


def starttime_shell(pid):
    """Print field22 after the LAST comm closing delimiter, with checked reads."""
    pid = _pid(pid)
    return ('task_proc_pid=' + pid + '; '
        'case "$task_proc_pid" in (""|0*|*[!0-9]*) exit 1;; esac; '
        'task_proc_line=$(cat /proc/$task_proc_pid/stat) || exit 1; '
        'case "$task_proc_line" in ("$task_proc_pid ("*") "*) ;; (*) exit 1;; esac; '
        "task_proc_delimiter=') '; task_proc_tail=${task_proc_line##*\"$task_proc_delimiter\"}; "
        'set -f; set -- $task_proc_tail; test "$#" -ge 20 || exit 1; '
        'case "$1" in (R|S|D|Z|T|t|X|x|K|W|P|I) ;; (*) exit 1;; esac; '
        'shift 19; case "$1" in (""|0*|*[!0-9]*) exit 1;; esac; '
        'printf "%s\\n" "$1"')


def uids_shell(pid):
    pid = _pid(pid)
    return ('task_proc_pid=' + pid + '; '
        'case "$task_proc_pid" in (""|0*|*[!0-9]*) exit 1;; esac; '
        'task_proc_uids=$(sed -n \'s/^Uid:[[:space:]]*//p\' /proc/$task_proc_pid/status) || exit 1; '
        'set -f; set -- $task_proc_uids; test "$#" = 4 || exit 1; '
        'for task_proc_uid do case "$task_proc_uid" in (""|*[!0-9]*) exit 1;; esac; done; '
        'printf "%s %s %s %s\\n" "$1" "$2" "$3" "$4"')


def identity_shell(bundle, *, all_uids=True):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]+', bundle):
        raise ValueError('exact bundle required')
    return ('task_mic_app_pid=$(pidof ' + bundle + ') || exit 1; '
        'case "$task_mic_app_pid" in (""|0*|*[!0-9]*) exit 1;; esac; '
        'task_mic_app_start=$( ' + starttime_shell('$task_mic_app_pid') + ') || exit 1; '
        'task_mic_app_uids=$( ' + uids_shell('$task_mic_app_pid') + ') || exit 1; '
        'task_mic_app_after=$( ' + starttime_shell('$task_mic_app_pid') + ') || exit 1; '
        'test "$task_mic_app_start" = "$task_mic_app_after" || exit 1; '
        'printf "%s %s " "$task_mic_app_pid" "$task_mic_app_start"; ' +
        ('printf "%s\\n" "$task_mic_app_uids"' if all_uids else
         'set -f; set -- $task_mic_app_uids; '
         'test "$1" = "$2" && test "$1" = "$3" && test "$1" = "$4" || exit 1; printf "%s\\n" "$1"'))


def _remote(remote):
    if not re.fullmatch(r'/data/local/tmp/qemu-mic-[0-9a-f]{32}', remote):
        raise ValueError('exact owned microphone directory required')
    return remote


def producer_shell(remote, marker, *, repeat=20, timeout_ms=30000):
    remote = _remote(remote)
    if not re.fullmatch(r'__PCM_CHILD_EXIT_[0-9a-f]{32}__=', marker):
        raise ValueError('fresh owned PCM child exit nonce required')
    if (repeat, timeout_ms) not in ((20, 30000), (60, 90000)):
        raise ValueError('reviewed finite PCM configuration required')
    wrapper = ('umask 077; set -C; '
        'printf "%s\\n" "$$" > ' + remote + '/producer.pid || exit 1; '
        'task_pcm_start=$( ' + starttime_shell('$$') + ') || exit 1; '
        'printf "%s\\n" "$task_pcm_start" > ' + remote + '/producer.start || exit 1; '
        'unset LD_LIBRARY_PATH LD_PRELOAD; exec ' + remote + '/alsa_inject --input ' + remote +
        '/challenge.pcm --rate 48000 --channels 2 --repeat ' + str(repeat) + ' --timeout-ms ' + str(timeout_ms))
    # The inner sh is replaced by the native producer. The enclosing target sh
    # reports that child's real wait status, even when HDC itself returns zero.
    return ('sh -c ' + shlex.quote(wrapper) + '; task_pcm_child_rc=$?; '
            'printf "\\n' + marker + '%s\\n" "$task_pcm_child_rc"')


def producer_rows(raw, producer, *, remote, repeat=20, timeout_ms=30000):
    marker = producer.get('guest_exit_marker', '')
    expected = producer_shell(remote, marker, repeat=repeat, timeout_ms=timeout_ms)
    argv = producer.get('argv', [])
    if not argv or argv[-1] != expected:
        raise ValueError('PCM receipt does not bind the exact child wrapper/nonce')
    raw = raw.replace('\r', '')
    footer = '\n' + marker + '0\n'
    if (producer.get('host_exit_code') != 0 or producer.get('guest_exit_code') != 0 or
            not raw.endswith(footer) or raw.count(marker) != 1):
        raise ValueError('actual independent PCM child did not exit successfully')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError('duplicate PCM JSON field')
            value[key] = item
        return value
    def constant(value): raise ValueError('nonfinite PCM JSON value')
    return [json.loads(line, object_pairs_hook=unique, parse_constant=constant)
            for line in raw[:-len(footer)].splitlines() if line.strip()]


def producer_exit_code(raw, marker):
    if not re.fullmatch(r'__PCM_CHILD_EXIT_[0-9a-f]{32}__=', marker):
        raise ValueError('PCM child exit nonce missing')
    raw=raw.replace('\r','')
    matches=re.findall(r'\n'+re.escape(marker)+r'([0-9]+)\n\Z',raw)
    if len(matches)!=1 or raw.count(marker)!=1:
        raise ValueError('actual PCM child exit record incomplete or duplicated')
    return int(matches[0])


def cleanup_producer_shell(remote):
    remote = _remote(remote)
    return ('test -d ' + remote + ' && test ! -L ' + remote +
        ' && test "$(stat -c \'%u %a\' ' + remote + ')" = "0 700" || exit 1; '
        'if test -e ' + remote + '/producer.pid || test -L ' + remote + '/producer.pid; then '
        'test -f ' + remote + '/producer.pid && test ! -L ' + remote + '/producer.pid && '
        'test -f ' + remote + '/producer.start && test ! -L ' + remote + '/producer.start && '
        'test "$(stat -c %u ' + remote + '/producer.pid)" = 0 && '
        'test "$(stat -c %u ' + remote + '/producer.start)" = 0 || exit 1; '
        'task_mic_pid=$(cat ' + remote + '/producer.pid) || exit 1; '
        'task_mic_start=$(cat ' + remote + '/producer.start) || exit 1; '
        'case "$task_mic_pid" in (""|0*|*[!0-9]*) exit 1;; esac; '
        'case "$task_mic_start" in (""|0*|*[!0-9]*) exit 1;; esac; '
        'if test -d /proc/$task_mic_pid; then '
        'task_mic_current=$( ' + starttime_shell('$task_mic_pid') + ') || exit 1; '
        'task_mic_uids=$( ' + uids_shell('$task_mic_pid') + ') || exit 1; '
        'task_mic_exe=$(readlink /proc/$task_mic_pid/exe) || exit 1; '
        'test "$task_mic_current" = "$task_mic_start" && test "$task_mic_uids" = "0 0 0 0" && '
        'test "$task_mic_exe" = ' + remote + '/alsa_inject || exit 1; '
        'task_mic_final=$( ' + starttime_shell('$task_mic_pid') + ') || exit 1; '
        'test "$task_mic_final" = "$task_mic_start" || exit 1; '
        'kill -TERM "$task_mic_pid" || exit 1; '
        'task_mic_wait=0; while test -d /proc/$task_mic_pid; do '
        'task_mic_current=$( ' + starttime_shell('$task_mic_pid') + ') || '
        '{ test ! -d /proc/$task_mic_pid && break; exit 1; }; '
        'test "$task_mic_current" = "$task_mic_start" || exit 1; '
        'test "$task_mic_wait" -lt 30 || exit 1; task_mic_wait=$((task_mic_wait + 1)); sleep 0.1; done; fi; '
        'else test ! -e ' + remote + '/producer.start && test ! -L ' + remote + '/producer.start; fi')
