#!/usr/bin/env python3
"""Full phone preload/load/GN and DSP library link in a new isolated source tree.

Production sources/outputs must be mounted read-only. This does not package or
boot a QEMU artifact, change a live product graph, or pass the first-package gate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

DSP = 'foundation/multimedia/audio_framework'
WINDOW = 'foundation/window/window_manager/etc'
TARGET = 'qemu_audio_suite_dsp'


def validate_isolation(root, staged):
    if staged == root or staged.is_relative_to(root) or root.is_relative_to(staged):
        raise ValueError('scratch source must be separate from the production source')
    for path in (root, root / 'out'):
        if not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise ValueError('production source and out must both be mounted read-only')


def skeleton_foundation(root, staged):
    # The component loader walks directories without following child symlinks.
    # Preserve real directories for every component; link only read-only files.
    # The two writable subtrees are copied separately, never linked to live data.
    omitted = {root / DSP, root / WINDOW}

    def ignore(directory, names):
        return [name for name in names if Path(directory) / name in omitted]

    def link(source, destination):
        os.symlink(source, destination)
        return destination

    shutil.copytree(root / 'foundation', staged / 'foundation', symlinks=True,
                    copy_function=link, ignore=ignore)
    for relative in (DSP, WINDOW):
        shutil.copytree(root / relative, staged / relative, symlinks=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--product', choices=('arm64_virt', 'armv7a_virt', 'x86_64_virt'), required=True)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--compile', action='store_true')
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    root, repo = args.source_root.resolve(), args.repo_root.resolve()
    staged = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix='audio-dsp-full-gn-'))
    validate_isolation(root, staged)
    staged.mkdir(parents=True, exist_ok=True)
    if any(staged.iterdir()) or args.jobs < 1:
        raise ValueError('scratch source must be empty and jobs positive')
    copied = {'build', 'vendor', 'productdefine', 'drivers'}
    excluded = copied | {'out', 'foundation', '.gn', '.ohos-qemu-patches', '.ccache'}
    for child in root.iterdir():
        if child.name not in excluded:
            (staged / child.name).symlink_to(child, target_is_directory=child.is_dir())
    for name in copied:
        shutil.copytree(root / name, staged / name, symlinks=True)
    shutil.copy2(root / '.gn', staged / '.gn')
    skeleton_foundation(root, staged)
    subprocess.run(['bash', str(repo / 'patches/common/build/notice/readonly_input/apply.sh'),
                    '--source-root', str(staged)], check=True)
    subprocess.run(['bash', str(repo / 'patches/common/foundation/multimedia/audio_framework/audio_suite_dsp/apply.sh'),
                    '--source-root', str(staged)], check=True)
    subprocess.run(['bash', str(repo / 'patches/common/vendor/ohemu/camera_profile/apply.sh'),
                    '--source-root', str(staged)], check=True)
    subprocess.run(['bash', str(repo / 'patches/common/drivers/peripheral/camera/usb_backend/apply.sh'),
                    '--source-root', str(staged)], check=True)
    subprocess.run(['bash', str(repo / 'patches/common/drivers/peripheral/camera/vivid_capture/apply.sh'),
                    '--source-root', str(staged)], check=True)
    subprocess.run(['bash', str(repo / 'patches/2in1/product_profile/apply.sh'), '--source-root', str(staged),
                    '--disable', '--product', args.product], check=True)
    subprocess.run(['bash', str(repo / 'patches/phone/product_profile/apply.sh'), '--source-root', str(staged),
                    '--product', args.product], check=True)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    environment['PATH'] = str(root / 'prebuilts/build-tools/linux-x86/bin') + os.pathsep + environment['PATH']
    python = root / 'prebuilts/python/linux-x86/3.11.4/bin/python3'
    if not python.is_file():
        python = Path(sys.executable)
    command = [str(python), str(staged / 'build/hb/main.py'), 'build', '--no-indep',
               '--product-name', args.product, '--prebuilt-sdk=true', '--build-target',
               TARGET, '--build-only-gn', '--ccache=false', '--gn-args', 'device_type="phone"']
    log = staged / 'audio-dsp-full-gn.log'
    with log.open('w') as stream:
        generated = subprocess.run(command, cwd=staged, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    result = {'scope': 'isolated_full_preload_load_GN_and_optional_DSP_link_not_QEMU_acceptance',
              'product': args.product, 'device': 'phone', 'scratch_source': str(staged),
              'gn_command': command, 'gn_exit_code': generated.returncode,
              'gn_log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
              'first_artifact_behavior_gate_passed': False}
    code = generated.returncode
    if code == 0 and args.compile:
        # Match the fixed hb/services/ninja.py invocation, not a local bypass.
        command = [str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'), '-w', 'dupbuild=warn',
                   '-C', str(staged / 'out' / args.product),
                   '-j', str(args.jobs), TARGET]
        link_log = staged / 'audio-dsp-link.log'
        with link_log.open('w') as stream:
            linked = subprocess.run(command, cwd=staged, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        code = linked.returncode
        result.update(link_command=command, link_exit_code=code,
                      link_log_sha256=hashlib.sha256(link_log.read_bytes()).hexdigest())
        library = staged / 'out' / args.product / 'multimedia/audio_framework/libqemu_audio_suite_dsp.z.so'
        if code == 0:
            if not library.is_file() or not library.stat().st_size:
                raise ValueError('Ninja succeeded without the expected actual DSP shared library')
            result.update(library=str(library), library_sha256=hashlib.sha256(library.read_bytes()).hexdigest())
    (staged / 'audio-dsp-build-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    print(log.read_text()[-6000:])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
