#!/usr/bin/env python3
"""Build/replay the pure C GET-only observer using the actual ALSA C GN anchor.

Default is a command plan with no source/out access. Root alone may explicitly
--execute-build in its owned offline compiler environment with read-only source,
product out, archive/images/profile and repository mounts. No SDK fallback.
--verify-existing is pure file replay and never invokes native tools or Ninja.
"""
import argparse
import hashlib
import json
from pathlib import Path
import posixpath
import re
import shutil
import struct

import batch_system_build_runtime_helpers as product

HERE = Path(__file__).resolve().parent
NAME = 'netlink_snapshot'
SOURCE = HERE / 'probes' / (NAME + '.c')
ALSA = {'graph': 'obj/third_party/alsa-lib/libasound.ninja',
        'object': 'obj/third_party/alsa-lib/src/libasound/async.o',
        'source': 'third_party/alsa-lib/src/async.c',
        'header': 'third_party/alsa-lib/include/alsa/asoundlib.h'}
TOOLS = (Path(__file__), Path(product.__file__), SOURCE, HERE / 'batch_network_kernel_snapshot.py')


def require(value, message):
    if not value: raise ValueError(message)


def descriptor(path):
    path = Path(path)
    return {'path': str(path), 'sha256': product.sha(path), 'bytes': path.stat().st_size}


def elf_needed(path):
    """Read DT_NEEDED from actual ARM64 ELF bytes, independent of readelf text."""
    product.elf_header(path, executable=True)
    data = Path(path).read_bytes(); offset = struct.unpack_from('<Q', data, 32)[0]
    entry, count = struct.unpack_from('<HH', data, 54)
    loads = []; dynamic = []; interpreters = []
    for i in range(count):
        kind, _, start, address, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', data, offset + i * entry)
        require(start + size <= len(data), 'truncated actual ELF segment')
        if kind == 1: loads.append((address, start, size))
        if kind == 2: dynamic.append((start, size))
        if kind == 3: interpreters.append(data[start:start + size])
    require(interpreters == [b'/lib/ld-musl-aarch64.so.1\0'], 'exact product musl interpreter')
    require(len(dynamic) == 1 and dynamic[0][1] % 16 == 0, 'one complete ELF dynamic segment')
    start, size = dynamic[0]; tags = {}; needed = []; ended = False
    for i in range(start, start + size, 16):
        kind, value = struct.unpack_from('<qQ', data, i)
        if kind == 0: ended = True; break
        if kind == 1: needed.append(value)
        elif kind in (5, 10):
            require(kind not in tags, 'duplicate ELF string table tag'); tags[kind] = value
    require(ended and set(tags) == {5, 10} and 0 < len(needed) <= 128, 'complete ELF dynamic string table')
    positions = [file + tags[5] - address for address, file, size in loads
                 if address <= tags[5] and tags[5] + tags[10] <= address + size]
    require(len(positions) == 1, 'ELF string table mapping')
    table = data[positions[0]:positions[0] + tags[10]]; result = []
    for index in needed:
        end = table.find(b'\0', index)
        require(0 <= index < end < len(table), 'ELF needed string bounds')
        name = table[index:end].decode('ascii')
        require(re.fullmatch(r'[A-Za-z0-9_.+\-]+\.so', name), 'ELF needed SONAME')
        result.append(name)
    require(len(set(result)) == len(result), 'duplicate DT_NEEDED')
    return sorted(result)


def configure():
    # Runtime extension only; shared module and product GN are not changed.
    product.HELPERS[NAME] = dict(fixture='probes/netlink_snapshot.c', source_file=SOURCE,
        language='c', anchors=[ALSA], libraries=[], headers=[], extra_includes=[])


