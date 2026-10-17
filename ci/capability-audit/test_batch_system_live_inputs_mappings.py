"""Prepared host protocol/POSIX fixture counterexamples, never guest evidence.

Authoring is source-only. Root owns all future test execution. Synthetic init,
passwd, image receipts and /proc fixtures below never count as actual package,
process, callback or absence observations.
"""
from copy import deepcopy
import os
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import batch_system_live_mappings as maps
import batch_system_run_live_inputs as live

BOOT = '11111111-2222-3333-4444-555555555555'
NONCE = 'a' * 32
OTHER = 'b' * 32
BUSINESS = maps.LIBRARIES['liblbsservice_gnss.z.so']
IMAGES = {'system': '1' * 64, 'vendor': '2' * 64}


def hx(value):
    return (value.encode() if isinstance(value, str) else value).hex()


def stat(pid, *, start=321, state='S', flags=0, comm='unit name ) with spaces', ppid=1):
    fields = [state, str(ppid), str(pid), '0', '0', '-1', str(flags)] + ['0'] * 12 + [str(start)] + ['0'] * 30
    return f'{pid} ({comm}) ' + ' '.join(fields) + '\n'


def mapping(path=BUSINESS, *, inode=3024, device='08:01', deleted=False, perms='r-xp'):
    return f'1000-2000 {perms} 00000000 {device} {inode} {path}' + (' (deleted)' if deleted else '') + '\n'


def process(pid=77, *, uid=1021, start=321, role='business', ppid=1):
    argv = ['/system/bin/sa_main', '/system/profile/locationhub.json'] if role == 'business' else ['/vendor/bin/hdf_devhost', '-i', '24', '-n', 'location_host']
    context = 'u:r:locationhub:s0' if role == 'business' else 'u:r:location_host:s0'
    library_rows = mapping() if role == 'business' else ''.join(mapping(p) for p in maps.ROLE_LIBRARIES['provider'].values())
    value = stat(pid, start=start, ppid=ppid)
    data = [value, f'Name:\tunit\nPid:\t{pid}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n',
            b'\x00'.join(s.encode() for s in argv) + b'\x00', argv[0], library_rows, context + '\n', value]
    return {op: (0, hx(payload)) for op, payload in zip(maps.OPS, data)}


def frame(*, nonce=NONCE, boot=BOOT, pid=None, libraries=(), records=None, start_ids=None, end_ids=None,
          uptime='1.00 0.00', direct_changes=None):
    records = {1: process(1, uid=0, ppid=0)} if records is None else records
    start_ids = list(records) if start_ids is None else start_ids
    end_ids = start_ids if end_ids is None else end_ids
    before = {'observer_uid': (0, hx('0')), 'boot_before': (0, hx(boot)), 'uptime_before': (0, hx(uptime))}
    after = {}
    for i, library in enumerate(libraries):
        before['file_before_' + str(i)] = (0, hx('801 3024 4096'))
        before['hash_before_' + str(i)] = (0, hx('3' * 64 + '  ' + library))
        after['file_after_' + str(i)] = (0, hx('801 3024 4096'))
        after['hash_after_' + str(i)] = (0, hx('3' * 64 + '  ' + library))
    if pid is None:
        before['list_before'] = (0, hx('\n'.join(map(str, start_ids))))
        after = {'list_after': (0, hx('\n'.join(map(str, end_ids)))), **after}
    after.update(uptime_after=(0, hx(uptime)), boot_after=(0, hx(boot)))
    changes = direct_changes or {}
    before = {key: changes.get(key, value) for key, value in before.items()}
    after = {key: changes.get(key, value) for key, value in after.items()}
    lines = ['|'.join(('BEGIN', maps.SCHEMA, nonce, boot, 'all' if pid is None else str(pid), ','.join(libraries) or '-'))]
    for key, (rc, raw) in before.items(): lines.append(f'D|{key}|{rc}|{raw}')
    count = 0
    for number, queries in records.items():
        lines.append('PID|' + str(number))
        for op, (rc, raw) in queries.items():
            lines.append(f'Q|{number}|{op}|{rc}|{raw}'); count += 1
        lines.append(f'TERMINAL|{number}|{len(queries)}')
    for key, (rc, raw) in after.items(): lines.append(f'D|{key}|{rc}|{raw}')
    lines.append(f'END|{nonce}|{len(records)}|{count}|{len(before) + len(after)}')
    return '\n'.join(lines) + '\n'


class MappingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def artifact(self, name, value):
        path = self.root / name
        data = value.encode() if isinstance(value, str) else json.dumps(value).encode()
        path.write_bytes(data)
        return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest())

    def parse(self, raw, *, nonce=NONCE, pid=None, libraries=()):
        return maps.parse_snapshot(raw, nonce, BOOT, pid=pid, libraries=libraries)

    def contract(self, role='business'):
        name = 'locationhub' if role == 'business' else 'location_host'
        uid_name = 'gps' if role == 'business' else 'location_host'
        argv = ['/system/bin/sa_main', '/system/profile/locationhub.json'] if role == 'business' else ['/vendor/bin/hdf_devhost', '-i', '24', '-n', 'location_host']
        init = self.artifact(role + '-init.json', dict(services=[dict(name=name, path=argv, uid=uid_name,
            secon='u:r:' + name + ':s0')]))
        passwd = self.artifact(role + '-passwd', 'gps:x:1021:1021::/:/bin/false\nlocation_host:x:1022:1022::/:/bin/false\n')
        image_paths = {'system': '/synthetic/system.img', 'vendor': '/synthetic/vendor.img'}
        receipt = self.artifact(role + '-config.json', dict(exit_code=0,
            image_records={k: dict(path=image_paths[k], sha256=v) for k, v in IMAGES.items()},
            dumped=[dict(**init, image='system' if role == 'business' else 'vendor', image_path='/etc/init/unit.cfg'),
                    dict(**passwd, image='system', image_path='/etc/passwd')]))
        assets = {key: dict(sha256='3' * 64, image_path=remote.removeprefix('/system').removeprefix('/vendor'),
                           image_path_aliases=[remote]) for key, remote in maps.ROLE_LIBRARIES[role].items()}
        evidence = self.artifact(role + '-image.json', dict(status='pass',
            scope='GNSS_source_build_image_binding_ONLY_NOT_loaded_or_public_location',
            system_image_sha256=IMAGES['system'], vendor_image_sha256=IMAGES['vendor'], image_assets=assets))
        descriptor = dict(role=role, service_name=name, init=init, passwd=passwd, config_receipt=receipt, image_evidence=evidence)
        if role == 'business':
            profile = self.artifact('profile.json', dict(process=name, systemability=[dict(name=2803, libpath='liblbsservice_gnss.z.so')]))
            profile_receipt = self.artifact('profile-receipt.json', dict(image=image_paths['system'],
                expected_system_image_sha256=IMAGES['system'], commands=[dict(argv=['/host/debugfs', '-R',
                    'dump ' + argv[1] + ' ' + profile['path'], image_paths['system']], exit_code=0, exists=True, sha256=profile['sha256'])]))
            descriptor.update(profile=profile, profile_receipt=profile_receipt)
        return descriptor

    def cuts(self, role='business', *, pid=77, start=321):
        libraries = list(maps.ROLE_LIBRARIES[role].values()); uid = 1021 if role == 'business' else 1022
        records = {pid: process(pid, uid=uid, role=role, start=start)}
        before = self.parse(frame(pid=pid, libraries=libraries, records=records), pid=pid, libraries=libraries)
        after = self.parse(frame(nonce=OTHER, pid=pid, libraries=libraries, records=records, uptime='1.10 0.00'),
                           nonce=OTHER, pid=pid, libraries=libraries)
        return before, after

    def test_complete_global_scan_can_emit_compatibility_view(self):
        observed = self.parse(frame())
        self.assertTrue(observed['global_absence_eligible'])
        self.assertIn('PROCESS /proc/1', maps.legacy_text(observed))
        self.assertEqual(observed['processes'][1]['before']['comm'], 'unit name ) with spaces')

    def test_partial_prefix_missing_pid_terminal_or_end_cannot_be_promoted(self):
        raw = frame(records={1: process(1, uid=0, ppid=0), 77: process()})
        for broken in (raw.rsplit('END|', 1)[0], raw.replace('TERMINAL|77|7\n', ''),
                       raw.replace('Q|77|maps|0|', 'Q|78|maps|0|'),
                       raw.replace('END|' + NONCE + '|2|14|7', 'END|' + NONCE + '|1|14|7')):
            with self.subTest(raw=broken[-100:]), self.assertRaises(ValueError): self.parse(broken)

    def test_old_process_text_and_manual_done_marker_are_not_full_scan(self):
        for raw in ('PROCESS /proc/77\nUid: 1021 1021 1021 1021\n', '__LIVE_PROCESS_SCAN_DONE__\n'):
            with self.assertRaises(ValueError): self.parse(raw)

    def test_boot_nonce_scope_and_root_visibility_are_bound(self):
        for raw in (frame().replace(NONCE, OTHER, 1), frame().replace(BOOT, '0' * 8 + BOOT[8:], 1)):
            with self.assertRaises(ValueError): self.parse(raw)
        observed = self.parse(frame(direct_changes={'observer_uid': (0, hx('20010040'))}))
        with self.assertRaises(maps.MappingGap): maps.legacy_text(observed)

    def test_list_error_is_gap_despite_end_and_some_successful_pids(self):
        observed = self.parse(frame(direct_changes={'list_before': (1, hx('ls: /proc: Permission denied'))}))
        self.assertFalse(observed['complete'])
        self.assertEqual(observed['queries']['list_before']['rc'], 1)
        with self.assertRaises(maps.MappingGap): maps.legacy_text(observed)

    def test_unread_new_pid_and_gone_pid_keep_enumeration_gap(self):
        for final in ([1, 77], [1, 88]):
            observed = self.parse(frame(end_ids=final))
            self.assertFalse(observed['global_absence_eligible'])
            self.assertTrue(any(g['kind'] == 'enumeration_churn' for g in observed['gaps']))
            with self.assertRaises(maps.MappingGap): maps.legacy_text(observed)

    def test_short_lived_unread_enumerator_is_never_inspected_or_complete(self):
        missing = {op: (1, hx('/proc/77/' + op + ': No such file or directory')) for op in maps.OPS}
        observed = self.parse(frame(records={1: process(1, uid=0, ppid=0), 77: missing}, end_ids=[1]))
        self.assertIsNone(observed['processes'][77]['before'])
        self.assertEqual(observed['processes'][77]['boot_id'], BOOT)
        self.assertFalse(observed['processes'][77]['complete'])
        self.assertEqual(observed['processes'][77]['queries']['stat_before']['rc'], 1)
        with self.assertRaises(maps.MappingGap): maps.legacy_text(observed)

    def test_any_failed_process_query_cannot_mean_no_library(self):
        for op in maps.OPS:
            record = process(); record[op] = (7, hx('partial raw data then Input/output error'))
            observed = self.parse(frame(records={1: process(1, uid=0, ppid=0), 77: record}))
            with self.subTest(operation=op):
                self.assertFalse(observed['processes'][77]['complete'])
                with self.assertRaises(maps.MappingGap): maps.legacy_text(observed)

    def test_successful_empty_live_maps_is_gap_not_absence(self):
        record = process(); record['maps'] = (0, '')
        observed = self.parse(frame(records={1: process(1, uid=0, ppid=0), 77: record}))
        self.assertTrue(any(g['kind'] == 'live_maps_empty' for g in observed['gaps']))
        with self.assertRaises(maps.MappingGap): maps.legacy_text(observed)

    def test_pid_reuse_or_generation_change_is_gap(self):
        record = process(); record['stat_after'] = (0, hx(stat(77, start=999)))
        observed = self.parse(frame(records={1: process(1, uid=0, ppid=0), 77: record}))
        self.assertTrue(any(g['kind'] == 'process_generation_changed' for g in observed['gaps']))
        with self.assertRaises(maps.MappingGap): maps.legacy_text(observed)

    def test_false_complete_flags_do_not_override_raw_gap(self):
        record = process(); record['maps'] = (1, hx('maps: Permission denied'))
        observed = self.parse(frame(records={1: process(1, uid=0, ppid=0), 77: record}))
        observed.update(complete=True, global_absence_eligible=True, gaps=[])
        with self.assertRaises(maps.MappingGap): maps.legacy_text(observed)

    def test_single_pid_complete_is_not_global_absence(self):
        before, _ = self.cuts()
        self.assertTrue(before['complete']); self.assertFalse(before['global_absence_eligible'])
        with self.assertRaises(maps.MappingGap): maps.legacy_text(before)

    def test_kernel_requires_both_stats_and_actual_empty_maps(self):
        record = process(2, uid=0)
        for op in ('stat_before', 'stat_after'):
            record[op] = (0, hx(stat(2, state='I', flags=maps.KERNEL_CONTRACT['PF_KTHREAD'])))
        record.update(exe=(1, ''), maps=(0, ''), cmdline=(0, ''))
        observed = self.parse(frame(records={1: process(1, uid=0, ppid=0), 2: record}))
        self.assertTrue(observed['complete']); self.assertEqual(observed['processes'][2]['classification'], 'kernel')
        record['maps'] = (1, hx('/proc/2/maps: Permission denied'))
        observed = self.parse(frame(records={1: process(1, uid=0, ppid=0), 2: record}))
        with self.assertRaises(maps.MappingGap): maps.legacy_text(observed)

    def test_maps_and_argv_must_retain_complete_boundaries(self):
        for op, value in (('maps', mapping().rstrip('\n')), ('cmdline', b'/system/bin/sa_main')):
            record = process(); record[op] = (0, hx(value))
            with self.subTest(op=op), self.assertRaises(ValueError):
                self.parse(frame(records={1: process(1, uid=0, ppid=0), 77: record}))

    def test_product_roles_derive_distinct_uids_and_dso_sets(self):
        business = maps.load_contract(self.contract(), image_hashes=IMAGES)
        provider = maps.load_contract(self.contract('provider'), image_hashes=IMAGES)
        self.assertEqual((business['uid'], provider['uid']), (1021, 1022))
        self.assertEqual(set(business['libraries']), {BUSINESS})
        self.assertEqual(len(provider['libraries']), 2)

    def test_unknown_contract_and_old_image_are_not_bare_uid_assertions(self):
        with self.assertRaises(maps.MappingGap): maps.load_contract(None, image_hashes=IMAGES)
        descriptor = self.contract()
        with self.assertRaises(ValueError): maps.load_contract(dict(descriptor, uid=1021), image_hashes=IMAGES)
        with self.assertRaises(ValueError): maps.load_contract(descriptor, image_hashes=dict(IMAGES, system='9' * 64))

    def test_contract_changed_init_or_passwd_is_rejected(self):
        for name in ('init', 'passwd', 'profile'):
            descriptor = self.contract(); Path(descriptor[name]['path']).write_text('{}\n')
            with self.subTest(source=name), self.assertRaises(ValueError): maps.load_contract(descriptor, image_hashes=IMAGES)

    def test_init_uid_name_requires_real_unique_passwd_entry(self):
        descriptor = self.contract()
        descriptor['passwd'] = self.artifact('wrong-passwd', 'other:x:1021:1021::/:/bin/false\n')
        # Also update the synthetic image-export join, so only account semantics
        # determine this counterexample rather than an earlier stale hash check.
        receipt = json.loads(Path(descriptor['config_receipt']['path']).read_text())
        receipt['dumped'][1].update(descriptor['passwd'])
        descriptor['config_receipt'] = self.artifact('changed-config', receipt)
        with self.assertRaises(ValueError): maps.load_contract(descriptor, image_hashes=IMAGES)

    def test_exact_business_pid_uid_generation_and_dso_binding(self):
        before, after = self.cuts()
        header = dict(processPid=77, traceEpochBootNs=500_000_000, snapshotBootNs=1_050_000_000)
        proof = maps.bind_trace_process(before, after, header, self.contract(), image_hashes=IMAGES)
        self.assertEqual((proof['pid'], proof['uid'], proof['start_ticks']), (77, 1021, 321))
        self.assertFalse(proof['global_absence_proven']); self.assertFalse(proof['wire_nonce_proven'])

    def test_kernel_context_terminal_nul_retains_raw_bytes(self):
        record = process(); raw = hx(b'u:r:locationhub:s0\x00')
        record['attr'] = (0, raw)
        observed = self.parse(frame(pid=77, records={77: record}), pid=77)
        self.assertEqual(observed['processes'][77]['attr'], 'u:r:locationhub:s0')
        self.assertEqual(observed['processes'][77]['queries']['attr']['hex'], raw)
        record['attr'] = (0, hx(b'u:r:location\x00hub:s0'))
        with self.assertRaises(ValueError): self.parse(frame(pid=77, records={77: record}), pid=77)

    def test_root_dump_client_pid_or_arbitrary_process_row_is_not_service(self):
        before, after = self.cuts()
        with self.assertRaises(ValueError):
            maps.bind_trace_process(before, after, dict(processPid=78, traceEpochBootNs=1, snapshotBootNs=1_050_000_000), self.contract(), image_hashes=IMAGES)

    def test_provider_requires_both_adapter_and_bridge_on_same_pid(self):
        before, after = self.cuts('provider')
        proof = maps.bind_process(before, after, 77, self.contract('provider'), image_hashes=IMAGES)
        self.assertEqual(proof['uid'], 1022)
        libraries = list(maps.ROLE_LIBRARIES['provider'].values())
        record = process(uid=1022, role='provider'); record['maps'] = (0, hx(mapping(libraries[0])))
        bad = self.parse(frame(nonce=OTHER, pid=77, libraries=libraries, records={77: record}), nonce=OTHER, pid=77, libraries=libraries)
        with self.assertRaises(ValueError): maps.bind_process(before, bad, 77, self.contract('provider'), image_hashes=IMAGES)

    def test_wrong_role_uid_argv_context_or_generation_never_binds(self):
        before, _ = self.cuts()
        for change in ('uid', 'argv', 'context', 'start'):
            record = process()
            if change == 'uid': record['status'] = (0, hx('Name:\tunit\nPid:\t77\nUid:\t1022\t1022\t1022\t1022\n'))
            elif change == 'argv': record['cmdline'] = (0, hx(b'locationhub\x00'))
            elif change == 'context': record['attr'] = (0, hx('u:r:location_host:s0\n'))
            else:
                for op in ('stat_before', 'stat_after'): record[op] = (0, hx(stat(77, start=999)))
            after = self.parse(frame(nonce=OTHER, pid=77, libraries=[BUSINESS], records={77: record}, uptime='1.10 0.00'), nonce=OTHER, pid=77, libraries=[BUSINESS])
            with self.subTest(change=change), self.assertRaises(ValueError): maps.bind_process(before, after, 77, self.contract(), image_hashes=IMAGES)

    def test_deleted_dso_wrong_inode_device_or_nonexecutable_mapping_rejected(self):
        before, _ = self.cuts()
        for kwargs in (dict(deleted=True), dict(inode=99), dict(device='08:02'), dict(perms='r--p')):
            record = process(); record['maps'] = (0, hx(mapping(**kwargs)))
            after = self.parse(frame(nonce=OTHER, pid=77, libraries=[BUSINESS], records={77: record}, uptime='1.10 0.00'), nonce=OTHER, pid=77, libraries=[BUSINESS])
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): maps.bind_process(before, after, 77, self.contract(), image_hashes=IMAGES)

    def test_dso_file_hash_or_identity_change_is_not_loaded_image_proof(self):
        before, _ = self.cuts()
        for key, value in (('hash_after_0', '9' * 64 + '  ' + BUSINESS), ('file_after_0', '801 3333 4096')):
            raw = frame(nonce=OTHER, pid=77, libraries=[BUSINESS], records={77: process()}, uptime='1.10 0.00', direct_changes={key: (0, hx(value))})
            after = self.parse(raw, nonce=OTHER, pid=77, libraries=[BUSINESS])
            with self.subTest(key=key), self.assertRaises(ValueError): maps.bind_process(before, after, 77, self.contract(), image_hashes=IMAGES)

    def test_trace_clock_outside_cuts_or_provider_role_rejected(self):
        before, after = self.cuts()
        for header in (dict(processPid=77, traceEpochBootNs=1, snapshotBootNs=9_000_000_000),
                       dict(processPid=77, traceEpochBootNs=2_000_000_000, snapshotBootNs=1_050_000_000)):
            with self.assertRaises(ValueError): maps.bind_trace_process(before, after, header, self.contract(), image_hashes=IMAGES)
        with self.assertRaises(ValueError): maps.bind_trace_process(before, after, dict(processPid=77, traceEpochBootNs=1, snapshotBootNs=1_050_000_000), self.contract('provider'), image_hashes=IMAGES)

    def evidence(self, *, gap=False):
        raw = frame(direct_changes={'observer_uid': (0, hx('20010040'))}) if gap else frame()
        observed = self.parse(raw)
        parser = Path(maps.__file__).resolve()
        entry = dict(nonce=NONCE, boot_id=BOOT, pid=None, libraries=[],
            parser=dict(path=str(parser), sha256=hashlib.sha256(parser.read_bytes()).hexdigest()),
            script=self.artifact('collector.sh', maps.snapshot_script(NONCE, BOOT)), raw=self.artifact('raw.txt', raw),
            parsed=self.artifact('parsed.json', {k: v for k, v in observed.items() if k != 'raw'}),
            complete=observed['complete'], global_absence_eligible=observed['global_absence_eligible'])
        marker = '__LIVE_GUEST_EXIT_' + 'c' * 32 + '__='
        script = maps.snapshot_script(NONCE, BOOT)
        command = dict(exit_code=0, argv=['/host/hdc', '-t', 'unit-target', 'shell',
            '(' + script + '); task_live_rc=$?; printf "\\n' + marker + '%s\\n" "$task_live_rc"'])
        log = self.artifact('command.log', raw + '\n' + marker + '0\n')
        command.update(log=log['path'], sha256=log['sha256'])
        return entry, command

    def test_raw_script_parser_and_actual_guest_exit_are_independently_bound(self):
        entry, command = self.evidence()
        observed = maps.verify_evidence(entry, command, target='unit-target')
        self.assertTrue(observed['global_absence_eligible'])
        for change in ('exit', 'script', 'target', 'raw', 'view', 'log'):
            entry, command = self.evidence()
            if change == 'exit': command['exit_code'] = 1
            elif change == 'script': command['argv'][-1] += '; printf success'
            elif change == 'target': command['argv'][2] = 'other-target'
            elif change == 'raw': Path(entry['raw']['path']).write_text('partial\n')
            elif change == 'view': Path(entry['parsed']['path']).write_text('{}')
            else: Path(command['log']).write_text('partial\n')
            with self.subTest(change=change), self.assertRaises(ValueError): maps.verify_evidence(entry, command, target='unit-target')

    def test_derived_complete_flag_or_legacy_view_cannot_wash_gap(self):
        entry, command = self.evidence(gap=True)
        entry['complete'] = entry['global_absence_eligible'] = True
        with self.assertRaises(ValueError): maps.verify_evidence(entry, command, target='unit-target')
        entry, command = self.evidence(gap=True)
        entry['legacy_view'] = self.artifact('fake-legacy.txt', 'PROCESS /proc/1\nUid: 0 0 0 0\n')
        with self.assertRaises(maps.MappingGap): maps.verify_evidence(entry, command, target='unit-target')

    def test_capture_mappings_keeps_gap_raw_and_never_emits_legacy_success(self):
        capture = live.Capture.__new__(live.Capture)
        capture.mapping_snapshot = Mock(return_value=dict(snapshot=self.parse(frame(end_ids=[1, 77])), evidence={}))
        capture.output = self.root
        with self.assertRaises(maps.MappingGap): capture.mappings('gap')
        self.assertFalse((self.root / 'gap.txt').exists())

    def test_shell_has_no_grep_awk_or_success_footer_error_bypass(self):
        script = maps.snapshot_script(NONCE, BOOT)
        self.assertNotIn('ls -1', script)
        self.assertNotIn('tr -d', script)
        self.assertNotIn('grep', script); self.assertNotIn('awk', script)
        self.assertIn('task_maps_rc=$?; task_maps_direct list_after', script)
        self.assertIn('task_maps_query "$task_maps_pid" maps', script)
        self.assertIn("IFS='\n\t '", script)
        for nonce, pid, libraries in (('bad', None, ()), (NONCE, True, ()), (NONCE, 0, ()), (NONCE, None, ('/tmp/evil',))):
            with self.assertRaises(ValueError): maps.snapshot_script(nonce, BOOT, pid=pid, libraries=libraries)

    @unittest.skipUnless(all(shutil.which(tool) for tool in ('sh', 'od', 'cat', 'readlink', 'id', 'stat', 'sha256sum')), 'root host needs actual POSIX fixture tools')
    def test_executed_host_proc_fixture_preserves_actual_query_failure_rc(self):
        # This runs only when root elects to execute tests. It reads a private
        # host fixture, never /proc of a guest, and never claims actual UID0.
        proc = self.root / 'proc'; (proc / 'sys/kernel/random').mkdir(parents=True)
        (proc / 'sys/kernel/random/boot_id').write_text(BOOT + '\n'); (proc / 'uptime').write_text('1.00 0.00\n')
        task = proc / '1'; (task / 'attr').mkdir(parents=True)
        (task / 'stat').write_text(stat(1, ppid=0)); (task / 'status').write_text('Name:\tunit\nPid:\t1\nUid:\t0\t0\t0\t0\n')
        (task / 'cmdline').write_bytes(b'/system/bin/init\x00'); (task / 'exe').symlink_to('/system/bin/init')
        (task / 'attr/current').write_text('u:r:init:s0\n')
        # Deliberately missing maps; an END/zero shell exit must not repair it.
        tools = proc.parent / 'minimal-guest-tools'; tools.mkdir()
        for tool in ('od', 'cat', 'readlink', 'id', 'stat', 'sha256sum'):
            (tools / tool).symlink_to(shutil.which(tool))
        command = subprocess.run([shutil.which('sh'), '-c', maps._snapshot_script(NONCE, BOOT, proc_root=str(proc))],
            env=dict(os.environ, PATH=str(tools)), capture_output=True, text=True, timeout=15)
        self.assertEqual(command.returncode, 0, command.stderr)
        observed = self.parse(command.stdout)
        self.assertNotEqual(observed['processes'][1]['queries']['maps']['rc'], 0)
        with self.assertRaises(maps.MappingGap): maps.legacy_text(observed)


if __name__ == '__main__':
    unittest.main()
