#!/usr/bin/env python3
"""Require the complete known AudioHaptic lifecycle source state."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/player_framework'
REVISION = '3d3b1231db27561e8978652d7ae867c12f488d9a'
FILES = (('frameworks/native/audio_haptic/audio_haptic_sound_normal_impl.cpp',
  'cd42f8c73e9c0bf96058b3b936f540203a8d92e55dba6a264829e4994d6e4ff7',
  '056a94964b725406c4a9b57e41cfcb7c7f047ff1cc741d439e6a5917fa9cf4aa'),
 ('frameworks/native/audio_haptic/audio_haptic_player_impl.cpp',
  'a6198066e31ce68afbdd131975b8c03515033aa09109a4af3b68aae945f8cf75',
  '894081f3ded7e729c0a630c9c42979485fdfcd2f5169a106074a132b4cec9db6'))


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('AudioHaptic lifecycle repair present: ' + str(validate(args.source_root, args.require_patched)))
