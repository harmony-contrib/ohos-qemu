"""Exact user-approved non-deliverables; never evidence that a gap was fixed.

2026-10-09: user explicitly declined implementation of CloudSync and
imageGeneration. The immutable original audit remains intact. No CLI switches,
environment flags or broad SysCap exclusions are allowed.
2026-10-19: user instructed treating complete providers unavailable in inspected
OpenHarmony/SIG sources as unsupported; exact findings and source evidence
are separately pinned below. This never claims implementation/runtime success.
2026-10-21: real local ASR was found in the fixed official SIG source. Reopen
LiveCaptions; integration/licensing/new-QEMU behavior remain mandatory.
"""
import hashlib
import json
from pathlib import Path

SCOPE = 'audited_Cxx_ArkTS11_gap_closure_with_explicit_user_exclusions'
IMAGE_GENERATION = frozenset('arkts_export:@ohos.arkui.intelligence.imageGeneration:' + name for name in (
    'closeGeneratorDialog', 'closeGeneratorNodeGraph', 'hideGeneratorDialog', 'hideGeneratorNodeGraph',
    'openGeneratorNodeGraph', 'PartialResultType', 'restoreGeneratorDialog', 'restoreGeneratorNodeGraph'))


PROVIDER_POLICY = 'ci/capability-audit/policy579/execution-20261021/unsupported-public-providers.json'
PROVIDER_POLICY_SHA256 = 'cad6913851d8fe91f06b7256af6248004400a37087dd19533d1a3377763dc3a8'
PROVIDER_IDS = {
    'NumberIdentity': 'behavior:telephony-number-identity-provider-missing',
    'DeviceAttest': 'behavior:device-attest-uninitialized',
    'SecurityGuardModels': 'behavior:security-guard-empty-model-config',
    'AudioVividMetaBuilder': 'behavior:audio-vivid-metadata-runtime-plugin-missing',
    'ScreenReader': 'behavior:accessibility-screen-reader-provider-missing',
    'DesktopLyrics': 'behavior:avsession-desktop-lyrics-provider-missing',
    'ExpandedTextMenu': 'behavior:arkui-expanded-text-menu-providers-missing',
    'TextServicePlugins': 'behavior:arkui-text-service-runtime-plugins-missing',
}
PARTIAL_PROVIDER_IDS = {
    'LocationDistrictGeocoder579': 'arkts_export:@ohos.geoLocationManager:getCurrentDistrict',
    'LocationBluetoothScanController579': 'arkts_export:@ohos.geoLocationManager:startBluetoothSearch',
    'LocationBluetoothStopOnLiveController579': 'arkts_export:@ohos.geoLocationManager:stopBluetoothSearch',
    'QemuBluetoothStateController579': 'behavior:bluetooth-state-transition-false-success',
    'AdsCompleteProvider579': 'behavior:advertising-service-provider-missing',
    'QemuCarrierIMSTransport579': 'behavior:telephony-no-modem-or-sim',
    'Msdp579PublicModels': 'behavior:msdp-device-status-mock-or-missing-clients',
}


def _provider_policy(device):
    if device not in ('phone', '2in1'):
        raise ValueError('unknown device profile for approved provider boundary')
    root = Path(__file__).resolve().parents[2]
    path = root / PROVIDER_POLICY
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != PROVIDER_POLICY_SHA256:
        raise ValueError('user-approved public provider boundary changed')
    value = json.loads(path.read_text())
    if (value.get('schema') != 'user-approved-public-provider-boundary/20261021' or
            value.get('decision') != 'current_complete_provider_unsupported_not_fixed_not_runtime_validated' or
            {name: row['id'] for name, row in value['features'].items()} != PROVIDER_IDS or
            any(row['repaired'] is not False or row['runtime_pass'] is not False for row in value['features'].values())):
        raise ValueError('exact unsupported provider IDs and non-success status required')
    partial = value.get('partial_features', {})
    if ({name: row['id'] for name, row in partial.items()} != PARTIAL_PROVIDER_IDS or
            any(row['whole_id_unsupported'] is not False or row['repaired'] is not False or
                row['runtime_pass'] is not False or row['new_formal_closure'] is not False or
                row['passable_without_new_runtime'] is not False for row in partial.values())):
        raise ValueError('partial provider boundaries cannot skip a whole ID or invent a runtime pass')
    for evidence in value['evidence']:
        name = evidence['path']
        aliases = {
            'docs/capability-audit/execution-20261021/livecaptions-source579.md':
                'ci/capability-audit/policy579/execution-20261021/livecaptions-source579.md',
            'docs/capability-audit/execution-20261021/livecaptions-har579.json':
                'ci/capability-audit/policy579/execution-20261021/livecaptions-har579.json'}
        source = root / aliases.get(name, name)
        if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != evidence['sha256']:
            raise ValueError('public implementation boundary evidence changed')
    return value


def provider_policy(device):
    value = _provider_policy(device)
    return {name: row for name, row in value['features'].items() if device in row['devices']}


def partial_provider_policy(device):
    """Source dispositions only; these IDs stay in actual runtime acceptance."""
    value = _provider_policy(device)
    return {name: row for name, row in value['partial_features'].items() if device in row['devices']}


def exclusion_labels(device):
    return ['ArkTS Static', 'CloudSync', 'imageGeneration', *provider_policy(device)]


def exclusion_record(device, baseline_ids):
    if device not in ('phone', '2in1'):
        raise ValueError('unknown device profile for approved release scope')
    cloud = {'behavior:cloud-provider-implementation-missing'}
    if device == 'phone':
        cloud.add('arkts_export:@ohos.data.cloudExtension:Flag')
    providers = provider_policy(device)
    excluded = IMAGE_GENERATION | cloud | {row['id'] for row in providers.values()}
    if not excluded <= set(baseline_ids):
        raise ValueError('approved release exclusions do not match the immutable audit baseline')
    return {
        'decision': 'user_conditional_public_provider_scope_revised_2026-10-21_caption_reopened',
        'policy_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'status': 'excluded_by_user_not_fixed_not_validated',
        'features': {'CloudSync': sorted(cloud), 'imageGeneration': sorted(IMAGE_GENERATION),
                     **{name: [row['id']] for name, row in providers.items()}},
        'unsupported_public_providers': {'policy_path': PROVIDER_POLICY, 'policy_sha256': PROVIDER_POLICY_SHA256,
                                         'status': 'unsupported_not_fixed_not_runtime_validated', 'features': providers,
                                         'partial_features': partial_provider_policy(device)},
        'ids': sorted(excluded),
        'count': len(excluded),
    }
