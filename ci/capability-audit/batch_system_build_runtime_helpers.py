#!/usr/bin/env python3
"""Build read-only guest helpers with actual selected-product innerkit/CFI ABI.

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
# Keep the original default for existing callers; never mutate this global to
# select a different source/out tree. Targets are package identities, not SDK
# triples. A new target's triple, float ABI and CRT come from its actual graph.
TARGETS = {
    'arm64_virt': {'arch': 'arm64', 'class': 64, 'machine': 183, 'kernel': 'Image',
                   'qemu': 'qemu-system-aarch64'},
    'armv7a_virt': {'arch': 'armv7a', 'class': 32, 'machine': 40, 'kernel': 'zImage',
                    'qemu': 'qemu-system-arm'},
    'x86_64_virt': {'arch': 'x86_64', 'class': 64, 'machine': 62, 'kernel': 'bzImage',
                    'qemu': 'qemu-system-x86_64'}}


def target_spec(product):
    if not isinstance(product, str) or product not in TARGETS:
        raise ValueError('one finite actual full-source product required')
    return TARGETS[product]


def compiler_target(flags):
    values = [word.split('=', 1)[1] for word in flags if word.startswith('--target=')]
    if len(values) != 1 or not re.fullmatch(r'[A-Za-z0-9_.+\-]+', values[0]):
        raise ValueError('one literal target from the actual Ninja command required')
    return values[0]


def validate_compiler_target(flags, product, actual_target):
    target_spec(product)
    selected = compiler_target(flags)
    if product == PRODUCT:
        if selected != 'aarch64-linux-ohos':
            raise ValueError('original actual AArch64 product target required')
    elif actual_target is None:
        raise ValueError('nondefault target needs a bound actual executable-link anchor')
    if actual_target is not None and selected != actual_target:
        raise ValueError('actual object and executable-link compiler targets differ')
    return selected
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
NUMBER_LOCAL_HELPER_NAMES580 = ('number_token_query395',)
COMMUNICATION_HELPER_NAMES = ('communications578_permission_controller', 'communications578_at_peer')
SETTINGS_HELPER_NAMES = ('settings_idle579_napi',)
OWNING_SERVICES_HELPER_NAMES579 = ('owning_services579_napi',)
MSDP579_HELPER_NAMES = ('msdp579_napi',)
WIFI_HELPER_NAMES = ('apps579_wifi_peer',)
PRODUCTION_HELPER_NAMES579 = ('audio_haptic_sampler', 'audio_observation_clock', 'calendar_runtime_observer',
    'gnss_existing_sa_dump', 'alsa_inject', 'audio_capture_token', 'netlink_snapshot',
    'apn579_modem_peer', 'apps_paired579_net')
GLOBAL_CLOCK_HELPER_NAMES579 = ('audio_global579_control', 'audio_global579_status', 'audio_global579_af')
GLOBAL_THREEUID_HELPER_NAMES579 = ('audio_global579_passive', 'audio_global579_token')
NETWORKING_HELPER_NAMES579 = ('networking579_bpf_snapshot',)
USB579_HELPER_NAMES = ('usb579_device_peer',)
C_ABI_GUARD = '/* C helper retains actual C GN flags; no C++ ABI assertion. */\n'
ABI_GUARD = '''#include <string>
#include <type_traits>
#ifdef __EXCEPTIONS
#error Actual product fno-exceptions must be preserved
#endif
static_assert(std::is_same<std::string, std::__h::basic_string<char>>::value,
    "Use actual system libc++ __h headers; never redefine the ABI namespace");
'''


def helper_spec(name):
    """Communication helpers are available only by finite explicit selection.

    Preserve the original HELPERS/default set and avoid requiring the new
    recipe module for an ordinary original build or original artifact recheck.
    """
    if name in HELPERS:
        return HELPERS[name]
    if name in NUMBER_LOCAL_HELPER_NAMES580:
        return {'fixture': 'batch_apps/number_runtime/number_token_query395.cpp',
            'anchors': [TOKEN], 'libraries': ['security/access_token/libaccesstoken_sdk.z.so'],
            'headers': [TOKEN['header'],
                        'base/security/access_token/interfaces/innerkits/accesstoken/include/hap_token_info.h'],
            'extra_includes': []}
    if name in USB579_HELPER_NAMES:
        from usb579_native import helper_recipes
        recipes = helper_recipes()
        if set(recipes) != set(USB579_HELPER_NAMES):
            raise ValueError('one explicit ordinary C USB device peer required')
        return recipes[name]
    if name in NETWORKING_HELPER_NAMES579:
        from networking579_native import helper_recipes
        recipes = helper_recipes()
        if set(recipes) != set(NETWORKING_HELPER_NAMES579):
            raise ValueError('fixed single read-only product BPF observer recipe required')
        return recipes[name]
    if name in GLOBAL_THREEUID_HELPER_NAMES579:
        from audio_threeuid_arm32_global579_native import helper_recipes
        recipes = helper_recipes()
        if set(recipes) != set(GLOBAL_THREEUID_HELPER_NAMES579):
            raise ValueError('fixed two original-source global-clock AU helpers required')
        return recipes[name]
    if name in GLOBAL_CLOCK_HELPER_NAMES579:
        from onset579_global_native import helper_recipes
        recipes = helper_recipes()
        if set(recipes) != set(GLOBAL_CLOCK_HELPER_NAMES579):
            raise ValueError('fixed three global clock helpers required')
        return recipes[name]
    if name in PRODUCTION_HELPER_NAMES579:
        from production579_native import helper_recipes
        recipes = helper_recipes()
        if set(recipes) != set(PRODUCTION_HELPER_NAMES579):
            raise ValueError('complete explicit original-kind and delivered579 recipes required')
        return recipes[name]
    if name in WIFI_HELPER_NAMES:
        from apps_providers579_wifi_native import helper_recipes
        recipes = helper_recipes()
        if set(recipes) != set(WIFI_HELPER_NAMES):
            raise ValueError('fixed isolated-radio C helper recipe required')
        return recipes[name]
    if name in MSDP579_HELPER_NAMES:
        from msdp579_native import helper_recipes
        recipes = helper_recipes()
        if set(recipes) != set(MSDP579_HELPER_NAMES):
            raise ValueError('one actual product ABI MSDP inner-client supplement')
        return recipes[name]
    if name in OWNING_SERVICES_HELPER_NAMES579:
        from owning_services579_native import helper_recipes
        recipes = helper_recipes()
        if set(recipes) != set(OWNING_SERVICES_HELPER_NAMES579):
            raise ValueError('fixed owning-service NAPI caller only')
        return recipes[name]
    if name in SETTINGS_HELPER_NAMES:
        from settings_idle579_native import helper_recipes
        recipes = helper_recipes()
        if set(recipes) != set(SETTINGS_HELPER_NAMES):
            raise ValueError('fixed settings shared-NAPI recipe required')
        return recipes[name]
    if name not in COMMUNICATION_HELPER_NAMES:
        raise ValueError('unknown fixed helper selection')
    from communications578_native import helper_recipes
    recipes = helper_recipes()
    if set(recipes) != set(COMMUNICATION_HELPER_NAMES) or set(recipes) & set(HELPERS):
        raise ValueError('fixed explicit communications helper recipes required')
    return recipes[name]


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


def validate_flags(flags, *, product=PRODUCT, actual_target=None):
    validate_compiler_target(flags, product, actual_target)
    sysroots = [x for x in flags if x.startswith('--sysroot=')]
    lto = [x for x in flags if x == '-flto' or x.startswith(('-flto=', '-fno-lto'))]
    exceptions = [x for x in flags if x in ('-fexceptions', '-fno-exceptions')]
    if (len(sysroots) != 1 or not lto or
            lto[-1].startswith('-fno-lto') or not exceptions or exceptions[-1] != '-fno-exceptions' or
            not effective_cfi(flags)):
        raise ValueError('actual selected system sysroot/LTO/CFI/fno-exceptions flags required')


def validate_c_flags(flags, *, product=PRODUCT, actual_target=None):
    """Selected C flags retain actual musl/LTO/cross-DSO CFI on every target."""
    validate_compiler_target(flags, product, actual_target)
    sysroots = [x for x in flags if x.startswith('--sysroot=')]
    lto = [x for x in flags if x == '-flto' or x.startswith(('-flto=', '-fno-lto'))]
    for index, word in enumerate(flags):
        if word == '-x' and (index + 1 == len(flags) or flags[index + 1] != 'c'):
            raise ValueError('actual C language selection required')
        if word.startswith('-x') and word not in ('-x', '-xc'):
            raise ValueError('non-C language override refused')
    if (len(sysroots) != 1 or not lto or
            lto[-1].startswith('-fno-lto') or not effective_cfi(flags) or
            any(x in ('-xc++', '-fexceptions') or x.startswith(('-std=c++', '-std=gnu++')) or
                '_LIBCPP_ABI_NAMESPACE' in x or '__n1' in x for x in flags)):
        raise ValueError('actual selected C GN sysroot/LTO/cross-DSO CFI flags required; C++ ABI substitution refused')


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


def elf_segments(data, product):
    """Decode the real class-specific file layout, never reinterpret ELF32 as 64."""
    target = target_spec(product)
    bits = target['class']; minimum = 64 if bits == 64 else 52
    if (len(data) < minimum or data[:7] != b'\x7fELF' + bytes((2 if bits == 64 else 1, 1, 1)) or
            struct.unpack_from('<H', data, 18)[0] != target['machine'] or
            struct.unpack_from('<I', data, 20)[0] != 1):
        raise ValueError('actual selected little-endian ELF class/machine/version required')
    ehsize_offset = 52 if bits == 64 else 40
    if struct.unpack_from('<H', data, ehsize_offset)[0] != minimum:
        raise ValueError('invalid actual ELF header size')
    if struct.unpack_from('<H', data, 16)[0] != 3:
        raise ValueError('actual DSO/PIE ELF type required')
    offset = struct.unpack_from('<Q' if bits == 64 else '<I', data, 32 if bits == 64 else 28)[0]
    size, count = struct.unpack_from('<HH', data, 54 if bits == 64 else 42)
    expected = 56 if bits == 64 else 32
    if size != expected or not count or count == 0xffff or offset < minimum or offset + size * count > len(data):
        raise ValueError('invalid actual program headers; extended numbering not admitted')
    segments = []
    for index in range(count):
        if bits == 64:
            kind, flags, start, va, _, length, memory, _ = struct.unpack_from('<IIQQQQQQ', data, offset + index * size)
        else:
            kind, start, va, _, length, memory, flags, _ = struct.unpack_from('<IIIIIIII', data, offset + index * size)
        if start + length > len(data) or (kind == 1 and length > memory):
            raise ValueError('actual ELF segment outside file or invalid load size')
        segments.append((kind, start, va, length, flags))
    return segments


def elf_needed(path, *, product=PRODUCT):
    """Decode DT_NEEDED using the selected actual class. No tool/process call.

    This decodes bytes only; callers separately bind interpreter/machine ABI to
    the retained actual normal executable through native579_artifact_context.
    """
    data = Path(path).read_bytes(); segments = elf_segments(data, product)
    stride = 16 if target_spec(product)['class'] == 64 else 8
    fmt = '<qQ' if stride == 16 else '<iI'
    loads = [(va, start, length) for kind, start, va, length, _ in segments if kind == 1]
    tables = [(start, length) for kind, start, _, length, _ in segments if kind == 2]
    if len(tables) != 1 or not tables[0][1] or tables[0][1] % stride:
        raise ValueError('one complete actual class-specific dynamic segment required')
    start, length = tables[0]; tags = {}; needed = []; ended = False
    for offset in range(start, start + length, stride):
        tag, value = struct.unpack_from(fmt, data, offset)
        if tag == 0: ended = True; break
        if tag == 1: needed.append(value)
        elif tag in (5, 10):
            if tag in tags: raise ValueError('ambiguous actual dynamic string table')
            tags[tag] = value
    if not ended or set(tags) != {5, 10} or not 1 <= len(needed) <= 128 or not tags[10]:
        raise ValueError('complete actual DT_NEEDED/string table required')
    positions = [file + tags[5] - va for va, file, size in loads
                 if va <= tags[5] and tags[5] + tags[10] <= va + size]
    if len(positions) != 1: raise ValueError('actual ELF string table is not file backed')
    table = data[positions[0]:positions[0] + tags[10]]; names = []
    for index in needed:
        if not 0 <= index < len(table): raise ValueError('DT_NEEDED offset outside actual strings')
        end = table.find(b'\0', index)
        if not index < end <= index + 256: raise ValueError('unterminated/oversize actual SONAME')
        name = table[index:end].decode('ascii')
        if not re.fullmatch(r'[A-Za-z0-9_.+\-]+\.so', name): raise ValueError('unsafe actual DT_NEEDED')
        names.append(name)
    if len(names) != len(set(names)): raise ValueError('duplicate actual DT_NEEDED')
    return sorted(names)


def elf_soname(path, *, product=PRODUCT):
    """Read the actual class-specific DT_SONAME, not a basename/tool claim."""
    data = Path(path).read_bytes(); segments = elf_segments(data, product)
    bits = target_spec(product)['class']; stride = 16 if bits == 64 else 8
    loads, dynamic = [], []
    for kind, start, va, length, _ in segments:
        if kind == 1: loads.append((va, start, length))
        if kind == 2:
            if dynamic or not length or length % stride:
                raise ValueError('ambiguous or invalid DSO dynamic table')
            dynamic = [struct.unpack_from('<qQ' if bits == 64 else '<iI', data, n)
                       for n in range(start, start + length, stride)]
    tags = {}; terminated = False
    for tag, value in dynamic:
        if tag == 0: terminated = True; break
        if tag in (5, 10, 14):
            if tag in tags: raise ValueError('ambiguous DSO SONAME/string table')
            tags[tag] = value
    if dynamic and not terminated: raise ValueError('unterminated DSO dynamic table')
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
    Version 1 keeps the original ARM64 paths. Version 2 binds the actual package
    manifest and uses the product's physical packages/phone staging directory,
    including for the full 2in1 profile. It never relabels an old profile.
    The root producer owns extraction of image_file from image_member; the whole
    archive/image and these independent dumped bytes are immutable build inputs.
    """
    keys = {'schema_version', 'kind', 'product', 'arch', 'device', 'source_root', 'archive', 'system_image', 'dsos'}
    if not isinstance(profile, dict) or not keys <= profile.keys():
        raise ValueError('versioned actual installed runtime profile required')
    version = profile['schema_version']; product = profile['product']
    target = target_spec(product)
    extra = {'package_manifest', 'package_metadata'} if type(version) is int and version == 2 else set()
    if (set(profile) - keys - {'vendor_image'} - extra or
            type(version) is not int or version not in (1, 2) or
            profile['kind'] != 'installed_product_runtime' or
            profile['arch'] != target['arch'] or profile['device'] not in ('phone', '2in1') or
            version == 1 and product != PRODUCT):
        raise ValueError('finite product/arch and original-v1 or actual-package-v2 profile required')
    package_root = 'openharmony-qemu-' + target['arch'] + '-' + product + '-' + profile['device']
    if version == 2:
        if not extra <= profile.keys(): raise ValueError('actual package manifest/data binding required')
        manifest = _profile_record(profile['package_manifest']); metadata = profile['package_metadata']
        if manifest.get('archive_member') != package_root + '/manifest.json' or not isinstance(metadata, dict):
            raise ValueError('exact actual archive manifest member required')
        expected = {'product': product, 'guest_arch': target['arch'], 'device_type': profile['device'],
                    'device_type_profile': 'qemu_' + profile['device'] + '_full_source',
                    'kernel': target['kernel'], 'qemu_unix': target['qemu']}
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ValueError('actual package manifest product/arch/full-device profile differs')
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
        if member != package_root + '/images/' + name + '.img':
            raise ValueError('archive member product/device differs from installed profile')
    if ((archive_sha256 is not None and archive['sha256'] != archive_sha256) or
            (system_image_sha256 is not None and image['sha256'] != system_image_sha256)):
        raise ValueError('installed runtime profile belongs to another archive/system image')
    entries = profile['dsos']
    if not isinstance(entries, dict) or not {'libc++.so', 'libc.so'} <= entries.keys():
        raise ValueError('installed system libc++ and musl loader profile required')
    prefix = installed_prefix(profile)
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
        loader = (basename == 'ld-musl-aarch64.so.1' if version == 1 else
                  re.fullmatch(r'ld-musl-[A-Za-z0-9_+\-]+\.so\.1', basename) is not None)
        if basename != soname and not (soname == 'libc.so' and loader):
            raise ValueError('unproved installed SONAME/file alias: ' + soname)
        if soname == 'libc.so' and not loader:
            raise ValueError('use the actual installed musl loader, never a libc symbol proxy')
        if (soname == 'libc++.so' and
                relative not in (('/lib64/chipset-sdk-sp/libc++.so',) if version == 1 else
                                 ('/lib/chipset-sdk-sp/libc++.so', '/lib64/chipset-sdk-sp/libc++.so'))):
            raise ValueError('actual system __h libc++ installation required')
    return entries


