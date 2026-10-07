#!/usr/bin/env python3
"""Require real closure for every audited gap, not a handful of green samples.

Only explicitly registered behavior verifiers may close findings. Unregistered
Native ABI, ArkTS exports/classes/constants, permissions and provider/backend
gaps remain unresolved. The checked-in old ledger establishes requirements,
never runtime success; every accepted child must match this new archive/boot.
"""
import argparse
import json
from pathlib import Path

from run_root_probe import digest

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / 'docs/capability-audit/native-arkts11-gap-ledger.json'

NETFIREWALL_OPTIONAL = 'native:SystemCapability.Communication.NetManager.NetFirewall:libnet_trafficfilter.so'
VIDEO_PROCESSING_OPTIONAL = frozenset({
    'native:SystemCapability.Multimedia.VideoProcessingEngine:libimage_processing.so',
    'native:SystemCapability.Multimedia.VideoProcessingEngine:libvideo_processing.so',
})
AUDIO_SUITE_NATIVE = 'native:SystemCapability.Multimedia.Audio.SuiteEngine:libohaudiosuite.so'


def optional_profile_resolutions(optional, device):
    """Close only false declarations absent from the actual guest SysCap image."""
    optional = set(optional)
    resolved = set()
    if device == 'phone' and NETFIREWALL_OPTIONAL in optional:
        resolved.add('behavior:netfirewall-feature-disabled')
    if VIDEO_PROCESSING_OPTIONAL <= optional:
        resolved.add('behavior:video-processing-libraries-not-packaged')
    return resolved


def requirements(device):
    rows = {}

    def add(identifier, row):
        if identifier in rows:
            raise ValueError('duplicate audited gap identifier: ' + identifier)
        rows[identifier] = row

    for row in device['native_abi_gaps']:
        add('native:' + row['syscap'] + ':' + row['library'], row)
    for row in device['arkts11_module_load_gaps']:
        add('arkts_load:' + row['module'], row)
    for row in device['arkts11_runtime_export_gaps']:
        for missing in row['missing']:
            add('arkts_export:' + row['module'] + ':' + missing['name'], missing)
    for row in device['arkts11_compiled_constant_enum_contracts']:
        for contract in row['contracts']:
            add('const_enum:' + row['module'] + ':' + contract['name'], contract)
    for row in device['permission_registry_gaps']:
        add('permission:' + row['permission'], row)
    for row in device['runtime_behavior_gaps']:
        add('behavior:' + row['id'], row)
    if not rows:
        raise ValueError('empty audit baseline cannot demonstrate complete closure')
    return rows


