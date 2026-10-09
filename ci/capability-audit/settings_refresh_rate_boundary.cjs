// Execute the actual candidate controller; fake services test rejection paths,
// never provide package/runtime acceptance evidence.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require(process.argv[3]);
const source = fs.readFileSync(process.argv[2], 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }, reportDiagnostics: true });
assert.equal((compiled.diagnostics || []).filter(x => x.category === ts.DiagnosticCategory.Error).length, 0);
let active = 0;
let calls = [];
let behavior = 'apply';
let finish;
const modes = [
  {id: 7, width: 1280, height: 800, refreshRate: 60},
  {id: 11, width: 1280, height: 800, refreshRate: 90},
  {id: 19, width: 1920, height: 1080, refreshRate: 60}
];
function current() {
  return {id: 3, sourceMode: 0, supportedModeInfo: modes.map(x => ({...x})), activeModeIndex: active,
    async setScreenActiveMode(id) {
      calls.push(id);
      if (behavior === 'reject') throw new Error('service rejection');
      if (behavior === 'defer') await new Promise(resolve => { finish = resolve; });
      if (behavior !== 'ignore') active = id;
    }};
}
const api = {ScreenSourceMode: {SCREEN_MAIN: 0}, getAllScreens: async () => [current()]};
const output = {exports: {}};
vm.runInNewContext(compiled.outputText, {
  exports: output.exports, module: output,
  require(name) { assert.equal(name, '@ohos.screen'); return {default: api}; }
});
const {mainScreen, refreshChoices, QemuRefreshRateController} = output.exports;
let cases = 0;
function check(action) { action(); cases++; }
async function reject(action) { await assert.rejects(action); cases++; }
(async () => {
  check(() => assert.equal(mainScreen([current()]).activeModeIndex, 0));
  check(() => assert.deepEqual(Array.from(refreshChoices(current()), x => x.id), [7, 11]));
  for (const screens of [[], [current(), current()], [{...current(), sourceMode: 1}],
      [{...current(), activeModeIndex: 99}], [{...current(), supportedModeInfo: []}],
      [{...current(), supportedModeInfo: [modes[0], modes[0]]}]]) {
    check(() => assert.throws(() => mainScreen(screens)));
  }
  for (const index of [-1, 3, 7, 0.5, NaN, '0']) {
    check(() => assert.throws(() => mainScreen([{...current(), activeModeIndex: index}])));
  }
  for (const key of ['id', 'width', 'height', 'refreshRate']) {
    for (const value of [-1, NaN, 1.5]) {
      check(() => assert.throws(() => mainScreen([{...current(), supportedModeInfo: [{...modes[0], [key]: value}]}])));
    }
  }
  const controller = new QemuRefreshRateController();
  check(() => assert.equal(calls.length, 0));
  await controller.change(7);
  check(() => assert.equal(calls.length, 0));
  for (const value of [19, 999, -1, 7.5, '11']) await reject(() => controller.change(value));
  check(() => assert.equal(calls.length, 0));
  const changed = await controller.change(11);
  check(() => assert.equal(changed.activeModeIndex, 1));
  check(() => assert.deepEqual(calls, [1]));
  behavior = 'reject';
  await reject(() => controller.change(7));
  behavior = 'ignore';
  await reject(() => controller.change(7));
  behavior = 'defer';
  const pending = controller.change(7);
  while (!finish) await new Promise(resolve => setImmediate(resolve));
  await reject(() => controller.change(7));
  finish();
  check(() => assert.equal(calls.length, 4));
  const completed = await pending;
  check(() => assert.equal(completed.activeModeIndex, 0));
  behavior = 'apply';
  check(() => assert.equal(refreshChoices({...current(), supportedModeInfo: [modes[0]]}).length, 1));
  console.log(JSON.stringify({status: 'pass', cases, scope: 'host_actual_controller_boundaries_NOT_guest'}));
})().catch(error => { console.error(error); process.exitCode = 1; });
