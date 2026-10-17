"""Host ZIP payload counterexamples, not HAP signature/profile verification."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import batch_system_live_inputs as live
import batch_apps_contact_picker_coordinator as shared


class LiveInputsSignedPayloadTests(unittest.TestCase):
    def payload(self):
        return {'module.json': json.dumps({'app': {'buildHash': 'HOSTONLY', 'bundleName': 'org.hostonly'}, 'module': {}}).encode(),
                'ets/modules.abc': b'HOSTONLY-ABC', 'resources.index': b'HOSTONLY-INDEX',
                'resources/rawfile/input.txt': b'HOSTONLY-resource'}

    def write(self, path, members, *, signed=False):
        with zipfile.ZipFile(path, 'w') as archive:
            for name, raw in members.items():
                info = zipfile.ZipInfo(name, (2026, 10, 18, 0, 0, 0) if signed else (2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED if signed else zipfile.ZIP_STORED
                info.external_attr = (0o100644 if signed else 0o100600) << 16
                info.comment = b'repacked-by-host-test' if signed else b''
                archive.writestr(info, raw)

    def test_shared_member_comparator_accepts_only_added_aligned_page_bitmap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); unsigned, signed = root/'unsigned.hap', root/'signed.hap'
            members = self.payload(); self.write(unsigned, members)
            self.write(signed, dict(members, **{'.pages.info': b'HOSTONLY'*20}), signed=True)
            # ZIP container metadata may change; actual compiled member bytes may not.
            live.verify_signed_payload(unsigned, signed)
            for name in members:
                altered = dict(members, **{'.pages.info': b'HOSTONLY'*20}); altered[name] += b'changed'
                self.write(signed, altered, signed=True)
                with self.subTest(name=name), self.assertRaises(ValueError): live.verify_signed_payload(unsigned, signed)

    def test_empty_misaligned_missing_extra_and_duplicate_member_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); unsigned, signed = root/'unsigned.hap', root/'signed.hap'
            members = self.payload(); self.write(unsigned, members)
            for bitmap in (b'', b'bad'):
                self.write(signed, dict(members, **{'.pages.info': bitmap}), signed=True)
                with self.subTest(bitmap=bitmap), self.assertRaises(ValueError): live.verify_signed_payload(unsigned, signed)
            variants = [members, dict(members, **{'.pages.info': b'HOSTONLY', 'other': b'changed'}),
                        {k: v for k, v in dict(members, **{'.pages.info': b'HOSTONLY'}).items() if k != 'resources.index'}]
            for altered in variants:
                self.write(signed, altered, signed=True)
                with self.assertRaises(ValueError): live.verify_signed_payload(unsigned, signed)
            self.write(signed, dict(members, **{'.pages.info': b'HOSTONLY'}), signed=True)
            with zipfile.ZipFile(signed, 'a') as archive: archive.writestr('ets/modules.abc', members['ets/modules.abc'])
            with self.assertRaises(ValueError): live.verify_signed_payload(unsigned, signed)

    def test_live_delegates_and_propagates_rejection_without_normalization(self):
        with patch.object(shared, 'verify_signed_payload', side_effect=ValueError('changed ABC')) as compare:
            with self.assertRaisesRegex(ValueError, 'changed ABC'):
                live.verify_signed_payload(Path('/host-only/unsigned'), Path('/host-only/signed'))
            compare.assert_called_once_with(Path('/host-only/unsigned'), Path('/host-only/signed'))

    def test_run_and_independent_replay_use_one_shared_strict_contract(self):
        here = Path(live.__file__).parent
        for name in ('batch_system_run_live_inputs.py', 'batch_system_verify_live_inputs.py'):
            source = (here/name).read_text()
            self.assertIn('verify_signed_payload(', source)
            self.assertNotIn('hap_payload(', source)


if __name__ == '__main__': unittest.main()
