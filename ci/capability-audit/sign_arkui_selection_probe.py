#!/usr/bin/env python3
"""Sign exact selection roles, keeping every role an ordinary application."""
import argparse
from pathlib import Path
import re
from build_arkui_selection_probe import BUNDLE, ROLES, PERMISSION, module as expected_module
from sign_certificate_probe import sign


def configure_profile(profile,role,udid,module):
    if role not in ROLES or re.fullmatch('[a-fA-F0-9]{64}',udid or '') is None:
        raise ValueError('exact selection role and actual guest UDID required')
    requested=module['module'].get('requestPermissions')
    if role=='reader':
        if (not isinstance(requested,list) or len(requested)!=1 or
                set(requested[0])!={'name','reason','reasonId','usedScene'} or
                type(requested[0]['reasonId']) is not int or requested[0]['reasonId']<=0):
            raise ValueError('actual compiled user-grant permission resource identity required')
        requested=[{key:value for key,value in requested[0].items() if key!='reasonId'}]
    if module['app'].get('bundleName')!=BUNDLE or requested!=expected_module(role)['module']['requestPermissions']:
        raise ValueError('exact selection request permission set required')
    permissions=[PERMISSION] if role=='reader' else []
    profile['bundle-info']['bundle-name']=BUNDLE
    profile['bundle-info']['apl']='normal' if role=='normal' else 'system_basic'
    profile['bundle-info']['app-feature']='hos_normal_app'
    profile['debug-info']['device-ids']=[udid]
    profile['acls']['allowed-acls']=permissions
    profile['permissions']['restricted-permissions']=permissions
    return profile


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('signer-dist','jar','unsigned','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--role',choices=ROLES,required=True)
    parser.add_argument('--udid',required=True)
    sign(parser.parse_args(),configure_profile)
