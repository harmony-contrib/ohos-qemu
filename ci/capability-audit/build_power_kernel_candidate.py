#!/usr/bin/env python3
"""Link an isolated power diagnosis kernel from a stopped package build seed.

This saves repeating an entire OS build while diagnosing suspend/wakeup. It
does not rebuild the package or satisfy the required first-artifact gate.
Production source/output are read-only and remain untouched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from check_power_kernel_config import REQUIRED, resolved_config
from check_camera_kernel_config import ARCHITECTURES
from compile_camera_component import assert_seed_inactive


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--seed-kernel', type=Path, required=True)
    parser.add_argument('--seed-image-sha256', required=True)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--with-binder-async-sender', action='store_true',
                        help='include the approved trusted asynchronous identity repair; still diagnostic only')
    args = parser.parse_args()
    source, seed, repo, output = (path.resolve() for path in
        (args.source_root, args.seed_kernel, args.repo_root, args.output))
    for path in (source, seed):
        if not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise ValueError('production source and seed output must be mounted read-only')
    for path in (source, seed, repo):
        if path == output or path in output.parents or output in path.parents:
            raise ValueError('owned output must not overlap any input')
    image = seed / 'arch/arm64/boot/Image'
    assert_seed_inactive(seed)
    if sha(image) != args.seed_image_sha256:
        raise ValueError('stopped seed kernel does not match the actual diagnostic package Image')
    output.mkdir(parents=True, exist_ok=False)
    evidence = {'schema_version': 1, 'status': 'fail',
        'scope': 'isolated_ARM64_power_kernel_link_NOT_new_package_or_behavior_acceptance',
        'first_artifact_behavior_gate_passed': False,
        'seed': str(seed), 'seed_image_sha256': sha(image),
        'seed_config_sha256': sha(seed / '.config'), 'commands': [], 'failures': []}

    def command(argv, label, cwd=None, env=None):
        log = output / (label + '.log')
        with log.open('w') as stream:
            result = subprocess.run(list(map(str, argv)), cwd=cwd, env=env,
                                    stdout=stream, stderr=subprocess.STDOUT, check=False)
        evidence['commands'].append({'argv': list(map(str, argv)), 'exit_code': result.returncode,
                                     'log': str(log), 'sha256': sha(log)})
        if result.returncode:
            raise ValueError('actual isolated kernel preparation/link failed: ' + label)

    try:
        # Kernel staging has relative links to genuine HDF/QoS source inputs.
        # Materialize those read-only files: copying the links into a shallower
        # directory would break their targets, and building through live links
        # would not give this attempt ownership of generated outputs.
        staged = output / 'source'
        kernel = staged / 'kernel/linux/linux-6.6'
        for directory, children, names in os.walk(seed, followlinks=False):
            for name in children + names:
                original = Path(directory) / name
                if original.is_symlink():
                    resolved = original.resolve(strict=True)
                    if not os.statvfs(resolved).f_flag & os.ST_RDONLY:
                        raise ValueError('seed link references a mutable production input')
        shutil.copytree(seed, kernel, symlinks=False)
        # Preserve the genuine HDF source/product layout: its Makefiles derive
        # PRODUCT_PATH from the real adapter directory, not the kernel link.
        # All possible HDF/vendor object destinations stay owned and writable;
        # the original shared source is still read-only.
        hdf_source = source / 'drivers/hdf_core'
        shutil.copytree(hdf_source, staged / 'drivers/hdf_core', symlinks=False,
                        ignore=shutil.ignore_patterns('.git'))
        shutil.copytree(source / 'vendor/ohemu/virt', staged / 'vendor/ohemu/virt', symlinks=False,
                        ignore=shutil.ignore_patterns('.git'))
        preserved = output / 'materialized-seed-hdf'
        preserved.mkdir()
        for name in ('drivers/hdf/khdf', 'drivers/hdf/framework', 'drivers/hdf/inner_api', 'include/hdf'):
            original = seed / name
            if not original.is_symlink():
                raise ValueError('unknown kernel HDF staging link: ' + name)
            target = original.resolve(strict=True)
            relative = target.relative_to(hdf_source)
            shutil.move(str(kernel / name), str(preserved / name.replace('/', '-')))
            os.symlink(staged / 'drivers/hdf_core' / relative, kernel / name)
        for name in ('prebuilts', 'third_party', 'base', 'utils'):
            if (source / name).is_dir():
                os.symlink(source / name, staged / name)
        mutable = ('drivers/input/keyboard/gpio_keys.c', '.config')
        if any((kernel / name).is_symlink() for name in mutable):
            raise ValueError('unexpected mutable seed input symlink')
        patch = repo / 'patches/common/kernel/linux/linux_6_6/qemu_power_button'
        evidence['power_button_patch_sha256'] = sha(patch / '0001-mark-only-virt-platform-power-button-as-wakeup-source.patch')
        command(['bash', patch / 'apply.sh', '--source-root', staged], 'apply-real-wake-source')
        evidence['gpio_keys_source_sha256'] = sha(kernel / mutable[0])
        gpu_patch = repo / 'patches/common/kernel/linux/linux_6_6/qemu_virtio_gpu_s2idle'
        evidence['virtio_gpu_s2idle_patch_sha256'] = sha(gpu_patch / '0001-preserve-qemu-virtio-gpu-queues-during-s2idle.patch')
        command(['bash', gpu_patch / 'apply.sh', '--source-root', staged], 'apply-real-gpu-s2idle-state')
        evidence['virtio_pci_source_sha256'] = sha(kernel / 'drivers/virtio/virtio_pci_common.c')
        if args.with_binder_async_sender:
            binder_patch = repo / 'patches/common/kernel/linux/linux_6_6/binder_async_sender'
            evidence['binder_async_sender_patch_sha256'] = sha(
                binder_patch / '0001-preserve-kernel-trusted-oneway-sender-identity.patch')
            evidence['binder_async_sender_component_sha256'] = {
                str(path.relative_to(binder_patch)): sha(path)
                for path in sorted(binder_patch.iterdir()) if path.is_file()}
            command(['bash', binder_patch / 'apply.sh', '--source-root', staged], 'apply-trusted-binder-async-sender')
            evidence['binder_source_sha256'] = sha(kernel / 'drivers/android/binder.c')
            command(['bash', kernel / 'scripts/config', '--file', kernel / '.config',
                     '--enable', 'BINDER_SENDER_INFO'], 'set-BINDER_SENDER_INFO')
        for key, value in REQUIRED.items():
            if key in ('CONFIG_PM_SLEEP', 'CONFIG_PM'):
                continue  # Derived by real Kconfig, never faked into headers.
            option = key.removeprefix('CONFIG_')
            argv = ['bash', kernel / 'scripts/config', '--file', kernel / '.config']
            argv += ['--enable', option] if value == 'y' else ['--set-val', option, value]
            command(argv, 'set-' + option)
        _, gcc_arch, gcc_directory, _ = ARCHITECTURES['arm64']
        gcc = source / 'prebuilts/gcc/linux-x86' / gcc_arch / gcc_directory / 'bin'
        if not (gcc / 'aarch64-linux-gnu-gcc').is_file():
            raise ValueError('fixed-release actual GCC cross compiler missing')
        environment = dict(os.environ, PATH=str(gcc) + os.pathsep + os.environ.get('PATH', ''),
                           PRODUCT_PATH='vendor/ohemu/virt', OHOS_SOURCE_ROOT=str(staged))
        make = ['make', '-j2', 'ARCH=arm64', 'CROSS_COMPILE=aarch64-linux-gnu-']
        command(make + ['olddefconfig'], 'real-olddefconfig', cwd=kernel, env=environment)
        selected = resolved_config((kernel / '.config').read_text())
        if args.with_binder_async_sender and selected.get('CONFIG_BINDER_SENDER_INFO') != 'y':
            raise ValueError('actual Binder sender-info support is not enabled')
        evidence['resolved'] = {key: selected[key] for key in REQUIRED}
        command(make + ['Image'], 'real-Image-link', cwd=kernel, env=environment)
        candidate = kernel / 'arch/arm64/boot/Image'
        with candidate.open('rb') as stream:
            header = stream.read(64)
        if header[56:60] != b'ARM\x64' or sha(candidate) == evidence['seed_image_sha256']:
            raise ValueError('candidate is not a newly linked ARM64 kernel Image')
        shutil.copy2(candidate, output / 'Image')
        evidence.update(status='pass', image=str(output / 'Image'), image_sha256=sha(output / 'Image'),
                        image_size=candidate.stat().st_size, config_sha256=sha(kernel / '.config'))
        if sha(image) != evidence['seed_image_sha256'] or sha(seed / '.config') != evidence['seed_config_sha256']:
            raise ValueError('read-only seed identity changed during candidate build')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        evidence['status'] = 'fail'
        evidence['failures'].append(str(error))
    finally:
        (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({key: evidence.get(key) for key in ('status', 'image_sha256', 'failures')}))
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
