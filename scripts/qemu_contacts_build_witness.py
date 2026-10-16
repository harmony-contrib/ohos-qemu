#!/usr/bin/env python3
"""Bind fresh Contacts JS/ABC/blob/native/CFI outputs to the packaged image.

No ABC record/literal semantics or guest runtime result is inferred.  This tool
never invokes GN, Ninja, a compiler or a guest; selected commands are expanded
from the retained actual product Ninja files. Only begin moves owned outputs.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import sys
import tempfile
import time

sys.dont_write_bytecode = True

from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_runtime_elf_contract import read_elf

ROOT = Path(__file__).resolve().parents[1]
BASE = 'applications/standard/contacts_data/contacts'
OBJ = 'obj/' + BASE
LIBRARY = 'libcontact.z.so'
LINKED = 'applications/contacts_data/' + LIBRARY
UNSTRIPPED = 'lib.unstripped/' + LINKED
JS = BASE + '/src/contact.js'
ABC = OBJ + '/contact.abc'
JS_OBJECT, ABC_OBJECT = OBJ + '/contact.o', OBJ + '/contact_abc.o'
NAMES = ('contacts_api', 'contacts_sync_api', 'contacts_sync_operations', 'contacts_build',
         'contacts_control', 'contacts_napi_utils', 'kit_pixel_map_util', 'native_module',
         'result_convert', 'contacts_telephony_permission', 'kit_bundle_mgr_helper', 'sync_json_helper')
UNITS = {OBJ + '/src/contact/' + name + '.o': BASE + '/src/' + name + '.cpp' for name in NAMES}
PRODUCTS = {'arm64_virt': ('arm64', 'aarch64', 'arm64', 'lib64'),
            'armv7a_virt': ('armv7a', 'arm', 'arm', 'lib'),
            'x86_64_virt': ('x86_64', 'x86_64', 'x86_64', 'lib64')}
SCOPE = 'actual_Contacts_full_build_JS_ABC_native_CFI_image_ONLY_NOT_ABC_semantics_or_runtime'
WITNESS, PENDING = 'qemu-contacts-build-witness.json', 'qemu-contacts-build-pending.json'
CLANG = 'prebuilts/clang/ohos/linux-x86_64/llvm/bin/clang++'
TOOLCHAIN = 'toolchain.ninja'
GRAPH = OBJ + '/contact.ninja'
PINNED = {
    BASE + '/BUILD.gn': '1a8cdceeded0737519429540c55e91dae7ad4b5312e54bbb199fb624acde4cb8',
    JS: 'ae22907681082d8f7ccdaeaa81ee80d3da31114353bf2b167a060c2cf946b759',
    BASE + '/src/contacts_api.cpp': 'e4d8a123de6ba2e943c6fda5e0258960376998f54fd61565e81e8b224beeb4d8',
    BASE + '/src/contacts_napi_utils.cpp': 'ffd0180bf9632f6adc7fff2721d865446f27c65a3013f5b09b01433b484d4358',
    BASE + '/include/contacts_napi_utils.h': '3066f698312815e0bbfba4d71fb54e49d589641cd4947ba98859092dc8b1efc8',
    BASE + '/include/contact_picker_protocol.h': '722ead111840a4ecdc0336eec4511fa43790228f9decb2155bee08a5a2fa60c1',
    BASE + '/src/native_module.cpp': '994663de97eaa8835bd5fbb6e11d569b8a117e0dbe02d25d1a8ae217c3fb4e50',
    BASE + '/include/contacts_record_classes.h': '08ffca19368e55398ab59060e35db617cc4d91be7391d2a18aa12c5792de8546',
    BASE + '/src/contacts_build.cpp': '14ffa0847c8d374215fd63f5986ac412530fef0a302fd9298f3495969899231f',
    BASE + '/include/contacts_napi_object.h': 'bdc17782c1e19d44da4c93e942fd75eeea10f500b7fa2c95e24d98d908f93f46',
    'build/scripts/generate_js_bytecode.py': '2e5309400613831ae89ea784c82b5bc16094e70ccb164c76bbf6c0dcd19667de',
    'build/scripts/run_objcopy.py': '0a020914c718a7d13e564c8a02b2d68ca1bcf67049412f49c6822daead7bdd27',
    'build/ohos/ace/ace.gni': '970b3de58515b36a7ce68c18c40054bdb21ee543e850e99ee0aa6d436810a687',
}
COMPONENTS = tuple(ROOT / 'patches/common/applications/standard/contacts_data' / name for name in
                   ('attribute_mapping', 'record_classes', 'sync_mode', 'picker_result_protocol'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
            'actual regular Contacts evidence required: ' + str(path))
    return path


def relative(name):
    require(isinstance(name, str) and name and not name.startswith('/') and
            '..' not in PurePosixPath(name).parts and str(PurePosixPath(name)) == name,
            'canonical relative evidence path required')
    return name


def write(path, value):
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8))
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')
    os.replace(temporary, path)


def staged(product):
    return 'packages/phone/system/' + PRODUCTS[product][3] + '/module/' + LIBRARY


def outputs(product):
    return [ABC, JS_OBJECT, ABC_OBJECT, *UNITS, LINKED, UNSTRIPPED, staged(product)]


def payload_api():
    # Public Apps parser is the single ELF/blob/ABC implementation.
    location = str(ROOT / 'ci/capability-audit')
    if location not in sys.path:
        sys.path.insert(0, location)
    return importlib.import_module('batch_apps_contact_payload')


def recipe():
    paths = [Path(__file__), ROOT / 'ci/capability-audit/batch_apps_contact_payload.py',
             ROOT / 'scripts/ext_image_entries.py', ROOT / 'scripts/verify_alsa_config_image.py',
             ROOT / 'scripts/verify_runtime_elf_contract.py']
    for component in COMPONENTS:
        require(component.is_dir(), 'Contacts source component missing')
        paths += [p for p in component.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    return {str(p.relative_to(ROOT)): file_sha256(regular(p)) for p in sorted(set(paths))}


def sources(source):
    names = set(PINNED) | set(UNITS.values())
    names.update(str(p.relative_to(source)) for p in (source / BASE / 'include').glob('*.h'))
    values = {name: file_sha256(regular(source / name)) for name in sorted(names)}
    require(all(values.get(name) == checksum for name, checksum in PINNED.items()),
            'complete current Contacts JS/callback/native registration/build source composition required')
    return values


def source_map_check(values):
    require(isinstance(values, dict) and set(PINNED) | set(UNITS.values()) <= set(values),
            'complete Contacts native/source map required')
    for name, checksum in values.items():
        relative(name)
        require(name in PINNED or name in UNITS.values() or
                (str(PurePosixPath(name).parent) == BASE + '/include' and name.endswith('.h')),
                'unrelated source in Contacts inventory')
        require(isinstance(checksum, str) and re.fullmatch('[a-f0-9]{64}', checksum), 'source checksum malformed')
    require(all(values[name] == checksum for name, checksum in PINNED.items()), 'fixed current source changed')


def begin(source, product):
    source = Path(source); current = sources(source); build = source / 'out' / product
    regular(source / BASE / 'BUILD.gn')
    names = outputs(product) + [WITNESS]
    # Check every existing path before the first move; a symlink must not produce
    # a half-preserved attempt. No stamps, unrelated targets or sources move.
    existing = [name for name in names if (build / name).exists() or (build / name).is_symlink()]
    for name in existing:
        regular(build / name)
    value = dict(schema_version=1, phase='prepared', scope=SCOPE, product=product,
                 nonce=secrets.token_hex(16), start_ns=time.time_ns(), source_root=str(source),
                 source_sha256=current, recipe=recipe(), preserved={})
    archive = build / '.qemu-contacts-witness' / value['nonce']; archive.mkdir(parents=True)
    for name in existing:
        path = build / name; destination = archive / name; destination.parent.mkdir(parents=True, exist_ok=True)
        value['preserved'][name] = dict(path=str(destination), sha256=file_sha256(path))
        os.replace(path, destination)
    write(archive / 'prepared.json', value); write(build / PENDING, value)
    return value


def logical_lines(text):
    require('\x00' not in text and '\r' not in text, 'malformed Ninja text')
    return re.sub(r'\$\n[ \t]*', '', text).splitlines()


def bindings(lines):
    result = {}
    for line in lines:
        match = re.fullmatch(r'[ \t]*([A-Za-z_][A-Za-z_0-9]*)[ \t]*=[ \t]?(.*)', line)
        if match:
            require(match[1] not in result, 'duplicate Ninja binding: ' + match[1])
            result[match[1]] = match[2]
    return result


def block(lines, prefix):
    indices = [i for i, line in enumerate(lines) if line == prefix]
    require(len(indices) == 1, 'missing/ambiguous actual Ninja rule or edge: ' + prefix)
    index = indices[0]; end = index + 1
    while end < len(lines) and (lines[end].startswith((' ', '\t')) or not lines[end]):
        end += 1
    return lines[index], bindings(lines[index + 1:end])


def expand(text, env, stack=()):
    result = ''; index = 0
    while index < len(text):
        if text[index] != '$':
            result += text[index]; index += 1; continue
        require(index + 1 < len(text), 'trailing Ninja escape')
        char = text[index + 1]
        if char in '$ :':
            result += char; index += 2; continue
        match = re.match(r'\$\{([A-Za-z_][A-Za-z_0-9]*)\}|\$([A-Za-z_][A-Za-z_0-9]*)', text[index:])
        require(match is not None, 'unsupported Ninja expression')
        name = match[1] or match[2]
        require(name in env and name not in stack, 'unknown/cyclic selected Ninja binding: ' + name)
        result += expand(env[name], env, stack + (name,)); index += len(match[0])
    return result


def edge(lines, target):
    # These fixed Contacts outputs contain no escaped whitespace/colons.
    matches = []
    for line in lines:
        match = re.fullmatch(r'build ([^:]+): (\S+)(.*)', line)
        if match and target in [str(PurePosixPath(s)) for s in match[1].split()]:
            matches.append((line, match))
    require(len(matches) == 1, 'unique actual Contacts build edge required: ' + target)
    line, match = matches[0]; _, local = block(lines, line)
    tokens = match[3].split(); explicit = tokens[:next((i for i, s in enumerate(tokens) if s in ('|', '||')), len(tokens))]
    return match[2], explicit, tokens, local, [str(PurePosixPath(s)) for s in match[1].split()]


def words(command):
    require(isinstance(command, str) and not re.search(r'[;&|<>`#\n\r]|\$\(', command),
            'shell control/comment/substitution outside the fixed product command contract')
    argv = shlex.split(command)
    require(argv and not any(x in (';', '&&', '||', '|', '>', '<') for x in argv), 'shell composition in selected command')
    return argv


def protected(argv, product, exceptions=True):
    state = dict(vcall=False, icall=False, cross_dso=False, lto=False, exceptions=True, rtti=True)
    for flag in argv:
        if flag.startswith(('-fsanitize=', '-fno-sanitize=')):
            enabled = flag.startswith('-fsanitize=')
            for name in flag.split('=', 1)[1].split(','):
                for kind in ('vcall', 'icall'):
                    if name in ('all', 'cfi', 'cfi-' + kind): state[kind] = enabled
        elif flag in ('-fsanitize-cfi-cross-dso', '-fno-sanitize-cfi-cross-dso'):
            state['cross_dso'] = flag == '-fsanitize-cfi-cross-dso'
        elif flag in ('-flto', '-flto=thin', '-flto=full', '-fno-lto'):
            state['lto'] = flag != '-fno-lto'
        elif flag in ('-fexceptions', '-fno-exceptions'):
            state['exceptions'] = flag == '-fexceptions'
        elif flag in ('-frtti', '-fno-rtti'):
            state['rtti'] = flag == '-frtti'
    require(all(state[k] for k in ('vcall', 'icall', 'cross_dso', 'lto')) and
            (not exceptions or not state['exceptions'] and not state['rtti']) and
            [x for x in argv if x.startswith('--target=')] == ['--target=' + PRODUCTS[product][1] + '-linux-ohos'] and
            '-target' not in argv and [x for x in argv if x.startswith('--sysroot=')] == ['--sysroot=obj/third_party/musl'],
            'actual final effective CFI/LTO/product compiler flags required')


def compile_check(command, unit, product):
    argv = words(command)
    if Path(argv[0]).name == 'ccache': argv = argv[1:]
    require(argv and argv[0] == '../../' + CLANG and argv.count('-c') == argv.count('-o') == 1 and
            argv.index('-c') + 1 < len(argv) and argv.index('-o') + 1 < len(argv) and
            argv[argv.index('-c') + 1] == '../../' + UNITS[unit] and argv[argv.index('-o') + 1] == unit and
            '--sysroot=obj/third_party/musl' in argv and not any(x.startswith('@') for x in argv),
            'actual Contacts source/output compiler command required')
    protected(argv, product)


def action_check(command, kind, source_root, product):
    source = Path(source_root); build = source / 'out' / product
    argv = words(command)
    require(argv[:1] == ['/usr/bin/env'], 'actual fixed GN action launcher required')
    if kind == 'abc':
        expected = ['/usr/bin/env', '../../build/scripts/generate_js_bytecode.py', '--src-js', str(source / JS),
                    '--dst-file', str(build / ABC), '--frontend-tool-path', str(build / 'clang_x64/arkcompiler/ets_frontend'), '--module']
    else:
        input_path = source / JS if kind == 'js' else build / ABC
        output_path = build / (JS_OBJECT if kind == 'js' else ABC_OBJECT)
        expected = ['/usr/bin/env', '../../build/scripts/run_objcopy.py', '--objcopy',
                    str(source / 'prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-objcopy'),
                    '--input', str(input_path), '--output', str(output_path), '--arch', PRODUCTS[product][2]]
    require(argv == expected, 'actual current absolute JS/ABC/objcopy GN action differs')


def graph_commands(graph, toolchain, source_root, product):
    lines, rules = logical_lines(graph), logical_lines(toolchain)
    before_build = lines[:next((i for i, line in enumerate(lines) if line.startswith('build ')), len(lines))]
    common = bindings(before_build); commands = {}
    cxx_rule, cxx = block(rules, 'rule cxx')
    require(cxx_rule == 'rule cxx', 'wrong product compiler rule')
    for unit, src in UNITS.items():
        rule, inputs, _, local, outs = edge(lines, unit)
        require(rule == 'cxx' and inputs == ['../../' + src] and outs == [unit], 'native source/object GN edge differs')
        env = {**common, **local, 'in': inputs[0], 'out': unit}
        command = expand(cxx['command'], env); compile_check(command, unit, product); commands[unit] = command
    rule, inputs, _, local, outs = edge(lines, LINKED)
    require(rule == 'solink' and outs == [LINKED, UNSTRIPPED] and
            all(inputs.count(unit) == 1 for unit in [*UNITS, JS_OBJECT, ABC_OBJECT]),
            'complete native + both embedded objects must be linked exactly once')
    name, link = block(rules, 'rule solink')
    require(name == 'rule solink', 'actual solink rule differs')
    env = {**common, **local, 'in': ' '.join(inputs), 'out': ' '.join(outs)}
    command = expand(link['command'], env); argv = words(command)
    require('--' in argv and argv.count('--') == 1, 'actual protected solink wrapper required')
    driver = argv[argv.index('--') + 1:]
    require(argv[0:2] == ['/usr/bin/env', '../../build/toolchain/gcc_solink_wrapper.py'] and
            '--sofile=./' + UNSTRIPPED in argv and '--output=' + LINKED in argv and
            driver and driver[0] == '../../' + CLANG and '-shared' in driver and driver.count('-o') == 1 and
            '--sysroot=obj/third_party/musl' in driver and
            driver[driver.index('-o') + 1] == './' + UNSTRIPPED and
            [x for x in driver if x.startswith('@')] == ['@' + LINKED + '.rsp'] and '-Wl,-soname=' + LIBRARY in driver,
            'actual Contacts full protected link command/output required')
    response = expand(link['rspfile_content'], env); response_words = words(response)
    require(not any(x.startswith('@') for x in response_words), 'nested unretained linker response file')
    effective_driver = [value for token in driver for value in (response_words if token == '@' + LINKED + '.rsp' else [token])]
    protected(effective_driver, product, exceptions=False); commands[LINKED] = command
    require(all(response_words.count(unit) == 1 for unit in [*UNITS, JS_OBJECT, ABC_OBJECT]), 'link response lacks actual inputs')
    for kind, target, label in [('abc', ABC, 'gen_contact_abc'), ('js', JS_OBJECT, 'gen_js_obj_contact_js'),
                                ('abc_object', ABC_OBJECT, 'gen_js_obj_contact_abc')]:
        rule, inputs, tokens, _, outs = edge(rules, target)
        require(inputs == [] and outs == [target] and tokens.count('|') == 1, 'Contacts GN action output/dependency edge differs')
        _, bindings_ = block(rules, 'rule ' + rule)
        require(bindings_.get('description') == 'ACTION //' + BASE + ':' + label +
                '(//build/toolchain/ohos:ohos_clang_' + PRODUCTS[product][2] + ')', 'actual product action label differs')
        action = bindings_['command']; action_check(action, kind, source_root, product)
        required = {'abc': ['../../build/scripts/generate_js_bytecode.py', '../../' + JS, 'clang_x64/arkcompiler/ets_frontend/es2abc'],
                    'js': ['../../build/scripts/run_objcopy.py', '../../' + JS, OBJ + '/gen_contact_abc.stamp'],
                    'abc_object': ['../../build/scripts/run_objcopy.py', ABC, OBJ + '/gen_contact_abc.stamp']}[kind]
        require(tokens[1:] == required, 'actual source/tool/action dependency set differs')
        commands[target] = action
    return {'commands': commands, 'link_response': response,
            'command_scope': 'expanded_actual_retained_product_GN_rules_NOT_separately_executed_commands'}


def full_build_argv(argv, product):
    require(isinstance(argv, list) and all(isinstance(s, str) for s in argv) and argv and argv[0] == './build.sh',
            'actual full build argv JSON array required')
    def option(key):
        values = []
        for i, arg in enumerate(argv):
            if arg == key:
                require(i + 1 < len(argv), 'missing build option value'); values.append(argv[i + 1])
            elif arg.startswith(key + '='): values.append(arg.split('=', 1)[1])
        require(len(values) == 1, 'unique full build argument required: ' + key)
        return values[0]
    require(option('--product-name') == product and option('--build-target') == 'images' and
            option('--build-only-load') == 'false' and option('--fast-rebuild') == 'false',
            'actual images build with fresh GN (not persisted fast/load-only) required')


def build_log_check(text, commands, source_root, product):
    lines = text.splitlines(); positions = []
    for unit in UNITS:
        hits = [i for i, line in enumerate(lines) if re.search(r'\bCXX\s+' + re.escape(unit) + r'\s*$', line)]
        require(len(hits) == 1, 'full build log requires one forced native compilation: ' + unit); positions += hits
    for label in ('gen_contact_abc', 'gen_js_obj_contact_js', 'gen_js_obj_contact_abc'):
        suffix = 'ACTION //' + BASE + ':' + label + '(//build/toolchain/ohos:ohos_clang_' + PRODUCTS[product][2] + ')'
        hits = [i for i, line in enumerate(lines) if line.rstrip().endswith(suffix)]
        require(len(hits) == 1, 'full build log missing/duplicate forced action: ' + label); positions += hits
    links = [i for i, line in enumerate(lines) if re.search(r'\bSOLINK\s+' + re.escape(LINKED) + r'\s*$', line)]
    require(len(links) == 1, 'full build log requires actual final Contacts solink'); positions += links
    source = Path(source_root); build = source / 'out' / product
    expected = ['./ets_frontend/es2abc', '--output', str(build / ABC), '--module', str(source / JS), '--target-api-sub-version=beta3']
    executions = []
    for i, line in enumerate(lines):
        if './ets_frontend/es2abc ' in line and str(build / ABC) in line:
            match = re.search(r'(\./ets_frontend/es2abc .*?) \| execution_path: (.*)$', line)
            require(match is not None and words(match[1]) == expected and
                    match[2].strip() == str(build / 'clang_x64/arkcompiler'), 'actual es2abc invocation/cwd differs')
            executions.append(i)
    require(len(executions) == 1, 'fresh real es2abc execution line required'); positions += executions
    success = [i for i, line in enumerate(lines) if re.fullmatch(r'\[OHOS INFO\][ \t]+' + re.escape(product) + r' build success[ \t]*', line)]
    require(len(success) == 1 and success[0] > max(positions), 'complete actual hb product build success required after forced work')
    require(not re.search(r'(?m)(?:^|\s)(?:FAILED:|ninja: build stopped:)|^\[OHOS ERROR\].*build failed', text), 'failed actual build log')


def tool_hashes(source, product):
    paths = [CLANG, 'prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-objcopy',
             'out/' + product + '/clang_x64/arkcompiler/ets_frontend/es2abc']
    values = {}
    for name in paths:
        path = source / name; resolved = path.resolve(strict=True)
        require(resolved.is_file() and resolved.is_relative_to(source), 'actual source-bound build tool required')
        values[name] = {'resolved_source_path': str(resolved.relative_to(source)), 'sha256': file_sha256(resolved)}
    return values


def cfi_check(path, product):
    info = read_elf(regular(path)); expected = {'arm64_virt': 183, 'armv7a_virt': 40, 'x86_64_virt': 62}[product]
    require(info.machine == expected and '__cfi_check' in info.defined, 'actual product Contacts cross-DSO CFI export missing')
    names = info.defined | info.undefined
    require(any('NSt3__h' in name for name in names) and
            not any('NSt3__n1' in name or 'NSt4__Cr' in name for name in names), 'Contacts requires the actual product std::__h ABI')


def capture(source, product):
    build = source / 'out' / product
    graph, toolchain = regular(build / GRAPH).read_bytes(), regular(build / TOOLCHAIN).read_bytes()
    selected = graph_commands(graph.decode(), toolchain.decode(), str(source), product)
    return selected, {'graph/contact.ninja': graph, 'graph/toolchain.ninja': toolchain,
                      'graph/args.gn': regular(build / 'args.gn').read_bytes()}


def artifact_rows(build, product, start, end):
    result = {}
    for name in outputs(product):
        path = regular(build / name); stat = path.stat()
        require(start <= stat.st_mtime_ns <= end and stat.st_size > 0, 'Contacts output not fresh in this attempt: ' + name)
        result[name] = dict(sha256=file_sha256(path), mtime_ns=stat.st_mtime_ns, bytes=stat.st_size)
    return result


def payload_check(directory, product, image_dso=None):
    data = lambda path: regular(directory / ('outputs/' + path))
    for name in (UNSTRIPPED, LINKED, staged(product)):
        cfi_check(data(name), product)
    result = payload_api().verify_payloads(source_js=regular(directory / ('source/' + JS)), abc=data(ABC),
        js_object=data(JS_OBJECT), abc_object=data(ABC_OBJECT), unstripped=data(UNSTRIPPED), linked=data(LINKED),
        staged=data(staged(product)), image_dso=image_dso or data(staged(product)), arch=PRODUCTS[product][0])
    canonical = {'source_js': 'source/' + JS, 'abc': 'outputs/' + ABC, 'js_object': 'outputs/' + JS_OBJECT,
                 'abc_object': 'outputs/' + ABC_OBJECT, 'unstripped': 'outputs/' + UNSTRIPPED,
                 'linked': 'outputs/' + LINKED, 'staged': 'outputs/' + staged(product),
                 'image_dso': 'independently_extracted_image/' + LIBRARY}
    require(set(result.get('artifacts', {})) == set(canonical), 'public payload parser contract changed')
    for name, path in canonical.items():
        result['artifacts'][name]['path'] = path
    return result


def witness_check(value, product):
    require(value.get('schema_version') == 1 and value.get('phase') == 'completed' and value.get('scope') == SCOPE and
            value.get('product') == product and value.get('recipe') == recipe() and
            isinstance(value.get('nonce'), str) and re.fullmatch('[a-f0-9]{32}', value['nonce']) and
            type(value.get('start_ns')) is int and type(value.get('finished_ns')) is int and
            0 < value['start_ns'] <= value['finished_ns'] and value.get('build_exit_code') == 0 and
            type(value.get('build_exit_code')) is int, 'complete current actual Contacts build witness required')
    root = value.get('source_root')
    require(isinstance(root, str) and Path(root).is_absolute() and str(Path(root)) == root and '..' not in Path(root).parts,
            'actual canonical source root required')
    source_map_check(value.get('source_sha256'))
    require(set(value.get('artifacts', {})) == set(outputs(product)), 'exact 18 forced Contacts outputs required')
    for row in value['artifacts'].values():
        require(isinstance(row.get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', row['sha256']) and
                type(row.get('mtime_ns')) is int and value['start_ns'] <= row['mtime_ns'] <= value['finished_ns'] and
                type(row.get('bytes')) is int and row['bytes'] > 0, 'fresh Contacts output record missing')
    for key in ('build_log', 'build_argv'):
        row = value.get(key, {})
        require(isinstance(row.get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', row['sha256']) and
                type(row.get('bytes')) is int and row['bytes'] > 0 and type(row.get('mtime_ns')) is int and
                0 < row['mtime_ns'] <= value['finished_ns'] and
                (key != 'build_log' or row['mtime_ns'] >= value['start_ns']), 'actual fresh build log/argv metadata required')
    for field in ('module_record_and_literal_binding_verified', 'public_runtime_execution_verified', 'first_artifact_behavior_gate_passed'):
        require(value.get(field) is False, 'build evidence must not claim ABC semantics or runtime')
    require(set(value.get('tools', {})) == {CLANG, 'prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-objcopy',
            'out/' + product + '/clang_x64/arkcompiler/ets_frontend/es2abc'}, 'actual three build tool identities missing')
    for tool in value['tools'].values():
        relative(tool['resolved_source_path']); require(re.fullmatch('[a-f0-9]{64}', tool['sha256']), 'actual tool hash missing')


def check_inventory(value, product, directory, image_dso=None):
    directory = Path(directory)
    require(value.get('schema_version') == 1 and value.get('scope') == SCOPE and value.get('product') == product and
            value.get('recipe') == recipe() and value.get('first_artifact_behavior_gate_passed') is False,
            'current Contacts build inventory required')
    files = value.get('files_sha256', {})
    for name, checksum in files.items():
        relative(name); require(file_sha256(regular(directory / name)) == checksum, 'Contacts evidence bytes changed: ' + name)
    witness = json.loads(regular(directory / 'witness.json').read_text()); witness_check(witness, product)
    expected = {'witness.json', 'build-log.txt', 'build-argv.json', 'commands.json', 'link-response.txt',
                'graph/contact.ninja', 'graph/toolchain.ninja', 'graph/args.gn'}
    expected |= {'source/' + name for name in witness['source_sha256']}
    expected |= {'outputs/' + name for name in outputs(product)}
    require(set(files) == expected and value.get('source_sha256') == witness['source_sha256'], 'complete exact Contacts evidence payload set required')
    actual = {str(path.relative_to(directory)) for path in directory.rglob('*') if path.is_file() or path.is_symlink()}
    require(actual - {'inventory.json'} == expected, 'extra or missing Contacts package evidence files')
    for name, checksum in witness['source_sha256'].items():
        require(files['source/' + name] == checksum, 'source witness differs from raw actual source')
    for name, row in witness['artifacts'].items():
        path = regular(directory / ('outputs/' + name))
        require(files['outputs/' + name] == row['sha256'] and path.stat().st_size == row['bytes'], 'actual forced output witness mismatch')
    commands = graph_commands((directory / 'graph/contact.ninja').read_text(), (directory / 'graph/toolchain.ninja').read_text(),
                              witness['source_root'], product)
    require(json.loads((directory / 'commands.json').read_text()) == commands and
            (directory / 'link-response.txt').read_text() == commands['link_response'] and
            witness.get('commands') == commands, 'raw selected graph/command/link response mismatch')
    for key, path in [('build_log', 'build-log.txt'), ('build_argv', 'build-argv.json')]:
        require(witness.get(key, {}).get('sha256') == files[path] and
                witness[key]['bytes'] == (directory / path).stat().st_size, 'actual full build command/log witness mismatch')
    require(witness.get('graphs_sha256') == {name: files['graph/' + name] for name in ('contact.ninja', 'toolchain.ninja', 'args.gn')},
            'actual product raw graphs differ from build witness')
    full_build_argv(json.loads((directory / 'build-argv.json').read_text()), product)
    build_log_check((directory / 'build-log.txt').read_text(), commands, witness['source_root'], product)
    result = payload_check(directory, product, image_dso)
    # The public parser independently rereads every source/blob/DSO. Its own
    # deliberately narrower claims are preserved rather than rewritten as runtime.
    require(witness.get('payload_identity') == result, 'stored Contacts payload identity differs')
    return value


def materialize(source, product, witness, graph_payload, directory, log, argv_path):
    payload = dict(graph_payload)
    payload.update({'witness.json': (json.dumps(witness, indent=2) + '\n').encode(),
                    'build-log.txt': regular(log).read_bytes(), 'build-argv.json': regular(argv_path).read_bytes(),
                    'commands.json': (json.dumps(witness['commands'], indent=2) + '\n').encode(),
                    'link-response.txt': witness['commands']['link_response'].encode()})
    for name in witness['source_sha256']:
        payload['source/' + name] = regular(source / name).read_bytes()
    for name in outputs(product):
        payload['outputs/' + name] = regular(source / 'out' / product / name).read_bytes()
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in payload.items():
        path = directory / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    return dict(schema_version=1, scope=SCOPE, product=product, source_sha256=witness['source_sha256'], recipe=recipe(),
                files_sha256={name: sha(data) for name, data in payload.items()}, first_artifact_behavior_gate_passed=False)


def finish(source, product, log, argv_path, exit_code):
    source = Path(source); build = source / 'out' / product
    value = json.loads(regular(build / PENDING).read_text())
    require(value.get('phase') == 'prepared' and value.get('product') == product and value.get('scope') == SCOPE and
            value.get('source_root') == str(source) and value.get('recipe') == recipe() and
            value.get('source_sha256') == sources(source), 'current Contacts preparation/source changed')
    require(type(exit_code) is int and exit_code == 0, 'actual full product build must exit zero')
    full_build_argv(json.loads(regular(argv_path).read_text()), product)
    selected, graphs = capture(source, product)
    build_log_check(regular(log).read_text(), selected, str(source), product)
    now = time.time_ns(); artifacts = artifact_rows(build, product, value['start_ns'], now)
    require(value['start_ns'] <= regular(log).stat().st_mtime_ns <= now, 'actual full build log predates this attempt')
    value.update(phase='completed', finished_ns=now, artifacts=artifacts, commands=selected, tools=tool_hashes(source, product),
        graphs_sha256={name.removeprefix('graph/'): sha(data) for name, data in graphs.items()}, build_exit_code=exit_code,
        build_log=dict(path=str(log), sha256=file_sha256(log), bytes=Path(log).stat().st_size, mtime_ns=Path(log).stat().st_mtime_ns),
        build_argv=dict(path=str(argv_path), sha256=file_sha256(argv_path), bytes=Path(argv_path).stat().st_size, mtime_ns=Path(argv_path).stat().st_mtime_ns),
        module_record_and_literal_binding_verified=False, public_runtime_execution_verified=False, first_artifact_behavior_gate_passed=False)
    with tempfile.TemporaryDirectory(prefix='contacts-build-check-') as temporary:
        directory = Path(temporary).resolve()
        inventory = materialize(source, product, value, graphs, directory, log, argv_path)
        value['payload_identity'] = payload_check(directory, product)
        # Replace only our own temporary witness after filling the parser result.
        write(directory / 'witness.json', value); inventory['files_sha256']['witness.json'] = file_sha256(directory / 'witness.json')
        check_inventory(inventory, product, directory)
    write(build / WITNESS, value)
    return value


def package(source, product, directory):
    source = Path(source); directory = Path(directory)
    value = json.loads(regular(source / 'out' / product / WITNESS).read_text()); witness_check(value, product)
    require(value['source_sha256'] == sources(source), 'Contacts source changed after full build')
    require(value['source_root'] == str(source), 'Contacts build source root differs')
    _, graphs = capture(source, product)
    require(not directory.exists() and not directory.is_symlink(), 'new exclusive Contacts provenance directory required')
    # Validate all evidence in private scratch before publishing a package directory.
    with tempfile.TemporaryDirectory(prefix='contacts-package-check-') as temporary:
        scratch = Path(temporary).resolve()
        inventory = materialize(source, product, value, graphs, scratch, Path(value['build_log']['path']), Path(value['build_argv']['path']))
        check_inventory(inventory, product, scratch)
        directory.mkdir(parents=True)
        for name in inventory['files_sha256']:
            target = directory / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes((scratch / name).read_bytes())
        write(directory / 'inventory.json', inventory)
    return inventory


def image(system_image, directory, product):
    directory = Path(directory); regular(system_image)
    inventory = check_inventory(json.loads(regular(directory / 'inventory.json').read_text()), product, directory)
    prefix = PRODUCTS[product][3] + '/module/' + LIBRARY
    with tempfile.TemporaryDirectory(prefix='contacts-image-') as temporary:
        binary, inode = dump_unique_file(system_image, ('/' + prefix, '/system/' + prefix), Path(temporary).resolve(), debugfs_path())
        require(file_sha256(binary) == inventory['files_sha256']['outputs/' + staged(product)], 'actual system.img Contacts DSO differs')
        check_inventory(inventory, product, directory, image_dso=binary)
    return dict(status='pass', scope=SCOPE, product=product, image_entry=inode,
        system_image_sha256=file_sha256(system_image), inventory_sha256=file_sha256(directory / 'inventory.json'),
        module_record_and_literal_binding_verified=False, public_runtime_execution_verified=False, first_artifact_behavior_gate_passed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('begin', 'finish', 'package', 'verify'))
    parser.add_argument('--source-root', type=Path); parser.add_argument('--product', choices=PRODUCTS, required=True)
    parser.add_argument('--build-log', type=Path); parser.add_argument('--build-argv-json', type=Path)
    parser.add_argument('--build-exit-code', type=int); parser.add_argument('--directory', type=Path)
    parser.add_argument('--system-image', type=Path); parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.phase in ('begin', 'finish', 'package') and args.source_root is None: parser.error('source-root required')
    if args.phase == 'finish' and (args.build_log is None or args.build_argv_json is None or args.build_exit_code is None):
        parser.error('actual build-log/build-argv-json/build-exit-code required')
    if args.phase in ('package', 'verify') and (args.directory is None or args.system_image is None):
        parser.error('directory/system-image required')
    source = args.source_root.resolve() if args.source_root else None
    if args.phase == 'begin': result = begin(source, args.product)
    elif args.phase == 'finish': result = finish(source, args.product, args.build_log, args.build_argv_json, args.build_exit_code)
    else:
        if args.phase == 'package': package(source, args.product, args.directory)
        result = image(args.system_image, args.directory, args.product)
    if args.output: write(args.output, result)
    print(json.dumps({key: result[key] for key in ('phase', 'product', 'status', 'scope', 'nonce') if key in result}))


if __name__ == '__main__': main()
