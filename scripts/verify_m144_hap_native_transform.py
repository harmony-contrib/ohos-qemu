#!/usr/bin/env python3
"""Replay the unchanged official permission/SDK-strip pipeline, byte for byte.

NativeStrip is a normal Release HAP step, not arbitrary permission to accept
changed libraries. Keep the original five native outputs and independently
reproduce every final library with the pinned original tools in owned scratch.
This is build provenance, never guest behavior acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from verify_arkweb_core_image import REQUIRED_LIBRARIES, verify_hap

SCOPE = 'exact_official_kernelpermission_and_API26_NativeStrip_NOT_guest_acceptance'
SDK_STRIP_SHA256 = '78bee3733d321304ee24d068840878a4413cc4ac814c6beab5705da14e65a7af'
OFFICIAL_INPUTS = {
    'BUILD.gn': '902782d19b87f6ee5d14755b2a7b67714348088f0da359fe0daebcf48b0b0038',
    'add_kernel_permission.py': 'daad67a24c194a0f617a6d83e34308e63fc74a9e48154df44a0a4c187b2bcbbc',
    'encaps.json': '546b155169f64c90435df391c5809a7ea70a9166e5bac3913b72405603fc147e',
    'llvm-objcopy': '6fc53bec43e759291533d02d4c80a2cdd741b1f1251aefd71b3bd2b3ecfd5b39',
}
ARCHES = {'arm': 'armv7a', 'arm64': 'arm64', 'x86_64': 'x86_64'}
PRODUCTS = {'arm': 'rk3568', 'arm64': 'rk3568_64', 'x86_64': 'x86_64'}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def owned(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('unsafe native transform path')
    if root.is_symlink() or any(parent.is_symlink() for parent in (path, *path.parents)
                                if parent == root or parent.is_relative_to(root)):
        raise ValueError('aliased native transform input')
    if not path.is_file():
        raise ValueError('missing native transform input: ' + relative)
    return path


def file_record(path):
    return {'sha256': sha(path), 'size': path.stat().st_size}


def validate(root, native, observed, repository):
    root, repository = Path(root), Path(repository)
    report = json.loads(owned(root, 'hap-native-transform.json').read_text())
    if (type(report.get('schema_version')) is not int or report.get('schema_version') != 1
            or report.get('scope') != SCOPE or report.get('status') != 'pass'
            or report.get('failures') != []
            or report.get('first_artifact_behavior_gate_passed') is not False
            or report.get('verifier_sha256') != sha(repository / 'scripts/verify_m144_hap_native_transform.py')
            or report.get('sdk_strip_sha256') != SDK_STRIP_SHA256
            or report.get('official_inputs_sha256') != OFFICIAL_INPUTS
            or report.get('native_evidence_sha256') != sha(owned(root, 'native-build-evidence.json'))
            or report.get('signed_hap_sha256') != observed['hap_sha256']
            or set(report.get('libraries', {})) != REQUIRED_LIBRARIES):
        raise ValueError('incomplete or stale exact HAP native transformation evidence')
    for name, digest in OFFICIAL_INPUTS.items():
        if sha(owned(root, 'hap-transform-work/tools/' + name)) != digest:
            raise ValueError('official HAP transformation tool/input changed: ' + name)
    for name in REQUIRED_LIBRARIES:
        row = report['libraries'][name]
        original = file_record(owned(root, 'native-libraries/' + name))
        transformed = file_record(owned(root, 'hap-transform-work/stripped/' + name))
        built = native['artifacts'][name]
        member = observed['native_libraries']['libs/' + observed['abi'] + '/' + name]
        if (original != {'sha256': built['sha256'], 'size': built['size']}
                or row.get('native') != original or row.get('stripped') != transformed
                or transformed != {'sha256': member['sha256'], 'size': member['size']}
                or row.get('kernelpermission_applied') is not (name == 'libarkweb_engine.so')
                or type(row.get('strip_exit_code')) is not int or row.get('strip_exit_code') != 0):
            raise ValueError('HAP native bytes cannot be reproduced exactly: ' + name)
    kernel = report.get('kernelpermission_command', {})
    if type(kernel.get('exit_code')) is not int or kernel.get('exit_code') != 0:
        raise ValueError('official kernelpermission replay did not succeed')
    return report


def record(root, source, ohos, product, arch, signed_hap, unsigned_hap, repository):
    root, source, ohos, repository = map(Path, (root, source, ohos, repository))
    if product != PRODUCTS[arch]:
        raise ValueError('actual native product/architecture must match')
    report_path, work = root / 'hap-native-transform.json', root / 'hap-transform-work'
    if any(path.exists() or path.is_symlink() for path in (report_path, work)):
        raise ValueError('fresh native transform evidence/work directory required')
    native = json.loads(owned(root, 'native-build-evidence.json').read_text())
    if (type(native.get('exit_code')) is not int or native.get('exit_code') != 0
            or native.get('failures') != [] or set(native.get('artifacts', {})) != REQUIRED_LIBRARIES):
        raise ValueError('complete successful archived native build required')
    signed = verify_hap(Path(signed_hap), ARCHES[arch])
    unsigned = verify_hap(Path(unsigned_hap), ARCHES[arch])
    if unsigned['native_libraries'] != signed['native_libraries']:
        raise ValueError('code signing unexpectedly changed native HAP members')
    original_sdk = ohos / 'prebuilts/ohos-sdk/linux/26.0.0/native'
    if not os.statvfs(ohos).f_flag & os.ST_RDONLY:
        raise ValueError('original release SDK must be read-only')
    strip = source / 'ohos_sdk/26.0.0/native/llvm/bin/llvm-strip'
    original_strip = original_sdk / 'llvm/bin/llvm-strip'
    if sha(strip) != SDK_STRIP_SHA256 or sha(original_strip) != SDK_STRIP_SHA256:
        raise ValueError('NativeStrip must use the unchanged fixed API26 SDK tool')
    tools, transformed, stripped = work / 'tools', work / 'transformed', work / 'stripped'
    for path in (tools, transformed, stripped):
        path.mkdir(parents=True)
    official = source / 'third_party/ohos_nweb_hap'
    for name, digest in OFFICIAL_INPUTS.items():
        if sha(official / name) != digest:
            raise ValueError('fixed official kernelpermission input differs: ' + name)
        shutil.copy2(official / name, tools / name)
    report = {'schema_version': 1, 'scope': SCOPE, 'status': 'fail',
        'verifier_sha256': sha(repository / 'scripts/verify_m144_hap_native_transform.py'),
        'sdk_strip_sha256': sha(strip), 'official_inputs_sha256': OFFICIAL_INPUTS,
        'native_evidence_sha256': sha(root / 'native-build-evidence.json'),
        'signed_hap_sha256': signed['hap_sha256'], 'unsigned_hap_sha256': unsigned['hap_sha256'],
        'first_artifact_behavior_gate_passed': False, 'libraries': {}, 'failures': []}
    try:
        for name in sorted(REQUIRED_LIBRARIES):
            original = owned(root, 'native-libraries/' + name)
            baseline = native['artifacts'][name]
            if file_record(original) != {'sha256': baseline['sha256'], 'size': baseline['size']}:
                raise ValueError('archived native output differs: ' + name)
            candidate = transformed / name
            shutil.copy2(original, candidate)
            permission = name == 'libarkweb_engine.so'
            if permission:
                argv = ['python3', str(tools / 'add_kernel_permission.py'), '--llvm-objcopy',
                        str(tools / 'llvm-objcopy'), '--input', str(candidate), '--encaps-json',
                        str(tools / 'encaps.json'), '--output', str(candidate)]
                process = subprocess.run(argv, capture_output=True, text=True, timeout=120)
                report['kernelpermission_command'] = {'argv': argv, 'exit_code': process.returncode,
                    'stdout': process.stdout, 'stderr': process.stderr}
                if process.returncode:
                    raise ValueError('official kernelpermission replay failed')
            # The pinned Hvigor NativeStrip worker invokes the SDK tool with
            # exactly these arguments. Do not use another LLVM version/flags.
            argv = [str(strip), str(candidate), '-o' + str(stripped / name)]
            process = subprocess.run(argv, capture_output=True, text=True, timeout=120)
            row = {'native': file_record(original), 'kernelpermission_applied': permission,
                   'strip_argv': argv, 'strip_exit_code': process.returncode,
                   'strip_stdout': process.stdout, 'strip_stderr': process.stderr}
            report['libraries'][name] = row
            if process.returncode:
                raise ValueError('actual original SDK NativeStrip replay failed: ' + name)
            row['stripped'] = file_record(stripped / name)
            member = signed['native_libraries']['libs/' + signed['abi'] + '/' + name]
            if row['stripped'] != {'sha256': member['sha256'], 'size': member['size']}:
                raise ValueError('exact official transformation does not reproduce HAP library: ' + name)
        report['status'] = 'pass'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    if report['status'] != 'pass':
        raise ValueError('; '.join(report['failures']))
    validate(root, native, signed, repository)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('artifact-directory', 'source-root', 'ohos-root', 'signed-hap', 'unsigned-hap'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--product', required=True)
    parser.add_argument('--arch', choices=ARCHES, required=True)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    value = record(args.artifact_directory, args.source_root, args.ohos_root, args.product,
                   args.arch, args.signed_hap, args.unsigned_hap, args.repository)
    print(json.dumps({'status': value['status'], 'scope': value['scope'],
                      'libraries': len(value['libraries'])}))


if __name__ == '__main__':
    main()
