#!/usr/bin/env python3
"""Reject a QEMU ALSA HDI without named-device configuration support."""
import argparse
import json
from pathlib import Path


def validate(features, device):
    if device not in ('phone', '2in1'):
        raise ValueError('unsupported QEMU audio profile: ' + device)
    for feature in ('drivers_peripheral_audio_feature_alsa_lib', 'alsa_lib_feature_config_enable'):
        if features.get(feature) is not True:
            raise ValueError(f'incomplete QEMU ALSA features: {feature} must be true, got {features.get(feature)!r}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features', type=Path, required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    args = parser.parse_args()
    validate(json.loads(args.features.read_text())['features'], args.device)
    print(f'QEMU {args.device} ALSA HDI/config feature pair validated')


if __name__ == '__main__':
    main()
