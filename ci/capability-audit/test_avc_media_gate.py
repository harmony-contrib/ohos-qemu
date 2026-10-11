"""Synthetic provenance/gate mutation tests, not compiler or guest evidence."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))

from avc_media_contract import ABIS, HEADERS, SCOPE, inputs, source, sha
from test_verify_avc_media_results import RUN, UID, IDENTITY, rows, render
import verify_avc_media_results as verifier


def elf(arch='arm64'):
    _, _, machine, class_ = ABIS[arch]
    data = bytearray(64)
    data[:6] = b'\x7fELF' + bytes((class_, 1))
    struct.pack_into('<HH', data, 16, 3, machine)
    return bytes(data) + b'Synthetic fixture, not executable or compiler proof.'


class AvcMediaGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='avc-gate-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project, self.sdk = self.root / 'project', self.root / 'sdk'
        page = self.project / 'entry/src/main/ets/pages/Index.ets'
        page.parent.mkdir(parents=True)
        page.write_text(source(RUN))
        (self.project / 'entry/src/main/module.json5').write_text(json.dumps({'module': {'requestPermissions': []}}))
        header = self.sdk / 'native/sysroot/usr/include/multimedia/player_framework'
        header.mkdir(parents=True)
        for name in HEADERS:
            (header / name).write_text('// Synthetic SDK unit fixture only: ' + name)
        for name in ('native', 'ets'):
            path = self.sdk / name
            path.mkdir(exist_ok=True)
            (path / 'oh-uni-package.json').write_text(json.dumps({'apiVersion': '26', 'releaseType': 'Release',
                                                                'platformVersion': '26.0.0'}))
        binary = self.project / 'entry/libs/arm64-v8a/libavcmediaprobe.so'
        binary.parent.mkdir(parents=True)
        binary.write_bytes(elf())
        self.files = {'result': self.root / 'verified-result.json', 'raw_results': self.root / 'results.log',
            'ordinary_identity': self.root / 'application-identity.json', 'hap': self.root / 'ordinary-probe-signed.hap',
            'compiled_contract_inputs': self.project / 'avc-media-probe-inputs.json'}
        self.files['compiled_contract_inputs'].write_text(json.dumps(inputs(self.project, self.sdk, 'arm64', RUN)))
        self.files['raw_results'].write_text(render(rows()))
        self.files['ordinary_identity'].write_text(IDENTITY)
        self.hap(elf())
        self.value = {'status': 'pass', 'scope': SCOPE, 'failures': [], 'archive_sha256': 'a' * 64,
            'arch': 'arm64', 'run_id': RUN, 'first_artifact_behavior_gate_passed': False,
            'hardware_codec_tested': False, 'hevc_tested': False, 'mathematical_CBR_conformance_tested': False,
            'verifier_sha256': sha(Path(verifier.__file__)), 'results_sha256': sha(self.files['raw_results']),
            'application_identity_sha256': sha(self.files['ordinary_identity']),
            'compiled_inputs_sha256': sha(self.files['compiled_contract_inputs']),
            'results': verifier.verify(render(rows()), RUN, IDENTITY), 'result': verifier.result(rows())}
        self.document = {'status': 'pass', 'persona': 'avc-media', 'failures': [], 'device': 'phone',
            'target': 'unit-target', 'archive_sha256': 'a' * 64, 'boot_id': 'unit-boot', 'arch': 'arm64',
            'run_id': RUN, 'ordinary_uid': UID, 'first_artifact_behavior_gate_passed': False,
            'result': str(self.files['result'])}
        self.rehash()

    def hap(self, data, name='libs/arm64-v8a/libavcmediaprobe.so'):
        with zipfile.ZipFile(self.files['hap'], 'w') as archive:
            archive.writestr(name, data)

    def rehash(self):
        self.files['result'].write_text(json.dumps(self.value))
        self.document.update({key + '_sha256': sha(path) for key, path in self.files.items()})

    def check(self, document=None):
        return verifier.verify_evidence(document or self.document, 'a' * 64, 'unit-boot', 'arm64',
                                        'phone', 'unit-target')

    def test_default_selection_evidence_is_narrow_and_raw_replayed(self):
        actual = self.check()
        self.assertEqual(actual['closed'], ['behavior:media-video-encoder-creation-failure'])
        self.assertEqual(actual['observations'], 473)
        self.assertEqual(actual['challenged_frames'], 48)
        self.assertEqual(actual['encoder_MIME_cycles'], 6)
        self.assertIn('HEVC_encoding', actual['not_claimed'])
        self.assertIn('transcoding_pipelines', actual['not_claimed'])

    def test_wrong_archive_boot_abi_profile_target_or_identity_rejected(self):
        for key, value in (('archive_sha256', 'b' * 64), ('boot_id', 'old'), ('arch', 'x86_64'),
                           ('device', '2in1'), ('target', 'another-VM'), ('ordinary_uid', 0),
                           ('run_id', 'b' * 32), ('first_artifact_behavior_gate_passed', True)):
            document = dict(self.document, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(document)

    def test_each_evidence_file_hash_is_required(self):
        for key in self.files:
            document = dict(self.document, **{key + '_sha256': '0' * 64})
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(document)

    def test_rehashed_wrong_binary_or_wrong_HAP_ABI_is_not_proof(self):
        for data, name in ((elf('x86_64'), 'libs/arm64-v8a/libavcmediaprobe.so'),
                           (elf() + b'wrong code', 'libs/arm64-v8a/libavcmediaprobe.so'),
                           (elf(), 'libs/x86_64/libavcmediaprobe.so')):
            self.hap(data, name)
            self.rehash()
            with self.subTest(name=name, data=data[-10:]), self.assertRaises(ValueError): self.check()

    def test_rehashed_raw_advertisement_or_creation_path_failure_rejected(self):
        for name in ('avc_encoder_default_is_software', 'hevc_encoder_unadvertised',
                     'legacy_rk_encoder_avc_rejected', 'encoder_creation_path', 'decoder_creation_path'):
            changed = rows()
            index = next(index for index, row in enumerate(changed) if row.get('name') == name)
            changed[index]['actual'] = 0
            self.files['raw_results'].write_text(render(changed))
            self.value['results_sha256'] = sha(self.files['raw_results'])
            self.rehash()
            with self.subTest(name=name), self.assertRaises(ValueError): self.check()

    def test_sdk_source_permission_and_native_compile_command_mutations_rejected(self):
        original = json.loads(self.files['compiled_contract_inputs'].read_text())
        for key, value in (('native_compile_command', ['true']), ('source_sha256', {}),
                           ('request_permissions', ['ohos.permission.INTERNET']), ('contract_sha256', '0' * 64)):
            changed = dict(original, **{key: value})
            self.files['compiled_contract_inputs'].write_text(json.dumps(changed))
            self.value['compiled_inputs_sha256'] = sha(self.files['compiled_contract_inputs'])
            self.rehash()
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()
        self.files['compiled_contract_inputs'].write_text(json.dumps(original))
        module = self.project / 'entry/src/main/module.json5'
        module.write_text(json.dumps({'module': {'requestPermissions': [{'name': 'ohos.permission.INTERNET'}]}}))
        with self.assertRaises(ValueError): self.check()

    def test_no_HEVC_hardware_or_full_media_overclaim_can_be_rehashed(self):
        original = deepcopy(self.value)
        for key, value in (('hevc_tested', True), ('hardware_codec_tested', True),
                           ('result', {'closed': ['all-media']}), ('verifier_sha256', '0' * 64)):
            self.value = dict(original, **{key: value})
            self.rehash()
            with self.subTest(key=key), self.assertRaises(ValueError): self.check()

    def test_new_gate_requires_default_AVC_on_both_profiles_not_old_SOFTWARE_test(self):
        from verify_first_artifact_gate import REQUIRED_CHECKS
        self.assertIn('avc-media', REQUIRED_CHECKS)
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("check('avc-media', path, [record])", suite)
        native = Path(__file__).with_name('probes') / 'avc_media.cpp'
        text = native.read_text()
        self.assertIn('OH_VideoEncoder_CreateByMime(OH_AVCODEC_MIMETYPE_VIDEO_AVC)', text)
        self.assertIn('OH_VideoDecoder_CreateByMime(OH_AVCODEC_MIMETYPE_VIDEO_AVC)', text)
        self.assertNotIn('"software_encoder_create"', text)


if __name__ == '__main__':
    unittest.main()
