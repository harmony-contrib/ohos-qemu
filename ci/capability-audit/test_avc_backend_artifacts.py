"""Synthetic ELF/metadata fixtures only; never validates a real media backend."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'patches/lib'))
sys.path.insert(0, str(REPO / 'scripts'))
import avc_artifacts as avc
import verify_avc_backend_image as image


def fixture_elf(arch, symbols=avc.EXPORTS, needed='libc.so', soname='libavcenc_ohos.z.so'):
    elf_class, machine = avc.MACHINES[arch]
    is64 = elf_class == 2
    section_format = '<IIQQQQIIQQ' if is64 else '<IIIIIIIIII'
    section_size = struct.calcsize(section_format)
    header = bytearray(64)
    header[:6] = b'\x7fELF' + bytes((elf_class, 1))
    struct.pack_into('<HH', header, 16, 3, machine)
    struct.pack_into('<Q' if is64 else '<I', header, 40 if is64 else 32, 64)
    struct.pack_into('<HH', header, 58 if is64 else 46, section_size, 4)
    strings = b'\0'
    names = {}
    dependencies = [needed] if isinstance(needed, str) else list(needed)
    for name in sorted(symbols) + dependencies + [soname]:
        names[name] = len(strings)
        strings += name.encode() + b'\0'
    symformat = '<IBBHQQ' if is64 else '<IIIBBH'
    symbytes = b''
    for name in sorted(symbols):
        values = (names[name], 0x12, 0, 1, 0, 1) if is64 else (names[name], 0, 1, 0x12, 0, 1)
        symbytes += struct.pack(symformat, *values)
    dynformat = '<qQ' if is64 else '<iI'
    dynbytes = b''.join(struct.pack(dynformat, tag, value)
                        for tag, value in [*((1, names[name]) for name in dependencies),
                                           (14, names[soname]), (0, 0)])
    base = 64 + section_size * 4
    sections = [(0,) * 10,
                (0, 3, 0, 0, base, len(strings), 0, 0, 1, 0),
                (0, 11, 0, 0, base + len(strings), len(symbytes), 1, 0, 1, struct.calcsize(symformat)),
                (0, 6, 0, 0, base + len(strings) + len(symbytes), len(dynbytes), 1, 0, 1, struct.calcsize(dynformat))]
    return bytes(header) + b''.join(struct.pack(section_format, *section) for section in sections) + strings + symbytes + dynbytes


class AvcBackendArtifactTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'licenses').mkdir()
        notices = {}
        for name in avc.LICENSES:
            data = ('synthetic test notice only:' + name).encode()
            (self.root / 'licenses' / name).write_bytes(data)
            notices[name] = hashlib.sha256(data).hexdigest()
        self.license_patch = patch.dict(avc.LICENSE_HASHES, notices, clear=True)
        self.license_patch.start()
        self.addCleanup(self.license_patch.stop)
        self.manifest = dict(avc.PINS, schema_version=1, backend='real pinned M144 OpenH264 AVC encoder',
                             status='compile_only_not_new_image_runtime_acceptance', licenses=notices,
                             inputs={name: avc.checksum(REPO / 'patches/common/web/arkweb/m144_avc_encoder/files' / name)
                                     for name in avc.INPUTS}, artifacts={})
        for arch in avc.MACHINES:
            path = self.root / arch / 'libavcenc_ohos.z.so'
            path.parent.mkdir()
            path.write_bytes(fixture_elf(arch))
            self.manifest['artifacts'][arch + '/libavcenc_ohos.z.so'] = avc.verify_binary(path, arch)
        self.save()

    def save(self, manifest=None):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest if manifest is None else manifest))

    def test_three_abi_fixture_and_compile_only_scope(self):
        self.assertEqual(set(avc.validate(self.root, list(avc.MACHINES))), set(avc.MACHINES))
        for arch in avc.MACHINES:
            self.assertEqual(avc.validate(self.root, [arch])[arch]['needed'], ['libc.so'])

    def test_fixed_sources_and_status_cannot_be_substituted(self):
        for key, value in [('schema_version', True), ('status', 'runtime_pass'), ('backend', 'stub')] + [
                (key, 'master') for key in avc.PINS]:
            broken = copy.deepcopy(self.manifest)
            broken[key] = value
            self.save(broken)
            with self.assertRaises(ValueError): avc.validate(self.root, ['arm64'])

    def test_adapter_input_changes_require_rebuild(self):
        for name in avc.INPUTS:
            broken = copy.deepcopy(self.manifest)
            broken['inputs'][name] = '0' * 64
            self.save(broken)
            with self.assertRaisesRegex(ValueError, 'stale'): avc.validate(self.root, ['arm64'])

    def test_all_notices_are_required_and_pinned_not_self_asserted(self):
        for name in avc.LICENSES:
            broken = copy.deepcopy(self.manifest)
            broken['licenses'][name] = '0' * 64
            self.save(broken)
            with self.assertRaises(ValueError): avc.validate(self.root, ['arm64'])
        self.save()
        (self.root / 'licenses/compiler-rt-LICENSE.TXT').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'notice differs'): avc.validate(self.root, ['arm64'])

    def test_duplicate_provenance_is_rejected(self):
        (self.root / 'manifest.json').write_text('{"schema_version": 1, "schema_version": 1}')
        with self.assertRaisesRegex(ValueError, 'duplicate'): avc.validate(self.root, ['arm64'])

    def test_exact_binary_size_hash_and_native_abi(self):
        for key, value in (('size', True), ('sha256', '0' * 64), ('elf_class', 1), ('elf_machine', 40)):
            broken = copy.deepcopy(self.manifest)
            broken['artifacts']['arm64/libavcenc_ohos.z.so'][key] = value
            self.save(broken)
            with self.assertRaises(ValueError): avc.validate(self.root, ['arm64'])
        self.save()
        (self.root / 'arm64/libavcenc_ohos.z.so').write_bytes(fixture_elf('arm'))
        with self.assertRaises(ValueError): avc.validate(self.root, ['arm64'])

    def test_missing_extra_exports_or_host_dependencies_are_rejected(self):
        target = self.root / 'arm64/libavcenc_ohos.z.so'
        for data in (fixture_elf('arm64', symbols=avc.EXPORTS - {'EncodeProcess'}),
                     fixture_elf('arm64', symbols=avc.EXPORTS | {'fake_success'}),
                     fixture_elf('arm64', needed='libc.so.6'), fixture_elf('arm64', soname='libfake.so')):
            target.write_bytes(data)
            with self.assertRaises(ValueError): avc.verify_binary(target, 'arm64')

    def test_truncated_and_unterminated_dynamic_sections_fail(self):
        for data in (b'', fixture_elf('arm64')[:80], fixture_elf('arm')[:80]):
            with self.assertRaises(ValueError): avc.dynamic_contract(data)
        data = bytearray(fixture_elf('arm64'))
        struct.pack_into('<q', data, len(data) - 16, 1)
        with self.assertRaises(ValueError): avc.dynamic_contract(data)

    def test_image_dump_zero_exit_without_file_is_not_success(self):
        with patch.object(image.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'lacks the real'):
                image.verify_image(Path('/fixture/system.img'), 183, 'fixture-debugfs')
            self.assertEqual(run.call_count, 2)

    def test_image_reads_actual_library_provenance_and_all_notices(self):
        def dump(command, **kwargs):
            source, target = command[2].removeprefix('dump ').split(' ', 1)
            path = Path(target)
            if source == '/lib64/libavcenc_ohos.z.so': origin = self.root / 'arm64/libavcenc_ohos.z.so'
            elif source == '/etc/notice/qemu_avc/provenance.json': origin = self.root / 'manifest.json'
            elif source.startswith('/etc/notice/qemu_avc/'):
                origin = self.root / 'licenses' / source.rsplit('/', 1)[1]
            else: return
            path.write_bytes(origin.read_bytes())
        with patch.object(image.subprocess, 'run', side_effect=dump):
            result = image.verify_image(Path('/fixture/system.img'), 183, 'fixture-debugfs')
            self.assertEqual(result['backend']['sha256'], self.manifest['artifacts']['arm64/libavcenc_ohos.z.so']['sha256'])
            self.assertEqual(result['licenses'], self.manifest['licenses'])

    def test_preparation_and_full_package_checks_are_mandatory(self):
        launcher = (REPO / 'scripts/run_2in1_full_build_docker.sh').read_text()
        builder = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        verifier = (REPO / 'scripts/verify_device_type_package.sh').read_text()
        self.assertIn('"${REPO_ROOT}/patches/lib/avc_artifacts.py"', launcher)
        self.assertIn('-e QEMU_AVC_ARTIFACTS="${QEMU_AVC_ARTIFACTS}"', launcher)
        self.assertLess(builder.index('bash "${SOFTWARE_AVC_COMPONENT_SCRIPT}"'), builder.index('  write_source_preparation_metadata'))
        self.assertIn('"${SCRIPT_DIR}/verify_avc_backend_image.py"', verifier)
        self.assertIn('--system-image "${SYSIMG}" --machine "${ELF_MACHINE}"', verifier)
        self.assertIn('not media API behavior', verifier)
        component = (REPO / 'patches/common/foundation/multimedia/av_codec/software_avc/apply.sh').read_text()
        self.assertIn('AvcEnc_Typedef.h', component)
        self.assertIn('avc_eos/verify_source.py', component)
        self.assertLess(component.index('wrapper source/ABI differs'), component.index('apply_component_dir.sh'))


if __name__ == '__main__':
    unittest.main()
