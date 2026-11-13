#!/usr/bin/env python3
"""Export source-only candidates from a read-only prepared OHOS tree.

Every omission is recorded. This does not publish, build, or claim that the
entire legacy patch stack has been migrated. Generated outputs are not sources.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

GENERATED_PROJECTS = {'third_party_cups-filters', 'third_party_sane-airscan',
    'third_party_freetype', 'third_party_tzdata', 'third_party_libvpx'}
GENERATED_PARTS = {'.hvigor', 'out', 'node_modules', 'oh_modules', '__pycache__',
    'legacy_bin', 'qemu_llvm', 'qemu_llvm_build', 'build-ohos-armv7a-qemu-source-21.3.3',
    'build-ohos-qemu-source-21.3.3-fixed'}
BINARY_SUFFIXES = {'.hap', '.har', '.app', '.p7b', '.p12', '.jks', '.so', '.a', '.o',
    '.jar', '.ttf', '.mp4', '.zip', '.tgz', '.gz', '.bz2', '.xz', '.onnx', '.profdata'}


def reason(project, name, untracked):
    path = Path(name)
    if project in GENERATED_PROJECTS:
        return 'upstream build-generated/extracted tree; no QEMU patch owner'
    if GENERATED_PARTS.intersection(path.parts) or (untracked and 'build' in path.parts):
        return 'build/cache output'
    if path.suffix in BINARY_SUFFIXES or path.name in ('local.properties', 'BuildProfile.ets'):
        return 'binary dependency, signing output or host-local configuration'
    if path.suffix in ('.cmd', '.d', '.order', '.rej', '.pyc') or path.name.endswith('.lock'):
        return 'build or patch process output'
    if path.name == 'package-lock.json':
        return 'dependency installation output; review separately'
    if '/generated/' in name and project == 'arkui_ace_engine':
        return 'generated ArkUI interface output; migrate its generator instead'
    if name == 'virt/hdf_config/khdf/.hdf_hcs_hex.o.d':
        return 'kernel compiler dependency output'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Fresh export directory required; preserve earlier evidence')
    args.output.mkdir(parents=True)
    summaries = []
    for project in json.loads(args.inventory.read_text())['projects']:
        if 'error' in project:
            summaries.append(dict(name=project['name'], error=project['error']))
            continue
        root = args.root / project['path']
        selected, omitted = [], []
        for name in project['tracked_changes']:
            excluded = reason(project['name'], name, False)
            path = root / name
            if not excluded and path.is_file() and not path.is_symlink():
                # Restored former-LFS assets can be text files with arbitrary
                # suffixes. Keep their binary/data provenance separate.
                original = subprocess.check_output(['git', '-c', 'safe.directory=*',
                    '-C', str(root), 'show', 'HEAD:' + name])
                if b'version https://git-lfs.github.com/spec/v1' in original[:200]:
                    excluded = 'restored upstream LFS asset; not a source patch'
            if excluded:
                omitted.append(dict(path=name, reason=excluded))
            else:
                selected.append(name)
        files = []
        for entry in project['untracked']:
            name = entry['path']
            excluded = reason(project['name'], name, True)
            if excluded:
                omitted.append(dict(path=name, reason=excluded))
            else:
                files.append(name)
        if not selected and not files:
            if omitted:
                summaries.append(dict(name=project['name'], source_changes=0, omitted=omitted))
            continue
        destination = args.output / project['name']
        destination.mkdir()
        environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
        with (destination / 'tracked.patch').open('wb') as stream:
            subprocess.run(['git', '-c', 'safe.directory=*', '-c', 'filter.lfs.required=false',
                '-c', 'filter.lfs.clean=', '-c', 'filter.lfs.process=', '-C', str(root),
                'diff', '--binary', '--no-ext-diff', '--no-textconv', 'HEAD', '--', *selected],
                stdout=stream, env=environment, check=True) if selected else None
        copied = []
        for name in files:
            source, target = root / name, destination / 'files' / name
            if source.is_symlink():
                link = os.readlink(source)
                if os.path.isabs(link):
                    omitted.append(dict(path=name, reason='absolute host symlink'))
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(link)
                copied.append(dict(path=name, symlink=link))
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied.append(dict(path=name, sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                                   mode=oct(target.stat().st_mode & 0o777)))
        record = dict(name=project['name'], path=project['path'], upstream_revision=project['head'],
                      tracked=selected, added=copied, omitted=omitted,
                      scope='source_candidates_NOT_build_or_runtime_validation')
        (destination / 'export.json').write_text(json.dumps(record, indent=2) + '\n')
        summaries.append(dict(name=project['name'], source_changes=len(selected) + len(copied),
                              omitted_count=len(omitted)))
        print(project['name'] + ': exported ' + str(len(selected) + len(copied)) + ' source candidates', flush=True)
    (args.output / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')


if __name__ == '__main__':
    main()
