#!/usr/bin/env python3
"""Check phone Camera HDI/VDI/config pairing, not virtual-device acceptance."""
import argparse
import json
from pathlib import Path


def validate(features, device):
    if device not in ('phone', '2in1'):
        raise ValueError('unsupported QEMU Camera profile: ' + device)
    if device == '2in1':
        # Camera.Core is outside this official profile. Keep its existing
        # libraries without turning an unvalidated backend into a declaration.
        return
    expected = {
        'drivers_peripheral_camera_feature_usb': True,
        'drivers_peripheral_camera_use_commom_usb_camera_host_config': True,
        'drivers_peripheral_camera_qemu_vivid_capture': True,
        'drivers_peripheral_camera_v4l2_emulator': False,
    }
    failures = [f'{key}: expected {value}, got {features.get(key)!r}'
                for key, value in expected.items() if features.get(key) is not value]
    if failures:
        raise ValueError('incomplete QEMU phone Camera backend configuration: ' + '; '.join(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features', type=Path, required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    args = parser.parse_args()
    validate(json.loads(args.features.read_text())['features'], args.device)
    print(f'QEMU {args.device} Camera configuration scope validated (not runtime acceptance)')


if __name__ == '__main__':
    main()
