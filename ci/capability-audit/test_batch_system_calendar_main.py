"""Execute actual CalendarData viewer/consumer bodies; host doubles, no guest proof."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'ci/capability-audit/fixtures/batch_system/calendar_main'
COMPONENTS = ROOT / 'patches/common/applications/standard/calendardata'
OWNER = ROOT / 'patches/common/base/notification/distributed_notification_service/calendar_owner'
PROJECT = 'applications/standard/calendardata'
NOTIFICATION = 'base/notification/distributed_notification_service'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def function(source, signature):
    start = source.index(signature)
    opened = source.index('{', start)
    depth = 1
    end = opened + 1
    while depth:
        if source[end] == '{':
            depth += 1
        elif source[end] == '}':
            depth -= 1
        end += 1
    return source[start:end]


class CalendarMainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='calendar-main-host-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / PROJECT
        editor = ROOT / 'ci/capability-audit/fixtures/batch_apps/calendar_editor'
        for relative, row in json.loads((editor / 'provenance.json').read_text())['files'].items():
            self.write(relative, gzip.decompress(base64.b64decode((editor / row['fixture']).read_bytes())), row['sha256'])
        for row in json.loads((FIXTURE / 'provenance.json').read_text())['files']:
            self.write(row['path'], gzip.decompress(base64.b64decode((FIXTURE / row['fixture']).read_bytes())), row['sha256'])
        for name in ('event_editor', 'editor_callback_dispatch'):
            result = self.run_component(name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        meta = json.loads((FIXTURE / 'notification-provenance.json').read_text())
        for row in meta['files']:
            data = gzip.decompress(base64.b64decode((FIXTURE / row['fixture']).read_bytes()))
            self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
            path = self.root / NOTIFICATION / row['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def write(self, relative, data, sha):
        self.assertEqual(hashlib.sha256(data).hexdigest(), sha)
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run_component(self, name):
        component = OWNER if name == 'calendar_owner' else COMPONENTS / name
        return subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def prepare(self):
        for name in ('main_ui', 'calendar_owner'):
            result = self.run_component(name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def snapshot(self):
        return {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob('*') if p.is_file()}

    def test_exact_predecessor_complete_replay_and_unchanged_permissions(self):
        before = json.loads((self.project / 'entry/src/main/module.json5').read_text())['module']
        self.prepare()
        snapshot = self.snapshot()
        for name in ('event_editor', 'editor_callback_dispatch', 'main_ui', 'calendar_owner'):
            result = self.run_component(name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(snapshot, self.snapshot())
        after = json.loads((self.project / 'entry/src/main/module.json5').read_text())['module']
        expected = json.loads(json.dumps(before))
        read = next(x for x in expected['requestPermissions'] if x['name'] == 'ohos.permission.READ_WHOLE_CALENDAR')
        read['usedScene']['abilities'].append('MainAbility')
        self.assertEqual(after, expected)
        self.assertEqual(json.loads((self.project / 'AppScope/app.json5').read_text())['app']['bundleName'],
                         'com.ohos.calendardata')

    def test_full_source_provider_stack_replay(self):
        fixture = ROOT / 'ci/capability-audit/fixtures/batch_apps/calendar_dispatch/source-provider-pristine.json'
        for relative, row in json.loads(fixture.read_text())['files'].items():
            self.write(relative, gzip.decompress(base64.b64decode(row['gzip_base64'])), row['sha256'])
        result = self.run_component('source_provider')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.prepare()
        before = self.snapshot()
        for name in ('source_provider', 'event_editor', 'editor_callback_dispatch', 'main_ui', 'calendar_owner'):
            result = self.run_component(name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_unknown_partial_predecessor_and_symlink_reject_before_writes(self):
        main = self.project / 'entry/src/main/ets/MainAbility/MainAbility.ets'
        original = main.read_bytes()
        main.write_bytes(original + b'// unknown drift\n')
        before = self.snapshot()
        self.assertNotEqual(self.run_component('main_ui').returncode, 0)
        self.assertEqual(before, self.snapshot())
        main.write_bytes(original)
        self.prepare()
        reader = self.project / 'entry/src/main/ets/reminder/CalendarReminderReader.ets'
        reader.unlink()
        before = self.snapshot()
        self.assertNotEqual(self.run_component('main_ui').returncode, 0)
        self.assertEqual(before, self.snapshot())
        outside = self.root / 'outside.ets'
        outside.write_text('preserve outside')
        reader.symlink_to(outside)
        self.assertNotEqual(self.run_component('main_ui').returncode, 0)
        self.assertEqual(outside.read_text(), 'preserve outside')

    def test_unknown_native_or_identity_rejected(self):
        for relative in ('calendarmanager/napi/src/calendar_manager_napi.cpp', 'AppScope/app.json5'):
            target = self.project / relative
            original = target.read_bytes()
            target.write_bytes(original + b'\n')
            before = self.snapshot()
            self.assertNotEqual(self.run_component('main_ui').returncode, 0)
            self.assertEqual(before, self.snapshot())
            target.write_bytes(original)

    def test_publication_failure_rolls_back_all_targets(self):
        implementation = load(COMPONENTS / 'main_ui/apply.py', 'calendar_main_apply_test')
        before = self.snapshot()
        calls = []

        def fail_second(path, data, mode):
            calls.append(path)
            implementation.replace(path, data, mode)
            if len(calls) == 2:
                raise OSError('injected publication failure')

        with self.assertRaisesRegex(OSError, 'injected publication'):
            implementation.apply(self.root, publish=fail_second)
        self.assertEqual(before, self.snapshot())
        self.prepare()

    def test_actual_reader_and_ability_lifecycle(self):
        self.prepare()
        for harness, relative in (
            ('reader.cjs', 'entry/src/main/ets/reminder/CalendarReminderReader.ets'),
            ('ability.cjs', 'entry/src/main/ets/MainAbility/MainAbility.ets'),
        ):
            result = subprocess.run(['node', '--unhandled-rejections=strict', str(FIXTURE / harness),
                                     str(self.project / relative)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS ', result.stdout)

    def test_actual_producer_both_reminder_branches_preserve_uri(self):
        self.prepare()
        source = (self.project / 'datamanager/src/main/ets/processor/reminders/ReminderAgentHelper.ets').read_text()
        body = function(source, 'function getReminderRequest(')
        constants = '\n'.join(re.findall(r'^const (?:CALENDAR_BUNDLE_NAME|CALENDAR_ABILITY_NAME|SNOOZE_DELAY|IMPORTANT_ALERT).*?;', source, re.M))
        harness = """
