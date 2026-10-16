#!/usr/bin/env python3
"""Apply one completely known capture loopback state; preserve CRLF and fail on partial edits."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
MANIFEST=json.loads((HERE/'manifest.json').read_text())


def sha(data):return hashlib.sha256(data).hexdigest()


def path_for(root,name):
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('unsafe capture loopback target')
    path=root/name
    for cursor in (path,*path.parents):
        if cursor==root:break
        if cursor.is_symlink():raise ValueError('linked capture loopback target: '+name)
    return path


def validate(root,require_patched=False):
    root=Path(root).resolve()
    for name,revision in MANIFEST['projects'].items():
        project=root/name
        if (project/'.git').exists():
            actual=subprocess.check_output(['git','-C',str(project),'rev-parse','HEAD'],text=True).strip()
            if actual!=revision:raise ValueError('capture loopback requires fixed project revision: '+name)
    states=[]
    for name,entry in MANIFEST['files'].items():
        path=path_for(root,name)
        if not path.exists():
            if entry['before'] is not None:raise ValueError('missing pinned capture loopback hook: '+name)
            states.append(False);continue
        if not path.is_file():raise ValueError('regular capture loopback file required: '+name)
        value=sha(path.read_bytes())
        if value==entry['after']:states.append(True)
        elif value==entry['before']:states.append(False)
        else:raise ValueError('unknown capture loopback changes; preserving source: '+name)
    if len(set(states))!=1 or (require_patched and not all(states)):
        raise ValueError('partial capture loopback component; preserving source')
    return all(states)


def run(root):
    root=Path(root).resolve()
    if validate(root):return
    marker=root/'.ohos-qemu-patches'
    if marker.is_symlink():raise ValueError('linked capture loopback lock directory')
    marker.mkdir(exist_ok=True)
    descriptor=os.open(marker/'capture-loopback.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if validate(root):return
        outputs={};snapshots={}
        for name,entry in MANIFEST['files'].items():
            path=path_for(root,name)
            original=path.read_bytes() if path.exists() else None
            snapshots[name]=original
            data=(HERE/'files'/entry['payload']).read_bytes()
            if sha(data)!=entry['after']:raise ValueError('capture loopback payload differs from manifest: '+name)
            outputs[name]=data
        for name,original in snapshots.items():
            path=path_for(root,name)
            if (path.read_bytes() if path.exists() else None)!=original:
                raise ValueError('capture loopback source changed during preparation')
        for name,data in outputs.items():
            path=path_for(root,name);path.parent.mkdir(parents=True,exist_ok=True)
            mode=(path.stat().st_mode&0o777) if path.exists() else 0o644
            descriptor,temporary=tempfile.mkstemp(prefix='.capture-loopback-',dir=path.parent)
            try:
                with os.fdopen(descriptor,'wb') as target:target.write(data)
                os.chmod(temporary,mode);os.replace(temporary,path)
            finally:
                if os.path.exists(temporary):os.unlink(temporary)
    validate(root,True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--require-patched',action='store_true')
    parser.add_argument('--product')
    args=parser.parse_args()
    if args.require_patched:validate(args.source_root,True)
    else:run(args.source_root)
    print('verified complete capture loopback component')
