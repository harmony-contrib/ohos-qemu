#!/usr/bin/env python3
"""Exact seven-source transaction after the ORIGINAL backend installer.

Prefix rewind may leave a pristine/other old prefix for its original guards;
it never admits that state. Forward and package require the full final vector,
actual two project HEADs and all normal staged QEMU payload/recipe identities.
"""
import argparse
import fcntl
import os
import stat
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[5]/'lib'))
from guarded_source_vector579 import load,heads,vector,target,apply

HERE=Path(__file__).resolve().parent

# Complete installed C28 epoch; never accepted by forward/final/readonly.
PREVIOUS_PROJECTS = {'foundation/communication/netmanager_ext': '8c41289750820fb2ddb347b1205cee9a7b527388', 'foundation/communication/netmanager_base': '9831989d54f490d046a632ab13d309580d2fa710'}
PREVIOUS_FILES = {
    'foundation/communication/netmanager_base/services/netmanagernative/include/manager/multi_vpn_manager.h': ['33f2563d6bdcdf76f1b1bf4c99eb0f088a47a23079a4711c0312c33133a82095', '9ca73304629ca1ffa916e48b0e8a07ee10e279ca60213348fb147092b362a52f'],
    'foundation/communication/netmanager_base/services/netmanagernative/include/manager/route_manager.h': ['269ab9cd1907eef43e330ae30b57180b8d101ce52051089aa98b84fbdfed4054', '41f39b3a5b5f1f82efa0a6505d30662d6617d617251b82daa30f57fce00c9836'],
    'foundation/communication/netmanager_base/services/netmanagernative/src/manager/multi_vpn_manager.cpp': ['d3de1f59d3de45305d92a605e800e07b8c584e70a7d3800d66c3ee737231346d', 'ff4c5f272205eb1983c1c926a65ea73ceece537e253040ba6e8e435121f13d70'],
    'foundation/communication/netmanager_base/services/netmanagernative/src/manager/route_manager.cpp': ['d565bb4b42bcbbaa30720104bf92b0c95514636cf6c0a08373ddf46791c2c98e', 'e766263b2d5ad09169f49e42d73910cb2dc44d78a9dd14c2122edde777de1f54'],
    'foundation/communication/netmanager_base/services/netmanagernative/src/netsys/system_vpn_wrapper.cpp': ['54d3eb71cb6ca158d027d92a4b31ce43802dd0b2a214e9b02f9baac5c4a14943', 'a88b0655cef6d293be379c46b7d13de61f3ff0ac87e6dfb006e2b2835d544319'],
    'foundation/communication/netmanager_ext/services/vpnmanager/include/open_vpn_ctl.h': ['2338830aa4b631a95a85e2ee1d71e9b49f275622153ae68a8eea5e9eaab6304d', 'ee486831b14c0bfb7a0c6892cbfc0e732a1886ca68bb2e79b4cb022f325deadc'],
    'foundation/communication/netmanager_ext/services/vpnmanager/src/open_vpn_ctl.cpp': ['145584763fb092e40c77242bb75281842bd6be0f105fb1381fc56d551dbf9b78', '10476997dca7b0d6b11ab71a99322f62f45367560b08cf127ad20889799eca47'],
}
PREVIOUS_PATCH = 'legacy/previous-c28-product-source.patch'
PREVIOUS_PATCH_SHA256 = '0d5b8c808670787ed55a8aaf4785dc251ef7f3436558304329a02826c85afd5f'

def payloads(root):
    value=json.loads((HERE/'staged_inputs.json').read_text())
    if value['schema']!='qemu-openvpn-options579-normal-staged-inputs/v1' or len(value['payloads'])!=10 or len(value['recipes'])!=3:
        raise ValueError('complete fixed normal QEMU payload/recipe vector')
    for name,digest in {**value['payloads'],**value['recipes']}.items():
        if hashlib.sha256(target(root,name).read_bytes()).hexdigest()!=digest:
            raise ValueError('normal staged backend source differs: '+name)

def _prepare(root,*,rewind=False,require_final=False):
    value=load(HERE)
    if len(value['files'])!=7:raise ValueError('complete fixed seven-source native options transaction')
    heads(root,value)
    if rewind:
        if (value['projects']!=PREVIOUS_PROJECTS or set(value['files'])!=set(PREVIOUS_FILES) or
            any(value['files'][name][0]!=pair[0] for name,pair in PREVIOUS_FILES.items())):
            raise ValueError('fixed complete options epochs must share the original projects/before7')
        observed={name:hashlib.sha256(target(root,name).read_bytes()).hexdigest() for name in value['files']}
        current_final={name:pair[1] for name,pair in value['files'].items()}
        previous_final={name:pair[1] for name,pair in PREVIOUS_FILES.items()}
        if observed==current_final:
            reverse=dict(value,files={name:list(reversed(pair)) for name,pair in value['files'].items()})
            apply(root,HERE,reverse,reverse=True)
        elif observed==previous_final:
            patch=HERE/PREVIOUS_PATCH
            if (patch.is_symlink() or patch.parent.is_symlink() or not patch.is_file() or
                hashlib.sha256(patch.read_bytes()).hexdigest()!=PREVIOUS_PATCH_SHA256):
                raise ValueError('fixed complete previous options patch differs')
            reverse=dict(value,files={name:list(reversed(pair)) for name,pair in PREVIOUS_FILES.items()})
            apply(root,HERE,reverse,reverse=True,patch_name=PREVIOUS_PATCH)
        elif any(observed[name] in (current_final[name],previous_final[name]) for name in value['files']):
            raise ValueError('mixed/unknown installed native options epochs cannot be rewound')
        # This is deliberately NOT source acceptance. Original normal hooks
        # still check every ancestor; forward below requires exact RO13 before.
        return
    payloads(root)
    if require_final:
        if vector(root,value)!='final':raise ValueError('complete final native options vector required')
        return
    apply(root,HERE,value)
    payloads(root)
    if vector(root,value)!='final':raise ValueError('final options transaction differs')

@contextmanager
def locked(root,readonly):
    marker=root/'.ohos-qemu-patches'
    if marker.is_symlink():raise ValueError('linked source lock directory')
    if not readonly:marker.mkdir(exist_ok=True)
    if not marker.is_dir():raise ValueError('normal preparation source lock missing')
    path=marker/'qemu-openvpn-options579.lock'
    flags=os.O_RDONLY if readonly else os.O_RDWR|os.O_CREAT
    fd=os.open(path,flags|os.O_NOFOLLOW,0o600)
    try:
        state=os.fstat(fd)
        if not stat.S_ISREG(state.st_mode) or state.st_nlink!=1 or stat.S_IMODE(state.st_mode)!=0o600 or state.st_uid!=os.geteuid():
            raise ValueError('unknown component lock inode/owner/mode')
        fcntl.flock(fd,fcntl.LOCK_SH if readonly else fcntl.LOCK_EX)
        named=path.stat(follow_symlinks=False)
        if (named.st_dev,named.st_ino)!=(state.st_dev,state.st_ino):raise ValueError('component lock replaced')
        yield
    finally:os.close(fd)

def prepare(root,*,rewind=False,require_final=False):
    with locked(root,require_final):_prepare(root,rewind=rewind,require_final=require_final)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--rewind',action='store_true');mode.add_argument('--require-final',action='store_true')
    args=parser.parse_args();prepare(args.source_root.resolve(),rewind=args.rewind,require_final=args.require_final)
    print('Native VPN option source preparation only; new QEMU acceptance remains pending')
