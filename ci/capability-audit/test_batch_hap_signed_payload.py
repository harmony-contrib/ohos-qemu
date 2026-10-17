"""Host ZIP counterexamples; these inputs never count as signature or guest evidence."""
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from batch_apps_contact_picker_coordinator import verify_signed_payload


class SignedPayloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.payload = {'module.json': json.dumps({'app': {}, 'module': {}}).encode(),
                        'ets/modules.abc': b'HOST ONLY ABC',
                        'resources.index': b'HOST ONLY resources',
                        'resources/rawfile/input.bin': b'HOST ONLY input'}
        self.unsigned = self.hap('unsigned', self.payload)

    def hap(self, name, members):
        target = self.root / (name + '.hap')
        with warnings.catch_warnings(), zipfile.ZipFile(target, 'w') as archive:
            warnings.simplefilter('ignore', UserWarning)
            for member, data in (members.items() if isinstance(members, dict) else members):
                archive.writestr(member, data)
        return target

    def signed(self, **changes):
        value = dict(self.payload, **{'.pages.info': b'HOSTONLY'})
        value.update(changes)
        return self.hap('signed', value)

    def test_only_added_nonempty_word_aligned_bitmap_is_accepted(self):
        verify_signed_payload(self.unsigned, self.signed())

    def test_changed_abc_module_resources_and_rawfile_are_rejected(self):
        for name in self.payload:
            with self.subTest(member=name), self.assertRaises(ValueError):
                verify_signed_payload(self.unsigned, self.signed(**{name: b'changed'}))

    def test_absent_empty_or_misaligned_bitmap_is_rejected(self):
        for bitmap in (None, b'', b'1234567', b'123456789'):
            value = dict(self.payload)
            if bitmap is not None: value['.pages.info'] = bitmap
            with self.subTest(bitmap=bitmap), self.assertRaises(ValueError):
                verify_signed_payload(self.unsigned, self.hap('bad-bitmap', value))

    def test_extra_missing_and_duplicate_members_are_rejected(self):
        good = list(dict(self.payload, **{'.pages.info': b'HOSTONLY'}).items())
        variants = [good + [('extra.bin', b'extra')], good[1:],
                    good + [good[0]], good + [('.pages.info', b'HOSTONLY')]]
        for index, members in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                verify_signed_payload(self.unsigned, self.hap('bad-members', members))

    def test_preexisting_unsigned_bitmap_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_signed_payload(self.signed(), self.signed())

    def test_unsafe_member_on_both_sides_remains_rejected(self):
        for name in ('../escape', '/absolute', 'a\\b'):
            original = dict(self.payload, **{name: b'x'})
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify_signed_payload(self.hap('unsafe-plain', original),
                                      self.hap('unsafe-signed', dict(original, **{'.pages.info': b'HOSTONLY'})))

    def test_empty_or_missing_compiled_resource_is_rejected(self):
        for member in ('ets/modules.abc', 'resources.index'):
            for remove in (False, True):
                original = dict(self.payload)
                if remove: del original[member]
                else: original[member] = b''
                with self.subTest(member=member, remove=remove), self.assertRaises(ValueError):
                    verify_signed_payload(self.hap('empty-plain', original),
                                          self.hap('empty-signed', dict(original, **{'.pages.info': b'HOSTONLY'})))

    def test_symlink_member_is_rejected_even_when_payload_bytes_match(self):
        link = zipfile.ZipInfo('resource-link')
        link.create_system = 3
        link.external_attr = (0o120777 << 16)
        original = list(self.payload.items()) + [(link, b'resources.index')]
        with self.assertRaises(ValueError):
            verify_signed_payload(self.hap('link-plain', original),
                                  self.hap('link-signed', original + [('.pages.info', b'HOSTONLY')]))


if __name__ == '__main__': unittest.main()