def installed_prefix(profile):
    # package_standard_qemu.sh selects packages/phone for all three products.
    staging = profile['device'] if profile['schema_version'] == 1 else 'phone'
    return profile['source_root'].rstrip('/') + '/out/' + profile['product'] + '/packages/' + staging


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
    prefix = installed_prefix(profile) + '/'
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


def elf_header(path, executable=False, shared=False, *, product=PRODUCT, interpreter_path=None):
    data = Path(path).read_bytes(); segments = elf_segments(data, product)
    target = target_spec(product)
    interpreters = []
    for kind, start, _, length, _ in segments:
        if kind != 3: continue
        value = data[start:start + length]
        if not value.endswith(b'\0') or b'\0' in value[:-1]:
            raise ValueError('invalid actual ELF interpreter string')
        interpreters.append(value[:-1].decode('ascii'))
    if len(interpreters) > 1: raise ValueError('ambiguous actual ELF interpreter')
    if executable:
        if interpreter_path is None:
            if product != PRODUCT:
                raise ValueError('selected target needs its actual installed loader path')
            if len(interpreters) != 1 or not interpreters[0].startswith('/') or not interpreters[0].endswith('/ld-musl-aarch64.so.1'):
                raise ValueError('original actual ARM64 musl guest interpreter absent')
        elif interpreters != [interpreter_path]:
            raise ValueError('actual executable interpreter differs from the installed image loader')
    if shared and interpreters:
        raise ValueError('actual shared NAPI must not carry a program interpreter')
    return {'class': target['class'], 'machine': target['machine'], 'type': 'ET_DYN', 'sha256': sha(path)}


