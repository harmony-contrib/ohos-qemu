"""Resolve the published head of each component from append-only receipts."""
import collections
import json


def published_heads(journals):
    commits=collections.defaultdict(set)
    parents=collections.defaultdict(set)
    for path in journals or []:
        if not path.exists():continue
        for row in map(json.loads,path.read_text().splitlines()):
            if row.get('status')!='published':continue
            commits[row['name']].add(row['qemu_commit'])
            if row.get('parent'):parents[row['name']].add(row['parent'])
    result={}
    for name,values in commits.items():
        leaves=values-parents[name]
        if len(leaves)!=1:
            raise ValueError('Publication receipts require branch lineage review: '+name)
        result[name]=next(iter(leaves))
    return result
