"""Explicit same-image/test-only updates; production input equality is mandatory."""
import hashlib
import json
from pathlib import Path
import re

# These files only build/run/verify test callers. No image builders, product
# patches, audit expectations or launchers may be substituted by this mechanism.
TEST_ONLY = frozenset('ci/capability-audit/' + name for name in (
    'boot_package.py', 'validation_input_binding.py', 'test_validation_input_binding.py',
    'build_luminance_probe.py', 'build_screen_blink_probe.py', 'luminance_sampler_probe.ets',
    'run_luminance_probe.py', 'run_packaged_qemu_suite.py', 'run_packaged_screen_blink_probe.py',
    'run_screen_blink_probe.py', 'run_wifi_scan_diagnostic.py', 'screen_blink_probe.ets',
    'screen_blink_runtime.py', 'sign_luminance_probe.py', 'test_luminance_results.py',
    'test_packaged_screen_blink.py', 'test_router_observer.py', 'test_screen_blink_results.py',
    'test_screen_blink_runtime.py', 'test_wifi_scan_diagnostic.py', 'verify_gap_closure.py',
    'verify_luminance_results.py', 'verify_router_observer_results.py', 'verify_screen_blink_results.py'))

# Reviewed dedicated callers/observers and their exact shared signing helper.
# Explicit receipt binding remains mandatory for every changed input.
DEDICATED_QA_TEST_ONLY = frozenset((
    'ci/capability-audit/batch_apps_contact_picker_coordinator.py',
    'ci/capability-audit/batch_media_wallpaper_suite.py',
    'ci/capability-audit/batch_media_wallpaper_coordinator.py',
    'ci/capability-audit/batch_media_verify_wallpaper_runtime.py',
    'ci/capability-audit/batch_media_knowledge_suite.py',
    'ci/capability-audit/batch_media_knowledge_runtime.py',
    'ci/capability-audit/batch_system_live_inputs_suite.py',
    'ci/capability-audit/fixtures/batch_media/wallpaper_runtime/oracle_fixture.py',
    'ci/capability-audit/test_batch_media_wallpaper_coordinator.py',
    'ci/capability-audit/test_batch_hap_signed_payload.py',
    'ci/capability-audit/batch_media_audio_haptic_build_callers.py',
    'ci/capability-audit/batch_media_audio_haptic_project.py',
    'ci/capability-audit/batch_media_audio_haptic_reviewfix_checks.py',
    'ci/capability-audit/batch_media_audio_haptic_runtime.py',
    'ci/capability-audit/batch_media_audio_haptic_verify.py',
    'ci/capability-audit/batch_system_calendar_runtime_binding.py',
    'ci/capability-audit/batch_system_calendar_runtime_build.py',
    'ci/capability-audit/batch_system_calendar_runtime_capture.py',
    'ci/capability-audit/batch_system_calendar_runtime_project.py',
    'ci/capability-audit/batch_system_calendar_runtime_protocol.py',
    'ci/capability-audit/batch_system_calendar_runtime_tests.py',
    'ci/capability-audit/batch_system_calendar_runtime_verify.py',
    'ci/capability-audit/fixtures/batch_media/audio_haptic_runtime/Index.ets',
    'ci/capability-audit/fixtures/batch_system/calendar_runtime/CalendarAudit.ets',
    'ci/capability-audit/fixtures/batch_system/calendar_runtime/host.cjs',
))
TEST_ONLY = TEST_ONLY | DEDICATED_QA_TEST_ONLY


