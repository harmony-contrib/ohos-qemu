"""Exact patch/map/package guard regressions, not QEMU PCM evidence."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/vendor/ohemu/audio_policy_7'
sys.path.insert(0, str(ROOT / 'scripts'))
from verify_qemu_audio_policy_image import contract, verify_image


def patch_images():
    text = (COMPONENT / '0001-map-normal-audio-routes-with-7.0-pipe-schema.patch').read_text()
    before, after = [], []
    for line in text.splitlines():
        if line.startswith(('--- a/', '+++ b/')):
            continue
        if line.startswith('-'):
            before.append(line[1:])
        if line.startswith('+'):
            after.append(line[1:])
    return ('\n'.join(before) + '\n').encode(), ('\n'.join(after) + '\n').encode()


class AudioPolicy7Tests(unittest.TestCase):
    def candidate(self):
        return ET.fromstring(patch_images()[1])

    def assert_rejected(self, root):
        with self.assertRaises(ValueError):
            contract.validate_document(ET.tostring(root), require_hash=False)

    def test_exact_original_and_candidate_patch_bytes(self):
        before, after = patch_images()
        self.assertEqual(hashlib.sha256(before).hexdigest(), contract.ORIGINAL_SHA256)
        self.assertEqual(hashlib.sha256(after).hexdigest(), contract.REPAIRED_SHA256)
        result = contract.validate_document(after)
        self.assertEqual((result['pipes'], result['device_routes']), (5, 8))
        with self.assertRaises(ValueError):
            contract.validate_document(before)

    def test_missing_and_wrong_normal_route_flags_rejected(self):
        for value in (None, 'AUDIO_OUTPUT_FLAG_FAST', 'AUDIO_FLAG_NORMAL', '0'):
            root = self.candidate()
            attributes = root.find('./adapters/adapter/pipes/pipe/attributes')
            flag = attributes.find('./attribute[@name="flag"]')
            if value is None:
                attributes.remove(flag)
            else:
                flag.set('value', value)
            self.assert_rejected(root)

    def test_missing_unknown_wrong_role_and_incomplete_support_devices_rejected(self):
        for value in ('', 'No_Device', 'Speaker_Out', 'Builtin_Mic_In'):
            root = self.candidate()
            root.find('./adapters/adapter/pipes/pipe/streamProps/streamProp').set('supportDevices', value)
            self.assert_rejected(root)

    def test_device_side_only_mapping_does_not_satisfy_7_0(self):
        root = self.candidate()
        for prop in root.findall('.//streamProp'):
            prop.attrib.pop('supportDevices')
        self.assert_rejected(root)

    def test_ignored_buffer_size_and_invalid_frames_rejected(self):
        for value in ('0', '-4', '3'):
            root = self.candidate()
            root.find('.//streamProp').set('bufferSize', value)
            self.assert_rejected(root)
        root = self.candidate()
        prop = root.find('.//streamProp')
        prop.set('buffer_size', prop.attrib.pop('bufferSize'))
        self.assert_rejected(root)

    def test_broken_reciprocal_device_mapping_rejected(self):
        root = self.candidate()
        root.find('.//device').set('supportPipes', 'nonexistent')
        self.assert_rejected(root)

    def test_pipe_deletion_duplicate_and_default_change_rejected(self):
        root = self.candidate()
        pipes = root.find('./adapters/adapter/pipes')
        pipes.remove(pipes[0])
        self.assert_rejected(root)
        root = self.candidate()
        pipes = root.find('./adapters/adapter/pipes')
        pipes.append(ET.fromstring(ET.tostring(pipes[0])))
        self.assert_rejected(root)
        root = self.candidate()
        root.find('./globalConfigs/defaultOutput').set('device', 'PretendSpeaker')
        self.assert_rejected(root)

    def test_parser_input_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').mkdir()
            (root / 'real/file').write_bytes(b'unchanged')
            (root / 'owned').symlink_to(root / 'real', target_is_directory=True)
            with self.assertRaises(ValueError):
                contract.real_file(root, 'owned/file')
            self.assertEqual((root / 'real/file').read_bytes(), b'unchanged')

    def test_debugfs_zero_without_actual_file_is_not_success(self):
        with patch('verify_qemu_audio_policy_image.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'unambiguous'):
                verify_image(Path('/fixture/chip_prod.img'), 'fixture-debugfs')
            self.assertEqual(run.call_count, 2)

    def test_image_reads_one_exact_runtime_config_and_rejects_ambiguity(self):
        data = patch_images()[1]
        def dump(command, **kwargs):
            source, target = command[2].split()[1:]
            if source.startswith('/etc/'):
                Path(target).write_bytes(data)
        with patch('verify_qemu_audio_policy_image.subprocess.run', side_effect=dump):
            result = verify_image(Path('/fixture/chip_prod.img'), 'fixture-debugfs')
            self.assertEqual(result['configuration']['device_routes'], 8)
        def ambiguous(command, **kwargs):
            Path(command[2].split()[-1]).write_bytes(data)
        with patch('verify_qemu_audio_policy_image.subprocess.run', side_effect=ambiguous):
            with self.assertRaisesRegex(ValueError, 'unambiguous'):
                verify_image(Path('/fixture/chip_prod.img'), 'fixture-debugfs')

    def test_source_guard_rejects_unknown_edits_before_modifying(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xml = root / 'vendor/ohemu' / contract.XML_PATH
            xml.parent.mkdir(parents=True)
            xml.write_bytes(b'owned user edit')
            framework = root / 'foundation/multimedia/audio_framework'
            for relative in contract.FRAMEWORK_INPUTS:
                target = framework / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'not the pinned parser')
            with patch.object(contract.subprocess, 'check_output', side_effect=[
                    contract.VENDOR_REVISION, patch_images()[0], contract.FRAMEWORK_REVISION]):
                with self.assertRaisesRegex(ValueError, 'semantics changed'):
                    contract.validate_source(root)
            self.assertEqual(xml.read_bytes(), b'owned user edit')

    def test_builder_and_full_package_require_policy_before_traversal(self):
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        hook = 'bash "${QEMU_AUDIO_POLICY_7_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'
        self.assertLess(builder.index(hook), builder.index('  configure_qemu_device_profile\n'))
        verifier = (ROOT / 'scripts/verify_device_type_package.sh').read_text()
        self.assertIn('"${SCRIPT_DIR}/verify_qemu_audio_policy_image.py"', verifier)
        self.assertIn('--chip-prod-image "${PACKAGE}/images/chip_prod.img"', verifier)
        self.assertIn('offline only, not PCM behavior', verifier)


if __name__ == '__main__':
    unittest.main()
