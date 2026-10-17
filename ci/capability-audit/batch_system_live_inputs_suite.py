#!/usr/bin/env python3
"""Fresh-guest GNSS/Sensor/public-still capture, independent check and cleanup.

Root selects explicit controlled virtual protocol vectors or supplies fresh
external replay files. No guest result, physical fix or callback is generated
offline. This does not build/boot, grant permissions or close the package gate.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shutil
import struct
import subprocess
import sys
import tempfile
import time

from batch_system_live_inputs import (BUNDLE, FIXTURES, PERMISSIONS, SCOPE, digest,
    nonce, read_json, trace, verify_project, write_json)

HERE = Path(__file__).resolve().parent
FAMILY = 'external-inputs'
CONTROLLED = 'controlled_virtual_protocol_vectors'
TOOLS = ['batch_system_live_inputs_suite.py', 'batch_system_run_live_inputs.py',
    'batch_system_verify_live_inputs.py', 'batch_system_live_inputs.py',
    'batch_system_sdk_native_strip.py',
    'batch_system_gnss_controller.py', 'batch_system_qemu_sensor_controller.py',
    'batch_apps_contact_picker_coordinator.py', 'sign_web_probe.py', 'enclosing_acceptance_guest.py']


def require(value, message):
    if not value: raise ValueError(message)


def regular(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'absolute regular file required: ' + str(path))
    return path.resolve()


def descriptor(path):
    path = regular(path)
    return {'path': str(path), 'sha256': digest(path)}


def checked(row):
    path = regular(row['path'])
    require(re.fullmatch('[a-f0-9]{64}', row.get('sha256', '')) and digest(path) == row['sha256'], 'artifact SHA changed: ' + str(path))
    return path


def apps_api():
    # Parent integrates the real shared implementation. Missing implementation
    # is a failure, never a local signature/profile substitute.
    return importlib.import_module('batch_apps_contact_picker_coordinator')


def tool_hashes():
    return {name: digest(regular(HERE / name)) for name in TOOLS}


def source_vectors(spec):
    require(spec.get('mode') == CONTROLLED and isinstance(spec.get('source_id'), str) and
            1 <= len(spec['source_id']) <= 200 and spec['source_id'].strip(), 'explicit root controlled virtual vector source required')
    path = checked(spec['vectors']); value = read_json(path)
    require(set(value) == {'schema_version', 'source_id', 'generations'} and type(value['schema_version']) is int and value['schema_version'] == 1 and
            value['source_id'] == spec['source_id'] and isinstance(value['generations'], list) and
            len(value['generations']) == 2, 'controlled vector schema/source identity differs')
    result = {}
    for row in value['generations']:
        require(set(row) == {'generation', 'gnss', 'sensor'} and type(row['generation']) is int and
                row['generation'] in (1, 2) and row['generation'] not in result, 'two unique logical input generations required')
        generation = row['generation']
        require(isinstance(row['gnss'], list) and isinstance(row['sensor'], list), 'explicit bounded vector arrays required')
        require(3 <= len(row['gnss']) <= 2000 and 30 <= len(row['sensor']) <= 2000, 'controlled vectors exceed required limits')
        for sample in row['gnss']:
            require(isinstance(sample, dict) and 'utc_ms' not in sample and type(sample.get('at_ms')) is int,
                    'controlled vector UTC is assigned only after actual ready; integer relative milliseconds required')
        for sample in row['sensor']:
            require(isinstance(sample, dict) and type(sample.get('at_ms')) is int, 'integer relative sensor milliseconds required')
        # Strict existing schemas/float32/phase checks, using a validation epoch
        # only in private host parser input. These bytes are never guest evidence.
        with tempfile.TemporaryDirectory(prefix='live-vector-schema-') as scratch:
            scratch = Path(scratch)
            for kind in ('gnss', 'sensor'):
                samples = row[kind] if kind == 'sensor' else [dict(s, utc_ms=1577836800000 + s['at_ms']) for s in row[kind]]
                write_json(scratch / (kind + '.json'), samples); trace(scratch / (kind + '.json'), kind)
        result[generation] = row
    require(set(result) == {1, 2} and all(result[1][kind] != result[2][kind] for kind in ('gnss', 'sensor')),
            'root must select distinct coordinates and accelerations for each generation')
    return result


def atomic_json(path, value):
    path = Path(path); require(not path.exists(), 'fresh publication path already exists')
    temporary = path.with_name(path.name + '.publishing-' + secrets.token_hex(8))
    try:
        write_json(temporary, value)
        # The wrapper owns a fresh private directory. Hard-link publishes a
        # complete immutable byte sequence exclusively, without replacing input.
        os.link(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()


def publish_controlled(artifacts, capture, inputs, run_id, output, wait=600):
    """Separate root-owned host producer; never connects to an API/provider."""
    artifacts, capture, inputs, output = map(Path, (artifacts, capture, inputs, output))
    result = {'scope': CONTROLLED + '_NOT_physical_measurements_or_guest_results', 'status': 'fail',
        'artifacts': descriptor(artifacts), 'run_id': nonce(run_id), 'pid': os.getpid(), 'generations': []}
    try:
        spec = read_json(artifacts)['input_source']; source_vectors(spec); result['source'] = spec
        for generation in (1, 2):
            ready = capture / ('ready-' + str(generation) + '.json'); end = time.monotonic() + wait
            while not ready.is_file() and time.monotonic() < end: time.sleep(.1)
            value = read_json(regular(ready))
            require(value.get('run_id') == run_id and value.get('generation') == generation, 'actual ready belongs to another run/generation')
            # The source is checked again at publication, after the real ready.
            row = source_vectors(spec)[generation]
            utc_ms, monotonic_ns = time.time_ns() // 1_000_000, time.monotonic_ns()
            paths = {}
            for kind in ('gnss', 'sensor'):
                samples = row[kind] if kind == 'sensor' else [dict(s, utc_ms=utc_ms + s['at_ms']) for s in row[kind]]
                path = inputs / (kind + '-' + str(generation) + '.json')
                atomic_json(path, samples); trace(path, kind); paths[kind] = descriptor(path)
            manifest = {'run_id': run_id, 'generation': generation, 'source': CONTROLLED + ':' + spec['source_id'],
                'gnss_file': Path(paths['gnss']['path']).name, 'sensor_file': Path(paths['sensor']['path']).name,
                'source_kind': CONTROLLED, 'source_descriptor': spec['vectors'],
                'published_host_utc_ms': utc_ms, 'published_host_monotonic_ns': monotonic_ns}
            target = inputs / ('generation' + str(generation) + '.json'); atomic_json(target, manifest)
            result['generations'].append({'generation': generation, 'ready': descriptor(ready), 'manifest': descriptor(target),
                'gnss': paths['gnss'], 'sensor': paths['sensor'], 'host_utc_ms': utc_ms, 'host_monotonic_ns': monotonic_ns})
        result['status'] = 'published_NOT_guest_verified'
    except Exception as error: result['error'] = type(error).__name__ + ': ' + str(error)
    finally: write_json(output, result)
    return 0 if result['status'] == 'published_NOT_guest_verified' else 1


def elf64_arm64(path):
    data = regular(path).read_bytes()
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01' and struct.unpack_from('<HH', data, 16) == (3, 183),
            'actual ARM64 SDK native DSO required')
    return descriptor(path)


def sdk_caller(spec, sdk):
    api = apps_api(); caller = spec['caller']
    checked(caller['source_manifest'])
    result = api.verify_sdk_project(caller, fixture=FIXTURES, source_manifest='live-inputs-contract.json')
    project = Path(caller['source_project']).resolve(); contract = read_json(project / 'live-inputs-contract.json')
    verify_project(project, sdk, nonce(contract['run_id']), 'arm64')
    evidence = read_json(checked(caller['sdk_evidence'])); commands = [c for c in evidence['commands'] if c.get('project') == caller['sdk_project']]
    native = [c for c in commands if c.get('label') == 'compile-native']
    builds = [r for r in evidence.get('native_builds', []) if r.get('project') == caller['sdk_project']]
    require(len(native) == len(builds) == 1, 'one actual native SDK command and full native_builds receipt required')
    command, build = native[0], builds[0]; argv = command['argv']
    binary = project / contract['native_packaging']['relative_library']; source = project / 'socket_probe.cpp'
    require(build.get('command_label') == 'compile-native' and command.get('exit_code') == 0 and
            '--target=aarch64-linux-ohos' in argv and '-shared' in argv and '-fPIC' in argv and '-Werror' in argv and
            str(source) in argv and argv.count('-o') == 1 and argv[argv.index('-o') + 1] == str(binary),
            'actual native source/ARM64 output/SDK command binding differs')
    require(checked(build['source']) == source and digest(source) == digest(FIXTURES / 'socket_probe.cpp') and
            checked(build['binary']) == binary and build.get('headers') and
            all(Path(name).is_absolute() and re.fullmatch('[a-f0-9]{64}', value) for name, value in build['headers'].items()) and
            any(name.endswith('/napi/native_api.h') for name in build['headers']) and
            Path(build['compiler']['path']).name == 'clang++' and argv[0] == build['compiler']['path'] and
            re.fullmatch('[a-f0-9]{64}', build['compiler']['sha256']) and
            build['sdk_native_metadata_sha256'] == contract['sdk']['native_metadata']['sha256'],
            'actual native SDK source/compiler/header/metadata receipt missing')
    # Official Hvigor NativeStrip changes the DSO's non-loadable sections.
    # Independently replay the exact SDK tool into a private output and bind
    # every main/runtime library to its actual packaged member, byte for byte.
    # This reads the separately captured replay; it never rebuilds the caller
    # or rewrites the original successful SDK report.
    native_strip = importlib.import_module('batch_system_sdk_native_strip').verify(caller, build, binary)
    result.update(source_project=str(project), contract=descriptor(project / 'live-inputs-contract.json'),
        native_binary=elf64_arm64(binary), native_build_receipt=build, native_strip=native_strip,
        native_tool_header_hash_scope='Actual Linux SDK reads recorded by the original frozen SDK runner, not host tool rereads',
        run_id=contract['run_id'])
    return result, commands, api.source_rows(evidence, caller['sdk_project'])


def capture_project(destination, spec, sdk_result, commands, rows):
    """Copy only hash-checked inputs; retain original SDK receipts unmodified."""
    destination = Path(destination); destination.mkdir()
    source = Path(sdk_result['source_project'])
    for relative, expected in rows.items():
        path = regular(source / relative); require(digest(path) == expected, 'SDK source changed before private copy')
        target = destination / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        require(digest(target) == expected, 'private source copy differs')
    # Build output is not source inventory; explicitly bind and copy the real DSO.
    contract = read_json(source / 'live-inputs-contract.json')
    relative = contract['native_packaging']['relative_library']; target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(checked(sdk_result['native_binary']), target)
    write_json(destination / 'live-inputs-build.json', {'status': 'pass',
        'scope': 'derived_verified_actual_SDK_receipts_NOT_new_compilation', 'original_sdk_evidence': spec['caller']['sdk_evidence'],
        'unsigned_hap': str(checked(spec['caller']['unsigned_hap'])), 'unsigned_hap_sha256': spec['caller']['unsigned_hap']['sha256'],
        'commands': commands, 'native_library': str(target), 'native_sha256': digest(target),
        'native_strip': sdk_result['native_strip']})
    return destination


def verify_capture_project(project, spec, sdk_result, commands, rows):
    project = Path(project).resolve()
    for relative, expected in rows.items():
        require(digest(regular(project / relative)) == expected, 'private capture source differs from actual compiled source: ' + relative)
    build = read_json(project / 'live-inputs-build.json')
    require(build.get('status') == 'pass' and build.get('scope') == 'derived_verified_actual_SDK_receipts_NOT_new_compilation' and
            build.get('original_sdk_evidence') == spec['caller']['sdk_evidence'] and build.get('commands') == commands and
            regular(build['unsigned_hap']) == checked(spec['caller']['unsigned_hap']) and
            build['unsigned_hap_sha256'] == spec['caller']['unsigned_hap']['sha256'],
            'derived capture receipt differs from original verified SDK commands/HAP')
    contract = read_json(project / 'live-inputs-contract.json'); native = project / contract['native_packaging']['relative_library']
    require(regular(build['native_library']) == native and digest(native) == build['native_sha256'] == sdk_result['native_binary']['sha256'],
            'private native library differs from actual SDK/HAP output')
    require(build.get('native_strip') == sdk_result['native_strip'],
            'private native strip proof differs from independently verified SDK replay')


class Commands:
    def __init__(self, output, rows, target, hdc):
        self.output = Path(output); self.output.mkdir(); self.rows = rows; self.target = target; self.hdc = str(hdc)

    def execute(self, argv, label, accepted_failure=False):
        require(re.fullmatch('[A-Za-z0-9_-]+', label), 'bounded command label required')
        stem = self.output / (str(len(self.rows)).zfill(4) + '-' + label)
        row = {'argv': list(map(str, argv)), 'label': label}; self.rows.append(row); p = None
        try:
            p = subprocess.Popen(row['argv'], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True, env=dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C', PYTHONDONTWRITEBYTECODE='1'))
            try:
                stdout, stderr = p.communicate(timeout=120); row['exit_code'] = p.returncode
            except subprocess.TimeoutExpired:
                # The fixed signer Python driver can own a Java child. Quiesce
                # only this newly created command group, never shared services.
                try: os.killpg(p.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: stdout, stderr = p.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    try: os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    stdout, stderr = p.communicate(timeout=3)
                row.update(exit_code=124, timed_out=True, process_returncode=p.returncode)
        except subprocess.TimeoutExpired as error:
            stdout, stderr = error.stdout or b'', error.stderr or b''
            row.update(exit_code=124, timed_out=True, process_group_cleanup_unconfirmed=True)
        except OSError as error:
            stdout, stderr = b'', str(error).encode(); row.update(exit_code=127, launch_error=str(error))
            if p is not None and p.poll() is None: row['process_group_cleanup_unconfirmed'] = True
        for name, data in (('stdout', stdout), ('stderr', stderr), ('log', stdout + stderr)):
            path = Path(str(stem) + '-' + name + '.log'); path.write_bytes(data); row[name] = descriptor(path)
        from hdc_transport import failed
        text, err = stdout.decode(errors='replace').replace('\r', ''), stderr.decode(errors='replace')
        require(accepted_failure or row['exit_code'] == 0 and not failed(text, err), 'actual command failed: ' + label)
        return text, err, row

    def __call__(self, argv, label):
        text, err, _ = self.execute(argv, label); return text + err

    def shell(self, script, label, accepted_failure=False):
        marker = '__LIVE_SUITE_EXIT_' + secrets.token_hex(16) + '__='
        wrapped = '(' + script + '); task_live_suite_rc=$?; printf "\\n' + marker + '%s\\n" "$task_live_suite_rc"'
        text, err, row = self.execute([self.hdc, '-t', self.target, 'shell', wrapped], label, accepted_failure)
        matches = re.findall(r'\n' + marker + r'([0-9]+)\n?$', text)
        require(len(matches) == 1 and text.count(marker) == 1 and (accepted_failure or matches[0] == '0'), 'actual guest exit missing/nonzero: ' + label)
        raw = text.rsplit('\n' + marker, 1)[0]
        path = self.output / (label + '-raw.txt'); require(not path.exists(), 'duplicate actual raw command label')
        path.write_text(raw); row.update(script=script, marker=marker, guest_exit_code=int(matches[0]), raw=descriptor(path))
        return raw, row


def uid_process_scan(uid):
    require(uid is None or type(uid) is int and uid > 10000, 'ordinary UID only for cleanup scan')
    # No grep/ps format assumption. proc cmdline remains actual OS evidence.
    script = 'for f in /proc/[0-9]*/cmdline; do test -r "$f" || continue; p=${f%/cmdline}; '
    script += 'name=$(tr "\\000" " " < "$f" 2>/dev/null); case "$name" in ' + BUNDLE + '|' + BUNDLE + r'\ *|' + BUNDLE + ':*) printf "PROCESS %s\\n%s\\n" "$p" "$name";; esac; '
    if uid is not None:
        script += 'while read -r key real effective saved fs rest; do test "$key" = "Uid:" || continue; '
        script += 'if test "$real" = "' + str(uid) + '"; then printf "UID_PROCESS %s\\n" "$p"; cat "$p/status"; fi; break; done < "$p/status" 2>/dev/null; '
    return script + 'done; printf "__LIVE_PROCESS_SCAN_DONE__\\n"'


def binding(archive, boot):
    from enclosing_acceptance_guest import validate_binding
    value = read_json(regular(boot)); env = validate_binding(value, digest(regular(archive)))
    require(env['guest_arch'] == 'arm64' and env['device_type'] == 'phone' and env['product'] == 'arm64_virt',
            'new representative ARM64 phone acceptance boot required')
    return env


def checked_command(row):
    stdout, stderr, log = (checked(row[name]) for name in ('stdout', 'stderr', 'log'))
    require(log.read_bytes() == stdout.read_bytes() + stderr.read_bytes(), 'actual command stdout/stderr/log binding differs')
    require(type(row.get('exit_code')) is int, 'actual command exit missing')
    return stdout.read_text().replace('\r', '')


def cleanup_raw(row, script, target):
    text = checked_command(row); raw = checked(row['raw']).read_text(); marker = row['marker']
    require(row.get('script') == script and row['argv'][1:4] == ['-t', target, 'shell'] and
            row['argv'][-1] == '(' + script + '); task_live_suite_rc=$?; printf "\\n' + marker + '%s\\n" "$task_live_suite_rc"' and
            row['exit_code'] == 0 and row.get('guest_exit_code') == 0 and
            re.fullmatch('__LIVE_SUITE_EXIT_[a-f0-9]{32}__=', marker) and text == raw + '\n' + marker + '0\n',
            'cleanup capture is not bound to an actual successful guest command')
    return raw


def verify_cleanup(report, target):
    require(report.get('cleanup_complete') is True and report.get('cleanup_errors') == [], 'owned resource cleanup incomplete')
    value = report['cleanup']; rows = report['commands']
    require(not any(row.get('process_group_cleanup_unconfirmed') for row in rows), 'owned command process group did not quiesce')
    require({'BMS_after', 'process_scans', 'forwards_after', 'owned_forwards', 'open_streams', 'producer'} <= value.keys(),
            'actual complete resource cleanup captures required')
    def row(index):
        require(type(index) is int and 0 <= index < len(rows), 'missing cleanup command reference'); return rows[index]
    raw = cleanup_raw(row(value['BMS_after']), 'bm dump -a', target)
    require(re.search(r'(?<![A-Za-z0-9_.])com\.ohos\.[A-Za-z0-9_.]+', raw) and
            not re.search(r'(?<![A-Za-z0-9_.])' + re.escape(BUNDLE) + r'(?![A-Za-z0-9_.])', raw),
            'actual installed system bundle list missing or ordinary app remains installed')
    require(len(value['process_scans']) == 2, 'two actual process absence observations required')
    script = uid_process_scan(value.get('ordinary_uid'))
    for index in value['process_scans']:
        require(cleanup_raw(row(index), script, target) == '__LIVE_PROCESS_SCAN_DONE__\n', 'owned app/UID process remains')
    forwards = row(value['forwards_after']); raw = checked_command(forwards)
    from hdc_transport import failed
    require(forwards['exit_code'] == 0 and forwards['argv'][1:] == ['-t', target, 'fport', 'ls'], 'actual forward-list inspection missing')
    require(not failed(raw, checked(forwards['stderr']).read_text()), 'actual forward-list transport failed')
    for local, remote in value['owned_forwards']:
        require(re.fullmatch('tcp:[0-9]{1,5}', local) and remote in ('localfilesystem:/dev/unix/socket/qemu_gnss/input',
                'localfilesystem:/dev/unix/socket/qemu_sensor/input') and local not in raw, 'private forward remains or invalid ownership')
    require(value['open_streams'] == 0, 'private client sockets remain open')
    producer = value['producer']
    require(producer.get('owned') is False or producer.get('exited') is True and type(producer.get('exit_code')) is int,
            'owned publisher did not terminate')
    return {'status': 'pass', 'app_absent': True, 'two_process_scans': True, 'forwards_absent': True, 'producer_exited': True}


def verify_input_source(report, spec, capture):
    source = spec['input_source']
    if source.get('mode') == CONTROLLED:
        values = source_vectors(source); receipt = read_json(checked(report['publisher']))
        require(receipt.get('status') == 'published_NOT_guest_verified' and receipt.get('run_id') == report['run_id'] and
                receipt.get('source') == source and [r['generation'] for r in receipt['generations']] == [1, 2],
                'independent publisher receipt incomplete or wrong source')
        require(report['cleanup']['producer'].get('owned') is True and
                receipt['artifacts'] == report['artifacts'] and type(receipt.get('pid')) is int and receipt['pid'] > 1 and
                report['publisher_process']['pid'] == receipt['pid'], 'independent publisher process/artifact ownership differs')
        for row in receipt['generations']:
            generation = row['generation']; ready = checked(row['ready'])
            require(ready == (capture / ('ready-' + str(generation) + '.json')).resolve(), 'publisher not bound to actual capture ready')
            signal = read_json(ready); require(signal['run_id'] == report['run_id'] and signal['generation'] == generation, 'publisher ready identity differs')
            manifest = read_json(checked(row['manifest'])); base = capture / ('input-' + str(generation))
            require(read_json(base / 'manifest.json') == manifest and manifest['source'] == CONTROLLED + ':' + source['source_id'] and
                    manifest['source_descriptor'] == source['vectors'] and manifest['source_kind'] == CONTROLLED,
                    'actual input provenance differs from root vector selection')
            require(type(row['host_utc_ms']) is int and type(row['host_monotonic_ns']) is int and row['host_monotonic_ns'] > 0 and
                    manifest['published_host_utc_ms'] == row['host_utc_ms'] and manifest['published_host_monotonic_ns'] == row['host_monotonic_ns'],
                    'actual UTC/monotonic publication receipt missing')
            require(type(signal.get('host_utc_ms')) is int and 0 <= row['host_utc_ms'] - signal['host_utc_ms'] <= 120000,
                    'controlled input publication did not follow the actual ready in its bounded interval')
            raw_capture = read_json(capture / 'capture.json')
            valid_sessions = [v for v in raw_capture['sessions'] if v.get('generation') == generation and
                              v.get('label') == 'valid-generation-' + str(generation)]
            require(len(valid_sessions) == 2 and all(v.get('trace_start_monotonic_ns', 0) >= row['host_monotonic_ns'] for v in valid_sessions),
                    'raw valid wire session preceded post-ready independent publication')
            for kind in ('gnss', 'sensor'):
                path = checked(row[kind]); expected = values[generation][kind]
                if kind == 'gnss': expected = [dict(s, utc_ms=row['host_utc_ms'] + s['at_ms']) for s in expected]
                require(read_json(path) == expected and path.read_bytes() == (base / (kind + '.json')).read_bytes(),
                        'wire source is not the root-selected post-ready vector publication')
        require(report['cleanup']['producer']['exit_code'] == 0, 'independent source producer failed')
        return {'mode': CONTROLLED, 'source_id': source['source_id'], 'physical_accuracy_verified': False}
    require(source.get('mode') == 'external_publisher_directory' and Path(source['directory']).is_absolute(), 'unsupported input source mode')
    require(report['cleanup']['producer']['owned'] is False, 'external publisher ownership differs')
    # Existing verifier validates copied provenance/UTC/raw frames and callbacks.
    return {'mode': source['mode'], 'physical_accuracy_verified': False}


def verify_evidence(evidence_path, archive_path, boot_path):
    evidence_path, archive_path, boot_path = map(regular, (evidence_path, archive_path, boot_path))
    report = read_json(evidence_path); env = binding(archive_path, boot_path)
    require(report.get('family') == FAMILY and report.get('status') == 'pass' and report.get('failures') == [] and
            report['archive_sha256'] == digest(archive_path) and report['boot_id'] == env['boot_id'] and
            checked(report['boot']) == boot_path and checked(report['archive']) == archive_path and
            report['tools_sha256'] == tool_hashes(), 'suite evidence archive/boot/source binding differs')
    spec = read_json(checked(report['artifacts']))
    require(type(spec.get('schema_version')) is int and spec['schema_version'] == 1, 'actual artifacts schema1 required')
    sdk_result, commands, source_rows = sdk_caller(spec, spec['sdk'])
    require(sdk_result == report['sdk'], 'stored actual SDK proof differs on independent recomputation')
    for row in report['commands']: checked_command(row)
    cleanup = verify_cleanup(report, env['target'])
    capture = checked(report['capture']).parent
    require(capture.is_relative_to(evidence_path.parent) and report['run_id'] == sdk_result['run_id'], 'capture escapes wrapper/run identity')
    capture_report = read_json(capture / 'capture.json')
    require(report['cleanup']['ordinary_uid'] == capture_report['ordinary_uid'], 'cleanup did not inspect the actual ordinary UID')
    forwards = [row for row in capture_report['commands'] if row.get('label') in ('own-forward-gnss', 'own-forward-sensor')]
    require(len(forwards) == 2 and len({row['label'] for row in forwards}) == 2 and
            all(row.get('exit_code') == 0 and row['argv'][1:4] == ['-t', env['target'], 'fport'] and len(row['argv']) == 6 for row in forwards) and
            report['cleanup']['owned_forwards'] == [row['argv'][-2:] for row in forwards],
            'cleanup forward ownership differs from actual captured creations')
    require(regular(capture_report['signed_hap']) == checked(report['signed']['signed_hap']) and
            regular(capture_report['signer_jar']) == regular(spec['signer_jar']) and
            capture_report['sdk'] == str(Path(spec['sdk']).resolve()), 'captured caller/signer/SDK differs from independently verified inputs')
    project = Path(capture_report['project']).resolve()
    require(project == evidence_path.parent / 'capture-project', 'private capture project escapes wrapper output')
    verify_capture_project(project, spec, sdk_result, commands, source_rows)
    source = verify_input_source(report, spec, capture)
    api = apps_api(); unsigned = checked(spec['caller']['unsigned_hap']); signed = checked(report['signed']['signed_hap'])
    api.verify_signed_payload(unsigned, signed)
    with tempfile.TemporaryDirectory(prefix='live-parent-reverify-') as scratch:
        scratch = Path(scratch); crypto_rows = []; command = Commands(scratch / 'commands', crypto_rows, env['target'], report['hdc'])
        api.verify_signed_hap_artifacts(signed, BUNDLE, PERMISSIONS, env['udid'], spec['signer_dist'], spec['signer_jar'], scratch / 'signature', command)
    verifier = importlib.import_module('batch_system_verify_live_inputs')
    results = verifier.verify(capture, archive_path, boot_path, spec['sdk'])
    require(all(results.get(key, {}).get('status') == 'pass' for key in ('gnss', 'sensor', 'msdp_public_still')),
            'raw GNSS/Sensor/public-still independent verification failed: ' + json.dumps(results))
    require(read_json(checked(report['independent_result'])) == results, 'stored verifier results differ from raw recomputation')
    return {'status': 'pass', 'archive_sha256': digest(archive_path), 'boot_id': env['boot_id'],
        'scope': SCOPE, 'cleanup': cleanup, 'source': source, 'results': results,
        'actual_crypto_commands_reexecuted': len(crypto_rows), 'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}


def run(args):
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'family': FAMILY, 'scope': SCOPE, 'status': 'fail', 'failures': [], 'commands': [],
        'cleanup_complete': False, 'cleanup_errors': [], 'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}
    guest = None; capture = None; publisher = None; publisher_log = None; command = None; attempted = False
    try:
        env = binding(args.archive, args.boot); spec = read_json(regular(args.artifacts))
        require(type(spec.get('schema_version')) is int and spec['schema_version'] == 1, 'actual artifacts schema1 required')
        report.update(archive=descriptor(args.archive), archive_sha256=digest(args.archive), boot=descriptor(args.boot),
            boot_id=env['boot_id'], artifacts=descriptor(args.artifacts), tools_sha256=tool_hashes(), hdc=str(Path(args.hdc).resolve()))
        sdk_result, commands, source_rows = sdk_caller(spec, spec['sdk']); report['sdk'] = sdk_result; report['run_id'] = sdk_result['run_id']
        from enclosing_acceptance_guest import EnclosingAcceptanceGuest
        guest = EnclosingAcceptanceGuest(args.boot, args.archive, args.hdc, output / 'guest').start()
        command = Commands(output / 'commands', report['commands'], env['target'], args.hdc)
        before, _ = command.shell('bm dump -a', 'BMS-before')
        require(not re.search(r'(?<![A-Za-z0-9_.])' + re.escape(BUNDLE) + r'(?![A-Za-z0-9_.])', before), 'owned caller already installed; fresh guest baseline required')
        signed = apps_api().sign_normal_hap(checked(spec['caller']['unsigned_hap']), BUNDLE, PERMISSIONS, env['udid'],
            spec['signer_dist'], spec['signer_jar'], output / 'signing', command); report['signed'] = signed
        project = capture_project(output / 'capture-project', spec, sdk_result, commands, source_rows)
        source = spec['input_source']; capture_dir = output / 'capture'
        if source.get('mode') == CONTROLLED:
            source_vectors(source); inputs = output / 'inputs'; inputs.mkdir()
            log = output / 'publisher.log'; publisher_log = log.open('xb')
            argv = [sys.executable, str(Path(__file__).resolve()), '_publish', '--artifacts', str(Path(args.artifacts).resolve()),
                '--capture', str(capture_dir), '--inputs', str(inputs), '--run-id', report['run_id'], '--output', str(output / 'publisher.json')]
            publisher = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=publisher_log, stderr=subprocess.STDOUT,
                env=dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C', PYTHONDONTWRITEBYTECODE='1'))
            report['publisher_process'] = {'argv': argv, 'pid': publisher.pid}
        else:
            require(source.get('mode') == 'external_publisher_directory', 'root must explicitly select a supported independent input source')
            inputs = Path(source['directory']); require(inputs.is_absolute() and inputs.is_dir() and not inputs.is_symlink(), 'external input directory required')
        require(not any((inputs / ('generation' + str(g) + '.json')).exists() for g in (1, 2)), 'input manifest existed before actual ready')
        driver = importlib.import_module('batch_system_run_live_inputs')
        capture = driver.Capture(argparse.Namespace(output=capture_dir, archive=Path(args.archive), boot=Path(args.boot),
            project=project, sdk=Path(spec['sdk']), arch='arm64', signed_hap=checked(signed['signed_hap']), signer_jar=Path(spec['signer_jar']),
            hdc=str(args.hdc), target=env['target'], run_id=report['run_id'], input_directory=inputs,
            input_wait=120, permission_allow_text=spec.get('permission_allow_text')))
        attempted = True; raw = capture.run(); report['capture'] = descriptor(capture_dir / 'capture.json')
        require(raw.get('capture_complete') is True and raw.get('failures') == [], 'actual ordinary callback capture failed: ' + json.dumps(raw.get('failures')))
        if publisher:
            require(publisher.wait(timeout=5) == 0, 'independent publisher failed'); report['publisher'] = descriptor(output / 'publisher.json')
        verifier = importlib.import_module('batch_system_verify_live_inputs')
        results = verifier.verify(capture_dir, args.archive, args.boot, spec['sdk'])
        write_json(output / 'independent-result.json', results); report['independent_result'] = descriptor(output / 'independent-result.json')
        require(all(results.get(key, {}).get('status') == 'pass' for key in ('gnss', 'sensor', 'msdp_public_still')), 'actual input/API paths failed: ' + json.dumps(results))
        guest.healthy(); report['status'] = 'pass'
    except Exception as error: report['failures'].append(type(error).__name__ + ': ' + str(error))
    finally:
        cleanup = {'producer': {'owned': publisher is not None}, 'open_streams': 0, 'owned_forwards': [], 'process_scans': []}
        report['cleanup'] = cleanup
        if any(row.get('process_group_cleanup_unconfirmed') for row in report['commands']):
            report['cleanup_errors'].append('owned command process group did not quiesce')
        if publisher:
            try:
                if publisher.poll() is None:
                    publisher.terminate()
                    try: publisher.wait(timeout=3)
                    except subprocess.TimeoutExpired: publisher.kill(); publisher.wait(timeout=3)
                cleanup['producer'].update(exited=publisher.poll() is not None, exit_code=publisher.returncode)
                if (output / 'publisher.json').is_file(): report['publisher'] = descriptor(output / 'publisher.json')
            except Exception as error: report['cleanup_errors'].append('publisher: ' + str(error))
        if publisher_log:
            publisher_log.close(); report['publisher_log'] = descriptor(output / 'publisher.log')
        if capture:
            for stream in capture.streams:
                try: stream.close()
                except OSError as error: report['cleanup_errors'].append('private stream: ' + str(error))
            cleanup['open_streams'] = sum(s.fileno() != -1 for s in capture.streams)
            cleanup['owned_forwards'] = [list(pair) for pair in capture.forwards]
            cleanup['ordinary_uid'] = capture.report.get('ordinary_uid')
        if command and attempted:
            for script, label in [('aa force-stop ' + BUNDLE, 'cleanup-stop'), ('bm uninstall -n ' + BUNDLE, 'cleanup-uninstall')]:
                try: command.shell(script, label, accepted_failure=True)
                except Exception as error: report['cleanup_errors'].append(label + ': ' + str(error))
            try:
                _, row = command.shell('bm dump -a', 'cleanup-BMS-after'); cleanup['BMS_after'] = report['commands'].index(row)
                for i in (1, 2):
                    _, row = command.shell(uid_process_scan(cleanup.get('ordinary_uid')), 'cleanup-processes-' + str(i))
                    cleanup['process_scans'].append(report['commands'].index(row))
                    if i == 1: time.sleep(.25)
                _, _, row = command.execute([args.hdc, '-t', command.target, 'fport', 'ls'], 'cleanup-forwards-after')
                cleanup['forwards_after'] = report['commands'].index(row)
            except Exception as error: report['cleanup_errors'].append('actual cleanup inspection: ' + str(error))
            if not report['cleanup_errors']:
                report['cleanup_complete'] = True
                try: verify_cleanup(report, command.target)
                except Exception as error: report['cleanup_errors'].append('cleanup verification: ' + str(error)); report['cleanup_complete'] = False
        elif not attempted and not report['cleanup_errors']:
            # No app/forward/guest mutations were started by this wrapper.
            report['cleanup_complete'] = True; cleanup['guest_mutation_started'] = False
        if report['cleanup_errors']: report['status'] = 'fail'
        if guest:
            write_json(output / 'enclosing-guest-commands.json', guest.report); guest.close()
        write_json(output / 'evidence.json', report)
    if report['status'] == 'pass':
        try: verify_evidence(output / 'evidence.json', args.archive, args.boot)
        except Exception as error:
            # Preserve the initial local pass receipt, then publish the actual
            # final failure without replacing any capture/log/signature bytes.
            (output / 'evidence.json').rename(output / 'initial-evidence.json')
            report['status'] = 'fail'; report['failures'].append('final independent check: ' + str(error))
            write_json(output / 'evidence.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    if len(sys.argv) > 1 and sys.argv[1] == '_publish':
        sys.argv.pop(1)
        for name in ('artifacts', 'capture', 'inputs', 'output'): parser.add_argument('--' + name, type=Path, required=True)
        parser.add_argument('--run-id', required=True); args = parser.parse_args()
        return publish_controlled(args.artifacts, args.capture, args.inputs, args.run_id, args.output)
    for name in ('boot', 'archive', 'hdc', 'artifacts', 'output'): parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(); report = run(args)
    print(json.dumps({k: report.get(k) for k in ('status', 'archive_sha256', 'boot_id', 'cleanup_complete', 'cleanup_errors', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__': raise SystemExit(main())
