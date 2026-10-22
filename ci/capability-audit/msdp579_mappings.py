"""Checked, read-only /proc maps evidence; no incomplete-scan absence claims.

The public renderer fixes /proc and never signals, starts an observer, or changes
permissions. Every read has a raw byte/diagnostic payload and exit status. A
framed END proves transport shape only. Failed reads, PID churn, reused PIDs and
unread newly enumerated PIDs remain explicit gaps. In particular, short-lived
enumeration children are not silently counted as inspected processes.

Global absence requires a complete all-PID capture. A separate positive proof
can bind two complete single-PID cuts to an actual GNSS Dump header. Its UID,
argv, SELinux context and required DSOs derive from hashed same-image init,
passwd and GNSS image receipts, never a naked expected_uid argument. The owning
driver must retain the commands ordering the two cuts around its actual Dump.
This module does not prove a callback, wire nonce, SDK, or runtime acceptance.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex

SCHEMA = 'LIVE_MAPS_V1'
MAX_BYTES = 32 * 1024 * 1024
MAX_PIDS = 32768
OPS = ('stat_before', 'status', 'cmdline', 'exe', 'maps', 'attr', 'stat_after')
LIBRARIES = {
    'vendorGnssAdapter.so': '/vendor/lib64/vendorGnssAdapter.so',
    'libgnss_interface_service_2.0.z.so': '/vendor/lib64/libgnss_interface_service_2.0.z.so',
    'liblbsservice_gnss.z.so': '/system/lib64/liblbsservice_gnss.z.so',
    'libhdi_sensor_impl.z.so': '/vendor/lib64/libhdi_sensor_impl.z.so',
    'libsensor_driver.z.so': '/vendor/lib64/libsensor_driver.z.so',
    'libdevicestatus_algo.z.so': '/system/lib64/libdevicestatus_algo.z.so',
    'libdevicestatus_service.z.so': '/system/lib64/libdevicestatus_service.z.so',
    'libdevicestatus_mock.z.so': '/system/lib64/libdevicestatus_mock.z.so',
}
ROLE_LIBRARIES = {
    'business': {'service.so': LIBRARIES['liblbsservice_gnss.z.so']},
    'provider': {'provider.so': LIBRARIES['vendorGnssAdapter.so'],
                 'bridge.so': LIBRARIES['libgnss_interface_service_2.0.z.so']},
}
# Same independently exported product sched.h contract used by process cleanup.
# An empty maps read is still required; PF_KTHREAD never excuses unread maps.
KERNEL_CONTRACT = {
    'PF_KTHREAD': 0x00200000,
    'producer_sha256': 'f6f41151f6a432b91a2be30d81288571b112bdc76c5a39771686f0cdd9e2fbdf',
    'linux-5.10/include/linux/sched.h': 'eb02fc4e99e49685496289fe245af492b2612709f0233114e087f16304d5fca9',
    'linux-6.6/include/linux/sched.h': 'c15bf201f1782aceb3ccda7f75ac8bc99c598efacaa20a71baeae723bd18e405',
}


class MappingSchemaError(ValueError):
    """Incomplete/ambiguous raw transport; no parsed completeness is available."""


class MappingGap(ValueError):
    """Actual raw evidence is retained but cannot support the requested proof."""
    def __init__(self, message, snapshot=None):
        self.snapshot = snapshot
        super().__init__(message)


def require(value, message):
    if not value:
        raise MappingSchemaError(message)


LIBRARIES = dict(LIBRARIES, msdp579_cooperate64='/system/lib64/libintention_cooperate.z.so',
                 msdp579_cooperate32='/system/lib/libintention_cooperate.z.so',
                 msdp579_client64='/system/lib64/libdevicestatus_client.z.so',
                 msdp579_client32='/system/lib/libdevicestatus_client.z.so',
                 msdp579_client_platform64='/system/lib64/platformsdk/libdevicestatus_client.z.so',
                 msdp579_client_platform32='/system/lib/platformsdk/libdevicestatus_client.z.so')


def _identity(nonce, boot_id, pid, libraries):
    require(type(nonce) is str and re.fullmatch('[a-f0-9]{32}', nonce) and nonce != '0' * 32,
            'fresh scan nonce required')
    require(type(boot_id) is str and re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', boot_id),
            'actual boot ID required')
    require(pid is None or type(pid) is int and 0 < pid < 2**31, 'positive target PID or all-PID scope required')
    require(type(libraries) in (tuple, list) and len(libraries) == len(set(libraries)) and
            all(value in LIBRARIES.values() or re.fullmatch(r'/system/(?:lib|lib64)/(?:platformsdk/|chipset-sdk/|chipset-sdk-sp/)?lib(?:devicestatus_client|intention_cooperate)\.z\.so',value) is not None for value in libraries), 'exact bounded library paths required')


def _snapshot_script(nonce, boot_id, *, pid=None, libraries=(), proc_root='/proc'):
    # Alternate proc_root is for root's future POSIX fixture tests only. The
    # public API below never permits a caller to replace the genuine /proc.
    _identity(nonce, boot_id, pid, libraries)
    require(type(proc_root) is str and proc_root.startswith('/') and '\x00' not in proc_root, 'absolute proc root required')
    scope = 'all' if pid is None else str(pid)
    first = '|'.join(('BEGIN', SCHEMA, nonce, boot_id, scope, ','.join(libraries) or '-'))
    body = r'''LC_ALL=C; export LC_ALL
set -f
IFS='
\t '
for task_maps_tool in od cat readlink id sha256sum stat; do
  command -v "$task_maps_tool" >/dev/null 2>&1 || exit 1
done
task_maps_n=0; task_maps_q=0; task_maps_d=0
# Builtin glob expansion creates no short-lived ls process in its own PID set.
# A failed/unexpanded glob remains an explicit nonzero query, never empty success.
task_maps_enumerate() {
  task_maps_listing=''
  set +f
  set -- "$task_maps_proc"/[0-9]*
  set -f
  for task_maps_entry do
    task_maps_number=${task_maps_entry##*/}
    case "$task_maps_number" in (''|0*|*[!0-9]*) return 1;; esac
    task_maps_listing="$task_maps_listing$task_maps_number
"
  done
}
task_maps_compact() {
  task_maps_hex=''
  for task_maps_byte in $1; do
    case "$task_maps_byte" in
      ([0123456789abcdef][0123456789abcdef]) task_maps_hex=$task_maps_hex$task_maps_byte;;
      (*) exit 1;;
    esac
  done
}
task_maps_texthex() {
  task_maps_od=$(od -An -v -tx1 <<TASK_MAPS_TEXT
$1
TASK_MAPS_TEXT
  ) || exit 1
  task_maps_compact "$task_maps_od"
  case "$task_maps_hex" in *0a) task_maps_hex=${task_maps_hex%0a};; *) exit 1;; esac
}
task_maps_read() {
  task_maps_data=$(od -An -v -tx1 "$1" 2>&1); task_maps_rc=$?
  if test "$task_maps_rc" -eq 0; then
    task_maps_compact "$task_maps_data"
  else task_maps_texthex "$task_maps_data"; fi
}
task_maps_direct() {
  task_maps_texthex "$3"
  printf 'D|%s|%s|%s\n' "$1" "$2" "$task_maps_hex" || exit 1
  task_maps_d=$((task_maps_d + 1))
}
task_maps_query() {
  task_maps_read "$3"
  printf 'Q|%s|%s|%s|%s\n' "$1" "$2" "$task_maps_rc" "$task_maps_hex" || exit 1
  task_maps_q=$((task_maps_q + 1))
}
task_maps_value=$(id -u 2>&1); task_maps_rc=$?; task_maps_direct observer_uid "$task_maps_rc" "$task_maps_value"
task_maps_value=$(cat "$task_maps_proc/sys/kernel/random/boot_id" 2>&1); task_maps_rc=$?; task_maps_direct boot_before "$task_maps_rc" "$task_maps_value"
task_maps_value=$(cat "$task_maps_proc/uptime" 2>&1); task_maps_rc=$?; task_maps_direct uptime_before "$task_maps_rc" "$task_maps_value"
task_maps_i=0
for task_maps_lib in $task_maps_libraries; do
  task_maps_value=$(stat -L -c '%D %i %s' "$task_maps_lib" 2>&1); task_maps_rc=$?; task_maps_direct "file_before_$task_maps_i" "$task_maps_rc" "$task_maps_value"
  task_maps_value=$(sha256sum "$task_maps_lib" 2>&1); task_maps_rc=$?; task_maps_direct "hash_before_$task_maps_i" "$task_maps_rc" "$task_maps_value"
  task_maps_i=$((task_maps_i + 1))
done
if test "$task_maps_scope" = all; then
  task_maps_enumerate; task_maps_rc=$?
  task_maps_direct list_before "$task_maps_rc" "$task_maps_listing"
else task_maps_listing=$task_maps_scope; fi
for task_maps_pid in $task_maps_listing; do
  case "$task_maps_pid" in ''|*[!0-9]*) continue;; esac
  task_maps_n=$((task_maps_n + 1)); task_maps_path=$task_maps_proc/$task_maps_pid
  printf 'PID|%s\n' "$task_maps_pid" || exit 1
  task_maps_query "$task_maps_pid" stat_before "$task_maps_path/stat"
  task_maps_query "$task_maps_pid" status "$task_maps_path/status"
  task_maps_query "$task_maps_pid" cmdline "$task_maps_path/cmdline"
  task_maps_value=$(readlink "$task_maps_path/exe" 2>&1); task_maps_rc=$?
  task_maps_texthex "$task_maps_value"
  printf 'Q|%s|exe|%s|%s\n' "$task_maps_pid" "$task_maps_rc" "$task_maps_hex" || exit 1
  task_maps_q=$((task_maps_q + 1))
  task_maps_query "$task_maps_pid" maps "$task_maps_path/maps"
  task_maps_query "$task_maps_pid" attr "$task_maps_path/attr/current"
  task_maps_query "$task_maps_pid" stat_after "$task_maps_path/stat"
  printf 'TERMINAL|%s|7\n' "$task_maps_pid" || exit 1
done
if test "$task_maps_scope" = all; then
  task_maps_enumerate; task_maps_rc=$?; task_maps_direct list_after "$task_maps_rc" "$task_maps_listing"
fi
task_maps_i=0
for task_maps_lib in $task_maps_libraries; do
  task_maps_value=$(stat -L -c '%D %i %s' "$task_maps_lib" 2>&1); task_maps_rc=$?; task_maps_direct "file_after_$task_maps_i" "$task_maps_rc" "$task_maps_value"
  task_maps_value=$(sha256sum "$task_maps_lib" 2>&1); task_maps_rc=$?; task_maps_direct "hash_after_$task_maps_i" "$task_maps_rc" "$task_maps_value"
  task_maps_i=$((task_maps_i + 1))
done
task_maps_value=$(cat "$task_maps_proc/uptime" 2>&1); task_maps_rc=$?; task_maps_direct uptime_after "$task_maps_rc" "$task_maps_value"
task_maps_value=$(cat "$task_maps_proc/sys/kernel/random/boot_id" 2>&1); task_maps_rc=$?; task_maps_direct boot_after "$task_maps_rc" "$task_maps_value"
printf 'END|%s|%s|%s|%s\n' "$task_maps_nonce" "$task_maps_n" "$task_maps_q" "$task_maps_d" || exit 1
'''
    # A real TAB, not a shell IFS containing the literal letters backslash/t.
    body = body.replace("IFS='\n\\t '", "IFS='\n\t '")
    return ('task_maps_proc=' + shlex.quote(proc_root) + '; task_maps_scope=' + scope +
            '; task_maps_nonce=' + nonce + '; task_maps_libraries=' + shlex.quote(' '.join(libraries)) + ';\n' +
            "printf '%s\\n' " + shlex.quote(first) + ' || exit 1\n' + body)


def snapshot_script(nonce, boot_id, *, pid=None, libraries=()):
    return _snapshot_script(nonce, boot_id, pid=pid, libraries=libraries)


def _hex(value):
    require(type(value) is str and len(value) <= MAX_BYTES and re.fullmatch('(?:[a-f0-9]{2})*', value), 'bounded raw hex required')
    return bytes.fromhex(value)


def _text(value):
    return _hex(value).decode('utf-8')


def _stat(value, pid):
    text = _text(value)
    match = re.fullmatch(r'([1-9][0-9]*) \((.*)\) (.*)\n', text, re.S)
    require(match and int(match[1]) == pid, 'raw stat PID/complete newline differs')
    fields = match[3].split()
    require(len(fields) >= 20 and fields[0] in tuple('RSDZTWtXxKIP') and
            all(re.fullmatch('[0-9]+', fields[index]) for index in (1, 2, 6, 19)) and int(fields[19]) > 0,
            'raw stat state/flags/positive start generation differs')
    return dict(pid=pid, comm=match[2], state=fields[0], ppid=int(fields[1]), pgrp=int(fields[2]),
                flags=int(fields[6]), start_ticks=int(fields[19]), raw_hex=value)


def _status(value, pid):
    text = _text(value); fields = {}
    require(text.endswith('\n'), 'complete status required')
    for line in text.splitlines():
        key, sep, item = line.partition(':')
        if sep and key in ('Pid', 'Uid', 'Name'):
            require(key not in fields, 'duplicate status identity field')
            fields[key] = item.strip()
    require(fields.get('Pid') == str(pid) and re.fullmatch('[0-9]+(?:[ \t]+[0-9]+){3}', fields.get('Uid', '')),
            'status PID/four UID values required')
    return text, list(map(int, fields['Uid'].split()))


def _maps(value):
    text = _text(value)
    require(not text or text.endswith('\n'), 'maps read lacks complete final line')
    result = []
    for line in text.splitlines():
        match = re.fullmatch(r'([0-9a-f]+)-([0-9a-f]+) ([r-][w-][x-][ps]) ([0-9a-f]+) ([0-9a-f]+):([0-9a-f]+) ([0-9]+)(?:[ \t]+(.*))?', line)
        require(match and int(match[1], 16) < int(match[2], 16), 'malformed full maps line')
        path = match[8] or ''; deleted = path.endswith(' (deleted)')
        result.append(dict(path=path[:-10] if deleted else path, deleted=deleted, permissions=match[3],
                           device=[int(match[5], 16), int(match[6], 16)], inode=int(match[7]), raw_line=line))
    return result


def _listing(value):
    names = _text(value).splitlines()
    require(names and all(re.fullmatch('[A-Za-z0-9_.-]+', name) for name in names), 'complete /proc listing required')
    pids = [int(name) for name in names if name.isdigit()]
    require(1 in pids and len(pids) == len(set(pids)) and len(pids) <= MAX_PIDS and all(0 < p < 2**31 for p in pids),
            'unique bounded init-containing PID enumeration required')
    return pids


def _uptime(value):
    fields = _text(value).split()
    require(len(fields) == 2 and all(re.fullmatch(r'[0-9]+\.[0-9]+', f) for f in fields), 'actual /proc/uptime required')
    whole, fraction = fields[0].split('.')
    require(len(fraction) <= 9, 'bounded uptime precision required')
    lower = int(whole) * 10**9 + int(fraction.ljust(9, '0'))
    return lower, lower + 10**(9 - len(fraction))


def parse_snapshot(raw, nonce, boot_id, *, pid=None, libraries=()):
    _identity(nonce, boot_id, pid, libraries)
    require(type(raw) is str and raw.endswith('\n') and len(raw.encode()) <= MAX_BYTES, 'complete bounded raw maps frame required')
    lines = raw.splitlines(); scope = 'all' if pid is None else str(pid)
    require(lines and lines[0] == '|'.join(('BEGIN', SCHEMA, nonce, boot_id, scope, ','.join(libraries) or '-')),
            'maps frame schema/nonce/boot/scope/library binding differs')
    tail = lines[-1].split('|')
    require(len(tail) == 5 and tail[:2] == ['END', nonce] and all(re.fullmatch('[0-9]+', x) for x in tail[2:]), 'complete maps END required')
    pre = ['observer_uid', 'boot_before', 'uptime_before']
    pre += [name for i in range(len(libraries)) for name in (f'file_before_{i}', f'hash_before_{i}')]
    post = [name for i in range(len(libraries)) for name in (f'file_after_{i}', f'hash_after_{i}')]
    if pid is None: pre += ['list_before']; post.insert(0, 'list_after')
    post += ['uptime_after', 'boot_after']
    records, direct = {}, {}; current = None; count = 0; rows_started = False; rows_finished = False
    for line in lines[1:-1]:
        parts = line.split('|'); kind = parts[0]
        if kind == 'D':
            require(current is None and len(parts) == 4 and parts[1] not in direct and re.fullmatch('[a-z_0-9]+', parts[1]) and
                    re.fullmatch('[0-9]+', parts[2]) and int(parts[2]) <= 255, 'unique checked metadata query required')
            if rows_started: rows_finished = True
            _hex(parts[3]); direct[parts[1]] = dict(rc=int(parts[2]), hex=parts[3])
        elif kind == 'PID':
            require(not rows_finished and current is None and len(parts) == 2 and re.fullmatch('[1-9][0-9]*', parts[1]), 'misplaced PID begin')
            require(list(direct) == pre, 'actual pre-query metadata missing/reordered')
            current = int(parts[1]); require(current < 2**31 and current not in records and len(records) < MAX_PIDS, 'duplicate/unbounded PID')
            rows_started = True; records[current] = {}
        elif kind == 'Q':
            require(current is not None and len(parts) == 5 and parts[1] == str(current) and
                    parts[2] in OPS and parts[2] not in records[current] and re.fullmatch('[0-9]+', parts[3]) and int(parts[3]) <= 255,
                    'invalid/duplicate checked process query')
            _hex(parts[4]); records[current][parts[2]] = dict(rc=int(parts[3]), hex=parts[4]); count += 1
        elif kind == 'TERMINAL':
            require(current is not None and parts == ['TERMINAL', str(current), str(len(OPS))] and tuple(records[current]) == OPS,
                    'partial/misordered process query set')
            current = None
        else:
            raise MappingSchemaError('unknown/control injection in maps frame')
    require(current is None and list(map(int, tail[2:])) == [len(records), count, len(direct)], 'partial PID/query/count/END capture')
    require(list(direct) == pre + post, 'missing/extra/reordered actual metadata observations')
    gaps = [dict(kind='query_error', operation=name, **item) for name, item in direct.items() if item['rc']]
    def metadata(name):
        return _text(direct[name]['hex']) if direct[name]['rc'] == 0 else None
    if metadata('observer_uid') != '0': gaps.append(dict(kind='root_visibility_unproved'))
    for name in ('boot_before', 'boot_after'):
        if metadata(name) != boot_id: gaps.append(dict(kind='boot_changed_or_unread', operation=name))
    uptime = None
    if not direct['uptime_before']['rc'] and not direct['uptime_after']['rc']:
        first, last = _uptime(direct['uptime_before']['hex']), _uptime(direct['uptime_after']['hex'])
        if last[0] < first[0]: gaps.append(dict(kind='clock_regressed'))
        else: uptime = [first[0], last[1]]
    start_ids = end_ids = None
    if pid is None:
        if not direct['list_before']['rc']: start_ids = _listing(direct['list_before']['hex'])
        if not direct['list_after']['rc']: end_ids = _listing(direct['list_after']['hex'])
        if start_ids is not None:
            require(list(records) == start_ids, 'enumerated PID missing/unlisted/reordered: partial scan')
        if start_ids is not None and end_ids is not None and set(start_ids) != set(end_ids):
            gaps.append(dict(kind='enumeration_churn', gone=sorted(set(start_ids) - set(end_ids)),
                             unread_new_pids=sorted(set(end_ids) - set(start_ids))))
    else:
        require(list(records) == [pid], 'exact single-PID capture required')
    processes = {}
    for number, queries in records.items():
        local = []; before = after = None
        for op in ('stat_before', 'stat_after'):
            if not queries[op]['rc']:
                item = _stat(queries[op]['hex'], number)
                if op == 'stat_before': before = item
                else: after = item
        kernel = bool(before and after and before['flags'] & KERNEL_CONTRACT['PF_KTHREAD'] and after['flags'] & KERNEL_CONTRACT['PF_KTHREAD'])
        zombie = bool(before and after and before['state'] in 'ZXx' and after['state'] in 'ZXx')
        for op, item in queries.items():
            # This is an explicit product-kernel non-executable category. It
            # never excuses failed maps/status/stat reads, or nonempty stderr.
            if item['rc'] and not (op == 'exe' and item['rc'] in (1, 2) and item['hex'] == '' and (kernel or zombie)):
                local.append(dict(kind='process_query_error', pid=number, operation=op, **item))
        if before and after and (before['start_ticks'], before['ppid'], before['pgrp']) != (after['start_ticks'], after['ppid'], after['pgrp']):
            local.append(dict(kind='process_generation_changed', pid=number, before=before, after=after))
        status, uids, maps, argv, exe, attr = None, None, [], None, None, None
        if queries['status']['rc'] == 0: status, uids = _status(queries['status']['hex'], number)
        if queries['maps']['rc'] == 0: maps = _maps(queries['maps']['hex'])
        if queries['maps']['rc'] == 0 and not maps and not (kernel or zombie):
            local.append(dict(kind='live_maps_empty', pid=number))
        if queries['exe']['rc'] == 0:
            exe = _text(queries['exe']['hex']); require(exe.startswith('/') and '\n' not in exe and '\x00' not in exe, 'exact actual executable path required')
        if queries['cmdline']['rc'] == 0:
            cmd = _hex(queries['cmdline']['hex'])
            if cmd:
                require(cmd.endswith(b'\x00'), 'complete actual argv boundary required')
                argv = [part.decode('utf-8') for part in cmd[:-1].split(b'\x00')]
                require(argv[0], 'nonempty actual argv0 required')
            elif not (kernel or zombie): local.append(dict(kind='live_cmdline_empty', pid=number))
            else: argv = []
        if queries['attr']['rc'] == 0:
            # procattr can expose the kernel context's terminating NUL. Retain
            # every raw byte; only the parsed context view removes that one
            # terminator and/or one final newline, never interior bytes.
            context = re.fullmatch(r'([^\x00\n]+)(?:\x00)?\n?', _text(queries['attr']['hex']))
            require(context is not None, 'complete actual SELinux context required')
            attr = context[1]
        if (kernel or zombie) and maps: local.append(dict(kind='non_executable_has_mappings', pid=number))
        if before and after and not (kernel or zombie) and (before['state'] in 'ZXx' or after['state'] in 'ZXx'):
            local.append(dict(kind='process_exited_during_capture', pid=number))
        processes[number] = dict(pid=number, boot_id=boot_id, before=before, after=after, status=status, uids=uids,
                                  argv=argv, exe=exe, attr=attr, maps=maps, complete=not local,
                                  classification='kernel' if kernel else 'zombie' if zombie else 'user', queries=queries, gaps=local)
        gaps.extend(local)
    if pid is None and (1 not in processes or not processes[1]['complete'] or not processes[1]['before'] or processes[1]['before']['ppid'] != 0):
        gaps.append(dict(kind='live_init_not_fully_observed'))
    return dict(schema=SCHEMA, nonce=nonce, boot_id=boot_id, pid=pid, libraries=list(libraries),
                raw=raw, raw_sha256=hashlib.sha256(raw.encode()).hexdigest(), queries=direct,
                processes=processes, start_pids=start_ids, end_pids=end_ids, uptime_interval_ns=uptime,
                complete=not gaps, global_absence_eligible=pid is None and not gaps, gaps=gaps,
                scope='read_only_proc_maps_observation_ONLY', first_artifact_behavior_gate_passed=False, capabilityIdsClosed=0)


def _reparse(snapshot):
    # Do not let a hand-edited complete flag promote a retained partial capture.
    return parse_snapshot(snapshot['raw'], snapshot['nonce'], snapshot['boot_id'],
                          pid=snapshot['pid'], libraries=snapshot['libraries'])


def require_complete(snapshot, *, global_absence=False):
    actual = _reparse(snapshot)
    if not actual['complete'] or global_absence and not actual['global_absence_eligible']:
        raise MappingGap('incomplete actual proc/maps observation: ' + json.dumps(actual['gaps']), actual)
    return actual


def legacy_text(snapshot):
    """Compatibility view for the existing verifier, only after full coverage."""
    actual = require_complete(snapshot, global_absence=True); blocks = []
    for pid, process in actual['processes'].items():
        chosen = [row['raw_line'] for row in process['maps'] if Path(row['path']).name in LIBRARIES]
        if chosen:
            blocks.append('PROCESS /proc/' + str(pid) + '\n' + process['status'] + process['attr'] + '\n' + '\n'.join(chosen))
    return '\n\n'.join(blocks) + '\n'


def verify_evidence(entry, command, *, target):
    """Recompute a retained Capture.mapping_snapshot, including actual shell rc.

    The caller selects command from capture.report.commands[command_index]. It
    must retain that enclosing report. A derived JSON/PROCESS view cannot hide
    raw gaps, change scope, or detach from the exact collector command.
    """
    require(_artifact(entry['parser']) == Path(__file__).read_bytes(), 'actual maps helper source differs')
    script = _artifact(entry['script']).decode('utf-8')
    require(script == snapshot_script(entry['nonce'], entry['boot_id'], pid=entry['pid'], libraries=entry['libraries']), 'collector script/source binding differs')
    raw = _artifact(entry['raw']).decode('utf-8')
    result = parse_snapshot(raw, entry['nonce'], entry['boot_id'], pid=entry['pid'], libraries=entry['libraries'])
    expected = json.loads(json.dumps({key: value for key, value in result.items() if key != 'raw'}, allow_nan=False))
    require(_json_artifact(entry['parsed']) == expected and entry['complete'] is result['complete'] and
            entry['global_absence_eligible'] is result['global_absence_eligible'], 'derived maps observation flags/view differ from retained raw')
    require(type(command.get('exit_code')) is int and command['exit_code'] == 0 and not command.get('timed_out') and
            command['argv'][1:4] == ['-t', target, 'shell'], 'actual successful target shell command required')
    argv = command['argv'][-1]
    markers = re.findall('__LIVE_GUEST_EXIT_[a-f0-9]{32}__=', argv)
    require(len(markers) == 1, 'unique actual guest exit nonce required')
    marker = markers[0]
    require(argv == '(' + script + '); task_live_rc=$?; printf "\\n' + marker + '%s\\n" "$task_live_rc"', 'actual command is not the exact maps collector')
    output = _artifact(dict(path=command['log'], sha256=command['sha256'])).decode('utf-8').replace('\r', '')
    require(output == raw + '\n' + marker + '0\n', 'actual raw collector/guest exit log differs')
    if 'legacy_view' in entry:
        require(_artifact(entry['legacy_view']).decode('utf-8') == legacy_text(result), 'legacy maps view not derived from complete retained scan')
    return result


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate contract field'); result[key] = value
    return result


def _artifact(descriptor):
    require(type(descriptor) is dict and set(descriptor) == {'path', 'sha256'} and
            type(descriptor['path']) is str and re.fullmatch('[a-f0-9]{64}', descriptor['sha256'] or ''), 'exact contract artifact descriptor required')
    path = Path(descriptor['path'])
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'actual regular contract artifact required')
    data = path.read_bytes(); require(hashlib.sha256(data).hexdigest() == descriptor['sha256'], 'contract artifact changed')
    return data


def _json_artifact(descriptor):
    return json.loads(_artifact(descriptor), object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(MappingSchemaError('nonfinite contract JSON')))


def load_contract(descriptor, *, image_hashes):
    """Derive role from actual image-export receipts; missing facts are a gap.

    descriptor keys: role, service_name, init, passwd, config_receipt,
    image_evidence; business also requires profile and profile_receipt. Artifact
    fields are exact {path,sha256} records. Root must
    supply image_hashes from the *current* enclosing package/boot, not old F09.
    Supported config receipt uses dumped[] and image_records as the root's
    read-only image exporter. Its init/passwd entries must join those bytes.
    """
    if descriptor is None:
        raise MappingGap('actual same-image init/passwd/DSO contract is unavailable')
    require(type(descriptor) is dict and type(descriptor.get('role')) is str and descriptor['role'] in ROLE_LIBRARIES,
            'actual source-bound GNSS process role required')
    role = descriptor['role']
    require(descriptor.get('service_name') == {'business': 'locationhub', 'provider': 'location_host'}[role],
            'actual GNSS init service role differs')
    fields = {'role', 'service_name', 'init', 'passwd', 'config_receipt', 'image_evidence'}
    if role == 'business': fields |= {'profile', 'profile_receipt'}
    require(set(descriptor) == fields, 'exact source-bound GNSS role contract required')
    require(type(image_hashes) is dict and {'system', 'vendor'} <= image_hashes.keys() and
            all(re.fullmatch('[a-f0-9]{64}', image_hashes[k] or '') for k in ('system', 'vendor')), 'current boot image hashes required')
    receipt = _json_artifact(descriptor['config_receipt']); evidence = _json_artifact(descriptor['image_evidence'])
    require(receipt.get('exit_code') == 0 and evidence.get('status') == 'pass' and
            evidence.get('scope') == 'GNSS_source_build_image_binding_ONLY_NOT_loaded_or_public_location', 'actual image config/GNSS byte receipts required')
    for image in ('system', 'vendor'):
        require(receipt['image_records'][image]['sha256'] == image_hashes[image] == evidence[image + '_image_sha256'], 'old/foreign image role contract')
    for key in ('init', 'passwd'):
        source = descriptor[key]; _artifact(source)
        entries = [row for row in receipt['dumped'] if row.get('path') == source['path'] and row.get('sha256') == source['sha256']]
        require(len(entries) == 1 and entries[0]['image'] in image_hashes and
                receipt['image_records'][entries[0]['image']]['sha256'] == image_hashes[entries[0]['image']], 'config bytes not joined to current image export')
    config = _json_artifact(descriptor['init'])
    matches = [s for s in config['services'] if s.get('name') == descriptor['service_name']]
    require(len(matches) == 1, 'unique actual init service required')
    service = matches[0]; uid_name = service['uid']
    passwd = _artifact(descriptor['passwd']).decode('utf-8')
    accounts = [line.split(':') for line in passwd.splitlines() if line and not line.startswith('#')]
    require(type(uid_name) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_-]*', uid_name), 'actual named init UID required')
    accounts = [fields for fields in accounts if fields[0] == uid_name]
    require(len(accounts) == 1 and len(accounts[0]) == 7 and re.fullmatch('[0-9]+', accounts[0][2]), 'unique actual passwd UID required')
    uid = int(accounts[0][2]); argv = service['path']; context = service['secon']
    require(0 < uid < 10000 and type(argv) is list and argv and all(type(a) is str and a for a in argv) and
            argv[0].startswith('/') and type(context) is str and context.startswith('u:r:'), 'actual init UID/argv/context contract incomplete')
    if role == 'business':
        profile = _json_artifact(descriptor['profile']); profile_receipt = _json_artifact(descriptor['profile_receipt'])
        require(len(argv) == 2 and argv[1].startswith('/') and profile['process'] == service['name'] and
                profile_receipt['expected_system_image_sha256'] == image_hashes['system'] and
                profile_receipt['image'] == receipt['image_records']['system']['path'], 'same-image init/SA profile process join missing')
        commands = [command for command in profile_receipt['commands'] if command.get('exists') is True and
                    command.get('exit_code') == 0 and command.get('sha256') == descriptor['profile']['sha256'] and
                    len(command.get('argv', [])) == 4 and command['argv'][1:] == ['-R',
                        'dump ' + argv[1] + ' ' + descriptor['profile']['path'], profile_receipt['image']]]
        require(len(commands) == 1, 'actual same-image SA profile export command missing')
        abilities = [ability for ability in profile['systemability'] if ability.get('name') == 2803]
        require(len(abilities) == 1 and abilities[0]['libpath'] == 'liblbsservice_gnss.z.so', 'actual GNSS business SA/DSO profile differs')
    libraries = {}
    for asset, remote in ROLE_LIBRARIES[role].items():
        item = evidence['image_assets'][asset]
        require(re.fullmatch('[a-f0-9]{64}', item['sha256']) and
                (remote in item.get('image_path_aliases', []) or remote.removeprefix('/system').removeprefix('/vendor') == item['image_path']),
                'GNSS DSO path/image contract differs')
        libraries[remote] = item['sha256']
    return dict(role=role, uid=uid, argv=argv, exe=argv[0], context=context, libraries=libraries, sources=descriptor,
                image_hashes=image_hashes, scope='derived_actual_image_role_NOT_loaded_process')


def _file_identity(text):
    match = re.fullmatch('([a-fA-F0-9]+) ([0-9]+) ([0-9]+)', text)
    require(match and int(match[2]) > 0 and int(match[3]) > 0, 'actual file device/inode/size required')
    dev = int(match[1], 16)
    return dict(device=[(dev >> 8) & 0xfff, (dev & 0xff) | ((dev >> 12) & 0xffffff00)], inode=int(match[2]), size=int(match[3]))


def bind_process(before, after, pid, descriptor, *, image_hashes):
    contract = load_contract(descriptor, image_hashes=image_hashes)
    cuts = [require_complete(before), require_complete(after)]
    require(cuts[0]['nonce'] != cuts[1]['nonce'] and cuts[0]['boot_id'] == cuts[1]['boot_id'] and
            all(cut['pid'] == pid for cut in cuts), 'two distinct same-boot exact-PID cuts required')
    require(cuts[0]['uptime_interval_ns'] and cuts[1]['uptime_interval_ns'] and
            cuts[0]['uptime_interval_ns'][0] <= cuts[1]['uptime_interval_ns'][0], 'process observation cuts regressed')
    actual = []
    for cut in cuts:
        process = cut['processes'][pid]
        if (process['classification'] != 'user' or process['uids'] != [contract['uid']] * 4 or process['exe'] != contract['exe'] or
                process['argv'] != contract['argv'] or process['attr'] != contract['context']):
            raise MappingGap('actual target PID does not match its init/passwd process role', cut)
        require(set(cut['libraries']) == set(contract['libraries']), 'exact required role DSO file queries missing')
        for i, remote in enumerate(cut['libraries']):
            direct = cut['queries']
            first = _file_identity(_text(direct[f'file_before_{i}']['hex']))
            last = _file_identity(_text(direct[f'file_after_{i}']['hex']))
            require(first == last, 'actual DSO file identity changed during process observation')
            expected_hash = contract['libraries'][remote]
            for phase in ('before', 'after'):
                require(_text(direct[f'hash_{phase}_{i}']['hex']) == expected_hash + '  ' + remote, 'actual guest DSO bytes differ from current image')
            mapped = [row for row in process['maps'] if row['path'] == remote]
            require(mapped and any('x' in row['permissions'] for row in mapped) and
                    all(not row['deleted'] and row['inode'] == first['inode'] and row['device'] == first['device'] for row in mapped),
                    'exact target mapped DSO/inode/device missing, replaced or deleted')
        actual.append(process)
    require(actual[0]['before']['start_ticks'] == actual[1]['after']['start_ticks'], 'target PID generation changed around actual operation')
    return dict(scope='same_boot_process_generation_and_actual_mapped_image_DSOs_ONLY', pid=pid, boot_id=cuts[0]['boot_id'],
                start_ticks=actual[0]['before']['start_ticks'], uid=contract['uid'], role=contract['role'], contract=descriptor,
                before_raw_sha256=cuts[0]['raw_sha256'], after_raw_sha256=cuts[1]['raw_sha256'],
                global_absence_proven=False, first_artifact_behavior_gate_passed=False, capabilityIdsClosed=0)


def bind_trace_process(before, after, trace_header, descriptor, *, image_hashes):
    """Bind the header's real processPid, never the separate root Dump client PID."""
    if descriptor is None:
        raise MappingGap('actual trace process role contract unavailable')
    require(type(trace_header) is dict and type(trace_header.get('processPid')) is int and trace_header['processPid'] > 0 and
            type(trace_header.get('traceEpochBootNs')) is int and type(trace_header.get('snapshotBootNs')) is int and
            0 < trace_header['traceEpochBootNs'] <= trace_header['snapshotBootNs'], 'actual parsed trace header required')
    require(type(descriptor) is dict and descriptor.get('role') == 'business', 'trace callback business DSO role required; provider PID is separate')
    result = bind_process(before, after, trace_header['processPid'], descriptor, image_hashes=image_hashes)
    cuts = [_reparse(before), _reparse(after)]
    require(cuts[0]['uptime_interval_ns'] and cuts[1]['uptime_interval_ns'] and
            cuts[0]['uptime_interval_ns'][0] <= trace_header['snapshotBootNs'] < cuts[1]['uptime_interval_ns'][1],
            'actual Dump clock is outside retained process observation cuts')
    result.update(trace_epoch_boot_ns=trace_header['traceEpochBootNs'], snapshot_boot_ns=trace_header['snapshotBootNs'],
                  ordering_scope='coarse actual proc/uptime bounds; owning driver must also retain before/Dump/after command ordering',
                  root_dump_client_pid_used_as_service_identity=False, wire_nonce_proven=False)
    return result
