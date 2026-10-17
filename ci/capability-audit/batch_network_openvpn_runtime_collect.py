#!/usr/bin/env python3
"""Root-only future collector on an existing acceptance VM; never builds/boots it.

No TLS peer or CONNECTED claim. Missing policy/API/worker observations fail.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import time
import zipfile

import batch_network_openvpn_runtime_project as project
import batch_apps_contact_picker_coordinator as shared
from check_m144_core_package import verified_profile_content
from enclosing_acceptance_guest import EnclosingAcceptanceGuest
from hdc_transport import failed

HERE = Path(__file__).resolve().parent
require, sha, checked, load, descriptor = project.require, project.sha, project.checked, project.load, project.descriptor
quote = shlex.quote


def profile(value, role, udid, module):
    require(role == 'system' and re.fullmatch('[a-fA-F0-9]{64}', udid) and
            module['app']['bundleName'] == project.BUNDLE and
            module['module']['requestPermissions'] == [{'name': project.PERMISSION}], 'exact own system VPN caller required')
    value['bundle-info'].update({'bundle-name': project.BUNDLE, 'apl': 'system_core', 'app-feature': 'hos_system_app'})
    value['debug-info']['device-ids'] = [udid]
    value['acls']['allowed-acls'] = [project.PERMISSION]
    value['permissions']['restricted-permissions'] = [project.PERMISSION]
    return value


def verify_profile(value, udid):
    require(value['bundle-info']['bundle-name'] == project.BUNDLE and
            value['bundle-info']['apl'] == 'system_core' and value['bundle-info']['app-feature'] == 'hos_system_app' and
            value['debug-info']['device-ids'] == [udid] and
            value['acls']['allowed-acls'] == [project.PERMISSION] and
            value['permissions']['restricted-permissions'] == [project.PERMISSION], 'actual signature profile differs')


def verify_signed_payload(unsigned_path, signed_path):
    with zipfile.ZipFile(unsigned_path) as unsigned, zipfile.ZipFile(signed_path) as signed:
        before, after = unsigned.namelist(), signed.namelist()
        require(len(before) == len(set(before)) and len(after) == len(set(after)) and
                '.pages.info' not in before and set(after) == set(before) | {'.pages.info'},
                'signed HAP members differ from the compiled caller')
        bitmap = signed.read('.pages.info')
        require(bitmap and len(bitmap) % 8 == 0 and
                all(unsigned.read(name) == signed.read(name) for name in before),
                'signed HAP payload or executable page bitmap changed')


# Current-source fact, independently exported by the root producer. This is not
# a host-kernel assumption; both supported product kernel sources agree.
KERNEL_PROCESS_CONTRACT = {
    'name': 'current-product-linux-sched-pf-kthread-v1', 'PF_KTHREAD': 0x00200000,
    'producer_sha256': 'f6f41151f6a432b91a2be30d81288571b112bdc76c5a39771686f0cdd9e2fbdf',
    'sources': {
        'kernel/linux/linux-5.10/include/linux/sched.h': 'eb02fc4e99e49685496289fe245af492b2612709f0233114e087f16304d5fca9',
        'kernel/linux/linux-6.6/include/linux/sched.h': 'c15bf201f1782aceb3ccda7f75ac8bc99c598efacaa20a71baeae723bd18e405'},
}
PROCESS_CONTRACT_ID = hashlib.sha256(json.dumps(KERNEL_PROCESS_CONTRACT, sort_keys=True).encode()).hexdigest()
HELPERS = ('/system/bin/qemu_openvpn', '/system/bin/qemu_openvpn_service', '/system/bin/qemu_openvpn_tun')


class SnapshotRace(ValueError):
    """A complete capture proved a generation change; retry the whole capture."""


def decode_hex(value, *, empty=False, nul=False):
    require(isinstance(value, str) and len(value) <= 8 * 1024 * 1024 and
            re.fullmatch(r'(?:[0-9a-f]{2})*', value) is not None and (empty or value), 'invalid/bounded raw hex required')
    raw = bytes.fromhex(value)
    if nul: require(raw and raw.endswith(b'\0'), 'complete NUL-terminated actual cmdline required')
    return raw


def argv_hex(value):
    raw = decode_hex(value, nul=True)
    args = raw[:-1].split(b'\0')
    require(args and args[0] and len(raw) <= 1024 * 1024, 'actual bounded nonempty argv0 required')
    return [arg.decode('utf-8') for arg in args]  # Empty final arguments remain observable.


def stat_hex(value, pid):
    text = decode_hex(value).decode('utf-8')
    require(text.endswith('\n') and text.count('\n') >= 1, 'complete raw stat required')
    parsed = project.proc_stat(text)
    fields = text[text.rfind(')') + 2:].split()
    require(parsed['pid'] == pid and len(fields) >= 20 and fields[6].isdigit() and
            parsed['start'].isdigit() and len(parsed['state']) == 1 and parsed['state'] in 'RSDZTWtXxKIP', 'stat identity/flags/generation malformed')
    parsed['flags'] = int(fields[6]); parsed['raw_hex'] = value
    return parsed


def _pid_list(value):
    lines = decode_hex(value).decode('ascii').splitlines()
    require(lines and all(re.fullmatch('[A-Za-z0-9_.-]+', line) for line in lines), 'successful complete /proc listing required')
    ids = [int(line) for line in lines if line.isdigit()]
    require(1 in ids and len(ids) == len(set(ids)) and all(0 < pid < 2**31 for pid in ids), 'complete unique init-containing PID enumeration required')
    return ids


def _status(value, pid):
    text = decode_hex(value).decode('utf-8'); rows = {}
    require(text.endswith('\n'), 'complete raw process status required')
    for line in text.splitlines():
        key, sep, val = line.partition(':')
        if sep and key in ('Uid', 'Pid', 'Name'):
            require(key not in rows, 'duplicate process status field'); rows[key] = val.strip()
    require(rows.get('Pid') == str(pid) and re.fullmatch(r'[0-9]+(?:[ \t]+[0-9]+){3}', rows.get('Uid', '')), 'actual status PID/four UID fields required')
    return text, tuple(map(int, rows['Uid'].split())), rows.get('Name', '')


def _missing(query, path):
    rc, data = query
    if rc not in (1, 2): return False
    text = decode_hex(data, empty=True).decode('utf-8')
    return path in text and ('No such file or directory' in text or 'No such process' in text) and not any(
        bad in text for bad in ('Permission denied', 'Operation not permitted', 'inaccessible', 'not found', 'Input/output error'))


# The public renderer always fixes /proc and the production private root. The
# internal renderer's paths permit executed POSIX fixture tests without guest IO.
def _snapshot_script(nonce, boot_id, *, mode='vpn', uid=None, bundle=None, library=None,
                     proc_root='/proc', private_root=project.ROOT):
    require(re.fullmatch('[a-f0-9]{32}', nonce or '') and re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', boot_id or ''), 'fresh scan nonce/boot required')
    require(mode in ('vpn', 'uid', 'maps') and (uid is None or type(uid) is int and uid > 10000), 'bounded process scan mode/UID required')
    require(mode != 'uid' or re.fullmatch('[A-Za-z0-9_.]+', bundle or ''), 'exact ordinary bundle required')
    require(mode != 'maps' or library in ('/system/lib/libwallpaper_service.z.so', '/system/lib64/libwallpaper_service.z.so'), 'exact packaged Wallpaper library required')
    uid_text = '-' if uid is None else str(uid); bundle_text = '-' if bundle is None else bundle.encode().hex()
    preamble = 'task_scan_proc=' + quote(proc_root) + '; task_scan_root=' + quote(private_root) + '; task_scan_mode=' + mode + '; task_scan_uid=' + uid_text + '; task_scan_bundle=' + quote(bundle or '') + '; task_scan_library=' + quote(library or '') + ';\n'
    preamble += 'task_scan_boot=$(cat "$task_scan_proc/sys/kernel/random/boot_id") || exit 1; test "$task_scan_boot" = ' + quote(boot_id) + ' || exit 1;\n'
    preamble += "printf '%s\\n' " + quote('|'.join(('BEGIN','PROCESS_V2',nonce,boot_id,mode,uid_text,bundle_text,PROCESS_CONTRACT_ID))) + ';\n'
    script = r'''LC_ALL=C; export LC_ALL
IFS='
	 '
set -f
for task_scan_tool in od readlink sed stat ls; do
  command -v "$task_scan_tool" >/dev/null 2>&1 || exit 1
done
task_scan_q=0; task_scan_n=0; task_scan_r=0
# Byte-preserving POSIX printf conversion, only for short command text/listings.
task_scan_texthex() {
  task_scan_text_od=$(od -An -v -tx1 <<TASK_SCAN_TEXT_BYTES
$1
TASK_SCAN_TEXT_BYTES
  ) || return 1
  task_scan_text_result=
  for task_scan_byte in $task_scan_text_od; do
    case "$task_scan_byte" in [0123456789abcdef][0123456789abcdef]) ;; *) return 1;; esac
    task_scan_text_result=$task_scan_text_result$task_scan_byte
  done
  case "$task_scan_text_result" in *0a) task_scan_text_result=${task_scan_text_result%0a};; *) return 1;; esac
}
task_scan_od() {
  task_scan_data=$(od -An -v -tx1 "$1" 2>&1); task_scan_rc=$?
  if test "$task_scan_rc" -eq 0; then
    task_scan_hex=
    for task_scan_byte in $task_scan_data; do
      case "$task_scan_byte" in [0123456789abcdef][0123456789abcdef]) ;; *) exit 1;; esac
      task_scan_hex=$task_scan_hex$task_scan_byte
    done
  else task_scan_texthex "$task_scan_data" || exit 1; task_scan_hex=$task_scan_text_result; fi
}
task_scan_qod() {
  task_scan_od "$3"
  printf 'Q|%s|%s|%s|%s\n' "$1" "$2" "$task_scan_rc" "$task_scan_hex"
  task_scan_q=$((task_scan_q + 1)); task_scan_pq=$((task_scan_pq + 1))
}
task_scan_qtext() {
  task_scan_texthex "$4" || exit 1
  printf 'Q|%s|%s|%s|%s\n' "$1" "$2" "$3" "$task_scan_text_result"
  task_scan_q=$((task_scan_q + 1)); task_scan_pq=$((task_scan_pq + 1))
}
task_scan_d() {
  task_scan_texthex "$3" || exit 1
  printf 'D|%s|%s|%s\n' "$1" "$2" "$task_scan_text_result"
}
task_scan_initial=$(ls -1 "$task_scan_proc" 2>&1); task_scan_rc=$?
test "$task_scan_rc" -eq 0 || exit 1
task_scan_texthex "$task_scan_initial" || exit 1
printf 'LIST|start|%s\n' "$task_scan_text_result"
if test "$task_scan_mode" = maps; then
  test -f "$task_scan_library" && test ! -L "$task_scan_library" || exit 1
  task_scan_value=$(stat -c '%d %i %s' "$task_scan_library" 2>&1); task_scan_rc=$?; task_scan_d file-before-stat "$task_scan_rc" "$task_scan_value"
  task_scan_value=$(sha256sum "$task_scan_library" 2>&1); task_scan_rc=$?; task_scan_d file-before-hash "$task_scan_rc" "$task_scan_value"
fi
for task_scan_pid in $task_scan_initial; do
  case "$task_scan_pid" in ''|*[!0-9]*) continue;; esac
  task_scan_p=$task_scan_proc/$task_scan_pid; task_scan_pq=0; task_scan_n=$((task_scan_n + 1))
  printf 'PID|%s\n' "$task_scan_pid"
  task_scan_qod "$task_scan_pid" stat "$task_scan_p/stat"
  task_scan_exe=$(readlink "$task_scan_p/exe" 2>&1); task_scan_erc=$?
  task_scan_qtext "$task_scan_pid" exe "$task_scan_erc" "$task_scan_exe"
  if test "$task_scan_erc" -ne 0; then
    # readlink may fail silently. stat -L supplies independent target errno;
    # an empty failed readlink alone never proves absence or a kernel thread.
    task_scan_target=$(stat -L -c '%F' "$task_scan_p/exe" 2>&1); task_scan_trc=$?
    task_scan_qtext "$task_scan_pid" exe_target "$task_scan_trc" "$task_scan_target"
  fi
  task_scan_selected=no
  if test "$task_scan_erc" -eq 0; then
    case "$task_scan_exe" in /system/bin/qemu_openvpn|/system/bin/qemu_openvpn_service|/system/bin/qemu_openvpn_tun) task_scan_selected=yes;; esac
    if test "$task_scan_mode" = uid; then
      task_scan_qod "$task_scan_pid" status "$task_scan_p/status"
      task_scan_qod "$task_scan_pid" cmdline "$task_scan_p/cmdline"
      task_scan_cmdhex=$task_scan_hex
      task_scan_hint=$(sed -n 's/^Uid:[[:space:]]*//p' "$task_scan_p/status" 2>&1); task_scan_hrc=$?
      task_scan_qtext "$task_scan_pid" uid_hint "$task_scan_hrc" "$task_scan_hint"
      task_scan_selected=no
      if test "$task_scan_hrc" -eq 0; then
        for task_scan_id in $task_scan_hint; do test "$task_scan_id" != "$task_scan_uid" || task_scan_selected=yes; done
      fi
      case "$task_scan_cmdhex" in ''|__BUNDLE_HEX__00*|__BUNDLE_HEX__3a*) task_scan_selected=yes;; esac
    elif test "$task_scan_mode" = maps; then
      task_scan_selected=no
      task_scan_match=$(grep -F -q 'libwallpaper_service.z.so' "$task_scan_p/maps" 2>&1); task_scan_mrc=$?
      task_scan_qtext "$task_scan_pid" maps_match "$task_scan_mrc" "$task_scan_match"
      test "$task_scan_mrc" -ne 0 || task_scan_selected=yes
    fi
    if test "$task_scan_selected" = yes; then
      if test "$task_scan_mode" != uid; then
        task_scan_qod "$task_scan_pid" status "$task_scan_p/status"
        task_scan_qod "$task_scan_pid" cmdline "$task_scan_p/cmdline"
      fi
      if test "$task_scan_mode" = maps; then task_scan_qod "$task_scan_pid" maps "$task_scan_p/maps"; fi
      task_scan_qod "$task_scan_pid" stat_after "$task_scan_p/stat"
    fi
  elif test "$task_scan_mode" = uid; then
    task_scan_qod "$task_scan_pid" status "$task_scan_p/status"
  fi
  printf 'TERMINAL|%s|%s\n' "$task_scan_pid" "$task_scan_pq"
done
task_scan_final=$(ls -1 "$task_scan_proc" 2>&1); task_scan_rc=$?
test "$task_scan_rc" -eq 0 || exit 1
task_scan_texthex "$task_scan_final" || exit 1
printf 'LIST|end|%s\n' "$task_scan_text_result"
if test "$task_scan_mode" = vpn; then
  task_scan_parent=${task_scan_root%/*}; task_scan_ancestor=${task_scan_parent%/*}
  test ! -L "$task_scan_parent" && test ! -L "$task_scan_root" || exit 1
  task_scan_value=$(ls -a1 "$task_scan_ancestor" 2>&1); task_scan_rc=$?; task_scan_d ancestor-list "$task_scan_rc" "$task_scan_value"
  task_scan_value=$(stat -c '%u:%g:%a:%F:%h:%d:%i' "$task_scan_parent" 2>&1); task_scan_prc=$?; task_scan_d parent-stat "$task_scan_prc" "$task_scan_value"
  if test "$task_scan_prc" -eq 0; then
    task_scan_value=$(ls -a1 "$task_scan_parent" 2>&1); task_scan_rc=$?; task_scan_d parent-list "$task_scan_rc" "$task_scan_value"
  fi
  task_scan_value=$(stat -c '%u:%g:%a:%F:%h:%d:%i' "$task_scan_root" 2>&1); task_scan_rrc=$?; task_scan_d root-stat "$task_scan_rrc" "$task_scan_value"
  if test "$task_scan_rrc" -eq 0; then
    task_scan_value=$(ls -a1 "$task_scan_root" 2>&1); task_scan_rc=$?; task_scan_d root-list "$task_scan_rc" "$task_scan_value"
    set +f
    for task_scan_path in "$task_scan_root"/* "$task_scan_root"/.[!.]* "$task_scan_root"/..?*; do
      if test ! -e "$task_scan_path" && test ! -L "$task_scan_path"; then
        case "$task_scan_path" in "$task_scan_root/*"|"$task_scan_root/.[!.]*"|"$task_scan_root/..?*") continue;; esac
      fi
      test ! -L "$task_scan_path" || exit 1
      task_scan_name=${task_scan_path##*/}
      task_scan_texthex "$task_scan_name" || exit 1; task_scan_namehex=$task_scan_text_result
      task_scan_value=$(stat -c '%u:%g:%a:%F:%h:%d:%i' "$task_scan_path" 2>&1); task_scan_rc=$?
      task_scan_texthex "$task_scan_value" || exit 1
      printf 'R|%s|%s|%s\n' "$task_scan_namehex" "$task_scan_rc" "$task_scan_text_result"
      task_scan_r=$((task_scan_r + 1))
    done
    set -f
  fi
elif test "$task_scan_mode" = maps; then
  task_scan_value=$(stat -c '%d %i %s' "$task_scan_library" 2>&1); task_scan_rc=$?; task_scan_d file-after-stat "$task_scan_rc" "$task_scan_value"
  task_scan_value=$(sha256sum "$task_scan_library" 2>&1); task_scan_rc=$?; task_scan_d file-after-hash "$task_scan_rc" "$task_scan_value"
fi
'''
    script = script.replace('__BUNDLE_HEX__', (bundle or 'unused').encode().hex())
    tools = '' if mode != 'maps' else 'command -v grep >/dev/null 2>&1 && command -v sha256sum >/dev/null 2>&1 || exit 1;\n'
    return preamble + tools + script + "printf 'END|%s|%s|%s|%s\\n' " + quote(nonce) + ' "$task_scan_n" "$task_scan_q" "$task_scan_r"\n'


def snapshot_script(nonce, boot_id, *, mode='vpn', uid=None, bundle=None, library=None):
    return _snapshot_script(nonce, boot_id, mode=mode, uid=uid, bundle=bundle, library=library)


def parse_snapshot(raw, nonce=None, boot_id=None, *, mode='vpn', uid=None, bundle=None, library=None):
    require(isinstance(nonce,str) and re.fullmatch('[a-f0-9]{32}',nonce) and isinstance(boot_id,str) and re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',boot_id), 'expected scan nonce and boot required; legacy partial snapshots rejected')
    require(mode in ('vpn','uid','maps') and (uid is None or type(uid) is int and uid>10000), 'exact scan mode/UID required')
    require(mode!='uid' or isinstance(bundle,str) and re.fullmatch('[A-Za-z0-9_.]+',bundle), 'exact UID scan bundle required')
    require(mode!='maps' or library in ('/system/lib/libwallpaper_service.z.so','/system/lib64/libwallpaper_service.z.so'), 'exact native library required')
    require(isinstance(raw, str) and raw.endswith('\n') and len(raw.encode()) <= 16 * 1024 * 1024, 'complete bounded framed process capture required')
    lines = raw.splitlines(); expected = '|'.join(('BEGIN','PROCESS_V2',nonce,boot_id,mode,'-' if uid is None else str(uid),'-' if bundle is None else bundle.encode().hex(),PROCESS_CONTRACT_ID))
    require(lines and lines[0] == expected, 'wrong scan framing/nonce/boot/kernel contract')
    tail = lines[-1].split('|'); require(len(tail) == 5 and tail[:2] == ['END',nonce] and all(value.isdigit() for value in tail[2:]), 'missing/malformed scan END')
    records, listings, direct, entries = {}, {}, {}, []; current = None; qcount = 0
    for line in lines[1:-1]:
        parts = line.split('|'); tag = parts[0]
        if tag == 'LIST':
            require(current is None and len(parts) == 3 and parts[1] in ('start','end') and parts[1] not in listings, 'duplicate/misplaced PID listing')
            listings[parts[1]] = _pid_list(parts[2])
        elif tag == 'PID':
            require(current is None and len(parts) == 2 and parts[1].isdigit() and 'start' in listings and 'end' not in listings, 'invalid PID begin')
            current = int(parts[1]); require(current not in records and current in listings['start'], 'duplicate/unlisted PID')
            records[current] = {}
        elif tag == 'Q':
            require(current is not None and len(parts) == 5 and parts[1] == str(current) and re.fullmatch('[a-z_]+',parts[2]) and parts[3].isdigit() and 0 <= int(parts[3]) <= 255, 'invalid process query record')
            require(parts[2] not in records[current], 'duplicate process query')
            decode_hex(parts[4], empty=True); records[current][parts[2]] = (int(parts[3]),parts[4]); qcount += 1
        elif tag == 'TERMINAL':
            require(current is not None and len(parts) == 3 and parts[1] == str(current) and parts[2] == str(len(records[current])), 'incomplete/duplicate PID terminal')
            current = None
        elif tag == 'D':
            require(current is None and len(parts) == 4 and parts[1] not in direct and parts[2].isdigit() and 0 <= int(parts[2]) <= 255, 'invalid independent metadata query')
            decode_hex(parts[3], empty=True); direct[parts[1]] = (int(parts[2]),parts[3])
        elif tag == 'R':
            require(current is None and mode == 'vpn' and len(parts) == 4 and parts[2].isdigit(), 'invalid private root record')
            entries.append((decode_hex(parts[1]).decode('utf-8'),int(parts[2]),parts[3])); decode_hex(parts[3], empty=True)
        else: raise ValueError('unknown/control injection in process capture')
    require(current is None and set(listings) == {'start','end'} and set(records) == set(listings['start']) and
            list(map(int,tail[2:])) == [len(records),qcount,len(entries)], 'partial PID prefix/count/terminal capture rejected')
    stats, processes, gone, classifications = {}, {}, {}, {}
    for pid, queries in records.items():
        require({'stat','exe'} <= queries.keys(), 'missing mandatory stat/exe query')
        allowed = {'stat','exe','exe_target','status','cmdline','stat_after','uid_hint','maps_match','maps'}
        require(set(queries) <= allowed and list(queries)[:2]==['stat','exe'], 'unknown/misordered process query opcode')
        order = ['stat','exe','exe_target'] + (['maps_match','status','cmdline','maps','stat_after'] if mode=='maps' else ['status','cmdline','uid_hint','stat_after'])
        require([order.index(op) for op in queries]==sorted(order.index(op) for op in queries), 'process queries out of order')
        require(('exe_target' in queries) == bool(queries['exe'][0]), 'failed readlink requires independent target stat; live exe must not add it')
        exe_missing = bool(queries['exe'][0]) and queries['exe'][0] in (1,2) and (not queries['exe'][1] or
            _missing(queries['exe'],f'/proc/{pid}/exe')) and _missing(queries['exe_target'],f'/proc/{pid}/exe')
        first = stat_hex(queries['stat'][1],pid) if queries['stat'][0] == 0 else None
        kernel = first is not None and bool(first['flags'] & KERNEL_PROCESS_CONTRACT['PF_KTHREAD'])
        zombie = first is not None and first['state'] in ('Z','X','x')
        bad = {op:row for op,row in queries.items() if row[0] and not(op == 'maps_match' and row[0] == 1 and not row[1])}
        paths = {'stat':'stat','stat_after':'stat','exe':'exe','exe_target':'exe','status':'status','cmdline':'cmdline','uid_hint':'status','maps_match':'maps','maps':'maps'}
        if (kernel or zombie) and exe_missing:
            bad.pop('exe'); bad.pop('exe_target')  # Source-proven non-executable task with independent missing-target proof.
        if bad:
            require(all(exe_missing if op=='exe' else _missing(row,f'/proc/{pid}/'+paths[op]) for op,row in bad.items()), 'process query failed; cannot classify as empty/gone')
            if pid in listings['end']: raise SnapshotRace('PID still present after missing process read; fresh complete scan required')
            gone[pid] = {'stat':first,'failed_queries':bad,'queries':queries}; classifications[pid] = 'gone'; continue
        if kernel or zombie:
            if queries['exe'][0] == 0: raise SnapshotRace('non-executable task changed while querying exe')
            require(set(queries)==({'stat','exe','exe_target','status'} if mode=='uid' else {'stat','exe','exe_target'}), 'unexpected non-executable task queries')
            require(exe_missing, 'kernel/zombie exe query is not proved missing')
            if mode == 'uid':
                require('status' in queries, 'UID scan requires status even for zombie/no-exe tasks')
                status, ids, name = _status(queries['status'][1],pid)
                if zombie and uid is None and any(value > 10000 for value in ids):
                    raise SnapshotRace('ordinary zombie cannot be excluded by bundle without known UID')
                if zombie and uid is not None and uid in ids:
                    processes[pid] = dict(first,exe='',uid=ids[0],argv=[],status=status,name=name)
            stats[pid] = first; classifications[pid] = 'kernel' if kernel else 'zombie'; continue
        require(first is not None, 'missing live stat')
        if 'stat_after' in queries:
            observed_after = stat_hex(queries['stat_after'][1],pid)
            if observed_after['start'] != first['start']: raise SnapshotRace('selected PID generation changed')
            if observed_after['state'] in ('Z','X','x'):
                if mode == 'uid':
                    status, ids, name = _status(queries['status'][1],pid)
                    if uid is None and any(value > 10000 for value in ids): raise SnapshotRace('ordinary zombie requires known UID')
                    if uid is not None and uid in ids: processes[pid]=dict(observed_after,exe='',uid=ids[0],argv=[],status=status,name=name)
                stats[pid] = observed_after; classifications[pid] = 'zombie'; continue
        exe = decode_hex(queries['exe'][1]).decode('utf-8')
        selected = exe in HELPERS if mode == 'vpn' else False
        actual_uid, argv, status, name = None, None, None, None
        if mode == 'uid' or selected or mode == 'maps' and queries.get('maps_match',(None,None))[0] == 0:
            require({'status','cmdline'} <= queries.keys(), 'missing actual status/cmdline')
            status, ids, name = _status(queries['status'][1],pid); actual_uid = ids[0]; argv = argv_hex(queries['cmdline'][1])
            if mode == 'uid':
                require('uid_hint' in queries and decode_hex(queries['uid_hint'][1]).decode().split() == list(map(str,ids)), 'UID hint differs from captured status')
                selected = uid in ids if uid is not None else False
                selected = selected or argv[0] == bundle or argv[0].startswith(bundle + ':')
            elif mode == 'maps': selected = True
        expected_queries = {'stat','exe'}
        if mode == 'uid': expected_queries |= {'status','cmdline','uid_hint'}
        elif mode == 'maps': expected_queries.add('maps_match')
        if selected: expected_queries |= {'status','cmdline','stat_after'}
        if mode == 'maps' and selected: expected_queries.add('maps')
        require(set(queries) == expected_queries, 'missing/unexpected query for process classification')
        if mode == 'maps':
            require('maps_match' in queries and queries['maps_match'][0] in (0,1), 'missing valid maps query')
        if selected:
            require('stat_after' in queries, 'selected process lacks generation recheck')
            after = stat_hex(queries['stat_after'][1],pid)
            if after['start'] != first['start']: raise SnapshotRace('selected PID generation changed')
            if after['ppid'] != first['ppid'] or after['pgrp'] != first['pgrp']: raise SnapshotRace('selected ancestry/group changed during observation')
            first = after
            row = dict(first,exe=exe,uid=actual_uid,argv=argv,status=status,name=name)
            if mode == 'maps': require('maps' in queries, 'actual selected maps missing'); row['maps'] = decode_hex(queries['maps'][1]).decode('utf-8')
            processes[pid] = row
        stats[pid] = first; classifications[pid] = 'selected' if selected else 'other'
    require(1 in stats and stats[1]['ppid'] == 0, 'actual live init stat required')
    def text(name):
        require(name in direct and direct[name][0] == 0, 'independent metadata query failed: '+name)
        return decode_hex(direct[name][1], empty=True).decode('utf-8')
    result = dict(stats=stats,processes=processes,entries=[],gone=gone,classifications=classifications,
                  nonce=nonce,boot_id=boot_id,mode=mode,kernel_contract=KERNEL_PROCESS_CONTRACT,metadata={},queries=records)
    if mode == 'vpn':
        ancestor = text('ancestor-list').splitlines(); parent = str(Path(project.ROOT).parent)
        parent_row = direct.get('parent-stat'); root_row = direct.get('root-stat')
        require(parent_row is not None and root_row is not None, 'private root query missing')
        if parent_row[0]:
            require(_missing(parent_row,parent) and Path(parent).name not in ancestor and _missing(root_row,project.ROOT) and not entries and set(direct)=={'ancestor-list','parent-stat','root-stat'}, 'private parent read failure is not proved absence')
        else:
            parent_fields=decode_hex(parent_row[1]).decode().split(':')
            require(len(parent_fields)==7 and parent_fields[3]=='directory' and all(parent_fields[i].isdigit() for i in (0,1,4,5,6)) and re.fullmatch('[0-7]{1,4}',parent_fields[2]), 'private parent metadata is incomplete/not directory')
            names = text('parent-list').splitlines()
            if root_row[0]: require(_missing(root_row,project.ROOT) and Path(project.ROOT).name not in names and not entries and set(direct)=={'ancestor-list','parent-stat','parent-list','root-stat'}, 'private root query error is not absence')
            else:
                root_fields=decode_hex(root_row[1]).decode().split(':')
                require(len(root_fields)==7 and root_fields[3]=='directory' and all(root_fields[i].isdigit() for i in (0,1,4,5,6)) and re.fullmatch('[0-7]{1,4}',root_fields[2]) and set(direct)=={'ancestor-list','parent-stat','parent-list','root-stat','root-list'}, 'private root metadata is incomplete/not directory')
                names = [item for item in text('root-list').splitlines() if item not in ('.','..')]
                require(len(names) == len(set(names)) and set(names) == {row[0] for row in entries} and len(entries)==len(names), 'incomplete/duplicate private root enumeration')
                for name,rc,data in entries:
                    require(re.fullmatch('[A-Za-z0-9_.-]+',name) and name not in ('.','..'), 'unsafe private root name')
                    if rc:
                        if _missing((rc,data),project.ROOT+'/'+name): raise SnapshotRace('private root entry disappeared; retry complete scan')
                        raise ValueError('private entry stat query failed')
                    meta = decode_hex(data).decode('utf-8'); fields = meta.split(':')
                    require(len(fields)==7 and all(fields[i].isdigit() for i in (0,1,4,5,6)) and re.fullmatch('[0-7]{1,4}',fields[2]) and fields[3] in ('directory','regular file','regular empty file'), 'complete non-alias private entry metadata required')
                    result['entries'].append(name+'|'+':'.join(fields[:4])); result['metadata'][name]=meta
        require(set(direct) <= {'ancestor-list','parent-stat','parent-list','root-stat','root-list'}, 'unexpected root query')
    elif mode == 'maps':
        require(set(direct)=={'file-before-stat','file-before-hash','file-after-stat','file-after-hash'} and not entries, 'complete native file queries required')
        result['metadata']={name:text(name) for name in direct}
    else: require(not direct and not entries, 'unexpected UID scan metadata')
    return result


def capture_snapshot(shell, label, boot_id, *, mode='vpn', uid=None, bundle=None, library=None, attempts=3):
    require(type(attempts) is int and 1 <= attempts <= 3, 'bounded complete scan retry count required')
    for attempt in range(attempts):
        nonce = secrets.token_hex(16)
        raw = shell(snapshot_script(nonce,boot_id,mode=mode,uid=uid,bundle=bundle,library=library),label+'-'+str(attempt))
        try: return raw,parse_snapshot(raw,nonce,boot_id,mode=mode,uid=uid,bundle=bundle,library=library)
        except SnapshotRace:
            if attempt+1 == attempts: raise
            time.sleep(.05)
    raise AssertionError('unreachable')


def claimed(snapshot, profile_sha):
    clients = [row for row in snapshot['processes'].values() if row['exe'] == '/system/bin/qemu_openvpn']
    require(len(clients) == 1, 'one real OpenVPN exec child required; no simulated claim')
    client = clients[0]; workers = snapshot['processes']; argv = client['argv']
    require(client['uid'] == 1098 and argv.count('--config') == 1, 'real owned client identity required')
    require(argv.index('--config') + 1 < len(argv), 'real config argv is truncated')
    config = argv[argv.index('--config') + 1]
    require(re.fullmatch(re.escape(project.ROOT) + r'/session-[A-Za-z0-9]{6}/client\.ovpn', config), 'exact private config required')
    marks = [argv[i+2] for i in range(len(argv)-2) if argv[i:i+2] == ['--setenv', 'OHOS_OPENVPN_SESSION']]
    require(len(marks) == 1 and re.fullmatch('[a-f0-9]{32}', marks[0]), 'real generation argv required')
    worker = workers.get(client['ppid']); require(worker is not None, 'actual worker parent missing')
    broker = workers.get(worker['ppid']); require(broker is not None, 'actual broker parent missing')
    require(worker['exe'] == broker['exe'] == '/system/bin/qemu_openvpn_service' and
            worker['uid'] == broker['uid'] == 1098 and worker['pgrp'] == worker['pid'] and
            client['pgrp'] == worker['pid'] and broker['ppid'] == 1, 'real init/broker/worker/group ancestry differs')
    require(len([e for e in snapshot['entries'] if e.startswith('session-')]) == 1, 'foreign or extra session present')
    return {'client': client, 'worker': worker, 'broker': broker, 'generation': marks[0],
            'directory': str(Path(config).parent), 'config': config, 'profile_sha256': profile_sha,
            'claim_proof': 'actual_client_exec_after_successful_production_NotifyConnectStage_claim_NOT_direct_claim_telemetry'}


def journal(raw, run, boot, uid, token):
    require(0 < len(raw.encode()) < 1048576 and raw.endswith('\n'), 'complete bounded app journal required')
    rows = [json.loads(line, object_pairs_hook=shared.unique) for line in raw.splitlines()]
    for index, row in enumerate(rows, 1):
        require(isinstance(row, dict) and set(row) == {'schema_version', 'run_id', 'boot_id', 'operation_id', 'action',
                'sequence', 'uid', 'pid', 'token_id', 'event', 'code', 'value'} and
                all(type(row[key]) is int for key in ('schema_version', 'sequence', 'uid', 'pid', 'token_id', 'code')) and
                re.fullmatch('[a-f0-9]{32}', row['operation_id']) and
                row['schema_version'] == 1 and row['sequence'] == index and row['run_id'] == run and
                row['boot_id'] == boot and row['uid'] == uid and row['token_id'] == token and row['pid'] > 1 and
                row['action'] in ('setup', 'destroy', 'inspect') and
                row['event'] in ('begin', 'permission', 'resolved', 'rejected', 'getters', 'getter-error', 'complete'),
                'foreign/reordered/malformed journal')
        require(row['event'] != 'getter-error', 'public getters failed')
        if row['event'] == 'permission': require(type(row['code']) is int and row['code'] == 0, 'actual MANAGE_VPN denied')
        if row['event'] == 'getters':
            require(json.loads(row['value']) == {'config_undefined': True, 'apps': []}, 'unexpected CONNECTED or foreign VPN')
    require(len({row['pid'] for row in rows}) == 1, 'caller restarted and lost its owned connection')
    return rows


class Collector:
    def __init__(self, args):
        self.args = args; self.output = args.output.resolve(); self.output.mkdir(parents=True, exist_ok=False)
        self.output.chmod(0o700)
        self.report = dict(schema_version=1, status='fail', scope=project.SCOPE, commands=[], phases=[], failures=[],
            cleanup_verified=False, first_artifact_behavior_gate_passed=False,
            gaps=['No observation of old-PGID signal delivery or forced PID reuse', 'No CONNECTED/TLS/TUN/data-plane proof',
                  'Single system owner only; no second-owner isolation proof', 'No real callback event stream coverage'])
        self.guest = None; self.install_attempted = False; self.installed = False
        self.fault = None; self.identity = None; self.started = False
        try:
            self.spec = load(args.inputs); self.data = project.binding(self.spec)
            self.report['inputs'] = descriptor(args.inputs); self.report['source'] = self.data
        except (ValueError, OSError, KeyError, TypeError) as error:
            self.report['failures'].append('input binding: ' + str(error)); raise
        finally: self.save()

    def save(self):
        if self.guest: self.report['guest'] = self.guest.report
        project.write(self.output / 'evidence.json', self.report)

    def command(self, argv, label):
        argv = list(map(str, argv)); self.guest.healthy()
        path = self.output / (str(len(self.report['commands'])).zfill(3) + '-' + label + '.log')
        try: result = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired as error:
            def text(value): return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            path.write_text(text(error.stdout) + text(error.stderr))
            self.report['commands'].append({'argv': argv, 'exit_code': None, 'timed_out': True, 'raw': descriptor(path)})
            self.save(); raise ValueError('real command timed out; partial output preserved: ' + label) from error
        path.write_text(result.stdout + result.stderr)
        self.report['commands'].append({'argv': argv, 'exit_code': result.returncode, 'raw': descriptor(path)}); self.save()
        require(result.returncode == 0 and not failed(result.stdout + result.stderr), 'real command failed: ' + label)
        return result.stdout

    def shell(self, value, label):
        try:
            require(self.guest.shell('cat /proc/sys/kernel/random/boot_id', label + '-boot').strip() ==
                    self.guest.env['boot_id'], 'owned guest kernel boot changed')
            return self.guest.shell(value, label)
        finally: self.save()

    def snapshot(self, label): return capture_snapshot(self.shell,label,self.guest.env['boot_id'])[1]

    def phase(self, action, expected='resolved'):
        operation = secrets.token_hex(16)
        request = dict(run_id=self.data['run_id'], boot_id=self.guest.env['boot_id'], operation_id=operation, action=action)
        launched = self.shell('aa start -a EntryAbility -b ' + project.BUNDLE + ' --ps request ' + quote(json.dumps(request)), 'launch-' + action)
        require('start ability successfully' in launched.lower(), 'actual QA Ability launch failed')
        deadline = time.monotonic() + 20
        while True:
            raw = self.shell('if test -f ' + quote(self.remote) + '; then cat ' + quote(self.remote) + '; fi', 'journal-' + action)
            if raw:
                rows = journal(raw, self.data['run_id'], self.guest.env['boot_id'], self.identity['uid'], self.identity['token'])
                current = [row for row in rows if row['operation_id'] == operation]
                if current and current[-1]['event'] == 'complete': break
            require(time.monotonic() < deadline, 'actual public API did not complete'); time.sleep(0.25)
        require([row['event'] for row in current] == ['begin', 'permission', expected, 'getters', 'complete'],
                'actual API outcome differs: ' + action)
        require(all(row['action'] == action for row in current), 'journal action differs from actual request')
        if expected == 'rejected': require(current[2]['code'] == 2200003, 'cleanup must fail with actual internal/backend error')
        self.report['phases'].append({'request': request, 'outcome': current[2], 'journal_command': len(self.guest.report['commands']) - 1})
        self.save(); return current

    def install(self):
        require(project.BUNDLE not in self.shell('bm dump -a', 'BMS-before'), 'fresh own QA bundle must be absent')
        dist, jar, _ = shared.signer_inputs(self.args.signer_dist, self.args.jar)
        signed = self.output / 'signed.hap'
        self.command([sys.executable, Path(__file__), 'sign', '--unsigned', checked(self.spec['unsigned_hap']),
            '--signer-dist', dist, '--jar', jar, '--udid', self.guest.udid, '--output', signed], 'sign-system-caller')
        verify_signed_payload(checked(self.spec['unsigned_hap']), signed)
        chain, embedded = self.output / 'chain.cer', self.output / 'embedded.p7b'
        log = self.command(['java', '-jar', jar, 'verify-app', '-inFile', signed, '-outCertChain', chain, '-outProfile', embedded], 'verify-app')
        require(all(v in log for v in ('verify codesign success', 'Digest verify result: true', 'verify permission sign success', 'verify-app success')), 'signature verify markers missing')
        shared.application_leaf(log)
        # Reuse fixed signer inputs and independently verify CMS with its fixed
        # leaf; do not weaken the shared ordinary/system_basic verifier.
        certs = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', (dist / 'OpenHarmonyProfileDebug.pem').read_text(), re.S)
        require(len(certs) == 3, 'fixed profile certificate chain differs')
        leaf = self.output / 'profile-leaf.pem'; leaf.write_text(certs[-1] + '\n')
        decoded = self.output / 'profile.json'
        self.command(['openssl', 'cms', '-verify', '-inform', 'DER', '-in', embedded, '-nointern', '-certfile', leaf, '-noverify', '-out', decoded], 'fixed-profile-CMS')
        verify_profile(verified_profile_content(load(decoded)), self.guest.udid)
        self.report['signed_hap'] = descriptor(signed)
        self.install_attempted = True
        reply = self.command([self.args.hdc, '-t', self.guest.target, 'install', signed], 'install')
        require('success' in reply.lower(), 'actual BMS install failed')
        self.installed = True
        raw = self.shell('bm dump -n ' + project.BUNDLE, 'BMS-installed')
        bms = json.JSONDecoder().raw_decode(raw[raw.find('{'):])[0]; app = bms['applicationInfo']
        require(app.get('isSystemApp') is True and app.get('appPrivilegeLevel') == 'system_core' and
                app['uid'] // 200000 == 100 and app['accessTokenId'] > 0, 'actual system UID/token/APL required')
        self.identity = {'uid': app['uid'], 'token': app['accessTokenId']}; self.report['identity'] = self.identity
        paths = {r['hapPath'] for r in shared.verifier.objects(bms) if isinstance(r.get('hapPath'), str) and r['hapPath'].startswith('/data/app/')}
        require(len(paths) == 1, 'one actual installed HAP path required')
        remote_hap = next(iter(paths))
        require(self.shell('sha256sum ' + quote(remote_hap), 'installed-HAP-hash').split() == [sha(signed), remote_hap], 'installed HAP differs')
        self.remote = '/data/app/el2/100/base/' + project.BUNDLE + '/files/openvpn-' + self.data['run_id'] + '.jsonl'

    def no_group(self, snapshot, old):
        require(not any(row['pgrp'] == old['worker']['pid'] for row in snapshot['stats'].values()), 'actual old process group remains')

    def wait_claim(self, label):
        deadline = time.monotonic() + 8
        while True:
            snapshot = self.snapshot(label)  # Query/decoder errors are never claim-not-ready.
            try:
                result = claimed(snapshot, self.data['profile_sha256'])
                break
            except ValueError as error:
                require(time.monotonic() < deadline, 'no actual worker/client/claim evidence: ' + str(error)); time.sleep(0.25)
        self.shell('test ! -L {p} && test "$(stat -c \'%u:%a\' {p})" = 1098:700'.format(p=quote(result['directory'])), label + '-directory')
        require(self.shell('sha256sum ' + quote(result['config']), label + '-profile-hash').split() ==
                [self.data['profile_sha256'], result['config']], 'worker config differs from actual owned input')
        return result

    def remove_fault(self):
        if not self.fault: return
        marker = 'openvpn-owned-' + self.data['run_id']
        script = ('if test ! -e {p} && test ! -L {p}; then :; else '
                  'test -f {p} && test ! -L {p} && test "$(stat -c \'%u:%a:%h\' {p})" = 0:600:1 && '
                  'test "$(cat {p})" = {m} && rm {p}; fi').format(p=quote(self.fault), m=quote(marker))
        self.shell(script, 'remove-only-own-fault'); self.fault = None

    def start_owned_session(self):
        self.phase('inspect')
        self.started = True
        self.phase('setup')

    def execute(self):
        self.guest = EnclosingAcceptanceGuest(self.args.boot, self.args.archive, self.args.hdc, self.output / 'guest')
        self.guest.start()
        self.report['boot'] = descriptor(self.args.boot)
        self.report['archive'] = {'path': str(self.args.archive.resolve()), 'sha256': load(self.args.boot)['archive_sha256']}
        self.report['tools'] = {name: descriptor(HERE / name) for name in
            ('batch_network_openvpn_runtime_project.py', 'batch_network_openvpn_runtime_collect.py',
             'enclosing_acceptance_guest.py', 'batch_apps_contact_picker_coordinator.py', 'sign_certificate_probe.py')}
        before = self.snapshot('before')
        require(len(before['processes']) <= 1 and (not before['processes'] or
                all(row['exe'] == '/system/bin/qemu_openvpn_service' and row['ppid'] == 1 for row in before['processes'].values())), 'foreign VPN client/worker present')
        require(all(row.startswith('backend.lock|') for row in before['entries']), 'foreign/unknown existing private root content')
        # An unused loopback UDP port is the controlled unreachable endpoint.
        hex_port = f'{self.data["port"]:04X}'
        nets = self.shell('cat /proc/net/udp /proc/net/udp6', 'unused-loopback-endpoint')
        require(not re.search(r':[0]*' + hex_port + r'\s', nets, re.I), 'controlled endpoint already has a UDP socket')
        self.install()
        # Inspect before any mutating request: a foreign non-OpenVPN connection
        # is not visible in our private helper/process namespace.
        self.start_owned_session()
        first = self.wait_claim('first-claim')
        self.report['first_claim'] = first; self.save()
        self.fault = first['directory'] + '/qa-' + self.data['run_id']
        marker = 'openvpn-owned-' + self.data['run_id']
        self.shell('test ! -e {p} && test ! -L {p} && (umask 077; set -C; printf "%s\\n" {m} > {p})'.format(p=quote(self.fault), m=quote(marker)), 'inject-only-own-unknown-file')
        self.shell('test ! -L {p} && test "$(stat -c \'%u:%a:%h\' {p})" = 0:600:1'.format(p=quote(self.fault)), 'own-fault-metadata')
        self.phase('destroy', 'rejected')
        stopped = self.snapshot('reaped-with-cleanup-blocked'); self.no_group(stopped, first)
        self.shell('test -d ' + quote(first['directory']) + ' && test -f ' + quote(self.fault), 'cleanup-reservation-retained')
        self.phase('setup', 'rejected')
        blocked = self.snapshot('restart-blocked'); self.no_group(blocked, first)
        require(all(row['exe'] == '/system/bin/qemu_openvpn_service' and row['ppid'] == 1
                    for row in blocked['processes'].values()) and
                [row.split('|')[0] for row in blocked['entries'] if row.startswith('session-')] == [Path(first['directory']).name],
                'conflicting setup created another worker/session while cleanup was blocked')
        self.remove_fault()
        deadline = time.monotonic() + 12
        while True:
            absent = self.shell('if test -e {p} || test -L {p}; then echo PRESENT; else echo ABSENT; fi'.format(p=quote(first['directory'])), 'reap-cleanup-retry').strip()
            if absent == 'ABSENT': break
            require(time.monotonic() < deadline, 'real periodic cleanup did not retry'); time.sleep(0.25)
        # Recreate proves operational release; absence of a PID alone does not.
        self.phase('setup')
        second = self.wait_claim('second-claim')
        require(second['generation'] != first['generation'] and second['worker']['start'] != first['worker']['start'], 'new real generation/worker required')
        self.report['second_claim'] = second; self.phase('destroy')
        after = self.snapshot('final-processes'); self.no_group(after, first); self.no_group(after, second)
        require(all(row.startswith('backend.lock|') for row in after['entries']) and
                all(row['exe'] == '/system/bin/qemu_openvpn_service' and row['ppid'] == 1 for row in after['processes'].values()),
                'private session artifacts or real worker/client remain')
        self.report['cleanup_verified'] = True; self.report['status'] = 'pass_narrow_guest_cleanup_NOT_full_gate'

    def cleanup(self):
        if not self.guest or not self.install_attempted:
            return
        if self.started:
            try:
                self.remove_fault()
                if not self.report['cleanup_verified']:
                    self.phase('destroy'); remaining = self.snapshot('failure-public-cleanup')
                    require(all(row.startswith('backend.lock|') for row in remaining['entries']) and
                            not any(row['exe'] != '/system/bin/qemu_openvpn_service' or row['ppid'] != 1 for row in remaining['processes'].values()),
                            'failed test still owns live/session resources')
                    self.report['cleanup_verified'] = True
            except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
                self.report['status'] = 'fail'; self.report['failures'].append('native cleanup: ' + str(error))
            if not self.report['cleanup_verified']:
                self.report['status'] = 'fail'
                self.report['failures'].append('guest cannot be reused with unproved owner cleanup')
                return
        # No setup request was sent when install/identity/inspect failed. The
        # only possible installed bundle is ours, absent at the verified BMS
        # baseline; remove it independently of native cleanup verification.
        try:
            if self.installed:
                self.shell('aa force-stop ' + project.BUNDLE, 'stop-own-QA-Ability')
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
            self.report['status'] = 'fail'; self.report['failures'].append('stop own QA: ' + str(error))
        try:
            present = project.BUNDLE in self.shell('bm dump -a', 'BMS-before-uninstall')
            if present:
                reply = self.command([self.args.hdc, '-t', self.guest.target, 'uninstall', project.BUNDLE], 'uninstall-own-QA')
                require('success' in reply.lower(), 'actual BMS uninstall failed')
            require(project.BUNDLE not in self.shell('bm dump -a', 'BMS-after-uninstall'), 'own QA bundle remains installed')
            self.report['qa_bundle_removed'] = True
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
            self.report['status'] = 'fail'; self.report['failures'].append('uninstall own QA: ' + str(error))

    def run(self):
        try: self.execute()
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
            self.report['failures'].append(str(error))
        finally:
            self.cleanup()
            self.save()
        return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='mode', required=True)
    sign = sub.add_parser('sign')
    for name in ('unsigned', 'signer-dist', 'jar', 'output'): sign.add_argument('--' + name, type=Path, required=True)
    sign.add_argument('--udid', required=True)
    run = sub.add_parser('run')
    for name in ('boot', 'archive', 'inputs', 'signer-dist', 'jar', 'output'): run.add_argument('--' + name, type=Path, required=True)
    run.add_argument('--hdc', default='hdc'); args = parser.parse_args()
    if args.mode == 'sign':
        from sign_certificate_probe import sign as sign_hap
        args.role = 'system'; sign_hap(args, configure=profile); return 0
    result = Collector(args).run(); print(json.dumps({'status': result['status'], 'failures': result['failures']}))
    return result['status'] != 'pass_narrow_guest_cleanup_NOT_full_gate'


if __name__ == '__main__': raise SystemExit(main())
