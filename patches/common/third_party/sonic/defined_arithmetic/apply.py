#!/usr/bin/env python3
"""Apply the fixed Sonic defined arithmetic repair before the audio queue component."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import re
import stat

HERE=Path(__file__).resolve().parent
MANIFEST_SHA='0d171169972dfa9e5c32fd49e7bb5a6a3d7d6819039f5771025ec691b724b83f'


def require(value,message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def regular(path):
    require(path.is_absolute() and path.resolve()==path and
            not any(p.is_symlink() for p in (path,*path.parents)), 'canonical non-alias path required')
    s=path.stat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink==1,'single regular source required')
    return path.read_bytes()


def read_manifest():
    raw=regular(HERE/'manifest.json')
    require(digest(raw)==MANIFEST_SHA,'sonic-defined-arithmetic manifest changed')
    manifest=json.loads(raw)
    require(manifest['schema']=='sonic-defined-arithmetic536/v1','exact sonic-defined-arithmetic schema required')
    patch=regular(HERE/'defined_arithmetic.patch')
    require(digest(patch)==manifest['patch_sha256'],'sonic-defined-arithmetic patch changed')
    return manifest,patch


def source_path(root,name):
    p=PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and '.' not in p.parts and str(p)==name,
            'fixed relative source path required')
    return root/name


def transform(original,patch,reverse=False):
    """Strict exact unified hunks, preserving line-ending bytes; no Git/fuzz."""
    lines=patch.splitlines(keepends=True)
    result={};i=0
    while i<len(lines):
        require(lines[i].startswith(b'--- a/'),'exact patch before header required')
        name=lines[i][6:].rstrip(b'\r\n').decode();i+=1
        require(i<len(lines) and lines[i]==b'+++ b/'+name.encode()+b'\n','exact patch after header required')
        i+=1;require(name in original and name not in result,'exact unique managed patch source required')
        src=original[name].splitlines(keepends=True);out=[];cursor=0;hunks=0
        while i<len(lines) and not lines[i].startswith(b'--- a/'):
            match=re.fullmatch(rb'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\r\n]*\r?\n',lines[i])
            require(match is not None,'exact hunk header required')
            oldstart,oldcount,newstart,newcount=match.groups()
            oldstart=int(oldstart);newstart=int(newstart)
            oldcount=int(oldcount) if oldcount is not None else 1
            newcount=int(newcount) if newcount is not None else 1
            i+=1;before=[];after=[]
            while i<len(lines) and not lines[i].startswith((b'@@ ',b'--- a/')):
                line=lines[i];require(line[:1] in (b' ',b'-',b'+'),'unsupported patch line')
                if line[:1] in (b' ',b'-'):before.append(line[1:])
                if line[:1] in (b' ',b'+'):after.append(line[1:])
                i+=1
            require(len(before)==oldcount and len(after)==newcount,'exact hunk lengths required')
            start=(newstart if reverse else oldstart)-1
            a,b=(after,before) if reverse else (before,after)
            require(start>=cursor and src[start:start+len(a)]==a,'source hunk differs')
            out.extend(src[cursor:start]);out.extend(b);cursor=start+len(a);hunks+=1
        require(hunks>0,'at least one fixed hunk required')
        result[name]=b''.join(out+src[cursor:])
    require(set(result)==set(original),'entire exact managed vector required')
    return result


def preflight(root,require_patched=False):
    require(root.is_absolute() and root.resolve()==root and root.is_dir() and
            not any(p.is_symlink() for p in (root,*root.parents)),'canonical source root required')
    manifest,patch=read_manifest();original={};states=[]
    for name,digest_ in manifest['prerequisites'].items():
        require(digest(regular(source_path(root,name)))==digest_,'readonly Sonic header prerequisite changed: '+name)
    for name,row in manifest['files'].items():
        path=source_path(root,name);raw=regular(path);original[name]=raw;h=digest(raw)
        require(stat.S_IMODE(path.stat().st_mode)==row['mode'],'exact source mode required')
        require(len(raw) in (row['before_bytes'],row['after_bytes']),'exact source length required')
        states.append('before' if h==row['before_sha256'] else 'after' if h==row['after_sha256'] else 'unknown')
    require(len(set(states))==1 and states[0] in ('before','after'),'whole sonic-defined-arithmetic vector required; partial/unknown source rejected')
    state=states[0]
    require(not require_patched or state=='after','complete sonic-defined-arithmetic final state required')
    if state=='before':
        final=transform(original,patch)
        for name,row in manifest['files'].items():
            require(digest(final[name])==row['after_sha256'],'exact sonic-defined-arithmetic result required')
    return state,original,manifest,patch


def apply(root,require_patched=False):
    state,original,manifest,patch=preflight(root,require_patched)
    if require_patched or state=='after':
        return state
    final=transform(original,patch)
    # Parent owns the source lease. Recheck the complete vector before the first
    # mutation; an interrupted/partial install is rejected on the next preflight.
    for name,raw in original.items():
        require(regular(source_path(root,name))==raw,'source changed after preflight')
    for name,raw in final.items():
        path=source_path(root,name)
        with path.open('wb') as stream:
            stream.write(raw)
    preflight(root,True)
    return 'after'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--require-patched',action='store_true')
    parser.add_argument('--preflight',action='store_true')
    parser.add_argument('--product',action='append')
    args=parser.parse_args()
    if args.preflight:
        state=preflight(args.source_root,args.require_patched)[0]
    else:
        state=apply(args.source_root,args.require_patched)
    print(json.dumps(dict(component='sonic-defined-arithmetic536',state=state,hardware_playback_proven=False),sort_keys=True))


if __name__=='__main__':
    main()
