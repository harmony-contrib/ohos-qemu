"""Run fixed capability cases on the original Owner's actual packaged guest.

Installed by trusted root code before Owner.run. There is no independent host
test, resource owner, VM, HDC server or native builder here. The original suite
body and original finish/quarantine path remain authoritative. Source fixtures
are built only to execute these real guest cases.
"""
from pathlib import Path
import json
import secrets
import traceback

from capability578_callers import prepare_callers
from capability578_https import OwnedHTTPS
from capability578_owned_io import OwnedIO, reference, require


class UnsettledCapability(RuntimeError):
    """A cleanup failure must escape independent_probe's recoverable handler."""


def data_file(ref):
    require(type(ref) is dict and set(ref) in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}),
            'actual immutable data reference required')
    require(reference(ref['path']) == {k: ref[k] for k in ('path', 'sha256')},
            'capability input bytes changed')
    path = Path(ref['path'])
    if 'bytes' in ref:
        require(path.stat().st_size == ref['bytes'], 'capability input length changed')
    return path


def read_inputs(ref, owner):
    value = json.loads(data_file(ref).read_text())
    require(type(value) is dict and set(value) == {
        'schema', 'source_commit', 'archive', 'providers', 'native_helpers', 'native_addons',
        'ui_plans', 'communications_services', 'permission_allow_text', 'livecaptions579'},
        'fixed capability fixture data required; no executable or expected-result field')
    require(value['schema'] == 'actual-qemu-capability578-inputs/v1' and
            data_file(value['archive']) == owner.archive and
            value['archive']['sha256'] == owner.config['archive']['sha256'],
            'capability fixtures belong to another package')
    build = json.loads((owner.vm.directory / 'build-inputs.json').read_text())
    require(build['source_git_revision'] == value['source_commit'],
            'capability inputs and actual packaged source differ')
    require(type(value['providers']) is dict and type(value['native_helpers']) is dict and
            type(value['native_addons']) is dict and set(value['native_addons']) == {'settings_idle579'} and
            type(value['ui_plans']) is dict and type(value['communications_services']) is dict and
            set(value['communications_services']) == {'ril', 'bluetooth'} and
            type(value['permission_allow_text']) is str and 0 < len(value['permission_allow_text']) <= 128,
            'actual finite package metadata required')
    for plan in value['ui_plans'].values():
        data_file(plan)
    return value


