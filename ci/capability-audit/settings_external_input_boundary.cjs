const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const ts = require(process.argv[3]);
const source = fs.readFileSync(process.argv[2], 'utf8');
const output = ts.transpileModule(source, { compilerOptions: {
  target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.CommonJS
}}).outputText;
let adds = 0, removes = 0, queries = 0, backendFailure = false;
const methods = [{ name: 'com.example.keyboard', id: 'InputAbility', label: 'Installed Keyboard' }];
class Base { constructor() { this.context = { config: { fontSizeScale: 1 } }; } }
class LocalStorage { constructor(values) { this.values = values; } }
class InputPushParam { constructor(extra, title) { this.extra = extra; this.title = title; } }
const modules = {
  '@kit.AbilityKit': { UIExtensionAbility: Base },
  '@ohos.inputMethod': { default: { getSetting() { return {
    getAllInputMethodsSync() { queries++; if (backendFailure) throw Error('backend'); return methods; }
  }; } } },
  '@ohos/settings.common/src/main/ets/ability/AbilityContextManager': {
    AbilityContextManager: { addContext() { adds++; }, removeContext() { removes++; } }
  },
  '@ohos/settings.common/src/main/ets/utils/FontScaleUtils': { FontScaleUtils: { setConfig() {} } },
  '@ohos/settings.common/src/main/ets/utils/LogUtil': { LogUtil: { error() {} } },
  '../pages/input/controller/inputSettingController': { InputPushParam }
};
const exportsObject = {};
vm.runInNewContext(output, { exports: exportsObject, LocalStorage,
  require(name) { assert.ok(Object.hasOwn(modules, name), name); return modules[name]; }
});
const Extension = exportsObject.default;
function session(fail = false) { return { closes: 0, loads: [],
  terminateSelf() { this.closes++; },
  loadContent(path, storage) { if (fail) throw Error('load'); this.loads.push({ path, storage }); }
}; }
function detail(extra = { value: methods[0].name, name: methods[0].id }) {
  return { uri: 'other_input_detail_settings', parameters: {
    isParamJsonObject: true, pushParam: JSON.stringify({ extra })
  } };
}
let passed = 0;
function run(name, fn) { fn(); passed++; }
run('list opens original UI without enumerating or modifying an IME', () => {
  const extension = new Extension(), view = session();
  extension.onSessionCreate({ uri: 'set_input', parameters: { uri: 'password_settings' } }, view);
  assert.equal(view.loads.length, 1); assert.equal(queries, 0);
  assert.equal(view.loads[0].path, 'pages/input/ExternalInputSettings');
  assert.equal(view.loads[0].storage.values.inputRoute, 'set_input');
  extension.onSessionDestroy(view); extension.onSessionDestroy(view);
  assert.equal(adds, removes);
});
run('detail uses installed identity and label only', () => {
  const extension = new Extension(), view = session(), request = detail();
  request.parameters.pushParams = { title: 'Spoofed', value: 'victim' };
  extension.onSessionCreate(request, view);
  assert.equal(view.loads.length, 1);
  const config = view.loads[0].storage.values.inputConfig;
  assert.equal(config.title, methods[0].label);
  assert.equal(config.extra.value, methods[0].name); assert.equal(config.extra.name, methods[0].id);
  extension.onSessionDestroy(view);
});
const bad = [ {}, { uri: '' }, { uri: 'password_settings' }, { uri: 'set_input/../password' },
  { uri: 'other_input_detail_settings' },
  detail({ value: 'com.unknown', name: 'InputAbility' }),
  detail({ value: methods[0].name, name: 'Unknown' }),
  detail({ value: '', name: 'id' }), detail({ value: 1, name: 'id' }),
  detail({ value: 'x'.repeat(513), name: 'id' }), detail(null)
];
for (const raw of ['null', '[]', '{}', 'false', '1', '"x"', '{', '{"extra":[]}',
  '{"extra":{"value":"x"}}', ' '.repeat(8193)]) {
  bad.push({ uri: 'other_input_detail_settings', parameters: { isParamJsonObject: true, pushParam: raw } });
}
for (const flag of [false, 'true', 1, null, undefined]) {
  const request = detail(); request.parameters.isParamJsonObject = flag; bad.push(request);
}
for (const request of bad) run('reject malformed, unregistered, or unrelated route', () => {
  const extension = new Extension(), view = session(), before = adds;
  extension.onSessionCreate(request, view);
  assert.equal(view.loads.length, 0); assert.equal(view.closes, 1); assert.equal(adds, before);
  extension.onSessionDestroy(view); assert.equal(adds, removes);
});
run('backend failure closes without false success', () => {
  const extension = new Extension(), view = session(); backendFailure = true;
  extension.onSessionCreate(detail(), view); backendFailure = false;
  assert.equal(view.loads.length, 0); assert.equal(view.closes, 1); assert.equal(adds, removes);
});
run('failed UI load releases context', () => {
  const extension = new Extension(), view = session(true);
  extension.onSessionCreate({ uri: 'set_input' }, view);
  assert.equal(view.closes, 1); assert.equal(adds, removes);
});
run('foreign and duplicate sessions cannot replace live UI state', () => {
  const extension = new Extension(), first = session(), second = session();
  extension.onSessionCreate({ uri: 'set_input' }, first);
  extension.onSessionCreate(detail(), second);
  assert.equal(first.loads.length, 1); assert.equal(first.closes, 0);
  assert.equal(second.loads.length, 0); assert.equal(second.closes, 1);
  extension.onSessionDestroy(second); assert.equal(adds, removes + 1);
  extension.onSessionDestroy(first); assert.equal(adds, removes);
});
console.log(JSON.stringify({ status: 'pass', cases: passed, actual_extension_source: process.argv[2],
  scope: 'host-mocked request/session boundaries; not guest runtime proof' }));
