#!/usr/bin/env python3
"""Contracts for genuine external-input / ordinary API tests; no success defaults."""
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zipfile

FIXTURES = Path(__file__).with_name('fixtures') / 'batch_system/live_inputs'
BUNDLE = 'org.harmonycontrib.liveinputaudit'
PERMISSIONS = ['ohos.permission.ACCELEROMETER', 'ohos.permission.APPROXIMATELY_LOCATION', 'ohos.permission.LOCATION']
SOCKETS = {'gnss': '/dev/unix/socket/qemu_gnss/input', 'sensor': '/dev/unix/socket/qemu_sensor/input'}
SCOPE = 'new_package_external_input_to_ordinary_public_callbacks_NOT_all_MSDP_or_first_artifact_gate'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def unique_pairs(values):
    result = {}
    for key, value in values:
        if key in result: raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=unique_pairs,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + v)))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream: json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')


def nonce(value):
    if not isinstance(value, str) or re.fullmatch('[a-f0-9]{32}', value) is None or value == '0' * 32:
        raise ValueError('fresh externally chosen 128-bit lowercase hex run ID required')
    return value


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def f32(value):
    if not finite(value): raise ValueError('finite float32 required')
    result = struct.unpack('<f', struct.pack('<f', value))[0]
    if not math.isfinite(result): raise ValueError('float32 overflow')
    return result


def trace(path, kind):
    # Reuse the real existing sender's complete schema/range validation.
    if kind == 'gnss':
        from batch_system_gnss_controller import load_trace
    else:
        from batch_system_qemu_sensor_controller import load_trace
    read_json(path)  # Reject ambiguous duplicate fields before the shared codec.
    rows = load_trace(Path(path))
    if len(rows) > 2000 or rows[-1]['at_ms'] > 45000:
        raise ValueError('live diagnostic trace limited to2000 samples/45s')
    if kind == 'gnss':
        if any(b['at_ms'] - a['at_ms'] < 1000 for a, b in zip(rows, rows[1:])):
            raise ValueError('space actual GNSS fixes >=1000ms for ordinary callback observation')
        if len(rows) < 3 or len({(x['latitude'], x['longitude']) for x in rows}) < 3:
            raise ValueError('GNSS challenge needs at least three distinct external positions')
    else:
        # Source candidate uses an independent public TYPE_STILL instance of the
        # actual existing five-event magnitude heuristic. No physical accuracy claim.
        magnitudes = [math.sqrt(sum(f32(x[k]) ** 2 for k in ('x', 'y', 'z'))) for x in rows]
        if any(min(abs(v - 7), abs(v - 11)) < .1 for v in magnitudes):
            raise ValueError('external challenge too close to actual float32 algorithm threshold')
        if any(b['at_ms'] - a['at_ms'] < 150 for a, b in zip(rows, rows[1:])):
            raise ValueError('space actual sensor challenge >=150ms for 100100100ns algorithm subscription')
        labels = [7 < value < 11 for value in magnitudes]
        runs = []
        for label in labels:
            if not runs or runs[-1][0] != label: runs.append([label, 1])
            else: runs[-1][1] += 1
        if len(runs) < 3 or [x[0] for x in runs[:3]] != [True, False, True] or min(x[1] for x in runs) < 10:
            raise ValueError('sensor trace needs >=10 samples each in/out/in7..11m/s²; no built-in trace generated')
        if len({(x['x'], x['y'], x['z']) for x in rows}) < 12:
            raise ValueError('external sensor challenge must contain varied raw measurements')
    return rows


