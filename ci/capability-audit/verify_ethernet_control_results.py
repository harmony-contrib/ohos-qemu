"""Replay actual public controls and kernel flags; not full Ethernet/traffic proof."""
import json
from pathlib import Path
import re
import zipfile
from build_ethernet_control_probe import BUNDLE, ROLES, PERMISSIONS, TEMPLATE, SCOPE, module, page
from run_root_probe import digest
from sign_ethernet_control_probe import configure_profile
from verify_always_on_vpn_results import identity, verify_restart

EVIDENCE_SCOPE = 'three_real_Ethernet_roles_kernel_admin_flags_and_caller_restart_NOT_traffic_or_full_gate'
METHODS = ('disableEthernetInterface', 'enableEthernetInterface', 'isEthernetEnabled')


def expected(role, phase):
    if role not in ROLES or phase not in ('seed', 'restart', 'denial') or (
            (role == 'system') != (phase != 'denial')):
        raise ValueError('exact Ethernet role and compatible phase required')
    rows = [('identity', None)]
    if role != 'system':
        rows += [('denied.' + str(method), [1, 202 if role == 'normal' else 201, 1]) for method in range(3)]
    else:
        rows.append((phase + '.initial', True))
        for repeat in range(3 if phase == 'seed' else 1):
            rows += [(name + '.' + str(repeat), enabled) for name, enabled in (
                ('disabled', False), ('disabled-again', False), ('enabled', True), ('enabled-again', True))]
        rows.append(('cleanup', True))
    return rows + [('summary', [1, 1 if phase == 'seed' else 0])]


def verify(text, run_id, role, phase, identity_text):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or not text.endswith('\n'):
        raise ValueError('fresh challenge and complete raw Ethernet observations required')
    uid = identity(identity_text, role)
    rows = [json.loads(line) for line in text.splitlines()]
    contract = expected(role, phase)
    if len(rows) != len(contract):
        raise ValueError('missing/extra Ethernet observations')
    for row, (name, expected_value) in zip(rows, contract):
        if (not isinstance(row, dict) or set(row) != {'runId', 'role', 'name', 'values', 'error'} or
                row['runId'] != run_id or row['role'] != role or row['name'] != name or row['error'] != '' or
                not isinstance(row['values'], list) or any(type(value) is not int for value in row['values'])):
            raise ValueError('failed/malformed/foreign/reordered Ethernet result: ' + name)
        values = row['values']
        if expected_value is None:
            if len(values) != 3 or values[:2] != [uid, uid] or values[2] <= 1:
                raise ValueError('Ethernet caller must match actual non-root installed identity')
        elif type(expected_value) is bool:
            if (len(values) != 3 or values[:2] != [1, int(expected_value)] or
                    not 0 <= values[2] <= 0xFFFFFFFF or bool(values[2] & 1) != expected_value):
                raise ValueError('global policy and actual kernel administrative flags differ: ' + name)
        elif values != expected_value:
            raise ValueError('actual numeric denial/summary differs: ' + name)
    return rows


def verify_inputs(value, nonce, arch, role):
    generated, declaration = (Path(value[key]) for key in ('generated_source', 'sdk_declaration'))
    if (type(value.get('schema_version')) is not int or value['schema_version'] != 1 or
            value.get('run_id') != nonce or value.get('arch') != arch or value.get('role') != role or
            arch not in ('arm64', 'armv7a', 'x86_64') or value.get('scope') != SCOPE or
            value.get('request_permissions') != (list(PERMISSIONS) if role == 'system' else []) or
            value.get('template_sha256') != digest(TEMPLATE) or declaration.name != '@ohos.net.ethernet.d.ts' or
            any(path.is_symlink() or not path.is_file() or digest(path) != value.get(key)
                for path, key in ((generated, 'generated_source_sha256'), (declaration, 'sdk_declaration_sha256'))) or
            generated.read_text() != page(nonce, role)):
        raise ValueError('Ethernet observations require exact current typed source/SDK/permissions')


