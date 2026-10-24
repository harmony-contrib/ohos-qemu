#!/usr/bin/env python3
"""Build and cache the two ARM32 sherpa inputs inside the existing Linux builder.

The system CPU provider uses softfp/ThinLTO/CFI; the HAR uses the upstream
hard-float NAPI recipe. These are separate outputs, never interchangeable.
This helper creates no containers and makes no runtime acceptance claim.
"""
import argparse
import copy
import fcntl
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import zipfile

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / 'ci/capability-audit'))
from livecaptions579_arm32_contract import admit, elf32, har_proof, raw, ref, ref2, require, tar_members
from livecaptions579_arm32_sources import DEPENDENCIES, LIBS, ORT_SHA, RPATH_PATCH, RPATH_SOURCE_SHA
from livecaptions579_native import PREFIX, recipe

SHERPA_ARCHIVE = 'sherpa-onnx-v1.11.2.tar.gz'
NODE_ARCHIVE = 'node-addon-api-c679f6f4c9dc6bf9fc0d99cbe5982bd24a5e2c7b.tar.gz'
ORT_ARCHIVE = 'onnxruntime-ohos-armeabi-v7a-1.16.3.zip'
SHERPA_SHA = '076031e8801d0f079f008733ad3ad73140ca57ca024bb114a69943eef93f76ba'
NODE_SHA = '5bedae00cf74848e61a308688da0bcebacf2149b9d186ba493ca167571c6db17'
CPU_LIBS = ('libsherpa-onnx-c-api.so', 'libonnxruntime.so', 'libc++_shared.so')
CPU_FLAGS = '-mfloat-abi=softfp -flto=thin -fsanitize=cfi -fsanitize-cfi-cross-dso -fvisibility=hidden'


def write_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        pending = Path(stream.name)
        try:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(pending, path)
        finally:
            pending.unlink(missing_ok=True)


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        pending = Path(stream.name)
    try:
        shutil.copyfile(source.resolve(), pending)
        os.chmod(pending, 0o644)
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)


def checked(path, checksum):
    require(ref(path)['sha256'] == checksum, 'pinned native source changed: ' + str(path))
    return path


def relative(name):
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and '\\' not in name,
            'unsafe native archive path: ' + name)
    return path


def extract(archive, destination, strip_root=False):
    destination.mkdir(parents=True)
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as stream:
            for row in stream.infolist():
                path = relative(row.filename)
                require(stat.S_IFMT(row.external_attr >> 16) != stat.S_IFLNK, 'linked native zip member')
                if row.is_dir():
                    continue
                target = destination / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(stream.read(row))
    else:
        with tarfile.open(archive) as stream:
            rows = stream.getmembers()
            roots = {relative(row.name).parts[0] for row in rows if relative(row.name).parts}
            require(not strip_root or len(roots) == 1, 'one upstream archive root required')
            links = []
            for row in rows:
                path = relative(row.name)
                if strip_root:
                    path = PurePosixPath(*path.parts[1:])
                if row.isdir():
                    continue
                if row.issym():
                    # The pinned release contains two unused Go example links
                    # into its author's machine. They are outside native inputs.
                    if (path.parent == PurePosixPath('scripts/go/_internal/vad-spoken-language-identification') and
                            path.name in ('main.go', 'run.sh') and row.linkname ==
                            '/Users/fangjun/open-source/sherpa-onnx/go-api-examples/vad-spoken-language-identification/' + path.name):
                        continue
                    links.append((destination / path, row.linkname))
                    continue
                require(row.isfile() and path.parts, 'regular native source member required')
                target = destination / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(stream.extractfile(row).read())
                target.chmod(row.mode & 0o777)
            # Upstream includes relative links to shared Kotlin and test sources.
            # Publish links last so no archive file can be written through one.
            for target, link in links:
                require(not PurePosixPath(link).is_absolute() and '\\' not in link and
                        (target.parent / link).resolve().is_relative_to(destination.resolve()),
                        'native source link escapes the extracted tree')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(link)
            require(all(target.resolve().is_relative_to(destination.resolve()) for target, _ in links),
                    'native source link chain escapes the extracted tree')


def sdk_root(source):
    for candidate in (source / 'prebuilts/ohos-sdk/linux/20/native',
                      Path('/Volumes/PSSD/qemu/artifacts/ohos-native-sdk26-linux/native')):
        candidate = candidate.resolve()
        if (candidate / 'build/cmake/ohos.toolchain.cmake').is_file():
            return candidate
    raise ValueError('Linux OHOS native SDK not found under the source root or SDK26 artifact cache')


def libcxx(sdk):
    for path in (sdk / 'sysroot/usr/lib/arm-linux-ohos/libc++_shared.so',
                 sdk / 'llvm/lib/arm-linux-ohos/libc++_shared.so'):
        if path.is_file():
            elf32(path.read_bytes())
            return path
    raise ValueError('ARM32 libc++_shared.so missing from the selected OHOS native SDK')


