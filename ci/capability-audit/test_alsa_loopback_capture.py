"""Source transaction and executed launcher boundaries; not guest capture proof."""
import importlib.util
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('alsa_capture', ROOT /
    'patches/common/device/qemu/alsa_loopback_capture/apply.py')
CAPTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPTURE)


class AlsaCaptureSourceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = (b'CONFIG_SOUND=y\nCONFIG_SND=y\nCONFIG_SND_PCM=y\n'
                       b'CONFIG_SND_DRIVERS=y\nCONFIG_SND_PCI=y\nCONFIG_SND_ENS1370=y\n'
                       b'# CONFIG_SND_ALOOP is not set\nCONFIG_UNRELATED=y\n')
        for relative in CAPTURE.CONFIGS + (CAPTURE.JSON_PATH,):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(CAPTURE.ORIGINAL_JSON if relative == CAPTURE.JSON_PATH else self.config)
        self.revisions = patch.object(CAPTURE.subprocess, 'check_output', side_effect=
            lambda cmd, **kwargs: CAPTURE.REVISIONS[str(Path(cmd[2]).relative_to(self.root))] + '\n')
        self.revisions.start()
        self.addCleanup(self.revisions.stop)

    def snapshot(self):
        return {p: (self.root / p).read_bytes() for p in CAPTURE.CONFIGS + (CAPTURE.JSON_PATH,)}

    def test_repeat_preserves_render_and_unrelated_selections(self):
        result = CAPTURE.apply(self.root)
        expected = self.config.replace(b'# CONFIG_SND_ALOOP is not set', b'CONFIG_SND_ALOOP=y')
        self.assertEqual(len(result['files']), 4)
        for relative in CAPTURE.CONFIGS:
            self.assertEqual((self.root / relative).read_bytes(), expected)
        self.assertEqual((self.root / CAPTURE.JSON_PATH).read_bytes(), CAPTURE.FINAL_JSON)
        before = self.snapshot()
        CAPTURE.apply(self.root)
        self.assertEqual(before, self.snapshot())

    def test_unknown_json_or_each_kernel_dependency_rejects_before_any_write(self):
        cases = [self.config.replace(b'CONFIG_SND_DRIVERS=y', b'# CONFIG_SND_DRIVERS is not set'),
                 self.config.replace(b'CONFIG_SND_ENS1370=y', b'CONFIG_SND_ENS1370=m'),
                 self.config.replace(b'# CONFIG_SND_ALOOP is not set', b'CONFIG_SND_ALOOP=m'),
                 self.config + b'CONFIG_SND_ALOOP=y\n']
        path = self.root / CAPTURE.CONFIGS[-1]
        for data in cases:
            with self.subTest(data=data):
                path.write_bytes(data)
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    CAPTURE.apply(self.root)
                self.assertEqual(before, self.snapshot())
        path.write_bytes(self.config)
        (self.root / CAPTURE.JSON_PATH).write_bytes(CAPTURE.FINAL_JSON.replace(b'"captureDevice": 0', b'"captureDevice": 1'))
        before = self.snapshot()
        with self.assertRaises(ValueError):
            CAPTURE.apply(self.root)
        self.assertEqual(before, self.snapshot())

    def test_unknown_source_revision_and_symlink_preserve_all_inputs(self):
        before = self.snapshot()
        with patch.object(CAPTURE.subprocess, 'check_output', return_value='foreign\n'):
            with self.assertRaises(ValueError):
                CAPTURE.apply(self.root)
        self.assertEqual(before, self.snapshot())
        path = self.root / CAPTURE.CONFIGS[-1]
        external = self.root / 'external'
        path.rename(external)
        path.symlink_to(external)
        with self.assertRaises(ValueError):
            CAPTURE.apply(self.root)
        self.assertEqual(external.read_bytes(), self.config)
        self.assertEqual((self.root / CAPTURE.CONFIGS[0]).read_bytes(), self.config)

    def test_failed_publication_rolls_back_every_earlier_file(self):
        before = self.snapshot()
        writer = CAPTURE.atomic_write
        calls = 0

        def fail_second(path, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('injected publication failure')
            writer(path, data)

        with patch.object(CAPTURE, 'atomic_write', side_effect=fail_second):
            with self.assertRaises(OSError):
                CAPTURE.apply(self.root)
        self.assertEqual(before, self.snapshot())

    def test_canonical_repo_metadata_links_allow_source_transaction(self):
        for relative in CAPTURE.REVISIONS:
            git = self.root / relative / '.git'
            metadata = self.root / '.repo/projects' / (relative + '.git')
            metadata.mkdir(parents=True)
            git.symlink_to(os.path.relpath(metadata, git.parent))
        result = CAPTURE.apply(self.root)
        self.assertEqual(len(result['files']), 4)

    def test_foreign_or_symlinked_repo_metadata_target_preserves_sources(self):
        git = self.root / 'device/qemu/.git'
        before = self.snapshot()
        foreign = self.root / 'foreign-metadata'; foreign.mkdir()
        git.symlink_to(foreign)
        with self.assertRaisesRegex(ValueError, 'noncanonical repo metadata'):
            CAPTURE.apply(self.root)
        self.assertEqual(before, self.snapshot())
        git.unlink()
        metadata = self.root / '.repo/projects/device/qemu.git'
        metadata.parent.mkdir(parents=True)
        metadata.symlink_to(foreign, target_is_directory=True)
        git.symlink_to(os.path.relpath(metadata, git.parent))
        with self.assertRaisesRegex(ValueError, 'metadata target rejected'):
            CAPTURE.apply(self.root)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
