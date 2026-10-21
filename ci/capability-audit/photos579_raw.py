"""Pure raw helpers. No callback replay, Guest, command or resource object."""
from pathlib import Path
import hashlib
import json
import re
import shlex
from decimal import Decimal
from guest_ui import command_exit

PROVIDER = 'com.ohos.photos'
PROCESS_SCRIPT = r'''set -eu
printf 'PHOTOS579_PROCESS_V1\n'
cat /proc/sys/kernel/random/boot_id
for d in /proc/[0-9]*; do
  test -r "$d/cmdline" || continue
  cmd=$(tr '\000' '\n' < "$d/cmdline" 2>/dev/null) || exit 42
  first=${cmd%%'
'*}
  case "$first" in com.ohos.photos|com.ohos.photos:*) ;; *) continue ;; esac
  printf 'PID %s\n' "${d##*/}"
  cat "$d/stat" || exit 42
  sed -n '/^Uid:/p' "$d/status" || exit 42
  printf 'CMD %s\nENDPID\n' "$first"
done
printf 'END_PHOTOS579_PROCESS_V1\n'
'''


def need(ok, message):
    if not ok:
        raise ValueError(message)


def unique(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, 'duplicate actual raw JSON key')
        value[key] = item
    return value


def loads(text):
    return json.loads(text, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite actual raw')))


def ref(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and path.is_file() and
        not any(p.is_symlink() for p in (path, *path.parents)), 'actual regular absolute source/raw')
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def checked(row):
    need(type(row) is dict and set(row) in ({'path','sha256'}, {'path','sha256','bytes'}), 'actual Ref2/3')
    path = Path(row['path'])
    need(ref(path) == {k:row[k] for k in ('path','sha256')} and
        ('bytes' not in row or path.stat().st_size == row['bytes']), 'raw bytes changed')
    return path


def document(row):
    return loads(checked(row).read_text())


def title_hash(title):
    # Exact selected official PickerUtil.getHash, not an estimated timestamp.
    value = 0
    for char in title:
        value = (value * 13 + ord(char)) % 9999991
    return str(value)


def processes(text, boot):
    lines = text.splitlines()
    need(lines[:2] == ['PHOTOS579_PROCESS_V1',boot] and lines[-1:] == ['END_PHOTOS579_PROCESS_V1'],
        'complete actual kernel process scan')
    rows = []
    at = 2
    while at < len(lines)-1:
        block = lines[at:at+5]
        need(len(block) == 5 and re.fullmatch(r'PID [1-9][0-9]*',block[0]) and block[4] == 'ENDPID',
            'actual kernel PID/UID/cmd/stat framing')
        pid = int(block[0][4:]); stat = block[1]
        prefix, suffix = stat.rsplit(') ',1)
        parts = suffix.split()
        need(prefix.startswith(str(pid)+' (') and len(parts) >= 20 and parts[19].isdigit(), 'actual /proc PID starttime')
        uid = re.fullmatch(r'Uid:\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)',block[2])
        need(uid is not None and len(set(uid.groups())) == 1 and block[3].startswith('CMD '+PROVIDER), 'actual process UID/name')
        name = block[3][4:]
        need(name == PROVIDER or name.startswith(PROVIDER+':'), 'exact actual Photos process namespace')
        rows.append(dict(pid=pid,starttime=int(parts[19]),uid=int(uid[1]),name=name))
        at += 5
    need(at == len(lines)-1 and len({row['pid'] for row in rows}) == len(rows), 'unique complete kernel process snapshot')
    return rows


def extensions(text, host):
    records = re.split(r'(?=^    uri \[)', text, flags=re.M)
    selected = []
    for block in records:
        if (block.startswith('    uri [/com.ohos.photos/') and
            'bundle name [com.ohos.photos]' in block and 'ability type [UIEXTENSION]' in block and
            'root host bundle name ['+host+']' in block):
            current = re.findall(r'AbilityRecord ID #([0-9]+)\s+state #(FOREGROUND|ACTIVE)\b',block)
            if current:
                selected.extend(int(row[0]) for row in current)
    need(len(selected) == 1, 'one actual Photos UIExtension connected to the real ordinary host')
    return selected[0]


def wire(row, *, boot, target, script=None):
    need(row['boot_id'] == boot and row['timed_out'] is False and type(row['exit_code']) is int,
        'actual completed original command')
    stdout,stderr = checked(row['stdout_ref']).read_text(),checked(row['stderr_ref']).read_text()
    need(stdout == row['stdout'] and stderr == row['stderr'] and checked(row['log']).read_text() == stdout+stderr,
        'original stdout/stderr/log association')
    argv = row['argv']
    if len(argv) == 5 and argv[1:4] == ['-t',target,'shell']:
        cap = re.fullmatch(r'(.*); cap578_rc=\$\?; printf "\\n(__CAP578_EXIT_[a-f0-9]{32}__=)%s\\n" "\$cap578_rc"',argv[4],re.S)
        ui = re.fullmatch(r'(.*); task_ui_rc=\$\?; printf "\\n(__UITEST_EXIT_[a-f0-9]{32}__=)%s\\n" "\$task_ui_rc"',argv[4],re.S)
        need(cap or ui,'actual original shell footer')
        mark=cap or ui
        body,code=command_exit(stdout,mark[2])
        if cap:
            words=shlex.split(mark[1]); need(len(words)==3 and words[:2]==['sh','-c'] and shlex.join(words)==mark[1], 'original isolated guest program')
            program=words[2]
        else:
            program=mark[1]
        need('shell_stdout_ref' not in row or checked(row['shell_stdout_ref']).read_text() == body,
            'actual guest body differs')
        need('shell_exit_code' not in row or row['shell_exit_code']==code, 'actual guest status differs')
        need(script is None or program==script,'fixed source guest script differs')
        return dict(script=program,body=body,exit_code=code)
    need(script is None,'required guest script not observed')
    return dict(script=None,body=stdout,exit_code=row['exit_code'])
