#!/usr/bin/env python3
"""Root-only SDK105 build of this one QA project; no fixed Media/Calendar role reuse.

Serial official Node/OHPM/Hvigor commands with private caches and complete
source/log/HAP inventory. Never signs, installs, boots, or writes product out.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

import batch_network_openvpn_runtime_project as project

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NAME = project.SDK_NAME


def build(args):
    project.require(args.execute_sdk_build, 'root must explicitly authorize actual SDK execution')
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    source = args.project.resolve(); evidence = output / 'evidence.json'
    report = dict(schema_version=1, scope=project.SDK_SCOPE,
        exit_code=1, source_commit=None, runner_sha256=project.sha(Path(__file__)), commands=[],
        source_files={}, source_tools={name: project.sha(HERE / name) for name in project.SOURCE_TOOLS},
        haps=[], failures=[], first_artifact_behavior_gate_passed=False)
    def save(): project.write(evidence, report)
    save()
    try:
        project.require(source.is_absolute() and source.is_dir() and not args.project.is_symlink() and
                        not source.is_relative_to(ROOT) and not output.is_relative_to(source), 'fresh private prepared QA project and separate output required')
        manifest_path = source / 'openvpn-runtime-source.json'; manifest = project.load(manifest_path)
        project.require(manifest['scope'] == project.SCOPE and manifest['bundle'] == project.BUNDLE and
                        manifest['requested_permissions'] == [project.PERMISSION] and manifest['apl'] == 'system_core' and
                        manifest['system_app'] is True and manifest['fixtures'] == {p.name: project.sha(p) for p in project.FIX.glob('*.ets')},
                        'this exact own prepared system QA source is required')
        project.require(project.load(args.sdk / 'ets/oh-uni-package.json')['version'] == '26.0.0.105' and
                        Path(manifest['sdk']['metadata']['path']).resolve() == (args.sdk / 'ets/oh-uni-package.json').resolve(),
                        'the actual prepared SDK105 must match this build')
        for row in manifest['sdk'].values(): project.checked(row)
        report['sdk'] = manifest['sdk']
        report['source_commit'] = subprocess.check_output(['git', '-C', ROOT, 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
        project.require(re.fullmatch('[a-f0-9]{40}', report['source_commit']), 'actual repository commit required')
        for path in (args.node, args.ohpm, args.hvigor): project.shared.regular(path)
        report['node_version'] = subprocess.check_output([args.node, '--version'], text=True, timeout=10).strip()
        project.require(report['node_version'] == 'v18.20.1', 'official Node18.20.1 required')
        report['tools'] = {name: project.descriptor(getattr(args, name)) for name in ('node', 'ohpm', 'hvigor')}
        shutil.copytree(args.hvigor_cache, output / 'hvigor-home', symlinks=True)
        if args.ohpm_cache: shutil.copytree(args.ohpm_cache, output / 'ohpm-home', symlinks=True)
        cpu = output / 'cpu-cap.cjs'
        # Reuse only the bounded CPU preload, not another capability's role or
        # source guard. The copied exact bytes are part of this build receipt.
        shutil.copyfile(HERE / 'fixtures/batch_media/audio_haptic_runtime/cpu-cap.cjs', cpu)
        report['tools']['cpu_cap'] = project.descriptor(cpu)
        properties = source / 'local.properties'
        project.require(not properties.exists() and not properties.is_symlink(), 'preserve previous project local.properties')
        properties.write_text('sdk.dir=' + str(args.sdk.resolve().parent) + '\nnodejs.dir=' + str(args.node.resolve().parent.parent) + '\n')
        inventory = dict(manifest['sources']); inventory.update({manifest_path.name: project.sha(manifest_path), 'local.properties': project.sha(properties)})
        for name, digest in inventory.items():
            relative = Path(name)
            project.require(not relative.is_absolute() and '..' not in relative.parts and project.sha(source / name) == digest,
                            'actual prepared source changed before SDK compilation')
        paths = list(source.rglob('*'))
        project.require(not any(path.is_symlink() for path in paths) and
                        {str(path.relative_to(source)) for path in paths if path.is_file()} == set(inventory),
                        'unexpected or aliased source files before SDK compilation')
        project.require(not (source / 'entry/build').exists(), 'no previous build output is eligible for a fresh SDK receipt')
        report['source_files'][NAME] = inventory; save()
        environment = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C',
            NODE_HOME=str(args.node.resolve().parent.parent), DEVECO_SDK_HOME=str(args.sdk.resolve().parent),
            HVIGOR_USER_HOME=str(output / 'hvigor-home'), OHPM_HOME=str(output / 'ohpm-home'))
        environment.pop('NODE_OPTIONS', None)
        environment['PATH'] = str(args.node.resolve().parent) + os.pathsep + environment.get('PATH', '')
        commands = [('dependencies', [args.node, '--max-old-space-size=2048', '--require', cpu, args.ohpm,
            'install', '--all', '--registry', 'http://127.0.0.1:9', '--fetch_timeout', '10000', '--retry_times', '0']),
            ('compile', [args.node, '--max-old-space-size=2048', '--require', cpu, args.hvigor,
            'assembleHap', '--mode', 'module', '-p', 'product=default', '-p', 'module=entry', '-p', 'debuggable=false',
            '-p', 'hvigor-obfuscation=false', '--no-daemon', '--no-parallel', '--no-incremental', '--max-old-space-size', '2048'])]
        for label, argv in commands:
            argv = list(map(str, argv)); log = output / (label + '.log')
            row = dict(project=NAME, label=label, argv=argv, cwd=str(source), log=str(log), exit_code=None)
            report['commands'].append(row); save()
            with log.open('xb') as stream:
                child = subprocess.Popen(argv, cwd=source, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, start_new_session=True)
                try: code = child.wait(timeout=1200)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM)
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
                    code = 124; row['timed_out'] = True
            row.update(exit_code=code, sha256=project.sha(log)); save()
            project.require(code == 0, 'actual SDK command failed; no native or HAP success claim: ' + label)
            if label == 'compile': project.require('BUILD SUCCESSFUL' in log.read_text(errors='replace'), 'real Hvigor success marker absent')
        for name, digest in inventory.items(): project.require(project.sha(source / name) == digest, 'SDK source changed during compilation')
        haps = list(source.glob('entry/build/default/outputs/default/*-unsigned.hap'))
        project.require(len(haps) == 1, 'one actual complete unsigned HAP required')
        project.shared.hap_contents(haps[0])
        report['haps'] = [dict(project=NAME, **project.descriptor(haps[0]), bytes=haps[0].stat().st_size)]
        report['exit_code'] = 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally: save()
    if report['exit_code'] == 0:
        spec = dict(sdk_evidence=project.descriptor(evidence), sdk_project=NAME, source_project=str(source),
                    source_manifest=project.descriptor(source / 'openvpn-runtime-source.json'), unsigned_hap=project.descriptor(haps[0]))
        # Actual shared generic verifier must accept our own generated receipt;
        # no Calendar/Media role substitution or synthesized build success.
        try:
            project.binding(spec)
            project.write(output / 'project-inputs.json', spec)
        except (ValueError, OSError, KeyError, TypeError) as error:
            report['exit_code'] = 1; report['failures'].append('actual SDK/HAP source binding: ' + str(error)); save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('project', 'sdk', 'node', 'ohpm', 'hvigor', 'hvigor-cache', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--ohpm-cache', type=Path); parser.add_argument('--execute-sdk-build', action='store_true')
    result = build(parser.parse_args()); print(json.dumps({'exit_code': result['exit_code'], 'failures': result['failures']}))
    raise SystemExit(result['exit_code'])
