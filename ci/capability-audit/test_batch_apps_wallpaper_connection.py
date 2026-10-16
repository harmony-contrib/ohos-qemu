#!/usr/bin/env python3
"""Synthetic source-grammar counterexamples, never evidence of an actual guest."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import batch_apps_wallpaper_connection as w


def ams():
    return '''  ExtensionRecords:
    uri [/com.ohos.wallpaper/phone_wallpaper/WallpaperExtAbility]
      AbilityRecord ID #0   state #INACTIVE   start time [1234]
      main name [WallpaperExtAbility]
      bundle name [com.ohos.wallpaper]
      ability type [SERVICE]
      app state #BACKGROUND
        isKeepAlive: false
      Connections: 1
       > com.ohos.wallpaper/WallpaperExtAbility   connectionState #CONNECTED
  AppRunningRecords:
    AppRunningRecord ID #0
      process name [com.ohos.wallpaper]
      pid #2345  uid #20010012
      state #BACKGROUND
'''


class WallpaperConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.target = '127.0.0.1:5555'
        self.bms = {'appInfo': {'bundleName': w.BUNDLE, 'uid': 20010012, 'isSystemApp': True}}

    def test_real_dump_grammar_keeps_explicit_observation_limits(self):
        result = w.parse_connection(ams(), self.bms, '2345')
        self.assertEqual(result['connection']['record_id'], 0)
        self.assertFalse(result['service_token_to_pid_directly_observed'])
        self.assertFalse(result['connection_caller_identity_observed'])
        self.assertFalse(result['theme_service_GN_selection_verified'])
        self.assertFalse(result['first_artifact_behavior_gate_passed'])

    def test_pid_only_and_self_reported_pass_are_not_connections(self):
        for text in ['{"status":"pass","pid":2345}', ams().split('  AppRunningRecords:')[1]]:
            with self.assertRaisesRegex(ValueError, 'complete actual AMS'): w.parse_connection(text, self.bms, '2345')

    def test_ordinary_same_named_ability_or_ui_extension_is_rejected(self):
        for kind in ('PAGE', 'UIEXTENSION', 'UI_SERVICE'):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'ordinary similarly named'):
                w.parse_connection(ams().replace('[SERVICE]', '[' + kind + ']'), self.bms, '2345')
        with self.assertRaisesRegex(ValueError, 'complete actual AMS'):
            w.parse_connection(ams().replace('  ExtensionRecords:', '  MissionRecords:'), self.bms, '2345')

    def test_wrong_bundle_module_and_ability_cannot_borrow_matching_pid(self):
        for old, new in [('/phone_wallpaper/', '/entry/'), ('main name [WallpaperExtAbility]', 'main name [MainAbility]'),
                         ('bundle name [com.ohos.wallpaper]', 'bundle name [com.ohos.launcher]')]:
            with self.subTest(new=new), self.assertRaises(ValueError): w.parse_connection(ams().replace(old, new), self.bms, '2345')

    def test_duplicate_service_record_rejected(self):
        service, process = ams().split('  AppRunningRecords:')
        with self.assertRaisesRegex(ValueError, 'one actual connected'):
            w.parse_connection(service + service.split('  ExtensionRecords:\n')[1] + '  AppRunningRecords:' + process, self.bms, '2345')

    def test_no_connection_disconnected_and_count_mismatch_rejected(self):
        for text in [ams().replace('Connections: 1', 'Connections: 0'),
                     ams().replace('#CONNECTED', '#DISCONNECTED'), ams().replace('Connections: 1', 'Connections: 2'),
                     ams().replace('> com.ohos.wallpaper/WallpaperExtAbility', '> com.ohos.wallpaper/MainAbility')]:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'connection missing or malformed'):
                w.parse_connection(text, self.bms, '2345')

    def test_bms_system_and_current_user_are_required(self):
        for mutation in [dict(isSystemApp=False), dict(uid=10012)]:
            value = copy.deepcopy(self.bms); value['appInfo'].update(mutation)
            with self.assertRaises(ValueError): w.parse_connection(ams(), value, '2345')

    def test_process_pid_uid_and_unique_bundle_process_required(self):
        for text, pids in [(ams(), '2346'), (ams(), '2345 2346'), (ams().replace('uid #20010012', 'uid #20010013'), '2345'),
                           (ams() + '    AppRunningRecord ID #1\n      process name [com.ohos.wallpaper:other]\n      pid #2346  uid #20010012\n', '2345')]:
            with self.subTest(text=text), self.assertRaises(ValueError): w.parse_connection(text, self.bms, pids)

    def runtime(self):
        value = {'commands': [], 'stages': []}
        def raw(label, script, text):
            path = self.root / (label + '.raw'); path.write_text(text)
            marker = '__UITEST_EXIT_' + 'a' * 32 + '__='
            log = self.root / (label + '.transport'); log.write_text(text + '\n' + marker + '0\n')
            value['commands'].append({'label': label, 'exit_code': 0, **w.descriptor(log),
                'argv': ['hdc', '-t', self.target, 'shell', script + '; task_ui_rc=$?; printf "\\n' + marker + '%s\\n" "$task_ui_rc"']})
            return w.descriptor(path)
        value['renderer_identity'] = raw('renderer-BMS', 'bm dump -n com.ohos.wallpaper', json.dumps(self.bms))
        for name in w.REQUIRED_STAGES:
            value['stages'].append({'name': name, 'started_ns': 10, 'finished_ns': 20,
                'ams': raw(name + '-AMS', 'aa dump -a -u 100', ams().rstrip('\n')),
                'renderer_pids': raw(name + '-renderer-pid', 'pidof com.ohos.wallpaper', '2345')})
        path = self.root / 'runtime.json'; path.write_text(json.dumps(value)); return value, path

    def test_both_challenges_bind_real_command_targets_scripts_exit_and_output(self):
        _, path = self.runtime()
        result = w.verify_runtime_connections(path, target=self.target)
        self.assertEqual([stage['stage'] for stage in result['stages']], ['desktop-1', 'desktop-2'])
        self.assertFalse(result['ledger_closed'])

    def test_other_user_dump_command_cannot_claim_user100_grammar(self):
        value, path = self.runtime(); value['commands'][1]['argv'][4] = value['commands'][1]['argv'][4].replace('-u 100', '-u 0')
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'exact actual requested'): w.verify_runtime_connections(path, target=self.target)

    def test_wrong_target_transport_cannot_borrow_raw_stage(self):
        _, path = self.runtime()
        with self.assertRaisesRegex(ValueError, 'another guest'): w.verify_runtime_connections(path, target='127.0.0.1:5556')

    def test_modified_derived_stage_cannot_borrow_unchanged_transport(self):
        value, path = self.runtime(); descriptor = value['stages'][0]['ams']
        p = Path(descriptor['path']); p.write_text(p.read_text().replace('start time [1234]', 'start time [1235]'))
        value['stages'][0]['ams'] = w.descriptor(p); path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'transport bytes'): w.verify_runtime_connections(path, target=self.target)

    def test_remote_failure_is_not_transport_success(self):
        value, path = self.runtime(); command = value['commands'][1]; p = Path(command['path'])
        p.write_text(p.read_text().replace('__=0\n', '__=1\n')); command.update(w.descriptor(p)); path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'actual guest exit'): w.verify_runtime_connections(path, target=self.target)

    def test_missing_second_challenge_cannot_be_complete(self):
        value, path = self.runtime(); value['stages'].pop(); path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'both real new desktop'): w.verify_runtime_connections(path, target=self.target)


if __name__ == '__main__': unittest.main()
