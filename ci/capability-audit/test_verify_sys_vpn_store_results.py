"""Synthetic strict-verifier regressions only, never actual VPN acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_sys_vpn_store_probe import TEMPLATE, module, page, SCOPE
from sign_always_on_vpn_probe import configure_profile
from test_verify_always_on_vpn_results import identity, UID, RUN
from verify_sys_vpn_store_results import EVIDENCE_SCOPE, METHODS, expected, expected_config, verify, verify_inputs, verify_evidence
from verify_always_on_vpn_results import verify_restart
from run_root_probe import digest


def rows(role, phase, nonce=RUN, pid=123):
    return [dict(runId=nonce, role=role, name=name, values=values if values is not None else [UID, UID, pid],
        config='' if config is None else json.dumps(expected_config(nonce, *config, UID // 200000,
            zero_ports=name.startswith(('default-port.', 'undefined-port.')))), error='')
        for name, values, config in expected(role, phase)]


def text(value):
    return '\n'.join(json.dumps(row) for row in value) + '\n'


def fixture(root):
    doc = dict(status='pass', scope=EVIDENCE_SCOPE, archive_sha256='b' * 64,
        boot_id='12345678-1234-1234-1234-123456789abc', arch='arm64', device='phone',
        target='127.0.0.1:56789', failures=[], roles={}, udid='1' * 64, caller_cleanup_verified=True)
    for index, role in enumerate(('normal', 'system-denied', 'system')):
        directory = root / role; directory.mkdir()
        nonce = str(index + 1) * 32
        generated, sdk = directory / 'Index.ets', directory / '@ohos.net.vpn.d.ts'
        generated.write_text(page(nonce, role)); sdk.write_text('// synthetic fixture NOT actual SDK')
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
                                    role, doc['udid'], module(role, compiled=True))
        paths['signing_receipt'].write_text(json.dumps(dict(status='pass', role=role,
            scope='actual_signature_profile_and_codesign_NOT_guest', verified_profile=profile,
            signed_sha256=digest(paths['signed_hap']))))
        record = dict(run_id=nonce, actual_uid=UID, status='pass', phases={})
        for field, path in paths.items():
            record.update({field: str(path), field + '_sha256': digest(path)})
        for phase in (('seed', 'restart') if role == 'system' else ('denial',)):
            observations = rows(role, phase, nonce, 124 if phase == 'restart' else 123)
            raw = directory / (phase + '.jsonl'); raw.write_text(text(observations))
            record['phases'][phase] = dict(results=observations, raw_results=str(raw), raw_results_sha256=digest(raw))
        doc['roles'][role] = record
    return doc


class VerifySysVpnStoreTests(unittest.TestCase):
    def check(self, value, role='system', phase='seed'):
        return verify(text(value), RUN, role, phase, identity(role))

    def evidence(self, doc):
        return verify_evidence(doc, 'b' * 64, '12345678-1234-1234-1234-123456789abc',
                               'arm64', 'phone', '127.0.0.1:56789')

    def test_typed_sources_roles_and_each_exact_positive_phase(self):
        for role in ('normal', 'system-denied', 'system'):
            self.assertNotIn('__SYSVPN_', page(RUN, role))
            self.assertEqual(module(role)['module']['requestPermissions'],
                [{'name': 'ohos.permission.MANAGE_VPN'}] if role == 'system' else [])
            for phase in (('seed', 'restart') if role == 'system' else ('denial',)):
                value = rows(role, phase)
                self.assertEqual(self.check(value, role, phase), value)
        self.assertIn('vpn.SysVpnType.IKEV2_IPSEC_PSK', page(RUN, 'system'))
        self.assertNotIn('getConnectedSysVpnConfig(', page(RUN, 'system'))
        for nonce, role in (('', 'normal'), (RUN, 'root'), ('z' * 32, 'system')):
            with self.assertRaises(ValueError): page(nonce, role)

    def test_lossy_arrays_prefixes_routes_flags_and_variant_credentials_are_rejected(self):
        for key, changed in (
            ('addresses', []), ('addresses', expected_config(RUN, 0, 0)['addresses'][:1]),
            ('localAddresses', []), ('remoteAddresses', ['198.19.0.1']),
            ('dnsAddresses', ['198.18.0.53']), ('searchDomains', ['a.' + RUN + '.invalid']),
            ('routes', []), ('mtu', 0), ('isIPv6Accepted', False), ('isBlocking', False),
            ('trustedApplications', []), ('userId', 0), ('password', ''), ('ovpnConfig', '')):
            value = rows('system', 'seed'); config = json.loads(value[2]['config']); config[key] = changed
            value[2]['config'] = json.dumps(config)
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(value)
        for key in ('prefixLength', 'family', 'port'):
            value = rows('system', 'seed'); config = json.loads(value[2]['config'])
            target = config['addresses'][1] if key == 'prefixLength' else config['addresses'][1]['address']
            target[key] = 1; value[2]['config'] = json.dumps(config)
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(value)
        value = rows('system', 'seed'); config = json.loads(value[2]['config'])
        config['routes'][1]['isExcludedRoute'] = False; value[2]['config'] = json.dumps(config)
        with self.assertRaises(ValueError): self.check(value)

    def test_js_bool_integer_equivalence_and_missing_required_fields_fail(self):
        for key in ('mtu', 'userId', 'isIPv4Accepted', 'isIPv6Accepted', 'isLegacy', 'isBlocking', 'saveLogin'):
            value = rows('system', 'seed'); config = json.loads(value[2]['config'])
            config[key] = True if type(config[key]) is int else int(config[key])
            value[2]['config'] = json.dumps(config)
            with self.subTest(key=key), self.assertRaises(ValueError): self.check(value)
        value = rows('system', 'seed'); config = json.loads(value[2]['config']); config.pop('addresses')
        value[2]['config'] = json.dumps(config)
        with self.assertRaises(ValueError): self.check(value)
        # Existing omission of an optional empty array is allowed, not loss of data.
        value = rows('system', 'seed')
        for row in value:
            if row['config']:
                config = json.loads(row['config'])
                for key in ('trustedApplications', 'blockedApplications'):
                    if not config[key]: config.pop(key)
                row['config'] = json.dumps(config)
        self.check(value)

    def test_numeric_denials_atomic_invalid_updates_and_cleanup_are_mandatory(self):
        for role in ('normal', 'system-denied'):
            value = rows(role, 'denial'); value[1]['values'] = [0, 0, 0]
            with self.assertRaises(ValueError): self.check(value, role, 'denial')
        for key, changed in ((name, changed) for name in ('invalid.prefix', 'invalid.route.0', 'invalid.route.1',
                                 'invalid.family.0', 'invalid.family.1', 'invalid.family.2', 'invalid.family.3',
                                 'invalid.port.0', 'invalid.port.1', 'invalid.port.2', 'invalid.port.3')
                             for changed in ([0, 0, 0], [1, '401', 1])):
            value = rows('system', 'seed'); next(row for row in value if row['name'] == key)['values'] = changed
            with self.assertRaises(ValueError): self.check(value)
        value = rows('system', 'seed'); target = next(row for row in value if row['name'] == 'after-invalid.get.0')
        config = json.loads(target['config']); config['addresses'][0]['prefixLength'] = 1
        target['config'] = json.dumps(config)
        with self.assertRaises(ValueError): self.check(value)
        value = rows('system', 'restart'); next(row for row in value if row['name'] == 'cleanup')['values'] = [1]
        with self.assertRaises(ValueError): self.check(value, phase='restart')
        seed, restarted = rows('system', 'seed'), rows('system', 'restart')
        with self.assertRaises(ValueError): verify_restart(seed, restarted)
        restarted[0]['values'][2] += 1; verify_restart(seed, restarted)

    def test_default_and_undefined_families_require_real_readback_and_both_optional_paths(self):
        source = page(RUN, 'system')
        self.assertIn('await this.defaultFamily(false)', source)
        self.assertIn('await this.defaultFamily(true)', source)
        for name in ('default-family.get.0', 'default-family.list.0', 'undefined-family.get.0', 'undefined-family.list.0'):
            value = rows('system', 'seed'); target = next(row for row in value if row['name'] == name)
            config = json.loads(target['config']); config['addresses'][0]['address']['family'] = 0
            target['config'] = json.dumps(config)
            with self.subTest(name=name), self.assertRaises(ValueError): self.check(value)

    def test_full_width_ports_zero_defaults_and_restart_are_required_not_accepted_truncation(self):
        source = page(RUN, 'system')
        self.assertIn('await this.defaultPort(false)', source)
        self.assertIn('await this.defaultPort(true)', source)
        for phase in ('seed', 'restart'):
            value = rows('system', phase)
            target = next(row for row in value if row['config'] and not row['name'].startswith(('default-port.', 'undefined-port.')))
            config = json.loads(target['config'])
            for field in (config['addresses'][0]['address'], config['localAddresses'][0]['address'],
                          config['routes'][0]['destination']['address'], config['routes'][0]['gateway']):
                original = field['port']; field['port'] = original & 255
                if original != field['port']:
                    target['config'] = json.dumps(config)
                    with self.subTest(phase=phase, port=original), self.assertRaises(ValueError): self.check(value, phase=phase)
                field['port'] = original
        for name in ('default-port.get.0', 'default-port.list.0', 'undefined-port.get.0', 'undefined-port.list.0'):
            value = rows('system', 'seed'); target = next(row for row in value if row['name'] == name)
            config = json.loads(target['config']); config['addresses'][0]['address']['port'] = 17
            target['config'] = json.dumps(config)
            with self.subTest(name=name), self.assertRaises(ValueError): self.check(value)

    def test_missing_reordered_failed_foreign_root_and_extra_observations_fail_closed(self):
        value = rows('system', 'seed')
        for changed in (value[:-1], value + [value[-1]], [value[1], value[0], *value[2:]]):
            with self.assertRaises(ValueError): self.check(changed)
        for key, changed in (('runId', 'f' * 32), ('role', 'normal'), ('error', 'failed'), ('values', [0, 0, 1])):
            altered = copy.deepcopy(value); altered[0][key] = changed
            with self.assertRaises(ValueError): self.check(altered)

    def test_full_archive_bound_evidence_replays_roles_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = fixture(Path(directory))
            self.assertEqual(self.evidence(doc), ['arkts_export:@ohos.net.vpn:' + name for name in METHODS])
            for key, changed in (('status', 'fail'), ('scope', 'export-only'), ('archive_sha256', 'old'),
                ('boot_id', 'old'), ('device', '2in1'), ('arch', 'x86_64'), ('target', 'foreign'),
                ('caller_cleanup_verified', False)):
                altered = copy.deepcopy(doc); altered[key] = changed
                with self.subTest(key=key), self.assertRaises(ValueError): self.evidence(altered)
            for role in doc['roles']:
                altered = copy.deepcopy(doc); altered['roles'].pop(role)
                with self.assertRaises(ValueError): self.evidence(altered)
            for field in ('inputs', 'application_identity', 'signed_hap', 'signing_receipt'):
                path = Path(doc['roles']['system'][field]); original = path.read_bytes()
                path.write_bytes(original + b' changed')
                with self.subTest(field=field), self.assertRaises(ValueError): self.evidence(doc)
                path.write_bytes(original)

    def test_suite_closure_and_delivery_gate_require_real_store_evidence(self):
        root = Path(__file__).resolve().parents[2]
        suite = (root / 'ci/capability-audit/run_packaged_qemu_suite.py').read_text()
        gate = (root / 'scripts/verify_first_artifact_gate.py').read_text()
        closure = (root / 'ci/capability-audit/verify_gap_closure.py').read_text()
        self.assertIn("check('sys-vpn-store'", suite)
        self.assertIn("with independent_probe(report, 'sys-vpn-store'", suite)
        self.assertIn('"sys-vpn-store"', gate.split('DEVICE_CHECKS', 1)[0])
        self.assertIn("elif name == 'sys-vpn-store':", gate)
        self.assertIn("vpn_store = child('sys-vpn-store/evidence.json')", closure)
        self.assertIn('from verify_sys_vpn_store_results import verify_evidence', closure)


if __name__ == '__main__':
    unittest.main()
