#!/usr/bin/env python3
"""Preserve Photos' existing exact privileges while canonicalizing policy."""
import argparse
import json
from pathlib import Path

BUNDLE = 'com.ohos.photos'
OLD = '9AED2A79925ECA050CD2BB9D2A7F694E49E5E135D28EBDCE53836DE76B5080ED'
NEW = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'
PERMISSIONS = ('READ_IMAGEVIDEO', 'WRITE_IMAGEVIDEO', 'READ_MEDIA', 'WRITE_MEDIA',
               'MEDIA_LOCATION', 'DISTRIBUTED_DATASYNC')


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('duplicate capability-policy key')
        result[name] = value
    return result


def prepare(path, require_patched=False, permissions=False):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('refuse redirected Photos capability policy')
    policy = json.loads(path.read_text(), object_pairs_hook=unique_object)
    entries = policy if permissions else policy.get('install_list')
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError('unexpected capability install list')
    matches = [entry for entry in entries if entry.get('bundleName') == BUNDLE]
    if len(matches) != 1:
        raise ValueError('missing or duplicate Photos signing policy')
    entry = matches[0]
    if permissions:
        expected = {'bundleName': BUNDLE, 'app_signature': entry.get('app_signature'),
            'permissions': [{'name': 'ohos.permission.' + name, 'userCancellable': False} for name in PERMISSIONS]}
        valid = entry == expected and all(item.get('userCancellable') is False for item in entry.get('permissions', []))
    else:
        valid = (set(entry) == {'bundleName', 'app_signature', 'allowAppUsePrivilegeExtension', 'allowFormVisibleNotify'} and
                 entry['allowAppUsePrivilegeExtension'] is True and entry['allowFormVisibleNotify'] is True)
    if not valid or entry.get('app_signature') not in ([OLD], [NEW]):
        raise ValueError('unknown Photos certificate/privilege policy; preserve it')
    if require_patched and entry['app_signature'] != [NEW]:
        raise ValueError('Photos source signer does not match the precise vendor certificate pin')
    return (json.dumps(policy, indent=2, ensure_ascii=False) + '\n').encode()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append')
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    directory = args.source_root / 'vendor/ohemu/virt/preinstall-config'
    # Validate both policies before normalizing either; a changed grant list or
    # redirected sibling must not partially change the other policy.
    planned = [(directory / name, permissions) for name, permissions in (
        ('install_list_capability.json', False), ('install_list_permissions.json', True))]
    normalized = [(path, prepare(path, args.require_patched, permissions)) for path, permissions in planned]
    for path, content in normalized:
        if path.read_bytes() != content:
            path.write_bytes(content)
