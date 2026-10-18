"""Public Calendar locale regressions; host fixtures do not prove guest success.

The retained four-row journal is historical input only. Synthetic capture tests
use a double solely at the independent capture-validation boundary, then run the
real public adapter, marked-command/journal parsing and locale comparison.
"""
import copy
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

import batch_system_calendar_runtime_resources as resources
from batch_system_calendar_runtime_resources import public_locales_equivalent
from batch_system_calendar_runtime_project import ROLES, challenge, record
import batch_system_calendar_runtime_verify as verifier


FIXTURE = Path(__file__).with_name("fixtures") / "batch_system/calendar_public_locale/retained_journal.jsonl"
SUPPORTED = ('en-US', 'en-Latn-US', 'zh-CN', 'zh-Hans-CN')
RESOURCE_PAIRS = (
    ('en-US', 'en-US'), ('en-US', 'en_US'),
    ('en-Latn-US', 'en-Latn-US'), ('en-Latn-US', 'en_Latn_US'),
    ('zh-CN', 'zh-CN'), ('zh-CN', 'zh_CN'),
    ('zh-Hans-CN', 'zh-Hans-CN'), ('zh-Hans-CN', 'zh_Hans_CN'),
)


class PublicLocales(unittest.TestCase):
    def test_unchanged_four_supported_equal_pairs(self):
        for locale in SUPPORTED:
            with self.subTest(locale=locale):
                self.assertIs(public_locales_equivalent(locale, locale), True)

    def test_exact_eight_resource_forms_select_only_existing_four_tokens(self):
        for system, resource in RESOURCE_PAIRS:
            with self.subTest(system=system, resource=resource):
                self.assertIs(public_locales_equivalent(system, resource), True)

    def test_all_other_supported_token_cross_pairs_are_conflicts(self):
        for expected, resource in RESOURCE_PAIRS:
            for system in SUPPORTED:
                with self.subTest(system=system, resource=resource):
                    self.assertIs(public_locales_equivalent(system, resource), system == expected)

    def test_never_infers_or_removes_default_scripts(self):
        for system, resource in [('en-US', 'en_Latn_US'), ('en-Latn-US', 'en_US'),
                                 ('zh-CN', 'zh_Hans_CN'), ('zh-Hans-CN', 'zh_CN')]:
            with self.subTest(system=system, resource=resource):
                self.assertIs(public_locales_equivalent(system, resource), False)

    def test_system_underscore_forms_remain_unsupported(self):
        for system in ('en_US', 'en_Latn_US', 'zh_CN', 'zh_Hans_CN'):
            for resource in (system, system.replace('_', '-')):
                with self.subTest(system=system, resource=resource):
                    self.assertIs(public_locales_equivalent(system, resource), False)

    def test_unknown_language_region_script_variants_and_parameters_fail(self):
        for unsupported in ('', 'en', 'zh', 'fr-FR', 'fr_FR', 'zh-Hant-TW', 'zh_Hant_TW',
                            'zh-Hans-SG', 'en-GB', 'en-Cyrl-US', 'zh-Hans-CN-u-ca-chinese',
                            'en-US-POSIX', 'Get parameter "persist.sys.locale" fail! errNum is:106!',
                            '$string:app_name', 'CalendarData', '日历存储'):
            for system, resource in ((unsupported, unsupported), ('zh-Hans-CN', unsupported),
                                     (unsupported, 'zh_Hans_CN')):
                with self.subTest(system=system, resource=resource):
                    self.assertIs(public_locales_equivalent(system, resource), False)

    def test_mixed_duplicate_separators_and_case_are_not_normalized(self):
        for malformed in ('zh-Hans_CN', 'zh_Hans-CN', 'zh__Hans_CN', 'zh-Hans--CN',
                          'zh/Hans/CN', 'zh.Hans.CN', 'zh–Hans–CN', 'ZH_Hans_CN',
                          'zh_hans_CN', 'zh_Hans_cn', 'ZH-HANS-CN'):
            with self.subTest(resource=malformed):
                self.assertIs(public_locales_equivalent('zh-Hans-CN', malformed), False)

    def test_whitespace_controls_and_multiple_lines_are_not_stripped(self):
        for resource in (' zh_Hans_CN', 'zh_Hans_CN ', 'zh_Hans_CN\n', 'zh_Hans_CN\r\n',
                         '\tzh_Hans_CN', 'zh_Hans_CN\0', 'zh_Hans_CN\nen_US'):
            with self.subTest(resource=resource):
                self.assertIs(public_locales_equivalent('zh-Hans-CN', resource), False)
        for system in (' zh-Hans-CN', 'zh-Hans-CN ', 'zh-Hans-CN\n', 'zh-Hans-CN\0'):
            with self.subTest(system=system):
                self.assertIs(public_locales_equivalent(system, 'zh_Hans_CN'), False)

    def test_only_literal_strings_are_accepted(self):
        class StringSubclass(str):
            pass
        for invalid in (None, True, False, 0, 1, b'zh_Hans_CN', [], {}, ['zh_Hans_CN'],
                        StringSubclass('zh_Hans_CN')):
            for system, resource in (('zh-Hans-CN', invalid), (invalid, 'zh_Hans_CN')):
                with self.subTest(system=system, resource=resource):
                    self.assertIs(public_locales_equivalent(system, resource), False)

    def test_retained_journal_preserves_both_original_locale_values(self):
        # Historical failed-attempt input only; no current capture/provenance PASS.
        path = FIXTURE
        before = path.read_bytes()
        rows = [json.loads(line) for line in before.splitlines() if line]
        self.assertEqual([(r['event'], r['api']) for r in rows], [
            ('begin', 'request'), ('system-locale', 'i18n.System.getSystemLocale'),
            ('resource-locale', 'ResourceManager.getConfiguration'), ('complete', 'request')])
        self.assertTrue(all(r['error_code'] == 0 and r['error_message'] == '' for r in rows))
        system = json.loads(rows[1]['value_json'])['locale']
        resource = json.loads(rows[2]['value_json'])['locale']
        self.assertEqual((system, resource), ('zh-Hans-CN', 'zh_Hans_CN'))
        self.assertIs(public_locales_equivalent(system, resource), True)
        self.assertEqual((system, resource), ('zh-Hans-CN', 'zh_Hans_CN'))
        self.assertEqual(path.read_bytes(), before)


