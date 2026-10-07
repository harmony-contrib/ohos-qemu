#!/usr/bin/env python3
"""Resolve candidate USB-serial settings with the actual Linux 6.6 Kconfig.

This checks dependency resolution, not compilation, guest discovery, or I/O.
It never runs the board build script or modifies production source/output.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

CONFIG_DIR = Path('device/qemu/common/virt_full/kernel')
ARCHITECTURES = {
    'arm64': ('arm64_virt_defconfig', 'aarch64',
              'gcc-linaro-7.5.0-2019.12-x86_64_aarch64-linux-gnu', 'aarch64-linux-gnu-'),
    'arm': ('arm_virt_defconfig', 'arm', 'gcc-linaro-7.5.0-arm-linux-gnueabi', 'arm-linux-gnueabi-'),
    'x86_64': ('x86_64_virt_defconfig', '', '', ''),
}
REQUIRED = ('CONFIG_USB_SERIAL', 'CONFIG_USB_SERIAL_FTDI_SIO',
            'CONFIG_USB_XHCI_HCD', 'CONFIG_USB_XHCI_PCI')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    source = args.source_root.resolve()
    repo = args.repo_root.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('release source must be mounted read-only')
    scratch = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix='serial-kconfig-'))
    if scratch == source or source in scratch.parents or scratch in source.parents:
        raise ValueError('work directory must be outside production source')
    scratch.mkdir(parents=True, exist_ok=True)
    if any(scratch.iterdir()):
        raise ValueError('work directory must be empty')
    configs = scratch / 'source' / CONFIG_DIR
    configs.mkdir(parents=True)
    for filename, _, _, _ in ARCHITECTURES.values():
        shutil.copy2(source / CONFIG_DIR / filename, configs / filename)
    subprocess.run(['bash', str(repo / 'patches/2in1/device/qemu/serial_usb_endpoint/apply.sh'),
                    '--source-root', str(scratch / 'source')], check=True)
    # Fixed Linux Kconfig references directories installed by build_kernel.sh.
    # Stage the real directories; retain all unchanged kernel files read-only.
    kernel = scratch / 'kernel'
    shutil.copytree(source / 'kernel/linux/linux-6.6', kernel, symlinks=True,
                    copy_function=lambda original, target: os.symlink(original, target))
    common = source / 'kernel/linux/common_modules'
    for module, relative in (('memory_security', 'fs/proc/memory_security'),
                             ('code_sign', 'fs/code_sign'), ('dec', 'fs/dec'),
                             ('xpm', 'security/xpm'),
                             ('container_escape_detection', 'security/container_escape_detection')):
        shutil.copytree(common / module, kernel / relative, symlinks=True)
    results = []
    for arch, (filename, gcc_arch, gcc_directory, prefix) in ARCHITECTURES.items():
        output = scratch / arch
        output.mkdir()
        shutil.copy2(configs / filename, output / '.config')
        command = ['make', '-C', str(kernel),
                   'O=' + str(output), 'ARCH=' + arch]
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
        passed = process.returncode == 0 and all(value == 'y' for value in resolved.values())
        results.append({'arch': arch, 'command': command, 'exit_code': process.returncode,
                        'resolved': resolved, 'configuration_passed': passed,
                        'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
    evidence = {'scope': 'linux_6_6_kconfig_only_not_kernel_build_or_runtime_acceptance',
                'results': results, 'first_package_gate_passed': False}
    (scratch / 'serial-kconfig-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))
    return 0 if all(item['configuration_passed'] for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
