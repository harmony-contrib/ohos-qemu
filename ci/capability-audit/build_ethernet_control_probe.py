#!/usr/bin/env python3
"""Build real API26 Ethernet callers; compiling is not interface/guest proof."""
import argparse
import os
from pathlib import Path
import re
from build_always_on_vpn_probe import BUNDLE, ROLES, build_application, module as base_module

TEMPLATE = Path(__file__).with_name('ethernet_control_probe.ets')
PERMISSIONS = ('ohos.permission.CONNECTIVITY_INTERNAL', 'ohos.permission.GET_NETWORK_INFO')
SCOPE = 'three_role_public_Ethernet_controls_and_readonly_real_kernel_flags_NOT_other_network_APIs'


def module(role, compiled=False):
    value = base_module(role, compiled)
    value['module']['requestPermissions'] = [{'name': name} for name in PERMISSIONS] if role == 'system' else []
    return value


def page(run_id, role):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or role not in ROLES:
        raise ValueError('fresh Ethernet nonce and exact caller role required')
    return TEMPLATE.read_text().replace('__ETHERNET_RUN__', run_id).replace('__ETHERNET_ROLE__', role)


def build(args):
    return build_application(args, page(args.run_id, args.role), TEMPLATE,
        'ethernet-control-probe-inputs.json', SCOPE, '@ohos.net.ethernet.d.ts', module_factory=module)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    build(parser.parse_args())
