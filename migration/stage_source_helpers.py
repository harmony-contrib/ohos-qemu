#!/usr/bin/env python3
"""Stage tracked source-preparation helpers beside their owning component recipes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--catalog',type=Path,required=True)
    ap.add_argument('--owners',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--index',type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():raise ValueError('Fresh source-helper candidate directory required')
    projects={r['name']:r for r in json.loads(args.catalog.read_text())['repositories']}
    owners=json.loads(args.owners.read_text())['files']
    index=json.loads(args.index.read_text());existing={r['path'] for r in index['files']}
    tracked={}
    for record in subprocess.check_output(['git','ls-files','--stage','-z','scripts']).decode().split('\0'):
        if not record:continue
        meta,name=record.split('\t');mode,oid,stage=meta.split()
        if stage!='0':raise ValueError('Unmerged source helper: '+name)
        tracked[name]=(mode,oid)
    staged={}
    for name,owner in owners.items():
        if owner not in projects or name not in tracked or name in existing:
            raise ValueError('Missing owner, untracked file or duplicate recipe: '+name)
        data=Path(name).read_bytes();mode,oid=tracked[name]
        if hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=oid:
            raise ValueError('Source helper has unreviewed worktree edits: '+name)
        target='.qemu/adaptations/'+name
        dest=args.output/owner/'files'/target;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        sha=hashlib.sha256(data).hexdigest()
        staged.setdefault(owner,[]).append(dict(path=target,sha256=sha,mode=oct(int(mode,8)&0o777)))
        index['files'].append(dict(path=name,mode=mode,sha256=sha,original_git_blob=oid,
            parts=[dict(repository=owner,path=target,sha256=sha)]))
        index['repositories'][owner]=projects[owner]['inputs']
    for owner,files in staged.items():
        revisions={i['revision'] for i in projects[owner]['inputs']}
        if len(revisions)!=1:raise ValueError('Ambiguous baseline '+owner)
        root=args.output/owner
        (root/'tracked.patch').write_bytes(b'')
        (root/'export.json').write_text(json.dumps(dict(name=owner,upstream_revision=next(iter(revisions)),
            tracked=[],added=files,omitted=[],scope='component_owned_source_helpers_NOT_build_or_runtime_validation'),indent=2)+'\n')
    args.index.write_text(json.dumps(index,indent=2)+'\n')
    print(f'Staged {len(owners)} source helper files into {len(staged)} component repositories')


if __name__=='__main__':main()
