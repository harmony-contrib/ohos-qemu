#!/usr/bin/env python3
"""Compile actual ArkWeb numeric BusinessError repair in all three products."""
import argparse
import json
from pathlib import Path

from compile_ethernet_enum import ROOT, run


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args(),
        component=ROOT / 'patches/common/base/web/webview/business_error',
        project_path=Path('base/web/webview'),
        source_path=Path('base/web/webview/interfaces/kits/napi/common/business_error.cpp'),
        target='obj/base/web/webview/interfaces/kits/napi/common/webview_napi/business_error.o',
        caller=Path(__file__), scope='three_actual_ArkWeb_BusinessError_TU_objects_NOT_link_or_guest')
    print(json.dumps({'status': result['status'], 'objects': len(result['objects']), 'scope': result['scope']}))
