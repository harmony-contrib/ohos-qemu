#!/usr/bin/env python3
"""Root-only serial actual SDK105 build. Explicit execution; never sign/install/boot."""
import argparse
import json
import os
from pathlib import Path
import shutil
import time

from batch_apps_share578_project import (ROOT, FIX, ROLES, checked, load_challenge, prepared,
    record, repository, require, sdk_contract, sha, source_tools, write)

SCOPE = 'actual_share578_three_ordinary_SDK105_unsigned_HAPs_ONLY'


def sdk_commands(tools):
    paths = {name: str(checked(tools[name])) for name in ('node', 'ohpm', 'hvigor', 'cpu_cap')}
    prefix = [paths['node'], '--max-old-space-size=2048', '--require', paths['cpu_cap']]
    return [('dependencies', prefix + [paths['ohpm'], 'install', '--all', '--registry', 'http://127.0.0.1:9',
        '--fetch_timeout', '10000', '--retry_times', '0']),
        ('compile', prefix + [paths['hvigor'], 'assembleHap', '--mode', 'module', '-p', 'product=default',
        '-p', 'module=entry', '-p', 'debuggable=false', '-p', 'hvigor-obfuscation=false',
        '--no-daemon', '--no-parallel', '--no-incremental', '--max-old-space-size', '2048'])]


def build(args, *, runner=None):
    require(args.execute_sdk_build, 'root must explicitly authorize actual SDK execution')
    require(callable(runner), 'actual root-owned lease runner callback required; no resource fallback')
    data = load_challenge(args.challenge); require(data['source_commit'] == args.commit, 'challenge commit differs')
    repository(args.commit)
    output = Path(args.output).absolute()
    require(not output.exists() and output.parent.resolve() == output.parent and ROOT not in output.parents,
            'fresh canonical private SDK output required')
    output.mkdir(parents=True)
    projects = {}
    for item in args.project:
        name, separator, path = item.partition('=')
        require(separator and name in ROLES and name not in projects, 'unique exact role=/absolute/project required')
        p = Path(path); require(p.is_absolute() and p.resolve() == p and ROOT not in p.parents, 'private canonical project required')
        projects[name] = p
    require(set(projects) == set(ROLES) and len(set(projects.values())) == 3, 'all three independent projects required')
    inventories = {role: prepared(project, role, args.challenge) for role, project in projects.items()}
    proof = sdk_contract(args.sdk)
    require(all(m['sdk'] == proof for m, _ in inventories.values()), 'actual compiler SDK differs from preparation')
    wrapper = Path(args.hvigor_cache).resolve() / 'wrapper'
    require(wrapper.is_dir(), 'real Hvigor wrapper cache required')
    shutil.copytree(wrapper, output / 'hvigor-home/wrapper', symlinks=True)
    if args.ohpm_cache: shutil.copytree(Path(args.ohpm_cache).resolve(), output / 'ohpm-home', symlinks=True)
    cpu = output / 'cpu-cap.cjs'; shutil.copyfile(FIX / 'cpu-cap.cjs', cpu)
    tools = {name: record(Path(getattr(args, name)).resolve()) for name in ('node', 'ohpm', 'hvigor')}
    tools['cpu_cap'] = record(cpu)
    report = {'schema_version': 1, 'scope': SCOPE, 'source_commit': args.commit, 'challenge': record(args.challenge),
        'source_tools': source_tools(), 'sdk': proof, 'tools': tools, 'source_files': {role: rows for role, (_, rows) in inventories.items()},
        'commands': [], 'haps': [], 'failures': [], 'exit_code': 1, 'runtime_validated': False,
        'first_artifact_behavior_gate_passed': False}
    env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C', NODE_HOME=str(Path(args.node).resolve().parent.parent),
        DEVECO_SDK_HOME=str(Path(args.sdk).resolve().parent), HVIGOR_USER_HOME=str(output / 'hvigor-home'),
        OHPM_HOME=str(output / 'ohpm-home'))
    env.pop('NODE_OPTIONS', None); env['PATH'] = str(Path(args.node).resolve().parent) + os.pathsep + env.get('PATH', '')
    start = time.monotonic()
    def command(argv, role, label, timeout):
        log = output / (role + '-' + label + '.log')
        require(not log.exists() and not log.is_symlink(), 'fresh actual command log required')
        cwd = projects[role] if role in projects else output
        row = {'argv': list(argv), 'cwd': str(cwd), 'project': role, 'label': label,
               'planned_log_path': str(log), 'actual_observation_received': False}
        if role == 'tools': report['node_version_command'] = row
        else: report['commands'].append(row)
        # The caller holds the ONE actual SDK lease for this whole function.
        # No subprocess, nested lock, owner JSON assertion or fallback exists.
        observed = runner(list(argv), cwd=cwd, env=env, log=log,
                          timeout=timeout, role=role, label=label)
        require(isinstance(observed, dict) and observed.get('argv') == argv and
                observed.get('cwd') == str(cwd) and type(observed.get('exit_code')) is int and
                observed.get('log') == record(log) and
                type(observed.get('started_ns')) is int and type(observed.get('finished_ns')) is int and
                0 < observed['started_ns'] <= observed['finished_ns'],
                'root callback did not return exact actual command/log observation')
        row.clear(); row.update(observed, project=role, label=label, actual_observation_received=True)
        require(observed['exit_code'] == 0 and not observed.get('timed_out', False),
                'actual root SDK command failed: ' + role + '/' + label)
        return log.read_text(errors='replace')
    try:
        report['node_version'] = command([str(checked(tools['node'])), '--version'], 'tools', 'node-version', 10).strip()
        require(report['node_version'] == 'v18.20.1', 'official pinned Node18.20.1 required')
        for role in ROLES:
            project = projects[role]
            for label, argv in sdk_commands(tools):
                text = command(argv, role, label, 120 if label == 'dependencies' else 1800)
                if label == 'compile': require('BUILD SUCCESSFUL' in text, 'real Hvigor success missing')
            _, now = prepared(project, role, args.challenge)
            require(now == report['source_files'][role], 'actual source changed during build')
            hap = project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
            from batch_apps_contact_picker_coordinator import ordinary_hap
            ordinary_hap(hap, ROLES[role]['bundle'], [])
            report['haps'].append({'project': role, **record(hap), 'bytes': hap.stat().st_size})
        repository(args.commit)
        require(report['source_tools'] == source_tools() and report['sdk'] == sdk_contract(args.sdk), 'compiler/source freeze changed')
        report['exit_code'] = 0
    except Exception as error: report['failures'].append(type(error).__name__ + ': ' + str(error))
    finally:
        report['seconds'] = time.monotonic() - start
        write(output / 'evidence.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('node', 'ohpm', 'hvigor', 'sdk', 'hvigor-cache', 'output', 'challenge'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--ohpm-cache', type=Path); parser.add_argument('--commit', required=True)
    parser.add_argument('--project', action='append', required=True); parser.add_argument('--execute-sdk-build', action='store_true')
    parser.parse_args()
    parser.error('direct SDK execution refused: root must hold its existing SDK lease and call build(args, runner=owned_callback)')


if __name__ == '__main__': main()
