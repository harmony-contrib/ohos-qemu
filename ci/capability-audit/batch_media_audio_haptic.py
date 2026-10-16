#!/usr/bin/env python3
"""AudioHaptic source/data preparation and passive HDI time bounds, not a gate.

No compilation, signing, VM, HDC, permission mutation, audio output or vibration
is performed here. Root must combine actual SDK/identity/HDI/WAV/time evidence.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import struct
import wave

HERE = Path(__file__).resolve().parent
PAGE = HERE / 'batch_media_audio_haptic_probe.ets'
OBSERVER = HERE / 'batch_media_audio_haptic_hdi_observer.cpp'
SDK_CAPABILITIES = {'SystemCapability.Multimedia.AudioHaptic.Core', 'SystemCapability.Sensors.MiscDevice',
                    'SystemCapability.Multimedia.Audio.Core', 'SystemCapability.FileManagement.File.FileIO',
                    'SystemCapability.Utils.Lang', 'SystemCapability.MiscServices.Time',
                    'SystemCapability.BundleManager.BundleFramework.Core', 'SystemCapability.Security.AccessToken'}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def record(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'regular source/artifact required')
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')


def check_sdk(sdk):
    sdk = Path(sdk)
    meta = sdk / 'ets/oh-uni-package.json'
    require(json.loads(meta.read_text())['version'] == '26.0.0.105', 'actual SDK105 required')
    default = sdk / 'ets/api/device-define/default.json'
    require(SDK_CAPABILITIES <= set(json.loads(default.read_text())['SysCaps']), 'actual default profile lacks required syscaps')
    api = sdk / 'ets/api/@ohos.multimedia.audioHaptic.d.ts'
    text = api.read_text()
    for signature in ['registerSource(audioUri: string, hapticUri: string)', 'createPlayer(id: number, options?: AudioHapticPlayerOptions)',
                      'isMuted(type: AudioHapticType)', 'start(): Promise<void>', 'stop(): Promise<void>', 'release(): Promise<void>',
                      "on(type: 'audioInterrupt'", "on(type: 'endOfStream'"]:
        require(signature in text, 'actual SDK AudioHaptic API missing: '+signature)
    return {'metadata': record(meta), 'default_profile': record(default), 'audio_haptic': record(api)}


def verify_export(path):
    path = Path(path)
    value = json.loads(path.read_text())
    require(value['exit_code'] == 0 and value['scope'].startswith('actual read-only prepared product source export'), 'real fixed-source export required')
    for descriptor in value['files'].values():
        require(record(descriptor['path']) == descriptor, 'fixed source export bytes changed')
    schema = next(v for name, v in value['files'].items() if name.endswith('/schemas/oh_schema.json'))
    sample = next(v for name, v in value['files'].items() if name.endswith('/test_data/oh_no_curve_sample.json'))
    expected = json.loads(Path(sample['path']).read_text())
    require(expected['MetaData'] == {'Version': 1.0, 'ChannelNumber': 1} and
            expected['Channels'][0]['Pattern'][0]['Event']['Type'] == 'continuous', 'actual no-curve sample format changed')
    return {'export': record(path), 'schema': schema, 'sample': sample}


def haptic(duration_ms):
    require(type(duration_ms) is int and 100 <= duration_ms <= 5000, 'bounded real continuous event duration required')
    # Exactly the exported OH schema/no-curve format. One event at zero avoids
    # claiming pulse-gap support from the virtual VDI's aggregate deadline.
    return {'MetaData': {'Version': 1.0, 'ChannelNumber': 1}, 'Channels': [{'Parameters': {'Index': 0},
            'Pattern': [{'Event': {'Type': 'continuous', 'StartTime': 0, 'Duration': duration_ms,
                                 'Parameters': {'Intensity': 80, 'Frequency': 50}}}]}]}


def prepare(output, sdk, source_export):
    proof = check_sdk(sdk)
    source = verify_export(source_export)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    run = secrets.token_hex(16)
    cases = {}
    for case, audio_ms, haptic_ms in [('expiry', 3000, 600+secrets.randbelow(6)*100), ('stop', 6000, 4000)]:
        path = output / f'{run}-{case}.wav'
        chips = [[secrets.choice((-1, 1)) for _ in range(audio_ms//20+1)] for _ in range(2)]
        data = bytearray()
        for index in range(48*audio_ms):
            pair = [round(10000*chips[channel][index//960]*math.sin(2*math.pi*frequency*index/48000))
                    for channel, frequency in enumerate((700, 1100))]
            data.extend(struct.pack('<hh', *pair))
        with wave.open(str(path), 'wb') as stream:
            stream.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            stream.writeframes(data)
        json_path = output / f'{run}-{case}.json'
        write(json_path, haptic(haptic_ms))
        cases[case] = {'audio': record(path), 'haptic': record(json_path), 'audio_duration_ms': audio_ms,
                       'haptic_duration_ms': haptic_ms, 'haptic_start_ms': 0,
                       'pcm_sha256': hashlib.sha256(data).hexdigest(), 'frames': 48*audio_ms}
    page = output / 'Index.ets'
    write(page, PAGE.read_text().replace('__AUDIO_HAPTIC_RUN__', run))
    value = {'schema_version': 1, 'scope': 'source_and_external_challenges_ONLY_NOT_audio_haptic_runtime',
             'run_id': run, 'sdk': proof, 'fixed_source': source, 'page': record(page), 'template': record(PAGE),
             'observer_source': record(OBSERVER), 'cases': cases, 'pcm': {'sample_rate': 48000, 'channels': 2, 'bits': 16},
             'required_profile': {'apl': 'normal', 'app_feature': 'hos_normal_app', 'allowed_acls': [], 'restricted_permissions': []},
             'positive_permissions': ['ohos.permission.VIBRATE'], 'denied_permissions': [],
             'runtime_validated': False, 'first_artifact_behavior_gate_passed': False, 'ledger_closed': False}
    write(output / 'challenge.json', value)
    return output / 'challenge.json'


def project(output, challenge, sdk, *, denied=False):
    """Complete ordinary default-profile API26 source project; never builds/signs."""
    proof = check_sdk(sdk)
    data = json.loads(Path(challenge).read_text())
    require(re.fullmatch('[a-f0-9]{32}', data['run_id']), 'challenge run nonce required')
    require(record(PAGE) == data['template'] and record(data['page']['path']) == data['page'], 'frozen real page changed')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    bundle = 'org.harmonycontrib.audiohapticdenied' if denied else 'org.harmonycontrib.audiohaptic'
    permissions = [] if denied else ['ohos.permission.VIBRATE']
    def put(name, value):
        write(output/name, value)
    put('AppScope/app.json5', {'app': {'bundleName': bundle, 'vendor': 'Harmony Contrib', 'versionCode': 1,
        'versionName': '1.0.0', 'label': '$string:app_name', 'icon': '$media:app_icon'}})
    put('AppScope/resources/base/element/string.json', {'string': [{'name': 'app_name', 'value': 'Audio haptic actual API audit'}]})
    put('AppScope/resources/base/media/app_icon.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#493d82"/></svg>\n')
    put('build-profile.json5', {'app': {'products': [{'name': 'default', 'compileSdkVersion': '26.0.0',
        'compatibleSdkVersion': '26.0.0', 'targetSdkVersion': '26.0.0', 'runtimeOS': 'OpenHarmony'}]},
        'modules': [{'name': 'entry', 'srcPath': './entry', 'targets': [{'name': 'default', 'applyToProducts': ['default']}]}]})
    put('oh-package.json5', {'modelVersion': '6.0.0', 'name': 'audio-haptic-audit', 'version': '1.0.0', 'dependencies': {}, 'devDependencies': {}})
    put('hvigor/hvigor-config.json5', {'modelVersion': '6.0.0', 'dependencies': {}, 'execution': {'daemon': False, 'parallel': False}})
    put('hvigorfile.ts', "import { appTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: appTasks, plugins: [] };\n")
    put('entry/hvigorfile.ts', "import { hapTasks } from '@ohos/hvigor-ohos-plugin';\nexport default { system: hapTasks, plugins: [] };\n")
    put('entry/build-profile.json5', {'apiType': 'stageMode', 'targets': [{'name': 'default'}]})
    put('entry/oh-package.json5', {'name': 'entry', 'version': '1.0.0', 'dependencies': {}})
    put('entry/src/main/module.json5', {'module': {'name': 'entry', 'type': 'entry', 'mainElement': 'EntryAbility',
        'deviceTypes': ['default'], 'deliveryWithInstall': True, 'installationFree': False, 'pages': '$profile:main_pages',
        'requestPermissions': [{'name': p} for p in permissions], 'abilities': [{'name': 'EntryAbility',
        'srcEntry': './ets/entryability/EntryAbility.ets', 'launchType': 'singleton', 'exported': True,
        'label': '$string:app_name', 'icon': '$media:app_icon', 'startWindowIcon': '$media:app_icon',
        'startWindowBackground': '$color:start_window_background'}]}})
    put('entry/src/main/resources/base/element/color.json', {'color': [{'name': 'start_window_background', 'value': '#FFFFFF'}]})
    put('entry/src/main/resources/base/profile/main_pages.json', {'src': ['pages/Index']})
    put('entry/src/main/ets/pages/Index.ets', Path(data['page']['path']).read_text())
    put('entry/src/main/ets/entryability/EntryAbility.ets', "import UIAbility from '@ohos.app.ability.UIAbility';\nimport window from '@ohos.window';\nexport default class EntryAbility extends UIAbility {\n  onWindowStageCreate(stage: window.WindowStage): void { stage.loadContent('pages/Index'); }\n}\n")
    manifest = {'schema_version': 1, 'bundle_name': bundle, 'run_id': data['run_id'], 'requested_permissions': permissions,
                'sdk': proof, 'challenge': record(challenge), 'template': record(PAGE), 'generator': record(Path(__file__)),
                'required_apl': 'normal', 'required_system_app': False, 'allowed_acls': [], 'restricted_permissions': [],
                'source_hashes': {str(p.relative_to(output)): record(p)['sha256'] for p in sorted(output.rglob('*')) if p.is_file()},
                'runtime_validated': False, 'ledger_closed': False}
    put('audio-haptic-source-manifest.json', manifest)
    return output/'audio-haptic-source-manifest.json'


def parse_hdi(raw, run, boot, exit_code):
    """Check only actual passive HDI rows, preserving IPC and timing uncertainty."""
    require(type(exit_code) is int and exit_code == 0, 'actual observer exited nonzero')
    require(re.fullmatch('[a-f0-9]{32}', run) and re.fullmatch('[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', boot), 'real run/boot identity required')
    require(isinstance(raw, str) and 0 < len(raw.encode()) <= 8388608 and raw.endswith('\n'), 'complete bounded observer JSONL required')
    rows = [json.loads(line) for line in raw.splitlines()]
    require(3 <= len(rows) <= 15002, 'bounded complete HDI stream required')
    begin, complete = rows[0], rows[-1]
    require(set(begin) == {'schema_version', 'kind', 'run_id', 'boot_id', 'device_id', 'vibrator_id', 'uid',
            'duration_ms', 'period_ms', 'before_ns', 'after_ns', 'result', 'time_delay', 'hd_haptic', 'preset_mapping'} and
            set(complete) == {'schema_version', 'kind', 'run_id', 'boot_id', 'samples'}, 'exact observer envelopes required')
    for row in rows:
        require(type(row.get('schema_version')) is int and row['schema_version'] == 1 and
                row.get('run_id') == run and row.get('boot_id') == boot, 'old/mixed observer identity')
    require(begin['kind'] == 'begin' and complete['kind'] == 'complete' and type(begin['uid']) is int and begin['uid'] == 0 and
            type(begin['device_id']) is int and begin['device_id'] == 0 and type(begin['vibrator_id']) is int and
            begin['vibrator_id'] == 0 and type(begin['result']) is int and begin['result'] == 0 and
            begin['time_delay'] is True and begin['hd_haptic'] is False and begin['preset_mapping'] is False, 'actual virtual TIME capacity observation required')
    require(type(begin['duration_ms']) is int and 100 <= begin['duration_ms'] <= 60000 and
            type(begin['period_ms']) is int and 5 <= begin['period_ms'] <= 100 and begin['period_ms'] < begin['duration_ms'], 'invalid bounded observer cadence')
    require(type(begin['before_ns']) is int and type(begin['after_ns']) is int and
            0 < begin['before_ns'] <= begin['after_ns'], 'actual initial clock brackets required')
    previous = begin['after_ns']
    samples = rows[1:-1]
    for index, row in enumerate(samples, 1):
        require(set(row) == {'schema_version', 'kind', 'run_id', 'boot_id', 'sequence', 'before_ns', 'after_ns', 'result', 'running'}, 'exact getter sample required')
        require(row['kind'] == 'sample' and type(row['sequence']) is int and row['sequence'] == index and
                type(row['result']) is int and row['result'] == 0 and type(row['running']) is bool, 'failed/reordered actual HDI getter')
        require(type(row['before_ns']) is int and type(row['after_ns']) is int and
                0 < previous <= row['before_ns'] <= row['after_ns'], 'unbracketed/backwards actual clock')
        previous = row['after_ns']
    require(type(complete['samples']) is int and complete['samples'] == len(samples) and
            previous-begin['after_ns'] >= begin['duration_ms']*1000000, 'observer did not finish its declared real interval')
    return samples


def parse_hap(raw, run, boot, uid):
    """Return actual public API rows. Never equate a return to real output."""
    require(isinstance(raw, str) and 0 < len(raw.encode()) <= 8388608 and raw.endswith('\n'), 'complete bounded actual HAP journal required')
    rows, seen, active = [], set(), None
    keys = {'schema_version', 'run_id', 'boot_id', 'operation_id', 'sequence', 'uid', 'event', 'api',
            'before_ns', 'after_ns', 'value_json', 'error_code', 'error_message'}
    for line in raw.splitlines():
        row = json.loads(line)
        require(set(row) == keys and type(row['schema_version']) is int and row['schema_version'] == 1 and
                row['run_id'] == run and row['boot_id'] == boot and type(row['uid']) is int and row['uid'] == uid and
                type(row['sequence']) is int and row['sequence'] == len(rows)+1 and re.fullmatch('[a-f0-9]{32}', row['operation_id']), 'stale/mixed/reordered HAP identity')
        require(type(row['before_ns']) is int and type(row['after_ns']) is int and
                0 < row['before_ns'] <= row['after_ns'] < 2**53 and type(row['error_code']) is int and
                isinstance(row['error_message'], str) and isinstance(row['value_json'], str), 'actual safe ACTIVE clock/API error fields required')
        require(row['event'] in ('begin', 'token', 'return', 'getters', 'callbacks', 'complete', 'error'), 'unknown public API observation')
        if row['event'] != 'error':
            require(row['error_code'] == 0 and row['error_message'] == '', 'return/callback hides an API error')
        row['value'] = json.loads(row['value_json'])
        if row['event'] == 'begin':
            require(active is None and row['operation_id'] not in seen, 'reused/interleaved HAP operation')
            seen.add(row['operation_id']); active = row['operation_id']
        require(active == row['operation_id'], 'API result outside its actual request')
        if row['event'] in ('complete', 'error'):
            active = None
        if row['event'] == 'callbacks':
            value = row['value']
            require(type(value['overflow']) is int and value['overflow'] == 0 and isinstance(value['events'], list) and len(value['events']) <= 128, 'callback overflow is not complete evidence')
            for event in value['events']:
                require(event['kind'] in ('endOfStream', 'audioInterrupt') and event['released'] is False and
                        type(event['monotonic_ns']) is int and 0 < event['monotonic_ns'] <= row['after_ns'] and
                        type(event['generation']) is int and event['generation'] > 0 and
                        all(type(event[key]) is int for key in ('event_type', 'force_type', 'hint_type')), 'invalid/late actual callback')
        rows.append(row)
    require(active is None, 'incomplete public API request')
    return rows


def time_episodes(samples):
    require(len(samples) >= 3 and samples[0]['running'] is False and samples[-1]['running'] is False,
            'real idle observations before and after playback required')
    episodes, start = [], None
    for previous, current in zip(samples, samples[1:]):
        if previous['running'] == current['running']:
            continue
        # Query takes effect somewhere within before..after. Do not tighten an
        # edge to after(previous) or before(current): those bounds are unsound.
        edge = [previous['before_ns'], current['after_ns']]
        if current['running']:
            start = edge
        else:
            require(start is not None, 'unmatched TIME stop')
            episodes.append({'start_ns': start, 'end_ns': edge,
                             'duration_ns': [max(0, edge[0]-start[1]), edge[1]-start[0]]})
            start = None
    require(start is None, 'TIME effect still active')
    return episodes


def alignment_bounds(haptic_start, audio_start):
    for bounds in (haptic_start, audio_start):
        require(isinstance(bounds, (list, tuple)) and len(bounds) == 2 and
                all(type(v) is int and v >= 0 for v in bounds) and bounds[0] <= bounds[1], 'actual finite clock bounds required')
    return {'haptic_minus_audio_ns': [haptic_start[0]-audio_start[1], haptic_start[1]-audio_start[0]],
            'haptic_uncertainty_ns': haptic_start[1]-haptic_start[0],
            'audio_uncertainty_ns': audio_start[1]-audio_start[0], 'full_runtime_gate': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    prepare_cli = sub.add_parser('prepare')
    prepare_cli.add_argument('--sdk', type=Path, required=True)
    prepare_cli.add_argument('--source-export', type=Path, required=True)
    prepare_cli.add_argument('--output', type=Path, required=True)
    project_cli = sub.add_parser('project')
    project_cli.add_argument('--sdk', type=Path, required=True)
    project_cli.add_argument('--challenge', type=Path, required=True)
    project_cli.add_argument('--denied', action='store_true')
    project_cli.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        print(prepare(args.output, args.sdk, args.source_export))
    else:
        print(project(args.output, args.challenge, args.sdk, denied=args.denied))


if __name__ == '__main__':
    main()
