"""Host-only source/protocol QA; fixtures never count as native or guest proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import shutil
from unittest.mock import patch
from types import SimpleNamespace

import batch_network_openvpn_runtime_collect as collect
import batch_network_openvpn_runtime_project as project
import batch_network_openvpn_runtime_build as builder


def stat(pid, ppid, pgrp):
    return f'{pid} (name with spaces) S {ppid} {pgrp} ' + ' '.join(['0'] * 16 + ['1234'])


class RuntimeProtocolTests(unittest.TestCase):
    def test_independent_builder_receipt_rejects_failed_or_foreign_provenance(self):
        # Metadata guard only. This intentionally non-HAP unit file cannot pass
        # the separate generic compiled-HAP verifier used by binding().
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); source = root / 'source'; source.mkdir()
            hap = root / 'unit-NOT-real.hap'; hap.write_bytes(b'unit metadata fixture')
            tools = {}
            for name in ('node', 'ohpm', 'hvigor'):
                path = root / name; path.write_text('unit tool never executed'); tools[name] = project.descriptor(path)
            cpu = root / 'cpu-cap.cjs'; shutil.copyfile(project.HERE / 'fixtures/batch_media/audio_haptic_runtime/cpu-cap.cjs', cpu)
            tools['cpu_cap'] = project.descriptor(cpu)
            prefix = [str(root / 'node'), '--max-old-space-size=2048', '--require', str(cpu)]
            commands = [('dependencies', prefix + [str(root / 'ohpm'), 'install', '--all', '--registry',
                         'http://127.0.0.1:9', '--fetch_timeout', '10000', '--retry_times', '0']),
                        ('compile', prefix + [str(root / 'hvigor'), 'assembleHap', '--mode', 'module', '-p',
                         'product=default', '-p', 'module=entry', '-p', 'debuggable=false', '-p',
                         'hvigor-obfuscation=false', '--no-daemon', '--no-parallel', '--no-incremental',
                         '--max-old-space-size', '2048'])]
            value = {'scope': project.SDK_SCOPE, 'exit_code': 0, 'failures': [], 'node_version': 'v18.20.1',
                'source_commit': 'a' * 40, 'runner_sha256': project.sha(project.HERE / 'batch_network_openvpn_runtime_build.py'),
                'source_tools': {name: project.sha(project.HERE / name) for name in project.SOURCE_TOOLS},
                'source_files': {project.SDK_NAME: {}}, 'tools': tools,
                'haps': [{'project': project.SDK_NAME, **project.descriptor(hap), 'bytes': hap.stat().st_size}],
                'commands': [dict(project=project.SDK_NAME, label=label, argv=argv, cwd=str(source), exit_code=0) for label, argv in commands]}
            evidence = root / 'evidence.json'
            project.verify_sdk_receipt(value, evidence, source, hap)
            for change in ('scope', 'failed', 'failure-list', 'runner', 'source-tool', 'extra-project', 'cwd', 'argv', 'hap'):
                wrong = copy.deepcopy(value)
                if change == 'scope': wrong['scope'] = 'foreign builder'
                if change == 'failed': wrong['exit_code'] = 1
                if change == 'failure-list': wrong['failures'] = ['actual failed batch']
                if change == 'runner': wrong['runner_sha256'] = 'f' * 64
                if change == 'source-tool': wrong['source_tools'][project.SOURCE_TOOLS[0]] = 'f' * 64
                if change == 'extra-project': wrong['source_files']['foreign'] = {}
                if change == 'cwd': wrong['commands'][1]['cwd'] = str(root / 'foreign')
                if change == 'argv': wrong['commands'][1]['argv'].append('--foreign-flag')
                if change == 'hap': wrong['haps'][0]['sha256'] = 'f' * 64
                with self.subTest(change=change), self.assertRaises(ValueError):
                    project.verify_sdk_receipt(wrong, evidence, source, hap)

    def test_codesign_allows_only_page_bitmap_and_preserves_every_compiled_byte(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); unsigned, signed = root / 'unsigned.hap', root / 'signed.hap'
            payload = {'module.json': b'{"compiled":"unit protocol fixture"}', 'ets/modules.abc': b'unit-abc'}
            with zipfile.ZipFile(unsigned, 'w') as bundle:
                for name, data in payload.items(): bundle.writestr(name, data)
            for change in ('valid', 'rewrite', 'extra', 'missing', 'empty', 'unaligned'):
                with zipfile.ZipFile(signed, 'w') as bundle:
                    for name, data in payload.items():
                        bundle.writestr(name, b'changed' if change == 'rewrite' and name == 'ets/modules.abc' else data)
                    if change != 'missing': bundle.writestr('.pages.info', b'' if change == 'empty' else b'0' * (7 if change == 'unaligned' else 8))
                    if change == 'extra': bundle.writestr('foreign.txt', b'foreign')
                if change == 'valid': collect.verify_signed_payload(unsigned, signed)
                else:
                    with self.subTest(change=change), self.assertRaises(ValueError): collect.verify_signed_payload(unsigned, signed)

    def test_foreign_connected_getter_prevents_first_mutating_request(self):
        caller = object.__new__(collect.Collector); caller.started = False; calls = []
        def phase(action):
            calls.append(action)
            if action == 'inspect': raise ValueError('actual getter observed foreign VPN')
        caller.phase = phase
        with self.assertRaises(ValueError): caller.start_owned_session()
        self.assertEqual(calls, ['inspect']); self.assertFalse(caller.started)

    def test_install_only_failures_attempt_own_uninstall_even_if_force_stop_fails(self):
        for confirmed in (False, True):
            caller = object.__new__(collect.Collector)
            caller.guest = SimpleNamespace(target='owned'); caller.args = SimpleNamespace(hdc='unit-hdc')
            caller.install_attempted = True; caller.installed = confirmed; caller.started = False
            caller.report = {'status': 'fail', 'failures': ['original identity/readback failure'], 'cleanup_verified': False}
            state = {'present': True}; calls = []
            def shell(value, label):
                calls.append(label)
                if label == 'stop-own-QA-Ability': raise ValueError('force-stop failed')
                return project.BUNDLE if state['present'] else ''
            def command(argv, label):
                calls.append(label); self.assertEqual(argv[-2:], ['uninstall', project.BUNDLE]); state['present'] = False
                return 'Success'
            caller.shell = shell; caller.command = command
            caller.cleanup()
            self.assertTrue(caller.report['qa_bundle_removed']); self.assertFalse(state['present'])
            self.assertIn('BMS-after-uninstall', calls); self.assertFalse(caller.report['cleanup_verified'])

    def test_unproved_live_owner_is_preserved_without_uninstall(self):
        caller = object.__new__(collect.Collector)
        caller.guest = SimpleNamespace(); caller.install_attempted = True; caller.installed = True; caller.started = True
        caller.report = {'status': 'fail', 'failures': [], 'cleanup_verified': False}
        caller.remove_fault = lambda: None
        caller.phase = lambda action: (_ for _ in ()).throw(ValueError('public destroy failed'))
        caller.command = lambda *args: self.fail('must not uninstall an unproved live owner')
        caller.cleanup()
        self.assertFalse(caller.report['cleanup_verified']); self.assertEqual(len(caller.report['failures']), 2)

    def test_proc_parent_group_and_start_are_actual_fields(self):
        value = project.proc_stat(stat(23, 10, 23))
        self.assertEqual((value['pid'], value['ppid'], value['pgrp'], value['start']), (23, 10, 23, '1234'))

    def test_claim_requires_real_exec_argv_ancestry_uid_and_one_session(self):
        processes = {}
        for pid, ppid, pgrp, name in ((10, 1, 10, 'qemu_openvpn_service'), (23, 10, 23, 'qemu_openvpn_service'),
                                     (24, 23, 23, 'qemu_openvpn')):
            processes[pid] = {**project.proc_stat(stat(pid, ppid, pgrp)), 'uid': 1098,
                'exe': '/system/bin/' + name, 'argv': []}
        processes[24]['argv'] = ['/system/bin/qemu_openvpn', '--config', project.ROOT + '/session-Ab12Cd/client.ovpn',
            '--setenv', 'OHOS_OPENVPN_SESSION', 'a' * 32]
        snapshot = {'processes': processes, 'entries': ['session-Ab12Cd|1098:1098:700:directory']}
        self.assertEqual(collect.claimed(snapshot, 'b' * 64)['worker']['pid'], 23)
        for change in ('uid', 'parent', 'group', 'alias', 'generation', 'directory', 'extra', 'truncated'):
            value = copy.deepcopy(snapshot)
            if change == 'uid': value['processes'][24]['uid'] = 0
            if change == 'parent': value['processes'][23]['ppid'] = 999
            if change == 'group': value['processes'][24]['pgrp'] = 10
            if change == 'alias': value['processes'][24]['exe'] = '/data/local/tmp/fake'
            if change == 'generation': value['processes'][24]['argv'][-1] = 'bad'
            if change == 'directory': value['processes'][24]['argv'][2] = project.ROOT + '/session-../client.ovpn'
            if change == 'extra': value['entries'].append('session-ZZ12ab|1098:1098:700:directory')
            if change == 'truncated': value['processes'][24]['argv'] = ['--config']
            with self.subTest(change=change), self.assertRaises(ValueError): collect.claimed(value, 'b' * 64)

    def test_journal_rejects_connected_getter_denied_stale_reordered_and_restart(self):
        base = dict(schema_version=1, run_id='a' * 32, boot_id='b' * 36, operation_id='c' * 32, action='setup',
                    sequence=1, uid=20010001, pid=23, token_id=123, event='permission', code=0, value='')
        good = json.dumps(base) + '\n'
        self.assertEqual(len(collect.journal(good, 'a' * 32, 'b' * 36, 20010001, 123)), 1)
        for key, wrong in (('code', -1), ('run_id', 'f' * 32), ('sequence', 2), ('schema_version', True), ('token_id', 999), ('action', 'foreign')):
            row = dict(base); row[key] = wrong
            with self.subTest(key=key), self.assertRaises(ValueError):
                collect.journal(json.dumps(row) + '\n', 'a' * 32, 'b' * 36, 20010001, 123)
        row = dict(base, event='getters', value=json.dumps({'config_undefined': False, 'apps': []}))
        with self.assertRaises(ValueError): collect.journal(json.dumps(row) + '\n', 'a' * 32, 'b' * 36, 20010001, 123)
        other = dict(base, sequence=2, pid=24)
        with self.assertRaises(ValueError): collect.journal(good + json.dumps(other) + '\n', 'a' * 32, 'b' * 36, 20010001, 123)

    def test_raw_process_evidence_rejects_unreadable_live_proc(self):
        with self.assertRaises(ValueError): collect.parse_snapshot('E|/proc/123\n')
        with self.assertRaises(ValueError): collect.parse_snapshot('')

    def test_profile_only_permits_one_exact_loopback_endpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'unit-only-not-valid-TLS.ovpn'
            unit = 'client\nproto udp4\nremote 127.0.0.1 54123\n<ca>\nUNIT ONLY\n</ca>\n<cert>\nUNIT ONLY\n</cert>\n'
            path.write_text(unit)
            self.assertTrue(project.profile_input(path, 54123, 'a' * 32).endswith('# qemu-owned-run-' + 'a' * 32 + '\n'))
            for suffix in ('remote 203.0.113.1 1194\n', '<connection>\n', 'up /tmp/hook\n', 'config foreign\n'):
                path.write_text(unit + suffix)
                with self.subTest(suffix=suffix), self.assertRaises(ValueError): project.profile_input(path, 54123, 'a' * 32)

    def test_fixture_is_typed_real_system_setup_and_never_synthetic_connected(self):
        text = (project.FIX / 'EntryAbility.ets').read_text()
        for call in ('vpn.createVpnConnection(this.context)', 'this.connection.setUp(config)', 'this.connection.destroy()',
                     'checkAccessTokenSync', 'vpn.getConnectedSysVpnConfig()', 'vpn.getConnectedVpnAppInfo()'):
            self.assertIn(call, text)
        self.assertIn('vpnId:', text); self.assertIn('vpn.SysVpnType.OPENVPN', text)
        self.assertNotIn('NotifyConnectStage', text)

    def test_render_reads_real_sdk105_but_never_builds_or_signs(self):
        sdk = Path('/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); profile = root / 'UNIT-ONLY-not-valid-native-TLS.ovpn'
            profile.write_text('client\nproto udp4\nremote 127.0.0.1 54123\n<ca>\nUNIT ONLY\n</ca>\n<cert>\nUNIT ONLY\n</cert>\n')
            with patch('subprocess.run', side_effect=AssertionError('no build/sign allowed')):
                value = project.prepare(root / 'project', sdk, profile, 54123)
            self.assertFalse(value['native_build_or_runtime_proof'])
            module = project.load(root / 'project/entry/src/main/module.json5')['module']
            self.assertEqual(module['requestPermissions'], [{'name': project.PERMISSION}])
            self.assertEqual(module['deviceTypes'], ['default'])
            self.assertEqual((root / 'project').stat().st_mode & 0o777, 0o700)

    def test_builder_requires_explicit_root_execution_before_any_subprocess(self):
        with patch('subprocess.Popen', side_effect=AssertionError('SDK must not execute')):
            with self.assertRaises(ValueError): builder.build(SimpleNamespace(execute_sdk_build=False))

    def test_signature_contract_rejects_extra_permissions_wrong_apl_bundle_or_udid(self):
        template = {'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}}
        module = {'app': {'bundleName': project.BUNDLE}, 'module': {'requestPermissions': [{'name': project.PERMISSION}]}}
        actual = collect.profile(template, 'system', 'a' * 64, module)
        collect.verify_profile(actual, 'a' * 64)
        for field, wrong in (('apl', 'normal'), ('app-feature', 'hos_normal_app'), ('bundle-name', 'foreign.bundle')):
            value = copy.deepcopy(actual); value['bundle-info'][field] = wrong
            with self.subTest(field=field), self.assertRaises(ValueError): collect.verify_profile(value, 'a' * 64)
        value = copy.deepcopy(actual); value['acls']['allowed-acls'].append('ohos.permission.INTERNET')
        with self.assertRaises(ValueError): collect.verify_profile(value, 'a' * 64)
        with self.assertRaises(ValueError): collect.verify_profile(actual, 'b' * 64)
        with self.assertRaises(ValueError): collect.profile(copy.deepcopy(template), 'normal', 'a' * 64, module)


if __name__ == '__main__': unittest.main()
