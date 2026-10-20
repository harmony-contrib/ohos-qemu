"""Synthetic source-state boundaries only; never admit an observer or a guest."""
from pathlib import Path
import copy
import json
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ci/capability-audit'))
from number_native496 import consumer496 as core
from number_native496 import evidence_join496 as join

BOOT = '12345678-1234-1234-1234-123456789abc'


def clock(at):
    return dict(schema='number-native-clock496/v1', nonce='a' * 32, boot_id=BOOT,
                clk_tck=100, monotonic_before_ns=at, boottime_ns=at + 5,
                monotonic_after_ns=at + 10, time_ns_dev=4, time_ns_inode=900)


def source_graph():
    """An untrusted finite lifecycle, never an actual callback observation."""
    rows = []
    def add(event, seq, at, instance=0, connection=0, request=0, route=0):
        value = dict(event=event, seq=seq, mono_ns=at, pid=123, tid=123,
                     instance=instance, connection=connection, request=request,
                     route=route, result=-1 if event.endswith('-enter') else 1,
                     caller_pid=456 if request else 0,
                     caller_uid=20001001 if request else 0,
                     caller_token=777 if request else 0)
        rows.append(core.Event('native', value, b'SYNTHETIC ONLY', 123, 123))
    def load(event, at, result):
        return core.Event('load', dict(event=event, pid=123, tid=123, load=100000000,
            mono_ns=at, result=result, path='/system/lib64/libnumber_identity.z.so'),
            b'SYNTHETIC ONLY', 123, 123)
    add('register-enter', 1, 110000000)
    add('register-result', 2, 120000000)
    add('creator-enter', 3, 160000000)
    add('create-result', 5, 170000000, 4)
    add('creator-result', 6, 180000000, 4)
    add('connect-enter', 8, 190000000, 4, 7)
    add('connect-result', 9, 200000000, 4, 7)
    add('query-enter', 11, 1100000000, 4, 7, 10, 1)
    add('query-result', 12, 1200000000, 4, 7, 10, 1)
    add('query-enter', 14, 1300000000, 4, 7, 13, 2)
    add('query-result', 15, 1400000000, 4, 7, 13, 2)
    return [load('enter', 100000000, -1), *rows[:2],
            load('result', 150000000, 1), *rows[2:]]


def chain(graph=None, **caller_changes):
    caller = dict(pid=456, uid=20001001, token=777, start_ticks=1)
    caller.update(caller_changes)
    return core.chain(source_graph() if graph is None else graph,
        process=dict(pid=123, uid=20001009, start_ticks=1,
                     bundle='com.ohos.numberidentity'),
        samples=[clock(10000000), clock(1600000000)],
        window=(1000000000, 1500000000), caller=caller)


def caller_frame(c, start_ticks=10):
    role = 'system-granted';bundle = c.ROLES[role][0]
    fields = dict(bundle=['name'], uid=['applicationInfo', 'uid'],
                  token=['applicationInfo', 'accessTokenId'],
                  systemApp=['applicationInfo', 'isSystemApp'])
    document = dict(name=bundle, applicationInfo=dict(bundleName=bundle,
        uid=20001001, accessTokenId=777, isSystemApp=True),
        hapModuleInfos=[dict(bundleName=bundle, moduleName='entry', name='entry',
            mainElementName='EntryAbility', hapPath='/data/app/entry.hap')])
    raw = json.dumps(document).encode();bms = c.bms_fields(raw, bundle, fields)
    status = b'Uid:\t20001001\t20001001\t20001001\t20001001\n'
    cmdline = bundle.encode() + b'\0'
    proc = ('456 (model) S ' + '0 ' * 18 + str(start_ticks) + '\n').encode()
    identity = c.process_identity('456', status, cmdline, proc, bundle, bms['uid'])
    namespace = dict(path='/proc/456/ns/time', raw_hex=b'4 900\n'.hex(),
                     guest_exit_code=0, value=dict(dev=4, inode=900))
    commands = {'pidof ' + bundle: [(b'456\n', 0)],
        'bm dump -n ' + bundle: [(raw, 0), (raw, 0)],
        "stat -Lc '%d %i' /proc/456/ns/time": [(b'4 900\n', 0), (b'4 900\n', 0)]}
    for leaf, body in [('status', status), ('cmdline', cmdline), ('stat', proc)]:
        commands['cat /proc/456/' + leaf] = [(body, 0), (body, 0)]
    frame = dict(commands=commands, namespace=(4, 900),
        clocks=[clock(1000000000), clock(1100000000)],
        report={'caller496': dict(role=role, process_absent=False,
            process=identity, bms=bms, namespace_before=namespace,
            namespace_after=copy.deepcopy(namespace))})
    return frame, role, fields


