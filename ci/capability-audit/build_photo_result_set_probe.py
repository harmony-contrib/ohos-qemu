#!/usr/bin/env python3
"""Typed actual photo query factory, three bounded caller roles; no DB writes."""
import argparse
import json
import os
from pathlib import Path
import re

from build_always_on_vpn_probe import BUNDLE, ROLES, build_application, module as base_module
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('photo_result_set_probe.ets')
DECLARATION = '@ohos.file.photoAccessHelper.d.ts'
PERMISSION = 'ohos.permission.ACCESS_MEDIALIB_THUMB_DB'
SCOPE = 'real_photo_query_ResultSet_readonly_typed_values_cursors_errors_and_three_permission_roles'


def module(role, compiled=False):
    value = base_module(role, compiled)
    value['module']['requestPermissions'] = [{'name': PERMISSION}] if role == 'system' else []
    return value


def page(run_id, role):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or role not in ROLES:
        raise ValueError('fresh nonce and exact photo query role required')
    return TEMPLATE.read_text().replace('__RESULT_SET_RUN__', run_id).replace('__RESULT_SET_ROLE__', role)


def build(args):
    build_application(args, page(args.run_id, args.role), TEMPLATE,
        'photo-result-set-probe-inputs.json', SCOPE, DECLARATION, module_factory=module)
    receipt = args.output.resolve() / 'photo-result-set-probe-inputs.json'
    value = json.loads(receipt.read_text())
    value['module_sha256'] = digest(args.output / 'entry/src/main/module.json5')
    value['builder_sha256'] = digest(Path(__file__))
    value['shared_builder_sha256'] = digest(Path(__file__).with_name('build_always_on_vpn_probe.py'))
    receipt.write_text(json.dumps(value, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    build(parser.parse_args())
