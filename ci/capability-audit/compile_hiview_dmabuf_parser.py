#!/usr/bin/env python3
"""Compile the real patched Hiview parser for three SDK ABIs; not a guest gate."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess

from build_serial_hap_probe import ARCHITECTURES
from run_root_probe import digest
from test_dmabuf_parser import CASES, COMPONENT, RELATIVE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-source', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=False)
    source = work / 'source' / RELATIVE
    source.parent.mkdir(parents=True)
    shutil.copy2(args.original_source, source)
    report = dict(status='fail', scope='real_parser_ASan_UBSan_and_three_ABI_objects_NOT_guest_accounting',
        original_source_sha256=digest(args.original_source), sdk=str(args.sdk.resolve()),
        runner_sha256=digest(Path(__file__)),
        boundary_cases_sha256=digest(Path(__file__).with_name('test_dmabuf_parser.py')),
        patch_sha256={p.name: digest(p) for p in COMPONENT.glob('*.patch')},
        first_artifact_behavior_gate_passed=False, commands=[])

    def run(argv, label):
        log = work / (label + '.log')
        with log.open('x') as stream:
            result = subprocess.run(list(map(str, argv)), stdout=stream, stderr=subprocess.STDOUT, timeout=180)
        report['commands'].append(dict(argv=list(map(str, argv)), exit_code=result.returncode,
                                       log=str(log), sha256=digest(log)))
        if result.returncode:
            raise ValueError('real parser validation failed: ' + label)

    try:
        for i in range(2):
            run(['bash', COMPONENT / 'apply.sh', '--source-root', work / 'source'], 'apply-' + str(i))
        text = source.read_text()
        structure = text[text.index('struct DmaInfo {'):text.index('int32_t MemoryTrackerGetGLByPid')]
        function = text[text.index('void CreateDmaInfo('):text.index('int32_t GetGraphByPid(')]
        test = work / 'actual-parser-test.cpp'
        test.write_text('#include <cassert>\n#include <cstdint>\n#include <map>\n#include <string>\n'
                        '#include <charconv>\n#include <sstream>\n' + structure + function + CASES)
        binary = work / 'actual-parser-test'
        run(['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
             '-fno-sanitize-recover=all', test, '-o', binary], 'host-compile')
        run([binary], 'host-boundary-runtime')
        native = args.sdk.resolve() / 'native'
        report['objects'] = {}
        for arch, (triple, _) in ARCHITECTURES.items():
            output = work / (arch + '.o')
            flags = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon'] if arch == 'armv7a' else []
            run([native / 'llvm/bin/clang++', '--target=' + triple, '--sysroot=' + str(native / 'sysroot'),
                 *flags, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-c', test, '-o', output], arch)
            header = output.read_bytes()[:20]
            elf_class, machine = {'arm64': (2, 183), 'armv7a': (1, 40), 'x86_64': (2, 62)}[arch]
            if (header[:6] != b'\x7fELF' + bytes((elf_class, 1)) or
                    struct.unpack_from('<HH', header, 16) != (1, machine)):
                raise ValueError('actual relocatable object ABI mismatch: ' + arch)
            report['objects'][arch] = digest(output)
        report.update(status='pass', patched_source_sha256=digest(source), extracted_test_sha256=digest(test))
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    (work / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], error=report.get('error'))))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
