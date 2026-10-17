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
JOURNAL_SCHEMA = 2
JOURNAL_FIELDS = {'schema', 'run_id', 'seq', 'kind', 'generation', 'boot_ns', 'values', 'text'}
JOURNAL_KINDS = {'ready', 'socket_denials', 'permissions', 'error', 'start', 'subscribed', 'start_complete',
                 'location', 'sensor', 'still', 'stop_begin', 'stopped', 'quiet_marker', 'finished',
                 'location_switch_query', 'location_switch_state'}
LOCATION_SWITCH_API = 'geoLocationManager.isLocationEnabled'
LOCATION_SWITCH_CONTROL = 'live-location-switch-state'
SDK_PRODUCT = {'name': 'default', 'compileSdkVersion': '26.0.0', 'compatibleSdkVersion': '26.0.0',
               'targetSdkVersion': '26.0.0', 'runtimeOS': 'OpenHarmony'}
HVIGOR_CONFIG = {'modelVersion': '6.0.0', 'dependencies': {}, 'execution': {'daemon': False, 'parallel': False}}
HVIGOR_APP = "import { appTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: appTasks, plugins: [] };\n"
HVIGOR_HAP = "import { hapTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: hapTasks, plugins: [] };\n"
ENTRY_PROFILE = {'apiType': 'stageMode', 'targets': [{'name': 'default'}]}
NATIVE_TARGETS = {'arm64': ('arm64-v8a', 'aarch64-linux-ohos'),
                  'armv7a': ('armeabi-v7a', 'arm-linux-ohos'), 'x86_64': ('x86_64', 'x86_64-linux-ohos')}


