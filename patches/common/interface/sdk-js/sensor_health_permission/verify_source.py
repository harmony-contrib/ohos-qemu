#!/usr/bin/env python3
"""Fail closed unless legacy Sensor docs match the real AccessToken backend."""
import argparse
import hashlib
import json
from pathlib import Path
import re


CURRENT = 'ohos.permission.READ_HEALTH_DATA'
LEGACY = ('ohos.permission.HEALTH_DATA', 'ohos.permission.HEART_RATE')


SOURCE_FILES = ('interface/sdk-js/api/@ohos.sensor.d.ts',
                'base/sensors/sensor/utils/common/include/permission_util.h',
                'base/security/access_token/services/accesstokenmanager/permission_definitions.json')


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(source_root: Path) -> dict:
    paths = [source_root / name for name in SOURCE_FILES]
    sdk = paths[0].read_text()
    backend = paths[1].read_text()
    definitions = json.loads(paths[2].read_text())
    rows = definitions['definePermissions']
    relevant = [row for row in rows if row['name'] in (CURRENT, *LEGACY)]
    if (len(relevant) != 1 or relevant[0]['name'] != CURRENT or
            relevant[0]['grantMode'] != 'user_grant' or relevant[0]['availableLevel'] != 'normal' or
            relevant[0].get('deviceTypes') != ['phone', '2in1', 'tablet', 'tv', 'wearable']):
        raise ValueError('registered heart-rate permission policy is absent or changed')
    if re.search(r'READ_HEALTH_DATA_PERMISSION\s*=\s*"' + re.escape(CURRENT) + '"', backend) is None:
        raise ValueError('Sensor service no longer checks the documented permission')
    for legacy in LEGACY:
        if '@permission ' + legacy in sdk:
            raise ValueError('legacy unregistered Sensor permission remains in SDK API')
    contracts = re.findall(r'@permission\s+(ohos\.permission\.[A-Z_]+)\s*\n\s*\*\s*@param\s*\{\s*SensorType\.SENSOR_TYPE_ID_HEART_RATE\s*\}', sdk)
    if contracts != [CURRENT, CURRENT, CURRENT]:
        raise ValueError('three deprecated heart-rate overloads do not use the registered permission')
    patch = Path(__file__).with_name('0001-document-the-registered-heart-rate-permission.patch')
    return {'schema_version': 1, 'status': 'pass',
            'scope': 'three_Sensor_deprecated_overloads_match_registered_checked_health_permission',
            'permission': CURRENT, 'legacy_unregistered_names': list(LEGACY),
            'source_sha256': {name: checksum(path) for name, path in zip(SOURCE_FILES, paths)},
            'patch_sha256': checksum(patch)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.source_root)
    if args.output is not None:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('verified three Sensor heart-rate declarations against unchanged AccessToken policy')


if __name__ == '__main__':
    main()
