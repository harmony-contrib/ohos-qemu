"""Finite request DATA for original Owner delivery to the actual singleton HAP.

No process/SDK/HDC/QEMU calls. The existing Owner generates fresh operation IDs,
signs/installs/launches the caller, sends each JSON request using its existing
AMS launch machinery, waits for the matching raw end row and retains raw bytes.
"""
import re
from verify_location_eight_raw import PROFILES

def commands(profile, run, boot, operation_ids, stimulus, actual_ble_ids=None):
    if profile not in PROFILES or not re.fullmatch('[a-f0-9]{32}', run) or not re.fullmatch('[a-f0-9-]{36}', boot):
        raise ValueError('Unknown fixed profile or original Owner identity')
    if len(operation_ids) != len(PROFILES[profile]) or len(set(operation_ids)) != len(operation_ids) or any(
            type(s) is not str or not re.fullmatch('[a-f0-9]{32}', s) for s in operation_ids):
        raise ValueError('One fresh original Owner nonce per command required')
    if stimulus.get('source') != 'controlled_virtual_QGN2_stimulus' or stimulus.get('physical_receiver') is not False:
        raise ValueError('Explicit virtual input source required')
    if profile == 'ble' and not actual_ble_ids:
        raise ValueError('No made-up BLE device IDs: actual controller/peer discovery required')
    # A denied call deliberately uses syntactically valid negative-test data.
    # It is never called discovered or used by the positive BLE scan oracle.
    if profile == 'denied':
        if actual_ble_ids: raise ValueError('Denied permission boundary does not claim peer discovery')
        actual_ble_ids = ['02:' + ':'.join(run[n:n+2] for n in range(0,10,2))]
    center = stimulus['center']
    return [dict(run_id=run, boot_id=boot, operation_id=op, action=action,
                 identifier='loc_' + run, latitude=center['latitude'], longitude=center['longitude'],
                 radius=stimulus['radius_m'], expiration_ms=120000,
                 device_ids=actual_ble_ids or [], rssi=-80, wait_ms=20000 if profile in ('track', 'fence') else 2000)
            for action, op in zip(PROFILES[profile], operation_ids)]
