'use strict';
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const original = process.argv[2];
const candidate = process.argv[3];
let checks = 0;
const plain = value => JSON.parse(JSON.stringify(value));
function load(file, mode = {}) {
  const state = {connect: 0, disconnect: [], sequences: [], requests: [], callbacks: [], timers: new Set()};
  class NativeHelper {}
  const native = new Proxy({getPhotoAccessHelper() {return new NativeHelper();}}, {
    get(target, key) {return key in target ? target[key] : class {};}
  });
  const proxy = {async sendMessageRequest(code, data, reply) {
    state.requests.push({code, data: data.items.slice()});
    if (mode.sendFailure) throw new Error('real-like IPC failure');
    return {errCode: mode.errCode || 0, reply};
  }};
  const context = {
    connectServiceExtensionAbility(want, callbacks) {
      ++state.connect;
      assert.equal(want.bundleName, 'com.ohos.photos');
      assert.equal(want.abilityName, 'RecentPhotoInfoAbility');
      state.callbacks.push(callbacks);
      if (mode.connectThrow) throw new Error('connect rejected');
      if (mode.syncFailure) callbacks.onFailed();
      else if (mode.syncDisconnect) callbacks.onDisconnect();
      else if (!mode.timeout) {
        if (mode.cold) setTimeout(() => callbacks.onConnect({}, proxy), 15);
        else queueMicrotask(() => callbacks.onConnect({}, proxy));
      }
      return state.connect - 1;
    },
    async disconnectServiceExtensionAbility(id) {state.disconnect.push(id);}
  };
  const rpc = {
    MessageOption: class {},
    MessageSequence: {create() {
      if (mode.allocationFailure === state.sequences.length) throw new Error('allocation failed');
      const sequence = {
        items: [], reclaimed: 0,
        writeInterfaceToken(value) {this.items.push(value); if (mode.writeFailure) throw new Error('write failed');},
        writeInt(value) {this.items.push(value);}, writeString(value) {this.items.push(value);},
        readLong() {return mode.dateTaken === undefined ? 123456 : mode.dateTaken;},
        readString() {return mode.identifier === undefined ? 'actual-asset' : mode.identifier;},
        reclaim() {++this.reclaimed; if (mode.reclaimFailure) throw new Error('reclaim failed');}
      };
      state.sequences.push(sequence);
      return sequence;
    }}
  };
  const sandbox = {console: {info(){},error(){},log(){}},
    requireNapi: () => native,
    requireInternal: name => name === 'rpc' ? rpc : {},
    setTimeout(callback, delay) {
      const timer = setTimeout(() => {state.timers.delete(timer); callback();}, delay === 10000 ? 25 : 1);
      state.timers.add(timer); return timer;
    },
    clearTimeout(timer) {state.timers.delete(timer); clearTimeout(timer);},
    getContext: () => context,
  };
  vm.createContext(sandbox);
  const source = fs.readFileSync(file, 'utf8').replace('export default {', 'globalThis.publicModule = {');
  vm.runInContext(source + '\nglobalThis.testApi = {getRecentPhotoInfo, checkArguments};', sandbox, {filename:file});
  sandbox.publicModule.getPhotoAccessHelper(context);
  return {state, api:sandbox.testApi, module:sandbox.publicModule};
}
async function run() {
  const old = load(original);
  assert.throws(() => old.api.getRecentPhotoInfo(), error => error.code === 401);
  const oldOptions = {};
  await old.api.getRecentPhotoInfo(oldOptions);
  assert.notDeepEqual(plain(oldOptions), {});
  assert.equal(old.state.disconnect.length, 0);
  assert.equal(old.api.checkArguments([{maxSelectNumber:0.5}]).code, 13900020);
  checks += 4;
  for (const options of [undefined, {}, Object.freeze({}), Object.freeze({period:0}),
      Object.freeze({period:-1}), Object.freeze({period:86401}),
      Object.freeze({MIMEType:'image/*', photoSource:1,period:123})]) {
    const item = load(candidate);
    const before = options === undefined ? undefined : plain(options);
    for (let n=0;n<2;n++) {
      const result = await item.api.getRecentPhotoInfo(options);
      assert.deepEqual(plain(result), {dateTaken:123456,identifier:'actual-asset'});
      assert.deepEqual(options === undefined ? undefined : plain(options), before);
      ++checks;
    }
    assert.deepEqual(item.state.requests[0].data,item.state.requests[1].data);
    assert.deepEqual(item.state.disconnect,[0,1]);
    assert(item.state.sequences.every(s => s.reclaimed === 1));
    assert.equal(item.state.timers.size,0);
    checks += 4;
  }
  for (const invalid of [null, [], 'bad', 1, {period:NaN}, {period:Infinity}, {period:null},
                         {photoSource:NaN}, {photoSource:Infinity}, {photoSource:null}]) {
    const item = load(candidate);
    assert.throws(() => item.api.getRecentPhotoInfo(invalid), error => error.code === 401);
    assert.equal(item.state.connect,0);
    checks += 2;
  }
  for (const mode of [{timeout:true},{syncFailure:true},{syncDisconnect:true},{connectThrow:true},
      {sendFailure:true},{errCode:5},{writeFailure:true},{allocationFailure:0},{allocationFailure:1}]) {
    const item = load(candidate,mode);
    assert.deepEqual(plain(await item.api.getRecentPhotoInfo()),{dateTaken:-1,identifier:'-1'});
    assert.deepEqual(item.state.disconnect,mode.connectThrow ? [] : [0]);
    assert(item.state.sequences.every(s => s.reclaimed===1));
    assert.equal(item.state.timers.size,0);
    if (mode.timeout) {
      item.state.callbacks[0].onConnect({},{});
      item.state.callbacks[0].onFailed();
      assert.deepEqual(item.state.disconnect,[0]);
    }
    checks += 4;
  }
  const empty = load(candidate,{dateTaken:0,identifier:'unused'});
  assert.deepEqual(plain(await empty.api.getRecentPhotoInfo()),{dateTaken:0,identifier:'0'});
  const cold = load(candidate,{cold:true});
  assert.equal((await cold.api.getRecentPhotoInfo()).identifier,'actual-asset');
  assert.deepEqual(cold.state.disconnect,[0]);
  const concurrent = load(candidate);
  const results = await Promise.all(Array.from({length:64},() => concurrent.api.getRecentPhotoInfo({})));
  assert(results.every(x => x.identifier==='actual-asset'));
  assert.equal(new Set(concurrent.state.disconnect).size,64);
  assert.equal(concurrent.state.disconnect.length,64);
  assert(concurrent.state.sequences.every(s => s.reclaimed === 1));
  checks += 7;
  const picker = load(candidate);
  for (const args of [[{maxSelectNumber:0.5}],[{maxSelectNumber:NaN}],[{maxSelectNumber:Infinity}],
      [{maxSelectNumber:'2'}],[{maxSelectNumber:501}],[null],[[]],['bad'],[{},null],[{},{},{}]]) {
    assert.equal(picker.api.checkArguments(args).code,401); ++checks;
  }
  for (const args of [[],[undefined],[{}],[()=>{}],[{},()=>{}],[{maxSelectNumber:1}],
      [{maxSelectNumber:500}],[{maxSelectNumber:-1}],[new picker.module.PhotoSelectOptions()]]) {
    assert.equal(picker.api.checkArguments(args),undefined); ++checks;
  }
  let callbackCalls = 0;
  await new picker.module.PhotoViewPicker().select({maxSelectNumber:0.5}, error => {
    ++callbackCalls;
    assert.equal(error.code,401);
  });
  assert.equal(callbackCalls,1);
  await assert.rejects(new picker.module.PhotoViewPicker().select({maxSelectNumber:0.5}), error => error.code===401);
  checks += 2;
  console.log(JSON.stringify({status:'pass',checks,
    scope:'whole actual JS with named RPC/context fixtures, NOT guest or package acceptance',
    original_optional_parameter_mutation_connection_and_picker_errors_reproduced:true}));
}
run().catch(error => {console.error(error);process.exitCode=1;});
