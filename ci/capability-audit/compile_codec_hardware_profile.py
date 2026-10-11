#!/usr/bin/env python3
"""Compile exact QEMU HCS configuration in scratch, never guest codec proof."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/vendor/ohemu/codec_hardware_profile'
spec = importlib.util.spec_from_file_location('codec_profile_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


def sha(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular HCS/tool input required: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    source = args.source_root.resolve()
    report = {'status': 'fail', 'scope': 'exact_QEMU_HCS_HCB_compile_ONLY_NOT_guest_or_six_package_gate',
              'first_artifact_behavior_gate_passed': False, 'commands': [], 'failures': []}
    base = source / 'vendor/ohemu/virt/hdf_config/uhdf'
    tool = source / 'drivers/hdf_core/adapter/khdf/linux/hc_gen_build/hc-gen'
    report['source_revision'] = baseline.REVISION
    original = {str(path.relative_to(base)): sha(path) for path in sorted(base.rglob('*')) if path.is_file()}
    report['source_inputs_sha256'] = original
    report['hc_gen_sha256'] = sha(tool)
    report['component_sha256'] = {str(path.relative_to(COMPONENT)): sha(path)
                                for path in sorted(COMPONENT.iterdir()) if path.is_file()}
    try:
        if baseline.validate(source):
            raise ValueError('compile diagnostic requires exact original source, not a modified shared build')
        with tempfile.TemporaryDirectory(prefix='codec-hardware-profile-') as directory:
            root = Path(directory)
            staged = root / 'vendor/ohemu/virt/hdf_config/uhdf'
            shutil.copytree(base, staged)
            for iteration in (1, 2):
                argv = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)]
                result = subprocess.run(argv, capture_output=True, text=True)
                report['commands'].append({'iteration': iteration, 'argv': argv,
                    'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
                result.check_returncode()
            baseline.validate(root, True)
            report['patched_inputs_sha256'] = {relative: sha(root / baseline.PROJECT / relative)
                                              for relative, _, _ in baseline.FILES}
            report['compiled'] = []
            for source_path in [staged / 'hdf.hcs',
                                *(staged / 'media_codec' / Path(relative).name for relative, _, _ in baseline.FILES)]:
                name = source_path.stem
                binary = root / (name + '.hcb')
                argv = [str(tool), '-b', '-o', str(binary), str(source_path)]
                result = subprocess.run(argv, capture_output=True, text=True)
                report['commands'].append({'argv': argv, 'exit_code': result.returncode,
                                          'stdout': result.stdout, 'stderr': result.stderr})
                result.check_returncode()
                recovered = root / (name + '-decompiled.d.hcs')
                # The pinned decompiler strips the requested suffix and
                # appends .d.hcs, as its real generator/tests specify.
                argv = [str(tool), '-d', '-o', str(root / (name + '-decompiled.hcs')), str(binary)]
                result = subprocess.run(argv, capture_output=True, text=True)
                report['commands'].append({'argv': argv, 'exit_code': result.returncode,
                                          'stdout': result.stdout, 'stderr': result.stderr})
                result.check_returncode()
                content = recovered.read_text()
                if any(token in content for token in ('OMX.rk.video_', 'rk.video_', 'HDF_video_hw_',
                                                       'codec.avc.hardware', 'codec.hevc.hardware')):
                    raise ValueError('actual HCB still contains false hardware video advertisements')
                report['compiled'].append({'source': str(source_path.relative_to(staged)),
                    'hcb_sha256': sha(binary), 'hcb_bytes': binary.stat().st_size,
                    'decompiled_sha256': sha(recovered), 'decompiled': content})
        report['status'] = 'pass'
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        report['failures'].append(str(error))
    current = {str(path.relative_to(base)): sha(path) for path in sorted(base.rglob('*')) if path.is_file()}
    report['inputs_unchanged'] = current == original and sha(tool) == report['hc_gen_sha256']
    if not report['inputs_unchanged']:
        report['status'] = 'fail'
        report['failures'].append('original HCS/tool inputs changed during scratch compilation')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'inputs_unchanged', 'failures')}))
    raise SystemExit(0 if report['status'] == 'pass' else 1)
