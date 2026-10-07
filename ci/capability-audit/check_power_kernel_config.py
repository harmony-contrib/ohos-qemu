#!/usr/bin/env python3
"""Resolve/compile real Linux power inputs in scratch, never boot evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from check_camera_kernel_config import ARCHITECTURES, CONFIG_DIR

REQUIRED = {'CONFIG_SUSPEND': 'y', 'CONFIG_PM_SLEEP': 'y', 'CONFIG_PM': 'y',
            'CONFIG_PM_WAKELOCKS': 'y', 'CONFIG_PM_WAKELOCKS_LIMIT': '100',
            'CONFIG_PM_WAKELOCKS_GC': 'y'}
COMPONENTS = ('common/device/qemu/power_wakelocks',
              'common/kernel/linux/linux_6_6/qemu_power_button',
              'common/kernel/linux/linux_6_6/qemu_virtio_gpu_s2idle')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolved_config(text):
    result = {}
    for line in text.splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
        elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
            key, value = line[2:-11], 'n'
        else:
            continue
        if key in result:
            raise ValueError('duplicate resolved kernel option: ' + key)
        result[key] = value
    if any(result.get(key) != value for key, value in REQUIRED.items()):
        raise ValueError('real suspend/userspace wakeup-source dependencies are not enabled')
    if result.get('CONFIG_PM_AUTOSLEEP', 'n') != 'n':
        raise ValueError('the repair must not enable opportunistic autosleep')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--compile', action='store_true')
    args = parser.parse_args()
    source, repo = args.source_root.resolve(), args.repo_root.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('production source must be mounted read-only')
    scratch = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix='power-kernel-'))
    if scratch == source or source in scratch.parents or scratch in source.parents:
        raise ValueError('scratch must not overlap production source')
    scratch.mkdir(parents=True, exist_ok=True)
    if any(scratch.iterdir()):
        raise ValueError('scratch must be empty')
    staged = scratch / 'source'
    staged.mkdir()
    kernel = staged / 'kernel/linux/linux-6.6'
    shutil.copytree(source / 'device/qemu', staged / 'device/qemu', symlinks=True)
    shutil.copytree(source / 'kernel/linux/linux-6.6', kernel, symlinks=True,
                    copy_function=lambda original, target: os.symlink(original, target))
    for relative in map(Path, ('drivers/input/keyboard/gpio_keys.c',
                              'drivers/virtio/virtio_pci_common.c',
                              'drivers/virtio/virtio_pci_common.h')):
        (kernel / relative).unlink()
        shutil.copy2(source / 'kernel/linux/linux-6.6' / relative, kernel / relative)
    for component in COMPONENTS:
        subprocess.run(['bash', str(repo / 'patches' / component / 'apply.sh'),
                        '--source-root', str(staged)], check=True)
    common = source / 'kernel/linux/common_modules'
    for name, relative in (('memory_security', 'fs/proc/memory_security'), ('code_sign', 'fs/code_sign'),
                           ('dec', 'fs/dec'), ('xpm', 'security/xpm'),
                           ('container_escape_detection', 'security/container_escape_detection')):
        shutil.copytree(common / name, kernel / relative, symlinks=True)
    if args.compile:
        # Required genuine board headers, not fabricated compiler definitions.
        names = {'memcheck.h', 'memcg_policy.h', 'mm_purgeable.h', 'reclaim_acct.h',
                 'xpm.h', 'xpm_types.h', 'zswapd.h'}
        sections, found = [], set()
        board_patch = staged / CONFIG_DIR / 'patch/virt.patch'
        for section in board_patch.read_text().split('diff --git ')[1:]:
            if '\n+++ b/include/linux/page-flags.h\n' in section:
                target = kernel / 'include/linux/page-flags.h'
                expected = (source / 'kernel/linux/linux-6.6/include/linux/page-flags.h').resolve(strict=True)
                if not target.is_symlink() or target.resolve(strict=True) != expected:
                    raise ValueError('unexpected actual page-flags preimage')
                target.unlink()
                shutil.copy2(expected, target)
                sections.append('diff --git ' + section)
                found.add('page-flags.h')
            elif '\n--- /dev/null\n' in section and '\n+++ b/include/linux/' in section:
                name = section.split('\n+++ b/', 1)[1].splitlines()[0]
                if name != 'include/linux/' + Path(name).name or Path(name).name not in names:
                    raise ValueError('unexpected fixed board added header')
                if (kernel / name).exists() or (kernel / name).is_symlink():
                    raise ValueError('unexpected preexisting board header')
                sections.append('diff --git ' + section)
                found.add(Path(name).name)
        if found != names | {'page-flags.h'}:
            raise ValueError('incomplete genuine board header inputs')
        actual = scratch / 'actual-board-headers.patch'
        actual.write_text(''.join(sections))
        command = ['patch', '--batch', '--fuzz=0', '-d', str(kernel), '-p1', '-i', str(actual)]
        subprocess.run(command + ['--dry-run'], check=True)
        subprocess.run(command, check=True)
    evidence = {'status': 'fail', 'scope': 'real_three_ABI_Kconfig_and_objects_NOT_packaged_boot_or_power_behavior',
                'first_artifact_behavior_gate_passed': False, 'results': [],
                'gpio_keys_source_sha256': sha(kernel / 'drivers/input/keyboard/gpio_keys.c'),
                'virtio_pci_source_sha256': sha(kernel / 'drivers/virtio/virtio_pci_common.c')}
    for arch, (filename, gcc_arch, gcc_directory, prefix) in ARCHITECTURES.items():
        output = scratch / arch
        output.mkdir()
        shutil.copy2(staged / CONFIG_DIR / filename, output / '.config')
        command = ['make', '-C', str(kernel), 'O=' + str(output), 'ARCH=' + arch]
        environment = dict(os.environ)
        if prefix:
            gcc = source / 'prebuilts/gcc/linux-x86' / gcc_arch / gcc_directory / 'bin'
            environment['PATH'] = str(gcc) + os.pathsep + environment['PATH']
            command += ['CROSS_COMPILE=' + prefix]
        row = {'arch': arch, 'commands': [], 'status': 'fail'}
        evidence['results'].append(row)
        try:
            targets = [['olddefconfig']]
            if args.compile:
                targets.append(['-j2', 'kernel/power/wakelock.o', 'drivers/input/keyboard/gpio_keys.o',
                                'drivers/virtio/virtio_pci_common.o'])
                if arch != 'x86_64':
                    targets[-1].append('drivers/gpio/gpio-pl061.o')
            for index, target in enumerate(targets):
                log = scratch / (arch + '-power-' + str(index) + '.log')
                with log.open('w') as stream:
                    result = subprocess.run(command + target, env=environment, stdout=stream, stderr=subprocess.STDOUT)
                row['commands'].append({'argv': command + target, 'exit_code': result.returncode,
                                        'log': str(log), 'sha256': sha(log)})
                if result.returncode:
                    raise ValueError('real kernel Kconfig/targeted compile failed')
                selected = resolved_config((output / '.config').read_text())
                row['resolved'] = {key: selected[key] for key in REQUIRED}
            if args.compile:
                objects = ['kernel/power/wakelock.o', 'drivers/input/keyboard/gpio_keys.o',
                           'drivers/virtio/virtio_pci_common.o']
                if arch != 'x86_64':
                    objects.append('drivers/gpio/gpio-pl061.o')
                row['objects'] = {}
                for name in objects:
                    path = output / name
                    data = path.read_bytes()
                    if (data[:4] != b'\x7fELF' or data[5] != 1 or struct.unpack_from('<H', data, 18)[0] !=
                            {'arm64': 183, 'arm': 40, 'x86_64': 62}[arch]):
                        raise ValueError('wrong actual kernel object ABI')
                    row['objects'][name] = sha(path)
            row['status'] = 'pass'
        except (OSError, ValueError) as error:
            row['failure'] = str(error)
    if all(row['status'] == 'pass' for row in evidence['results']):
        evidence['status'] = 'pass'
    (scratch / 'power-kernel-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
