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
from release_scope import SCOPE, exclusion_record

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


def reflection_closes_contract(module, requirement, value):
    """Presence is discovery, not a callable/class/provider behavior proof."""
    if value.get('read_status') != 0 or value.get('read_exception') is not False:
        return False
    if requirement['kind'] == 'enum':
        return (type(value.get('value_type')) is int and value['value_type'] == 6 and
                value.get('enum_contract_applicable') is True and value.get('enum_contract_valid') is True)
    if module == '@ohos.settings' and requirement['name'] == 'TTS' and requirement['kind'] == 'namespace':
        # This is the exact constant-key namespace plus identity with its
        # existing legacy alias, not a callable or settings provider claim.
        from verify_arkts_exports_results import settings_tts_verified
        return settings_tts_verified(module, value)
    return False


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

    completion = child('completion-handler/evidence.json')
    if completion:
        from verify_completion_handler_results import verify_evidence as verify_completion
        boot_path = runtime / 'boot/boot.json'
        if boot_path.is_symlink() or not boot_path.is_file():
            raise ValueError('constructor closure requires actual new-package boot evidence')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or
                environment.get('device_type') != device_type or
                any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_assistance', 'diagnostic_power_button'))):
            raise ValueError('constructor proof requires this unchanged acceptance package')
        verify_completion(completion[1], archive_sha, boot_id, environment['guest_arch'])
        closed['arkts_export:@ohos.app.ability.CompletionHandlerForAbilityStartCallback:'
               'CompletionHandlerForAbilityStartCallback'] = {
            'evidence': str(completion[0]), 'sha256': digest(completion[0]),
            'verifier': 'ordinary_typed_ArkTS_constructor_optional_callbacks_isolation_subclass_and_existing_enum',
            'not_claimed': 'component_start_callback_delivery_or_service_IPC'}

    metadata = child('image-metadata/evidence.json')
    if metadata:
        from verify_image_metadata_results import (
            verify_evidence as verify_metadata, AVIS_CONTRACT, RECORD_CONTRACTS)
        boot_path = runtime / 'boot/boot.json'
        if not boot_path.is_file() or boot_path.is_symlink():
            raise ValueError('image constructor closure requires actual acceptance boot')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or
                environment.get('device_type') != device_type or
                any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_assistance', 'diagnostic_power_button'))):
            raise ValueError('image constructor proof requires unchanged acceptance package')
        actual = verify_metadata(metadata[1], archive_sha, boot_id, environment['guest_arch'])
        if actual['closed'] != [AVIS_CONTRACT, *RECORD_CONTRACTS]:
            raise ValueError('image constructor proof must match all three actual typed contracts')
        for contract in actual['closed']:
            closed[contract] = {
                'evidence': str(metadata[0]), 'sha256': digest(metadata[0]),
                'verifier': 'ordinary_typed_constructor_isolation_and_real_DNG_TIFF_AVIS_factory_instances',
                'not_claimed': 'other_image_APIs'}

    thermal = child('thermal/evidence.json')
    if thermal:
        from verify_thermal_results import verify_evidence as verify_thermal
        boot_path = runtime / 'boot/boot.json'
        if boot_path.is_symlink() or not boot_path.is_file():
            raise ValueError('thermal closure requires actual new-package boot evidence')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or
                environment.get('device_type') != device_type or
                any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_assistance', 'diagnostic_power_button'))):
            raise ValueError('thermal proof requires this unchanged acceptance package')
        verify_thermal(thermal[1], archive_sha, boot_id, environment['guest_arch'])
        closed['behavior:thermal-backend-zero-data'] = {
            'evidence': str(thermal[0]), 'sha256': digest(thermal[0]),
            'verifier': 'actual_nonzero_kernel_service_readback_and_four_ordinary_thermal_callback_lifetimes',
            'not_claimed': 'hot_transitions_or_real_physical_temperature'}

    quota = child('project-quota/result.json')
    hitrace = child('hitrace/diagnostic.json')
    if hitrace:
        from verify_hitrace_evidence import verify_evidence as verify_hitrace
        boot_path = runtime / 'boot/boot.json'
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (hitrace[1].get('enclosing_boot') != str(boot_path.resolve()) or
                environment.get('device_type') != device_type):
            raise ValueError('HiTrace closure requires this exact suite-owned acceptance guest')
        actual = verify_hitrace(hitrace[1], archive_sha, boot_id, environment['guest_arch'])
        for identifier in actual['closed']:
            closed[identifier] = {'evidence': str(hitrace[0]), 'sha256': digest(hitrace[0]),
                'verifier': 'ordinary_public_Cxx_ArkTS_calls_matched_to_real_kernel_trace_and_restored_policy',
                'not_claimed': actual['not_claimed']}

    storage = child('storage-stats/evidence.json')
    graphics_memory = child('graphics-memory/diagnostic.json')
    if graphics_memory:
        from verify_graphics_memory_evidence import verify_evidence as verify_graphics_memory
        boot_path = runtime / 'boot/boot.json'
        environment = json.loads(boot_path.read_text()).get('test_environment', {})
        if (graphics_memory[1].get('enclosing_boot') != str(boot_path.resolve()) or
                environment.get('device_type') != device_type):
            raise ValueError('graphics memory closure requires this exact suite-owned acceptance guest')
        actual = verify_graphics_memory(graphics_memory[1], archive_sha, boot_id, environment['guest_arch'])
        for identifier in actual['closed']:
            closed[identifier] = {'evidence': str(graphics_memory[0]), 'sha256': digest(graphics_memory[0]),
                'verifier': 'ordinary_public_Cxx_ArkTS_allocations_matched_to_real_kernel_inodes_and_releases',
                'not_claimed': actual['not_claimed']}

    if quota and storage:
        from verify_storage_quota_closure import verify as verify_storage_quota
        closed.update(verify_storage_quota(runtime, archive_sha, boot_id, device_type))

    fa = child('fa-particle/evidence.json')
    stage = child('settings-navigation/evidence.json')
    if fa and stage:
        from verify_fa_particle_results import verify_evidence as verify_fa
        from verify_settings_navigation_results import verify_evidence as verify_stage
        boot_path = runtime / 'boot/boot.json'
        if not boot_path.is_file() or boot_path.is_symlink():
            raise ValueError('FA/Stage closure requires original new-package boot evidence')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or
                environment.get('device_type') != device_type):
            raise ValueError('FA and Stage must run on the same fresh acceptance package')
        arch = environment['guest_arch']
        verify_fa(fa[1], archive_sha, boot_id, arch)
        verify_stage(stage[1], archive_sha, boot_id, arch)
        closed['arkts_export:@ohos.ability.particleAbility:ErrorCode'] = {
            'evidence': str(fa[0]), 'sha256': digest(fa[0]),
            'stage_evidence': str(stage[0]), 'stage_sha256': digest(stage[0]),
            'verifier': 'real_FA_service_constant_existing_calls_AND_same_package_ordinary_Stage_navigation',
            'not_claimed': 'all_FA_lifecycle_or_all_Stage_API_behavior'}

    backup = child('backup-init/evidence.json')
    if backup and backup[1].get('persona') == 'backup-init':
        document = backup[1]
        serial = backup[0].parent / 'serial.log'
        if (document.get('scope') == 'actual_init_accepts_and_execs_backup_sa_NOT_Backup_API_data_behavior' and
                document.get('serial') == str(serial) and serial.is_file() and not serial.is_symlink() and
                digest(serial) == document.get('serial_sha256')):
            from verify_backup_init_results import verify
            if verify(serial.read_text(errors='replace')) != document.get('result'):
                raise ValueError('backup SA init/exec differs from captured serial trace')
            closed['behavior:backup-init-invalid-linux-capability'] = {
                'evidence': str(backup[0]), 'sha256': digest(backup[0]),
                'serial': str(serial), 'serial_sha256': digest(serial),
                'verifier': 'actual_new_package_init_start_and_exec_same_backup_SA_pid',
                'not_claimed': 'Backup_API_data_transfer_restore_or_authorization'}

    profile = child('boot-profile/evidence.json')
    if profile and profile[1].get('persona') == 'boot-profile':
        document = profile[1]
        boot_path = runtime / 'boot/boot.json'
        boot = json.loads(boot_path.read_text()) if boot_path.is_file() and not boot_path.is_symlink() else {}
        image = Path(document.get('system_image', ''))
        image_root = runtime / 'boot/extract'
        files = {name: profile[0].parent / name for name in
                 ('serial.log', 'module-stat.txt', 'usage-system-stat.txt', 'usage-root-stat.txt')}
        if (document.get('scope') == 'module_update_initializer_and_unused_usage_init_only' and
                boot.get('status') == 'pass' and boot.get('purpose') == 'acceptance' and
                boot.get('archive_sha256') == archive_sha and
                boot.get('test_environment', {}).get('boot_id') == boot_id and
                boot.get('test_environment', {}).get('external_keepalive') is False and
                image.is_file() and not image.is_symlink() and image.parent.name == 'images' and
                image.name == 'system.img' and image_root in image.parents and
                boot.get('test_environment', {}).get('freshly_extracted_directory') == str(image.parent.parent) and
                digest(image) == document.get('system_image_sha256') ==
                boot.get('initial_package_file_sha256', {}).get('images/system.img') and
                all(path.is_file() and not path.is_symlink() for path in files.values()) and
                digest(files['serial.log']) == document.get('serial_sha256') and
                all(digest(files[name]) == document.get('stat_sha256', {}).get(name)
                    for name in files if name != 'serial.log')):
            from verify_boot_profile_results import verify
            actual = verify(files['module-stat.txt'].read_text(),
                            [files['usage-system-stat.txt'].read_text(),
                             files['usage-root-stat.txt'].read_text()],
                            files['serial.log'].read_text(errors='replace'))
            if actual != document.get('result'):
                raise ValueError('boot profile repair differs from actual image and init trace')
            proof = {'evidence': str(profile[0]), 'sha256': digest(profile[0]),
                     'verifier': 'actual_system_image_debugfs_and_fresh_boot_init_SA_events',
                     'not_claimed': 'full_module_update_or_usage_statistics_API_behavior'}
            closed['behavior:module-update-initializer-missing'] = proof
            closed['behavior:usage-statistics-stale-init-profile'] = proof

    huks = child('huks-compatibility/evidence.json')
    if huks and huks[1].get('persona') == 'huks-compatibility':
        from verify_huks_compatibility_results import verify_evidence
        boot_path = runtime / 'boot/boot.json'
        if not boot_path.is_file() or boot_path.is_symlink():
            raise ValueError('HUKS closure requires original acceptance boot evidence')
        verify_evidence(huks[1], huks[0].parent, json.loads(boot_path.read_text()), archive_sha, boot_id)
        closed['behavior:huks-compatibility-helper-missing'] = {
            'evidence': str(huks[0]), 'sha256': digest(huks[0]),
            'verifier': 'actual_package_helper_init_and_owned_legacy_UID_mode_migration',
            'not_claimed': 'legacy_encrypted_key_conversion_TEE_or_OEM_attestation'}

    for persona in ('curve', 'binding'):
        proof = child(persona + '/evidence.json')
        if proof and proof[1].get('persona') == persona:
            if persona == 'curve':
                from verify_curve_results import verify_evidence
            else:
                from verify_binding_results import verify_evidence
            result = verify_evidence(proof[1], proof[0].parent, archive_sha, boot_id)
            for identifier in result['closed']:
                closed[identifier] = {'evidence': str(proof[0]), 'sha256': digest(proof[0]),
                    'verifier': 'actual_typed_public_factories_and_original_input_replay',
                    'resolution': 'factory_member_contract_NOT_injected_constructor',
                    'not_claimed': result['not_claimed']}

    discovery = child('optional-phone-profile/evidence.json')
    if device_type == 'phone' and discovery and discovery[1].get('persona') == 'optional-phone-profile':
        from verify_optional_phone_profile_results import verify_evidence
        boot_path = runtime / 'boot/boot.json'
        if not boot_path.is_file() or boot_path.is_symlink():
            raise ValueError('phone discovery requires the original acceptance boot evidence')
        result = verify_evidence(discovery[1], discovery[0].parent,
            json.loads(boot_path.read_text()), archive_sha, boot_id)
        for identifier in result['closed']:
            closed[identifier] = {'evidence': str(discovery[0]), 'sha256': digest(discovery[0]),
                'verifier': 'actual_immutable_phone_image_AND_ordinary_dynamic_discovery',
                'resolution': 'outside_official_phone_false_declaration_removed',
                'not_claimed': result['not_claimed']}

    service_init = child('service-init-contracts/evidence.json')
    if service_init and service_init[1].get('persona') == 'service-init-contracts':
        from verify_service_init_contracts import verify_evidence
        boot_path = runtime / 'boot/boot.json'
        if not boot_path.is_file() or boot_path.is_symlink():
            raise ValueError('service init closure requires the original acceptance boot evidence')
        verify_evidence(service_init[1], service_init[0].parent, json.loads(boot_path.read_text()),
                        archive_sha, boot_id)
        proof = {'evidence': str(service_init[0]), 'sha256': digest(service_init[0]),
                 'verifier': 'actual_package_accounts_configs_directory_stat_and_same_boot_init_exec',
                 'not_claimed': 'Fusion_hardware_peer_ranging_or_OEM_customization_updates'}
        closed['behavior:fusion-connectivity-init-accounts'] = proof
        i18n = child('i18n/evidence.json')
        if i18n and i18n[1].get('persona') == 'i18n':
            from verify_i18n_data import verify as verify_i18n
            from run_normal_hap_probe import require_normal_identity
            document = i18n[1]
            raw, identity = i18n[0].parent / 'results.log', i18n[0].parent / 'application-identity.json'
            result = Path(document.get('result', ''))
            if all(path.is_file() and not path.is_symlink() and digest(path) == document.get(key)
                   for path, key in ((raw, 'raw_results_sha256'), (identity, 'ordinary_identity_sha256'),
                                     (result, 'result_sha256'))):
                require_normal_identity(identity.read_text())
                actual = verify_i18n(raw.read_text(), document['run_id'])
                verification = json.loads(result.read_text())
                if (verification.get('status') != 'pass' or verification.get('results') != actual or
                        verification.get('archive_sha256') != archive_sha or
                        verification.get('run_id') != document['run_id'] or
                        verification.get('results_sha256') != digest(raw)):
                    raise ValueError('I18n closure differs from actual fresh ordinary data/permission results')
                closed['behavior:i18n-core-and-customization-paths'] = dict(proof,
                    ordinary_data_evidence=str(i18n[0]), ordinary_data_sha256=digest(i18n[0]),
                    verifier='actual_init_paths_plus_ordinary_timezone_phone_locale_and_error_boundaries')

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
            if document['device'] == 'phone':
                boot_path = runtime / 'boot/boot.json'
                boot = json.loads(boot_path.read_text()) if boot_path.is_file() and not boot_path.is_symlink() else {}
                package_dir = Path(boot.get('test_environment', {}).get('freshly_extracted_directory', ''))
                metadata_path = package_dir / 'sensor-health-permission.json'
                if (boot.get('status') == 'pass' and boot.get('purpose') == 'acceptance' and
                        boot.get('archive_sha256') == archive_sha and
                        boot.get('test_environment', {}).get('boot_id') == boot_id and
                        package_dir.parent == runtime / 'boot/extract' and
                        not package_dir.is_symlink() and metadata_path.is_file() and
                        not metadata_path.is_symlink() and
                        digest(metadata_path) == boot.get('initial_package_file_sha256', {}).get(
                            'sensor-health-permission.json')):
                    from verify_sensor_health_resolution import verify as verify_sensor
                    patch = ROOT / ('patches/common/interface/sdk-js/sensor_health_permission/'
                                    '0001-document-the-registered-heart-rate-permission.patch')
                    legacy = verify_sensor(json.loads(metadata_path.read_text()),
                                           json.loads(definitions.read_text()), raw.read_text(), digest(patch))
                    for name in legacy:
                        closed['permission:' + name] = {
                            'evidence': str(permissions[0]), 'sha256': digest(permissions[0]),
                            'source_contract_evidence': str(metadata_path),
                            'source_contract_sha256': digest(metadata_path),
                            'resolution': 'incorrect_legacy_SDK_permission_annotation_corrected',
                            'verifier': 'registered_checked_READ_HEALTH_DATA_user_grant_and_exact_three_SDK_overloads',
                            'not_claimed': 'new_legacy_permission_grant_or_physical_heart_rate_sensor'}
            # The aggregate finding describes absent definitions, not grants.
            for profile_device, baseline in json.loads(LEDGER.read_text())['devices'].items():
                names = ['permission:' + row['permission'] for row in baseline['permission_registry_gaps']]
                if document['device'] == profile_device and names and all(name in closed for name in names):
                    closed['behavior:api26-permission-registry-gaps-' + profile_device] = {
                        'evidence': str(permissions[0]), 'sha256': digest(permissions[0]),
                        'verifier': 'all_original_permission_findings_resolved_by_registry_or_corrected_SDK_metadata',
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
    observer_info = child('observer-info/evidence.json')
    if observer_info:
        from verify_observer_info_results import verify_evidence as verify_info
        boot_path = runtime / 'boot/boot.json'
        if boot_path.is_symlink() or not boot_path.is_file():
            raise ValueError('observer info closure requires actual acceptance boot')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or environment.get('device_type') != device_type or
                any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_assistance', 'diagnostic_power_button'))):
            raise ValueError('observer info proof requires unchanged acceptance package')
        actual = verify_info(observer_info[1], archive_sha, boot_id, environment['guest_arch'])
        for contract in actual['closed']:
            closed[contract] = {'evidence': str(observer_info[0]), 'sha256': digest(observer_info[0]),
                'verifier': 'ordinary_real_density_context_and_breakpoint_constructor_instances_two_unsubscription_modes',
                'not_claimed': 'all_observer_ArkUI_APIs_or_other_windows'}
    spring = child('spring-loading/evidence.json')
    if spring:
        from verify_spring_loading_results import verify_evidence as verify_spring
        boot_path = runtime / 'boot/boot.json'
        if boot_path.is_symlink() or not boot_path.is_file():
            raise ValueError('spring closure requires actual acceptance boot')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or environment.get('device_type') != device_type or
                any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_assistance', 'diagnostic_power_button'))):
            raise ValueError('spring proof requires unchanged acceptance package')
        actual = verify_spring(spring[1], archive_sha, boot_id, environment['guest_arch'],
                               device_type, environment.get('target'))
        for contract in actual['closed']:
            closed[contract] = {'evidence': str(spring[0]), 'sha256': digest(spring[0]),
                'verifier': 'ordinary_real_class_and_four_QMP_hover_cycles_config_abort_cancel_and_reentry',
                'not_claimed': 'full_drag_MSDP_or_cross_app_UDMF_backend'}
    components = child('arkui-components/evidence.json')
    if components:
        from verify_arkui_components_results import verify_evidence as verify_components
        boot_path = runtime / 'boot/boot.json'
        if boot_path.is_symlink() or not boot_path.is_file():
            raise ValueError('component closure requires actual acceptance boot')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or environment.get('device_type') != device_type or
                any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_assistance', 'diagnostic_power_button'))):
            raise ValueError('component proof requires unchanged actual acceptance package')
        actual = verify_components(components[1], archive_sha, boot_id, environment['guest_arch'],
                                   device_type, environment.get('target'))
        for contract in actual['closed']:
            closed[contract] = {'evidence': str(components[0]), 'sha256': digest(components[0]),
                'verifier': 'ordinary_typed_native_Arc_factories_scroll_and_painted_dynamic_layout_preserved_frames',
                'resolution': actual['resolution'],
                'not_claimed': actual['not_claimed']}
    routed = child('router-observer/evidence.json')
    if routed:
        from verify_router_observer_results import verify_evidence as verify_routed
        boot_path = runtime / 'boot/boot.json'
        if boot_path.is_symlink() or not boot_path.is_file():
            raise ValueError('router callback closure requires actual acceptance boot')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or environment.get('device_type') != device_type or
                any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_assistance', 'diagnostic_power_button'))):
            raise ValueError('router callback proof requires unchanged acceptance package')
        verify_routed(routed[1], archive_sha, boot_id, environment['guest_arch'])
        closed['arkts_export:@ohos.arkui.observer:RouterPageInfo'] = {
            'evidence': str(routed[0]), 'sha256': digest(routed[0]),
            'verifier': 'ordinary_typed_four_real_routed_pages_two_listeners_and_two_unsubscription_modes',
            'resolution': 'callback_return_contract_verified_NOT_runtime_constructor',
            'not_claimed': 'constructor_export_density_breakpoints_or_all_observer_APIs'}
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
            for name in actual['record_classes']:
                closed['arkts_export:@ohos.contact:' + name] = {
                    'evidence': str(modes[0]), 'sha256': digest(modes[0]),
                    'verifier': 'ordinary_typed_constructor_instanceof_independent_properties_and_Holder_default',
                    'not_claimed': 'contacts_database_sync_picker_provider_or_permission_behavior'}
            for name in actual['state_record_classes']:
                closed['arkts_export:@ohos.arkui.StateManagement:' + name] = {
                    'evidence': str(modes[0]), 'sha256': digest(modes[0]),
                    'verifier': 'typed_constructor_inheritance_unset_fields_and_independent_creators',
                    'not_claimed': 'persistent_storage_backend_lifecycle_encryption_or_permissions'}
            for name in actual['photo_record_classes']:
                closed['arkts_export:@ohos.file.photoAccessHelper:' + name] = {
                    'evidence': str(modes[0]), 'sha256': digest(modes[0]),
                    'verifier': 'typed_constructor_instanceof_unset_fields_and_isolated_data_records',
                    'not_claimed': 'photo_assets_provider_permissions_factory_instances_or_album_ordering'}
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
                    value = properties.get(requirement['name'], {})
                    if reflection_closes_contract(module['module'], requirement, value):
                        # Never replace a previously verified constructor or
                        # behavior result with weaker reflection evidence.
                        closed.setdefault('arkts_export:' + module['module'] + ':' + requirement['name'], proof)
    enum_members = child('runtime-enum/evidence.json')
    if enum_members and enum_members[1].get('persona') == 'runtime-enum':
        document = enum_members[1]
        raw = enum_members[0].parent / 'results.log'
        identity = enum_members[0].parent / 'application-identity.json'
        inputs = Path(document.get('compiled_contract_inputs', ''))
        result = Path(document.get('result', ''))
        if all(path.is_file() and not path.is_symlink() and digest(path) == document.get(key)
               for path, key in ((raw, 'raw_results_sha256'), (identity, 'ordinary_identity_sha256'),
                                 (inputs, 'compiled_contract_inputs_sha256'), (result, 'result_sha256'))):
            from runtime_enum_contracts import SCOPE, verify_inputs
            from verify_runtime_enum_results import verify
            frozen = json.loads(inputs.read_text())
            if frozen.get('device') != device_type:
                raise ValueError('enum caller does not match actual package profile')
            contracts = verify_inputs(frozen, document['run_id'], document['arch'])
            actual = verify(raw.read_text(), contracts, document['run_id'], identity.read_text())
            verification = json.loads(result.read_text())
            if (verification.get('status') != 'pass' or verification.get('results') != actual or
                    verification.get('run_id') != document['run_id'] or
                    verification.get('arch') != document['arch'] or verification.get('scope') != SCOPE or
                    verification.get('archive_sha256') != archive_sha or
                    verification.get('inputs_sha256') != digest(inputs) or
                    verification.get('results_sha256') != digest(raw) or
                    verification.get('application_identity_sha256') != digest(identity)):
                raise ValueError('enum closure differs from actual complete typed/native member observations')
            for row in actual['closed']:
                closed[row['contract']] = {'evidence': str(enum_members[0]), 'sha256': digest(enum_members[0]),
                    'verifier': 'ordinary_API26_all_original_regular_enum_members_typed_plus_independent_NAPI',
                    'member_count': row['member_count'], 'not_claimed': actual['not_claimed']}
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
    web_factories = child('web-factory/evidence.json')
    if web_factories and web_factories[1].get('persona') == 'web-factory':
        document = web_factories[1]
        raw = web_factories[0].parent / 'results.log'
        identity = web_factories[0].parent / 'application-identity.json'
        inputs = Path(document.get('compiled_contract_inputs', ''))
        result = Path(document.get('result', ''))
        if all(path.is_file() and not path.is_symlink() and digest(path) == document.get(key)
               for path, key in ((raw, 'raw_results_sha256'), (identity, 'ordinary_identity_sha256'),
                                 (inputs, 'compiled_contract_inputs_sha256'), (result, 'result_sha256'))):
            from verify_web_factory_results import CONTRACTS, SCOPE, verify_inputs, verify
            verify_inputs(json.loads(inputs.read_text()), document['run_id'], document['arch'])
            actual = verify(raw.read_text(), document['run_id'], identity.read_text())
            verification = json.loads(result.read_text())
            if (verification.get('status') != 'pass' or verification.get('results') != actual or
                    verification.get('run_id') != document['run_id'] or
                    verification.get('arch') != document['arch'] or verification.get('scope') != SCOPE or
                    verification.get('archive_sha256') != archive_sha or
                    verification.get('inputs_sha256') != digest(inputs) or
                    verification.get('results_sha256') != digest(raw) or
                    verification.get('application_identity_sha256') != digest(identity)):
                raise ValueError('ArkWeb factory closure differs from actual stream/renderer/callback observations')
            for name in CONTRACTS:
                closed['arkts_export:@ohos.web.webview:' + name] = {
                    'evidence': str(web_factories[0]), 'sha256': digest(web_factories[0]),
                    'verifier': 'ordinary_API26_custom_scheme_POST_stream_response_roundtrip_two_media_callbacks',
                    'resolution': 'factory_callback_contract_verified_NOT_runtime_constructor',
                    'not_claimed': 'native_media_decoding_playback_visible_surface_or_all_ArkWeb_API_behavior'}
    camera = child('camera/evidence.json')
    if camera:
        from verify_camera_results import verify_evidence as verify_camera_evidence
        verify_camera_evidence(camera[1], archive_sha, boot_id)
        closed['arkts_export:@ohos.multimedia.camera:EffectSuggestionStatus'] = {
            'evidence': str(camera[0]), 'sha256': digest(camera[0]),
            'verifier': 'typed_constructor_instanceof_unset_fields_and_independent_records',
            'not_claimed': 'effect_suggestion_algorithm_or_system_session_setter'}
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
    vpn = child('vpn-policy/evidence.json')
    if vpn:
        from verify_always_on_vpn_results import verify_evidence as verify_vpn
        boot_path = runtime / 'boot/boot.json'
        if not boot_path.is_file() or boot_path.is_symlink():
            raise ValueError('VPN closure requires actual acceptance boot')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or environment.get('device_type') != device_type or
                any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_assistance', 'diagnostic_power_button'))):
            raise ValueError('VPN policy proof requires unchanged acceptance package')
        for contract in verify_vpn(vpn[1], archive_sha, boot_id, environment['guest_arch'], device_type):
            closed[contract] = {'evidence': str(vpn[0]), 'sha256': digest(vpn[0]),
                'verifier': 'three_real_HAP_roles_policy_persistence_restart_readback_cleanup_and_numeric_denials',
                'not_claimed': 'VPN_tunnel_server_traffic_or_all_VPN_configuration_APIs'}
    vpn_store = child('sys-vpn-store/evidence.json')
    if vpn_store:
        from verify_sys_vpn_store_results import verify_evidence as verify_vpn_store
        boot_path = runtime / 'boot/boot.json'
        if not boot_path.is_file() or boot_path.is_symlink():
            raise ValueError('system VPN CRUD closure requires actual acceptance boot')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or environment.get('device_type') != device_type or
                any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_assistance', 'diagnostic_power_button'))):
            raise ValueError('system VPN store proof requires unchanged acceptance package')
        for contract in verify_vpn_store(vpn_store[1], archive_sha, boot_id, environment['guest_arch'],
                                         device_type, environment['target']):
            closed[contract] = {'evidence': str(vpn_store[0]), 'sha256': digest(vpn_store[0]),
                'verifier': 'three_real_HAP_roles_three_variants_complete_network_CRUD_replace_caller_restart_and_denials',
                'not_claimed': 'connected_tunnel_traffic_PKCS12_legacy_DB_migration_or_all_VPN_options'}
    luminance = child('luminance-sampler/evidence.json')
    if luminance:
        from verify_luminance_results import verify_evidence as verify_luminance
        boot_path = runtime / 'boot/boot.json'
        if not boot_path.is_file() or boot_path.is_symlink():
            raise ValueError('luminance closure requires actual acceptance boot')
        boot = json.loads(boot_path.read_text())
        environment = boot.get('test_environment', {})
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                boot.get('archive_sha256') != archive_sha or environment.get('boot_id') != boot_id or
                environment.get('external_keepalive') is not False or environment.get('device_type') != device_type or
                any(boot.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_assistance', 'diagnostic_power_button'))):
            raise ValueError('luminance proof requires unchanged acceptance package')
        for contract in verify_luminance(luminance[1], archive_sha, boot_id, environment['guest_arch'], device_type):
            closed[contract] = {'evidence': str(luminance[0]), 'sha256': digest(luminance[0]),
                'verifier': 'SDK_documented_UIContext_factory_real_RS_dark_light_cycles_and_unsubscription',
                'not_claimed': 'public_constructor_or_other_ArkUI_classes_or_all_luminance_options'}
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
    original_count = len(expected)
    exclusions = exclusion_record(args.device, expected)
    expected = {key: row for key, row in expected.items() if key not in exclusions['ids']}
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
    result = {'schema_version': 2, 'scope': SCOPE,
        'status': 'fail' if unresolved else 'pass', 'device': args.device,
        'archive': str(args.archive.resolve()), 'archive_sha256': archive_sha,
        'boot_id': environment['boot_id'], 'audit_baseline': str(LEDGER), 'audit_baseline_sha256': digest(LEDGER),
        'expected_count': len(expected), 'closed_count': len(closed), 'closed': closed,
        'unresolved': unresolved, 'excluded': ['ArkTS Static', 'CloudSync', 'imageGeneration'],
        'original_expected_count': original_count, 'release_exclusions': exclusions,
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
