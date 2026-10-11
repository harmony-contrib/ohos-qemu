#!/usr/bin/env python3
"""Sign the bounded three-role VPN policy test; never alter image permissions."""
import argparse
from pathlib import Path
import re

from build_always_on_vpn_probe import BUNDLE, PERMISSION, ROLES
from sign_certificate_probe import sign


def configure_profile(profile, role, udid, module):
    if role not in ROLES or re.fullmatch('[0-9a-fA-F]{64}', udid) is None:
        raise ValueError('explicit VPN role and actual guest UDID required')
    expected = [{'name': PERMISSION}] if role == 'system' else []
    if module['app'].get('bundleName') != BUNDLE or module['module'].get('requestPermissions') != expected:
        raise ValueError('VPN probe must request exactly its own role permissions')
    profile['bundle-info']['bundle-name'] = BUNDLE
    profile['bundle-info']['apl'] = 'normal' if role == 'normal' else 'system_core'
    profile['bundle-info']['app-feature'] = 'hos_normal_app' if role == 'normal' else 'hos_system_app'
    profile['debug-info']['device-ids'] = [udid]
    profile['acls']['allowed-acls'] = [PERMISSION] if role == 'system' else []
    profile['permissions']['restricted-permissions'] = [PERMISSION] if role == 'system' else []
    return profile


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('signer-dist', 'jar', 'unsigned', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--udid', required=True)
    sign(parser.parse_args(), configure=configure_profile)
