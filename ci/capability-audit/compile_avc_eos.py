#!/usr/bin/env python3
"""Compile exact AVC EOS source repair with real product args, in scratch only."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/foundation/multimedia/av_codec/avc_eos'
sys.path.insert(0, str(COMPONENT))
from verify_source import FILE, repaired_source, REVISION
from compile_i18n_error import stage_missing_png_dependency


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', choices=('arm64_virt', 'armv7a_virt', 'x86_64_virt'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    project = root / 'foundation/multimedia/av_codec'
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('AVC compiler check requires exact fixed wrapper source')
    original = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:' + FILE]).decode()
    target = 'obj/foundation/multimedia/av_codec/services/engine/codec/video/avcencoder/avc_encoder/avc_encoder.o'
    cwd = root / 'out' / args.product
    commands = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', target], check=True, capture_output=True, text=True)
    command = shlex.split(commands.stdout.splitlines()[-1])
    if Path(command[0]).name == 'ccache': command.pop(0)
    if Path(command[0]).name != 'clang++' or any(token in command for token in ('&&', ';', '|')):
        raise ValueError('expected exactly one real product clang++ command')
    index = command.index('-c') + 1
    if (cwd / command[index]).resolve() != project / FILE: raise ValueError('wrong AVC wrapper compile source')
    with tempfile.TemporaryDirectory(prefix='qemu-avc-eos-compile-') as directory:
        staged = Path(directory)
        source_dir = Path(FILE).parent
        shutil.copytree(project / source_dir, staged / source_dir)
        candidate = staged / FILE
        candidate.write_text(repaired_source(original))
        object_path = staged / 'avc_encoder.o'
        command[index] = str(candidate)
        command[command.index('-o') + 1] = str(object_path)
        command[command.index('-MF') + 1] = str(staged / 'avc_encoder.d')
        dependency = stage_missing_png_dependency(root, staged, cwd, command)
        subprocess.run(command, cwd=cwd, check=True)
        result = {'status': 'pass', 'product': args.product, 'scope': 'scratch_actual_wrapper_compile_only_not_guest',
                  'first_artifact_behavior_gate_passed': False,
                  'source_revision': REVISION,
                  'source_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
                  'patch_sha256': hashlib.sha256((COMPONENT / '0001-reset-avc-eos-buffer-and-propagate-backend-failure.patch').read_bytes()).hexdigest(),
                  'object_sha256': hashlib.sha256(object_path.read_bytes()).hexdigest(),
                  'compiler_args_sha256': hashlib.sha256(json.dumps(command).encode()).hexdigest(),
                  'scratch_dependency': dependency}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
