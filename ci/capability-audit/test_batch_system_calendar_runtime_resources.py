"""Host-only V2 resource counterexamples; no guest/SDK/signature acceptance."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

import batch_system_calendar_runtime_resources as r
from batch_system_calendar_runtime_project import record


class CalendarResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.resource_id = 0x05000000

    def index(self):
        def u(*values): return struct.pack('<' + 'I' * len(values), *values)
        keys = b''
        for key, language, region in [(0, '', ''), (1, 'en', 'US'), (2, 'zh', 'CN')]:
            keys += b'KEYS' + u(key, 2 if language else 0)
            if language:
                keys += u(0, int.from_bytes(language.encode(), 'big'), 1, int.from_bytes(region.encode(), 'big'))
        name = b'app_name'; type_length = 12 + 12 + len(name); ids_length = 16 + type_length
        data_offset = 140 + len(keys) + ids_length; record_offset = data_offset + 12
        pool_offset = record_offset + 36; strings = b''; pairs = b''
        for config_id, text in enumerate(('HOST base', 'HOST English', '主机中文')):
            value = text.encode(); pairs += u(config_id, pool_offset + len(strings))
            strings += struct.pack('<H', len(value)) + value
        ids = b'IDSS' + u(ids_length, 1, 1) + u(9, type_length, 1) + u(self.resource_id, record_offset, len(name)) + name
        values = b'DATA' + u(48, 1) + u(self.resource_id, 36, 3) + pairs + strings
        version = b'RestoolV2 6.1.0.003'
        header = version + b'\0' * (128 - len(version)) + u(140 + len(keys) + len(ids) + len(values), 3, data_offset)
        return header + keys + ids + values

    def materials(self):
        label = {'label': '$string:app_name', 'labelId': self.resource_id}
        ability = dict(label, name='MainAbility')
        remote = '/system/app/com.ohos.calendardata/CalendarData.hap'
        app = dict(label, name=r.PROVIDER, bundleName=r.PROVIDER, uid=20010024, accessTokenId=123,
                   isSystemApp=True, appPrivilegeLevel='system_core')
        bms = {'applicationInfo': app, 'hapModuleInfos': [dict(label, name='entry', hapPath=remote, abilityInfos=[ability])]}
        module = {'app': dict(label, bundleName=r.PROVIDER, debug=False), 'module': {'abilities': [ability]}}
        hap = self.root / 'host-only.hap'
        with zipfile.ZipFile(hap, 'w') as z:
            z.writestr('module.json', json.dumps(module)); z.writestr('resources.index', self.index())
            z.writestr('ets/modules.abc', b'HOST ONLY; not compiled ABC')
        path = self.root / 'bms.json'; path.write_text(json.dumps(bms))
        locale = self.root / 'locale.txt'; locale.write_text('zh-Hans-CN\n')
        return {'installed_hap': record(hap), 'bms': record(path), 'locale': record(locale), 'archive_sha256': 'a' * 64,
                'boot_id': '12345678-1234-1234-1234-123456789abc', 'run_id': 'd' * 32}

    def test_exact_id_type_name_and_supported_locale(self):
        context = self.materials()
        for locale, expected in [('en-US', 'HOST English'), ('en-Latn-US', 'HOST English'),
                                 ('zh-CN', '主机中文'), ('zh-Hans-CN', '主机中文')]:
            result = r.resolve_provider_label(context['installed_hap']['path'], Path(context['bms']['path']).read_text(), locale + '\n')
            self.assertEqual(result['selected']['value'], expected)
        for locale in ('', 'en', 'fr-FR', 'zh-Hant-TW', 'en_US', 'en-US\nzh-CN', 'zh-Hans-CN '):
            with self.subTest(locale=locale), self.assertRaises(ValueError):
                r.resolve_provider_label(context['installed_hap']['path'], Path(context['bms']['path']).read_text(), locale)

    def test_truncation_unknown_qualifier_duplicates_and_wrong_id_rejected(self):
        data = self.index()
        for end in (0, 128, 139, len(data) - 1):
            with self.subTest(end=end), self.assertRaises(ValueError): r.parse_label_index(data[:end], self.resource_id)
        for offset, value in [(128, len(data) + 1), (132, 0), (136, len(data) + 1),
                              (160, 5), (164, 5), (156, 0)]:
            changed = bytearray(data); struct.pack_into('<I', changed, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError): r.parse_label_index(bytes(changed), self.resource_id)
        with self.assertRaises(ValueError): r.parse_label_index(data, self.resource_id + 1)
        with self.assertRaises(ValueError): r.parse_label_index(data, self.resource_id, 'foreign_name')

    def test_retained_F09_index_uses_the_same_structural_parser(self):
        import hashlib
        path = Path('/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r56-Calendar-resource-tool-feasibility-01/CalendarData.hap')
        if not path.is_file(): self.skipTest('retained F09 file unavailable; host format check only')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), '5e82563e81ea5b8d145ef7150e2a6426842ffe08f41d2122c963deddd6fa2bc5')
        with zipfile.ZipFile(path) as z: index = z.read('resources.index')
        self.assertEqual(hashlib.sha256(index).hexdigest(), 'eb0b3a7c049ca380690410f2b1a743e430e677ada79bec7eee6d4fbc25ad8a58')
        values = r.parse_label_index(index, self.resource_id)['configurations']
        self.assertEqual([(v['qualifiers'], v['value']) for v in values], [({}, 'CalendarData'),
            ({'language': 'en', 'region': 'US'}, 'CalendarData'), ({'language': 'zh', 'region': 'CN'}, '日历存储')])

    def test_symbolic_bms_label_requires_proof_and_same_requester(self):
        import batch_system_calendar_runtime_binding as binding
        context = self.materials(); proof = r.make_provider_label_proof(**context)
        app = json.loads(Path(context['bms']['path']).read_text())['applicationInfo']
        with self.assertRaises(ValueError): binding.permission_label(r.PROVIDER, {r.PROVIDER: app}, context['run_id'])
        self.assertEqual(binding.permission_label(r.PROVIDER, {r.PROVIDER: app}, context['run_id'],
            provider_label_proof=proof, provider_label_context=context), '主机中文')
        with self.assertRaises(ValueError):
            binding.permission_label(r.PROVIDER, {r.PROVIDER: dict(app, uid=20010025)}, context['run_id'],
                provider_label_proof=proof, provider_label_context=context)

    def test_proof_requires_actual_bytes_and_exact_archive_boot_run_context(self):
        context = self.materials(); proof = r.make_provider_label_proof(**context)
        self.assertEqual(r.verify_provider_label_proof(proof, **context), '主机中文')
        for key, value in [('archive_sha256', 'b' * 64), ('run_id', 'e' * 32),
                           ('boot_id', '22345678-1234-1234-1234-123456789abc')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                r.verify_provider_label_proof(proof, **dict(context, **{key: value}))
        boolean = copy.deepcopy(proof); boolean['schema_version'] = True
        with self.assertRaises(ValueError): r.verify_provider_label_proof(boolean, **context)
        for key in ('selected', 'resource_index', 'identity'):
            changed = copy.deepcopy(proof); changed['resolved'][key] = {}
            with self.subTest(key=key), self.assertRaises(ValueError): r.verify_provider_label_proof(changed, **context)
        Path(context['locale']['path']).write_text('en-US\n')
        with self.assertRaises(ValueError): r.verify_provider_label_proof(proof, **context)


if __name__ == '__main__':
    unittest.main()
