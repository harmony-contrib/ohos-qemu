"""Synthetic strict boundaries only, not crypto, SDK compilation or guest proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_certificate_probe import DECLARATION, TEMPLATE, module, page
from run_root_probe import digest
from sign_certificate_probe import PERMISSIONS, configure_profile
from verify_certificate_results import SCOPE, identity, names, verify, verify_evidence, verify_inputs
from verify_gap_closure import behavior_results
from compile_certificate_empty_lists import run as compile_candidate
from types import SimpleNamespace

RUN = '0123456789abcdef0123456789abcdef'
BOOT = '12345678-1234-1234-1234-123456789abc'
ARCHIVE = 'a' * 64


def application(role):
    return json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal' if role == 'normal' else 'system_core',
        'isSystemApp': role == 'system', 'uid': 20010001 if role == 'normal' else 20010002}})


def observations(role, run_id=RUN):
    rows = []
    for name in names(role):
        row = {'name': name, 'runId': run_id, 'role': role, 'code': 0, 'uri': '',
               'credentials': [], 'values': [], 'error': ''}
        if name.startswith('denied.'):
            row['code'] = 201 if name in ('denied.own', 'denied.install') else 202
        elif name.startswith(('install.', 'uninstall.')):
            row['uri'] = 'synthetic_uri_' + name[-1]
        elif name.startswith('populated.'):
            generation = name.split('.')[1]
            row['credentials'] = [{'type': 'PKCS12', 'alias': 'qemu_' + run_id[:16] + '_' + generation,
                                   'keyUri': 'synthetic_uri_' + generation}]
        elif name.startswith('boundary.'):
            row['code'] = 401 if name in ('boundary.alias', 'boundary.uri') else 17500003
        elif name == 'repeat.empty':
            row['values'] = [64, 0]
        elif name == 'summary':
            row['values'] = [len(names(role)) - 1, 0]
        rows.append(row)
    return rows


def raw(rows):
    return '\n'.join(map(json.dumps, rows)) + '\n'


def inputs(root, role, run_id):
    root.mkdir(parents=True)
    fixture = root / 'fixture.p12'; fixture.write_bytes(b'synthetic fixture, NOT a real certificate')
    generated = root / 'Index.ets'; generated.write_text(page(run_id, role, fixture.read_bytes()))
    declaration = root / DECLARATION; declaration.write_text('// synthetic SDK identity fixture, NOT an SDK')
    return {'schema_version': 1, 'run_id': run_id, 'arch': 'arm64', 'role': role, 'scope': SCOPE,
        'request_permissions': list(PERMISSIONS) if role == 'system' else [], 'template_sha256': digest(TEMPLATE),
        'generated_source': str(generated), 'generated_source_sha256': digest(generated),
        'test_pkcs12': str(fixture), 'test_pkcs12_sha256': digest(fixture),
        'sdk_declaration': str(declaration), 'sdk_declaration_sha256': digest(declaration)}


def evidence_fixture(root):
    document = {'status': 'pass', 'scope': 'two_real_certificate_HAP_roles_NOT_full_gate',
        'archive_sha256': ARCHIVE, 'boot_id': BOOT, 'arch': 'arm64', 'udid': '1' * 64,
        'roles': {}, 'failures': []}
    for role in ('system', 'normal'):
        challenge = RUN if role == 'system' else 'f' * 32
        directory = root / role; value = inputs(directory / 'project', role, challenge)
        paths = {field: directory / filename for field, filename in (
            ('inputs', 'inputs.json'), ('raw_results', 'raw.jsonl'), ('application_identity', 'identity.json'),
            ('result', 'verified.json'), ('signed_hap', 'synthetic-NOT-signed.hap'), ('signing_receipt', 'receipt.json'))}
        paths['inputs'].write_text(json.dumps(value))
        paths['raw_results'].write_text(raw(observations(role, challenge)))
        paths['application_identity'].write_text(application(role))
        paths['result'].write_text(json.dumps({'status': 'pass', 'scope': SCOPE, 'role': role, 'arch': 'arm64',
            'run_id': challenge, 'archive_sha256': ARCHIVE, 'results': observations(role, challenge),
            'results_sha256': digest(paths['raw_results']), 'inputs_sha256': digest(paths['inputs']),
            'application_identity_sha256': digest(paths['application_identity'])}))
        with zipfile.ZipFile(paths['signed_hap'], 'w') as hap:
            hap.writestr('module.json', json.dumps(module(role, compiled=True)))
        profile = configure_profile({'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}},
            role, document['udid'], module(role, compiled=True))
        paths['signing_receipt'].write_text(json.dumps({'status': 'pass', 'role': role,
            'scope': 'actual_signature_profile_and_codesign_NOT_guest', 'verified_profile': profile,
            'signed_sha256': digest(paths['signed_hap'])}))
        row = {'status': 'pass', 'run_id': challenge, 'actual_uid': identity(application(role), role)}
        for field, path in paths.items():
            row[field] = str(path); row[field + '_sha256'] = digest(path)
        document['roles'][role] = row
    return document


class CertificateResultsTests(unittest.TestCase):
    def test_complete_twenty_five_system_and_five_normal_rows(self):
        self.assertEqual(len(names('system')), 25)
        self.assertEqual(len(names('normal')), 5)
        for role in ('system', 'normal'):
            rows = observations(role)
            self.assertEqual(verify(raw(rows), RUN, role, application(role)), rows)

    def test_identity_and_denial_never_allow_root_system_or_ordinary_success(self):
        for role, wrong in (('normal', application('system')), ('system', application('normal')),
                             ('system', application('system').replace('20010002', '3081'))):
            with self.assertRaises(ValueError):
                verify(raw(observations(role)), RUN, role, wrong)
        for code in (0, 401, 17500001, True):
            rows = observations('normal'); rows[0]['code'] = code
            with self.subTest(code=code), self.assertRaises(ValueError):
                verify(raw(rows), RUN, 'normal', application('normal'))
        for index in (2, 3):
            rows = observations('normal'); rows[index]['code'] = 202
            with self.assertRaises(ValueError):
                verify(raw(rows), RUN, 'normal', application('normal'))

    def test_fields_undefined_nonempty_alias_uri_cleanup_repeat_and_boundary_fail_closed(self):
        changes = [lambda rows: rows[0].update(credentials=None),
            lambda rows: rows[0].update(credentials=copy.deepcopy(rows[4]['credentials'])),
            lambda rows: rows[4]['credentials'][0].update(alias='other'),
            lambda rows: rows[5]['credentials'][0].update(keyUri='other'),
            lambda rows: rows[6]['credentials'][0].update(type=''),
            lambda rows: rows[7].update(uri='someone_else'),
            lambda rows: rows[19].update(code=0), lambda rows: rows[20].update(code=17500001),
            lambda rows: rows[21].update(code=201), lambda rows: rows[22].update(code=0),
            lambda rows: rows[23].update(values=[64, 1]), lambda rows: rows[-1].update(values=[24, 1])]
        for change in changes:
            rows = observations('system'); change(rows)
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify(raw(rows), RUN, 'system', application('system'))

    def test_order_nonce_extra_fields_error_and_role_rejected(self):
        rows = observations('system')
        for bad in (rows[:-1], rows[::-1], rows + [rows[0]]):
            with self.assertRaises(ValueError):
                verify(raw(bad), RUN, 'system', application('system'))
        for field, value in (('runId', '0' * 32), ('role', 'normal'), ('error', 'service failure'), ('extra', 1)):
            bad = observations('system'); bad[0][field] = value
            with self.assertRaises(ValueError):
                verify(raw(bad), RUN, 'system', application('system'))

    def test_inputs_match_full_typed_page_fixture_sdk_and_exact_role_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            value = inputs(Path(directory) / 'inputs', 'system', RUN)
            verify_inputs(value, RUN, 'arm64', 'system')
            for field, wrong in (('template_sha256', '0' * 64), ('request_permissions', []),
                                  ('test_pkcs12_sha256', '0' * 64), ('generated_source_sha256', '0' * 64)):
                bad = dict(value, **{field: wrong})
                with self.assertRaises(ValueError):
                    verify_inputs(bad, RUN, 'arm64', 'system')
            generated = Path(value['generated_source'])
            generated.write_text(generated.read_text().replace('await this.snapshots', '// await this.snapshots'))
            value['generated_source_sha256'] = digest(generated)
            with self.assertRaises(ValueError):
                verify_inputs(value, RUN, 'arm64', 'system')

    def test_same_archive_boot_both_roles_current_raw_and_exact_one_finding_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); owned = root / 'certificate-manager'; owned.mkdir()
            document = evidence_fixture(owned)
            self.assertEqual(set(verify_evidence(document, ARCHIVE, BOOT)), {'normal', 'system'})
            path = owned / 'evidence.json'; path.write_text(json.dumps(document))
            closed = behavior_results(root, BOOT, ARCHIVE)
            self.assertEqual(set(closed), {'behavior:certificate-manager-undefined-result'})
            self.assertEqual(behavior_results(root, 'different-boot', ARCHIVE), {})
            self.assertEqual(behavior_results(root, BOOT, 'different-archive'), {})
            for change in (lambda doc: doc['roles'].pop('normal'),
                           lambda doc: doc.update(udid='*'),
                           lambda doc: doc.update(boot_id='other'),
                           lambda doc: doc.update(archive_sha256='b' * 64)):
                bad = copy.deepcopy(document); change(bad)
                with self.assertRaises(ValueError):
                    verify_evidence(bad, ARCHIVE, BOOT)
            Path(document['roles']['normal']['raw_results']).write_text('tampered')
            with self.assertRaises(ValueError):
                verify_evidence(document, ARCHIVE, BOOT)

    def test_no_uninstall_all_permission_bypass_or_api_stubs_and_default_wiring(self):
        source = TEMPLATE.read_text()
        for bad in ('uninstallAll', '@ts-ignore', 'requireNapi', 'grantPermission', 'clearStorage'):
            self.assertNotIn(bad, source)
        for call in ('getAllAppPrivateCertificates', 'getPrivateCertificates',
                     'installPrivateCertificate', 'uninstallPrivateCertificate'):
            self.assertIn(call, source)
        self.assertEqual(module('normal')['module']['requestPermissions'], [])
        self.assertEqual(module('system')['module']['requestPermissions'], [{'name': name} for name in PERMISSIONS])
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("'run_certificate_probe.py'", suite)
        self.assertIn("check('certificate-manager'", suite)
        self.assertLess(source.index("this.record(name, 0, '', [], [], 'unexpected install success')"),
                        source.index('uninstallPrivateCertificate(installed.uri)'))

    def test_compile_checker_preserves_existing_evidence_and_symlink_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); old = root / 'evidence.json'; old.write_text('old actual evidence')
            link = root / 'link.json'; link.symlink_to(old)
            for output in (old, link):
                with self.assertRaisesRegex(ValueError, 'preserve existing'):
                    compile_candidate(SimpleNamespace(output=output, source_root=root))
                self.assertEqual(old.read_text(), 'old actual evidence')


if __name__ == '__main__':
    unittest.main()
