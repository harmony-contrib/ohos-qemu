#!/usr/bin/env python3
"""Build isolated real page/link intent callers with exact API26 permissions."""
import argparse
import os
from pathlib import Path
import re
from build_always_on_vpn_probe import build_application, module as base_module
from build_insight_driver_probe import PERMISSIONS, ROLES

BUNDLE = 'org.harmonycontrib.insightnavigationaudit'
TEMPLATE = Path(__file__).with_name('insight_navigation_probe.ets')
SCOPE = 'candidate_actual_decorated_page_and_link_navigation_NOT_guest_or_complete_gate'


def module(role, compiled=False):
    if role not in ROLES:
        raise ValueError('exact navigation caller role required')
    value = base_module(role, compiled)
    if compiled:
        value['app']['bundleName'] = BUNDLE
    value['module']['requestPermissions'] = [{'name': name} for name in PERMISSIONS] if role == 'system' else []
    return value


def page(run_id, role, target_nonce):
    if (re.fullmatch('[a-f0-9]{32}', run_id or '') is None or role not in ROLES or
            re.fullmatch('[a-f0-9]{32}', target_nonce or '') is None):
        raise ValueError('fresh navigation nonce and exact caller role required')
    return TEMPLATE.read_text().replace('__RUN__', run_id).replace('__ROLE__', role).replace('__TARGET_RUN__', target_nonce)


def build(args):
    return build_application(args, page(args.run_id, args.role, args.target_run_id), TEMPLATE,
        'insight-navigation-probe-inputs.json', SCOPE, '@ohos.app.ability.insightIntentDriver.d.ts',
        module_factory=module, bundle_name=BUNDLE)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--target-run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    build(parser.parse_args())
