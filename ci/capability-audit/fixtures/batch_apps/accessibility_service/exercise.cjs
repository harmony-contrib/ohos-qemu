// Host-only service doubles; execute the service body extracted from the actual patch.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
const scenario = process.argv[3];
const configCalls = [], events = [], logs = [], writes = [], pending = [];
const model = {ignoreRepeatClick: true};
let terminateCalls = 0, configMode = 'deferred', writeFails = false;
let service, reentered = false;
const config = {};
for (const key of ['ignoreRepeatClick', 'animationOff']) {
  config[key] = {set(value) {
    assert.equal(value, false);
    configCalls.push(key);
    if (configMode === 'throw') throw Object.assign(new Error('sync denied'), {code: 201});
    if (configMode === 'reject') return Promise.reject(Object.assign(new Error('async denied'), {code: 201}));
    if (configMode === 'reenter' && !reentered) {
      reentered = true;
      service.onRequest({action: 'reOpenTransitionAnimations'}, 2);
    }
    return new Promise((resolve, reject) => pending.push({key, resolve, reject}));
  }};
}
const sandbox = {
  ServiceExtensionAbility: class {
    constructor() {
      this.context = {terminateSelf() {
        terminateCalls++;
        throw new Error('service must not introduce unconditional asynchronous termination');
      }};
    }
  },
  config,
  LogUtil: Object.fromEntries(['showInfo', 'warn', 'error', 'info'].map(k => [k, (...a) => logs.push([k, a.join(' ')])])),
  SettingsDataUtils: {setSecureValue(...args) {
    if (writeFails) throw new Error('write denied');
    writes.push(args);
  }},
  HiSysEventUtil: {reportDefaultBehaviorEventByUE(...args) { events.push(args); }},
  HiSysAccessibilityEventGroup: {IGNORE_REPEAT_TOUCHES_SWITCH: 'ignore', TRANSITION_ANIMATIONS_STATE: 'animation'},
  CLICK_SWITCH_OFF: '0',
  IgnoreRepeatedStateModel: {getInstance: () => model},
};
vm.createContext(sandbox);
vm.runInContext(source + '\nthis.Service = IgnoreRepeatClickService;', sandbox);
service = new sandbox.Service();
const tick = () => new Promise(resolve => setImmediate(resolve));
const successLogs = () => logs.filter(row => row[1].includes('success'));
const errors = () => logs.filter(row => row[0] === 'error');
const request = action => service.onRequest({action, bundleName: 'com.ohos.settings', abilityName: 'IgnoreRepeatClickExtService'}, 1);
function finish(error) {
  const action = pending.shift();
  assert.ok(action, 'expected real pending configuration');
  if (error) action.reject(error); else action.resolve();
}
async function main() {
  if (scenario === 'pending_success') {
    request('disableIgnoreRepeatClick');
    await tick();
    assert.equal(model.ignoreRepeatClick, true, 'cache must not anticipate backend completion');
    assert.equal(events.length, 0);
    assert.equal(successLogs().length, 0);
    assert.equal(terminateCalls, 0);
    finish(); await tick();
    assert.equal(model.ignoreRepeatClick, false);
    assert.deepEqual(events, [['ignore', 'off']]);
    assert.equal(successLogs().length, 1);
    assert.equal(terminateCalls, 0);
  } else if (scenario === 'animation_success') {
    request('reOpenTransitionAnimations'); await tick();
    assert.equal(events.length, 0); assert.equal(terminateCalls, 0);
    finish(); await tick();
    assert.deepEqual(events, [['animation', 'on']]);
    assert.equal(terminateCalls, 0);
  } else if (['async_rejection', 'sync_throw'].includes(scenario)) {
    configMode = scenario === 'async_rejection' ? 'reject' : 'throw';
    request('disableIgnoreRepeatClick'); await tick();
    assert.equal(model.ignoreRepeatClick, true);
    assert.equal(events.length, 0); assert.equal(successLogs().length, 0);
    assert.equal(errors().length, 1); assert.match(errors()[0][1], /201/);
    assert.equal(terminateCalls, 0);
    // A failed request cannot poison the queue and suppress a later operation.
    configMode = 'deferred'; request('reOpenTransitionAnimations'); await tick();
    assert.equal(pending.length, 1); finish(); await tick();
    assert.deepEqual(events, [['animation', 'on']]); assert.equal(terminateCalls, 0);
  } else if (['queued', 'reentrant'].includes(scenario)) {
    configMode = scenario === 'reentrant' ? 'reenter' : 'deferred';
    request('disableIgnoreRepeatClick');
    if (scenario === 'queued') request('reOpenTransitionAnimations');
    await tick();
    assert.deepEqual(configCalls, ['ignoreRepeatClick']);
    finish(); await tick();
    assert.deepEqual(configCalls, ['ignoreRepeatClick', 'animationOff']);
    assert.equal(terminateCalls, 0, 'earlier request cannot terminate a queued request');
    assert.equal(pending.length, 1); finish(); await tick();
    assert.equal(events.length, 2); assert.equal(terminateCalls, 0);
  } else if (scenario === 'failure_then_queued') {
    request('disableIgnoreRepeatClick'); request('reOpenTransitionAnimations'); await tick();
    finish(new Error('first operation rejected')); await tick();
    assert.equal(model.ignoreRepeatClick, true);
    assert.equal(events.length, 0); assert.equal(terminateCalls, 0);
    assert.deepEqual(configCalls, ['ignoreRepeatClick', 'animationOff']);
    finish(); await tick(); assert.deepEqual(events, [['animation', 'on']]);
    assert.equal(terminateCalls, 0);
  } else if (scenario === 'notification_actions') {
    request('disableNotificaiton'); request('disableTransitionAnimationsNotification'); await tick();
    assert.deepEqual(writes, [['ignore_repeat_click_notification', '0'], ['transition_animations_notification', '0']]);
    assert.equal(configCalls.length, 0); assert.equal(terminateCalls, 0);
  } else if (scenario === 'notification_failure') {
    writeFails = true; request('disableNotificaiton'); await tick();
    assert.equal(errors().length, 1); assert.equal(terminateCalls, 0);
    assert.equal(configCalls.length, 0); assert.equal(events.length, 0);
  } else if (scenario === 'unknown_action') {
    request('unexpected'); await tick();
    assert.equal(configCalls.length, 0); assert.equal(writes.length, 0);
    assert.equal(events.length, 0); assert.equal(successLogs().length, 0);
    assert.equal(terminateCalls, 0);
  } else throw new Error('unknown test scenario: ' + scenario);
  console.log('PASS ' + scenario);
}
main().catch(error => { console.error(error); process.exitCode = 1; });
