"""Explicit controlled QEMU GNSS stimulus, never a physical measurement/result.

Pure source preparation for the existing Owner's *single* negotiated QGN2
session. It does not connect, invoke a callback or write a guest/API result.
Parent must retain these source artifacts, encoded bytes, actual send times,
native trace and public journal from the newly packaged same boot.
"""
import math
import struct

def challenge(source_utc_ms):
    if type(source_utc_ms) is not int or not 1577836800000 <= source_utc_ms <= 4102444800000:
        raise ValueError('Explicit current source UTC required; never rewrite a historical capture')
    center = {'latitude': 31.25, 'longitude': 121.5}
    # Stationary, sub-accuracy edge, clear exit, return, then a teleport outlier.
    # The stimulus deliberately exercises real service logic. It does not
    # assert that any location/track/fence callback will actually be delivered.
    metres = [0, 0, 0, 18, 20, 23, 40, 60, 60, 40, 20, 0, 0, 100000, 0]
    rows = []
    for i, north in enumerate(metres):
        rows.append({'utc_ms': source_utc_ms + i * 1000,
                     'at_ms': i * 1000,
                     'latitude': center['latitude'] + north / 6371008.8 * 180 / math.pi,
                     'longitude': center['longitude'], 'altitude': 20.0,
                     'horizontal_accuracy_bits': struct.pack('>f', 2.5).hex(),
                     'horizontal_accuracy_valid': True})
    return {'schema': 1, 'source': 'controlled_virtual_QGN2_stimulus',
            'physical_receiver': False, 'public_results': None,
            'center': center, 'radius_m': 20.0, 'interval_ms': 1000,
            'measurements': rows, 'native_trace': None, 'public_journal': None}

def encoded_rows(stimulus, nonce, original_encode_precision_sample):
    if stimulus.get('source') != 'controlled_virtual_QGN2_stimulus' or stimulus.get('physical_receiver') is not False:
        raise ValueError('Stimulus provenance must remain explicitly virtual')
    if type(nonce) is not bytes or len(nonce) != 16:
        raise ValueError('Original live QGN2 session nonce required')
    return [original_encode_precision_sample(nonce, i + 1, row)
            for i, row in enumerate(stimulus['measurements'])]
