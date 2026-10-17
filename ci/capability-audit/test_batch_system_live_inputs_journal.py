"""Host parser/control counterexamples only; not SDK, API, guest or switch evidence."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import batch_system_live_inputs as journal
import batch_system_run_live_inputs as runner

RUN = '1e5db8dfe36a82a80a70fe406af6f15f'


def row(seq, kind, values=None, *, schema=2, generation=0, text='', **extra):
    return dict(schema=schema, run_id=RUN, seq=seq, kind=kind, generation=generation,
                boot_ns=str(90000000000 + seq), values=[] if values is None else values, text=text, **extra)


def encoded(rows):
    return ''.join(json.dumps(value, allow_nan=False) + '\n' for value in rows)


def typed_error(seq, code='3301100', operation='location.on', values=None):
    kind = 'string' if type(code) is str else 'number'
    return row(seq, 'error', values, generation=1, text=operation,
               error=dict(code_type=kind, operation=operation, **{'raw_code_' + kind: code},
                          name='BusinessError', message='actual API error fixture'))


def switch_pair(query_seq=2, request_id=1, enabled=False, generation=0):
    return [row(query_seq, 'location_switch_query', [request_id], generation=generation, text=journal.LOCATION_SWITCH_API),
            row(query_seq + 1, 'location_switch_state', [request_id, query_seq], generation=generation,
                text=journal.LOCATION_SWITCH_API, location_enabled=enabled)]


class JournalTests(unittest.TestCase):
    def parsed(self, rows):
        return journal.parse_rows(encoded(rows), RUN)

    def capture(self, rows):
        capture = runner.Capture.__new__(runner.Capture)
        capture.rows = Mock(return_value=rows)
        capture.click = Mock()
        capture.report = {}
        return capture

    def test_c1_string_error_preserved_and_later_marker_remains_visible(self):
        # Same C1 shape: permission success, string switch-off code, real marker.
        rows = [row(1, 'ready', schema=1), row(2, 'permissions', [0, 0], schema=1),
                row(3, 'start', schema=1, generation=1),
                row(4, 'error', ['3301100'], schema=1, generation=1, text='location.on'),
                row(5, 'start_complete', schema=1, generation=1)]
        parsed = self.parsed(rows)
        self.assertEqual(parsed, rows)
        self.assertIs(type(parsed[3]['values'][0]), str)
        self.assertEqual(parsed[-1]['kind'], 'start_complete')
        with self.assertRaises(journal.OrdinaryApiError) as error:
            journal.require_no_api_errors(parsed)
        self.assertIn('"3301100"', str(error.exception))
        self.assertEqual(error.exception.rows, (rows[3],))

    def test_legacy_integer_error_does_not_turn_into_string(self):
        values = self.parsed([row(1, 'error', [3301100], schema=1, text='location.on')])
        self.assertIs(type(values[0]['values'][0]), int)
        with self.assertRaises(journal.OrdinaryApiError): journal.require_no_api_errors(values)

    def test_unknown_string_code_remains_fatal_and_exact(self):
        values = self.parsed([row(1, 'error', ['future-code:001'], schema=1, text='future.on')])
        with self.assertRaises(journal.OrdinaryApiError) as error: journal.require_no_api_errors(values)
        self.assertIn('future-code:001', str(error.exception))

    def test_legacy_error_rejects_bool_null_object_and_float_code(self):
        for code in (True, None, {}, [], 3301100.5):
            with self.subTest(code=code), self.assertRaises(journal.JournalSchemaError):
                self.parsed([row(1, 'error', [code], schema=1, text='location.on')])

    def test_nonerror_values_stay_numeric_for_both_versions(self):
        for version in (1, 2):
            for value in ('3301100', True, None, {}, []):
                with self.subTest(schema=version, value=value), self.assertRaises(journal.JournalSchemaError):
                    self.parsed([row(1, 'sensor', [value], schema=version)])
        with self.assertRaises(journal.JournalSchemaError):
            journal.parse_rows(encoded([row(1, 'sensor', [1])]).replace('[1]', '[NaN]'), RUN)

    def test_v2_string_integer_and_absent_code_keep_discriminators(self):
        for code in ('03301100', 3301100):
            value = typed_error(1, code)
            parsed = self.parsed([value])
            self.assertEqual(parsed[0]['error'], value['error'])
            with self.assertRaises(journal.OrdinaryApiError): journal.require_no_api_errors(parsed)
        value = row(1, 'error', text='duplicate start', error=dict(code_type='undefined', operation='duplicate start', message='duplicate start'))
        with self.assertRaises(journal.OrdinaryApiError): journal.require_no_api_errors(self.parsed([value]))

    def test_v2_unsupported_code_is_explicit_fatal_diagnostic(self):
        value = row(1, 'error', text='future.on', error=dict(code_type='unsupported', operation='future.on',
                    raw_code_type='boolean', raw_code_text='true', raw_error_json='{"code":true}'))
        parsed = self.parsed([value])
        self.assertEqual(parsed[0]['error']['raw_code_type'], 'boolean')
        with self.assertRaises(journal.OrdinaryApiError): journal.require_no_api_errors(parsed)

    def test_v2_error_cannot_mix_or_forge_code_types(self):
        for mutate in ('wrong_raw_type', 'other_raw_field', 'wrong_operation', 'extra', 'string_context'):
            value = typed_error(1)
            if mutate == 'wrong_raw_type': value['error']['raw_code_string'] = 3301100
            elif mutate == 'other_raw_field': value['error']['raw_code_number'] = 3301100
            elif mutate == 'wrong_operation': value['error']['operation'] = 'other.on'
            elif mutate == 'extra': value['error']['pretend_success'] = True
            else: value['values'] = ['3301100']
            with self.subTest(mutation=mutate), self.assertRaises(journal.JournalSchemaError): self.parsed([value])

    def test_schema_versions_cannot_be_mixed_or_future_version_guessed(self):
        for rows in ([row(1, 'ready', schema=1), row(2, 'finished')], [row(1, 'ready', schema=3)]):
            with self.assertRaises(journal.JournalSchemaError): self.parsed(rows)

    def test_extra_error_payload_on_normal_row_is_rejected(self):
        with self.assertRaises(journal.JournalSchemaError): self.parsed([row(1, 'sensor', [1], error={})])

    def test_wait_reports_actual_api_error_even_if_requested_marker_exists(self):
        rows = self.parsed([typed_error(1), row(2, 'start_complete', generation=1)])
        capture = self.capture(rows)
        with patch.object(runner.time, 'sleep', side_effect=AssertionError('must not poll API error')):
            with self.assertRaises(journal.OrdinaryApiError): capture.wait('start_complete', 1)
        self.assertEqual(capture.rows.call_count, 1)

    def test_wait_reports_schema_error_immediately(self):
        capture = self.capture([]); capture.rows.side_effect = journal.JournalSchemaError('bad actual row')
        with patch.object(runner.time, 'sleep', side_effect=AssertionError('must not poll schema error')):
            with self.assertRaisesRegex(journal.JournalSchemaError, 'bad actual row'): capture.wait('start_complete', 1)

    def test_wait_reports_transport_failure_immediately(self):
        capture = self.capture([]); capture.rows.side_effect = ValueError('actual HDC failure')
        with patch.object(runner.time, 'sleep', side_effect=AssertionError('must not poll transport error')):
            with self.assertRaisesRegex(ValueError, 'actual HDC failure'): capture.wait('ready')

    def test_wait_only_retries_explicit_journal_not_ready(self):
        capture = self.capture([]); ready = row(1, 'ready')
        capture.rows.side_effect = [runner.JournalNotReady('not written yet'), [ready]]
        with patch.object(runner.time, 'sleep'):
            self.assertEqual(capture.wait('ready'), ready)
        self.assertEqual(capture.rows.call_count, 2)

    def test_missing_journal_after_observation_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            capture = runner.Capture.__new__(runner.Capture)
            capture.output = Path(directory); capture.remote = '/only-host-test/path'
            capture.a = SimpleNamespace(run_id=RUN)
            capture.shell = Mock(return_value='__LIVE_JOURNAL_NOT_CREATED__')
            with self.assertRaises(runner.JournalNotReady): capture.rows()
            capture._journal_seen = True
            with self.assertRaises(journal.JournalSchemaError): capture.rows()

    def test_switch_false_is_original_boolean_not_permission_or_enable_proof(self):
        rows = self.parsed([row(1, 'ready'), *switch_pair(enabled=False)])
        observations = journal.switch_observations(rows, require_complete=True)
        self.assertIs(observations[0]['location_enabled'], False)
        self.assertEqual((observations[0]['before_seq'], observations[0]['after_seq']), (2, 3))

    def test_switch_boolean_cannot_be_number_string_or_null(self):
        for value in (0, 1, 'false', 'true', None):
            with self.subTest(value=value), self.assertRaises(journal.JournalSchemaError):
                self.parsed([row(1, 'ready'), *switch_pair(enabled=value)])

    def test_switch_before_after_id_generation_and_duplicate_are_bound(self):
        for mutate in ('before_seq', 'query_id', 'generation', 'operation', 'duplicate'):
            rows = [row(1, 'ready'), *switch_pair()]
            if mutate == 'before_seq': rows[2]['values'][1] = 1
            elif mutate == 'query_id': rows[2]['values'][0] = 2
            elif mutate == 'generation': rows[2]['generation'] = 1
            elif mutate == 'operation': rows[2]['text'] = 'enableLocation'
            else: rows.append(dict(rows[2], seq=4, boot_ns='90000000004'))
            with self.subTest(mutation=mutate), self.assertRaises(journal.JournalSchemaError): self.parsed(rows)

    def test_repeated_public_queries_keep_before_after_sequence(self):
        rows = self.parsed([row(1, 'ready'), *switch_pair(), *switch_pair(4, 2, True)])
        values = journal.switch_observations(rows, require_complete=True)
        self.assertEqual([(r['request_id'], r['before_seq'], r['after_seq'], r['location_enabled']) for r in values],
                         [(1, 2, 3, False), (2, 4, 5, True)])

    def test_pending_query_is_readable_but_not_complete_evidence(self):
        rows = self.parsed([row(1, 'ready'), switch_pair()[0]])
        with self.assertRaises(journal.JournalSchemaError): journal.switch_observations(rows, require_complete=True)

    def test_state_query_error_never_becomes_false_or_true(self):
        query = switch_pair()[0]
        error = typed_error(3, '3301000', journal.LOCATION_SWITCH_API, [1, 2]); error['generation'] = 0
        rows = self.parsed([row(1, 'ready'), query, error])
        self.assertEqual(journal.switch_observations(rows, require_complete=True), [])
        with self.assertRaises(journal.OrdinaryApiError): journal.require_no_api_errors(rows)

    def test_read_control_uses_new_request_and_preserves_prior_api_failure(self):
        previous = [row(1, 'ready'), *switch_pair(), typed_error(4)]
        # Query generation must match its begin; diagnostic reads do not erase a
        # pre-existing subscription error or claim acceptance during restoration.
        following = [*previous, *switch_pair(5, 2, False, generation=1)]
        capture = self.capture([]); capture.rows.side_effect = [self.parsed(previous), self.parsed(following)]
        result = capture.read_location_switch_state('restore-readback')
        capture.click.assert_called_once_with(journal.LOCATION_SWITCH_CONTROL)
        self.assertIs(result['location_enabled'], False)
        self.assertEqual(result['prior_api_errors'], [previous[-1]])
        self.assertIn('NOT_acceptance', result['scope'])
        with self.assertRaises(journal.OrdinaryApiError): journal.require_no_api_errors(self.parsed(following))

    def test_read_control_rejects_new_api_error_without_polling(self):
        before = [row(1, 'ready')]
        error = typed_error(3, 'UNKNOWN', journal.LOCATION_SWITCH_API, [1, 2]); error['generation'] = 0
        capture = self.capture([]); capture.rows.side_effect = [self.parsed(before), self.parsed([*before, switch_pair()[0], error])]
        with patch.object(runner.time, 'sleep', side_effect=AssertionError('must not poll query error')):
            with self.assertRaises(journal.OrdinaryApiError): capture.read_location_switch_state('initial-read')

    def test_ui_fixture_only_reads_modern_public_switch_api(self):
        source = (journal.FIXTURES / 'Index.ets.in').read_text()
        self.assertEqual(source.count(".id('live-location-switch-state')"), 1)
        self.assertEqual(source.count('location.isLocationEnabled()'), 1)
        self.assertIn('schema: 2', source)
        self.assertIn("'location_switch_query', [requestId]", source)
        self.assertIn("'location_switch_state', [requestId, beforeSeq]", source)
        for forbidden in ('requestEnableLocation', 'location.enableLocation(', 'location.disableLocation(', 'MANAGE_SECURE_SETTINGS', 'CONTROL_LOCATION_SWITCH'):
            self.assertNotIn(forbidden, source)
        self.assertNotIn('BusinessError).code]', source)
        self.assertEqual(journal.PERMISSIONS, ['ohos.permission.ACCELEROMETER',
            'ohos.permission.APPROXIMATELY_LOCATION', 'ohos.permission.LOCATION'])


if __name__ == '__main__':
    unittest.main()
