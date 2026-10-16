#!/usr/bin/env python3
"""Apply one completely known knowledge calendar state; preserve CRLF and fail on partial edits."""
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
spec=importlib.util.spec_from_file_location('knowledge_calendar_transforms',HERE/'transforms.py')
transforms=importlib.util.module_from_spec(spec)
spec.loader.exec_module(transforms)
MANIFEST=json.loads((HERE/'manifest.json').read_text())


def sha(data):return hashlib.sha256(data).hexdigest()


def path_for(root,name):
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('unsafe knowledge calendar target')
    path=root/name
    for cursor in (path,*path.parents):
        if cursor==root:break
        if cursor.is_symlink():raise ValueError('linked knowledge calendar target: '+name)
    return path


def validate(root,require_patched=False):
    root=Path(root).resolve()
    for name,revision in MANIFEST['projects'].items():
        project=root/name
        if (project/'.git').exists():
            actual=subprocess.check_output(['git','-C',str(project),'rev-parse','HEAD'],text=True).strip()
            if actual!=revision:raise ValueError('knowledge calendar requires fixed project revision: '+name)
    actual={}
    for name,entry in MANIFEST['files'].items():
        path=path_for(root,name)
        if path.exists() and not path.is_file():raise ValueError('regular knowledge calendar file required: '+name)
        actual[name]=sha(path.read_bytes()) if path.exists() else None
        if actual[name] not in (entry['before'],entry['after']):
            raise ValueError('unknown knowledge calendar source; preserving edits: '+name)
    if all(actual[name]==entry['after'] for name,entry in MANIFEST['files'].items()):return True
    if not require_patched and all(actual[name]==entry['before'] for name,entry in MANIFEST['files'].items()):return False
    raise ValueError('partial knowledge calendar state; preserving source')


def run(root):
    root=Path(root).resolve()
    if validate(root):return
    marker=root/'.ohos-qemu-patches'
    if marker.is_symlink():raise ValueError('linked knowledge calendar lock directory')
    marker.mkdir(exist_ok=True)
    descriptor=os.open(marker/'knowledge-calendar.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if validate(root):return
        outputs={};snapshots={}
        for name,entry in MANIFEST['files'].items():
            path=path_for(root,name)
            original=path.read_bytes() if path.exists() else None
            snapshots[name]=original
            if 'payload' in entry:data=(HERE/'files'/entry['payload']).read_bytes()
            elif 'transform' in entry:data=transforms.repair(entry['transform'],original)
            else:data=original
            if sha(data)!=entry['after']:raise ValueError('knowledge calendar payload differs from manifest: '+name)
            outputs[name]=data
        for name,original in snapshots.items():
            path=path_for(root,name)
            if (path.read_bytes() if path.exists() else None)!=original:
                raise ValueError('knowledge calendar source changed during preparation')
        for name,data in outputs.items():
            path=path_for(root,name);path.parent.mkdir(parents=True,exist_ok=True)
            mode=(path.stat().st_mode&0o777) if path.exists() else 0o644
            descriptor,temporary=tempfile.mkstemp(prefix='.knowledge-calendar-',dir=path.parent)
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
    print('verified complete knowledge calendar component')
