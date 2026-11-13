#!/usr/bin/env python3
"""Materialize component-owned recipes from a manifest ownership index.

This file is destined for the OHOS build repository. The generated directory is
only a compatibility interface for existing relative imports, never a second
editable source of adaptation logic. No patch, build or package is executed.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile


def relative(value):
    p=PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError('Unsafe relative path: '+value)
    return Path(*p.parts)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def materialize(index, roots, output, payload_root=None):
    manifest=json.loads(index.read_text())
    if manifest['schema_version']!=1:raise ValueError('Unsupported adaptation index')
    destinations=set()
    for entry in manifest['files']:
        destination=relative(entry['path'])
        if str(destination) in destinations:raise ValueError('Duplicate destination')
        destinations.add(str(destination))
        for part in entry['parts']:
            relative(part['path'])
            if part['repository'] not in manifest['repositories']:
                raise ValueError('Unknown recipe owner')
    if output.exists():raise ValueError('Fresh output directory required; preserve prior evidence')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.qemu-recipes-',dir=output.parent) as temporary:
        stage=Path(temporary)/'recipes';stage.mkdir()
        for entry in manifest['files']:
            data=[]
            for part in entry['parts']:
                if payload_root:
                    source=payload_root/part['repository']/'files'/relative(part['path'])
                else:
                    checkouts=manifest['repositories'][part['repository']]
                    # Catalog variants ensure each maintained repository has one
                    # source identity. Accept only an explicitly supplied tree.
                    available=[c for c in checkouts if c['tree'] in roots]
                    if len(available)!=1:raise ValueError('Missing or ambiguous checkout: '+part['repository'])
                    c=available[0]
                    source=roots[c['tree']]/relative(c['path'])/relative(part['path'])
                if not source.is_file() or source.is_symlink():
                    raise ValueError('Recipe must be a regular file: '+str(source))
                piece=source.read_bytes()
                if digest(piece)!=part['sha256']:raise ValueError('Recipe checksum mismatch: '+str(source))
                data.append(piece)
            complete=b''.join(data)
            if digest(complete)!=entry['sha256']:raise ValueError('Reassembled recipe differs: '+entry['path'])
            dest=stage/relative(entry['path']);dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(complete);dest.chmod(int(entry['mode'],8)&0o777)
        (stage/'.component-recipes.json').write_text(json.dumps(dict(
            index_sha256=digest(index.read_bytes()),files=len(destinations),
            generated=True,editable=False,build_validated=False,runtime_validated=False),indent=2)+'\n')
        stage.rename(output)
    return len(destinations)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--index',type=Path,required=True)
    ap.add_argument('--ohos',type=Path)
    ap.add_argument('--arkweb',type=Path)
    ap.add_argument('--external',type=Path)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--payload-root',type=Path,help='Administrative source-candidate verification only')
    args=ap.parse_args()
    roots={tree:getattr(args,tree) for tree in ('ohos','arkweb','external') if getattr(args,tree)}
    count=materialize(args.index,roots,args.output,args.payload_root)
    print(f'Materialized {count} component-owned recipe files; no build or runtime validation')


if __name__=='__main__':main()
