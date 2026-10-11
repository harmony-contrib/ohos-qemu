#!/usr/bin/env python3
"""Investigate real API26 abstract RPC type/value lowering, not guest closure."""
import argparse
import os
from pathlib import Path
import re

from build_always_on_vpn_probe import build_application, module as base_module

TEMPLATE = Path(__file__).with_name('rpc_contract_probe.ets')
SCOPE = 'real_API26_RPC_abstract_type_value_compilation_NOT_guest_or_IPC'
CASES = ('typed-object', 'instance-check', 'abstract-subclass', 'abstract-new')


def module(role, compiled=False):
    if role != 'normal':
        raise ValueError('RPC contract caller must remain an ordinary application')
    return base_module(role, compiled)


def page(run_id, case):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None or case not in CASES:
        raise ValueError('fresh nonce and exact RPC compiler case required')
    declaration = ''
    operation = 'this.result = object.getDescriptor() + ":" + String(object.isObjectDead());'
    if case == 'instance-check':
        operation = 'this.result = String(object instanceof rpc.IRemoteObject);'
    elif case == 'abstract-subclass':
        declaration = 'class AuditAbstract extends rpc.IRemoteObject {}'
        operation = 'this.result = new AuditAbstract().getDescriptor();'
    elif case == 'abstract-new':
        operation = 'this.result = new rpc.IRemoteObject().getDescriptor();'
    return (TEMPLATE.read_text().replace('__RPC_RUN__', run_id)
            .replace('__RPC_DECLARATION__', declaration).replace('__RPC_OPERATION__', operation))


def build(args):
    return build_application(args, page(args.run_id, args.case), TEMPLATE,
        'rpc-contract-probe-inputs.json', SCOPE, '@ohos.rpc.d.ts', module_factory=module)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--role', choices=('normal',), default='normal')
    parser.add_argument('--case', choices=CASES, default='typed-object')
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    build(parser.parse_args())
