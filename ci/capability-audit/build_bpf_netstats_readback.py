#!/usr/bin/env python3
"""Compile the read-only fixed-release NetManager map diagnostic for three ABIs."""
import argparse
import json
from pathlib import Path
import subprocess

from build_wpa_frequency_readback import TARGETS, sha

SOURCE = Path(__file__).with_name('probes') / 'bpf_netstats_readback.c'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk, output = args.sdk.resolve(), args.output.resolve()
    metadata = sdk / 'native/oh-uni-package.json'
    version = json.loads(metadata.read_text())
    if version.get('apiVersion') != '26' or version.get('releaseType') != 'Release':
        raise ValueError('actual API26 Release SDK required')
    output.mkdir(exist_ok=False)
    compiler = sdk / 'native/llvm/bin/clang'
    header = sdk / 'native/sysroot/usr/include/linux/bpf.h'
    paths = {'source': SOURCE, 'compiler': compiler, 'sdk_metadata': metadata,
             'bpf_header': header, 'builder': Path(__file__),
             'targets_helper': Path(__file__).with_name('build_wpa_frequency_readback.py')}
    inputs = {name: sha(path) for name, path in paths.items()}
    rows = []
    for arch, (triple, flags) in TARGETS.items():
        binary = output / ('bpf-netstats-readback-' + arch)
        argv = [str(compiler), '--target=' + triple, *flags,
                '--sysroot=' + str(sdk / 'native/sysroot'), '-std=c11',
                '-Wall', '-Wextra', '-Werror', '-O2', str(SOURCE), '-o', str(binary)]
        log = output / (arch + '-compile.log')
        with log.open('x') as stream:
            subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, check=True)
        rows.append(dict(arch=arch, triple=triple, argv=argv, binary=str(binary),
                         binary_sha256=sha(binary), log_sha256=sha(log)))
    if inputs != {name: sha(path) for name, path in paths.items()}:
        raise ValueError('read-only probe build inputs changed')
    report = dict(status='pass', scope='read_only_NetManager_map_caller_BUILD_NOT_traffic_or_API_acceptance',
                  inputs_sha256=inputs, sdk=version, outputs=rows,
                  first_artifact_behavior_gate_passed=False)
    (output / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], architectures=len(rows))))


if __name__ == '__main__':
    main()
