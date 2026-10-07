#!/usr/bin/env python3
"""Verify actual fixed jsoncpp generation with production source read-only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/third_party/jsoncpp/generated_source'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve() / 'third_party/jsoncpp'
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise SystemExit('production source must be read-only')
    work = args.work.absolute()
    if work.is_symlink() or not str(work).startswith('/tmp/jsoncpp-generated-'):
        raise SystemExit('exclusive /tmp/jsoncpp-generated-* work required')
    work.mkdir(exist_ok=True)
    if any(work.iterdir()):
        raise SystemExit('work must be empty; preserve prior evidence')
    evidence = {'scope': 'actual readonly dependency generation and host upstream tests, not QEMU runtime',
                'source': str(source), 'source_readonly': True, 'commands': [], 'passed': False,
                'guest_acceptance': False, 'first_package_gate_passed': False}
    def run(argv, cwd, filename, required=True):
        log = work / filename
        start = time.monotonic()
        with log.open('w') as output:
            output.write(json.dumps({'argv': list(map(str, argv)), 'cwd': str(cwd)}) + '\n')
            output.flush()
            result = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=output, stderr=subprocess.STDOUT)
        record = {'argv': list(map(str, argv)), 'cwd': str(cwd), 'returncode': result.returncode,
                  'elapsed_seconds': round(time.monotonic() - start, 3), 'log': str(log), 'log_sha256': digest(log)}
        evidence['commands'].append(record)
        (work / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        if required and result.returncode:
            raise RuntimeError(json.dumps(record))
        return record
    staged = work / 'source'
    staged.mkdir()
    archive = subprocess.Popen(['git', '-C', str(source), 'archive', '--prefix=third_party/jsoncpp/', 'HEAD'],
                               stdout=subprocess.PIPE)
    subprocess.run(['tar', '-xf', '-', '-C', str(staged)], stdin=archive.stdout, check=True)
    archive.stdout.close()
    if archive.wait():
        raise RuntimeError('actual pinned git archive failed')
    copied = staged / 'third_party/jsoncpp'
    gitdir = subprocess.check_output(['git', '-C', str(source), 'rev-parse', '--absolute-git-dir'], text=True).strip()
    (copied / '.git').write_text('gitdir: ' + gitdir + '\n')
    evidence['revision'] = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    evidence['source_archive_sha256'] = digest(source / 'jsoncpp-1.9.6.tar.gz')
    evidence['production_installer_sha256'] = digest(source / 'install.py')
    evidence['component_inputs'] = {path.name: digest(path) for path in sorted(COMPONENT.iterdir())
                                    if path.is_file() and path.suffix in ('.py', '.sh', '.patch')}
    for iteration in (1, 2):
        run(['bash', COMPONENT / 'apply.sh', '--source-root', staged], work, f'apply-{iteration}.log')
    generated = work / 'generated'
    # Reproduce the fresh GN source-output directory creation, not an
    # artificially nonexistent destination that misses the real failure.
    skeleton = generated / 'jsoncpp-1.9.6/src/lib_json'
    skeleton.mkdir(parents=True)
    evidence['gn_empty_skeleton_before_generation'] = {
        'directories': sorted(str(path.relative_to(generated)) for path in generated.rglob('*') if path.is_dir()),
        'files': [str(path.relative_to(generated)) for path in generated.rglob('*') if path.is_file()]}
    sibling = generated / 'outside-component-sentinel'
    sibling.write_text('preserve unrelated generated output\n')
    sibling_sha = digest(sibling)
    for iteration in (1, 2):
        # Deliberately read the real production source, not the writable copy.
        run(['python3', copied / 'install.py', '--source-file', source, '--gen-dir', generated],
            work, f'install-{iteration}.log')
    tree = generated / 'jsoncpp-1.9.6'
    outputs = ('src/lib_json/json_reader.cpp', 'src/lib_json/json_value.cpp',
               'src/lib_json/json_writer.cpp', 'include/json/json.h')
    evidence['outputs'] = {name: digest(tree / name) for name in outputs}
    damaged = work / 'damaged-source'
    damaged.mkdir()
    (damaged / 'jsoncpp-1.9.6.tar.gz').write_bytes(b'damaged actual archive fixture')
    failure = run(['python3', copied / 'install.py', '--source-file', damaged, '--gen-dir', generated],
                  work, 'reject-archive.log', required=False)
    if failure['returncode'] == 0 or any(digest(tree / name) != value for name, value in evidence['outputs'].items()):
        raise RuntimeError('archive failure swallowed or previous generated output changed')
    evidence['actual_incremental_install_and_fail_closed_preservation_passed'] = True
    partial = work / 'partial-generated'
    protected = partial / 'jsoncpp-1.9.6/src/lib_json/json_reader.cpp'
    protected.parent.mkdir(parents=True)
    protected.write_text('preserve unknown partial generated output\n')
    protected_sha = digest(protected)
    rejected = run(['python3', copied / 'install.py', '--source-file', source, '--gen-dir', partial],
                   work, 'reject-partial-output.log', required=False)
    if rejected['returncode'] == 0 or digest(protected) != protected_sha or digest(sibling) != sibling_sha:
        raise RuntimeError('partial output accepted/modified or unrelated output overwritten')
    evidence['fresh_GN_empty_skeleton_and_partial_tree_boundaries_passed'] = True
    build = work / 'native-build'
    run(['cmake', '-S', tree, '-B', build, '-DJSONCPP_WITH_TESTS=ON', '-DBUILD_SHARED_LIBS=ON'], work, 'cmake.log')
    run(['cmake', '--build', build, '--parallel', '2'], work, 'build.log')
    run(['ctest', '--test-dir', build, '--output-on-failure'], work, 'ctest.log')
    if digest(source / 'install.py') != evidence['production_installer_sha256']:
        raise RuntimeError('production source installer changed')
    if digest(sibling) != sibling_sha:
        raise RuntimeError('generation overwrote a sibling output')
    evidence['passed'] = True
    (work / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
