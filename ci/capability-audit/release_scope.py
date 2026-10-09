"""Exact user-approved non-deliverables; never evidence that a gap was fixed.

2026-10-09: user explicitly declined implementation of CloudSync and
imageGeneration. The immutable original audit remains intact. No CLI switches,
environment flags, broad SysCap exclusions, or inferred exclusions are allowed.
"""
import hashlib
from pathlib import Path

SCOPE = 'audited_Cxx_ArkTS11_gap_closure_with_explicit_user_exclusions'
IMAGE_GENERATION = frozenset('arkts_export:@ohos.arkui.intelligence.imageGeneration:' + name for name in (
    'closeGeneratorDialog', 'closeGeneratorNodeGraph', 'hideGeneratorDialog', 'hideGeneratorNodeGraph',
    'openGeneratorNodeGraph', 'PartialResultType', 'restoreGeneratorDialog', 'restoreGeneratorNodeGraph'))


def exclusion_record(device, baseline_ids):
    if device not in ('phone', '2in1'):
        raise ValueError('unknown device profile for approved release scope')
    cloud = {'behavior:cloud-provider-implementation-missing'}
    if device == 'phone':
        cloud.add('arkts_export:@ohos.data.cloudExtension:Flag')
    excluded = IMAGE_GENERATION | cloud
    if not excluded <= set(baseline_ids):
        raise ValueError('approved release exclusions do not match the immutable audit baseline')
    return {
        'decision': 'user_2026-10-09_do_not_implement_CloudSync_or_imageGeneration',
        'policy_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'status': 'excluded_by_user_not_fixed_not_validated',
        'features': {'CloudSync': sorted(cloud), 'imageGeneration': sorted(IMAGE_GENERATION)},
        'ids': sorted(excluded),
        'count': len(excluded),
    }
