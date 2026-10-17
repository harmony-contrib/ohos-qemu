const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const {stripTypeScriptTypes} = require('node:module');
let code = fs.readFileSync(process.argv[2], 'utf8').replace(/^import .*?;\n/gm, '')
  .replace(/^export /gm, '');
code = stripTypeScriptTypes(code, {mode: 'transform'});
let permission = 0, permissions = 0, managers = 0, queries = [], mode = 'ok', pending;
const event = {id: 42, title: 'Persisted title', startTime: 1800000000000,
  endTime: 1800003600000, description: 'Persisted note'};
const calendar = {async getEvents(filter) {
  queries.push(filter[0]);
  if (mode === 'query-fail') throw new Error('service failed');
  if (mode === 'query-defer') return new Promise(resolve => pending = resolve);
  if (mode === 'missing') return [];
  if (mode === 'wrong-id') return [{...event, id: 777}];
  if (mode === 'duplicate') return [event, event];
  return [event];
}};
const sandbox = {
  abilityAccessCtrl: {createAtManager() {return {async requestPermissionsFromUser(context, names) {
    permissions++; assert.equal(names[0], 'ohos.permission.READ_WHOLE_CALENDAR');
    if (mode === 'permission-defer') return new Promise(resolve => pending = resolve);
    return {authResults: [permission]};
  }}}},
  calendarManager: {EventFilter: {filterById(ids) {return ids;}}, getCalendarManager() {
    managers++; return {async getAllCalendars() {
      if (mode === 'manager-fail') throw new Error('not permitted');
      return [calendar];
    }};
  }}
};
vm.createContext(sandbox);
vm.runInContext(code + '\nthis.Reader = CalendarReminderReader; this.parse = parseCalendarReminder;', sandbox);
const uri = 'calendar://com.ohos.calendar?event_id=42&start=100&end=200';
const tick = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  const c = new sandbox.Reader({});
  assert.equal(sandbox.parse(uri), 42);
  for (const bad of ['', null, 'https://com.ohos.calendar?event_id=42&start=1&end=2',
    uri + '&title=Spoofed', uri + '#fragment', uri.replace('42', '0'), uri.replace('42', '01'),
    uri.replace('42', '2147483648'), uri.replace('42', '1.5'), uri.replace('100', '-1'),
    uri.replace('end=200', 'end=99'), uri.replace('end=200', 'end=8640000000000001'),
    uri.replace('event_id=42', 'event_id=%34%32'), 'x'.repeat(513)]) {
    assert.throws(() => sandbox.parse(bad));
  }
  await c.open(''); assert.equal(permissions, 0); assert.equal(managers, 0);
  await c.open('bad'); assert.equal(permissions, 0); assert.equal(managers, 0);
  permission = -1; await c.open(uri); assert.equal(managers, 0); assert.equal(c.event, undefined);
  permission = 0; await c.open(uri); assert.equal(c.event.title, event.title);
  assert.equal(c.event.startTime, event.startTime); assert.notEqual(c.event.startTime, 100);
  assert.equal(queries[0], 42); assert.equal(c.status, '');
  for (const badMode of ['manager-fail', 'query-fail', 'missing', 'wrong-id', 'duplicate']) {
    mode = badMode; await c.open(uri); assert.equal(c.event, undefined); assert.ok(c.status);
  }
  mode = 'query-defer'; const old = c.open(uri); await tick(); const resolveOld = pending;
  mode = 'ok'; await c.open(uri); resolveOld([{...event, title: 'Stale'}]); await old;
  assert.equal(c.event.title, event.title);
  mode = 'permission-defer'; const dying = c.open(uri); const managerBefore = managers;
  c.dispose(); pending({authResults: [0]}); await dying;
  assert.equal(managers, managerBefore); assert.equal(c.event, undefined);
  await c.open(uri); assert.equal(managers, managerBefore);
  const first = new sandbox.Reader({}), second = new sandbox.Reader({});
  mode = 'ok'; first.dispose(); await second.open(uri); assert.equal(second.event.title, event.title);
  console.log('PASS validation permission persisted-read failures supersession disposal isolation');
})().catch(error => {console.error(error); process.exitCode = 1;});