def behavior_results(runtime, boot_id, archive_sha, device_type=None):
    closed = {}
    actual_modules = None

    def child(relative):
        path = runtime / relative
        if path.is_symlink() or not path.is_file():
            return None
        result = json.loads(path.read_text())
        if (result.get('status') != 'pass' or result.get('boot_id') != boot_id or
                result.get('archive_sha256') != archive_sha):
            return None
        return path, result

    web = child('web/evidence.json')
    if web and web[1].get('persona') == 'web':
        verification = Path(web[1].get('result', ''))
        raw = web[0].parent / 'results.log'
        if (verification.is_file() and digest(verification) == web[1].get('result_sha256') and
                raw.is_file() and digest(raw) == web[1].get('raw_results_sha256')):
            from verify_web_results import verify
            if verify(raw.read_text()).get('status') == 'pass':
                for finding in ('web-basic-load-gpu-context-failure', 'webgl-context-unavailable'):
                    closed['behavior:' + finding] = {'evidence': str(web[0]), 'sha256': digest(web[0]),
                        'verifier': 'verify_web_results:JS_DOM_Canvas_WebGL_callbacks_renderer_recovery'}
    vulkan = child('vulkan.json')
    if vulkan:
        expected = {'vulkan-device', 'vulkan-headless', 'vulkan-ohos-surface', 'vulkan-window'}
        children = vulkan[1].get('results', {})
        if set(children) == expected and all(Path(row['evidence']).is_file() and
                not Path(row['evidence']).is_symlink() and digest(Path(row['evidence'])) == row['sha256'] and
                json.loads(Path(row['evidence']).read_text()).get('status') == 'pass' for row in children.values()):
            closed['behavior:vulkan-no-icd'] = {'evidence': str(vulkan[0]), 'sha256': digest(vulkan[0]),
                'verifier': 'Vulkan_native_submission_readback_WSI_resize_real_compositor'}
    bindings = child('native-bindings/evidence.json')
    if bindings:
        document = bindings[1]
        from run_native_bindings_e2e import declared_modules, verify_modules
        snapshot_document = json.loads(Path(document['source_snapshot']).read_text())
        if digest(Path(document['source_snapshot'])) == document['source_snapshot_sha256']:
            project = Path(snapshot_document['snapshot']) / 'examples-ui'
            modules = declared_modules((project / 'scripts/run-ohostest.sh').read_text())
            actual = verify_modules(project, bindings[0].parent / 'diagnostics', modules)
            actual_modules = actual if actual == document.get('modules') else None
            if actual == document.get('modules') and actual.get('qos', {}).get('case_count', 0) > 0:
                closed['behavior:qos-authorization-backend'] = {'evidence': str(bindings[0]),
                    'sha256': digest(bindings[0]), 'verifier': 'complete_current_QoS_Hypium_auth_worker_boundary_suite',
                    'not_claimed': 'scheduler_latency_or_physical_performance'}
    permissions = child('permission-registry/result.json')
    if permissions and permissions[1].get('kind') == 'permission-registry':
        document = permissions[1]
        definitions = Path(document.get('definitions', ''))
        raw = permissions[0].parent / 'stdout.jsonl'
        if (document.get('kernel_boot_id_unchanged') is True and definitions.is_file() and
                not definitions.is_symlink() and digest(definitions) == document.get('definitions_sha256') and
                raw.is_file() and not raw.is_symlink() and digest(raw) == document.get('log_sha256')):
            from verify_permission_results import verify
            actual = verify(json.loads(definitions.read_text()), raw.read_text(), document['device'],
                            document['run_id'], document['probe_exit_code'])
            if actual != document.get('result'):
                raise ValueError('actual permission metadata verification differs from recorded result')
            for row in map(json.loads, raw.read_text().splitlines()):
                if row.get('kind') == 'definition' and row.get('result') == 0:
                    closed['permission:' + row['permissionName']] = {'evidence': str(permissions[0]),
                        'sha256': digest(permissions[0]),
                        'verifier': 'complete_actual_AccessToken_definition_policy_and_four_query_boundaries',
                        'not_claimed': 'application_authorization_or_privilege_grant'}
            # The aggregate finding describes absent definitions, not grants.
            for profile_device, baseline in json.loads(LEDGER.read_text())['devices'].items():
                names = ['permission:' + row['permission'] for row in baseline['permission_registry_gaps']]
                if document['device'] == profile_device and names and all(name in closed for name in names):
                    closed['behavior:api26-permission-registry-gaps-' + profile_device] = {
                        'evidence': str(permissions[0]), 'sha256': digest(permissions[0]),
                        'verifier': 'all_original_registry_gaps_resolved_with_actual_source_policy_metadata',
                        'not_claimed': 'application_authorization_or_privilege_grant'}
    vibrator = child('vibrator-hdi/result.json')
    if vibrator and actual_modules and actual_modules.get('vibrator', {}).get('cases') == [
            'start and cancel', 'customStart from rawfile']:
        document = vibrator[1]
        raw = vibrator[0].parent / 'stdout.jsonl'
        probe = Path(document.get('probe', ''))
        if (document.get('kind') == 'vibrator-hdi' and document.get('kernel_boot_id_unchanged') is True
                and raw.is_file() and not raw.is_symlink() and digest(raw) == document.get('log_sha256')
                and probe.is_file() and not probe.is_symlink() and digest(probe) == document.get('probe_sha256')):
            from verify_vibrator_hdi_results import verify
            actual = verify(raw.read_text(), document['arch'], document['run_id'], document['probe_exit_code'])
            if actual != document.get('result'):
                raise ValueError('Vibrator HDI result differs from actual complete boundary observations')
            closed['behavior:phone-device-service-basic-probes'] = {
                'evidence': str(vibrator[0]), 'sha256': digest(vibrator[0]),
                'ordinary_bindings_evidence': str(bindings[0]), 'ordinary_bindings_sha256': digest(bindings[0]),
                'verifier': '14_actual_HDI_time_backend_cases_and_strict_ordinary_CAPI_JSON_Hypium_calls',
                'not_claimed': 'physical_motor_or_HD_frequency_intensity_modulation'}
    renderer = child('audio-stream/evidence.json')
    if renderer and renderer[1].get('persona') == 'audio-stream':
        document = renderer[1]
        raw = renderer[0].parent / 'results.log'
        identity = renderer[0].parent / 'application-identity.json'
        result = Path(document.get('result', ''))
        if (raw.is_file() and not raw.is_symlink() and digest(raw) == document.get('raw_results_sha256')
                and identity.is_file() and not identity.is_symlink()
                and digest(identity) == document.get('ordinary_identity_sha256')
                and result.is_file() and not result.is_symlink() and digest(result) == document.get('result_sha256')):
            from run_normal_hap_probe import require_normal_identity
            from verify_audio_stream_results import verify
            require_normal_identity(identity.read_text())
            actual = verify(raw.read_text(), document['run_id'], identity.read_text())
            verification = json.loads(result.read_text())
            if (verification.get('status') != 'pass' or verification.get('results') != actual or
                    verification.get('archive_sha256') != archive_sha):
                raise ValueError('Renderer closure differs from actual complete ordinary PCM/lifecycle observations')
            closed['behavior:audio-renderer-data-path-unavailable'] = {
                'evidence': str(renderer[0]), 'sha256': digest(renderer[0]),
                'verifier': 'ordinary_account100_71_actual_PCM_callback_state_recreate_and_error_boundary_rows',
                'not_claimed': 'Capturer_host_speaker_interrupt_haptic_or_distributed_audio'}
    constants = child('const-enum/evidence.json')
    if constants and constants[1].get('persona') == 'const-enum':
        document = constants[1]
        raw = constants[0].parent / 'results.log'
        inputs = Path(document.get('compiled_contract_inputs', ''))
        result = Path(document.get('result', ''))
        if (raw.is_file() and not raw.is_symlink() and digest(raw) == document.get('raw_results_sha256')
                and inputs.is_file() and not inputs.is_symlink()
                and digest(inputs) == document.get('compiled_contract_inputs_sha256')
                and result.is_file() and digest(result) == document.get('result_sha256')):
            from verify_const_enum_results import verify
            actual = verify(raw.read_text(), json.loads(inputs.read_text()), document['run_id'], document['arch'])
            if actual != json.loads(result.read_text()).get('result'):
                raise ValueError('compiled enum result differs from actual complete SDK caller')
            for identifier in actual['contracts']:
                closed[identifier] = {'evidence': str(constants[0]), 'sha256': digest(constants[0]),
                    'verifier': 'actual_API26_typed_all_member_compilation_and_ordinary_guest_execution',
                    'not_claimed': 'NAPI_class_export_or_associated_service_backend_or_permission'}
    for mode, port in (('legacy', 'parentPort'), ('thread', 'workerPort')):
        persona = 'worker-' + mode
        worker = child(persona + '/evidence.json')
        if not worker or worker[1].get('persona') != persona:
            continue
        document = worker[1]
        raw = worker[0].parent / 'results.log'
        identity = worker[0].parent / 'application-identity.json'
        inputs = Path(document.get('compiled_contract_inputs', ''))
        result = Path(document.get('result', ''))
        if not all(path.is_file() and not path.is_symlink() and digest(path) == document.get(key)
                   for path, key in ((raw, 'raw_results_sha256'), (identity, 'ordinary_identity_sha256'),
                                     (inputs, 'compiled_contract_inputs_sha256'), (result, 'result_sha256'))):
            continue
        from worker_contracts import verify_inputs
        from verify_worker_results import verify
        verify_inputs(json.loads(inputs.read_text()), inputs.parent, document['run_id'], document['arch'], mode)
        actual = verify(raw.read_text(), document['run_id'], identity.read_text(), mode)
        verification = json.loads(result.read_text())
        if (verification.get('status') != 'pass' or verification.get('mode') != mode or
                verification.get('run_id') != document['run_id'] or verification.get('result') != actual or
                verification.get('archive_sha256') != archive_sha or
                verification.get('compiled_inputs_sha256') != digest(inputs) or
                verification.get('results_sha256') != digest(raw) or
                verification.get('application_identity_sha256') != digest(identity)):
            raise ValueError('Worker port closure differs from its exact compiled ordinary-app lifecycle')
        closed['arkts_export:@ohos.worker:' + port] = {
            'evidence': str(worker[0]), 'sha256': digest(worker[0]),
            'verifier': 'ordinary_worker_context_two_generations_256_actual_words_and_closed_buffer_boundaries',
            'not_claimed': 'main_thread_port_export_TaskPool_sendable_shared_memory_or_all_Worker_APIs'}
    modes = child('contact-sync-mode/evidence.json')
    if modes and modes[1].get('persona') == 'contact-sync-mode':
        document = modes[1]
        raw = modes[0].parent / 'results.log'
        identity = modes[0].parent / 'application-identity.json'
        inputs = Path(document.get('compiled_contract_inputs', ''))
        result = Path(document.get('result', ''))
        if all(path.is_file() and not path.is_symlink() and digest(path) == document.get(key)
               for path, key in ((raw, 'raw_results_sha256'), (identity, 'ordinary_identity_sha256'),
                                 (inputs, 'compiled_contract_inputs_sha256'), (result, 'result_sha256'))):
            from contact_sync_mode_contract import CONTRACT, AUDIO_CONTRACT, PHOTO_CONTRACT, verify_inputs
            from verify_contact_sync_mode_results import verify
            verify_inputs(json.loads(inputs.read_text()), document['run_id'], document['arch'])
            actual = verify(raw.read_text(), document['run_id'], identity.read_text())
            checked = json.loads(result.read_text())
            if (checked.get('status') != 'pass' or checked.get('result') != actual or
                    checked.get('archive_sha256') != archive_sha or checked.get('run_id') != document['run_id'] or
                    checked.get('arch') != document['arch'] or checked.get('compiled_inputs_sha256') != digest(inputs) or
                    checked.get('results_sha256') != digest(raw) or
                    checked.get('application_identity_sha256') != digest(identity)):
                raise ValueError('ContactSyncMode closure differs from actual typed/native ordinary-app values')
            closed[CONTRACT] = {'evidence': str(modes[0]), 'sha256': digest(modes[0]),
                               'verifier': 'typed_and_native_public_enum_own_members_and_exact_values',
                               'not_claimed': 'contacts_sync_storage_or_provider_backend'}
            closed[AUDIO_CONTRACT] = {'evidence': str(modes[0]), 'sha256': digest(modes[0]),
                               'verifier': 'typed_and_native_public_enum_own_members_and_exact_values',
                               'not_claimed': 'microphone_blocking_events_routing_or_audio_backend'}
            closed[PHOTO_CONTRACT] = {'evidence': str(modes[0]), 'sha256': digest(modes[0]),
                               'verifier': 'typed_and_native_public_enum_own_members_and_exact_values',
                               'not_claimed': 'fusion_provider_album_storage_sync_or_permission_behavior'}
    exports = child('arkts-exports/evidence.json')
    if exports and exports[1].get('persona') == 'arkts-exports' and device_type is not None:
        document = exports[1]
        raw = exports[0].parent / 'results.log'
        inputs = Path(document.get('compiled_contract_inputs', ''))
        result = Path(document.get('result', ''))
        if (raw.is_file() and not raw.is_symlink() and digest(raw) == document.get('raw_results_sha256') and
                inputs.is_file() and not inputs.is_symlink() and
                digest(inputs) == document.get('compiled_contract_inputs_sha256') and
                result.is_file() and not result.is_symlink() and digest(result) == document.get('result_sha256')):
            from verify_arkts_exports_results import verify
            actual = verify(raw.read_text(), json.loads(inputs.read_text()), document['run_id'], document['arch'])
            if actual != json.loads(result.read_text()).get('modules'):
                raise ValueError('export collection differs from complete actual ordinary-app reflection')
            # The ordinary application evidence records ABI and boot identity;
            # the device profile belongs to the enclosing package-bound suite.
            metadata = json.loads(LEDGER.read_text())['devices'][device_type]
            expected = {row['module']: row['missing'] for row in metadata['arkts11_runtime_export_gaps']}
            for module in actual:
                if (module['load_status'] != 0 or module['load_exception'] or module['module_type'] not in (6, 7)
                        or module['collection_status'] != 0 or module['collection_exception']):
                    continue
                proof = {'evidence': str(exports[0]), 'sha256': digest(exports[0]),
                         'verifier': 'actual_API26_NAPI_all_own_property_name_and_value_type',
                         'not_claimed': 'compiled_injected_factory_type_or_provider_backend_behavior'}
                closed['arkts_load:' + module['module']] = proof
                properties = {row['name']: row for row in module['properties']
                              if row['read_status'] == 0 and not row['read_exception']}
                for requirement in expected.get(module['module'], []):
                    value = properties.get(requirement['name'], {}).get('value_type')
                    kind = requirement['kind']
                    permitted = ({7} if kind in ('function', 'class') else {6} if kind == 'namespace'
                                 else set(range(2, 10)) if kind == 'variable' else set())
                    if (kind == 'enum' and properties.get(requirement['name'], {}).get('enum_contract_applicable') and
                            properties[requirement['name']].get('enum_contract_valid')):
                        permitted = {6}
                    if value in permitted:
                        closed['arkts_export:' + module['module'] + ':' + requirement['name']] = proof
    matrix = child('matrix4/evidence.json')
    if matrix and matrix[1].get('persona') == 'matrix4':
        document = matrix[1]
        raw = matrix[0].parent / 'results.log'
        identity = matrix[0].parent / 'application-identity.json'
        inputs = Path(document.get('compiled_contract_inputs', ''))
        result = Path(document.get('result', ''))
        if all(path.is_file() and not path.is_symlink() and digest(path) == document.get(key)
               for path, key in ((raw, 'raw_results_sha256'), (identity, 'ordinary_identity_sha256'),
                                 (inputs, 'compiled_contract_inputs_sha256'), (result, 'result_sha256'))):
            from verify_matrix4_results import verify_inputs, verify
            verify_inputs(json.loads(inputs.read_text()), document['run_id'], document['arch'])
            actual = verify(raw.read_text(), document['run_id'], identity.read_text())
            verification = json.loads(result.read_text())
            if (verification.get('status') != 'pass' or verification.get('results') != actual or
                    verification.get('run_id') != document['run_id'] or
                    verification.get('arch') != document['arch'] or
                    verification.get('archive_sha256') != archive_sha or
                    verification.get('inputs_sha256') != digest(inputs) or
                    verification.get('results_sha256') != digest(raw) or
                    verification.get('application_identity_sha256') != digest(identity)):
                raise ValueError('Matrix4 closure differs from actual complete typed arithmetic/boundaries')
            for name in ('combine', 'copy', 'invert', 'rotate', 'scale', 'transformPoint', 'translate'):
                closed['arkts_export:@ohos.matrix4:' + name] = {
                    'evidence': str(matrix[0]), 'sha256': digest(matrix[0]),
                    'verifier': 'ordinary_API26_typed_root_arithmetic_boundaries_objects_and_64_roundtrips',
                    'not_claimed': 'all_ArkUI_exports_layout_or_compositor_behavior'}
    factories = child('factory-objects/evidence.json')
    if factories and factories[1].get('persona') == 'factory-objects':
        document = factories[1]
        raw = factories[0].parent / 'results.log'
        identity = factories[0].parent / 'application-identity.json'
        inputs = Path(document.get('compiled_contract_inputs', ''))
        result = Path(document.get('result', ''))
        if all(path.is_file() and not path.is_symlink() and digest(path) == document.get(key)
               for path, key in ((raw, 'raw_results_sha256'), (identity, 'ordinary_identity_sha256'),
                                 (inputs, 'compiled_contract_inputs_sha256'), (result, 'result_sha256'))):
            from verify_factory_objects_results import CONTRACTS, verify_inputs, verify
            verify_inputs(json.loads(inputs.read_text()), document['run_id'], document['arch'])
            actual = verify(raw.read_text(), document['run_id'], identity.read_text())
            verification = json.loads(result.read_text())
            if (verification.get('status') != 'pass' or verification.get('results') != actual or
                    verification.get('run_id') != document['run_id'] or
                    verification.get('arch') != document['arch'] or
                    verification.get('scope') != 'five_real_factory_returned_types_only' or
                    verification.get('archive_sha256') != archive_sha or
                    verification.get('inputs_sha256') != digest(inputs) or
                    verification.get('results_sha256') != digest(raw) or
                    verification.get('application_identity_sha256') != digest(identity)):
                raise ValueError('factory closure differs from actual complete typed factory observations')
            for module, names in CONTRACTS.items():
                for name in names:
                    closed['arkts_export:' + module + ':' + name] = {
                        'evidence': str(factories[0]), 'sha256': digest(factories[0]),
                        'verifier': 'ordinary_typed_sync_promise_callback_snapshot_and_two_live_task_generations',
                        'resolution': 'factory_return_contract_verified_NOT_runtime_constructor',
                        'not_claimed': 'runtime_constructor_export_or_all_resource_and_TaskPool_APIs'}
    camera = child('camera/evidence.json')
    if camera:
        from verify_camera_results import verify_evidence as verify_camera_evidence
        verify_camera_evidence(camera[1], archive_sha, boot_id)
        closed['behavior:camera-host-backend-missing'] = {
            'evidence': str(camera[0]), 'sha256': digest(camera[0]),
            'verifier': 'ordinary_Camera_real_user_UI_NDK_ArkTS_two_previews_four_JPEGs_callbacks_recreation',
            'not_claimed': 'physical_camera_video_or_advanced_modes'}
    certificates = child('certificate-manager/evidence.json')
    if certificates:
        from verify_certificate_results import verify_evidence
        verify_evidence(certificates[1], archive_sha, boot_id)
        closed['behavior:certificate-manager-undefined-result'] = {
            'evidence': str(certificates[0]), 'sha256': digest(certificates[0]),
            'verifier': 'two_real_HAP_roles_empty_callback_own_import_query_cleanup_64_repeats_and_denial',
            'not_claimed': 'certificate_dialog_UI_ukey_or_all_certificate_API_behavior'}
    native = child('native-gap-abi/result.json')
    if native and native[1].get('kind') == 'native-gap-abi':
        document = native[1]
        definitions = Path(document.get('definitions', ''))
        raw = native[0].parent / 'stdout.jsonl'
        if (document.get('kernel_boot_id_unchanged') is True and definitions.is_file() and
                not definitions.is_symlink() and digest(definitions) == document.get('definitions_sha256') and
                raw.is_file() and not raw.is_symlink() and digest(raw) == document.get('log_sha256')):
            from verify_native_gap_abi_results import verify
            inputs = json.loads(definitions.read_text())
            if document.get('actual_guest_syscap_sha256') != inputs['actual_syscap_sha256']:
                raise ValueError('actual guest SysCaps differ from complete Native ABI definitions')
            actual = verify(raw.read_text(), inputs, document['arch'], document['device'],
                            document['run_id'], document['probe_exit_code'])
            if actual != document.get('result'):
                raise ValueError('Native ABI closure differs from actual complete system-loader observations')
            for identifier in actual['resolved_original_contracts']:
                optional = identifier in actual['optional_undeclared_not_implemented']
                closed[identifier] = {'evidence': str(native[0]), 'sha256': digest(native[0]),
                    'verifier': 'actual_all_fixed_source_public_DSO_symbols_and_exact_system_provider_ownership',
                    'resolution': 'optional_undeclared_NOT_implemented' if optional else 'complete_native_ABI',
                    'not_claimed': 'ordinary_app_namespace_API_call_or_provider_backend_behavior'}
            for identifier in optional_profile_resolutions(actual['optional_undeclared_not_implemented'], device_type):
                closed[identifier] = {'evidence': str(native[0]), 'sha256': digest(native[0]),
                    'verifier': 'actual_guest_SysCap_absent_and_outside_official_device_profile',
                    'resolution': 'false_declaration_removed_NOT_capability_implemented'}
            suite = child('audio-suite/result.json')
            if (suite and AUDIO_SUITE_NATIVE in actual['resolved_original_contracts'] and
                    AUDIO_SUITE_NATIVE not in actual['optional_undeclared_not_implemented'] and
                    suite[1].get('kind') == 'audio-suite' and
                    suite[1].get('kernel_boot_id_unchanged') is True):
                suite_document = suite[1]
                suite_raw = suite[0].parent / 'stdout.jsonl'
                suite_probe = Path(suite_document.get('probe', ''))
                if (suite_raw.is_file() and not suite_raw.is_symlink() and
                        digest(suite_raw) == suite_document.get('log_sha256') and
                        suite_probe.is_file() and not suite_probe.is_symlink() and
                        digest(suite_probe) == suite_document.get('probe_sha256')):
                    from verify_audio_suite_results import verify as verify_suite
                    suite_actual = verify_suite(suite_raw.read_text(), suite_document['probe_exit_code'])
                    if suite_actual != suite_document.get('result'):
                        raise ValueError('AudioSuite PCM closure differs from real guest observations')
                    closed['behavior:audio-suite-placeholder-library'] = {
                        'evidence': str(suite[0]), 'sha256': digest(suite[0]),
                        'native_abi_evidence': str(native[0]), 'native_abi_sha256': digest(native[0]),
                        'verifier': 'all_65_public_symbols_and_real_two_cycle_PCM_data_state_boundary',
                        'not_claimed': 'algorithm_plugins_or_realtime_audio_device'}
    return closed


