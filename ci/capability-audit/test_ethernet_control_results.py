"""Synthetic strict-replay rejection fixtures, not actual network acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from build_ethernet_control_probe import BUNDLE, ROLES, PERMISSIONS, TEMPLATE, SCOPE, module, page
from run_normal_hap_probe import APP_FILES
from run_root_probe import digest
from sign_ethernet_control_probe import configure_profile
import test_verify_always_on_vpn_results as identities
from verify_ethernet_control_results import (
    BEHAVIOR_CONTRACT, EVIDENCE_SCOPE, EXPORT_CONTRACTS, METHODS, expected, verify, verify_evidence)

UID = identities.UID
RUN = identities.RUN


def observations(role, phase, nonce=RUN, pid=123):
    def values(expected_value):
        if expected_value is None: return [UID, UID, pid]
        if type(expected_value) is bool: return [1, int(expected_value), 4099 if expected_value else 4098]
        return expected_value
    return [dict(runId=nonce, role=role, name=name, values=values(value), error='')
            for name, value in expected(role, phase)]


def text(rows):
    return '\n'.join(json.dumps(row) for row in rows) + '\n'


def fixture(root):
    doc = dict(status='pass', scope=EVIDENCE_SCOPE, archive_sha256='b' * 64,
        boot_id='12345678-1234-1234-1234-123456789abc', arch='arm64', device='phone',
        target='127.0.0.1:56789', failures=[], roles={}, udid='1' * 64,
        caller_cleanup_verified=True, commands=[], role_setup={})
    def command(label, reply, script=None, argv=None):
        path = root / (f'{len(doc["commands"]):03d}-' + label + '.log')
        path.write_text(reply)
        doc['commands'].append(dict(argv=argv or ['hdc', '-t', doc['target'], 'shell', script],
            log=str(path), sha256=digest(path), exit_code=0))
    for index, role in enumerate(ROLES):
        directory = root / role; directory.mkdir()
        nonce = str(index + 1) * 32
        generated, sdk = directory / 'Index.ets', directory / '@ohos.net.ethernet.d.ts'
        generated.write_text(page(nonce, role)); sdk.write_text('// NOT actual SDK')
        paths = {key: directory / name for key, name in (('inputs', 'inputs.json'),
            ('application_identity', 'identity.json'), ('signed_hap', 'NOT-signed.hap'),
            ('unsigned_hap', 'NOT-built.hap'), ('signing_receipt', 'receipt.json'))}
        paths['inputs'].write_text(json.dumps(dict(schema_version=1, run_id=nonce, role=role, arch='arm64', scope=SCOPE,
            request_permissions=list(PERMISSIONS) if role == 'system' else [], template_sha256=digest(TEMPLATE),
            generated_source=str(generated), generated_source_sha256=digest(generated),
            sdk_declaration=str(sdk), sdk_declaration_sha256=digest(sdk))))
        identity = identities.identity(role); paths['application_identity'].write_text(identity)
        for field in ('unsigned_hap', 'signed_hap'):
            with zipfile.ZipFile(paths[field], 'w') as hap:
                hap.writestr('module.json', json.dumps(module(role, compiled=True)))
        profile = configure_profile({'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}},
                                    role, doc['udid'], module(role, compiled=True))
        paths['signing_receipt'].write_text(json.dumps(dict(status='pass', role=role,
            scope='actual_signature_profile_and_codesign_NOT_guest', verified_profile=profile,
            signed_sha256=digest(paths['signed_hap']), unsigned_sha256=digest(paths['unsigned_hap']))))
        record = dict(run_id=nonce, actual_uid=UID, status='pass', phases={})
        for field, path in paths.items():
            record.update({field: str(path), field + '_sha256': digest(path)})
        doc['roles'][role] = record
        prefix = role + '-pre-replacement-'
        command(prefix+'stop-own-previous-audit-app', 'force stop process successfully.\n', 'aa force-stop '+BUNDLE)
        for _ in range(2):
            command(prefix+'previous-own-kernel-processes', 'ABSENT\n', 'task_probe_pids=$(pidof '+BUNDLE+'); '+
                'if test -n "$task_probe_pids"; then printf "%s\\n" "$task_probe_pids"; else echo ABSENT; fi')
            command(prefix+'previous-own-ability-and-process-records', 'User ID #100\nAppRunningRecords:\n',
                'aa dump -a -u 100')
        doc['role_setup'][role] = {'caller_drained_before_replacement': {
            'scope': 'bounded_own_test_bundle_lifecycle_setup_NOT_capability_pass', 'bundle': BUNDLE,
            'stop_reply': 'force stop process successfully.', 'observations': 2,
            'consecutive_absent_observations': 2, 'kernel_process_absent': True,
            'ability_process_records_absent': True}}
        command(role+'-uninstall-own-old', 'uninstall bundle successfully.\n',
            argv=['hdc','-t',doc['target'],'uninstall',BUNDLE])
        command(role + '-install', 'install bundle successfully.\n',
                argv=['hdc', '-t', doc['target'], 'install', str(paths['signed_hap'])])
        command(role + '-identity', identity, 'bm dump -n ' + BUNDLE)
        for phase in (('seed', 'restart') if role == 'system' else ('denial',)):
            command(role + '-' + phase + '-boot-before', doc['boot_id'] + '\n', 'cat /proc/sys/kernel/random/boot_id')
            if phase == 'restart':
                command('system-force-stop-own-caller', 'force stop process successfully.\n', 'aa force-stop ' + BUNDLE)
                command('system-old-caller-absence', 'ABSENT\n',
                        'if test -d /proc/123; then echo PRESENT; else echo ABSENT; fi')
            command(role + '-' + phase + '-launch', 'start ability successfully.\n',
                    'aa start -a EntryAbility -b ' + BUNDLE)
            rows = observations(role, phase, nonce, 124 if phase == 'restart' else 123)
            raw = directory / (phase + '.jsonl'); raw.write_text(text(rows))
            record['phases'][phase] = dict(results=rows, raw_results=str(raw), raw_results_sha256=digest(raw))
            command(role + '-' + phase + '-poll', text(rows),
                    'cat ' + APP_FILES + 'ethernet-control-' + nonce + '-results.log 2>/dev/null')
            command(role + '-' + phase + '-boot-after', doc['boot_id'] + '\n', 'cat /proc/sys/kernel/random/boot_id')
    command('stop-own-previous-audit-app', 'force stop process successfully.\n', 'aa force-stop ' + BUNDLE)
    for _ in range(2):
        command('previous-own-kernel-processes', 'ABSENT\n', 'task_probe_pids=$(pidof ' + BUNDLE + '); ' +
                'if test -n "$task_probe_pids"; then printf "%s\\n" "$task_probe_pids"; else echo ABSENT; fi')
        command('previous-own-ability-and-process-records', 'User ID #100\nAppRunningRecords:\n', 'aa dump -a -u 100')
    return doc


class EthernetControlResultTests(unittest.TestCase):
    def check(self, rows, role='system', phase='seed'):
        return verify(text(rows), RUN, role, phase, identities.identity(role))

    def evidence(self, doc):
        return verify_evidence(doc, 'b' * 64, '12345678-1234-1234-1234-123456789abc',
                               'arm64', 'phone', '127.0.0.1:56789')

    def test_live_kernel_or_ability_record_cannot_hide_behind_drain_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            doc = fixture(Path(temporary))
            self.evidence(doc)
            for label, reply in (
                    ('normal-pre-replacement-previous-own-kernel-processes', '5746\n'),
                    ('normal-pre-replacement-previous-own-ability-and-process-records',
                     'User ID #100\nAppRunningRecords:\n'+BUNDLE+'\n')):
                row = [row for row in doc['commands'] if Path(row['log']).name.endswith(label+'.log')][-1]
                path = Path(row['log']); before = path.read_text()
                path.write_text(reply); row['sha256'] = digest(path)
                with self.assertRaises(ValueError): self.evidence(doc)
                path.write_text(before); row['sha256'] = digest(path)

    def test_missing_or_reordered_pre_replacement_queries_never_close_the_gap(self):
        with tempfile.TemporaryDirectory() as temporary:
            doc = fixture(Path(temporary))
            for suffix in ('stop-own-previous-audit-app', 'previous-own-kernel-processes',
                           'previous-own-ability-and-process-records'):
                changed = copy.deepcopy(doc)
                index = next(i for i,row in enumerate(changed['commands']) if
                    Path(row['log']).name.endswith('normal-pre-replacement-'+suffix+'.log'))
                del changed['commands'][index]
                with self.assertRaises(ValueError): self.evidence(changed)
            changed = copy.deepcopy(doc)
            install = next(i for i,row in enumerate(changed['commands']) if Path(row['log']).name.endswith('normal-install.log'))
            changed['commands'][0],changed['commands'][install] = changed['commands'][install],changed['commands'][0]
            with self.assertRaises(ValueError): self.evidence(changed)

    def test_roles_and_exact_positive_phases(self):
        for role in ROLES:
            self.assertNotIn('__ETHERNET_', page(RUN, role))
            self.assertEqual(module(role)['module']['requestPermissions'],
                [{'name': name} for name in PERMISSIONS] if role == 'system' else [])
            for phase in (('seed', 'restart') if role == 'system' else ('denial',)):
                rows = observations(role, phase); self.assertEqual(self.check(rows, role, phase), rows)
        for nonce, role in (('', 'normal'), (RUN, 'root'), ('z' * 32, 'system')):
            with self.assertRaises(ValueError): page(nonce, role)

    def test_false_success_carrier_only_boolean_and_invalid_flags_fail(self):
        for values in ([1, 0, 4099], [1, 0, 1], [1, 0, -1], [1, 0, 0x100000000], [1, 0, True], [1, 0, '0x0']):
            rows = observations('system', 'seed'); rows[2]['values'] = values
            with self.subTest(values=values), self.assertRaises(ValueError): self.check(rows)
        rows = observations('system', 'seed'); rows[1]['values'] = [0, 1, 4099]
        with self.assertRaises(ValueError): self.check(rows)

    def test_full_kernel_flags_are_not_truncated_to_ioctl_short_or_carrier_state(self):
        rows = observations('system', 'seed')
        for row, (_, value) in zip(rows, expected('system', 'seed')):
            if type(value) is bool:
                # Linux flags include bits >=16; only IFF_UP is the admin switch.
                row['values'][2] = 0xFFFFFFFF if value else 0xFFFFFFFE
        self.check(rows)
        self.assertIn('flags > 0xFFFFFFFF', page(RUN, 'system'))

    def test_missing_reordered_failed_foreign_root_and_wrong_denials_fail(self):
        value = observations('system', 'seed')
        for rows in (value[:-1], value + [value[-1]], [value[1], value[0], *value[2:]]):
            with self.assertRaises(ValueError): self.check(rows)
        for key, changed in (('runId', 'f' * 32), ('error', 'failed'), ('values', [0, 0, 123])):
            rows = copy.deepcopy(value); rows[0][key] = changed
            with self.assertRaises(ValueError): self.check(rows)
        for role in ('normal', 'system-denied'):
            for values in ([0, 0, 0], [1, '201', 1], [1, 202 if role == 'system-denied' else 201, 1]):
                rows = observations(role, 'denial'); rows[1]['values'] = values
                with self.assertRaises(ValueError): self.check(rows, role, 'denial')

    def test_bound_evidence_and_actual_command_journal_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = fixture(Path(directory))
            self.assertEqual(self.evidence(doc), [*EXPORT_CONTRACTS, BEHAVIOR_CONTRACT])
            for key, changed in (('status', 'fail'), ('scope', 'discovery'), ('archive_sha256', 'old'),
                ('boot_id', 'old'), ('arch', 'x86_64'), ('target', 'foreign'), ('device', '2in1'),
                ('caller_cleanup_verified', False), ('commands', [])):
                altered = copy.deepcopy(doc); altered[key] = changed
                with self.subTest(key=key), self.assertRaises(ValueError): self.evidence(altered)
            for label in ('system-install', 'system-seed-launch', 'system-old-caller-absence',
                          'stop-own-previous-audit-app', 'previous-own-kernel-processes'):
                altered = copy.deepcopy(doc)
                altered['commands'] = [row for row in altered['commands'] if not Path(row['log']).name.endswith(label + '.log')]
                with self.subTest(label=label), self.assertRaises(ValueError): self.evidence(altered)
            for field in ('inputs', 'application_identity', 'signed_hap', 'signing_receipt', 'unsigned_hap'):
                path = Path(doc['roles']['system'][field]); original = path.read_bytes(); path.write_bytes(original + b' changed')
                with self.subTest(field=field), self.assertRaises(ValueError): self.evidence(doc)
                path.write_bytes(original)

    def test_failed_or_changed_commands_and_still_present_caller_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            doc = fixture(Path(directory))
            for key, value in (('exit_code', 1), ('exit_code', False), ('timed_out', True)):
                changed = copy.deepcopy(doc); changed['commands'][0][key] = value
                with self.assertRaises(ValueError): self.evidence(changed)
            row = next(row for row in doc['commands'] if Path(row['log']).name.endswith('system-old-caller-absence.log'))
            path = Path(row['log']); path.write_text('PRESENT\n'); row['sha256'] = digest(path)
            with self.assertRaises(ValueError): self.evidence(doc)

    def test_suite_gate_and_closure_require_real_behavior_not_host_compile(self):
        root = Path(__file__).resolve().parents[2]
        suite = (root / 'ci/capability-audit/run_packaged_qemu_suite.py').read_text()
        gate = (root / 'scripts/verify_first_artifact_gate.py').read_text()
        closure = (root / 'ci/capability-audit/verify_gap_closure.py').read_text()
        self.assertIn("check('ethernet-control'", suite)
        self.assertIn('"ethernet-control"', gate.split('DEVICE_CHECKS', 1)[0])
        self.assertIn("elif name == 'ethernet-control':", gate)
        self.assertIn("ethernet = child('ethernet-control/evidence.json')", closure)
        self.assertIn('from verify_ethernet_control_results import verify_evidence', closure)

    def test_behavior_closure_is_only_the_three_audited_API26_controls(self):
        root = Path(__file__).resolve().parents[2]
        ledger = json.loads((root / 'docs/capability-audit/native-arkts11-gap-ledger.json').read_text())
        # Bind the claim to the original finding, not the broader Ethernet/BPF
        # backends. A discovery-only or partial-role document still cannot close it.
        findings = []
        def collect(value):
            if isinstance(value, dict):
                if value.get('id') == 'ethernet-api26-export-gaps':
                    findings.append(value)
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)
        collect(ledger)
        self.assertTrue(findings)
        for finding in findings:
            self.assertTrue(all(name in finding['evidence'] for name in METHODS))
        with tempfile.TemporaryDirectory() as directory:
            doc = fixture(Path(directory))
            closed = self.evidence(doc)
            self.assertEqual([item for item in closed if item.startswith('behavior:')], [BEHAVIOR_CONTRACT])
            partial = copy.deepcopy(doc)
            del partial['roles']['system']['phases']['restart']
            with self.assertRaises(ValueError):
                self.evidence(partial)


if __name__ == '__main__':
    unittest.main()
