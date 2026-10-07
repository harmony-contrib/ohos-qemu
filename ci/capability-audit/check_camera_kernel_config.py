#!/usr/bin/env python3
"""Resolve real Vivid capture dependencies in the pinned Linux Kconfig.

This is isolated Kconfig validation, not a kernel build or captured frame.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

CONFIG_DIR = Path('device/qemu/common/virt_full/kernel')
ARCHITECTURES = {
    'arm64': ('arm64_virt_defconfig', 'aarch64',
              'gcc-linaro-7.5.0-2019.12-x86_64_aarch64-linux-gnu', 'aarch64-linux-gnu-'),
    'arm': ('arm_virt_defconfig', 'arm', 'gcc-linaro-7.5.0-arm-linux-gnueabi', 'arm-linux-gnueabi-'),
    'x86_64': ('x86_64_virt_defconfig', '', '', ''),
}
REQUIRED = dict.fromkeys(('CONFIG_MEDIA_SUPPORT', 'CONFIG_MEDIA_CAMERA_SUPPORT',
                         'CONFIG_MEDIA_TEST_SUPPORT', 'CONFIG_VIDEO_DEV', 'CONFIG_V4L_TEST_DRIVERS',
                         'CONFIG_VIDEO_VIVID', 'CONFIG_VIDEOBUF2_VMALLOC', 'CONFIG_VIDEOBUF2_DMA_CONTIG',
                         'CONFIG_VIDEO_V4L2_TPG', 'CONFIG_MEDIA_CONTROLLER',
                         'CONFIG_MEDIA_CONTROLLER_REQUEST_API', 'CONFIG_FB', 'CONFIG_HAS_DMA'), 'y')
REQUIRED['CONFIG_VIDEO_VIVID_MAX_DEVS'] = '1'
VIVID_OBJECTS = {'vivid-core.o', 'vivid-ctrls.o', 'vivid-vid-common.o', 'vivid-vbi-gen.o',
                 'vivid-vid-cap.o', 'vivid-vid-out.o', 'vivid-kthread-cap.o', 'vivid-kthread-out.o',
                 'vivid-radio-rx.o', 'vivid-radio-tx.o', 'vivid-radio-common.o', 'vivid-rds-gen.o',
                 'vivid-sdr-cap.o', 'vivid-vbi-cap.o', 'vivid-vbi-out.o', 'vivid-osd.o',
                 'vivid-meta-cap.o', 'vivid-meta-out.o', 'vivid-kthread-touch.o', 'vivid-touch-cap.o'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--compile-vivid', action='store_true',
                        help='Also compile the actual driver objects; still not a booted kernel/API test')
    args = parser.parse_args()
    source, repo = args.source_root.resolve(), args.repo_root.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('release source must be mounted read-only')
    scratch = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix='camera-kconfig-'))
    if scratch == source or source in scratch.parents or scratch in source.parents:
        raise ValueError('scratch must not overlap production source')
    scratch.mkdir(parents=True, exist_ok=True)
    if any(scratch.iterdir()):
        raise ValueError('scratch must be empty')
    staged = scratch / 'source'
    staged.mkdir()
    (staged / '.repo').symlink_to(source / '.repo', target_is_directory=True)
    shutil.copytree(source / 'device/qemu', staged / 'device/qemu', symlinks=True)
    kernel = staged / 'kernel/linux/linux-6.6'
    shutil.copytree(source / 'kernel/linux/linux-6.6', kernel, symlinks=True,
                    copy_function=lambda original, target: os.symlink(original, target))
    # Only the producer defaults are writable; all other existing source files
    # retain their read-only production links. Added common-module dirs are real.
    vivid = Path('drivers/media/test-drivers/vivid/vivid-core.c')
    (kernel / vivid).unlink()
    shutil.copy2(source / 'kernel/linux/linux-6.6' / vivid, kernel / vivid)
    for component in ('common/device/qemu/vivid_capture', 'common/kernel/linux/linux_6_6/vivid_capture'):
        subprocess.run(['bash', str(repo / 'patches' / component / 'apply.sh'),
                        '--source-root', str(staged)], check=True)
    common = source / 'kernel/linux/common_modules'
    for module, relative in (('memory_security', 'fs/proc/memory_security'),
                             ('code_sign', 'fs/code_sign'), ('dec', 'fs/dec'), ('xpm', 'security/xpm'),
                             ('container_escape_detection', 'security/container_escape_detection')):
        shutil.copytree(common / module, kernel / relative, symlinks=True)
    if args.compile_vivid:
        # The fixed board supplies required OpenHarmony headers even for
        # targeted driver preparation. Materialize only its seven actual added
        # headers and page-flags header fix, not HDF/security configuration. No old out
        # headers, stubs, fabricated definitions or writes through source links.
        board_patch = staged / CONFIG_DIR / 'patch/virt.patch'
        names = {'memcheck.h', 'memcg_policy.h', 'mm_purgeable.h', 'reclaim_acct.h',
                 'xpm.h', 'xpm_types.h', 'zswapd.h'}
        sections, found = [], set()
        for section in board_patch.read_text().split('diff --git ')[1:]:
            if '\n+++ b/include/linux/page-flags.h\n' in section:
                path = kernel / 'include/linux/page-flags.h'
                expected = (source / 'kernel/linux/linux-6.6/include/linux/page-flags.h').resolve(strict=True)
                if not path.is_symlink() or path.resolve(strict=True) != expected:
                    raise ValueError('unexpected actual page-flags preimage')
                path.unlink()
                shutil.copy2(expected, path)
                sections.append('diff --git ' + section)
                found.add('page-flags.h')
                continue
            if '\n--- /dev/null\n' not in section or '\n+++ b/include/linux/' not in section:
                continue
            relative = section.split('\n+++ b/', 1)[1].splitlines()[0]
            if relative != 'include/linux/' + Path(relative).name or Path(relative).name not in names:
                raise ValueError('unexpected fixed board kernel header')
            if (kernel / relative).exists() or (kernel / relative).is_symlink():
                raise ValueError('unexpected preexisting staged board header')
            found.add(Path(relative).name)
            sections.append('diff --git ' + section)
        if found != names | {'page-flags.h'} or len(sections) != len(names) + 1:
            raise ValueError('incomplete fixed board kernel header input')
        header_patch = scratch / 'actual-board-added-headers.patch'
        header_patch.write_text(''.join(sections))
        patch_command = ['patch', '--batch', '--fuzz=0', '-d', str(kernel), '-p1', '-i', str(header_patch)]
        subprocess.run(patch_command + ['--dry-run'], check=True)
        subprocess.run(patch_command, check=True)
    results = []
    for arch, (filename, gcc_arch, gcc_directory, prefix) in ARCHITECTURES.items():
        output = scratch / arch
        output.mkdir()
        shutil.copy2(staged / CONFIG_DIR / filename, output / '.config')
        command = ['make', '-C', str(kernel), 'O=' + str(output), 'ARCH=' + arch]
        environment = dict(os.environ)
        if prefix:
            gcc = source / 'prebuilts/gcc/linux-x86' / gcc_arch / gcc_directory / 'bin'
            environment['PATH'] = str(gcc) + os.pathsep + environment['PATH']
            command.append('CROSS_COMPILE=' + prefix)
        command.append('olddefconfig')
        log = scratch / (arch + '-olddefconfig.log')
        with log.open('w') as stream:
            process = subprocess.run(command, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        selected = dict(line.split('=', 1) for line in (output / '.config').read_text().splitlines()
                        if line.startswith('CONFIG_') and '=' in line)
        resolved = {key: selected.get(key, 'not set') for key in REQUIRED}
        results.append({'arch': arch, 'command': command, 'exit_code': process.returncode,
                        'resolved': resolved,
                        'configuration_passed': process.returncode == 0 and resolved == REQUIRED,
                        'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
        if args.compile_vivid and results[-1]['configuration_passed']:
            compile_command = command[:-1] + ['-j2', 'drivers/media/test-drivers/vivid/']
            compile_log = scratch / (arch + '-vivid-compile.log')
            with compile_log.open('w') as stream:
                compiled = subprocess.run(compile_command, env=environment, stdout=stream, stderr=subprocess.STDOUT)
            objects = {}
            machine = {'arm': 40, 'arm64': 183, 'x86_64': 62}[arch]
            for obj in sorted((output / 'drivers/media/test-drivers/vivid').glob('*.o')):
                data = obj.read_bytes()
                if len(data) < 64 or data[:4] != b'\x7fELF' or data[5] != 1 or struct.unpack_from('<H', data, 18)[0] != machine:
                    raise ValueError('wrong actual Vivid object ABI: ' + str(obj))
                objects[obj.name] = hashlib.sha256(data).hexdigest()
            archive = output / 'drivers/media/test-drivers/vivid/built-in.a'
            results[-1]['targeted_driver_compile'] = {
                'command': compile_command, 'exit_code': compiled.returncode, 'objects': objects,
                'log_sha256': hashlib.sha256(compile_log.read_bytes()).hexdigest(),
                'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest() if archive.is_file() else None,
                'passed': compiled.returncode == 0 and VIVID_OBJECTS <= objects.keys() and archive.is_file() and archive.stat().st_size > 0,
                'scope': 'actual_driver_objects_only_not_linked_kernel_or_Camera_frames',
            }
    evidence = {'scope': ('real_Linux_6_6_Kconfig_and_targeted_driver_objects_not_linked_kernel_or_Camera_acceptance'
                          if args.compile_vivid else 'real_Linux_6_6_Kconfig_only_not_kernel_compile_or_Camera_acceptance'),
                'required': REQUIRED, 'results': results, 'first_package_gate_passed': False}
    (scratch / 'camera-kconfig-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
    return 0 if all(item['configuration_passed'] and
                    (not args.compile_vivid or item.get('targeted_driver_compile', {}).get('passed'))
                    for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
