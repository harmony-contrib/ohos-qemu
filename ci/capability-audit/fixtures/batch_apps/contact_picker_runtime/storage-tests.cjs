/* Actual ETS method host checks with explicit storage/API doubles, NOT guest proof. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const { stripTypeScriptTypes } = require('node:module');

function withoutBuild(text) {
  const start = text.indexOf('  build() {');
  assert.ok(start >= 0);
  let pos = text.indexOf('{', start) + 1, depth = 1;
  while (depth) { depth += (text[pos] === '{') - (text[pos] === '}'); ++pos; }
  return text.slice(0, start) + text.slice(pos);
}
function load(root, seed) {
  const folder = path.join(root, seed ? 'contact_picker_seed' : 'contact_picker_runtime');
  const entry = fs.readFileSync(path.join(folder, 'EntryAbility.ets'), 'utf8');
  const page = fs.readFileSync(path.join(folder, 'Index.ets'), 'utf8');
  assert.match(page, /@Entry\(\{ useSharedStorage: true \}\)/);
  assert.match(entry, /private storage: LocalStorage = new LocalStorage\(\)/);
  const codeOnly = (entry + page).replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
  assert.doesNotMatch(codeOnly, /AppStorage\s*\./);
  function code(text) {
    return stripTypeScriptTypes(text.replace(/^import .*;\n/gm, '')
      .replace('export default ', '').replace(/^@Entry.*\n|^@Component\n/gm, '')
      .replace(/@(?:LocalStorageLink|Watch)\('[^']*'\)\s*/g, '').replace(/@State\s*/g, '')
      .replace('struct Index', 'class Index'), { mode: 'strip' });
  }
  const operations = [];
  class LocalStorage {
    constructor() { this.values = new Map(); this.page = null; }
    setOrCreate(key, value) {
      this.values.set(key, value);
      if (this.page) {
        this.page[key === 'seedRequest' ? 'requestJson' : key] = value;
        if (key === 'seedRequest') this.page.onRequestChanged();
        else if (key === 'requestJson') this.page.onLaunchChanged();
        else this.page.onLifecycleChanged();
      }
    }
  }
  class Request { constructor() { this.runId = ''; this.operationId = ''; this.mode = ''; } }
  class Input { constructor() { this.runId = ''; this.launchId = ''; this.caseId = ''; this.seedIds = []; } }
  class Store {
    constructor(context, request) { this.request = request; }
    execute() { return new Promise(resolve => operations.push({ request: this.request, resolve })); }
  }
  class Cases {
    constructor(input, context, status) { this.input = input; this.status = status; this.disposed = false; }
    start() {} lifecycle() {} dispose() { this.disposed = true; }
  }
  const sandbox = { UIAbility: class {}, LocalStorage, SeedRequest: Request, SeedStore: Store,
    LaunchInput: Input, PickerCases: Cases, CASE_IDS: ['select-promise', 'reopen'], JSON, Set, Number, Error };
  vm.createContext(sandbox);
  // Per-file lexical scopes mirror the real two ETS modules.
  vm.runInContext('(function(){' + code(entry) + ';globalThis.Ability=EntryAbility;})()', sandbox);
  vm.runInContext('(function(){' + code(withoutBuild(page)) + ';globalThis.Page=Index;})()', sandbox);
  function attach(ability) {
    let storage;
    ability.onWindowStageCreate({ loadContent: (route, own) => { assert.equal(route, 'pages/Index'); storage = own; } });
    assert.ok(storage instanceof LocalStorage);
    const view = new sandbox.Page();
    view.getUIContext = () => ({ getHostContext: () => ({ filesDir: '/host-double-only' }) });
    for (const [key, value] of storage.values) view[key === 'seedRequest' ? 'requestJson' : key] = value;
    storage.page = view;
    view.aboutToAppear();
    return { view, storage };
  }
  return { sandbox, attach, operations };
}

(async () => {
  const root = process.argv[2];
  const seed = load(root, true);
  const a = new seed.sandbox.Ability();
  a.onCreate({ parameters: { runId: 'run1', operationId: 'op1', mode: 'create' } });
  const first = seed.attach(a);
  assert.equal(first.view.status, 'Ready: run1/op1/create');
  const b = new seed.sandbox.Ability();
  b.onCreate({ parameters: { runId: 'run2', operationId: 'op2', mode: 'cleanup' } });
  const second = seed.attach(b);
  assert.notEqual(first.storage, second.storage);
  assert.equal(first.view.status, 'Ready: run1/op1/create');
  assert.equal(second.view.status, 'Ready: run2/op2/cleanup');
  const pending = first.view.start();
  assert.equal(seed.operations.length, 1);
  a.onNewWant({ parameters: { runId: 'run3', operationId: 'op3', mode: 'cleanup' } });
  assert.equal(first.view.valid, false);
  assert.equal(first.view.status, 'Waiting for the previous operation');
  assert.equal(seed.operations[0].request.runId, 'run1');
  seed.operations[0].resolve(); await pending;
  assert.equal(first.view.status, 'Ready: run3/op3/cleanup');
  a.onNewWant({ parameters: { runId: 'run1', operationId: 'op1', mode: 'create' } });
  assert.match(first.view.status, /Launch rejected: Operation already started/);
  await first.view.start(); assert.equal(seed.operations.length, 1);
  a.onNewWant({ parameters: { mode: 'create' } });
  assert.equal(first.view.valid, false); assert.match(first.view.status, /Launch rejected:/);

  const caller = load(root, false);
  const c = new caller.sandbox.Ability();
  const request = { runId: 'caller1', launchId: 'launch1', caseId: 'select-promise', seedIds: '[1,2,3]' };
  c.onCreate({ parameters: request });
  const current = caller.attach(c);
  assert.equal(current.view.status, 'Ready: caller1/launch1/select-promise');
  current.view.startCase(); const old = current.view.runs[0];
  c.onNewWant({ parameters: { ...request, runId: 'caller2', launchId: 'launch2' } });
  assert.equal(current.view.status, 'Ready: caller2/launch2/select-promise');
  old.status('late previous status');
  assert.equal(current.view.status, 'Ready: caller2/launch2/select-promise');
  assert.equal(old.input.runId, 'caller1'); assert.equal(old.input.launchId, 'launch1');
  const d = new caller.sandbox.Ability(); d.onCreate({ parameters: { caseId: 'select-promise', seedIds: '[1,2,3]' } });
  const invalid = caller.attach(d);
  assert.notEqual(current.storage, invalid.storage);
  assert.equal(invalid.view.valid, false);
  assert.match(invalid.view.status, /Launch rejected:/);
  c.onBackground(); assert.equal(old.disposed, false);
  assert.match(current.view.lifecycleEvent, /^background\//);
  current.view.aboutToDisappear(); assert.equal(old.disposed, true);
  console.log('actual shared-storage ETS method checks passed; NOT runtime evidence');
})().catch(error => { console.error(error); process.exitCode = 1; });