def run(args):
    baseline = json.loads(LEDGER.read_text())
    expected = requirements(baseline['devices'][args.device])
    boot = json.loads(args.boot.read_text())
    environment = boot.get('test_environment', {})
    archive_sha = digest(args.archive)
    if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
            boot.get('archive_sha256') != archive_sha or environment.get('device_type') != args.device or
            environment.get('external_keepalive') is not False or not environment.get('boot_id')):
        raise ValueError('complete audit closure requires the actual new unassisted package boot')
    closed = behavior_results(args.runtime_root, environment['boot_id'], archive_sha, args.device)
    closed = {key: row for key, row in closed.items() if key in expected}
    unresolved = [{'id': key, 'requirement': row,
                   'reason': 'no complete registered new-package behavior/ABI/permission proof'}
                  for key, row in expected.items() if key not in closed]
    result = {'schema_version': 1, 'scope': 'complete_audited_Cxx_ArkTS11_gap_closure',
        'status': 'fail' if unresolved else 'pass', 'device': args.device,
        'archive': str(args.archive.resolve()), 'archive_sha256': archive_sha,
        'boot_id': environment['boot_id'], 'audit_baseline': str(LEDGER), 'audit_baseline_sha256': digest(LEDGER),
        'expected_count': len(expected), 'closed_count': len(closed), 'closed': closed,
        'unresolved': unresolved, 'excluded': ['ArkTS Static'],
        'first_artifact_behavior_gate_passed': False}
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({key: result[key] for key in ('status', 'expected_count', 'closed_count')}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