const {stripTypeScriptTypes} = require('node:module');
const vm = require('node:vm'), assert = require('node:assert/strict');
const source = SOURCE;
const sandbox = {reminderAgentManager:{ReminderType:{REMINDER_TYPE_CALENDAR:1}},
  notificationManager:{SlotType:{CONTENT_INFORMATION:4}},setActionButton(){}};
vm.createContext(sandbox);vm.runInContext(stripTypeScriptTypes(source,{mode:'transform'})+'\\nthis.request=getReminderRequest;',sandbox);
for (const kind of [0,1]) {
  const uri='calendar://com.ohos.calendar?event_id=42&start=100&end=200';
  const value=sandbox.request({}, {agendaDetailUri:uri,eventId:42,end:200,title:'Saved',content:'Real'},kind);
  assert.equal(value.wantAgent.pkgName,'com.ohos.calendardata');
  assert.equal(value.wantAgent.abilityName,'MainAbility');
  assert.equal(value.wantAgent.uri,uri);assert.equal(value.notificationId,42);
}
console.log('PASS normal important real-owner uri');
""".replace('SOURCE', json.dumps(constants + '\n' + body))
        path = self.root / 'producer.cjs'
        path.write_text(harness)
        result = subprocess.run(['node', str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_consumer_rejects_old_owner_and_keeps_uri_with_fixed_owner(self):
        original = self.root / NOTIFICATION / 'services/reminder/include/reminder_calendar_share_table.h'
        for fixed in (False, True):
            if fixed:
                result = self.run_component('calendar_owner')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            header = self.root / 'reminder_calendar_share_table.h'
            header.write_bytes(original.read_bytes())
            source = (self.root / NOTIFICATION / 'services/reminder/src/reminder_datashare_helper.cpp').read_text()
            bodies = '\n'.join(function(source, 'void ReminderDataShareHelper::' + name + '(')
                               for name in ('InitNormalInfo', 'CheckWantAgent', 'UpdateCalendarUid'))
            cancel_record = json.loads((FIXTURE / 'notification-provenance.json').read_text())['functions'][0]
            cancel = (FIXTURE / cancel_record['fixture']).read_bytes()
            self.assertEqual(hashlib.sha256(cancel).hexdigest(), cancel_record['sha256'])
            bodies += '\n' + cancel.decode()
            harness = (FIXTURE / 'consumer.cpp').read_text().replace('// ACTUAL_FUNCTIONS', bodies)
            cpp = self.root / 'consumer.cpp'
            cpp.write_text(harness)
            binary = self.root / 'consumer'
            result = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-I', str(self.root),
                                     str(cpp), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary), 'fixed' if fixed else 'original'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
