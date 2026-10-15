#!/usr/bin/env python3
"""Build a real three-role intent lookup/execution candidate, not a guest gate."""
import argparse
import os
from pathlib import Path
import re
from build_always_on_vpn_probe import build_application, module as base_module

BUNDLE = 'org.harmonycontrib.insightdriveraudit'
TARGET_BUNDLE = 'org.harmonycontrib.capabilityaudit'
ROLES = ('normal', 'system-denied', 'system')
PERMISSIONS = ('ohos.permission.GET_BUNDLE_INFO_PRIVILEGED',
               'ohos.permission.EXECUTE_INSIGHT_INTENT',
               'ohos.permission.ABILITY_BACKGROUND_COMMUNICATION')
TEMPLATE = Path(__file__).with_name('insight_driver_probe.ets')
SCOPE = 'candidate_typed_BMS_decorated_intent_lookup_and_execution_NOT_guest_or_complete_gate'


def module(role, compiled=False):
    if role not in ROLES:
        raise ValueError('exact intent caller role required')
    value = base_module(role, compiled)
    if compiled:
        value['app']['bundleName'] = BUNDLE
    body = value['module']
    body['requestPermissions'] = [{'name': name} for name in PERMISSIONS] if role == 'system' else []
    return value


def page(run_id, role):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or role not in ROLES:
        raise ValueError('fresh intent nonce and exact caller role required')
    return TEMPLATE.read_text().replace('__RUN__', run_id).replace('__ROLE__', role)


def build(args):
    return build_application(args, page(args.run_id, args.role), TEMPLATE,
        'insight-driver-probe-inputs.json', SCOPE, '@ohos.app.ability.insightIntentDriver.d.ts',
        module_factory=module, bundle_name=BUNDLE)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    build(parser.parse_args())