def stage_dependencies(cache, source):
    for filename, _, checksum in DEPENDENCIES.values():
        shutil.copyfile(checked(cache / filename, checksum), source / filename)


class Builder:
    def __init__(self, work, sdk, ort):
        self.work = work
        self.commands = []
        self.environment = dict(os.environ,
            PATH=str(sdk / 'build-tools/cmake/bin') + ':' + str(sdk / 'llvm/bin') + ':' + os.environ['PATH'],
            SHERPA_ONNXRUNTIME_LIB_DIR=str(ort / 'lib'),
            SHERPA_ONNXRUNTIME_INCLUDE_DIR=str(ort / 'include'))

    def run(self, argv, label, cwd=None):
        argv = list(map(str, argv))
        log = self.work / (label + '.log')
        print('ARM32 ' + label + ': ' + str(log), flush=True)
        with log.open('wb') as stream:
            done = subprocess.run(argv, cwd=cwd, env=self.environment,
                                  stdout=stream, stderr=subprocess.STDOUT, timeout=7200)
        self.commands.append({'argv': argv, 'exit_code': done.returncode, 'log': ref(log)})
        require(done.returncode == 0, 'ARM32 ' + label + ' failed; see ' + str(log))


def cpu_valid(directory):
    return cpu_valid_paths({name: directory / name for name in CPU_LIBS})


def cpu_valid_paths(libraries):
    try:
        for name, path in libraries.items():
            actual = elf32(path.read_bytes())
            require(actual['soname'] == name and not actual['hard_float'], 'softfp CPU provider DSO required')
            if name == 'libsherpa-onnx-c-api.so':
                require('__cfi_check' in actual['exports'] and 'SherpaOnnxCreateOfflineRecognizer' in actual['exports'],
                        'real cross-DSO CFI CPU provider required')
        return True
    except (OSError, ValueError, struct.error):
        return False


def prepare_cpu(source_root, inputs, output, sdk, work_root):
    output.mkdir(parents=True, exist_ok=True)
    if not cpu_valid(output):
        work = Path(tempfile.mkdtemp(prefix='intelligent-voice-', dir=work_root))
        assets = REPOSITORY / 'patches/common/drivers/peripheral/intelligent_voice/cpu_provider/assets/arm32'
        source = work / 'source'
        extract(checked(assets / SHERPA_ARCHIVE, SHERPA_SHA), source, strip_root=True)
        extract(checked(assets / ORT_ARCHIVE, ORT_SHA), work / 'ort')
        ort = work / 'ort/onnxruntime-ohos-armeabi-v7a-1.16.3'
        stage_dependencies(inputs, source)
        builder = Builder(work, sdk, ort)
        cmake = Path('/usr/bin/cmake')
        ninja = source_root / 'prebuilts/build-tools/linux-x86/bin/ninja'
        require(cmake.is_file() and ninja.is_file(), 'system CMake and OHOS Ninja required')
        build, install = work / 'build', work / 'install'
        builder.run([cmake, '-S', source, '-B', build, '-G', 'Ninja', '-DOHOS_ARCH=armeabi-v7a',
            '-DCMAKE_TOOLCHAIN_FILE=' + str(sdk / 'build/cmake/ohos.toolchain.cmake'),
            '-DCMAKE_MAKE_PROGRAM=' + str(ninja), '-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY',
            '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_C_FLAGS=' + CPU_FLAGS, '-DCMAKE_CXX_FLAGS=' + CPU_FLAGS,
            '-DCMAKE_SHARED_LINKER_FLAGS=-flto=thin -fsanitize=cfi -fsanitize-cfi-cross-dso',
            '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DCMAKE_INSTALL_PREFIX=' + str(install),
            '-DBUILD_SHARED_LIBS=ON', '-DSHERPA_ONNX_ENABLE_C_API=ON', '-DSHERPA_ONNX_ENABLE_BINARY=OFF',
            '-DSHERPA_ONNX_ENABLE_TESTS=OFF', '-DSHERPA_ONNX_ENABLE_CHECK=OFF',
            '-DSHERPA_ONNX_ENABLE_PYTHON=OFF', '-DSHERPA_ONNX_ENABLE_PORTAUDIO=OFF',
            '-DSHERPA_ONNX_ENABLE_WEBSOCKET=OFF', '-DSHERPA_ONNX_ENABLE_JNI=OFF',
            '-DSHERPA_ONNX_ENABLE_TTS=OFF', '-DSHERPA_ONNX_ENABLE_SPEAKER_DIARIZATION=OFF'], 'configure')
        builder.run([cmake, '--build', build, '--parallel', '2', '--verbose'], 'compile-link')
        builder.run([cmake, '--install', build], 'install')
        libraries = {'libsherpa-onnx-c-api.so': install / 'lib/libsherpa-onnx-c-api.so',
                     'libonnxruntime.so': ort / 'lib/libonnxruntime.so', 'libc++_shared.so': libcxx(sdk)}
        require(cpu_valid_paths(libraries), 'compiled CPU provider failed ARM32/CFI validation')
        for name, path in libraries.items():
            copy_file(path, output / name)
        write_json(output / 'build.json', {'schema': 'direct-cpu-provider-ohos32-build/v1',
            'commands': builder.commands, 'sdk_root': str(sdk),
            'libraries': {name: ref(output / name) for name in CPU_LIBS},
            'runtime_validated': False, 'first_artifact_behavior_gate_passed': False})
    destination = source_root / 'drivers/peripheral/intelligent_voice/passthrough/cpu/prebuilt/armeabi-v7a'
    for name in CPU_LIBS:
        copy_file(output / name, destination / name)


