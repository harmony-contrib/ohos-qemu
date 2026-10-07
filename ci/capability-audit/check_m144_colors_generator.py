#!/usr/bin/env python3
"""Verify the actual Linux colors generator; not patched GN/engine/guest acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess


REVISION = 'a8168622b056f25c2e68d5f12fe2759bad2d9a44'
PATCH = Path(__file__).resolve().parents[2] / (
    'patches/common/web/arkweb/m144_core_build/'
    '0005-build-colors-generator-only-with-host-toolchain-on-ohos.patch')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_host_elf(header):
    if (len(header) < 64 or header[:7] != b'\x7fELF\x02\x01\x01' or
            struct.unpack_from('<HH', header, 16) not in ((2, 62), (3, 62))):
        raise ValueError('colors generator must be an actual Linux x86_64 executable, not an OHOS target')


def check_graph(target, host):
    label = 'chrome/browser/new_tab_page/chrome_colors/'
    if ('subninja obj/' + label + 'generate_colors_info.ninja' in target or
            'subninja clang_x64/obj/' + label + 'generate_colors_info.ninja' not in host):
        raise ValueError('fresh OHOS graph must declare the real generator only in its host toolchain')
    action = ('python3 ../../build/gn_run_binary.py clang_x64/generate_colors_info '
              'gen/' + label + 'generated_colors_info.h')
    if action not in target:
        raise ValueError('fresh OHOS graph lost the actual host generator action')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--product', choices=('rk3568', 'rk3568_64', 'x86_64'), default='rk3568_64')
    parser.add_argument('--require-host-only-graph', action='store_true')
    args = parser.parse_args()
    source = args.source_root.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise ValueError('actual source and native output must remain read-only')
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('colors preflight requires the pinned release Chromium commit')
    work = args.work.resolve()
    if work.parent != Path('/tmp').resolve() or not work.name.startswith('m144-colors-'):
        raise ValueError('exclusive /tmp/m144-colors-* work required')
    work.mkdir()
    tool = source / 'out' / args.product / 'clang_x64/generate_colors_info'
    with tool.open('rb') as stream:
        check_host_elf(stream.read(64))
    original = source / 'out' / args.product / 'gen/chrome/browser/new_tab_page/chrome_colors/generated_colors_info.h'
    before = {str(path): digest(path) for path in (tool, original, PATCH)}
    graph = []
    if args.require_host_only_graph:
        graph = [source / 'out' / args.product / 'toolchain.ninja',
                 source / 'out' / args.product / 'clang_x64/toolchain.ninja']
        before.update({str(path): digest(path) for path in graph})
        check_graph(graph[0].read_text(), graph[1].read_text())
    check = ['git', '-C', str(source.parent), 'apply', '--check', str(PATCH)]
    checked = subprocess.run(check, capture_output=True, text=True)
    state = 'unapplied_candidate'
    if checked.returncode:
        state = 'already_patched'
        check.insert(-1, '--reverse')
        checked = subprocess.run(check, capture_output=True, text=True)
    (work / 'patch-check.log').write_text(checked.stdout + checked.stderr)
    generated = work / 'generated_colors_info.h'
    argv = [str(tool), str(generated)]
    log = work / 'generator.log'
    with log.open('x') as stream:
        executed = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT)
    passed = (checked.returncode == 0 and executed.returncode == 0 and generated.is_file() and
              digest(generated) == digest(original) and
              all(digest(Path(path)) == value for path, value in before.items()))
    evidence = {'scope': 'actual_existing_Linux_host_tool_execution_and_candidate_patch_preflight_only',
                'source_revision': REVISION, 'source_readonly': True, 'patch_state': state,
                'input_sha256': before, 'patch_check_argv': check, 'patch_check_exit_code': checked.returncode,
                'argv': argv, 'exit_code': executed.returncode, 'log_sha256': digest(log),
                'generated_header_sha256': digest(generated) if generated.is_file() else None,
                'passed': passed, 'patched_full_GN_validation_passed': False,
                'current_host_only_GN_graph_check_passed': bool(graph) and passed,
                'new_engine_or_HAP_acceptance': False, 'first_artifact_behavior_gate_passed': False}
    (work / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    if not passed:
        raise RuntimeError('actual host generator/candidate preflight failed; preserve its evidence')
    print('actual Linux host colors generator and fixed patch preflight passed; not engine/guest acceptance')


if __name__ == '__main__':
    main()
