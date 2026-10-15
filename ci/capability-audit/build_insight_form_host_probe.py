#!/usr/bin/env python3
"""Build the isolated actual form-host caller, not a form creation claim."""
import argparse
import os
from pathlib import Path
import re
from build_always_on_vpn_probe import build_application, module as base_module
from run_root_probe import digest

BUNDLE = 'org.harmonycontrib.insightformhostaudit'
ROLES = ('normal', 'system-denied', 'system')
PERMISSIONS = ('ohos.permission.REQUIRE_FORM', 'ohos.permission.GET_BUNDLE_INFO_PRIVILEGED')
TEMPLATE = Path(__file__).with_name('insight_form_host_probe.ets')
SCOPE = 'candidate_real_form_service_lifecycle_NOT_guest_or_complete_gate'
COMPONENT_DECLARATION = 'ets/component/form_component.d.ts'
COMPONENT_SHA256 = '2810366b9d7386bbc41ca39593805dd2c7c0195fc0187ca729fc9ec0bb9c308d'
LOADER_DECLARATION = 'ets/build-tools/ets-loader/declarations/form_component.d.ts'


def module(role, compiled=False):
    if role not in ROLES:
        raise ValueError('exact form caller role required')
    value = base_module(role, compiled)
    if compiled:
        value['app']['bundleName'] = BUNDLE
    value['module']['requestPermissions'] = [{'name': name} for name in PERMISSIONS] if role == 'system' else []
    return value


def page(run_id, role):
    if re.fullmatch('[a-f0-9]{32}', run_id or '') is None or role not in ROLES:
        raise ValueError('fresh form nonce and exact caller role required')
    return TEMPLATE.read_text().replace('__RUN__', run_id).replace('__ROLE__', role)


def build(args):
    declaration = args.sdk / COMPONENT_DECLARATION
    if declaration.is_symlink() or not declaration.is_file() or digest(declaration) != COMPONENT_SHA256:
        raise ValueError('unchanged pinned API26 system FormComponent declaration required')
    loader = args.sdk / LOADER_DECLARATION
    prepared = declaration.read_bytes().replace(b"import('../api/", b"import('../../../api/")
    if loader.is_symlink() or not loader.is_file() or loader.read_bytes() != prepared:
        raise ValueError('actual loader FormComponent declaration must differ only in its two SDK import paths')
    return build_application(args, page(args.run_id, args.role), TEMPLATE,
        'insight-form-host-probe-inputs.json', SCOPE, '@ohos.app.form.formHost.d.ts',
        module_factory=module, bundle_name=BUNDLE,
        additional_sdk_declarations=(COMPONENT_DECLARATION, LOADER_DECLARATION))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--role', choices=ROLES, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    args = parser.parse_args()
    build(args)
