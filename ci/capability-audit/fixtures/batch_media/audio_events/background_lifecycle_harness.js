// Controlled SDK dependencies exercise the actual ETS helper; no device/backend proof.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const root = process.argv[3];
const run = '0123456789abcdef0123456789abcdef';
async function scenario(name) {
  const directory = path.join(root, name); fs.mkdirSync(directory);
  const calls = []; const callbacks = {}; const timers = new Map();
  let notificationEnabled = name !== 'notification_denied';
  let actualStatus = 0; let evidenceBroken = false;
  const control = {
    run: () => {
      calls.push('native_run');
      const ready = { run_id: run, action: 'focus_begin', state_result: 0,
        state: name === 'not_running' ? 3 : 2, frames_result: 0, frames: 57600, copied_bytes: 230400 };
      fs.writeFileSync(path.join(directory, 'audio-event-' + run + '-focus_begin-ready.json'), JSON.stringify(ready));
      return true;
    },
    status: () => actualStatus,
    abort: () => { calls.push('native_abort'); actualStatus = 2; return true; }
  };
  const context = { abilityInfo: { bundleName: 'org.harmonycontrib.capabilityaudit', name: 'EntryAbility', moduleName: 'entry' },
    getApplicationContext: () => ({ filesDir: directory }) };
  const bgtask = {
    on: (event, callback) => { callbacks[event] = callback; calls.push('on_' + event); },
    off: (event, callback) => { assert.strictEqual(callback, callbacks[event]); delete callbacks[event]; calls.push('off_' + event); },
    startBackgroundRunning: async (ctx, modes, target) => {
      assert.strictEqual(ctx, context); assert.deepStrictEqual(Array.from(modes), ['audioRecording']);
      assert.strictEqual(target.owner, 'ordinary'); calls.push('background_start');
      return { notificationId: 4, continuousTaskId: 42 };
    },
    stopBackgroundRunning: async (ctx) => { assert.strictEqual(ctx, context); calls.push('background_stop'); }
  };
  const file = {
    OpenMode: { CREATE: 1, WRITE_ONLY: 2 }, accessSync: fs.existsSync,
    readTextSync: (name) => fs.readFileSync(name, 'utf8'),
    openSync: (name) => { if (evidenceBroken) throw new Error('controlled EIO'); return { fd: fs.openSync(name, 'wx', 0o600) }; },
    writeSync: (fd, bytes) => fs.writeSync(fd, Buffer.from(bytes)), fsyncSync: fs.fsyncSync,
    closeSync: (handle) => fs.closeSync(handle.fd)
  };
  const dependencies = {
    '@ohos.file.fs': file,
    '@ohos.hilog': { info() {}, error() {} },
    '@ohos.util': { TextEncoder: class { encodeInto(text) { return Uint8Array.from(Buffer.from(text)); } } },
    '@ohos.resourceschedule.backgroundTaskManager': bgtask,
    '@ohos.notificationManager': {
      isNotificationEnabled: async () => notificationEnabled,
      requestEnableNotification: async (ctx) => { assert.strictEqual(ctx, context); calls.push('notification_request'); }
    },
    '@ohos.wantAgent': {
      OperationType: { START_ABILITY: 2 }, WantAgentFlags: { CONSTANT_FLAG: 0 },
      getWantAgent: async (info) => { assert.strictEqual(info.wants[0].bundleName, context.abilityInfo.bundleName); return { owner: 'ordinary' }; }
    }
  };
  const exports = {};
  vm.runInNewContext(source, { exports,
    require: (name) => { assert(name in dependencies, 'unexpected import ' + name); return { default: dependencies[name] }; },
    setInterval: (callback) => { timers.set(1, callback); return 1; }, clearInterval: (id) => timers.delete(id),
    setTimeout, Date, Promise, Error, ArrayBuffer, Uint8Array, JSON });
  const session = new exports.AudioRecordingSession(context, run, 1, control);
  if (name === 'notification_denied') {
    await assert.rejects(session.start(true), /notification remains disabled/);
    assert(!calls.includes('native_run')); assert(!calls.includes('background_start'));
    assert(calls.includes('notification_request')); return;
  }
  if (name === 'not_running') {
    await assert.rejects(session.start(true), /no real RUNNING PCM/);
    assert(calls.includes('native_abort')); assert(!calls.includes('background_start'));
  } else {
    await session.start(true);
    assert(calls.indexOf('native_run') < calls.indexOf('background_start'));
    const snapshots = fs.readdirSync(directory).filter((name) => name.includes('-background-'))
      .map((name) => JSON.parse(fs.readFileSync(path.join(directory, name), 'utf8')));
    assert(snapshots.some((row) => row.event === 'native_microphone_ready'));
    assert(snapshots.some((row) => row.event === 'background_started'));
    callbacks.continuousTaskCancel({ id: 99, reason: 0 });
    callbacks.continuousTaskSuspend({ continuousTaskId: 42, suspendState: false, suspendReason: 0 });
    assert(!calls.includes('native_abort'));
    if (name === 'cancel') {
      callbacks.continuousTaskSuspend({ continuousTaskId: 42, suspendState: true, suspendReason: 7 });
      assert(calls.includes('native_abort'));
    } else { actualStatus = 1; }
    if (name === 'evidence_io_error') evidenceBroken = true;
  }
  assert.strictEqual(timers.size, 1); timers.get(1)();
  // The actual helper's cleanup is asynchronous; allow its returned service promises to resolve.
  await new Promise((resolve) => setImmediate(resolve));
  assert.strictEqual(timers.size, 0); assert.deepStrictEqual(Object.keys(callbacks), []);
  if (name !== 'not_running') assert(calls.includes('background_stop'));
}
(async () => {
  for (const name of ['normal', 'cancel', 'not_running', 'notification_denied', 'evidence_io_error']) await scenario(name);
  console.log('Actual ETS helper with controlled SDK dependencies: real-readiness prerequisite, notification denial, task identity/suspend, abort and guaranteed stop cleanup passed; not runtime proof');
})().catch((error) => { console.error(error); process.exitCode = 1; });