class KernelSnapshotBuilder(product.Builder):
    def anchor(self, spec, name):
        row = super().anchor(spec, name)
        private = self.output / (name + '.ninja')
        private.write_bytes((self.build / spec['graph']).read_bytes())
        require(product.sha(private) == row['graph']['sha256'], 'GN graph changed during copy')
        row['private_graph'] = descriptor(private)
        return row

    def check_elf(self, name, binary, direct, row):
        row['elf'] = product.elf_header(binary, executable=True)
        info = self.command([self.readelf, '-h', '-l', '-d', '--dyn-syms', '--wide', '--demangle', binary],
                            name + '-actual-ELF-ABI')
        needed = product.dynamic_needed(info)
        require('libc.so' in needed, 'actual installed musl dependency required')
        require(not row['CFI_preserved'] or product.defined_symbol(info, '__cfi_check'),
                'actual selected C GN CFI must be present')
        for soname in needed: product.runtime_link_records(row, soname)
        row['DT_NEEDED'] = sorted(needed)
        row['system_ABI_proof'] = 'actual ALSA C GN flags/CRT/LTO/runtime selections and installed F image; no C++ assertion'


def build(source_root, output, runtime_profile, runtime_profile_sha256, *, plan_only=False):
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    configure()
    builder = KernelSnapshotBuilder(source_root, output / 'product-build', [NAME], plan_only=plan_only,
        runtime_profile=runtime_profile, runtime_profile_sha256=runtime_profile_sha256)
    native = builder.run()
    report = {'schema': 'network-kernel-helper-build/v1', 'status': 'fail',
        'scope': 'actual_product_C_compile_link_ONLY_NOT_guest_or_VPN', 'arch': 'arm64',
        'plan_only': plan_only, 'tools': {p.relative_to(HERE).as_posix(): descriptor(p) for p in TOOLS},
        'actual_c_compiler': builder.inputs.get(str(builder.c_compiler.resolve())),
        'product_build': descriptor(builder.output / 'build.json'), 'artifacts': {},
        'requirements_closed': 0, 'first_artifact_behavior_gate_passed': False}
    profile_copy = output / 'runtime-profile.json'; profile_copy.write_bytes(Path(runtime_profile).read_bytes())
    report['profile_copy'] = descriptor(profile_copy)
    row = native['helpers'].get(NAME, {})
    if native['status'] == 'pass_compile_link_ONLY' and not plan_only:
        private = Path(row['binary']).parent
        for key, path in {'binary': Path(row['binary']), 'object': private / (NAME + '.o'),
                          'source': private / SOURCE.name, 'depfile': private / 'headers.d',
                          'guard': private / 'actual_system_abi.h'}.items():
            report['artifacts'][key] = descriptor(path)
        shutil.copyfile(row['binary'], output / NAME)
        report['installed_tool'] = descriptor(output / NAME)
        report['status'] = 'pass_compile_link_ONLY'
    elif plan_only and native['status'] == 'planned_NOT_compiled': report['status'] = 'planned_NOT_compiled'
    path = output / 'build.json'; path.write_text(json.dumps(report, indent=2) + '\n')
    if report['status'] == 'pass_compile_link_ONLY': verify_existing(path, product.sha(path))
    return report


