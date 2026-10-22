"""Run these three cases only on the parent's already-owned fresh package VM.

No owner/runner subclass, resource lease, process launcher, executable selector,
SDK lookup or CLI. The parent owns the enclosing package acceptance gate.
"""
import hashlib
import json
from pathlib import Path
import re
import zipfile
from io import BytesIO

from system_services578_project import (ROLES, IDS, bundle, permissions, source_files,
                                        module_fields, configure_profile, validate, require)


def raw(ref):
    require(type(ref) is dict and set(ref) == {'path', 'sha256'}, 'actual immutable raw file reference required')
    p = Path(ref['path'])
    require(p.is_absolute() and p.is_file() and not p.is_symlink(), 'regular absolute evidence file required')
    data = p.read_bytes()
    require(hashlib.sha256(data).hexdigest() == ref['sha256'], 'raw evidence bytes changed')
    return data


def commands(records, boot_id=None):
    require(type(records) is list and records, 'actual command records required')
    for r in records:
        require(type(r) is dict and type(r.get('argv')) is list and r['argv'] and
                all(type(s) is str for s in r['argv']) and type(r.get('exit_code')) is int,
                'actual argv/exit required')
        raw(r['stdout']); raw(r['stderr'])
        require(r['exit_code'] == 0 and not r.get('timed_out'), 'actual root-owned command failed')
        if boot_id is not None:
            require(r.get('boot_id') == boot_id, 'command belongs to another boot')


