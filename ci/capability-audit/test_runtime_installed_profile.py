"""Pure negative contracts only; synthetic records never prove a guest pass."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import batch_system_build_runtime_helpers as p


ARCHIVE = '19eeedad8aabde7c8af3534fc643793cbb179bff4a630d13a430f6b3ece5ed4a'
IMAGE = '548ba51de90aa146519655b475ee8b5d4e6702256ec13da054ace0ce9673f44e'


def record(path, digest='a' * 64, size=128):
    return dict(path=path, sha256=digest, bytes=size)


def profile():
    value = dict(schema_version=1, kind='installed_product_runtime', product='arm64_virt', arch='arm64',
        device='phone', source_root='/ohos', archive=record('/runtime-profile/F.tar.gz', ARCHIVE),
        system_image=dict(record('/runtime-profile/system.img', IMAGE),
            archive_member='openharmony-qemu-arm64-arm64_virt-phone/images/system.img'),
        vendor_image=dict(record('/runtime-profile/vendor.img', 'b' * 64),
            archive_member='openharmony-qemu-arm64-arm64_virt-phone/images/vendor.img'), dsos={})
    for soname, partition, member in [('libc++.so', 'system', '/lib64/chipset-sdk-sp/libc++.so'),
            ('libc.so', 'system', '/lib/ld-musl-aarch64.so.1'),
            ('libasound.so', 'vendor', '/lib64/libasound.so'),
            ('libclang_rt.ubsan_minimal.so', 'system', '/lib64/chipset-sdk-sp/libclang_rt.ubsan_minimal.so')]:
        value['dsos'][soname] = dict(soname=soname,
            staged=record('/ohos/out/arm64_virt/packages/phone/' + partition + member),
            image_file=record('/runtime-profile/image-dumps/' + member.rsplit('/', 1)[-1]), image_member=member)
    return value


def helper():
    value = profile()
    inputs = [copy.deepcopy(e['staged']) for e in value['dsos'].values()]
    return dict(installed_runtime_profile=dict(source=record('/runtime-profile/runtime-profile.json'), profile=value),
        actual_link_inputs=inputs, actual_link_input_sonames={e['staged']['path']: s for s, e in value['dsos'].items()},
        DT_NEEDED=sorted(value['dsos']))


class InstalledRuntimeTests(unittest.TestCase):
    def test_replay_maps_required_GN_direct_selection_to_same_byte_installed_library(self):
        row = helper(); installed = row['installed_runtime_profile']['profile']['dsos']['libasound.so']['staged']
        original = dict(installed, path='/ohos/out/arm64_virt/thirdparty/alsa-lib/libasound.so')
        row.update(original_GN_direct_libraries=[original], linked_libraries=[installed],
                   actual_link_inputs=[installed])
        inputs = {r['path']: r for r in (original, installed)}
        with patch.object(p, 'elf_soname', return_value='libasound.so'):
            self.assertEqual(p.verify_direct_selection(row, inputs, {Path(original['path'])}), [Path(installed['path'])])
            for mutation in ('missing-GN', 'unbound-GN', 'wrong-SHA', 'missing-trace', 'old-path', 'legacy-retrofit'):
                bad = copy.deepcopy(row); bound = copy.deepcopy(inputs)
                if mutation == 'missing-GN': bad['original_GN_direct_libraries'] = []
                elif mutation == 'unbound-GN': bound.pop(original['path'])
                elif mutation == 'wrong-SHA':
                    bad['original_GN_direct_libraries'][0]['sha256'] = 'f' * 64
                    bound[original['path']] = bad['original_GN_direct_libraries'][0]
                elif mutation == 'missing-trace': bad['actual_link_inputs'] = []
                elif mutation == 'old-path': bad['linked_libraries'] = [original]
                else: bad.pop('installed_runtime_profile')
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    p.verify_direct_selection(bad, bound, {Path(original['path'])})

    def test_same_full_bytes_alias_and_derived_guest_paths(self):
        row = helper()
        p.validate_installed_profile(row['installed_runtime_profile']['profile'], archive_sha256=ARCHIVE, system_image_sha256=IMAGE)
        self.assertEqual(p.runtime_guest_paths(row, 'libc.so'), ('/system/lib/ld-musl-aarch64.so.1',))
        self.assertEqual(p.runtime_guest_paths(row, 'libasound.so'), ('/vendor/lib64/libasound.so',))
        expected = 'test -f /system/lib/ld-musl-aarch64.so.1 && test ! -L /system/lib/ld-musl-aarch64.so.1 && sha256sum /system/lib/ld-musl-aarch64.so.1'
        self.assertEqual(p.runtime_guest_script(row, 'libc.so'), expected)
        observed = p.verify_guest_runtime_raw(row, 'libc.so', 'a' * 64 + '  /system/lib/ld-musl-aarch64.so.1\n', archive_sha256=ARCHIVE)
        self.assertEqual(observed['soname'], 'libc.so')

    def test_wrong_package_or_image_binding_is_rejected(self):
        for key in ('archive', 'system_image'):
            value = profile(); value[key]['sha256'] = '0' * 64
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.validate_installed_profile(value, archive_sha256=ARCHIVE, system_image_sha256=IMAGE)
        with self.assertRaises(ValueError):
            p.verify_guest_runtime_raw(helper(), 'libc.so', 'a' * 64 + '  /system/lib/ld-musl-aarch64.so.1', archive_sha256='0' * 64)

    def test_staging_image_and_unproved_alias_mutations_fail(self):
        for mutation in ('sdk', 'sysroot', 'different-full-sha', 'different-size', 'wrong-member', 'free-guest-path',
                         'libc-symbol-proxy', 'same-image-file', 'unknown-schema', 'missing-vendor-image'):
            value = profile(); entry = value['dsos']['libc.so']
            if mutation == 'sdk': entry['staged']['path'] = '/ohos/prebuilts/ohos-sdk/libc.so'
            elif mutation == 'sysroot': entry['staged']['path'] = '/ohos/out/arm64_virt/obj/third_party/musl/libc.so'
            elif mutation == 'different-full-sha': entry['image_file']['sha256'] = 'c' * 64
            elif mutation == 'different-size': entry['image_file']['bytes'] += 1
            elif mutation == 'wrong-member': entry['image_member'] = '/lib64/libc.so'
            elif mutation == 'free-guest-path': entry['guest_paths'] = ['/lib/libc.so']
            elif mutation == 'libc-symbol-proxy':
                entry['staged']['path'] = '/ohos/out/arm64_virt/packages/phone/system/lib64/libc.so'; entry['image_member'] = '/lib64/libc.so'
            elif mutation == 'same-image-file': entry['image_file']['path'] = entry['staged']['path']
            elif mutation == 'unknown-schema': value['schema_version'] = True
            else: value.pop('vendor_image')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): p.validate_installed_profile(value)

    def test_no_legacy_receipt_retrofit_or_basename_acceptance(self):
        row = helper()
        for mutation in ('legacy', 'wrong-path-same-hash', 'old-unstripped-full-hash', 'missing-trace', 'wrong-soname', 'extra-old-input'):
            bad = copy.deepcopy(row); expected = p.runtime_link_records(bad, 'libc.so')[0]
            if mutation == 'legacy': bad.pop('installed_runtime_profile')
            elif mutation == 'wrong-path-same-hash': expected['path'] = '/ohos/out/arm64_virt/obj/third_party/musl/usr/lib/aarch64-linux-ohos/libc.so'
            elif mutation == 'old-unstripped-full-hash': expected['sha256'] = 'd' * 64
            elif mutation == 'missing-trace': bad['actual_link_inputs'].remove(expected)
            elif mutation == 'wrong-soname': bad['actual_link_input_sonames'][expected['path']] = 'libnot-libc.so'
            else:
                old = record('/ohos/out/arm64_virt/obj/third_party/musl/usr/lib/aarch64-linux-ohos/libc.so', 'f' * 64)
                bad['actual_link_inputs'].append(old); bad['actual_link_input_sonames'][old['path']] = 'libc.so'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): p.runtime_link_records(bad, 'libc.so')

    def test_raw_requires_exact_full_sha_and_installed_path(self):
        row = helper(); good = 'a' * 64 + '  /system/lib/ld-musl-aarch64.so.1'
        for raw in ('', good + '\n' + good, good + '\n\n', good.replace('a' * 64, 'b' * 64),
                    good.replace('/system/lib/ld-musl-aarch64.so.1', '/lib/ld-musl-aarch64.so.1'),
                    good.replace('  /', ' /'), 'claimed: ' + good, good + ' extra'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                p.verify_guest_runtime_raw(row, 'libc.so', raw, archive_sha256=ARCHIVE)

    def test_only_explicit_runtime_relinks_preserve_static_GN_runtime(self):
        selected = ['-lunwind', '-lc++', '../../clang/libclang_rt.ubsan_minimal.so', '-lc', 'libc++abi.a', 'libclang_rt.builtins.a', '-ldl', '-lm']
        actual = p.replace_runtime_libraries(selected, profile())
        self.assertEqual(actual[0], selected[0]); self.assertEqual(actual[4:], selected[4:])
        self.assertTrue(all('/packages/phone/system/' in actual[i] for i in (1, 2, 3)))
        for wrong in ([x for x in selected if x != '-lc'], selected + ['-lc++']):
            with self.assertRaises(ValueError): p.replace_runtime_libraries(wrong, profile())

    def test_SONAME_is_read_from_ELF_not_filename(self):
        # Minimal synthetic ELF exercises only the parser; never a real DSO proof.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'misleading-libc.so'
            data = bytearray(320); data[:7] = b'\x7fELF\x02\x01\x01'
            struct.pack_into('<HH', data, 16, 3, 183); struct.pack_into('<Q', data, 32, 64)
            struct.pack_into('<HH', data, 54, 56, 2)
            struct.pack_into('<IIQQQQQQ', data, 64, 1, 4, 0, 0x1000, 0, len(data), len(data), 8)
            struct.pack_into('<IIQQQQQQ', data, 120, 2, 4, 192, 0x10c0, 0, 64, 64, 8)
            struct.pack_into('<qQqQqQqQ', data, 192, 5, 0x1100, 10, 32, 14, 1, 0, 0)
            data[256:273] = b'\0libdifferent.so\0'
            path.write_bytes(data)
            self.assertEqual(p.elf_soname(path), 'libdifferent.so')
            data[256:288] = b'x' * 32; path.write_bytes(data)
            with self.assertRaises(ValueError): p.elf_soname(path)


if __name__ == '__main__': unittest.main()