class PublicLocaleCapture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.challenge = record(challenge(self.root / 'challenge'))
        run_id = json.loads(Path(self.challenge['path']).read_text())['run_id']
        self.request = dict(schema_version=1, run_id=run_id,
            boot_id='12345678-1234-1234-1234-123456789abc', archive_sha256='a' * 64,
            operation_id='b' * 32, role='observer', action='locale', case_id='provider-locale')
        self.context = {key: self.request[key] for key in ('archive_sha256', 'boot_id', 'run_id')}
        self.capture = dict(archive={'sha256': self.request['archive_sha256']},
            boot_id=self.request['boot_id'], run_id=run_id, stage='public-operation',
            request=copy.deepcopy(self.request), challenge=self.challenge,
            artifacts={'observer': {'uid': 20010042, 'token_id': 123}})
        self.rows = [dict(self.request, sequence=index, timestamp_ms=1800000000000,
            uid=20010042, token_id=123, event=event, api=api,
            value_json=json.dumps(value), error_code=0, error_message='')
            for index, (event, api, value) in enumerate([
                ('begin', 'request', self.request),
                ('system-locale', 'i18n.System.getSystemLocale', {'locale': 'zh-Hans-CN'}),
                ('resource-locale', 'ResourceManager.getConfiguration', {'locale': 'zh_Hans_CN'}),
                ('complete', 'request', {})], start=1)]
        self.raw_file = self.root / 'raw-0001-public-locale.txt'
        self.log_file = self.root / 'synthetic-command.log'
        self.capture_file = self.root / 'synthetic-public-capture.json'
        self.marker = '__QEMU_CHILD_EXIT_' + 'c' * 32 + '__='
        remote = ('/data/app/el2/100/base/' + ROLES['observer']['bundle'] +
                  '/files/calendar-' + run_id + '-' + self.request['boot_id'] + '.jsonl')
        quoted = shlex.quote(remote)
        script = 'if test -f ' + quoted + '; then cat ' + quoted + '; fi'
        self.shell = '(' + script + '); task_child_rc=$?; printf "\\n' + self.marker + '%s\\n" "$task_child_rc"'
        self.write_rows()

    def write_capture(self):
        self.capture_file.write_text(json.dumps(self.capture), encoding='utf-8')

    def write_rows(self):
        # All bytes here are synthetic and confined to this test's temporary dir.
        for sequence, row in enumerate(self.rows, start=1):
            row['sequence'] = sequence
        text = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in self.rows)
        self.raw_file.write_text(text, encoding='utf-8')
        self.log_file.write_text(text + '\n' + self.marker + '0\n', encoding='utf-8')
        self.capture['journal'] = record(self.raw_file)
        self.capture['guest_commands'] = [dict(
            argv=['controlled-hdc', '-t', 'controlled-target', 'shell', self.shell],
            log=str(self.log_file), sha256=record(self.log_file)['sha256'], exit_code=0)]
        self.write_capture()

    def parse(self):
        # Capture/signature acceptance is intentionally doubled. operation(),
        # raw_bound(), protocol.parse(), challenge loading and locale parsing run.
        with patch.object(verifier, 'validate_capture', return_value=self.capture) as replay:
            result = resources.public_locale_from_capture(record(self.capture_file), **self.context)
            replay.assert_called_once()
            self.assertEqual(replay.call_args.args[0], self.capture_file)
            return result

    def test_public_capture_parses_both_raw_locale_forms_and_preserves_context(self):
        for system, resource in RESOURCE_PAIRS:
            self.rows[1]['value_json'] = json.dumps({'locale': system})
            self.rows[2]['value_json'] = json.dumps({'locale': resource})
            self.write_rows()
            before = self.raw_file.read_bytes()
            with self.subTest(system=system, resource=resource):
                result = self.parse()
                self.assertEqual((result['system_locale'], result['resource_locale']), (system, resource))
                self.assertEqual(result['source'], resources.PUBLIC_LOCALE_SOURCE)
                self.assertEqual(result['observer_bundle'], ROLES['observer']['bundle'])
                self.assertEqual((result['uid'], result['token_id']), (20010042, 123))
                self.assertEqual(result['operation_id'], self.request['operation_id'])
                self.assertEqual(result['timestamp_ms'], self.rows[-1]['timestamp_ms'])
                self.assertEqual(result['challenge'], self.challenge)
                self.assertEqual((result['system_api'], result['resource_api']),
                                 ('i18n.System.getSystemLocale', 'ResourceManager.getConfiguration'))
                self.assertEqual(self.raw_file.read_bytes(), before)

    def test_public_capture_rejects_foreign_context_role_action_or_stage_before_replay(self):
        baseline = copy.deepcopy(self.capture)
        for changed in (
            {'archive': {'sha256': 'd' * 64}}, {'boot_id': 'foreign-boot'}, {'run_id': 'd' * 32},
            {'stage': 'post-operation'}, {'request': dict(self.request, role='producer')},
            {'request': dict(self.request, action='calendar-read')},
        ):
            self.capture = copy.deepcopy(baseline)
            self.capture.update(changed)
            self.write_capture()
            with self.subTest(changed=changed), patch.object(verifier, 'validate_capture') as replay:
                with self.assertRaises(ValueError):
                    resources.public_locale_from_capture(record(self.capture_file), **self.context)
                replay.assert_not_called()

    def test_public_capture_rejects_conflicting_malformed_or_untyped_locale_values(self):
        baseline = copy.deepcopy(self.rows)
        changes = [(2, json.dumps({'locale': value})) for value in (
            'en_US', 'zh_CN', 'zh_Hant_TW', 'zh-Hans-CN\n', 'zh__Hans_CN',
            'Get parameter "persist.sys.locale" fail! errNum is:106!', None, 1, True)]
        changes += [(1, json.dumps({'locale': 'zh_Hans_CN'})),
                    (2, '{"locale":"zh_Hans_CN","extra":0}'),
                    (2, '{"locale":"zh_Hans_CN","locale":"en_US"}'),
                    (2, '["zh_Hans_CN"]')]
        for index, value in changes:
            self.rows = copy.deepcopy(baseline)
            self.rows[index]['value_json'] = value
            self.write_rows()
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                self.parse()

    def test_public_capture_rejects_extra_reordered_failed_or_nonpublic_reads(self):
        baseline = copy.deepcopy(self.rows)
        for mutation in ('extra', 'reordered', 'missing-complete', 'permission', 'error-code',
                         'error-message', 'calendar-api', 'foreign-uid'):
            self.rows = copy.deepcopy(baseline)
            if mutation == 'extra':
                extra = dict(self.rows[2], event='calendar-read', api='Calendar.getEvents')
                self.rows.insert(3, extra)
            elif mutation == 'reordered':
                self.rows[1], self.rows[2] = self.rows[2], self.rows[1]
            elif mutation == 'missing-complete':
                self.rows.pop()
            elif mutation == 'permission':
                self.rows[2]['event'] = 'permission'
            elif mutation == 'error-code':
                self.rows[2]['error_code'] = 201
            elif mutation == 'error-message':
                self.rows[2]['error_message'] = 'permission denied'
            elif mutation == 'calendar-api':
                self.rows[2]['api'] = 'Calendar.getEvents'
            else:
                self.rows[2]['uid'] += 1
            self.write_rows()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.parse()

    def test_public_capture_keeps_strict_marked_transport_hash_and_utf8_checks(self):
        for mutation in ('nonzero-footer', 'incomplete-footer', 'different-script',
                         'journal-hash', 'journal-log-mismatch', 'invalid-utf8'):
            self.write_rows()
            if mutation == 'nonzero-footer':
                self.log_file.write_text(self.raw_file.read_text() + '\n' + self.marker + '1\n', encoding='utf-8')
            elif mutation == 'incomplete-footer':
                self.log_file.write_text(self.raw_file.read_text() + '\n' + self.marker + '0', encoding='utf-8')
            elif mutation == 'different-script':
                self.capture['guest_commands'][0]['argv'][-1] += '; unrelated-command'
            elif mutation == 'journal-hash':
                self.raw_file.write_bytes(self.raw_file.read_bytes() + b'changed')
            elif mutation == 'journal-log-mismatch':
                self.raw_file.write_bytes(self.raw_file.read_bytes() + b'\n')
                self.capture['journal'] = record(self.raw_file)
            else:
                self.raw_file.write_bytes(b'non-text \xd2\n')
                self.capture['journal'] = record(self.raw_file)
                self.log_file.write_bytes(self.raw_file.read_bytes() + ('\n' + self.marker + '0\n').encode())
            self.capture['guest_commands'][0]['sha256'] = record(self.log_file)['sha256']
            self.write_capture()
            exception = UnicodeDecodeError if mutation == 'invalid-utf8' else ValueError
            with self.subTest(mutation=mutation), self.assertRaises(exception):
                self.parse()


if __name__ == '__main__':
    unittest.main()
