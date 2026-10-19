"""Pure source-assembly security and canonical branch admission regressions."""
from pathlib import Path
import ast
import json
import tempfile
import unittest
from unittest.mock import patch

import batch_location375_kit as kit

LOCK = kit.ROOT / 'docs/capability-audit/parallel/location/round375/source-lock.json'
LOCK_SHA = 'e9644c398cd6e34428bb5fff8571cf323168b5ee5c4d1da8a68f09884643c674'


class AssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (kit.H / kit.COMPILE / 'SOURCE_MANIFEST.json').is_file():
            raise unittest.SkipTest('explicit private Location predecessor sources are not installed in this checkout')
        cls.lock, cls.retained = kit.inputs(LOCK, LOCK_SHA)
        cls.files = kit.generated(cls.lock, cls.retained)

    def test_all_source_originals_rechecked_against_lock(self):
        self.assertEqual(len(self.retained), 117)
        self.assertGreater(len(self.files), 100)
        for name, data in self.retained.items():
            self.assertEqual(kit.row(data), self.lock['files'][name])

    def test_inert_plan_has_no_input_read_and_no_write(self):
        with patch.object(kit, 'read', side_effect=AssertionError('must not read')), patch.object(kit, 'assemble', side_effect=AssertionError('must not assemble')):
            self.assertEqual(kit.main([]), 0)

    def test_malformed_json_and_duplicate_keys_rejected(self):
        for raw in ['{"x": 1, "x": 2}', '{"x":NaN}', '{"x":Infinity}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                kit.decode(raw)

    def test_paths_refuse_normalization_and_escape(self):
        for name in ['/outside', '../x', 'a/../x', 'a//x', 'a/./x', 'x/', '', 'a\\x']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                kit.relative(name)

    def test_input_hash_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'lock changed'):
            kit.inputs(LOCK, '0' * 64)

    def test_exact_source_preimage_required_for_transformation(self):
        for source in ('none', 'a a'):
            with self.assertRaisesRegex(ValueError, 'preimage'):
                kit.replace_once(source, 'a', 'b')

    def test_leaf_and_parent_symlinks_rejected(self):
        with tempfile.TemporaryDirectory(prefix='location375-pure-') as raw:
            root = Path(raw).resolve(); actual = root / 'actual'; actual.mkdir()
            (actual / 'input').write_bytes(b'x'); (root / 'alias').symlink_to(actual, target_is_directory=True)
            (root / 'leaf').symlink_to(actual / 'input')
            for path in [root / 'leaf', root / 'alias/input']:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    kit.read(path)

    def test_nonregular_and_hardlink_refused(self):
        import os
        with tempfile.TemporaryDirectory(prefix='location375-pure-') as raw:
            root = Path(raw).resolve(); source = root / 'input'; source.write_bytes(b'x')
            os.link(source, root / 'alias')
            with self.assertRaises(ValueError): kit.read(source)
            with self.assertRaises(ValueError): kit.read(root)

    def test_finite_source_cap_refused_before_large_read(self):
        with tempfile.TemporaryDirectory(prefix='location375-pure-') as raw:
            source = Path(raw).resolve() / 'input'; source.write_bytes(b'12345')
            with patch.object(kit, 'MAX_FILE', 4), self.assertRaisesRegex(ValueError, 'cap'):
                kit.read(source)

    def test_overlay_exact_postimages_and_original_sources_untouched(self):
        for name, pair in self.lock['overlays'].items():
            self.assertEqual(self.files[name], self.retained[pair['post']])
            self.assertEqual(kit.read(kit.H / self.lock['copy'][name]), self.retained[pair['pre']])

    def test_owner_only_two_path_constants_change(self):
        name = kit.SUPPORT + '/owned_resource35.py'
        before = ast.parse(self.retained[name]); after = ast.parse(self.files[name])
        self.assertEqual(len(before.body), len(after.body))
        for old, new in zip(before.body, after.body):
            if isinstance(old, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('HERE', 'QA_ROOT') for t in old.targets):
                continue
            self.assertEqual(ast.dump(old), ast.dump(new))

    def test_compile_policy_and_inner_AST_unchanged(self):
        for filename in ['compile_contract129.py', 'compile_inner129.py', 'endpoint_owner129.py']:
            name = kit.COMPILE + '/' + filename
            self.assertEqual(self.files[name], self.retained[name])
        source = self.files[kit.COMPILE + '/compile_contract129.py'].decode()
        self.assertIn('actual CFI/LTO required; never add it', source)
        self.assertIn('actual required CFI/LTO/noRTTI absent', source)

    def test_immutable_manifests_retained_and_successors_pin_actual_bytes(self):
        for folder in [kit.COMPILE, kit.INVENTORY, kit.GN]:
            original = self.files['provenance375/' + folder + '-SOURCE_MANIFEST.json']
            self.assertEqual(original, self.retained[folder + '/SOURCE_MANIFEST.json'])
            manifest = json.loads(self.files[folder + '/SOURCE_MANIFEST.json'])
            self.assertEqual(manifest['successor375']['predecessor_manifest'], kit.row(original))
            rows = {r['relative']: r for r in manifest['files']} if folder == kit.COMPILE else manifest['files_except_manifest']
            for name, info in rows.items():
                self.assertEqual({k: info[k] for k in ('sha256', 'bytes')}, kit.row(self.files[folder + '/' + name]))
            for name, info in manifest.get('external_source_pins', {}).items():
                self.assertEqual(info, kit.row(self.files[name]))

    def test_support_pins_match_real_new_owner_and_clean_guard(self):
        pins = {name: kit.sha(self.files[kit.SUPPORT + '/' + name]) for name in kit.SUPPORT_FILES}
        for folder, entry in [(kit.COMPILE, 'run_location_compile129.py'), (kit.INVENTORY, 'run_inventory354.py'), (kit.GN, 'run_GN_export370.py')]:
            tree = ast.parse(self.files[folder + '/' + entry])
            literal = next(node.value for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SUPPORT_PINS' for t in node.targets))
            self.assertEqual(ast.literal_eval(literal), pins)

    def test_clean_guard_accepts_only_same_canonical_branch_commit_and_clean(self):
        source = self.files[kit.SUPPORT + '/support_common35.py'].decode()
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'clean')
        function = compile(ast.Module(body=[node], type_ignores=[]), '<pure clean guard>', 'exec')
        for root, branch, head, dirty, expected in [(kit.ROOT, 'codex/ohos7-integrated-development', 'a' * 40, '', True),
                (kit.ROOT, 'other', 'a' * 40, '', False), (kit.ROOT, 'codex/ohos7-integrated-development', 'b' * 40, '', False),
                (kit.ROOT, 'codex/ohos7-integrated-development', 'a' * 40, ' M product', False),
                (Path('/retired/worktree'), 'codex/ohos7-integrated-development', 'a' * 40, '', False)]:
            def git(owner, checked_root, *args):
                return {'symbolic-ref': branch, 'rev-parse': head, 'status': dirty}[args[0]]
            scope = {'require': kit.need, 'QA_ROOT': kit.ROOT, 'E_COMMIT': 'c' * 40, 'git': git}
            exec(function, scope)
            if expected: scope['clean'](object(), root, 'a' * 40)
            else:
                with self.subTest(root=root, branch=branch, head=head, dirty=dirty), self.assertRaises(ValueError):
                    scope['clean'](object(), root, 'a' * 40)

    def test_assembler_contains_no_process_or_git_resource_API(self):
        tree = ast.parse(Path(kit.__file__).read_text())
        imports = [alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names]
        self.assertFalse(set(imports) & {'subprocess', 'socket', 'fcntl', 'signal'})
        self.assertNotIn('Popen', Path(kit.__file__).read_text())

    def test_complete_assembly_and_actual_private_bindings(self):
        with tempfile.TemporaryDirectory(prefix='location375-full-HOST-') as raw:
            parent = Path(raw).resolve()
            with patch.object(kit, 'OUTPUT_PARENT', parent):
                manifest_row = kit.assemble(LOCK, LOCK_SHA, parent / 'complete')
            manifest_path = Path(manifest_row['path'])
            actual = kit.verify(manifest_path, manifest_row['sha256'])
            bindings = kit.private_bindings(manifest_path, manifest_row['sha256'])
            self.assertEqual(set(bindings['runtime_config_private_sources']), set(kit.PRIVATE_FILES))
            for name, digest in bindings['runtime_config_private_sources'].items():
                self.assertEqual(digest, kit.sha(kit.read(manifest_path.parent / name)))
            self.assertFalse(bindings['source_commit_or_package_descriptors_synthesized'])
            self.assertFalse(bindings['first_artifact_behavior_gate_passed'])
            self.assertEqual(kit.row(kit.read(Path(actual['assembler']['path']))),
                             {key: actual['assembler'][key] for key in ('sha256', 'bytes')})
            # Unlisted imports and modified known members cannot pass the full-kit guard.
            extra = manifest_path.parent / 'foreign.py'; extra.write_text('raise RuntimeError("foreign")\n')
            with self.assertRaisesRegex(ValueError, 'unlisted'): kit.verify(manifest_path, manifest_row['sha256'])
            extra.unlink()
            selected = manifest_path.parent / kit.PRIVATE_FILES[0]
            selected.write_bytes(selected.read_bytes() + b'\n# HOST tamper\n')
            with self.assertRaisesRegex(ValueError, 'member changed'): kit.verify(manifest_path, manifest_row['sha256'])

    def test_existing_or_foreign_output_is_not_reused(self):
        with tempfile.TemporaryDirectory(prefix='location375-full-HOST-') as raw:
            parent = Path(raw).resolve(); existing = parent / 'existing'; existing.mkdir()
            with patch.object(kit, 'OUTPUT_PARENT', parent), self.assertRaisesRegex(ValueError, 'fresh direct'):
                kit.assemble(LOCK, LOCK_SHA, existing)
            with self.assertRaisesRegex(ValueError, 'fresh direct'):
                kit.assemble(LOCK, LOCK_SHA, parent / 'foreign')


if __name__ == '__main__':
    unittest.main()
