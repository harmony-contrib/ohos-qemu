#!/usr/bin/env python3
"""Compile both full native RPC interface-base TUs with real product commands."""
import argparse
import json
from pathlib import Path

from compile_contact_sync_mode import ROOT, PRODUCTS, run

FILES = {
    'proxy': (
        'foundation/communication/ipc/ipc/native/src/napi/src/napi_remote_proxy.cpp',
        'obj/foundation/communication/ipc/ipc/native/src/napi/src/rpc/napi_remote_proxy.o'),
    'error': (
        'foundation/communication/ipc/ipc/native/src/napi_common/source/napi_rpc_error.cpp',
        'obj/foundation/communication/ipc/ipc/native/src/napi_common/source/ipc_napi/napi_rpc_error.o'),
    'holder': (
        'foundation/communication/ipc/ipc/native/src/napi_common/source/napi_remote_object.cpp',
        'obj/foundation/communication/ipc/ipc/native/src/napi_common/source/ipc_napi/napi_remote_object.o'),
    'module': (
        'foundation/communication/ipc/ipc/native/src/napi/src/napi_rpc_native_module.cpp',
        'obj/foundation/communication/ipc/ipc/native/src/napi/src/rpc/napi_rpc_native_module.o'),
}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    parser.add_argument('--tu', choices=FILES, required=True)
    args = parser.parse_args()
    source, target = FILES[args.tu]
    result = run(args, component=ROOT / 'patches/common/foundation/communication/ipc/remote_interface_base',
        source_file=Path(source), target=target, caller=__file__,
        overlay_component_headers=args.tu in ('holder', 'proxy'))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