class CallerBirthTests(unittest.TestCase):
    def test_source_state_can_reach_narrow_result_without_runtime_flags(self):
        result = chain()
        self.assertEqual(result['selected_requests']['1']['request'], 10)
        self.assertEqual(result['selected_requests']['2']['request'], 13)
        self.assertEqual(result['caller']['start_ticks'], 1)
        self.assertFalse(result['first_artifact_behavior_gate_passed'])
        self.assertFalse(result['aggregate_provider_passed'])
        self.assertNotIn('native_callback_chain_checked', result)

    def test_same_pid_uid_token_with_later_birth_cannot_explain_earlier_query(self):
        with self.assertRaisesRegex(core.Pending, 'caller PID birth'):
            chain(start_ticks=140)

    def test_query_birth_tick_upper_edge_uses_conservative_clock_offset(self):
        graph = source_graph()
        graph[-4].value['mono_ns'] = 1100000005
        self.assertEqual(chain(graph, start_ticks=109)['caller']['start_ticks'], 109)
        graph[-4].value['mono_ns'] -= 1
        with self.assertRaisesRegex(core.Pending, 'caller PID birth'):
            chain(graph, start_ticks=109)

    def test_caller_birth_is_required_positive_exact_integer(self):
        for value in (None, True, 0, -1, 1 << 64):
            with self.subTest(value=value), self.assertRaises(ValueError):
                chain(start_ticks=value)

    def test_before_caller_absence_requires_exact_original_raw(self):
        c, _, _, _ = join.original_modules()
        role = 'system-readonly'
        command = 'pidof ' + c.ROLES[role][0]
        frame = dict(commands={command: [(b'', 1)]},
                     report={'caller496': dict(role=role, process_absent=True)})
        self.assertIsNone(join.replay_caller(frame, role, {}, c, allow_absent=True))
        for raw in ((b'', 0), (b'456\n', 1), (b'', 2)):
            bad = copy.deepcopy(frame);bad['commands'][command] = [raw]
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                join.replay_caller(bad, role, {}, c, allow_absent=True)
        with self.assertRaises(core.Pending):
            join.replay_caller(frame, role, {}, c)

    def test_before_and_after_kernel_birth_must_agree_when_caller_exists(self):
        c, _, _, _ = join.original_modules()
        before, role, fields = caller_frame(c, 10)
        after, _, _ = caller_frame(c, 10)
        self.assertEqual(join.replay_caller_generation(before, after, role, fields, c)
                         ['process']['start_ticks'], 10)
        after, _, _ = caller_frame(c, 11)
        with self.assertRaisesRegex(ValueError, 'across the public request'):
            join.replay_caller_generation(before, after, role, fields, c)

    def test_provider_absence_uses_actual_helper_namespace_for_existing_caller(self):
        c, _, _, _ = join.original_modules()
        frame, role, fields = caller_frame(c)
        del frame['namespace']
        self.assertEqual(join.replay_caller(frame, role, fields, c)['namespace'], (4, 900))
        frame['clocks'][1]['time_ns_inode'] = 901
        with self.assertRaisesRegex(ValueError, 'helper namespace'):
            join.replay_caller(frame, role, fields, c)


class ImageAliasTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='number-consumer-model-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.image = self.root / 'SYNTHETIC_NOT_IMAGE';self.image.write_bytes(b'not an image')
        self.elfs = {}
        for name in core.SONAMES:
            data = bytearray(64);data[:7] = b'\x7fELF\x02\x01\x01'
            struct.pack_into('<HH', data, 16, 3, 183)
            data += b'NUMBER_NATIVE495_LOAD v=1' if name == core.SONAMES[0] else b'NUMBER_NATIVE495 v=1'
            path = self.root / name;path.write_bytes(data)
            self.elfs[name] = join.descriptor496(path)
        self.image_record = join.descriptor496(self.image)
        loader = self.elfs[core.SONAMES[0]]
        number = self.elfs[core.SONAMES[1]]
        self.report = dict(status='pass', failures=[],
            system_image_sha256=self.image_record['sha256'],
            bundled_native_provider={'sha256': number['sha256']},
            native_libraries={core.SONAMES[1]: {'sha256': number['sha256']}},
            loader_library=dict(sha256=loader['sha256'], bytes=loader['bytes'],
                file=loader['path'], basename=core.SONAMES[0], image_inode=9,
                system_image_sha256=self.image_record['sha256'],
                scope='on-disk loader ELF only; loaded process and callback remain unverified',
                loaded_process_verified=False, native_callback_proven=False,
                elf_class=2, elf_machine=183, elf_type=3))

    def replay(self, aliases, primary=None):
        self.report['loader_library'].update(image_path_aliases=aliases,
            image_path=primary if primary is not None else aliases[0])
        path = self.root / 'SYNTHETIC_REPORT.json';path.write_text(json.dumps(self.report))
        record = join.descriptor496(path)
        bindings = dict(loader_image_report=record, number_image_report=record,
                        system_image=self.image_record, emitter_elfs=self.elfs)
        after = {'loaded': {name: {'file': row} for name, row in self.elfs.items()}}
        return join.image_bytes(bindings, after)

    def test_finite_same_inode_alias_contract_accepts_all_original_dump_shapes(self):
        first = '/lib64/' + core.SONAMES[0]
        second = '/system/lib64/' + core.SONAMES[0]
        for aliases in ([first], [second], [first, second]):
            with self.subTest(aliases=aliases):
                self.assertEqual(set(self.replay(aliases)), set(core.SONAMES))

    def test_alias_order_duplicates_foreign_path_or_wrong_primary_refused(self):
        first = '/lib64/' + core.SONAMES[0]
        second = '/system/lib64/' + core.SONAMES[0]
        for aliases in ([first, first], [second, first], [first, '/foreign/loader.so']):
            with self.subTest(aliases=aliases), self.assertRaises(ValueError):
                self.replay(aliases)
        with self.assertRaises(ValueError):self.replay([first, second], primary=second)


if __name__ == '__main__':
    unittest.main()
