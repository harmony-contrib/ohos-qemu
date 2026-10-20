#!/usr/bin/env python3
"""Exact Location8 system test role using the existing certificate signer mechanics."""
import argparse
from pathlib import Path
import re
from sign_certificate_probe import sign

BUNDLE = 'org.harmonycontrib.capabilityaudit'
PERMISSIONS = {'ohos.permission.LOCATION', 'ohos.permission.APPROXIMATELY_LOCATION'}

def configure_profile(profile, role, udid, module):
    requests = module['module'].get('requestPermissions')
    abilities = module['module'].get('abilities')
    if (role != 'system' or not re.fullmatch('[a-fA-F0-9]{64}', udid or '') or
            module['app'].get('bundleName') != BUNDLE or module['module'].get('type') != 'entry' or
            not isinstance(requests, list) or len(requests) != 2 or
            any(not isinstance(r, dict) or not {'name', 'reason', 'reasonId', 'usedScene'} <= set(r) or
                type(r['reasonId']) is not int or r['reasonId'] <= 0 or
                r['usedScene'] != {'abilities': ['EntryAbility'], 'when': 'inuse'} for r in requests) or
            {r['name'] for r in requests} != PERMISSIONS or
            not isinstance(abilities, list) or len(abilities) != 1 or
            abilities[0].get('name') != 'EntryAbility' or abilities[0].get('launchType') != 'singleton' or
            module['module'].get('extensionAbilities', []) != []):
        raise ValueError('Exact singleton Location8 Stage caller and two user permissions required')
    profile['bundle-info']['bundle-name'] = BUNDLE
    profile['bundle-info']['apl'] = 'system_basic'
    profile['bundle-info']['app-feature'] = 'hos_system_app'
    profile['debug-info']['device-ids'] = [udid]
    profile['acls']['allowed-acls'] = []
    profile['permissions']['restricted-permissions'] = []
    return profile

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('signer-dist', 'jar', 'unsigned', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--role', choices=('system',), required=True)
    parser.add_argument('--udid', required=True)
    sign(parser.parse_args(), configure_profile)
