#!/usr/bin/env python3
"""Canonicalize pristine/SceneBoard JSON before the independent signature diff."""
import argparse
import json
from pathlib import Path

BUNDLE = 'com.ohos.calendardata'
OLD = 'CC249153FA175206B1427C71DB0F2232D91FA4B2ED7955AE1D6EBA4C362D359A'
NEW = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key in capability policy: ' + key)
        result[key] = value
    return result


def prepare(path):
    policy = json.loads(path.read_text(), object_pairs_hook=unique_object)
    entries = policy.get('install_list')
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError('unexpected capability install list')
    matches = [entry for entry in entries if entry.get('bundleName') == BUNDLE]
    if len(matches) != 1:
        raise ValueError('missing or duplicated CalendarData signing policy')
    entry = matches[0]
    if (set(entry) != {'bundleName', 'app_signature', 'allowAppDesktopIconHide',
                      'allowAppUsePrivilegeExtension'} or
            entry['app_signature'] not in ([OLD], [NEW]) or
            entry['allowAppDesktopIconHide'] is not True or
            entry['allowAppUsePrivilegeExtension'] is not True):
        raise ValueError('unknown CalendarData certificate/privilege policy; refuse to overwrite')
    # The fixed pristine file uses compact fields and CRLF; the earlier
    # SceneBoard component uses this same JSON format. Preserve every value
    # and certificate here; only the numbered patch changes the matching leaf.
    canonical = json.dumps(policy, indent=2, ensure_ascii=False) + '\n'
    if path.read_bytes() != canonical.encode():
        path.write_text(canonical)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append')
    args = parser.parse_args()
    prepare(args.source_root / 'vendor/ohemu/virt/preinstall-config/install_list_capability.json')


if __name__ == '__main__':
    main()
