#!/usr/bin/env python3
"""Root-only real SDK105 build of the two prepared ordinary HAP projects.

Runs actual Node/OHPM/Hvigor, preserves every failure and complete unsigned HAP.
No signing, SDK installation, VM, grants or product source/out mutation.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess

import batch_media_audio_haptic_project as project


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('normal', 'denied', 'sdk', 'node', 'ohpm', 'hvigor', 'hvigor-cache', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--ohpm-cache', type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve(); args.output.mkdir(parents=True, exist_ok=False)
    require, sha, record = project.require, project.sha, project.record
    require(project.load(args.sdk / 'ets/oh-uni-package.json')['version'] == '26.0.0.105', 'actual SDK105 required')
    for path in (args.node, args.ohpm, args.hvigor): require(path.is_file(), 'actual SDK build executable/script missing')
    shutil.copytree(args.hvigor_cache, args.output / 'hvigor-home', symlinks=True)
    if args.ohpm_cache: shutil.copytree(args.ohpm_cache, args.output / 'ohpm-home', symlinks=True)
    cpu = args.output / 'cpu-cap.cjs'; shutil.copyfile(project.FIX / 'cpu-cap.cjs', cpu)
    env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C', NODE_HOME=str(args.node.resolve().parent.parent),
        HVIGOR_USER_HOME=str(args.output / 'hvigor-home'), OHPM_HOME=str(args.output / 'ohpm-home'))
    env.pop('NODE_OPTIONS', None)
    env['PATH'] = str(args.node.resolve().parent) + os.pathsep + env.get('PATH', '')
    report = dict(schema_version=1, scope='actual_SDK105_full_unsigned_AudioHaptic_HAPs_ONLY_NOT_signature_or_guest',
        source_commit=subprocess.check_output(['git', '-C', str(project.ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        runner_sha256=sha(Path(__file__)), commands=[], source_files={}, haps=[], failures=[], exit_code=1,
        runtime_inputs={str(p): record(p) for p in (args.node, args.ohpm, args.hvigor, cpu)},
        first_artifact_behavior_gate_passed=False)
    evidence = args.output / 'evidence.json'
    def save(): evidence.write_text(json.dumps(report, indent=2)+'\n')
    save()
    for role in project.ROLES:
        source = getattr(args, role).resolve()
        manifest = project.load(source / 'audio-haptic-source-manifest.json')
        require(manifest['role'] == role and manifest['sdk'] is not None, 'actual prepared role source required')
        properties = source / 'local.properties'
        require(not properties.exists(), 'preserve existing SDK project local.properties; prepare fresh project')
        properties.write_text('sdk.dir='+str(args.sdk.resolve().parent)+'\nnodejs.dir='+str(args.node.resolve().parent.parent)+'\n')
        inventory = dict(manifest['sources'])
        inventory.update({'audio-haptic-source-manifest.json': sha(source / 'audio-haptic-source-manifest.json'), 'local.properties': sha(properties)})
        require(all(sha(source / name) == expected for name, expected in inventory.items()), 'prepared source changed before compilation')
        report['source_files'][role] = inventory
        commands = [('dependencies', [str(args.node), '--max-old-space-size=2048', '--require', str(cpu), str(args.ohpm),
            'install', '--all', '--registry', 'http://127.0.0.1:9', '--fetch_timeout', '10000', '--retry_times', '0']),
            ('compile', [str(args.node), '--max-old-space-size=2048', '--require', str(cpu), str(args.hvigor),
            'assembleHap', '--mode', 'module', '-p', 'product=default', '-p', 'module=entry', '-p', 'debuggable=false',
            '-p', 'hvigor-obfuscation=false', '--no-daemon', '--no-parallel', '--no-incremental', '--max-old-space-size', '2048'])]
        for label, argv in commands:
            log = args.output / (role+'-'+label+'.log')
            try:
                with log.open('xb') as stream:
                    child = subprocess.Popen(argv, cwd=source, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                             stdin=subprocess.DEVNULL, start_new_session=True)
                    try: code = child.wait(timeout=1200)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGTERM)
                        try: child.wait(timeout=5)
                        except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
                        code = 124
            except OSError as error:
                with log.open('ab') as stream: stream.write((str(error)+'\n').encode())
                code = 127
            report['commands'].append(dict(project=role, label=label, argv=argv, cwd=str(source), exit_code=code, log=str(log), sha256=sha(log)))
            save()
            if code:
                report['failures'].append(role+'/'+label+' failed with '+str(code)); break
        candidates = list(source.glob('entry/build/default/outputs/default/*-unsigned.hap'))
        if len(candidates) == 1:
            hap = candidates[0]; report['haps'].append(dict(project=role, path=str(hap), sha256=sha(hap), bytes=hap.stat().st_size))
        else: report['failures'].append(role+' requires exactly one complete unsigned HAP')
        if any(sha(source/name) != expected for name, expected in inventory.items()): report['failures'].append(role+' prepared input changed during build')
        save()
    report['exit_code'] = 0 if not report['failures'] and len(report['haps']) == 2 else 1
    save()
    inputs = {}
    for role in project.ROLES:
        haps = [row for row in report['haps'] if row['project'] == role]
        if len(haps) == 1:
            source = getattr(args, role).resolve()
            inputs[role] = dict(sdk_evidence=record(evidence), sdk_project=role, source_project=str(source),
                source_manifest=record(source/'audio-haptic-source-manifest.json'), unsigned_hap=record(haps[0]['path']))
    project.write(args.output / 'project-inputs.json', inputs)
    print(json.dumps(dict(exit_code=report['exit_code'], failures=report['failures'], haps=report['haps']), indent=2))
    raise SystemExit(report['exit_code'])


if __name__ == '__main__': main()
