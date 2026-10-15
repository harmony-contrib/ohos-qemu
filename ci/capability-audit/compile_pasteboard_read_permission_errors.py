#!/usr/bin/env python3
"""Compile the complete repaired NAPI TU using all three actual product commands."""
import argparse
import json
from pathlib import Path
from compile_contact_sync_mode import ROOT, PRODUCTS, run

COMPONENT = ROOT/'patches/common/foundation/distributeddatamgr/pasteboard/read_permission_errors'
SOURCE = Path('foundation/distributeddatamgr/pasteboard/interfaces/kits/napi/src/napi_systempasteboard.cpp')
TARGET = 'obj/foundation/distributeddatamgr/pasteboard/interfaces/kits/napi/src/pasteboard_napi/napi_systempasteboard.o'


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--product',choices=PRODUCTS,action='append')
    args = parser.parse_args()
    report = run(args,component=COMPONENT,source_file=SOURCE,target=TARGET,caller=__file__,
                 prepare_component_idl=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],objects_count=report['objects_count'])))
