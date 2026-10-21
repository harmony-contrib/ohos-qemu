#!/usr/bin/env python3
"""Collect one Calendar QA stage in an enclosing real guest. No boot/build/install.

Raw output is collector-owned. Stage success never asserts the full lifecycle,
onNewWant delivery, independent instances, or a package gate.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

import batch_apps_contact_picker_coordinator as signatures
from batch_apps_run_contact_picker_runtime import clickable_for_text
from batch_system_calendar_runtime_project import (CONTRACT, FIX, ROLES, checked, load_challenge,
    record, request, require, sha, write)
import batch_system_calendar_runtime_protocol as protocol
from batch_system_calendar_runtime_binding import permission_label, sdk_binding, signed_payload
from enclosing_acceptance_guest import EnclosingAcceptanceGuest
from guest_ui import GuestUi, LayoutNotReady, NodeNotReady, select_node

HERE = Path(__file__).resolve().parent
PROVIDER = CONTRACT['provider']


def helper_proof(spec):
    """Consume actual future product-helper builder output; no NDK fallback."""
    import batch_system_build_runtime_helpers as product
    binary, receipt = checked(spec['binary']), checked(spec['receipt'])
    report = protocol.decode(receipt.read_text())
    selected_product = report['installed_runtime_profile']['profile']['product']
    mapping = spec.get('path_map', {})
    require(not mapping or set(mapping) == {'/work', '/evidence/helpers'}, 'only original product helper witness mappings supported')
    def actual(item):
        return signatures.witness_artifact(item, mapping)
    require(report.get('plan_only') is False and report.get('product') == selected_product and
            report.get('changed_inputs') == [] and report.get('builder_sha256') == sha(HERE / 'batch_system_build_runtime_helpers.py'),
            'current immutable product helper build receipt required')
    original = None
    row = report['helpers']['calendar_runtime_observer']
    compile_commands = report['commands']
    if report.get('verify_existing') is True:
        reference = report['original_report']
        original = protocol.decode(actual(reference).read_text())
        require(reference.get('rewritten') is False and reference['status'] == original['status'] and
                reference['builder_sha256'] == original['builder_sha256'] and original.get('plan_only') is False and
                original.get('changed_inputs') == [] and original.get('product') == selected_product,
                'actual immutable Calendar original helper receipt required')
        prior = original['helpers']['calendar_runtime_observer']
        require(all(row.get(k) == prior.get(k) for k in ('compile_command', 'link_command')),
                'Calendar recheck changed original compile/link commands')
        require(actual(row['reused_artifacts']['binary']) == binary and
                sha(actual(row['reused_artifacts']['source'])) == sha(FIX / 'observer.cpp'),
                'Calendar recheck reused different artifacts')
        row = {**prior, **row}
        compile_commands = report['original_commands']
    extension = original if original is not None else report
    require(sha(actual(extension.get('calendar_runtime_extension', {}))) == sha(HERE / 'batch_system_calendar_runtime_helper.py'),
            'actual dedicated helper extension/anchor configuration differs')
    require(row.get('status') == 'pass_compile_link_ONLY' and row.get('CFI_preserved') is True and
            row.get('fixture') == 'batch_system/calendar_runtime/observer.cpp' and
            row.get('private_source_sha256') == sha(FIX / 'observer.cpp') and
            row.get('binary_sha256') == sha(binary) and signatures.witness_path(row['binary'], mapping).resolve() == binary,
            'actual Calendar helper source/binary/product CFI differs')
    for name in ('source',):
        require(sha(actual(row[name])) == sha(FIX / 'observer.cpp'), 'actual compiled observer source differs')
    for kind in ('compile', 'link'):
        commands = [c for c in compile_commands if c.get('label') == 'calendar_runtime_observer-' + kind]
        require(len(commands) == 1 and commands[0]['exit_code'] == 0 and commands[0]['argv'] == row[kind + '_command'],
                'real product helper compile/link failed')
        if original is not None:
            old = [c for c in original['commands'] if c.get('label') == commands[0]['label']]
            require(len(old) == 1 and all(old[0][k] == commands[0][k]
                    for k in ('argv', 'label', 'log', 'sha256', 'exit_code')), 'original Calendar compile log was rewritten')
            actual(commands[0]['verified_log'])
        else:
            actual({'path': commands[0]['log'], 'sha256': commands[0]['sha256']})
    compile_argv = row['compile_command']
    require('-fno-exceptions' in compile_argv and
            '-fsanitize-cfi-cross-dso' in compile_argv and any(x.startswith('-fsanitize=') and 'cfi' in x for x in compile_argv) and
            product.effective_cfi(compile_argv) and product.effective_cfi(row['link_command']) and '-pie' in row['link_command'] and
            row.get('actual_compiler_dependencies') and row.get('actual_link_inputs') and row.get('anchors'),
            'actual product headers/DSO/CFI commands missing')
    from native579_artifact_context import binding_context
    native_context579 = binding_context(original if original is not None else report, row, binary, actual)
    product.validate_flags(compile_argv, product=selected_product, actual_target=native_context579['compiler_target'])
    require([a['object_target'] for a in row['anchors']] == [product.APP['object'], product.TOKEN['object']],
            'actual APP/TOKEN graph anchors differ')
    require({'libapp_manager.z.so', 'libaccesstoken_sdk.z.so'} <= set(row.get('DT_NEEDED', [])), 'real innerkit DSOs missing')
    commands = [c for c in report['commands'] if c.get('label') == 'calendar_runtime_observer-actual-ELF-ABI']
    require(len(commands) == 1 and commands[0]['exit_code'] == 0 and Path(commands[0]['argv'][0]).name == 'llvm-readelf',
            'actual ELF/CFI readback required')
    elf = actual({'path': commands[0]['log'], 'sha256': commands[0]['sha256']}).read_text()
    require('__cfi_check' in elf and 'std::__h::' in elf and 'std::__n1::' not in elf, 'actual ELF product libc++/CFI missing')
    from run_root_probe import validate_elf
    validate_elf(binary, native_context579['arch'])
    from batch_media_wallpaper_artifacts import elf_dependencies, installed_runtime_binding
    installed_runtime_binding(row, elf_dependencies(binary, product_name=selected_product), original['inputs'] if original is not None else report['inputs'])
    return row


def exact_signature(signed, role, udid, signer, output, command):
    """Actual Java code-sign + fixed application leaf + independent profile CMS."""
    policy = ROLES[role]
    dist, jar, inputs = signatures.signer_inputs(signer['dist'], checked(signer['jar']))
    module, payload = signatures.hap_contents(signed)
    require(module['app']['bundleName'] == policy['bundle'] and module['app'].get('debug') is False and
            sorted(x['name'] for x in module['module'].get('requestPermissions', [])) == sorted(policy['permissions']) and
            module['module'].get('extensionAbilities', []) == [] and
            len(module['module'].get('abilities', [])) == 1 and module['module']['abilities'][0]['name'] == 'EntryAbility',
            'actual compiled QA role permission/Ability surface differs')
    output.mkdir(parents=True, exist_ok=False)
    chain, profile = output / 'chain.cer', output / 'profile.p7b'
    log = command(['java', '-jar', str(jar), 'verify-app', '-inFile', str(signed), '-outCertChain', str(chain), '-outProfile', str(profile)], 'signature-' + role)
    require(all(s in log for s in ('verify codesign success', 'Digest verify result: true', 'verify permission sign success', 'verify-app success')),
            'real app signature/codesign failed')
    signatures.application_leaf(log)
    decoded = output / 'java-profile.json'
    log = command(['java', '-jar', str(jar), 'verify-profile', '-inFile', str(profile), '-outFile', str(decoded)], 'profile-' + role)
    require('verify-profile success' in log, 'real embedded profile verification failed')
    from check_m144_core_package import verified_profile_content
    value = verified_profile_content(protocol.decode(decoded.read_text()))
    leaf = output / 'profile-leaf.pem'
    certs = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', (dist / 'OpenHarmonyProfileDebug.pem').read_text(), re.S)
    require(len(certs) == 3, 'fixed profile issuer chain differs')
    leaf.write_text(certs[-1] + '\n')
    fingerprint = command(['openssl', 'x509', '-in', str(leaf), '-noout', '-fingerprint', '-sha256'], 'issuer-' + role)
    require(fingerprint.strip().split('=')[-1].replace(':', '').upper() == signatures.PROFILE_LEAF, 'profile issuer differs')
    cms = output / 'cms-profile.json'
    command(['openssl', 'cms', '-verify', '-inform', 'DER', '-in', str(profile), '-nointern', '-certfile', str(leaf), '-noverify', '-out', str(cms)], 'CMS-' + role)
    require(protocol.decode(cms.read_text()) == value, 'independent CMS profile differs')
    info = value['bundle-info']
    require(info['bundle-name'] == policy['bundle'] and info['apl'] == policy['apl'] and
            info['app-feature'] == ('hos_system_app' if policy['system_app'] else 'hos_normal_app') and
            value['debug-info']['device-ids'] == [udid] and value['acls']['allowed-acls'] == policy['allowed_acls'] and
            value['permissions']['restricted-permissions'] == policy['allowed_acls'] and
            value['validity']['not-before'] <= int(time.time()) < value['validity']['not-after'],
            'exact role/UDID/ACL/validity differs')
    return {'verified_profile': record(cms), 'signed_hap': record(signed), 'fixed_signer_inputs': inputs, 'payload': payload}


class Collector:
    def __init__(self, args):
        self.args = args
        self.output = args.output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.challenge = load_challenge(args.challenge)
        self.run = self.challenge['run_id']
        self.plan = protocol.decode(args.plan.read_text())
        self.guest = EnclosingAcceptanceGuest(args.boot, args.archive, args.hdc, self.output / 'guest').start()
        product_name579 = self.guest.report['test_environment']['product']
        import batch_system_build_runtime_helpers as product579
        expected_arch579 = product579.target_spec(product_name579)['arch']
        require(self.guest.report['test_environment']['guest_arch'] == expected_arch579 and self.guest.report['test_environment']['device_type'] in ('phone','2in1'),
                'actual finite full-source Calendar guest product/profile required')
        self.boot = self.guest.env['boot_id']
        self.report = {'schema_version': 1, 'scope': 'actual_calendar_QA_stage_NOT_full_calendar_or_package_gate',
            'status': 'fail', 'run_id': self.run, 'boot_id': self.boot, 'archive': record(args.archive.resolve()),
            'boot': record(args.boot.resolve()), 'challenge': record(args.challenge.resolve()), 'plan': record(args.plan.resolve()),
            'collector': record(Path(__file__)), 'commands': [], 'artifacts': {}, 'failures': [], 'gaps': [],
            'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}
        self.ui = GuestUi(self.command, args.hdc, self.guest.target, self.output / 'ui')
        self.apps = {}
        self.save()

    def save(self):
        self.report['guest_commands'] = self.guest.report['commands']
        (self.output / 'capture.json').write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + '\n')

    def command(self, argv, label):
        self.guest.healthy()
        result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=30)
        path = self.output / ('command-' + str(len(self.report['commands'])).zfill(4) + '.log')
        write(path, result.stdout + result.stderr)
        self.report['commands'].append({'argv': list(map(str, argv)), 'label': label, 'exit_code': result.returncode, **record(path)})
        self.save()
        from hdc_transport import failed
        require(result.returncode == 0 and not failed(result.stdout, result.stderr), 'actual command failed: ' + label)
        self.guest.healthy()
        return result.stdout.replace('\r', '')

    def raw(self, script, label):
        text = self.guest.shell(script, label)
        path = self.output / ('raw-' + str(len(self.guest.report['commands'])).zfill(4) + '-' + label + '.txt')
        write(path, text)
        self.save()
        return text, record(path)

    def token(self, bundle, label):
        initial = self.apps[bundle]
        bms_raw, before = self.raw('bm dump -n ' + bundle, label + '-BMS-before')
        _, app, _ = protocol.bms(bms_raw, bundle)
        fields = ('uid', 'accessTokenId', 'isSystemApp', 'appPrivilegeLevel')
        require(all(app.get(k) == initial.get(k) for k in fields), 'BMS identity changed before native token query')
        raw, artifact = self.raw(shlex.join([self.plan['helper']['remote'], self.run, bundle, str(app['uid'])]), label)
        identity = {'run_id': self.run, 'boot_id': self.boot}
        value = protocol.token(protocol.decode(raw), identity, bundle, app)
        bms_raw, after = self.raw('bm dump -n ' + bundle, label + '-BMS-after')
        _, again, _ = protocol.bms(bms_raw, bundle)
        require(all(again.get(k) == app.get(k) for k in fields), 'BMS identity changed during native token query')
        self.report.setdefault('token_bms_bindings', []).append({'bundle': bundle, 'token': artifact,
            'before': before, 'after': after})
        self.save()
        previous = getattr(self, 'clock_anchor', None)
        if previous:
            require(abs((value['realtime_ns']-previous['realtime_ns']) -
                    (value['boottime_ns']-previous['boottime_ns'])) <= 2_000_000_000,
                    'guest wall clock changed relative to suspend-aware real elapsed time')
        self.clock_anchor = value
        return value, artifact

    def setup(self):
        require(set(self.plan['roles']) == set(ROLES), 'producer/observer/denied roles must be explicit and distinct')
        helper = self.plan['helper']
        row = helper_proof(helper)
        require(helper['remote'].startswith('/data/local/tmp/') and '..' not in Path(helper['remote']).parts, 'owned installed diagnostic path required')
        actual, proof = self.raw('sha256sum ' + shlex.quote(helper['remote']), 'helper-sha')
        require(actual.split()[0] == sha(checked(helper['binary'])), 'guest observer differs from actual product ELF')
        import batch_system_build_runtime_helpers as product
        product.validate_installed_profile(row['installed_runtime_profile']['profile'],
                                           archive_sha256=self.report['archive']['sha256'])
        # Locations come exclusively from the exact image/staging profile, never the plan.
        require('guest_dsos' not in helper, 'legacy caller-supplied Calendar DSO paths are not accepted')
        dso_observations = {}
        for name in row['DT_NEEDED']:
            text, observation = self.raw(product.runtime_guest_script(row, name),
                                         'DSO-' + re.sub('[^A-Za-z0-9_-]', '-', name))
            product.verify_guest_runtime_raw(row, name, text, archive_sha256=self.report['archive']['sha256'])
            dso_observations[name] = observation
        self.report['helper'] = {'binary': helper['binary'], 'receipt': helper['receipt'], 'guest_sha': proof,
            'dsos': dso_observations}
        for role, policy in ROLES.items():
            item = self.plan['roles'][role]
            sdk = sdk_binding(item['sdk'], item['source_manifest'], role, self.args.challenge.resolve())
            signed = checked(item['signed_hap'])
            signature = exact_signature(signed, role, self.guest.udid, self.plan['signer'], self.output / ('signature-' + role), self.command)
            signed_payload(checked(item['sdk']['unsigned_hap']), signed)
            raw, bm = self.raw('bm dump -n ' + policy['bundle'], 'BMS-' + role)
            _, app, remote = protocol.bms(raw, policy['bundle'], policy)
            self.apps[policy['bundle']] = app
            installed = self.output / (role + '-installed.hap')
            self.command([self.args.hdc, '-t', self.guest.target, 'file', 'recv', remote, str(installed)], 'pull-' + role)
            require(sha(installed) == sha(signed), 'actual BMS-installed QA HAP differs')
            token, token_file = self.token(policy['bundle'], 'token-' + role)
            if role in ('producer', 'denied'):
                require(all(token['permissions'][p] == -1 for p in ('ohos.permission.READ_WHOLE_CALENDAR',
                        'ohos.permission.WRITE_WHOLE_CALENDAR', 'ohos.permission.NOTIFICATION_CONTROLLER')), 'ordinary role unexpectedly privileged')
            else:
                require(token['permissions']['ohos.permission.NOTIFICATION_CONTROLLER'] == 0,
                        'observer exact system_basic/provision-ACL candidate was not actually granted; preserve BMS/token gap')
            self.report['artifacts'][role] = {'sdk': sdk, 'source_manifest': item['source_manifest'], 'signature': signature,
                'bms': bm, 'installed_hap': record(installed), 'token': token_file, 'uid': app['uid'], 'token_id': app['accessTokenId']}
        require(len({a['uid'] for a in self.apps.values()}) == 3 and len({a['accessTokenId'] for a in self.apps.values()}) == 3,
                'QA producer and observer identities overlap')
        raw, bm = self.raw('bm dump -n ' + PROVIDER, 'BMS-provider')
        _, app, remote = protocol.bms(raw, PROVIDER)
        require(app.get('isSystemApp') is True and app.get('appPrivilegeLevel') == 'system_core', 'real source provider system-core identity missing')
        self.apps[PROVIDER] = app
        installed = self.output / 'provider-installed.hap'
        self.command([self.args.hdc, '-t', self.guest.target, 'file', 'recv', remote, str(installed)], 'pull-provider')
        provider_receipt = checked(self.plan['provider']['archive_binding'])
        provider = protocol.decode(provider_receipt.read_text())
        require(provider['archive'] == record(self.args.archive.resolve()) and provider['collector'] ==
                record(HERE / 'batch_system_calendar_runtime_archive.py') and
                provider['scope'] == 'actual_archive_system_image_Calendar_HAP_signature_frozen_inputs_ONLY',
                'actual current archive provider derivation required; old SDK HAP is not a runtime provider')
        require(sha(installed) == sha(checked(provider['signed_hap'])), 'installed source provider differs from actual archive image HAP')
        inputs = protocol.decode(checked(provider['build_inputs']).read_text())
        require(inputs['tree_sha256'] == provider['build_inputs_tree_sha256'], 'archive build inputs changed')
        for name, expected in provider['source_component_hashes'].items():
            require(inputs['files_sha256'].get(name) == expected and sha(HERE.parents[1] / name) == expected,
                    'current/archive reminder component bytes differ')
        for entry in provider['commands']:
            require(entry['exit_code'] == 0, 'actual archive provider signature check failed')
            checked({'path': entry['path'], 'sha256': entry['sha256']})
        module, payload = signatures.hap_contents(installed)
        require(module['app']['bundleName'] == PROVIDER and payload == provider['module_payload'],
                'installed provider is not the actual archive image source payload')
        schema = protocol.schema(module)
        token, token_art = self.token(PROVIDER, 'token-provider')
        self.provider_label_proof = None
        self.provider_label_context = None
        self.report['artifacts']['provider'] = {'archive_binding': record(provider_receipt), 'bms': bm, 'installed_hap': record(installed),
            'token': token_art, 'uid': app['uid'], 'token_id': app['accessTokenId'], 'schema': schema}
        locale_only = self.args.stage == 'operation' and self.args.role == 'observer' and self.args.action == 'locale'
        if not locale_only:
            from batch_system_calendar_runtime_resources import make_provider_label_proof, require_fresh_public_locale
            self.provider_label_context = {'installed_hap': record(installed), 'bms': bm,
                'locale': self.plan['provider']['public_locale_capture'], 'archive_sha256': self.report['archive']['sha256'],
                'boot_id': self.boot, 'run_id': self.run}
            self.provider_label_proof = make_provider_label_proof(**self.provider_label_context)
            observed = self.provider_label_proof['public_locale']
            observer = self.apps[ROLES['observer']['bundle']]
            require(observed['uid'] == observer['uid'] and observed['token_id'] == observer['accessTokenId'] and
                    observed['challenge'] == self.report['challenge'], 'public locale used another installed observer/challenge')
            require_fresh_public_locale(self.provider_label_proof, token['realtime_ns'])
            self.report['artifacts']['provider']['label_proof'] = self.provider_label_proof
        self.save()

    def permission_preflight(self):
        layout, path = self.ui.layout(label='permission-preflight')
        require(not protocol.permission_windows(layout, self.plan.get('permission_bundle', 'com.ohos.permissionmanager')),
                'pre-existing permission prompt: preserve it before starting any new request')
        self.report['permission_preflight'] = {'layout': record(path)}
        self.save()

    def permission_click(self, decision, target):
        bundle = self.plan.get('permission_bundle', 'com.ohos.permissionmanager')
        texts = self.plan.get('allow_texts', ['允许', 'Allow']) if decision == 'allow' else self.plan.get('deny_texts', ['不允许', 'Deny'])
        layout, path = self.ui.layout(label='permission')
        if not protocol.permission_windows(layout, bundle):
            return None
        provider_locale = None
        if target == PROVIDER:
            from batch_system_calendar_runtime_resources import require_fresh_public_locale
            # Starting the observer here would replace the very permission UI under review.
            # A fresh before-launch public capture and the exact actual requester label are required instead.
            token, provider_locale = self.token(PROVIDER, 'provider-label-clock-before-decision')
            require_fresh_public_locale(self.provider_label_proof, token['realtime_ns'])
        label = permission_label(target, self.apps, self.run,
            provider_label_proof=self.provider_label_proof if target == PROVIDER else None,
            provider_label_context=self.provider_label_context if target == PROVIDER else None)
        selected = protocol.permission_control(layout, bundle, target, label, texts)
        node = selected['selected_node']
        screen = self.ui.screenshot(label='permission-before')
        x, y, w, h = node['rect']
        self.ui.shell(f'uitest uiInput click {x+w//2} {y+h//2}', 'permission-actual-node')
        proof = {'decision': decision, 'layout': record(path), 'screenshot': record(screen), **selected}
        if provider_locale is not None: proof['provider_locale_clock'] = provider_locale
        return proof

    def operation(self, role, action, case):
        policy = ROLES[role]
        value = request(self.args.challenge, self.boot, sha(self.args.archive), role, action, case,
            lead_minutes=self.args.lead_minutes, spacing_minutes=self.args.spacing_minutes)
        if action == 'cleanup':
            require(self.args.readback is not None, 'cleanup requires a fresh actual independent observer read capture')
            from batch_system_calendar_runtime_verify import validate_capture, operation
            observed = validate_capture(self.args.readback, self.challenge, self.report['archive'])
            require(observed['request']['role'] == 'observer' and observed['request']['action'] == 'read' and
                    observed['boot_id'] == self.boot, 'current-boot whole-reader cleanup preflight required')
            rows = operation(observed)
            require(not protocol.values(rows, 'error'), 'independent cleanup preflight read failed')
            native = protocol.decode(checked(observed['token_after']).read_text())
            require(native['permissions']['ohos.permission.READ_WHOLE_CALENDAR'] == 0,
                    'cleanup preflight lacks actual whole-calendar grant')
            readings = protocol.values(rows, 'events', 'Calendar.getEvents')
            require(len(readings) == 1 and 0 <= self.clock_anchor['realtime_ns']//1_000_000 - rows[-1]['timestamp_ms'] <= 120000,
                    'fresh unique independent complete account read required; preserve uncertain data')
            value['cleanup_guard'] = {'calendar_id': readings[0]['calendar_id'], 'events': readings[0]['events'],
                'observed_ms': rows[-1]['timestamp_ms']}
            self.report['readback_capture'] = record(self.args.readback.resolve())
        self.report['request'] = value
        self.report['stage'] = 'public-operation'
        self.report['empty_journal_proves_no_side_effect'] = False
        self.report['preserve_owned_data_until_independent_cleanup'] = True
        self.permission_preflight()
        self.report['operation_launch'] = self.raw(shlex.join(['aa', 'start', '-b', policy['bundle'], '-a', 'EntryAbility', '--ps', 'request', json.dumps(value, separators=(',', ':'))]), 'launch-request')[1]
        deadline = time.monotonic() + self.args.timeout
        clicked = False
        last = ''
        while time.monotonic() < deadline:
            try:
                if not clicked:
                    self.report['run_click'] = self.ui.click(policy['bundle'], identifier='calendar-qa-run', label='execute-real-operation')
                    self.report['run_click']['layout'] = record(Path(self.report['run_click']['layout']))
                    clicked = True
                if self.args.permission_decision:
                    decision = self.permission_click(self.args.permission_decision, policy['bundle'])
                    if decision:
                        self.report.setdefault('permission_clicks', []).append(decision)
                path = '/data/app/el2/100/base/' + policy['bundle'] + '/files/calendar-' + self.run + '-' + self.boot + '.jsonl'
                raw, artifact = self.raw('if test -f ' + shlex.quote(path) + '; then cat ' + shlex.quote(path) + '; fi', 'public-journal')
                if raw:
                    _, own = protocol.parse(raw, value, self.apps[policy['bundle']])
                    if own:
                        self.report['journal'] = artifact
                        self.report['operation_errors'] = [r for r in own if r['event'] == 'error']
                        self.report['token_after'] = self.token(policy['bundle'], 'token-after-operation')[1]
                        self.report['status'] = 'captured'
                        return
            except (LayoutNotReady, NodeNotReady) as error:
                last = str(error)
            self.save(); time.sleep(0.25)
        self.report['operation_diagnostic'] = {'diagnostic_only': True, 'side_effects': 'unknown_without_complete_journal'}
        try:
            layout, path = self.ui.layout(label='public-operation-timeout')
            self.report['operation_diagnostic']['layout'] = record(path)
            self.report['operation_diagnostic']['screenshot'] = record(self.ui.screenshot(label='public-operation-timeout'))
            self.report['operation_diagnostic']['AMS'] = self.raw('aa dump -a -u 100', 'public-operation-timeout-AMS')[1]
        except Exception as error:
            self.report['operation_diagnostic']['capture_error'] = str(error)
        self.save()
        raise ValueError('actual public operation timed out; preserve potentially changed data: ' + last)

    def seed(self):
        from batch_system_calendar_runtime_verify import validate_capture
        capture = validate_capture(self.args.seed, self.challenge, self.report['archive'])
        require(capture.get('run_id') == self.run and capture['archive'] == record(self.args.archive.resolve()) and
                capture.get('request', {}).get('role') == 'producer' and capture['request']['action'] == 'create', 'actual same-run create capture required')
        row = capture['artifacts']['producer']
        app = {'uid': row['uid'], 'accessTokenId': row['token_id']}
        _, own = protocol.parse(checked(capture['journal']).read_text(), capture['request'], app)
        require(own is not None, 'seed capture incomplete')
        cases = protocol.created(own, self.run)
        require(self.args.case in cases, 'actual owned event case required')
        self.report['seed_capture'] = record(self.args.seed.resolve())
        self.report['seed_event'] = cases[self.args.case]
        return cases[self.args.case]

    def view(self, expected=None, blank=False):
        deadline = time.monotonic() + min(self.args.timeout, 90)
        last = ''
        while time.monotonic() < deadline:
            try:
                if self.args.permission_decision:
                    decision = self.permission_click(self.args.permission_decision, PROVIDER)
                    if decision: self.report.setdefault('permission_clicks', []).append(decision)
                layout, path = self.ui.layout(bundle=PROVIDER, label='viewer')
                nodes = protocol.viewer_nodes(layout, blank)
                title, description, start, end = [nodes[k] for k in ('title', 'description', 'start', 'end')]
                text = title['attributes'].get('text', '') if title else ''
                if expected is not None:
                    if (text != expected['event']['title'] or description['attributes'].get('text', '') != expected['event']['description'] or
                            start['attributes'].get('text', '') != expected['display']['start'] or
                            end['attributes'].get('text', '') != expected['display']['end']):
                        raise NodeNotReady('persisted challenge title/description not yet visible')
                self.report['view'] = {'layout': record(path), 'screenshot': record(self.ui.screenshot(label='viewer-pixels')),
                    'nodes': nodes,
                    'expected_persisted': expected, 'expected_blank': blank}
                self.report['provider_token_after'] = self.token(PROVIDER, 'provider-token-after-view')[1]
                return
            except (LayoutNotReady, NodeNotReady) as error:
                last = str(error)
            self.save(); time.sleep(0.25)
        raise ValueError('viewer outcome timed out: ' + last)

    def independent(self, seed):
        from batch_system_calendar_runtime_verify import validate_capture
        capture = validate_capture(self.args.readback, self.challenge, self.report['archive'])
        require(capture['run_id'] == self.run and capture['boot_id'] == self.boot and
                capture['archive'] == record(self.args.archive.resolve()) and capture['request']['role'] == 'observer' and
                capture['request']['action'] == 'read', 'actual independent current-boot public read required')
        _, rows = protocol.parse(checked(capture['journal']).read_text(), capture['request'], self.apps[ROLES['observer']['bundle']])
        require(rows and not protocol.values(rows, 'error'), 'independent reader failed')
        values = protocol.values(rows, 'events', 'Calendar.getEvents')
        matches = [(event, value) for value in values for event in value['events'] if event.get('id') == seed['id']]
        require(len(matches) == 1, 'one actual independently read event required')
        event, value = matches[0]
        require(event['title'].startswith('QCAL_' + self.run + '_'), 'independent event is outside this run')
        display = [d for d in value['display'] if d['id'] == seed['id']]
        require(len(display) == 1, 'actual guest-locale time readback required')
        self.report['readback_capture'] = record(self.args.readback.resolve())
        return {'event': event, 'display': display[0]}

    def notification_click(self):
        seed = self.seed()
        from batch_system_calendar_runtime_verify import validate_capture
        observation = validate_capture(self.args.notification, self.challenge, self.report['archive'])
        require(observation.get('run_id') == self.run and observation.get('boot_id') == self.boot and
                observation['archive'] == record(self.args.archive.resolve()) and observation['request']['role'] == 'observer' and
                observation['request']['action'] == 'notifications', 'actual current-boot observer notification capture required')
        app = self.apps[ROLES['observer']['bundle']]
        _, own = protocol.parse(checked(observation['journal']).read_text(), observation['request'], app)
        want = protocol.notification(own, seed)
        require(want['uid'] == self.apps[PROVIDER]['uid'], 'actual reminder WantAgent UID differs from installed provider')
        expected = self.independent(seed) if self.args.expect == 'persisted' else None
        self.report.update(stage='notification-click', notification_capture=record(self.args.notification.resolve()), observed_want=want)
        self.permission_preflight()
        before, artifact = self.raw('aa dump -a -u 100', 'AMS-before-notification')
        self.report['AMS_before'] = artifact
        # Opening the shade is a gesture based on actual compositor geometry.
        # The notification tap itself must use its actual matching UI node.
        image = self.ui.screenshot(label='before-shade')
        from PIL import Image
        with Image.open(image) as screen:
            width, height = screen.size
        self.ui.shell(f'uitest uiInput swipe {width//2} 1 {width//2} {height*3//4}', 'open-real-notification-shade')
        bundle = self.plan.get('notification_bundle', 'com.ohos.systemui')
        require(bundle != PROVIDER and bundle not in {p['bundle'] for p in ROLES.values()}, 'notification node must belong to actual notification UI')
        transition_deadline = time.monotonic() + min(self.args.timeout, 30)
        while True:
            try:
                layout, path = self.ui.layout(label='notification-shade')
                node = clickable_for_text(layout, bundle, seed['event']['title'])
                break
            except (LayoutNotReady, NodeNotReady):
                if time.monotonic() >= transition_deadline: raise
                self.save(); time.sleep(.25)
        self.report['notification_click'] = {'layout': record(path), 'screenshot': record(self.ui.screenshot(label='notification-before-click')), 'selected_node': node}
        x, y, w, h = node['rect']
        self.ui.shell(f'uitest uiInput click {x+w//2} {y+h//2}', 'actual-notification-node-click')
        self.view(expected, self.args.expect == 'blank')
        self.report['AMS_after'] = self.raw('aa dump -a -u 100', 'AMS-after-notification')[1]
        self.report['status'] = 'captured'
        self.report['gaps'].append('actual notification clicked; onNewWant vs new-instance requires independent actual Ability lifecycle/mission evidence')

    def uri(self):
        seed = self.seed(); event = seed['event']
        uri = f"calendar://com.ohos.calendar?event_id={seed['id']}&start={event['startTime']}&end={event['endTime']}"
        kind = self.args.uri_case
        if kind == 'bad-uri': uri = uri.replace('calendar://', 'https://')
        elif kind == 'missing-id': uri = uri.replace('event_id=' + str(seed['id']) + '&', '')
        elif kind == 'bad-id': uri = uri.replace('event_id=' + str(seed['id']), 'event_id=0')
        # Deleted IDs are supplied from an actual delete capture, never guessed.
        if kind == 'deleted-id':
            from batch_system_calendar_runtime_verify import validate_capture
            deletion = validate_capture(self.args.deleted, self.challenge, self.report['archive'])
            require(deletion['run_id'] == self.run and deletion['archive'] == record(self.args.archive.resolve()), 'same-run actual delete required')
            app = self.apps[ROLES['producer']['bundle']]
            _, rows = protocol.parse(checked(deletion['journal']).read_text(), deletion['request'], app)
            require(not protocol.values(rows, 'error') and protocol.values(rows, 'event-deleted', 'Calendar.deleteEvent') ==
                    [{'id': seed['id'], 'case_id': self.args.case}], 'actual owned event delete missing')
            self.report['delete_capture'] = record(self.args.deleted.resolve())
        expected = self.independent(seed) if self.args.expect == 'persisted' else None
        self.report.update(stage='direct-uri-boundary', uri=uri, uri_case=kind)
        self.permission_preflight()
        self.report['launch'] = self.raw(shlex.join(['aa', 'start', '-b', PROVIDER, '-a', 'MainAbility', '-U', uri]), 'explicit-URI-boundary')[1]
        self.view(expected, self.args.expect == 'blank')
        self.report['AMS_after'] = self.raw('aa dump -a -u 100', 'AMS-after-URI')[1]
        self.report['status'] = 'captured'
        self.report['gaps'].append('explicit URI launch is only a boundary test and never notification delivery proof')

    def execute(self):
        try:
            self.setup()
            if self.args.stage == 'operation': self.operation(self.args.role, self.args.action, self.args.case)
            elif self.args.stage == 'notification-click': self.notification_click()
            elif self.args.stage == 'uri': self.uri()
            else:
                self.report['stage'] = 'viewer-snapshot'
                self.view(self.independent(self.seed()) if self.args.expect == 'persisted' else None, self.args.expect == 'blank')
                self.report['AMS_after'] = self.raw('aa dump -a -u 100', 'AMS-snapshot')[1]
                self.report['status'] = 'captured'
        except Exception as error:
            self.report['failures'].append(str(error))
        finally:
            self.report['hilog'] = None
            try:
                self.report['hilog'] = self.raw('hilog -x', 'actual-final-hilog')[1]
            except Exception as error:
                self.report['failures'].append('hilog: ' + str(error))
            self.save(); self.guest.close()
        return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'boot', 'hdc', 'challenge', 'plan', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--stage', choices=('operation', 'notification-click', 'uri', 'snapshot'), required=True)
    parser.add_argument('--role', choices=ROLES, default='producer')
    parser.add_argument('--action', choices=('permission', 'access', 'create', 'read', 'notifications', 'update', 'delete', 'cleanup', 'routes', 'locale'), default='read')
    parser.add_argument('--case', default='public-read')
    parser.add_argument('--seed', type=Path)
    parser.add_argument('--notification', type=Path)
    parser.add_argument('--deleted', type=Path)
    parser.add_argument('--readback', type=Path)
    parser.add_argument('--uri-case', choices=('valid', 'bad-uri', 'missing-id', 'bad-id', 'deleted-id'), default='valid')
    parser.add_argument('--expect', choices=('persisted', 'blank'), default='persisted')
    parser.add_argument('--permission-decision', choices=('allow', 'deny'))
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--lead-minutes', type=int, default=2)
    parser.add_argument('--spacing-minutes', type=int, default=2)
    args = parser.parse_args()
    require(1 <= args.timeout <= 900, 'bounded real wall-clock timeout required')
    require(args.stage not in ('notification-click', 'uri') or args.seed is not None, 'actual create capture required')
    require(args.stage != 'notification-click' or args.notification is not None, 'actual notification observer capture required')
    require(args.uri_case != 'deleted-id' or args.deleted is not None, 'actual delete capture required')
    require(args.stage == 'operation' or args.expect != 'persisted' or args.seed is not None and args.readback is not None,
            'persisted UI assertions require actual seed and independent observer read captures')
    report = Collector(args).execute()
    print(args.output / 'capture.json')
    raise SystemExit(0 if report['status'] == 'captured' and not report['failures'] else 1)


if __name__ == '__main__':
    main()
