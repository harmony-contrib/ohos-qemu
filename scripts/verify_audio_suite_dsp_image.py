#!/usr/bin/env python3
"""Offline native-ABI DSP and three exact AudioSuite XML routes, not behavior."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_runtime_elf_contract import read_elf, verify_machine

EXPORTS = {f'iMedia_{kind}_{method}' for kind in ('Eq', 'Surround', 'Env')
           for method in ('GetSPECS', 'GetSize', 'Init', 'Apply', 'SetParams', 'GetParams')} | {'iMedia_Eq_GetVersion'}
ROUTES = {'EQUALIZER', 'SOUND_FIELD', 'ENVIRONMENT_EFFECT'}
ALL_NODES = ROUTES | {'NOISE_REDUCTION', 'AUDIO_SEPARATION', 'AUDIO_MIXER', 'VOICE_BEAUTIFIER',
                      'PURE_CHANGE', 'GENERAL_CHANGE', 'TEMPO_PITCH', 'SPACE_RENDER', 'HOA_RENDER'}
LIBRARY = 'libqemu_audio_suite_dsp.z.so'
SANITIZER = 'libclang_rt.ubsan_minimal.so'
SANITIZER_EXPORTS = {'__ubsan_handle_mul_overflow_minimal_abort',
                     '__ubsan_handle_out_of_bounds_minimal_abort'}
ARM_UNWIND_RUNTIME = 'libc++.so'
ARM_UNWIND_EXPORTS = {'__aeabi_unwind_cpp_pr0', '__aeabi_unwind_cpp_pr1'}


def expected_dependencies(machine):
    if machine not in (40, 183, 62):
        raise ValueError('unsupported native DSP ABI')
    # The real ARM32 OHOS link emits ARM EHABI personality references even
    # with -fno-exceptions. Keep its security/default toolchain settings and
    # verify the actual packaged unwind implementation rather than dropping it.
    return sorted(['libc.so', SANITIZER] + ([ARM_UNWIND_RUNTIME] if machine == 40 else []))


def dynamic_contract(data):
    """Validate actual DT_NEEDED/SONAME, including required security runtime."""
    if len(data) < 64 or data[:4] != b'\x7fELF' or data[4] not in (1, 2) or data[5] != 1:
        raise ValueError('invalid DSP ELF dynamic header')
    if data[4] == 2:
        offset, = struct.unpack_from('<Q', data, 40)
        size, count = struct.unpack_from('<HH', data, 58)
        section_format, entry_format = '<IIQQQQIIQQ', '<qQ'
    else:
        offset, = struct.unpack_from('<I', data, 32)
        size, count = struct.unpack_from('<HH', data, 46)
        section_format, entry_format = '<IIIIIIIIII', '<iI'
    if size < struct.calcsize(section_format) or not count or offset + count * size > len(data):
        raise ValueError('invalid DSP dynamic sections')
    sections = [struct.unpack_from(section_format, data, offset + index * size) for index in range(count)]
    tables = [section for section in sections if section[1] == 6]
    if len(tables) != 1:
        raise ValueError('DSP must have exactly one dynamic table')
    table = tables[0]
    if table[6] >= count:
        raise ValueError('invalid DSP dynamic string index')
    strings_section = sections[table[6]]
    if strings_section[1] != 3 or strings_section[4] + strings_section[5] > len(data):
        raise ValueError('invalid DSP dynamic string data')
    strings = data[strings_section[4]:strings_section[4] + strings_section[5]]
    entry_size = struct.calcsize(entry_format)
    if table[4] + table[5] > len(data) or table[5] % entry_size or table[9] != entry_size:
        raise ValueError('invalid DSP dynamic entries')
    needed, sonames, terminated = [], [], False
    for position in range(table[4], table[4] + table[5], entry_size):
        tag, value = struct.unpack_from(entry_format, data, position)
        if tag == 0:
            terminated = True
            break
        if tag not in (1, 14):
            continue
        end = strings.find(b'\0', value)
        if value >= len(strings) or end < 0:
            raise ValueError('invalid DSP dependency string')
        name = strings[value:end].decode('ascii')
        (needed if tag == 1 else sonames).append(name)
    machine, = struct.unpack_from('<H', data, 18)
    if (not terminated or sorted(needed) != expected_dependencies(machine) or
            sonames != [LIBRARY]):
        raise ValueError('unexpected DSP runtime dependencies/SONAME')
    return sorted(needed)


def verify_xml(text):
    document = ET.fromstring(text)
    if document.tag != 'audioSuiteCapabilities':
        raise ValueError('wrong AudioSuite configuration root')
    observed = {}
    for node in document.findall('./nodeCapability/nodeType'):
        name = node.get('name')
        if not name or name in observed:
            raise ValueError('duplicate or unnamed AudioSuite route')
        observed[name] = dict(node.attrib)
    if set(observed) != ALL_NODES:
        raise ValueError('AudioSuite config must retain all 12 upstream nodes')
    for name, attrs in observed.items():
        if name in ROUTES:
            if (attrs.get('soName') != LIBRARY or attrs.get('soPath') != '/system/lib64/' or
                    attrs.get('frameLen') != '480' or attrs.get('general') != 'yes'):
                raise ValueError('missing/mismatched real DSP route: ' + name)
        elif attrs.get('soName') == LIBRARY:
            raise ValueError('unimplemented algorithm incorrectly routed to DSP: ' + name)
    if not ROUTES.issubset(observed):
        raise ValueError('missing DSP capability route')
    return {name: observed[name] for name in sorted(ROUTES)}


def verify_image(image, machine, executable):
    if machine not in (40, 183, 62):
        raise ValueError('unsupported native DSP ABI')
    abi = 'lib' if machine == 40 else 'lib64'
    with tempfile.TemporaryDirectory(prefix='qemu-audiosuite-dsp-image-') as directory:
        staged = Path(directory)
        def dump(source, target):
            subprocess.run([executable, '-R', f'dump {source} {target}', str(image)], check=True, capture_output=True)
            return target.is_file() and target.stat().st_size > 0
        root, library = None, None
        for index, prefix in enumerate(('', '/system')):
            candidate = staged / f'library-{index}.so'
            if dump(f'{prefix}/{abi}/{LIBRARY}', candidate):
                if root is not None:
                    raise ValueError('ambiguous DSP library roots')
                root, library = prefix, candidate
        if library is None:
            raise ValueError('system image lacks real native-ABI AudioSuite DSP')
        data = library.read_bytes()
        info = read_elf(library)
        verify_machine(info, machine, library)
        if data[4] != (1 if machine == 40 else 2):
            raise ValueError('wrong DSP ELF class')
        if {name for name in info.defined if name.startswith('iMedia_')} != EXPORTS:
            raise ValueError('DSP lacks exact three algorithms ABI exports')
        if '__cfi_check' not in info.defined:
            raise ValueError('DSP lacks required cross-DSO CFI entry')
        needed = dynamic_contract(data)
        runtimes = {}
        runtime_requirements = [
                ('libc.so', {'__cfi_fail_report', 'cos', 'pow', 'sin', 'tanh'}, ''),
                (SANITIZER, SANITIZER_EXPORTS, '/platformsdk')]
        if machine == 40:
            runtime_requirements.append((ARM_UNWIND_RUNTIME, ARM_UNWIND_EXPORTS, ''))
        for name, required, subdir in runtime_requirements:
            runtime = staged / name
            source = f'{root}/{abi}{subdir}/{name}'
            if not dump(source, runtime):
                raise ValueError('missing DSP security/math runtime: ' + source)
            runtime_info = read_elf(runtime)
            verify_machine(runtime_info, machine, runtime)
            if runtime.read_bytes()[4] != (1 if machine == 40 else 2) or not required <= runtime_info.defined:
                raise ValueError('wrong DSP security/math runtime ABI: ' + source)
            runtimes[name] = {'path': source, 'sha256': file_sha256(runtime)}
        config = staged / 'audio_suite_capabilities.xml'
        if not dump(root + '/etc/audio/audio_suite_capabilities.xml', config):
            raise ValueError('system image lacks AudioSuite XML config')
        return {'library': f'{root}/{abi}/{LIBRARY}', 'library_sha256': file_sha256(library),
                'machine': machine, 'needed': needed, 'security_math_runtimes': runtimes,
                'routes': verify_xml(config.read_text()), 'config_sha256': file_sha256(config)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-image', type=Path, required=True)
    parser.add_argument('--machine', type=int, choices=(40, 183, 62), required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'offline three DSP native ABI/config routes only',
              'first_artifact_behavior_gate_passed': False, 'AudioSuite_behavior_validated': False,
              'system_image': str(args.system_image.resolve()), 'failures': []}
    try:
        before = args.system_image.stat()
        result['system_image_sha256'] = file_sha256(args.system_image)
        result.update(verify_image(args.system_image, args.machine, debugfs_path()))
        after = args.system_image.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('system image changed while checking DSP')
        result['status'] = 'pass'
    except (OSError, ValueError, TypeError, KeyError, struct.error, subprocess.SubprocessError, ET.ParseError) as error:
        result['failures'].append(str(error))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
