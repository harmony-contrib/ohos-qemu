"""Pure finite entry on one original held guest and seven bound callbacks.

Raw semantic observations are deliberately separate from full original-ID
acceptance. Source-only generation and a successful narrow slice cannot close
an aggregate, and the first-package behavior gate is always owned by root.
"""
import json
import math
import re
import time

from apps_providers579_bindings import raw
from apps_providers579_project import IDS, ROLES, require, validate

KEYS = {'prepare_callers', 'install', 'start', 'input', 'collect', 'network', 'cleanup'}
REMAINING = {
    'camera': [],
    'photos': ['actual_2in1_package', 'FA_live_form_host_refresh_after_asset_mutations', 'cloud_userPropertySettings_full_provider_and_real_account_flow'],
    'location': ['full_external_LocationPrivacyDetailAbility_provider_and_real_details_navigation'],
    'cast': ['second_same_artifact_QEMU_SoftBus_auth', 'real_cast_nonce_media_peer_decode_and_pause_resume_disconnect'],
    'volume': [],
    'input': ['complete_AVInputCastPickerAbility_input_device_provider', 'actual_selected_input_routing_and_independent_PCM_nonce'],
    'dhardware': ['second_same_artifact_QEMU_SoftBus_PIN_accept_reject_cancel_unbind_recovery'],
    'vpn': ['original_Network_full_TLS_TUN_data_manual_aggregate_raw'],
    'wifi': ['independent_radio_L2_and_IP_endpoint', 'actual_STA_DHCP_or_static_IP_data',
             'AP_station_join_leave_DHCP_data', 'actual_OS_detected_portal_notification_and_browser',
             'actual_idle_hotspot_notification_tap_reenable', 'source_bounded_thermal_supported_range'],
    'published': ['six_retired_labels_owning_service_behavior_raw'],
    'exports': ['new_package_surface_and_exact_182_member_typed_aggregation'],
    'imagegen': ['complete_official_SIG_seven_control_provider_or_source_bounded_unsupported_boundary'],
    'ethernet': [], 'sysvpn': ['actual_connected_config_and_appInfo_raw_from_original_Network_peer'],
    'alwaysvpn': []}


def rows(reference, run, role=None, request_id=None):
    values = [json.loads(line) for line in raw(reference).decode().splitlines() if line]
    require(values and all(row['run_id'] == run for row in values), 'actual nonce caller journal required')
    return [row for row in values if (role is None or row['role'] == role) and
            (request_id is None or row['request_id'] == request_id)]


def one(values, event):
    selected = [row for row in values if row['event'] == event]
    require(len(selected) == 1, 'one actual ' + event + ' required')
    return json.loads(selected[0]['value'])


def permission_boundary(values):
    rejected = [row for row in values if row['event'] == 'error' and row['code'] in (201, 202, 13900001, 13900012)]
    require(len(rejected) == 1 and not any(row['event'] in ('done', 'media-bytes', 'ungranted-uri-read-returned') for row in values),
            'actual native identity/permission denial required, not 401/undefined/API absence')
    return rejected[0]


