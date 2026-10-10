#!/usr/bin/env python3
"""Exercise the exact candidate constructor in host Node N-API, NOT Ark/IPC."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/ability/ability_runtime/completion_handler'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(source, node_root, output):
    if output.exists():
        raise ValueError('fresh evidence required')
    spec = importlib.util.spec_from_file_location('completion_handler_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if digest(source) != baseline.FILES[0][2]:
        raise ValueError('requires exact reviewed candidate source')
    data = source.read_text()
    start = data.index('static napi_value CompletionHandlerConstructor(')
    end = data.index('\nstatic napi_value CompletionHandlerForAbilityStartCallbackInit(', start)
    constructor = data[start:end]
    with tempfile.TemporaryDirectory(prefix='completion-handler-napi-') as directory:
        work = Path(directory)
        cpp = work / 'constructor.cpp'
        cpp.write_text('''#include <node_api.h>
#define NAPI_CALL(env, expression) do { if ((expression) != napi_ok) return nullptr; } while (0)
''' + constructor + '''
static napi_value Init(napi_env env, napi_value exports)
{
    napi_value constructor = nullptr;
    NAPI_CALL(env, napi_define_class(env, "CompletionHandlerForAbilityStartCallback", NAPI_AUTO_LENGTH,
        CompletionHandlerConstructor, nullptr, 0, nullptr, &constructor));
    NAPI_CALL(env, napi_set_named_property(env, exports, "CompletionHandlerForAbilityStartCallback", constructor));
    return exports;
}
NAPI_MODULE(NODE_GYP_MODULE_NAME, Init)
''')
        addon = work / 'constructor.node'
        compile_command = ['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                           '-I', str(node_root / 'include/node'), str(cpp), '-o', str(addon)]
        import sys
        if sys.platform == 'darwin':
            compile_command += ['-undefined', 'dynamic_lookup']
        subprocess.run(compile_command, check=True, capture_output=True)
        script = work / 'boundary.cjs'
        script.write_text('''const assert = require('node:assert/strict');
const {CompletionHandlerForAbilityStartCallback: Handler} = require('./constructor.node');
assert.equal(typeof Handler, 'function');
assert.equal(Handler.name, 'CompletionHandlerForAbilityStartCallback');
assert.throws(() => Handler(), TypeError);
assert.throws(() => Handler.call({}), TypeError);
const first = new Handler();
const second = new Handler();
assert.ok(first instanceof Handler);
assert.equal(first.onRequestSuccess, undefined);
assert.equal(first.onRequestFailure, undefined);
assert.notEqual(first, second);
let called = [];
first.onRequestSuccess = name => called.push(['success', name]);
first.onRequestFailure = (name, code, message) => called.push(['failure', name, code, message]);
first.onRequestSuccess('bundle#module#ability');
first.onRequestFailure('', 1, 'cancelled');
assert.deepEqual(called, [['success', 'bundle#module#ability'], ['failure', '', 1, 'cancelled']]);
assert.equal(second.onRequestSuccess, undefined);
assert.equal(second.onRequestFailure, undefined);
delete first.onRequestSuccess;
assert.equal(first.onRequestSuccess, undefined);
class Child extends Handler { marker = 7; }
const child = new Child();
assert.ok(child instanceof Handler && child instanceof Child);
assert.equal(child.marker, 7);
for (let i = 0; i < 10000; ++i) {
    const item = new Handler();
    item.onRequestSuccess = () => i;
    assert.equal(item.onRequestSuccess(), i);
    if (i % 1000 === 0) global.gc();
}
console.log('PASS constructor/new-only/optional-callbacks/instance-isolation/subclass/10000-GC-cycles');
''')
        result = subprocess.run([str(node_root / 'bin/node'), '--expose-gc', str(script)],
                                check=True, capture_output=True, text=True)
        report = dict(status='pass', scope='exact_constructor_host_Node_NAPI_NOT_Ark_or_service_IPC',
            source_sha256=digest(source), constructor_sha256=hashlib.sha256(constructor.encode()).hexdigest(),
            harness_sha256=digest(cpp), test_sha256=digest(script),
            node_version=subprocess.check_output([str(node_root / 'bin/node'), '--version'], text=True).strip(),
            node_sha256=digest(node_root / 'bin/node'), compiler_command=compile_command,
            output=result.stdout.strip(), first_artifact_behavior_gate_passed=False)
    if digest(source) != baseline.FILES[0][2]:
        raise ValueError('candidate changed during test')
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-source', type=Path, required=True)
    parser.add_argument('--node-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.candidate_source, args.node_root, args.output)))
