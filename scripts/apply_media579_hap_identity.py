#!/usr/bin/env python3
"""Restore real full-token HAP system identity checks in normal product source.

Only the two unconditional root-build HAP bypasses are removed. Explicit native,
shell and UID_ROOT special cases remain. No binary/image/runtime mutation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
TARGET='foundation/multimedia/audio_framework/frameworks/native/audioutils/src/audio_utils.cpp'
BEFORE='23bfe111fe1847d63b0c8f0c25f73e610bbf2144e59bb7ec9f756e4979420c96'
AFTER='c34d1afa07b1e5897113db8a114ff6b2216d5e726e6afde8fbdc528ef81f0dd2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def apply(root,receipt):
    target=root.resolve()/TARGET;asset=Path(__file__).resolve().parent/'media579-product/audio_utils.cpp'
    if not target.is_file() or any(p.is_symlink() for p in (target,*target.parents)) or sha(asset)!=AFTER:
        raise ValueError('exact regular actual audio permission source/asset required')
    current=sha(target)
    if current not in (BEFORE,AFTER):raise ValueError('foreign complete audio permission source preimage')
    if current==BEFORE:
        temporary=target.with_name(target.name+'.media579.tmp')
        with temporary.open('xb') as f:f.write(asset.read_bytes());f.flush();os.fsync(f.fileno())
        temporary.chmod(target.stat().st_mode&0o777);os.replace(temporary,target)
    if sha(target)!=AFTER:raise ValueError('actual full-token HAP source write mismatch')
    receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps(dict(schema='media579-normal-source-HAP-identity-apply/v1',path=TARGET,before=BEFORE,after=AFTER,was_already_applied=current==AFTER,source_only=True),indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();apply(a.source_root,a.receipt)