def executable_interpreter(path, product):
    data = Path(path).read_bytes()
    rows = [data[start:start + length] for kind, start, _, length, _ in elf_segments(data, product) if kind == 3]
    if len(rows) != 1 or not rows[0].endswith(b'\0') or b'\0' in rows[0][:-1]:
        raise ValueError('one actual normal executable interpreter required')
    value = rows[0][:-1].decode('ascii')
    if not re.fullmatch(r'/[A-Za-z0-9_./+\-]+', value) or any(p in ('', '.', '..') for p in value.split('/')[1:]):
        raise ValueError('unsafe actual normal executable interpreter')
    return value


def machine_abi_flags(path, product):
    # ARM e_flags carries EABI/float-call ABI. Use the complete actual value,
    # not an inferred -mfloat-abi or a synthesized architecture default.
    data = Path(path).read_bytes(); elf_segments(data, product)
    return struct.unpack_from('<I', data, 36 if target_spec(product)['class'] == 32 else 48)[0]


def abi_options(flags):
    return [word for word in flags if word in ('-marm', '-mthumb', '-mbig-endian', '-mlittle-endian') or
            word.startswith(('-mfloat-abi=', '-mfpu=', '-mabi='))]


# Actual RO R71 build-project source; these are grammar identities, never an
# executable selection supplied by JSON. New source revisions need a reviewed
# grammar successor rather than silently accepting another wrapper.
NORMAL_LINK_GRAMMAR579 = (
    ('build/toolchain/gcc_toolchain.gni', '131c19f86c59bf81dc71a7c8eeeefa7a5ea4ad08f204fe7a73af1ec37d224e70'),
    ('build/toolchain/ohos/ohos_toolchain.gni', '60e3ddf4b11479b0dc8a2a6af1aa13f54e8a62e2c1f71acd043af8c797c3287f'),
    ('build/toolchain/gcc_link_wrapper.py', '3866b8cc7548881f11d74b6003a0ac447df4c1b93e6b303c486ec4fcf8694816'),
    ('build/toolchain/wrapper_utils.py', '93a167722959994276fe0a23db583c5f372290227e05c2771726f0f6c8b43e24'))


def normal_query_streams579(row):
    """Original successful readonly query; both actual full streams required."""
    if (row.get('stream_mode') != 'normal-query-separate-stdio579/v1' or
            type(row.get('exit_code')) is not int or row['exit_code'] != 0 or row.get('timed_out') is not False):
        raise ValueError('actual normal readonly query status/split-stream identity differs')
    for key in ('stdout', 'stderr'):
        ref = row.get(key)
        if (type(ref) is not dict or set(ref) != {'path', 'sha256', 'bytes'} or
                not isinstance(ref['path'], str) or not Path(ref['path']).is_absolute() or
                '..' in Path(ref['path']).parts or not re.fullmatch('[a-f0-9]{64}', ref.get('sha256', '')) or
                type(ref['bytes']) is not int or ref['bytes'] < 0):
            raise ValueError('complete original normal query stdout/stderr Ref3 required')
    if (row['stdout']['path'] == row['stderr']['path'] or
            row.get('log') != row['stdout']['path'] or row.get('sha256') != row['stdout']['sha256']):
        raise ValueError('legacy normal query log aliases must equal the complete stdout, never merge')
    return row['stdout'], row['stderr']


def normal_edge579(target, text):
    """One actual Ninja -t query edge; explicit inputs are not shell flags."""
    if len(text.encode()) > 2 * 1024 * 1024: raise ValueError('normal query exceeds finite edge bound')
    lines = text.splitlines()
    if len(lines) < 3 or lines[0] != target + ':' or not re.fullmatch(r'  input: (?:[A-Za-z0-9_]+_)?link', lines[1]):
        raise ValueError('one actual executable-link input edge required')
    rule = lines[1].split(': ', 1)[1]
    groups = {'explicit': [], 'implicit': [], 'order_only': []}; pos = 2; stage = 0
    while pos < len(lines) and lines[pos].startswith('    '):
        token = lines[pos][4:]; kind = 'explicit'
        if token.startswith('|| '): token = token[3:]; kind = 'order_only'; next_stage = 2
        elif token.startswith('| '): token = token[2:]; kind = 'implicit'; next_stage = 1
        else: next_stage = 0
        if (next_stage < stage or not re.fullmatch(r'[A-Za-z0-9_./+\-]+', token) or
                token.startswith(('/', '-')) or '$' in token or '@' in token):
            raise ValueError('unreviewed normal input edge grammar')
        stage = next_stage; groups[kind].append(token); pos += 1
    if pos >= len(lines) or lines[pos] != '  outputs:' or not groups['explicit']:
        raise ValueError('normal query output/explicit-input boundary missing')
    # Consumers/validation edges are data only. Do not interpret them as inputs.
    for line in lines[pos + 1:]:
        if line and not (line.startswith('    ') or line == '  validation for:'):
            raise ValueError('unknown trailing normal query grammar')
    if sum(map(len, groups.values())) > 8192: raise ValueError('normal edge exceeds finite input count')
    return {'target': target, 'rule': rule, **groups}


def normal_rule579(path, rule):
    """Read one generated rule, retaining its complete file identity separately.

    The 97 MiB toolchain is streamed, never copied or executed. Duplicate rule
    definitions and unbounded source lines fail instead of selecting a match.
    """
    if Path(path).stat().st_size > 256 * 1024 * 1024: raise ValueError('generated toolchain exceeds finite read bound')
    blocks = []; current = None
    with Path(path).open('r', encoding='utf-8', newline='') as stream:
        for number, line in enumerate(stream, 1):
            if len(line.encode()) > 1024 * 1024: raise ValueError('generated Ninja line exceeds finite bound')
            if current is not None and line.strip() and not line.startswith((' ', '\t')):
                blocks.append(current); current = None
            if line == 'rule ' + rule + '\n': current = {'first_line': number, 'last_line': number, 'text': ''}
            if current is not None:
                current['text'] += line; current['last_line'] = number
                if len(current['text'].encode()) > 65536: raise ValueError('normal rule exceeds finite bound')
    if current is not None: blocks.append(current)
    if len(blocks) != 1: raise ValueError('one unique actual generated link rule required')
    return blocks[0]


