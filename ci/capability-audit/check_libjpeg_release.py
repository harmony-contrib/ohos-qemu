#!/usr/bin/env python3
"""Exercise fixed 3.1.0 patches and upstream native tests in an owned copy.

Production source must be mounted read-only. This is dependency verification,
not a packaged Camera/public Image API or other QEMU runtime acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/third_party/libjpeg-turbo/release_3_1_0'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, cwd, log):
    started = time.monotonic()
    with log.open('w') as output:
        output.write(json.dumps({'argv': list(map(str, argv)), 'cwd': str(cwd)}) + '\n')
        output.flush()
        result = subprocess.run(list(map(str, argv)), cwd=cwd, stdout=output, stderr=subprocess.STDOUT)
    return {'argv': list(map(str, argv)), 'cwd': str(cwd), 'returncode': result.returncode,
            'elapsed_seconds': round(time.monotonic() - started, 3), 'log': str(log),
            'log_sha256': digest(log)}


def checked(argv, cwd, log):
    result = command(argv, cwd, log)
    if result['returncode']:
        raise RuntimeError(json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve() / 'third_party/libjpeg-turbo'
    if not os.statvfs(source).f_flag & os.ST_RDONLY:
        raise SystemExit('production source must be read-only')
    work = args.work.absolute()
    if work.is_symlink() or not str(work).startswith('/tmp/libjpeg-release-'):
        raise SystemExit('exclusive /tmp/libjpeg-release-* work directory required')
    work.mkdir(exist_ok=True)
    if any(work.iterdir()):
        raise SystemExit('work directory must be empty; preserve prior evidence')
    staged = work / 'source'
    staged.mkdir()
    archive = subprocess.Popen(['git', '-C', str(source), 'archive', '--prefix=third_party/libjpeg-turbo/',
                                'HEAD'], stdout=subprocess.PIPE)
    subprocess.run(['tar', '-xf', '-', '-C', str(staged)], stdin=archive.stdout, check=True)
    archive.stdout.close()
    if archive.wait():
        raise RuntimeError('actual pinned git archive failed')
    copied = staged / 'third_party/libjpeg-turbo'
    gitdir = subprocess.check_output(['git', '-C', str(source), 'rev-parse', '--absolute-git-dir'], text=True).strip()
    # Read-only object metadata permits exact HEAD checks without copying or
    # mutating the production repository. All patches target the owned files.
    (copied / '.git').write_text('gitdir: ' + gitdir + '\n')
    evidence = {'scope': 'isolated actual libjpeg dependency, not QEMU runtime',
                'source_root': str(source), 'source_readonly': True, 'work': str(work),
                'revision': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
                'commands': [], 'guest_acceptance': False, 'first_package_gate_passed': False,
                'dependency_checks_passed': False, 'validation_status': 'running'}
    for iteration in (1, 2):
        evidence['commands'].append(checked(['bash', COMPONENT / 'apply.sh', '--source-root', staged],
                                            work, work / f'apply-{iteration}.log'))
    generated = work / 'generated'
    generated.mkdir()
    for iteration in (1, 2):
        evidence['commands'].append(checked(['python3', copied / 'install.py', '--source-dir', copied,
                                            '--gen-dir', generated], work, work / f'install-{iteration}.log'))
    evidence['actual_installer_incremental_replay_passed'] = True
    tree = generated / 'libjpeg-turbo-3.1.0'
    if list(tree.rglob('*.rej')) or any('FAILED' in (work / f'install-{iteration}.log').read_text()
                                       for iteration in (1, 2)):
        raise RuntimeError('patch rejection despite successful installer')
    with tarfile.open(copied / 'libjpeg-turbo-3.1.0.tar.gz') as original:
        for relative in ('java/turbojpeg-jni.c', 'java/TJUnitTest.java', 'src/tjunittest.c'):
            expected = original.extractfile('libjpeg-turbo-3.1.0/' + relative).read()
            if (tree / relative).read_bytes() != expected:
                raise RuntimeError('3.1.0 ABI/overflow tests were regressed: ' + relative)
    evidence['upstream_jni_java_and_native_overflow_tests_unchanged'] = True
    evidence['headers'] = {name: digest(copied / name) for name in ('jmorecfg.h', 'jerror.h', 'jpeglib.h')}
    # Actual C header compilation, both standard public typedef and the
    # narrowly scoped LiteOS platform-supplied typedef. Not LiteOS acceptance.
    for liteos in (False, True):
        fixture = work / ('header-liteos.c' if liteos else 'header-standard.c')
        fixture.write_text(('typedef int INT32;\n#define LITEOS_M_TYPE_DEFINE 1\n' if liteos else '') +
                           '#include "jmorecfg.h"\nINT32 value;\nint main(void) { return (int)value; }\n')
        evidence['commands'].append(checked(['cc', '-Wall', '-Werror', '-fsyntax-only', '-I', tree / 'src', fixture],
                                            work, work / (fixture.stem + '.log')))
    # Exercise a REAL failing patch subprocess before the long native build.
    # Preserve both previously generated output and all published headers.
    before = {name: (copied / name).read_bytes() for name in evidence['headers']}
    generated_before = {name: digest(tree / 'src' / name)
                        for name in ('jdhuff_opt.c', 'jconfig.h', 'jconfigint.h')}
    (copied / 'liteos_adapting.patch').write_text('--- a/src/missing-file.h\n+++ b/src/missing-file.h\n'
                                                '@@ -1 +1 @@\n-old\n+new\n')
    failure = command(['python3', copied / 'install.py', '--source-dir', copied, '--gen-dir', generated],
                      work, work / 'reject-patch.log')
    evidence['commands'].append(failure)
    if (failure['returncode'] == 0 or any((copied / name).read_bytes() != data for name, data in before.items())
            or any(digest(tree / 'src' / name) != value for name, value in generated_before.items())):
        raise RuntimeError('installer swallowed patch failure or changed previous generated tree/headers')
    evidence['real_rejected_patch_failed_before_publication'] = True
    evidence['validation_status'] = 'installer_passed_full_native_test_pending'
    (work / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    # CMake generates its own platform/compiler configuration. Keeping the
    # OHOS GN-injected configs here would silently select different SIMD and
    # arithmetic options. Retain them as evidence, not as host build inputs.
    configurations = work / 'retained-ohos-gn-config'
    configurations.mkdir()
    evidence['retained_ohos_configuration'] = {}
    for name in ('jconfig.h', 'jconfigint.h'):
        injected = tree / 'src' / name
        evidence['retained_ohos_configuration'][name] = digest(injected)
        injected.rename(configurations / name)
    evidence['host_build_configuration'] = 'upstream CMake host GCC, SIMD disabled; not an OHOS GN link'
    build = work / 'native-build'
    try:
        evidence['commands'].append(checked(['cmake', '-S', tree, '-B', build, '-DWITH_SIMD=OFF',
                                            '-DENABLE_SHARED=ON', '-DENABLE_STATIC=OFF', '-DWITH_JAVA=ON'],
                                            work, work / 'cmake.log'))
        evidence['commands'].append(checked(['cmake', '--build', build, '--parallel', '4'], work, work / 'build.log'))
        evidence['commands'].append(checked(['ctest', '--test-dir', build, '--output-on-failure', '--parallel', '4'],
                                            work, work / 'ctest.log'))
    except RuntimeError as failure:
        evidence['commands'].append(json.loads(str(failure)))
        evidence['validation_status'] = 'failed_full_native_build_or_test'
        (work / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
        raise
    evidence['dependency_checks_passed'] = True
    evidence['validation_status'] = 'passed'
    (work / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
