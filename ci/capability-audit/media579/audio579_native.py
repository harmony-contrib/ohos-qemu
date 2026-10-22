"""One actual SDK C-ABI addon, built by the existing held IO command callback.

Public MIDI headers absent from this SDK are copied from Root's authenticated
same-product source export. The addon links the actual installed libohmidi C
API. That library is never copied into a HAP or substituted in the image.
"""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile
from audio579_common import HERE, need, ref, checked, doc, dependency, save, source_guard, communication_napi

ABIS = {'arm64': ('arm64-v8a', 'aarch64-linux-ohos'),
        'armv7a': ('armeabi-v7a', 'arm-linux-ohos'), 'x86_64': ('x86_64', 'x86_64-linux-ohos')}


def prepare_native(io, project):
    original = dependency('capability578_owned_io')
    need(type(io) is original.OwnedIO and io.owner.vm is io.guest and not io._closed,
         'actual existing main OwnedIO only')
    io.owner.held_binding(io.guest)
    context = doc(source_guard()); commit = context['source_commit']
    need(doc(ref(io.guest.directory / 'build-inputs.json'))['source_git_revision'] == commit,
         'normal supplemental source must match the actual freshly packaged build inputs')
    arch = io.guest.report['test_environment']['guest_arch']; abi, triple = ABIS[arch]
    inputs = io.package_inputs['media579_audio']
    need(inputs['schema'] == 'media579-audio-product-inputs/v1' and inputs['source_commit'] == commit and
         inputs['archive']['sha256'] == io.archive_sha256 and inputs['arch'] == arch,
         'actual same new archive/product MIDI source inputs')
    exported = doc(inputs['source_export'])
    need(exported['source_commit'] == commit and exported['archive_sha256'] == io.archive_sha256 and
         exported['product'] == io.guest.report['test_environment']['product'] and
         exported['source_kind'] == 'actual_shared_source_and_out_readonly_export' and
         exported['resources_executed'] is True and exported['cleanup_verified'] is True and
         exported['failures'] == [], 'original Root source export must finish before main guest starts')
    headers = inputs['midi_headers']
    need(set(headers) == {'midi/native_midi.h', 'midi/native_midi_base.h'}, 'exact two real public C headers')
    product = dependency('batch_system_build_runtime_helpers')
    profile = doc(inputs['installed_runtime_profile'])
    product.validate_installed_profile(profile, archive_sha256=io.archive_sha256)
    library = checked(inputs['midi_library'])
    soname = product.elf_soname(library, product=profile['product'])
    need(soname == 'libohmidi.so', 'actual original public MIDI C API DSO')
    installed = profile['dsos'].get(soname)
    need(installed is not None and installed['image_file']['sha256'] == inputs['midi_library']['sha256'] and
         checked(installed['image_file']).read_bytes() == library.read_bytes(),
         'MIDI DSO must be exactly the actual packaged installed-runtime profile')
    for logical, row in headers.items():
        checked(row)
        source = 'foundation/multimedia/midi_framework/interfaces/kits/c/' + logical
        need(exported['files'][source]['sha256'] == row['sha256'], 'real exported public header origin')
    root = io.output / 'audio579-native'
    if not root.exists():
        root.mkdir()
        for logical, row in headers.items():
            target = root / 'include' / logical; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(checked(row), target)
        link = root / 'link'; link.mkdir()
        shutil.copyfile(library, link / 'libohmidi.so')
        sdk = Path(io.owner.config['sdk'])
        compiler = sdk / 'native/llvm/bin/clang++'
        sdk_metadata = {part: ref(sdk / part / 'oh-uni-package.json') for part in ('native', 'ets')}
        for row in sdk_metadata.values():
            value = doc(row)
            need(value['apiVersion'] == '26' and value['platformVersion'] == '26.0.0' and
                 value['releaseType'] == 'Release', 'actual official API26 Release SDK')
        cxx = sdk / 'native/llvm/lib' / triple / 'libc++_shared.so'
        need(cxx.is_file(), 'actual same-ABI official SDK C++ runtime')
        midi_include = ref(HERE / 'usb579_midi_session.inc')
        binary = root / 'libaudio579midi.so'
        flags = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon'] if arch == 'armv7a' else []
        argv = [str(compiler), '--target=' + triple, '--sysroot=' + str(sdk / 'native/sysroot'), *flags,
            '-std=c++17', '-shared', '-fPIC', '-MMD', '-MF', str(root / 'headers.d'), '-pthread', '-O2', '-Wall', '-Wextra', '-Werror',
            '-I' + str(root / 'include'), str(HERE / 'audio579_midi.cpp'), '-L' + str(link),
            '-l:libohmidi.so', '-lace_napi.z', '-o', str(binary)]
        actual = io.command(['/usr/bin/nice', '-n', '10', *argv], 'audio579_actual_public_MIDI_C_addon',
            timeout=300, cwd=root)
        contract = dependency('avc_media_contract')
        contract.verify_elf(binary.read_bytes(), arch)
        save(root / 'build.json', dict(schema='audio579-real-SDK-C-addon/v1', run=io.run_id,
            archive_sha256=io.archive_sha256, boot_id=io.boot_id, arch=arch, source=ref(HERE / 'audio579_midi.cpp'),
            midi_session_include=midi_include, native_dependencies=ref(root / 'headers.d'),
            compiler=ref(compiler.resolve()), invoked_compiler=str(compiler), sdk=sdk_metadata, inputs=inputs, headers=headers,
            link_library=inputs['midi_library'], command=io.ref_receipt(actual), binary=ref(binary),
            runtime_sha256=contract.runtime_identity(binary.read_bytes(), arch),
            cxx=ref(cxx.resolve()), cxx_runtime_sha256=contract.runtime_identity(cxx.read_bytes(), arch),
            C_ABI_only=True, copied_system_DSO_into_HAP=False,
            runtime_pass=False, first_artifact_behavior_gate_passed=False))
    built = ref(root / 'build.json'); value = doc(built)
    need(value['run'] == io.run_id and value['archive_sha256'] == io.archive_sha256 and
         value['boot_id'] == io.boot_id and value['source'] == ref(HERE / 'audio579_midi.cpp') and
         value['midi_session_include'] == ref(HERE / 'usb579_midi_session.inc') and checked(value['native_dependencies']) and
         value['inputs'] == inputs and value['arch'] == arch, 'one same IO native build reused by exactly four roles')
    binary = checked(value['binary'])
    destination = Path(project) / 'entry/libs' / abi / 'libaudio579midi.so'
    destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(binary, destination)
    cxx_destination = destination.with_name('libc++_shared.so')
    shutil.copyfile(checked(value['cxx']), cxx_destination)
    profile_path = Path(project) / 'entry/build-profile.json5'
    profile = json.loads(profile_path.read_text())
    profile.setdefault('buildOption', {})['externalNativeOptions'] = {'abiFilters': [abi]}
    profile['buildOption']['nativeLib'] = {'debugSymbol': {'strip': False}}
    profile_path.write_text(json.dumps(profile, indent=2) + '\n')
    need(Path(value['invoked_compiler']).resolve() == checked(value['compiler']), 'real invoked SDK compiler target')
    return dict(cxx=value['cxx'], cxx_runtime_sha256=value['cxx_runtime_sha256'], build=built, binary=value['binary'], destination=str(destination), abi=abi, arch=arch,
        runtime_sha256=value['runtime_sha256'])


def verify_native_hap(hap, native):
    with zipfile.ZipFile(hap) as package:
        name = 'libs/' + native['abi'] + '/libaudio579midi.so'
        need(package.namelist().count(name) == 1 and not any(row.endswith('/libohmidi.so') for row in package.namelist()),
             'one original addon and no bundled replacement product MIDI service library')
        actual = package.read(name)
        runtime_name = 'libs/' + native['abi'] + '/libc++_shared.so'
        need(package.namelist().count(runtime_name) == 1, 'one actual same-ABI SDK C++ runtime in each HAP')
        runtime = package.read(runtime_name)
    need(actual == checked(native['binary']).read_bytes() and runtime == checked(native['cxx']).read_bytes(),
         'exact actual addon and same-ABI SDK C++ bytes in unsigned and signed HAPs')
    need(dependency('avc_media_contract').runtime_identity(actual, native['arch']) == native['runtime_sha256'],
         'actual signed/unsigned HAP preserves the freshly compiled native C API code/data')
    need(dependency('avc_media_contract').runtime_identity(runtime, native['arch']) == native['cxx_runtime_sha256'],
         'actual signed/unsigned HAP preserves the freshly selected SDK C++ runtime code/data')
    return native
