"""Whole-stack patch application against isolated generated source fixtures."""
import difflib
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest


HELPER = Path(__file__).resolve().parents[2] / 'patches/lib/apply_exact_component.py'


class ExactComponentApplyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root, self.component = self.base / 'source', self.base / 'component'
        self.project = self.root / 'foundation/component'
        self.project.mkdir(parents=True)
        self.component.mkdir()
        self.before = {'a.cpp': 'start\noriginal\nend\n', 'b.h': 'before\n'}
        self.after = {'a.cpp': 'start\nfinal\nend\n', 'b.h': 'after\n'}
        for name, value in self.before.items():
            (self.project / name).write_text(value)
        entries = [(name, hashlib.sha256(self.before[name].encode()).hexdigest(),
                    hashlib.sha256(self.after[name].encode()).hexdigest()) for name in self.before]
        (self.component / 'verify_source.py').write_text(
            'from exact_source_states import validate_component\n'
            "PROJECT='foundation/component'\nREVISION='fixture-with-no-git-metadata'\n"
            + 'FILES=' + repr(tuple(entries)) + '\n'
            + 'def validate(root, require_patched=False):\n'
            + '    return validate_component(root, PROJECT, REVISION, FILES, require_patched)\n')
        middle = 'start\nmiddle\nend\n'
        self.patch('0001-first.patch', 'a.cpp', self.before['a.cpp'], middle)
        self.patch('0002-overlap.patch', 'a.cpp', middle, self.after['a.cpp'])
        self.patch('0003-header.patch', 'b.h', self.before['b.h'], self.after['b.h'])

    def patch(self, filename, name, before, after):
        relative = 'foundation/component/' + name
        (self.component / filename).write_text(''.join(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True), fromfile='a/' + relative, tofile='b/' + relative)))

    def run_helper(self):
        return subprocess.run(['python3', str(HELPER), '--component-dir', str(self.component),
                               '--source-root', str(self.root)], capture_output=True, text=True)

    def values(self):
        return {name: (self.project / name).read_text() for name in self.before}

    def test_overlapping_stack_fresh_apply_and_whole_state_idempotence(self):
        first = self.run_helper()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.values(), self.after)
        second = self.run_helper()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.values(), self.after)

    def test_stale_or_forged_old_patch_markers_do_not_skip_original_sources(self):
        markers = self.root / '.ohos-qemu-patches'
        markers.mkdir()
        for patch in self.component.glob('*.patch'):
            (markers / (hashlib.sha256(patch.read_bytes()).hexdigest() + '.applied')).write_text('old marker\n')
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.values(), self.after)

    def test_unknown_and_mixed_sources_are_preserved_before_mutation(self):
        for value in ('unknown user edit\n', self.after['a.cpp']):
            (self.project / 'a.cpp').write_text(value)
            expected = self.values()
            result = self.run_helper()
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.values(), expected)
            self.assertFalse((self.root / '.ohos-qemu-patches').exists())

    def test_later_patch_failure_preflight_does_not_partly_apply_earlier_patch(self):
        self.patch('0002-overlap.patch', 'a.cpp', 'unrecognized\n', self.after['a.cpp'])
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.values(), self.before)

    def test_patch_target_outside_exact_component_is_rejected_without_modification(self):
        outside = self.project / 'outside.cpp'
        outside.write_text('preserve\n')
        self.patch('0004-outside.patch', 'outside.cpp', 'preserve\n', 'modified\n')
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(outside.read_text(), 'preserve\n')
        self.assertEqual(self.values(), self.before)

    def test_new_file_is_exact_and_repeatable_without_accepting_unknown_content(self):
        new_name = 'profile/qemu.xml'
        new_value = '<profile>qemu</profile>\n'
        verifier = self.component / 'verify_source.py'
        source = verifier.read_text()
        entry = (new_name, None, hashlib.sha256(new_value.encode()).hexdigest())
        source = source.replace("FILES=(", "FILES=(" + repr(entry) + ", ")
        verifier.write_text(source)
        target = self.project / new_name
        target.parent.mkdir()
        self.patch('0004-new-profile.patch', new_name, '', new_value)
        first = self.run_helper()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(target.read_text(), new_value)
        second = self.run_helper()
        self.assertEqual(second.returncode, 0, second.stderr)
        target.write_text('unknown\n')
        failed = self.run_helper()
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(target.read_text(), 'unknown\n')


if __name__ == '__main__':
    unittest.main()
