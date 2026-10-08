// Actual module evaluation for enum exports only, not RPC/provider behavior.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
(async () => {
  const source = fs.readFileSync(process.argv[2], 'utf8');
  for (let repeat = 0; repeat < 128; repeat++) {
    const requests = [];
    const context = vm.createContext({
      requireNapi(name) {
        requests.push(name);
        if (name === 'rpc') return { RemoteObject: class {
          constructor() { throw new Error('enum check must not instantiate an RPC provider'); }
        }};
        if (name === 'data.relationalStore') return Object.freeze({});
        throw new Error('unexpected extra module dependency: ' + name);
      }
    });
    const module = new vm.SourceTextModule(source, { context });
    await module.link(() => { throw new Error('unexpected external ESM dependency'); });
    await module.evaluate();
    assert.deepEqual(requests, ['data.relationalStore', 'rpc']);
    const nested = module.namespace.cloudExtension;
    const exported = module.namespace.default;
    assert.equal(exported.cloudExtension, nested);
    assert.equal(exported.Flag, nested.Flag);
    const flag = exported.Flag;
    assert.equal(Object.hasOwn(exported, 'Flag'), true);
    assert.equal(Object.hasOwn(nested, 'Flag'), true);
    assert.deepEqual(Object.keys(flag).sort(), ['0','1','2','DELETE','INSERT','UPDATE'].sort());
    for (const [name, value] of [['INSERT',0],['UPDATE',1],['DELETE',2]]) {
      assert.equal(flag[name], value);
      assert.equal(typeof flag[name], 'number');
      assert.equal(flag[value], name);
    }
    assert.equal(typeof exported.createCloudServiceStub, 'function');
    assert.equal(typeof exported.createCloudDBStub, 'function');
    assert.equal(typeof exported.createAssetLoaderStub, 'function');
    assert.equal(typeof exported.createShareServiceStub, 'function');
    assert.equal(exported.FieldType, nested.FieldType);
    assert.equal(exported.ErrorCode, nested.ErrorCode);
  }
  process.stdout.write(JSON.stringify({
    status:'pass', scope:'host_actual_JS_module_enum_export_NOT_RPC_provider_or_Ark_guest',
    repetitions:128, values:{INSERT:0,UPDATE:1,DELETE:2}
  }) + '\n');
})().catch(error => { process.stderr.write(String(error.stack)); process.exitCode = 1; });