def verify_existing(path, expected_sha256, *, archive_sha256=None):
    """Independent file replay, relocating only the prior private build prefix.

    Original source/out paths are identities in retained receipts, never probed.
    Actual graph/command/depfile/link-trace/ELF/dumped installed DSOs are replayed
    from immutable build artifacts. This is neither guest execution nor new GN
    target selection and cannot close the runtime behavior gate.
    """
    path = Path(path).resolve()
    require(re.fullmatch('[0-9a-f]{64}', expected_sha256 or '') and product.sha(path) == expected_sha256,
            'external build receipt SHA required')
    value = json.loads(path.read_text()); root = path.parent
    require(value.get('schema') == 'network-kernel-helper-build/v1' and
            value.get('status') == 'pass_compile_link_ONLY' and value.get('plan_only') is False and
            value.get('arch') == 'arm64' and value.get('requirements_closed') == 0 and
            value.get('first_artifact_behavior_gate_passed') is False, 'successful compile-only receipt required')
    require(set(value['tools']) == {p.relative_to(HERE).as_posix() for p in TOOLS} and
            all(all(value['tools'][p.relative_to(HERE).as_posix()][k] == descriptor(p)[k]
                    for k in ('sha256','bytes')) for p in TOOLS), 'builder/native/decoder/common tools changed')
    origin = Path(value['product_build']['path']).parent
    def relocated(record):
        old = Path(record['path'])
        require(old.is_absolute() and '..' not in old.parts, 'absolute artifact identity')
        try: relative = old.relative_to(origin)
        except ValueError as error: raise ValueError('private artifact escapes original build prefix') from error
        local = root / 'product-build' / relative
        require(local.is_file() and not local.is_symlink() and local.resolve().is_relative_to((root / 'product-build').resolve()), 'artifact missing/symlink escape')
        require(product.sha(local) == record['sha256'] and ('bytes' not in record or local.stat().st_size == record['bytes']), 'artifact bytes changed')
        return local
    report = json.loads(relocated(value['product_build']).read_text())
    require(report.get('status') == 'pass_compile_link_ONLY' and report.get('changed_inputs') == [] and
            report.get('plan_only') is False and report.get('builder_sha256') == product.sha(Path(product.__file__)) and
            set(report['helpers']) == {NAME}, 'complete unchanged actual product builder receipt required')
    row = report['helpers'][NAME]; inputs = report['inputs']
    require(row.get('status') == 'pass_compile_link_ONLY' and row.get('language') == 'c' and
            row.get('actual_C_GN_flags_preserved') is True and row['source'] == inputs.get(row['source']['path']) and
            row['source']['sha256'] == product.sha(SOURCE) == row['private_source_sha256'], 'actual current C source contract')
    profile_file = root / 'runtime-profile.json'
    require(value['profile_copy']['sha256'] == product.sha(profile_file) and
            profile_file.stat().st_size == value['profile_copy']['bytes'], 'retained original installed profile differs')
    profile = json.loads(profile_file.read_text()); product.validate_installed_profile(profile, archive_sha256=archive_sha256)
    require(row['installed_runtime_profile'] == report['installed_runtime_profile'] and
            row['installed_runtime_profile']['profile'] == profile and
            row['installed_runtime_profile']['source']['sha256'] == product.sha(profile_file), 'row/profile original binding')
    commands = report['commands']; labels = [r['label'] for r in commands]
    require(len(set(labels)) == len(labels), 'ambiguous command labels')
    logs = {}
    for c in commands:
        require(c.get('exit_code') == 0 and not c.get('timed_out') and c['cwd'] == report['build_directory'], 'actual native command failure')
        logs[c['label']] = relocated({'path': c['log'], 'sha256': c['sha256']}).read_text()
    def command(label, argv):
        selected = [c for c in commands if c['label'] == label]
        require(len(selected) == 1 and selected[0]['argv'] == argv, 'exact actual compiler/link command binding')
        return selected[0]
    require(len(row['anchors']) == 1, 'exact one C GN anchor')
    anchor = row['anchors'][0]; graph = relocated(anchor['private_graph'])
    require(product.sha(graph) == anchor['graph']['sha256'] == inputs[anchor['graph']['path']]['sha256'] and
            anchor['object_target'] == ALSA['object'], 'actual graph selection changed')
    variables = product.variables(graph.read_text())
    require(all(anchor[k] == variables[k] for k in ('include_dirs','ldflags','libs')) and
            anchor['selected_shared_dependencies'] == product.selected_shared_dependencies(graph.read_text()), 'actual graph variables/dependencies changed')
    compile_argv, link_argv = row['compile_command'], row['link_command']
    build_dir = Path(report['build_directory']); compiler = Path(compile_argv[0])
    require(compiler.name == 'clang' and link_argv[0] == str(compiler) and
            value['actual_c_compiler'] == inputs.get(value['actual_c_compiler']['path']) and
            Path(value['actual_c_compiler']['path']).parent == compiler.parent and
            row['anchors'][0]['actual_command'] in logs[NAME + '-0-actual-GN-command'].splitlines(), 'actual C compiler/GN command identity')
    flags = product.compile_flags(anchor['actual_command'], compiler,
        Path(report['source_root']) / ALSA['source'], build_dir)
    require(flags == anchor['flags'] and [f for f in flags if f.startswith('--target=')] == ['--target=aarch64-linux-ohos'] and
            [f for f in flags if f.startswith('--sysroot=')] == ['--sysroot=obj/third_party/musl'] and
            any(f in ('-flto','-flto=thin','-flto=full') for f in flags), 'actual C flags/target/LTO selection')
    flags += [x for x in anchor['include_dirs'] if x not in flags]
    artifact = value['artifacts']; paths = {k: relocated(v) for k, v in artifact.items()}
    old_private = Path(row['binary']).parent
    require(compile_argv == [str(compiler), *flags, '-fPIE', '-MD', '-MF', str(old_private / 'headers.d'),
        '-c', str(old_private / SOURCE.name), '-o', str(old_private / (NAME + '.o'))] and
        product.argument(link_argv, '-o') == str(old_private / NAME) and
        str(old_private / (NAME + '.o')) in link_argv, 'exact C source/object/depfile/link arguments')
    command(NAME + '-compile', compile_argv); command(NAME + '-link', link_argv)
    require(paths['source'].read_bytes() == SOURCE.read_bytes() and
            paths['guard'].read_text() == '/* C helper retains actual C GN flags; no C++ ABI assertion. */\n' and
            product.sha(paths['depfile']) == row['depfile_sha256'], 'source/guard/depfile bytes')
    dependencies = product.dep_paths(paths['depfile'], build_dir)
    recorded = row['actual_compiler_dependencies']
    require(dependencies == [Path(r['path']).resolve() for r in recorded] and
            all(r == inputs.get(r['path']) or r['path'] == str(old_private / SOURCE.name) and
                r['sha256'] == product.sha(SOURCE) for r in recorded), 'complete real compiler dependency identities')
    require(product.elf_header(paths['binary'], executable=True)['sha256'] == row['binary_sha256'] and
            product.sha(root / NAME) == value['installed_tool']['sha256'] == row['binary_sha256'], 'actual ARM64 PIE binary')
    elf = logs[NAME + '-actual-ELF-ABI']; needed = product.dynamic_needed(elf)
    # Read actual ELF dynamic entries independently of the pretty-printer log.
    require(elf_needed(paths['binary']) == row['DT_NEEDED'] == sorted(needed) and 'libc.so' in needed,
            'actual ELF DT_NEEDED differs')
    inspections = [c for c in commands if c['label'] == NAME + '-actual-ELF-ABI']
    require(len(inspections) == 1 and Path(inspections[0]['argv'][0]).name == 'llvm-readelf' and
            inspections[0]['argv'][1:] == ['-h','-l','-d','--dyn-syms','--wide','--demangle',row['binary']],
            'exact actual native ELF inspection binding')
    require(row['CFI_preserved'] == product.effective_cfi(flags) and
            (not row['CFI_preserved'] or product.defined_symbol(elf, '__cfi_check')), 'actual C CFI selection differs')
    ld, removed = product.link_flags(anchor['ldflags'], old_private)
    require(row['removed_component_DSO_only_export_maps'] == removed and '-nostdlib' in ld and
            any('lto' in x for x in ld), 'actual C GN link/CRT/LTO policy')
    runtime = product.replace_runtime_libraries(anchor['libs'], profile)
    require(row['actual_runtime_libraries_from_anchors'] == list(dict.fromkeys(anchor['libs'])) and
            anchor['selected_shared_dependencies'] == [] and row['linked_libraries'] == [] and
            row['original_GN_direct_libraries'] == [], 'exact actual ALSA C GN/runtime selections retained')
    crt = [str(build_dir / 'obj/third_party/musl/usr/lib/aarch64-linux-ohos' / n)
           for n in ('Scrt1.o','crti.o','crtn.o')]
    expected_link = [str(compiler), *ld, '-pie', '-Wl,--threads=2', '-Wl,--export-dynamic',
        '-o', str(old_private / NAME), *crt[:2], '-Wl,-t', '-Wl,--start-group',
        str(old_private / (NAME + '.o')), *runtime, '-Wl,--end-group', crt[2]]
    require(link_argv == expected_link, 'exact actual C GN link/CRT/runtime argv differs')
    trace = logs[NAME + '-link']
    opened = {posixpath.normpath(str(Path(line.strip().split('(',1)[0]) if line.strip().startswith('/') else
                  build_dir / line.strip().split('(',1)[0]))
              for line in re.sub(r'\x1b\[[0-9;]*m', '', trace).splitlines() if line.strip()}
    require(all(r == inputs.get(r['path']) and r['path'] in opened for r in row['actual_link_inputs']), 'actual opened link input/trace identities')
    require(str(old_private / (NAME + '.o')) in opened, 'real helper object absent from link trace')
    image = report['installed_runtime_image_proof']
    for partition in ('system','vendor'):
        if partition + '_image' not in profile: continue
        expected = profile[partition + '_image']
        require(image['archive_members'][partition] == {k: expected[k] for k in ('archive_member','sha256','bytes')}, 'archive/image rehash proof differs')
    for soname in needed:
        for record in product.runtime_link_records(row, soname): require(record['path'] in opened, 'installed DSO absent from actual link trace')
        dump = image['dsos'][soname]; actual = relocated(dump); expected = profile['dsos'][soname]['staged']
        require(product.sha(actual) == expected['sha256'] and actual.stat().st_size == expected['bytes'] and
                product.elf_soname(actual) == soname, 'independent image DSO redump differs')
        stat = commands[dump['stat_command']]
        entry = profile['dsos'][soname]
        require(stat['argv'] == [image['tools']['debugfs']['path'], '-R', 'stat ' + entry['image_member'],
                profile[dump['partition'] + '_image']['path']] and
                re.search(r'(?m)^Inode: ' + str(dump['image_inode']) + r'\s+Type: regular\s', logs[stat['label']]),
                'exact actual image regular inode/stat command proof absent')
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--runtime-profile', type=Path)
    p.add_argument('--runtime-profile-sha256')
    p.add_argument('--execute-build', action='store_true')
    p.add_argument('--verify-existing', type=Path)
    p.add_argument('--expected-sha256')
    p.add_argument('--archive-sha256')
    a = p.parse_args()
    if a.verify_existing:
        require(not a.execute_build, 'build/replay modes are exclusive')
        verify_existing(a.verify_existing, a.expected_sha256, archive_sha256=a.archive_sha256)
        print(json.dumps({'status': 'replayed_compile_link_ONLY', 'guest_validated': False})); return 0
    require(all((a.source_root, a.output, a.runtime_profile, a.runtime_profile_sha256)), 'explicit actual source/output/profile and external SHA required')
    if not a.execute_build:
        print(json.dumps({'status': 'plan_ONLY_no_inputs_opened', 'source_root': str(a.source_root),
            'output': str(a.output), 'anchor': ALSA, 'helper': str(SOURCE), 'arch': 'arm64',
            'runtime_profile': str(a.runtime_profile), 'runtime_profile_sha256': a.runtime_profile_sha256,
            'next': 'root resource lease plus --execute-build', 'requirements_closed': 0})); return 0
    result = build(a.source_root, a.output, a.runtime_profile, a.runtime_profile_sha256)
    print(json.dumps({'status': result['status'], 'guest_validated': False}))
    return result['status'] != 'pass_compile_link_ONLY'


if __name__ == '__main__': raise SystemExit(main())
