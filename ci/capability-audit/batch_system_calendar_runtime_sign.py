#!/usr/bin/env python3
"""Exact QA signing roles. Producer remains normal and empty-ACL."""
import argparse
from pathlib import Path
import re
from batch_system_calendar_runtime_project import ROLES, require
from sign_certificate_probe import sign


def configure(profile, role, udid, module):
    require(role in ROLES and re.fullmatch('[a-fA-F0-9]{64}', udid), 'exact role and actual guest UDID required')
    policy = ROLES[role]
    value = module['module']
    require(module['app']['bundleName'] == policy['bundle'] and
            sorted(p['name'] for p in value.get('requestPermissions', [])) == sorted(policy['permissions']) and
            value.get('extensionAbilities', []) == [] and len(value['abilities']) == 1 and
            value['abilities'][0]['name'] == 'EntryAbility', 'compiled QA role contract differs')
    profile['bundle-info'].update({'bundle-name': policy['bundle'], 'apl': policy['apl'],
        'app-feature': 'hos_system_app' if policy['system_app'] else 'hos_normal_app'})
    profile['debug-info']['device-ids'] = [udid]
    profile['acls']['allowed-acls'] = policy['allowed_acls'][:]
    profile['permissions']['restricted-permissions'] = policy['allowed_acls'][:]
    return profile


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('signer-dist', 'jar', 'unsigned', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--udid', required=True)
    sign(parser.parse_args(), configure)