def run(guest, root_callbacks, parameters):
    require(type(root_callbacks) is dict and set(root_callbacks) == KEYS and all(callable(v) for v in root_callbacks.values()),
            'exact seven original held callbacks')
    require(type(parameters) is dict and set(parameters) <= {'case', 'run_id', 'profile', 'knowledge_hook'}, 'finite stage data only')
    case, run_id, profile = parameters['case'], parameters['run_id'], parameters['profile']
    validate(case, run_id, parameters={'profile': profile})
    cb = root_callbacks
    result = {'schema_version': 1, 'case': case, 'requirement_ids': list(IDS[case]), 'run_id': run_id,
        'profile': profile, 'operations': [], 'observed_slices': [], 'failures': [],
        'unresolved_requirements': list(REMAINING[case]), 'runtime_pass': False,
        'first_artifact_behavior_gate_passed': False, 'closed_requirement_ids': []}
    serial = 0

    def keep(kind, value):
        result['operations'].append({'kind': kind, 'record': value})
        return value

    def start(role, action, payload=None):
        nonlocal serial
        serial += 1
        request = {'run_id': run_id, 'request_id': ('%03d_' % serial) + action.replace('-', '_'),
                   'action': action, 'payload': payload or {}}
        keep('request', request)
        keep('start', cb['start'](role, action, request))
        return request['request_id']

    def finish(role, request_id, *, errors=False):
        observed = keep('collect', cb['collect'](role, request_id))
        values = rows(observed['journal'], run_id, role, request_id)
        require(values and any(row['event'] == 'request' for row in values), 'actual dispatched caller request missing')
        if not errors:
            require(any(row['event'] == 'done' for row in values) and not any(row['event'] in ('error', 'request-error', 'page-error')
                    for row in values), 'actual typed operation failed or did not finish')
        return values, observed

    def call(role, action, payload=None, *, errors=False):
        return finish(role, start(role, action, payload), errors=errors)

    def touch(action, payload=None):
        return keep('input_' + action, cb['input'](action, payload or {}))

    def picture(label):
        return touch('snapshot', {'label': label})

    def native_denials(values, event, methods, code):
        errors = [row for row in values if row['event'] == event]
        require(len(errors) == len(methods) and all(row['code'] == code and
                json.loads(row['value'])['codeType'] == 'number' for row in errors),
                'every actual typed method must reject the real caller with native numeric permission code')
        require(not any(row['event'].endswith('-returned') or row['event'] == 'ethernet-unexpected-return' for row in values),
                'typed permission boundary unexpectedly returned')

    def observed(name, **evidence):
        result['observed_slices'].append({'slice': name, **evidence})

    try:
        prepared = keep('prepared_callers', cb['prepare_callers'](case, run_id, ROLES[case]))
        require(prepared['profile'] == profile, 'requested profile differs from actual boot package')
        result.update(boot_id=prepared['boot_id'], archive_sha256=prepared['archive_sha256'])
        for role in ROLES[case]:
            keep('install_' + role, cb['install'](role))
        if case in ('photos', 'camera'):
            request = start('janitor', 'permissions'); touch('media-permission'); granted, _ = finish('janitor', request)
            require(one(granted, 'permission-result')['authResults'] == [0, 0], 'actual declared READ/WRITE cleanup permissions required')
        picture('initial')
        if case == 'camera':
            call('normal', 'probe')
            for media in ('photo', 'video'):
                request = start('normal', media)
                picture(media + '_provider_before')
                touch('camera-control', {'control': media})
                if media == 'video':
                    # Public pick duration=2. Actual metadata must still show
                    # duration and a decodable stream; elapsed time is no proof.
                    time.sleep(3)
                touch('camera-control', {'control': 'confirm'})
                values, capture = finish('normal', request)
                picked = one(values, 'picker-result')
                require(picked['resultCode'] == 0 and picked['resultUri'].startswith('file://media/Photo/') and capture['binaries'],
                        'normal camera capture/result/actual readable bytes required')
                detail = one(values, 'image-pixels' if media == 'photo' else 'video-metadata')
                if media == 'photo':
                    require(detail['width'] > 0 and detail['height'] > 0 and len(detail['center']) == 4, 'actual image decode required')
                else:
                    require(detail and any('duration' in key.lower() and float(str(value)) > 0 for key, value in detail.items()),
                            'actual captured video duration required')
                foreign, denied = call('foreign', 'read-ungranted', {'uri': picked['resultUri'], 'video': media == 'video'}, errors=True)
                permission_boundary(foreign)
                cancel = start('normal', 'cancel-' + media)
                picture(media + '_cancel_before'); touch('back')
                cancelled, _ = finish('normal', cancel, errors=True)
                cancelled_result = one(cancelled, 'picker-result')
                require(cancelled_result['resultCode'] != 0 and not cancelled_result.get('resultUri') and
                        not any(row['event'] == 'media-bytes' for row in cancelled), 'real cancel must return no granted capture')
                pending = start('normal', 'cancel-' + media)
                picture(media + '_death_before'); touch('force-stop', {'role': 'normal'})
                picture(media + '_death_after')
                call('normal', 'identity')
                revoked, _ = call('normal', 'read-ungranted', {'uri': picked['resultUri'], 'video': media == 'video'}, errors=True)
                permission_boundary(revoked)
                removed, _ = call('janitor', 'cleanup-owned', {'uri': picked['resultUri']})
                require(one(removed, 'cleanup-active-after')['count'] == one(removed, 'cleanup-trash-after')['count'] == 0,
                        'actual owned capture must be absent from active and TRASH')
                observed(media + '_capture_cancel_foreign_and_process_death', capture=capture, foreign=denied,
                         abandoned_request=pending, uri=picked['resultUri'])
        elif case == 'photos':
            fixture_record = keep('original_knowledge_fixture', cb['network']('knowledge-fixture', {}))
            fixture = json.loads(raw(fixture_record['fixture']))
            before, _ = call('normal', 'recent-info')
            baseline = one(before, 'recent-info')
            creation = start('normal', 'create')
            touch('photos-consent', {'kind': 'save'})
            created, created_raw = finish('normal', creation)
            fresh = one(created, 'asset-created')
            require(fresh['uri'].startswith('file://media/Photo/'), 'actual newly consented recent image required')
            recent, recent_raw = call('normal', 'recent-info')
            info = one(recent, 'recent-info')
            require(info['defaults'] == info['explicit'] and info['defaults']['dateTaken'] > 0 and
                    info['defaults']['identifier'] not in ('', '0') and info['defaults'] != baseline['defaults'],
                    'new actual asset must change recent-info with default options normalization')
            album, album_raw = call('normal', 'default-album')
            require(type(one(album, 'default-album')) is str and one(album, 'default-album'), 'actual localized default album required')
            component = start('normal', 'recent-component')
            picture('recent_component')
            component_rows, component_raw = finish('normal', component)
            exists = [row for row in component_rows if row['event'] == 'recent-component-exists']
            require(exists and any(json.loads(row['value']) is True for row in exists), 'real recent component must report actual fresh asset')
            call('normal', 'hide-recent')
            # Remove only this caller's freshly created asset. Borrowed strict
            # family nonce assets stay exclusively owned by the original curator.
            deleted, _ = call('janitor', 'cleanup-owned', {'uri': fresh['uri']})
            require(one(deleted, 'cleanup-active-after')['count'] == one(deleted, 'cleanup-trash-after')['count'] == 0,
                    'exact fresh asset must be absent from active and TRASH')
            target_case = fixture['challenge']['cases'][0]
            uri = fixture['uris'][target_case['case_id']]
            call('normal', 'use-owned-fixture', {'uri': uri})
            selected = start('normal', 'select')
            selection = touch('photos-select-fixture')
            selected_rows, selected_raw = finish('normal', selected)
            require(one(selected_rows, 'select-result')['photoUris'] == [uri], 'real user-picked nonce URI must match original fixture')
            require(selected_raw['binaries'] and selected_raw['binaries'][0]['raw']['sha256'] == target_case['image']['sha256'],
                    'ordinary picker URI grant must expose the exact original nonce JPEG bytes')
            denied, denied_raw = call('foreign', 'read-denied', {'uri': uri}, errors=True); permission_boundary(denied)
            cancel = start('normal', 'cancel-select'); picture('photos_cancel_before'); touch('back')
            cancelled, _ = finish('normal', cancel)
            require(one(cancelled, 'select-result')['photoUris'] == [], 'cancel must not return any Photo URI')
            pending = start('normal', 'cancel-select'); picture('photos_death_before')
            touch('force-stop', {'role': 'normal'}); picture('photos_death_after')
            call('normal', 'identity'); call('normal', 'recent-info')
            observed('actual_recent_info_default_album_component_picker_grant_cancel_and_reentry',
                fresh_created=created_raw, recent_info=recent_raw, album=album_raw, component=component_raw,
                original_nonce_selection=selected_raw, foreign_denial=denied_raw, selection_ui=selection, abandoned_request=pending)
            if profile == '2in1':
                result['unresolved_requirements'].remove('actual_2in1_package')
            else:
                result['profile_scope'] = 'phone_related_slice_only_not_2in1_ID_acceptance'
        elif case == 'location':
            for role in ('normal', 'denied'):
                values, _ = call(role, 'enable', errors=True); permission_boundary(values)
            call('grant', 'reset-own-fixture')
            values, _ = call('grant', 'enable', errors=True)
            require(any(row['event'] == 'error' and row['code'] == 3301000 for row in values), 'native pending privacy dialog code required')
            picture('location_reject_before'); touch('location-reject')
            snapshot, _ = call('grant', 'snapshot'); rejected = one(snapshot, 'location-state')
            require(rejected == {'enabled': False, 'confirmed': False}, 'reject must preserve disabled/unconfirmed state')
            call('grant', 'enable', errors=True); picture('location_details_before'); touch('location-details')
            picture('location_details_actual'); touch('back'); touch('location-reject')
            call('grant', 'enable', errors=True); picture('location_accept_before'); touch('location-accept')
            snapshot, raw_state = call('grant', 'snapshot'); accepted = one(snapshot, 'location-state')
            require(accepted == {'enabled': True, 'confirmed': True}, 'real consent must enable and confirm native state')
            touch('force-stop', {'role': 'grant'}); call('grant', 'snapshot')
            restore, restore_raw = call('grant', 'restore')
            observed('native_privacy_reject_accept_permission_and_restart_restore', accepted=raw_state, restored=restore_raw)
        elif case == 'volume':
            observe_id = start('grant', 'observe'); finish('grant', observe_id)
            call('grant', 'show-volume'); picture('volume_provider')
            touch('volume-slider', {'level': 'low'}); low, low_raw = call('grant', 'volume-current')
            touch('volume-slider', {'level': 'high'}); high, high_raw = call('grant', 'volume-current')
            require(one(high, 'volume-current') > one(low, 'volume-current'), 'actual system volume must follow real provider slider')
            # Original observe request retains real volumeChange callback rows.
            callbacks = keep('volume_callbacks', cb['collect']('grant', observe_id))
            callback_rows = rows(callbacks['journal'], run_id, 'grant', observe_id)
            require(any(row['event'] == 'volume-change' for row in callback_rows), 'actual provider adjustment callback required')
            call('grant', 'hide-volume'); picture('volume_hidden')
            touch('force-stop', {'role': 'grant'}); call('grant', 'restore')
            observed('real_volume_panel_adjust_query_callback_cancel_and_restart_restore', low=low_raw, high=high_raw, callbacks=callbacks)
        elif case == 'input':
            call('grant', 'observe')
            call('grant', 'show-input'); touch('caller-control', {'role': 'grant', 'control': 'input'})
            picture('input_actual_provider_boundary'); touch('back'); call('grant', 'hide-input')
            observed('real_public_input_component_provider_boundary')
        elif case == 'vpn':
            keep('strict_peer', cb['network']('strict-vpn', {}))
            for role, control in (('deny', 'vpn-deny'), ('cancel', 'back'), ('allow', 'vpn-allow')):
                request = start(role, 'authorize'); picture('vpn_' + role + '_before'); touch(control)
                values, collected = finish(role, request)
                all_rows = rows(collected['journal'], run_id, role)
                tunnels = [r for r in all_rows if r['event'] == 'vpn-tun-created']
                if role == 'allow':
                    require(len(tunnels) == 1 and json.loads(tunnels[0]['value'])['fd'] >= 0, 'Allow must create a real ordinary caller TUN')
                else:
                    require(not tunnels, 'deny/cancel must not create a TUN')
                call(role, 'stop-vpn'); picture('vpn_' + role + '_after')
                observed('vpn_auth_' + role, raw=collected)
            touch('force-stop', {'role': 'allow'}); call('allow', 'identity')
        elif case == 'dhardware':
            keep('distinct_real_peer', cb['network']('peer-binding', {}))
            values, rejected = call('normal', 'discover', errors=True); permission_boundary(values)
            values, invalid = call('grant', 'invalid-auth', errors=True)
            require(any(row['code'] == 401 for row in values), 'actual DM invalid parameter boundary required')
            call('grant', 'discover'); picture('dm_discovery'); call('grant', 'trusted')
            observed('real_DM_discovery_permission_invalid_parameter_boundary', denied=rejected, invalid=invalid)
        elif case == 'cast':
            keep('distinct_real_peer', cb['network']('peer-binding', {}))
            call('grant', 'session-create')
            request = start('grant', 'picker'); picture('cast_actual_provider')
            touch('back'); finish('grant', request)
            call('grant', 'discover'); picture('cast_discovery')
            call('grant', 'cleanup')
            observed('actual_cast_session_picker_cancel_discovery_slice')
        elif case == 'wifi':
            for role in ('normal', 'denied'):
                values, _ = call(role, 'ap-start', errors=True); permission_boundary(values)
            values, _ = call('grant', 'snapshot'); before = one(values, 'wifi-before')
            require(not before['enabled'] and not before['hotspot'], 'refuse to disturb preexisting foreign STA/AP')
            keep('real_hwsim_radios', cb['network']('wifi-radio-prepare', {}))
            keep('actual_independent_AP', cb['network']('wifi-peer-start', {'mode': 'ap'}))
            call('grant', 'sta-start')
            deadline = time.monotonic() + 30
            while True:
                peer = keep('actual_STA_air_auth', cb['network']('wifi-peer-collect', {}))
                station = raw(peer['station']).decode() if peer['station'] else ''
                if '[AUTHORIZED]' in station:
                    break
                require(time.monotonic() < deadline, 'actual second-radio WPA authorization absent')
                time.sleep(.25)
            linked, linked_raw = call('grant', 'sta-state')
            require(one(linked, 'sta-linked')['ssid'] == 'apps579_' + run_id[:12], 'public STA must select the actual nonce AP')
            call('grant', 'sta-stop'); keep('actual_AP_peer_stop', cb['network']('wifi-peer-stop', {}))
            call('grant', 'ap-start')
            keep('actual_independent_STA', cb['network']('wifi-peer-start', {'mode': 'sta'}))
            deadline = time.monotonic() + 30
            while True:
                peer = keep('actual_AP_air_auth', cb['network']('wifi-peer-collect', {}))
                status = raw(peer['status']).decode()
                if re.search(r'^wpa_state=COMPLETED$', status, re.M):
                    break
                require(time.monotonic() < deadline, 'actual second-radio STA did not complete WPA authentication')
                time.sleep(.25)
            ap, ap_raw = call('grant', 'ap-state')
            peer_mac = raw(peer['mac']).decode().strip().lower()
            ap_state = one(ap, 'ap-state')
            require(ap_state['active'] is True and any(station['macAddress'].lower() == peer_mac for station in ap_state['stations']),
                    'actual public AP must enumerate the independently observed second-radio MAC')
            keep('actual_wlan_services', cb['network']('wifi-radio-collect', {})); picture('hotspot_actual')
            keep('actual_STA_peer_stop', cb['network']('wifi-peer-stop', {}))
            call('grant', 'ap-stop'); call('grant', 'restore')
            observed('real_two_hwsim_radio_STA_AP_WPA_permission_activation_and_restore_slice', sta=linked_raw, ap=ap_raw)
        elif case == 'ethernet':
            boundary_records = []
            for role, code in (('normal', 202), ('denied', 201)):
                values, reference = call(role, 'boundaries')
                native_denials(values, 'ethernet-denied', ('disable', 'enable', 'enabled'), code)
                boundary_records.append(reference)
            before, baseline_raw = call('grant', 'snapshot')
            baseline = one(before, 'ethernet-before')
            require(baseline['enabled'] is True and baseline['flags'] & 1, 'actual Ethernet baseline must be enabled')
            values, cycle_raw = call('grant', 'cycle')
            for event, enabled in (('ethernet-disabled', False), ('ethernet-disabled-again', False),
                                   ('ethernet-enabled', True), ('ethernet-enabled-again', True)):
                states = [json.loads(row['value']) for row in values if row['event'] == event]
                require(len(states) == 2 and all(state['enabled'] is enabled and bool(state['flags'] & 1) is enabled
                        for state in states), 'actual native Ethernet result differs from independent kernel IFF_UP')
            require(one(values, 'ethernet-restored')['enabled'] is True, 'in-caller Ethernet recovery missing')
            touch('force-stop', {'role': 'grant'})
            restored, restart_raw = call('grant', 'restore')
            require(one(restored, 'ethernet-restored') == baseline, 'actual Ethernet kernel/native state not restored after restart')
            observed('three_Ethernet_methods_native_kernel_cycles_permissions_restart_restore',
                     baseline=baseline_raw, cycle=cycle_raw, boundaries=boundary_records, restart=restart_raw)
        elif case == 'alwaysvpn':
            methods = ('isAlwaysOnVpnEnabled', 'setAlwaysOnVpnEnabled')
            boundaries = []
            for role, code in (('normal', 202), ('denied', 201)):
                values, reference = call(role, 'boundaries')
                native_denials(values, 'policy-boundary-error', methods, code)
                boundaries.append(reference)
            seeded, seeded_raw = call('grant', 'seed')
            require(one(seeded, 'policy-before') is False and one(seeded, 'policy-seeded') is True,
                    'actual owned installed VPN policy baseline/seed differs')
            for event, enabled in (('policy-enabled', True), ('policy-disabled', False)):
                states = [json.loads(row['value']) for row in seeded if row['event'] == event]
                require(len(states) == 2 and [state['round'] for state in states] == [0, 1] and
                        all(state['value'] is enabled for state in states), 'real policy toggle readback differs')
            touch('force-stop', {'role': 'grant'})
            persisted, persisted_raw = call('grant', 'verify-persisted')
            require(one(persisted, 'policy-persisted') is True, 'real system policy did not survive caller restart')
            restored, restored_raw = call('grant', 'cleanup')
            require(one(restored, 'policy-restored') is False, 'actual owned VPN policy cleanup failed')
            observed('two_AlwaysOn_methods_installed_extension_policy_persistence_and_restore',
                     seed=seeded_raw, restart=persisted_raw, boundaries=boundaries, restoration=restored_raw)
        elif case == 'sysvpn':
            from verify_sys_vpn_store_results import verify_config
            boundaries = []
            methods = ('addSysVpnConfig', 'deleteSysVpnConfig', 'getSysVpnConfig', 'getSysVpnConfigList',
                       'getConnectedSysVpnConfig', 'getConnectedVpnAppInfo')
            for role, code in (('normal', 202), ('denied', 201)):
                values, reference = call(role, 'boundaries')
                require([json.loads(row['value']) for row in values if row['event'] == 'vpn-boundary-method'] == list(methods),
                        'six original methods must each perform a real typed call')
                native_denials(values, 'vpn-boundary-error', methods, code)
                boundaries.append(reference)
            seeded, seeded_raw = call('grant', 'seed')
            baseline = one(seeded, 'store-before')
            for phase, revision in (('seed', 0), ('replace', 1)):
                for index in range(3):
                    for method in ('get', 'list'):
                        actual = one(seeded, phase + '-' + method + '-' + str(index))
                        verify_config(json.dumps(actual), run_id, index, revision, 100)
            invalid = [row for row in seeded if row['event'] == 'invalid-error']
            require(len(invalid) == 78 and all(row['code'] == 401 and json.loads(row['value'])['codeType'] == 'number'
                    for row in invalid) and not any(row['event'] == 'invalid-returned' for row in seeded),
                    'native invalid family/port/prefix/route validation differs')
            for method in ('get', 'list'):
                verify_config(json.dumps(one(seeded, 'after-invalid-' + method + '-0')), run_id, 0, 1, 100)
            touch('force-stop', {'role': 'grant'})
            persisted, persisted_raw = call('grant', 'verify-persisted')
            for index in range(3):
                for method in ('get', 'list'):
                    verify_config(json.dumps(one(persisted, 'restart-' + method + '-' + str(index))), run_id, index, 1, 100)
            connected, connected_raw = call('grant', 'connected')
            require([json.loads(row['value']) for row in connected if row['event'] == 'connected-method'] ==
                    ['getConnectedSysVpnConfig', 'getConnectedVpnAppInfo'], 'actual disconnected getters absent')
            keep('actual_connected_Network_family', cb['network']('family-evidence', {}))
            restored, restored_raw = call('grant', 'cleanup')
            require(sorted(one(restored, 'store-after'), key=lambda item: item['vpnId']) ==
                    sorted(baseline, key=lambda item: item['vpnId']), 'native unrelated VPN store changed during owned cleanup')
            observed('four_store_methods_rich_three_types_replace_invalid_restart_cleanup_and_six_denials',
                     seed=seeded_raw, restart=persisted_raw, disconnected=connected_raw,
                     boundaries=boundaries, restoration=restored_raw)
        elif case == 'imagegen':
            actual = []
            methods = ('openGeneratorNodeGraph', 'hideGeneratorNodeGraph', 'restoreGeneratorNodeGraph',
                       'closeGeneratorNodeGraph', 'hideGeneratorDialog', 'restoreGeneratorDialog', 'closeGeneratorDialog')
            for role in ROLES[case]:
                values, reference = call(role, 'boundaries')
                require([json.loads(row['value']) for row in values if row['event'] == 'imagegen-boundary-method'] == list(methods),
                        'all seven original image controls must be called with a real caller UIContext')
                actual.append({'role': role, 'raw': reference, 'ui': picture('imagegen_' + role + '_boundary')})
            # These actual per-method results intentionally do not become a
            # permission/provider pass from TypeError or missing exports. Root
            # attaches the fixed official/SIG source-bound support disposition.
            observed('seven_ImageGeneration_actual_typed_boundary_records', roles=actual)
        elif case == 'published':
            values, declarations = call('normal', 'declarations')
            labels = one(values, 'exact-labels')
            require(len(labels) == 6 and all(type(v) is bool and not v for v in labels.values()), 'exact retired codec labels should remain undeclared')
            keep('actual_owning_families', cb['network']('family-evidence', {}))
            observed('exact_six_retired_label_boundary', raw=declarations)
        elif case == 'exports':
            modern, modern_raw = call('normal', 'matrix-modern'); values = one(modern, 'matrix-values')
            expected = {'copy': [2, 3], 'translate': [7, -3], 'invert': [-3, 9], 'combine': [2, 3],
                        'scale': [4, 9], 'rotate': [-3, 2], 'transformPoint': [2, 3]}
            require(all(len(values[k]) == 2 and all(math.isfinite(a) and abs(a - b) <= .0001 for a, b in zip(values[k], v))
                        for k, v in expected.items()), 'typed matrix operation semantics differ')
            legacy, legacy_raw = call('normal', 'matrix-legacy')
            from verify_matrix4_results import EXPECTED as MATRIX_EXPECTED
            actual = [json.loads(row['value']) for row in legacy if row['event'] == 'matrix-case']
            require([value['name'] for value in actual] == [name for name in MATRIX_EXPECTED if name != 'summary'] and
                    not any(row['event'] == 'matrix-case-error' for row in legacy), 'actual seven namespace helpers did not all run')
            for value in actual:
                expected_values = MATRIX_EXPECTED[value['name']]
                require(len(value['values']) == len(expected_values) and all(type(number) in (int, float) and
                        math.isfinite(number) and abs(number - expected) <= .0001 for number, expected in
                        zip(value['values'], expected_values)), 'actual namespace arithmetic/boundary/isolation differs')
            require(one(legacy, 'matrix-summary') == {'count': 16, 'failures': 0}, 'real legacy matrix regression failed')
            keep('original_typed_families', cb['network']('family-evidence', {}))
            observed('seven_original_matrix_members_modern_and_legacy_raw', modern=modern_raw, legacy=legacy_raw)
    except Exception as error:
        result['failures'].append(type(error).__name__ + ': ' + str(error))
    finally:
        # The Knowledge phase hook keeps the same consumer installed only
        # until its original collector's finally hook. No resource leaks across
        # CLI completion, no extra asset mutations in the original 22 steps.
        if not parameters.get('knowledge_hook', False):
            try:
                result['cleanup'] = cb['cleanup']()
                require(not result['cleanup'].get('failures'), 'actual cleanup/restoration failed')
            except Exception as error:
                result['failures'].append('cleanup: ' + type(error).__name__ + ': ' + str(error))
    return result


def observe_photos_phase(callbacks, run_id, phase):
    require(phase in ('hidden', 'unhidden', 'trashed', 'recovered', 'deleted', 'cleanup'), 'fixed original real phase hook')
    output = {'phase': phase, 'operations': [], 'runtime_pass': False, 'closed_requirement_ids': []}
    output['fixture'] = callbacks['network']('knowledge-fixture', {})
    for action in ('recent-info', 'default-album'):
        request_id = 'original_' + phase + '_' + action.replace('-', '_')
        request = {'run_id': run_id, 'request_id': request_id, 'action': action, 'payload': {}}
        output['operations'].append({'request': request, 'start': callbacks['start']('normal', action, request),
                                     'collect': callbacks['collect']('normal', request_id)})
    output['ui'] = callbacks['input']('snapshot', {'label': 'original_' + phase})
    return output