def sdk_contract(sdk):
    sdk = Path(sdk)
    result = {}
    anchors = {
        '@ohos.stationary.d.ts': ["'still' | 'relativeStill'", 'function on(activity: ActivityType', 'function off(activity: ActivityType'],
        '@ohos.sensor.d.ts': ['SensorId.ACCELEROMETER', 'interface AccelerometerResponse', 'timestamp: number'],
        '@ohos.geoLocationManager.d.ts': ["type: 'locationChange'", 'LocationRequestPriority', 'timeSinceBoot: number', 'GNSS = 1'],
    }
    for name, values in anchors.items():
        path = sdk / 'ets/api' / name
        text = path.read_text()
        if not all(v in text for v in values): raise ValueError('actual public SDK contract changed: ' + name)
        result[name] = digest(path)
    for part in ('ets', 'native'):
        path = sdk / part / 'oh-uni-package.json'
        value = read_json(path)
        if (str(value.get('apiVersion')) != '26' or value.get('releaseType') != 'Release' or
                value.get('platformVersion') != '26.0.0'):
            raise ValueError('actual API26 Release SDK required')
        result[part + '_metadata'] = {'sha256': digest(path), 'value': value}
    return result


def project_files(project):
    # Source/native inputs, not generated build output/cache state.
    project = Path(project)
    names = ['AppScope/app.json5', 'build-profile.json5', 'entry/src/main/module.json5',
             'entry/src/main/ets/pages/Index.ets', 'entry/src/main/ets/entryability/EntryAbility.ets',
             'socket_probe.cpp', 'entry/src/main/cpp/types/libliveinputaudit/Index.d.ts']
    return {name: digest(project / name) for name in names}


def verify_project(project, sdk, run_id, arch):
    project = Path(project)
    value = read_json(project / 'live-inputs-contract.json')
    expected = (FIXTURES / 'Index.ets.in').read_text().replace('__LIVE_RUN_ID__', nonce(run_id))
    if ((project / 'entry/src/main/ets/pages/Index.ets').read_text() != expected or
            (project / 'socket_probe.cpp').read_bytes() != (FIXTURES / 'socket_probe.cpp').read_bytes() or
            (project / 'entry/src/main/ets/entryability/EntryAbility.ets').read_bytes() != (FIXTURES / 'EntryAbility.ets').read_bytes() or
            value['source_files'] != project_files(project) or value['sdk'] != sdk_contract(sdk) or
            value['run_id'] != run_id or value['arch'] != arch or value['bundle'] != BUNDLE or
            value['fixture_hashes'] != {p.name: digest(p) for p in FIXTURES.iterdir() if p.is_file()}):
        raise ValueError('actual compiled public caller/source/SDK fixture changed')
    module = read_json(project / 'entry/src/main/module.json5')['module']
    if sorted(x['name'] for x in module['requestPermissions']) != sorted(PERMISSIONS):
        raise ValueError('ordinary HAP permissions changed')
    return value


def hap_payload(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(n.startswith('/') or '..' in Path(n).parts for n in names):
            raise ValueError('ambiguous HAP archive entries')
        return {n: hashlib.sha256(archive.read(n)).hexdigest() for n in names if not n.endswith('/') and not n.startswith('META-INF/')}


def load_rows(path, run_id):
    text = Path(path).read_text()
    if not text.endswith('\n') or len(text) > 8000000: raise ValueError('incomplete/excessive ordinary raw results')
    rows = []
    previous = 0
    for seq, line in enumerate(text.splitlines(), 1):
        row = json.loads(line, object_pairs_hook=unique_pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite callback')))
        if (set(row) != {'schema', 'run_id', 'seq', 'kind', 'generation', 'boot_ns', 'values', 'text'} or
                row['schema'] != 1 or row['run_id'] != run_id or type(row['seq']) is not int or row['seq'] != seq or
                type(row['generation']) is not int or row['generation'] not in (0, 1, 2) or
                not isinstance(row['boot_ns'], str) or re.fullmatch('[1-9][0-9]{0,19}', row['boot_ns']) is None or
                int(row['boot_ns']) < previous or not isinstance(row['values'], list) or
                any(not finite(x) for x in row['values']) or not isinstance(row['text'], str)):
            raise ValueError('malformed/stale/out-of-order actual app result')
        previous = int(row['boot_ns']); rows.append(row)
    if not rows or len(rows) > 20000: raise ValueError('missing/bounded raw app results required')
    return rows
