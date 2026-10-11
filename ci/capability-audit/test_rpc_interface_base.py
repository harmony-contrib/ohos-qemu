"""Real host NAPI ownership/identity regressions; Binder is an explicit double."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import re

from test_access_token_kernel import patch_sections

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / ('patches/common/foundation/communication/ipc/remote_interface_base/'
                '0001-bind-the-real-remote-interface-base.patch')

SUPPORT = r'''
#include <node_api.h>
#include <array>
#include <atomic>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <string>
#include <cassert>
#define NAPI_ASSERT(env, condition, message) do { if (!(condition)) { \
    napi_throw_error(env, nullptr, message); return nullptr; } } while (false)
static constexpr napi_type_tag REMOTE_INTERFACE_STUB_TAG = {0x67586d35e34947baULL, 0xb4a8f0be52bc1791ULL};
static constexpr napi_type_tag TEST_STUB_TAG = {1, 2}, TEST_PROXY_TAG = {3, 4};
template<class T> using sptr = std::shared_ptr<T>;
struct IRemoteObject {
    bool proxy = false;
    std::string descriptor;
    bool IsProxyObject() const { return proxy; }
};
struct NAPIRemoteObjectHolder {
    sptr<IRemoteObject> target;
    NAPIRemoteObjectHolder(napi_env, const char16_t*, napi_value): target(std::make_shared<IRemoteObject>()) {}
    sptr<IRemoteObject> Get() { return target; }
};
// Only the platform-specific transfer/Binder holder is a double. Host NAPI
// references, callbacks, finalizers, type tags, GC and prototypes are real.
static void RemoteObjectHolderFinalizeCb(napi_env, void *data, void *) {
    delete static_cast<NAPIRemoteObjectHolder *>(data);
}
static void *RemoteObjectDetachCb = nullptr, *RemoteObjectAttachCb = nullptr;
static napi_status napi_coerce_to_native_binding_object(napi_env, napi_value, ...) { return napi_ok; }
enum errorDesc { CHECK_PARAM_ERROR = 401, PROXY_OR_REMOTE_OBJECT_INVALID_ERROR = 1900008 };
struct NapiError {
    napi_value ThrowError(napi_env env, int code) {
        napi_value message, error, number;
        napi_create_string_utf8(env, "native RPC error", NAPI_AUTO_LENGTH, &message);
        napi_create_error(env, nullptr, message, &error);
        napi_create_int32(env, code, &number);
        napi_set_named_property(env, error, "code", number);
        napi_throw(env, error); return nullptr;
    }
};
static NapiError napiErr;
static std::atomic<int> references{0};
static napi_status TrackCreateReference(napi_env env, napi_value value, uint32_t count, napi_ref *result) {
    auto status = napi_create_reference(env, value, count, result);
    if (status == napi_ok) ++references;
    return status;
}
static napi_status TrackDeleteReference(napi_env env, napi_ref reference) {
    auto status = napi_delete_reference(env, reference);
    if (status == napi_ok) --references;
    assert(references >= 0); return status;
}
// Reproduce the pinned engine's observable ACENAPI_TYPETAG property, including
// its true result for a present non-BigInt value. It is not an identity guard.
static napi_status ObservableTag(napi_env env, napi_value object, const napi_type_tag *tag) {
    uint64_t words[] = {tag->lower, tag->upper}; napi_value value;
    auto status = napi_create_bigint_words(env, 0, 2, words, &value);
    return status == napi_ok ? napi_set_named_property(env, object, "ACENAPI_TYPETAG", value) : status;
}
static napi_status CheckObservableTag(napi_env env, napi_value object, const napi_type_tag *tag, bool *result) {
    auto status = napi_has_named_property(env, object, "ACENAPI_TYPETAG", result);
    if (status != napi_ok || !*result) return status;
    napi_value value; napi_valuetype kind;
    status = napi_get_named_property(env, object, "ACENAPI_TYPETAG", &value);
    if (status != napi_ok) return status;
    status = napi_typeof(env, value, &kind);
    if (status != napi_ok || kind != napi_bigint) return status;
    int sign = 0; size_t size = 2; uint64_t words[2] = {};
    status = napi_get_value_bigint_words(env, value, &sign, &size, words);
    if (status == napi_ok && sign == 0 && (size == 1 || size == 2)) {
        *result = words[0] == tag->lower && words[1] == tag->upper;
    }
    return status;
}
static sptr<IRemoteObject> NAPI_ohos_rpc_getNativeRemoteObject(napi_env, napi_value);
static napi_value NativeStubMethod(napi_env, napi_callback_info);
static napi_value NativeProxyMethod(napi_env, napi_callback_info);
#define NAPI_RemoteObject_queryLocalInterface NativeStubMethod
#define NAPI_RemoteObject_getLocalInterface NativeStubMethod
#define NAPI_RemoteObject_sendRequest NativeStubMethod
#define NAPI_RemoteObject_sendMessageRequest NativeStubMethod
#define NAPI_RemoteObject_addDeathRecipient NativeStubMethod
#define NAPI_RemoteObject_registerDeathRecipient NativeStubMethod
#define NAPI_RemoteObject_removeDeathRecipient NativeStubMethod
#define NAPI_RemoteObject_unregisterDeathRecipient NativeStubMethod
#define NAPI_RemoteObject_getInterfaceDescriptor NativeStubMethod
#define NAPI_RemoteObject_getDescriptor NativeStubMethod
#define NAPI_RemoteObject_isObjectDead NativeStubMethod
#define napi_create_reference TrackCreateReference
#define napi_delete_reference TrackDeleteReference
#define napi_type_tag_object ObservableTag
#define napi_check_object_type_tag CheckObservableTag
'''

TAIL = r'''
#undef napi_create_reference
#undef napi_delete_reference
#undef napi_type_tag_object
#undef napi_check_object_type_tag
static napi_value Concrete(napi_env env, napi_callback_info info) {
    size_t argc = 1; napi_value argv[1], self; void *data;
    napi_get_cb_info(env, info, &argc, argv, &self, &data);
    bool proxy = data != nullptr;
    auto holder = new NAPIRemoteObjectHolder(env, u"", self);
    holder->target->proxy = proxy;
    holder->target->descriptor = proxy ? "proxy" : "stub";
    napi_wrap(env, self, holder, RemoteObjectHolderFinalizeCb, nullptr, nullptr);
    napi_type_tag_object(env, self, proxy ? &TEST_PROXY_TAG : &TEST_STUB_TAG);
    return self;
}
static napi_value NativeKindMethod(napi_env env, napi_callback_info info, bool proxy) {
    napi_value self; size_t argc = 6; napi_value argv[6];
    napi_get_cb_info(env, info, &argc, argv, &self, nullptr);
    auto target = NAPI_ohos_rpc_getNativeRemoteObject(env, self);
    if (!target) return napiErr.ThrowError(env, PROXY_OR_REMOTE_OBJECT_INVALID_ERROR);
    assert(target->IsProxyObject() == proxy);
    napi_value result;
    std::string text = target->descriptor + ":" + std::to_string(argc);
    napi_create_string_utf8(env, text.c_str(), NAPI_AUTO_LENGTH, &result);
    return result;
}
static napi_value NativeStubMethod(napi_env env, napi_callback_info info) {
    return NativeKindMethod(env, info, false);
}
static napi_value NativeProxyMethod(napi_env env, napi_callback_info info) {
    return NativeKindMethod(env, info, true);
}
static napi_value Make(napi_env env, napi_callback_info) {
    napi_value exports; napi_create_object(env, &exports);
    const char *names[] = {"queryLocalInterface", "getLocalInterface", "sendRequest", "sendMessageRequest",
        "addDeathRecipient", "registerDeathRecipient", "removeDeathRecipient", "unregisterDeathRecipient",
        "getInterfaceDescriptor", "getDescriptor", "isObjectDead"};
    std::array<napi_property_descriptor, 11> methods{};
    for (int proxy=0; proxy<2; ++proxy) {
        for (size_t i=0; i<11; ++i) methods[i] = {names[i], nullptr,
            proxy ? NativeProxyMethod : NativeStubMethod, nullptr, nullptr, nullptr, napi_default, nullptr};
        napi_value constructor;
        napi_define_class(env, proxy ? "RemoteProxy" : "RemoteObject", NAPI_AUTO_LENGTH,
            Concrete, proxy ? reinterpret_cast<void*>(1) : nullptr, 11, methods.data(), &constructor);
        napi_set_named_property(env, exports, proxy ? "RemoteProxy" : "RemoteObject", constructor);
    }
    std::array<napi_callback, 11> proxies; proxies.fill(NativeProxyMethod);
    return NAPIRemoteInterfaceExport(env, exports, proxies.data(), proxies.size());
}
static napi_value Alias(napi_env env, napi_callback_info info) {
    size_t argc=1; napi_value source, alias; void *wrapped=nullptr;
    napi_get_cb_info(env, info, &argc, &source, nullptr, nullptr);
    napi_unwrap(env, source, &wrapped);
    napi_create_object(env, &alias);
    napi_wrap(env, alias, wrapped, nullptr, nullptr, nullptr);
    ObservableTag(env, alias, &REMOTE_INTERFACE_STUB_TAG);
    return alias;
}
static napi_value Count(napi_env env, napi_callback_info) {
    napi_value result; napi_create_int32(env, references, &result); return result;
}
static napi_value ForeignAlias(napi_env env, napi_callback_info) {
    void *wrapped=nullptr;
    {
        std::lock_guard<std::mutex> lock(remoteInterfaceIdentityMutex);
        for (auto identity : remoteInterfaceIdentities) {
            while (identity != nullptr) {
                if (identity->env != env) { wrapped=identity->holder; break; }
                identity=identity->next;
            }
            if (wrapped != nullptr) break;
        }
    }
    if (wrapped == nullptr) { napi_throw_error(env, nullptr, "live foreign identity required"); return nullptr; }
    napi_value alias; napi_create_object(env, &alias);
    napi_wrap(env, alias, wrapped, nullptr, nullptr, nullptr);
    ObservableTag(env, alias, &REMOTE_INTERFACE_STUB_TAG);
    return alias;
}
static napi_value Init(napi_env env, napi_value exports) {
    for (const auto& entry : {std::pair<const char*, napi_callback>{"make", Make}, {"alias", Alias},
        {"count", Count}, {"foreign", ForeignAlias}}) {
        napi_value function; napi_create_function(env, entry.first, NAPI_AUTO_LENGTH, entry.second, nullptr, &function);
        napi_set_named_property(env, exports, entry.first, function);
    }
    return exports;
}
NAPI_MODULE(NODE_GYP_MODULE_NAME, Init)
'''

SCRIPT = r'''
const assert = require('node:assert/strict');
const addon = require(process.argv[2]);
const rpc = addon.make();
assert.notEqual(rpc.IRemoteObject, rpc.RemoteObject);
assert.notEqual(rpc.IRemoteObject, rpc.RemoteProxy);
for (const concrete of [rpc.RemoteObject, rpc.RemoteProxy]) {
  assert.equal(Object.getPrototypeOf(concrete), rpc.IRemoteObject);
  assert.equal(Object.getPrototypeOf(concrete.prototype), rpc.IRemoteObject.prototype);
  assert.equal(new concrete() instanceof rpc.IRemoteObject, true);
}
class Derived extends rpc.IRemoteObject {}
let derived = new Derived();
assert.equal(derived.getDescriptor(), ':0');
assert.equal(addon.count(), 1); // One weak identity; method callbacks have no per-realm data/refs.
for (const [object, prefix] of [[new rpc.RemoteObject(), 'stub'], [new rpc.RemoteProxy(), 'proxy'], [derived, '']]) {
  for (const key of Object.getOwnPropertyNames(rpc.IRemoteObject.prototype).filter(key => key !== 'constructor')) {
    const method = rpc.IRemoteObject.prototype[key];
    for (let argc = 0; argc <= 5; argc++) assert.equal(method.call(object, ...Array(argc).fill(7)), prefix + ':' + argc);
  }
}
const descriptor = rpc.IRemoteObject.prototype.getDescriptor;
for (const fake of [{}, Object.create(rpc.IRemoteObject.prototype), addon.alias(derived)]) {
  for (const tag of [derived.ACENAPI_TYPETAG, '', -1n, 1n << 250n]) {
    fake.ACENAPI_TYPETAG = tag;
    assert.throws(() => descriptor.call(fake), error => error.code === 1900008);
  }
}
// A real proxy carrying a copied observable tag must remain a proxy. In
// particular it must never be interpreted as a NAPIRemoteObjectHolder.
const proxy = new rpc.RemoteProxy();
proxy.ACENAPI_TYPETAG = derived.ACENAPI_TYPETAG;
assert.equal(descriptor.call(proxy), 'proxy:0');
assert.throws(() => new Derived(1), error => error.code === 401);
const alias = addon.alias(derived);
async function gcUntil(count) {
  for (let i=0; i<100; ++i) {
    global.gc(); await new Promise(resolve => setImmediate(resolve));
    if (addon.count() === count) return;
  }
  assert.equal(addon.count(), count);
}
(async () => {
  // An actual second NAPI environment must reject a wrapped pointer/tag from
  // this live environment before touching its weak reference or holder.
  const { Worker } = require('node:worker_threads');
  const worker = new Worker(`
    const {parentPort,workerData}=require('node:worker_threads');
    const assert=require('node:assert/strict');
    const addon=require(workerData); const rpc=addon.make();
    const foreign=addon.foreign();
    assert.throws(() => rpc.IRemoteObject.prototype.getDescriptor.call(foreign),
      error => error.code===1900008);
    parentPort.postMessage('foreign identity rejected');
  `, {eval:true, workerData:process.argv[2]});
  await new Promise((resolve,reject) => {
    let observed=false;
    worker.on('message', value => { assert.equal(value, 'foreign identity rejected'); observed=true; });
    worker.on('error', reject);
    worker.on('exit', code => code===0 && observed ? resolve() : reject(new Error('foreign-env test incomplete')));
  });
  derived = null;
  await gcUntil(0);
  assert.throws(() => descriptor.call(alias), error => error.code === 1900008);
  // Drop the owning module/class and force real GC while the extracted callable
  // remains live. V8 may retain its creation context; do not prescribe which
  // unreachable class members it must collect before releasing this function.
  let saved;
  (() => { const temporary = addon.make(); saved = temporary.IRemoteObject.prototype.getDescriptor; })();
  for (let i=0; i<20; ++i) { global.gc(); await new Promise(resolve => setImmediate(resolve)); }
  assert.equal(addon.count(), 0);
  assert.equal(saved.call(new rpc.RemoteObject()), 'stub:0');
  saved = null;
  await gcUntil(0);
  for (let i=0; i<64; ++i) { (() => { const temporary=addon.make(); new temporary.IRemoteObject(); })(); }
  await gcUntil(0);
  process.stdout.write('real host NAPI identity/proxy/argument/GC regressions passed\n');
})().catch(error => { console.error(error); process.exitCode=1; });
'''


class RpcInterfaceBaseTests(unittest.TestCase):
    def test_exact_component_files_and_pre_gn_hook(self):
        sections = patch_sections(PATCH)
        self.assertEqual(set(sections), {
            'foundation/communication/ipc/ipc/native/src/napi_common/source/napi_remote_object.cpp',
            'foundation/communication/ipc/ipc/native/src/napi/src/napi_rpc_native_module.cpp'})
        source = PATCH.read_text()
        self.assertIn('identity->holder == wrapped && identity->env == env', source)
        self.assertIn('napi_strict_equals(env, actual, object, &equal)', source)
        self.assertIn('napi_create_reference(env, thisVar, 0', source)
        self.assertNotIn('"IRemoteObject", stub)', source)
        self.assertNotIn('"IRemoteObject", proxy)', source)
        script = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('bash "${RPC_INTERFACE_BASE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"', script)

    def test_actual_native_callback_tables_match_every_public_base_method(self):
        sections = patch_sections(PATCH)
        object_source = '\n'.join('\n'.join(hunk[2]) for hunk in sections[
            'foundation/communication/ipc/ipc/native/src/napi_common/source/napi_remote_object.cpp'])
        module_source = '\n'.join('\n'.join(hunk[2]) for hunk in sections[
            'foundation/communication/ipc/ipc/native/src/napi/src/napi_rpc_native_module.cpp'])
        exported = object_source.split('napi_value NAPIRemoteInterfaceExport(', 1)[1]
        names = re.findall(r'"(\w+)"', exported.split('names[] = {', 1)[1].split('};', 1)[0])
        stubs = re.findall(r'NAPI_RemoteObject_(\w+)', exported.split('stubMethods[] = {', 1)[1].split('};', 1)[0])
        proxies = re.findall(r'NAPI_RemoteProxy_(\w+)', module_source.split('proxyMethods[] = {', 1)[1].split('};', 1)[0])
        self.assertEqual(names, stubs)
        self.assertEqual(names, proxies)
        self.assertEqual(len(names), 11)
        self.assertEqual(len(set(names)), 11)
        self.assertIn('proxyMethods[index] != nullptr', exported)
        self.assertIn('methods[index].proxy == proxyMethods[index]', exported)
        self.assertIn('static std::array<RemoteInterfaceMethod, count> methods{};', exported)
        self.assertNotIn('napi_create_reference', exported)
        self.assertNotIn('napi_add_finalizer', exported)
        self.assertNotIn('new ', exported)

    def test_real_host_napi_extracted_lifetimes_and_observable_tag_forgery(self):
        if sys.platform != 'darwin':
            self.skipTest('this actual host NAPI fixture uses the macOS bundled Node toolchain')
        node_home = Path('/Applications/DevEco-Studio.app/Contents/tools/node')
        self.assertTrue((node_home / 'include/node/node_api.h').is_file())
        compiler = subprocess.check_output(['xcrun', '--find', 'clang++'], text=True).strip()
        self.assertTrue(Path(compiler).is_file())
        host_sdk = Path(subprocess.check_output(['xcrun', '--show-sdk-path'], text=True).strip())
        self.assertTrue((host_sdk / 'usr/include/c++/v1/array').is_file())
        sections = patch_sections(PATCH)
        blocks = ['\n'.join(hunk[2]) for hunk in sections[
            'foundation/communication/ipc/ipc/native/src/napi_common/source/napi_remote_object.cpp']]
        identity = next(block for block in blocks if 'struct RemoteInterfaceIdentity {' in block)
        identity = identity[identity.index('struct RemoteInterfaceIdentity {'):].split(
            '\nnapi_value RemoteObject_JS_Constructor(', 1)[0]
        guard = next(block for block in blocks if 'bool interfaceStub = false;' in block)
        guard = guard[guard.index('    if (object != nullptr) {'):].split(
            '\n        napi_value global = nullptr;', 1)[0]
        helpers = next(block for block in blocks if 'struct RemoteInterfaceMethod {' in block)
        helpers = helpers[helpers.index('struct RemoteInterfaceMethod {'):].split('\nEXTERN_C_START', 1)[0]
        export = next(block for block in blocks if 'napi_value NAPIRemoteInterfaceExport(' in block)
        export = export[export.index('napi_value NAPIRemoteInterfaceExport('):].split('\nEXTERN_C_END', 1)[0]
        get_native = ('static sptr<IRemoteObject> NAPI_ohos_rpc_getNativeRemoteObject(napi_env env, napi_value object) {\n' +
            guard + r'''
        // Concrete transport-kind recognition is a double using real Node
        // private tags; the candidate registry/weak-identity guard above is exact.
        bool stub=false, proxy=false;
        ::napi_check_object_type_tag(env, object, &TEST_STUB_TAG, &stub);
        ::napi_check_object_type_tag(env, object, &TEST_PROXY_TAG, &proxy);
        if (stub || proxy) {
            void *wrapped=nullptr;
            if (napi_unwrap(env, object, &wrapped)==napi_ok && wrapped) {
                return static_cast<NAPIRemoteObjectHolder*>(wrapped)->Get();
            }
        }
    }
    return nullptr;
}
''')
        # Temporarily undo the tag double only around concrete-kind recognition.
        get_native = get_native.replace('        bool stub=false, proxy=false;',
            '#undef napi_check_object_type_tag\n        bool stub=false, proxy=false;').replace(
            '    return nullptr;\n}', '    return nullptr;\n}\n#define napi_check_object_type_tag CheckObservableTag')
        with tempfile.TemporaryDirectory(prefix='rpc-host-napi-') as directory:
            root = Path(directory)
            source, addon, script = root / 'probe.cpp', root / 'probe.node', root / 'probe.js'
            source.write_text(SUPPORT + identity + get_native + helpers + export + TAIL)
            script.write_text(SCRIPT)
            compiled = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-parameter', '-shared', '-undefined', 'dynamic_lookup',
                '-isysroot', str(host_sdk), '-isystem', str(host_sdk / 'usr/include/c++/v1'),
                '-I' + str(node_home / 'include/node'), str(source), '-o', str(addon)],
                capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            undefined = subprocess.check_output(['nm', '-u', str(addon)], text=True)
            exported = subprocess.check_output(['nm', '-gU', str(node_home / 'bin/node')], text=True)
            missing = [line.strip() for line in undefined.splitlines() if line.strip().startswith(
                ('_napi_', '_node_api_')) and line.strip() not in exported]
            self.assertEqual(missing, [], 'host Node must supply every used NAPI symbol')
            result = subprocess.run([str(node_home / 'bin/node'), '--expose-gc', str(script), str(addon)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + '\n'.join(result.stderr.splitlines()[-35:]))
            self.assertIn('regressions passed', result.stdout)


if __name__ == '__main__': unittest.main()
