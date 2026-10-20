#!/usr/bin/env python3
"""Build read-only guest helpers with actual ARM64 product innerkit/CFI ABI.

Only root may run the compiler under its resource lease. --plan-only queries the
existing Ninja graph but never invokes clang or regenerates/builds that graph.
These new helpers are diagnostics, not targets selected by a fresh product GN.
--verify-existing reads immutable prior compile/link artifacts and checks their
ELF/DSO contracts; it never invokes Ninja, clang, a linker or a guest executable.
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
import sys
import tarfile
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
        'libraries': ['security/access_token/libaccesstoken_sdk.z.so'], 'headers': [TOKEN['header']], 'extra_includes': []},
    'knowledge_token_query': {'fixture': 'batch_media/knowledge_runtime/knowledge_token_query.cpp', 'anchors': [TOKEN],
        'libraries': ['security/access_token/libaccesstoken_sdk.z.so'], 'headers': [TOKEN['header']], 'extra_includes': []}}
# Private fixed Number diagnostic only; all original Builder/ExistingVerifier guards retained.
HELPERS["number_token_query395"] = {'fixture': 'batch_apps/number_runtime/number_token_query395.cpp', 'anchors': [{'graph': 'obj/base/security/access_token/interfaces/innerkits/accesstoken/libaccesstoken_sdk.ninja', 'object': 'obj/base/security/access_token/interfaces/innerkits/accesstoken/src/libaccesstoken_sdk/accesstoken_kit.o', 'source': 'base/security/access_token/interfaces/innerkits/accesstoken/src/accesstoken_kit.cpp', 'header': 'base/security/access_token/interfaces/innerkits/accesstoken/include/accesstoken_kit.h'}], 'libraries': ['security/access_token/libaccesstoken_sdk.z.so'], 'headers': ['base/security/access_token/interfaces/innerkits/accesstoken/include/accesstoken_kit.h', 'base/security/access_token/interfaces/innerkits/accesstoken/include/hap_token_info.h'], 'extra_includes': []}

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
    # LLVM tools select their driver/output format using argv[0]. Keep clang++
    # and llvm-readelf, while input_record hashes their canonical file targets.
    return path.absolute()


def input_record(path, root=None):
    path = regular(path).resolve()
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
            literal = m[2].replace('$:', ':')  # Ninja's literal-colon escape is not variable expansion.
            if '$' in literal: raise ValueError('unexpanded selected Ninja variable: ' + m[1])
            result[m[1]] = shlex.split(literal)
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
    indices = [i for i, value in enumerate(tokens) if Path(value).name in ('clang', 'clang++', compiler.name) and
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
    # llvm-readobj's actual LLVM format (including an llvm-readelf symlink whose
    # argv[0] was canonicalized by the original builder). A Name mention alone,
    # a missing Section, or an undefined symbol never satisfies this check.
    for block in re.findall(r'(?ms)^\s*Symbol \{\s*\n(.*?)^\s*\}\s*$', text):
        names = re.findall(r'(?m)^\s*Name: (.+)$', block)
        sections = re.findall(r'(?m)^\s*Section: (.+)$', block)
        if len(names) != 1 or len(sections) != 1: continue
        symbol = re.sub(r' \([0-9]+\)$', '', names[0]).split('@')[0]
        section = sections[0].split(' (', 1)[0]
        if symbol == name and section not in ('Undefined', 'UND', ''): return True
    return False


def dynamic_needed(text):
    """Actual GNU readelf and LLVM readobj dynamic-table rows, not mentions."""
    return set(re.findall(r'(?m)^\s*0x[0-9A-Fa-f]+\s+\(?NEEDED\)?\s+Shared library: \[([^\]\n]+)\]\s*$', text))


def elf_soname(path):
    """Read DT_SONAME from actual ELF bytes, without trusting a basename/tool claim."""
    elf_header(path)
    data = Path(path).read_bytes()
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    if size != 56 or not count or offset + size * count > len(data):
        raise ValueError('invalid DSO program headers')
    loads, dynamic = [], []
    for i in range(count):
        kind, _, start, va, _, length, _, _ = struct.unpack_from('<IIQQQQQQ', data, offset + i * size)
        if start + length > len(data): raise ValueError('DSO segment outside file')
        if kind == 1: loads.append((va, start, length))
        if kind == 2:
            if length % 16: raise ValueError('invalid DSO dynamic table size')
            dynamic += [struct.unpack_from('<qQ', data, n) for n in range(start, start + length, 16)]
    tags = {}
    for tag, value in dynamic:
        if tag == 0: break
        if tag in (5, 10, 14):
            if tag in tags: raise ValueError('ambiguous DSO SONAME/string table')
            tags[tag] = value
    if 14 not in tags: return None
    if not {5, 10} <= tags.keys() or tags[14] >= tags[10]: raise ValueError('invalid DSO SONAME table')
    tables = [start + tags[5] - va for va, start, length in loads
              if va <= tags[5] and tags[5] + tags[10] <= va + length]
    if len(tables) != 1: raise ValueError('DSO string table is not file backed')
    begin, end = tables[0] + tags[14], tables[0] + tags[10]
    stop = data.find(b'\0', begin, end)
    if stop < 0: raise ValueError('unterminated DSO SONAME')
    result = data[begin:stop].decode('ascii')
    if not re.fullmatch(r'[A-Za-z0-9_.+\-]+', result): raise ValueError('unsafe DSO SONAME')
    return result


def _profile_record(value):
    if (not isinstance(value, dict) or not {'path', 'sha256', 'bytes'} <= value.keys() or
            not isinstance(value['path'], str) or not value['path'].startswith('/') or
            any(p in ('', '.', '..') for p in value['path'].split('/')[1:]) or
            not re.fullmatch(r'[A-Za-z0-9_./+\-]+', value['path']) or
            not isinstance(value.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', value['sha256']) or
            type(value.get('bytes')) is not int or value['bytes'] <= 0):
        raise ValueError('exact absolute file/hash/size profile record required')
    return value


def validate_installed_profile(profile, *, archive_sha256=None, system_image_sha256=None):
    """Pure schema/binding check. File existence and ELF checks belong to Builder.

    Every DSO has independent image-dump bytes and its real installation source.
    Guest paths are derived from packages/<device>/system, never collector input.
    The root producer owns extraction of image_file from image_member; the whole
    archive/image and these independent dumped bytes are immutable build inputs.
    """
    keys = {'schema_version', 'kind', 'product', 'arch', 'device', 'source_root', 'archive', 'system_image', 'dsos'}
    if (not isinstance(profile, dict) or not keys <= profile.keys() or set(profile) - keys - {'vendor_image'} or
            type(profile['schema_version']) is not int or profile['schema_version'] != 1 or
            profile['kind'] != 'installed_product_runtime' or profile['product'] != PRODUCT or
            profile['arch'] != 'arm64' or profile['device'] not in ('phone', '2in1')):
        raise ValueError('versioned actual ARM64 installed runtime profile required')
    root = profile['source_root']
    _profile_record(dict(path=root, sha256='0' * 64, bytes=1))
    archive = _profile_record(profile['archive']); image = _profile_record(profile['system_image'])
    for name in ('system', 'vendor'):
        if name + '_image' not in profile: continue
        descriptor = _profile_record(profile[name + '_image'])
        member = descriptor.get('archive_member', '')
        if (not re.fullmatch(r'[A-Za-z0-9_.+\-/]+/images/' + name + r'\.img', member) or
                member.startswith('/') or any(p in ('', '.', '..') for p in member.split('/'))):
            raise ValueError('exact ' + name + '.img archive member required')
        if member != 'openharmony-qemu-arm64-' + PRODUCT + '-' + profile['device'] + '/images/' + name + '.img':
            raise ValueError('archive member product/device differs from installed profile')
    if ((archive_sha256 is not None and archive['sha256'] != archive_sha256) or
            (system_image_sha256 is not None and image['sha256'] != system_image_sha256)):
        raise ValueError('installed runtime profile belongs to another archive/system image')
    entries = profile['dsos']
    if not isinstance(entries, dict) or not {'libc++.so', 'libc.so'} <= entries.keys():
        raise ValueError('installed system libc++ and musl loader profile required')
    prefix = root.rstrip('/') + '/out/' + PRODUCT + '/packages/' + profile['device']
    paths = set()
    for soname, entry in entries.items():
        if (not isinstance(soname, str) or not re.fullmatch(r'[A-Za-z0-9_.+\-]+', soname) or not isinstance(entry, dict) or
                set(entry) != {'soname', 'staged', 'image_file', 'image_member'} or entry['soname'] != soname):
            raise ValueError('unambiguous installed DSO SONAME entry required')
        staged, dumped = _profile_record(entry['staged']), _profile_record(entry['image_file'])
        suffix = staged['path'].removeprefix(prefix + '/')
        partition, _, rest = suffix.partition('/')
        relative = '/' + rest
        if (suffix == staged['path'] or partition not in ('system', 'vendor') or
                partition + '_image' not in profile or not rest or
                entry['image_member'] != relative or staged['path'] in paths or
                staged['path'] == dumped['path'] or
                (staged['sha256'], staged['bytes']) != (dumped['sha256'], dumped['bytes'])):
            raise ValueError('installed staging/image member/full bytes binding differs: ' + soname)
        paths.add(staged['path'])
        basename = relative.rsplit('/', 1)[-1]
        if basename != soname and not (soname == 'libc.so' and basename == 'ld-musl-aarch64.so.1'):
            raise ValueError('unproved installed SONAME/file alias: ' + soname)
        if soname == 'libc.so' and basename != 'ld-musl-aarch64.so.1':
            raise ValueError('use the actual installed musl loader, never a libc symbol proxy')
        if soname == 'libc++.so' and relative != '/lib64/chipset-sdk-sp/libc++.so':
            raise ValueError('actual system __h libc++ installation required')
    return entries


def _runtime_profile(row, archive_sha256=None):
    if not isinstance(row, dict): raise ValueError('actual helper receipt must be an object')
    receipt = row.get('installed_runtime_profile', {})
    if not isinstance(receipt, dict) or set(receipt) != {'source', 'profile'}:
        raise ValueError('fresh installed-runtime build receipt absent')
    _profile_record(receipt['source'])
    validate_installed_profile(receipt['profile'], archive_sha256=archive_sha256)
    return receipt['profile']


def runtime_link_records(row, soname):
    """Pure strict alias contract; it cannot retrofit a legacy linker receipt."""
    profile = _runtime_profile(row)
    if soname not in profile['dsos']: raise ValueError('DT_NEEDED absent from installed runtime profile: ' + soname)
    expected = profile['dsos'][soname]['staged']
    inputs, names = row.get('actual_link_inputs', []), row.get('actual_link_input_sonames', {})
    if (not isinstance(inputs, list) or not all(isinstance(r, dict) for r in inputs) or not isinstance(names, dict)):
        raise ValueError('actual opened ELF identities absent')
    selected = [r for r in inputs if names.get(r.get('path')) == soname]
    if len(selected) != 1 or any(selected[0].get(k) != expected[k] for k in ('path', 'sha256', 'bytes')):
        raise ValueError('actual linker did not exclusively open installed DSO bytes: ' + soname)
    return selected


def runtime_guest_paths(row, soname):
    runtime_link_records(row, soname)
    profile = _runtime_profile(row); entry = profile['dsos'][soname]
    prefix = profile['source_root'].rstrip('/') + '/out/' + PRODUCT + '/packages/' + profile['device'] + '/'
    partition = entry['staged']['path'].removeprefix(prefix).split('/', 1)[0]
    return ('/' + partition + entry['image_member'],)


def runtime_guest_script(row, soname):
    """Exact POSIX observation shared by collector and independent replay."""
    path, = runtime_guest_paths(row, soname)
    quoted = shlex.quote(path)
    return 'test -f ' + quoted + ' && test ! -L ' + quoted + ' && sha256sum ' + quoted


def verify_guest_runtime(row, soname, guest_path, sha256, *, archive_sha256):
    profile = _runtime_profile(row, archive_sha256)
    if guest_path not in runtime_guest_paths(row, soname) or sha256 != profile['dsos'][soname]['staged']['sha256']:
        raise ValueError('same-new-guest installed runtime differs: ' + soname)


def verify_guest_runtime_raw(row, soname, raw, *, archive_sha256):
    if not isinstance(raw, str): raise ValueError('actual guest SHA output must be text')
    lines = raw.splitlines()
    if len(lines) != 1: raise ValueError('one exact installed guest DSO SHA row required: ' + soname)
    match = re.fullmatch(r'([0-9a-f]{64})  (/[^\s]+)', lines[0])
    if not match: raise ValueError('malformed actual guest DSO SHA row: ' + soname)
    verify_guest_runtime(row, soname, match[2], match[1], archive_sha256=archive_sha256)
    return {'soname': soname, 'path': match[2], 'sha256': match[1]}


def replace_runtime_libraries(libraries, profile):
    """Explicit installed runtime relinks, never false same-byte equivalence.

    The selected UBSan runtime can differ from the installed runtime too. Static
    builtins/unwind/ABI archives remain exactly as selected by the GN graph.
    """
    entries = validate_installed_profile(profile)
    if any(libraries.count(flag) != 1 for flag in ('-lc++', '-lc')):
        raise ValueError('one exact GN -lc++ and -lc selection required')
    replacement = {'-lc++': entries['libc++.so']['staged']['path'], '-lc': entries['libc.so']['staged']['path']}
    result = []
    for word in libraries:
        if Path(word).name == 'libclang_rt.ubsan_minimal.so':
            if 'libclang_rt.ubsan_minimal.so' not in entries: raise ValueError('installed UBSan runtime profile absent')
            word = entries['libclang_rt.ubsan_minimal.so']['staged']['path']
        else: word = replacement.get(word, word)
        result.append(word)
    return result


def argument(argv, option):
    if not isinstance(argv, list) or not all(isinstance(word, str) for word in argv):
        raise ValueError('invalid recorded command arguments')
    positions = [i for i, word in enumerate(argv) if word == option]
    if len(positions) != 1 or positions[0] + 1 == len(argv):
        raise ValueError('one recorded command argument required: ' + option)
    return argv[positions[0] + 1]


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
    def __init__(self, source, output, helpers, plan_only=False, *, runtime_profile=None,
                 runtime_profile_sha256=None, _existing=False):
        self.root = Path(source).resolve(); self.build = self.root / 'out' / PRODUCT
        self.output = Path(output).resolve(); self.helpers = helpers; self.plan_only = plan_only
        for p in (self.root, self.root / 'out', self.build): require_ro(p)
        if any(within(self.output, p) for p in (self.root, ROOT)):
            raise ValueError('private output must be outside source/out and repository')
        self.output.mkdir(parents=True, exist_ok=False)
        self.compiler = regular(self.root / 'prebuilts/clang/ohos/linux-x86_64/llvm/bin/clang++')
        self.c_compiler = regular(self.compiler.parent / 'clang')
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
        self.installed_runtime = None
        if not _existing:
            try: self.load_runtime_profile(runtime_profile, runtime_profile_sha256)
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, tarfile.TarError) as error:
                self.report['preflight_error'] = type(error).__name__ + ': ' + str(error); self.save(); raise

    def load_runtime_profile(self, path, expected_sha256):
        if path is None or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256 or ''):
            raise ValueError('fresh builds require --runtime-profile and its external --runtime-profile-sha256')
        source = self.remember(path, source=False)
        if source['sha256'] != expected_sha256: raise ValueError('installed runtime profile SHA256 mismatch')
        profile = json.loads(Path(path).read_text())
        entries = validate_installed_profile(profile)
        if profile['source_root'] != str(self.root): raise ValueError('installed runtime profile source root differs')
        self.installed_runtime = {'source': source, 'profile': profile}
        self.report['installed_runtime_profile'] = self.installed_runtime
        archive = profile['archive']
        self.verify_profile_file(archive)
        # Read exact tar members without extracting paths, executing a guest or
        # trusting a prefilled hash. Each image file must equal its archive bytes.
        images = {name: profile[name + '_image'] for name in ('system', 'vendor') if name + '_image' in profile}
        for image in images.values(): self.verify_profile_file(image)
        proofs = {}
        with tarfile.open(archive['path'], 'r:*') as package:
            selected = {image['archive_member']: name for name, image in images.items()}
            seen = set()
            for member in package:
                if member.name not in selected: continue
                if member.name in seen or not member.isfile(): raise ValueError('ambiguous/nonregular archive image member')
                seen.add(member.name); name = selected[member.name]; image = images[name]
                if member.size != image['bytes']: raise ValueError('archive image member size differs')
                stream = package.extractfile(member); digest = hashlib.sha256()
                if stream is None: raise ValueError('archive image stream absent')
                with stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
                if digest.hexdigest() != image['sha256']: raise ValueError('archive image member SHA differs')
                proofs[name] = {'archive_member': member.name, 'sha256': digest.hexdigest(), 'bytes': member.size}
            if seen != set(selected): raise ValueError('archive does not contain every profiled image exactly once')
        scripts = ROOT / 'scripts'
        sys.path.insert(0, str(scripts))
        try:
            from ext_image_entries import dump_unique_file
            from verify_alsa_config_image import debugfs_path
        finally: sys.path.pop(0)
        executable = regular(debugfs_path())
        tools = {'debugfs': self.remember(executable, source=False),
                 'extractor': self.remember(scripts / 'ext_image_entries.py', source=False),
                 'selector': self.remember(scripts / 'verify_alsa_config_image.py', source=False)}
        destination = self.output / 'installed-runtime-image'; destination.mkdir()
        dumps = {}
        prefix = str(self.build / 'packages' / profile['device']) + '/'
        for index, (soname, entry) in enumerate(entries.items()):
            for descriptor in (entry['staged'], entry['image_file']): self.verify_profile_file(descriptor)
            for descriptor in (entry['staged'], entry['image_file']):
                if elf_soname(descriptor['path']) != soname: raise ValueError('actual ELF SONAME differs: ' + soname)
            partition = entry['staged']['path'].removeprefix(prefix).split('/', 1)[0]
            image = images[partition]; private = destination / str(index); private.mkdir()
            stat = self.command([executable, '-R', 'stat ' + entry['image_member'], image['path']],
                                'installed-runtime-stat-' + soname)
            dumped, identity = dump_unique_file(image['path'], (entry['image_member'],), private, str(executable))
            expected = entry['staged']
            if (dumped.stat().st_size != expected['bytes'] or sha(dumped) != expected['sha256'] or
                    elf_soname(dumped) != soname or
                    not re.search(r'(?m)^Inode: ' + str(identity['image_inode']) + r'\s+Type: regular\s', stat)):
                raise ValueError('independent actual image extraction differs from staged runtime: ' + soname)
            dumps[soname] = dict(identity, path=str(dumped), sha256=sha(dumped), bytes=dumped.stat().st_size,
                                 partition=partition, stat_command=len(self.report['commands']) - 1)
        self.report['installed_runtime_image_proof'] = {'archive_members': proofs, 'tools': tools, 'dsos': dumps}
        self.save()

    def verify_profile_file(self, descriptor):
        actual = self.remember(descriptor['path'], source=False)
        if any(actual[key] != descriptor[key] for key in ('path', 'sha256', 'bytes')):
            raise ValueError('actual immutable profile file differs: ' + descriptor['path'])
        return actual

    def installed_direct(self, paths, row):
        row['original_GN_direct_libraries'] = [self.remember(p) for p in paths]
        entries = self.installed_runtime['profile']['dsos']; result = []
        for path in paths:
            soname = elf_soname(path)
            if soname in entries:
                expected = entries[soname]['staged']
                if sha(path) != expected['sha256'] or path.stat().st_size != expected['bytes']:
                    if soname not in ('libc++.so', 'libc.so', 'libclang_rt.ubsan_minimal.so'):
                        raise ValueError('GN direct DSO differs from installed bytes (no silent substitution): ' + soname)
                    row.setdefault('runtime_replacements', []).append({'GN_selection': str(path),
                        'prior_file': self.remember(path), 'installed': self.remember(expected['path']),
                        'reason': 'explicit installed runtime relink of GN direct dependency; no same-byte claim'})
                result.append(Path(expected['path']))
            else: result.append(path)
        return list(dict.fromkeys(result))

    def bind_link_runtime(self, row, opened):
        row['installed_runtime_profile'] = self.installed_runtime
        names = {}
        for path in opened:
            with path.open('rb') as stream: magic = stream.read(4)
            if magic == b'\x7fELF' and struct.unpack_from('<H', path.read_bytes(), 16)[0] == 3:
                names[str(path)] = elf_soname(path)
                if (path.name in self.installed_runtime['profile']['dsos'] and names[str(path)] != path.name or
                        path.name == 'ld-musl-aarch64.so.1' and names[str(path)] != 'libc.so'):
                    raise ValueError('actual linker input file has an unexpected SONAME: ' + str(path))
        row['actual_link_input_sonames'] = names
        # Reject any wrong same-SONAME ELF, including hidden driver fallbacks.
        for soname in self.installed_runtime['profile']['dsos']:
            if soname in names.values(): runtime_link_records(row, soname)

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
        driver = self.c_compiler if spec['source'].endswith('.c') else self.compiler
        lines = [line for line in output.splitlines() if driver.name + ' ' in line and ' -c ' in line]
        if len(lines) != 1: raise ValueError('ambiguous actual one-object compiler command')
        v['flags'] = compile_flags(lines[0], driver, (self.root / spec['source']).resolve(), self.build)
        v['selected_shared_dependencies'] = selected_shared_dependencies(text)
        v['actual_command'] = lines[0]; v['graph'] = self.remember(graph); v['object_target'] = spec['object']
        return v

    def check_elf(self, name, binary, direct, row):
        """Shared strict contract for fresh builds and immutable artifact rechecks."""
        spec = HELPERS[name]
        row['elf'] = elf_header(binary, executable=True)
        info = self.command([self.readelf, '-h', '-l', '-d', '--dyn-syms', '--wide', '--demangle', binary], name + '-actual-ELF-ABI')
        if not defined_symbol(info, '__cfi_check') or 'std::__h::' not in info or 'std::__n1::' in info:
            raise ValueError('actual guest ELF lacks system __h ABI/CFI or exposes SDK __n1 ABI')
        needed = dynamic_needed(info)
        if not {Path(n).name for n in spec['libraries']} <= needed:
            raise ValueError('actual helper does not bind its required product SONAMEs')
        row['DT_NEEDED'] = sorted(needed)
        if row.get('installed_runtime_profile') is not None:
            for soname in needed: runtime_link_records(row, soname)
        for p in direct:
            if p.name not in {Path(value).name for value in spec['libraries']}: continue
            elf_header(p)
            symbols = self.command([self.readelf, '-h', '-d', '--dyn-syms', '--wide', '--demangle', p], name + '-linked-' + p.name)
            if p.name == 'libaccesstoken_sdk.z.so' and not defined_symbol(symbols, '__cfi_check'):
                raise ValueError('actual product AccessToken DSO lacks its selected cross-DSO CFI')

    def helper(self, name):
        spec = HELPERS[name]; private = self.output / name; private.mkdir()
        row = {'status': 'fail', 'fixture': spec['fixture']}; self.report['helpers'][name] = row; self.save()
        try:
            fixture = Path(spec.get('source_file', HERE / 'fixtures' / spec['fixture']))
            if not within(fixture, HERE): raise ValueError('helper source outside owned QA tools')
            row['source'] = self.remember(fixture, source=False)
            source = private / fixture.name; source.write_bytes(fixture.read_bytes())
            c_language = spec.get('language') == 'c'
            driver = self.c_compiler if c_language else self.compiler
            guard = private / 'actual_system_abi.h'
            guard.write_text('/* C helper retains actual C GN flags; no C++ ABI assertion. */\n' if c_language else ABI_GUARD)
            row['abi_guard_sha256'] = sha(guard); row['language'] = 'c' if c_language else 'c++'
            anchors = [self.anchor(s, name + '-' + str(i)) for i, s in enumerate(spec['anchors'])]
            flags = anchors[0]['flags'][:]; ld = anchors[0]['ldflags'][:]
            runtime_libs = list(dict.fromkeys(word for anchor in anchors for word in anchor['libs']))
            row['actual_runtime_libraries_from_anchors'] = runtime_libs
            selected_runtime = runtime_libs
            runtime_libs = replace_runtime_libraries(runtime_libs, self.installed_runtime['profile'])
            row['runtime_replacements'] = []
            for before, after in zip(selected_runtime, runtime_libs):
                if before != after:
                    previous = self.remember(self.build / before) if not before.startswith('-') else None
                    row['runtime_replacements'].append({'GN_selection': before, 'prior_file': previous,
                        'installed': self.remember(after), 'reason': 'explicit installed runtime relink; no same-byte claim'})
            row['installed_runtime_profile'] = self.installed_runtime
            if not c_language and not effective_cfi(flags):
                flags += cfi_flags(anchors[-1]['flags']); ld += cfi_flags(anchors[-1]['ldflags'])
                row['diagnostic_cfi_augmentation_from_actual_product_graph'] = spec['anchors'][-1]['graph']
            if c_language:
                if ([x for x in flags if x.startswith('--target=')] != ['--target=aarch64-linux-ohos'] or
                        len([x for x in flags if x.startswith('--sysroot=')]) != 1 or
                        not any(x == '-flto' or x.startswith('-flto=') for x in flags)):
                    raise ValueError('actual ARM64 C GN target/LTO flags required')
                row['actual_C_GN_flags_preserved'] = True
            else: validate_flags(flags)
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
            direct = self.installed_direct(direct, row)
            row['linked_libraries'] = [self.remember(p) for p in direct]
            for p in direct: elf_header(p)
            self.remember(driver); self.remember(self.compiler); self.remember(self.readelf); self.remember(self.ninja)
            self.remember(self.build / 'toolchain.ninja')
            flags += [x for x in includes if x not in flags]
            obj, binary, deps = private / (name + '.o'), private / name, private / 'headers.d'
            compile_cmd = [driver, *flags, '-fPIE', *([] if c_language else ['-include', guard]), '-MD', '-MF', deps, '-c', source, '-o', obj]
            ld, removed = link_flags(ld, private); row['removed_component_DSO_only_export_maps'] = removed
            crtroot = self.build / 'obj/third_party/musl/usr/lib/aarch64-linux-ohos'
            crt = [crtroot / n for n in ('Scrt1.o', 'crti.o', 'crtn.o')]
            for p in crt: self.remember(p)
            # Preserve GN headers/CRT/safety flags. Explicit -nostdlib prevents
            # clang adding its prebuilt libc++ or sysroot libc after our inputs.
            if '-nostdlib' not in ld: raise ValueError('actual GN -nostdlib link policy required')
            searches = ['-Wl,-rpath-link=' + str(path) for path in dict.fromkeys(p.parent for p in direct)]
            link_cmd = [driver, *ld, *searches, '-pie', '-Wl,--threads=2', '-Wl,--export-dynamic', '-o', binary,
                *crt[:2], '-Wl,-t', '-Wl,--start-group', obj, *direct, *runtime_libs, '-Wl,--end-group', crt[2]]
            if ((not c_language and not effective_cfi(ld)) or
                    not any(x == '-flto' or x.startswith('-flto=') for x in ld)):
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
            self.bind_link_runtime(row, opened)
            for soname in ('libc++.so', 'libc.so'): runtime_link_records(row, soname)
            if any(not within(p, self.root) and not within(p, private) for p in opened):
                raise ValueError('linker consumed an input outside read-only product/private helper')
            self.check_elf(name, binary, direct, row)
            if sha(source) != row['source']['sha256'] or sha(guard) != row['abi_guard_sha256']:
                raise ValueError('private source/ABI guard changed during compiler invocation')
            row.update(status='pass_compile_link_ONLY', binary=str(binary), binary_sha256=sha(binary), runtime_validated=False)
        except (OSError, ValueError, KeyError, TypeError, struct.error, subprocess.SubprocessError) as e:
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


def verify_direct_selection(row, inputs, required):
    """Replay the original GN selection and its explicit installed relinks."""
    linked = row.get('linked_libraries', []); opened = row.get('actual_link_inputs', [])
    if not opened: raise ValueError('original actual linker input hashes absent')
    for record in [*linked, *opened]:
        if inputs.get(record['path']) != record: raise ValueError('original linker input not hash-bound')
    direct = [Path(r['path']) for r in linked]
    expected = set(required)
    if row.get('installed_runtime_profile') is not None:
        profile = _runtime_profile(row)
        original = row.get('original_GN_direct_libraries', [])
        if not original or not expected <= {Path(r['path']) for r in original}:
            raise ValueError('original required GN direct selections missing')
        mapped = []
        for record in original:
            if inputs.get(record['path']) != record: raise ValueError('original GN direct input not hash-bound')
            soname = elf_soname(record['path']); entry = profile['dsos'].get(soname)
            if entry is None:
                mapped.append(Path(record['path'])); continue
            installed = entry['staged']
            if inputs.get(installed['path']) != installed:
                raise ValueError('original staged direct input not hash-bound')
            if any(record[k] != installed[k] for k in ('sha256', 'bytes')):
                replacement = {'GN_selection': record['path'], 'prior_file': record, 'installed': installed,
                    'reason': 'explicit installed runtime relink of GN direct dependency; no same-byte claim'}
                if (soname not in ('libc++.so', 'libc.so', 'libclang_rt.ubsan_minimal.so') or
                        replacement not in row.get('runtime_replacements', [])):
                    raise ValueError('original GN direct bytes differ without explicit permitted runtime relink')
            mapped.append(Path(installed['path']))
        if list(dict.fromkeys(mapped)) != direct:
            raise ValueError('original GN direct selections do not map to actual installed direct inputs')
        expected = set(mapped)
    if not expected <= set(direct) or not set(direct) <= {Path(r['path']) for r in opened}:
        raise ValueError('original required product libraries/link trace binding missing')
    return direct


class ExistingVerifier(Builder):
    """No compilation: bind old receipts, immutable artifacts and unchanged DSOs."""
    def __init__(self, source, output, helpers, report, expected_sha256):
        self.previous_path = regular(report).resolve(); self.previous_root = self.previous_path.parent
        require_ro(self.previous_path)
        if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256 or '') or sha(self.previous_path) != expected_sha256:
            raise ValueError('original build report SHA256 mismatch')
        self.previous = json.loads(self.previous_path.read_text())
        old = self.previous
        if (old.get('product') != PRODUCT or old.get('plan_only') is not False or old.get('changed_inputs') != [] or
                old.get('source_root') != str(Path(source).resolve()) or
                old.get('build_directory') != str(Path(source).resolve() / 'out' / PRODUCT) or
                not re.fullmatch(r'[0-9a-f]{64}', old.get('builder_sha256', ''))):
            raise ValueError('original product/source/complete unchanged-input receipt required')
        if within(output, self.previous_root): raise ValueError('new recheck output must be outside original artifacts')
        super().__init__(source, output, helpers, _existing=True)
        self.report.update(scope='read_only_recheck_of_prior_compile_link_artifacts_and_actual_product_DSO_ELF_ONLY_NOT_runtime',
            verify_existing=True, original_report={'path': str(self.previous_path), 'sha256': expected_sha256,
                'status': old['status'], 'builder_sha256': old['builder_sha256'], 'rewritten': False},
            original_commands=[], original_input_count=len(old.get('inputs', {})),
            object_hash_provenance='Captured during recheck; original report did not hash objects. No retroactive object hash claim.')
        self.artifact_origin = None
        self.save()
        self.remember(self.previous_path, source=False)
        for command in old.get('commands', []):
            log = Path(command['log'])
            if not log.is_absolute() or command.get('exit_code') != 0:
                raise ValueError('successful original command receipts required')
            if self.artifact_origin is None: self.artifact_origin = log.parent
            if log.parent != self.artifact_origin or log.name in ('.', '..'):
                raise ValueError('original command log escapes artifact directory')
            record = self.bound_artifact(log, command['sha256'])
            self.report['original_commands'].append(dict(command, verified_log=record))
        if self.artifact_origin is None or str(self.artifact_origin) == '/':
            raise ValueError('original complete command logs absent')
        allowed_fixtures = {(HERE / 'fixtures' / spec['fixture']).resolve() for spec in HELPERS.values()}
        allowed_runtime = {}
        prior_runtime = old.get('installed_runtime_profile')
        if prior_runtime is not None:
            profile = _runtime_profile({'installed_runtime_profile': prior_runtime})
            descriptors = [prior_runtime['source'], profile['archive'], profile['system_image']]
            if 'vendor_image' in profile: descriptors.append(profile['vendor_image'])
            descriptors += [entry['image_file'] for entry in profile['dsos'].values()]
            descriptors += list(old.get('installed_runtime_image_proof', {}).get('tools', {}).values())
            allowed_runtime = {r['path']: {k: r[k] for k in ('path', 'sha256', 'bytes')} for r in descriptors}
            if (sha(prior_runtime['source']['path']) != prior_runtime['source']['sha256'] or
                    json.loads(Path(prior_runtime['source']['path']).read_text()) != profile):
                raise ValueError('original installed profile file/receipt changed; no replacement is allowed')
        if not old.get('inputs'): raise ValueError('original complete source/header/DSO input hashes absent')
        for key, record in old['inputs'].items():
            path = Path(key)
            if record.get('path') != key or not path.is_absolute() or (not within(path, self.root) and
                    path.resolve() not in allowed_fixtures and allowed_runtime.get(key) != record):
                raise ValueError('original input is outside actual source/out or known fixtures')
            actual = self.remember(path, source=within(path, self.root))
            if actual != record:
                self.report['preflight_error'] = 'original source/header/DSO bytes changed: ' + str(path)
                self.save(); raise ValueError(self.report['preflight_error'])
        for tool in (self.compiler, self.readelf):
            if str(tool.resolve()) not in old['inputs']:
                raise ValueError('current actual tool identity missing from original input receipt')
            self.remember(tool)
        self.save()

    def command(self, argv, label, timeout=60):
        words = list(map(str, argv))
        if (not words or words[0] != str(self.readelf) or words[1:-1] not in (
                ['-h', '-l', '-d', '--dyn-syms', '--wide', '--demangle'],
                ['-h', '-d', '--dyn-syms', '--wide', '--demangle'])):
            raise ValueError('verify-existing permits only read-only actual ELF inspections')
        path = regular(words[-1]).resolve()
        if not within(path, self.root) and not within(path, self.previous_root):
            raise ValueError('ELF recheck input outside immutable source/artifacts')
        self.remember(path, source=within(path, self.root))
        return super().command(words, label, timeout=timeout)

    def bound_artifact(self, path, expected=None):
        """Only relocate the old private artifact prefix, never source/out inputs."""
        path = Path(path)
        if self.artifact_origin is None or not path.is_absolute() or '..' in path.parts:
            raise ValueError('invalid original artifact path')
        try: relative = path.relative_to(self.artifact_origin)
        except ValueError as error: raise ValueError('original artifact prefix mismatch') from error
        local = self.previous_root / relative
        if not within(local, self.previous_root): raise ValueError('original artifact symlink escapes read-only directory')
        record = self.remember(local, source=False)
        if expected is not None and record['sha256'] != expected:
            raise ValueError('original artifact/log SHA256 mismatch: ' + str(local))
        return record

    def prior_command(self, label, argv=None):
        commands = [c for c in self.previous['commands'] if c['label'] == label]
        if len(commands) != 1 or argv is not None and commands[0]['argv'] != argv:
            raise ValueError('original command/receipt binding mismatch: ' + label)
        return commands[0]

    def helper(self, name):
        row = {'status': 'fail', 'runtime_validated': False}; self.report['helpers'][name] = row; self.save()
        try:
            old = self.previous['helpers'].get(name, {}); spec = HELPERS[name]
            if old.get('fixture') != spec['fixture'] or not old.get('CFI_preserved'):
                raise ValueError('original helper source/CFI receipt missing')
            compile_cmd, link_cmd = old['compile_command'], old['link_command']
            validate_flags(compile_cmd)
            if not effective_cfi(link_cmd) or not any(w == '-flto' or w.startswith('-flto=') for w in link_cmd):
                raise ValueError('original link CFI/LTO missing')
            if Path(compile_cmd[0]).resolve() != self.compiler.resolve() or Path(link_cmd[0]).resolve() != self.compiler.resolve():
                raise ValueError('original actual compiler identity mismatch')
            self.prior_command(name + '-compile', compile_cmd); self.prior_command(name + '-link', link_cmd)
            prior_elf = self.prior_command(name + '-actual-ELF-ABI')
            base = self.artifact_origin / name
            source = base / Path(spec['fixture']).name; guard = base / 'actual_system_abi.h'
            obj = base / (name + '.o'); binary = base / name; deps = base / 'headers.d'
            if (argument(compile_cmd, '-c') != str(source) or argument(compile_cmd, '-include') != str(guard) or
                    argument(compile_cmd, '-o') != str(obj) or argument(compile_cmd, '-MF') != str(deps) or
                    argument(link_cmd, '-o') != str(binary) or str(obj) not in link_cmd or prior_elf['argv'][-1] != str(binary)):
                raise ValueError('original private compile/link/ELF artifact binding mismatch')
            if old['private_source_sha256'] != old['source']['sha256'] or old['source'] != self.previous['inputs'].get(old['source']['path']):
                raise ValueError('original fixture/private source hash binding mismatch')
            if old['source']['path'] != str((HERE / 'fixtures' / spec['fixture']).resolve()):
                raise ValueError('original helper does not use current known fixture')
            row['reused_artifacts'] = {
                'source': self.bound_artifact(source, old['source']['sha256']),
                'abi_guard': self.bound_artifact(guard, old['abi_guard_sha256']),
                'object_new_hash_capture': self.bound_artifact(obj),
                'binary': self.bound_artifact(binary, old['elf']['sha256']),
                'depfile': self.bound_artifact(deps, old['depfile_sha256'])}
            if sha(row['reused_artifacts']['abi_guard']['path']) != hashlib.sha256(ABI_GUARD.encode()).hexdigest():
                raise ValueError('original guard is not the actual system __h/fno-exceptions guard')
            dependencies = old.get('actual_compiler_dependencies', [])
            if not dependencies: raise ValueError('original complete compiler header dependencies absent')
            for record in dependencies:
                path = Path(record['path'])
                if within(path, self.root):
                    if self.previous['inputs'].get(str(path)) != record: raise ValueError('original dependency not hash-bound')
                elif path in (source, guard): self.bound_artifact(path, record['sha256'])
                else: raise ValueError('original dependency outside actual source/private helper')
            actual_deps = dep_paths(Path(row['reused_artifacts']['depfile']['path']), self.build)
            if actual_deps != [Path(r['path']).resolve() for r in dependencies]:
                raise ValueError('original depfile/recorded header list mismatch')
            linked = old.get('linked_libraries', []); opened = old.get('actual_link_inputs', [])
            required = {(self.build / p).resolve() for p in spec['libraries']}
            direct = verify_direct_selection(old, self.previous['inputs'], required)
            row.update(original_helper_status=old['status'], original_helper_error=old.get('error'),
                compile_command=compile_cmd, link_command=link_cmd, original_ELF_log_sha256=prior_elf['sha256'],
                linked_libraries=linked, actual_compiler_dependencies=dependencies,
                CFI_preserved=True, actual_link_inputs=opened)
            if old.get('installed_runtime_profile') is not None:
                if old['installed_runtime_profile'] != self.previous.get('installed_runtime_profile'):
                    raise ValueError('original helper installed profile did not belong to original build')
                row.update(installed_runtime_profile=old['installed_runtime_profile'],
                           actual_link_input_sonames=old['actual_link_input_sonames'])
                for soname in old['DT_NEEDED']: runtime_link_records(row, soname)
            self.check_elf(name, Path(row['reused_artifacts']['binary']['path']), direct, row)
            row.update(status='pass_compile_link_ONLY', binary=row['reused_artifacts']['binary']['path'],
                binary_sha256=row['reused_artifacts']['binary']['sha256'])
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            row['error'] = type(error).__name__ + ': ' + str(error)
        finally: self.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=[PRODUCT], required=True)
    parser.add_argument('--helper', choices=HELPERS, action='append', help='Repeat to select; default all registered helpers')
    parser.add_argument('--plan-only', action='store_true', help='Read/query existing GN only; never clang/build GN')
    parser.add_argument('--verify-existing', type=Path, help='Read-only original build.json; no Ninja/compiler/linker invocation')
    parser.add_argument('--existing-report-sha256', help='Required external SHA256 binding of the original report')
    parser.add_argument('--runtime-profile', type=Path, help='Root-produced installed image/staging runtime profile')
    parser.add_argument('--runtime-profile-sha256', help='External exact profile SHA256; required for every fresh build/plan')
    args = parser.parse_args()
    helpers = args.helper or list(HELPERS)
    if len(helpers) != len(set(helpers)): parser.error('duplicate helper selection')
    if args.verify_existing and (args.plan_only or not args.existing_report_sha256):
        parser.error('--verify-existing requires --existing-report-sha256 and excludes --plan-only')
    if args.existing_report_sha256 and not args.verify_existing: parser.error('--existing-report-sha256 requires --verify-existing')
    if args.verify_existing and (args.runtime_profile or args.runtime_profile_sha256):
        parser.error('--verify-existing cannot add or replace an installed runtime profile')
    try:
        if args.verify_existing:
            builder = ExistingVerifier(args.source_root, args.output, helpers, args.verify_existing, args.existing_report_sha256)
        else: builder = Builder(args.source_root, args.output, helpers, args.plan_only,
                               runtime_profile=args.runtime_profile, runtime_profile_sha256=args.runtime_profile_sha256)
        report = builder.run()
        print(json.dumps({'status': report['status'], 'helpers': {n: r['status'] for n, r in report['helpers'].items()}}))
        return 1 if report['status'] == 'fail' else 0
    except (OSError, ValueError, KeyError, TypeError, struct.error, tarfile.TarError, subprocess.SubprocessError) as e:
        print(json.dumps({'status': 'fail', 'error': type(e).__name__ + ': ' + str(e)})); return 1


if __name__ == '__main__': raise SystemExit(main())
