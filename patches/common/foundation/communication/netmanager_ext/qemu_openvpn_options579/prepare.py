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
        observed={name:hashlib.sha256(target(root,name).read_bytes()).hexdigest() for name in value['files']}
        if observed=={name:pair[1] for name,pair in value['files'].items()}:
            reverse=dict(value,files={name:list(reversed(pair)) for name,pair in value['files'].items()})
            apply(root,HERE,reverse,reverse=True)
        elif any(observed[name]==pair[1] for name,pair in value['files'].items()):
            raise ValueError('mixed new native options vector cannot be rewound')
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