def collect_licenses(archives, directory):
    rows = []
    for dependency, archive in archives.items():
        found = []

        def save(name, data):
            path = relative(name)
            require(len(data) <= 2 * 1024 * 1024, 'bounded dependency license required')
            target = directory / dependency / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            found.append({'dependency': dependency, 'source': name, 'file': ref(target)})

        pattern = r'^(LICENSE|LICENCE|COPYING|NOTICE|COPYRIGHT)([._-].*)?$'
        if archive.name.endswith('.zip'):
            with zipfile.ZipFile(archive) as stream:
                for row in stream.infolist():
                    if not row.is_dir() and re.match(pattern, relative(row.filename).name, re.I):
                        save(row.filename, stream.read(row))
        else:
            with tarfile.open(archive) as stream:
                for row in stream:
                    if row.isfile() and re.match(pattern, relative(row.name).name, re.I):
                        save(row.name, stream.extractfile(row).read())
        require(found, 'native dependency license missing: ' + dependency)
        rows.extend(found)
    require(sum(row['file']['bytes'] for row in rows) <= 8 * 1024 * 1024, 'bounded full dependency notices required')
    return rows


def merge_har(base, output, libraries, notices, metadata):
    members = tar_members(raw(base))
    profile = 'package/build-profile.json5'
    anchor = b'"arm64-v8a",'
    require(members[profile].count(anchor) == 1, 'fixed official HAR profile required')
    members[profile] = members[profile].replace(anchor, b'"armeabi-v7a",\n        ' + anchor, 1)
    members['package/libs/armeabi-v7a'] = None
    for name, row in libraries.items():
        members['package/libs/armeabi-v7a/' + name] = raw(row['file'])
    members['package/NOTICE.arm32.txt'] = raw(notices)
    members['package/ARM32_NATIVE_SOURCES.json'] = (json.dumps(metadata, indent=2) + '\n').encode()
    with output.open('wb') as physical:
        with gzip.GzipFile(fileobj=physical, mode='wb', mtime=0, filename='') as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as stream:
                for name, data in members.items():
                    row = tarfile.TarInfo(name)
                    row.mode = 0o755 if data is None else 0o644
                    if data is None:
                        row.type = tarfile.DIRTYPE
                        stream.addfile(row)
                    else:
                        row.size = len(data)
                        stream.addfile(row, io.BytesIO(data))


