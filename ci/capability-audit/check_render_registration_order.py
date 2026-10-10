#!/usr/bin/env python3
"""Compile actual critical sections against deterministic host scheduling doubles.

This is not an AppMgr unit-test replacement or packaged Web closure evidence.
The source must already pass the component's exact patched-file verifier.
"""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/ability/ability_runtime/render_attach_registration'


def sections(source):
    start = source.index('int AppMgrServiceInner::StartRenderProcessImpl(')
    end = source.index('\nvoid AppMgrServiceInner::SetRenderStartMsg(', start)
    method = source[start:end]
    spawn = method[method.index('    pid_t pid = 0;'):method.rindex('\n    return 0;')]
    start = source.index('void AppMgrServiceInner::AttachRenderProcess(')
    end = source.index('\nvoid AppMgrServiceInner::SaveBrowserChannel(', start)
    method = source[start:end]
    attach = method[method.index('    if (pid <= 0)'):method.index('    CheckRenderAttachTimeout(')]
    return spawn, attach


def run(root):
    spec = importlib.util.spec_from_file_location('registration_source', COMPONENT / 'verify_source.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    verifier.validate(root, require_patched=True)
    compiler = shutil.which('c++')
    if compiler is None:
        raise RuntimeError('host C++ compiler required')
    relative = Path(verifier.PROJECT) / 'services/appmgr/src/app_mgr_service_inner.cpp'
    harness = (Path(__file__).parent / 'probes/render_registration_order.cpp').read_text()
    with tempfile.TemporaryDirectory(prefix='render-registration-order-') as temporary:
        temporary = Path(temporary)
        baseline = temporary / 'baseline'
        for relative_file, _, _ in verifier.FILES:
            destination = baseline / verifier.PROJECT / relative_file
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / verifier.PROJECT / relative_file, destination)
        subprocess.run(['git', 'apply', '--reverse', str(COMPONENT /
            '0001-serialize-render-publication-and-attachment.patch')], cwd=baseline, check=True)
        assert verifier.validate(baseline) is False
        applied = temporary / 'applied'
        shutil.copytree(baseline, applied)
        apply_argv = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(applied)]
        for _ in range(2):
            subprocess.run(apply_argv, check=True, capture_output=True, text=True)
            assert verifier.validate(applied, require_patched=True) is True
        header = applied / verifier.PROJECT / verifier.FILES[0][0]
        repaired_header = header.read_bytes()
        paths = [applied / verifier.PROJECT / row[0] for row in verifier.FILES]
        for replacement in (repaired_header + b'\n// unknown external edit\n',
                            (baseline / verifier.PROJECT / verifier.FILES[0][0]).read_bytes()):
            header.write_bytes(replacement)
            before = {path: path.read_bytes() for path in paths}
            rejected = subprocess.run(apply_argv, capture_output=True, text=True)
            assert rejected.returncode != 0
            assert before == {path: path.read_bytes() for path in paths}
        print('exact forward/repeat application and unknown/partial preservation passed')
        for fixed, source_root in ((False, baseline), (True, root)):
            spawn, attach = sections((source_root / relative).read_text())
            text = harness.replace('/* ACTUAL_SPAWN_SECTION */', spawn).replace(
                '/* ACTUAL_ATTACH_SECTION */', attach)
            source = temporary / ('fixed.cpp' if fixed else 'baseline.cpp')
            source.write_text(text)
            binary = source.with_suffix('.bin')
            subprocess.run([compiler, '-std=c++17', '-pthread', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                '-DEXPECT_FIXED=' + str(int(fixed)), str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=60)
            print(('patched' if fixed else 'baseline') + ' actual critical-section checks passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    run(parser.parse_args().source_root.resolve())
