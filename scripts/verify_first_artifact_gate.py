#!/usr/bin/env python3
"""Require archive-bound real behavior evidence for the gate and each delivery.

Static archive verification and tests against an older image are insufficient.
This validates the evidence contract; it does not itself boot or test QEMU.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import tarfile

from snapshot_build_inputs import digest_files
from power_test_policy import verify_policy_states

REQUIRED_CHECKS = frozenset(("boot", "arkweb", "vulkan", "issue20-library-exit",
                             "native-bindings-e2e", "cxx-arkts11-gaps", "power-suspend", "certificate-manager", "rs-objects", "avc-media",
                             "application-home", "photos-asset", "photo-result-set", "settings-navigation", "settings-all-navigation", "fa-particle", "screen-modes", "storage-stats", "project-quota", "completion-handler", "rpc-runtime", "thermal", "network-accounting", "hitrace", "graphics-memory", "image-metadata", "observer-info", "spring-loading", "arkui-components", "sys-vpn-store", "screen-blink", "luminance-sampler", "ethernet-control", "insight-contract", "lazy-column", "lazy-layouts", "selection", "env-reader"))
DEVICE_CHECKS = {"phone": frozenset(), "2in1": frozenset(("serial",))}
REQUIRED_CHECKS |= frozenset(('child-default-profile',))
REQUIRED_CHECKS |= frozenset(('audio-capture', 'media-recorder', 'audio-revoke', 'audio-focus'))
REPRESENTATIVE_CHECKS = frozenset(('contacts-picker', 'wallpaper', 'external-inputs'))


def verified_payload(name, path, identity, environment):
    """Do not accept a text log plus an invented outer 'pass' field."""
    payload = json.loads(path.read_text())
    if payload.get('status') != 'pass':
        raise ValueError('inner behavior evidence did not pass: ' + name)
    if name == 'boot':
        actual_environment = payload.get('test_environment', {})
        if (payload.get('scope') != 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate' or
                payload.get('purpose') != 'acceptance' or
                any(payload.get(key) for key in ('candidate_kernel', 'kernel_command_line_diagnostic',
                    'diagnostic_power_button', 'diagnostic_assistance')) or
                actual_environment.get('external_keepalive') is not False or
                payload.get('kernel_boot_id_unchanged') is not True or
                actual_environment.get('boot_id') != environment['boot_id'] or
                payload.get('archive_sha256') != identity['sha256'] or
                payload.get('build_inputs_tree_sha256') != identity['build_inputs_tree_sha256'] or
                type(payload.get('stable_seconds_without_external_keepalive')) is not int or
                payload['stable_seconds_without_external_keepalive'] < 60):
            raise ValueError('boot is diagnostic, assisted, too short, or from another archive')
        if payload.get('power_cycle'):
            cycle = payload['power_cycle']
            serial = Path(cycle.get('serial_evidence', ''))
            if (cycle.get('scope') != 'one_real_power_key_after_observed_s2idle' or
                    type(cycle.get('count')) is not int or cycle['count'] != 1 or
                    cycle.get('execute') != 'system_powerdown' or serial.is_symlink() or not serial.is_file() or
                    checksum(serial) != cycle.get('serial_sha256')):
                raise ValueError('packaged sleep/wake evidence is missing, changed or not a finite real key')
            log = serial.read_text(errors='replace')
            entry, exit_ = log.rfind('PM: suspend entry (s2idle)'), log.rfind('PM: suspend exit')
            if entry < 0 or exit_ <= entry:
                raise ValueError('packaged kernel did not complete the actual observed suspend/resume')
    elif name == 'application-home':
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
        from run_application_home_probe import SCOPE, system_screen, service_pids
        if (payload.get('scope') != SCOPE or payload.get('archive_sha256') != identity['sha256'] or
                payload.get('boot_id') != environment['boot_id'] or payload.get('after_screen') != 'home' or
                payload.get('privileged_unlock') is not False or payload.get('power_override_cleared') is not False or
                payload.get('failures') != [] or type(payload.get('swipe_count')) is not int or
                payload['swipe_count'] not in (0, 1)):
            raise ValueError('actual ordinary system home setup is incomplete, privileged or from another guest')
        for key in ('before_layout', 'after_layout', 'screenshot'):
            raw = Path(payload.get(key, ''))
            if raw.is_symlink() or not raw.is_file() or checksum(raw) != payload.get(key + '_sha256'):
                raise ValueError('actual home setup raw evidence changed: ' + key)
        before = system_screen(json.loads(Path(payload['before_layout']).read_text()))[0]
        after, home = system_screen(json.loads(Path(payload['after_layout']).read_text()))
        if (before != payload.get('before_screen') or after != 'home' or home != payload.get('home_node') or
                payload['swipe_count'] != (1 if before == 'locked' else 0)):
            raise ValueError('actual home setup layouts/gesture are inconsistent')
        pids = payload.get('service_pids_before', [])
        if not isinstance(pids, list) or any(not isinstance(pid, str) for pid in pids):
            raise ValueError('actual system home process identity records are invalid')
        if service_pids('\n'.join(pids)) != pids or pids != payload.get('service_pids_after'):
            raise ValueError('critical services changed during home setup')
        before_policy, after_policy = payload.get('policy_before'), payload.get('policy_after')
        if not isinstance(after_policy, dict):
            raise ValueError('actual home policy readback is missing')
        # Reuse the strict policy type/positive-value validation without
        # claiming to have installed the test override at this earlier stage.
        verify_policy_states(after_policy, dict(after_policy, override_ms=86400000), after_policy)
        if (not isinstance(before_policy, dict) or set(before_policy) != {'base_ms', 'override_ms'} or
                type(before_policy['base_ms']) is not int or before_policy['base_ms'] != after_policy['base_ms'] or
                (before_policy['override_ms'] is not None and
                 (type(before_policy['override_ms']) is not int or before_policy['override_ms'] <= 0))):
            raise ValueError('home gesture did not retain the original actual power policy')
        if before_policy['override_ms'] not in ((None, 10000) if before == 'locked' else (None,)):
            raise ValueError('home setup attempted to replace an unknown power override')
    elif name == 'issue20-library-exit':
        rows = payload.get('results', [])
        cases = {'empty', 'udmf', 'pasteboard', 'avplayer', 'udmf-pasteboard',
                 'pasteboard-udmf', 'avplayer-udmf', 'udmf-avplayer'}
        keys = {(row.get('case'), row.get('repeat')) for row in rows}
        if (payload.get('candidate_inputs') or payload.get('target') != environment['target'] or
                payload.get('arch') != environment['guest_arch'] or
                payload.get('device') != environment['device_type'] or len(rows) < 24 or
                len(rows) != len(keys) or not {(case, repeat) for case in cases for repeat in range(3)} <= keys or
                any(type(row.get('guest_exit_code')) is not int or row['guest_exit_code'] != 0 for row in rows)):
            raise ValueError('system DSO exit coverage is incomplete or uses private substitute libraries')
    else:
        if payload.get('boot_id') != environment['boot_id']:
            raise ValueError('child behavior belongs to another boot: ' + name)
        if payload.get('archive_sha256') != identity['sha256']:
            raise ValueError('child behavior belongs to another package: ' + name)
        if name in REPRESENTATIVE_CHECKS:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from parallel_runtime_suite import verify_family
            verify_family(name, path, Path(identity['archive']), environment)
        if name == 'power-suspend':
            cycles = payload.get('cycles', [])
            if (payload.get('scope') != 'fresh_packaged_finite_suspend_key_wake_real_compositor' or
                    payload.get('sleep_policy_changed') is not False or
                    payload.get('periodic_external_input') is not False or
                    payload.get('independent_real_sleep_wake_compositor_cycles') != 2 or len(cycles) != 2):
                raise ValueError('real packaged sleep/wake/compositor regression is incomplete or assisted')
            for cycle in cycles:
                if (cycle.get('execute') != 'system_powerdown' or
                        cycle.get('observed_actual_s2idle_before_key') is not True or
                        type(cycle.get('render_service_pid')) is not int or
                        type(cycle.get('foundation_pid')) is not int or not cycle.get('actual_visible_windows')):
                    raise ValueError('actual sleep, finite physical key and same compositor proof required')
                for key, hash_key in (('serial_evidence', 'serial_sha256'), ('layout', 'layout_sha256'),
                                      ('screenshot', 'screenshot_sha256')):
                    nested = Path(cycle.get(key, ''))
                    if nested.is_symlink() or not nested.is_file() or checksum(nested) != cycle.get(hash_key):
                        raise ValueError('sleep/wake raw evidence missing/changed: ' + key)
                log = Path(cycle['serial_evidence']).read_text(errors='replace')
                if log.rfind('PM: suspend entry (s2idle)') < 0 or log.rfind('PM: suspend exit') <= log.rfind(
                        'PM: suspend entry (s2idle)'):
                    raise ValueError('actual kernel resume was not completed')
                with Path(cycle['screenshot']).open('rb') as picture:
                    header = picture.read(24)
                if (len(header) != 24 or header[:8] != b'\x89PNG\r\n\x1a\n' or
                        header[12:16] != b'IHDR' or min(struct.unpack('>II', header[16:24])) < 100 or
                        cycle.get('screen_metrics', {}).get('sample_color_count', 0) < 64 or
                        cycle.get('screen_metrics', {}).get('luminance_range', 0) < 16):
                    raise ValueError('actual resumed compositor image is blank')
            if (cycles[0]['render_service_pid'] != cycles[1]['render_service_pid'] or
                    cycles[0]['foundation_pid'] != cycles[1]['foundation_pid']):
                raise ValueError('compositor/framework restarted during repeated resume')
        elif name == 'serial':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from guest_ui import select_node
            from verify_serial_results import EXPECTED_CASE_ORDER, verify as verify_basic
            from verify_serial_attachment_results import ORDER, verify as verify_attachment
            scenarios = payload.get('scenarios', {})
            if (payload.get('scope') != 'fresh_packaged_2in1_ordinary_Serial_USB_UI_data_attachment_regressions' or
                    environment['device_type'] != '2in1' or payload.get('device') != '2in1' or
                    payload.get('kernel_boot_id_unchanged') is not True or
                    payload.get('no_raw_node_permission_changes') is not True or
                    payload.get('no_authorization_IPC_shortcut') is not True or
                    set(scenarios) != {'basic', 'attachment'}):
                raise ValueError('actual packaged ordinary Serial/attachment regression missing or substituted')
            for scenario, count in (('basic', len(EXPECTED_CASE_ORDER)), ('attachment', len(ORDER))):
                row = scenarios[scenario]
                if (row.get('status') != 'pass' or row.get('case_count') != count or
                        type(row.get('ordinary_uid')) is not int or row['ordinary_uid'] // 200000 != 100 or
                        row['ordinary_uid'] % 200000 < 10000):
                    raise ValueError('Serial scenario incomplete or not an ordinary account100 app')
                for key, hash_key in (('build_inputs', 'build_inputs_sha256'), ('guest_results', 'guest_sha256'),
                                      ('host_results', 'host_sha256')):
                    nested = Path(row.get(key, ''))
                    if nested.is_symlink() or not nested.is_file() or checksum(nested) != row.get(hash_key):
                        raise ValueError('actual Serial raw evidence changed/missing: ' + key)
                inputs = json.loads(Path(row['build_inputs']).read_text())
                page = audit / ('serial_probe.ets' if scenario == 'basic' else 'serial_attachment_probe.ets')
                if (inputs.get('request_permissions') != [] or inputs.get('run_id') != row.get('run_id') or
                        inputs.get('scenario') != scenario or inputs.get('arch') != environment['guest_arch'] or
                        inputs.get('page_source_sha256') != checksum(page)):
                    raise ValueError('Serial HAP permissions/source/nonce/ABI do not match current tests')
                guest_rows = [json.loads(line) for line in Path(row['guest_results']).read_text().splitlines()]
                host_rows = [json.loads(line) for line in Path(row['host_results']).read_text().splitlines()]
                if scenario == 'basic':
                    errors = verify_basic(guest_rows, host_rows, inputs['run_id'], inputs['bundle_name'], inputs['port_name'])
                else:
                    errors = verify_attachment(guest_rows, inputs['run_id'], inputs['bundle_name'], inputs['port_name'])
                    operations = ['begin', 'attach', 'detach', 'attach', 'detach', 'attach', 'detach', 'quit']
                    if ([item.get('operation') for item in host_rows] != operations or
                            any(item.get('run_id') != inputs['run_id'] or item.get('host_operation_completed') is not True
                                for item in host_rows)):
                        errors.append('actual host attachment cycle transcript missing/changed')
                if errors:
                    raise ValueError('actual Serial strict transcript verification failed: ' + '; '.join(errors))
            expected_actions = {'basic-trusted-deny': ('notAllowButton', True),
                'basic-trusted-allow': ('allowButton', True),
                'original-trusted-request-before-unplug': ('allowButton', False),
                'replacement-new-trusted-deny': ('notAllowButton', True),
                'replacement-new-trusted-allow': ('allowButton', True),
                'replug-new-trusted-deny': ('notAllowButton', True),
                'replug-new-trusted-allow': ('allowButton', True)}
            actions = [row for row in payload.get('ui_actions', []) if row.get('trusted_bundle') == 'com.usb.right']
            if len(actions) != len(expected_actions) or {row.get('label') for row in actions} != set(expected_actions):
                raise ValueError('genuine trusted Serial Allow/Deny UI actions not complete')
            for action in actions:
                nested = Path(action.get('layout', ''))
                if (nested.is_symlink() or not nested.is_file() or checksum(nested) != action.get('layout_sha256') or
                        (action.get('decision'), action.get('clicked')) != expected_actions[action['label']]):
                    raise ValueError('trusted Serial UI snapshot/decision changed')
                selected = select_node(json.loads(nested.read_text()), 'com.usb.right',
                                       text=action['selected_node']['attributes']['text'], clickable=True)
                if selected != action['selected_node']:
                    raise ValueError('trusted Serial action did not target the actual visible node')
            required_devices = {'initial-unconnected-endpoint': False, 'basic-real-USB-attach': True,
                'basic-host-disconnect-actual-USB-detach': False, 'attachment-original': True,
                'unplug-while-real-authorization-pending': False, 'replacement-identical-public-USB-tuple': True,
                'detach-live-open-port': False, 'replug-same-physical-public-tuple': True,
                'final-own-endpoint-detached': False}
            snapshots = payload.get('device_snapshots', [])
            if len(snapshots) != len(required_devices) or {row.get('label'): row.get('present')
                    for row in snapshots} != required_devices:
                raise ValueError('actual guest USB devnode lifecycle evidence incomplete')
        elif name == 'arkweb':
            if (payload.get('persona') != 'web' or type(payload.get('ordinary_uid')) is not int or
                    payload['ordinary_uid'] // 200000 != 100):
                raise ValueError('Web execution must be an actual ordinary account100 app')
            nested = Path(payload.get('result', ''))
            if (not nested.is_file() or nested.is_symlink() or checksum(nested) != payload.get('result_sha256') or
                    json.loads(nested.read_text()).get('status') != 'pass'):
                raise ValueError('actual Web strict verification is missing or changed')
        elif name == 'vulkan':
            required = {'vulkan-device', 'vulkan-headless', 'vulkan-ohos-surface', 'vulkan-window', 'gles-llvm'}
            results = payload.get('results', {})
            if set(results) != required:
                raise ValueError('Vulkan device, WSI, compositor and LLVM GLES shader lifetimes are mandatory')
            for kind, row in results.items():
                nested = Path(row.get('evidence', ''))
                if (nested.is_symlink() or not nested.is_file() or checksum(nested) != row.get('sha256') or
                        json.loads(nested.read_text()).get('status') != 'pass'):
                    raise ValueError('actual Vulkan child result missing or changed: ' + kind)
                if kind == 'gles-llvm':
                    native = json.loads(nested.read_text())
                    audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
                    sys.path.insert(0, str(audit))
                    from run_root_probe import verify_result
                    raw = nested.parent / 'stdout.jsonl'
                    stderr = nested.parent / 'stderr.txt'
                    if (native.get('kind') != kind or
                            native.get('scope') != 'isolated_root_probe_only_not_normal_app_or_full_capability_gate' or
                            native.get('archive_sha256') != identity['sha256'] or
                            native.get('boot_id') != environment['boot_id'] or
                            native.get('archive_binding') != 'actual_live_owned_boot_and_initial_full_archive_inventory' or
                            native.get('arch') != environment['guest_arch'] or
                            native.get('device') != environment['device_type'] or
                            native.get('target') != environment['target'] or
                            native.get('kernel_boot_id_unchanged') is not True or
                            native.get('first_artifact_behavior_gate_passed') is not False or
                            raw.is_symlink() or not raw.is_file() or checksum(raw) != native.get('log_sha256') or
                            stderr.is_symlink() or not stderr.is_file() or checksum(stderr) != native.get('stderr_sha256')):
                        raise ValueError('LLVM GLES must execute on this actual newly packaged boot')
                    if re.search(r'bad fde:|FDE is really a CIE', stderr.read_text(), re.I):
                        raise ValueError('actual LLVM GLES JIT registration failed')
                    verified = verify_result(kind, raw.read_text(), environment['guest_arch'],
                                             native.get('run_id'), native.get('probe_exit_code'))
                    if native.get('result') != verified:
                        raise ValueError('LLVM GLES typed verification differs from actual raw results')
        elif name in ('rs-objects', 'screen-modes', 'project-quota'):
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from run_root_probe import verify_result
            raw = path.parent / 'stdout.jsonl'
            if (payload.get('kind') != name or
                    payload.get('scope') != 'isolated_root_probe_only_not_normal_app_or_full_capability_gate' or
                    payload.get('archive_binding') != 'actual_live_owned_boot_and_initial_full_archive_inventory' or
                    payload.get('arch') != environment['guest_arch'] or payload.get('device') != environment['device_type'] or
                    payload.get('target') != environment['target'] or payload.get('kernel_boot_id_unchanged') is not True or
                    payload.get('first_artifact_behavior_gate_passed') is not False or
                    raw.is_symlink() or not raw.is_file() or checksum(raw) != payload.get('log_sha256')):
                raise ValueError('real newly packaged root-probe evidence required: ' + name)
            result = verify_result(name, raw.read_text(), environment['guest_arch'], payload.get('run_id'),
                                   payload.get('probe_exit_code'))
            if result != payload.get('result'):
                raise ValueError('root-probe result differs from its actual process transcript: ' + name)
            if name == 'project-quota':
                from verify_project_quota import data_device
                mounts = path.parent / 'actual-mounts.log'
                if (mounts.is_symlink() or not mounts.is_file() or
                        checksum(mounts) != payload.get('actual_mounts_sha256') or
                        data_device(mounts.read_text()) != payload.get('quota_device')):
                    raise ValueError('actual secure userdata mount with quota enforcement required')
        elif name == 'certificate-manager':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_certificate_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'])
        elif name == 'photos-asset':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_photos_asset_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'settings-navigation':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_settings_navigation_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'settings-all-navigation':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_settings_all_navigation_evidence import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                            environment['device_type'], environment['target'])
        elif name == 'child-default-profile':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_child_default_profile_evidence import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                            environment['device_type'], environment['target'])
        elif name == 'storage-stats':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_storage_stats_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'completion-handler':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_completion_handler_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'image-metadata':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_image_metadata_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'rpc-runtime':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_rpc_runtime_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'avc-media':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_avc_media_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                            environment['device_type'], environment['target'])
        elif name == 'audio-capture':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_audio_capture_results import verify_batch
            verify_batch(payload, Path(identity['archive']), environment['boot_id'], environment['guest_arch'])
        elif name == 'media-recorder':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_media_recorder_results import verify_batch
            verify_batch(payload, Path(identity['archive']), environment['boot_id'], environment['guest_arch'])
        elif name == 'audio-focus':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_audio_focus_results import verify_evidence
            verify_evidence(payload, Path(identity['archive']), environment['boot_id'], environment['guest_arch'])
        elif name == 'audio-revoke':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_audio_revoke_results import verify_evidence
            verify_evidence(payload, Path(identity['archive']), environment['boot_id'], environment['guest_arch'])
        elif name == 'observer-info':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_observer_info_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'spring-loading':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_spring_loading_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                            environment['device_type'], environment['target'])
        elif name == 'arkui-components':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_arkui_components_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                            environment['device_type'], environment['target'])
        elif name == 'screen-blink':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_screen_blink_evidence import verify_evidence as verify_blink
            verify_blink(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                         environment['device_type'], environment['target'])
        elif name == 'luminance-sampler':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_luminance_results import verify_evidence as verify_luminance
            if payload.get('target') != environment['target']:
                raise ValueError('luminance caller belongs to another packaged guest')
            verify_luminance(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                             environment['device_type'])
        elif name == 'ethernet-control':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_ethernet_control_results import verify_evidence as verify_ethernet
            verify_ethernet(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                            environment['device_type'], environment['target'])
        elif name == 'insight-contract':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_insight_contract_evidence import verify_evidence as verify_insight
            verify_insight(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                           environment['device_type'], environment['target'])
        elif name == 'lazy-column':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_lazy_column_evidence import verify_evidence as verify_lazy
            verify_lazy(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                        environment['device_type'], environment['target'])
        elif name == 'lazy-layouts':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_lazy_layouts_evidence import verify_evidence as verify_lazy_layouts
            verify_lazy_layouts(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                                environment['device_type'], environment['target'])
        elif name == 'selection':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_selection_evidence import verify_evidence as verify_selection
            verify_selection(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                             environment['device_type'], environment['target'])
        elif name == 'env-reader':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_env_reader_evidence import verify_evidence as verify_env_reader
            verify_env_reader(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                              environment['device_type'], environment['target'])
        elif name == 'sys-vpn-store':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_sys_vpn_store_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                            environment['device_type'], environment['target'])
        elif name == 'photo-result-set':
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from verify_photo_result_set_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'],
                            environment['device_type'], environment['target'])
        elif name == 'network-accounting':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_network_accounting_evidence import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'hitrace':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_hitrace_evidence import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'graphics-memory':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_graphics_memory_evidence import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'thermal':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_thermal_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'fa-particle':
            audit = Path(__file__).resolve().parents[1] / 'ci/capability-audit'
            sys.path.insert(0, str(audit))
            from verify_fa_particle_results import verify_evidence
            verify_evidence(payload, identity['sha256'], environment['boot_id'], environment['guest_arch'])
        elif name == 'native-bindings-e2e':
            modules = payload.get('modules', {})
            expected = payload.get('expected_modules', [])
            if (not isinstance(expected, list) or len(expected) < 32 or len(set(expected)) != len(expected) or
                    set(modules) != set(expected) or payload.get('module_count') != len(expected) or
                    any(row.get('status') != 'pass' or type(row.get('case_count')) is not int or
                        row['case_count'] < 1 for row in modules.values()) or
                    payload.get('dependency_locks_unchanged') is not True or
                    payload.get('original_checkout_unchanged') is not True):
                raise ValueError('all current bindings modules must really run, without skips or dependency changes')
        elif name == 'cxx-arkts11-gaps':
            baseline_path = Path(__file__).resolve().parent.parent / 'docs/capability-audit/native-arkts11-gap-ledger.json'
            baseline = json.loads(baseline_path.read_text())['devices'][environment['device_type']]
            expected = {'native:' + row['syscap'] + ':' + row['library'] for row in baseline['native_abi_gaps']}
            expected |= {'arkts_load:' + row['module'] for row in baseline['arkts11_module_load_gaps']}
            expected |= {'arkts_export:' + row['module'] + ':' + missing['name']
                         for row in baseline['arkts11_runtime_export_gaps'] for missing in row['missing']}
            expected |= {'const_enum:' + row['module'] + ':' + value['name']
                         for row in baseline['arkts11_compiled_constant_enum_contracts'] for value in row['contracts']}
            expected |= {'permission:' + row['permission'] for row in baseline['permission_registry_gaps']}
            expected |= {'behavior:' + row['id'] for row in baseline['runtime_behavior_gaps']}
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci/capability-audit'))
            from release_scope import SCOPE, exclusion_record
            original_count = len(expected)
            exclusions = exclusion_record(environment['device_type'], expected)
            expected -= set(exclusions['ids'])
            if (payload.get('schema_version') != 2 or payload.get('scope') != SCOPE or
                    payload.get('original_expected_count') != original_count or
                    payload.get('release_exclusions') != exclusions or
                    payload.get('excluded') != ['ArkTS Static', 'CloudSync', 'imageGeneration'] or
                    payload.get('unresolved') != [] or type(payload.get('expected_count')) is not int or
                    payload['expected_count'] != len(expected) or payload.get('closed_count') != len(expected) or
                    set(payload.get('closed', {})) != expected or
                    payload.get('audit_baseline_sha256') != checksum(baseline_path)):
                raise ValueError('complete C++/ArkTS1.1 audit closure is missing; narrow samples are insufficient')
    return payload


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_inputs(archive):
    name = archive.name.removesuffix(".tar.gz") + "/build-inputs.json"
    with tarfile.open(archive, "r:gz") as package:
        candidates = [member for member in package.getmembers() if member.name == name]
        if len(candidates) != 1 or not candidates[0].isfile() or candidates[0].size > 8 * 1024 * 1024:
            raise ValueError("first archive has no unique regular frozen build-input manifest")
        return json.load(package.extractfile(candidates[0]))


def verify(archive, evidence, repository, product, device_type):
    if evidence.is_symlink() or not evidence.is_file():
        raise ValueError("new first-artifact behavior evidence is required; do not start the remaining matrix")
    document = json.loads(evidence.read_text())
    if (document.get("schema_version") != 2 or document.get("scope") != "new_packaged_qemu_behavior"
            or document.get("first_artifact_behavior_gate_passed") is not True):
        raise ValueError("static, older-image or failed evidence cannot satisfy the first-artifact gate")
    identity = document.get("package", {})
    if (Path(identity.get("archive", "")).absolute() != archive.absolute()
            or identity.get("sha256") != checksum(archive)):
        raise ValueError("first behavior evidence does not match the actual new archive")
    inputs = archive_inputs(archive)
    current = digest_files(repository)
    current_tree = hashlib.sha256(json.dumps(current, sort_keys=True).encode()).hexdigest()
    if (inputs.get("files_sha256") != current or inputs.get("tree_sha256") != current_tree
            or identity.get("build_inputs_tree_sha256") != current_tree):
        raise ValueError("first artifact was not built from the current frozen scripts/patches")
    environment = document.get("test_environment", {})
    if (environment.get("product") != product or environment.get("device_type") != device_type
            or environment.get("external_keepalive") is not False
            or not environment.get("qemu_command") or not environment.get("guest_identity")
            or re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', environment.get('boot_id', '')) is None
            or not environment.get('target') or not environment.get('guest_arch')):
        raise ValueError("first-artifact boot environment is absent, wrong or assisted by external keepalive")
    checks = document.get("checks", {})
    setup = document.get('application_test_setup', {})
    if (setup.get('method') != 'existing_power-shell_development_override' or
            setup.get('after_unassisted_default_policy_boot_validation') is not True or
            setup.get('not_default_power_policy_acceptance') is not True or setup.get('restored') is not True):
        raise ValueError('finite application test setup was not actually restored')
    policy = setup.get('policy_states', {})
    verify_policy_states(policy.get('before'), policy.get('setup'), policy.get('restored'))
    required = REQUIRED_CHECKS | DEVICE_CHECKS[device_type]
    if product == 'arm64_virt' and device_type == 'phone':
        required |= REPRESENTATIVE_CHECKS
    if not required.issubset(checks):
        raise ValueError("first-artifact behavior/boundary/regression coverage is incomplete")
    for name in required:
        record = checks[name]
        path = Path(record.get("evidence", ""))
        if not path.is_absolute():
            path = evidence.parent / path
        commands = record.get("commands", [])
        if (record.get("status") != "pass" or path.is_symlink() or not path.is_file()
                or record.get("sha256") != checksum(path)
                or not commands or not all(isinstance(c, dict) and c.get("argv")
                    and type(c.get("exit_code")) is int and c.get("exit_code") == 0 for c in commands)):
            raise ValueError("missing, changed or unsuccessful real behavior evidence: " + name)
        verified_payload(name, path, identity, environment)
    return document


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument("--device-type", choices=("phone", "2in1"), required=True)
    args = parser.parse_args()
    verify(args.archive, args.evidence, args.repository, args.product, args.device_type)
    print("PASS: new archive-bound behavior gate; remaining matrix may proceed")
