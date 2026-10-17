#!/usr/bin/env python3
"""Read-only Calendar-specific source/SDK provenance; never builds or signs."""
import hashlib
import json
from pathlib import Path
import re

import batch_apps_contact_picker_coordinator as shared
from batch_system_calendar_runtime_project import (FIX, ROLES, checked, expected_sources, load_challenge,
    record, require, sdk_contract, sha)

HERE = Path(__file__).resolve().parent
SDK_SCOPE = 'actual_private_Calendar_QA_SDK105_HAP_compile_ONLY'
SOURCE_TOOLS = ('batch_system_calendar_runtime_project.py', 'batch_system_calendar_runtime_binding.py')


def source_tools():
    return {name: sha(HERE / name) for name in SOURCE_TOOLS}


def prepared(source, role, challenge_path):
    source = Path(source)
    require(source.is_absolute() and source.is_dir() and not source.is_symlink(), 'actual private Calendar project required')
    challenge_file = Path(challenge_path)
    require(challenge_file.is_absolute() and challenge_file.is_file() and not challenge_file.is_symlink(),
            'absolute regular Calendar challenge required')
    challenge_file = challenge_file.resolve()
    manifest_path = source / 'calendar-source-manifest.json'
    manifest = json.loads(manifest_path.read_text())
    data = load_challenge(challenge_path)
    require(manifest.get('schema_version') == 1 and manifest.get('role') == role and role in ROLES and
            manifest.get('run_id') == data['run_id'] and all(manifest.get(k) == v for k, v in ROLES[role].items()) and
            manifest.get('challenge') == record(challenge_file) and manifest.get('signed') is False and
            manifest.get('runtime_acceptance') is False, 'exact prepared role/run/challenge required')
    metadata = checked(manifest['sdk']['metadata'])
    require(metadata.name == 'oh-uni-package.json' and metadata.parent.name == 'ets', 'actual SDK metadata path required')
    sdk = metadata.parent.parent
    require(manifest['sdk'] == sdk_contract(sdk) and manifest.get('fixture_hashes') ==
            {p.name: sha(p) for p in sorted(FIX.iterdir()) if p.is_file()}, 'actual SDK105/fixture changed')
    files = expected_sources(data, role, sdk)
    hashes = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()}
    require(manifest.get('source_hashes') == hashes, 'source manifest does not describe the exact role/run source recipe')
    for name, text in files.items():
        path = source / name
        require(not path.is_symlink() and path.is_file() and path.read_bytes() == text.encode(),
                'actual compiled source differs from role/run recipe: ' + name)
    # New input files under source/resource roots can change the HAP even when
    # none of the manifest's listed files changed. Generated build output is
    # outside these input roots and is deliberately not treated as source.
    for prefix in ('AppScope', 'entry/src/main', 'hvigor'):
        for path in (source / prefix).rglob('*'):
            if path.is_file():
                require(str(path.relative_to(source)) in hashes and not path.is_symlink(),
                        'unlisted Calendar source/resource input')
    hashes['calendar-source-manifest.json'] = sha(manifest_path)
    return manifest, hashes


def sdk_commands(tools):
    paths = {name: str(checked(tools[name])) for name in ('node', 'ohpm', 'hvigor', 'cpu_cap')}
    prefix = [paths['node'], '--max-old-space-size=2048', '--require', paths['cpu_cap']]
    return [('dependencies', prefix + [paths['ohpm'], 'install', '--all', '--registry', 'http://127.0.0.1:9',
                '--fetch_timeout', '10000', '--retry_times', '0']),
            ('compile', prefix + [paths['hvigor'], 'assembleHap', '--mode', 'module', '-p', 'product=default',
                '-p', 'module=entry', '-p', 'debuggable=false', '-p', 'hvigor-obfuscation=false',
                '--no-daemon', '--no-parallel', '--no-incremental', '--max-old-space-size', '2048'])]


def sdk_binding(spec, manifest_artifact, role, challenge_path):
    """Strict successful Calendar builder receipt, source recipe and HAP binding."""
    source = Path(spec['source_project'])
    manifest, hashes = prepared(source, role, challenge_path)
    require(checked(manifest_artifact) == source / 'calendar-source-manifest.json' and
            spec['sdk_project'] == role, 'exact role source manifest/project required')
    evidence = checked(spec['sdk_evidence'])
    report = json.loads(evidence.read_text())
    require(report.get('schema_version') == 1 and report.get('scope') == SDK_SCOPE and
            type(report.get('exit_code')) is int and report['exit_code'] == 0 and report.get('failures') == [] and
            report.get('node_version') == 'v18.20.1' and re.fullmatch('[a-f0-9]{40}', report.get('source_commit', '')) and
            report.get('runner_sha256') == sha(HERE / 'batch_system_calendar_runtime_build.py') and
            report.get('source_tools') == source_tools() and report.get('sdk') == manifest['sdk'],
            'successful dedicated Calendar SDK105 builder provenance required')
    projects = set(report['source_files'])
    require(projects and projects <= set(ROLES) and role in projects and report['source_files'][role] == hashes and
            len(report['haps']) == len(projects) and {h.get('project') for h in report['haps']} == projects,
            'exact complete successful Calendar SDK inventories required')
    tools = report['tools']
    require(checked(tools['cpu_cap']) == evidence.parent / 'cpu-cap.cjs' and
            sha(checked(tools['cpu_cap'])) == sha(FIX / 'cpu-cap.cjs'), 'actual bounded SDK preload differs')
    commands = sdk_commands(tools)
    require(len(report['commands']) == 2 * len(projects) and all(
            c.get('project') in projects and type(c.get('exit_code')) is int and c['exit_code'] == 0 and
            not c.get('timed_out', False) for c in report['commands']), 'successful serial SDK commands required')
    selected = [c for c in report['commands'] if c['project'] == role]
    require(len(selected) == len(commands), 'exact two role SDK commands required')
    for row, (label, argv) in zip(selected, commands):
        require(row.get('label') == label and row.get('argv') == argv and row.get('cwd') == str(source),
                'actual dedicated SDK command/cwd differs')
    # The generic verifier also hashes the actual logs, source files and HAP,
    # and checks the selected compile log contains real Hvigor success output.
    return shared.verify_sdk_project(spec)


def permission_label(bundle, apps, run):
    for role, policy in ROLES.items():
        if policy['bundle'] == bundle:
            return 'Calendar QA ' + role + ' ' + run
    require(bundle == 'com.ohos.calendardata', 'only current Calendar provider can request viewer permission')
    label = apps[bundle].get('label')
    require(isinstance(label, str) and label.strip() == label and label and len(label) <= 256 and
            not label.startswith(('$', '@')) and label != bundle,
            'actual BMS provider label is unavailable; preserve permission-requester identity gap')
    return label


def signed_payload(unsigned, signed):
    # Root owns this shared implementation. Do not add a local fallback or
    # permit any extra member beyond its exact .pages.info signing contract.
    return shared.verify_signed_payload(unsigned, signed)