def verify_evidence(document, archive_sha, boot_id, arch, device, target):
    if (document.get('status') != 'pass' or document.get('scope') != EVIDENCE_SCOPE or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('device') != device or document.get('target') != target or
            document.get('failures') != [] or document.get('caller_cleanup_verified') is not True or
            set(document.get('roles', {})) != set(ROLES) or
            re.fullmatch('[0-9a-fA-F]{64}', document.get('udid', '')) is None):
        raise ValueError('all real Ethernet caller roles on the exact new package are required')
    nonces = set()
    for role, record in document['roles'].items():
        paths = {}
        for field in ('inputs', 'application_identity', 'signed_hap', 'signing_receipt'):
            path = Path(record[field])
            if path.is_symlink() or not path.is_file() or digest(path) != record.get(field + '_sha256'):
                raise ValueError('Ethernet evidence changed/missing: ' + field)
            paths[field] = path
        nonce = record['run_id']; nonces.add(nonce)
        if record.get('status') != 'pass' or record.get('actual_uid') != identity(paths['application_identity'].read_text(), role):
            raise ValueError('installed Ethernet identity differs')
        verify_inputs(json.loads(paths['inputs'].read_text()), nonce, arch, role)
        receipt = json.loads(paths['signing_receipt'].read_text())
        profile = receipt.get('verified_profile', {})
        with zipfile.ZipFile(paths['signed_hap']) as hap:
            compiled = json.loads(hap.read('module.json'))
        unsigned = Path(record['unsigned_hap'])
        if (unsigned.is_symlink() or not unsigned.is_file() or digest(unsigned) != record.get('unsigned_hap_sha256') or
                receipt.get('status') != 'pass' or receipt.get('role') != role or
                receipt.get('scope') != 'actual_signature_profile_and_codesign_NOT_guest' or
                receipt.get('signed_sha256') != digest(paths['signed_hap']) or
                receipt.get('unsigned_sha256') != digest(unsigned) or
                compiled['module'].get('requestPermissions') != module(role)['module']['requestPermissions'] or
                configure_profile(json.loads(json.dumps(profile)), role, document['udid'], compiled) != profile):
            raise ValueError('actual Ethernet signature and role permissions differ')
        phases = record.get('phases', {})
        if set(phases) != ({'seed', 'restart'} if role == 'system' else {'denial'}):
            raise ValueError('missing Ethernet phase')
        for phase, row in phases.items():
            raw = Path(row['raw_results'])
            if raw.is_symlink() or not raw.is_file() or digest(raw) != row.get('raw_results_sha256'):
                raise ValueError('raw Ethernet observations changed/missing')
            actual = verify(raw.read_text(), nonce, role, phase, paths['application_identity'].read_text())
            if actual != row.get('results'):
                raise ValueError('Ethernet summary differs from actual observations')
        if role == 'system':
            verify_restart(phases['seed']['results'], phases['restart']['results'])
    if len(nonces) != len(ROLES):
        raise ValueError('independent fresh challenge required for every role')
    verify_commands(document)
    return ['arkts_export:@ohos.net.ethernet:' + name for name in METHODS]


