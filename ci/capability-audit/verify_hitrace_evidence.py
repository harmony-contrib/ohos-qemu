"""Replay same-boot public API/kernel evidence for the audited FTRACE backend gap."""
import json
from pathlib import Path
import re
import zipfile

from build_hitrace_app_probe import BUNDLE
from build_serial_hap_probe import ARCHITECTURES
from enclosing_acceptance_guest import validate_binding
from hitrace_kernel_contract import trace_configuration, verify_restored_configuration, verify_rows, verify_trace
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest, validate_elf
from power_test_policy import power_timeout
from qemu_test_hap_archive import canonical_library

ROOT = Path(__file__).resolve().parent
GAP = 'behavior:hitrace-arm64-kernel'


def verify_evidence(document, archive_sha, boot_id, arch):
    if (document.get('status') != 'pass' or document.get('failures') != [] or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('enclosing_guest_preserved') is not True or
            document.get('first_artifact_behavior_gate_passed') is not False or
            document.get('power_restoration') != 'unchanged_enclosing_policy' or
            document.get('power_before') != document.get('power_after') or
            document.get('runner_sha256') != digest(ROOT / 'run_hitrace_diagnostic.py') or
            document.get('verifier_sha256') != digest(ROOT / 'hitrace_kernel_contract.py')):
        raise ValueError('HiTrace proof must belong to this unchanged enclosing acceptance run')
    boot = Path(document.get('enclosing_boot', ''))
    if (not boot.is_absolute() or boot.name != 'boot.json' or boot.parent.name != 'boot' or
            boot.is_symlink() or not boot.is_file() or digest(boot) != document.get('enclosing_boot_sha256')):
        raise ValueError('original enclosing boot evidence required')
    env = validate_binding(json.loads(boot.read_text()), archive_sha)
    if (env != document.get('test_environment') or env['boot_id'] != boot_id or env['guest_arch'] != arch or
            env['device_type'] != document.get('device')):
        raise ValueError('HiTrace ABI, profile or live guest binding mismatch')
    root = boot.parent.parent / 'hitrace'
    files = {'actual_results': root / 'actual-results.log', 'kernel_trace': root / 'actual-kernel-trace.log',
        'ordinary_identity': root / 'ordinary-identity.json', 'signed_hap': root / 'ordinary-signed.hap',
        'compiled_inputs': root / 'project/hitrace-probe-inputs.json'}
    for key, path in files.items():
        if path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('changed HiTrace evidence: ' + key)
    run_id = document.get('run_id')
    if re.fullmatch('[a-f0-9]{32}', run_id or '') is None:
        raise ValueError('fresh HiTrace challenge required')
    inputs = json.loads(files['compiled_inputs'].read_text())
    if (inputs.get('status') != 'pass' or inputs.get('arch') != arch or inputs.get('run_id') != run_id or
            inputs.get('bundle') != BUNDLE or inputs.get('request_permissions') != [] or
            inputs.get('first_artifact_behavior_gate_passed') is not False or
            inputs.get('source_sha256') != digest(ROOT / 'hitrace_app_probe.cpp') or
            inputs.get('template_sha256') != digest(ROOT / 'hitrace_app_probe.ets') or
            inputs.get('builder_sha256') != digest(ROOT / 'build_hitrace_app_probe.py')):
        raise ValueError('actual public caller source, role or ABI changed')
    project = root / 'project'
    abi = ARCHITECTURES[arch][1]
    built = {'module': project / 'entry/src/main/module.json5',
        'generated_source': project / 'entry/src/main/ets/pages/Index.ets',
        'native_library': project / 'entry/libs' / abi / 'libhitraceprobe.so',
        'hap': project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'}
    for key, path in built.items():
        if path.is_symlink() or not path.is_file() or digest(path) != inputs.get(key + '_sha256'):
            raise ValueError('compiled HiTrace caller changed: ' + key)
    module = json.loads(built['module'].read_text())['module']
    validate_elf(built['native_library'], arch)
    if module.get('requestPermissions') != []:
        raise ValueError('HiTrace caller must not request privileged permissions')
    if built['generated_source'].read_text() != (ROOT / 'hitrace_app_probe.ets').read_text().replace('__RUN__', run_id):
        raise ValueError('fresh typed caller does not match its nonce-bearing source')
    # Arkdown strips the packaged .so. Compare the signed payload to the hashed
    # actual build HAP, not to the intentionally unstripped compiler output.
    with zipfile.ZipFile(files['signed_hap']) as signed, zipfile.ZipFile(built['hap']) as unsigned:
        names = unsigned.namelist()
        payload = {}
        for name in names:
            data = unsigned.read(name)
            canonical = canonical_library(name, data) if name.startswith('libs/') else name
            if canonical in payload:
                raise ValueError('duplicate compiled HAP payload')
            payload[canonical] = data
        # Pinned PageInfoGenerator adds only this code-sign executable-page bitmap.
        if (len(signed.namelist()) != len(set(signed.namelist())) or
                set(signed.namelist()) != set(payload) | {'.pages.info'} or
                'libs/' + abi + '/libhitraceprobe.so' not in payload or
                any(signed.read(name) != data for name, data in payload.items()) or
                not signed.read('.pages.info') or len(signed.read('.pages.info')) % 8 != 0):
            raise ValueError('signed caller payload differs from the actual build HAP')
    signed_logs = [row for row in document.get('commands', [])
                   if row.get('log') == str(root / 'sign-ordinary-no-permissions.log')]
    if len(signed_logs) != 1 or signed_logs[0].get('exit_code') != 0:
        raise ValueError('actual ordinary code-sign verification required')
    signing_log = root / 'sign-ordinary-no-permissions.log'
    if signing_log.is_symlink() or digest(signing_log) != signed_logs[0].get('sha256'):
        raise ValueError('actual signing transcript changed')
    if not all(marker in signing_log.read_text() for marker in ('verify codesign success',
            'Digest verify result: true', 'verify-app success', 'verify permission sign success')):
        raise ValueError('code signature, digest and ordinary permissions were not verified')
    uid = require_normal_identity(files['ordinary_identity'].read_text(), BUNDLE)
    pid, tid = verify_rows(files['actual_results'].read_text(), run_id, uid)
    actual = verify_trace(files['kernel_trace'].read_text(), run_id, pid, tid)
    if actual != document.get('result'):
        raise ValueError('HiTrace summary differs from actual public calls and kernel records')

    def observation(label):
        rows = [row for row in document.get('guest_commands', [])
                if Path(row.get('log', '')).name.endswith('-' + label + '.log')]
        if len(rows) != 1:
            raise ValueError('one actual guest observation required: ' + label)
        row = rows[0]
        path = Path(row['log'])
        if (path.parent != root / 'guest-commands' or path.is_symlink() or not path.is_file() or
                row.get('exit_code') != 0 or digest(path) != row.get('sha256')):
            raise ValueError('changed guest observation: ' + label)
        text = path.read_text().replace('\r', '')
        suffix = re.search(r'\n__QEMU_CHILD_EXIT_[a-f0-9]{32}__=0\n$', text)
        if suffix is None:
            raise ValueError('guest command did not return successful status: ' + label)
        return text[:suffix.start()]

    status = observation('actual-kernel-thread-identity')
    if (re.findall(r'^Pid:\s+(\d+)$', status, re.M) != [str(tid)] or
            re.findall(r'^Tgid:\s+(\d+)$', status, re.M) != [str(pid)] or
            re.findall(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$', status, re.M) !=
            [(str(uid),) * 4]):
        raise ValueError('kernel trace TID is not owned by the real ordinary process')
    for label in ('boot-before', 'final-same-boot', 'enclosing-final-boot'):
        if observation(label).strip() != boot_id:
            raise ValueError('HiTrace crossed kernel boot identities')
    if (power_timeout(observation('power-before')) != document.get('power_before') or
            power_timeout(observation('enclosing-power-unchanged')) != document.get('power_after')):
        raise ValueError('enclosing power policy was not preserved in actual guest observations')
    if set(re.findall(r'^KernelPageSize:\s+([0-9]+) kB$', observation('actual-kernel-page-size'), re.M)) != {'4'}:
        raise ValueError('actual 4 KiB kernel page size required')
    before, enabled, after = [trace_configuration(observation(label))
                               for label in ('trace-before', 'trace-enabled', 'trace-restored')]
    if (before != document.get('trace_before') or enabled != document.get('trace_enabled') or
            after != document.get('trace_restored') or before['on'] != '0' or before['tags'] != '0' or
            before['pid'] != '-1' or enabled['on'] != '1' or not int(enabled['tags']) & (1 << 62)):
        raise ValueError('real tracing policy was not bounded and enabled for public app traces')
    restored = verify_restored_configuration(before, after, 4096, arch)
    if restored != document.get('trace_restoration'):
        raise ValueError('actual kernel trace policy restoration differs')
    return dict(closed=[GAP], public_api_kernel_records=actual['public_api_kernel_records'],
                not_claimed='all_HiTrace_APIs_or_other_architecture_profile_runs')
