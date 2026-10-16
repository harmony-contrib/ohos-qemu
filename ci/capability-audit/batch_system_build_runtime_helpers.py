#!/usr/bin/env python3
"""Build three read-only guest helpers with actual ARM64 product innerkit/CFI ABI.

Only root may run the compiler under its resource lease. --plan-only queries the
existing Ninja graph but never invokes clang or regenerates/builds that graph.
These new helpers are diagnostics, not targets selected by a fresh product GN.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shlex
import struct
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRODUCT = 'arm64_virt'
TOKEN = {
    'graph': 'obj/base/security/access_token/interfaces/innerkits/accesstoken/libaccesstoken_sdk.ninja',
    'object': 'obj/base/security/access_token/interfaces/innerkits/accesstoken/src/libaccesstoken_sdk/accesstoken_kit.o',
    'source': 'base/security/access_token/interfaces/innerkits/accesstoken/src/accesstoken_kit.cpp',
    'header': 'base/security/access_token/interfaces/innerkits/accesstoken/include/accesstoken_kit.h'}
APP = {
    'graph': 'obj/foundation/ability/ability_runtime/interfaces/inner_api/app_manager/app_manager.ninja',
    'object': 'obj/foundation/ability/ability_runtime/interfaces/inner_api/app_manager/src/appmgr/app_manager/app_mgr_client.o',
    'source': 'foundation/ability/ability_runtime/interfaces/inner_api/app_manager/src/appmgr/app_mgr_client.cpp',
    'header': 'foundation/ability/ability_runtime/interfaces/inner_api/app_manager/include/appmgr/app_mgr_client.h'}
WALLPAPER = {
    'graph': 'obj/base/theme/wallpaper_mgr/services/wallpaper_service.ninja',
    'object': 'obj/base/theme/wallpaper_mgr/services/src/wallpaper_service/wallpaper_service.o',
    'source': 'base/theme/wallpaper_mgr/services/src/wallpaper_service.cpp',
    'header': 'base/customization/config_policy/interfaces/inner_api/include/config_policy_utils.h'}
HELPERS = {
    'contact_picker_observer': {'fixture': 'batch_apps/contact_picker_seed/observer.cpp', 'anchors': [APP, TOKEN],
        'libraries': ['ability/ability_runtime/libapp_manager.z.so', 'security/access_token/libaccesstoken_sdk.z.so'],
        'headers': [APP['header'], TOKEN['header'], 'third_party/json/include/nlohmann/json.hpp'],
        'extra_includes': ['third_party/json/include/nlohmann']},
    'wallpaper_default_resolver': {'fixture': 'batch_media/wallpaper_runtime/default_resolver.cpp', 'anchors': [WALLPAPER],
        'libraries': ['customization/config_policy/libconfigpolicy_util.z.so', 'thirdparty/cJSON/libcjson.z.so'],
        'headers': [WALLPAPER['header'], 'third_party/cJSON/cJSON.h'], 'extra_includes': []},
    'wallpaper_token_query': {'fixture': 'batch_media/wallpaper_receipts/token_query.cpp', 'anchors': [TOKEN],
        'libraries': ['security/access_token/libaccesstoken_sdk.z.so'], 'headers': [TOKEN['header']], 'extra_includes': []}}
ABI_GUARD = '''#include <string>
#include <type_traits>
#ifdef __EXCEPTIONS
#error Actual product fno-exceptions must be preserved
#endif
static_assert(std::is_same<std::string, std::__h::basic_string<char>>::value,
    "Use actual system libc++ __h headers; never redefine the ABI namespace");
'''


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def within(path, root):
    return Path(path).resolve().is_relative_to(Path(root).resolve())


def require_ro(path):
    if not os.statvfs(path).f_flag & os.ST_RDONLY:
        raise ValueError('actual input filesystem must be read-only: ' + str(path))


def regular(path):
    path = Path(path)
    if not path.is_file(): raise ValueError('actual regular input missing: ' + str(path))
    return path.resolve()


def input_record(path, root=None):
    path = regular(path)
    if root is not None and not within(path, root): raise ValueError('input escapes actual source/out: ' + str(path))
    require_ro(path)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def variables(text):
    """Only the selected per-target graph variables; unknown expansion fails."""
    result = {}
    for line in text.replace('$\n', '').splitlines():
        m = re.fullmatch(r'\s*(include_dirs|ldflags|libs) = (.*)', line)
        if m:
            if m[1] in result: raise ValueError('ambiguous selected Ninja variable: ' + m[1])
            if '$' in m[2]: raise ValueError('unexpanded selected Ninja variable: ' + m[1])
            result[m[1]] = shlex.split(m[2])
    if not {'include_dirs', 'ldflags', 'libs'} <= result.keys(): raise ValueError('incomplete actual Ninja target')
    return result


def selected_shared_dependencies(text):
    lines = [line for line in text.replace('$\n', '').splitlines() if line.startswith('build ') and ': solink ' in line]
    if len(lines) != 1: raise ValueError('one actual selected product DSO edge required')
    dependencies = shlex.split(lines[0].split(': solink ', 1)[1])
    dependencies = dependencies[:next((i for i, item in enumerate(dependencies) if item in ('|', '||')), len(dependencies))]
    # Real system CRT/runtime selection comes from the unchanged GN libs flags;
    # do not choose the product's symbol-proxy libc as a helper runtime library.
    return list(dict.fromkeys(x for x in dependencies if x.endswith('.so') and not x.startswith('obj/third_party/musl/')))


def compile_flags(command, compiler, anchor_source, build):
    """Strip only launcher/source/output/dependency effects from a real command."""
    compiler, anchor_source = Path(compiler).resolve(), Path(anchor_source).resolve()
    tokens = shlex.split(command)
    if any(x in {'&&', '||', ';', '|', '>', '<'} or x.startswith('@') for x in tokens):
        raise ValueError('unsupported shell/response syntax in actual compiler command')
    indices = [i for i, value in enumerate(tokens) if Path(value).name in ('clang++', compiler.name) and
               (Path(value) if Path(value).is_absolute() else build / value).resolve() == compiler]
    if len(indices) != 1: raise ValueError('actual product clang++ not selected exactly once')
    i = indices[0]
    if i and tokens[:i] != ['/usr/bin/ccache']: raise ValueError('unknown product compiler launcher')
    tokens = tokens[i + 1:]; result = []; sources = []; output_count = 0; compile_count = 0; n = 0
    while n < len(tokens):
        word = tokens[n]
        if word in ('-o', '-MF', '-MT', '-MQ'):
            if n + 1 == len(tokens): raise ValueError('truncated compiler output argument')
            output_count += word == '-o'; n += 2; continue
        if word in ('-c', '-MD', '-MMD', '-MP'):
            compile_count += word == '-c'; n += 1; continue
        if word.startswith(('-save-temps', '-fprofile-generate', '-ftime-trace', '-serialize-diagnostics')):
            raise ValueError('unexpected writable compiler side effect')
        if '_LIBCPP_ABI_NAMESPACE' in word or '__n1' in word: raise ValueError('ABI namespace replacement refused')
        if not word.startswith('-') and (build / word).resolve() == anchor_source:
            sources.append(word); n += 1; continue
        result.append(word); n += 1
    if len(sources) != 1 or output_count != 1 or compile_count != 1: raise ValueError('actual anchor source/output mismatch')
    return result


def cfi_flags(flags):
    return [x for x in flags if x.startswith(('-fsanitize', '-fno-sanitize', '-ftrap-function=', '-fcfi-trap-function=', '-fvisibility=')) or
            x.startswith('-Wl,--version-script=') and x.endswith('/cfi.versionscript')]


def effective_cfi(flags):
    selected = set()
    for word in flags:
        if word.startswith('-fno-sanitize='):
            for item in word.split('=', 1)[1].split(','):
                if item == 'cfi': selected = {x for x in selected if not x.startswith('cfi')}
                else: selected.discard(item)
        if word.startswith('-fsanitize='): selected.update(word.split('=', 1)[1].split(','))
    return any(x.startswith('cfi') for x in selected) and '-fsanitize-cfi-cross-dso' in flags


def validate_flags(flags):
    target = [x for x in flags if x.startswith('--target=')]
    sysroots = [x for x in flags if x.startswith('--sysroot=')]
    lto = [x for x in flags if x == '-flto' or x.startswith(('-flto=', '-fno-lto'))]
    exceptions = [x for x in flags if x in ('-fexceptions', '-fno-exceptions')]
    if (target != ['--target=aarch64-linux-ohos'] or len(sysroots) != 1 or not lto or
            lto[-1].startswith('-fno-lto') or not exceptions or exceptions[-1] != '-fno-exceptions' or
            not effective_cfi(flags)):
        raise ValueError('actual ARM64 system sysroot/LTO/CFI/fno-exceptions flags required')


def link_flags(flags, private):
    result = []; removed = []
    for word in flags:
        if word.startswith('-Wl,--version-script=') and not word.endswith('/cfi.versionscript'):
            removed.append(word); continue  # Component DSO export map is not a helper export contract.
        if word.startswith('-Wl,--thinlto-cache-dir='): word = '-Wl,--thinlto-cache-dir=' + str(private / 'lto-cache')
        if word.startswith('-Wl,--thinlto-jobs='): word = '-Wl,--thinlto-jobs=2'
        result.append(word)
    return result, removed


def dep_paths(path, build):
    text = path.read_text().replace('\\\n', '')
    if ':' not in text: raise ValueError('missing complete compiler dependency output')
    # Makefile escaping is not shell escaping. Handle spaces, # and backslashes.
    values = re.findall(r'(?:\\.|[^\s])+', text.split(':', 1)[1]); result = []
    for value in values:
        value = re.sub(r'\\(.)', r'\1', value).replace('$$', '$')
        p = Path(value); result.append((p if p.is_absolute() else build / p).resolve())
    if not result: raise ValueError('empty compiler dependency output')
    return list(dict.fromkeys(result))


def trace_link_inputs(text, build):
    paths = []
    for line in re.sub(r'\x1b\[[0-9;]*m', '', text).splitlines():
        candidate = line.strip().split('(', 1)[0]
        if not candidate: continue
        p = Path(candidate); p = p if p.is_absolute() else build / p
        if p.is_file(): paths.append(p.resolve())
    return list(dict.fromkeys(paths))


def defined_symbol(text, name):
    for line in text.splitlines():
        fields = line.split(maxsplit=7)
        if len(fields) == 8 and fields[0].endswith(':') and fields[6] != 'UND' and fields[7].split('@')[0] == name:
            return True
    return False


def elf_header(path, executable=False):
    data = Path(path).read_bytes()
    if len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('actual ELF64 little-endian AArch64 required')
    if struct.unpack_from('<H', data, 16)[0] != 3: raise ValueError('actual DSO/PIE ELF type required')
    if executable:
        offset = struct.unpack_from('<Q', data, 32)[0]; size, count = struct.unpack_from('<HH', data, 54)
        if size != 56 or count == 0 or offset + count * size > len(data): raise ValueError('invalid actual program headers')
        interpreter = None
        for i in range(count):
            kind, flags, file_offset, _, _, file_size, _, _ = struct.unpack_from('<IIQQQQQQ', data, offset + i * size)
            if kind == 3: interpreter = data[file_offset:file_offset + file_size].rstrip(b'\0').decode('ascii')
        if interpreter is None or not interpreter.startswith('/') or not interpreter.endswith('ld-musl-aarch64.so.1'):
            raise ValueError('actual ARM64 musl guest interpreter absent')
    return {'class': 64, 'machine': 183, 'type': 'ET_DYN', 'sha256': sha(path)}


class Builder:
    def __init__(self, source, output, helpers, plan_only=False):
        self.root = Path(source).resolve(); self.build = self.root / 'out' / PRODUCT
        self.output = Path(output).resolve(); self.helpers = helpers; self.plan_only = plan_only
        for p in (self.root, self.root / 'out', self.build): require_ro(p)
        if any(within(self.output, p) for p in (self.root, ROOT)):
            raise ValueError('private output must be outside source/out and repository')
        self.output.mkdir(parents=True, exist_ok=False)
        self.compiler = regular(self.root / 'prebuilts/clang/ohos/linux-x86_64/llvm/bin/clang++')
        self.ninja = regular(self.root / 'prebuilts/build-tools/linux-x86/bin/ninja')
        self.readelf = regular(self.compiler.parent / 'llvm-readelf')
        self.inputs = {}
        self.report = {'status': 'fail', 'scope': 'diagnostic_new_helpers_using_existing_actual_product_GN_flags_NOT_fresh_GN_target_selection_or_runtime',
            'product': PRODUCT, 'plan_only': plan_only, 'source_root': str(self.root), 'build_directory': str(self.build),
            'builder_sha256': sha(Path(__file__)), 'commands': [], 'helpers': {}, 'inputs': self.inputs,
            'requirements_closed': 0, 'first_artifact_behavior_gate_passed': False}
        self.environment = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C', TMPDIR=str(self.output / 'tmp'))
        for key in ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
                    'LIBRARY_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'CFLAGS', 'CXXFLAGS', 'LDFLAGS'):
            self.environment.pop(key, None)
        (self.output / 'tmp').mkdir()

    def remember(self, path, source=True):
        row = input_record(path, self.root if source else None)
        previous = self.inputs.get(row['path'])
        if previous is not None and previous['sha256'] != row['sha256']: raise ValueError('actual shared input changed between helpers')
        self.inputs[row['path']] = row
        return row

    def save(self):
        (self.output / 'build.json').write_text(json.dumps(self.report, indent=2) + '\n')

    def command(self, argv, label, timeout=180):
        log = self.output / (str(len(self.report['commands'])).zfill(3) + '-' + label + '.log')
        row = {'argv': list(map(str, argv)), 'cwd': str(self.build), 'log': str(log), 'label': label}
        self.report['commands'].append(row); self.save()
        with log.open('xb') as stream:
            try:
                process = subprocess.Popen(row['argv'], cwd=self.build, env=self.environment,
                    stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    row['exit_code'] = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Only this command's newly owned process group is signalled.
                    os.killpg(process.pid, signal.SIGTERM)
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); process.wait()
                    row.update(exit_code=124, timed_out=True, process_returncode=process.returncode)
            except OSError as error:
                stream.write((str(error) + '\n').encode()); row.update(exit_code=127, launch_error=str(error))
        row['sha256'] = sha(log); self.save()
        if row['exit_code']: raise ValueError('actual command failed: ' + label)
        return log.read_text(errors='replace')

    def anchor(self, spec, name):
        graph = self.build / spec['graph']; self.remember(graph); self.remember(self.root / spec['source'])
        self.remember(self.root / Path(spec['graph']).relative_to('obj').parent / 'BUILD.gn')
        text = graph.read_text(); v = variables(text)
        output = self.command([self.ninja, '-w', 'dupbuild=warn', '-C', self.build, '-t', 'commands', '-s', spec['object']],
                              name + '-actual-GN-command', timeout=30)
        lines = [line for line in output.splitlines() if 'clang++ ' in line and ' -c ' in line]
        if len(lines) != 1: raise ValueError('ambiguous actual one-object compiler command')
        v['flags'] = compile_flags(lines[0], self.compiler, (self.root / spec['source']).resolve(), self.build)
        v['selected_shared_dependencies'] = selected_shared_dependencies(text)
        v['actual_command'] = lines[0]; v['graph'] = self.remember(graph); v['object_target'] = spec['object']
        return v

    def helper(self, name):
        spec = HELPERS[name]; private = self.output / name; private.mkdir()
        row = {'status': 'fail', 'fixture': spec['fixture']}; self.report['helpers'][name] = row; self.save()
        try:
            fixture = HERE / 'fixtures' / spec['fixture']; row['source'] = self.remember(fixture, source=False)
            source = private / fixture.name; source.write_bytes(fixture.read_bytes())
            guard = private / 'actual_system_abi.h'; guard.write_text(ABI_GUARD); row['abi_guard_sha256'] = sha(guard)
            anchors = [self.anchor(s, name + '-' + str(i)) for i, s in enumerate(spec['anchors'])]
            flags = anchors[0]['flags'][:]; ld = anchors[0]['ldflags'][:]
            runtime_libs = list(dict.fromkeys(word for anchor in anchors for word in anchor['libs']))
            row['actual_runtime_libraries_from_anchors'] = runtime_libs
            if not effective_cfi(flags):
                flags += cfi_flags(anchors[-1]['flags']); ld += cfi_flags(anchors[-1]['ldflags'])
                row['diagnostic_cfi_augmentation_from_actual_product_graph'] = spec['anchors'][-1]['graph']
            validate_flags(flags)
            sysroot = next(x.split('=', 1)[1] for x in flags if x.startswith('--sysroot='))
            if (self.build / sysroot).resolve() != (self.build / 'obj/third_party/musl').resolve():
                raise ValueError('actual system product musl sysroot required; SDK sysroot refused')
            includes = []
            for a in anchors:
                includes += [x for x in a['include_dirs'] if x not in includes]
            includes += ['-I' + str(self.root / p) for p in spec['extra_includes']]
            row['anchors'] = anchors
            for header in spec['headers']: self.remember(self.root / header)
            direct = [self.build / p for p in spec['libraries']]
            # These actual GN public dependencies support inline innerkit types.
            if name == 'contact_picker_observer':
                direct += [self.build / 'commonlibrary/c_utils/libutils.z.so', self.build / 'communication/ipc/libipc_single.z.so']
            direct += [self.build / p for anchor in anchors for p in anchor['selected_shared_dependencies']]
            direct = list(dict.fromkeys(direct))
            row['linked_libraries'] = [self.remember(p) for p in direct]
            for p in direct: elf_header(p)
            self.remember(self.compiler); self.remember(self.readelf); self.remember(self.ninja)
            self.remember(self.build / 'toolchain.ninja')
            flags += [x for x in includes if x not in flags]
            obj, binary, deps = private / (name + '.o'), private / name, private / 'headers.d'
            compile_cmd = [self.compiler, *flags, '-fPIE', '-include', guard, '-MD', '-MF', deps, '-c', source, '-o', obj]
            ld, removed = link_flags(ld, private); row['removed_component_DSO_only_export_maps'] = removed
            crtroot = self.build / 'obj/third_party/musl/usr/lib/aarch64-linux-ohos'
            crt = [crtroot / n for n in ('Scrt1.o', 'crti.o', 'crtn.o')]
            for p in crt: self.remember(p)
            # Product link flags and runtime libraries are unchanged apart from
            # private cache/CPU limits and adapting DSO output to this new PIE.
            searches = ['-Wl,-rpath-link=' + str(path) for path in dict.fromkeys(p.parent for p in direct)]
            link_cmd = [self.compiler, *ld, *searches, '-pie', '-Wl,--threads=2', '-Wl,--export-dynamic', '-o', binary,
                *crt[:2], '-Wl,-t', '-Wl,--start-group', obj, *direct, *runtime_libs, '-Wl,--end-group', crt[2]]
            if not effective_cfi(ld) or not any(x == '-flto' or x.startswith('-flto=') for x in ld):
                raise ValueError('actual link LTO/CFI must be retained too')
            row.update(compile_command=list(map(str, compile_cmd)), link_command=list(map(str, link_cmd)),
                       compile_LTO_flags=[x for x in flags if 'lto' in x], CFI_preserved=effective_cfi(flags))
            for word in [*flags, *ld, *runtime_libs]:
                if word.startswith(('-fsanitize-blacklist=', '-fsanitize-ignorelist=', '-Wl,--version-script=')):
                    self.remember(self.build / word.split('=', 1)[1])
                elif not word.startswith('-') and word.endswith(('.a', '.so')):
                    self.remember(self.build / word)
            row['private_source_sha256'] = sha(source)
            self.save()
            if self.plan_only: row['status'] = 'planned_NOT_compiled'; return
            self.command(compile_cmd, name + '-compile')
            headers = []
            for p in dep_paths(deps, self.build):
                if p in (source.resolve(), guard.resolve()): headers.append({'path': str(p), 'sha256': sha(p)})
                else: headers.append(self.remember(p))
            row['actual_compiler_dependencies'] = headers; row['depfile_sha256'] = sha(deps)
            trace = self.command(link_cmd, name + '-link')
            opened = trace_link_inputs(trace, self.build)
            row['actual_link_inputs'] = [self.remember(p) for p in opened if within(p, self.root)]
            if not all(p.resolve() in opened for p in direct): raise ValueError('link trace omitted actual direct product DSO')
            if not any('libc++' in p.name for p in opened): raise ValueError('actual system libc++ link identity absent')
            if any(not within(p, self.root) and not within(p, private) for p in opened):
                raise ValueError('linker consumed an input outside read-only product/private helper')
            row['elf'] = elf_header(binary, executable=True)
            info = self.command([self.readelf, '-h', '-l', '-d', '--dyn-syms', '--wide', '--demangle', binary], name + '-actual-ELF-ABI')
            if not defined_symbol(info, '__cfi_check') or 'std::__h::' not in info or 'std::__n1::' in info:
                raise ValueError('actual guest ELF lacks system __h ABI/CFI or exposes SDK __n1 ABI')
            needed = set(re.findall(r'\(NEEDED\).*?\[([^]\n]+)\]', info))
            if not {Path(n).name for n in spec['libraries']} <= needed:
                raise ValueError('actual helper does not bind its required product SONAMEs')
            row['DT_NEEDED'] = sorted(needed)
            for p in direct:
                if p.name not in {Path(value).name for value in spec['libraries']}: continue
                symbols = self.command([self.readelf, '-h', '-d', '--dyn-syms', '--wide', '--demangle', p], name + '-linked-' + p.name)
                if p.name == 'libaccesstoken_sdk.z.so' and not defined_symbol(symbols, '__cfi_check'):
                    raise ValueError('actual product AccessToken DSO lacks its selected cross-DSO CFI')
            if sha(source) != row['source']['sha256'] or sha(guard) != row['abi_guard_sha256']:
                raise ValueError('private source/ABI guard changed during compiler invocation')
            row.update(status='pass_compile_link_ONLY', binary=str(binary), binary_sha256=sha(binary), runtime_validated=False)
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            row['error'] = type(e).__name__ + ': ' + str(e)
        finally:
            self.save()

    def run(self):
        for name in self.helpers: self.helper(name)
        changed = []
        for name, row in self.inputs.items():
            try:
                require_ro(name)
                if sha(name) != row['sha256']: changed.append(name)
            except (OSError, ValueError): changed.append(name)
        self.report['changed_inputs'] = changed
        expected = 'planned_NOT_compiled' if self.plan_only else 'pass_compile_link_ONLY'
        if not changed and all(row['status'] == expected for row in self.report['helpers'].values()):
            self.report['status'] = 'planned_NOT_compiled' if self.plan_only else 'pass_compile_link_ONLY'
        self.save(); return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=[PRODUCT], required=True)
    parser.add_argument('--helper', choices=HELPERS, action='append', help='Repeat to select; default all three')
    parser.add_argument('--plan-only', action='store_true', help='Read/query existing GN only; never clang/build GN')
    args = parser.parse_args()
    helpers = args.helper or list(HELPERS)
    if len(helpers) != len(set(helpers)): parser.error('duplicate helper selection')
    try:
        report = Builder(args.source_root, args.output, helpers, args.plan_only).run()
        print(json.dumps({'status': report['status'], 'helpers': {n: r['status'] for n, r in report['helpers'].items()}}))
        return 1 if report['status'] == 'fail' else 0
    except (OSError, ValueError) as e:
        print(json.dumps({'status': 'fail', 'error': type(e).__name__ + ': ' + str(e)})); return 1


if __name__ == '__main__': raise SystemExit(main())
