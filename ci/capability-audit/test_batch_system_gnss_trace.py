"""Diagnostic parser/CFI contract negatives; synthetic inputs are never runtime proof."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import batch_system_gnss_trace_helper as helper
import batch_system_gnss_trace_window as window


def snapshot(last, pid=123, epoch=10):
    first = max(1, last - 127)
    header = dict(schema=window.SCHEMA, kind='snapshot', capacity=128, count=min(last, 128),
                  firstRetainedOrdinal=first if last else 0, lastCapturedOrdinal=last,
                  overwrittenTotal=max(0, last - 128), droppedBeforeStore=0, ordinalOverflow=False,
                  clockErrorsTotal=0, traceEpochBootNs=epoch, snapshotBootNs=10000 + last,
                  processPid=pid, cachedCaptured=False)
    rows = [dict(kind='hdi_report_location', localOrdinal=n, fieldValidity=1539,
                 horizontalAccuracyBits='0x7fa00042', latitudeBits='0x403e000000000000',
                 longitudeBits='0x405e000000000000', sourceUtcMs=1800000000000 + n,
                 sourceBootNs=n + 100, receiptBootNs=n + 100,
                 callbackCallerUid=1000, callbackCallerPid=321) for n in range(first, last + 1)]
    return '\n'.join(json.dumps(x) for x in [header, *rows]) + '\n'


class GnssTraceTests(unittest.TestCase):
    def test_fixed_client_only_checks_existing_SA_and_requires_actual_root(self):
        source = helper.product.HERE / 'fixtures/batch_system/gnss_trace/gnss_existing_sa_dump.cpp'
        self.assertEqual(helper.CLIENT_SHA256, helper.product.sha(source))
        text = source.read_text()
        self.assertIn('uid != 0 || euid != 0', text)
        self.assertIn('CheckSystemAbility(OHOS::LOCATION_GNSS_SA_ID)', text)
        self.assertNotRegex(text, r'->(?:LoadSystemAbility|GetSystemAbility|EnableGnss|StartGnss|RegisterCallBack)\(')

    def test_actual_selected_macro_and_HDI_feature_are_mandatory(self):
        builder = object.__new__(helper.GnssDumpBuilder)
        good = ['-DFEATURE_GNSS_SUPPORT', '-DQEMU_GNSS_HDI_RAW_TRACE=1']
        with patch.object(helper.product.Builder, 'anchor', return_value={'flags': good}):
            self.assertEqual(good, builder.anchor({}, 'test')['flags'])
        for flags in ([], good[:1], good[1:], good + [good[1]], [good[0], '-DQEMU_GNSS_HDI_RAW_TRACE=0']):
            with self.subTest(flags=flags), patch.object(helper.product.Builder, 'anchor', return_value={'flags': flags}):
                with self.assertRaises(ValueError): builder.anchor({}, 'test')

    def elf(self):
        return ('  1: 0000000000003000 240 FUNC GLOBAL DEFAULT 15 __cfi_check\n'
                '  2: 0000000000000000 0 FUNC GLOBAL DEFAULT UND __cfi_slowpath\n' +
                ''.join('  0x0000000000000001 (NEEDED) Shared library: [' + name + ']\n'
                        for name in sorted(helper.NEEDED)))

    def test_inlined_client_ABI_does_not_require_exported_string_symbol(self):
        text = self.elf()
        self.assertNotIn('std::__h::', text)
        self.assertEqual(helper.NEEDED, helper.validate_symbols(text))
        for wrong in (text.replace('DEFAULT 15 __cfi_check', 'DEFAULT UND __cfi_check'),
                      text.replace('__cfi_slowpath', 'unrelated'), text + 'std::__n1::string\n',
                      text.replace('[libsamgr_proxy.z.so]', '[unrelated.so]')):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError): helper.validate_symbols(wrong)

    def test_empty_capacity_and_overwritten_interval_boundaries(self):
        for before, after, complete in ((0, 0, True), (0, 128, True), (0, 129, False),
                                        (150, 160, True), (150, 300, False)):
            value = window.capture_window(window.read_snapshot(snapshot(before)), window.read_snapshot(snapshot(after)))
            self.assertEqual(complete, value['captureWindowComplete'])
            self.assertFalse(value['rawHdiRuntimeProven'])
            self.assertEqual(0, value['capabilityIdsClosed'])

    def test_truncation_duplicates_raw_words_and_unbounded_input_are_rejected(self):
        text = snapshot(1)
        header, row = [json.loads(line) for line in text.splitlines()]
        bad = copy.deepcopy(row); bad['horizontalAccuracyBits'] = 'NaN'
        for value in (json.dumps(header) + '\n', text.replace('"count": 1', '"count": 1, "count": 1'),
                      json.dumps(header) + '\n' + json.dumps(bad), text * 129,
                      ' ' * (window.MAX_SNAPSHOT_BYTES + 1)):
            with self.subTest(value=value[:100]), self.assertRaises(ValueError): window.read_snapshot(value)

    def test_process_restart_clock_failure_and_duplicate_source_do_not_prove_match(self):
        before, after = window.read_snapshot(snapshot(0)), window.read_snapshot(snapshot(2))
        changed = (dict(after[0], processPid=999), after[1])
        self.assertFalse(window.capture_window(before, changed)['captureWindowComplete'])
        changed = (dict(after[0], clockErrorsTotal=1), after[1])
        self.assertFalse(window.capture_window(before, changed)['captureWindowComplete'])
        value = window.capture_window(before, after)
        expected = [dict(row) for row in value['records']]
        self.assertEqual(2, window.match_expected(value, expected)['matched'])
        value['records'][1]['sourceUtcMs'] = value['records'][0]['sourceUtcMs']
        with self.assertRaises(ValueError): window.match_expected(value, expected)


if __name__ == '__main__':
    unittest.main()
