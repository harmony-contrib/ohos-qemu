// Execute the actual generated public JS wrapper against a controlled transport.
// This tests error/overload handling, not real UI, BMS, permissions or a HAP.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
let scenarios = 0;
function load(result, ...contextArgs) {
  const context = contextArgs.length > 0 ? contextArgs[0] : {};
  let calls = [];
  const native = new Proxy({startContactsPicker: (ctx, config) => {
    calls.push({ctx, config});
    if (typeof result === 'function') { return result(ctx, config); }
    return Promise.resolve(result);
  }}, {get: (object, key) => object[key]});
  const sandbox = {requireInternal: () => native, requireNapi: () => ({deviceType: 'phone'}),
    getContext: () => { if (context instanceof Error) { throw context; } return context; },
    console: {log() {}, warn() {}, error() {}}};
  vm.runInNewContext(source.replace('export default {', 'globalThis.api = {'), sandbox);
  return {api: sandbox.api, calls};
}
function contacts(count, offset = 0) {
  return Array.from({length: count}, (_, id) => ({id: offset + id, key: `key-${offset + id}`}));
}
function result(values, code = 0) { return {resultCode: code, total: values.length, pickerData: JSON.stringify(values)}; }
function errorCode(code) { return error => typeof error === 'object' && error !== null && error.code === code; }
async function callback(call, expectedError, expectedLength) {
  let count = 0;
  let resolve;
  let reject;
  const completed = new Promise((yes, no) => { resolve = yes; reject = no; });
  const returned = call((error, data) => {
    count++;
    try {
      if (expectedError === undefined) {
        assert.equal(error, undefined);
        assert.equal(data.length, expectedLength);
      } else { assert(errorCode(expectedError)(error)); assert.equal(data, undefined); }
      resolve();
    } catch (error) { reject(error); }
  });
  assert.equal(returned, undefined, 'callback API must return void');
  await completed;
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(count, 1, 'exactly one callback');
}
(async () => {
  for (const name of ['selectContact', 'selectContacts']) {
    const {api} = load(result(contacts(1)));
    assert.equal((await api[name]()).length, 1); scenarios++;
    await callback(cb => api[name](cb), undefined, 1); scenarios++;
  }
  {
    const {api, calls} = load(result(contacts(205)));
    const values = await api.selectContacts({isMultiSelect: true, maxSelectable: 205, isDisplayedByName: true,
      isAutoDismissOnNavigation: true});
    assert.deepEqual(JSON.parse(JSON.stringify(values)), contacts(205));
    assert.equal(calls[0].config.parameters.isAutoDismissOnNavigation, true);
    assert.equal(calls[0].config.parameters.selectLimit, 205);
    assert.equal(calls[0].config.parameters.isContactMultiSelect, true);
    await callback(cb => api.selectContacts({isMultiSelect: true, maxSelectable: 205}, cb), undefined, 205);
    scenarios += 2;
  }
  {
    const {api, calls} = load(result([]));
    await api.selectContacts({maxSelectable: 10001});
    assert.equal(calls[0].config.parameters.selectLimit, 10000);
    scenarios++;
  }
  for (const packet of [result([], 1), result(contacts(3, 500), 0)]) {
    const {api} = load(packet);
    const values = await api.selectContacts({isMultiSelect: true});
    assert.deepEqual(JSON.parse(JSON.stringify(values)), JSON.parse(packet.pickerData));
    await callback(cb => api.selectContacts({}, cb), undefined, packet.total);
    scenarios += 2;
  }
  for (const [packet, expected] of [
    [{resultCode: -1}, 16700001], [{resultCode: 401}, 401], [{resultCode: 201}, 201],
    [{resultCode: 16000050}, 16700001], [undefined, 16700001],
    [{resultCode: 0, total: 1, pickerData: 'not JSON'}, 16700001],
    [{resultCode: 0, total: 205, pickerData: JSON.stringify(contacts(100))}, 16700001],
    [{resultCode: 0, total: 0, pickerData: '{}'}, 16700001],
    [{resultCode: 0, total: 0, pickerData: 'null'}, 16700001],
    [{resultCode: 0, total: 1, pickerData: '[null]'}, 16700001],
    [{resultCode: 0, total: 1, pickerData: '[[]]'}, 16700001],
    [{resultCode: 0, total: -1, pickerData: '[]'}, 16700001],
    [{resultCode: 0, total: 0.1, pickerData: '[]'}, 16700001],
    [result(contacts(1), 1), 16700001],
  ]) {
    const {api} = load(packet);
    await assert.rejects(api.selectContacts(), errorCode(expected));
    await callback(cb => api.selectContacts(cb), expected);
    await callback(cb => api.selectContacts({}, cb), expected);
    scenarios += 3;
  }
  for (const failure of [new Error('native throws'), {code: 401}, -1]) {
    for (const fail of [() => { throw failure; }, () => Promise.reject(failure)]) {
      const {api} = load(fail);
      const expected = failure.code === 401 ? 401 : 16700001;
      await assert.rejects(api.selectContacts(), errorCode(expected));
      await callback(cb => api.selectContacts(cb), expected);
      scenarios += 2;
    }
  }
  for (const context of [undefined, new Error('context destroyed')]) {
    const fixture = load(result([]), context);
    await assert.rejects(fixture.api.selectContacts(), errorCode(16700001));
    await callback(cb => fixture.api.selectContacts({}, cb), 16700001);
    scenarios += 2;
  }
  for (const args of [[null], [[]], [1], ['bad'], [{}, 'bad'], [{}, () => {}, 'extra'],
    [() => {}, () => {}], [{maxSelectable: 0}], [{maxSelectable: 1.5}], [{maxSelectable: NaN}],
    [{maxSelectable: Infinity}], [{isMultiSelect: 1}], [{isDisplayedByName: 'true'}],
    [{isAutoDismissOnNavigation: 1}], [{filter: null}], [{filter: []}]]) {
    const {api, calls} = load(result([]));
    assert.throws(() => api.selectContacts(...args), errorCode(401));
    assert.equal(calls.length, 0);
    scenarios++;
  }
  // Concurrent calls retain their own context/config/result destination.
  {
    let completions = [];
    const {api} = load(() => new Promise(resolve => completions.push(resolve)));
    const first = api.selectContacts({maxSelectable: 1});
    const second = api.selectContacts({maxSelectable: 2});
    completions[1](result(contacts(2, 200)));
    completions[0](result(contacts(1, 100)));
    assert.equal((await first)[0].id, 100);
    assert.equal((await second)[0].id, 200);
    scenarios++;
  }
  console.log(`${scenarios} actual public JS wrapper scenarios passed`);
})().catch(error => { console.error(error); process.exitCode = 1; });
