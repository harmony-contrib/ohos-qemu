#!/usr/bin/env python3
"""Strict raw behavior oracle. Never closes capability IDs or proves an image/Owner.

The parent must correlate the provider input with its original same-boot GNSS
wire/HDI windows, real geocoder exchange or independent BLE-controller capture.
This module neither starts resources nor accepts a supplied `passed` boolean.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

PROFILES = {
    'icon': ['icon', 'track-start', 'quiet', 'icon', 'track-stop', 'quiet', 'icon', 'cleanup', 'quiet'],
    'district': ['district', 'cleanup', 'quiet'],
    'track': ['track-start', 'quiet', 'track-stop', 'track-read', 'track-read', 'cleanup', 'quiet'],
    'fence': ['fence-add', 'quiet', 'fence-remove', 'quiet', 'fence-remove', 'cleanup', 'quiet'],
    'ble': ['ble-start-a', 'ble-start-b', 'quiet', 'ble-stop-a', 'quiet', 'ble-stop-all', 'quiet', 'cleanup', 'quiet'],
    'invalid': ['district-invalid', 'track-invalid', 'fence-invalid', 'cleanup', 'quiet'],
    'ordinary': ['icon', 'supported', 'fence-add', 'fence-remove', 'cleanup', 'quiet'],
    'denied': ['district', 'track-read', 'fence-add', 'ble-start-a', 'cleanup', 'quiet'],
    'switch-off': ['district', 'track-read', 'cleanup', 'quiet'],
    'supported': ['supported', 'cleanup', 'quiet'],
}
FIELDS = {'schema', 'run_id', 'boot_id', 'operation_id', 'action', 'seq', 'monotonic_ms', 'pid', 'uid', 'kind', 'code', 'value_json'}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'Duplicate JSON key: ' + key)
        out[key] = value
    return out

def decode(text):
    def forbidden(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(text, object_pairs_hook=unique, parse_constant=forbidden)

def number(n):
    return type(n) in (int, float) and math.isfinite(n)

def rows_from_text(text, run, boot, pid, uid):
    require(len(text.encode()) <= 16 * 1024 * 1024 and text.endswith('\n'), 'Raw truncated/oversized journal')
    rows = []
    previous = -1
    for line in text.splitlines():
        require(0 < len(line) <= 262144, 'Raw line limit')
        row = decode(line)
        require(type(row) is dict and set(row) == FIELDS, 'Raw field set')
        require(row['schema'] == 1 and row['run_id'] == run and row['boot_id'] == boot and
                row['pid'] == pid and row['uid'] == uid, 'Foreign run/boot/process/UID')
        require(type(row['seq']) is int and row['seq'] == len(rows) + 1, 'Raw sequence gap/duplicate')
        require(type(row['monotonic_ms']) is int and row['monotonic_ms'] >= previous, 'Raw time regression')
        require(type(row['operation_id']) is str and re.fullmatch('[a-f0-9]{32}', row['operation_id']), 'Operation nonce')
        require(row['kind'] in ('begin', 'return', 'throw', 'end', 'location', 'fence', 'ble', 'cleanup-step'), 'Unknown raw kind')
        require(type(row['code']) is int and type(row['value_json']) is str, 'Raw code/value type')
        row['value'] = decode(row['value_json'])
        previous = row['monotonic_ms']
        rows.append(row)
    require(rows, 'Empty raw journal')
    return rows

def distance(a, b):
    p, q = math.radians(a['latitude']), math.radians(b['latitude'])
    dl = math.radians(math.remainder(b['longitude'] - a['longitude'], 360))
    h = math.sin((q - p) / 2) ** 2 + math.cos(p) * math.cos(q) * math.sin(dl / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, max(0, h))))

def point(p):
    require(type(p) is dict and all(k in p for k in ('latitude', 'longitude', 'altitude', 'accuracy', 'timeSinceBoot')), 'Missing actual point fields')
    require(all(number(p[k]) for k in ('latitude', 'longitude', 'altitude', 'accuracy')) and
            abs(p['latitude']) <= 90 and abs(p['longitude']) <= 180 and p['accuracy'] >= 0 and
            type(p['timeSinceBoot']) is int and p['timeSinceBoot'] > 0, 'Invalid measured point')

def processed_track(points):
    """Independent numeric oracle for the current patch's measured-GNSS filter.

    Only call with the exact original native trace's actual accepted GNSS inputs,
    before filter processing, in the same registration interval and token scope.
    Public callbacks can already be throttled; they are not the input oracle.
    """
    result = []
    variance = 0.0
    for raw in points:
        point(raw)
        current = dict(raw)
        measurement = max(1, raw['accuracy'] ** 2)
        if result:
            last = result[-1]
            dt = (raw['timeSinceBoot'] - last['timeSinceBoot']) / 1e9
            if dt <= 0 or distance(last, raw) > max(120 * dt, 3 * (raw['accuracy'] + last['accuracy'])):
                continue
            if dt <= 60:
                prior = variance + 36 * dt * dt
                gain = min(.95, max(.2, prior / (prior + measurement)))
                current['latitude'] = last['latitude'] + gain * (raw['latitude'] - last['latitude'])
                current['longitude'] = math.remainder(last['longitude'] + gain * math.remainder(raw['longitude'] - last['longitude'], 360), 360)
                current['altitude'] = last['altitude'] + gain * (raw['altitude'] - last['altitude'])
                variance = (1 - gain) * prior
                current['accuracy'] = math.sqrt(variance)
                current['speed'] = distance(last, current) / dt
                dl = math.radians(math.remainder(current['longitude'] - last['longitude'], 360))
                p, q = math.radians(last['latitude']), math.radians(current['latitude'])
                current['direction'] = (math.degrees(math.atan2(math.sin(dl) * math.cos(q),
                    math.cos(p) * math.sin(q) - math.sin(p) * math.cos(q) * math.cos(dl))) + 360) % 360
            else:
                variance = measurement
        else:
            variance = measurement
        result.append(current)
    return result

def review(rows, profile, provider):
    require(profile in PROFILES, 'Unknown fixed profile')
    begins = [r for r in rows if r['kind'] == 'begin']
    require([r['action'] for r in begins] == PROFILES[profile], 'Incomplete or extra operation sequence')
    require(len({r['operation_id'] for r in begins}) == len(begins), 'Operation replay')
    require(all(r['operation_id'] in {b['operation_id'] for b in begins} for r in rows), 'Unbound raw operation')
    require(all(b['value'].get('run_id') == b['run_id'] and b['value'].get('boot_id') == b['boot_id'] and
                b['value'].get('operation_id') == b['operation_id'] and b['value'].get('action') == b['action']
                for b in begins), 'Command/raw identity mismatch')
    require(all(r['code'] == 0 for r in rows if r['kind'] == 'cleanup-step'), 'Actual release failed')
    require(all(r['code'] == 0 for r in rows if r['kind'] in ('begin', 'end')), 'Control row error code')
    operations = []
    for i, begin in enumerate(begins):
        rs = [r for r in rows if r['operation_id'] == begin['operation_id']]
        ends = [r for r in rs if r['kind'] == 'end']
        terminals = [r for r in rs if r['kind'] in ('return', 'throw')]
        require(len(ends) == len(terminals) == 1 and begin['seq'] < terminals[0]['seq'] < ends[0]['seq'], 'Unfinished/duplicate operation')
        require(all(r['action'] == begin['action'] for r in rs), 'Callback action identity drift')
        if i + 1 < len(begins):
            require(ends[0]['seq'] < begins[i + 1]['seq'], 'Concurrent/reordered command')
        if begin['action'] == 'quiet':
            wait = begin['value']['wait_ms']
            require(type(wait) is int and 1000 <= wait <= 30000 and ends[0]['monotonic_ms'] - begin['monotonic_ms'] >= wait, 'Quiet window did not actually elapse')
        operations.append((begin, terminals[0], ends[0]))
    errors = {'invalid': {'district-invalid': 401, 'track-invalid': 3301200, 'fence-invalid': 401},
              'ordinary': {'icon': 202, 'supported': 202, 'fence-add': 202, 'fence-remove': 202},
              'denied': {'district': 201, 'track-read': 201, 'fence-add': 201, 'ble-start-a': 201},
              'switch-off': {'district': 3301100, 'track-read': 3301100}}.get(profile, {})
    for index, (begin, terminal, end) in enumerate(operations):
        code = errors.get(begin['action'], 0)
        if profile == 'fence' and index == 4:
            code = 3301602
        require(terminal['code'] == code and terminal['kind'] == ('throw' if code else 'return'), 'Wrong API outcome for ' + begin['action'])
    cleanup = [o for o in operations if o[0]['action'] == 'cleanup'][0]
    require(not any(r['kind'] in ('location', 'ble', 'fence') and r['seq'] > cleanup[1]['seq'] for r in rows), 'Native callback after cleanup acknowledgement')
    callbacks = [r for r in rows if r['kind'] in ('location', 'fence', 'ble')]
    require(all(r['code'] == 0 for r in callbacks), 'Actual callback carried an error')
    if profile == 'supported':
        require(operations[0][1]['value'] is True, 'Fusion support positive path absent')
    if profile == 'icon':
        require([o[1]['value'] for o in operations if o[0]['action'] == 'icon'] == [0, 1, 0], 'Live normal icon lifecycle mismatch')
        require(any(r['kind'] == 'location' for r in callbacks), 'No actual normal GNSS callback')
    if profile == 'district':
        value = operations[0][1]['value']
        allowed = {'locale', 'countryCode', 'countryName', 'administrativeArea', 'subAdministrativeArea', 'locality', 'subLocality'}
        require(type(value) is dict and set(value) <= allowed and set(value) - {'locale'} and
                all(type(v) is str and v for v in value.values()), 'Empty/invalid district result')
        require(provider.get('district') == value, 'District not equal to independent actual reverse-geocoder response')
    if profile in ('track', 'icon', 'fence'):
        require(type(provider.get('gnss')) is list and len(provider['gnss']) >= 2, 'Independent actual native GNSS inputs required')
        for p in provider['gnss']:
            point(p)
            require(p.get('isFromMock') is False and p.get('sourceType') == 1, 'Mock/non-GNSS native input')
        for r in callbacks:
            if r['kind'] == 'location':
                p = r['value']; point(p)
                require(p.get('isFromMock') is False and any(
                    p['timeSinceBoot'] == q['timeSinceBoot'] and all(abs(p[k] - q[k]) <= 1e-7 for k in ('latitude', 'longitude', 'accuracy'))
                    for q in provider['gnss']), 'Public fix not correlated with actual raw GNSS')
    if profile == 'track':
        reads = [o[1]['value'] for o in operations if o[0]['action'] == 'track-read']
        expected = processed_track(provider['gnss'])
        require(type(reads[0]) is list and len(reads[0]) == len(expected) >= 2 and reads[1] == [], 'Track lost samples or replayed incremental cursor')
        for actual, expected_point in zip(reads[0], expected):
            point(actual)
            require(actual['timeSinceBoot'] == expected_point['timeSinceBoot'] and all(
                abs(actual[k] - expected_point[k]) <= (1e-6 if k == 'accuracy' else 1e-7)
                for k in ('latitude', 'longitude', 'altitude', 'accuracy')), 'Track numeric filter diverged from actual GNSS input')
            require(all(number(actual.get(k)) and number(expected_point.get(k)) and
                        abs(actual[k] - expected_point[k]) <= 1e-5 for k in ('speed', 'direction')), 'Track speed/bearing filter mismatch')
    if profile == 'fence':
        c = operations[0][0]['value']; events = [r for r in callbacks if r['kind'] == 'fence']
        require({r['value'].get('transitionEvent') for r in events} >= {1, 2}, 'No genuine ENTER and EXIT transition')
        remove = operations[2][1]
        require(all(r['seq'] < remove['seq'] and r['value'].get('identifier') == c['identifier'] and
                    r['value'].get('scene') == 4 for r in events), 'Foreign fence or queued post-remove callback')
        center = {'latitude': c['latitude'], 'longitude': c['longitude']}
        for r in events:
            candidates = [p for p in provider['gnss'] if 0 <= r['monotonic_ms'] - p['timeSinceBoot'] / 1e6 <= 5000]
            sign = -1 if r['value']['transitionEvent'] == 1 else 1
            require(candidates, 'Fence transition lacks a current actual GNSS evaluation input')
            latest = max(candidates, key=lambda p: p['timeSinceBoot'])
            require(sign * (distance(center, latest) - c['radius']) > latest['accuracy'], 'Fence transition lacks measured position outside uncertainty boundary')
    if profile == 'ble':
        captures = provider.get('ble')
        require(type(captures) is list and captures, 'Independent actual controller advertisements required')
        stop_a, stop_all = operations[3][1]['seq'], operations[5][1]['seq']
        events = [r for r in callbacks if r['kind'] == 'ble']
        a, b = operations[0][0], operations[1][0]
        require(any(r['operation_id'] == a['operation_id'] and r['seq'] < stop_a for r in events), 'Listener A never received actual scan')
        require(any(r['operation_id'] == b['operation_id'] and stop_a < r['seq'] < stop_all for r in events), 'Stopping A also removed B')
        for r in events:
            c = a['value'] if r['operation_id'] == a['operation_id'] else b['value']
            p = r['value']
            require(r['operation_id'] in (a['operation_id'], b['operation_id']) and r['seq'] < stop_all and
                    (r['operation_id'] != a['operation_id'] or r['seq'] < stop_a), 'Queued BLE callback after stop')
            require(type(p) is dict and p.get('deviceId', '').lower() in [s.lower() for s in c['device_ids']] and
                    type(p.get('rssi')) is int and p['rssi'] > c['rssi'], 'BLE ID/strict RSSI filter mismatch')
            require(any(q.get('deviceId', '').lower() == p['deviceId'].lower() and q.get('rssi') == p['rssi'] and
                        number(q.get('monotonic_ms')) and 0 <= r['monotonic_ms'] - q['monotonic_ms'] <= 5000 for q in captures), 'BLE callback not correlated with actual controller capture')
    return {'schema': 1, 'profile': profile, 'raw_behavior': 'matched', 'operations': len(operations),
            'callbacks': len(callbacks), 'capability_ids_closed': [], 'actual_sdk': None,
            'actual_package': None, 'actual_guest_gate': None,
            'scope': 'raw behavior only; parent original registered same-boot/source/provider/Owner/cleanup closure required'}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True); p.add_argument('--provider', type=Path, required=True)
    p.add_argument('--profile', choices=PROFILES, required=True); p.add_argument('--run-id', required=True)
    p.add_argument('--boot-id', required=True); p.add_argument('--pid', type=int, required=True); p.add_argument('--uid', type=int, required=True)
    a = p.parse_args()
    require(re.fullmatch('[a-f0-9]{32}', a.run_id) and re.fullmatch('[a-f0-9-]{36}', a.boot_id), 'Fresh run and boot identifiers required')
    result = review(rows_from_text(a.raw.read_text(), a.run_id, a.boot_id, a.pid, a.uid), a.profile, decode(a.provider.read_text()))
    result['raw_sha256'] = hashlib.sha256(a.raw.read_bytes()).hexdigest()
    result['provider_sha256'] = hashlib.sha256(a.provider.read_bytes()).hexdigest()
    print(json.dumps(result, sort_keys=True))

if __name__ == '__main__':
    main()