def normal_wrapper579(owner, target, words):
    """Finite source-bound POSIX wrapper adapter. It never runs printed code."""
    if words.count('--') != 1: raise ValueError('one official wrapper/driver separator required')
    split = words.index('--'); prefix = words[:split]; driver = words[split + 1:]
    wrapper = owner.root / 'build/toolchain/gcc_link_wrapper.py'
    if len(prefix) < 3 or prefix[0] != '/usr/bin/env' or (owner.build / prefix[1]).resolve() != wrapper:
        raise ValueError('unreviewed normal executable wrapper launcher')
    options = {}; switches = []
    for word in prefix[2:]:
        if word in ('--mini-debug', '--remove-unstripped-exe'):
            if word in switches: raise ValueError('duplicate normal wrapper switch')
            switches.append(word)
        elif word.startswith(('--output=', '--strip=', '--unstripped-file=', '--clang-base-dir=')):
            key, value = word.split('=', 1)
            if key in options or not value or any(char in value for char in ('\x00', '\n', '\r', '$', '`')):
                raise ValueError('unknown/duplicate normal wrapper option')
            options[key] = value
        else:
            # Map-file/static/sanitizer variants have not been observed in this
            # normal-link contract. Never run them or infer their semantics.
            raise ValueError('normal wrapper option needs actual-source adapter')
    if set(options) not in ({'--output', '--clang-base-dir'},
            {'--output', '--clang-base-dir', '--strip', '--unstripped-file'}):
        raise ValueError('normal wrapper output/strip pair incomplete')
    primary = (owner.build / target).resolve()
    if (owner.build / options['--output']).resolve() != primary or not within(primary, owner.build):
        raise ValueError('official wrapper primary output differs from queried target')
    if not Path(options['--clang-base-dir']).is_absolute(): raise ValueError('literal absolute clang-base-dir required')
    linked = primary
    if '--strip' in options:
        if (owner.build / options['--strip']).resolve() != (owner.compiler.parent / 'llvm-strip').resolve():
            raise ValueError('normal wrapper strip tool is outside selected actual clang tree')
        linked = (owner.build / options['--unstripped-file']).resolve()
        if linked != owner.build / 'exe.unstripped' / target:
            raise ValueError('normal unstripped/primary output mapping differs')
    elif switches:
        raise ValueError('mini-debug/removal needs the actual unstripped output pair')
    if '-static' in driver:
        raise ValueError('static-link wrapper semantics are outside this dynamic PIE contract')
    if not driver or Path(driver[0]).name not in ('clang', 'clang++'):
        raise ValueError('literal actual clang driver after wrapper required')
    if argument(driver, '-o') is None or (owner.build / argument(driver, '-o')).resolve() != linked:
        raise ValueError('wrapper output pair and actual driver output differ')
    sources = []
    for relative, digest in NORMAL_LINK_GRAMMAR579:
        row = owner.remember(owner.root / relative)
        if row['sha256'] != digest: raise ValueError('normal executable wrapper/GN source revision changed: ' + relative)
        sources.append(row)
    edge = normal_edge579(target, owner.normal_link_edge_text)
    observation = owner.normal_link_rule_observation
    expected_source = owner.remember(owner.build / 'toolchain.ninja')
    if (set(observation) != {'source', 'first_line', 'last_line', 'text'} or observation['source'] != expected_source or
            type(observation['first_line']) is not int or type(observation['last_line']) is not int or
            observation['first_line'] < 1 or observation['last_line'] < observation['first_line']):
        raise ValueError('actual generated rule source/cut missing')
    if (type(observation['text']) is not str or len(observation['text'].encode()) > 65536 or
            type(expected_source.get('bytes')) is not int or expected_source['bytes'] > 256 * 1024 * 1024):
        raise ValueError('retained generated rule/source exceeds finite byte bound')
    rule_lines = observation['text'].splitlines()
    if not rule_lines or rule_lines[0] != 'rule ' + edge['rule'] or len(rule_lines) != observation['last_line'] - observation['first_line'] + 1:
        raise ValueError('retained generated rule boundary differs')
    fields = {}
    for line in rule_lines[1:]:
        if not line.strip(): continue
        match = re.fullmatch(r'  ([a-z_]+) = (.*)', line)
        if match is None or match[1] in fields: raise ValueError('unreviewed generated rule field grammar')
        fields[match[1]] = match[2]
    if set(fields) != {'command', 'description', 'rspfile', 'rspfile_content', 'pool'}:
        raise ValueError('generated link rule fields differ from selected source grammar')
    rsp_expression = '${output_dir}/${target_output_name}${output_extension}.rsp'
    if fields['rspfile'] != rsp_expression or fields['rspfile_content'] != '${in}' or fields['command'].count('@"' + rsp_expression + '"') != 1:
        raise ValueError('actual generated response contents are not exactly explicit edge inputs')
    rsp = [word for word in driver if word.startswith('@')]
    if rsp != ['@' + target + '.rsp']:
        raise ValueError('normal response token does not bind the actual primary output')
    inline_deps = [Path(word).name for word in driver if word.endswith('.a') and '/common/deps' in word]
    if len(inline_deps) != len(set(inline_deps)):
        raise ValueError('wrapper duplicate-static-dependency rewrite needs a reviewed literal variant')
    inputs = edge['explicit']
    for token in inputs:
        if not within((owner.build / token).resolve(), owner.root) or not re.search(r'\.(?:o|a|so(?:\.[0-9]+)*)$', token):
            raise ValueError('response graph contains flags/unknown normal linker input grammar')
    expanded = []
    for word in driver:
        expanded.extend(inputs if word.startswith('@') else [word])
    block = observation['text'].encode()
    return expanded, primary, {'schema': 'actual-normal-gcc-link-wrapper579/v1', 'literal_prefix': prefix,
        'options': options, 'switches': switches, 'driver_words': driver, 'effective_driver_words': expanded,
        'grammar_sources': sources, 'primary_output': str(primary), 'driver_output': str(linked),
        'generated_rule': {'source': expected_source, 'name': edge['rule'],
            'first_line': observation['first_line'], 'last_line': observation['last_line'],
            'sha256': hashlib.sha256(block).hexdigest(), 'bytes': len(block), 'fields': fields},
        'response': {'literal': rsp[0], 'kind': 'actual_generated_rule_and_query_explicit_inputs_NOT_rsp_file_bytes',
            'edge': edge},
        'clang_base_dir': {'literal': options['--clang-base-dir'], 'relocated': False,
            'use': 'forwarded by the pinned wrapper to mini_debug_info.py; not the clang driver selector'},
        'printed_wrapper_executed': False}


