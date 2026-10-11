#!/usr/bin/env python3
"""Sign exact screen-blink test roles without modifying image permission rules."""
import argparse
from pathlib import Path
import re

from build_screen_blink_probe import BUNDLE, PERMISSIONS, ROLES, module
from sign_certificate_probe import sign


def configure_profile(profile, role, udid, compiled):
    if role not in ROLES or re.fullmatch('[0-9a-fA-F]{64}', udid) is None:
        raise ValueError('explicit blink role and actual UDID required')
    expected = module(role)['module']['requestPermissions']
    if compiled['app'].get('bundleName') != BUNDLE or compiled['module'].get('requestPermissions') != expected:
        raise ValueError('blink probe must request exactly its role permissions')
    permissions = list(PERMISSIONS) if role == 'system' else []
    profile['bundle-info']['bundle-name'] = BUNDLE
    profile['bundle-info']['apl'] = 'normal' if role == 'normal' else 'system_core'
    profile['bundle-info']['app-feature'] = 'hos_normal_app' if role == 'normal' else 'hos_system_app'
    profile['debug-info']['device-ids'] = [udid]
    profile['acls']['allowed-acls'] = permissions
    profile['permissions']['restricted-permissions'] = permissions
    return profile


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('signer-dist', 'jar', 'unsigned', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--udid', required=True)
    sign(parser.parse_args(), configure=configure_profile)