# Exact F09 runtime diagnostic repairs. These tools may compile private QA
# callers against immutable product inputs; they cannot change packaged images,
# native recipes, production patches, audit ledgers, or the full gate policy.
F09_RUNTIME_QA_TEST_ONLY = frozenset((
    'ci/capability-audit/test_focus_cleanup_binding.py',
    'ci/capability-audit/test_batch_apps_contact_picker_coordinator.py',
    'ci/capability-audit/test_microphone_failure_preservation.py',
    'ci/capability-audit/audio_capture_runtime.py',
    'ci/capability-audit/audio_focus_runtime.py',
    'ci/capability-audit/batch_apps_contact_picker_coordinator.py',
    'ci/capability-audit/batch_apps_production_provider_binding.py',
    'ci/capability-audit/batch_media_audio_haptic_build_sampler.py',
    'ci/capability-audit/batch_media_audio_haptic_runtime.py',
    'ci/capability-audit/batch_media_audio_haptic_verify.py',
    'ci/capability-audit/batch_media_knowledge_artifacts.py',
    'ci/capability-audit/batch_media_knowledge_suite.py',
    'ci/capability-audit/batch_media_wallpaper_artifacts.py',
    'ci/capability-audit/batch_media_wallpaper_coordinator.py',
    'ci/capability-audit/batch_media_wallpaper_native.py',
    'ci/capability-audit/batch_media_wallpaper_suite.py',
    'ci/capability-audit/batch_network_openvpn_runtime_collect.py',
    'ci/capability-audit/batch_network_openvpn_runtime_test.py',
    'ci/capability-audit/batch_system_build_runtime_helpers.py',
    'ci/capability-audit/batch_system_calendar_runtime_archive.py',
    'ci/capability-audit/batch_system_calendar_runtime_capture.py',
    'ci/capability-audit/batch_system_calendar_runtime_helper.py',
    'ci/capability-audit/batch_system_calendar_runtime_verify.py',
    'ci/capability-audit/batch_system_gnss_trace_helper.py',
    'ci/capability-audit/batch_system_live_inputs.py',
    'ci/capability-audit/batch_system_live_inputs_suite.py',
    'ci/capability-audit/batch_system_run_live_inputs.py',
    'ci/capability-audit/batch_system_verify_live_inputs.py',
    'ci/capability-audit/build_audio_capture_tools.py',
    'ci/capability-audit/probes/audio_capture_token.cpp',
    'ci/capability-audit/run_audio_focus_probe.py',
    'ci/capability-audit/run_graphics_memory_diagnostic.py',
    'ci/capability-audit/run_hitrace_diagnostic.py',
    'ci/capability-audit/run_normal_hap_probe.py',
    'ci/capability-audit/run_root_probe.py',
    'ci/capability-audit/run_selection_contract_probe.py',
    'ci/capability-audit/test_audio_capture_token_diagnostics.py',
    'ci/capability-audit/test_audio_cleanup_boot.py',
    'ci/capability-audit/test_batch_media_wallpaper_native.py',
    'ci/capability-audit/test_batch_media_wallpaper_suite.py',
    'ci/capability-audit/test_batch_production_provider_binding.py',
    'ci/capability-audit/test_batch_runtime_process_snapshots.py',
    'ci/capability-audit/test_batch_system_build_runtime_helpers.py',
    'ci/capability-audit/test_batch_system_live_inputs_payload.py',
    'ci/capability-audit/test_batch_system_live_inputs_suite.py',
    'ci/capability-audit/test_family_installed_runtime_bindings.py',
    'ci/capability-audit/test_microphone_application_cleanup.py',
    'ci/capability-audit/test_microphone_runtime_binding.py',
    'ci/capability-audit/test_runtime_archive_roots.py',
    'ci/capability-audit/test_runtime_installed_profile.py',
    'ci/capability-audit/test_selection_executor_binding.py',
    'ci/capability-audit/test_validation_input_binding.py',
    'ci/capability-audit/validation_input_binding.py',
    'ci/capability-audit/verify_audio_capture_results.py',
    'ci/capability-audit/verify_audio_focus_results.py',
    'ci/capability-audit/verify_selection_evidence.py',
))
TEST_ONLY = TEST_ONLY | F09_RUNTIME_QA_TEST_ONLY


def tree_digest(files):
    if not isinstance(files, dict) or not files or any(
            not isinstance(name, str) or not isinstance(value, str) or
            re.fullmatch('[a-f0-9]{64}', value) is None for name, value in files.items()):
        raise ValueError('invalid frozen file identity')
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def verify_update(inputs, current, archive_sha256, path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular explicit validation update receipt required')
    raw = path.read_bytes()
    receipt = json.loads(raw)
    original = inputs.get('files_sha256')
    original_tree, current_tree = tree_digest(original), tree_digest(current)
    changed = sorted(name for name in original.keys() | current.keys()
                     if original.get(name) != current.get(name))
    if (inputs.get('tree_sha256') != original_tree or
            set(receipt) != {'schema_version', 'archive_sha256', 'build_tree_sha256',
                             'validation_tree_sha256', 'changed_test_files'} or
            type(receipt['schema_version']) is not int or receipt['schema_version'] != 1 or
            receipt['archive_sha256'] != archive_sha256 or
            receipt['build_tree_sha256'] != original_tree or
            receipt['validation_tree_sha256'] != current_tree or
            receipt['changed_test_files'] != changed or not changed or
            not set(changed).issubset(TEST_ONLY) or not original.keys() <= current.keys()):
        raise ValueError('validation-only update does not match exact archive/build/test identities')
    return dict(scope='explicit_test_only_update_NO_image_or_production_input_change',
                receipt=str(path.resolve()), receipt_sha256=hashlib.sha256(raw).hexdigest(),
                build_tree_sha256=original_tree, validation_tree_sha256=current_tree,
                changed_test_files=changed)