def compiled_fields_match(actual, expected):
    # Hvigor adds compiled metadata. Expected permissions/skills must retain
    # exact list cardinality and order, while unrelated object keys may grow.
    if type(expected) is dict:
        return type(actual) is dict and all(k in actual and compiled_fields_match(actual[k], v)
                                            for k, v in expected.items())
    if type(expected) is list:
        return type(actual) is list and len(actual) == len(expected) and all(
            compiled_fields_match(a, e) for a, e in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def prepared(spec, case, run_id, hosts, boot, udid):
    require(spec['case'] == case and spec['run_id'] == run_id and spec['boot_id'] == boot,
            'caller build not bound to actual run/boot')
    require(set(spec['callers']) == set(ROLES[case]), 'all exact caller identities required')
    for role, caller in spec['callers'].items():
        require(caller['bundle'] == bundle(case, role), 'wrong compiled caller bundle')
        root = Path(caller['project'])
        require(root.is_absolute() and root.is_dir(), 'actual compiled project required')
        for rel, content in source_files(case, run_id, role, hosts).items():
            require((root / rel).read_text() == content, 'compiled source differs: ' + rel)
        for key in ('build_commands', 'sign_commands', 'verify_commands'):
            commands(caller[key])
        raw(caller['unsigned']); raw(caller['signed'])
        with zipfile.ZipFile(caller['signed']['path']) as hap:
            compiled = json.loads(hap.read('module.json'))
            require(len(hap.read('ets/modules.abc')) > 0, 'actual compiled caller ABC missing')
        require(compiled['app']['bundleName'] == bundle(case, role), 'signed HAP bundle mismatch')
        require(compiled_fields_match(compiled['module'], module_fields(case, role, hosts)),
                'signed HAP permissions/skills mismatch')
        profile = json.loads(raw(caller['verified_profile']))
        require(configure_profile(case)(json.loads(json.dumps(profile)), role, udid, compiled) == profile,
                'actual verified signature profile does not match persona')
    return spec['callers']


def run(guest, root_callbacks, parameters):
    case, run_id = parameters['case'], parameters['run_id']
    hosts = parameters.get('hosts')
    validate(case, run_id, ROLES.get(case, ('',))[0], hosts)
    for name in ('prepare_callers', 'install', 'start', 'input', 'collect', 'network', 'cleanup'):
        require(callable(root_callbacks.get(name)), 'missing fixed parent callback: ' + name)
    cb = root_callbacks
    environment = guest.report['test_environment']
    boot = environment['boot_id']
    udid = parameters['udid']
    require(guest.shell('cat /proc/sys/kernel/random/boot_id', 'system_services578_boot').strip() == boot,
            'parent guest is not the fresh recorded boot')
    report = {'id': IDS[case], 'case': case, 'run_id': run_id, 'boot_id': boot,
        'status': 'fail', 'runtime_pass': False, 'first_artifact_behavior_gate_passed': False,
        'records': [], 'failures': [], 'observations': {}}
    identities = {}
    primary_identities = {}
    active_user = parameters.get('primary_user', 100)
    seen = {}
    serial = 0

    def expect(ok, message):
        if not ok:
            report['failures'].append(message)

    def record_call(name, *args):
        result = cb[name](*args)
        report['records'].append({'callback': name, 'arguments': args, 'result': result})
        require(result['boot_id'] == boot, 'callback changed fresh boot: ' + name)
        commands(result['commands'], boot)
        return result

    def collect(role, request_id):
        result = record_call('collect', role, request_id)
        rows = [json.loads(line) for line in raw(result['journal']).decode().splitlines() if line]
        for row in rows:
            require(row['run_id'] == run_id and row['kind'] == case and row['role'] == role and
                    row['bundle'] == bundle(case, role) and row['uid'] == identities[role]['uid'],
                    'raw caller identity/run mismatch')
            key = (role, row['pid'], row['seq'])
            previous = seen.get(key)
            require(previous is None or previous == row, 'append-only caller journal changed')
            seen[key] = row
        return [r for r in rows if r['request_id'] == request_id]

    def action(role, name):
        nonlocal serial
        serial += 1
        request_id = name.replace('-', '_') + '_' + str(serial)
        request = {'run_id': run_id, 'request_id': request_id, 'action': name}
        try:
            record_call('start', role, name, request)
            rows = collect(role, request_id)
            expect(any(r['event'] == 'request' and r['action'] == name for r in rows), 'missing actual request ' + request_id)
            return request_id, rows
        except (ValueError, KeyError, OSError) as error:
            report['failures'].append(request_id + ': ' + str(error))
            return request_id, []

    def event(rows, name, code=0):
        matches = [r for r in rows if r['event'] == name and r['code'] == code]
        expect(len(matches) == 1, 'expected one actual ' + name + '/' + str(code))
        return json.loads(matches[0]['value']) if len(matches) == 1 else None

    def install(role):
        result = record_call('install', role)
        identity = json.loads(raw(result['identity']))
        require(identity['bundle'] == bundle(case, role) and type(identity['uid']) is int and
                identity['uid'] > 0 and identity['user_id'] == active_user,
                'actual BMS caller identity required in the active account')
        expected = callers[role]['identity']
        require(type(identity['appIdentifier']) is str and identity['fingerprint'] == expected['fingerprint'],
                'actual BMS/self signature and independently verified signer certificate differ')
        identities[role] = identity
        return result

    def done(rows):
        event(rows, 'done')
        expect(not any(r['event'] in ('error', 'request-error', 'page-error') for r in rows), 'actual caller operation failed')

    def dump(label):
        text = guest.shell('hidumper -s 4606 -a "-a"', 'system_services578_' + label)
        report['observations'][label] = text
        return text

    def network(action_name, payload):
        return record_call('network', action_name, payload)

    def query(expected):
        _, rows = action('grant', 'query')
        data = event(rows, 'query')
        if data is not None:
            expect(('https://' + hosts['host'] in data['domains']) == expected, 'OS associated-domain state differs')
            expect((bundle('domain', 'target') in data['bundles']) == expected, 'OS verified bundle state differs')
            expect(bundle('domain', 'other') not in data['bundles'] and not data['otherDomains'] and
                not data['otherBundles'], 'mismatching bundle/domain gained verified ownership')
        report['observations']['domain_dump_' + str(serial)] = guest.shell('hidumper -s 6200',
            'system_services578_domain_' + str(serial))

    def route(name, success, target_present=True, other_present=True):
        request_id, rows = action('normal', name)
        event(rows, 'open-result', 0 if success else 16000019)
        # Pull both targets after a bounded parent observation window, including
        # absent-receiver cases; an empty fabricated journal is not accepted.
        target = collect('target', request_id) if target_present else []
        other = collect('other', request_id) if other_present else []
        expect(sum(r['event'] == 'routed' for r in target) == (1 if success else 0), 'actual routed target count differs')
        expect(not any(r['event'] == 'routed' for r in other), 'unverified sibling received App Linking Want')

    def capture(role, feature):
        from PIL import Image
        result = record_call('input', 'capture', {'role': role, 'feature': feature})
        with Image.open(BytesIO(raw(result['frame']))) as source:
            picture = source.convert('RGB')
        require(picture.width >= 320 and picture.height >= 240, 'actual QMP framebuffer too small')
        report['observations']['frame_' + str(len(report['records']))] = result['frame']
        return picture

    def markers(picture):
        red = green = 0
        for r, g, b in picture.getdata():
            red += r > 230 and g < 24 and 44 < b < 100
            green += r < 24 and 195 < g < 245 and 78 < b < 130
        return red, green

    def frame_changed(before, after):
        from PIL import ImageChops
        require(before.size == after.size, 'display resolution changed during session test')
        difference = ImageChops.difference(before, after)
        return sum(max(pixel) > 24 for pixel in difference.getdata()) > 400

    def window_dump(window_id, label, pid=None, visible=None):
        require(type(window_id) is int and window_id > 0, 'actual positive public window ID required')
        text = guest.shell('hidumper -s 4606 -a "-w ' + str(window_id) + '"', 'system_services578_' + label)
        report['observations'][label] = text
        expect(re.search(r'^WinId:\s*' + str(window_id) + r'\s*$', text, re.M) is not None,
               'public Window ID not bound to actual SceneSession')
        if pid is not None:
            expect(re.search(r'^Pid:\s*' + str(pid) + r'\s*$', text, re.M) is not None, 'actual session owner PID differs')
        if visible is not None:
            expect(re.search(r'^IsVisible:\s*' + ('true' if visible else 'false') + r'\s*$', text, re.M) is not None,
                   'actual session visibility differs')
        return text

    try:
        build = cb['prepare_callers'](case, run_id, ROLES[case])
        report['records'].append({'callback': 'prepare_callers', 'result': build})
        callers = prepared(build, case, run_id, hosts, boot, udid)
        if case == 'domain':
            for role in ('normal', 'grant', 'denied'):
                install(role)
            setup = network('start', {'hosts': hosts, 'run_id': run_id})
            fixture = json.loads(raw(setup['fixture']))
            require(fixture['hosts'] == hosts and fixture['guest_listener'] == '127.0.0.1:443' and
                    fixture['transport'] == 'owned-hdc-rport' and
                    fixture['ca_guest_path'].startswith('/system/etc/security/certificates/') and
                    fixture['verification'] == {'peer': 1, 'host': 2}, 'actual owned HTTPS fixture required')
            install('target')
            identity = identities['target']
            require(identity['fingerprint'], 'actual verified signer fingerprint missing')
            app = {'appIdentifier': identity['appIdentifier'], 'bundleName': bundle(case, 'target'),
                   'fingerprint': identity['fingerprint']}
            for phase in ('match', 'fingerprint-mismatch', 'revoke', 'server-error', 'untrusted-cert', 'wrong-host', 'retry'):
                apps = [dict(app)] if phase not in ('revoke', 'server-error') else []
                if phase == 'fingerprint-mismatch':
                    apps[0]['fingerprint'] = ('0' if app['fingerprint'][0] != '0' else '1') + app['fingerprint'][1:]
                body = json.dumps({'applinking': {'apps': apps}, 'auditNonce': run_id + '-' + phase}, separators=(',', ':')).encode()
                payload = {'generation': phase, 'host': hosts['host'], 'body': body.decode(),
                    'body_sha256': hashlib.sha256(body).hexdigest(), 'status': 500 if phase == 'server-error' else 200,
                    'tls_profile': phase if phase in ('untrusted-cert', 'wrong-host') else 'trusted',
                    'other_host_body': '{"applinking":{"apps":[]}}'}
                network('publish', payload)
                install('target')
                if phase == 'match':
                    install('other')
                    # Ensure both installed receivers have real append-only
                    # lifecycle journals even when a later route is rejected.
                    action('target', 'probe'); action('other', 'probe')
                query(phase in ('match', 'retry'))
                peer = network('collect', {'generation': phase})
                requests = [json.loads(line) for line in raw(peer['requests']).decode().splitlines() if line]
                if phase in ('untrusted-cert', 'wrong-host'):
                    connections = [json.loads(line) for line in raw(peer['connections']).decode().splitlines() if line]
                    expect(any(r['generation'] == phase and r['peer_ip'] == peer['transport_peer_ip'] and
                        r['sni'] == hosts['host'] and r['tls_profile'] == phase and r['handshake_error']
                        for r in connections), 'no actual guest TLS rejection: ' + phase)
                    expect(not any(r['generation'] == phase and r['host'] == hosts['host'] for r in requests),
                           'OS sent HTTPS asset request despite invalid TLS identity')
                else:
                    expect(any(r['generation'] == phase and r['method'] == 'GET' and r['scheme'] == 'https' and
                        r['host'] == hosts['host'] and r['path'] == '/.well-known/applinking.json' and
                        r['response_sha256'] == payload['body_sha256'] and r['status'] == payload['status'] and
                        r['peer_ip'] == peer['transport_peer_ip'] for r in requests), 'no matching independent OS HTTPS transaction: ' + phase)
                route('open', phase in ('match', 'retry'))
                if phase == 'match':
                    route('open-http', False); route('open-other', False)
                    _, rows = action('grant', 'query-invalid'); event(rows, 'error', 401)
                    _, rows = action('denied', 'query'); event(rows, 'error', 201)
                    _, rows = action('normal', 'query')
                    expect(sum(r['event'] == 'error' and r['code'] in (201, 202) for r in rows) == 1,
                           'ordinary caller did not receive documented permission/system-app rejection')
            # Caller death/restart must preserve real OS-verified cache. The
            # parent terminates only this test caller, never the shared SA.
            record_call('input', 'force-stop', {'role': 'normal'})
            route('open', True)
            query(True)
            # Account control and HDC selection stay with the parent. Verified
            # ownership may be global; launchability must follow the actual
            # target installation for the active account.
            primary_identities = dict(identities)
            secondary = build['secondary_user']
            require(parameters.get('secondary_user', secondary) == secondary, 'specified secondary account differs from actually created account')
            require(type(secondary) is int and secondary >= 100 and secondary != active_user,
                    'parent-owned distinct secondary OS account required')
            switched = record_call('input', 'account-switch', {'user_id': secondary})
            state = json.loads(raw(switched['account_state']))
            require(state['active_user_id'] == secondary and bundle(case, 'target') not in state['installed_bundles'],
                    'actual fresh secondary account must not already contain the target')
            active_user = secondary
            identities = {}
            install('normal')
            route('open', False, target_present=False, other_present=False)
            install('target')
            action('target', 'probe')
            route('open', True, other_present=False)
            restored = record_call('input', 'account-switch', {'user_id': parameters.get('primary_user', 100)})
            state = json.loads(raw(restored['account_state']))
            require(state['active_user_id'] == parameters.get('primary_user', 100), 'original account was not restored')
            active_user = parameters.get('primary_user', 100)
            identities = primary_identities
            query(True)
            route('open', True)
            report['observations']['domain_scope'] = 'BMS install/update refresh, revoke, 500/retry, caller restart/cache and second-account launch isolation; no direct registry writes or host-HTTP substitution'
        elif case == 'session':
            for role in ROLES[case]:
                install(role)
            report['observations']['sceneboard_switch'] = guest.shell('cat /system/etc/sceneboard.config',
                'system_services578_sceneboard')
            expect(report['observations']['sceneboard_switch'].strip() == 'ENABLED', 'actual image SceneBoard switch is not enabled')
            _, rows = action('normal', 'probe'); cap = event(rows, 'capabilities')
            expect(cap is not None and cap['session'] is True, 'actual canIUse SessionManager false')
            _, rows = action('normal', 'window-create'); created = event(rows, 'window-created'); done(rows)
            initial = dump('created')
            if created:
                expect(str(created['id']) in initial and 's578_' + run_id[:8] in initial,
                       'new public subwindow absent from actual SA4606 session dump')
                owner_pid = next(r['pid'] for r in rows if r['event'] == 'window-created')
                window_dump(created['id'], 'created_detail', owner_pid, True)
            before_touch = capture('normal', 'child-created')
            expect(all(n > 100 for n in markers(before_touch)), 'new subwindow pixels missing from actual framebuffer')
            record_call('input', 'touch', {'role': 'normal', 'selector': 'services578-child-touch'})
            touched = collect('normal', rows[0]['request_id']) if rows else []
            event(touched, 'child-touch')
            _, rows = action('normal', 'window-update'); changed = event(rows, 'window-updated'); done(rows)
            limits = event(rows, 'limits')
            expect(limits is not None and limits['applied'] == limits['readback'], 'actual SessionManager limits readback differs')
            expect(created and changed and created['id'] == changed['id'] and
                created['windowRect'] != changed['windowRect'], 'window session update did not retain ID/change rectangle')
            dump('updated')
            _, rows = action('normal', 'window-hide'); hidden = event(rows, 'window-hide'); done(rows)
            if hidden: window_dump(hidden['id'], 'hidden_detail', visible=False)
            hidden_frame = capture('normal', 'child-hidden')
            expect(sum(markers(hidden_frame)) < sum(markers(before_touch)) / 5, 'hidden child is still visibly rendered')
            _, rows = action('normal', 'window-show'); shown = event(rows, 'window-show'); done(rows)
            if shown: window_dump(shown['id'], 'shown_detail', visible=True)
            expect(all(n > 100 for n in markers(capture('normal', 'child-shown'))), 'shown child pixels not restored')
            prior_background = sum(r['event'] == 'background' for r in seen.values() if r['role'] == 'normal')
            record_call('input', 'home', {'role': 'normal'})
            collect('normal', 'lifecycle')
            expect(sum(r['event'] == 'background' for r in seen.values() if r['role'] == 'normal') > prior_background,
                   'ordinary Home gesture did not background the caller')
            _, rows = action('normal', 'probe'); event(rows, 'capabilities'); done(rows)
            _, rows = action('normal', 'system-api'); event(rows, 'error', 202)
            _, rows = action('grant', 'system-api'); event(rows, 'system-api-restored'); done(rows)
            _, rows = action('grant', 'foreign-window')
            expect(sum(r['event'] == 'error' and r['code'] == 1300002 for r in rows) == 1, 'another process obtained a foreign window handle')
            _, rows = action('normal', 'invalid-window'); event(rows, 'error', 401)
            _, rows = action('normal', 'window-destroy'); event(rows, 'window-destroyed'); event(rows, 'destroyed-handle', 1300002)
            after = dump('destroyed')
            expect('s578_' + run_id[:8] not in after, 'destroyed session remains in actual SA4606 dump')
            for feature, start, stop, started, stopped in (
                ('pip', 'pip-start', 'pip-stop', 2, 4),
                ('ball', 'ball-start', 'ball-stop', 1, 2),
                ('view', 'view-start', 'view-stop', 1, 3)):
                if not cap:
                    continue
                if cap[feature] is not True:
                    _, rows = action('grant', start); event(rows, 'error', 801)
                    report['failures'].append('product disables ' + feature + '; root must bind exact product applicability before aggregate closure')
                    continue
                if feature in ('ball', 'view'):
                    _, rows = action('denied', start); event(rows, 'error', 201)
                _, rows = action('grant', start)
                states = [json.loads(r['value']) for r in rows if r['event'] == feature + '-state']
                expect(any(s.get('state') == started for s in states), 'actual feature STARTED callback missing: ' + feature)
                done(rows); dump(feature + '_started')
                _, info_rows = action('grant', feature + '-info'); info = event(info_rows, 'feature-info')
                if info:
                    window_dump(info['windowId'], feature + '_detail', visible=True)
                started_frame = capture('grant', feature)
                if feature == 'ball':
                    _, rows = action('grant', 'ball-update'); event(rows, 'ball-update'); done(rows)
                    expect(frame_changed(started_frame, capture('grant', 'ball-updated')), 'floating-ball update had no real pixel change')
                _, rows = action('grant', stop)
                states = [json.loads(r['value']) for r in rows if r['event'] == feature + '-state']
                expect(any(s.get('state') == stopped for s in states), 'actual feature STOPPED callback missing: ' + feature)
                done(rows); dump(feature + '_stopped')
                expect(frame_changed(started_frame, capture('grant', feature + '-stopped')), 'stopped feature remains visibly unchanged')
                # Independent actual system close control, followed by reopen.
                cancel_id, rows = action('grant', start); done(rows)
                _, info_rows = action('grant', feature + '-info'); event(info_rows, 'feature-info')
                record_call('input', 'close-feature', {'role': 'grant', 'feature': feature})
                cancelled = collect('grant', cancel_id)
                states = [json.loads(r['value']) for r in cancelled if r['event'] == feature + '-state']
                expect(any(s.get('state') == stopped for s in states), 'system close did not cancel real feature: ' + feature)
                if feature == 'view':
                    expect(any(s.get('state') == stopped and s.get('stopReason') == 'TITLE_BAR_STOP_CLICK' for s in states),
                           'FloatView close did not come from the actual title-bar control')
                if feature == 'ball':
                    event(cancelled, 'ball-user-cancel')
                _, rows = action('grant', start); done(rows)
                _, rows = action('grant', stop); done(rows)
            # A new process/window after abrupt caller death checks session
            # cleanup without restarting foundation, SA4606 or SceneBoard.
            action('normal', 'window-create')
            record_call('input', 'force-stop', {'role': 'normal'})
            expect('s578_' + run_id[:8] not in dump('process_death'), 'dead caller leaked a real session')
            _, rows = action('normal', 'window-create'); reopened = event(rows, 'window-created'); done(rows)
            expect(created and reopened and created['id'] != reopened['id'], 'restart reused destroyed persistent ID')
            # A finite default-policy sleep and key wake is performed by the
            # parent with its original serial observer and policy restoration.
            before_sleep = capture('normal', 'before-sleep')
            power = record_call('input', 'sleep-wake', {'role': 'normal'})
            serial = raw(power['serial_before_key']).decode(errors='replace')
            from boot_package import kernel_sleeping
            expect(kernel_sleeping(serial), 'owned serial never reached actual kernel s2idle before key input')
            expect(not kernel_sleeping(raw(power['serial_after_key']).decode(errors='replace')),
                   'actual key did not leave kernel s2idle')
            expect(raw(power['foundation_before']).strip() == raw(power['foundation_after']).strip() and
                   raw(power['render_before']).strip() == raw(power['render_after']).strip(),
                   'foundation/RenderService restarted during session recovery')
            _, rows = action('normal', 'window-properties'); recovered = event(rows, 'window-properties'); done(rows)
            expect(reopened and recovered and reopened['id'] == recovered['id'] and
                   reopened['windowRect'] == recovered['windowRect'], 'sleep/wake replaced or moved the actual session')
            after_sleep = capture('normal', 'after-sleep')
            expect(all(n > 100 for n in markers(before_sleep)) and all(n > 100 for n in markers(after_sleep)),
                   'session content not restored after actual sleep/wake')
            record_call('input', 'touch', {'role': 'normal', 'selector': 'services578-child-touch'})
            touched = collect('normal', rows[0]['request_id']) if rows else []
            event(touched, 'child-touch')
            action('normal', 'window-destroy')
        else:
            install('normal')
            _, rows = action('normal', 'probe'); event(rows, 'syscap')
            for name in ('invalid', 'invalid-display'):
                _, rows = action('normal', name); event(rows, 'error', 401)
            for name in ('load', 'multi'):
                _, rows = action('normal', name)
                expect(sum(r['event'] == 'ad-failure' and r['code'] == 12 for r in rows) == 1,
                    'fixed framework connection-failure boundary did not return raw error 12: ' + name)
                expect(not any(r['event'] == 'ad-success' for r in rows), 'unexpected provider exists: reopen full Ads behavior')
            record_call('input', 'force-stop', {'role': 'normal'})
            _, rows = action('normal', 'load')
            event(rows, 'ad-failure', 12)
            report['observations']['ads_scope'] = 'framework invalid-parameter/absent-provider/restart boundaries only; complete provider exclusion is bounded source review, never a load/render pass'
            report['observations']['actual_ads_config'] = guest.shell(
                'cat /system/etc/advertising/ads_framework/ad_service_config.json', 'system_services578_ads_config')
            config = json.loads(report['observations']['actual_ads_config'])
            report['observations']['actual_installed_bundles'] = guest.shell('bm dump -a', 'system_services578_ads_bundles')
            expect(config.get('providerBundleName') == ['com.samples.AdsServiceDemo'] and
                   not config.get('providerApiAbilityName') and
                   'com.samples.AdsServiceDemo' not in report['observations']['actual_installed_bundles'],
                   'actual product differs from bounded Ads provider exclusion; inspect full current provider')
            report['observations']['provider_exclusion_scope'] = 'complete bundled OEM Ads provider/content backend in the fixed reviewed repositories only; framework/API is exercised and is not excluded'
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as error:
        report['failures'].append(str(error))
    finally:
        try:
            record_call('cleanup')
            require(guest.shell('cat /proc/sys/kernel/random/boot_id', 'system_services578_after_boot').strip() == boot,
                    'fresh package boot changed during system-services case')
        except (ValueError, KeyError, TypeError, OSError) as error:
            report['failures'].append('cleanup: ' + str(error))
    report['status'] = 'pass' if not report['failures'] else 'fail'
    # Deliberate: only the enclosing parent suite can promote package-bound,
    # independent raw semantics and the complete original ID to runtime pass.
    return report
