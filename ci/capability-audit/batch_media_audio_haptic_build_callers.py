#!/usr/bin/env python3
"""Root-only actual SDK105 build. Never signing or guest success evidence."""
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
    evidence = args.output / 'evidence.json'
    report = dict(schema_version=1, scope=project.SDK_SCOPE, source_commit=None,
        runner_sha256=sha(Path(__file__)), source_tools={name: sha(project.HERE / name) for name in project.SDK_SOURCE_TOOLS},
        fixture_hashes=project.fixture_hashes(), commands=[], source_files={}, projects={}, haps=[], failures=[], exit_code=1,
        first_artifact_behavior_gate_passed=False)
    def save(): evidence.write_text(json.dumps(report, indent=2) + '\n')
    def execute(argv, role, label, cwd, timeout=1200):
        log = args.output / (role + '-' + label + '.log'); timed_out = False
        try:
            with log.open('xb') as stream:
                child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, start_new_session=True)
                try: code = child.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True; os.killpg(child.pid, signal.SIGTERM)
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
                    code = 124
        except OSError as error:
            with log.open('ab') as stream: stream.write((str(error) + '\n').encode())
            code = 127
        report['commands'].append(dict(project=role, label=label, argv=argv, cwd=str(cwd), exit_code=code,
            timed_out=timed_out, log=str(log), sha256=sha(log))); save()
        require(code == 0, role + '/' + label + ' failed with ' + str(code))
        return log.read_text(errors='replace')
    save()
    try:
        report['sdk'] = project.sdk_inputs(args.sdk)
        require(project.load(project.checked(report['sdk']['metadata']))['version'] == '26.0.0.105', 'actual SDK105 required')
        report['source_commit'] = subprocess.check_output(['git', '-C', str(project.ROOT), 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
        for name in ('node', 'ohpm', 'hvigor'):
            setattr(args, name, project.checked(record(getattr(args, name))))
        shutil.copytree(args.hvigor_cache, args.output / 'hvigor-home', symlinks=True)
        if args.ohpm_cache: shutil.copytree(args.ohpm_cache, args.output / 'ohpm-home', symlinks=True)
        cpu = args.output / 'cpu-cap.cjs'; shutil.copyfile(project.FIX / 'cpu-cap.cjs', cpu)
        report['runtime_inputs'] = {name: record(path) for name, path in
            {'node': args.node, 'ohpm': args.ohpm, 'hvigor': args.hvigor, 'cpu_cap': cpu}.items()}
        env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C', NODE_HOME=str(args.node.parent.parent),
            HVIGOR_USER_HOME=str(args.output / 'hvigor-home'), OHPM_HOME=str(args.output / 'ohpm-home'))
        env.pop('NODE_OPTIONS', None)
        env['PATH'] = str(args.node.parent) + os.pathsep + env.get('PATH', '')
        report['node_version'] = execute([str(args.node), '--version'], '_toolchain', 'node-version', args.output, 10).strip()
        require(report['node_version'] == 'v18.20.1', 'actual fixed SDK Node version required')
        for role in project.ROLES:
            try:
                source = getattr(args, role).resolve(); report['projects'][role] = str(source)
                require(source.is_dir() and not source.is_relative_to(project.ROOT) and not args.output.is_relative_to(source),
                        'fresh private prepared project with separate evidence required')
                manifest = project.load(source / 'audio-haptic-source-manifest.json')
                require(manifest['role'] == role and manifest['sdk'] == report['sdk'] and
                        manifest['fixture_hashes'] == project.fixture_hashes(), 'prepared role/fixed fixture/actual SDK differs')
                properties = source / 'local.properties'
                require(not properties.exists(), 'preserve existing SDK project local.properties; prepare fresh project')
                properties.write_text('sdk.dir=' + str(args.sdk.resolve().parent) + '\nnodejs.dir=' + str(args.node.parent.parent) + '\n')
                inventory = dict(manifest['sources'])
                inventory.update({'audio-haptic-source-manifest.json': sha(source / 'audio-haptic-source-manifest.json'), 'local.properties': sha(properties)})
                require(all(sha(source / name) == expected for name, expected in inventory.items()), 'prepared source changed before compilation')
                report['source_files'][role] = inventory; save()
                prefix = [str(args.node), '--max-old-space-size=2048', '--require', str(cpu)]
                execute(prefix + [str(args.ohpm), 'install', '--all', '--registry', 'http://127.0.0.1:9',
                    '--fetch_timeout', '10000', '--retry_times', '0'], role, 'dependencies', source)
                execute(prefix + [str(args.hvigor), 'assembleHap', '--mode', 'module', '-p', 'product=default', '-p',
                    'module=entry', '-p', 'debuggable=false', '-p', 'hvigor-obfuscation=false', '--no-daemon',
                    '--no-parallel', '--no-incremental', '--max-old-space-size', '2048'], role, 'compile', source)
                candidates = list(source.glob('entry/build/default/outputs/default/*-unsigned.hap'))
                require(len(candidates) == 1, role + ' requires exactly one complete unsigned HAP')
                hap = candidates[0]; report['haps'].append(dict(project=role, path=str(hap), sha256=sha(hap), bytes=hap.stat().st_size))
                require(all(sha(source / name) == expected for name, expected in inventory.items()), 'prepared input changed during build')
                save()
            except Exception as error:
                report['failures'].append(role + ': ' + type(error).__name__ + ': ' + str(error)); save()
        report['exit_code'] = 0 if not report['failures'] and len(report['haps']) == len(project.ROLES) else 1
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
    finally: save()
    inputs = {}
    if report['exit_code'] == 0:
        for role in project.ROLES:
            source = Path(report['projects'][role]); hap = next(h for h in report['haps'] if h['project'] == role)
            inputs[role] = dict(sdk_evidence=record(evidence), sdk_project=role, source_project=str(source),
                source_manifest=record(source / 'audio-haptic-source-manifest.json'), unsigned_hap=record(hap['path']))
        try:
            for role, spec in inputs.items(): project.project_binding(spec, role, project.checked(project.load(spec['source_manifest']['path'])['challenge']))
        except Exception as error:
            report['exit_code'] = 1; report['failures'].append('actual SDK source binding: ' + str(error)); save(); inputs = {}
    # Failed batches never publish a ready artifact-input manifest.
    if inputs: project.write(args.output / 'project-inputs.json', inputs)
    print(json.dumps(dict(exit_code=report['exit_code'], failures=report['failures'], haps=report['haps']), indent=2))
    raise SystemExit(report['exit_code'])


if __name__ == '__main__': main()
