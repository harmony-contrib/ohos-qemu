#!/usr/bin/env python3
"""Scratch-compile DSP with each real product's AudioSuite C++ flags (not full GN)."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/foundation/multimedia/audio_framework/audio_suite_dsp'
sys.path.insert(0, str(COMPONENT))
from apply import REVISION, HEADER_HASH
from compile_i18n_error import stage_missing_png_dependency


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', choices=('arm64_virt', 'armv7a_virt', 'x86_64_virt'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    project = root / 'foundation/multimedia/audio_framework'
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('DSP compile check requires fixed 7.0 AudioSuite source')
    header = project / 'services/audio_suite/client/utils/include/imedia_api.h'
    if hashlib.sha256(header.read_bytes()).hexdigest() != HEADER_HASH:
        raise ValueError('primary DSP ABI header hash changed')
    cwd = root / 'out' / args.product
    targets = [('obj/foundation/multimedia/audio_framework/frameworks/native/ohaudiosuite/ohaudiosuite/OHAudioSuiteEngine.o',
                'OHAudioSuiteEngine.cpp'),
               ('obj/foundation/multimedia/audio_framework/services/audio_suite/client/manager/src/audio_suite/audio_suite_client_download_manager_stub.o',
                'audio_suite_client_download_manager_stub.cpp')]
    # Older ARM32/x86_64 output graphs disable AudioSuite and have no public
    # engine source at all. Its real framework stub supplies compiler flags
    # only; compiling this DSP must not be reported as enabling that graph.
    for target, expected_source in targets:
        result = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
            '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', target], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            break
    else:
        raise ValueError('no known actual AudioSuite compiler command: ' + result.stderr)
    command = shlex.split(result.stdout.splitlines()[-1])
    if Path(command[0]).name == 'ccache':
        command.pop(0)
    if Path(command[0]).name != 'clang++' or any(token in command for token in ('&&', ';', '|')):
        raise ValueError('expected one real product clang++ command')
    index = command.index('-c') + 1
    if (cwd / command[index]).resolve().name != expected_source:
        raise ValueError('wrong actual product AudioSuite compile command')
    candidate = COMPONENT / 'files/qemu_audio_suite_dsp.cpp'
    with tempfile.TemporaryDirectory(prefix='qemu-audiosuite-dsp-compile-') as directory:
        staged = Path(directory)
        object_path = staged / 'qemu_audio_suite_dsp.o'
        command[index] = str(candidate)
        command[command.index('-o') + 1] = str(object_path)
        command[command.index('-MF') + 1] = str(staged / 'qemu_audio_suite_dsp.d')
        command += ['-I' + str(header.parent), '-Wall', '-Wextra', '-Werror']
        dependency = stage_missing_png_dependency(root, staged, cwd, command)
        subprocess.run(command, cwd=cwd, check=True)
        evidence = {'status': 'pass', 'product': args.product,
                    'scope': 'actual_product_compiler_flags_scratch_DSP_object_only_not_full_GN_or_guest',
                    'first_artifact_behavior_gate_passed': False,
                    'source_revision': REVISION, 'abi_header_sha256': HEADER_HASH,
                    'compiler_template_target': target,
                    'template_is_disabled_framework_stub': expected_source.endswith('_stub.cpp'),
                    'source_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
                    'object_sha256': hashlib.sha256(object_path.read_bytes()).hexdigest(),
                    'compiler_args_sha256': hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                    'scratch_dependency': dependency}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