def run_on_owner(owner, inputs_ref, resources, **context):
    """Collect every known failure, stopping guest reuse on unsettled cleanup."""
    from apps_ui578_contract import CASES as APP_CASES
    from apps_ui578_bindings import bind as bind_apps
    from apps_ui578_runtime import run as run_apps
    from apps_ui578_verify import (verify_observations as verify_apps, verify_negative as verify_apps_negative,
        cleanup as replay_apps_cleanup)
    from communications578_bindings import bind as bind_communications
    from communications578_contract import PROFILES
    from communications578_runtime import run as run_communications
    from communications578_lifecycle import run_lifecycle
    from system_services578_bindings import bind as bind_services
    from system_services578_runtime import run as run_services
    from system_services578_peer import fixture_spec
    from settings_idle579_runtime import run as run_settings_idle
    from apps_providers579_bindings import bind as bind_providers
    from apps_providers579_project import IDS as PROVIDER_CASES
    from apps_providers579_runtime import run as run_providers
    from apps_providers579_wifi_bindings import bind as bind_wifi
    from apps_providers579_wifi_runtime import run as run_wifi
    from livecaptions579_runtime import run as run_captions
    from verify_screen_blink_evidence import verify_evidence as replay_original_blink

    guest = context['guest']
    owner.held_binding(guest)
    require(owner.vm is guest and Path(context['archive']) == owner.archive,
            'only the original held package guest may run capability cases')
    inputs = read_inputs(inputs_ref, owner)
    expected_plans = set(APP_CASES) - {'blink', 'accessibility-input'}
    require(set(inputs['ui_plans']) == expected_plans,
            'every applicable fixed apps UI case needs its actual source-backed plan')
    root = Path(context['suite_work']) / 'capability578'
    root.mkdir(exist_ok=False)
    boot = guest.report['test_environment']['boot_id']
    archive_sha = guest.report['archive_sha256']
    report = {'schema': 'actual-owned-qemu-capability578/v1',
        'archive_sha256': archive_sha, 'boot_id': boot, 'inputs': inputs_ref,
        'scope': 'fixed actual business and boundary flows; full audit is reconciled separately',
        'cases': [], 'failures': [], 'cleanup_complete': False,
        'first_artifact_behavior_gate_passed': False, 'closed_ids': []}
    settings_actions = None

    def save():
        (root / 'evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        context['suite_report']['capability578'] = reference(root / 'evidence.json')
        context['save_suite']()

    save()

    def fresh_io(group, case):
        # The system image is the one actually extracted for this held boot.
        # Provider HAPs are subsequently bound to BMS and installed hashes by
        # the real UI cases. No separate host image test is dispatched.
        package = {'archive': inputs['archive'],
            'system_image': reference(guest.directory / 'images/system.img'),
            'providers': inputs['providers']}
        if group == 'communications':
            package = {'native_helpers': inputs['native_helpers']}
        elif group == 'settings-idle':
            package = {'native_addons': inputs['native_addons'], 'settings_actions579': settings_actions}
        elif group == 'livecaptions':
            package = {'livecaptions579': inputs['livecaptions579']}
        io = OwnedIO(owner, guest, root / (group + '-' + case),
            run_id=secrets.token_hex(16), package_inputs=package,
            prepare_callers=prepare_callers, https_factory=OwnedHTTPS)
        resources.append(io)  # Retain intent before a callback can open anything.
        io.environment.update(communications578_services=inputs['communications_services'],
                              permission_allow_text=inputs['permission_allow_text'])
        if group == 'apps' and case == 'apn':
            # Keep the Apps provider package's original exact three keys.
            # Only the fixed virtual-SIM wrapper consumes this separate data.
            io.apn579_native_helper = inputs['native_helpers']['apn579']
        if group == 'providers':
            package['native_helpers'] = inputs['native_helpers']
            # Only actual already-completed same-guest family documents can
            # accompany these extra observations. Missing peer/owner work is
            # left unresolved by the provider's fixed runtime contract.
            io.apps579_family_results = {}
            for source_name, name in (('external-inputs', 'live_inputs578'),
                                      ('knowledge-holiday', 'knowledge')):
                original = context['suite_report']['checks'].get(source_name)
                if original is not None:
                    path = Path(original['evidence'])
                    value = json.loads(path.read_text())
                    require(value.get('archive_sha256') == archive_sha and
                            value.get('boot_id') == boot, 'prior family changed package or boot')
                    io.apps579_family_results[name] = reference(path)
        return io

    def attempt(group, case, execute, verify=None):
        context['same_guest']('before-capability578-' + group + '-' + case)
        io = fresh_io(group, case)
        row = {'group': group, 'case': case, 'boot_id': boot, 'status': 'running'}
        report['cases'].append(row); save()
        try:
            result = execute(io)
            result_path = io.output / 'stage-result.json'
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
            row['result'] = reference(result_path)
            if verify is not None:
                proof = verify(io, result)
                proof_path = io.output / 'raw-review.json'
                proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
                row['raw_review'] = reference(proof_path)
                if proof.get('runtime_pass') is False:
                    row['status'] = 'unresolved_actual_guest_boundary'
                    report['failures'].append(group + '/' + case + ': ' +
                        str(proof.get('classification', proof.get('reason', 'actual boundary remains unresolved'))))
                else:
                    row['status'] = 'actual_guest_flow_observed'
            else:
                row['status'] = 'actual_guest_flow_observed'
        except Exception as error:
            row.update(status='fail', error=type(error).__name__ + ': ' + str(error),
                       traceback=traceback.format_exc())
            report['failures'].append(group + '/' + case + ': ' + row['error'])
        finally:
            try:
                row['cleanup'] = io.close()
                if io._https is not None and io._https.thread_errors:
                    row.update(status='fail', peer_errors=list(io._https.thread_errors))
                    report['failures'].append(group + '/' + case + ': actual HTTPS content peer failed: ' +
                                              repr(io._https.thread_errors))
            except Exception as error:
                row['cleanup_error'] = type(error).__name__ + ': ' + str(error)
                save()
                raise UnsettledCapability('stop guest reuse after ' + group + '/' + case + ': ' + str(error)) from error
            save()
        context['same_guest']('after-capability578-' + group + '-' + case)
        return row

    def communications(io, profile):
        return run_communications(guest, bind_communications(io), profile=profile,
            run_id=io.run_id, boot_id=boot, output=io.output / 'runtime', executables=[
                io.hdc, '/usr/bin/nice',
                str(Path(io.environment['JAVA_HOME']) / 'bin/java')])

    def communications_review(io, result):
        require(result.get('status') in ('raw_behavior_matched_NOT_capability_closure',
                    'raw_lifecycle_matched_NOT_capability_closure') and not result.get('cleanup_errors'),
                'actual communications behavior or cleanup failed: ' + str(result.get('error')))
        for receipt in result['receipts']:
            require(receipt['boot_id'] == boot, 'communication receipt changed boot')
            if 'log' in receipt:
                originals = [r for r in io.receipts if r['argv'] == receipt['argv'] and
                             r['log'] == receipt['log']]
                require(len(originals) == 1 and originals[0]['stderr_ref'] == receipt['stderr_ref'] and
                        originals[0]['exit_code'] == receipt.get('transport_exit_code', receipt['exit_code']),
                        'communication receipt is not the actual original Owner command')
                data_file(receipt['log']); data_file(receipt['stdout_ref']); data_file(receipt['stderr_ref'])
            else:
                held = [r for r in io._long.values() if r['argv'] == receipt['argv'] and
                        reference(r['out']) == receipt.get('transport_stdout_ref') and
                        reference(r['err']) == receipt['stderr_ref']]
                require(len(held) == 1 and held[0]['child'].returncode == receipt['transport_exit_code'],
                        'communication transport is not the actual held process generation')
                data_file(receipt['stdout_ref'])
        # Existing typed runtime independently matches public journals to raw
        # modem/transport receipts. It deliberately leaves absent peer positive
        # sessions and whole-ID closure to the final current-package audit.
        return {'actual_raw_behavior_matched': True, 'boot_id': boot,
                'archive_sha256': archive_sha, 'whole_id_closure': False}

    # Observe the genuine initial registry state before this boot's first 5A
    # producer. Subsequent profiles may reuse only the fully cleaned same boot.
    order = ('observer',) + tuple(p for p in PROFILES if p != 'observer')
    for profile in order:
        attempt('communications', profile, lambda io, p=profile: communications(io, p), communications_review)

    def lifecycle(io):
        return run_lifecycle(guest, bind_communications(io), run_id=io.run_id,
            boot_id=boot, output=io.output / 'runtime', executables=[
                io.hdc, '/usr/bin/nice', str(Path(io.environment['JAVA_HOME']) / 'bin/java')])

    attempt('communications', 'observer-lifecycle', lifecycle, communications_review)

    def service_review(io, result):
        require(result.get('status') == 'pass' and result.get('failures') == [],
                'actual system-services case failed: ' + repr(result.get('failures')))
        originals = [io.ref_receipt(r) for r in io.receipts]
        for record in result['records']:
            for command in record['result']['commands']:
                require(command in originals and command['boot_id'] == boot,
                        'system-services callback is not an original held Owner command')
                data_file(command['stdout']); data_file(command['stderr'])
        return {'actual_raw_behavior_matched': True, 'boot_id': boot,
                'archive_sha256': archive_sha, 'whole_id_closure': False}

    for case in ('domain', 'session', 'ads'):
        def service(io, c=case):
            parameters = {'case': c, 'run_id': io.run_id, 'udid': io.udid, 'primary_user': 100}
            if c == 'domain':
                parameters['hosts'] = fixture_spec(io.run_id)['hosts']
            return run_services(guest, bind_services(io), parameters)
        attempt('system-services', case, service, service_review)

    for case in APP_CASES:
        bindings = {}

        def apps(io, c=case):
            if c == 'apn':
                from apn579_owned_runtime import run as run_apn_with_modem
                return run_apn_with_modem(io, {'case': c, 'output': str(io.output / 'runtime'),
                    'ui_plan': inputs['ui_plans'][c], 'full_blink': True}, bindings)
            bindings.update(bind_apps(io))
            return run_apps(guest, bindings, {'case': c, 'output': str(io.output / 'runtime'),
                'ui_plan': inputs['ui_plans'].get(c), 'full_blink': True})

        def apps_review(io, result):
            def bind_actual_receipt(observed):
                keys = ('argv', 'exit_code', 'stdout_ref', 'stderr_ref', 'log', 'boot_id', 'timed_out')
                originals = []
                for retained in io.receipts:
                    row = dict(retained)
                    if 'shell_exit_code' in row:
                        row.update(exit_code=row['shell_exit_code'], stdout_ref=row['shell_stdout_ref'])
                    if all(observed.get(k) == row.get(k) for k in keys):
                        originals.append(row)
                require(len(originals) == 1, 'apps root receipt is not the actual held Owner operation')
                for key in ('stdout_ref', 'stderr_ref', 'log'):
                    data_file(observed[key])

            def cleanup_replay(actual, value, records, rows):
                for observed in actual['records']:
                    bind_actual_receipt(observed)
                return replay_apps_cleanup(actual, value, records, rows)

            def boundary_replay(proof, expected_archive, expected_boot):
                require(proof['archive_sha256'] == expected_archive == archive_sha and
                        proof['boot_id'] == expected_boot == boot,
                        'actual boundary changed archive or boot')
                bind_actual_receipt(proof['bms'])

            def image_guard(kind, expected_archive):
                require(expected_archive == archive_sha, 'provider replay changed archive')
                # Re-read every current package input, then replay the original
                # concrete binding. Installed bytes are independently checked
                # in the apps raw oracle rather than accepted from this data.
                read_inputs(inputs_ref, owner)
                for entry in inputs['providers'][kind]['modules'].values():
                    data_file(entry['hap'])
                return bindings['verify_provider_image'](guest, kind)

            def qmp_replay(boundary, expected_archive, expected_boot):
                require(expected_archive == archive_sha and expected_boot == boot,
                        'QMP boundary changed archive or boot')
                for observed in boundary['qmp']:
                    require(observed in io.qmp_receipts and observed.get('completed') is True,
                            'QMP claim is not an original held socket operation')
                    data_file(observed['request']); data_file(observed['response'])

            def blink_replay(expected_archive, expected_boot):
                require(expected_archive == archive_sha and expected_boot == boot,
                        'original blink replay changed package or boot')
                original = Path(context['suite_work']) / 'screen-blink/evidence.json'
                env = guest.report['test_environment']
                return replay_original_blink(json.loads(original.read_text()), archive_sha, boot,
                    env['guest_arch'], env['device_type'], guest.target)

            if result.get('boundary_observations') is not None:
                return verify_apps_negative(result, guest.report, archive_sha256=archive_sha,
                    boot_id=boot, hdc=io.hdc, target=io.target,
                    original_cleanup_replay=cleanup_replay, original_boundary_replay=boundary_replay)
            return verify_apps(result, guest.report, archive_sha256=archive_sha,
                boot_id=boot, hdc=io.hdc, target=io.target, original_image_guard=image_guard,
                original_cleanup_replay=cleanup_replay, original_qmp_replay=qmp_replay,
                original_blink_replay=blink_replay)

        row = attempt('apps', case, apps, apps_review)
        if case == 'accessibility-settings':
            snapshot = root / 'apps-accessibility-settings-owner.json'
            snapshot.write_text(json.dumps(guest.report, ensure_ascii=False, indent=2) + '\n')
            settings_actions = {'report': row.get('result'), 'owner': reference(snapshot)}

    def settings_idle_review(io, result):
        require(result.get('status') == 'observed' and result.get('archive_sha256') == archive_sha and
                result.get('boot_id') == boot, 'actual conditional-idle runtime failed')
        value = json.loads(data_file(result['report']).read_text())
        require(value['failures'] == [] and value['cleanup_verified'] is True,
                'actual conditional-idle semantics or cleanup failed')
        # The stage replays actual nonce journals, native IPC and the prior
        # Apps UI slice. Bind its transport records to this original IO too.
        originals = [io.ref_receipt(r) for r in io.receipts]
        for observed in value['commands']:
            require(observed['receipt'] in originals, 'conditional-idle command is not original held IO')
            data_file(observed['body'])
        return {'actual_raw_behavior_matched': True, 'boot_id': boot,
                'archive_sha256': archive_sha, 'whole_id_closure': False}

    attempt('settings-idle', 'conditional', run_settings_idle, settings_idle_review)

    def caption_case(io):
        return {'evidence': run_captions(io), 'archive_sha256': archive_sha, 'boot_id': boot}

    def caption_review(io, result):
        observed = json.loads(data_file(result['evidence']).read_text())
        require(observed.get('schema') == 'actual-livecaptions579-runtime/v1' and
                observed.get('archive_sha256') == archive_sha and observed.get('boot_id') == boot and
                observed.get('runtime_validated') is True and observed.get('cleanup_complete') is True and
                observed.get('failures') == [] and len(observed.get('cases', [])) == 7,
                'complete actual speech, consent, lifecycle and cleanup required')
        actual = [io.ref_receipt(r) for r in io.receipts]
        for receipt in observed['commands']:
            require(receipt['receipt'] in actual, 'caption command is not the original held IO')
        return {'actual_raw_behavior_matched': True, 'archive_sha256': archive_sha,
                'boot_id': boot, 'whole_id_closure': False}

    attempt('livecaptions', 'english', caption_case, caption_review)

    def provider_review(io, result):
        require(result.get('archive_sha256') == archive_sha and result.get('boot_id') == boot and
                result.get('runtime_pass') is False and result.get('closed_requirement_ids') == [],
                'provider observations must retain their original aggregate boundary')
        require(result.get('failures') == [] and result.get('cleanup', {}).get('failures') == [],
                'actual provider flow or restoration failed: ' + repr(result.get('failures')))
        actual = [io.ref_receipt(row) for row in io.receipts]
        for operation in result['operations']:
            record = operation.get('record')
            if type(record) is dict and 'commands' in record:
                require(record.get('boot_id') == boot and record.get('archive_sha256') == archive_sha,
                        'provider command group changed package or boot')
                for receipt in record['commands']:
                    require(receipt in actual, 'provider receipt was not emitted by the held original IO')
        pending = result['unresolved_requirements']
        return {'actual_raw_behavior_matched': True, 'boot_id': boot,
                'archive_sha256': archive_sha, 'whole_id_closure': False,
                'runtime_pass': not pending,
                'classification': 'unresolved actual guest work: ' + repr(pending)}

    for case in PROVIDER_CASES:
        if case in ('photos', 'photosform'):
            # Photos runs while the original Knowledge actor still holds its
            # assets. Recreating a fixture here would lose that real lifecycle.
            continue
        def provider_case(io, c=case):
            runner, binder = (run_wifi, bind_wifi) if c == 'wifi' else (run_providers, bind_providers)
            return runner(guest, binder(io), {'case': c, 'run_id': io.run_id,
                'profile': guest.report['test_environment']['device_type']})
        attempt('providers', case, provider_case, provider_review)

    read_inputs(inputs_ref, owner)
    report['cleanup_complete'] = True
    report['status'] = 'fail' if report['failures'] else 'actual_guest_flows_observed'
    if report['failures']:
        context['suite_report']['failures'].extend('capability578: ' + e for e in report['failures'])
    save()
    return report


def install_on_original_children(children, inputs_ref=None, *, deferred_inputs=None, held_stage=None, after_suite=None):
    """Add a fixed same-Owner hook; keep original suite validation and finish."""
    require((inputs_ref is None) != (deferred_inputs is None),
            'one immutable input Ref or fixed root deferred producer required')
    if inputs_ref is not None:
        data_file(inputs_ref)
    else:
        require(callable(deferred_inputs), 'fixed source-pinned root input producer required')
    require(after_suite is None or callable(after_suite), 'fixed root post-suite implementation required')
    require(held_stage is None or callable(held_stage), 'fixed root held-guest implementation required')
    original_suite_function = children.suite_function
    require(getattr(original_suite_function, '__self__', None) is children,
            'original bound suite verifier required')
    installed = {'owner': None, 'resources': [], 'inputs': inputs_ref, 'resolving': False}

    def resolve_inputs(owner):
        owner.held_binding(owner.vm)
        if installed['inputs'] is None:
            require(not installed['resolving'] and installed['owner'] is owner,
                    'one nonrecursive producer on the original held Owner required')
            installed['resolving'] = True
            try:
                actual = deferred_inputs(owner, installed['resources'])
                require(type(actual) is dict and set(actual) == {'path', 'sha256'},
                        'actual deferred producer must return an immutable input Ref')
                data_file(actual)
                read_inputs(actual, owner)
                installed['inputs'] = dict(actual)
            finally:
                installed['resolving'] = False
        read_inputs(installed['inputs'], owner)
        return installed['inputs']

    def suite_function(original):
        canonical = original_suite_function(original)

        def full(args, *, owned_command, owned_guest_factory, owned_select_hook, owned_graphics3d_hook):
            owner = getattr(owned_guest_factory, '__self__', None)
            require(owner is not None and owner.children is children and all(
                getattr(callback, '__self__', None) is owner for callback in
                (owned_command, owned_select_hook, owned_graphics3d_hook)),
                'capability stage requires the unchanged original same-Owner callbacks')
            require(installed['owner'] is None, 'capability stage cannot move to another Owner')
            installed['owner'] = owner
            original_finish = owner.finish

            def finish():
                errors = []
                for io in reversed(installed['resources']):
                    if not io._closed:
                        try:
                            io.close()
                        except Exception as error:
                            errors.append(type(error).__name__ + ': ' + str(error))
                try:
                    original_finish()  # Original VM/HDC/groups/env settlement.
                finally:
                    if errors:
                        # Owner.run's original quarantine retains the SAME lease
                        # after all possible original disposal has been tried.
                        owner.cleanup_complete = False
                        raise UnsettledCapability('original capability resources remain: ' + repr(errors))

            owner.finish = finish

            def command_with_knowledge_inputs(argv, *, label, timeout, env, log):
                # The actual original argv is retained exactly. Only this
                # known CLI receives a fixed data manifest in its environment.
                # No executable, expected result or callback comes from data.
                entry = Path(__file__).with_name('batch_media_knowledge_suite.py')
                if len(argv) > 1 and Path(argv[1]) == entry and label == 'actual-knowledge-holiday-complete-boundaries':
                    require(owner.vm is not None and '--apps579-artifacts' not in argv,
                            'one original live Knowledge actor requires fresh prepared consumers')
                    guest = owner.vm
                    owner.held_binding(guest)
                    resolve_inputs(owner)
                    key = 'QEMU_TEST_APPS579_KNOWLEDGE_ARTIFACTS'
                    child_environment = dict(owner.env if env is None else env)
                    require(key not in child_environment, 'untrusted prior Photos artifact override')
                    io = OwnedIO(owner, guest, owner.output / ('knowledge579-callers-' + secrets.token_hex(8)),
                        run_id=secrets.token_hex(16), package_inputs={},
                        prepare_callers=prepare_callers, https_factory=OwnedHTTPS)
                    installed['resources'].append(io)
                    try:
                        from apps_providers579_knowledge import prepare_knowledge_manifest
                        prepared = prepare_callers(io, 'apps_providers579', 'photos', io.run_id,
                            ('normal', 'foreign', 'janitor'),
                            {'profile': guest.report['test_environment']['device_type'], 'udid': guest.udid})
                        manifest = prepare_knowledge_manifest(io, prepared)
                        data_file(manifest)
                        child_environment[key] = manifest['path']
                    finally:
                        io.close()
                    actual = owned_command(argv, label=label, timeout=timeout,
                                           env=child_environment, log=log)
                    data_file(manifest)
                    return actual
                return owned_command(argv, label=label, timeout=timeout, env=env, log=log)

            def graphics_and_capabilities(**context):
                # The original blink batch is already complete at this seam.
                # Collect all safely cleaned additional cases even if Graphics
                # subsequently records an independent business failure.
                run_on_owner(owner, resolve_inputs(owner), installed['resources'], **context)
                if held_stage is not None:
                    held_stage(owner, installed['resources'], resolve_inputs(owner), **context)
                return owned_graphics3d_hook(**context)

            def select_with_package_inputs(**context):
                # BMS and the original fresh guest are ready here. Export the
                # actual installed system HAPs before Share/MMS or Knowledge
                # consumers need their immutable package input descriptors.
                resolve_inputs(owner)
                original_result = owned_select_hook(**context)
                factory = getattr(owner, 'capability579_export_factory', None)
                require(deferred_inputs is not None and
                    type(getattr(factory, 'exports', None)) is dict and
                    'mms_facts' in factory.exports,
                    'actual selected same-package MMS export required for new URI boundaries')
                from mms_share579_integration import run_after_original_share
                run_after_original_share(owner, installed['resources'], original_result,
                    mms_facts=factory.exports['mms_facts'], context=context)
                return original_result

            result = canonical(args, owned_command=command_with_knowledge_inputs, owned_guest_factory=owned_guest_factory,
                owned_select_hook=select_with_package_inputs, owned_graphics3d_hook=graphics_and_capabilities)
            if after_suite is not None:
                require(installed['inputs'] is not None, 'paired stage needs the actual first guest input export')
                pair = after_suite(owner, installed['resources'], installed['inputs'])
                require(type(pair) is dict and pair.get('first_artifact_behavior_gate_passed') is False,
                        'actual paired observations cannot replace the complete first-artifact gate')
                (owner.output / 'paired579-after-suite.json').write_text(json.dumps(pair, indent=2) + '\n')
            return result

        return full

    children.suite_function = suite_function
