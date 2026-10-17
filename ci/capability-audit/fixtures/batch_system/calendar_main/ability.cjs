const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const {stripTypeScriptTypes} = require('node:module');
let code = fs.readFileSync(process.argv[2], 'utf8').replace(/^import .*?;\n/gm, '')
  .replace('export default class', 'class');
code = stripTypeScriptTypes(code, {mode: 'transform'});
const sandbox = {UIAbility: class {}, LocalStorage: class {
  values = new Map(); setOrCreate(name, value) {this.values.set(name, value);}
}};
vm.createContext(sandbox); vm.runInContext(code + '\nthis.Ability = MainAbility;', sandbox);
const one = new sandbox.Ability(), two = new sandbox.Ability();
one.onCreate({uri: 'first'}); two.onCreate({});
let calls = [];
one.onWindowStageCreate({loadContent(path, storage) {calls.push({path, storage});}});
two.onWindowStageCreate({loadContent(path, storage) {calls.push({path, storage});}});
assert.equal(calls[0].path, 'pages/index');
assert.equal(calls[0].storage.values.get('calendarRoute'), 'first');
assert.equal(calls[1].storage.values.get('calendarRoute'), '');
one.onNewWant({uri: 'second'});
assert.equal(calls[0].storage.values.get('calendarRoute'), 'second');
assert.equal(calls[1].storage.values.get('calendarRoute'), '');
const revision = calls[0].storage.values.get('calendarRevision');
one.onNewWant({uri: 'second'});
assert.ok(calls[0].storage.values.get('calendarRevision') > revision);
const foregroundRevision = calls[0].storage.values.get('calendarRevision');
one.onForeground();
assert.ok(calls[0].storage.values.get('calendarRevision') > foregroundRevision);
one.onDestroy(); assert.equal(calls[0].storage.values.get('calendarRoute'), '');
console.log('PASS create new-want per-ability-storage window destruction');
