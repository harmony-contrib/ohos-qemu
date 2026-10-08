// Private whole-checked-in-JS regression fixture, NOT a guest or AI-provider proof.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function load(name) {
  const options = { images: [{ url: 'input://one' }], layoutImage: { image: 'layout://one' },
    shapePath: 'shape-path', userPrompt: 'prompt', style: 3, resolution: { width: 128, height: 128 } };
  const context = { imageGeneration: { PartialResultType: { PARTIAL: 0, COMPLETED: 1, PARTIAL_FAIL: 2 } },
    AIGenerateOptions: { getInstance: () => options }, console: { info() {}, error() {} },
    setTimeout() { throw Error('mock/default-model timers are not accepted by this fixture'); } };
  const source = fs.readFileSync(name, 'utf8')
    .replace(/^import .+;\n/gm, '').replace('export class AIGenerateImpl', 'class AIGenerateImpl');
  vm.runInNewContext(source + '\nthis.GeneratedClass = AIGenerateImpl;', context);
  return { instance: new context.GeneratedClass(), options };
}

function callbacks() {
  const events = [];
  return { events, callback: { onReady: () => events.push(['ready']), onError: () => events.push(['error']),
    onComplete: (images) => events.push(['complete', JSON.parse(JSON.stringify(images))]) } };
}

async function run() {
  const original = load(process.argv[2]).instance;
  original.setSelfImageGenerateModal({ requestImageGeneration(id, params, callback) {
    callback({ type: 0, imageData: 'image://before' }); } });
  await assert.rejects(original.ImageAIGenerate(callbacks().callback), /undefined.*push/);

  const { instance, options } = load(process.argv[3]);
  const synchronous = callbacks();
  instance.setSelfImageGenerateModal({ requestImageGeneration(id, params, callback) {
    assert.equal(id, 0); assert.equal(params.images, options.images);
    assert.equal(params.positionImage, options.layoutImage.image);
    assert.equal(params.selectPath, options.shapePath); assert.equal(params.prompt, options.userPrompt);
    assert.equal(params.style, options.style); assert.equal(params.imageSize, options.resolution);
    assert.deepEqual(synchronous.events, [['ready']]);
    callback({ type: 0, imageData: 'image://first' });
    callback({ type: 0, imageData: 'image://second' });
    callback({ type: 1, totalCount: 2 });
    callback({ type: 1, imageData: 'invalid-completion-image' });
    callback({ type: 0, imageData: 'late-image' });
  } });
  assert.equal(await instance.ImageAIGenerate(synchronous.callback), 0);
  assert.deepEqual(synchronous.events, [['ready'], ['complete', ['image://first', 'image://second']]]);

  const saved = new Map();
  const cancelled = [];
  instance.setSelfImageGenerateModal({ requestImageGeneration(id, params, callback) { saved.set(id, callback); },
    cancelImageGeneration(id) { cancelled.push(id); saved.get(id)({ type: 1 }); } });
  const a = callbacks(), b = callbacks();
  const aId = await instance.ImageAIGenerate(a.callback), bId = await instance.ImageAIGenerate(b.callback);
  saved.get(aId)({ type: 0, imageData: 'stale' }); saved.get(aId)({ type: 1 });
  saved.get(bId)({ type: 0 }); // Optional data must not create an undefined image.
  saved.get(bId)({ type: 2 }); // Error type is sufficient; BusinessError is optional.
  saved.get(bId)({ type: 0, partialFail: { code: 1 } });
  saved.get(bId)({ type: 0, imageData: 'valid' });
  saved.get(bId)({ type: 1 });
  assert.deepEqual(a.events, [['ready']]);
  assert.deepEqual(b.events, [['ready'], ['error'], ['error'], ['complete', ['valid']]]);
  assert.ok(bId > aId);

  const c = callbacks(); const cId = await instance.ImageAIGenerate(c.callback);
  await instance.cancelImageGenerateTask(cId);
  saved.get(cId)({ type: 0, imageData: 'cancelled' }); saved.get(cId)({ type: 1 });
  assert.deepEqual(c.events, [['ready']]); assert.equal(instance.getCurrentImageSessionId(), -1);
  const d = callbacks(); const dId = await instance.ImageAIGenerate(d.callback);
  await instance.cancelImageGenerateTask(cId); // Cancel old session cannot invalidate the new one.
  assert.equal(instance.getCurrentImageSessionId(), dId); saved.get(dId)({ type: 1 });
  assert.deepEqual(d.events, [['ready'], ['complete', []]]);
  assert.deepEqual(cancelled, [cId, cId]);

  const independent = load(process.argv[3]).instance;
  const isolated = callbacks();
  independent.setSelfImageGenerateModal({ requestImageGeneration(id, params, callback) {
    callback({ type: 0, imageData: 'independent' }); callback({ type: 1 }); } });
  await independent.ImageAIGenerate(isolated.callback);
  assert.deepEqual(isolated.events, [['ready'], ['complete', ['independent']]]);
  assert.deepEqual(d.events, [['ready'], ['complete', []]]);
  await independent.ImageAIGenerate({ onReady() {}, onError() {}, onComplete: undefined });
  process.stdout.write(JSON.stringify({ status: 'pass', scope: 'whole_runtime_JS_custom_model_callback_fixture',
    original_failure_reproduced: true, not_claimed: ['guest_execution', 'actual_AI_model', 'dialog_UI',
      'missing_public_dialog_or_node_graph_functions', 'default_Celia_model'] }) + '\n');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
