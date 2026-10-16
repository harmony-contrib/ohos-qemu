"""Recheck each real exit invocation against the packaged guest's boot identity."""
import json
from pathlib import Path
import re
import shlex

from build_library_exit_probes import CASES
from enclosing_acceptance_guest import validate_binding
from run_root_probe import digest, parse_exit, validate_elf

SCOPE = 'fresh_packaged_system_DSO_empty_main_exit_cleanup_only'


def execution_script(remote, case, repeat, nonce, bound=False):
    destination = remote + '/' + case
    stem = destination + '-' + str(repeat)
    script = ('unset LD_LIBRARY_PATH LD_PRELOAD; ' + shlex.quote(destination) +
        ' >' + shlex.quote(stem + '.out') + ' 2>' + shlex.quote(stem + '.err') + '; probe_status=$?; ')
    if bound:
        script = boot_marker(nonce, 'BEFORE') + '; ' + script + boot_marker(nonce, 'AFTER') + '; '
    return script + "printf '__OHOS_PROBE_EXIT_" + nonce + "=%s\\n' \"$probe_status\""


def boot_marker(nonce, phase):
    return "printf '__OHOS_LIBRARY_BOOT_" + nonce + '_' + phase + "='; cat /proc/sys/kernel/random/boot_id"


def cleanup_script(remote, run_id):
    return ('rm -rf -- ' + shlex.quote(remote) + ' && test ! -e ' + shlex.quote(remote) +
            " && printf '__OHOS_LIBRARY_CLEANED_" + run_id + "\\n'")


def execution_result(text, nonce, boot_id):
    lines = text.splitlines()
    if len(lines) != 3:
        raise ValueError('exit invocation must retain both actual boot observations and the exit record')
    code = parse_exit(lines[-1] + '\n', nonce)
    expected = ('__OHOS_LIBRARY_BOOT_' + nonce + '_BEFORE=' + boot_id + '\n' +
                '__OHOS_LIBRARY_BOOT_' + nonce + '_AFTER=' + boot_id + '\n' +
                '__OHOS_PROBE_EXIT_' + nonce + '=' + str(code) + '\n')
    if text != expected:
        raise ValueError('exit invocation did not observe this exact guest boot before and after execution')
    return code


def regular(path):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('absolute regular exit evidence required: ' + str(path))
    return path


def verify_evidence(payload, identity, environment):
    if (payload.get('scope') != SCOPE or payload.get('schema_version') != 2 or
            payload.get('archive_binding') != 'actual_enclosing_guest_before_each_exit_and_after' or
            payload.get('status') != 'pass' or payload.get('failures') != [] or
            payload.get('candidate_inputs') or payload.get('archive_sha256') != identity['sha256'] or
            payload.get('boot_id') != environment['boot_id'] or
            (payload.get('arch'), payload.get('device'), payload.get('target')) !=
            (environment['guest_arch'], environment['device_type'], environment['target'])):
        raise ValueError('exit probe requires its own unchanged archive and actual guest binding')
    boot = regular(payload['bound_boot']['path'])
    if digest(boot) != payload['bound_boot']['sha256'] or validate_binding(json.loads(boot.read_text()), identity['sha256']) != environment:
        raise ValueError('exit probe boot snapshot differs from the current packaged guest')
    manifest_path = regular(payload['probe_manifest']['path'])
    manifest = json.loads(manifest_path.read_text())
    if (digest(manifest_path) != payload['probe_manifest']['sha256'] or
            manifest.get('source_sha256') != digest(Path(__file__).with_name('probes') / 'library_exit.c')):
        raise ValueError('exit executable inputs no longer match the actual reviewed empty main')
    repeats = payload.get('repeats')
    rows = payload.get('results', [])
    if type(repeats) is not int or not 3 <= repeats <= 10 or not isinstance(rows, list):
        raise ValueError('real repeated exit results required')
    expected = {(case, repeat) for case in CASES for repeat in range(repeats)}
    if len(rows) != len(expected) or {(row.get('case'), row.get('repeat')) for row in rows} != expected:
        raise ValueError('exit link order/repetition coverage is incomplete')
    run_id = payload.get('run_id', '')
    if re.fullmatch('[a-f0-9]{32}', run_id) is None:
        raise ValueError('actual private exit run identity required')
    remote = '/data/local/tmp/ohos-library-exit-' + run_id
    index = payload.get('cleanup_command_index')
    commands = payload.get('commands', [])
    if type(index) is not int or not 0 <= index < len(commands):
        raise ValueError('owned exit directory cleanup has no raw command receipt')
    cleanup = commands[index]
    if (payload.get('cleanup_complete') is not True or payload.get('cleanup_errors') != [] or
            cleanup.get('argv') != [payload.get('hdc'), '-t', environment['target'], 'shell', cleanup_script(remote, run_id)] or
            type(cleanup.get('transport_exit_code')) is not int or cleanup['transport_exit_code'] != 0 or
            cleanup.get('stderr') != '' or cleanup.get('stdout', '').replace('\r', '') != '__OHOS_LIBRARY_CLEANED_' + run_id + '\n'):
        raise ValueError('owned exit directory cleanup was not actually completed')
    seen = set()
    for row in rows:
        case, repeat, nonce = row['case'], row['repeat'], row.get('nonce', '')
        if type(repeat) is not int or re.fullmatch('[a-f0-9]{32}', nonce) is None or nonce in seen:
            raise ValueError('independent real exit invocation nonce required')
        seen.add(nonce)
        executable = regular(manifest_path.parent / environment['guest_arch'] / case)
        validate_elf(executable, environment['guest_arch'])
        compiled = manifest['artifacts'][environment['guest_arch'] + '/' + case]
        if (digest(executable) != row.get('probe_sha256') or compiled['sha256'] != row['probe_sha256'] or
                compiled['link_order'] != list(CASES[case]) or row.get('link_order') != list(CASES[case])):
            raise ValueError('exit invocation executable or exact DSO order changed')
        index = row.get('command_index')
        commands = payload.get('commands', [])
        if type(index) is not int or not 0 <= index < len(commands):
            raise ValueError('exit invocation has no actual raw transport receipt')
        command = commands[index]
        if (command.get('argv') != [payload.get('hdc'), '-t', environment['target'], 'shell',
                execution_script(remote, case, repeat, nonce, bound=True)] or
                type(command.get('transport_exit_code')) is not int or command['transport_exit_code'] != 0 or
                command.get('stderr') != '' or type(row.get('guest_exit_code')) is not int or
                row['guest_exit_code'] != 0 or
                execution_result(command.get('stdout', '').replace('\r', ''), nonce, environment['boot_id']) != 0):
            raise ValueError('exit raw command, observed boot or actual process exit differs')
        for suffix in ('out', 'err'):
            record = row[suffix]
            path = regular(record['path'])
            if path.parent != boot.parent or path.name != case + '-' + str(repeat) + '.' + suffix or digest(path) != record['sha256']:
                raise ValueError('actual exit stdout/stderr evidence is missing or changed')
    return payload
