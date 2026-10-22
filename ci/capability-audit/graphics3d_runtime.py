"""One real Graphics3D case on the parent's held QemuGuest; no resource owner.

There is deliberately no CLI, QEMU constructor/start/close, subprocess, Docker,
SDK substitute, library injection or capability-closure decision in this module.
The original suite command runner owns SDK/signing children; the original guest
owns every HDC/QMP operation. The parent serializes this callable with other UI.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import secrets
import shlex
import sys
import time
import zipfile

from boot_package import QemuGuest
from enclosing_acceptance_guest import validate_binding
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady, command_exit, select_node, bounds
from guest_process_identity import identity_shell
from hap_identity_binding import bms_application_identity
from hdc_transport import failed as hdc_failed
from graphics3d_asset import asset, invalid_asset, descriptors, specification
from graphics3d_contract import ACTIONS, commands
from verify_graphics3d_raw import decode, parse_rows, ppm, review
import batch_apps_contact_picker_coordinator as signing

HERE = Path(__file__).resolve().parent
BUNDLE = 'org.harmonycontrib.capabilityaudit'
VIEW = 'graphics3d-audit-view'
BOOT = 'cat /proc/sys/kernel/random/boot_id'

def require(value, message):
    if not value:
        raise ValueError(message)

def descriptor(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1,
            'actual regular single-link artifact required: ' + str(path))
    data = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)

def application(text):
    result = bms_application_identity(text, BUNDLE)
    document = decode(text[text.index('{'):])
    info = document['applicationInfo']
    require(info.get('isSystemApp') is False and info.get('appPrivilegeLevel') == 'normal' and
            document.get('reqPermissions', []) == [], 'actual ordinary permission-free identity required')
    paths = {node['hapPath'] for node in objects(document)
             if isinstance(node.get('hapPath'), str) and node['hapPath'].endswith('.hap')}
    require(len(paths) == 1, 'one actual installed HAP path required')
    path = paths.pop()
    require(path.startswith('/data/app/') and PurePosixPath(path).as_posix() == path and
            not any(part in ('', '.', '..') for part in path.split('/')[1:]), 'canonical actual installed HAP path required')
    result['hap_path'] = path
    return result

def visible_roots(layout):
    pending = [(root, '') for root in (layout if isinstance(layout, list) else [layout])]
    rectangles = []
    while pending:
        node, inherited = pending.pop()
        require(isinstance(node, dict) and isinstance(node.get('attributes'), dict) and
                isinstance(node.get('children', []), list), 'malformed actual UI hierarchy')
        attrs = node['attributes']
        bundle = attrs.get('bundleName') or inherited
        if bundle == BUNDLE and attrs.get('visible') == 'true':
            rectangles.append(list(bounds(attrs.get('bounds'))))
        pending.extend((child, bundle) for child in node.get('children', []))
    return rectangles

def debug_caller(unsigned, run):
    module, contents = signing.hap_contents(unsigned)
    app, entry = module['app'], module['module']
    require(app.get('bundleName') == BUNDLE and app.get('debug') is True and app.get('buildMode') == 'debug' and
            app.get('minAPIVersion') == app.get('targetAPIVersion') == 26 and app.get('apiReleaseType') == 'Release' and
            app.get('compileSdkType') == 'OpenHarmony' and app.get('compileSdkVersion', '').startswith('26.0.0.') and
            entry.get('name') == entry.get('type') == 'entry' and entry.get('requestPermissions', []) == [] and
            entry.get('extensionAbilities', []) == [] and entry.get('dependencies', []) == [] and
            len(entry.get('abilities', [])) == 1 and entry['abilities'][0].get('name') == 'EntryAbility' and
            entry['abilities'][0].get('launchType') == 'singleton', 'exact original API26 debug ordinary caller required')
    with zipfile.ZipFile(unsigned) as archive:
        require(archive.read('resources/rawfile/graphics3d-audit.glb') == asset(run) and
                archive.read('resources/rawfile/graphics3d-invalid.glb') == invalid_asset(), 'compiled real GLB challenge changed')
    return {'module': module, 'payload_sha256': contents, 'assets': descriptors(run)}

def sign_caller(unsigned, run, udid, dist, jar, output, command):
    """Preserve the existing Release caller guard; check this exact debug caller separately."""
    debug_caller(unsigned, run)
    dist, jar, inputs = signing.signer_inputs(dist, jar)
    output.mkdir(exist_ok=False)
    signed = output / 'signed.hap'
    command(signing.normal_sign_argv(unsigned, BUNDLE, [], udid, dist, jar, signed), 'sign-normal-debug-HAP')
    signing.verify_signed_payload(unsigned, signed)
    debug_caller(signed, run)
    chain, profile = output / 'verified-chain.cer', output / 'verified-profile.p7b'
    log = command(['java', '-jar', str(jar), 'verify-app', '-inFile', str(signed),
                   '-outCertChain', str(chain), '-outProfile', str(profile)], 'verify-app')
    require(all(marker in log for marker in ('verify codesign success', 'Digest verify result: true',
                'verify permission sign success', 'verify-app success')), 'actual signed ABC/digest/permission verification missing')
    signing.application_leaf(log)
    descriptor(chain); descriptor(profile)
    verified = output / 'verified-profile.json'
    log = command(['java', '-jar', str(jar), 'verify-profile', '-inFile', str(profile),
                   '-outFile', str(verified)], 'verify-profile')
    require('verify-profile success' in log, 'actual profile verification failed')
    value = signing.verified_profile_content(decode(verified.read_text()))
    certificates = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',
                              (dist / 'OpenHarmonyProfileDebug.pem').read_text(), re.S)
    require(len(certificates) == 3, 'fixed profile chain shape changed')
    leaf = output / 'profile-leaf.pem'; leaf.write_text(certificates[-1] + '\n')
    fingerprint = command(['openssl', 'x509', '-in', str(leaf), '-noout', '-fingerprint', '-sha256'], 'profile-leaf')
    require(fingerprint.strip().split('=')[-1].replace(':', '').upper() == signing.PROFILE_LEAF, 'fixed profile leaf changed')
    cms = output / 'cms-profile.json'
    command(['openssl', 'cms', '-verify', '-inform', 'DER', '-in', str(profile), '-nointern',
             '-certfile', str(leaf), '-noverify', '-out', str(cms)], 'profile-CMS')
    require(decode(cms.read_text()) == value, 'actual CMS and Java decoded profile differ')
    signing.verify_profile(value, BUNDLE, [], udid, apl='normal', system_app=False)
    return {'unsigned_hap': descriptor(unsigned), 'signed_hap': descriptor(signed),
            'unsigned_payload': debug_caller(unsigned, run), 'signed_payload': debug_caller(signed, run),
            'signer_inputs': inputs, 'actual_profile': value, 'verified_chain': descriptor(chain),
            'embedded_profile': descriptor(profile), 'verified_profile': descriptor(verified), 'CMS': descriptor(cms)}

def verify_capture_fences(report):
    """Pure causal validation; booleans cannot replace command/raw/QMP facts."""
    requests, frames = report['requests'], report['frames']
    require(len(requests) == len(ACTIONS) and len(frames) == 6 and
            [r['index'] for r in requests] == list(range(len(ACTIONS))), 'full finite actual request sequence required')
    expected = commands(report['run_id'], report['boot_id'], [r['request']['operation_id'] for r in requests])
    require([r['request'] for r in requests] == expected, 'actual requests differ from source challenge')
    require([r['action_index'] for r in frames] == [1, 3, 5, 8, 10, 12], 'missing/extra/reordered actual QMP frame')
    identity = requests[0]['actual_process']
    for index, request in enumerate(requests):
        require(type(request['dispatched_ns']) is int and type(request['raw_end_observed_ns']) is int and
                request['raw_end_observed_ns'] > request['dispatched_ns'] and request['actual_process'] == identity,
                'actual app generation/completion fence drift')
        if index:
            require(request['dispatched_ns'] > requests[index - 1]['raw_end_observed_ns'], 'overlapping Want requests')
        for field in ('Want_command_index', 'end_command_index'):
            require(type(request[field]) is int and 0 <= request[field] < len(report['commands']), 'actual original command index absent')
        want, end = (report['commands'][request[field]] for field in ('Want_command_index', 'end_command_index'))
        require(want['label'] == 'Want-' + str(index) + '-' + request['request']['action'] and
                end['label'] == 'end-' + str(index) and
                want['started_ns'] >= request['dispatched_ns'] and
                end['finished_ns'] <= request['raw_end_observed_ns'], 'Want/end raw command fence differs')
    for frame in frames:
        request = requests[frame['action_index']]
        qmp, ui = frame['qmp'], frame['UI']
        require(frame['operation_id'] == request['request']['operation_id'] and frame['raw_end_observed_ns'] ==
                request['raw_end_observed_ns'] and frame['process_after'] == identity and
                qmp['execute'] == 'screendump' and qmp['arguments'] == {'filename': frame['capture']['path'], 'format': 'ppm'} and
                qmp['reply'] == {} and type(qmp['started_ns']) is int and type(qmp['finished_ns']) is int and
                request['raw_end_observed_ns'] <= ui['observed_ns'] <= qmp['started_ns'] < qmp['finished_ns'] <
                requests[frame['action_index'] + 1]['dispatched_ns'], 'actual QMP/image/UI command causal fence mismatch')
        require(descriptor(frame['capture']['path']) == frame['capture'] and descriptor(ui['layout']['path']) == ui['layout'],
                'original QMP/UI bytes changed')
        tree = decode(Path(ui['layout']['path']).read_text())
        require(ui['window_rect'] in visible_roots(tree), 'actual same app window missing from original UI hierarchy')
        if frame['action_index'] in (5, 12):
            try:
                select_node(tree, BUNDLE, identifier=VIEW)
            except NodeNotReady:
                require(ui['selected_node'] is None, 'destroyed view selection forged')
            else:
                raise ValueError('actual destroyed Component3D still mounted')
        else:
            require(select_node(tree, BUNDLE, identifier=VIEW) == ui['selected_node'] and
                    ui['selected_node']['rect'] == frame['roi'], 'actual whole Component3D ROI differs')
    require(all(frame['roi'] == frames[0]['roi'] and frame['UI']['window_rect'] == frames[0]['UI']['window_rect']
                for frame in frames), 'actual foreground viewport/window drift')

def run_owned_graphics3d(*, guest, suite_command, same_guest, held_binding, suite_report,
                        save_suite, suite_work, archive, sdk, signer_dist, signer_jar,
                        hvigor_home, node_home, process_env=None, product_inputs=None):
    """Execute the real 15-command/6-QMP case using only the passed original owner.

    The function returns a fail report after preserving/cleaning a failed case.
    Cleanup uncertainty always raises. The parent must treat any returned fail
    as a real failed supplemental case, never a full-ledger/first-artifact pass.
    """
    from run_normal_hap_probe import BUNDLE as NORMAL_BUNDLE, require_normal_identity, stop_previous_probe, cleanup_microphone_application
    require(BUNDLE == NORMAL_BUNDLE and isinstance(guest, QemuGuest) and all(callable(c) for c in
            (suite_command, same_guest, held_binding, save_suite)), 'original held guest and actual suite callbacks required')
    held_binding(guest)
    archive, sdk, work = Path(archive).resolve(), Path(sdk).resolve(), Path(suite_work).resolve()
    archive_record = descriptor(archive)
    env = validate_binding(guest.report, archive_record['sha256'])
    require(guest.process.poll() is None and guest.target == env['target'] and guest.udid == env['udid'] and
            Path(guest.args.archive).resolve() == archive and Path(guest.args.output).resolve() == work / 'boot' and
            suite_report.get('work') == str(work) and suite_report.get('scope') == 'new_packaged_qemu_behavior' and
            suite_report.get('package', {}).get('sha256') == archive_record['sha256'] and
            suite_report.get('test_environment') == env, 'actual new package/root held boot binding differs')
    output = work / 'graphics3d'
    output.mkdir(exist_ok=False)
    run = secrets.token_hex(16)
    requests = commands(run, env['boot_id'], [secrets.token_hex(16) for _ in ACTIONS])
    remote = '/data/app/el2/100/base/' + BUNDLE + '/haps/entry/files/graphics3d-' + run + '.jsonl'
    report = {'schema_version': 1, 'scope': 'same_original_guest_Graphics3D_nonempty_asset_render_lifecycle_slice',
              'status': 'running', 'run_id': run, 'archive': archive_record, 'boot_id': env['boot_id'],
              'test_environment': dict(env), 'commands': [], 'process_commands': [], 'requests': [],
              'frames': [], 'failures': [], 'cleanup_complete': False, 'closed_ids': [],
              'full_graphics3d_verified': False, 'first_artifact_behavior_gate_passed': False}
    installed, complete_raw, actual_identity = False, None, None
    previous_cleanup_started, previous_cleanup_complete = False, False
    signed_sha, roi, window_rect = None, None, None

    def save():
        path = output / 'evidence.json'
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
        suite_report.setdefault('supplemental_checks', {})['graphics3d'] = dict(
            status=report['status'], evidence=str(path), sha256=descriptor(path)['sha256'],
            not_a_registered_first_artifact_or_gap_closure_check=True)
        guest.save(); save_suite()

    def healthy():
        held_binding(guest); guest.healthy()

    def command(argv, label, timeout=30, accepted_failure=False):
        healthy()
        argv = list(map(str, argv)); index = len(guest.report['commands'])
        started = time.monotonic_ns()
        guest.command(argv, 'graphics3d-' + label, timeout=timeout, allow_failure=True)
        finished = time.monotonic_ns()
        require(len(guest.report['commands']) == index + 1, 'one original guest command record required')
        row = guest.report['commands'][index]
        require(row.get('argv') == argv and type(row.get('exit_code')) is int and not row.get('timed_out'), 'actual guest command record missing')
        raw = descriptor(row['log'])
        require(raw['sha256'] == row['sha256'], 'original guest raw command changed')
        report['commands'].append(dict(label=label, guest_command_index=index, observation=dict(row),
                                       started_ns=started, finished_ns=finished))
        save()
        text = Path(raw['path']).read_text().replace('\r\n', '\n')
        require(accepted_failure or row['exit_code'] == 0 and not hdc_failed(text, ''), 'actual owned guest/HDC operation failed: ' + label)
        return text

    def shell(script, label, accepted_failure=False):
        marker = '__GRAPHICS3D_EXIT_' + secrets.token_hex(16) + '__='
        guarded = 'test "$(' + BOOT + ')" = ' + shlex.quote(env['boot_id']) + ' || exit 97; ' + script
        wrapped = '(' + guarded + '); task_graphics_rc=$?; printf "\\n' + marker + '%s\\n" "$task_graphics_rc"'
        raw = command([guest.args.hdc, '-t', guest.target, 'shell', wrapped], label, accepted_failure=True)
        require(report['commands'][-1]['observation']['exit_code'] == 0, 'actual HDC host transport failed: ' + label)
        body, code = command_exit(raw, marker)
        require(code != 97 and (accepted_failure or code == 0), 'actual guest shell failed/boot changed: ' + label)
        return body

    def host(argv, label, timeout=300):
        healthy()
        argv = list(map(str, argv)); started = time.monotonic_ns()
        row = suite_command(argv, 'graphics3d-' + label, timeout=timeout, env=process_env)
        finished = time.monotonic_ns()
        require(type(row) is dict and row.get('argv') == argv and type(row.get('exit_code')) is int and
                row['exit_code'] == 0 and not row.get('timed_out'), 'actual root-owned SDK/signer process failed: ' + label)
        artifact = descriptor(row['log'])
        require(row.get('sha256') == artifact['sha256'], 'actual suite process raw log changed')
        report['process_commands'].append(dict(label=label, observation=dict(row), started_ns=started, finished_ns=finished))
        save()
        return Path(row['log']).read_text()

    ui = GuestUi(command, guest.args.hdc, guest.target, output / 'ui')

    def layout(label, mounted, initial=False):
        deadline = time.monotonic() + 30
        while True:
            try:
                tree, path = ui.layout(bundle=None if initial else BUNDLE, label=label)
                if mounted:
                    node = select_node(tree, BUNDLE, identifier=VIEW)
                else:
                    try:
                        select_node(tree, BUNDLE, identifier=VIEW)
                    except NodeNotReady:
                        node = None
                    else:
                        raise ValueError('actual Component3D remained mounted')
                roots = visible_roots(tree)
                require(initial or roots, 'actual audit app is not a visible foreground window')
                selected_window = max(roots, key=lambda r: r[2] * r[3]) if roots else None
                return {'layout': descriptor(path), 'selected_node': node, 'window_rect': selected_window,
                        'command_count_after_layout': len(report['commands']), 'observed_ns': time.monotonic_ns()}
            except (LayoutNotReady, NodeNotReady):
                if time.monotonic() >= deadline:
                    raise ValueError('actual UI hierarchy/view not ready before finite deadline')
                time.sleep(.25)

    def identity(label):
        nonlocal actual_identity
        bms = shell('bm dump -n ' + BUNDLE, label + '-BMS')
        value = application(bms)
        require(require_normal_identity(bms) == value['uid'], 'ordinary BMS UID disagrees')
        raw = shell(identity_shell(BUNDLE), label + '-process')
        require(re.fullmatch(r'[1-9][0-9]*(?: [0-9]+){5}\n?', raw) is not None, 'actual PID/birth/four-UID observation missing')
        pid, birth, *uids = map(int, raw.split())
        require(birth > 0 and uids == [value['uid']] * 4, 'actual native process generation/UID differs')
        value.update(pid=pid, birth_ticks=birth)
        digest = shell('test -f ' + shlex.quote(value['hap_path']) + ' && test ! -L ' + shlex.quote(value['hap_path']) +
                       ' && sha256sum ' + shlex.quote(value['hap_path']), label + '-installed-HAP')
        require(digest.split() == [signed_sha, value['hap_path']], 'installed HAP differs from actual signed ABC')
        if actual_identity is None:
            actual_identity = value
        require(value == actual_identity, 'original app process generation/BMS/token/HAP changed')
        return dict(value)

    def receive(name):
        target = output / name
        require(not target.exists(), 'fresh journal output required')
        command([guest.args.hdc, '-t', guest.target, 'file', 'recv', remote, target], 'receive-' + name)
        descriptor(target)
        return target

    def preserve():
        nonlocal complete_raw
        present = shell('if test -f ' + shlex.quote(remote) + ' && test ! -L ' + shlex.quote(remote) +
                        '; then echo PRESENT; else echo ABSENT; fi', 'stopped-journal-presence').strip()
        if present == 'PRESENT':
            path = receive('journal-after-stop.jsonl')
            report['raw_after_stop'] = descriptor(path)
            if complete_raw is not None:
                if path.read_bytes() != complete_raw.read_bytes():
                    report['status'] = 'fail'
                    report['failures'].append('late journal row after explicit cleanup/quiet')
        else:
            require(present == 'ABSENT' and complete_raw is None, 'completed raw journal vanished')

    save()
    try:
        same_guest('before-graphics3d')
        report['source'] = {str(p.relative_to(HERE)): descriptor(p) for p in [
            HERE / 'graphics3d_runtime.py', HERE / 'graphics3d_contract.py', HERE / 'graphics3d_asset.py',
            HERE / 'verify_graphics3d_raw.py', HERE / 'graphics3d/EntryAbility.ets',
            HERE / 'graphics3d/Index.ets', HERE / 'graphics3d/GraphicsController.ets',
            HERE / 'build_hap_probe.py', HERE / 'sign_web_probe.py', HERE / 'guest_ui.py',
            HERE / 'boot_package.py', HERE / 'run_normal_hap_probe.py']}
        report['SDK'] = {}
        for part in ('native', 'ets'):
            path = sdk / part / 'oh-uni-package.json'; metadata = decode(path.read_text())
            require(metadata.get('apiVersion') == '26' and metadata.get('platformVersion') == '26.0.0' and
                    metadata.get('releaseType') == 'Release' and re.fullmatch(r'26\.0\.0\.[0-9]+', metadata.get('version', '')),
                    'actual official API26 Release SDK required')
            report['SDK'][part] = {'metadata': metadata, 'artifact': descriptor(path)}
        report['SDK']['declarations'] = {name: descriptor(sdk / 'ets' / name) for name in (
            'api/graphics3d/Scene.d.ts', 'api/graphics3d/SceneNodes.d.ts',
            'api/graphics3d/SceneResources.d.ts', 'component/component3d.d.ts')}
        project = output / 'project'
        build_log = host([sys.executable, HERE / 'build_hap_probe.py', '--graphics3d-only', '--arch', env['guest_arch'],
              '--sdk', sdk, '--udid', guest.udid, '--output', project, '--probe-run-id', run,
              '--hvigor-home', hvigor_home, '--node-home', node_home], 'build-fresh-real-caller', timeout=1800)
        require('BUILD SUCCESSFUL' in build_log, 'actual official Hvigor compilation success missing')
        for name, destination in [('EntryAbility.ets', 'entryability'), ('Index.ets', 'pages'), ('GraphicsController.ets', 'graphics3d')]:
            generated = project / 'entry/src/main/ets' / destination / name
            require(generated.read_text() == (HERE / 'graphics3d' / name).read_text().replace('__GRAPHICS3D_RUN__', run), 'compiled actual typed source differs')
        report['generated_inputs'] = descriptor(project / 'graphics3d-inputs.json')
        unsigned = project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
        report['signing'] = sign_caller(unsigned, run, guest.udid, signer_dist, signer_jar, output / 'signing', host)
        signed = Path(report['signing']['signed_hap']['path']); signed_sha = report['signing']['signed_hap']['sha256']
        previous_cleanup_started = True
        report['previous_app_cleanup'] = stop_previous_probe(shell)
        previous_cleanup_complete = True
        command([guest.args.hdc, '-t', guest.target, 'uninstall', BUNDLE], 'uninstall-previous-reserved-probe', accepted_failure=True)
        report['initial_unmounted'] = layout('before-launch-unmounted', False, initial=True)
        installed = True
        reply = command([guest.args.hdc, '-t', guest.target, 'install', signed], 'install-signed-ordinary-HAP')
        require(re.search('success', reply, re.I) and not re.search(r'\[Fail\]|failed', reply, re.I), 'actual HAP install failed')
        require(shell('if test -e ' + shlex.quote(remote) + '; then echo STALE; else echo ABSENT; fi', 'raw-absent-before-launch').strip() == 'ABSENT', 'stale raw journal exists')
        report['remote_journal'] = remote
        for index, request in enumerate(requests):
            if index:
                identity('before-' + str(index))
            started = time.monotonic_ns()
            launch = shlex.join(['aa', 'start', '-b', BUNDLE, '-a', 'EntryAbility', '--ps', 'request',
                                 json.dumps(request, separators=(',', ':'), allow_nan=False)])
            reply = shell(launch, 'Want-' + str(index) + '-' + request['action'])
            want_command_index = len(report['commands']) - 1
            require('start ability successfully' in reply, 'actual singleton Want dispatch failed')
            deadline = time.monotonic() + (120 if request['action'] in ('load', 'invalid') else 30)
            while True:
                healthy()
                tail = shell('if test -f ' + shlex.quote(remote) + ' && test ! -L ' + shlex.quote(remote) +
                             '; then tail -n 1 ' + shlex.quote(remote) + '; else echo MISSING; fi', 'end-' + str(index))
                try:
                    end = decode(tail.strip())
                except (ValueError, TypeError):
                    end = None
                if isinstance(end, dict) and end.get('kind') == 'end' and end.get('operation_id') == request['operation_id']:
                    require(end.get('run_id') == run and end.get('boot_id') == env['boot_id'] and end.get('action') == request['action'], 'foreign completion row')
                    break
                require(time.monotonic() < deadline, 'real caller command never reached raw end: ' + request['action'])
                time.sleep(.25)
            completed = time.monotonic_ns()
            end_command_index = len(report['commands']) - 1
            current = identity('after-' + str(index))
            report['requests'].append(dict(index=index, request=request, dispatched_ns=started,
                                           raw_end_observed_ns=completed, end=end, actual_process=current,
                                           Want_command_index=want_command_index, end_command_index=end_command_index,
                                           command_count_after_end=len(report['commands'])))
            if request['action'] == 'frame':
                mounted = index not in (5, 12)
                observation = layout('frame-' + str(index), mounted)
                if roi is None:
                    roi = observation['selected_node']['rect']; window_rect = observation['window_rect']
                require(observation['window_rect'] == window_rect and
                        (observation['selected_node']['rect'] == roi if mounted else True), 'actual viewport/window moved or resized')
                frame = output / ('frame-' + str(index) + '.ppm')
                require(not frame.exists(), 'fresh QMP frame path required')
                qmp_started = time.monotonic_ns()
                wire = []
                def keep_qmp_wire(direction, raw):
                    require(direction in ('request', 'response') and type(raw) is bytes and
                            0 < len(raw) <= 65536, 'actual original bounded QMP trace')
                    path = output / ('frame-' + str(index) + '-qmp-' + str(len(wire)).zfill(3) + '.raw')
                    with path.open('xb') as stream: stream.write(raw)
                    wire.append({'direction': direction, 'raw': descriptor(path)})
                response = guest.qmp('screendump', {'filename': str(frame), 'format': 'ppm'}, trace=keep_qmp_wire)
                qmp_finished = time.monotonic_ns()
                require(response == {} and qmp_started >= completed, 'actual QMP screendump/fence failed')
                ppm(frame.read_bytes())
                report['frames'].append(dict(operation_id=request['operation_id'], action_index=index,
                    raw_end_observed_ns=completed, UI=observation, roi=list(roi),
                    qmp={'execute': 'screendump', 'arguments': {'filename': str(frame), 'format': 'ppm'},
                         'reply': response, 'started_ns': qmp_started, 'finished_ns': qmp_finished},
                    capture=descriptor(frame), wire=wire, process_after=identity('frame-' + str(index) + '-after')))
                if index == 1 and product_inputs is not None:
                    require(descriptor(product_inputs['path'])['sha256'] == product_inputs['sha256'],
                            'actual Root product provenance input changed')
                    product_value = decode(Path(product_inputs['path']).read_text())
                    require(product_value['schema'] == 'media579-graphics3d-actual-product/v1' and
                            product_value['archive_sha256'] == archive_record['sha256'] and
                            product_value['product'] == env['product'], 'same selected product provenance')
                    profile_ref = product_value['installed_runtime_profile']
                    require(descriptor(profile_ref['path'])['sha256'] == profile_ref['sha256'], 'actual product profile changed')
                    profile = decode(Path(profile_ref['path']).read_text())
                    shell('cat /proc/' + str(current['pid']) + '/maps', 'actual-product-maps')
                    for soname in sorted(product_value['libraries']):
                        require(re.fullmatch('[A-Za-z0-9_.+-]+', soname) and soname in profile['dsos'],
                                'finite real installed Scene/core/plugin SONAME')
                        installed = profile['dsos'][soname]
                        staged = installed['staged']['path']
                        parts = staged.split('/packages/phone/')
                        require(len(parts) == 2 and parts[1].startswith(('system/', 'vendor/')),
                                'actual physical product staging partition')
                        guest_path = '/' + parts[1]
                        require(re.fullmatch('/(?:system|vendor)/lib(?:64)?/[A-Za-z0-9_./+-]+', guest_path) and
                                '..' not in Path(guest_path).parts, 'literal actual guest DSO path')
                        observed = shell('sha256sum ' + shlex.quote(guest_path), 'actual-product-sha-' + soname)
                        require(observed.split() == [installed['image_file']['sha256'], guest_path],
                                'live product DSO differs from actual new image')
                    report['product_inputs'] = product_inputs
            save()
        require(actual_identity is not None and len(report['frames']) == 6, 'actual complete process/six frame chain missing')
        require(shell('stat -c %u ' + shlex.quote(remote), 'actual-journal-owner').strip() == str(actual_identity['uid']), 'journal belongs to another UID')
        complete_raw = receive('journal-complete.jsonl')
        parse_rows(complete_raw.read_text(), run, env['boot_id'], actual_identity['pid'], actual_identity['uid'])
        report['raw'] = descriptor(complete_raw)
        report['oracle'] = review(complete_raw.read_text(), run, env['boot_id'], actual_identity['pid'], actual_identity['uid'],
                                  {r['operation_id']: Path(r['capture']['path']).read_bytes() for r in report['frames']}, roi)
        verify_capture_fences(report)
        require(descriptor(archive) == archive_record, 'actual archive changed during case')
        report['status'] = 'pass'
    except Exception as error:
        report['status'] = 'fail'; report['failures'].append(type(error).__name__ + ': ' + str(error))
    finally:
        if installed:
            try:
                report['application_cleanup'] = cleanup_microphone_application(
                    shell, command, guest.args.hdc, guest.target, env['boot_id'], preserve=preserve)
                report['cleanup_complete'] = True
            except Exception as error:
                report['status'] = 'fail'; report['failures'].append('cleanup: ' + str(error))
        else:
            report['cleanup_complete'] = not previous_cleanup_started or previous_cleanup_complete
        save()
    require(report['cleanup_complete'], 'Graphics3D cleanup uncertain; enclosing owner must stop this guest')
    try:
        same_guest('after-graphics3d')
    except Exception as error:
        report['status'] = 'fail'; report['failures'].append('final same-guest health: ' + str(error)); save()
        raise
    return report
