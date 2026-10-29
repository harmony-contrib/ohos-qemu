#!/usr/bin/env python3
"""Select API 26 unsigned compilation; GN signs with the existing OS profile."""
import argparse
import json
from pathlib import Path

PRODUCT = {"name": "default", "compileSdkVersion": "26.0.0",
           "targetSdkVersion": "26.0.0", "compatibleSdkVersion": 23,
           "runtimeOS": "OpenHarmony"}
ORIGINAL_PRODUCT = {"name": "default", "signingConfig": "release",
                    "compileSdkVersion": 23, "compatibleSdkVersion": 23}
MODULES = {"entry", "common", "datastructure", "datamanager", "rrule", "dataprovider"}


def configure(path):
    original = path.read_text()
    # The pinned source's build-profile.json5 is strict JSON. Reject an
    # unfamiliar future format rather than requiring a host-only parser.
    document = json.loads(original)
    modules = document.get('modules', [])
    if (len(modules) != 6 or {entry.get('name') for entry in modules} != MODULES or
            any(entry.get('srcPath') != './' + entry.get('name', '') for entry in modules)):
        raise ValueError('unexpected CalendarData local HAR graph; refuse to drop dependencies')
    app = document.get('app', {})
    if app.get('products') == [PRODUCT] and 'signingConfigs' not in app:
        return
    if app.get('products') != [ORIGINAL_PRODUCT]:
        raise ValueError('unexpected CalendarData source product configuration')
    configs = app.get('signingConfigs')
    if (not isinstance(configs, list) or len(configs) != 1 or configs[0].get('name') != 'release' or
            configs[0].get('material', {}).get('storeFile') != 'signature/OpenHarmony.p12' or
            configs[0].get('material', {}).get('profile') != 'signature/Calendardata.p7b'):
        raise ValueError('unexpected CalendarData IDE signing configuration')
    # This IDE config refers to an absent per-project keystore. Do not sign
    # twice or invent ACLs: app_sign uses the already pinned Calendardata.p7b.
    del app['signingConfigs']
    app['products'] = [PRODUCT]
    path.write_text(json.dumps(document, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product')
    args = parser.parse_args()
    configure(args.source_root / 'applications/standard/calendardata/build-profile.json5')
    print('CalendarData source provider uses API 26 and all five local HARs; runtime still requires validation')


if __name__ == '__main__':
    main()
