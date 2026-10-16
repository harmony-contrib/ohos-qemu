"""Metadata rejection tests. Synthetic payloads are never native/guest proof."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_qemu_msdp_image as M
import qemu_msdp_build_witness as W


def fixture(root):
    for filename in M.LIBRARIES.values():(root / filename).write_bytes(b'synthetic metadata test NOT ELF')
    graphs = {};log = []
    for name, units in M.UNITS.items():
        lines = [];commands = {}
        for unit in units:
            source = '../../' + M.BASE + '/' + M.unit_source(unit);target = 'obj/' + M.BASE + '/' + unit
            lines.append('build ' + target + ': cxx ' + source + ' || synthetic.stamp')
            commands[unit] = ('../../prebuilts/clang/ohos/linux-x86_64/llvm/bin/clang++ --target=aarch64-linux-ohos '
                '-flto -fsanitize=cfi -fsanitize-cfi-cross-dso -fno-exceptions -fno-rtti -DDEVICE_STATUS_SENSOR_ENABLE '
                '-DDEVICE_STATUS_DISABLE_MOCK_FALLBACK -c ' + source + ' -o ' + target)
            log.append('[synthetic metadata fixture] CXX ' + target)
        filename = M.LIBRARIES[name]
        lines.append('build msdp/device_status/' + filename + ' ./lib.unstripped/msdp/device_status/' + filename +
                     ': solink ' + ' '.join('obj/' + M.BASE + '/' + u for u in units))
        path = root / (name + '.ninja');path.write_text('\n'.join(lines) + '\n')
        log.append('[synthetic metadata fixture] SOLINK msdp/device_status/' + filename)
        graphs[name] = {'sha256': M.file_sha256(path), 'objects_sha256': {u: 'b'*64 for u in units},
                        'compile_commands': commands, 'cross_dso_cfi': True}
    (root / 'build-log.txt').write_text('\n'.join(log) + '\n')
    value = {'schema_version': 1, 'product': 'arm64_virt', 'source_sha256': M.source_hashes(), 'recipe': M.recipe(),
             'features': dict(M.EXPECTED), 'first_artifact_behavior_gate_passed': False, 'graphs': graphs,
             'files_sha256': {p.name: M.file_sha256(p) for p in root.iterdir()}}
    witness = {'schema_version': 1, 'phase': 'completed', 'product': 'arm64_virt', 'source_sha256': M.source_hashes(),
               'recipe': M.recipe(), 'graphs': graphs, 'start_ns': 1, 'finished_ns': 3, 'nonce': 'c'*32,
               'files_sha256': {n: value['files_sha256'][n] for n in M.LIBRARIES.values()},
               'artifacts': {n: {'sha256': 'b'*64, 'mtime_ns': 2, 'bytes': 1} for n in W.outputs('arm64_virt')},
               'build_log': {'path': str(root / 'build-log.txt'), 'sha256': M.file_sha256(root / 'build-log.txt')}}
    for name, checksum in witness['files_sha256'].items():
        for prefix in ('msdp/device_status/', 'packages/phone/system/lib64/'):witness['artifacts'][prefix+name]['sha256'] = checksum
    (root / 'build-witness.json').write_text(json.dumps(witness))
    value['files_sha256']['build-witness.json'] = M.file_sha256(root / 'build-witness.json')
    return value


class MsdpImageInventory(unittest.TestCase):
    def test_source_features_graph_commands_cfi_witness_and_payload_are_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve();value = fixture(root)
            # Isolate metadata validation explicitly. Production always parses
            # real ELF segments/symbols and requires the actual CFI exports.
            with patch.object(M, 'elf'):
                M.check_inventory(value, 'arm64_virt', root)
                for case in ('source','recipe','sensor','mock','numeric','graph','object','command','cfi','extra','missing-witness'):
                    broken = copy.deepcopy(value)
                    if case in ('source','recipe'):broken['source_sha256' if case=='source' else case] = {}
                    elif case=='sensor':broken['features']['device_status_sensor_enable'] = False
                    elif case=='mock':broken['features']['device_status_allow_mock_fallback'] = True
                    elif case=='numeric':broken['features']['device_status_sensor_enable'] = 1
                    elif case=='graph':broken['graphs']['algo']['sha256'] = 'a'*64
                    elif case=='object':broken['graphs']['algo']['objects_sha256'].pop(next(iter(M.UNITS['algo'])))
                    elif case=='command':broken['graphs']['service']['compile_commands'][M.UNITS['service'][0]] = 'not-a-compiler -c nonexistent -o nowhere'
                    elif case=='cfi':broken['graphs']['service']['cross_dso_cfi'] = False
                    elif case=='missing-witness':broken['files_sha256'].pop('build-witness.json')
                    else:broken['files_sha256']['unbound.so'] = 'd'*64
                    with self.subTest(case=case), self.assertRaises(ValueError):M.check_inventory(broken,'arm64_virt',root)
                witness = json.loads((root/'build-witness.json').read_text())
                witness['artifacts'][W.outputs('arm64_virt')[0]]['mtime_ns'] = 0
                (root/'build-witness.json').write_text(json.dumps(witness));value['files_sha256']['build-witness.json'] = M.file_sha256(root/'build-witness.json')
                with self.assertRaises(ValueError):M.check_inventory(value,'arm64_virt',root)

    def test_complete_metadata_cannot_accept_64_byte_fake_DSO_even_without_cfi_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve();value = fixture(root)
            raw = bytearray(64);raw[:7] = b'\x7fELF\x02\x01\x01';struct.pack_into('<HH',raw,16,3,183)
            path = root/M.LIBRARIES['algo'];path.write_bytes(raw)
            for cfi in (False,True):
                with self.subTest(cfi=cfi),self.assertRaises(ValueError):M.elf(path,'arm64_virt',cfi)
            with self.assertRaises(ValueError):M.check_inventory(value,'arm64_virt',root)

    def test_begin_preserves_only_owned_generated_outputs_and_invalidates_old_witness(self):
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary).resolve();build=source/'out/arm64_virt';build.mkdir(parents=True)
            for name in W.outputs('arm64_virt'):
                path=build/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(name.encode())
            unrelated=build/'unrelated.o';unrelated.write_bytes(b'unchanged')
            (build/'qemu-msdp-build-witness.json').write_text('old attempt')
            with patch.object(M,'source_hashes',return_value={}):result=W.begin(source,'arm64_virt')
            self.assertEqual(unrelated.read_bytes(),b'unchanged')
            self.assertFalse((build/'qemu-msdp-build-witness.json').exists())
            for name in W.outputs('arm64_virt'):
                self.assertFalse((build/name).exists());self.assertEqual(Path(result['preserved'][name]['path']).read_bytes(),name.encode())


if __name__=='__main__':unittest.main()
