"""Host file/graph counterexamples only; never native, signature or guest proof."""
import copy
import hashlib
import io
import json
from pathlib import Path
import shlex
import tarfile
import tempfile
import unittest

import batch_apps_production_provider_binding as binding


class ProductionProviderBindingTests(unittest.TestCase):
    def graph(self):
        project, target = 'applications/standard/contacts', 'contacts_hap'
        stem = 'obj/' + project + '/' + target
        compile_argv = ['/usr/bin/env', '../../build/scripts/compile_app.py', '--cwd', '../../' + project + '/',
            '--build-profile', '../../' + project + '/build-profile.json5', '--sdk-home', binding.SOURCE + '/prebuilts/ohos-sdk/linux',
            '--product', 'default', '--assemble-type', 'assembleHap', '--build-level', 'module',
            '--output-file', stem + '/unsigned_hap_path_list.json', '--build-modules', 'entry', '--hvigor-obfuscation']
        lines = []
        for part, suffix, argv, output in (
            ('compile', '_compile_app', compile_argv, stem + '/unsigned_hap_path_list.json'),
            ('sign', '', ['/usr/bin/env', '../../build/scripts/app_sign.py'], stem + '.stamp'),
            ('info', '_info', ['/usr/bin/env', '../../build/templates/metadata/gen_module_info.py'], stem + '_module_info.json')):
            description = 'ACTION //' + project + ':' + target + suffix + '(//build/toolchain/ohos:ohos_clang_arm64)'
            lines += ['rule ' + part, '  command = ' + shlex.join(argv).replace('$', '$$'), '  description = ' + description]
            dependencies = ' | ' + stem + '_compile_app.stamp ' + stem + '_info.stamp' if part == 'sign' else ' | ../../input'
            lines += ['build ' + output + ': ' + part + dependencies]
        return '\n'.join(lines) + '\n'

    def actions(self, text, directory):
        path = Path(directory) / 'toolchain.ninja'; path.write_text(text)
        return binding.graph_actions(path, 'applications/standard/contacts', 'contacts_hap')

    def test_complete_graph_and_five_disconnected_or_substituted_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            text = self.graph(); actions, edges = self.actions(text, directory)
            self.assertEqual('entry', binding.option(actions['compile'], '--build-modules'))
            self.assertEqual(3, len(edges))
            variants = [text.replace('contacts_hap.stamp: sign', 'other.stamp: sign'),
                        text.replace('contacts_hap_info.stamp', 'unrelated_info.stamp'),
                        text.replace('--product default', '--product other'),
                        text.replace('--hvigor-obfuscation', '--unreviewed'),
                        text + text]
            for changed in variants:
                with self.subTest(changed=variants.index(changed)), self.assertRaises(ValueError):
                    self.actions(changed, directory)

    def test_literal_colon_escape_and_unexpanded_variables(self):
        self.assertEqual('path with$:colon', binding.ninja_decode('path$ with$$$:colon'))
        for value in ('$in', '${out}', '$x', 'tail$'):
            with self.subTest(value=value), self.assertRaises(ValueError): binding.ninja_decode(value)

    def test_duplicate_json_and_signing_secrets_never_enter_proof(self):
        with self.assertRaises(ValueError): binding.decode('{"path":"first","path":"other"}')
        commands = {'sign': ['runner', '--keyPwd', 'HOSTONLYsecret1', '--keystorePwd', 'HOSTONLYsecret2']}
        original = copy.deepcopy(commands); public = binding.public_commands(commands)
        self.assertEqual(original, commands)
        self.assertEqual(['runner', '--keyPwd', '<redacted>', '--keystorePwd', '<redacted>'], public['sign'])
        self.assertNotIn('HOSTONLYsecret', json.dumps(public))

    def archive(self, root, *, omit_top=False, duplicate=False, corrupt=False):
        path = root / 'host-only.tar.gz'; name = 'host-only'
        entries = {key: json.dumps({'name': key}).encode() for key in
                   ('build-inputs.json', 'native-build-inputs.json', 'native-to-package-lineage.json',
                    'openharmony-project-heads.json', 'contacts-theme-provider-evidence.json')}
        checks = ''.join(hashlib.sha256(raw).hexdigest() + '  ' + key + '\n' for key, raw in entries.items())
        if omit_top: entries.pop('build-inputs.json')
        if corrupt: entries['native-build-inputs.json'] += b' '
        entries['SHA256SUMS'] = checks.encode(); entries['manifest.json'] = b'{}'
        entries['native-frozen-inputs/build-inputs.json'] = b'{"scope":"historical-A"}'
        with tarfile.open(path, 'w:gz') as archive:
            for key, raw in entries.items():
                member = tarfile.TarInfo(name + '/' + key); member.size = len(raw)
                archive.addfile(member, io.BytesIO(raw))
            if duplicate:
                raw = entries['build-inputs.json']; member = tarfile.TarInfo(name + '/build-inputs.json'); member.size = len(raw)
                archive.addfile(member, io.BytesIO(raw))
        return path

    def test_exact_top_level_metadata_keeps_honest_nested_native_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); result = binding.archive_metadata(self.archive(root))
            self.assertEqual({'name': 'build-inputs.json'}, result['build-inputs.json'])
            for option in ('omit_top', 'duplicate', 'corrupt'):
                with self.subTest(option=option), self.assertRaises(ValueError):
                    binding.archive_metadata(self.archive(root, **{option: True}))

    def test_retained_export_does_not_follow_arbitrary_source_redirect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); path = root / 'files/applications/standard/contacts/test.ets'
            path.parent.mkdir(parents=True); path.write_bytes(b'HOSTONLY')
            row = {'path': binding.SOURCE + '/applications/standard/contacts/test.ets',
                   'resolved': binding.SOURCE + '/applications/standard/contacts/test.ets',
                   'export_relative': 'files/applications/standard/contacts/test.ets',
                   'sha256': binding.sha(path), 'bytes': 8}
            self.assertEqual(path, binding.retained_exports([row], root)[row['path']][1])
            row['resolved'] = binding.SOURCE + '/applications/standard/theme/test.ets'
            with self.assertRaises(ValueError): binding.retained_exports([row], root)
            row['resolved'] = row['path']; row['export_relative'] = '../outside'
            with self.assertRaises(ValueError): binding.retained_exports([row], root)

    def test_supplement_restat_is_complete_and_never_claims_graph_recapture(self):
        source = {'path': '/host-only/source', 'resolved': '/host-only/source', 'sha256': 'a'*64,
                  'bytes': 8, 'mode': 420, 'mtime_ns': 123}
        first = {'project_haps': [], 'staged': [], 'source_inventory': {'contacts': {'file': source}},
                 'graphs': [{'path': '/host-only/original-graph'}]}
        second = {'unchanged_prior_inputs': [copy.deepcopy(source)]}
        self.assertEqual(1, binding.verify_prior_inputs(first, second))
        for change in (lambda v: v['unchanged_prior_inputs'].clear(),
                       lambda v: v['unchanged_prior_inputs'][0].update(mtime_ns=124),
                       lambda v: v['unchanged_prior_inputs'].append(copy.deepcopy(source))):
            altered = copy.deepcopy(second); change(altered)
            with self.assertRaises(ValueError): binding.verify_prior_inputs(first, altered)

    def launcher(self):
        return ('Build args: --product-name arm64_virt --build-target images --build-only-load=true --device-type default\n'
                '[OHOS INFO]  arm64_virt build success\n[OHOS INFO]  Cost Time:  0:03:34\n'
                'Build args: --product-name arm64_virt --build-target images --build-only-load=false --device-type phone\n'
                '[OHOS INFO]  arm64_virt build success\n[OHOS INFO]  Cost Time:  1:33:56\n'
                'later packaging failed; original overall attempt still exit1\n')

    def test_real_dual_phase_success_cannot_substitute_preparation_for_native_images(self):
        raw = self.launcher(); phases = binding.native_launcher_phases(raw)
        self.assertEqual(['load_only', 'native_images'], [v['stage'] for v in phases])
        self.assertEqual([True, False], [v['build_only_load'] for v in phases])
        self.assertEqual(['0:03:34', '1:33:56'], [v['cost_time'] for v in phases])
        mutations = [raw.replace('--build-only-load=false', '--build-only-load=true'),
                     raw.replace('--device-type phone', '--device-type default'),
                     raw.replace('--product-name arm64_virt', '--product-name other'),
                     raw + '[OHOS INFO]  arm64_virt build success\n',
                     raw.replace('[OHOS INFO]  arm64_virt build success', '', 1),
                     raw.replace('[OHOS INFO]  Cost Time:  1:33:56', 'missing completion footer')]
        for index, changed in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError): binding.native_launcher_phases(changed)

    def test_local_properties_is_separate_public_export_with_real_hash_not_source_loop_bytes(self):
        self.assertFalse(binding.selected_byte_source('local.properties', 'contacts'))
        self.assertFalse(binding.selected_byte_source('local.properties', 'theme'))
        self.assertTrue(binding.selected_byte_source('entry/src/main/module.json5', 'contacts'))
        self.assertTrue(binding.selected_byte_source('entry/modules.ap', 'contacts'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); project = binding.PROVIDERS['contacts'][0]
            path = root/'files'/project/'local.properties'; path.parent.mkdir(parents=True); path.write_bytes(b'public-only')
            original = {'path': binding.SOURCE+'/'+project+'/local.properties',
                        'resolved': binding.SOURCE+'/'+project+'/local.properties', 'sha256': 'a'*64,
                        'bytes': 200, 'mode': 420, 'mtime_ns': 123}
            public = dict(original, sha256=binding.sha(path), bytes=11,
                          export_relative='files/'+project+'/local.properties')
            first = {'source_inventory': {'contacts': {'local.properties': original}}}
            second = {'public_properties': {project: public}}
            proof = binding.local_properties_proof(first, second, root, 'contacts')
            self.assertEqual(original, proof['original_inventory'])
            self.assertEqual(binding.sha(path), proof['retained_public_export']['sha256'])
            self.assertFalse(proof['public_export_matches_inventory_sha256'])
            self.assertFalse(proof['complete_original_source_bytes_replayed'])
            self.assertFalse(proof['counted_in_source_files_verified'])
            original['sha256'] = public['sha256']; original['bytes'] = 11
            self.assertTrue(binding.local_properties_proof(first, second, root, 'contacts')['public_export_matches_inventory_sha256'])
            path.write_bytes(b'tampered')
            with self.assertRaises(ValueError): binding.local_properties_proof(first, second, root, 'contacts')

    def test_frozen_tree_is_canonical_and_never_accepts_bad_hashes(self):
        left = {'scripts/b': 'b'*64, 'patches/a': 'a'*64}
        self.assertEqual(binding.tree_digest(left), binding.tree_digest(dict(reversed(list(left.items())))))
        for bad in ({}, {'scripts/b': 'z'*64}, {'scripts/b': True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): binding.tree_digest(bad)


if __name__ == '__main__': unittest.main()
