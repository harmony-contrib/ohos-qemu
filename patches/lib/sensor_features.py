#!/usr/bin/env python3
"""Require the external HDI transport and real MSDP inputs in full QEMU profiles."""
import argparse
import json
from pathlib import Path

EXPECTED = {'drivers_peripheral_sensor_feature_community': True,
            'drivers_peripheral_sensor_feature_qemu_external': True,
            'device_status_sensor_enable': True, 'device_status_interaction_coordination': True, 'device_status_allow_mock_fallback': False}


def validate(features, device):
    if device not in ('phone', '2in1'):
        raise ValueError('full QEMU Sensor profile required')
    failures = [f'{name}: expected {value}, got {features.get(name)!r}'
                for name, value in EXPECTED.items() if features.get(name) is not value]
    if failures:
        raise ValueError('incomplete real QEMU sensor configuration: ' + '; '.join(failures))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--features', type=Path, required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    args = parser.parse_args()
    validate(json.loads(args.features.read_text())['features'], args.device)
    print('QEMU external sensor and real MSDP features validated')
