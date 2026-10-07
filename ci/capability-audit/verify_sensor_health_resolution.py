#!/usr/bin/env python3
"""Require corrected SDK metadata plus the real unchanged guest permission."""
import json
import re


CURRENT = 'ohos.permission.READ_HEALTH_DATA'
LEGACY = ('ohos.permission.HEALTH_DATA', 'ohos.permission.HEART_RATE')
SOURCE_FILES = {'interface/sdk-js/api/@ohos.sensor.d.ts',
                'base/sensors/sensor/utils/common/include/permission_util.h',
                'base/security/access_token/services/accesstokenmanager/permission_definitions.json'}


def verify(metadata: dict, definitions: dict, raw: str, patch_sha256: str) -> tuple[str, ...]:
    hashes = metadata.get('source_sha256', {})
    if (metadata.get('status') != 'pass' or
            metadata.get('scope') !=
            'three_Sensor_deprecated_overloads_match_registered_checked_health_permission' or
            metadata.get('permission') != CURRENT or
            metadata.get('legacy_unregistered_names') != list(LEGACY) or
            metadata.get('patch_sha256') != patch_sha256 or
            not isinstance(hashes, dict) or set(hashes) != SOURCE_FILES or
            any(not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None
                for value in hashes.values())):
        raise ValueError('packaged Sensor declaration/backend contract is not exact')
    rows = definitions.get('definePermissions', [])
    found = [row for row in rows if row.get('name') in (CURRENT, *LEGACY)]
    if (len(found) != 1 or found[0].get('name') != CURRENT or
            found[0].get('grantMode') != 'user_grant' or
            found[0].get('availableLevel') != 'normal' or
            found[0].get('deviceTypes') != ['phone', '2in1', 'tablet', 'tv', 'wearable']):
        raise ValueError('source AccessToken policy changed or legacy names were added')
    observed = [row for row in map(json.loads, raw.splitlines())
                if row.get('kind') == 'definition' and row.get('permissionName') == CURRENT]
    if (len(observed) != 1 or observed[0].get('result') != 0 or
            observed[0].get('grantMode') != 0 or observed[0].get('availableLevel') != 1 or
            observed[0].get('availableType') != 0 or
            any(observed[0].get(flag) is not False for flag in
                ('provisionEnable', 'distributedSceneEnable', 'isKernelEffect', 'hasValue'))):
        raise ValueError('actual guest did not register the unchanged health-data user permission')
    return LEGACY
