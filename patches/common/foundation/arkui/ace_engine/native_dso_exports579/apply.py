#!/usr/bin/env python3
"""Prepare one actual-bound ACE map; no build or behavior acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys

STATE_SHA = '72789304c24082da234ef4731c2c9e6927ee86bab73847ca0e1176aaf656e2e5'
BINDING_SHA = '70c78956039662bd0a6bac53b718ffd458133893f8fb49577053d9624447e5af'
LIBRARY_SHA = 'afb7560daa888493878e6d107baf1487f48c09fb6fe028fd89b331842e2b83ee'
PROJECT = 'foundation/arkui/ace_engine'
REVISION = 'e55e178228b9f6388b15d3024e8caf125fa293d7'
MAP = PROJECT + '/build/libace.map'
BEFORE = '51f2d090041e111edc17ff3aa87963b8024ceb3d67b1e860d0773aa3d115d566'
AFTER = 'c8b5d562a10f84d82c28450ed4c29b2f5bd1b16081306cfbb79d6066e07a0d95'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def regular(path):
    need(path.is_absolute() and path.resolve() == path and
         not any(p.is_symlink() for p in (path, *path.parents)), 'unaliased source snapshot')
    before = path.stat(follow_symlinks=False)
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'single ordinary source snapshot')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        body = stream.read()
        after = os.fstat(stream.fileno())
    named = path.stat(follow_symlinks=False)
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
                value.st_ctime_ns, stat.S_IMODE(value.st_mode), value.st_uid, value.st_gid)
    need(identity(before) == identity(opened) == identity(after) == identity(named),
         'source snapshot changed while read')
    return body


def checked(component, row):
    need(type(row) is dict and set(row) == {'path', 'sha256', 'bytes'}, 'component-local exact Ref3')
    name = row['path']
    need(type(name) is str, 'string source snapshot path')
    relative = PurePosixPath(name)
    need(not relative.is_absolute() and relative.as_posix() == name and
         '..' not in relative.parts and name not in ('', '.'), 'finite source snapshot path')
    body = regular(component / name)
    need(type(row['bytes']) is int and len(body) == row['bytes'] and
         hashlib.sha256(body).hexdigest() == row['sha256'], 'fixed source snapshot bytes changed')
    return body


def document(body):
    def unique(pairs):
        value = {}
        for name, item in pairs:
            need(name not in value, 'duplicate source metadata key')
            value[name] = item
        return value
    return json.loads(body, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite source metadata')))


def proof(component, state):
    row = state['actual_source_binding']
    need(row['path'] == 'actual_source_binding.json' and row['sha256'] == BINDING_SHA,
         'fixed non-null actual RO source binding')
    binding = document(checked(component, row))
    need(binding['schema'] == 'arkui579-actual-native-dso-export-binding/v1' and
         binding['project'] == PROJECT and binding['revision'] == REVISION and
         binding['source_commit_preimage'] == '553cdfc7fc0a8cdd0422d2dffbea853ac2578dd4' and
         binding['source_only'] is True and all(binding[x] is False for x in
             ('candidate_executed', 'runtime_pass', 'first_artifact_behavior_gate_passed')),
         'actual source binding identity, never runtime acceptance')
    need(set(binding['managed_files']) == {MAP} and
         binding['managed_files'][MAP]['path'] == 'before/' + MAP and
         binding['managed_files'][MAP]['sha256'] == BEFORE, 'one exact actual map preimage')
    original = checked(component, binding['managed_files'][MAP])
    provenance = binding['provenance']
    need(set(provenance) == {'FACTS579.json', 'SOURCE.json', 'producer.json', 'resources.json'},
         'complete original local RO metadata snapshots')
    docs = {}
    for name, item in provenance.items():
        need(item['path'] == 'provenance/' + name, 'fixed local provenance source')
        docs[name] = document(checked(component, item))
        origin = binding['original_provenance'][name]
        need((origin['sha256'], origin['bytes']) == (item['sha256'], item['bytes']),
             'original host Ref bytes retained without rewriting')
    facts, source, producer, resources = (docs[n] for n in
        ('FACTS579.json', 'SOURCE.json', 'producer.json', 'resources.json'))
    fact_ref = provenance['FACTS579.json']
    need(source['facts']['sha256'] == fact_ref['sha256'] and
         source['facts']['bytes'] == fact_ref['bytes'] and
         source['result']['inner_ref'] == source['facts'] and
         producer['source_export'] == binding['original_provenance']['SOURCE.json'] and
         producer['resource_ledger'] == binding['original_provenance']['resources.json'],
         'actual producer to original source/facts/resources join')
    need(facts['schema'] == 'actual-readonly-six-source-facts579/v1' and
         facts['status'] == source['result']['status'] == binding['source_scope_status'] ==
             'optional_facts_budget_partial_keep_raw' and
         facts['ro_identity_unchanged'] is True and
         all(facts[k] is False for k in ('whole_source_tree_verified', 'whole_out_freshness_proven',
                                       'runtime_validated', 'first_artifact_behavior_gate_passed')),
         'actual partial RO scope must remain partial and non-runtime')
    need(producer['root_integration_commit'] == binding['source_commit_preimage'] and
         producer['exit_code'] == 0 and producer['cleanup_verified'] is True and
         producer['owned_container_absent'] is True and resources['phase'] == 'closed' and
         resources['cleanup_verified'] is True and resources['failed'] is False,
         'original actual source-only producer closed')
    containers = resources['containers']
    need(len(containers) == 1 and containers[0]['id'] == producer['container_id'] and
         containers[0]['absent'] is True and
         all(containers[0]['mounts'][name]['RW'] is False for name in ('/ohos', '/ohos/out')),
         'same actual original closed CID and read-only source/out mounts')
    repo = facts['repositories'][PROJECT]
    need(repo['actual_head_before'] == repo['actual_head_after'] == REVISION and
         repo['head_unchanged'] is True and repo['head_before'] == binding['head_before'] and
         repo['head_after'] == binding['head_after'], 'actual same project HEAD before/after RO')
    matches = [x for x in facts['files'] if x['path'] == '/ohos/' + MAP]
    need(len(matches) == 1 and matches[0] == binding['map_record'], 'unique actual full source record')
    record = matches[0]
    need(record['status'] == 'exported_stable' and record['before'] == record['after'] and
         record['source_read_only_after'] is True and record['after_sha256'] == BEFORE and
         record['export_ref']['sha256'] == BEFORE and record['export_ref']['bytes'] == len(original),
         'actual immutable map bytes/stat/RO identity')
    commands = [repo['head_before'], repo['head_after'], *record['commands']]
    originals = [command[channel] for command in commands for channel in ('stdout', 'stderr')]
    need(len(binding['raw_bindings']) == len(originals), 'all relevant actual command raw channels')
    for command in commands:
        need(command['executed'] is True and command['exit_code'] == 0 and command['timed_out'] is False,
             'actual successful source read command')
    for expected, retained in zip(originals, binding['raw_bindings']):
        need(retained['original'] == expected, 'original CID raw reference unchanged')
        data = checked(component, retained['local'])
        need(hashlib.sha256(data).hexdigest() == expected['sha256'] and len(data) == expected['bytes'],
             'local non-executable snapshot is the original raw data')
    need(regular(component / ('before/' + MAP)) == original and
         hashlib.sha256(regular(component / ('after/' + MAP))).hexdigest() == AFTER,
         'complete retained before/final payload')
    need(state['patch'] == '0001-product-source.patch' and
         hashlib.sha256(regular(component / state['patch'])).hexdigest() == state['patch_sha256'],
         'fixed exact product patch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--require-final', action='store_true')
    mode.add_argument('--rewind', action='store_true')
    args = parser.parse_args()
    component = Path(__file__).resolve().parent
    raw = regular(component / 'source_states.json')
    need(hashlib.sha256(raw).hexdigest() == STATE_SHA, 'complete actual-bound state metadata changed')
    state = document(raw)
    need(state['schema'] == 'guarded-product-source-vector579/v1' and
         state['component'] == 'native_dso_exports579' and state['managed_count'] == 1 and
         state['projects'] == {PROJECT: REVISION} and state['files'] == {MAP: [BEFORE, AFTER]},
         'one exact complete native export map state')
    proof(component, state)
    library = component.parents[4] / 'lib/guarded_source_vector579.py'
    need(hashlib.sha256(regular(library)).hexdigest() == LIBRARY_SHA,
         'exact original scratch/transaction/rollback source helper')
    command = [sys.executable, '-B', str(library), '--component-dir', str(component),
               '--source-root', str(args.source_root.resolve())]
    if args.require_final:
        command.append('--require-final')
    if args.rewind:
        command.append('--rewind')
    subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
