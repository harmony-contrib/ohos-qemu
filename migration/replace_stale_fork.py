#!/usr/bin/env python3
"""Preserve an untouched upstream fork, then create an independent source mirror.

Used when a stale fork network cannot host current source/LFS history. Requires
exact upstream heads and no issues/PRs/releases. Never deletes the old repository.
"""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--name',required=True)
    ap.add_argument('--catalog',type=Path,required=True)
    ap.add_argument('--evidence',type=Path,required=True)
    args=ap.parse_args()
    c=json.loads(args.catalog.read_text());r=next(x for x in c['repositories'] if x['name']==args.name)
    upstream=r.get('github_upstream')
    if not upstream:raise ValueError('Expected an existing upstream fork')
    repo='openharmony-qemu/'+args.name;backup=args.name+'-upstream-fork-backup'
    def api(*argv):return json.loads(subprocess.check_output(['gh','api',*argv],text=True))
    m=api('repos/'+repo)
    pulls=api('repos/'+repo+'/pulls?state=all&per_page=100')
    releases=api('repos/'+repo+'/releases?per_page=100')
    def heads(repo):return subprocess.check_output(['git','ls-remote','--heads','git@github.com:'+repo+'.git'],text=True)
    original=heads(repo)
    if not m['fork'] or m['parent']['full_name'].lower()!=upstream.lower():raise ValueError('Fork identity differs')
    if pulls or releases or m['open_issues_count'] or original!=heads(upstream):
        raise ValueError('Fork has distinct content or metadata; preserve for manual review')
    record=dict(repository=repo,repository_id=m['id'],retained_backup='openharmony-qemu/'+backup,
        refs=original,metadata=m,reason='Upstream fork network LFS quota blocks current source synchronization')
    args.evidence.parent.mkdir(parents=True,exist_ok=True)
    args.evidence.write_text(json.dumps(record,indent=2)+'\n')
    subprocess.run(['gh','api','--method','PATCH','repos/'+repo,'-f','name='+backup,'--silent'],check=True)
    subprocess.run(['gh','repo','archive','openharmony-qemu/'+backup,'--yes'],check=True)
    r.update(original_github_upstream=upstream,github_upstream=None,
        retained_upstream_fork='openharmony-qemu/'+backup,mirror_reason=record['reason'])
    args.catalog.write_text(json.dumps(c,indent=2)+'\n')
    subprocess.run(['gh','repo','create',repo,'--public','--description',
        'QEMU OpenHarmony 7.0 source mirror; upstream: '+r['upstream_url']],check=True)
    print(repo+': independent mirror created; original fork retained')


if __name__=='__main__':main()
