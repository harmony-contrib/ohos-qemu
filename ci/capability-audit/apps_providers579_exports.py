"""Original 182-member aggregate, never a platform-wide API claim.

The historical table only selects the exact regression set. Every closure
requires newly packaged typed operation records or a source-bounded declaration
correction AND its owning typed behavior; a dynamic export/getter is insufficient.
"""
import hashlib
import json
from apps_providers579_bindings import raw
from apps_providers579_project import require

ORIGINAL_SHA256 = '6d27d8e2b2d701df56cf8fe821aff250e0a7ebe52d7faebcc94ce89d59b90d10'
FUNCTION_FAMILIES = {
    '@ohos.accessibility.config': ('apps_ui578', ('startBlinking', 'stopBlinking')),
    '@ohos.arkui.intelligence.imageGeneration': ('apps579_imagegen', ('closeGeneratorDialog', 'closeGeneratorNodeGraph',
        'hideGeneratorDialog', 'hideGeneratorNodeGraph', 'openGeneratorNodeGraph', 'restoreGeneratorDialog', 'restoreGeneratorNodeGraph')),
    '@ohos.bluetooth.connection': ('live_inputs578', ('startPairOutOfBand',)),
    '@ohos.geoLocationManager': ('live_inputs578', ('addFusionFence', 'getCurrentDistrict', 'getLocationIconStatus',
        'getPostProcessingTrack', 'isFusionFenceSupported', 'removeFusionFence', 'startBluetoothSearch', 'stopBluetoothSearch')),
    '@ohos.matrix4': ('apps579_exports', ('combine', 'copy', 'invert', 'rotate', 'scale', 'transformPoint', 'translate')),
    '@ohos.net.ethernet': ('apps579_ethernet', ('disableEthernetInterface', 'enableEthernetInterface', 'isEthernetEnabled')),
    '@ohos.net.vpn': ('apps579_sysvpn', ('addSysVpnConfig', 'deleteSysVpnConfig', 'getConnectedSysVpnConfig',
        'getConnectedVpnAppInfo', 'getSysVpnConfig', 'getSysVpnConfigList')),
    '@ohos.net.vpnExtension': ('apps579_alwaysvpn', ('isAlwaysOnVpnEnabled', 'setAlwaysOnVpnEnabled')),
    '@ohos.telephony.call': ('rtt578', ('offReceiveRttMessage', 'offRttErrCause', 'offRttModifyInd', 'onReceiveRttMessage',
        'onRttErrCause', 'onRttModifyInd', 'sendRttMessage', 'setRttCapability', 'startRtt', 'stopRtt')),
    '@ohos.telephony.observer': ('rtt578', ('offCommunicationStateChange', 'onCommunicationStateChange'))}


# Positive connected getters are owned by the original strict Network actor,
# whose real peer has already established the tunnel. Store CRUD stays here.
MEMBER_FAMILIES = {('@ohos.net.vpn', name): 'network578' for name in
                   ('getConnectedSysVpnConfig', 'getConnectedVpnAppInfo')}


def function_family(module, name):
    return MEMBER_FAMILIES.get((module, name), FUNCTION_FAMILIES[module][0])


def original_members(reference):
    body = raw(reference)
    require(hashlib.sha256(body).hexdigest() == ORIGINAL_SHA256, 'exact original audit regression set required')
    value = json.loads(body)
    members = {(module['module'], item['name']): item for module in value['modules']
               for item in module['missing_official_runtime_exports']}
    require(len(members) == 182 and len({module for module, _ in members}) == 54, 'original member set differs')
    functions = {key for key, item in members.items() if item['kind'] == 'function'}
    expected = {(module, name) for module, (_, names) in FUNCTION_FAMILIES.items() for name in names}
    require(functions == expected and len(functions) == 48, 'original typed function routes differ')
    return members


def aggregate(original, surface, families, *, boot_id, archive_sha256):
    members = original_members(original)
    latest = json.loads(raw(surface))
    require(latest['boot_id'] == boot_id and latest['archive_sha256'] == archive_sha256 and latest['profile'] == 'phone',
            'actual newly packaged phone surface required')
    # A fixed family record may report verified per-member operation receipts.
    # JSON cannot choose a Python callable, source file or executable. Missing
    # typed routes remain explicit gaps even if dynamic exports were repaired.
    coverage = {}
    for family, reference in families.items():
        value = json.loads(raw(reference))
        require(value['boot_id'] == boot_id and value['archive_sha256'] == archive_sha256, 'typed family package/boot differs')
        for row in value.get('api26_members', []):
            key = row['module'], row['member']
            require(key in members and key not in coverage, 'unknown/duplicate original member claim')
            if members[key]['kind'] == 'function':
                require(family == function_family(*key), 'typed member belongs to a different fixed family')
            require(row.get('caller_identity') and row.get('request') and row.get('journal') and row.get('oracle_raw') and
                    row.get('normal_action') and row.get('boundary_action') and row.get('restoration'),
                    'module/export/getter records cannot close a typed member')
            for name in ('caller_identity', 'request', 'journal', 'oracle_raw', 'restoration'):
                raw(row[name])
            coverage[key] = {'family': family, 'record': reference, 'operation': row}
    return {'scope': 'original_54_modules_182_members_only', 'historical_selector': original, 'new_surface': surface,
        'boot_id': boot_id, 'archive_sha256': archive_sha256,
        'typed_members': [{'module': key[0], 'member': key[1], **row} for key, row in sorted(coverage.items())],
        'unresolved_members': [{'module': key[0], 'member': key[1], 'kind': item['kind'],
            'required_family': function_family(*key) if item['kind'] == 'function' else 'typed_declaration_or_intrinsic_behavior'}
            for key, item in sorted(members.items()) if key not in coverage],
        'runtime_pass': False, 'first_artifact_behavior_gate_passed': False, 'closed_requirement_ids': []}
