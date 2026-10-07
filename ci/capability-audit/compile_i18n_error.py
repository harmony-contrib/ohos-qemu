#!/usr/bin/env python3
"""Compile the I18n BusinessError repair with actual product Ninja arguments.

Only scratch sources/objects are written. Neither the live source/output tree
nor an installed guest library is modified; this is not runtime acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import tarfile


def stage_missing_png_dependency(root, staged, cwd, command):
    """Run the pinned PNG preparation in scratch, never borrow another ABI's out.

    These products have GN commands but have not yet run the libpng extraction
    action. Reproduce its archive/config/patch inputs with strict error handling;
    upstream install.py unfortunately catches patch failures and returns zero.
    """
    include = next((token for token in command if token.rstrip('/') ==
                    '-Igen/third_party/libpng/libpng-1.6.55'), None)
    if include is None or (cwd / include[2:] / 'png.h').is_file():
        return None
    component = root / 'third_party/libpng'
    generated = staged / 'png-gen'
    generated.mkdir()
    archive = component / 'libpng-1.6.55.tar.gz'
    with tarfile.open(archive) as compressed:
        compressed.extractall(generated, filter='data')
    prepared = generated / 'libpng-1.6.55'
    config = component / 'pnglibconf.h'
    shutil.copy2(config, prepared / config.name)
    inputs = [archive, config]
    for name in ('huawei_libpng_CMakeList.patch', 'libpng-fix-arm-neon.patch', 'libpng-multilib.patch',
                 'backport-libpng-1.6.37-enable-valid.patch', 'CVE-2018-14048.patch', 'libpng_optimize.patch'):
        patch = component / name
        inputs.append(patch)
        subprocess.run(['patch', '-p1', '--fuzz=0', '--no-backup-if-mismatch',
                        '-i', str(patch), '-d', str(prepared)], check=True, capture_output=True)
    command[command.index(include)] = '-I' + str(prepared)
    return {
        'scope': 'scratch_pinned_libpng_dependency_preparation_not_product_build',
        'inputs': {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
        'headers': {name: hashlib.sha256((prepared / name).read_bytes()).hexdigest()
                    for name in ('png.h', 'pngconf.h', 'pnglibconf.h')},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', choices=('arm64_virt', 'armv7a_virt', 'x86_64_virt'), required=True)
    parser.add_argument('--patch', type=Path, required=True)
    parser.add_argument('--kind', choices=('helper', 'setters'), default='helper')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    cwd = root / 'out' / args.product
    relative = Path('base/global/i18n/interfaces/js')
    if args.kind == 'helper':
        source = relative / 'innerkits/intl/src/error_util.cpp'
        target = 'obj/' + str(relative / 'innerkits/intl/src/intl_napi/error_util.o')
    else:
        source = relative / 'kits/src/i18n_system_addon.cpp'
        target = 'obj/' + str(relative / 'kits/src/i18n/i18n_system_addon.o')
    commands = subprocess.run([
        str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'), '-w', 'dupbuild=warn',
        '-C', str(cwd), '-t', 'commands', target,
    ], capture_output=True, text=True, check=True)
    command = shlex.split(commands.stdout.splitlines()[-1])
    if Path(command[0]).name == 'ccache':
        command.pop(0)
    if Path(command[0]).name != 'clang++' or any(token in command for token in ('&&', ';', '|')):
        raise ValueError('expected one product clang++ command')
    index = command.index('-c') + 1
    if (cwd / command[index]).resolve() != root / source:
        raise ValueError('unexpected I18n error helper source')
    patch = args.patch.resolve()
    with tempfile.TemporaryDirectory(prefix='qemu-i18n-error-compile-') as directory:
        staged = Path(directory)
        shutil.copytree(root / relative, staged / relative, symlinks=True)
        subprocess.run(['git', '-C', str(staged), 'apply', '--ignore-space-change', str(patch)], check=True)
        candidate = staged / source
        command[index] = str(candidate)
        object_path = staged / 'error_util.o'
        command[command.index('-o') + 1] = str(object_path)
        command[command.index('-MF') + 1] = str(staged / 'error_util.d')
        png_dependency = stage_missing_png_dependency(root, staged, cwd, command)
        subprocess.run(command, cwd=cwd, check=True)
        result = {
            'product': args.product, 'kind': args.kind, 'status': 'pass', 'scope': 'compile_only_not_runtime',
            'patch_sha256': hashlib.sha256(patch.read_bytes()).hexdigest(),
            'source_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
            'object_sha256': hashlib.sha256(object_path.read_bytes()).hexdigest(),
            'compiler_args_sha256': hashlib.sha256(json.dumps(command).encode()).hexdigest(),
            'scratch_dependency_preparation': png_dependency,
        }
    content = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    print(content, end='')


if __name__ == '__main__':
    main()