class Builder:
    def __init__(self, source, output, helpers, plan_only=False, *, runtime_profile=None,
                 runtime_profile_sha256=None, product=PRODUCT, normal_link_target=None, _existing=False):
        self.product = product; self.target = target_spec(product)
        if set(helpers) & set(GLOBAL_CLOCK_HELPER_NAMES579) and product != 'armv7a_virt':
            raise ValueError('explicit global clock helpers belong only to actual ARM32 packages')
        if set(helpers) & set(GLOBAL_THREEUID_HELPER_NAMES579) and product != 'armv7a_virt':
            raise ValueError('explicit global-clock three-UID helpers belong only to actual ARM32 packages')
        admitted = (set(USB579_HELPER_NAMES) | set(HELPERS) | set(NUMBER_LOCAL_HELPER_NAMES580) | set(GLOBAL_CLOCK_HELPER_NAMES579) | set(GLOBAL_THREEUID_HELPER_NAMES579) |
            set(COMMUNICATION_HELPER_NAMES) | set(SETTINGS_HELPER_NAMES) | set(OWNING_SERVICES_HELPER_NAMES579) | set(MSDP579_HELPER_NAMES) | set(WIFI_HELPER_NAMES) | set(PRODUCTION_HELPER_NAMES579) |
            set(NETWORKING_HELPER_NAMES579))
        if not set(helpers) <= admitted:
            raise ValueError('only fixed source-defined helper recipes may select a target')
        if normal_link_target is not None and (not isinstance(normal_link_target, str) or
                not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./+\-]*', normal_link_target) or
                normal_link_target.startswith('/') or any(part in ('', '.', '..') for part in normal_link_target.split('/'))):
            raise ValueError('one existing relative normal executable Ninja output target required')
        if product != PRODUCT and normal_link_target is None and not _existing:
            raise ValueError('nondefault products require an actual normal executable link target; no guessed CRT/triple')
        self.normal_link_target = normal_link_target; self.normal_link = None
        self.root = Path(source).resolve(); self.build = self.root / 'out' / product
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
            'product': product, 'arch': self.target['arch'], 'plan_only': plan_only,
            'source_root': str(self.root), 'build_directory': str(self.build),
            'builder_sha256': sha(Path(__file__)), 'commands': [], 'helpers': {}, 'inputs': self.inputs,
            'requirements_closed': 0, 'first_artifact_behavior_gate_passed': False}
        if set(helpers) & set(USB579_HELPER_NAMES):
            self.report['usb579_native_recipe'] = self.remember(HERE / 'usb579_native.py', source=False)
        if set(helpers) & set(GLOBAL_THREEUID_HELPER_NAMES579):
            self.report['global_threeuid579_native_recipe'] = self.remember(HERE / 'audio_threeuid_arm32_global579_native.py', source=False)
        if set(helpers) & set(GLOBAL_CLOCK_HELPER_NAMES579):
            self.report['global_clock579_native_recipe'] = self.remember(HERE / 'onset579_global_native.py', source=False)
        if set(helpers) & set(COMMUNICATION_HELPER_NAMES):
            self.report['communications_native_recipe'] = self.remember(HERE / 'communications578_native.py', source=False)
        if set(helpers) & set(MSDP579_HELPER_NAMES):
            self.report['msdp579_native_recipe'] = self.remember(HERE / 'msdp579_native.py', source=False)
        if set(helpers) & set(OWNING_SERVICES_HELPER_NAMES579):
            self.report['owning_services_native_recipe'] = self.remember(HERE / 'owning_services579_native.py', source=False)
        if set(helpers) & set(SETTINGS_HELPER_NAMES):
            self.report['settings_native_recipe'] = self.remember(HERE / 'settings_idle579_native.py', source=False)
        if set(helpers) & set(WIFI_HELPER_NAMES):
            self.report['wifi_native_recipe'] = self.remember(HERE / 'apps_providers579_wifi_native.py', source=False)
        if set(helpers) & set(NETWORKING_HELPER_NAMES579):
            self.report['networking_native_recipe'] = self.remember(HERE / 'networking579_native.py', source=False)
        if set(helpers) & set(PRODUCTION_HELPER_NAMES579):
            from production579_native import recipe_sources
            self.report['production579_native_recipes'] = [self.remember(p, source=False) for p in recipe_sources()]
            if set(helpers) & {'audio_haptic_sampler', 'audio_observation_clock'}:
                self.report['audio_haptic_extension'] = self.remember(HERE / 'batch_media_audio_haptic_build_sampler.py', source=False)
            if 'calendar_runtime_observer' in helpers:
                self.report['calendar_runtime_extension'] = self.remember(HERE / 'batch_system_calendar_runtime_helper.py', source=False)
            if 'gnss_existing_sa_dump' in helpers:
                self.report['gnss_trace_extension'] = self.remember(HERE / 'batch_system_gnss_trace_helper.py', source=False)
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
            if normal_link_target is not None:
                self.load_normal_link(normal_link_target)

    def load_runtime_profile(self, path, expected_sha256):
        if path is None or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256 or ''):
            raise ValueError('fresh builds require --runtime-profile and its external --runtime-profile-sha256')
        source = self.remember(path, source=False)
        if source['sha256'] != expected_sha256: raise ValueError('installed runtime profile SHA256 mismatch')
        profile = json.loads(Path(path).read_text())
        entries = validate_installed_profile(profile)
        if profile['source_root'] != str(self.root) or profile['product'] != self.product:
            raise ValueError('installed runtime profile source root/product differs')
        self.installed_runtime = {'source': source, 'profile': profile}
        self.report['installed_runtime_profile'] = self.installed_runtime
        retained_profile = self.output / 'runtime-profile.raw.json'
        retained_profile.write_bytes(Path(path).read_bytes())
        if sha(retained_profile) != source['sha256'] or retained_profile.stat().st_size != source['bytes']:
            raise ValueError('actual installed profile changed during raw retention')
        self.report['profile_raw'] = {'path': str(retained_profile), 'sha256': sha(retained_profile), 'bytes': retained_profile.stat().st_size}
        archive = profile['archive']
        self.verify_profile_file(archive)
        # Read exact tar members without extracting paths, executing a guest or
        # trusting a prefilled hash. Each image file must equal its archive bytes.
        images = {name: profile[name + '_image'] for name in ('system', 'vendor') if name + '_image' in profile}
        for image in images.values(): self.verify_profile_file(image)
        package_manifest = profile.get('package_manifest')
        if package_manifest is not None:
            self.verify_profile_file(package_manifest)
            if json.loads(Path(package_manifest['path']).read_text()) != profile['package_metadata']:
                raise ValueError('actual retained manifest bytes differ from the complete profile metadata')
        proofs = {}
        with tarfile.open(archive['path'], 'r:*') as package:
            selected = {image['archive_member']: name for name, image in images.items()}
            if package_manifest is not None: selected[package_manifest['archive_member']] = 'manifest'
            seen = set()
            for member in package:
                if member.name not in selected: continue
                if member.name in seen or not member.isfile(): raise ValueError('ambiguous/nonregular archive image member')
                seen.add(member.name); name = selected[member.name]
                image = package_manifest if name == 'manifest' else images[name]
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
        prefix = installed_prefix(profile) + '/'
        for index, (soname, entry) in enumerate(entries.items()):
            for descriptor in (entry['staged'], entry['image_file']): self.verify_profile_file(descriptor)
            for descriptor in (entry['staged'], entry['image_file']):
                if elf_soname(descriptor['path'], product=self.product) != soname: raise ValueError('actual ELF SONAME differs: ' + soname)
            partition = entry['staged']['path'].removeprefix(prefix).split('/', 1)[0]
            image = images[partition]; private = destination / str(index); private.mkdir()
            stat = self.command([executable, '-R', 'stat ' + entry['image_member'], image['path']],
                                'installed-runtime-stat-' + soname)
            dumped, identity = dump_unique_file(image['path'], (entry['image_member'],), private, str(executable))
            expected = entry['staged']
            if (dumped.stat().st_size != expected['bytes'] or sha(dumped) != expected['sha256'] or
                    elf_soname(dumped, product=self.product) != soname or
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

    def read_normal_file(self, path):
        return Path(path)

    def normal_link_contract(self, target, text):
        """Read one actual direct link or the pinned official wrapper grammar.

        Printed code is never executed. Wrapper response inputs come from the
        actual generated rule plus the actual Ninja input edge, not a recreated
        rsp file or an estimate. Helpers retain their independent CFI gates.
        """
        if (not isinstance(target, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./+\-]*', target) or
                target.startswith('/') or any(part in ('', '.', '..') for part in target.split('/'))):
            raise ValueError('one safe existing normal executable Ninja output required')
        lines = [line for line in text.splitlines() if line.strip()]
        if len(lines) != 1: raise ValueError('one actual final normal-executable link command required')
        words = shlex.split(lines[0]); wrapper = None; primary = None
        if not words or any(word in ('&&', '||', ';', '|', '>', '<') for word in words):
            raise ValueError('actual normal link contains unsupported shell grammar')
        if Path(words[0]).name not in ('clang', 'clang++'):
            words, primary, wrapper = normal_wrapper579(self, target, words)
        if (any(word.startswith('@') for word in words) or Path(words[0]).name not in ('clang', 'clang++') or
                (self.build / words[0]).resolve() not in (self.compiler.resolve(), self.c_compiler.resolve())):
            raise ValueError('actual normal link uses an unreviewed driver/response grammar')
        if words.count('-o') != 1 or argument(words, '-o') is None or '-c' in words or '-shared' in words or '-pie' not in words:
            raise ValueError('actual normal PIE executable link required')
        binary = primary if wrapper is not None else (self.build / argument(words, '-o')).resolve()
        if binary != (self.build / target).resolve() or not within(binary, self.build):
            raise ValueError('actual normal executable output differs from queried Ninja target')
        selected = compiler_target(words)
        roots = [word.split('=', 1)[1] for word in words if word.startswith('--sysroot=')]
        if len(roots) != 1 or (self.build / roots[0]).resolve() != (self.build / 'obj/third_party/musl').resolve():
            raise ValueError('normal link must use this product actual system musl sysroot')
        lto = [word for word in words if word == '-flto' or word.startswith(('-flto=', '-fno-lto'))]
        if '-nostdlib' not in words or not lto or lto[-1].startswith('-fno-lto'):
            raise ValueError('normal executable actual -nostdlib/LTO required')
        # This executable supplies CRT/triple/float ABI, not the helper CFI
        # policy. R71 ark_aot really has CFI off. Preserve its flags as observed;
        # validate_flags/binding_context still require actual helper C++ CFI.
        startup = [Path(word).name for word in words if not word.startswith('-') and
                   re.fullmatch(r'(?:[rS]?crt[^/]*|crtbegin[^/]*|crtend[^/]*)\.o', Path(word).name)]
        if startup != ['Scrt1.o', 'crti.o', 'crtn.o']:
            raise ValueError('unknown/additional or reordered normal executable startup objects need actual-source adapter')
        crt = []
        for name in ('Scrt1.o', 'crti.o', 'crtn.o'):
            found = [word for word in words if not word.startswith('-') and Path(word).name == name]
            if len(found) != 1: raise ValueError('actual normal executable CRT selection is not explicit: ' + name)
            path = (self.build / found[0]).resolve()
            if not within(path, self.build / 'obj/third_party/musl/usr/lib'):
                raise ValueError('normal CRT is outside actual product musl output')
            crt.append(self.remember(path))
        if len({str(Path(row['path']).parent) for row in crt}) != 1:
            raise ValueError('actual normal executable mixes CRT directories')
        record = self.remember(binary)
        retained_binary = self.read_normal_file(binary)
        interpreter = executable_interpreter(retained_binary, self.product)
        elf = elf_header(retained_binary, executable=True, product=self.product, interpreter_path=interpreter)
        loader = Path(self.installed_runtime['profile']['dsos']['libc.so']['image_member']).name
        if Path(interpreter).name != loader:
            raise ValueError('normal executable interpreter differs from actual installed musl loader')
        result = {'target': target, 'actual_command': lines[0], 'compiler_target': selected,
                'abi_options': abi_options(words), 'CRT': crt, 'binary': record, 'elf': elf,
                'machine_abi_flags': machine_abi_flags(retained_binary, self.product), 'interpreter': interpreter,
                'effective_cfi': effective_cfi(words), 'lto_flags': lto}
        if wrapper is not None: result['wrapper'] = wrapper
        return result

    def load_normal_link(self, target):
        text = self.normal_query_command579([self.ninja, '-w', 'dupbuild=warn', '-C', self.build, '-t', 'commands', '-s', target],
                            'actual-normal-executable-link-command', timeout=30)
        printed = [line for line in text.splitlines() if line.strip()]
        if len(printed) != 1: raise ValueError('one actual normal link command required')
        words = shlex.split(printed[0])
        rule_observation = None
        if words and Path(words[0]).name not in ('clang', 'clang++'):
            self.normal_link_edge_text = self.normal_query_command579(
                [self.ninja, '-w', 'dupbuild=warn', '-C', self.build, '-t', 'query', target],
                'actual-normal-executable-input-edge', timeout=30)
            edge = normal_edge579(target, self.normal_link_edge_text)
            source = self.remember(self.build / 'toolchain.ninja')
            rule_observation = dict(source=source, **normal_rule579(self.build / 'toolchain.ninja', edge['rule']))
            if self.remember(self.build / 'toolchain.ninja') != source:
                raise ValueError('actual generated rule file changed during bounded read')
            self.normal_link_rule_observation = rule_observation
        self.normal_link = self.normal_link_contract(target, text)
        self.report['normal_link_contract'] = self.normal_link
        self.report['normal_link_tools'] = {name: {'literal': str(path), 'file': self.remember(path)}
            for name, path in (('compiler', self.compiler), ('c_compiler', self.c_compiler), ('ninja', self.ninja))}
        retained = self.output / 'normal-link-artifacts'; retained.mkdir()
        records = {}
        source_files = [('binary', self.normal_link['binary']),
                *[(str(i), item) for i, item in enumerate(self.normal_link['CRT'])]]
        if 'wrapper' in self.normal_link:
            source_files += [('grammar' + str(i), item)
                for i, item in enumerate(self.normal_link['wrapper']['grammar_sources'])]
            raw_rule = retained / 'generated-rule.raw.ninja'
            raw_rule.write_bytes(rule_observation['text'].encode())
            self.report['normal_link_rule_artifact'] = {'source': self.normal_link['wrapper']['generated_rule'],
                'retained': {'path': str(raw_rule), 'sha256': sha(raw_rule), 'bytes': raw_rule.stat().st_size}}
        for key, source in source_files:
            path = Path(source['path']); copy = retained / key
            data = path.read_bytes()
            if sha(path) != source['sha256'] or len(data) != source['bytes']:
                raise ValueError('normal executable/CRT changed before raw retention')
            copy.write_bytes(data)
            if sha(copy) != source['sha256'] or sha(path) != source['sha256']:
                raise ValueError('normal executable/CRT changed during raw retention')
            records[key] = {'source': source, 'retained': {'path': str(copy), 'sha256': sha(copy), 'bytes': len(data)}}
        self.report['normal_link_artifacts'] = records
        self.remember(self.build / 'toolchain.ninja')
        for entry in self.installed_runtime['profile']['dsos'].values():
            for key in ('staged', 'image_file'): self.check_target_abi(entry[key]['path'])
        self.save()

    def normal_query_command579(self, argv, label, timeout=30):
        """Only the two readonly normal queries retain independent full streams.

        Every other original compile/link/ELF command keeps command() unchanged.
        No warning line is filtered, reclassified as stdout, or discarded.
        """
        kinds = {'actual-normal-executable-link-command': ['commands', '-s'],
                 'actual-normal-executable-input-edge': ['query']}
        words = list(map(str, argv))
        if (label not in kinds or timeout != 30 or words != list(map(str,
                [self.ninja, '-w', 'dupbuild=warn', '-C', self.build, '-t', *kinds[label], self.normal_link_target]))):
            raise ValueError('only the fixed readonly normal Ninja queries may use split streams')
        stem = str(len(self.report['commands'])).zfill(3) + '-' + label
        stdout = self.output / (stem + '.stdout.log'); stderr = self.output / (stem + '.stderr.log')
        row = {'argv': words, 'cwd': str(self.build), 'log': str(stdout), 'label': label,
               'stream_mode': 'normal-query-separate-stdio579/v1', 'timed_out': False}
        self.report['commands'].append(row); self.save()
        with stdout.open('xb') as output_stream, stderr.open('xb') as error_stream:
            try:
                process = subprocess.Popen(words, cwd=self.build, env=self.environment,
                    stdin=subprocess.DEVNULL, stdout=output_stream, stderr=error_stream, start_new_session=True)
                try:
                    row['exit_code'] = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # The exact original command-owned signal/wait lifecycle.
                    os.killpg(process.pid, signal.SIGTERM)
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); process.wait()
                    row.update(exit_code=124, timed_out=True, process_returncode=process.returncode)
            except OSError as error:
                error_stream.write((str(error) + '\n').encode())
                row.update(exit_code=127, launch_error=str(error))
        row['stdout'] = {'path': str(stdout), 'sha256': sha(stdout), 'bytes': stdout.stat().st_size}
        row['stderr'] = {'path': str(stderr), 'sha256': sha(stderr), 'bytes': stderr.stat().st_size}
        row['sha256'] = row['stdout']['sha256']; self.save()
        if row['exit_code']: raise ValueError('actual normal query failed: ' + label)
        return stdout.read_text(errors='replace')

    def actual_target(self):
        return None if self.normal_link is None else self.normal_link['compiler_target']

    def validate_link_target(self, flags):
        if self.normal_link is None: return
        roots = [word.split('=', 1)[1] for word in flags if word.startswith('--sysroot=')]
        if (compiler_target(flags) != self.actual_target() or abi_options(flags) != self.normal_link['abi_options'] or
                len(roots) != 1 or (self.build / roots[0]).resolve() != (self.build / 'obj/third_party/musl').resolve()):
            raise ValueError('actual link target/float-call ABI/system sysroot differs from normal executable')

    def check_target_abi(self, path):
        if self.product != PRODUCT and self.normal_link is not None:
            if machine_abi_flags(path, self.product) != self.normal_link['machine_abi_flags']:
                raise ValueError('actual ELF machine ABI flags differ from the normal executable')

    def installed_direct(self, paths, row):
        row['original_GN_direct_libraries'] = [self.remember(p) for p in paths]
        entries = self.installed_runtime['profile']['dsos']; result = []
        for path in paths:
            soname = elf_soname(path, product=self.product)
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
                names[str(path)] = elf_soname(path, product=self.product)
                self.check_target_abi(path)
                if (path.name in self.installed_runtime['profile']['dsos'] and names[str(path)] != path.name or
                        path.name.startswith('ld-musl-') and names[str(path)] != 'libc.so'):
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
        if name.rpartition('-')[0] in PRODUCTION_HELPER_NAMES579:
            from production579_native import anchor_contract
            v = anchor_contract(self, spec, name, v)
        return v

    def check_elf(self, name, binary, direct, row):
        """Shared strict contract for fresh builds and immutable artifact rechecks."""
        spec = helper_spec(name)
        if spec.get('production579_elf_contract') is not None:
            from production579_native import check_elf
            return check_elf(self, name, binary, direct, row, spec['production579_elf_contract'])
        shared = spec.get('kind') == 'shared_napi'
        interpreter = None if self.normal_link is None else self.normal_link['interpreter']
        row['elf'] = elf_header(binary, executable=not shared, shared=shared,
                               product=self.product, interpreter_path=interpreter)
        self.check_target_abi(binary)
        if shared and elf_soname(binary, product=self.product) != spec['output_basename']:
            raise ValueError('actual shared-NAPI SONAME differs from the HAP import')
        row['elf_kind'] = 'shared_napi' if shared else 'executable'
        info = self.command([self.readelf, '-h', '-l', '-d', '--dyn-syms', '--wide', '--demangle', binary], name + '-actual-ELF-ABI')
        if spec.get('language') == 'c':
            if (not defined_symbol(info, '__cfi_check') or not defined_symbol(info, 'main') or
                    'std::' in info or '__n1' in info):
                raise ValueError('actual C guest ELF lacks defined main/CFI or imports a C++/SDK ABI')
            label = 'ARM64' if self.product == PRODUCT else self.target['arch']
            row['elf_language_contract'] = 'C_' + label + '_musl_product_CFI_LTO_no_CXX_symbol_assertion'
        elif not defined_symbol(info, '__cfi_check') or 'std::__h::' not in info or 'std::__n1::' in info:
            raise ValueError('actual guest ELF lacks system __h ABI/CFI or exposes SDK __n1 ABI')
        needed = dynamic_needed(info)
        if spec.get('language') == 'c' and 'libc.so' not in needed:
            raise ValueError('actual C helper must bind the installed product libc SONAME')
        if not {Path(n).name for n in spec['libraries']} <= needed:
            raise ValueError('actual helper does not bind its required product SONAMEs')
        row['DT_NEEDED'] = sorted(needed)
        if row.get('installed_runtime_profile') is not None:
            for soname in needed: runtime_link_records(row, soname)
        for p in direct:
            if p.name not in {Path(value).name for value in spec['libraries']}: continue
            elf_header(p, product=self.product); self.check_target_abi(p)
            symbols = self.command([self.readelf, '-h', '-d', '--dyn-syms', '--wide', '--demangle', p], name + '-linked-' + p.name)
            if p.name == 'libaccesstoken_sdk.z.so' and not defined_symbol(symbols, '__cfi_check'):
                raise ValueError('actual product AccessToken DSO lacks its selected cross-DSO CFI')

    def helper(self, name):
        spec = helper_spec(name); private = self.output / name; private.mkdir()
        row = {'status': 'fail', 'fixture': spec['fixture']}; self.report['helpers'][name] = row; self.save()
        try:
            fixture = Path(spec.get('source_file', HERE / 'fixtures' / spec['fixture']))
            if not within(fixture, HERE): raise ValueError('helper source outside owned QA tools')
            row['source'] = self.remember(fixture, source=False)
            source = private / fixture.name; source.write_bytes(fixture.read_bytes())
            private_headers = {}
            if name in GLOBAL_CLOCK_HELPER_NAMES579 or name in GLOBAL_THREEUID_HELPER_NAMES579:
                for filename, header in spec.get('private_headers', {}).items():
                    if Path(filename).name != filename or not filename.endswith('.h') or not within(header, HERE):
                        raise ValueError('fixed owned global clock header required')
                    original_header = self.remember(header, source=False)
                    copied = private / filename; copied.write_bytes(Path(header).read_bytes())
                    if sha(copied) != original_header['sha256']:
                        raise ValueError('fixed clock header changed during copy')
                    private_headers[filename] = original_header
                row['private_global_clock_headers'] = private_headers

            c_language = spec.get('language') == 'c'
            driver = self.c_compiler if c_language else self.compiler
            guard = private / 'actual_system_abi.h'
            guard.write_text(C_ABI_GUARD if c_language else ABI_GUARD)
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
                validate_c_flags(flags, product=self.product, actual_target=self.actual_target())
                row['actual_C_GN_flags_preserved'] = True
            else: validate_flags(flags, product=self.product, actual_target=self.actual_target())
            if self.normal_link is not None:
                self.validate_link_target(ld)
                if abi_options(flags) != self.normal_link['abi_options']:
                    raise ValueError('actual object and normal-link float-call ABI options differ')
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
            for p in direct:
                elf_header(p, product=self.product); self.check_target_abi(p)
            self.remember(driver); self.remember(self.compiler); self.remember(self.readelf); self.remember(self.ninja)
            self.remember(self.build / 'toolchain.ninja')
            flags += [x for x in includes if x not in flags]
            shared = spec.get('kind') == 'shared_napi'
            obj, binary, deps = private / (name + '.o'), private / spec.get('output_basename', name), private / 'headers.d'
            compile_cmd = [driver, *flags, '-fPIC' if shared else '-fPIE', *([] if c_language else ['-include', guard]), '-MD', '-MF', deps, '-c', source, '-o', obj]
            ld, removed = link_flags(ld, private); row['removed_component_DSO_only_export_maps'] = removed
            if self.normal_link is None:
                # Original ARM64 behavior only; a new target cannot enter this
                # fallback or synthesize a CRT directory from a guessed triple.
                if self.product != PRODUCT: raise ValueError('actual normal-link CRT receipt absent')
                crtroot = self.build / 'obj/third_party/musl/usr/lib/aarch64-linux-ohos'
                crt = [crtroot / n for n in (('crti.o', 'crtn.o') if shared else ('Scrt1.o', 'crti.o', 'crtn.o'))]
            else:
                crt = [Path(record['path']) for record in self.normal_link['CRT']]
                if shared: crt = crt[1:]
                row['normal_link_contract'] = self.normal_link
            for p in crt: self.remember(p)
            # Preserve GN headers/CRT/safety flags. Explicit -nostdlib prevents
            # clang adding its prebuilt libc++ or sysroot libc after our inputs.
            if '-nostdlib' not in ld: raise ValueError('actual GN -nostdlib link policy required')
            searches = ['-Wl,-rpath-link=' + str(path) for path in dict.fromkeys(p.parent for p in direct)]
            output_flags = (['-shared', '-Wl,-soname=' + spec['output_basename']] if shared else
                            ['-pie', '-Wl,--export-dynamic'])
            link_cmd = [driver, *ld, *searches, *output_flags, '-Wl,--threads=2', '-o', binary,
                *crt[:-1], '-Wl,-t', '-Wl,--start-group', obj, *direct, *runtime_libs, '-Wl,--end-group', crt[-1]]
            if (not effective_cfi(ld) or
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
                if p in (source.resolve(), guard.resolve()) or p in {(private / h).resolve() for h in private_headers}:
                    headers.append({'path': str(p), 'sha256': sha(p)})
                else: headers.append(self.remember(p))
            row['actual_compiler_dependencies'] = headers; row['depfile_sha256'] = sha(deps)
            trace = self.command(link_cmd, name + '-link')
            opened = trace_link_inputs(trace, self.build)
            row['actual_link_inputs'] = [self.remember(p) for p in opened if within(p, self.root)]
            if not all(p.resolve() in opened for p in direct): raise ValueError('link trace omitted actual direct product DSO')
            self.bind_link_runtime(row, opened)
            required_runtimes = ('libc.so',) if c_language else ('libc++.so', 'libc.so')
            for soname in required_runtimes: runtime_link_records(row, soname)
            if any(not within(p, self.root) and not within(p, private) for p in opened):
                raise ValueError('linker consumed an input outside read-only product/private helper')
            self.check_elf(name, binary, direct, row)
            if sha(source) != row['source']['sha256'] or sha(guard) != row['abi_guard_sha256']:
                raise ValueError('private source/ABI guard changed during compiler invocation')
            for filename, original_header in private_headers.items():
                if sha(private / filename) != original_header['sha256'] or sha(spec['private_headers'][filename]) != original_header['sha256']:
                    raise ValueError('fixed global clock header changed during compilation')
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
            soname = elf_soname(record['path'], product=profile['product']); entry = profile['dsos'].get(soname)
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
    def __init__(self, source, output, helpers, report, expected_sha256, *, product=PRODUCT):
        self.previous_path = regular(report).resolve(); self.previous_root = self.previous_path.parent
        require_ro(self.previous_path)
        if not re.fullmatch(r'[0-9a-f]{64}', expected_sha256 or '') or sha(self.previous_path) != expected_sha256:
            raise ValueError('original build report SHA256 mismatch')
        self.previous = json.loads(self.previous_path.read_text())
        old = self.previous
        target_spec(product)
        if (old.get('product') != product or old.get('plan_only') is not False or old.get('changed_inputs') != [] or
                old.get('source_root') != str(Path(source).resolve()) or
                old.get('build_directory') != str(Path(source).resolve() / 'out' / product) or
                not re.fullmatch(r'[0-9a-f]{64}', old.get('builder_sha256', ''))):
            raise ValueError('original product/source/complete unchanged-input receipt required')
        if within(output, self.previous_root): raise ValueError('new recheck output must be outside original artifacts')
        super().__init__(source, output, helpers, product=product, _existing=True)
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
        known = (set(USB579_HELPER_NAMES) & set(old.get('helpers', {}))) | (set(HELPERS) | (set(old.get('helpers', {})) &
            (set(COMMUNICATION_HELPER_NAMES) | set(SETTINGS_HELPER_NAMES) | set(OWNING_SERVICES_HELPER_NAMES579) | set(MSDP579_HELPER_NAMES) | set(WIFI_HELPER_NAMES) |
             set(PRODUCTION_HELPER_NAMES579) | set(NUMBER_LOCAL_HELPER_NAMES580) | set(GLOBAL_CLOCK_HELPER_NAMES579) | set(GLOBAL_THREEUID_HELPER_NAMES579) |
             set(NETWORKING_HELPER_NAMES579))))
        allowed_fixtures = {Path(helper_spec(name).get('source_file',
            HERE / 'fixtures' / helper_spec(name)['fixture'])).resolve() for name in known}
        if known & set(PRODUCTION_HELPER_NAMES579):
            from production579_native import recipe_sources
            allowed_fixtures.update(p.resolve() for p in recipe_sources())
        for group, module_name in ((GLOBAL_CLOCK_HELPER_NAMES579, 'onset579_global_native.py'),
                (GLOBAL_THREEUID_HELPER_NAMES579, 'audio_threeuid_arm32_global579_native.py')):
            if known & set(group):
                allowed_fixtures.add((HERE / module_name).resolve())
                for name in known & set(group):
                    allowed_fixtures.update(Path(p).resolve() for p in helper_spec(name).get('private_headers', {}).values())
        if known & set(USB579_HELPER_NAMES):
            allowed_fixtures.add((HERE / 'usb579_native.py').resolve())
        if known & set(COMMUNICATION_HELPER_NAMES):
            allowed_fixtures.add((HERE / 'communications578_native.py').resolve())
        if known & set(SETTINGS_HELPER_NAMES):
            allowed_fixtures.add((HERE / 'settings_idle579_native.py').resolve())
        if known & set(WIFI_HELPER_NAMES):
            allowed_fixtures.add((HERE / 'apps_providers579_wifi_native.py').resolve())
        if known & set(MSDP579_HELPER_NAMES):
            allowed_fixtures.add((HERE / 'msdp579_native.py').resolve())
        if known & set(OWNING_SERVICES_HELPER_NAMES579):
            allowed_fixtures.add((HERE / 'owning_services579_native.py').resolve())
        if known & set(NETWORKING_HELPER_NAMES579):
            allowed_fixtures.add((HERE / 'networking579_native.py').resolve())
        allowed_runtime = {}
        prior_runtime = old.get('installed_runtime_profile')
        if prior_runtime is not None:
            profile = _runtime_profile({'installed_runtime_profile': prior_runtime})
            if profile['product'] != product or profile['source_root'] != str(self.root):
                raise ValueError('original installed runtime profile product/source differs')
            descriptors = [prior_runtime['source'], profile['archive'], profile['system_image']]
            if 'vendor_image' in profile: descriptors.append(profile['vendor_image'])
            if 'package_manifest' in profile: descriptors.append(profile['package_manifest'])
            descriptors += [entry['image_file'] for entry in profile['dsos'].values()]
            descriptors += list(old.get('installed_runtime_image_proof', {}).get('tools', {}).values())
            allowed_runtime = {r['path']: {k: r[k] for k in ('path', 'sha256', 'bytes')} for r in descriptors}
            if (sha(prior_runtime['source']['path']) != prior_runtime['source']['sha256'] or
                    json.loads(Path(prior_runtime['source']['path']).read_text()) != profile):
                raise ValueError('original installed profile file/receipt changed; no replacement is allowed')
            self.installed_runtime = prior_runtime
            self.report['installed_runtime_profile'] = prior_runtime
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
        normal = old.get('normal_link_contract')
        if normal is not None:
            if prior_runtime is None: raise ValueError('normal-link recheck requires original installed runtime profile')
            self.installed_runtime = prior_runtime
            query = self.prior_command('actual-normal-executable-link-command')
            expected = list(map(str, [self.ninja, '-w', 'dupbuild=warn', '-C', self.build, '-t', 'commands', '-s', normal['target']]))
            if query['argv'] != expected: raise ValueError('original actual normal Ninja query differs')
            stdout_ref, stderr_ref = normal_query_streams579(query)
            for raw in (stdout_ref, stderr_ref):
                observed = self.bound_artifact(raw['path'], raw['sha256'])
                if observed['bytes'] != raw['bytes']:
                    raise ValueError('original normal stdout/stderr complete bytes differ')
            bound = self.bound_artifact(stdout_ref['path'], stdout_ref['sha256'])
            if 'wrapper' in normal:
                edge_argv = list(map(str, [self.ninja, '-w', 'dupbuild=warn', '-C', self.build, '-t', 'query', normal['target']]))
                edge_query = self.prior_command('actual-normal-executable-input-edge', edge_argv)
                edge_stdout, edge_stderr = normal_query_streams579(edge_query)
                for raw in (edge_stdout, edge_stderr):
                    observed = self.bound_artifact(raw['path'], raw['sha256'])
                    if observed['bytes'] != raw['bytes']:
                        raise ValueError('original normal edge stdout/stderr complete bytes differ')
                edge_bound = self.bound_artifact(edge_stdout['path'], edge_stdout['sha256'])
                self.normal_link_edge_text = Path(edge_bound['path']).read_text()
                edge = normal_edge579(normal['target'], self.normal_link_edge_text)
                rule = normal_rule579(self.build / 'toolchain.ninja', edge['rule'])
                self.normal_link_rule_observation = dict(source=self.remember(self.build / 'toolchain.ninja'), **rule)
                raw = old['normal_link_rule_artifact']
                retained = self.bound_artifact(raw['retained']['path'], raw['retained']['sha256'])
                if (raw['source'] != normal['wrapper']['generated_rule'] or
                        Path(retained['path']).read_bytes() != rule['text'].encode() or
                        retained['bytes'] != raw['retained']['bytes']):
                    raise ValueError('original generated rule cut/source changed')
            self.normal_link = self.normal_link_contract(normal['target'], Path(bound['path']).read_text())
            if self.normal_link != normal:
                raise ValueError('original normal executable/CRT/target/interpreter contract changed')
            self.report['normal_link_contract'] = normal
            for entry in profile['dsos'].values():
                for key in ('staged', 'image_file'): self.check_target_abi(entry[key]['path'])
        elif product != PRODUCT:
            raise ValueError('nondefault original report has no actual normal-link target/CRT contract')
        self.save()

    def normal_query_command579(self, argv, label, timeout=30):
        raise ValueError('verify-existing replays retained normal streams and never invokes Ninja')

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
            old = self.previous['helpers'].get(name, {}); spec = helper_spec(name)
            if old.get('fixture') != spec['fixture'] or not old.get('CFI_preserved'):
                raise ValueError('original helper source/CFI receipt missing')
            compile_cmd, link_cmd = old['compile_command'], old['link_command']
            c_language = spec.get('language') == 'c'
            if c_language:
                if old.get('language') != 'c' or old.get('actual_C_GN_flags_preserved') is not True:
                    raise ValueError('original actual C graph/language receipt missing')
                validate_c_flags(compile_cmd, product=self.product, actual_target=self.actual_target())
            else:
                validate_flags(compile_cmd, product=self.product, actual_target=self.actual_target())
            if self.normal_link is not None:
                self.validate_link_target(link_cmd)
                if (old.get('normal_link_contract') != self.normal_link or
                        abi_options(compile_cmd) != self.normal_link['abi_options']):
                    raise ValueError('original helper differs from actual normal target/float ABI/CRT receipt')
                crts = [record['path'] for record in self.normal_link['CRT']]
                if spec.get('kind') == 'shared_napi': crts = crts[1:]
                if any(link_cmd.count(path) != 1 for path in crts):
                    raise ValueError('original helper link lacks exact normal executable CRT inputs')
            if not effective_cfi(link_cmd) or not any(w == '-flto' or w.startswith('-flto=') for w in link_cmd):
                raise ValueError('original link CFI/LTO missing')
            driver = self.c_compiler if c_language else self.compiler
            if Path(compile_cmd[0]).resolve() != driver.resolve() or Path(link_cmd[0]).resolve() != driver.resolve():
                raise ValueError('original actual compiler identity mismatch')
            if c_language and (Path(compile_cmd[0]).absolute() != self.c_compiler.absolute() or
                               Path(link_cmd[0]).absolute() != self.c_compiler.absolute()):
                raise ValueError('actual C driver argv[0] required; clang++ symlink cannot select C')
            self.prior_command(name + '-compile', compile_cmd); self.prior_command(name + '-link', link_cmd)
            prior_elf = self.prior_command(name + '-actual-ELF-ABI')
            base = self.artifact_origin / name
            source = base / Path(spec['fixture']).name; guard = base / 'actual_system_abi.h'
            obj = base / (name + '.o'); binary = base / spec.get('output_basename', name); deps = base / 'headers.d'
            if spec.get('kind') == 'shared_napi':
                pic = [word for word in compile_cmd if word in ('-fPIC', '-fpic', '-fPIE', '-fpie')]
                if (old.get('elf_kind') != 'shared_napi' or not pic or pic[-1] != '-fPIC' or
                        link_cmd.count('-shared') != 1 or '-pie' in link_cmd or
                        '-Wl,-soname=' + spec['output_basename'] not in link_cmd):
                    raise ValueError('original actual shared-NAPI PIC/link/SONAME contract absent')
            if (argument(compile_cmd, '-c') != str(source) or
                    (c_language and '-include' in compile_cmd) or
                    (not c_language and argument(compile_cmd, '-include') != str(guard)) or
                    argument(compile_cmd, '-o') != str(obj) or argument(compile_cmd, '-MF') != str(deps) or
                    argument(link_cmd, '-o') != str(binary) or str(obj) not in link_cmd or prior_elf['argv'][-1] != str(binary)):
                raise ValueError('original private compile/link/ELF artifact binding mismatch')
            if old['private_source_sha256'] != old['source']['sha256'] or old['source'] != self.previous['inputs'].get(old['source']['path']):
                raise ValueError('original fixture/private source hash binding mismatch')
            if old['source']['path'] != str(Path(spec.get('source_file', HERE / 'fixtures' / spec['fixture'])).resolve()):
                raise ValueError('original helper does not use current known fixture')
            row['reused_artifacts'] = {
                'source': self.bound_artifact(source, old['source']['sha256']),
                'abi_guard': self.bound_artifact(guard, old['abi_guard_sha256']),
                'object_new_hash_capture': self.bound_artifact(obj),
                'binary': self.bound_artifact(binary, old['elf']['sha256']),
                'depfile': self.bound_artifact(deps, old['depfile_sha256'])}
            expected_guard = C_ABI_GUARD if c_language else ABI_GUARD
            if sha(row['reused_artifacts']['abi_guard']['path']) != hashlib.sha256(expected_guard.encode()).hexdigest():
                raise ValueError('original guard differs from the fixed actual C or system __h/fno-exceptions contract')
            private_headers = old.get('private_global_clock_headers', {})
            if name in GLOBAL_CLOCK_HELPER_NAMES579 or name in GLOBAL_THREEUID_HELPER_NAMES579:
                if set(private_headers) != set(spec.get('private_headers', {})):
                    raise ValueError('complete actual global header set required')
                for filename, header in spec.get('private_headers', {}).items():
                    record = private_headers[filename]
                    if (record != self.previous['inputs'].get(record['path']) or
                            record['path'] != str(Path(header).resolve()) or sha(header) != record['sha256']):
                        raise ValueError('fixed original clock header binding changed')
                    self.bound_artifact(base / filename, record['sha256'])
                row['private_global_clock_headers'] = private_headers
            elif private_headers:
                raise ValueError('unexpected global headers in another helper')
            dependencies = old.get('actual_compiler_dependencies', [])
            if not dependencies: raise ValueError('original complete compiler header dependencies absent')
            for record in dependencies:
                path = Path(record['path'])
                if within(path, self.root):
                    if self.previous['inputs'].get(str(path)) != record: raise ValueError('original dependency not hash-bound')
                elif path in (source, guard) or path in {base / n for n in private_headers}: self.bound_artifact(path, record['sha256'])
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
            if c_language:
                row.update(language='c', actual_C_GN_flags_preserved=True)
            if old.get('installed_runtime_profile') is not None:
                if old['installed_runtime_profile'] != self.previous.get('installed_runtime_profile'):
                    raise ValueError('original helper installed profile did not belong to original build')
                row.update(installed_runtime_profile=old['installed_runtime_profile'],
                           actual_link_input_sonames=old['actual_link_input_sonames'])
                for soname in old['DT_NEEDED']: runtime_link_records(row, soname)
            if name in PRODUCTION_HELPER_NAMES579 or name in GLOBAL_CLOCK_HELPER_NAMES579 or name in GLOBAL_THREEUID_HELPER_NAMES579 or name in OWNING_SERVICES_HELPER_NAMES579 or name in MSDP579_HELPER_NAMES:
                row.update(source=old['source'], private_source_sha256=old['private_source_sha256'])
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
    parser.add_argument('--product', choices=tuple(TARGETS), required=True)
    parser.add_argument('--normal-link-target', help='Actual existing PIE executable Ninja output; required for nondefault products; never an SDK triple or CRT override')
    parser.add_argument('--helper', choices=tuple(HELPERS) + NUMBER_LOCAL_HELPER_NAMES580 + USB579_HELPER_NAMES + GLOBAL_CLOCK_HELPER_NAMES579 + GLOBAL_THREEUID_HELPER_NAMES579 + COMMUNICATION_HELPER_NAMES + SETTINGS_HELPER_NAMES + OWNING_SERVICES_HELPER_NAMES579 + MSDP579_HELPER_NAMES + WIFI_HELPER_NAMES + PRODUCTION_HELPER_NAMES579 + NETWORKING_HELPER_NAMES579, action='append',
                        help='Repeat to select; default original helpers only; communication helpers require explicit selection')
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
    if args.verify_existing and (args.runtime_profile or args.runtime_profile_sha256 or args.normal_link_target):
        parser.error('--verify-existing cannot add or replace an installed runtime profile')
    try:
        if args.verify_existing:
            builder = ExistingVerifier(args.source_root, args.output, helpers, args.verify_existing, args.existing_report_sha256,
                                       product=args.product)
        else: builder = Builder(args.source_root, args.output, helpers, args.plan_only,
                               runtime_profile=args.runtime_profile, runtime_profile_sha256=args.runtime_profile_sha256,
                               product=args.product, normal_link_target=args.normal_link_target)
        report = builder.run()
        print(json.dumps({'status': report['status'], 'helpers': {n: r['status'] for n, r in report['helpers'].items()}}))
        return 1 if report['status'] == 'fail' else 0
    except (OSError, ValueError, KeyError, TypeError, struct.error, tarfile.TarError, subprocess.SubprocessError) as e:
        print(json.dumps({'status': 'fail', 'error': type(e).__name__ + ': ' + str(e)})); return 1


if __name__ == '__main__': raise SystemExit(main())
