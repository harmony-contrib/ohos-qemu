#!/usr/bin/env python3
"""Validate Camera GN/link in an exclusively owned, completed DSP scratch tree.

The actual production source and product out must be mounted read-only. This
never packages, boots, injects libraries into a guest, or passes the artifact
behavior gate. Existing DSP evidence is retained; its graph is regenerated.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import struct
import subprocess
import sys

PERIPHERAL_REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
COMPONENTS = (
    'patches/common/third_party/libjpeg-turbo/release_3_1_0',
    'patches/common/vendor/ohemu/camera_profile',
    'patches/common/drivers/peripheral/camera/usb_backend',
    'patches/common/drivers/peripheral/camera/vivid_capture',
)
INPUT_CONFIG = 'drivers/peripheral/camera/vdi_base/usb_camera/pipeline_core/pipeline_impl/src/strategy/config'
CLONE_PROVENANCE = 'camera-scratch-clone-provenance.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_tree(root, staged, product):
    if staged == root or staged.is_relative_to(root) or root.is_relative_to(staged):
        raise ValueError('scratch source must be separate from production source')
    for path in (root, root / 'out'):
        if not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise ValueError('production source and out must both be read-only')
    for relative in ('build', 'vendor', 'drivers', 'out'):
        path = staged / relative
        if not path.is_dir() or path.is_symlink():
            raise ValueError('scratch writable component/output must be a real directory: ' + relative)
    evidence = json.loads((staged / 'audio-dsp-build-evidence.json').read_text())
    if (evidence.get('product') != product
            or evidence.get('gn_exit_code') != 0 or evidence.get('link_exit_code') != 0):
        raise ValueError('scratch must contain matching completed actual DSP GN/link evidence')
    original_source = Path(evidence['scratch_source'])
    library = Path(evidence['library'])
    if original_source != staged:
        clone = json.loads((staged / CLONE_PROVENANCE).read_text())
        if (clone.get('seed_source') != str(original_source) or clone.get('scratch_source') != str(staged)
                or clone.get('product') != product
                or clone.get('seed_DSP_evidence_sha256') != sha(staged / 'audio-dsp-build-evidence.json')):
            raise ValueError('owned scratch clone provenance does not match preserved DSP evidence')
        if not library.is_relative_to(original_source / 'out'):
            raise ValueError('prior DSP library must be inside its actual original output')
        library = staged / library.relative_to(original_source)
    if not library.is_relative_to(staged / 'out') or sha(library) != evidence['library_sha256']:
        raise ValueError('prior actual DSP library evidence does not match scratch output')
    return evidence


def assert_seed_inactive(seed, proc_root=Path('/proc')):
    if not proc_root.is_dir():
        raise ValueError('isolated clone requires actual Linux process state')
    for process in proc_root.iterdir():
        if not process.name.isdigit():
            continue
        try:
            arguments = (process / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        active_tool = any(Path(os.fsdecode(argument)).name in
                          ('ninja', 'gn', 'clang', 'clang++', 'ld.lld', 'make', 'cmake')
                          for argument in arguments if argument)
        try:
            working_directory = (process / 'cwd').resolve(strict=True)
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            working_directory = None
        references_seed = any(str(seed).encode() in argument for argument in arguments)
        uses_seed_cwd = (working_directory is not None
                         and working_directory.is_relative_to(seed))
        if active_tool and (references_seed or uses_seed_cwd):
            raise ValueError('refusing to clone a source/output used by an active build tool')


def clone_stopped_scratch(root, seed, staged, product):
    """Preserve the completed seed tree/evidence; normal GN regenerates a clone."""
    if (staged == root or staged.is_relative_to(root) or root.is_relative_to(staged)
            or staged == seed or staged.is_relative_to(seed) or seed.is_relative_to(staged)):
        raise ValueError('clone must be separate from production and completed seed source')
    prior = validate_tree(root, seed, product)
    if (seed / CLONE_PROVENANCE).exists():
        raise ValueError('clone must start from an actual original completed DSP tree')
    staged.mkdir(parents=True, exist_ok=True)
    if any(staged.iterdir()):
        raise ValueError('new Camera clone directory must be empty')
    assert_seed_inactive(seed)
    dsp_evidence_sha = sha(seed / 'audio-dsp-build-evidence.json')
    subprocess.run(['cp', '--archive', '--reflink=auto', str(seed) + '/.', str(staged)], check=True)
    rewritten = []
    # Relative internal links retain their meaning. Remap explicit links into
    # the seed so a new candidate can never write through to the old evidence.
    for directory, directories, files in os.walk(staged, followlinks=False):
        for name in directories + files:
            path = Path(directory) / name
            if path.is_symlink():
                target = path.resolve()
                if target.is_relative_to(seed):
                    replacement = staged / target.relative_to(seed)
                    path.unlink()
                    path.symlink_to(replacement)
                    rewritten.append(str(path.relative_to(staged)))
    if sha(seed / 'audio-dsp-build-evidence.json') != dsp_evidence_sha:
        raise ValueError('completed seed evidence changed while cloning; do not use this candidate')
    provenance = {'scope': 'byte_clone_of_stopped_component_scratch_NOT_new_build_or_guest_acceptance',
                  'seed_source': str(seed), 'scratch_source': str(staged), 'product': product,
                  'seed_DSP_evidence_sha256': dsp_evidence_sha,
                  'seed_DSP_library_sha256': prior['library_sha256'],
                  'remapped_internal_symlinks': rewritten,
                  'production_source_and_out_mounted_readonly': True}
    with (staged / CLONE_PROVENANCE).open('x') as stream:
        json.dump(provenance, stream, indent=2)
        stream.write('\n')
    validate_tree(root, staged, product)
    return provenance


def input_config_hashes(staged):
    directory = staged / INPUT_CONFIG
    return {path.name: sha(path) for path in sorted(directory.glob('*')) if path.is_file()}


def materialize_directory_skeleton(root, staged, top):
    # Preserve every real child directory so the fixed component loader can
    # discover all components. Non-copied files remain read-only source links.
    for directory, subdirectories, _ in os.walk(root / top, followlinks=False):
        subdirectories[:] = [name for name in subdirectories if name not in ('.git', '__pycache__', 'node_modules')]
        original = Path(directory)
        target_directory = staged / original.relative_to(root)
        if target_directory.is_symlink():
            if target_directory.resolve() != original.resolve():
                raise ValueError('unexpected scratch input directory symlink')
            target_directory.unlink()
            target_directory.mkdir()
            for child in original.iterdir():
                (target_directory / child.name).symlink_to(child, target_is_directory=child.is_dir())
        elif not target_directory.is_dir():
            raise ValueError('missing actual scratch component directory')


def copy_libjpeg_inputs(root, staged, prefix):
    """Let the unchanged upstream installer write only its owned source copy."""
    materialize_directory_skeleton(root, staged, 'third_party')
    source = root / 'third_party/libjpeg-turbo'
    target = staged / 'third_party/libjpeg-turbo'
    backup = staged / 'out' / (prefix + '-libjpeg-prior-inputs')
    if backup.exists() or backup.is_symlink() or target.is_symlink() or not target.is_dir():
        raise ValueError('refusing to replace an unknown libjpeg scratch component')
    # Keep prior owned aliases/generated headers as evidence, not deletion.
    # Never overwrite a file through a read-only production-source symlink.
    target.rename(backup)
    shutil.copytree(source, target, symlinks=True)
    inputs = {str(path.relative_to(source)): sha(path) for path in sorted(source.rglob('*'))
              if path.is_file() and '__pycache__' not in path.parts and '.git' not in path.parts}
    for name, expected in inputs.items():
        if sha(target / name) != expected:
            raise ValueError('copied libjpeg input differs from production source bytes')
    return {'component': 'third_party/libjpeg-turbo', 'prior_owned_inputs_preserved': str(backup),
            'copied_input_sha256': inputs,
            'strict_release_3_1_0_component_applied_separately_before_GN': True}


def materialize_idl_inputs(root, staged):
    """Copy unmodified IDL data because the fixed IDL reader requires W_OK.

    Do not patch or bypass that reader, change a production mount, or copy old
    generated headers. Only original source IDL bytes become local inputs.
    """
    records = []
    for top in ('base', 'foundation', 'interface', 'commonlibrary', 'domains', 'test', 'drivers'):
        if not (root / top).is_dir():
            continue
        materialize_directory_skeleton(root, staged, top)
        for directory, subdirectories, filenames in os.walk(root / top, followlinks=False):
            subdirectories[:] = [name for name in subdirectories if name not in ('.git', '__pycache__', 'node_modules')]
            for name in sorted(filenames):
                if not name.endswith('.idl'):
                    continue
                source = Path(directory) / name
                relative = source.relative_to(root)
                if not source.resolve().is_relative_to(root):
                    raise ValueError('source IDL resolves outside the read-only production tree')
                target = staged / relative
                source_hash = sha(source)
                if target.is_symlink():
                    if target.resolve() != source.resolve():
                        raise ValueError('unexpected scratch IDL input symlink')
                    target.unlink()
                    shutil.copy2(source, target)
                if not target.is_file() or sha(target) != source_hash:
                    raise ValueError('existing scratch IDL source differs from fixed production input')
                records.append({'source': str(relative), 'sha256': source_hash})
    return sorted(records, key=lambda record: record['source'])


def elf_identity(path, product):
    header = path.read_bytes()[:64]
    expected_class, expected_machine = {'arm64_virt': (2, 183), 'armv7a_virt': (1, 40),
                                        'x86_64_virt': (2, 62)}[product]
    if (len(header) < 52 or header[:4] != b'\x7fELF' or header[4] != expected_class
            or header[5] != 1 or struct.unpack_from('<HH', header, 16) != (3, expected_machine)):
        raise ValueError('Camera DSO is not an actual matching little-endian shared library: ' + str(path))
    return {'elf_class': expected_class, 'elf_machine': expected_machine, 'elf_type': 3}


def elf_tls_segments(path):
    """Check TLS in the real linked DSO, not just an injected header macro."""
    data = path.read_bytes()
    if len(data) < 52 or data[:4] != b'\x7fELF' or data[5] != 1:
        raise ValueError('TLS check requires a little-endian ELF output')
    if data[4] == 1:
        offset = struct.unpack_from('<I', data, 28)[0]
        size, count = struct.unpack_from('<HH', data, 42)
        minimum_size = 32
    elif data[4] == 2 and len(data) >= 64:
        offset = struct.unpack_from('<Q', data, 32)[0]
        size, count = struct.unpack_from('<HH', data, 54)
        minimum_size = 56
    else:
        raise ValueError('TLS check requires an actual supported ELF class')
    if size < minimum_size or not count or offset + size * count > len(data):
        raise ValueError('linked DSO has missing or truncated program headers')
    return sum(struct.unpack_from('<I', data, offset + index * size)[0] == 7
               for index in range(count))


def jpeg_generated_headers(staged, output):
    source = staged / 'third_party/libjpeg-turbo'
    generated = output / 'gen/third_party/libjpeg-turbo/libjpeg-turbo-3.1.0'
    headers = []
    for name in ('jconfig.h', 'jconfigint.h'):
        path = generated / 'src' / name
        if path.read_bytes() != (source / name).read_bytes():
            raise ValueError('generated JPEG header differs from strict component source: ' + name)
        headers.append({'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size})
    cmake = (generated / 'CMakeLists.txt').read_text()
    match = re.search(r'^set\(COPYRIGHT_YEAR "([^"]+)"\)', cmake, re.MULTILINE)
    if not match or match.group(1) != '1991-2024':
        raise ValueError('generated JPEG version header requires the fixed archive copyright year')
    template = generated / 'src/jversion.h.in'
    path = generated / 'src/jversion.h'
    expected = template.read_bytes().replace(b'@COPYRIGHT_YEAR@', match.group(1).encode())
    if path.read_bytes() != expected:
        raise ValueError('generated JPEG version header differs from its same-archive 3.1 template')
    headers.append({'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size,
                    'same_archive_template_sha256': sha(template), 'copyright_year': match.group(1)})
    return headers


def symbol_present(table, name, kind, defined, bindings):
    for line in table.splitlines():
        fields = line.split()
        if (len(fields) == 8 and fields[0].endswith(':') and fields[7] == name
                and fields[3] == kind and fields[4] in bindings
                and (fields[6] != 'UND') == defined):
            return True
    return False


def arm_plt_emutls_call(accessor, plt, relocations):
    """ARM32 objdump labels PLT entries as $a, so resolve the actual GOT slot."""
    targets = re.findall(r'\bblx?\s+0x([0-9a-fA-F]+)', accessor)
    if len(targets) != 1:
        raise ValueError('ARM JPEG accessor must have exactly one inspected resolver call')
    target = int(targets[0], 16)
    instructions = [(int(address, 16), int(word, 16)) for address, word in re.findall(
        r'^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{8})\s+', plt, re.MULTILINE)]
    if (len(instructions) != 3 or [address for address, _ in instructions] !=
            [target, target + 4, target + 8]):
        raise ValueError('ARM resolver PLT instruction layout is not the actual supported 3-word entry')
    first, second, last = [word for _, word in instructions]
    if (first & 0xfffff000 != 0xe28fc000 or second & 0xfffff000 != 0xe28cc000
            or last & 0xfffff000 != 0xe5bcf000):
        raise ValueError('ARM resolver PLT does not implement ADD ip,pc; ADD ip,ip; LDR pc,[ip]!')
    def arm_immediate(word):
        value, rotation = word & 0xff, ((word >> 8) & 0xf) * 2
        return ((value >> rotation) | (value << (32 - rotation))) & 0xffffffff if rotation else value
    slot = (target + 8 + arm_immediate(first) + arm_immediate(second) + (last & 0xfff)) & 0xffffffff
    matches = re.findall(r'^\s*([0-9a-fA-F]+)\s+[0-9a-fA-F]+\s+R_ARM_JUMP_SLOT\s+'
                         r'[0-9a-fA-F]+\s+__emutls_get_address\b', relocations, re.MULTILINE)
    if len(matches) != 1 or int(matches[0], 16) != slot:
        raise ValueError('ARM accessor PLT GOT slot does not match the actual emutls resolver relocation')
    return {'accessor_call_target': hex(target), 'resolved_PLT_GOT_slot': hex(slot),
            'verified_relocation': 'R_ARM_JUMP_SLOT __emutls_get_address'}


def jpeg_tls_evidence(root, output, product, log):
    """Accept actual native TLS or the OHOS emutls implementation closure."""
    llvm = root / 'prebuilts/clang/ohos/linux-x86_64/llvm/bin'
    library = output / 'thirdparty/libjpeg-turbo/libturbojpeg.z.so'
    unstripped = output / 'lib.unstripped/thirdparty/libjpeg-turbo/libturbojpeg.z.so'
    identity = elf_identity(unstripped, product)
    commands = []
    with log.open('x') as stream:
        def inspect(command, cwd=output):
            commands.append(command)
            stream.write('COMMAND ' + shlex.join(command) + '\n')
            checked = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, check=True)
            stream.write(checked.stdout + '\n')
            stream.flush()
            return checked.stdout

        table = inspect([str(llvm / 'llvm-readelf'), '--symbols', str(unstripped)])
        segments = elf_tls_segments(library)
        if segments == 1 and symbol_present(table, 'errStr', 'TLS', True, {'LOCAL'}):
            mode = 'native_ELF_TLS'
            details = {}
        elif (segments == 0
              and symbol_present(table, '__emutls_v.errStr', 'OBJECT', True, {'LOCAL'})
              and symbol_present(table, '__emutls_t.errStr', 'OBJECT', True, {'LOCAL'})
              and symbol_present(table, '__emutls_get_address', 'FUNC', False, {'GLOBAL', 'WEAK'})):
            dynamic = inspect([str(llvm / 'llvm-readelf'), '--dynamic', str(library)])
            if 'Shared library: [libc++.so]' not in dynamic:
                raise ValueError('emutls consumer does not depend on its actual C++ runtime provider')
            disassembly = inspect([str(llvm / 'llvm-objdump'), '--disassemble-symbols=tjGetErrorStr',
                                   str(unstripped)])
            call_details = {'resolver_call_validation': 'symbolized_disassembly'}
            if '__emutls_get_address' not in disassembly:
                if product != 'armv7a_virt':
                    raise ValueError('actual JPEG error-string accessor does not call its emutls resolver')
                targets = re.findall(r'\bblx?\s+0x([0-9a-fA-F]+)', disassembly)
                if len(targets) != 1:
                    raise ValueError('ARM JPEG accessor does not have exactly one actual call target')
                target = int(targets[0], 16)
                plt = inspect([str(llvm / 'llvm-objdump'), '--disassemble', '--section=.plt',
                               '--start-address=' + hex(target), '--stop-address=' + hex(target + 12),
                               str(unstripped)])
                relocations = inspect([str(llvm / 'llvm-readelf'), '--relocations', '--wide', str(unstripped)])
                call_details = {'resolver_call_validation': 'ARM32_actual_PLT_instruction_and_relocation_address',
                                **arm_plt_emutls_call(disassembly, plt, relocations)}
            ninja = (output / 'obj/third_party/libjpeg-turbo/turbojpeg.ninja').read_text()
            match = re.search(r'^  ldflags = (.*)$', ninja, re.MULTILINE)
            if not match:
                raise ValueError('actual JPEG GN output lacks its linker target arguments')
            flags = [flag for flag in shlex.split(match.group(1)) if flag.startswith(
                ('--target=', '--sysroot=', '-march=', '-mcpu=', '-mfpu=', '-mfloat-abi=', '-L'))]
            provider_command = [str(llvm / 'clang++'), *flags, '-print-file-name=libc++.so']
            provider = Path(inspect(provider_command).strip()).resolve()
            if not provider.is_relative_to(root / 'prebuilts/clang'):
                raise ValueError('actual emutls provider did not resolve inside the read-only toolchain')
            elf_identity(provider, product)
            provider_table = inspect([str(llvm / 'llvm-readelf'), '--symbols', str(provider)])
            if not symbol_present(provider_table, '__emutls_get_address', 'FUNC', True, {'GLOBAL', 'WEAK'}):
                raise ValueError('actual runtime provider does not export the emutls resolver')
            provider_dynamic = inspect([str(llvm / 'llvm-readelf'), '--dynamic', str(provider)])
            if 'Shared library: [libc.so]' not in provider_dynamic:
                raise ValueError('emutls runtime provider does not declare its actual libc dependency')
            triple = {'arm64_virt': 'aarch64-linux-ohos', 'armv7a_virt': 'arm-linux-ohos',
                      'x86_64_virt': 'x86_64-linux-ohos'}[product]
            libc = output / 'obj/third_party/musl/usr/lib' / triple / 'libc.so'
            elf_identity(libc, product)
            libc_table = inspect([str(llvm / 'llvm-readelf'), '--symbols', str(libc)])
            for name in ('pthread_key_create', 'pthread_getspecific', 'pthread_setspecific'):
                if (not symbol_present(provider_table, name, 'FUNC', False, {'GLOBAL', 'WEAK'})
                        or not symbol_present(libc_table, name, 'FUNC', True, {'GLOBAL', 'WEAK'})):
                    raise ValueError('actual emutls pthread provider closure is incomplete: ' + name)
            mode = 'OHOS_emulated_TLS_descriptor_accessor_runtime_provider_closure'
            details = {'runtime_provider': str(provider), 'runtime_provider_sha256': sha(provider),
                       'pthread_provider': str(libc), 'pthread_provider_sha256': sha(libc),
                       'compiler_provider_selection_command': provider_command, **call_details}
        else:
            raise ValueError('actual linked JPEG error string is neither native TLS nor verified emutls')
    return {'scope': 'actual_component_linkage_and_provider_closure_NOT_guest_thread_behavior',
            'mode': mode, 'PT_TLS_segment_count': segments, 'unstripped_sha256': sha(unstripped),
            'unstripped_elf': identity, 'inspection_commands': commands,
            'inspection_log': str(log), 'inspection_log_sha256': sha(log), **details}


def postcheck_completed_build(root, repo, staged, product, prefix, evidence):
    if not evidence.is_relative_to(staged):
        raise ValueError('postcheck must reference this owned scratch evidence')
    original = json.loads(evidence.read_text())
    permitted_correction = (original.get('error') ==
                            'actual linked TurboJPEG output lacks its required real TLS segment'
                            or (product == 'armv7a_virt' and original.get('error') ==
                                'actual JPEG error-string accessor does not call its emutls resolver'))
    if (original.get('scratch_source') != str(staged) or original.get('product') != product
            or not permitted_correction
            or any(original.get(field) != 0 for field in
                   ('gn_exit_code', 'link_exit_code', 'installer_repeat_exit_code', 'repeat_link_exit_code'))):
        raise ValueError('postcheck may only correct the isolated native-TLS-only validator assumption')
    for item in original['artifacts']:
        if sha(Path(item['path'])) != item['sha256']:
            raise ValueError('actual linked build artifact changed after the failed validator')
    if {name: sha(repo / name) for name in original['component_payload_sha256']} != original['component_payload_sha256']:
        raise ValueError('component snapshot changed after the actual completed build')
    if input_config_hashes(staged) != original['input_pipeline_config_before']:
        raise ValueError('pipeline source config changed after the actual completed build')
    output = staged / 'out' / product
    result = {'scope': 'corrected_TLS_validator_for_referenced_actual_build_NOT_new_build_or_guest_acceptance',
              'referenced_build_evidence': str(evidence), 'referenced_build_evidence_sha256': sha(evidence),
              'prior_TLS_validator_exit_code': original['validation_exit_code'],
              'prior_TLS_validator_error': original['error'],
              'all_referenced_GN_link_repeat_installer_repeat_link_exit_codes': 0,
              'first_artifact_behavior_gate_passed': False,
              'verified_generated_JPEG_headers': jpeg_generated_headers(staged, output),
              'jpeg_TLS': jpeg_tls_evidence(root, output, product, staged / (prefix + '-tls.log')),
              'validation_exit_code': 0}
    with (staged / (prefix + '-evidence.json')).open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--scratch-source', type=Path, required=True,
                        help='caller-owned, inactive tree with successful matching DSP evidence')
    parser.add_argument('--seed-source', type=Path,
                        help='clone this stopped original DSP tree into a new empty scratch source')
    parser.add_argument('--clone-only', action='store_true',
                        help='only prepare an evidenced clone; do not freeze/apply components or build')
    parser.add_argument('--postcheck-evidence', type=Path,
                        help='non-mutating TLS correction audit of matching completed Camera GN/link evidence')
    parser.add_argument('--product', choices=('arm64_virt', 'armv7a_virt', 'x86_64_virt'), required=True)
    parser.add_argument('--run-tag', required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9-]+', args.run_tag) or not 1 <= args.jobs <= 2:
        raise ValueError('run tag must be simple and compile jobs must be 1 or 2')
    root, repo, staged = (path.resolve() for path in (args.source_root, args.repo_root, args.scratch_source))
    if args.seed_source:
        cloned = clone_stopped_scratch(root, args.seed_source.resolve(), staged, args.product)
        if args.clone_only:
            print(json.dumps(cloned, indent=2))
            return 0
    elif args.clone_only:
        raise ValueError('clone-only requires an evidenced original seed source')
    prior = validate_tree(root, staged, args.product)
    if args.postcheck_evidence:
        return postcheck_completed_build(root, repo, staged, args.product,
                                         'camera-component-' + args.run_tag,
                                         args.postcheck_evidence.resolve())
    started = datetime.now(timezone.utc).isoformat()
    prefix = 'camera-component-' + args.run_tag
    for suffix in ('gn.log', 'link.log', 'installer-repeat.log', 'link-repeat.log',
                   'evidence.json', 'idl-inputs.json'):
        if (staged / (prefix + '-' + suffix)).exists():
            raise ValueError('refusing to overwrite prior Camera validation evidence')
    input_before = input_config_hashes(staged)
    libjpeg_inputs = copy_libjpeg_inputs(root, staged, prefix)
    idl_inputs = materialize_idl_inputs(root, staged)
    idl_manifest = staged / (prefix + '-idl-inputs.json')
    with idl_manifest.open('x') as stream:
        json.dump(idl_inputs, stream, indent=2)
        stream.write('\n')
    patch_hashes = {}
    payload_hashes = {}
    for component in COMPONENTS:
        for patch in sorted((repo / component).glob('*.patch')):
            patch_hashes[str(patch.relative_to(repo))] = sha(patch)
        for payload in sorted((repo / component).rglob('*')):
            if payload.is_file() and '__pycache__' not in payload.parts:
                payload_hashes[str(payload.relative_to(repo))] = sha(payload)
        for _ in range(2):
            subprocess.run(['bash', str(repo / component / 'apply.sh'),
                            '--source-root', str(staged)], check=True)
    subprocess.run(['bash', str(repo / 'patches/2in1/product_profile/apply.sh'),
                    '--source-root', str(staged), '--disable', '--product', args.product], check=True)
    subprocess.run(['bash', str(repo / 'patches/phone/product_profile/apply.sh'),
                    '--source-root', str(staged), '--product', args.product], check=True)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    environment['PATH'] = str(root / 'prebuilts/build-tools/linux-x86/bin') + os.pathsep + environment['PATH']
    python = root / 'prebuilts/python/linux-x86/3.11.4/bin/python3'
    if not python.is_file():
        python = Path(sys.executable)
    command = [str(python), str(staged / 'build/hb/main.py'), 'build', '--no-indep',
               '--product-name', args.product, '--prebuilt-sdk=true', '--build-target',
               'camera_hal', 'turbojpeg', '--build-only-gn', '--ccache=false', '--gn-args', 'device_type="phone"']
    log = staged / (prefix + '-gn.log')
    with log.open('x') as stream:
        generated = subprocess.run(command, cwd=staged, env=environment, stdout=stream, stderr=subprocess.STDOUT)
    result = {'scope': 'isolated_full_preload_load_GN_Camera_HAL_USB_VDI_HCB_link_NOT_guest_acceptance',
              'jpeg_scope': 'existing_OHOS_8bit_GN_dependencies_NOT_all_TurboJPEG_3_1_API_or_multiprecision',
              'product': args.product, 'device': 'phone', 'scratch_source': str(staged),
              'started_utc': started, 'python_version': sys.version,
              'environment': dict(zip(('sysname', 'nodename', 'release', 'version', 'machine'), os.uname())),
              'production_source_and_out_mounted_readonly': True,
              'preserved_seed_clone_provenance': json.loads((staged / CLONE_PROVENANCE).read_text())
                  if (staged / CLONE_PROVENANCE).exists() else None,
              'mutating_installer_owned_input_copy': libjpeg_inputs,
              'unmodified_materialized_source_IDL_count': len(idl_inputs),
              'source_IDL_manifest': str(idl_manifest), 'source_IDL_manifest_sha256': sha(idl_manifest),
              'prior_DSP_library_sha256': prior['library_sha256'],
              'peripheral_revision': PERIPHERAL_REVISION, 'patch_sha256': patch_hashes,
              'component_payload_sha256': payload_hashes,
              'gn_command': command, 'gn_exit_code': generated.returncode,
              'gn_log_sha256': sha(log), 'first_artifact_behavior_gate_passed': False}
    code = generated.returncode
    if code == 0:
        command = [str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'), '-w', 'dupbuild=warn',
                   '-C', str(staged / 'out' / args.product), '-j', str(args.jobs),
                   'camera_hal', 'usb_camera_vdi_impl', 'turbojpeg']
        link_log = staged / (prefix + '-link.log')
        with link_log.open('x') as stream:
            linked = subprocess.run(command, cwd=staged, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        code = linked.returncode
        result.update(link_command=command, link_exit_code=code, link_log_sha256=sha(link_log))
        if code == 0:
            repeat_command = [str(python), str(staged / 'third_party/libjpeg-turbo/install.py'),
                              '--gen-dir', str(staged / 'out' / args.product / 'gen/third_party/libjpeg-turbo'),
                              '--source-dir', str(staged / 'third_party/libjpeg-turbo')]
            repeat_log = staged / (prefix + '-installer-repeat.log')
            with repeat_log.open('x') as stream:
                repeated = subprocess.run(repeat_command, cwd=staged, env=environment,
                                          stdout=stream, stderr=subprocess.STDOUT)
            code = repeated.returncode
            result.update(installer_repeat_command=repeat_command,
                          installer_repeat_exit_code=code, installer_repeat_log_sha256=sha(repeat_log),
                          installer_repeat_generated_tree_not_precleaned_by_validator=True)
        if code == 0:
            repeat_link_log = staged / (prefix + '-link-repeat.log')
            with repeat_link_log.open('x') as stream:
                relinked = subprocess.run(command, cwd=staged, env=environment,
                                         stdout=stream, stderr=subprocess.STDOUT)
            code = relinked.returncode
            result.update(repeat_link_command=command, repeat_link_exit_code=code,
                          repeat_link_log_sha256=sha(repeat_link_log))
    result['input_pipeline_config_before'] = input_before
    result['input_pipeline_config_after'] = input_config_hashes(staged)
    if result['input_pipeline_config_before'] != result['input_pipeline_config_after']:
        result['error'] = 'Camera build unexpectedly changed source pipeline config files'
        code = 1
    if code == 0:
        output = staged / 'out' / args.product
        paths = list((output / 'hdf/drivers_peripheral_camera').glob('*.so'))
        paths += list((output / 'thirdparty/libjpeg-turbo').glob('libturbojpeg*.so'))
        paths += list((output / 'gen/drivers/peripheral/camera').rglob('*.hcb'))
        paths += list((output / 'gen/drivers/peripheral/camera/vdi_base/usb_camera/camera_config').glob('*.c'))
        paths += list((output / 'gen/drivers/peripheral/camera/vdi_base/usb_camera/camera_config').glob('*.h'))
        result['artifacts'] = [{'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                               for path in sorted(set(paths)) if path.is_file()]
        for item in result['artifacts']:
            if item['path'].endswith('.so'):
                try:
                    item.update(elf_identity(Path(item['path']), args.product))
                    if Path(item['path']).name == 'libturbojpeg.z.so':
                        item['TLS'] = jpeg_tls_evidence(root, output, args.product,
                                                       staged / (prefix + '-tls.log'))
                except ValueError as error:
                    result['error'] = str(error)
                    code = 1
                    break
        for required in ('libcamera_host_service_1.0.z.so', 'libcamera_external_usb_camera.so',
                         'libusb_camera_pipeline_core.z.so', 'config.c', 'params.c',
                         'config.h', 'params.h', 'camera_host_config.hcb', 'ipp_algo_config.hcb',
                         'libturbojpeg.z.so'):
            if not any(Path(item['path']).name == required for item in result['artifacts']):
                result['error'] = 'Ninja succeeded without required actual Camera artifact: ' + required
                code = 1
                break
        if code == 0:
            try:
                result['verified_generated_JPEG_headers'] = jpeg_generated_headers(staged, output)
            except (ValueError, OSError) as error:
                result['error'] = str(error)
                code = 1
        payload_after = {name: sha(repo / name) for name in payload_hashes}
        if payload_after != payload_hashes:
            result['error'] = 'Camera component payload changed during validation; rebuild from one snapshot'
            code = 1
    result['validation_exit_code'] = code
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    (staged / (prefix + '-evidence.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if code:
        if 'repeat_link_exit_code' in result:
            suffix = '-link-repeat.log'
        elif 'installer_repeat_exit_code' in result:
            suffix = '-installer-repeat.log'
        else:
            suffix = '-link.log' if 'link_exit_code' in result else '-gn.log'
        failure_log = staged / (prefix + suffix)
        print(failure_log.read_text()[-8000:])
    return code


if __name__ == '__main__':
    raise SystemExit(main())
