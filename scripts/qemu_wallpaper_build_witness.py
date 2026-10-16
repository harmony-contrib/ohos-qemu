#!/usr/bin/env python3
"""Bind the actual QEMU Wallpaper fallback graph, fresh build and image DSO."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import struct
import subprocess
import tempfile
import time

from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_runtime_elf_contract import read_elf

ROOT = Path(__file__).resolve().parents[1]
BASE = 'base/theme/wallpaper_mgr'
LIBRARY = 'libwallpaper_service.z.so'
GRAPH = 'obj/' + BASE + '/services/wallpaper_service.ninja'
UNITS = ['obj/' + BASE + '/services/src/wallpaper_service/' + name + '.o' for name in
         ('wallpaper_service', 'wallpaper_extension_ability_connection')]
PRODUCTS = {'arm64_virt': (2, 183, 'aarch64'), 'armv7a_virt': (1, 40, 'arm'), 'x86_64_virt': (2, 62, 'x86_64')}
COMPONENT = ROOT / 'patches/common' / BASE / 'qemu_renderer'
FILES = {
    BASE + '/services/BUILD.gn': '3308963b13350d8ab5d19965a94d244a1ab98dda7141d518b4225ac8ca74d824',
    BASE + '/services/src/wallpaper_service.cpp': '5590864bd8e51f2223e03bc709207c1a1619d36abcf0b812f31ec67e0c47f1c4',
    BASE + '/wallpaper.gni': 'd727530a2f509b8e17f06b9c20cac2fc0a5489de3e0d59a13d74542a561d4033',
    BASE + '/services/src/wallpaper_extension_ability_connection.cpp': '1870196dae94f714357da2532de88c55f8b020bcb6bf105b86c3dbdc0edb317d',
}
PAYLOADS = {'graph.ninja', 'compile-commands.json', 'theme-service-args.txt', LIBRARY, 'witness.json', 'build-log.txt'}


def regular(path):
    path = Path(path)
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('actual regular Wallpaper evidence required: ' + str(path))
    return path


def recipe():
    files = [Path(__file__), ROOT / 'scripts/verify_runtime_elf_contract.py']
    files += [p for p in COMPONENT.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    return {str(p.relative_to(ROOT)): file_sha256(p) for p in sorted(files)}


def outputs(product):
    libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
    return UNITS + ['theme/wallpaper_mgr/' + LIBRARY, 'lib.unstripped/theme/wallpaper_mgr/' + LIBRARY,
                    'packages/phone/system/' + libdir + '/' + LIBRARY]


def write(path, value):
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8))
    with temporary.open('x') as stream: json.dump(value, stream, indent=2); stream.write('\n')
    os.replace(temporary, path)


def source_check(source):
    if {name: file_sha256(regular(source / name)) for name in FILES} != FILES:
        raise ValueError('complete fixed Wallpaper source/fallback composition required')


def begin(source, product):
    source_check(source); build = source / 'out' / product
    nonce = secrets.token_hex(16); archive = build / '.qemu-wallpaper-witness' / nonce
    archive.mkdir(parents=True)
    value = dict(schema_version=1, phase='prepared', product=product, nonce=nonce,
                 source_sha256=FILES, recipe=recipe(), start_ns=time.time_ns(), preserved={})
    for name in outputs(product) + ['qemu-wallpaper-build-witness.json']:
        path = build / name
        if path.exists() or path.is_symlink():
            regular(path); destination = archive / name; destination.parent.mkdir(parents=True, exist_ok=True)
            value['preserved'][name] = dict(path=str(destination), sha256=file_sha256(path))
            os.replace(path, destination)
    write(archive / 'prepared.json', value); write(build / 'qemu-wallpaper-build-pending.json', value)
    return value


def graph_check(text):
    definitions = [line for line in text.splitlines() if line.startswith('defines = ')]
    if len(definitions) != 1:
        raise ValueError('unique actual Wallpaper GN definitions required')
    flags = shlex.split(definitions[0].split('=', 1)[1])
    if '-DQEMU_WALLPAPER_RENDERER' not in flags or any(x == '-DTHEME_SERVICE' or x.startswith('-DTHEME_SERVICE=') for x in flags):
        raise ValueError('GN did not select the actual QEMU fallback without ThemeService')
    for unit in UNITS:
        source = '../../' + BASE + '/services/src/' + Path(unit).stem + '.cpp'
        start = 'build ' + unit + ': cxx ' + source
        if sum(line == start or line.startswith(start + ' ') for line in text.splitlines()) != 1:
            raise ValueError('Wallpaper source/object edge missing or ambiguous')
    edges = [line for line in text.splitlines() if line.startswith('build theme/wallpaper_mgr/' + LIBRARY + ' ')]
    if len(edges) != 1 or ': solink ' not in edges[0] or not set(UNITS) <= set(edges[0].split()):
        raise ValueError('actual Wallpaper fallback objects are not linked into the service')


def compile_check(command, unit, product):
    argv = shlex.split(command)
    if argv and Path(argv[0]).name == 'ccache': argv = argv[1:]
    effective = dict(vcall=False, icall=False, cross_dso=False, lto=False, exceptions=True, rtti=True)
    for flag in argv:
        if flag.startswith(('-fsanitize=', '-fno-sanitize=')):
            enabled = flag.startswith('-fsanitize=')
            names = flag.split('=', 1)[1].split(',')
            for kind in ('vcall', 'icall'):
                if any(name in ('all', 'cfi', 'cfi-' + kind) for name in names): effective[kind] = enabled
        elif flag in ('-fsanitize-cfi-cross-dso', '-fno-sanitize-cfi-cross-dso'):
            effective['cross_dso'] = flag == '-fsanitize-cfi-cross-dso'
        elif flag in ('-flto', '-flto=thin', '-flto=full', '-fno-lto'):
            effective['lto'] = flag != '-fno-lto'
        elif flag in ('-fexceptions', '-fno-exceptions'):
            effective['exceptions'] = flag == '-fexceptions'
        elif flag in ('-frtti', '-fno-rtti'):
            effective['rtti'] = flag == '-frtti'
    source = '../../' + BASE + '/services/src/' + Path(unit).stem + '.cpp'
    if (not argv or argv[0] != '../../prebuilts/clang/ohos/linux-x86_64/llvm/bin/clang++' or
            any(x in argv for x in (';', '&&', '|', '>', '<')) or argv.count('-c') != 1 or argv.count('-o') != 1 or
            argv.index('-c') + 1 == len(argv) or argv.index('-o') + 1 == len(argv) or
            argv[argv.index('-c') + 1] != source or argv[argv.index('-o') + 1] != unit or
            '--target=' + PRODUCTS[product][2] + '-linux-ohos' not in argv or
            '-DQEMU_WALLPAPER_RENDERER' not in argv or
            effective != dict(vcall=True, icall=True, cross_dso=True, lto=True, exceptions=False, rtti=False) or
            any(x == '-DTHEME_SERVICE' or x.startswith('-DTHEME_SERVICE=') for x in argv)):
        raise ValueError('actual protected Wallpaper fallback compiler command required')


def selected_args(text):
    headings = re.findall(r'^[A-Za-z_][A-Za-z_0-9]*[ \t]*$', text, re.M)
    current = re.findall(r'^[ \t]*Current value[^\r\n=]*=[ \t]*(\S+)[ \t]*$', text, re.M)
    if [heading.strip() for heading in headings] != ['theme_service'] or current != ['false']:
        raise ValueError('actual selected GN theme_service=false query required')


def selected_args_command(command, product):
    if not isinstance(command, list) or any(not isinstance(x, str) for x in command):
        raise ValueError('actual GN argument query argv required')
    if command and command[0] == '/usr/bin/qemu-x86_64-static': command = command[1:]
    if len(command) != 4 or command[1] != 'args' or command[3] != '--list=theme_service':
        raise ValueError('unique theme_service GN argument query required')
    build = Path(command[2]); source = build.parent.parent
    if (not build.is_absolute() or '..' in build.parts or build.parts[-2:] != ('out', product) or
            command[0] != str(source / 'prebuilts/build-tools/linux-x86/bin/gn')):
        raise ValueError('GN query does not bind the actual product source/build paths')


def elf_check(path, product):
    data = regular(path).read_bytes(); cls, machine, _ = PRODUCTS[product]
    if (len(data) < 64 or data[:7] != b'\x7fELF' + bytes((cls, 1, 1)) or
            struct.unpack_from('<HH', data, 16) != (3, machine)):
        raise ValueError('actual Wallpaper DSO ABI/type differs')
    offset = struct.unpack_from('<Q' if cls == 2 else '<I', data, 32 if cls == 2 else 28)[0]
    size, count = struct.unpack_from('<HH', data, 54 if cls == 2 else 42)
    fmt = '<IIQQQQQQ' if cls == 2 else '<IIIIIIII'
    if not count or size < struct.calcsize(fmt) or offset + count * size > len(data):
        raise ValueError('Wallpaper DSO program headers missing/truncated')
    kinds = set(); executable = False
    for i in range(count):
        values = struct.unpack_from(fmt, data, offset + size * i)
        kind = values[0]; start = values[2] if cls == 2 else values[1]
        length = values[5] if cls == 2 else values[4]; flags = values[1] if cls == 2 else values[6]
        if start + length > len(data): raise ValueError('Wallpaper DSO segment truncated')
        kinds.add(kind); executable |= kind == 1 and bool(flags & 1) and length > 0
    if not executable or not {1, 2} <= kinds or '__cfi_check' not in read_elf(path).defined:
        raise ValueError('actual executable Wallpaper implementation/cross-DSO CFI missing')


def query(source, product):
    source_check(source); build = source / 'out' / product
    graph = regular(build / GRAPH); graph_check(graph.read_text())
    ninja = source / 'prebuilts/build-tools/linux-x86/bin/ninja'; commands = {}
    for unit in UNITS:
        raw = subprocess.check_output([str(ninja), '-w', 'dupbuild=warn', '-C', str(build), '-t', 'commands', '-s', unit], text=True, timeout=120)
        lines = [line for line in raw.splitlines() if 'clang++ ' in line and ' -c ' in line]
        if len(lines) != 1: raise ValueError('actual one-object Wallpaper compile query is ambiguous')
        compile_check(lines[0], unit, product); commands[unit] = lines[0]
    gn = [str(source / 'prebuilts/build-tools/linux-x86/bin/gn')]
    if os.environ.get('QEMU_HOST_GN_QEMU_USER') == '1': gn.insert(0, '/usr/bin/qemu-x86_64-static')
    args_command = gn + ['args', str(build), '--list=theme_service']
    selected_args_command(args_command, product)
    args = subprocess.check_output(args_command, cwd=source, text=True, timeout=180); selected_args(args)
    return dict(graph_sha256=file_sha256(graph), compile_commands=commands, selected_args_command=args_command,
                selected_args_sha256=__import__('hashlib').sha256(args.encode()).hexdigest()), {
                    'graph.ninja': graph.read_bytes(), 'compile-commands.json': (json.dumps(commands, indent=2) + '\n').encode(),
                    'theme-service-args.txt': args.encode()}


def finish(source, product, log):
    build = source / 'out' / product
    value = json.loads(regular(build / 'qemu-wallpaper-build-pending.json').read_text())
    if (value.get('phase') != 'prepared' or value.get('product') != product or
            value.get('source_sha256') != FILES or value.get('recipe') != recipe()):
        raise ValueError('current Wallpaper build preparation missing')
    graph, payload = query(source, product); artifacts = {}
    for name in outputs(product):
        path = regular(build / name); stat = path.stat()
        if stat.st_mtime_ns < value['start_ns']: raise ValueError('Wallpaper output was not rebuilt in this attempt: ' + name)
        artifacts[name] = dict(sha256=file_sha256(path), mtime_ns=stat.st_mtime_ns, bytes=stat.st_size)
    linked = 'theme/wallpaper_mgr/' + LIBRARY
    if artifacts[linked]['sha256'] != artifacts[outputs(product)[-1]]['sha256']:
        raise ValueError('Wallpaper staging differs from this actual linked DSO')
    elf_check(build / linked, product)
    value.update(phase='completed', finished_ns=time.time_ns(), graph=graph, artifacts=artifacts,
                 build_log=dict(path=str(log), sha256=file_sha256(regular(log))))
    inventory = dict(schema_version=1, scope='actual_QEMU_Wallpaper_fallback_build_and_image_NOT_guest_connection',
        product=product, source_sha256=FILES, recipe=recipe(), graph=graph)
    payload.update({LIBRARY: (build / linked).read_bytes(), 'witness.json': (json.dumps(value, indent=2) + '\n').encode(),
                    'build-log.txt': regular(log).read_bytes()})
    _check(inventory, payload)
    write(build / 'qemu-wallpaper-build-witness.json', value)
    return value


def _check(value, payload):
    product = value['product']
    if (value.get('schema_version') != 1 or value.get('scope') != 'actual_QEMU_Wallpaper_fallback_build_and_image_NOT_guest_connection' or
            product not in PRODUCTS or value.get('source_sha256') != FILES or value.get('recipe') != recipe() or set(payload) != PAYLOADS):
        raise ValueError('current complete Wallpaper source/build inventory required')
    graph_check(payload['graph.ninja'].decode()); selected_args(payload['theme-service-args.txt'].decode())
    graph = value['graph']; selected_args_command(graph.get('selected_args_command'), product)
    commands = json.loads(payload['compile-commands.json'])
    sha = lambda data: __import__('hashlib').sha256(data).hexdigest()
    if (graph.get('graph_sha256') != sha(payload['graph.ninja']) or graph.get('compile_commands') != commands or
            graph.get('selected_args_sha256') != sha(payload['theme-service-args.txt']) or set(commands) != set(UNITS)):
        raise ValueError('Wallpaper raw GN and command bytes differ')
    for unit, command in commands.items(): compile_check(command, unit, product)
    witness = json.loads(payload['witness.json'])
    if (witness.get('phase') != 'completed' or witness.get('product') != product or witness.get('recipe') != recipe() or
            witness.get('source_sha256') != FILES or witness.get('graph') != graph or
            re.fullmatch('[a-f0-9]{32}', witness.get('nonce', '')) is None or
            type(witness.get('start_ns')) is not int or witness['start_ns'] <= 0 or
            type(witness.get('finished_ns')) is not int or witness['finished_ns'] < witness['start_ns'] or
            set(witness.get('artifacts', {})) != set(outputs(product)) or
            witness.get('build_log', {}).get('sha256') != sha(payload['build-log.txt'])):
        raise ValueError('fresh full-build Wallpaper witness incomplete')
    for row in witness['artifacts'].values():
        if (re.fullmatch('[a-f0-9]{64}', row.get('sha256', '')) is None or type(row.get('mtime_ns')) is not int or
                row['mtime_ns'] < witness['start_ns'] or type(row.get('bytes')) is not int or row['bytes'] <= 0):
            raise ValueError('Wallpaper output predates this forced build')
    for name in ('theme/wallpaper_mgr/' + LIBRARY, outputs(product)[-1]):
        if witness['artifacts'][name]['sha256'] != sha(payload[LIBRARY]): raise ValueError('Wallpaper staged/linked DSO differs')
    log = payload['build-log.txt'].decode(errors='replace')
    if any('CXX ' + unit not in log for unit in UNITS) or 'SOLINK theme/wallpaper_mgr/' + LIBRARY not in log:
        raise ValueError('actual full build did not compile/link both Wallpaper fallback consumers')


def check_inventory(value, product, directory):
    if value.get('product') != product: raise ValueError('Wallpaper inventory product differs')
    files = value.get('files_sha256', {})
    if set(files) != PAYLOADS: raise ValueError('Wallpaper evidence payload set differs')
    for name, checksum in files.items():
        if file_sha256(regular(directory / name)) != checksum: raise ValueError('Wallpaper evidence changed: ' + name)
    _check(value, {name: regular(directory / name).read_bytes() for name in PAYLOADS})
    elf_check(directory / LIBRARY, product)
    return value


def package(source, product, directory):
    build = source / 'out' / product; source_check(source)
    witness_path = regular(build / 'qemu-wallpaper-build-witness.json'); witness = json.loads(witness_path.read_text())
    graph, payload = query(source, product)
    for name, row in witness['artifacts'].items():
        if file_sha256(regular(build / name)) != row['sha256']: raise ValueError('Wallpaper build output changed before packaging')
    payload.update({LIBRARY: regular(build / ('theme/wallpaper_mgr/' + LIBRARY)).read_bytes(),
        'witness.json': witness_path.read_bytes(), 'build-log.txt': regular(witness['build_log']['path']).read_bytes()})
    value = dict(schema_version=1, scope='actual_QEMU_Wallpaper_fallback_build_and_image_NOT_guest_connection',
                 product=product, source_sha256=FILES, recipe=recipe(), graph=graph)
    _check(value, payload); directory.mkdir(parents=True, exist_ok=False)
    for name, data in payload.items(): (directory / name).write_bytes(data)
    value['files_sha256'] = {name: file_sha256(directory / name) for name in payload}
    write(directory / 'inventory.json', value); check_inventory(value, product, directory)
    return value


def image(system_image, directory, product):
    value = check_inventory(json.loads(regular(directory / 'inventory.json').read_text()), product, directory)
    libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
    with tempfile.TemporaryDirectory(prefix='wallpaper-native-image-') as temporary:
        binary, inode = dump_unique_file(system_image, tuple(p + '/' + libdir + '/' + LIBRARY for p in ('', '/system')),
                                         Path(temporary), debugfs_path())
        if file_sha256(binary) != value['files_sha256'][LIBRARY]: raise ValueError('new system.img Wallpaper DSO differs from actual fallback link')
    return dict(status='pass', scope=value['scope'], product=product, system_image_sha256=file_sha256(system_image),
        inventory_sha256=file_sha256(directory / 'inventory.json'), library_sha256=value['files_sha256'][LIBRARY],
        image_entry=inode, first_artifact_behavior_gate_passed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('begin', 'finish', 'package', 'verify'))
    parser.add_argument('--source-root', type=Path); parser.add_argument('--product', choices=PRODUCTS, required=True)
    parser.add_argument('--build-log', type=Path); parser.add_argument('--directory', type=Path)
    parser.add_argument('--system-image', type=Path); parser.add_argument('--output', type=Path)
    a = parser.parse_args()
    if a.phase in ('begin', 'finish', 'package') and a.source_root is None: parser.error('source-root required')
    if a.phase == 'finish' and a.build_log is None: parser.error('actual build-log required')
    if a.phase in ('package', 'verify') and (a.directory is None or a.system_image is None): parser.error('directory/system-image required')
    source = a.source_root.resolve() if a.source_root else None
    if a.phase == 'begin': result = begin(source, a.product)
    elif a.phase == 'finish': result = finish(source, a.product, a.build_log.resolve())
    else:
        if a.phase == 'package': package(source, a.product, a.directory.resolve())
        result = image(a.system_image, a.directory.resolve(), a.product)
    if a.output: write(a.output, result)
    print(json.dumps({k: result[k] for k in ('phase', 'product', 'status', 'scope', 'nonce') if k in result}))


if __name__ == '__main__': main()
