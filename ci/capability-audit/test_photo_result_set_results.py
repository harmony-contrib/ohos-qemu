"""Synthetic strict-verifier regressions, explicitly not guest acceptance."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_photo_result_set_probe import DECLARATION, PERMISSION, ROLES, SCOPE, TEMPLATE, module, page
from run_root_probe import digest
from sign_photo_result_set_probe import configure_profile
from test_verify_always_on_vpn_results import identity, UID
import verify_photo_result_set_results as verifier

RUN = 'a' * 32
BOOT = '12345678-1234-1234-1234-123456789abc'


def rows(role, nonce=RUN):
    output = []
    for sequence, (name, values, string) in enumerate(verifier.expected(role, nonce), 1):
        actual = values if values is not None else [UID, UID, 123] if name == 'identity' else [0, 1, 1]
        output.append(dict(runId=nonce, role=role, sequence=sequence, name=name, values=actual, text=string, error=''))
    return output


def text(value):
    return '\n'.join(json.dumps(row) for row in value) + '\n'


def fixture(root):
    document = dict(status='pass', scope=verifier.EVIDENCE_SCOPE, archive_sha256='b' * 64, boot_id=BOOT,
        arch='arm64', device='phone', target='127.0.0.1:56789', udid='1' * 64, failures=[], roles={},
        caller_cleanup_verified=True, first_artifact_behavior_gate_passed=False,
        verifier_sha256=digest(Path(verifier.__file__)))
    for index, role in enumerate(ROLES):
        directory = root / role; directory.mkdir()
        nonce = str(index + 1) * 32
        project = directory / 'project'
        generated = project / 'entry/src/main/ets/pages/Index.ets'; generated.parent.mkdir(parents=True)
        generated.write_text(page(nonce, role))
        module_path = project / 'entry/src/main/module.json5'; module_path.write_text(json.dumps(module(role)))
        sdk = directory / DECLARATION; sdk.write_text('// synthetic SDK fixture, never compiler evidence')
        paths = {key: directory / name for key, name in (
            ('inputs', 'inputs.json'), ('application_identity', 'identity.json'),
            ('signed_hap', 'NOT-actually-signed.hap'), ('unsigned_hap', 'NOT-actually-built.hap'),
            ('signing_receipt', 'signing.json'), ('raw_results', 'results.log'))}
        paths['inputs'].write_text(json.dumps(dict(schema_version=1, run_id=nonce, role=role, arch='arm64', scope=SCOPE,
            request_permissions=[PERMISSION] if role == 'system' else [], template_sha256=digest(TEMPLATE),
            generated_source=str(generated), generated_source_sha256=digest(generated),
            sdk_declaration=str(sdk), sdk_declaration_sha256=digest(sdk), module_sha256=digest(module_path),
            builder_sha256=digest(Path(__file__).with_name('build_photo_result_set_probe.py')),
            shared_builder_sha256=digest(Path(__file__).with_name('build_always_on_vpn_probe.py')))))
        paths['application_identity'].write_text(identity(role))
        paths['unsigned_hap'].write_text('synthetic unsigned fixture; no compiler/signature claim')
        with zipfile.ZipFile(paths['signed_hap'], 'w') as hap:
            hap.writestr('module.json', json.dumps(module(role, compiled=True)))
        profile = configure_profile({'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}},
                                    role, document['udid'], module(role, compiled=True))
        paths['signing_receipt'].write_text(json.dumps(dict(status='pass', role=role,
            scope='actual_signature_profile_and_codesign_NOT_guest', verified_profile=profile,
            signed_sha256=digest(paths['signed_hap']), unsigned_sha256=digest(paths['unsigned_hap']))))
        observations = rows(role, nonce); paths['raw_results'].write_text(text(observations))
        record = dict(run_id=nonce, actual_uid=UID, status='pass', results=observations)
        for field, path in paths.items():
            record.update({field: str(path), field + '_sha256': digest(path)})
        document['roles'][role] = record
    return document


class PhotoResultSetResultsTests(unittest.TestCase):
    def check(self, value, role='system'):
        return verifier.verify(text(value), RUN, role, identity(role))

    def evidence(self, document):
        return verifier.verify_evidence(document, 'b' * 64, BOOT, 'arm64', 'phone', '127.0.0.1:56789')

    def test_three_roles_exact_typed_queries_permissions_and_readonly_scope(self):
        for role in ROLES:
            actual = rows(role); self.assertEqual(self.check(actual, role), actual)
            source = page(RUN, role)
            self.assertNotIn('__RESULT_SET_', source)
            self.assertIn('helper.query(', source)
            self.assertIn('photoAccessHelper.ResultSet', source)
            self.assertIn(' FROM Photos', source)
            self.assertNotIn('Object.setPrototypeOf', source)
            for destructive in ('DELETE FROM', 'INSERT INTO', 'UPDATE Photos', 'DROP TABLE', 'mock', 'Object.assign'):
                self.assertNotIn(destructive, source)
            self.assertEqual(module(role)['module']['requestPermissions'], [{'name': PERMISSION}] if role == 'system' else [])
        for nonce, role in (('', 'normal'), (RUN, 'root'), ('g' * 32, 'system')):
            with self.assertRaises(ValueError): page(nonce, role)

    def test_missing_reordered_duplicate_stale_and_each_false_observation_rejected(self):
        for role in ROLES:
            original = rows(role)
            for changed in (original[:-1], original + original[:1], list(reversed(original))):
                with self.assertRaises(ValueError): self.check(changed, role)
            for index in range(len(original)):
                for key, changed in (('runId', 'b' * 32), ('role', 'root'), ('sequence', True),
                                     ('sequence', 0), ('error', 'native failure'), ('values', [True]), ('text', 'forged')):
                    value = deepcopy(original); value[index][key] = changed
                    with self.subTest(role=role, index=index, field=key), self.assertRaises(ValueError):
                        self.check(value, role)
        with self.assertRaises(ValueError): verifier.verify(text(rows('system')).rstrip('\n'), RUN, 'system', identity('system'))

    def test_null_missing_keys_bytes_narrowing_empty_close_and_recovery_cannot_be_relaxed(self):
        for name in ('factory.0', 'first.0', 'values.first.0', 'row.first.0', 'blob-copy.0', 'last.0',
                     'values.last.0', 'past-last.0', 'invalid.column.0', 'invalid.row.0',
                     'closed.0', 'bare-close.0', 'empty.0', 'invalid.sql.0', 'recovery.0', 'released'):
            value = rows('system'); target = next(row for row in value if row['name'] == name)
            target['values'][0] += 1
            with self.subTest(name=name), self.assertRaises(ValueError): self.check(value)
        for count in (-1, 0.5, True, '0', float('nan'), float('inf')):
            value = rows('system'); target = next(row for row in value if row['name'] == 'media-table.0')
            target['values'][0] = count
            with self.subTest(count=count), self.assertRaises(ValueError): self.check(value)
        for role in ('normal', 'system-denied'):
            value = rows(role); value[1]['values'] = [str(value[1]['values'][0]), 1]
            with self.assertRaises(ValueError): self.check(value, role)

    def test_exact_signing_roles_do_not_grant_query_permission_to_denials(self):
        for role in ROLES:
            profile = configure_profile({'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}},
                                        role, '1' * 64, module(role, compiled=True))
            requests = [PERMISSION] if role == 'system' else []
            self.assertEqual(profile['acls']['allowed-acls'], requests)
            self.assertEqual(profile['permissions']['restricted-permissions'], requests)
            self.assertEqual(profile['bundle-info']['apl'], 'normal' if role == 'normal' else 'system_core')
            changed = module(role, compiled=True); changed['module']['requestPermissions'].append({'name': 'ohos.permission.INTERNET'})
            with self.assertRaises(ValueError): configure_profile(profile, role, '1' * 64, changed)

    def test_complete_evidence_replay_closes_only_resultset(self):
        with tempfile.TemporaryDirectory(prefix='photo-query-synthetic-evidence-') as directory:
            document = fixture(Path(directory))
            self.assertEqual(self.evidence(document), ['arkts_export:@ohos.file.photoAccessHelper:ResultSet'])
            for key, changed in (('archive_sha256', 'c' * 64), ('boot_id', 'old'), ('arch', 'x86_64'),
                                 ('device', '2in1'), ('target', 'foreign'), ('failures', ['failed']),
                                 ('first_artifact_behavior_gate_passed', True), ('caller_cleanup_verified', False),
                                 ('verifier_sha256', '0' * 64)):
                value = deepcopy(document); value[key] = changed
                with self.subTest(field=key), self.assertRaises(ValueError): self.evidence(value)
            for role in ROLES:
                value = deepcopy(document); value['roles'].pop(role)
                with self.assertRaises(ValueError): self.evidence(value)
                for field in ('inputs', 'application_identity', 'signed_hap', 'unsigned_hap', 'signing_receipt', 'raw_results'):
                    value = deepcopy(document); value['roles'][role][field + '_sha256'] = '0' * 64
                    with self.subTest(role=role, field=field), self.assertRaises(ValueError): self.evidence(value)
            record = document['roles']['system']; path = Path(record['raw_results'])
            lines = path.read_text().splitlines()
            index = next(index for index, line in enumerate(lines) if json.loads(line)['name'] == 'values.first.0')
            invalid = json.loads(lines[index]); invalid['values'][-1] = 0
            lines[index] = json.dumps(invalid); path.write_text('\n'.join(lines) + '\n')
            record['raw_results_sha256'] = digest(path)
            with self.assertRaises(ValueError): self.evidence(document)

    def test_rehashed_generated_source_module_and_permission_changes_rejected(self):
        with tempfile.TemporaryDirectory(prefix='photo-query-synthetic-inputs-') as directory:
            document = fixture(Path(directory)); record = document['roles']['system']
            receipt = Path(record['inputs']); value = json.loads(receipt.read_text())
            module_path = Path(value['generated_source']).parents[5] / 'entry/src/main/module.json5'
            changed = json.loads(module_path.read_text()); changed['module']['requestPermissions'].append({'name': 'ohos.permission.INTERNET'})
            module_path.write_text(json.dumps(changed)); value['module_sha256'] = digest(module_path)
            receipt.write_text(json.dumps(value)); record['inputs_sha256'] = digest(receipt)
            with self.assertRaises(ValueError): self.evidence(document)

    def test_future_suite_and_delivery_gate_require_real_query_on_both_profiles(self):
        from verify_first_artifact_gate import REQUIRED_CHECKS
        self.assertIn('photo-result-set', REQUIRED_CHECKS)
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("check('photo-result-set', work / 'photo-result-set/evidence.json', [photo_result_set_record])", suite)
        self.assertIn('run_photo_result_set_probe.py', suite)
        closure = Path(__file__).with_name('verify_gap_closure.py').read_text()
        self.assertIn("child('photo-result-set/evidence.json')", closure)


if __name__ == '__main__': unittest.main()