def verify_commands(document):
    """Bind copied observations, restart and cleanup to actual hashed HDC replies."""
    from run_normal_hap_probe import APP_FILES, previous_probe_absent
    commands = document.get('commands')
    if not isinstance(commands, list) or not commands:
        raise ValueError('actual Ethernet command journal is required')
    journal = []
    for index, row in enumerate(commands):
        path = Path(row['log'])
        if (path.is_symlink() or not path.is_file() or digest(path) != row.get('sha256') or
                not isinstance(row.get('argv'), list) or any(not isinstance(arg, str) for arg in row['argv']) or
                type(row.get('exit_code')) is not int or row.get('timed_out') or
                not re.fullmatch(r'\d+-.+\.log', path.name)):
            raise ValueError('actual Ethernet command/log is malformed, missing or changed')
        journal.append((index, path.name.split('-', 1)[1][:-4], row, path.read_text().replace('\r', '')))

    def one(label, script=None, reply=None):
        matches = [row for row in journal if row[1] == label]
        if len(matches) != 1:
            raise ValueError('one successful command required: ' + label)
        index, _, row, output = matches[0]
        if row['exit_code'] != 0 or re.search(r'\[Fail\]|Device not found or connected', output):
            raise ValueError('required Ethernet command failed: ' + label)
        if script is not None and row['argv'][1:] != ['-t', document['target'], 'shell', script]:
            raise ValueError('Ethernet command escaped guest/caller: ' + label)
        if reply is not None and output.strip() != reply:
            raise ValueError('actual Ethernet reply differs: ' + label)
        return index, row, output

    for role, record in document['roles'].items():
        installed, install, install_reply = one(role + '-install')
        if (install['argv'][1:] != ['-t', document['target'], 'install', record['signed_hap']] or
                not re.search('success', install_reply, re.I) or re.search('failed to install', install_reply, re.I)):
            raise ValueError('actual exact-role Ethernet HAP installation is required')
        identity_index, _, reply = one(role + '-identity', 'bm dump -n ' + BUNDLE)
        if reply != Path(record['application_identity']).read_text() or installed >= identity_index:
            raise ValueError('installed identity must originate from this successful HAP installation')
        phase_indices = {}
        for phase, result in record['phases'].items():
            before, _, _ = one(role + '-' + phase + '-boot-before',
                'cat /proc/sys/kernel/random/boot_id', document['boot_id'])
            launched, _, launch_reply = one(role + '-' + phase + '-launch',
                'aa start -a EntryAbility -b ' + BUNDLE)
            if 'start ability successfully' not in launch_reply.lower():
                raise ValueError('actual Ethernet caller launch is required')
            after, _, _ = one(role + '-' + phase + '-boot-after',
                'cat /proc/sys/kernel/random/boot_id', document['boot_id'])
            raw = Path(result['raw_results']).read_text()
            polls = [row for row in journal if row[1] == role + '-' + phase + '-poll' and
                     row[2]['exit_code'] == 0 and row[3] == raw]
            remote = APP_FILES + 'ethernet-control-' + record['run_id'] + '-results.log'
            if (not identity_index < before < launched < after or not any(launched < row[0] < after and
                    row[2]['argv'][1:] == ['-t', document['target'], 'shell', 'cat ' + remote + ' 2>/dev/null']
                    for row in polls)):
                raise ValueError('raw results must be returned by this actual phase/caller, not copied summaries')
            phase_indices[phase] = (before, launched, after)
        if role == 'system':
            stopped, _, _ = one('system-force-stop-own-caller', 'aa force-stop ' + BUNDLE,
                               'force stop process successfully.')
            old_pid = record['phases']['seed']['results'][0]['values'][2]
            absent, _, _ = one('system-old-caller-absence', 'if test -d /proc/' + str(old_pid) +
                              '; then echo PRESENT; else echo ABSENT; fi', 'ABSENT')
            if not phase_indices['seed'][2] < stopped < absent < phase_indices['restart'][1]:
                raise ValueError('old caller absence must precede actual restart completion')
    cleanup_index, _, _ = one('stop-own-previous-audit-app', 'aa force-stop ' + BUNDLE,
                             'force stop process successfully.')
    if cleanup_index <= max(row[0] for row in journal if row[1].endswith('-boot-after')):
        raise ValueError('caller cleanup must follow the actual completed phases')
    pairs = []
    pending = None
    for index, label, row, reply in journal:
        if index <= cleanup_index:
            continue
        if row['exit_code'] != 0:
            raise ValueError('caller cleanup command failed')
        if label == 'previous-own-kernel-processes':
            script = 'task_probe_pids=$(pidof ' + BUNDLE + '); ' + (
                'if test -n "$task_probe_pids"; then printf "%s\\n" "$task_probe_pids"; else echo ABSENT; fi')
            if row['argv'][1:] != ['-t', document['target'], 'shell', script]:
                raise ValueError('cleanup kernel query used another guest')
            pending = reply
        elif label == 'previous-own-ability-and-process-records':
            if row['argv'][1:] != ['-t', document['target'], 'shell', 'aa dump -a -u 100'] or pending is None:
                raise ValueError('ordered kernel and ability cleanup queries required')
            pairs.append(previous_probe_absent(pending, reply)); pending = None
    if len(pairs) < 2 or pairs[-2:] != [True, True]:
        raise ValueError('two actual consecutive caller absence observations required')