def prepare_captions(inputs, output, sdk, work_root, base_path):
    descriptor_path = output / 'product-assets-arm32.json'
    if descriptor_path.is_file():
        try:
            admit(json.loads(descriptor_path.read_text()))
            return descriptor_path
        except (OSError, ValueError, KeyError, TypeError, struct.error, tarfile.TarError, zipfile.BadZipFile):
            print('Rebuild invalid cached ARM32 captions inputs', flush=True)
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='livecaptions-', dir=work_root))
    archives = {'sherpa': checked(inputs / SHERPA_ARCHIVE, SHERPA_SHA),
                'node_addon_api': checked(inputs / NODE_ARCHIVE, NODE_SHA),
                'onnxruntime': checked(inputs / ORT_ARCHIVE, ORT_SHA)}
    for name, (filename, _, checksum) in DEPENDENCIES.items():
        archives[name] = checked(inputs / filename, checksum)
    source, node = work / 'source', work / 'node'
    extract(archives['sherpa'], source, strip_root=True)
    extract(archives['node_addon_api'], node, strip_root=True)
    extract(archives['onnxruntime'], work / 'ort')
    stage_dependencies(inputs, source)
    ort = work / 'ort/onnxruntime-ohos-armeabi-v7a-1.16.3'
    builder = Builder(work, sdk, ort)
    checked(source / 'CMakeLists.txt', RPATH_SOURCE_SHA)
    patch = work / 'origin-rpath.patch'
    patch.write_text(RPATH_PATCH)
    builder.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i', patch], 'rpath-patch', cwd=source)
    builder.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1', '-i',
                 source / PREFIX / 'src/main/cpp/my-patch.diff'], 'node-addon-patch', cwd=node)
    paths = {'source': str(source), 'sdk_native': str(sdk), 'ort': str(ort),
             'c_api_build': str(work / 'c-api'), 'install': str(work / 'install'),
             'napi_build': str(work / 'napi'), 'node_addon': str(node)}
    spec = recipe('armeabi-v7a', paths)
    for label in ('c_api_configure', 'c_api_build', 'c_api_install'):
        builder.run(spec['commands'][label], label)
    for target, origin in spec['copy_before_napi'].items():
        copy_file(Path(origin), Path(target))
    builder.run(spec['commands']['napi_configure_after_actual_c_api_copy'], 'napi_configure')
    builder.run(spec['commands']['napi_build'], 'napi_build')
    native = output / 'native'
    native.mkdir(exist_ok=True)
    sources = {'libsherpa_onnx.so': work / 'napi/libsherpa_onnx.so',
               'libsherpa-onnx-c-api.so': work / 'install/lib/libsherpa-onnx-c-api.so',
               'libonnxruntime.so': ort / 'lib/libonnxruntime.so', 'libc++_shared.so': libcxx(sdk)}
    libraries = {}
    for name in LIBS:
        target = native / name
        copy_file(sources[name], target)
        builder.run([sdk / 'llvm/bin/llvm-strip', '--strip-unneeded', target], 'strip-' + name)
        libraries[name] = {'file': ref(target), 'elf': elf32(target.read_bytes())}
    base = json.loads(base_path.read_text())
    from livecaptions579_inputs import product_assets
    product_assets(base, 'arm64-v8a')
    licenses = collect_licenses(archives, output / 'licenses')
    notice_data = bytearray(raw(base['assets']['notices']))
    for row in licenses:
        notice_data.extend(('\n\n--- ARM32 native source ' + row['dependency'] + '/' + row['source'] + ' ---\n').encode())
        notice_data.extend(raw(row['file']))
    notices = output / 'LIVE_CAPTIONS_NOTICES.arm32.txt'
    notices.write_bytes(notice_data)
    metadata = {'sources': {name: ref(path) for name, path in archives.items()},
                'toolchain': ref(sdk / 'build/cmake/ohos.toolchain.cmake'),
                'rpath_patch': ref(patch), 'node_patch': ref(source / PREFIX / 'src/main/cpp/my-patch.diff'),
                'libraries': libraries, 'licenses': licenses, 'scope': 'native build only; runtime pending'}
    har = output / 'sherpa_onnx-1.11.2-three-abi.har'
    merge_har(base['assets']['har'], har, libraries, ref(notices), metadata)
    har_proof(base['assets']['har'], ref(har), libraries, ref(notices))
    build = {'schema': 'direct-livecaptions579-ohos32-build/v1',
             'status': 'compiled_linked_packaged_NOT_runtime_validated', 'exit_code': 0,
             'runtime_validated': False, 'first_artifact_behavior_gate_passed': False,
             'sdk_root': str(sdk), 'base_assets': base, 'base_har': base['assets']['har'],
             'har': ref(har), 'libraries': libraries, 'notices': ref(notices),
             'licenses': licenses, 'commands': builder.commands, 'native_sources': metadata}
    write_json(output / 'build.json', build)
    descriptor = copy.deepcopy(base)
    descriptor.pop('ohos32_source_build', None)
    descriptor.update(ohos32_direct_build=ref2(ref(output / 'build.json')))
    descriptor['assets'].update(har=ref2(ref(har)), notices=ref2(ref(notices)))
    product_assets(descriptor, 'armeabi-v7a')
    write_json(descriptor_path, descriptor)
    return descriptor_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--cache-root', required=True, type=Path)
    args = parser.parse_args()
    require(sys.platform.startswith('linux'), 'run inside the existing Linux Docker build container')
    source_root = args.source_root.resolve()
    cache = args.cache_root.resolve() / 'artifacts/livecaptions-lottie-7.0'
    sdk = sdk_root(source_root)
    output = cache / 'arm32-prebuilt'
    output.mkdir(parents=True, exist_ok=True)
    work_root = output / '.work'
    work_root.mkdir(exist_ok=True)
    with (output / '.prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prepare_cpu(source_root, cache / 'arm32-sources', output / 'intelligent_voice', sdk, work_root)
        descriptor = prepare_captions(cache / 'arm32-sources', output / 'livecaptions', sdk, work_root,
            cache / 'r66-asr-product-assets579-05/product-assets.json')
        print(str(descriptor) + '\t' + ref(descriptor)['sha256'])


if __name__ == '__main__':
    main()
