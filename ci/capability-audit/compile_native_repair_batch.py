#!/usr/bin/env python3
"""Compile complete AVC/child candidates in scratch with real product commands.

Apply every component patch to private fixed-revision source before compiling
all changed TUs. Keep successful objects and all failures. No source/out writes,
feature overrides, link result, package or runtime gate is implied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[2]
GROUPS = {
    'audio_capture': {
        'project': 'foundation/multimedia/av_codec',
        'revision': 'e5c525670d1f6622d441c9e5bf975ea0579ea177',
        'components': ['audio_capture_integrity'],
        'units': ['audio_capture_filter', 'audio_capture_module'],
        'sources': {
            'audio_capture_filter': 'services/media_engine/filters/audio_capture_filter.cpp',
            'audio_capture_module': 'services/media_engine/modules/source/audio_capture/audio_capture_module.cpp'},
        'targets': {
            'audio_capture_filter': 'obj/foundation/multimedia/av_codec/services/media_engine/filters/av_codec_media_engine_filters/audio_capture_filter.o',
            'audio_capture_module': 'obj/foundation/multimedia/av_codec/services/media_engine/modules/source/audio_capture/av_codec_media_engine_modules/audio_capture_module.o'},
        'required_headers': {
            'audio_capture_filter': 'interfaces/inner_api/native/audio_capture_filter.h',
            'audio_capture_module': 'services/media_engine/modules/source/audio_capture/audio_capture_module.h'},
    },
    'avc': {
        'project': 'foundation/multimedia/av_codec',
        'revision': 'e5c525670d1f6622d441c9e5bf975ea0579ea177',
        'components': ['avc_eos', 'avc_surface_layout'],
        'directory': 'services/engine/codec/video/avcencoder',
        'units': ['avc_encoder', 'avc_encoder_util'],
        'target': 'obj/foundation/multimedia/av_codec/services/engine/codec/video/avcencoder/avc_encoder/{unit}.o',
        'required_header': None,
    },
    'child': {
        'project': 'foundation/ability/ability_runtime',
        'revision': '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8',
        'components': ['native_child_process'],
        'directory': 'frameworks/native/child_process/src',
        'units': ['native_child_process', 'native_child_callback'],
        'target': 'obj/foundation/ability/ability_runtime/frameworks/native/child_process/src/child_process/{unit}.o',
        'required_header': 'frameworks/native/child_process/include/native_child_callback.h',
    },
    'graphics3d': {
        'project': 'foundation/graphic/graphic_3d',
        'revision': 'b2d7af910f2d4b941697630020b0940245d5bd99',
        'components': ['scene_startup'],
        'units': ['scene_adapter', 'RenderContextJS'],
        'sources': {'scene_adapter': '3d_scene_adapter/src/scene_adapter.cpp',
                    'RenderContextJS': 'kits/js/src/RenderContextJS.cpp'},
        'targets': {
            'scene_adapter': 'obj/foundation/graphic/graphic_3d/3d_scene_adapter/src/scene_adapter_source/scene_adapter.o',
            'RenderContextJS': 'obj/foundation/graphic/graphic_3d/kits/js/src/napi_source/RenderContextJS.o'},
        'required_header': None,
    },
}
PRODUCTS = {'arm64_virt': ('aarch64', 183, 2), 'armv7a_virt': ('arm', 40, 1),
            'x86_64_virt': ('x86_64', 62, 2)}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_paths(components):
    paths = set()
    for component in components:
        for patch in component.glob('*.patch'):
            for line in patch.read_text().splitlines():
                if line.startswith(('+++ b/', '--- a/')):
                    name = line[6:].split('\t', 1)[0]
                    if Path(name).is_absolute() or '..' in Path(name).parts:
                        raise ValueError('canonical patch path required')
                    paths.add(name)
    return sorted(paths)


def verify_object(obj, disassembler, arch, machine, elf_class):
    data = obj.read_bytes()[:20]
    if data.startswith(b'BC\xc0\xde'):
        ir = obj.with_suffix('.ll')
        subprocess.run([str(disassembler), str(obj), '-o', str(ir)], check=True)
        # CFI can make one product .o contain split-LTO modules. LLVM's real
        # disassembler writes .ll.0/.ll.1 in that case; verify every module.
        modules = [ir] if ir.is_file() else sorted(
            p for p in ir.parent.glob(ir.name + '.*')
            if re.fullmatch(re.escape(ir.name) + r'\.\d+', p.name))
        if not modules:
            raise ValueError('LLVM disassembler produced no actual modules')
        verified = []
        ir_arch = r'arm(?:v7a?)?' if arch == 'arm' else arch
        for module in modules:
            with module.open() as stream:
                triple = next((line.strip() for line in stream if line.startswith('target triple = ')), '')
            if not re.fullmatch('target triple = "' + ir_arch + '(?:-unknown)?-linux-ohos"', triple):
                raise ValueError('actual product LLVM target required for every module')
            verified.append({'file': module.name, 'target_triple': triple, 'sha256': sha(module)})
        return {'object_format': 'LLVM_bitcode', 'llvm_modules': verified}
    if (data[:6] == bytes([127, 69, 76, 70, elf_class, 1]) and
            int.from_bytes(data[18:20], 'little') == machine):
        return {'object_format': 'ELF'}
    raise ValueError('product ELF/LLVM output required')


def run(args):
    root, output = args.source_root.resolve(), args.output.absolute()
    if any(not os.statvfs(p).f_flag & os.ST_RDONLY for p in [root, root / 'out']):
        raise ValueError('fixed source and product out must be read-only')
    group = GROUPS[args.group]
    project = Path(group['project'])
    revision = subprocess.check_output(['git', '-C', str(root / project), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != group['revision']:
        raise ValueError('fixed source revision required')
    output.mkdir(parents=True, exist_ok=False)
    components = [ROOT / 'patches/common' / project / name for name in group['components']]
    owned = patch_paths(components)
    if any(not Path(name).is_relative_to(project) for name in owned):
        raise ValueError('component targets a different project')
    before = {name: sha(root / name) if (root / name).is_file() else None for name in owned}
    recipe = [Path(__file__), ROOT / 'patches/lib/apply_patch.sh',
              ROOT / 'patches/lib/apply_component_stack.py', ROOT / 'patches/lib/exact_source_states.py',
              *(p for c in components for p in c.rglob('*')
               if p.is_file() and '__pycache__' not in p.parts)]
    recipe_before = {str(p): sha(p) for p in recipe}
    staged = output / 'candidate'
    private = staged / project
    private.parent.mkdir(parents=True)
    with (output / 'source-checkout.log').open('xb') as log:
        subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(root / project), str(private)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
        # New files have no HEAD blob; the component creates them itself.
        existing = [str(Path(name).relative_to(project)) for name in owned
                    if subprocess.run(['git', '-C', str(private), 'cat-file', '-e',
                        revision + ':' + str(Path(name).relative_to(project))],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0]
        subprocess.run(['git', '-C', str(private), 'checkout', revision, '--', *existing],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    for attempt in (1, 2):
        for component in components:
            with (output / f'apply-{component.name}-{attempt}.log').open('xb') as log:
                subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(staged)],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
    headers = [name for name in owned if Path(name).suffix in ('.h', '.hpp')]
    overlay = output / 'headers.json'
    overlay.write_text(json.dumps({'version': 0, 'roots': [
        {'type': 'file', 'name': str(root / name), 'external-contents': str(staged / name),
         'use-external-name': True} for name in headers]}) + '\n')
    report = {'status': 'fail', 'group': args.group, 'source_revision': revision,
              'scope': 'complete_patched_product_TUs_ONLY_NOT_link_package_runtime',
              'components': group['components'], 'source_before_sha256': before,
              'candidate_sha256': {name: sha(staged / name) for name in owned},
              'recipe_sha256': recipe_before, 'objects': [], 'first_artifact_behavior_gate_passed': False}
    for product in args.product:
        cwd = root / 'out' / product
        arch, machine, elf_class = PRODUCTS[product]
        for unit in group['units']:
            row = {'product': product, 'unit': unit, 'status': 'fail'}
            try:
                target = group['targets'][unit] if 'targets' in group else group['target'].format(unit=unit)
                query = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                    '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
                    capture_output=True, text=True, timeout=180, check=True)
                (output / f'{product}-{unit}-query.log').write_text(query.stdout + query.stderr)
                argv = shlex.split(query.stdout.splitlines()[-1])
                if Path(argv[0]).name == 'ccache':
                    argv.pop(0)
                source = project / (group['sources'][unit] if 'sources' in group else
                                    group['directory'] + '/' + unit + '.cpp')
                if (Path(argv[0]).name != 'clang++' or '--target=' + arch + '-linux-ohos' not in argv or
                        argv.count('-c') != 1 or argv.count('-o') != 1 or argv.count('-MF') != 1 or
                        any(v in argv for v in ('&&', ';', '|')) or
                        (cwd / argv[argv.index('-c') + 1]).resolve() != root / source):
                    raise ValueError('exact real product TU command required')
                row['original_argv'] = argv[:]
                obj = output / f'{product}-{unit}.o'
                dep = output / f'{product}-{unit}.d'
                argv[argv.index('-c') + 1] = str(staged / source)
                argv[argv.index('-o') + 1] = str(obj)
                argv[argv.index('-MF') + 1] = str(dep)
                argv += ['-iquote', str((root / source).parent)]
                if headers:
                    argv += ['-ivfsoverlay', str(overlay)]
                row['executed_argv'] = argv
                with (output / f'{product}-{unit}-compile.log').open('xb') as log:
                    result = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=600)
                row['exit_code'] = result.returncode
                if result.returncode:
                    raise ValueError('product compilation failed; full log retained')
                disassembler = (cwd / argv[0]).resolve().parent / 'llvm-dis'
                row.update(verify_object(obj, disassembler, arch, machine, elf_class))
                dependency = dep.read_text()
                required = group.get('required_headers', {}).get(unit, group.get('required_header'))
                if str(staged / source) not in dependency or (required and str(private / required) not in dependency):
                    raise ValueError('compiler did not consume actual candidate source/header')
                row.update(status='pass', object_sha256=sha(obj), dependency_sha256=sha(dep))
            except Exception as error:
                row['error'] = type(error).__name__ + ': ' + str(error)
            report['objects'].append(row)
            (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    report['source_inputs_unchanged'] = all(
        (sha(root / name) if (root / name).is_file() else None) == checksum for name, checksum in before.items())
    report['recipe_inputs_unchanged'] = all(sha(Path(name)) == checksum for name, checksum in recipe_before.items())
    if (report['source_inputs_unchanged'] and report['recipe_inputs_unchanged'] and
            report['objects'] and all(x['status'] == 'pass' for x in report['objects'])):
        report['status'] = 'pass'
    (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'group': args.group, 'status': report['status'], 'objects': len(report['objects'])}))
    return report['status'] == 'pass'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--group', choices=GROUPS, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append', required=True)
    args = parser.parse_args()
    if len(args.product) != len(set(args.product)):
        parser.error('duplicate products cannot count as separate checks')
    raise SystemExit(0 if run(args) else 1)
