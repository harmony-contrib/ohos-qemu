"""Scratch isolation tests; fixture source does not establish real OHOS GN."""
from pathlib import Path
from types import SimpleNamespace
import os
import tempfile
import unittest
from unittest.mock import patch
from compile_audio_suite_dsp_gn import skeleton_foundation, validate_isolation, DSP, WINDOW


class DspGnIsolationTests(unittest.TestCase):
    def test_writable_production_mount_and_overlap_rejected(self):
        root = Path('/production/openharmony')
        for staged in (root, root / 'candidate', root.parent):
            with self.subTest(staged=staged), self.assertRaises(ValueError):
                validate_isolation(root, staged)
        for flags in ((0, os.ST_RDONLY), (os.ST_RDONLY, 0)):
            with self.subTest(flags=flags), patch('compile_audio_suite_dsp_gn.os.statvfs',
                    side_effect=[SimpleNamespace(f_flag=flag) for flag in flags]), self.assertRaises(ValueError):
                validate_isolation(root, Path('/scratch/candidate'))
        with patch('compile_audio_suite_dsp_gn.os.statvfs', return_value=SimpleNamespace(f_flag=os.ST_RDONLY)):
            validate_isolation(root, Path('/scratch/candidate'))

    def test_real_component_directories_and_only_two_writable_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            root, staged = Path(directory) / 'source', Path(directory) / 'candidate'
            staged.mkdir()
            for relative in (DSP, WINDOW, 'foundation/communication/netmanager_base'):
                path = root / relative
                path.mkdir(parents=True)
                (path / 'fixture').write_text('original')
            skeleton_foundation(root, staged)
            for relative in (DSP, WINDOW, 'foundation/communication/netmanager_base'):
                path = staged / relative
                self.assertTrue(path.is_dir())
                self.assertFalse(path.is_symlink())
                self.assertEqual((path / 'fixture').is_symlink(), relative not in (DSP, WINDOW))
            # A non-following directory walker still discovers every component.
            visited = {Path(path).relative_to(staged).as_posix() for path, _, _ in os.walk(staged)}
            self.assertIn('foundation/communication/netmanager_base', visited)
            for relative in (DSP, WINDOW):
                (staged / relative / 'fixture').write_text('generated scratch')
                self.assertEqual((root / relative / 'fixture').read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
