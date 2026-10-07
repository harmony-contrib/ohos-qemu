#!/usr/bin/env node
'use strict';
// Actual UI helper logic fixtures only. The controlled frontend IPC boundary
// below is never installed as a Serial SA, HDI, UI, or HAP implementation.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function main() {
  const [sourcePath, compilerPath] = process.argv.slice(2);
  if (!sourcePath || !compilerPath) {
    throw new Error('usage: check_serial_dialog_request.cjs ACTUAL_HELPER.ts TYPESCRIPT.js');
  }
  const typescript = require(compilerPath);
  const source = fs.readFileSync(sourcePath, 'utf8');
  const output = typescript.transpileModule(source, { reportDiagnostics: true,
    compilerOptions: { target: typescript.ScriptTarget.ES2020, module: typescript.ModuleKind.CommonJS } });
  assert.equal((output.diagnostics || []).filter(item => item.category === typescript.DiagnosticCategory.Error).length, 0);
  const pending = [];
  const calls = [];
  const closures = new Map();
  const logs = [];
  const context = { exports: {}, console: { error: message => logs.push(message) },
    require: name => {
      assert.equal(name, '@ohos.busManager.serial');
      return { default: { addPortAuthorization: (tokenId, deviceId) => {
        calls.push({ tokenId, deviceId });
        return new Promise((resolve, reject) => pending.push({ resolve, reject }));
      } } };
    } };
  vm.runInNewContext(output.outputText, context, { filename: sourcePath });
  const Request = context.exports.SerialDialogRequest;
  const make = (name, tokenId, deviceId, closeFailure = false) => new Request(tokenId, deviceId, 'app-' + name,
    'ttyUSB0', () => {
      closures.set(name, (closures.get(name) || 0) + 1);
      return closeFailure ? Promise.reject(new Error('own session already disconnected')) : Promise.resolve();
    });
  const old = make('old', '2147483648', 'ttyUSB0#request-old');
  const current = make('current', '2147483648', 'ttyUSB0#request-current');
  // Emulate another onSessionCreate replacing the formerly shared globals.
  context.want = { parameters: { tokenId: current.tokenId, deviceId: current.deviceId } };
  context.AppStorage = { session: 'must-never-be-closed' };
  const oldGrant = old.authorizePort();
  const currentGrant = current.authorizePort();
  await old.authorizePort();
  assert.equal(calls.length, 2, 'duplicate Allow must not start another grant or close early');
  assert.equal(closures.size, 0);
  assert.deepEqual(calls[0], { tokenId: '2147483648', deviceId: 'ttyUSB0#request-old' });
  assert.deepEqual(calls[1], { tokenId: '2147483648', deviceId: 'ttyUSB0#request-current' });
  const denied = Object.assign(new Error('old nonce denied by real boundary in runtime'), { code: 35700008 });
  pending[0].reject(denied);
  await assert.rejects(oldGrant, error => error.code === 35700008 && typeof error.code === 'number');
  assert.equal(closures.get('old'), 1);
  assert.equal(closures.get('current'), undefined, 'old finally must not close current session');
  pending[1].resolve();
  await currentGrant;
  await old.close();
  await current.close();
  assert.equal(closures.get('old'), 1);
  assert.equal(closures.get('current'), 1);
  assert.equal(context.AppStorage.session, 'must-never-be-closed');

  const beforeMissing = calls.length;
  const missing = make('missing', '', 'ttyUSB0#request-missing');
  await assert.rejects(missing.authorizePort(), error => /missing Serial authorization/.test(error.message));
  assert.equal(calls.length, beforeMissing, 'missing parameters must not grant');
  assert.equal(closures.get('missing'), 1);

  const failure = make('failure', '4294967295', 'ttyUSB0#request-other-user', true);
  const failureGrant = failure.authorizePort();
  const disconnectError = Object.assign(new Error('device unplugged'), { code: 35700003 });
  pending[2].reject(disconnectError);
  await assert.rejects(failureGrant, error => error.code === 35700003 && typeof error.code === 'number');
  assert.equal(closures.get('failure'), 1);
  assert.equal(closures.get('current'), 1);
  assert.equal(logs.length, 1, 'own close failure is logged without replacing numeric grant failure');
  assert.deepEqual(calls[2], { tokenId: '4294967295', deviceId: 'ttyUSB0#request-other-user' });

  const late = make('late', '2147483648', 'ttyUSB0#request-late');
  const fresh = make('fresh', '2147483649', 'ttyUSB0#request-fresh');
  const lateGrant = late.authorizePort();
  const freshGrant = fresh.authorizePort();
  pending[4].resolve();
  await freshGrant;
  assert.equal(closures.get('fresh'), 1);
  assert.equal(closures.get('late'), undefined);
  pending[3].resolve();
  await lateGrant;
  assert.equal(closures.get('late'), 1);
  assert.equal(closures.get('fresh'), 1, 'late successful finally still closes only its own session');

  // Exercise the actual UI ability's per-session LocalStorage routing too.
  // These native-session stand-ins are frontend lifecycle fixtures, not a UI,
  // permission decision, or runtime Serial implementation.
  const abilitySourcePath = path.join(path.dirname(sourcePath), '../ServiceExtAbility/UsbDialogAbility.ts');
  const abilitySource = fs.readFileSync(abilitySourcePath, 'utf8');
  const abilityOutput = typescript.transpileModule(abilitySource, { reportDiagnostics: true,
    compilerOptions: { target: typescript.ScriptTarget.ES2020, module: typescript.ModuleKind.CommonJS } });
  assert.equal((abilityOutput.diagnostics || []).filter(item => item.category === typescript.DiagnosticCategory.Error).length, 0);
  class LocalStorageFixture { constructor(values) { this.values = values; } }
  class UIExtensionFixture { constructor() { this.context = { getApplicationContext: () => ({ setColorMode: () => {} }) }; } }
  const sessionClosed = new Map();
  const loaded = new Map();
  const usbGlobals = { session: 'original-USB-session' };
  let globalCloseCount = 0;
  const abilityContext = { exports: {}, LocalStorage: LocalStorageFixture,
    console: { error: () => {}, log: () => {} }, AppStorage: { setOrCreate: (key, value) => { usbGlobals[key] = value; } },
    require: name => {
      if (name === '@ohos.app.ability.UIExtensionAbility') return { default: UIExtensionFixture };
      if (name === '../util/SerialDialogRequest') return { SerialDialogRequest: Request };
      if (name === '../util/DialogUtil') return { terminateDialog: () => { ++globalCloseCount; } };
      throw new Error('unexpected actual ability import: ' + name);
    } };
  const nativeSession = (name, loadFailure = false) => ({
    loadContent: (page, storage) => {
      if (loadFailure) throw new Error('own UI connection failed');
      loaded.set(name, { page, storage });
    }, setWindowBackgroundColor: () => {}, terminateSelf: () => {
      sessionClosed.set(name, (sessionClosed.get(name) || 0) + 1);
      return Promise.resolve();
    } });
  vm.runInNewContext(abilityOutput.outputText, abilityContext, { filename: abilitySourcePath });
  const ability = new abilityContext.exports.default();
  const originalUSB = nativeSession('usb');
  ability.onSessionCreate({ parameters: {} }, originalUSB);
  const usbWant = abilityContext.want;
  ability.onSessionCreate({ parameters: { tokenId: '2147483648', deviceId: 'ttyUSB0#request-session-old',
    appName: 'old', portName: 'ttyUSB0' } }, nativeSession('session-old'));
  ability.onSessionCreate({ parameters: { tokenId: '4294967295', deviceId: 'ttyUSB0#request-session-new',
    appName: 'new', portName: 'ttyUSB0' } }, nativeSession('session-new'));
  assert.equal(loaded.get('session-old').page, 'pages/SerialDialog');
  assert.notEqual(loaded.get('session-old').storage, loaded.get('session-new').storage);
  const oldPageRequest = loaded.get('session-old').storage.values.serialRequest;
  const newPageRequest = loaded.get('session-new').storage.values.serialRequest;
  assert.equal(oldPageRequest.tokenId, '2147483648');
  assert.equal(oldPageRequest.deviceId, 'ttyUSB0#request-session-old');
  assert.equal(newPageRequest.tokenId, '4294967295');
  await oldPageRequest.close();
  assert.equal(sessionClosed.get('session-old'), 1);
  assert.equal(sessionClosed.get('session-new'), undefined);
  assert.equal(sessionClosed.get('usb'), undefined);
  assert.equal(usbGlobals.session, originalUSB);
  assert.equal(abilityContext.want, usbWant, 'Serial route must not replace USB globals');
  ability.onSessionCreate({ parameters: { portName: 'ttyUSB0' } }, nativeSession('session-failed', true));
  await Promise.resolve();
  assert.equal(sessionClosed.get('session-failed'), 1);
  assert.equal(globalCloseCount, 0, 'failed Serial content load closes only its own native session');
  console.log(JSON.stringify({ scope: 'actual_UI_helper_frontend_logic_fixtures_NOT_runtime_authorization',
    source_sha256: crypto.createHash('sha256').update(source).digest('hex'),
    actual_ability_source_sha256: crypto.createHash('sha256').update(abilitySource).digest('hex'),
    checks: ['concurrent sessions', 'same-port stale nonce', 'immutable target token', 'duplicate Allow',
      'grant-before-own-close', 'late reject finally', 'late successful finally', 'missing parameters fail closed',
      'unplug error stays number', 'own close failure preserves grant error', 'global session untouched', 'close once',
      'actual ability per-session storage', 'existing USB route preserved', 'failed content load closes own session'],
    first_package_gate_passed: false }));
}

main().catch(error => { console.error(error); process.exitCode = 1; });
