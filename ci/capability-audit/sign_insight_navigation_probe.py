#!/usr/bin/env python3
"""Sign only the isolated navigation caller's exact identity and intent ACLs."""
import argparse
from pathlib import Path
import re
from build_insight_navigation_probe import BUNDLE, PERMISSIONS, ROLES, module as expected_module
from sign_certificate_probe import sign


def configure_profile(profile, role, udid, module):
    if role not in ROLES or re.fullmatch('[a-fA-F0-9]{64}', udid or '') is None:
        raise ValueError('exact navigation role and actual guest UDID required')
    if (module['app'].get('bundleName') != BUNDLE or
            module['module'].get('requestPermissions') != expected_module(role)['module']['requestPermissions']):
        raise ValueError('navigation caller identity or permission set differs')
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
