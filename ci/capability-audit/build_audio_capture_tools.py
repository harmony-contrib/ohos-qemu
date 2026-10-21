#!/usr/bin/env python3
"""Build MIC QA tools from real C/C++ product GN flags and installed runtimes.

Root alone runs this under its source/out read lease. The C ALSA producer keeps
its C GN flags and never compiles a fabricated C++ ABI assertion. Both tools
retain actual CRT/static-runtime selections and prove every opened dynamic
runtime against an independently re-extracted packaged image.
"""
import argparse
import json
from pathlib import Path
import re
import shutil

import batch_system_build_runtime_helpers as product
from audio_capture_contract import sha, runtime_identity

HERE = Path(__file__).resolve().parent
ALSA = {'graph': 'obj/third_party/alsa-lib/libasound.ninja',
        'object': 'obj/third_party/alsa-lib/src/libasound/async.o',
        'source': 'third_party/alsa-lib/src/async.c',
        'header': 'third_party/alsa-lib/include/alsa/asoundlib.h'}
SOURCES = {'alsa_inject': HERE / 'batch_media_alsa_inject.c',
           'audio_capture_token': HERE / 'probes/audio_capture_token.cpp'}
LIBRARIES = {'alsa_inject': 'libasound.so', 'audio_capture_token': 'libaccesstoken_sdk.z.so'}


def verify_compile_command(report, name, row):
    commands = [r for r in report['commands'] if r['label'] == name + '-compile']
    argv = row['compile_command']
    if (len(commands) != 1 or commands[0]['argv'] != argv or commands[0].get('exit_code') != 0 or
            commands[0].get('timed_out')):
        raise ValueError('exact actual MIC compiler command absent')
    private = Path(row['binary']).parent
    if (product.argument(argv, '-c') != str(private / SOURCES[name].name) or
            product.argument(argv, '-o') != str(private / (name + '.o')) or
            product.argument(argv, '-MF') != str(private / 'headers.d') or
            str(private / (name + '.o')) not in row['link_command']):
        raise ValueError('MIC compiler source/object/link binding differs')


def configure():
    product.HELPERS['alsa_inject'] = {'fixture': 'batch_media_alsa_inject.c', 'source_file': SOURCES['alsa_inject'],
        'language': 'c', 'anchors': [ALSA], 'libraries': ['thirdparty/alsa-lib/libasound.so'],
        'headers': [ALSA['header']], 'extra_includes': ['third_party/alsa-lib/include']}
    product.HELPERS['audio_capture_token'] = {'fixture': 'probes/audio_capture_token.cpp',
        'source_file': SOURCES['audio_capture_token'], 'anchors': [product.TOKEN],
        'libraries': ['security/access_token/libaccesstoken_sdk.z.so'],
        'headers': [product.TOKEN['header']], 'extra_includes': []}


class CaptureToolsBuilder(product.Builder):
    def check_elf(self, name, binary, direct, row):
        if name != 'alsa_inject': return super().check_elf(name, binary, direct, row)
        row['elf'] = product.elf_header(binary, executable=True, product=self.product,
            interpreter_path=None if self.normal_link is None else self.normal_link['interpreter'])
        info = self.command([self.readelf, '-h', '-l', '-d', '--dyn-syms', '--wide', '--demangle', binary],
                            name + '-actual-ELF-ABI')
        needed = product.dynamic_needed(info)
        if row['CFI_preserved'] and not product.defined_symbol(info, '__cfi_check'):
            raise ValueError('actual C GN cross-DSO CFI was selected but is absent from producer')
        if not {'libasound.so', 'libc.so'} <= needed:
            raise ValueError('real C producer must use installed ALSA and musl')
        for soname in needed: product.runtime_link_records(row, soname)
        row['DT_NEEDED'] = sorted(needed)
        row['system_ABI_proof'] = 'actual ALSA C GN flags/headers/CRT and installed link inputs; no C++ ABI assertion'


