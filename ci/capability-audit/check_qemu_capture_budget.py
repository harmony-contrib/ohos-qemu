#!/usr/bin/env python3
"""Source-assisted exact-state, GN predicate and real Future boundary checks.

Uses actual pinned Future/DropLock implementations, with PixelMap/callback/log
dependencies substituted on the host. This is NOT IPC, rendering or guest proof.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/window/window_manager/capture_budget'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(source_root, output):
    if output.exists():
        raise ValueError('fresh evidence required')
    spec = importlib.util.spec_from_file_location('capture_budget_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if baseline.validate(source_root):
        raise ValueError('requires pristine pinned inputs')
    source = source_root / baseline.PROJECT
    evidence = {'status': 'fail', 'scope': 'host_source_boundaries_NOT_IPC_or_guest',
                'first_artifact_behavior_gate_passed': False, 'checks': [], 'inputs': {}}
    for path in [Path(__file__), *COMPONENT.glob('*.py'), *COMPONENT.glob('*.patch'),
                 COMPONENT / 'apply.sh', Path(__file__).parent / 'fixtures/capture_budget/boundary.cpp']:
        evidence['inputs'][str(path)] = digest(path)
    with tempfile.TemporaryDirectory(prefix='capture-budget-check-') as directory:
        work = Path(directory)
        staged = work / 'source'
        for relative, _, _ in baseline.FILES:
            dest = staged / baseline.PROJECT / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, dest)
        command = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(staged)]
        for _ in range(2):
            subprocess.run(command, check=True, capture_output=True)
        baseline.validate(staged, require_patched=True)
        evidence['checks'].append('exact_apply_and_idempotence')
        originals = {staged / baseline.PROJECT / relative: (source / relative).read_bytes()
                     for relative, _, _ in baseline.FILES}
        repaired = {path: path.read_bytes() for path in originals}
        for kind in ('unknown', 'partial'):
            first = next(iter(originals))
            first.write_bytes(repaired[first] + b'\n# unrelated\n' if kind == 'unknown' else originals[first])
            before = {path: path.read_bytes() for path in originals}
            result = subprocess.run(command, capture_output=True)
            assert result.returncode != 0, kind
            assert before == {path: path.read_bytes() for path in originals}, kind
            for path, data in repaired.items():
                path.write_bytes(data)
            evidence['checks'].append(kind + '_preserved')
        cpp = (staged / baseline.PROJECT / baseline.FILES[1][0]).read_text()
        start = cpp.index('#ifdef WM_QEMU_SOFTWARE_CAPTURE\n')
        end = cpp.index('#endif', start) + len('#endif')
        (work / 'budget.inc').write_text(cpp[start:end] + '\n')
        headers = work / 'headers'
        headers.mkdir()
        for name in ('future.h', 'surface_capture_future.h', 'dms_global_mutex.h'):
            path = source / 'utils/include' / name
            evidence['inputs'][str(path)] = digest(path)
            shutil.copy2(path, headers / name)
        stubs = {
            'hilog/log.h': '#pragma once\n',
            'window_manager_hilog.h': '#pragma once\n#define TLOGE(...) ((void)0)\n#define TLOGD(...) ((void)0)\n',
            'pixel_map.h': '#pragma once\n#include <memory>\n#include <vector>\nnamespace OHOS::Media { struct PixelMap { int marker = 42; }; }\n',
            'transaction/rs_render_service_client.h': '''#pragma once
#include "pixel_map.h"
namespace OHOS::Rosen {
enum class CaptureError { CAPTURE_OK, INJECTED_FAILURE };
class SurfaceCaptureCallback {
public:
    virtual ~SurfaceCaptureCallback() = default;
    virtual void OnSurfaceCapture(std::shared_ptr<Media::PixelMap>) = 0;
    virtual void OnSurfaceCaptureHDR(std::shared_ptr<Media::PixelMap>, std::shared_ptr<Media::PixelMap>) = 0;
    virtual void OnSurfaceCaptureWithErrorCode(std::shared_ptr<Media::PixelMap>,
        std::shared_ptr<Media::PixelMap>, CaptureError) = 0;
};
}
''',
        }
        for name, data in stubs.items():
            path = headers / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
        for qemu in (False, True):
            binary = work / ('qemu' if qemu else 'hardware')
            command = ['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                       '-I', str(headers), '-I', str(work)]
            if qemu:
                command.append('-DWM_QEMU_SOFTWARE_CAPTURE')
            command += [str(Path(__file__).parent / 'fixtures/capture_budget/boundary.cpp'), '-o', str(binary)]
            subprocess.run(command, check=True, capture_output=True)
            result = subprocess.run([str(binary), '10000' if qemu else '2000'],
                                    check=True, capture_output=True, text=True, timeout=40)
            evidence['checks'].append({'branch': binary.name, 'result': result.stdout.strip()})
        # Execute the exact added GN product selection, not a Python reimplementation.
        gn = source_root / 'prebuilts/build-tools/linux-x86/bin/gn'
        build_text = (staged / baseline.PROJECT / baseline.FILES[0][0]).read_text()
        start = build_text.index('  if (product_name == "arm64_virt"')
        end = build_text.index('\n  }', start) + len('\n  }')
        predicate = build_text[start:end]
        gnroot = work / 'gn'
        gnroot.mkdir()
        (gnroot / '.gn').write_text('buildconfig = "//config.gn"\n')
        (gnroot / 'config.gn').write_text('set_default_toolchain("//:host")\n')
        for product in ('arm64_virt', 'armv7a_virt', 'x86_64_virt', 'rk3568', 'dayu200', 'not_qemu'):
            expected = 'true' if product in ('arm64_virt', 'armv7a_virt', 'x86_64_virt') else 'false'
            (gnroot / 'BUILD.gn').write_text('product_name = "' + product + '"\ndefines = []\n' + predicate +
                '\nassert((defines == [ "WM_QEMU_SOFTWARE_CAPTURE" ]) == ' + expected + ')\n' +
                'toolchain("host") { tool("stamp") { command = "touch {{output}}" } }\ngroup("all") {}\n')
            subprocess.run([str(gn), 'gen', str(gnroot / 'out')], cwd=gnroot,
                           check=True, capture_output=True)
            evidence['checks'].append('actual_GN_predicate:' + product)
    for path, expected in evidence['inputs'].items():
        assert digest(Path(path)) == expected, 'input changed during check: ' + path
    assert not baseline.validate(source_root)
    evidence['status'] = 'pass'
    output.write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.source_root, args.output)))
