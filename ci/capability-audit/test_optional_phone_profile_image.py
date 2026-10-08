"""Host provenance boundary fixtures, never an ext-image/guest acceptance pass."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from optional_phone_profile_image import binding, verify_capture, FILES
from run_root_probe import digest
import optional_phone_profile_image as capture_module
from verify_optional_phone_profile_results import OPTIONAL, POSITIVE


class ImageCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='profile-image-host-fixture-')
        runtime = Path(self.temporary.name)
        self.root = runtime / 'optional-phone-profile'
        self.root.mkdir()
        self.image = runtime / 'boot/extract/archive/images/system.img'
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b'host-image-digest-fixture-NOT-ext-filesystem-or-guest')
        syscap = self.root / 'actual-image-syscap.json'
        syscap.write_text(json.dumps({'components': [{'syscap': list(POSITIVE)}]}))
        profile = {'device_type': 'phone', 'resolved_syscap_sha256': digest(syscap),
            'qemu_adaptations': {'required_official_syscaps': list(POSITIVE),
                'explicit_qemu_requirements': [], 'enabled_required_syscaps': list(POSITIVE),
                'excluded_unsupported_syscaps': list(OPTIONAL)}}
        self.entry = {'image_path': '/etc/syscap.json', 'image_inode': 17,
            'image_path_aliases': ['/etc/syscap.json', '/system/etc/syscap.json']}
        package = self.image.parent.parent
        (package / FILES[0]).write_text(json.dumps(profile))
        report = {'status': 'pass', 'arch': 'arm64', 'device': 'phone', 'system_image_sha256': digest(self.image),
            'device_profile_sha256': digest(package / FILES[0]),
            'actual_syscap_sha256': digest(syscap), 'actual_syscap_image_entry': self.entry}
        (package / FILES[1]).write_text(json.dumps(report))
        initial = {'images/system.img': digest(self.image),
            **{name: digest(package / name) for name in FILES}}
        self.boot = {'status': 'pass', 'purpose': 'acceptance', 'archive_sha256': 'c' * 64,
            'test_environment': {'boot_id': 'owned-boot-fixture', 'guest_arch': 'arm64',
                'device_type': 'phone', 'external_keepalive': False,
                'freshly_extracted_directory': str(package)},
            'initial_package_file_sha256': initial}
        for name in FILES:
            (self.root / name).write_bytes((package / name).read_bytes())
        self.document = {'system_image': str(self.image), 'system_image_sha256': digest(self.image),
            'capture_sha256': digest(Path(capture_module.__file__)),
            'actual_syscap_image_entry': self.entry,
            'image_contract_files': {name: {'file': str(self.root / name),
                'sha256': digest(self.root / name)} for name in (*FILES, syscap.name)}}

    def tearDown(self):
        self.temporary.cleanup()

    def verify(self, boot=None, document=None):
        return verify_capture(document or self.document, self.root, boot or self.boot,
            'c' * 64, 'arm64', 'owned-boot-fixture')

    def test_exact_immutable_binding_fixture_is_replayable_not_behavior(self):
        profile, syscap = self.verify()
        self.assertEqual(profile['device_type'], 'phone')
        self.assertEqual(syscap['components'][0]['syscap'], list(POSITIVE))

    def test_other_archive_boot_arch_profile_or_external_keepalive_reject(self):
        for case in ('archive', 'boot', 'arch', 'device', 'purpose', 'status', 'keepalive', 'directory'):
            boot = deepcopy(self.boot)
            with self.subTest(case=case):
                if case == 'archive': boot['archive_sha256'] = 'd' * 64
                elif case == 'purpose': boot['purpose'] = 'diagnostic'
                elif case == 'status': boot['status'] = 'fail'
                else:
                    key = {'boot': 'boot_id', 'arch': 'guest_arch', 'device': 'device_type',
                        'keepalive': 'external_keepalive', 'directory': 'freshly_extracted_directory'}[case]
                    boot['test_environment'][key] = True if case == 'keepalive' else 'wrong'
                with self.assertRaises(ValueError): self.verify(boot=boot)

    def test_changed_packaged_originals_cannot_be_blessed_by_captured_metadata(self):
        for name in ('images/system.img', *FILES):
            path = self.image.parent.parent / name
            original = path.read_bytes()
            with self.subTest(name=name):
                path.write_bytes(original + b' ')
                with self.assertRaises(ValueError): self.verify()
                path.write_bytes(original)

    def test_captured_paths_hashes_contents_and_inode_are_strict(self):
        for case in ('path', 'hash', 'missing', 'unknown', 'syscap', 'inode', 'capture', 'image'):
            value = deepcopy(self.document)
            with self.subTest(case=case):
                if case == 'path': value['image_contract_files'][FILES[0]]['file'] = '/wrong'
                elif case == 'hash': value['image_contract_files'][FILES[0]]['sha256'] = '0' * 64
                elif case == 'missing': value['image_contract_files'].pop(FILES[0])
                elif case == 'unknown': value['image_contract_files']['unknown'] = {}
                elif case == 'syscap': value['image_contract_files']['actual-image-syscap.json']['sha256'] = '0' * 64
                elif case == 'inode': value['actual_syscap_image_entry']['image_inode'] += 1
                elif case == 'capture': value['capture_sha256'] = '0' * 64
                elif case == 'image': value['system_image_sha256'] = '0' * 64
                with self.assertRaises(ValueError): self.verify(document=value)

    def test_captured_file_symlink_to_identical_bytes_still_rejects(self):
        path = self.root / FILES[0]
        path.unlink()
        path.symlink_to(self.image.parent.parent / FILES[0])
        with self.assertRaises(ValueError): self.verify()


if __name__ == '__main__': unittest.main()
