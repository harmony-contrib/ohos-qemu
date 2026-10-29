#!/usr/bin/env python3
"""Require the fixed full AudioFramework source before the public enum fix."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/audio_framework'
REVISION = '6932fa64335b8272ca4a59de7808ab0d6c9eae7a'
FILES = (('frameworks/js/napi/common/napi_audio_enum.cpp',
          '85d14a90c62d33d36c50518bbc258f83067144fc93677a7dafe4af6203b3dd2b',
          '351b8bdb04cfe637c05643a050e8a964c3c4b09252461d3ded19b2d1504d51d0'),)


def validate(root, require_patched=False):
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    print('DeviceBlockStatus repair present: ' + str(validate(args.source_root, args.require_patched)))
