#!/usr/bin/env python3
"""Compile the real failing browser TU with its exact GN command in owned output."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[2]
RELATIVE = 'src/arkweb/chromium_ext/media/base/ohos/buffer_request_config_adapter_impl'
PATCH = 'patches/common/web/arkweb/m144_private_contract/0004-keep-request-timestamp-helper-out-of-release-vtable.patch'
TARGET = 'obj/content/browser/browser/buffer_request_config_adapter_impl.o'
REVISION = 'f3d904432cc1c57468f2b7fe01979d25e0157581'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    root, work = args.source_root.resolve(), args.work.resolve()
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError('source/output must be read-only')
    if work == root or work.is_relative_to(root) or root.is_relative_to(work):
        raise ValueError('owned output overlaps production')
    if subprocess.check_output(['git', '-C', str(root / 'src/arkweb'), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('fixed ArkWeb revision differs')
    work.mkdir(parents=True, exist_ok=False)
    evidence = {'scope': 'real_arm64_browser_translation_unit_NOT_link_HAP_or_guest', 'status': 'fail',
                'first_artifact_behavior_gate_passed': False, 'revision': REVISION, 'commands': [], 'inputs': {}}

    def run(argv, name, cwd=None):
        log = work / (name + '.log')
        with log.open('x') as stream:
            completed = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        evidence['commands'].append({'argv': argv, 'cwd': str(cwd) if cwd else None,
                                     'exit_code': completed.returncode, 'log': str(log), 'log_sha256': sha(log)})
        if completed.returncode:
            raise RuntimeError(name + ' failed')

    try:
        candidate = work / 'candidate'
        for suffix in ('.h', '.cc'):
            source = root / (RELATIVE + suffix)
            original = subprocess.check_output(['git', '-C', str(root / 'src/arkweb'),
                'show', 'HEAD:' + str(source.relative_to(root / 'src/arkweb'))])
            if source.read_bytes() != original:
                raise ValueError('unexpected edit in failing source input: ' + suffix)
            target = candidate / (RELATIVE + suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            evidence['inputs'][RELATIVE + suffix] = sha(target)
        frozen_patch = work / 'fix.patch'
        shutil.copy2(REPO / PATCH, frozen_patch)
        evidence['patch_sha256'] = sha(frozen_patch)
        run(['git', '-C', str(candidate), 'apply', '--check', str(frozen_patch)], 'patch-check')
        run(['git', '-C', str(candidate), 'apply', str(frozen_patch)], 'patch-apply')
        cwd = root / 'src/out/rk3568_64'
        ninja = root / 'src/third_party/depot_tools/ninja'
        commands = subprocess.run([str(ninja), '-C', str(cwd), '-t', 'commands', '-s', TARGET],
                                  text=True, capture_output=True, check=True)
        argv = shlex.split(commands.stdout.splitlines()[-1])
        if Path(argv[0]).name != 'clang++' or (cwd / argv[argv.index('-c') + 1]).resolve() != root / (RELATIVE + '.cc'):
            raise ValueError('unexpected actual browser compiler/source')
        argv[argv.index('-c') + 1] = str(candidate / (RELATIVE + '.cc'))
        output = work / 'buffer_request_config_adapter_impl.o'
        argv[argv.index('-o') + 1] = str(output)
        argv[argv.index('-MF') + 1] = str(output.with_suffix('.d'))
        run(argv, 'actual-browser-compile', cwd)
        evidence['patched_header_sha256'] = sha(candidate / (RELATIVE + '.h'))
        evidence['object_sha256'] = sha(output)
        evidence['object_size'] = output.stat().st_size
        evidence['status'] = 'pass'
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        evidence['error'] = str(error)
    (work / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'status': evidence['status'], 'error': evidence.get('error')}))
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
