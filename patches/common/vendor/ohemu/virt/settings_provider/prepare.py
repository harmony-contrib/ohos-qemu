#!/usr/bin/env python3
"""Validate the approved certificate-bound Settings extension privilege only."""
import argparse
import json
from pathlib import Path

BUNDLE = 'com.ohos.settings'
OLD = 'EB5DBE52EE8DD7206DDE612E7484E88CE264E74958704D0712BFA774C87F4DA1'
NEW = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'
CAPABILITY = {'bundleName': BUNDLE, 'app_signature': [NEW], 'allowAppUsePrivilegeExtension': True}
GRANTS = [{'name': 'ohos.permission.GET_INSTALLED_BUNDLE_LIST', 'userCancellable': False}]


def unique(pairs):
    value = {}
    for key, entry in pairs:
        if key in value:
            raise ValueError('duplicate Settings preinstall policy key')
        value[key] = entry
    return value


def prepare(path, require_patched=False, permissions=False):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('redirected Settings preinstall policy')
    value = json.loads(path.read_text(), object_pairs_hook=unique)
    rows = value if permissions else value.get('install_list')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('invalid Settings preinstall list')
    matches = [row for row in rows if row.get('bundleName') == BUNDLE]
    if permissions:
        if len(matches) != 1:
            raise ValueError('unique existing Settings grant row required')
        entry = matches[0]
        expected = {'bundleName': BUNDLE, 'app_signature': entry.get('app_signature'), 'permissions': GRANTS}
        if (entry != expected or entry.get('app_signature') not in ([OLD], [NEW]) or
                any(row.get('userCancellable') is not False for row in entry.get('permissions', []))):
            raise ValueError('unknown Settings signer or changed existing grants; preserving it')
        if require_patched and entry['app_signature'] != [NEW]:
            raise ValueError('Settings grant signer does not match source HAP')
    elif matches:
        if len(matches) != 1 or matches[0] != CAPABILITY or matches[0].get('allowAppUsePrivilegeExtension') is not True:
            raise ValueError('unknown Settings privilege; preserving it')
    elif require_patched:
        raise ValueError('approved narrow Settings extension capability is missing')
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append')
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    directory = args.source_root / 'vendor/ohemu/virt/preinstall-config'
    # Validate both siblings before either is normalized or patched.
    planned = [(directory / name, role) for name, role in
               [('install_list_capability.json', False), ('install_list_permissions.json', True)]]
    normalized = [(path, prepare(path, args.require_patched, role)) for path, role in planned]
    for path, content in normalized:
        if path.read_bytes() != content:
            path.write_bytes(content)


if __name__ == '__main__':
    main()
