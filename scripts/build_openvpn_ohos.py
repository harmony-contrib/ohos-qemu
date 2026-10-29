#!/usr/bin/env python3
"""Build fixed-source OpenVPN against a prepared OHOS output; no runtime claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {'arm64_virt': ('aarch64', 'aarch64-linux-ohos', 'AArch64'),
           'armv7a_virt': ('arm', 'arm-linux-ohos', 'ARM'),
           'x86_64_virt': ('x86_64', 'x86_64-linux-ohos', 'Advanced Micro Devices X86-64')}
PORT_PATCH = 'patches/common/third_party/openvpn/ohos_backend/0001-recognize-OHOS-and-isolate-duplicate-UAPI-socket-type.patch'

DNS_PATCH = 'patches/common/third_party/openvpn/ohos_backend/0002-export-final-DNS-policy-to-AF_UNIX-tunnel.patch'


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(4 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def recipe_identity():
    files = ('scripts/build_openvpn_ohos.py', 'scripts/build_product_openvpn.py',
             'scripts/build_openvpn_ohos_in_docker.sh', 'scripts/openvpn_source_lock.json',
             'scripts/openvpn_source_archive.py',
             'scripts/openharmony_release_source_lock.py',
             'scripts/openharmony_7_0_release_source_lock.json', PORT_PATCH, DNS_PATCH)
    hashes = {name: digest(ROOT / name) for name in files}
    return {'recipe_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            'files_sha256': hashes}


def product_build_path(source, product, output):
    """The GN action may write only below its own generated-output directory."""
    allowed = source / 'out' / product / 'gen/foundation/communication/netmanager_ext/qemu_openvpn'
    if not output.is_relative_to(allowed.resolve()) or output == allowed.resolve():
        raise ValueError('OpenVPN product build must use its dedicated GN generation directory')


def extract_source(archive, destination, lock):
    if (archive.is_symlink() or not archive.is_file() or
            archive.stat().st_size != lock['archive_bytes'] or digest(archive) != lock['archive_sha256']):
        raise ValueError('exact pinned OpenVPN source archive required')
    prefix = 'openvpn-' + lock['commit']
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        names = set()
        for member in members:
            path = Path(member.name)
            if (path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != prefix or
                    member.issym() or member.islnk() or not (member.isfile() or member.isdir()) or
                    str(path) in names):
                raise ValueError('source archive contains unexpected paths or file types')
            names.add(str(path))
        for member in members:
            path = Path(member.name)
            target = destination / path
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as inp, target.open('xb') as out:
                    shutil.copyfileobj(inp, out)
                target.chmod(member.mode & 0o777)
    root = destination / prefix
    if digest(root / lock['license_file']) != lock['license_file_sha256']:
        raise ValueError('upstream license identity differs')
    return root


def build(args):
    lock_path = ROOT / 'scripts/openvpn_source_lock.json'
    lock = json.loads(lock_path.read_text())
    source, output = args.source_root.resolve(), args.output.resolve()
    if output.exists() or output.is_symlink():
        raise ValueError('fresh OpenVPN output required')
    product_build = getattr(args, 'product_build', False)
    if product_build:
        product_build_path(source, args.product, output)
    elif not all(os.statvfs(path).f_flag & os.ST_RDONLY for path in (source, source / 'out')):
        raise ValueError('OHOS source and out must be mounted read-only')
    output.mkdir(parents=True)
    report = dict(schema_version=2, component='fixed source OpenVPN for QEMU OHOS',
        status='fail', scope='OHOS_OpenVPN_source_build_ONLY_NOT_packaged_or_runtime',
        recipe=recipe_identity(), product_build=product_build,
        runtime_gate_passed=False,
        first_artifact_behavior_gate_passed=False, product=args.product,
        source_lock_sha256=digest(lock_path), source_archive_sha256=digest(args.archive),
        source_commit=lock['commit'], commands=[], started_epoch=time.time())

    def save():
        (output / 'build-evidence.json').write_text(json.dumps(report, indent=2) + '\n')

    def command(argv, label, cwd, environment):
        log = output / (label + '.log')
        with log.open('xb') as stream:
            result = subprocess.run(list(map(str, argv)), cwd=cwd, env=environment,
                stdout=stream, stderr=subprocess.STDOUT, timeout=3600)
        report['commands'].append(dict(argv=list(map(str, argv)), exit_code=result.returncode,
            log=log.name, sha256=digest(log)))
        save()
        if result.returncode:
            raise ValueError('OpenVPN build command failed: ' + label)
        return log

    try:
        from openharmony_release_source_lock import load_lock, verify
        main_lock = ROOT / 'scripts/openharmony_7_0_release_source_lock.json'
        records = verify(source, load_lock(main_lock))
        report['main_source'] = dict(source_lock_sha256=digest(main_lock),
            checked_projects=len(records), projects=records)
        cpu, triple, machine = TARGETS[args.product]
        tool = source / 'prebuilts/clang/ohos/linux-x86_64/llvm/bin'
        product = source / 'out' / args.product
        sysroot = product / 'obj/third_party/musl'
        generated = product / 'obj/third_party/openssl/build_all_generated/include'
        libraries = product / 'thirdparty/openssl'
        required = [tool / name for name in ('clang', 'llvm-ar', 'llvm-ranlib', 'llvm-strip', 'llvm-readelf')]
        required += [generated / 'openssl/ssl.h', libraries / 'libssl_openssl.z.so', libraries / 'libcrypto_openssl.z.so']
        if not sysroot.is_dir() or any(not path.is_file() for path in required):
            raise ValueError('prepared fixed OHOS compiler, musl and generated OpenSSL outputs required')
        report['dependency_sha256'] = {str(path): digest(path) for path in required}
        environment = dict(os.environ, CC=str(tool / 'clang') + ' --target=' + triple + ' --sysroot=' + str(sysroot),
            AR=str(tool / 'llvm-ar'), RANLIB=str(tool / 'llvm-ranlib'), STRIP=str(tool / 'llvm-strip'),
            CFLAGS='-O2 -fPIC' + (' -march=armv7-a -mfloat-abi=softfp -mfpu=neon' if cpu == 'arm' else ''),
            OPENSSL_CFLAGS='-I' + str(generated) + ' -I' + str(source / 'third_party/openssl/include'),
            OPENSSL_LIBS='-L' + str(libraries) + ' -l:libssl_openssl.z.so -l:libcrypto_openssl.z.so',
            PKG_CONFIG_LIBDIR='/nonexistent')
        report['environment'] = {key: environment[key] for key in ('CC', 'AR', 'RANLIB', 'STRIP', 'CFLAGS',
            'OPENSSL_CFLAGS', 'OPENSSL_LIBS', 'PKG_CONFIG_LIBDIR')}
        save()
        with tempfile.TemporaryDirectory(prefix='openvpn-ohos-') as temporary:
            work = extract_source(args.archive, Path(temporary), lock)
            patch = ROOT / PORT_PATCH
            report['port_patch_sha256'] = digest(patch)
            command(['git', 'apply', '--check', patch], 'port-check', work, environment)
            command(['git', 'apply', patch], 'port-apply', work, environment)
            dns_patch = ROOT / DNS_PATCH
            report['dns_policy_patch_sha256'] = digest(dns_patch)
            command(['git', 'apply', '--check', dns_patch], 'dns-policy-check', work, environment)
            command(['git', 'apply', dns_patch], 'dns-policy-apply', work, environment)
            command(['autoreconf', '-fi'], 'autoreconf', work, environment)
            sub = work / 'config.sub'
            text = sub.read_text()
            marker = 'gnu* | android* | bsd*'
            if text.count(marker) != 1:
                raise ValueError('generated config.sub OS list changed')
            sub.write_text(text.replace(marker, 'ohos* | ' + marker))
            report['generated_config_sub_sha256'] = digest(sub)
            command(['./configure', '--host=' + cpu + '-unknown-ohos', '--build=x86_64-pc-linux-gnu',
                '--disable-dco', '--disable-lz4', '--disable-lzo', '--disable-pkcs11', '--disable-systemd',
                '--disable-plugins', '--disable-unit-tests', '--disable-dns-updown-by-default'],
                'configure', work, environment)
            command(['make', '-C', 'src/compat', '-j' + str(args.jobs)], 'make-compat', work, environment)
            command(['make', '-C', 'src/openvpn', '-j' + str(args.jobs)], 'make-openvpn', work, environment)
            binary = work / 'src/openvpn/openvpn'
            elf = command([tool / 'llvm-readelf', '-h', '-l', '-d', binary], 'ELF-identity', work, environment).read_text()
            interpreter = '/lib/ld-musl-' + ('arm' if cpu == 'arm' else cpu) + '.so.1'
            if machine not in elf or interpreter not in elf or any(value in elf for value in ('(RPATH)', '(RUNPATH)')):
                raise ValueError('unexpected target ELF identity or build path dependency')
            shutil.copy2(binary, output / 'openvpn')
            shutil.copy2(work / 'COPYING', output / 'COPYING')
            shutil.copy2(work / 'COPYRIGHT.GPL', output / 'COPYRIGHT.GPL')
        if report['dependency_sha256'] != {str(path): digest(path) for path in required}:
            raise ValueError('OHOS compiler/runtime dependencies changed during the build')
        report.update(status='pass_source_build_ONLY_NOT_packaged_or_runtime', binary_sha256=digest(output / 'openvpn'))
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        report['finished_epoch'] = time.time()
        save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'archive', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--product', choices=TARGETS, required=True)
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=2)
    parser.add_argument('--product-build', action='store_true',
        help='GN-only mode restricted to this product action\'s generated-output directory')
    result = build(parser.parse_args())
    print(json.dumps({key: result.get(key) for key in ('status', 'error', 'binary_sha256')}))
    raise SystemExit(not result['status'].startswith('pass_'))
