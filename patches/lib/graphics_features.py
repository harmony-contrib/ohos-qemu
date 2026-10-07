#!/usr/bin/env python3
"""Fail before compilation if the QEMU SceneBoard/compositor pair is broken."""
import argparse
import json
from pathlib import Path


def validate(features, device):
    if device not in ('phone', '2in1'):
        raise ValueError('unsupported QEMU graphics profile: ' + device)
    required = {
        'window_manager_use_sceneboard': True,
        'graphic_2d_feature_rs_enable_uni_render': True,
        'graphic_2d_feature_enable_opengl': True,
        # Vulkan is provided by the separate CPU ICD/WSI. Enabling Rosen's
        # different GPU backend is not required and must not replace softpipe.
        'graphic_2d_feature_enable_vulkan': False,
    }
    failures = [f'{name}: expected {value}, got {features.get(name)!r}'
                for name, value in required.items() if features.get(name) is not value]
    if failures:
        raise ValueError('incomplete QEMU SceneBoard/compositor features: ' + '; '.join(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features', type=Path, required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    args = parser.parse_args()
    validate(json.loads(args.features.read_text())['features'], args.device)
    print(f'QEMU {args.device} SceneBoard/compositor feature pair validated')


if __name__ == '__main__':
    main()
