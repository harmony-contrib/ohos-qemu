#!/usr/bin/env python3
"""Exercise actual baseline/candidate DRM functions with host boundary doubles."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/device/qemu/display_modes'


def function(text, signature):
    start = text.index(signature + '\n{')
    end = text.index('\n}\n', start) + 3
    return text[start:end]


def run(source_root):
    spec = importlib.util.spec_from_file_location('drm_mode_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    baseline.validate(source_root, require_patched=True)
    harness = (ROOT / 'ci/capability-audit/probes/qemu_display_modes.cpp').read_text()
    signatures = (
        'int32_t DrmCrtc::SetActivieMode(int32_t id)',
        'int32_t DrmDisplay::SetDisplayMode(uint32_t modeId)',
        'int32_t HdiDrmComposition::UpdateMode(std::unique_ptr<DrmModeBlock> &modeBlock)',
    )
    with tempfile.TemporaryDirectory(prefix='actual-qemu-modes-') as temporary:
        owned = Path(temporary)
        for path, _, _ in baseline.FILES:
            destination = owned / baseline.PROJECT / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_root / baseline.PROJECT / path, destination)
        for candidate in (True, False):
            if not candidate:
                subprocess.run(['git', '-C', str(owned), 'apply', '--reverse',
                    str(next(COMPONENT.glob('*.patch')))], check=True)
                if baseline.validate(owned):
                    raise ValueError('reverse patch did not restore actual original source')
                originals = {row[0]: (owned / baseline.PROJECT / row[0]).read_bytes() for row in baseline.FILES}
            extracted = '\n'.join(function((owned / baseline.PROJECT / row[0]).read_text(), signature)
                                  for row, signature in zip(baseline.FILES, signatures))
            cpp = owned / ('candidate.cpp' if candidate else 'original.cpp')
            cpp.write_text(harness.replace('// __ACTUAL_FUNCTIONS__', extracted))
            executable = cpp.with_suffix('')
            argv = ['clang++', '-std=c++17', '-g', '-O1', '-fsanitize=address,undefined',
                    '-fno-omit-frame-pointer', '-Wall', '-Wextra', '-Werror']
            if not candidate:
                argv += ['-DEXPECT_ORIGINAL_FAILURE', '-Wno-unused-function']
            subprocess.run(argv + [str(cpp), '-o', str(executable)], check=True)
            subprocess.run([str(executable)], check=True)
        for _ in range(2):
            subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(owned)], check=True)
        baseline.validate(owned, require_patched=True)
        for relative, _, _ in baseline.FILES:
            path = owned / baseline.PROJECT / relative
            original = path.read_bytes()
            for rejected in (original + b'\n// unknown edit\n', originals[relative]):
                path.write_bytes(rejected)
                before = {row[0]: (owned / baseline.PROJECT / row[0]).read_bytes() for row in baseline.FILES}
                result = subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(owned)],
                                        capture_output=True)
                after = {row[0]: (owned / baseline.PROJECT / row[0]).read_bytes() for row in baseline.FILES}
                assert result.returncode != 0 and after == before
            path.write_bytes(original)
    print('exact source, original negative control, candidate sanitizer boundaries and guarded apply passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    run(parser.parse_args().source_root)
