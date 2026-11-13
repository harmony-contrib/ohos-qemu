#!/usr/bin/env python3
"""Archive migration receipts and derive a manifest lock from verified publication.

Completion is explicit and fails closed unless the remote audit, component
payloads, all reviewed exports, daily mirrors and local ownership cutover agree.
This utility never changes source refs or starts a build.
"""
import argparse
import collections
import datetime
import gzip
import hashlib
import json
from pathlib import Path

from component_heads import published_heads

BRANCH = 'OpenHarmony-7.0-Release-qemu'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def snapshot(workspace, catalog_path, root, complete=False, cutover=None):
    manifest = workspace / 'manifest'
    catalog = read_json(catalog_path)
    selection = read_json(workspace / 'reviewed-publication-selection.json')
    index_bytes = (manifest / 'adaptations.json').read_bytes()
    index = json.loads(index_bytes)
    index_hash = sha(index_bytes)
    journals = [workspace / phase['journal'] for phase in selection['phases']]
    heads = {}
    archives = {}
    descriptions = []
    latest = {}
    for path in [workspace / 'repository-creation.jsonl',
                 workspace / 'baseline-publication.jsonl',
                 workspace / 'component-automation.jsonl', *journals]:
        raw = path.read_bytes() if path.exists() else b''
        if raw and not raw.endswith(b'\n'):
            raise ValueError('Journal append is incomplete; retry snapshot: ' + path.name)
        rows = [json.loads(line) for line in raw.splitlines()]
        latest[path.name] = {row['name']: row for row in rows}
        relative = 'publications/' + path.name + '.gz'
        compressed = gzip.compress(raw, mtime=0)
        archives[relative] = compressed
        descriptions.append(dict(file=relative, uncompressed_sha256=sha(raw),
            sha256=sha(compressed), records=len(rows), latest_status_counts=dict(
                collections.Counter(row['status'] for row in latest[path.name].values()))))
    for name, row in latest['baseline-publication.jsonl'].items():
        if row['status'] in ('published', 'preserved_existing'):
            heads[name] = row['remote_revision']
    imports = [read_json(path) for path in sorted((workspace / 'imported').glob('*.json'))]
    for row in imports:
        heads[row['repository'].split('/')[-1]] = row['qemu_commit']
    heads.update(published_heads(journals))

    phases = []
    for phase in selection['phases']:
        pending = []
        for name in phase['repositories']:
            export = workspace / phase['exports'] / name
            fingerprint = sha((export / 'export.json').read_bytes() +
                              (export / 'tracked.patch').read_bytes())
            row = latest[phase['journal']].get(name, {})
            if row.get('status') != 'published' or row.get('export_sha256') != fingerprint:
                pending.append(name)
        phases.append(dict(journal=phase['journal'], required=len(phase['repositories']),
                           published=len(phase['repositories']) - len(pending), pending=pending))

    projects = catalog['repositories']
    names = {project['name'] for project in projects}
    created = {name for name, row in latest['repository-creation.jsonl'].items()
               if row['status'] == 'created'} & names
    required_mirrors = {project['name'] for project in projects if project.get('auto_sync')}
    verified_mirrors = set()
    for path in (manifest / 'migration-evidence/mirror-sync').glob('*-sync-*.json'):
        report = read_json(path)
        if report.get('remote_refs_verified') and not report.get('results', {}).get('conflict'):
            verified_mirrors.add(report['repository'].split('/')[-1])
    verified_mirrors &= required_mirrors
    registry = read_json(workspace / 'mirror-sync/repositories.json', {'repositories': []})
    enabled_mirrors = {row['name'] for row in registry['repositories'] if row['enabled']}
    remote = read_json(workspace / 'remote-state-latest.json', {})
    observed = {row['name']: row for row in remote.get('repositories', [])}
    remote_complete = set(observed) == names and all(
        row.get('matches_expected') and row.get('default_branch') == BRANCH
        and row.get('qemu_revision') == heads.get(name)
        for name, row in observed.items())
    payload = read_json(workspace / 'component-payload-verification.json', {})
    payload_rows = {row['repository']: row for row in payload.get('repositories', [])}
    owners = set(index['repositories']) | {index['materializer']['repository']}
    payload_complete = (payload.get('complete') and payload.get('index_sha256') == index_hash
        and set(payload_rows) == owners and all(
            row.get('status') == 'verified' and row.get('qemu_commit') == heads.get(name)
            and row.get('verified_files') == row.get('expected_files')
            for name, row in payload_rows.items()))
    cutover_record = read_json(cutover, {}) if cutover else {}
    cutover_complete = (cutover_record.get('index_sha256') == index_hash
                        and cutover_record.get('original_files_preserved') is True)
    if cutover_complete:
        for entry in index['files']:
            original = root / entry['path']
            generated = root / '.qemu/component-inputs' / entry['path']
            if (not original.exists() or not generated.is_file()
                    or original.resolve() != generated.resolve()
                    or sha(original.read_bytes()) != entry['sha256']
                    or (original.stat().st_mode & 0o777) != (int(entry['mode'], 8) & 0o777)):
                cutover_complete = False
                break
    gates = dict(repository_creation=created == names,
        component_actions_disabled=all(
            latest['component-automation.jsonl'].get(name, {}).get('status') == 'disabled'
            and latest['component-automation.jsonl'][name].get('verified_actions_enabled') is False
            for name in names),
        remote_branches_and_defaults=remote_complete,
        reviewed_publications=all(not phase['pending'] for phase in phases),
        component_payloads=bool(payload_complete),
        daily_mirror_registry=enabled_mirrors == required_mirrors,
        production_mirror_verification=verified_mirrors == required_mirrors,
        legacy_input_cutover=bool(cutover_complete))
    if complete and not all(gates.values()):
        raise ValueError('Completion is not verified: ' + ', '.join(k for k, v in gates.items() if not v))
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    status = read_json(manifest / 'migration-status.json', {})
    status.update(schema_version=1, snapshot_at=timestamp,
        status='source_migration_complete' if complete else 'in_progress',
        repository_creation_complete=gates['repository_creation'],
        source_baselines_complete=remote_complete,
        patch_migration_complete=bool(gates['reviewed_publications'] and payload_complete and cutover_complete),
        build_validated=False, runtime_validated=False, completion_gates=gates,
        catalog_repositories=len(names), repositories_created=len(created),
        qemu_branches_recorded=len(names & heads.keys()), publication_phases=phases,
        source_components_published=sum(phase['published'] for phase in phases
            if phase['journal'] in ('source-publication.jsonl', 'arkweb-source-publication.jsonl')),
        mirrors_requiring_daily_sync=len(required_mirrors),
        mirrors_with_verified_production_sync=len(verified_mirrors),
        mirrors_awaiting_verification=sorted(required_mirrors - verified_mirrors),
        note='Source repository migration only; package builds and runtime validation remain deferred.')
    lock = dict(schema_version=1, complete=complete, baseline_branch=BRANCH,
        adaptations_sha256=index_hash, repositories=[dict(name=p['name'],
            qemu_revision=heads.get(p['name']),
            upstream_revisions=list(dict.fromkeys(item['revision'] for item in p['inputs'])))
            for p in projects])

    def write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + '\n')

    evidence = manifest / 'migration-evidence'
    for relative, data in archives.items():
        path = evidence / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    write_json(evidence / 'publication-journals.json', dict(snapshot_at=timestamp, journals=descriptions))
    write_json(evidence / 'reviewed-publication-selection.json', selection)
    write_json(evidence / 'imported-baselines.json', imports)
    if remote:
        write_json(evidence / 'remote-state.json', remote)
    if payload:
        write_json(evidence / 'component-payload-verification.json', payload)
    if cutover_complete:
        write_json(evidence / 'legacy-input-cutover.json', dict(index_sha256=index_hash,
            files=len(index['files']), original_files_preserved=True,
            original_backup_name=Path(cutover_record['original_backup']).name,
            build_validated=False, runtime_validated=False))
    write_json(manifest / 'components.lock.json', lock)
    write_json(manifest / 'migration-status.json', status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--cutover', type=Path)
    parser.add_argument('--complete', action='store_true')
    args = parser.parse_args()
    status = snapshot(args.workspace, args.catalog, args.root, args.complete, args.cutover)
    print(json.dumps({k: status[k] for k in ('status', 'repositories_created',
        'qemu_branches_recorded', 'source_components_published',
        'mirrors_with_verified_production_sync', 'completion_gates')}, indent=2))


if __name__ == '__main__':
    main()
