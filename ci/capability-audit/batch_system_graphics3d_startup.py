#!/usr/bin/env python3
"""Execute fixed-source scene startup boundaries; no guest rendering is claimed."""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FIXTURE = HERE / 'fixtures/batch_system/graphics3d_startup'
COMPONENT = ROOT / 'patches/common/foundation/graphic/graphic_3d/scene_startup'
PATCH = COMPONENT / '0001-retry-real-scene-plugins-and-report-engine-init-failures.patch'
ADAPTER = 'foundation/graphic/graphic_3d/3d_scene_adapter/src/scene_adapter.cpp'
JSCONTEXT = 'foundation/graphic/graphic_3d/kits/js/src/RenderContextJS.cpp'
BEFORE_FAILURES = ['missing_export_retry', 'preloaded_engine',
                   'plugin_retry', 'uid_failure', 'init_engine_factory', 'init_render_init', 'init_retry']
AFTER_CASES = BEFORE_FAILURES + ['missing_library_global', 'plugin_once', 'shutdown_reload', 'init_good', 'init_cached'] + [
    'init_' + value for value in ('queue_1', 'queue_2', 'queue_3', 'register_engine', 'register_io',
                                'register_release', 'check_schedule', 'init_schedule',
                                'engine_instance', 'class_factory', 'render_instance', 'metadata',
                                'resources', 'application', 'application_init', 'scene_context',
                                'scene_manager', 'queue_property')]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(root):
    meta = json.loads((FIXTURE / 'provenance.json').read_text())
    for row in meta['files']:
        data = gzip.decompress(base64.b64decode((FIXTURE / row['fixture']).read_bytes()))
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('fixed graphics source fixture changed')
        target = root / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return meta


def extract(text, start, end):
    first = text.index(start)
    last = text.index(end, first + len(start))
    return text[first:last]


def run_command(argv, log):
    proc = subprocess.run(argv, capture_output=True, text=True)
    log.write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise ValueError('compilation failed: ' + str(log))


def build(root, cxx):
    text = (root / ADAPTER).read_text()
    parts = [extract(text, 'template <typename T>\nbool LoadFunc(', 'inline SCENE_NS::IEcsContext*'),
             extract(text, 'bool SceneAdapter::LoadEngineLib()', 'void SceneAdapter::SetSceneObj('),
             extract(text, 'bool SceneAdapter::LoadPluginsAndInit()', 'void SceneAdapter::OnWindowChange('),
             extract(text, 'void SceneAdapter::ShutdownPluginRegistry()', 'void SceneAdapter::PropSync()'),
             extract(text, 'bool SceneAdapter::LoadPluginByUid(', 'CORE_NS::IEcs::Ptr SceneAdapter::GetEcs()')]
    unit = root / 'actual_adapter_functions.inc'
    unit.write_text('\n'.join(parts))
    selected = root / 'selected.so'
    output = root / 'startup_boundaries'
    flags = ['-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread', '-g',
             '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-I' + str(root), '-I' + str(HERE)]
    library_flag = '-dynamiclib' if platform.system() == 'Darwin' else '-shared'
    builds = []
    for name, extra in [('good', []), ('missing_export', ['-DBATCH_GRAPHICS_MISSING_EXPORT'])]:
        target = root / (name + '.so')
        argv = [cxx] + flags + [library_flag, '-fPIC'] + extra + [
            str(HERE / 'batch_system_graphics3d_test_library.cpp'), '-o', str(target)]
        run_command(argv, root / (name + '-compile.log'))
        builds.append(dict(argv=argv, sha256=digest(target)))
    argv = [cxx] + flags + ['-DLIB_ENGINE_CORE=' + str(selected.with_suffix('')),
                           str(HERE / 'batch_system_graphics3d_startup_harness.cpp'), '-o', str(output)]
    if platform.system() != 'Darwin':
        argv.append('-ldl')
    run_command(argv, root / 'host-compile.log')
    builds.append(dict(argv=argv, sha256=digest(output), extracted_sha256=digest(unit)))
    return output, selected, builds


def run(output, cxx='c++'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C',
               ASAN_OPTIONS=f'detect_leaks={int(platform.system() != "Darwin")}:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1')
    rows = []
    build_rows = []
    for state, cases in [('before', BEFORE_FAILURES), ('after', AFTER_CASES)]:
        root = output / state
        provenance = prepare(root)
        if state == 'after':
            subprocess.run(['git', '-C', str(root), 'apply', str(PATCH)], check=True)
        binary, selected, builds = build(root, cxx)
        build_rows.append(dict(state=state, builds=builds))
        for case in cases:
            if selected.exists():
                selected.unlink()
            if case != 'missing_library_global':
                shutil.copyfile(root / ('missing_export.so' if case == 'missing_export_retry' else 'good.so'), selected)
            proc = subprocess.run([str(binary), case, str(selected), str(root / 'good.so'),
                                   str(root / 'missing_export.so')], capture_output=True,
                                  text=True, env=env, timeout=20)
            (root / (case + '.log')).write_text(proc.stdout + proc.stderr)
            rows.append(dict(state=state, scenario=case, exit_code=proc.returncode))
            if state == 'before' and (proc.returncode == 0 or not proc.stderr.startswith(case + ': ')):
                raise ValueError('baseline did not reach expected assertion: ' + case)
            if state == 'after' and proc.returncode:
                raise ValueError('patched source boundary failed: ' + case)
    patched = (output / 'after' / JSCONTEXT).read_text()
    scene = extract(patched, 'napi_value RenderContextJS::CreateScene(', 'napi_value RenderContextJS::RegisterResourcePath(')
    if not scene.index('if (!sceneManager)') < scene.index('AcquireJsQueue(env)'):
        raise ValueError('scene manager failure must occur before acquiring a JS queue reference')
    result = dict(status='pass_host_graphics3d_startup_boundaries', provenance=provenance,
                  environment=dict(platform=platform.platform(), locale='C',
                                   compiler=subprocess.check_output([cxx, '--version'], text=True).splitlines()[0]),
                  patch_sha256=digest(PATCH), builds=build_rows, scenarios=rows,
                  js_queue_boundary='fixed-source ordering check only; no NAPI execution',
                  runtime_tested=False, requirements_closed=0, first_artifact_behavior_gate_passed=False,
                  limitations='Actual loader/initialization functions executed with test ABI shims; '
                              'real host dlopen/dlsym and failure/retry exercised. Test DSO never enters a '
                              'product image. Official GN translation units, real plugin registry, renderer, '
                              'Scene.load and guest lifetime remain to validate.')
    (output / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cxx', default='c++')
    args = parser.parse_args()
    result = run(args.output, args.cxx)
    print(json.dumps(dict(status=result['status'], cases=len(result['scenarios']))))
