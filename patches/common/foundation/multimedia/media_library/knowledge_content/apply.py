#!/usr/bin/env python3
"""Apply one completely known KnowledgeContent state; preserve CRLF and fail on partial edits."""
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
spec=importlib.util.spec_from_file_location('knowledge_content_transforms',HERE/'transforms.py')
transforms=importlib.util.module_from_spec(spec)
spec.loader.exec_module(transforms)
MANIFEST=json.loads((HERE/'manifest.json').read_text())


def sha(data):return hashlib.sha256(data).hexdigest()


def path_for(root,name):
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('unsafe KnowledgeContent target')
    path=root/transforms.PROJECT/name
    for cursor in (path,*path.parents):
        if cursor==root:break
        if cursor.is_symlink():raise ValueError('linked KnowledgeContent target: '+name)
    return path


def validate(root,require_patched=False):
    root=Path(root).resolve();project=root/transforms.PROJECT
    if (project/'.git').exists():
        actual=subprocess.check_output(['git','-C',str(project),'rev-parse','HEAD'],text=True).strip()
        if actual!=MANIFEST['revision']:raise ValueError('KnowledgeContent requires fixed media_library revision')
    states=[]
    for name,entry in MANIFEST['files'].items():
        path=path_for(root,name)
        if not path.exists():
            if entry['before'] is not None:raise ValueError('missing pinned KnowledgeContent hook: '+name)
            states.append(False);continue
        if not path.is_file():raise ValueError('regular KnowledgeContent file required: '+name)
        value=sha(path.read_bytes())
        if value==entry['after']:states.append(True)
        elif value==entry['before']:states.append(False)
        else:raise ValueError('unknown KnowledgeContent changes; preserving source: '+name)
    if len(set(states))!=1 or (require_patched and not all(states)):
        raise ValueError('partial KnowledgeContent component; preserving source')
    return all(states)


def run(root):
    root=Path(root).resolve()
    if validate(root):return
    marker=root/'.ohos-qemu-patches'
    if marker.is_symlink():raise ValueError('linked KnowledgeContent lock directory')
    marker.mkdir(exist_ok=True)
    descriptor=os.open(marker/'knowledge-content.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if validate(root):return
        outputs={};snapshots={}
        for name,entry in MANIFEST['files'].items():
            path=path_for(root,name)
            original=path.read_bytes() if path.exists() else None
            snapshots[name]=original
            if name in transforms.FILES:
                data=(HERE/'files'/transforms.FILES[name]).read_bytes()
            else:data=transforms.repair(name,original)
            if sha(data)!=entry['after']:raise ValueError('KnowledgeContent payload differs from manifest: '+name)
            outputs[name]=data
        for name,original in snapshots.items():
            path=path_for(root,name)
            if (path.read_bytes() if path.exists() else None)!=original:
                raise ValueError('KnowledgeContent source changed during preparation')
        for name,data in outputs.items():
            path=path_for(root,name);path.parent.mkdir(parents=True,exist_ok=True)
            mode=(path.stat().st_mode&0o777) if path.exists() else 0o644
            descriptor,temporary=tempfile.mkstemp(prefix='.knowledge-content-',dir=path.parent)
            try:
                with os.fdopen(descriptor,'wb') as target:target.write(data)
                os.chmod(temporary,mode);os.replace(temporary,path)
            finally:
                if os.path.exists(temporary):os.unlink(temporary)
    validate(root,True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    args=parser.parse_args();run(args.source_root)
    print('verified complete KnowledgeContent component')
