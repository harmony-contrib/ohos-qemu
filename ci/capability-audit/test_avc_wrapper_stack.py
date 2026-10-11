"""Real fixed wrapper bytes and whole-stack host checks, not guest proof."""
import base64
import gzip
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_avc_eos import REPO, COMPONENT, source

spec = importlib.util.spec_from_file_location('avc_wrapper_stack', REPO / 'patches/lib/apply_component_stack.py')
stack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stack)


def original():
    return gzip.decompress(base64.b64decode((Path(__file__).parent /
        'fixtures/avc_wrapper_original.cpp.gz.b64').read_text().strip(), validate=True))


class AvcWrapperStackTests(unittest.TestCase):
    def test_complete_real_pinned_wrapper_bytes_and_repair(self):
        value = original()
        self.assertEqual(hashlib.sha256(value).hexdigest(),
                         'd0ac01afa69a884d986342af5d79965dca8c4eb2e3fcceb8a6cd0059482c82ab')
        self.assertFalse(value.endswith(b'\n'))
        fixed = source.repaired_source(value.decode()).encode()
        self.assertEqual(hashlib.sha256(fixed).hexdigest(),
                         '7d97ae8e4fc86c31f7f0a7af019197d9a88b98364422812460ccb13e145457e0')

    def test_pristine_old_EOS_and_complete_states_with_stale_markers(self):
        before = original()
        fixed = source.repaired_source(before.decode()).encode()
        eos = source.repaired_source(before.decode(), False).encode()
        for value in (before, eos, fixed):
            with self.subTest(initial=hashlib.sha256(value).hexdigest()), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / 'foundation/multimedia/av_codec' / source.FILE
                target.parent.mkdir(parents=True)
                target.write_bytes(value)
                markers = root / '.ohos-qemu-patches'
                markers.mkdir()
                for numbered in COMPONENT.glob('*.patch'):
                    marker = hashlib.sha256(numbered.read_bytes()).hexdigest() + '.applied'
                    (markers / marker).write_text('stale old fixture marker\n')
                with patch.object(source.subprocess, 'check_output', side_effect=[source.REVISION + '\n', before]):
                    self.assertEqual(source.validate(root), value == fixed)
                for _ in range(2):
                    stack.run(COMPONENT, root)
                    self.assertEqual(target.read_bytes(), fixed)
                    with patch.object(source.subprocess, 'check_output', side_effect=[source.REVISION + '\n', before]):
                        self.assertTrue(source.validate(root, require_patched=True))

    def test_invalid_second_patch_does_not_apply_first_patch(self):
        before = original()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'foundation/multimedia/av_codec' / source.FILE
            target.parent.mkdir(parents=True)
            target.write_bytes(before)
            component = root / 'isolated-component'
            shutil.copytree(COMPONENT, component)
            patch_file = next(component.glob('0002-*.patch'))
            content = patch_file.read_text()
            self.assertIn('-    int32_t expect = 0;', content)
            patch_file.write_text(content.replace('-    int32_t expect = 0;', '-    int32_t absent_fixture = 123;'))
            with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                stack.run(component, root)
            self.assertEqual(target.read_bytes(), before)

    def test_exact_guards_enclose_marker_independent_stack(self):
        script = (COMPONENT / 'apply.sh').read_text()
        self.assertNotIn('apply_component_dir.sh', script)
        guard = script.index('python3 "${COMPONENT_DIR}/verify_source.py"')
        apply = script.index('python3 "${PATCH_ROOT}/lib/apply_component_stack.py"')
        complete = script.rindex('--require-patched')
        self.assertLess(guard, apply)
        self.assertLess(apply, complete)


if __name__ == '__main__':
    unittest.main()
