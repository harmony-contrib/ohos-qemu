import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_always_on_vpn_probe import module, page
from verify_always_on_vpn_results import SCOPE, expected, verify, verify_restart, verify_evidence
from sign_always_on_vpn_probe import configure_profile
from run_root_probe import digest
from build_always_on_vpn_probe import TEMPLATE

RUN = 'a' * 32
UID = 20010042


def identity(role):
    return json.dumps({'applicationInfo': {'uid': UID, 'appPrivilegeLevel':
        'normal' if role == 'normal' else 'system_core', 'isSystemApp': role != 'normal'}})


def rows(role, phase, pid=123):
    return [{'runId': RUN, 'role': role, 'name': name, 'values': values if values is not None else [UID, UID, pid],
             'error': ''} for name, values in expected(role, phase)]


def text(values):
    return '\n'.join(json.dumps(row) for row in values) + '\n'


def fixture(root):
    document = dict(status='pass', scope='three_real_VPN_policy_roles_and_caller_restart_NOT_tunnel_or_full_gate',
        archive_sha256='b' * 64, boot_id='12345678-1234-1234-1234-123456789abc', arch='arm64', device='phone',
        failures=[], roles={}, udid='1' * 64)
    for index, role in enumerate(('normal', 'system-denied', 'system')):
        directory = root / role
        directory.mkdir()
        nonce = str(index + 1) * 32
        generated, sdk = directory / 'Index.ets', directory / '@ohos.net.vpnExtension.d.ts'
        generated.write_text(page(nonce, role))
        sdk.write_text('// synthetic SDK fixture, not guest proof')
        paths = {key: directory / name for key, name in (('inputs', 'inputs.json'),
            ('application_identity', 'identity.json'), ('signed_hap', 'NOT-actually-signed.hap'),
            ('signing_receipt', 'receipt.json'))}
        paths['inputs'].write_text(json.dumps(dict(schema_version=1, run_id=nonce, role=role, arch='arm64', scope=SCOPE,
            request_permissions=['ohos.permission.MANAGE_VPN'] if role == 'system' else [],
            template_sha256=digest(TEMPLATE), generated_source=str(generated), generated_source_sha256=digest(generated),
            sdk_declaration=str(sdk), sdk_declaration_sha256=digest(sdk))))
        paths['application_identity'].write_text(identity(role))
        with zipfile.ZipFile(paths['signed_hap'], 'w') as hap:
            hap.writestr('module.json', json.dumps(module(role, compiled=True)))
        profile = configure_profile({'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}},
                                    role, document['udid'], module(role, compiled=True))
        paths['signing_receipt'].write_text(json.dumps(dict(status='pass', role=role,
            scope='actual_signature_profile_and_codesign_NOT_guest', verified_profile=profile,
            signed_sha256=digest(paths['signed_hap']))))
        record = dict(run_id=nonce, actual_uid=UID, status='pass', phases={})
        for field, path in paths.items():
            record.update({field: str(path), field + '_sha256': digest(path)})
        for phase in (('seed', 'restart') if role == 'system' else ('denial',)):
            observations = rows(role, phase, 124 if phase == 'restart' else 123)
            for row in observations:
                row['runId'] = nonce
            raw = directory / (phase + '.jsonl')
            raw.write_text(text(observations))
            record['phases'][phase] = dict(results=observations, raw_results=str(raw), raw_results_sha256=digest(raw))
        document['roles'][role] = record
    return document


class VerifyAlwaysOnVpnTests(unittest.TestCase):
    def test_roles_typed_page_and_permissions_are_exact(self):
        for role in ('normal', 'system-denied', 'system'):
            self.assertNotIn('__VPN_', page(RUN, role))
            self.assertEqual(module(role)['module']['requestPermissions'],
                [{'name': 'ohos.permission.MANAGE_VPN'}] if role == 'system' else [])
        for nonce, role in (('', 'normal'), (RUN, 'root'), ('g' * 32, 'system')):
            with self.assertRaises(ValueError):
                page(nonce, role)

    def test_exact_actual_values_and_every_row_failure_rejected(self):
        for role, phase in (('normal', 'denial'), ('system-denied', 'denial'), ('system', 'seed'), ('system', 'restart')):
            original = rows(role, phase)
            self.assertEqual(verify(text(original), RUN, role, phase, identity(role)), original)
            for index in range(len(original)):
                for key, replacement in (('error', 'failure'), ('runId', 'b' * 32), ('values', [True])):
                    changed = copy.deepcopy(original)
                    changed[index][key] = replacement
                    with self.assertRaises(ValueError):
                        verify(text(changed), RUN, role, phase, identity(role))
            for changed in (original[:-1], original + original[:1], list(reversed(original))):
                with self.assertRaises(ValueError):
                    verify(text(changed), RUN, role, phase, identity(role))

    def test_actual_process_restart_required(self):
        seed, restarted = rows('system', 'seed'), rows('system', 'restart', 124)
        verify_restart(seed, restarted)
        restarted[0]['values'][2] = 123
        with self.assertRaises(ValueError):
            verify_restart(seed, restarted)

    def test_signing_never_grants_permissions_to_denial_roles(self):
        for role in ('normal', 'system-denied', 'system'):
            profile = {'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}}
            value = configure_profile(profile, role, '1' * 64, module(role, compiled=True))
            required = ['ohos.permission.MANAGE_VPN'] if role == 'system' else []
            self.assertEqual(value['acls']['allowed-acls'], required)
            self.assertEqual(value['permissions']['restricted-permissions'], required)
            self.assertEqual(value['bundle-info']['app-feature'],
                             'hos_normal_app' if role == 'normal' else 'hos_system_app')
            changed = module(role, compiled=True)
            changed['module']['requestPermissions'].append({'name': 'ohos.permission.INTERNET'})
            with self.assertRaises(ValueError):
                configure_profile(profile, role, '1' * 64, changed)

    def test_complete_evidence_replayed_and_foreign_archive_or_role_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            document = fixture(Path(directory))
            args = ('b' * 64, document['boot_id'], 'arm64', 'phone')
            closed = verify_evidence(document, *args)
            self.assertEqual(len(closed), 2)
            for key, replacement in (('archive_sha256', 'c' * 64), ('boot_id', 'foreign'), ('arch', 'x86_64'),
                                     ('device', '2in1'), ('failures', ['failure'])):
                changed = copy.deepcopy(document)
                changed[key] = replacement
                with self.assertRaises(ValueError):
                    verify_evidence(changed, *args)
            for role in document['roles']:
                changed = copy.deepcopy(document)
                del changed['roles'][role]
                with self.assertRaises(ValueError):
                    verify_evidence(changed, *args)
            changed = copy.deepcopy(document)
            changed['roles']['system']['phases']['seed']['results'][5]['values'] = [1]
            with self.assertRaises(ValueError):
                verify_evidence(changed, *args)
            raw = Path(document['roles']['system']['phases']['restart']['raw_results'])
            raw.write_text(raw.read_text().replace('"cleanup"', '"cleanup.failed"'))
            document['roles']['system']['phases']['restart']['raw_results_sha256'] = digest(raw)
            with self.assertRaises(ValueError):
                verify_evidence(document, *args)


if __name__ == '__main__':
    unittest.main()
