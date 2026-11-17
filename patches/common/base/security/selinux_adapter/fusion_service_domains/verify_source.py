#!/usr/bin/env python3
"""Require fixed policy source and complete dedicated Fusion identity files."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from exact_source_states import validate_component

PROJECT='base/security/selinux_adapter'
REVISION='cfc1d5b31a7438dbc87763f9222f00337221cf21'
PREFIX='sepolicy/ohos_policy/communication/fusion_connectivity/'
FILES=(
    (PREFIX+'public/type.te','a1e9f618efdc04ab344bef9de23c4ce047fe2adabf7ba991db61f12374004b30',
     'fe60242147c91fda196d61da060f9d8a4509bb9d9f59296993721b549293c372'),
    (PREFIX+'public/service.te',None,'241c5c0842821efd529031d700a7402094d57a536c87286b267482fd7e86f0be'),
    (PREFIX+'public/service_contexts',None,'3afbb858aa293d00d4c9ea8da14324074c073f40076dadd4f9bb25599b77df4d'),
    (PREFIX+'system/fusion_services.te',None,'a47e5238776d198eea67d0a450ac9bb3f25191c56b8b07c9e96b7d2d4a09ffcd'),
)

def validate(root,require_patched=False):
    return validate_component(root,PROJECT,REVISION,FILES,require_patched)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--require-patched',action='store_true')
    args=parser.parse_args()
    print('Dedicated Fusion service policy: '+str(validate(args.source_root,args.require_patched)))