def native_packaging(arch):
    return {'mode': 'prebuilt', 'relative_library': 'entry/libs/' + NATIVE_TARGETS[arch][0] + '/libliveinputaudit.so'}


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
        '@ohos.geoLocationManager.d.ts': ["type: 'locationChange'", 'LocationRequestPriority', 'timeSinceBoot: number', 'GNSS = 1', 'function isLocationEnabled('],
    }
    for name, values in anchors.items():
        path = sdk / 'ets/api' / name
        text = path.read_text()
        if not all(v in text for v in values): raise ValueError('actual public SDK contract changed: ' + name)
        if name == '@ohos.geoLocationManager.d.ts' and re.search(r'function\s+isLocationEnabled\(\s*\)\s*:\s*boolean\s*;', text) is None:
            raise ValueError('actual SDK lacks the public synchronous boolean switch query')
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
    names = ['AppScope/app.json5', 'build-profile.json5', 'oh-package.json5', 'entry/oh-package.json5',
             'entry/build-profile.json5', 'hvigor/hvigor-config.json5', 'hvigorfile.ts', 'entry/hvigorfile.ts',
             'entry/src/main/cpp/types/libliveinputaudit/oh-package.json5', 'entry/src/main/module.json5',
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
    if (read_json(project / 'build-profile.json5')['app']['products'] != [SDK_PRODUCT] or
            read_json(project / 'hvigor/hvigor-config.json5') != HVIGOR_CONFIG or
            (project / 'hvigorfile.ts').read_text() != HVIGOR_APP or
            (project / 'entry/hvigorfile.ts').read_text() != HVIGOR_HAP):
        raise ValueError('actual OpenHarmony API26/Hvigor6 build configuration changed')
    if read_json(project / 'entry/build-profile.json5') != ENTRY_PROFILE:
        raise ValueError('actual prebuilt native module configuration changed')
    if (value.get('native_packaging') != native_packaging(arch) or
            (value.get('abi'), value.get('triple')) != NATIVE_TARGETS[arch]):
        raise ValueError('actual prebuilt native packaging contract changed')
    module = read_json(project / 'entry/src/main/module.json5')['module']
    if sorted(x['name'] for x in module['requestPermissions']) != sorted(PERMISSIONS):
        raise ValueError('ordinary HAP permissions changed')
    return value


def verify_signed_payload(unsigned, signed):
    """Use the shared exact member/bitmap contract on real SDK and signed HAPs."""
    from batch_apps_contact_picker_coordinator import verify_signed_payload as shared
    return shared(unsigned, signed)


def hap_payload(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(n.startswith('/') or '..' in Path(n).parts for n in names):
            raise ValueError('ambiguous HAP archive entries')
        return {n: hashlib.sha256(archive.read(n)).hexdigest() for n in names if not n.endswith('/') and not n.startswith('META-INF/')}


class JournalSchemaError(ValueError):
    """Actual journal is malformed; callers must not turn this into a timeout."""


class OrdinaryApiError(ValueError):
    """Actual API errors with their original string/integer code representation."""
    def __init__(self, rows, context):
        self.rows = tuple(rows)
        details = [{'schema': r['schema'], 'seq': r['seq'], 'generation': r['generation'],
                    'operation': r['text'], 'raw_values': r['values'],
                    **({'error': r['error']} if 'error' in r else {})} for r in rows]
        super().__init__(context + ': actual ordinary API error(s): ' +
                         json.dumps(details, ensure_ascii=False, allow_nan=False))


def require_no_api_errors(rows, context='ordinary public acceptance'):
    errors = [row for row in rows if row['kind'] == 'error']
    if errors:
        raise OrdinaryApiError(errors, context)


def _error_payload(row):
    if not row['text']:
        raise JournalSchemaError('error operation is missing')
    if row['schema'] == 1:
        # Retain genuine C1 ["3301100"] verbatim. This is diagnostic readability,
        # never an API success or a string-to-number conversion.
        values = row['values']
        if len(values) > 1 or any(type(v) not in (str, int) for v in values):
            raise JournalSchemaError('legacy error code must retain its string/integer type')
        return
    detail = row['error']
    if not isinstance(detail, dict):
        raise JournalSchemaError('typed error object required')
    optional = {'name', 'message'}
    required = {'code_type', 'operation'}
    extra = {'string': {'raw_code_string'}, 'number': {'raw_code_number'}, 'undefined': set(),
             'unsupported': {'raw_code_type', 'raw_code_text', 'raw_error_json'}}
    kind = detail.get('code_type')
    if (kind not in extra or not (required | extra[kind]) <= set(detail) or
            set(detail) - required - extra[kind] - optional):
        raise JournalSchemaError('typed error fields disagree with its original code type')
    if detail['operation'] != row['text'] or any(type(detail[k]) is not str for k in optional & detail.keys()):
        raise JournalSchemaError('typed error operation/name/message differs')
    if kind == 'string' and type(detail['raw_code_string']) is not str:
        raise JournalSchemaError('raw string API code was changed')
    if kind == 'number' and type(detail['raw_code_number']) is not int:
        raise JournalSchemaError('raw integer API code was changed')
    if kind == 'unsupported' and any(type(detail[k]) is not str for k in extra[kind]):
        raise JournalSchemaError('unsupported API error must preserve its raw diagnostic representation')
    if not all(finite(value) for value in row['values']):
        raise JournalSchemaError('typed error context must remain numeric')
    if row['text'] != LOCATION_SWITCH_API and row['values']:
        raise JournalSchemaError('unexpected typed error context')


def _switch_queries(rows):
    pending, completed = {}, set()
    for row in rows:
        if row['kind'] == 'location_switch_query':
            values = row['values']
            if (row['schema'] != JOURNAL_SCHEMA or row['text'] != LOCATION_SWITCH_API or len(values) != 1 or
                    type(values[0]) is not int or values[0] != len(pending) + 1):
                raise JournalSchemaError('public switch query ID/operation differs')
            pending[values[0]] = row
        elif row['kind'] == 'location_switch_state' or row['kind'] == 'error' and row['text'] == LOCATION_SWITCH_API:
            values = row['values']
            if (row['schema'] != JOURNAL_SCHEMA or len(values) != 2 or any(type(v) is not int for v in values) or
                    values[0] not in pending or values[0] in completed):
                raise JournalSchemaError('public switch response has no unique query')
            before = pending[values[0]]
            if (row['text'] != LOCATION_SWITCH_API or values[1] != before['seq'] or before['seq'] >= row['seq'] or
                    row['generation'] != before['generation']):
                raise JournalSchemaError('public switch response changed before sequence/generation')
            completed.add(values[0])
    return pending, completed


def switch_observations(rows, require_complete=False):
    pending, completed = _switch_queries(rows)
    if require_complete and set(pending) != completed:
        raise JournalSchemaError('public switch query did not produce a state/error response')
    return [{'request_id': row['values'][0], 'before_seq': row['values'][1], 'after_seq': row['seq'],
             'generation': row['generation'], 'location_enabled': row['location_enabled'],
             'operation': row['text'], 'boot_ns': row['boot_ns']} for row in rows if row['kind'] == 'location_switch_state']


def parse_rows(text, run_id):
    if not text or not text.endswith('\n') or len(text) > 8000000:
        raise JournalSchemaError('incomplete/excessive ordinary raw results')
    rows, previous, schema = [], 0, None
    for seq, line in enumerate(text.splitlines(), 1):
        try:
            row = json.loads(line, object_pairs_hook=unique_pairs,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite callback')))
            if not isinstance(row, dict):
                raise ValueError('journal row is not an object')
            version = row.get('schema')
            kind = row.get('kind')
            fields = JOURNAL_FIELDS | ({'error'} if version == 2 and kind == 'error' else set())
            fields |= {'location_enabled'} if version == 2 and kind == 'location_switch_state' else set()
            if (set(row) != fields or type(version) is not int or version not in (1, JOURNAL_SCHEMA) or
                    schema is not None and version != schema or kind not in JOURNAL_KINDS or
                    row['run_id'] != run_id or type(row['seq']) is not int or row['seq'] != seq or
                    type(row['generation']) is not int or row['generation'] not in (0, 1, 2) or
                    not isinstance(row['boot_ns'], str) or re.fullmatch('[1-9][0-9]{0,19}', row['boot_ns']) is None or
                    int(row['boot_ns']) < previous or not isinstance(row['values'], list) or not isinstance(row['text'], str)):
                raise ValueError('malformed/stale/out-of-order actual app result')
            if kind == 'error':
                _error_payload(row)
            elif any(not finite(value) for value in row['values']):
                raise ValueError('non-error values must remain finite numbers')
            if kind == 'location_switch_state' and type(row['location_enabled']) is not bool:
                raise ValueError('public isLocationEnabled result must remain an original boolean')
            previous, schema = int(row['boot_ns']), version
            rows.append(row)
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            raise JournalSchemaError('actual journal schema error at seq ' + str(seq) + ': ' + str(error)) from error
    if not rows or len(rows) > 20000:
        raise JournalSchemaError('missing/bounded raw app results required')
    _switch_queries(rows)
    return rows


def load_rows(path, run_id):
    return parse_rows(Path(path).read_text(), run_id)
