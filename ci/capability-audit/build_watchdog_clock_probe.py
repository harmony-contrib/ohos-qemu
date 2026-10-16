#!/usr/bin/env python3
"""Build three isolated SDK39 clock CLIs; never run them or change product DSOs.

Only the enclosing root task may execute this builder under its build lease.
verify_build is a read-only host adapter: it re-reads local source, receipt,
logs and ELF bytes, but does not pretend that Linux SDK tools/headers are
available on the host. Their original paths and actual builder hashes remain
in the receipt. A build pass is not guest clock, suspend or watchdog evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import time


CURRENT_SOURCE = Path(__file__).absolute().with_name('watchdog_clock_probe.c')
BUILDER = Path(__file__).absolute()
ARCHES = {
    'arm64': ('aarch64-linux-ohos', 2, 183, 'aarch64', ()),
    'armv7a': ('arm-linux-ohos', 1, 40, 'arm', ('-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon')),
    'x86_64': ('x86_64-linux-ohos', 2, 62, 'x86_64', ()),
}
SCOPE = 'actual_SDK39_compile_link_ELF_ONLY_NOT_guest_clock_or_watchdog_acceptance'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact(path):
    path = Path(path).absolute()
    require(path.is_file(), 'regular input/artifact missing: ' + str(path))
    return {'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size}


def input_record(path):
    # Keep argv[0]'s clang / llvm-readelf spelling. Only the hash target is
    # canonical; resolving llvm-readelf for invocation selects readobj mode.
    return {**artifact(path), 'canonical_path': str(Path(path).resolve())}


def checked(record):
    require(isinstance(record, dict) and artifact(record['path']) ==
            {key: record[key] for key in ('path', 'sha256', 'size')}, 'local artifact changed: ' + str(record))
    return Path(record['path'])


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def load(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=no_duplicates)


def native_metadata(value):
    require(isinstance(value, dict) and value.get('path') == 'native' and str(value.get('apiVersion')) == '26' and
            value.get('version') == '26.0.0.39' and value.get('platformVersion') == '26.0.0',
            'actual API26 native SDK 26.0.0.39 required')
    return value


def span(data, offset, size):
    require(offset >= 0 and size >= 0 and offset <= len(data) and size <= len(data) - offset,
            'ELF file range is truncated or outside file')
    return data[offset:offset + size]


def elf_metadata(data, arch):
    """Parse full ELF header/PH and real DT_NEEDED from file-backed PT_DYNAMIC."""
    require(arch in ARCHES, 'unsupported clock CLI architecture')
    _, cls, machine, loader, _ = ARCHES[arch]
    require(data[:7] == b'\x7fELF' + bytes((cls, 1, 1)), 'wrong ELF magic/class/data/version')
    fmt = '<HHIQQQIHHHHHH' if cls == 2 else '<HHIIIIIHHHHHH'
    ehsize = 16 + struct.calcsize(fmt)
    values = struct.unpack(fmt, span(data, 16, ehsize - 16))
    keys = ('type', 'machine', 'version', 'entry', 'phoff', 'shoff', 'flags', 'ehsize', 'phentsize',
            'phnum', 'shentsize', 'shnum', 'shstrndx')
    header = dict(zip(keys, values))
    header['ident_hex'] = data[:16].hex()
    require(header['type'] == 3 and header['machine'] == machine and header['version'] == 1 and
            header['ehsize'] == ehsize, 'actual target PIE ELF header required')
    require(header['shnum'] > 0 and header['shstrndx'] < header['shnum'] and
            header['shentsize'] == (64 if cls == 2 else 40), 'ELF section table malformed or extended')
    span(data, header['shoff'], header['shnum'] * header['shentsize'])
    if arch == 'armv7a':
        require(header['flags'] & 0xff000000 == 0x05000000 and not header['flags'] & 0x400,
                'actual ARM EABI5 base/softfp calling convention required')
    pfmt = '<IIQQQQQQ' if cls == 2 else '<IIIIIIII'
    require(header['phentsize'] == struct.calcsize(pfmt) and 0 < header['phnum'] < 65535,
            'ELF program table missing or malformed')
    span(data, header['phoff'], header['phnum'] * header['phentsize'])
    programs = []
    for index in range(header['phnum']):
        fields = struct.unpack(pfmt, span(data, header['phoff'] + index * header['phentsize'], header['phentsize']))
        if cls == 2:
            typ, flags, offset, address, physical, size, memory, align = fields
        else:
            typ, offset, address, physical, size, memory, flags, align = fields
        span(data, offset, size)
        require(typ not in (1, 2) or size <= memory, 'ELF segment file size exceeds memory size')
        if typ == 1:
            require(align in (0, 1) or (align & (align - 1) == 0 and address % align == offset % align),
                    'ELF PT_LOAD alignment mismatch')
        programs.append(dict(zip(('type', 'flags', 'offset', 'vaddr', 'paddr', 'filesz', 'memsz', 'align'),
                                 (typ, flags, offset, address, physical, size, memory, align))))
    loads = [row for row in programs if row['type'] == 1 and row['filesz'] > 0]

    def mapped(address, size):
        rows = [row for row in loads if address >= row['vaddr'] and address - row['vaddr'] <= row['filesz'] and
                size <= row['filesz'] - (address - row['vaddr'])]
        require(len(rows) == 1 and size > 0, 'ELF VA range not uniquely backed by PT_LOAD')
        return span(data, rows[0]['offset'] + address - rows[0]['vaddr'], size)

    entry = header['entry'] & ~1 if arch == 'armv7a' else header['entry']
    require(len([row for row in loads if row['flags'] & 1 and row['vaddr'] <= entry < row['vaddr'] + row['filesz']]) == 1,
            'ELF entry point is not in actual executable file bytes')
    interpreters = [span(data, row['offset'], row['filesz']) for row in programs if row['type'] == 3]
    require(len(interpreters) == 1 and interpreters[0].endswith(b'\0') and b'\0' not in interpreters[0][:-1],
            'one real NUL-terminated ELF interpreter required')
    interpreter = interpreters[0][:-1].decode('ascii')
    require(interpreter == '/lib/ld-musl-' + loader + '.so.1', 'wrong actual guest musl interpreter')
    dynamic = [row for row in programs if row['type'] == 2]
    dfmt = '<qQ' if cls == 2 else '<iI'
    dsize = struct.calcsize(dfmt)
    require(len(dynamic) == 1 and dynamic[0]['filesz'] > 0 and dynamic[0]['filesz'] % dsize == 0,
            'one real ELF dynamic segment required')
    row = dynamic[0]
    raw = span(data, row['offset'], row['filesz'])
    require(raw == mapped(row['vaddr'], row['filesz']), 'ELF dynamic segment differs from loaded bytes')
    tags = []
    for offset in range(0, len(raw), dsize):
        tag, value = struct.unpack_from(dfmt, raw, offset)
        tags.append([tag, value])
        if tag == 0:
            break
    require(tags[-1][0] == 0 and not any(tag in (15, 22, 29) for tag, _ in tags),
            'unterminated ELF dynamic tags or unexpected RPATH/RUNPATH/TEXTREL')
    tables = [value for tag, value in tags if tag == 5]
    sizes = [value for tag, value in tags if tag == 10]
    require(len(tables) == len(sizes) == 1, 'one actual dynamic string table required')
    strings = mapped(tables[0], sizes[0])
    needed = []
    for tag, value in tags:
        if tag != 1:
            continue
        require(value < len(strings) and strings.find(b'\0', value) >= 0, 'ELF DT_NEEDED outside dynamic strings')
        needed.append(strings[value:strings.index(b'\0', value)].decode('ascii'))
    require(needed == ['libc.so'], 'clock CLI must use only the actual C libc runtime')
    return {'ELF_header': header, 'program_headers': programs, 'interpreter': interpreter,
            'DT_NEEDED': needed, 'dynamic_entries': tags}


def readelf_matches(text, metadata, arch):
    require('ELF Header:' in text and 'Program Headers:' in text and 'Dynamic section' in text,
            'actual llvm-readelf complete header/program/dynamic output required')
    cls = re.findall(r'^\s*Class:\s*(ELF32|ELF64)\s*$', text, re.M)
    require(cls == ['ELF64' if ARCHES[arch][1] == 2 else 'ELF32'], 'llvm-readelf class differs from bytes')
    names = {'arm64': 'AArch64', 'armv7a': 'ARM', 'x86_64': 'Advanced Micro Devices X86-64'}
    machine = re.findall(r'^\s*Machine:\s*([^\n]+?)\s*$', text, re.M)
    require(machine == [names[arch]], 'llvm-readelf machine differs from bytes')
    require(re.findall(r'\[Requesting program interpreter: ([^\]\n]+)\]', text) == [metadata['interpreter']],
            'llvm-readelf interpreter differs from bytes')
    require(re.findall(r'\(NEEDED\)[^\n]*\[([^\]\n]+)\]', text) == metadata['DT_NEEDED'],
            'llvm-readelf NEEDED differs from bytes')


def compiler_logs(rows, source, directory, sdk):
    logs = {row['label']: checked(row['log']).read_text() for row in rows}
    require(all('clang version' in logs[name].lower() for name in ('compile', 'link')),
            'real verbose clang compile/link logs missing')
    require('-cc1' in logs['compile'] and str(source) in logs['compile'] and str(sdk / 'sysroot') in logs['compile'],
            'actual cc1 source/sysroot trace missing')
    require(str(sdk / 'llvm/bin/ld.lld') in logs['link'] and str(directory / 'watchdog_clock_probe.o') in logs['link'] and
            str(directory / 'watchdog_clock_probe') in logs['link'], 'actual LLVM link object/output trace missing')


def make_words(text):
    result, current = [], []
    escape = False
    for char in text:
        if escape:
            current.append(char); escape = False
        elif char == '\\':
            escape = True
        elif char.isspace():
            if current:
                result.append(''.join(current)); current = []
        else:
            current.append(char)
    require(not escape, 'unfinished make dependency escape')
    if current:
        result.append(''.join(current))
    return result


def dependencies(text, target):
    text = text.replace('\\\r\n', '').replace('\\\n', '')
    require(text.count(':') == 1 and '$' not in text, 'unsupported or ambiguous actual dependency file')
    left, right = text.split(':', 1)
    require(make_words(left) == [str(target)], 'dependency target differs from actual object')
    paths = make_words(right)
    require(paths and len(set(paths)) == len(paths), 'empty or repeated actual dependencies')
    return [os.path.abspath(path) for path in paths]


def commands(sdk, source, directory, arch):
    triple, _, _, _, flags = ARCHES[arch]
    common = [str(sdk / 'llvm/bin/clang'), '--target=' + triple, '--sysroot=' + str(sdk / 'sysroot'), *flags]
    obj = directory / 'watchdog_clock_probe.o'
    binary = directory / 'watchdog_clock_probe'
    return {
        'compile': [*common, '-std=c11', '-O2', '-g', '-Wall', '-Wextra', '-Werror', '-fPIE',
                    '-MD', '-MF', str(directory / 'dependencies.d'), '-MT', str(obj), '-c', str(source), '-o', str(obj), '-v'],
        'link': [*common, '-fuse-ld=lld', '-pie', '-Wl,-z,relro,-z,now', '-Wl,--no-undefined', str(obj), '-o', str(binary), '-v'],
        'readelf': [str(sdk / 'llvm/bin/llvm-readelf'), '-h', '-l', '-d', '-W', str(binary)],
    }


def run_command(argv, directory, label):
    log = directory / (label + '.log')
    started = time.time_ns()
    timed_out = False
    code = 127
    with log.open('xb') as stream:
        try:
            proc = subprocess.Popen(argv, cwd=directory, stdout=stream, stderr=subprocess.STDOUT,
                                    env={**os.environ, 'LC_ALL': 'C', 'LC_CTYPE': 'C', 'LANG': 'C'}, start_new_session=True)
            try:
                code = proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                code = 124
        except OSError as error:
            stream.write((str(error) + '\n').encode())
    return {'label': label, 'argv': argv, 'cwd': str(directory), 'exit_code': code, 'timed_out': timed_out,
            'started_ns': started, 'finished_ns': time.time_ns(), 'log': artifact(log)}


def sdk_inputs(sdk, source):
    return {key: input_record(path) for key, path in {
        'source': source, 'compiler': sdk / 'llvm/bin/clang', 'readelf': sdk / 'llvm/bin/llvm-readelf',
        'linker': sdk / 'llvm/bin/ld.lld',
        'native_metadata': sdk / 'oh-uni-package.json', 'toolchain': sdk / 'build/cmake/ohos.toolchain.cmake',
        'builder': BUILDER}.items()}


def build(sdk, source, output):
    sdk, source, output = (Path(path).absolute() for path in (sdk, source, output))
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'status': 'fail', 'scope': SCOPE, 'sdk': str(sdk),
              'source': str(source), 'output': str(output), 'architectures': {}, 'errors': [],
              'runtime_validated': False, 'first_artifact_behavior_gate_passed': False}
    before = None
    try:
        require(os.statvfs(sdk).f_flag & os.ST_RDONLY, 'actual SDK input mount must be read-only')
        report['SDK_filesystem_readonly'] = True
        report['canonical_sdk_root'] = str(sdk.resolve())
        before = sdk_inputs(sdk, source)
        report['inputs_before'] = before
        require(sha(source) == sha(CURRENT_SOURCE), 'provided source differs from current watchdog_clock_probe.c')
        report['current_source_before'] = input_record(CURRENT_SOURCE)
        metadata = native_metadata(load(sdk / 'oh-uni-package.json'))
        report['native_metadata'] = metadata
        inputs = output / 'inputs'; inputs.mkdir()
        for key in ('native_metadata', 'toolchain'):
            original = Path(before[key]['path'])
            frozen = inputs / original.name
            frozen.write_bytes(original.read_bytes())
            report['frozen_' + key] = artifact(frozen)
        require('arm-linux-ohos' in (sdk / 'build/cmake/ohos.toolchain.cmake').read_text() and
                re.search(r'-march=armv7-?a\b', (sdk / 'build/cmake/ohos.toolchain.cmake').read_text()),
                'actual SDK ARMv7 target/march toolchain contract missing')
    except (OSError, ValueError, KeyError) as error:
        report['errors'].append('preflight: ' + str(error))
    for arch in ARCHES:
        directory = output / arch; directory.mkdir()
        row = {'status': 'fail', 'commands': [], 'errors': []}
        report['architectures'][arch] = row
        if report['errors']:
            row['errors'].append('not run: global input preflight failed')
            continue
        try:
            plan = commands(sdk, source, directory, arch)
            for label in ('compile', 'link', 'readelf'):
                command = run_command(plan[label], directory, label)
                row['commands'].append(command)
                require(command['exit_code'] == 0 and not command['timed_out'], arch + ' ' + label + ' failed')
                if label == 'compile':
                    dep = directory / 'dependencies.d'
                    paths = dependencies(dep.read_text(), directory / 'watchdog_clock_probe.o')
                    require(str(source) in paths, 'compiled source absent from actual dependency file')
                    headers = [input_record(path) for path in paths if path != str(source)]
                    require(headers and {'time.h', 'stdio.h', 'stdint.h', 'inttypes.h'} <=
                            {Path(header['path']).name for header in headers}, 'real required SDK C headers missing')
                    require(all(Path(header['canonical_path']).is_relative_to(sdk.resolve()) for header in headers),
                            'compiler consumed a non-SDK header')
                    row['dependency_file'] = artifact(dep)
                    row['SDK_headers'] = headers
                    row['object'] = artifact(directory / 'watchdog_clock_probe.o')
                elif label == 'link':
                    row['binary'] = artifact(directory / 'watchdog_clock_probe')
                    row['ELF'] = elf_metadata(Path(row['binary']['path']).read_bytes(), arch)
                else:
                    readelf_matches(Path(command['log']['path']).read_text(), row['ELF'], arch)
            require(all(input_record(header['path']) == header for header in row['SDK_headers']),
                    'SDK header changed during actual build')
            compiler_logs(row['commands'], source, directory, sdk)
            row['status'] = 'pass_build_ONLY'
        except (OSError, ValueError, KeyError, UnicodeError, struct.error) as error:
            row['errors'].append(str(error))
    if before is not None:
        try:
            report['inputs_after'] = sdk_inputs(sdk, source)
            report['current_source_after'] = input_record(CURRENT_SOURCE)
            require(report['inputs_after'] == before and report['current_source_after'] == report['current_source_before'],
                    'source/compiler/readelf/SDK metadata/toolchain/builder changed during batch')
        except (OSError, ValueError, KeyError) as error:
            report['errors'].append('after-input check: ' + str(error))
    if not report['errors'] and all(row['status'] == 'pass_build_ONLY' for row in report['architectures'].values()):
        report['status'] = 'pass_build_ONLY'
    receipt = output / 'build.json'
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    return report


def verify_build(binary, receipt, arch):
    """Recompute local evidence; original Linux SDK/header SHA records stay raw."""
    require(arch in ARCHES, 'actual supported architecture required')
    receipt = Path(receipt).absolute()
    report = load(receipt)
    require(report.get('schema_version') == 1 and report.get('status') == 'pass_build_ONLY' and
            report.get('scope') == SCOPE and report.get('errors') == [] and
            report.get('SDK_filesystem_readonly') is True and report.get('runtime_validated') is False and
            report.get('first_artifact_behavior_gate_passed') is False, 'actual successful SDK-only batch receipt required')
    require(set(report['architectures']) == set(ARCHES), 'complete three-ABI batch required')
    require(report['inputs_before'] == report['inputs_after'] and
            report['current_source_before'] == report['current_source_after'], 'build input before/after records differ')
    before = report['inputs_before']
    original = checked(before['source'])
    require(sha(original) == sha(CURRENT_SOURCE) == before['source']['sha256'] and
            report['current_source_before']['sha256'] == sha(CURRENT_SOURCE), 'original/current C source differs')
    require(sha(BUILDER) == before['builder']['sha256'], 'receipt came from a different builder implementation')
    sdk, source = Path(report['sdk']), Path(report['source'])
    require(str(original) == str(source) and Path(report['output']) == receipt.parent and sdk.is_absolute(),
            'original source/output/SDK path differs')
    canonical_sdk = Path(report['canonical_sdk_root'])
    require(canonical_sdk.is_absolute(), 'original canonical SDK root missing')
    require(Path(report['frozen_native_metadata']['path']) == receipt.parent / 'inputs/oh-uni-package.json' and
            Path(report['frozen_toolchain']['path']) == receipt.parent / 'inputs/ohos.toolchain.cmake',
            'retained SDK metadata/toolchain must be this batch local copies')
    require(native_metadata(load(checked(report['frozen_native_metadata']))) == report['native_metadata'] and
            report['frozen_native_metadata']['sha256'] == before['native_metadata']['sha256'] and
            report['frozen_toolchain']['sha256'] == before['toolchain']['sha256'], 'retained actual SDK metadata/toolchain differs')
    checked(report['frozen_toolchain'])
    for name, expected in (('compiler', sdk / 'llvm/bin/clang'), ('readelf', sdk / 'llvm/bin/llvm-readelf'),
                           ('linker', sdk / 'llvm/bin/ld.lld'),
                           ('native_metadata', sdk / 'oh-uni-package.json'),
                           ('toolchain', sdk / 'build/cmake/ohos.toolchain.cmake')):
        require(before[name]['path'] == str(expected) and re.fullmatch(r'[a-f0-9]{64}', before[name]['sha256']) and
                type(before[name]['size']) is int and before[name]['size'] > 0 and
                Path(before[name]['canonical_path']).is_absolute(), 'original actual Linux SDK input record malformed')
    for abi, row in report['architectures'].items():
        require(row.get('status') == 'pass_build_ONLY' and row.get('errors') == [], 'incomplete ABI build')
        directory = receipt.parent / abi
        plan = commands(sdk, source, directory, abi)
        require([command['label'] for command in row['commands']] == ['compile', 'link', 'readelf'],
                'actual compile/link/readelf sequence missing or duplicated')
        for command in row['commands']:
            require(command['argv'] == plan[command['label']] and command['cwd'] == str(directory) and
                    command['exit_code'] == 0 and command['timed_out'] is False and
                    type(command['started_ns']) is int and type(command['finished_ns']) is int and
                    0 < command['started_ns'] < command['finished_ns'], 'actual successful tool invocation differs')
            require(Path(command['log']['path']) == directory / (command['label'] + '.log'),
                    'actual tool log belongs to another output path')
            checked(command['log'])
        compiler_logs(row['commands'], source, directory, sdk)
        obj = checked(row['object']); actual_binary = checked(row['binary'])
        require(obj == directory / 'watchdog_clock_probe.o' and actual_binary == directory / 'watchdog_clock_probe',
                'original object/binary output differs')
        parsed = elf_metadata(actual_binary.read_bytes(), abi)
        require(row['ELF'] == parsed, 'recorded ELF metadata differs from real local file')
        readelf_matches(checked(row['commands'][2]['log']).read_text(), parsed, abi)
        dep = checked(row['dependency_file'])
        require(dep == directory / 'dependencies.d', 'actual dependency file belongs to another output path')
        paths = dependencies(dep.read_text(), obj)
        headers = row['SDK_headers']
        require(str(source) in paths and [path for path in paths if path != str(source)] == [h['path'] for h in headers] and
                {'time.h', 'stdio.h', 'stdint.h', 'inttypes.h'} <= {Path(h['path']).name for h in headers},
                'original real dependency/header list differs')
        require(all(re.fullmatch(r'[a-f0-9]{64}', h['sha256']) and type(h['size']) is int and h['size'] > 0 and
                    Path(h['canonical_path']).is_relative_to(canonical_sdk) for h in headers), 'original actual SDK header record malformed')
    selected = checked(report['architectures'][arch]['binary'])
    require(Path(binary).absolute() == selected, 'requested binary is not the actual selected ABI output')
    return {'binary': artifact(selected), 'receipt': artifact(receipt), 'source_sha256': sha(CURRENT_SOURCE), 'arch': arch,
            'scope': SCOPE, 'verified_build_arches': list(ARCHES), 'runtime_validated': False,
            'SDK_tools_and_headers_re_read_on_host': False,
            'original_Linux_SDK_inputs_SHA_bound_to_receipt': True,
            'first_artifact_behavior_gate_passed': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True, help='actual SDK39 native directory')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new, nonexistent directory')
    args = parser.parse_args(argv)
    result = build(args.sdk, args.source, args.output)
    print(json.dumps({'status': result['status'], 'receipt': str(args.output.absolute() / 'build.json')}))
    return 0 if result['status'] == 'pass_build_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
