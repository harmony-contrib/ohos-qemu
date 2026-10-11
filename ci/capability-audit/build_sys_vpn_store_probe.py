#!/usr/bin/env python3
"""Build the actual SDK three-variant system VPN store caller, not a tunnel."""
import argparse
import os
from pathlib import Path
import re
from build_always_on_vpn_probe import BUNDLE, PERMISSION, ROLES, module, build_application

TEMPLATE = Path(__file__).with_name('sys_vpn_store_probe.ets')
SCOPE = 'real_three_variant_VPN_CRUD_prefix_replacement_and_caller_restart_NOT_tunnel'


def page(run_id, role):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or role not in ROLES:
        raise ValueError('fresh nonce and exact system VPN role required')
    return TEMPLATE.read_text().replace('__SYSVPN_RUN__', run_id).replace('__SYSVPN_ROLE__', role)


def build(args):
    return build_application(args, page(args.run_id, args.role), TEMPLATE,
                             'sys-vpn-store-probe-inputs.json', SCOPE, '@ohos.net.vpn.d.ts')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    build(parser.parse_args())
