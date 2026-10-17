#!/usr/bin/env python3
"""Exercise exact whole-byte/HEAD guards on all 28 actual original source files.

Only the private Git HEAD is substituted. Production full-file state hashes
remain unchanged and are recomputed from every complete original/prefix/final.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from batch_location_runtime_fixture import COMPONENT, FIXTURE, PREFIX, ROOT, function, runtime_sources


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest() if text is not None else None


class RuntimeSourceGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.states = {
            'original': json.loads(FIXTURE.read_text())['files'],
            **{'prefix_' + str(index): runtime_sources(prefix=index)
               for index in range(1, len(list(COMPONENT.glob('*.patch'))))},
            'final': runtime_sources(),
        }

    def fixture(self, directory, state='original'):
        root = Path(directory) / 'source'
        project = root / 'base/location/location'
        project.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        subprocess.run(['git', '-C', str(project), '-c', 'user.name=Location fixture', '-c',
                        'user.email=location-fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'Fixture HEAD'], check=True)
        head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        component = Path(directory) / 'fixture' / COMPONENT.relative_to(ROOT)
        shutil.copytree(COMPONENT, component)
        shutil.copytree(ROOT / 'patches/lib', Path(directory) / 'fixture/patches/lib')
        manifest = json.loads((component / 'source_states.json').read_text())
        pinned = manifest['revision']
        manifest['revision'] = head
        self.assertEqual(manifest['states'], {name: {path: digest(text) for path, text in values.items()}
                                              for name, values in self.states.items()})
        (component / 'source_states.json').write_text(json.dumps(manifest))
        verifier = component / 'verify_source.py'
        verifier.write_text(verifier.read_text().replace(pinned, head))
        for name, text in self.states[state].items():
            target = root / (PREFIX + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if text is not None:
                target.write_text(text)
        return root, component

    def apply(self, root, component):
        return subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(root)],
                              capture_output=True, text=True)

    def contents(self, root):
        return {name: (root / (PREFIX + name)).read_bytes() if (root / (PREFIX + name)).exists() else None for name in self.states['original']}

    def test_all_legal_prefixes_and_idempotence(self):
        for state in self.states:
            with self.subTest(state=state), tempfile.TemporaryDirectory(prefix='batch-location-guard-') as directory:
                root, component = self.fixture(directory, state)
                result = self.apply(root, component)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                expected = {name: text.encode() for name, text in self.states['final'].items()}
                self.assertEqual(expected, self.contents(root))
                result = self.apply(root, component)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(expected, self.contents(root))

    def test_unknown_and_mixed_edits_rejected_before_mutation(self):
        target = 'services/location_locator/locator/source/locator_required_data_manager.cpp'
        for mixed in [False, True]:
            with self.subTest(mixed=mixed), tempfile.TemporaryDirectory(prefix='batch-location-guard-') as directory:
                root, component = self.fixture(directory)
                path = root / (PREFIX + target)
                path.write_text(self.states['final'][target] if mixed else path.read_text() + '\n// unrelated edit\n')
                before = self.contents(root)
                self.assertNotEqual(0, self.apply(root, component).returncode)
                self.assertEqual(before, self.contents(root))
                self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_superseded_cf32293_strict_candidate_is_not_a_legal_prefix(self):
        """A changed patch7 cannot silently accept the old strict candidate."""
        contract = json.loads((Path(__file__).parent /
            'fixtures/batch_location/location_accuracy_compatibility_before.json').read_text())
        name = 'services/location_gnss/gnss/source/gnss_event_callback.cpp'
        old = self.states['prefix_6'][name]
        callback = function(old, 'int32_t GnssEventCallback::ReportLocation(')
        strict = old.replace(callback, contract['initial_strict_callback']['text'])
        strict = strict.replace('#include <singleton.h>', '#include <cmath>\n#include <singleton.h>', 1)
        locator_name = 'services/location_locator/locator/source/locator_ability.cpp'
        initial_locator = self.states['final'][locator_name]
        accuracy_guard = '        (location->GetFieldValidity() & LOCATION_FIELD_HORIZONTAL_ACCURACY_VALID) == 0 ||\n'
        self.assertEqual(1, initial_locator.count(accuracy_guard))
        initial_locator = initial_locator.replace(accuracy_guard, '', 1)
        with tempfile.TemporaryDirectory(prefix='batch-location-superseded-candidate-') as directory:
            root, component = self.fixture(directory, state='prefix_6')
            (root / PREFIX / name).write_text(strict)
            (root / PREFIX / locator_name).write_text(initial_locator)
            before = self.contents(root)
            self.assertNotEqual(0, self.apply(root, component).returncode)
            self.assertEqual(before, self.contents(root))
            self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_symlink_target_and_parent_rejected(self):
        for parent in [False, True]:
            with self.subTest(parent=parent), tempfile.TemporaryDirectory(prefix='batch-location-guard-') as directory:
                root, component = self.fixture(directory)
                target = root / PREFIX / ('services/location_locator/locator/include' if parent else
                                          'services/location_locator/locator/include/locator_ability.h')
                external = Path(directory) / 'outside'
                if parent:
                    shutil.copytree(target, external)
                    shutil.rmtree(target)
                else:
                    shutil.copy2(target, external)
                    target.unlink()
                target.symlink_to(external, target_is_directory=parent)
                before = self.contents(root)
                self.assertNotEqual(0, self.apply(root, component).returncode)
                self.assertEqual(before, self.contents(root))
                self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_wrong_head_and_changed_patch_rejected(self):
        for patch_change in [False, True]:
            with self.subTest(patch_change=patch_change), tempfile.TemporaryDirectory(prefix='batch-location-guard-') as directory:
                root, component = self.fixture(directory)
                if patch_change:
                    patch = sorted(component.glob('*.patch'))[0]
                    patch.write_text(patch.read_text() + '\n')
                else:
                    project = root / PREFIX
                    subprocess.run(['git', '-C', str(project), '-c', 'user.name=Location fixture', '-c',
                                    'user.email=location-fixture@example.invalid', 'commit', '--allow-empty', '-qm',
                                    'Unexpected HEAD'], check=True)
                before = self.contents(root)
                self.assertNotEqual(0, self.apply(root, component).returncode)
                self.assertEqual(before, self.contents(root))
                self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_production_revision_and_frozen_targets_are_consistent(self):
        manifest = json.loads((COMPONENT / 'source_states.json').read_text())
        frozen = json.loads((ROOT / 'docs/capability-audit/parallel/location/round2-freeze-inputs.json').read_text())
        self.assertEqual(frozen['revision'], manifest['revision'])
        additional = json.loads((ROOT / 'docs/capability-audit/parallel/location/round21-gnss-trace-build-input.json').read_text())
        self.assertEqual(27, len(frozen['targets']))
        self.assertEqual({'base/location/location/services/location_gnss/gnss/BUILD.gn'}, set(additional['targets']))
        self.assertEqual(frozen['revision'], additional['revision'])
        targets = {**frozen['targets'], **additional['targets']}
        self.assertEqual(28, len(targets))
        self.assertEqual(set(PREFIX + path for path in manifest['files']), set(targets))
        for path, info in targets.items():
            self.assertEqual(info['sha256'], manifest['states']['original'][path.removeprefix(PREFIX)])


    def test_all_28_actual_originals_replay_to_unchanged_production_state_hashes(self):
        manifest = json.loads((COMPONENT / 'source_states.json').read_text())
        self.assertEqual(8, len(manifest['patches']))
        self.assertEqual({'original', 'final'} | {'prefix_' + str(i) for i in range(1, 8)}, set(self.states))
        self.assertEqual(manifest['states'], {state: {name: digest(text) for name, text in files.items()}
                                            for state, files in self.states.items()})
        doc = json.loads((ROOT / 'docs/capability-audit/parallel/location/round21-gnss-trace-build-input.json').read_text())
        self.assertEqual(doc['historical_patches_sha256'], {name: manifest['patches'][name] for name in doc['historical_patches_sha256']})
        self.assertEqual(7, len(doc['historical_patches_sha256']))
        for row in doc['trace_source_hashes']:
            path = row['path'].removeprefix(PREFIX)
            self.assertEqual(row['pre_sha256'], manifest['states']['prefix_7'][path])
            self.assertEqual(row['post_sha256'], manifest['states']['final'][path])
        changed = {name for name in manifest['files'] if manifest['states']['prefix_7'][name] != manifest['states']['final'][name]}
        self.assertEqual({'services/location_gnss/gnss/source/gnss_event_callback.cpp',
                          'services/location_gnss/gnss/include/gnss_event_callback.h',
                          'services/location_gnss/gnss/source/gnss_ability.cpp',
                          'services/location_gnss/gnss/BUILD.gn'}, changed)

    def test_trace_BUILD_or_callback_partial_state_is_never_an_accepted_prefix(self):
        build = 'services/location_gnss/gnss/BUILD.gn'
        trace = ['services/location_gnss/gnss/source/gnss_event_callback.cpp',
                 'services/location_gnss/gnss/include/gnss_event_callback.h',
                 'services/location_gnss/gnss/source/gnss_ability.cpp']
        for changed in ([build], trace, [trace[0]], [trace[0], build]):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory(prefix='batch-location-partial-trace-') as directory:
                root, component = self.fixture(directory, state='prefix_7')
                for name in changed: (root / PREFIX / name).write_text(self.states['final'][name])
                before = self.contents(root)
                self.assertNotEqual(0, self.apply(root, component).returncode)
                self.assertEqual(before, self.contents(root))
                self.assertFalse((root / '.ohos-qemu-patches').exists())
        with tempfile.TemporaryDirectory(prefix='batch-location-unknown-trace-build-') as directory:
            root, component = self.fixture(directory, state='prefix_7')
            path = root / PREFIX / build; path.write_text(path.read_text() + '\n# unrelated BUILD change\n')
            before = self.contents(root)
            self.assertNotEqual(0, self.apply(root, component).returncode)
            self.assertEqual(before, self.contents(root)); self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_missing_or_symlinked_original_GNSS_BUILD_fails_before_writes(self):
        name = 'services/location_gnss/gnss/BUILD.gn'
        for symlink in (False, True):
            with self.subTest(symlink=symlink), tempfile.TemporaryDirectory(prefix='batch-location-trace-build-path-') as directory:
                root, component = self.fixture(directory, state='prefix_7')
                path = root / PREFIX / name; data = path.read_bytes(); path.unlink()
                if symlink:
                    outside = Path(directory) / 'outside-build.gn'; outside.write_bytes(data); path.symlink_to(outside)
                before = self.contents(root)
                self.assertNotEqual(0, self.apply(root, component).returncode)
                self.assertEqual(before, self.contents(root)); self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_patch8_preserves_frozen_trace_bytes_and_changes_only_four_owned_files(self):
        import re
        doc = json.loads((ROOT / 'docs/capability-audit/parallel/location/round21-gnss-trace-build-input.json').read_text())
        patch = (COMPONENT / doc['new_patch']).read_bytes()
        self.assertEqual(doc['reused_trace_patch']['sha256'], hashlib.sha256(patch[:doc['reused_trace_patch_bytes']]).hexdigest())
        paths = re.findall(r'^\+\+\+ b/(.+)$', patch.decode(), re.M)
        self.assertEqual(4, len(paths)); self.assertEqual(4, len(set(paths)))
        expected = {row['path'] for row in doc['trace_source_hashes']} | set(doc['targets'])
        self.assertEqual(expected, set(paths))

    def test_trace_define_only_inside_existing_HDI_gate_and_three_QEMU_products(self):
        name = 'services/location_gnss/gnss/BUILD.gn'
        original = self.states['prefix_7'][name]; final = self.states['final'][name]
        feature = '      defines += [ "FEATURE_GNSS_SUPPORT" ]\n'
        guarded = ('      if (device_company == "qemu" &&\n'
                   '          (product_name == "arm64_virt" || product_name == "armv7a_virt" ||\n'
                   '           product_name == "x86_64_virt")) {\n'
                   '        defines += [ "QEMU_GNSS_HDI_RAW_TRACE=1" ]\n'
                   '      }\n')
        self.assertEqual(2, original.count(feature)); self.assertEqual(2, final.count('"QEMU_GNSS_HDI_RAW_TRACE=1"'))
        self.assertEqual(original.replace(feature, feature + guarded), final)
        self.assertEqual(2, final.count('    if (location_feature_with_gnss &&\n        hdf_drivers_interface_location_gnss_enable) {'))
        self.assertEqual(2, final.count('      cfi = true')); self.assertEqual(2, final.count('      cfi_cross_dso = true'))


if __name__ == '__main__':
    unittest.main()