def verify_installed_tools(build, arch):
    """Read-only replay hook for collector and independent MIC verifiers."""
    from batch_media_wallpaper_artifacts import elf_dependencies
    path = Path(build); value = json.loads(path.read_text())
    if (arch not in ('arm64','armv7a','x86_64') or value.get('status') != 'pass' or value.get('arch') != arch or
            value.get('builder_sha256') != sha(Path(__file__)) or value.get('inputs_unchanged') is not True):
        raise ValueError('fresh actual product MIC tool builder receipt required')
    source = value['product_build']
    origin = Path(source['path']).parent
    private = path.parent / 'product-build'
    def relocated(original):
        try: relative = Path(original).relative_to(origin)
        except ValueError as error: raise ValueError('MIC artifact escapes original private build') from error
        if '..' in relative.parts: raise ValueError('MIC artifact traversal')
        result = private / relative
        if result.is_symlink() or not result.resolve().is_relative_to(private.resolve()):
            raise ValueError('MIC artifact symlink escape')
        return result
    product_file = relocated(source['path'])
    if sha(product_file) != source['sha256']: raise ValueError('actual product MIC build report changed')
    report = json.loads(product_file.read_text())
    if (report.get('status') != 'pass_compile_link_ONLY' or report.get('plan_only') is not False or
            report.get('changed_inputs') != [] or report.get('builder_sha256') != sha(Path(product.__file__)) or
            not report.get('installed_runtime_image_proof', {}).get('dsos')):
        raise ValueError('complete installed product MIC compile/link/image proof required')
    for command in report['commands']:
        if command.get('exit_code') != 0 or command.get('timed_out') or sha(relocated(command['log'])) != command['sha256']:
            raise ValueError('actual MIC product command failed or its complete log changed')
    from native579_artifact_context import binding_context
    for name, source_path in SOURCES.items():
        tool = value['tools'][name]; row = report['helpers'][name]
        if (row['status'] != 'pass_compile_link_ONLY' or row['source']['sha256'] != sha(source_path) or
                tool['source_sha256'] != sha(source_path) or sha(path.parent / name) != row['binary_sha256'] or
                tool['binary_sha256'] != row['binary_sha256'] or
                elf_dependencies(path.parent / name, product_name=report['product']) != row['DT_NEEDED'] or
                any(tool.get(key) != row.get(key) for key in ('DT_NEEDED', 'installed_runtime_profile',
                    'actual_link_inputs', 'actual_link_input_sonames'))):
            raise ValueError('actual compiled MIC tool source/binary/runtime receipt differs: ' + name)
        context579 = binding_context(report, row, path.parent / name,
            lambda ref: relocated(ref['path']))
        if context579['arch'] != arch: raise ValueError('actual MIC ELF/profile architecture differs')
        if '-nostdlib' not in row['link_command']: raise ValueError('MIC linker could select implicit prebuilt runtime libraries')
        verify_compile_command(report, name, row)
        if name == 'audio_capture_token':
            product.validate_flags(row['compile_command'], product=report['product'], actual_target=context579['compiler_target'])
            if not product.effective_cfi(row['link_command']): raise ValueError('MIC token actual link CFI missing')
        command = [r for r in report['commands'] if r['label'] == name + '-link']
        if len(command) != 1 or command[0]['argv'] != row['link_command'] or command[0]['exit_code'] != 0:
            raise ValueError('exact actual MIC linker command absent')
        log = relocated(command[0]['log'])
        if sha(log) != command[0]['sha256']: raise ValueError('actual MIC linker trace changed')
        # Installed replacements are absolute arguments and absolute -t rows;
        # do not probe host source/out paths while replaying container receipts.
        opened = {line.strip().split('(', 1)[0] for line in re.sub(r'\x1b\[[0-9;]*m', '', log.read_text()).splitlines()}
        for soname in row['DT_NEEDED']:
            for record in product.runtime_link_records(row, soname):
                if record['path'] not in opened: raise ValueError('installed MIC DSO missing from real linker trace')
    return value


def build(root, output, arch, runtime_profile, runtime_profile_sha256, *, normal_link_target=None):
    from production579_target import bound_profile
    actual_profile = bound_profile(runtime_profile, runtime_profile_sha256)
    if actual_profile['arch'] != arch: raise ValueError('actual MIC product profile/arch differs; no SDK fallback')
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    configure()
    builder = CaptureToolsBuilder(root, output / 'product-build', list(SOURCES),
        runtime_profile=runtime_profile, runtime_profile_sha256=runtime_profile_sha256,
        product=actual_profile['product'], normal_link_target=normal_link_target)
    native = builder.run()
    report = {'status': 'fail', 'scope': 'real_root_PCM_producer_and_independent_AccessToken_tools_ONLY',
        'arch': arch, 'product': actual_profile['product'], 'builder_sha256': sha(Path(__file__)),
        'inputs_sha256': {p: v['sha256'] for p, v in native['inputs'].items()},
        'inputs_unchanged': native.get('changed_inputs') == [], 'tools': {},
        'product_build': {'path': str(builder.output / 'build.json'), 'sha256': sha(builder.output / 'build.json')},
        'first_artifact_behavior_gate_passed': False}
    for name, row in native['helpers'].items():
        tool = {'status': 'fail', 'product_helper_status': row['status'], 'error': row.get('error')}
        report['tools'][name] = tool
        if row['status'] != 'pass_compile_link_ONLY': continue
        shutil.copyfile(row['binary'], output / name)
        library = row['installed_runtime_profile']['profile']['dsos'][LIBRARIES[name]]['staged']
        tool.update(status='pass', binary_sha256=sha(output / name), source_sha256=sha(SOURCES[name]),
            linked_library_sha256=library['sha256'],
            linked_library_runtime_sha256=runtime_identity(Path(library['path']).read_bytes(), arch),
            **{key: row[key] for key in ('DT_NEEDED', 'installed_runtime_profile', 'actual_link_inputs', 'actual_link_input_sonames')})
    if native['status'] == 'pass_compile_link_ONLY' and all(r['status'] == 'pass' for r in report['tools'].values()):
        report['status'] = 'pass'
    path = output / 'build.json'; path.write_text(json.dumps(report, indent=2) + '\n')
    if report['status'] == 'pass': verify_installed_tools(path, arch)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--runtime-profile', type=Path, required=True)
    parser.add_argument('--runtime-profile-sha256', required=True)
    parser.add_argument('--normal-link-target')
    args = parser.parse_args()
    result = build(args.source_root, args.output, args.arch, args.runtime_profile, args.runtime_profile_sha256,
        normal_link_target=args.normal_link_target)
    print(json.dumps({'status': result['status'], 'tools': result['tools']}))
    return result['status'] != 'pass'


if __name__ == '__main__': raise SystemExit(main())
